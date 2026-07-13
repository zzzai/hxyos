import { expect, test, type Page } from "@playwright/test";

const TEST_SESSION = {
  user: { account_id: "account-e2e", display_name: "测试店员" },
  active_assignment: {
    assignment_id: "assignment-e2e",
    organization: { id: "organization-e2e", name: "荷小悦" },
    store: { id: "store-e2e", name: "首店" },
    role: "store_employee",
    role_label: "门店员工",
    capabilities: [
      "conversation:use",
      "materials:create",
      "materials:read",
      "store:read",
      "tasks:read",
    ],
  },
  available_assignments: [],
};

const ROLE_SESSIONS = {
  founder: {
    user: { account_id: "account-founder", display_name: "测试创始人" },
    active_assignment: {
      assignment_id: "assignment-founder",
      organization: { id: "organization-e2e", name: "荷小悦" },
      store: null,
      role: "founder",
      role_label: "创始人",
      capabilities: [
        "conversation:use",
        "materials:create",
        "materials:read",
        "organization:read",
        "stores:read",
        "tasks:manage",
        "tasks:read",
      ],
    },
    available_assignments: [],
  },
  store_manager: {
    user: { account_id: "account-manager", display_name: "测试店长" },
    active_assignment: {
      assignment_id: "assignment-manager",
      organization: { id: "organization-e2e", name: "荷小悦" },
      store: { id: "store-e2e", name: "首店" },
      role: "store_manager",
      role_label: "店长",
      capabilities: [
        "conversation:use",
        "issues:create",
        "materials:create",
        "materials:read",
        "store:operate",
        "store:read",
        "tasks:manage",
        "tasks:read",
      ],
    },
    available_assignments: [],
  },
  store_employee: {
    user: { account_id: "account-employee", display_name: "测试店员" },
    active_assignment: {
      assignment_id: "assignment-employee",
      organization: { id: "organization-e2e", name: "荷小悦" },
      store: { id: "store-e2e", name: "首店" },
      role: "store_employee",
      role_label: "门店员工",
      capabilities: [
        "conversation:use",
        "issues:create",
        "materials:create",
        "materials:read",
        "store:read",
        "tasks:read",
        "training:practice",
      ],
    },
    available_assignments: [],
  },
} as const;

const OPENING_TASK = {
  id: "task-opening",
  title: "检查开业物料",
  details: "核对接待区和员工用品。",
  priority: "high",
  status: "open",
  visibility: "store",
  store_id: "store-e2e",
  assignee_assignment_id: null,
  source_conversation_id: null,
  source_message_id: null,
  result: null,
  due_at: null,
  completed_at: null,
  created_at: "2026-07-12T09:00:00Z",
  updated_at: "2026-07-12T09:00:00Z",
};

const PROCESSING_MATERIAL = {
  id: "70000000-0000-0000-0000-000000000001",
  file_name: "首店接待流程.md",
  media_type: "text/markdown",
  size_bytes: 42,
  status: "processing",
  receipt: {
    status: "已收到",
    message: "资料已安全保存，当前不会自动变成正式知识。",
  },
  original: {
    url: "/api/v1/materials/70000000-0000-0000-0000-000000000001/content",
    can_preview: true,
  },
  understanding: {
    summary: "资料已收到，系统正在继续理解。",
    document_type: "门店流程资料",
    source_origin: "internal",
    authority_level: "working_material",
    knowledge_scale: "micro",
    domain: "operations",
    parse_status: "needs_deep_parse",
    confidence: "low",
    warnings: [],
    official_use_allowed: false,
    use_boundary: "可用于整理候选流程，不能直接作为正式 SOP。",
  },
  created_at: "2026-07-10T10:00:00Z",
  updated_at: "2026-07-10T10:00:00Z",
};

async function mockProductApi(page: Page) {
  await page.route("**/api/v1/me", (route) =>
    route.fulfill({ status: 200, json: TEST_SESSION }),
  );
  await page.route("**/api/v1/conversations", async (route) => {
    if (route.request().method() === "POST") {
      await route.fulfill({
        status: 201,
        json: {
          conversation: {
            id: "60000000-0000-0000-0000-000000000001",
            title: "新对话",
            created_at: "2026-07-10T09:00:00Z",
            updated_at: "2026-07-10T09:00:00Z",
            last_message_at: null,
            message_count: 0,
            last_message: null,
          },
        },
      });
      return;
    }
    await route.fulfill({ status: 200, json: { items: [], count: 0 } });
  });
  await page.route("**/api/v1/conversations/*/messages", async (route) => {
    const request = route.request().postDataJSON();
    await route.fulfill({
      status: 200,
      json: {
        conversation: {
          id: "60000000-0000-0000-0000-000000000001",
          title: request.content,
          created_at: "2026-07-10T09:00:00Z",
          updated_at: "2026-07-10T09:00:02Z",
          last_message_at: "2026-07-10T09:00:02Z",
          message_count: 2,
          last_message: null,
        },
        user_message: {
          id: "60000000-0000-0000-0000-000000000002",
          conversation_id: "60000000-0000-0000-0000-000000000001",
          role: "user",
          content: request.content,
          created_at: "2026-07-10T09:00:01Z",
          answer_id: null,
          answer_status: null,
          confidence: null,
          needs_review: null,
          sources: [],
          next_actions: [],
        },
        assistant_message: {
          id: "60000000-0000-0000-0000-000000000003",
          conversation_id: "60000000-0000-0000-0000-000000000001",
          role: "assistant",
          content: "可以先了解顾客当下感受，再给出克制的服务建议，不承诺治疗效果。",
          created_at: "2026-07-10T09:00:02Z",
          answer_id: "60000000-0000-0000-0000-000000000004",
          answer_status: "已批准",
          confidence: "high",
          needs_review: false,
          sources: [
            {
              title: "员工标准话术",
              excerpt: "先问状态，不做治疗承诺",
              strength: "high",
              url: null,
            },
          ],
          next_actions: [],
        },
      },
    });
  });
  await page.route("**/api/v1/materials*", async (route) => {
    if (route.request().method() === "GET") {
      if (new URL(route.request().url()).pathname !== "/api/v1/materials") {
        await route.fulfill({
          status: 200,
          json: { material: PROCESSING_MATERIAL },
        });
        return;
      }
      await route.fulfill({ status: 200, json: { items: [], count: 0 } });
      return;
    }
    await route.fulfill({
      status: 201,
      json: { material: PROCESSING_MATERIAL },
    });
  });
}

async function mockRoleJourneyApi(
  page: Page,
  role: keyof typeof ROLE_SESSIONS,
) {
  await mockProductApi(page);
  const session = ROLE_SESSIONS[role];
  let tasks: Array<Record<string, unknown>> =
    role === "store_manager" ? [OPENING_TASK] : [];
  let lastIssueRequest: Record<string, unknown> | null = null;

  await page.route("**/api/v1/me", (route) =>
    route.fulfill({ status: 200, json: session }),
  );
  await page.route("**/api/v1/journeys/suggestions", (route) => {
    const items = {
      founder: [
        { type: "ask", label: "询问当前开业进度", prompt: "现在开业进度怎么样？" },
        { type: "tasks", label: "查看今天的关键事项" },
      ],
      store_manager: [
        { type: "tasks", label: "打开今天的待办" },
        { type: "issue", label: "上报一个门店问题" },
      ],
      store_employee: [
        { type: "ask", label: "询问该怎么说", prompt: "顾客这样问时我该怎么说？" },
        { type: "training", label: "练习一次接待话术" },
        { type: "issue", label: "上报一个门店问题" },
      ],
    }[role];
    return route.fulfill({ status: 200, json: { items } });
  });
  await page.route("**/api/v1/tasks", async (route) => {
    if (route.request().method() === "GET") {
      await route.fulfill({ status: 200, json: { items: tasks, count: tasks.length } });
      return;
    }
    const request = route.request().postDataJSON();
    const task = {
      ...OPENING_TASK,
      id: "task-from-answer",
      title: request.title,
      details: request.details,
      visibility: request.visibility,
      store_id: null,
      assignee_assignment_id: request.assignee_assignment_id,
      source_conversation_id: request.source_conversation_id,
      source_message_id: request.source_message_id,
    };
    tasks = [task, ...tasks];
    await route.fulfill({ status: 201, json: { task } });
  });
  await page.route("**/api/v1/issues", async (route) => {
    const request = route.request().postDataJSON();
    lastIssueRequest = request;
    const task = {
      ...OPENING_TASK,
      id: "task-from-issue",
      title: request.title,
      details: request.details,
      priority: "normal",
    };
    tasks = [task, ...tasks];
    await route.fulfill({
      status: 201,
      json: {
        result_type: "issue_report",
        primary_result: { task },
        actions: [{ type: "tasks", label: "查看门店待办" }],
        sources: [],
        limitations: ["问题已进入当前门店待办，处理结论需由负责人填写。"],
        artifact: { type: "task", id: task.id },
      },
    });
  });
  await page.route("**/api/v1/journeys/training/evaluate", (route) =>
    route.fulfill({
      status: 200,
      json: {
        result_type: "training_result",
        primary_result: {
          score: 68,
          level: "retrain",
          needs_retrain: true,
          standard_script: "可以说泡脚有助于放松，但不能替代医疗诊断或治疗。",
          correction_points: ["不要承诺治疗效果", "先回应顾客感受"],
        },
        actions: [{ type: "training", label: "再练一次合规表达" }],
        sources: [],
        limitations: ["训练结果用于岗位练习，不替代店长现场验收。"],
        artifact: { type: "training_session", id: "training-e2e" },
      },
    }),
  );
  await page.route("**/api/v1/conversations/*/messages", async (route) => {
    const request = route.request().postDataJSON();
    const employee = role === "store_employee";
    await route.fulfill({
      status: 200,
      json: {
        conversation: {
          id: "60000000-0000-0000-0000-000000000001",
          title: request.content,
          created_at: "2026-07-12T10:00:00Z",
          updated_at: "2026-07-12T10:00:02Z",
          last_message_at: "2026-07-12T10:00:02Z",
          message_count: 2,
          last_message: null,
        },
        user_message: {
          id: "message-role-user",
          conversation_id: "60000000-0000-0000-0000-000000000001",
          role: "user",
          content: request.content,
          created_at: "2026-07-12T10:00:01Z",
          answer_id: null,
          answer_status: null,
          confidence: null,
          needs_review: null,
          sources: [],
          next_actions: [],
        },
        assistant_message: {
          id: "message-role-assistant",
          conversation_id: "60000000-0000-0000-0000-000000000001",
          role: "assistant",
          content: employee
            ? "可以先了解顾客感受，再说明泡脚有助于放松，不承诺治疗效果。"
            : "首店开业准备已进入物料核对阶段，下一步完成现场验收。",
          created_at: "2026-07-12T10:00:02Z",
          answer_id: "answer-role",
          answer_status: "已批准",
          confidence: "high",
          needs_review: false,
          sources: [
            {
              title: employee ? "员工标准话术" : "首店开业计划",
              excerpt: employee ? "不承诺治疗效果" : "物料核对后进行现场验收",
              strength: "high",
              url: null,
            },
          ],
          next_actions: [],
          result_type: employee ? "frontdesk_answer" : "decision_support",
          actions: employee
            ? [
                { type: "training", label: "练习这个说法" },
                { type: "issue", label: "上报现场问题" },
              ]
            : [{ type: "tasks", label: "转为下一项任务" }],
        },
      },
    });
  });
  return {
    lastIssueRequest: () => lastIssueRequest,
  };
}

test.describe("HXYOS product shell viewport contract", () => {
  test("centers the empty composer and docks it after the first message", async ({
    page,
  }) => {
    await mockProductApi(page);
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/");

    const stage = page.locator(".conversation-stage");
    const composer = page.getByTestId("composer");
    const textbox = page.getByRole("textbox", {
      name: "告诉 HXYOS 你要做什么",
    });
    await expect(textbox).toBeEnabled();

    const emptyStageBox = await stage.boundingBox();
    const emptyComposerBox = await composer.boundingBox();
    expect(emptyStageBox).not.toBeNull();
    expect(emptyComposerBox).not.toBeNull();
    expect(
      Math.abs(
        emptyComposerBox!.x + emptyComposerBox!.width / 2 -
          (emptyStageBox!.x + emptyStageBox!.width / 2),
      ),
    ).toBeLessThanOrEqual(2);
    expect(
      Math.abs(
        emptyComposerBox!.y + emptyComposerBox!.height / 2 -
          (emptyStageBox!.y + emptyStageBox!.height / 2),
      ),
    ).toBeLessThanOrEqual(150);

    await textbox.fill("检查今天的开业任务");
    await page.getByRole("button", { name: "发送" }).click();
    await expect(page.getByText("检查今天的开业任务")).toBeVisible();

    const activeComposerBox = await composer.boundingBox();
    expect(activeComposerBox).not.toBeNull();
    expect(activeComposerBox!.y).toBeGreaterThan(emptyComposerBox!.y + 100);
    expect(activeComposerBox!.y + activeComposerBox!.height).toBeLessThanOrEqual(
      emptyStageBox!.y + emptyStageBox!.height,
    );
  });

  test("opens the mobile conversation from a one-time fragment link", async ({
    page,
  }) => {
    const grant = "g".repeat(64);
    let exchanged = false;
    await mockProductApi(page);
    await page.unroute("**/api/v1/me");
    await page.route("**/api/v1/auth/session-grant", async (route) => {
      expect(route.request().method()).toBe("POST");
      expect(route.request().postDataJSON()).toEqual({ grant });
      exchanged = true;
      await route.fulfill({ status: 200, json: { status: "authenticated" } });
    });
    await page.route("**/api/v1/me", async (route) => {
      await route.fulfill(
        exchanged
          ? { status: 200, json: TEST_SESSION }
          : { status: 401, json: { detail: "Unauthorized" } },
      );
    });
    await page.setViewportSize({ width: 390, height: 844 });

    await page.goto(`/#hxy_session_grant=${grant}`);

    await expect(
      page.getByRole("textbox", { name: "告诉 HXYOS 你要做什么" }),
    ).toBeEnabled();
    expect(exchanged).toBe(true);
    expect(page.url()).not.toContain("hxy_session_grant");
    await expect(page.getByText(grant)).toHaveCount(0);
    await expect(page.getByRole("textbox", { name: "用户名" })).toHaveCount(0);
    await expect(page.getByRole("textbox", { name: "密码" })).toHaveCount(0);
  });

  test("keeps the mobile composer visible above the primary navigation", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/");

    const composers = page.getByTestId("composer");
    await expect(composers).toHaveCount(1);

    const composerBox = await composers.boundingBox();
    const navigation = page.getByRole("navigation", { name: "主要导航" });
    const navigationBox = await navigation.boundingBox();
    const viewportHeight = await page.evaluate(() => window.innerHeight);

    expect(composerBox).not.toBeNull();
    expect(navigationBox).not.toBeNull();
    expect(composerBox!.y + composerBox!.height).toBeLessThanOrEqual(
      viewportHeight,
    );
    expect(composerBox!.y + composerBox!.height).toBeLessThanOrEqual(
      navigationBox!.y,
    );

    const labels = await navigation.getByRole("button").allTextContents();
    expect(labels.map((label) => label.trim())).toEqual(["对话", "待办", "我的"]);

    const viewportWidth = await page.evaluate(() => window.innerWidth);
    const documentWidth = await page.evaluate(
      () => document.documentElement.scrollWidth,
    );
    expect(documentWidth).toBeLessThanOrEqual(viewportWidth);
  });

  test("does not overflow horizontally on desktop", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/");

    const expandRail = page.getByRole("button", { name: "展开导航栏" });
    await expect(expandRail).toBeVisible();
    await expandRail.click();
    const collapseRail = page.getByRole("button", { name: "收起导航栏" });
    await expect(collapseRail).toBeVisible();
    await collapseRail.click();
    await expect(expandRail).toBeVisible();

    const dimensions = await page.evaluate(() => ({
      documentWidth: document.documentElement.scrollWidth,
      viewportWidth: window.innerWidth,
    }));
    expect(dimensions.documentWidth).toBeLessThanOrEqual(
      dimensions.viewportWidth,
    );
  });

  test("keeps the real answer and its sources inside one minimal conversation", async ({
    page,
  }) => {
    await mockProductApi(page);
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/");

    const composer = page.getByRole("textbox", {
      name: "告诉 HXYOS 你要做什么",
    });
    await expect(composer).toBeEnabled();
    await composer.fill("顾客问泡脚能不能治失眠，我该怎么说？");
    await page.getByRole("button", { name: "发送" }).click();

    await expect(
      page.getByText(
        "可以先了解顾客当下感受，再给出克制的服务建议，不承诺治疗效果。",
      ),
    ).toBeVisible();
    await page.getByRole("button", { name: "查看当前对话详情" }).click();
    const details = page.getByRole("dialog", { name: "当前对话详情" });
    await expect(details.getByText("员工标准话术")).toBeVisible();
    await expect(details.getByText("先问状态，不做治疗承诺")).toBeVisible();
    await expect(page.getByText("chunk_id")).toHaveCount(0);
    await expect(page.getByText("/root/hxy")).toHaveCount(0);
  });

  test("uploads a material into the mobile conversation without covering the composer", async ({
    page,
  }) => {
    await mockProductApi(page);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/");

    await page.locator('input[type="file"]').setInputFiles({
      name: "首店接待流程.md",
      mimeType: "text/markdown",
      buffer: Buffer.from("先问顾客状态，再介绍服务。"),
    });

    await expect(page.getByText("首店接待流程.md")).toBeVisible();
    await expect(page.getByText("正在理解")).toBeVisible();
    await expect(page.getByText("资料已收到，系统正在继续理解。")).toBeVisible();
    await expect(page.getByRole("link", { name: "查看原文" })).toBeVisible();
    await page.getByRole("link", { name: "查看原文" }).click({ trial: true });

    const composerBox = await page.getByTestId("composer").boundingBox();
    const navigationBox = await page
      .getByRole("navigation", { name: "主要导航" })
      .boundingBox();
    expect(composerBox).not.toBeNull();
    expect(navigationBox).not.toBeNull();
    expect(composerBox!.y + composerBox!.height).toBeLessThanOrEqual(
      navigationBox!.y,
    );
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth),
    ).toBeLessThanOrEqual(390);
  });

  test("lets the founder turn an evidence-backed answer into work", async ({ page }) => {
    await mockRoleJourneyApi(page, "founder");
    await page.goto("/");

    await page.getByRole("button", { name: "询问当前开业进度" }).click();
    await page.getByRole("button", { name: "发送" }).click();
    await expect(page.getByText("首店开业准备已进入物料核对阶段，下一步完成现场验收。"))
      .toBeVisible();
    await page.getByRole("button", { name: "查看当前对话详情" }).click();
    await expect(page.getByText("首店开业计划")).toBeVisible();
    await page.getByRole("button", { name: "关闭当前对话详情" }).click();
    await page.getByRole("button", { name: "转为下一项任务" }).click();
    await expect(page.getByRole("heading", { name: "跟进本次回答" })).toBeVisible();
  });

  test("lets a store manager move from current work to a follow-up issue", async ({ page }) => {
    const api = await mockRoleJourneyApi(page, "store_manager");
    await page.goto("/");

    await page.getByRole("button", { name: "打开今天的待办" }).click();
    await expect(page.getByRole("heading", { name: "检查开业物料" })).toBeVisible();
    await page.getByRole("button", { name: "反馈检查开业物料的问题" }).click();
    await expect(page.getByText("关联待办：检查开业物料")).toBeVisible();
    await page.getByRole("textbox", { name: "问题标题" }).fill("接待区物料不足");
    await page.getByRole("textbox", { name: "问题详情" }).fill("缺少两套顾客须知。");
    await page.getByRole("button", { name: "提交问题" }).click();
    await expect(page.getByRole("heading", { name: "接待区物料不足" })).toBeVisible();
    expect(api.lastIssueRequest()).toEqual({
      title: "接待区物料不足",
      details: "缺少两套顾客须知。",
      source_task_id: "task-opening",
    });
  });

  test("lets an employee answer, practice, correct, and report a live issue", async ({ page }) => {
    await mockRoleJourneyApi(page, "store_employee");
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/");

    const composer = page.getByRole("textbox", { name: "告诉 HXYOS 你要做什么" });
    await composer.fill("顾客问泡脚能不能治失眠，我该怎么说？");
    await page.getByRole("button", { name: "发送" }).click();
    await expect(page.getByText("可以先了解顾客感受，再说明泡脚有助于放松，不承诺治疗效果。"))
      .toBeVisible();
    await page.getByRole("button", { name: "练习这个说法" }).click();
    await page.getByRole("textbox", { name: "我的回答" }).fill("肯定可以治好。");
    await page.getByRole("button", { name: "提交练习" }).click();
    await expect(page.getByText("68 分")).toBeVisible();
    await expect(page.getByText("不要承诺治疗效果")).toBeVisible();
    await page.getByRole("button", { name: "返回对话" }).click();
    await page.getByRole("button", { name: "上报现场问题" }).click();
    await page.getByRole("textbox", { name: "问题标题" }).fill("顾客反复询问疗效");
    await page
      .getByRole("textbox", { name: "问题详情" })
      .fill("今天连续三位顾客询问是否能治疗失眠。");
    await page.getByRole("button", { name: "提交问题" }).click();
    await expect(page.getByRole("heading", { name: "顾客反复询问疗效" })).toBeVisible();

    const navigationBox = await page.getByRole("navigation", { name: "主要导航" }).boundingBox();
    const taskBox = await page.getByRole("heading", { name: "顾客反复询问疗效" }).boundingBox();
    expect(taskBox).not.toBeNull();
    expect(navigationBox).not.toBeNull();
    expect(taskBox!.y + taskBox!.height).toBeLessThan(navigationBox!.y);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  });
});
