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

test.describe("HXYOS product shell viewport contract", () => {
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
});
