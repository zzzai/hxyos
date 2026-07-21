import { expect, test } from "@playwright/test";

import {
  createGovernedOnboardingApi,
  expectAboveMobileNavigation,
  expectClipboardWrite,
  expectEllipsisContained,
  expectHorizontallyWithinViewport,
  expectMobileOrganizationTouchTargets,
  expectMobileTouchTarget,
  expectMutation,
  expectNoHorizontalOverflow,
  expectNoUnexpectedRequests,
  expectTextWrapsWithoutOverflow,
  expectWithinViewport,
  GOVERNED_FIXTURES,
  installClipboardWriteSpy,
} from "./support/governed-onboarding";

test.describe("HXYOS governed onboarding", () => {
  for (const viewport of [
    { width: 1440, height: 900 },
    { width: 390, height: 844 },
  ]) {
    test(`founder creates a store and issues one transient manager link at ${viewport.width}x${viewport.height}`, async ({
      page,
    }) => {
      await installClipboardWriteSpy(page);
      const state = await createGovernedOnboardingApi(page, "founder");
      await page.setViewportSize(viewport);
      await page.goto("/");
      await page.getByRole("button", { name: "我的" }).click();

      const profile = page.locator(".organization-panel");
      await expect(page.getByRole("heading", { name: "测试创始人" })).toBeVisible();
      await expectWithinViewport(
        page,
        page.locator(
          viewport.width <= 760 ? ".mobile-context-bar" : ".rail-identity",
        ),
      );
      await expectHorizontallyWithinViewport(page, profile);
      await expectNoHorizontalOverflow(page);

      await page.getByRole("button", { name: "新建门店" }).click();
      const storeForm = page.locator(".organization-form");
      await storeForm.scrollIntoViewIfNeeded();
      await expectWithinViewport(page, storeForm);
      await page.getByRole("textbox", { name: "门店名称" }).fill("荷小悦岳麓店");
      await page.getByRole("textbox", { name: "城市" }).fill("长沙");
      await page.getByRole("textbox", { name: "地址" }).fill("麓谷大道 88 号");
      const createStore = page.getByRole("button", { name: "创建门店" });
      await createStore.scrollIntoViewIfNeeded();
      await expectWithinViewport(page, createStore);
      if (viewport.width === 390) {
        await expectAboveMobileNavigation(page, createStore);
        await expectMobileOrganizationTouchTargets(page);
      }
      await createStore.click();
      await expect(page.getByText("荷小悦岳麓店", { exact: true })).toBeVisible();
      expectMutation(state, "/api/v1/organization/stores", {
        name: "荷小悦岳麓店",
        city: "长沙",
        address: "麓谷大道 88 号",
      });

      await page.getByRole("button", { name: "邀请店长" }).click();
      const inviteForm = page.locator(".organization-invite-form");
      await inviteForm.scrollIntoViewIfNeeded();
      await expectWithinViewport(page, inviteForm);
      await page
        .getByRole("combobox", { name: "邀请门店" })
        .selectOption(GOVERNED_FIXTURES.createdStoreId);
      await page.getByRole("textbox", { name: "成员姓名" }).fill("岳麓店长");
      const createInvite = page.getByRole("button", { name: "生成邀请" });
      await createInvite.scrollIntoViewIfNeeded();
      await expectWithinViewport(page, createInvite);
      if (viewport.width === 390) {
        await expectAboveMobileNavigation(page, createInvite);
      }
      await createInvite.click();

      expectMutation(state, "/api/v1/organization/invites", {
        role: "store_manager",
        display_name: "岳麓店长",
        store_id: GOVERNED_FIXTURES.createdStoreId,
      });
      const oneTimeResult = page.getByRole("status", { name: "一次性邀请链接" });
      await expect(oneTimeResult).toHaveCount(1);
      await expect(oneTimeResult).toContainText(GOVERNED_FIXTURES.oneTimeLink);
      await expect(
        page.getByText(GOVERNED_FIXTURES.oneTimeLink, { exact: true }),
      ).toHaveCount(1);
      await oneTimeResult.scrollIntoViewIfNeeded();
      await expectWithinViewport(page, oneTimeResult);
      const copyButton = page.getByRole("button", {
        name: "复制一次性邀请链接",
      });
      const closeButton = page.getByRole("button", {
        name: "关闭一次性邀请链接",
      });
      if (viewport.width === 390) {
        await expectMobileOrganizationTouchTargets(page);
        await expectMobileTouchTarget(copyButton);
        await expectMobileTouchTarget(closeButton);
      }
      await expectWithinViewport(page, copyButton);
      await expectWithinViewport(page, closeButton);
      await copyButton.click({ trial: true });
      await copyButton.click();
      await expect(oneTimeResult).toContainText("已复制");
      await expectClipboardWrite(page, GOVERNED_FIXTURES.oneTimeLink);

      await closeButton.click();
      await expect(oneTimeResult).toHaveCount(0);
      await expect(
        page.getByText(GOVERNED_FIXTURES.oneTimeLink, { exact: true }),
      ).toHaveCount(0);
      await page.getByRole("button", { name: "邀请店长" }).click();
      await expect(
        page.getByText(GOVERNED_FIXTURES.oneTimeLink, { exact: true }),
      ).toHaveCount(0);
      await page.getByRole("button", { name: "取消" }).click();
      await page.getByRole("button", { name: "停用首店店长" }).click();
      const dialog = page.getByRole("dialog", { name: "停用成员" });
      await expectWithinViewport(page, dialog);
      const cancelDialog = dialog.getByRole("button", { name: "取消" });
      await expectWithinViewport(page, cancelDialog);
      await cancelDialog.click({ trial: true });
      if (viewport.width === 390) {
        await expectMobileOrganizationTouchTargets(page);
      }
      await cancelDialog.click();
      if (viewport.width === 390) {
        const logout = page.getByRole("button", { name: "退出登录" });
        await expectAboveMobileNavigation(page, logout);
        await expectWithinViewport(page, logout);
        await expectMobileOrganizationTouchTargets(page);
      }
      await expectNoHorizontalOverflow(page);
      expectNoUnexpectedRequests(state);
    });
  }

  test("manager manages only own-store employee invitations on mobile", async ({
    page,
  }) => {
    const state = await createGovernedOnboardingApi(page, "store_manager");
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/");
    await page.getByRole("button", { name: "我的" }).click();

    const identity = page.getByRole("region", {
      name: GOVERNED_FIXTURES.longManagerName,
    });
    const identityStoreName = identity.getByText(
      GOVERNED_FIXTURES.longStoreName,
      { exact: true },
    );
    await expect(
      page.getByRole("heading", { name: GOVERNED_FIXTURES.longManagerName }),
    ).toBeVisible();
    await expect(identityStoreName).toBeVisible();
    await expect(
      page.getByText(GOVERNED_FIXTURES.longEmployeeName, { exact: true }),
    ).toBeVisible();
    await expectTextWrapsWithoutOverflow(
      page.getByRole("heading", {
        name: GOVERNED_FIXTURES.longManagerName,
      }),
    );
    await expectTextWrapsWithoutOverflow(identityStoreName);
    await expectEllipsisContained(
      page.getByText(GOVERNED_FIXTURES.longEmployeeName, { exact: true }),
    );
    const headerScope = page.locator(".mobile-context-bar button");
    await expect(headerScope).toHaveText(GOVERNED_FIXTURES.longStoreName);
    await expectEllipsisContained(headerScope);
    await expectWithinViewport(page, page.locator(".mobile-context-bar"));
    await expectHorizontallyWithinViewport(
      page,
      page.locator(".organization-panel"),
    );
    await expectNoHorizontalOverflow(page);
    expect(state.organizationRequests).not.toContain(
      "GET /api/v1/organization/stores",
    );

    await page.getByRole("button", { name: "邀请员工" }).click();
    const inviteForm = page.locator(".organization-invite-form");
    await inviteForm.scrollIntoViewIfNeeded();
    await expectWithinViewport(page, inviteForm);
    await page
      .getByRole("textbox", { name: "成员姓名" })
      .fill(GOVERNED_FIXTURES.longEmployeeName);
    const submit = page.getByRole("button", { name: "生成邀请" });
    await expectAboveMobileNavigation(page, submit);
    await expectWithinViewport(page, submit);
    await expectMobileOrganizationTouchTargets(page);
    await submit.click();

    expectMutation(state, "/api/v1/organization/invites", {
      role: "store_employee",
      display_name: GOVERNED_FIXTURES.longEmployeeName,
    });
    await expect(
      page.getByRole("button", {
        name: `撤销${GOVERNED_FIXTURES.longEmployeeName}的邀请`,
      }),
    ).toBeVisible();
    await expectEllipsisContained(
      page
        .locator(".organization-list-section")
        .last()
        .getByText(GOVERNED_FIXTURES.longEmployeeName),
    );

    await page
      .getByRole("button", { name: "关闭一次性邀请链接" })
      .click();
    const revoke = page.getByRole("button", {
      name: `撤销${GOVERNED_FIXTURES.longEmployeeName}的邀请`,
    });
    await revoke.click();
    let dialog = page.getByRole("dialog", { name: "撤销邀请" });
    await expectWithinViewport(page, dialog);
    await expectTextWrapsWithoutOverflow(
      dialog.getByText(
        `撤销 ${GOVERNED_FIXTURES.longEmployeeName} 的邀请？`,
      ),
    );
    const cancel = dialog.getByRole("button", { name: "取消" });
    await expectWithinViewport(page, cancel);
    await cancel.click({ trial: true });
    await cancel.click();
    await expect(dialog).toHaveCount(0);

    await revoke.click();
    dialog = page.getByRole("dialog", { name: "撤销邀请" });
    const confirm = dialog.getByRole("button", { name: "继续撤销" });
    await expectWithinViewport(page, dialog);
    await expectWithinViewport(page, confirm);
    await confirm.click({ trial: true });
    await expectMobileOrganizationTouchTargets(page);
    await confirm.click();
    await expect(dialog).toHaveCount(0);
    await expect(revoke).toHaveCount(0);
    expect(state.invites).toHaveLength(1);
    expect(state.invites[0].status).toBe("revoked");
    expectMutation(
      state,
      "/api/v1/organization/invites/invite-1/revoke",
      null,
    );
    expect(state.organizationRequests).not.toContain(
      "GET /api/v1/organization/stores",
    );
    expect(
      state.organizationRequests.every(
        (request) =>
          request.includes("/organization/members") ||
          request.includes("/organization/invites"),
      ),
    ).toBe(true);
    const logout = page.getByRole("button", { name: "退出登录" });
    await expectAboveMobileNavigation(page, logout);
    await expectWithinViewport(page, logout);
    await expectNoHorizontalOverflow(page);
    expectNoUnexpectedRequests(state);
  });

  test("employee profile has identity and logout without organization requests", async ({
    page,
  }) => {
    const state = await createGovernedOnboardingApi(page, "store_employee");
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/");
    await page.getByRole("button", { name: "我的" }).click();

    const identity = page.getByRole("region", { name: "测试员工" });
    await expect(identity).toContainText("门店员工");
    await expect(identity).toContainText("荷小悦首店");
    await expect(page.getByRole("button", { name: "退出登录" })).toBeVisible();
    await expect(page.getByText("门店与成员", { exact: true })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "新建门店" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "邀请店长" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "邀请员工" })).toHaveCount(0);
    expect(state.organizationRequests).toEqual([]);
    await expectWithinViewport(page, page.locator(".mobile-context-bar"));
    await expectHorizontallyWithinViewport(
      page,
      page.locator(".organization-panel"),
    );
    const logout = page.getByRole("button", { name: "退出登录" });
    await expectAboveMobileNavigation(page, logout);
    await expectWithinViewport(page, logout);
    await expectMobileOrganizationTouchTargets(page);
    await expectNoHorizontalOverflow(page);
    expectNoUnexpectedRequests(state);
  });

  test("recipient redeems a scrubbed invite fragment before loading the role home", async ({
    page,
  }) => {
    const state = await createGovernedOnboardingApi(page, "store_employee", {
      requireInviteRedemption: true,
    });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(`/#invite=${GOVERNED_FIXTURES.inviteToken}`);

    await expect.poll(() => state.redeemStarted).toBe(true);
    expect(state.meRequests).toHaveLength(0);
    state.releaseRedeemResponse();

    await expect(
      page.getByRole("textbox", { name: "问问题，或记录刚刚发生的事" }),
    ).toBeEnabled();
    expect(state.meRequests).toEqual(["GET /api/v1/me"]);
    const composer = page.getByTestId("composer");
    await composer.scrollIntoViewIfNeeded();
    await expectWithinViewport(page, composer);
    await page.getByRole("button", { name: "我的" }).click();
    const identity = page.getByRole("region", { name: "测试员工" });
    await expect(
      identity.getByRole("heading", { name: "测试员工", exact: true }),
    ).toBeVisible();
    await expect(identity.getByText("门店员工", { exact: true })).toBeVisible();
    await expect(identity.getByText("荷小悦首店", { exact: true })).toBeVisible();
    await identity.scrollIntoViewIfNeeded();
    await expectWithinViewport(page, identity);
    await expectHorizontallyWithinViewport(
      page,
      page.locator(".organization-panel"),
    );
    expect(GOVERNED_FIXTURES.inviteToken.length).toBeGreaterThanOrEqual(43);
    expect(GOVERNED_FIXTURES.inviteToken).toMatch(/^[A-Za-z0-9._~-]+$/);
    expect(state.redeemHashes).toEqual([""]);
    expect(state.redeemBodies).toEqual([
      { token: GOVERNED_FIXTURES.inviteToken },
    ]);
    expectMutation(state, "/api/v1/onboarding/invites/redeem", {
      token: GOVERNED_FIXTURES.inviteToken,
    });
    expect(new URL(page.url()).hash).toBe("");
    expect(page.url()).not.toContain(GOVERNED_FIXTURES.inviteToken);
    await expect(
      page.getByText(GOVERNED_FIXTURES.inviteToken, { exact: true }),
    ).toHaveCount(0);
    expect(await page.locator("body").textContent()).not.toContain(
      GOVERNED_FIXTURES.inviteToken,
    );
    const browserStorage = await page.evaluate(() => ({
      local: JSON.stringify({ ...localStorage }),
      session: JSON.stringify({ ...sessionStorage }),
    }));
    expect(browserStorage.local).not.toContain(GOVERNED_FIXTURES.inviteToken);
    expect(browserStorage.session).not.toContain(
      GOVERNED_FIXTURES.inviteToken,
    );
    await expectWithinViewport(page, page.locator(".mobile-context-bar"));
    await expectNoHorizontalOverflow(page);
    expectNoUnexpectedRequests(state);
  });
});
