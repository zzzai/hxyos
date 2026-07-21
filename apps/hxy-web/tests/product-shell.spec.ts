import { expect, test } from "@playwright/test";

const SESSION = {
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
      "records:create",
      "records:read",
      "services:create",
      "services:feedback",
      "services:read",
      "training:practice",
    ],
  },
  available_assignments: [],
};

async function mockSession(page: import("@playwright/test").Page) {
  await page.route("**/api/v1/me", (route) =>
    route.fulfill({ status: 200, json: SESSION }),
  );
  await page.route("**/api/v1/conversations", async (route) => {
    if (route.request().method() === "POST") {
      await route.fulfill({
        status: 201,
        json: {
          conversation: {
            id: "60000000-0000-0000-0000-000000000001",
            title: "新对话",
            created_at: "2026-07-21T09:00:00Z",
            updated_at: "2026-07-21T09:00:00Z",
            last_message_at: null,
            message_count: 0,
            last_message: null,
          },
        },
      });
      return;
    }
    await route.fulfill({ status: 200, json: { items: [] } });
  });
  await page.route("**/api/v1/conversations/*/messages", async (route) => {
    const request = route.request().postDataJSON();
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
          id: "60000000-0000-0000-0000-000000000002",
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
          id: "60000000-0000-0000-0000-000000000003",
          conversation_id: "60000000-0000-0000-0000-000000000001",
          role: "assistant",
          content: "先了解顾客当下感受，再给出克制的服务建议，不承诺治疗效果。",
          created_at: "2026-07-21T09:00:01Z",
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
  await page.route("**/api/v1/organization-records?*", (route) =>
    route.fulfill({ status: 200, json: { records: [] } }),
  );
  await page.route("**/api/v1/today?*", (route) =>
    route.fulfill({ status: 200, json: { items: [], role_action: null } }),
  );
  await page.route("**/api/v1/materials", async (route) => {
    if (route.request().method() === "GET") {
      await route.fulfill({ status: 200, json: { items: [], count: 0 } });
      return;
    }
    await route.fulfill({
      status: 201,
      json: {
        material: {
          id: "70000000-0000-0000-0000-000000000001",
          file_name: "门店记录.md",
          media_type: "text/markdown",
          size_bytes: 12,
          status: "processing",
          receipt: { status: "已收到", message: "资料已进入待处理区。" },
          original: {
            url: "/api/v1/materials/70000000-0000-0000-0000-000000000001/content",
            can_preview: true,
          },
          understanding: {
            summary: "资料已收到，系统正在理解。",
            document_type: "门店记录",
            source_origin: "internal",
            authority_level: "working_material",
            knowledge_scale: "micro",
            domain: "store",
            parse_status: "needs_deep_parse",
            confidence: "low",
            warnings: [],
            official_use_allowed: false,
            use_boundary: "仅作为组织资料使用。",
          },
          created_at: "2026-07-21T09:00:00Z",
          updated_at: "2026-07-21T09:00:00Z",
        },
      },
    });
  });
  await page.route("**/api/v1/organization-records", async (route) => {
    await route.fulfill({
      status: 201,
      json: {
        record: {
          id: "80000000-0000-0000-0000-000000000001",
          source_types: ["text"],
          preview: "今天完成了门店记录",
          submitted_by: "测试店员",
          store_id: "store-e2e",
          captured_at: "2026-07-21T09:00:00Z",
          occurred_at: null,
          processing_status: "received",
          original: { text: "今天完成了门店记录", assets: [] },
          interpretation: null,
        },
      },
    });
  });
  await page.route("**/api/v1/service-contexts/recent?*", (route) =>
    route.fulfill({ status: 200, json: { contexts: [] } }),
  );
  await page.route("**/api/v1/learning", (route) =>
    route.fulfill({
      status: 200,
      json: {
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
          attempts: 0,
          mastered: [],
          practicing: ["service-boundary-v1"],
          needs_attention: [],
        },
        limitations: ["不评估按摩技术。"],
      },
    }),
  );
  await page.route("**/api/v1/auth/logout", (route) =>
    route.fulfill({ status: 200, json: { status: "logged_out" } }),
  );
}

test.describe("HXYOS 当前产品外壳", () => {
  test("bare URL shows a working access gate", async ({ page }) => {
    await mockSession(page);
    await page.unroute("**/api/v1/me");
    await page.route("**/api/v1/me", (route) =>
      route.fulfill({ status: 401, json: { detail: "Unauthorized" } }),
    );

    await page.goto("/");
    await expect(page.getByRole("heading", { name: "进入 HXYOS" })).toBeVisible();
    await expect(page.getByLabel("一次性访问码")).toBeEnabled();
    await expect(page.getByRole("button", { name: "进入" })).toBeDisabled();
    await expect(page.getByRole("navigation", { name: "主要导航" })).toHaveCount(0);
    await expect(page.getByRole("textbox", { name: "问问题，或记录刚刚发生的事" })).toHaveCount(0);
  });

  test("one-time access code opens the workspace", async ({ page }) => {
    const grant = "g".repeat(64);
    let exchanged = false;
    await mockSession(page);
    await page.unroute("**/api/v1/me");
    await page.route("**/api/v1/auth/session-grant", async (route) => {
      expect(route.request().postDataJSON()).toEqual({ grant });
      exchanged = true;
      await route.fulfill({ status: 200, json: { status: "authenticated" } });
    });
    await page.route("**/api/v1/me", (route) =>
      route.fulfill(
        exchanged
          ? { status: 200, json: SESSION }
          : { status: 401, json: { detail: "Unauthorized" } },
      ),
    );

    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/");
    await page.getByLabel("一次性访问码").fill(grant);
    await page.getByRole("button", { name: "进入" }).click();
    await expect(page.getByRole("textbox", { name: "问问题，或记录刚刚发生的事" })).toBeEnabled();
    await expect(page.getByRole("navigation", { name: "移动端导航" })).toBeVisible();
    expect(page.url()).not.toContain(grant);
  });

  test("desktop shell has no horizontal overflow and keeps one composer", async ({ page }) => {
    await mockSession(page);
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/");
    await expect(page.getByTestId("composer")).toHaveCount(1);
    const dimensions = await page.evaluate(() => ({
      documentWidth: document.documentElement.scrollWidth,
      viewportWidth: window.innerWidth,
    }));
    expect(dimensions.documentWidth).toBeLessThanOrEqual(dimensions.viewportWidth);
    await expect(page.getByRole("button", { name: "打开对话" })).toBeVisible();
    await expect(page.getByRole("button", { name: "打开学习" })).toBeVisible();
  });

  test("mobile shell keeps the composer above the four-item navigation", async ({ page }) => {
    await mockSession(page);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/");
    const composer = await page.getByTestId("composer").boundingBox();
    const navigation = await page.getByRole("navigation", { name: "移动端导航" }).boundingBox();
    expect(composer).not.toBeNull();
    expect(navigation).not.toBeNull();
    expect(composer!.y + composer!.height).toBeLessThanOrEqual(navigation!.y);
    await expect(page.getByRole("button", { name: "今日" })).toBeVisible();
    await expect(page.getByRole("button", { name: "对话" })).toBeVisible();
    await expect(page.getByRole("button", { name: "学习" })).toBeVisible();
    await expect(page.getByRole("button", { name: "我的" })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  });
});
