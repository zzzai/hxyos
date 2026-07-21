import { expect, test, type Page } from "@playwright/test";

type Role = "store_employee" | "store_manager";

const RECORD_ID = "80000000-0000-0000-0000-000000000001";
const SERVICE_ID = "90000000-0000-0000-0000-000000000001";

function session(role: Role) {
  const employee = role === "store_employee";
  return {
    user: {
      account_id: employee ? "account-employee" : "account-manager",
      display_name: employee ? "李师傅" : "王店长",
    },
    active_assignment: {
      assignment_id: employee ? "assignment-employee" : "assignment-manager",
      organization: { id: "organization-e2e", name: "荷小悦" },
      store: { id: "store-e2e", name: "首店" },
      role,
      role_label: employee ? "技师" : "店长",
      capabilities: [
        "conversation:use",
        "materials:create",
        "materials:read",
        "records:create",
        "records:read",
        "services:create",
        "services:feedback",
        "services:read",
        ...(employee ? ["training:practice"] : ["services:reconcile"]),
      ],
    },
    available_assignments: [],
  };
}

function organizationRecord(text: string, assets: Array<Record<string, unknown>> = []) {
  return {
    id: RECORD_ID,
    source_types: assets.length ? ["text", "file"] : ["text"],
    preview: text || "现场资料",
    submitted_by: "当前用户",
    store_id: "store-e2e",
    captured_at: "2026-07-21T09:00:00Z",
    occurred_at: null,
    processing_status: "received",
    original: { text, assets },
    interpretation: null,
  };
}

function material(fileName = "现场记录.md") {
  return {
    id: "70000000-0000-0000-0000-000000000001",
    file_name: fileName,
    media_type: fileName.endsWith(".webm") ? "audio/webm" : "text/markdown",
    size_bytes: 24,
    status: "processing",
    receipt: { status: "已收到", message: "资料已进入待处理区。" },
    original: {
      url: "/api/v1/materials/70000000-0000-0000-0000-000000000001/content",
      can_preview: true,
    },
    understanding: {
      summary: "资料已收到，系统正在理解。",
      document_type: fileName.endsWith(".webm") ? "录音" : "门店记录",
      source_origin: "internal",
      authority_level: "working_material",
      knowledge_scale: "micro",
      domain: "store",
      parse_status: fileName.endsWith(".webm") ? "needs_multimodal" : "needs_deep_parse",
      confidence: "low",
      warnings: [],
      official_use_allowed: false,
      use_boundary: "仅作为组织资料使用。",
    },
    created_at: "2026-07-21T09:00:00Z",
    updated_at: "2026-07-21T09:00:00Z",
  };
}

function learningHome(attempts = 0) {
  return {
    next_action: {
      id: "service-boundary-v1",
      title: "回应顾客不适",
      purpose: "练习先回应感受，再说明服务边界。",
      estimated_minutes: 3,
      scenario: { customer_message: "我做完会不会马上好？" },
      response_modes: ["text"],
    },
    progress: {
      visibility: "private",
      attempts,
      mastered: [],
      practicing: ["回应顾客不适"],
      needs_attention: attempts ? ["避免承诺效果"] : [],
    },
    limitations: ["训练用于服务沟通。", "不评估或认证按摩手法。"],
  };
}

interface ApiState {
  recordRequests: Array<Record<string, unknown>>;
  messageRequests: Array<Record<string, unknown>>;
  feedbackRequests: Array<Record<string, unknown>>;
  productEvents: Array<Record<string, unknown>>;
  logoutCount: number;
}

async function installVoiceCapture(page: Page) {
  await page.addInitScript(() => {
    const stream = { getTracks: () => [{ stop: () => undefined }] };
    const mediaDevices = navigator.mediaDevices;
    Object.defineProperty(mediaDevices, "getUserMedia", {
      configurable: true,
      value: () => Promise.resolve(stream),
    });
    class FakeMediaRecorder {
      static isTypeSupported() { return true; }
      state = "inactive";
      mimeType = "audio/webm";
      ondataavailable: ((event: { data: Blob }) => void) | null = null;
      onstop: (() => void) | null = null;
      onerror: (() => void) | null = null;
      start() { this.state = "recording"; }
      stop() {
        this.state = "inactive";
        this.ondataavailable?.({ data: new Blob(["voice"], { type: "audio/webm" }) });
        this.onstop?.();
      }
    }
    Object.defineProperty(globalThis, "MediaRecorder", {
      configurable: true,
      value: FakeMediaRecorder,
    });
  });
}

async function mockStoreApi(
  page: Page,
  role: Role,
  options: { failFirstRecord?: boolean } = {},
): Promise<ApiState> {
  const state: ApiState = {
    recordRequests: [],
    messageRequests: [],
    feedbackRequests: [],
    productEvents: [],
    logoutCount: 0,
  };
  let recordAttempts = 0;
  let conversationCount = 0;
  let messageCount = 0;

  await page.route("**/api/v1/me", (route) =>
    route.fulfill({ status: 200, json: session(role) }),
  );
  await page.route("**/api/v1/today?*", (route) =>
    route.fulfill({
      status: 200,
      json: {
        items: [
          {
            id: "brief-one",
            kind: "risk",
            severity: "high",
            statement: "接待区物料今天需要复核",
            why_it_matters: "避免开业后影响顾客接待",
            source_record_id: RECORD_ID,
            evidence: [
              {
                source_record_id: RECORD_ID,
                source_asset_id: null,
                quote: "接待区物料待复核",
                locator: null,
              },
            ],
            captured_at: "2026-07-21T08:00:00Z",
            next_action: { type: "open_record", label: "查看依据", prompt: null },
          },
        ],
        role_action:
          role === "store_manager"
            ? {
                type: "closing_review",
                label: "记录闭店复盘",
                prompt: "闭店复盘：今天最重要的经营情况是",
              }
            : null,
      },
    }),
  );
  await page.route("**/api/v1/organization-records?*", (route) =>
    route.fulfill({ status: 200, json: { records: [] } }),
  );
  await page.route("**/api/v1/organization-records", async (route) => {
    const request = route.request().postDataJSON();
    state.recordRequests.push(request);
    recordAttempts += 1;
    if (options.failFirstRecord && recordAttempts === 1) {
      await route.fulfill({ status: 503, json: { detail: "temporary" } });
      return;
    }
    state.productEvents.push({
      event_name:
        request.purpose === "closing_review"
          ? "closing_review_completed"
          : "intake_succeeded",
      subject_id: RECORD_ID,
    });
    await route.fulfill({
      status: 201,
      json: { record: organizationRecord(request.text) },
    });
  });
  await page.route(`**/api/v1/organization-records/${RECORD_ID}`, (route) =>
    route.fulfill({
      status: 200,
      json: { record: organizationRecord("接待区物料待复核") },
    }),
  );
  await page.route("**/api/v1/conversations", async (route) => {
    if (route.request().method() === "GET") {
      await route.fulfill({ status: 200, json: { items: [] } });
      return;
    }
    conversationCount += 1;
    await route.fulfill({
      status: 201,
      json: {
        conversation: {
          id: `60000000-0000-0000-0000-00000000000${conversationCount}`,
          title: "新对话",
          created_at: "2026-07-21T09:00:00Z",
          updated_at: "2026-07-21T09:00:00Z",
          last_message_at: null,
          message_count: 0,
          last_message: null,
        },
      },
    });
  });
  await page.route("**/api/v1/conversations/*/messages", async (route) => {
    const request = route.request().postDataJSON();
    state.messageRequests.push(request);
    messageCount += 1;
    const hxyQuestion = String(request.content).includes("荷小悦");
    await route.fulfill({
      status: 200,
      json: {
        conversation: {
          id: "60000000-0000-0000-0000-000000000001",
          title: request.content,
          created_at: "2026-07-21T09:00:00Z",
          updated_at: "2026-07-21T09:00:01Z",
          last_message_at: "2026-07-21T09:00:01Z",
          message_count: 2,
          last_message: null,
        },
        user_message: {
          id: `61000000-0000-0000-0000-00000000000${messageCount}`,
          conversation_id: "60000000-0000-0000-0000-000000000001",
          role: "user",
          content: request.content,
          created_at: "2026-07-21T09:00:00Z",
          answer_id: null,
          answer_status: null,
          confidence: null,
          needs_review: null,
          sources: [],
          next_actions: [],
        },
        assistant_message: {
          id: `62000000-0000-0000-0000-00000000000${messageCount}`,
          conversation_id: "60000000-0000-0000-0000-000000000001",
          role: "assistant",
          content: hxyQuestion
            ? "荷小悦提供社区足疗养生与放松服务，不做医疗诊断或疗效承诺。"
            : "成都今天适合出门前查看实时天气。",
          created_at: "2026-07-21T09:00:01Z",
          answer_id: "60000000-0000-0000-0000-000000000004",
          answer_status: hxyQuestion ? "正式答案" : "通用回答",
          confidence: "high",
          needs_review: false,
          sources: hxyQuestion
            ? [{ title: "荷小悦品牌宪法", excerpt: "社区养生与放松服务", strength: "high", url: null }]
            : [],
          next_actions: [],
        },
      },
    });
  });
  await page.route("**/api/v1/materials", async (route) => {
    if (route.request().method() === "GET") {
      await route.fulfill({ status: 200, json: { items: [], count: 0 } });
      return;
    }
    const body = route.request().postDataBuffer()?.toString("utf8") ?? "";
    const fileName = body.includes("audio/webm") ? "hxy-voice.webm" : "现场记录.md";
    await route.fulfill({ status: 201, json: { material: material(fileName) } });
  });
  await page.route("**/api/v1/service-contexts/recent?*", (route) =>
    route.fulfill({
      status: 200,
      json: {
        contexts:
          role === "store_employee"
            ? [
                {
                  id: SERVICE_ID,
                  status: "provisional",
                  occurred_at: "2026-07-21T08:30:00Z",
                  service_label: "足部舒缓服务",
                  customer_display: "顾客 · 尾号 1234",
                  feedback_count: 0,
                  created_at: "2026-07-21T08:30:00Z",
                },
              ]
            : [],
      },
    }),
  );
  await page.route(`**/api/v1/service-contexts/${SERVICE_ID}/feedback`, async (route) => {
    const request = route.request().postDataJSON();
    state.feedbackRequests.push(request);
    state.productEvents.push({
      event_name: "service_feedback_completed",
      subject_id: "91000000-0000-0000-0000-000000000001",
      duration_ms: request.duration_ms,
    });
    await route.fulfill({
      status: 201,
      json: {
        feedback: {
          id: "91000000-0000-0000-0000-000000000001",
          context_id: SERVICE_ID,
          status: "received",
          created_at: "2026-07-21T09:05:00Z",
        },
        context: {
          id: SERVICE_ID,
          status: "provisional",
          occurred_at: "2026-07-21T08:30:00Z",
          service_label: "足部舒缓服务",
          customer_display: "顾客 · 尾号 1234",
          feedback_count: 1,
          created_at: "2026-07-21T08:30:00Z",
        },
      },
    });
  });
  await page.route("**/api/v1/learning", (route) =>
    route.fulfill({ status: 200, json: learningHome() }),
  );
  await page.route("**/api/v1/learning/practice", (route) => {
    state.productEvents.push({
      event_name: "learning_completed",
      subject_id: "92000000-0000-0000-0000-000000000001",
    });
    return route.fulfill({
      status: 200,
      json: {
        attempt: {
          id: "92000000-0000-0000-0000-000000000001",
          score: 72,
          level: "retrain",
          needs_retrain: true,
          standard_script: "我先了解您的感受，再说明本次服务能提供的放松体验。",
          correction_points: ["不要承诺立即见效"],
          physical_technique: "not_assessed",
        },
        ...learningHome(1),
      },
    });
  });
  await page.route("**/api/v1/auth/logout", (route) => {
    state.logoutCount += 1;
    return route.fulfill({ status: 200, json: { status: "logged_out" } });
  });
  await page.route("**/api/v1/product-events", async (route) => {
    const request = route.request().postDataJSON();
    if (request.event_name !== "briefing_feedback") {
      await route.fulfill({ status: 422, json: { detail: "unsupported event" } });
      return;
    }
    state.productEvents.push(request);
    await route.fulfill({
      status: 201,
      json: {
        event: {
          id: "93000000-0000-0000-0000-000000000001",
          event_name: request.event_name,
          created_at: "2026-07-21T10:00:00Z",
        },
      },
    });
  });
  return state;
}

async function assertLayout(page: Page, width: number) {
  const dimensions = await page.evaluate(() => ({
    documentWidth: document.documentElement.scrollWidth,
    viewportWidth: window.innerWidth,
  }));
  expect(dimensions.documentWidth).toBeLessThanOrEqual(dimensions.viewportWidth);

  const controls = page.locator("button:visible:not(:disabled), input:visible:not(:disabled), textarea:visible:not(:disabled)");
  const count = await controls.count();
  for (let index = 0; index < count; index += 1) {
    const control = controls.nth(index);
    const box = await control.boundingBox();
    expect(box, `control ${index} must have a hit area`).not.toBeNull();
    expect(box!.width).toBeGreaterThan(0);
    expect(box!.height).toBeGreaterThan(0);
    const receivesPointer = await control.evaluate((element) => {
      const box = element.getBoundingClientRect();
      const hit = document.elementFromPoint(
        Math.min(window.innerWidth - 1, box.left + box.width / 2),
        Math.min(window.innerHeight - 1, box.top + box.height / 2),
      );
      return hit === element || Boolean(hit && element.contains(hit));
    });
    expect(receivesPointer, `control ${index} must not be covered`).toBe(true);
  }

  if (width <= 390) {
    const composer = await page.getByTestId("composer").boundingBox();
    const navigation = await page.getByRole("navigation", { name: "移动端导航" }).boundingBox();
    expect(composer).not.toBeNull();
    expect(navigation).not.toBeNull();
    expect(composer!.y + composer!.height).toBeLessThanOrEqual(navigation!.y);
  }
}

test("keeps primary controls usable", async ({ page }) => {
  await installVoiceCapture(page);
  await mockStoreApi(page, "store_employee");
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "今日" })).toBeVisible();
  await assertLayout(page, page.viewportSize()?.width ?? 1440);
});

test("technician can ask general and governed HXY questions and upload a file", async ({ page }) => {
  const state = await mockStoreApi(page, "store_employee");
  await page.goto("/");
  await page.getByRole("button", { name: "对话" }).click();
  const composer = page.getByRole("textbox", { name: "问问题，或记录刚刚发生的事" });

  await composer.fill("成都今天适合出门吗？");
  await page.getByRole("button", { name: "发送" }).click();
  await expect(page.getByText("成都今天适合出门前查看实时天气。")).toBeVisible();

  await composer.fill("荷小悦是什么品牌？");
  await page.getByRole("button", { name: "发送" }).click();
  await expect(page.getByText("荷小悦提供社区足疗养生与放松服务，不做医疗诊断或疗效承诺。")).toBeVisible();

  await page.getByLabel("添加资料").setInputFiles({
    name: "现场记录.md",
    mimeType: "text/markdown",
    buffer: Buffer.from("接待区物料已到店"),
  });
  await expect(page.getByText("现场记录.md")).toBeVisible();
  await composer.fill("这是今天的现场记录");
  await page.getByRole("button", { name: "发送" }).click();
  await expect(page.getByText("已收到，正在处理")).toBeVisible();
  await expect.poll(() => state.recordRequests.length).toBe(3);
  await expect.poll(() => state.messageRequests.length).toBe(3);
  await expect.poll(
    () => state.productEvents.filter((event) => event.event_name === "intake_succeeded").length,
  ).toBe(3);
});

test("technician can capture voice and submit recent service feedback", async ({ page }) => {
  await installVoiceCapture(page);
  const state = await mockStoreApi(page, "store_employee");
  await page.goto("/");

  await page.getByRole("button", { name: "开始录音" }).click();
  await expect(page.getByRole("button", { name: "停止录音" })).toBeVisible();
  await page.getByRole("button", { name: "停止录音" }).click();
  await expect(page.getByText(/voice-.*\.webm/)).toBeVisible();

  await page.getByRole("textbox", { name: "服务反馈" }).fill("顾客反馈力度合适，离店时状态放松。");
  await page.getByRole("button", { name: "提交服务反馈" }).click();
  await expect(page.getByText("服务反馈已记录")).toBeVisible();
  expect(state.feedbackRequests).toHaveLength(1);
  expect(state.feedbackRequests[0]).not.toHaveProperty("phone");
  await expect.poll(
    () => state.productEvents.find((event) => event.event_name === "service_feedback_completed"),
  ).toEqual(expect.objectContaining({ subject_id: "91000000-0000-0000-0000-000000000001" }));
  await expect(page.getByText(/\b\d{11}\b/)).toHaveCount(0);
});

test("technician completes one private learning practice", async ({ page }) => {
  const state = await mockStoreApi(page, "store_employee");
  await page.goto("/");
  await page.getByRole("button", { name: "学习" }).click();
  await page.getByLabel("你会怎么回应？").fill("我先了解您的感受，再说明服务边界。");
  await page.getByRole("button", { name: "提交练习" }).click();
  await expect(page.getByText("72 分")).toBeVisible();
  await expect(page.getByText("不要承诺立即见效")).toBeVisible();
  await expect(page.getByText("仅自己可见")).toBeVisible();
  await expect.poll(
    () => state.productEvents.find((event) => event.event_name === "learning_completed"),
  ).toEqual(expect.objectContaining({ subject_id: "92000000-0000-0000-0000-000000000001" }));
});

test("technician can mark whether a briefing was useful", async ({ page }) => {
  const state = await mockStoreApi(page, "store_employee");
  await page.goto("/");
  await page.getByRole("button", { name: "认为“接待区物料今天需要复核”有帮助" }).click();
  await expect.poll(
    () => state.productEvents.find((event) => event.event_name === "briefing_feedback"),
  ).toEqual(expect.objectContaining({ subject_id: RECORD_ID, useful: true }));
});

test("manager records the closing review through the same composer", async ({ page }) => {
  const state = await mockStoreApi(page, "store_manager");
  await page.goto("/");
  await page.getByRole("button", { name: "记录闭店复盘" }).click();
  const composer = page.getByRole("textbox", { name: "问问题，或记录刚刚发生的事" });
  await expect(composer).toHaveValue("闭店复盘：今天最重要的经营情况是");
  await composer.fill("闭店复盘：今天接待流程顺畅，晚班交接需要补充耗材数量。");
  await page.getByRole("button", { name: "发送" }).click();
  await expect(page.getByRole("button", { name: "记录闭店复盘" })).toHaveCount(0);
  expect(state.recordRequests.at(-1)?.text).toContain("闭店复盘：");
  await expect.poll(
    () => state.productEvents.find((event) => event.event_name === "closing_review_completed"),
  ).toEqual(expect.objectContaining({ subject_id: RECORD_ID }));
});

test("retry preserves the same client record id", async ({ page }) => {
  const state = await mockStoreApi(page, "store_employee", { failFirstRecord: true });
  await page.goto("/");
  const composer = page.getByRole("textbox", { name: "问问题，或记录刚刚发生的事" });
  await composer.fill("现场缺少两套顾客须知");
  await page.getByRole("button", { name: "发送" }).click();
  await expect(page.getByRole("alert")).toContainText("请重试");
  await page.getByRole("button", { name: "发送" }).click();
  await expect(page.getByText("现场缺少两套顾客须知")).toBeVisible();
  expect(state.recordRequests).toHaveLength(2);
  expect(state.recordRequests[0].client_record_id).toBe(state.recordRequests[1].client_record_id);
});

test("user can leave the session from My", async ({ page }) => {
  const state = await mockStoreApi(page, "store_employee");
  await page.goto("/");
  await page.getByRole("button", { name: "我的" }).click();
  await page.getByRole("button", { name: "退出登录" }).click();
  await expect.poll(() => state.logoutCount).toBe(1);
});
