import { expect, test } from "@playwright/test";

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

    const dimensions = await page.evaluate(() => ({
      documentWidth: document.documentElement.scrollWidth,
      viewportWidth: window.innerWidth,
    }));
    expect(dimensions.documentWidth).toBeLessThanOrEqual(
      dimensions.viewportWidth,
    );
  });
});
