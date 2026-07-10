import { expect, test, type Page } from "@playwright/test";

const TEST_SESSION = {
  user: { account_id: "account-e2e", display_name: "测试店员" },
  active_assignment: {
    assignment_id: "assignment-e2e",
    organization: { id: "organization-e2e", name: "荷小悦" },
    store: { id: "store-e2e", name: "首店" },
    role: "store_employee",
    role_label: "门店员工",
    capabilities: ["conversation:use", "store:read", "tasks:read"],
  },
  available_assignments: [],
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
});
