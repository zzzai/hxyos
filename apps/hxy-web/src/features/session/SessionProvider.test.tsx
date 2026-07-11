import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { MeRequestError, type MeResponse } from "../../api/client";
import {
  SessionProvider,
  useSession,
  type SessionGrantExchanger,
  type SessionLoader,
} from "./SessionProvider";

const TEST_SESSION: MeResponse = {
  user: {
    account_id: "account-test",
    display_name: "测试用户",
  },
  active_assignment: {
    assignment_id: "assignment-test",
    organization: { id: "organization-test", name: "测试组织" },
    store: { id: "store-test", name: "测试门店" },
    role: "store_manager",
    role_label: "店长",
    capabilities: ["conversation:use", "store:read", "tasks:read"],
  },
  available_assignments: [],
};
const SESSION_GRANT = "g".repeat(64);

function SessionProbe() {
  const { status, session, retry } = useSession();

  return (
    <div>
      <span data-testid="session-status">{status}</span>
      <span data-testid="session-role">
        {session?.active_assignment.role ?? "none"}
      </span>
      <button type="button" onClick={retry}>
        重试身份
      </button>
    </div>
  );
}

afterEach(() => {
  window.history.replaceState({}, "", "/");
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("SessionProvider", () => {
  it("uses an injected initial session without calling the loader", () => {
    const loader = vi.fn<SessionLoader>();

    render(
      <SessionProvider loader={loader} initialSession={TEST_SESSION}>
        <SessionProbe />
      </SessionProvider>,
    );

    expect(screen.getByTestId("session-status")).toHaveTextContent(
      "authenticated",
    );
    expect(screen.getByTestId("session-role")).toHaveTextContent(
      "store_manager",
    );
    expect(loader).not.toHaveBeenCalled();
  });

  it("moves from loading to authenticated with an injected loader", async () => {
    let resolveSession: (session: MeResponse) => void = () => undefined;
    const loader = vi.fn<SessionLoader>(
      () =>
        new Promise((resolve) => {
          resolveSession = resolve;
        }),
    );

    render(
      <SessionProvider loader={loader}>
        <SessionProbe />
      </SessionProvider>,
    );

    expect(screen.getByTestId("session-status")).toHaveTextContent("loading");
    resolveSession(TEST_SESSION);

    await waitFor(() =>
      expect(screen.getByTestId("session-status")).toHaveTextContent(
        "authenticated",
      ),
    );
    expect(screen.getByTestId("session-role")).toHaveTextContent(
      "store_manager",
    );
  });

  it("loads /api/v1/me with included credentials and no browser token", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(TEST_SESSION), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    const storageRead = vi.spyOn(Storage.prototype, "getItem");
    vi.stubGlobal("fetch", fetchMock);

    render(
      <SessionProvider>
        <SessionProbe />
      </SessionProvider>,
    );

    await waitFor(() =>
      expect(screen.getByTestId("session-status")).toHaveTextContent(
        "authenticated",
      ),
    );
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/me",
      expect.objectContaining({ credentials: "include" }),
    );
    const requestOptions = fetchMock.mock.calls[0][1] as RequestInit;
    expect(new Headers(requestOptions.headers).has("Authorization")).toBe(false);
    expect(storageRead).not.toHaveBeenCalled();
  });

  it("surfaces unauthorized without retaining a session", async () => {
    const loader = vi
      .fn<SessionLoader>()
      .mockRejectedValue(new MeRequestError(401, "Unauthorized"));

    render(
      <SessionProvider loader={loader}>
        <SessionProbe />
      </SessionProvider>,
    );

    await waitFor(() =>
      expect(screen.getByTestId("session-status")).toHaveTextContent(
        "unauthorized",
      ),
    );
    expect(screen.getByTestId("session-role")).toHaveTextContent("none");
  });

  it("clears and exchanges a fragment grant before loading the session", async () => {
    const order: string[] = [];
    window.history.replaceState(
      {},
      "",
      `/#hxy_session_grant=${SESSION_GRANT}`,
    );
    const grantExchanger = vi.fn<SessionGrantExchanger>(async (grant) => {
      expect(grant).toBe(SESSION_GRANT);
      expect(window.location.hash).toBe("");
      order.push("exchange");
    });
    const loader = vi.fn<SessionLoader>(async () => {
      order.push("me");
      return TEST_SESSION;
    });

    render(
      <SessionProvider loader={loader} grantExchanger={grantExchanger}>
        <SessionProbe />
      </SessionProvider>,
    );

    await waitFor(() =>
      expect(screen.getByTestId("session-status")).toHaveTextContent(
        "authenticated",
      ),
    );
    expect(order).toEqual(["exchange", "me"]);
    expect(window.location.href).not.toContain(SESSION_GRANT);
    expect(document.body.textContent).not.toContain(SESSION_GRANT);
  });

  it("clears an invalid or consumed grant and stays unauthorized", async () => {
    window.history.replaceState(
      {},
      "",
      `/#hxy_session_grant=${SESSION_GRANT}`,
    );
    const grantExchanger = vi
      .fn<SessionGrantExchanger>()
      .mockRejectedValue(new MeRequestError(401, "Unauthorized"));
    const loader = vi.fn<SessionLoader>();

    render(
      <SessionProvider loader={loader} grantExchanger={grantExchanger}>
        <SessionProbe />
      </SessionProvider>,
    );

    await waitFor(() =>
      expect(screen.getByTestId("session-status")).toHaveTextContent(
        "unauthorized",
      ),
    );
    expect(window.location.hash).toBe("");
    expect(loader).not.toHaveBeenCalled();
    expect(document.body.textContent).not.toContain(SESSION_GRANT);
  });

  it("posts the fragment grant in a same-origin body before requesting me", async () => {
    window.history.replaceState(
      {},
      "",
      `/#hxy_session_grant=${SESSION_GRANT}`,
    );
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ status: "authenticated" }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify(TEST_SESSION), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );
    vi.stubGlobal("fetch", fetchMock);

    render(
      <SessionProvider>
        <SessionProbe />
      </SessionProvider>,
    );

    await waitFor(() =>
      expect(screen.getByTestId("session-status")).toHaveTextContent(
        "authenticated",
      ),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "/api/v1/auth/session-grant",
      expect.objectContaining({
        method: "POST",
        credentials: "include",
        body: JSON.stringify({ grant: SESSION_GRANT }),
      }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/api/v1/me",
      expect.objectContaining({ credentials: "include" }),
    );
    expect(window.location.hash).toBe("");
  });

  it("surfaces an error and retries through the injected loader", async () => {
    const user = userEvent.setup();
    let resolveRetry: (session: MeResponse) => void = () => undefined;
    const loader = vi
      .fn<SessionLoader>()
      .mockRejectedValueOnce(new Error("network unavailable"))
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            resolveRetry = resolve;
          }),
      );

    render(
      <SessionProvider loader={loader}>
        <SessionProbe />
      </SessionProvider>,
    );

    await waitFor(() =>
      expect(screen.getByTestId("session-status")).toHaveTextContent("error"),
    );
    await user.click(screen.getByRole("button", { name: "重试身份" }));

    expect(screen.getByTestId("session-status")).toHaveTextContent("loading");
    act(() => resolveRetry(TEST_SESSION));
    await waitFor(() =>
      expect(screen.getByTestId("session-status")).toHaveTextContent(
        "authenticated",
      ),
    );
    expect(loader).toHaveBeenCalledTimes(2);
  });
});
