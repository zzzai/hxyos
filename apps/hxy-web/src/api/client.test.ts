import { afterEach, describe, expect, it, vi } from "vitest";

import {
  OnboardingRequestError,
  productOnboardingClient,
} from "./client";

const EXPIRES_AT = "2026-07-15T10:00:00Z";

function stubJsonResponse(payload: unknown, status = 200) {
  const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(
    new Response(JSON.stringify(payload), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function expectRequest(
  fetchMock: ReturnType<typeof vi.fn<typeof fetch>>,
  path: string,
  method?: "POST",
  body?: unknown,
) {
  expect(fetchMock).toHaveBeenCalledTimes(1);
  const [actualPath, init] = fetchMock.mock.calls[0];
  const headers = new Headers(init?.headers);

  expect(actualPath).toBe(path);
  expect(init?.method).toBe(method);
  expect(init?.credentials).toBe("include");
  expect(headers.get("Accept")).toBe("application/json");
  expect(headers.has("Origin")).toBe(false);

  if (method === "POST") {
    expect(headers.get("Content-Type")).toBe("application/json");
  } else {
    expect(headers.has("Content-Type")).toBe(false);
  }

  if (body === undefined) {
    expect(init?.body).toBeUndefined();
  } else {
    expect(JSON.parse(String(init?.body))).toEqual(body);
  }
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("productOnboardingClient", () => {
  it("lists stores with a bounded response", async () => {
    const fetchMock = stubJsonResponse([
      {
        id: "store-1",
        name: "荷小悦一店",
        city: "长沙",
        address: "芙蓉路 1 号",
        status: "active",
        organization_id: "secret-organization",
        account_id: "secret-account",
        token: "secret-token",
        token_hash: "secret-token-hash",
        one_time_link: "https://example.invalid/#invite=secret-token",
        unexpected: "drop-me",
      },
    ]);

    await expect(productOnboardingClient.listStores()).resolves.toEqual([
      {
        id: "store-1",
        name: "荷小悦一店",
        city: "长沙",
        address: "芙蓉路 1 号",
        status: "active",
      },
    ]);
    expectRequest(fetchMock, "/api/v1/organization/stores");
  });

  it("creates a store without sending client-supplied organization authority", async () => {
    const fetchMock = stubJsonResponse(
      {
        id: "store-2",
        name: "荷小悦二店",
        city: "长沙",
        address: "湘江路 2 号",
        status: "active",
        organization_id: "secret-organization",
        token_hash: "secret-token-hash",
      },
      201,
    );
    const request = {
      name: "荷小悦二店",
      city: "长沙",
      address: "湘江路 2 号",
      organization_id: "attacker-organization",
    };

    await expect(productOnboardingClient.createStore(request)).resolves.toEqual({
      id: "store-2",
      name: "荷小悦二店",
      city: "长沙",
      address: "湘江路 2 号",
      status: "active",
    });
    expectRequest(fetchMock, "/api/v1/organization/stores", "POST", {
      name: "荷小悦二店",
      city: "长沙",
      address: "湘江路 2 号",
    });
  });

  it("lists members with canonical roles and bounded fields", async () => {
    const fetchMock = stubJsonResponse([
      {
        assignment_id: "assignment-1",
        store_id: "store-1",
        display_name: "小悦店长",
        role: "store_manager",
        status: "active",
        account_id: "secret-account",
        organization_id: "secret-organization",
        token: "secret-token",
        extra: true,
      },
    ]);

    await expect(productOnboardingClient.listMembers()).resolves.toEqual([
      {
        assignment_id: "assignment-1",
        store_id: "store-1",
        display_name: "小悦店长",
        role: "store_manager",
        status: "active",
      },
    ]);
    expectRequest(fetchMock, "/api/v1/organization/members");
  });

  it("lists invites without retaining token material or extra fields", async () => {
    const fetchMock = stubJsonResponse([
      {
        id: "invite-1",
        store_id: "store-1",
        role: "store_employee",
        display_name: "小悦员工",
        status: "pending",
        expires_at: EXPIRES_AT,
        token: "secret-token",
        token_hash: "secret-token-hash",
        one_time_link: "https://example.invalid/#invite=secret-token",
        account_id: "secret-account",
        organization_id: "secret-organization",
        unexpected: "drop-me",
      },
    ]);

    await expect(productOnboardingClient.listInvites()).resolves.toEqual([
      {
        id: "invite-1",
        store_id: "store-1",
        role: "store_employee",
        display_name: "小悦员工",
        status: "pending",
        expires_at: EXPIRES_AT,
      },
    ]);
    expectRequest(fetchMock, "/api/v1/organization/invites");
  });

  it("creates an invite and retains only the intentional one-time link", async () => {
    const fetchMock = stubJsonResponse(
      {
        invite: {
          id: "invite-2",
          role: "store_manager",
          display_name: "新店长",
          expires_at: EXPIRES_AT,
          store_id: "secret-store",
          token: "secret-token",
          token_hash: "secret-token-hash",
          organization_id: "secret-organization",
          status: "pending",
          unexpected: "drop-me",
        },
        one_time_link: "https://hxy.example/#invite=one-time-token",
        token: "secret-token",
        token_hash: "secret-token-hash",
        account_id: "secret-account",
        organization_id: "secret-organization",
        unexpected: "drop-me",
      },
      201,
    );
    const request = {
      store_id: "store-2",
      role: "store_manager" as const,
      display_name: "新店长",
      organization_id: "attacker-organization",
    };

    await expect(productOnboardingClient.createInvite(request)).resolves.toEqual({
      invite: {
        id: "invite-2",
        role: "store_manager",
        display_name: "新店长",
        expires_at: EXPIRES_AT,
      },
      one_time_link: "https://hxy.example/#invite=one-time-token",
    });
    expectRequest(fetchMock, "/api/v1/organization/invites", "POST", {
      store_id: "store-2",
      role: "store_manager",
      display_name: "新店长",
    });
  });

  it("omits an undefined store ID when creating an invite", async () => {
    const fetchMock = stubJsonResponse(
      {
        invite: {
          id: "invite-3",
          role: "store_employee",
          display_name: "新员工",
          expires_at: EXPIRES_AT,
        },
        one_time_link: "https://hxy.example/#invite=employee-token",
      },
      201,
    );

    await productOnboardingClient.createInvite({
      role: "store_employee",
      display_name: "新员工",
    });

    expectRequest(fetchMock, "/api/v1/organization/invites", "POST", {
      role: "store_employee",
      display_name: "新员工",
    });
  });

  it("revokes an encoded invite ID without a request body", async () => {
    const fetchMock = stubJsonResponse({
      id: "invite-4",
      store_id: "store-1",
      role: "store_employee",
      display_name: "已撤销员工",
      status: "revoked",
      expires_at: EXPIRES_AT,
      token_hash: "secret-token-hash",
    });

    await expect(
      productOnboardingClient.revokeInvite("invite/with ? reserved"),
    ).resolves.toEqual({
      id: "invite-4",
      store_id: "store-1",
      role: "store_employee",
      display_name: "已撤销员工",
      status: "revoked",
      expires_at: EXPIRES_AT,
    });
    expectRequest(
      fetchMock,
      "/api/v1/organization/invites/invite%2Fwith%20%3F%20reserved/revoke",
      "POST",
    );
  });

  it("deactivates an encoded assignment ID without a request body", async () => {
    const fetchMock = stubJsonResponse({
      assignment_id: "assignment-2",
      store_id: "store-1",
      display_name: "离职员工",
      role: "store_employee",
      status: "inactive",
      account_id: "secret-account",
    });

    await expect(
      productOnboardingClient.deactivateMember("assignment/with ? reserved"),
    ).resolves.toEqual({
      assignment_id: "assignment-2",
      store_id: "store-1",
      display_name: "离职员工",
      role: "store_employee",
      status: "inactive",
    });
    expectRequest(
      fetchMock,
      "/api/v1/organization/members/assignment%2Fwith%20%3F%20reserved/deactivate",
      "POST",
    );
  });

  it("redeems an invite by sending the token only in JSON", async () => {
    const token = "redeem-secret-token-that-must-not-appear-in-the-url";
    const fetchMock = stubJsonResponse({
      status: "authenticated",
      token,
      account_id: "secret-account",
      organization_id: "secret-organization",
      unexpected: "drop-me",
    });
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
    const consoleLog = vi.spyOn(console, "log").mockImplementation(() => {});
    const consoleWarn = vi.spyOn(console, "warn").mockImplementation(() => {});

    await expect(productOnboardingClient.redeemInvite(token)).resolves.toEqual({
      status: "authenticated",
    });
    expectRequest(
      fetchMock,
      "/api/v1/onboarding/invites/redeem",
      "POST",
      { token },
    );
    expect(String(fetchMock.mock.calls[0][0])).not.toContain(token);
    expect(consoleError).not.toHaveBeenCalled();
    expect(consoleLog).not.toHaveBeenCalled();
    expect(consoleWarn).not.toHaveBeenCalled();
  });

  it.each([
    ["stores must be an array", "listStores", { items: [] }],
    [
      "stores require all fields",
      "listStores",
      [{ id: "store-1", name: "Store", city: "City", status: "active" }],
    ],
    [
      "stores validate status",
      "listStores",
      [
        {
          id: "store-1",
          name: "Store",
          city: "City",
          address: "Address",
          status: "deleted",
        },
      ],
    ],
    [
      "members validate canonical roles",
      "listMembers",
      [
        {
          assignment_id: "assignment-1",
          store_id: "store-1",
          display_name: "Member",
          role: "owner",
          status: "active",
        },
      ],
    ],
    [
      "members validate status",
      "listMembers",
      [
        {
          assignment_id: "assignment-1",
          store_id: "store-1",
          display_name: "Member",
          role: "store_employee",
          status: "deleted",
        },
      ],
    ],
    [
      "invites validate invite roles",
      "listInvites",
      [
        {
          id: "invite-1",
          store_id: "store-1",
          display_name: "Invitee",
          role: "founder",
          status: "pending",
          expires_at: EXPIRES_AT,
        },
      ],
    ],
    [
      "invites validate status",
      "listInvites",
      [
        {
          id: "invite-1",
          store_id: "store-1",
          display_name: "Invitee",
          role: "store_employee",
          status: "expired",
          expires_at: EXPIRES_AT,
        },
      ],
    ],
    [
      "invites require ISO expiry timestamps",
      "listInvites",
      [
        {
          id: "invite-1",
          store_id: "store-1",
          display_name: "Invitee",
          role: "store_employee",
          status: "pending",
          expires_at: "tomorrow",
        },
      ],
    ],
  ])("rejects malformed responses: %s", async (_name, method, payload) => {
    stubJsonResponse(payload);

    const request =
      method === "listStores"
        ? productOnboardingClient.listStores()
        : method === "listMembers"
          ? productOnboardingClient.listMembers()
          : productOnboardingClient.listInvites();

    await expect(request).rejects.toEqual(
      expect.objectContaining({
        name: "OnboardingRequestError",
        message: "Onboarding request failed",
        status: 200,
      }),
    );
  });

  it("rejects malformed create and redemption responses", async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            invite: {
              id: "invite-5",
              role: "store_employee",
              display_name: "Invitee",
              expires_at: "not-ISO",
            },
            one_time_link: "https://hxy.example/#invite=secret",
          }),
          { status: 201 },
        ),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ status: "pending" }), { status: 200 }),
      );
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      productOnboardingClient.createInvite({
        role: "store_employee",
        display_name: "Invitee",
      }),
    ).rejects.toBeInstanceOf(OnboardingRequestError);
    await expect(
      productOnboardingClient.redeemInvite("redemption-token"),
    ).rejects.toBeInstanceOf(OnboardingRequestError);
  });

  it("throws a bounded status-bearing error without reading an HTTP error body", async () => {
    const secret = "server-secret-token";
    const response = new Response(
      JSON.stringify({ detail: `Unauthorized ${secret}`, token: secret }),
      { status: 403 },
    );
    const jsonSpy = vi.spyOn(response, "json");
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(response);
    vi.stubGlobal("fetch", fetchMock);

    const error = await productOnboardingClient.listStores().catch((reason) => reason);

    expect(error).toBeInstanceOf(OnboardingRequestError);
    expect(error).toEqual(
      expect.objectContaining({
        name: "OnboardingRequestError",
        message: "Onboarding request failed",
        status: 403,
      }),
    );
    expect(String(error)).not.toContain(secret);
    expect(jsonSpy).not.toHaveBeenCalled();
  });

  it("does not reflect invite tokens from transport or malformed JSON errors", async () => {
    const token = "transport-secret-invite-token";
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockRejectedValueOnce(new Error(`network failure for ${token}`))
      .mockResolvedValueOnce(new Response(`invalid JSON ${token}`, { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    const transportError = await productOnboardingClient
      .redeemInvite(token)
      .catch((reason) => reason);
    const jsonError = await productOnboardingClient
      .redeemInvite(token)
      .catch((reason) => reason);

    expect(transportError).toEqual(
      expect.objectContaining({
        message: "Onboarding request failed",
        status: 0,
      }),
    );
    expect(jsonError).toEqual(
      expect.objectContaining({
        message: "Onboarding request failed",
        status: 200,
      }),
    );
    expect(String(transportError)).not.toContain(token);
    expect(String(jsonError)).not.toContain(token);
  });
});
