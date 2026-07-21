import { expect, type Locator, type Page } from "@playwright/test";

export const GOVERNED_FIXTURES = Object.freeze({
  appOrigin: "http://127.0.0.1:4173",
  storeId: "store-governed",
  createdStoreId: "store-created",
  inviteToken: `invite_token-${"a".repeat(48)}`,
  oneTimeLink: `http://127.0.0.1:4173/#invite=${"manager_token-" + "b".repeat(48)}`,
  longManagerName: `Manager${"UnbrokenDisplayName".repeat(10)}`,
  longStoreName: `HXY${"UnbrokenStoreName".repeat(12)}`,
  longEmployeeName: `Employee${"UnbrokenDisplayName".repeat(10)}`,
});

export type GovernedRole = "founder" | "store_manager" | "store_employee";

interface GovernedStore {
  id: string;
  name: string;
  city: string;
  address: string;
  status: "active";
}

interface GovernedMember {
  assignment_id: string;
  store_id: string;
  display_name: string;
  role: "store_manager" | "store_employee";
  status: "active";
}

interface GovernedInvite {
  id: string;
  store_id: string;
  role: "store_manager" | "store_employee";
  display_name: string;
  status: "pending" | "redeemed" | "revoked";
  expires_at: string;
}

interface RecordedMutation {
  method: "POST";
  path: string;
  body: Record<string, unknown> | null;
  origin: string | undefined;
}

export interface GovernedOnboardingState {
  stores: GovernedStore[];
  members: GovernedMember[];
  invites: GovernedInvite[];
  redeemBodies: Array<Record<string, unknown>>;
  redeemHashes: string[];
  meRequests: string[];
  organizationRequests: string[];
  mutations: RecordedMutation[];
  unexpectedRequests: string[];
  redeemStarted: boolean;
  releaseRedeemResponse: () => void;
  redeemed: boolean;
}

export function expectMutation(
  state: GovernedOnboardingState,
  path: string,
  body: Record<string, unknown> | null,
) {
  expect(state.mutations.filter((mutation) => mutation.path === path)).toEqual([
    {
      method: "POST",
      path,
      body,
      origin: GOVERNED_FIXTURES.appOrigin,
    },
  ]);
}

export function expectNoUnexpectedRequests(state: GovernedOnboardingState) {
  expect(state.unexpectedRequests).toEqual([]);
}

export async function installClipboardWriteSpy(page: Page) {
  await page.addInitScript(() => {
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: {
        writeText: async (value: string) => {
          (
            window as typeof window & { __hxyClipboardWrite?: string }
          ).__hxyClipboardWrite = value;
        },
      },
    });
  });
}

export async function expectClipboardWrite(page: Page, expected: string) {
  expect(
    await page.evaluate(
      () =>
        (
          window as typeof window & { __hxyClipboardWrite?: string }
        ).__hxyClipboardWrite,
    ),
  ).toBe(expected);
}

function governedSession(role: GovernedRole) {
  const isFounder = role === "founder";
  const isManager = role === "store_manager";
  return {
    user: {
      account_id: `account-${role}`,
      display_name: isManager
        ? GOVERNED_FIXTURES.longManagerName
        : `测试${isFounder ? "创始人" : "员工"}`,
    },
    active_assignment: {
      assignment_id: `assignment-${role}`,
      organization: { id: "organization-governed", name: "荷小悦" },
      store: isFounder
        ? null
        : {
            id: GOVERNED_FIXTURES.storeId,
            name: isManager
              ? GOVERNED_FIXTURES.longStoreName
              : "荷小悦首店",
          },
      role,
      role_label: isFounder ? "创始人" : isManager ? "店长" : "门店员工",
      capabilities: ["conversation:use", "materials:read", "tasks:read"],
    },
    available_assignments: [],
  };
}

export async function createGovernedOnboardingApi(
  page: Page,
  role: GovernedRole,
  options: { requireInviteRedemption?: boolean } = {},
): Promise<GovernedOnboardingState> {
  let releaseRedeemResponse = () => {};
  const redeemResponseGate = new Promise<void>((resolve) => {
    releaseRedeemResponse = resolve;
  });
  const session = governedSession(role);
  const stores: GovernedStore[] = [
    {
      id: GOVERNED_FIXTURES.storeId,
      name:
        role === "store_manager"
          ? GOVERNED_FIXTURES.longStoreName
          : "荷小悦首店",
      city: "长沙",
      address: "芙蓉路 1 号",
      status: "active",
    },
  ];
  const members: GovernedMember[] =
    role === "store_manager"
      ? [
          {
            assignment_id: "assignment-store_manager",
            store_id: GOVERNED_FIXTURES.storeId,
            display_name: GOVERNED_FIXTURES.longManagerName,
            role: "store_manager",
            status: "active",
          },
          {
            assignment_id: "assignment-existing-employee",
            store_id: GOVERNED_FIXTURES.storeId,
            display_name: GOVERNED_FIXTURES.longEmployeeName,
            role: "store_employee",
            status: "active",
          },
        ]
      : [
          {
            assignment_id: "assignment-existing-manager",
            store_id: GOVERNED_FIXTURES.storeId,
            display_name: "首店店长",
            role: "store_manager",
            status: "active",
          },
        ];
  const state: GovernedOnboardingState = {
    stores,
    members,
    invites: [],
    redeemBodies: [],
    redeemHashes: [],
    meRequests: [],
    organizationRequests: [],
    mutations: [],
    unexpectedRequests: [],
    redeemStarted: false,
    releaseRedeemResponse,
    redeemed: !options.requireInviteRedemption,
  };

  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const method = request.method();
    const path = new URL(request.url()).pathname;
    if (path.startsWith("/api/v1/organization/")) {
      state.organizationRequests.push(`${method} ${path}`);
    }

    if (path === "/api/v1/me" && method === "GET") {
      state.meRequests.push(`${method} ${path}`);
      await route.fulfill(
        state.redeemed
          ? { status: 200, json: session }
          : { status: 401, json: { detail: "Unauthorized" } },
      );
      return;
    }
    if (path === "/api/v1/conversations" && method === "GET") {
      await route.fulfill({ status: 200, json: { items: [], count: 0 } });
      return;
    }
    if (path === "/api/v1/journeys/suggestions" && method === "GET") {
      await route.fulfill({ status: 200, json: { items: [] } });
      return;
    }
    if (path === "/api/v1/materials" && method === "GET") {
      await route.fulfill({ status: 200, json: { items: [], count: 0 } });
      return;
    }
    if (path === "/api/v1/tasks" && method === "GET") {
      await route.fulfill({ status: 200, json: { items: [], count: 0 } });
      return;
    }
    if (path === "/api/v1/organization/stores" && method === "GET") {
      await route.fulfill({ status: 200, json: state.stores });
      return;
    }
    if (path === "/api/v1/organization/stores" && method === "POST") {
      const body = request.postDataJSON() as Record<string, unknown>;
      state.mutations.push({
        method,
        path,
        body,
        origin: request.headers().origin,
      });
      const store: GovernedStore = {
        id: GOVERNED_FIXTURES.createdStoreId,
        name: body.name as string,
        city: body.city as string,
        address: body.address as string,
        status: "active",
      };
      state.stores.push(store);
      await route.fulfill({ status: 201, json: store });
      return;
    }
    if (path === "/api/v1/organization/members" && method === "GET") {
      await route.fulfill({ status: 200, json: state.members });
      return;
    }
    if (path === "/api/v1/organization/invites" && method === "GET") {
      await route.fulfill({ status: 200, json: state.invites });
      return;
    }
    if (path === "/api/v1/organization/invites" && method === "POST") {
      const body = request.postDataJSON() as Record<string, unknown>;
      state.mutations.push({
        method,
        path,
        body,
        origin: request.headers().origin,
      });
      const invite: GovernedInvite = {
        id: `invite-${state.invites.length + 1}`,
        store_id:
          typeof body.store_id === "string"
            ? body.store_id
            : GOVERNED_FIXTURES.storeId,
        role: body.role as "store_manager" | "store_employee",
        display_name: body.display_name as string,
        status: "pending",
        expires_at: "2026-07-15T10:00:00Z",
      };
      state.invites.push(invite);
      await route.fulfill({
        status: 201,
        json: {
          invite: {
            id: invite.id,
            role: invite.role,
            display_name: invite.display_name,
            expires_at: invite.expires_at,
          },
          one_time_link: GOVERNED_FIXTURES.oneTimeLink,
        },
      });
      return;
    }
    const revokeMatch =
      /^\/api\/v1\/organization\/invites\/([^/]+)\/revoke$/.exec(path);
    if (revokeMatch && method === "POST") {
      state.mutations.push({
        method,
        path,
        body: null,
        origin: request.headers().origin,
      });
      const invite = state.invites.find(
        (candidate) => candidate.id === revokeMatch[1],
      );
      if (!invite) {
        await route.fulfill({ status: 404, json: { detail: "Not found" } });
        return;
      }
      invite.status = "revoked";
      await route.fulfill({ status: 200, json: invite });
      return;
    }
    if (path === "/api/v1/onboarding/invites/redeem" && method === "POST") {
      const body = request.postDataJSON() as Record<string, unknown>;
      state.redeemBodies.push(body);
      state.redeemHashes.push(new URL(request.frame().url()).hash);
      state.mutations.push({
        method,
        path,
        body,
        origin: request.headers().origin,
      });
      state.redeemStarted = true;
      if (options.requireInviteRedemption) {
        await redeemResponseGate;
      }
      state.redeemed = true;
      await route.fulfill({ status: 200, json: { status: "authenticated" } });
      return;
    }
    if (path === "/api/v1/auth/logout" && method === "POST") {
      state.mutations.push({
        method,
        path,
        body: null,
        origin: request.headers().origin,
      });
      await route.fulfill({ status: 204, body: "" });
      return;
    }
    state.unexpectedRequests.push(`${method} ${path}`);
    await route.fulfill({
      status: 599,
      json: { detail: `Unexpected E2E request: ${method} ${path}` },
    });
  });

  return state;
}

export async function expectWithinViewport(page: Page, locator: Locator) {
  await expect(locator).toBeVisible();
  const box = await locator.boundingBox();
  const viewport = page.viewportSize();
  expect(box).not.toBeNull();
  expect(viewport).not.toBeNull();
  expect(box!.x).toBeGreaterThanOrEqual(0);
  expect(box!.x + box!.width).toBeLessThanOrEqual(viewport!.width);
  expect(box!.y).toBeGreaterThanOrEqual(0);
  expect(box!.y + box!.height).toBeLessThanOrEqual(viewport!.height);
}

export async function expectHorizontallyWithinViewport(
  page: Page,
  locator: Locator,
) {
  await expect(locator).toBeVisible();
  const box = await locator.boundingBox();
  const viewport = page.viewportSize();
  expect(box).not.toBeNull();
  expect(viewport).not.toBeNull();
  expect(box!.x).toBeGreaterThanOrEqual(0);
  expect(box!.x + box!.width).toBeLessThanOrEqual(viewport!.width);
}

export async function expectNoHorizontalOverflow(page: Page) {
  const widths = await page.evaluate(() => ({
    viewport: window.innerWidth,
    document: document.documentElement.scrollWidth,
  }));
  expect(widths.document).toBeLessThanOrEqual(widths.viewport);
}

export async function expectTextWrapsWithoutOverflow(locator: Locator) {
  const metrics = await locator.evaluate((element) => {
    const parent = element.parentElement;
    if (!parent) return null;
    const range = document.createRange();
    range.selectNodeContents(element);
    const lineTops = new Set(
      Array.from(range.getClientRects())
        .filter((rect) => rect.width > 0 && rect.height > 0)
        .map((rect) => Math.round(rect.top * 2) / 2),
    );
    const rangeRect = range.getBoundingClientRect();
    const childRect = element.getBoundingClientRect();
    const parentRect = parent.getBoundingClientRect();
    return {
      lineCount: lineTops.size,
      childLeft: childRect.left,
      childRight: childRect.right,
      childTop: childRect.top,
      childBottom: childRect.bottom,
      contentTop: rangeRect.top,
      contentBottom: rangeRect.bottom,
      parentLeft: parentRect.left,
      parentRight: parentRect.right,
      clientWidth: element.clientWidth,
      scrollWidth: element.scrollWidth,
      clientHeight: element.clientHeight,
      scrollHeight: element.scrollHeight,
      parentClientWidth: parent.clientWidth,
      parentScrollWidth: parent.scrollWidth,
    };
  });
  expect(metrics).not.toBeNull();
  expect(metrics!.lineCount).toBeGreaterThan(1);
  expect(metrics!.childLeft).toBeGreaterThanOrEqual(metrics!.parentLeft);
  expect(metrics!.childRight).toBeLessThanOrEqual(metrics!.parentRight);
  expect(metrics!.contentTop).toBeGreaterThanOrEqual(metrics!.childTop - 1);
  expect(metrics!.contentBottom).toBeLessThanOrEqual(
    metrics!.childBottom + 1,
  );
  expect(metrics!.scrollWidth).toBeLessThanOrEqual(metrics!.clientWidth);
  expect(metrics!.scrollHeight - metrics!.clientHeight).toBeLessThanOrEqual(1);
  expect(metrics!.parentScrollWidth).toBeLessThanOrEqual(
    metrics!.parentClientWidth,
  );
}

export async function expectEllipsisContained(locator: Locator) {
  const metrics = await locator.evaluate((element) => {
    const parent = element.parentElement;
    if (!parent) return null;
    const rect = element.getBoundingClientRect();
    const parentRect = parent.getBoundingClientRect();
    const style = getComputedStyle(element);
    return {
      left: rect.left,
      right: rect.right,
      parentLeft: parentRect.left,
      parentRight: parentRect.right,
      clientWidth: element.clientWidth,
      scrollWidth: element.scrollWidth,
      overflow: style.overflow,
      textOverflow: style.textOverflow,
    };
  });
  expect(metrics).not.toBeNull();
  expect(metrics!.left).toBeGreaterThanOrEqual(metrics!.parentLeft);
  expect(metrics!.right).toBeLessThanOrEqual(metrics!.parentRight);
  expect(metrics!.overflow).toBe("hidden");
  expect(metrics!.textOverflow).toBe("ellipsis");
  expect(metrics!.scrollWidth).toBeGreaterThan(metrics!.clientWidth);
}

export async function expectAboveMobileNavigation(
  page: Page,
  locator: Locator,
) {
  await locator.scrollIntoViewIfNeeded();
  const box = await locator.boundingBox();
  const navigationBox = await page
    .getByRole("navigation", { name: "移动端导航" })
    .boundingBox();
  expect(box).not.toBeNull();
  expect(navigationBox).not.toBeNull();
  expect(box!.y + box!.height).toBeLessThanOrEqual(navigationBox!.y);
}

export async function expectMobileOrganizationTouchTargets(page: Page) {
  const undersized = await page
    .locator(
      ".organization-panel button, .organization-panel input, .organization-panel select, .organization-dialog button",
    )
    .evaluateAll((elements) =>
      elements.flatMap((element) => {
        const rect = element.getBoundingClientRect();
        if (rect.width === 0 || rect.height === 0) return [];
        return rect.width >= 44 && rect.height >= 44
          ? []
          : [
              {
                label:
                  element.getAttribute("aria-label") ?? element.textContent,
                width: rect.width,
                height: rect.height,
              },
            ];
      }),
    );
  expect(undersized).toEqual([]);
}

export async function expectMobileTouchTarget(locator: Locator) {
  await expect(locator).toBeVisible();
  const box = await locator.boundingBox();
  expect(box).not.toBeNull();
  expect(box!.width).toBeGreaterThanOrEqual(44);
  expect(box!.height).toBeGreaterThanOrEqual(44);
}
