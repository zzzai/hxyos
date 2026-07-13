import { StrictMode } from "react";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { MeRequestError, type MeResponse } from "../../api/client";
import {
  SessionProvider,
  useSession,
  type SessionGrantExchanger,
  type SessionInviteExchanger,
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
const INVITE_TOKEN = "invite-token-that-must-remain-confidential";
const INVITED_SESSION: MeResponse = {
  ...TEST_SESSION,
  active_assignment: {
    ...TEST_SESSION.active_assignment,
    assignment_id: "assignment-invited",
    role: "store_employee",
    role_label: "门店员工",
  },
};

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
    const inviteExchanger = vi.fn<SessionInviteExchanger>();
    const loader = vi.fn<SessionLoader>(async () => {
      order.push("me");
      return TEST_SESSION;
    });

    render(
      <SessionProvider
        loader={loader}
        grantExchanger={grantExchanger}
        inviteExchanger={inviteExchanger}
      >
        <SessionProbe />
      </SessionProvider>,
    );

    await waitFor(() =>
      expect(screen.getByTestId("session-status")).toHaveTextContent(
        "authenticated",
      ),
    );
    expect(order).toEqual(["exchange", "me"]);
    expect(inviteExchanger).not.toHaveBeenCalled();
    expect(window.location.href).not.toContain(SESSION_GRANT);
    expect(document.body.textContent).not.toContain(SESSION_GRANT);
  });

  it("cleans an exact invite fragment before exchanging and loading me", async () => {
    const order: string[] = [];
    const historyState = { destination: "tasks" };
    window.history.replaceState(
      historyState,
      "",
      `/workspace?view=tasks#invite=${INVITE_TOKEN}`,
    );
    const replaceState = vi.spyOn(window.history, "replaceState");
    const inviteExchanger = vi.fn<SessionInviteExchanger>(async (token) => {
      expect(token).toBe(INVITE_TOKEN);
      expect(window.location.pathname).toBe("/workspace");
      expect(window.location.search).toBe("?view=tasks");
      expect(window.location.hash).toBe("");
      expect(window.history.state).toEqual(historyState);
      order.push("invite");
    });
    const grantExchanger = vi.fn<SessionGrantExchanger>();
    const loader = vi.fn<SessionLoader>(async () => {
      order.push("me");
      return INVITED_SESSION;
    });

    render(
      <SessionProvider
        loader={loader}
        grantExchanger={grantExchanger}
        inviteExchanger={inviteExchanger}
      >
        <SessionProbe />
      </SessionProvider>,
    );

    await waitFor(() =>
      expect(screen.getByTestId("session-status")).toHaveTextContent(
        "authenticated",
      ),
    );
    expect(order).toEqual(["invite", "me"]);
    expect(screen.getByTestId("session-role")).toHaveTextContent(
      "store_employee",
    );
    expect(grantExchanger).not.toHaveBeenCalled();
    expect(replaceState).toHaveBeenCalledWith(
      historyState,
      "",
      "/workspace?view=tasks",
    );
    expect(window.location.href).not.toContain(INVITE_TOKEN);
  });

  it("maps every invite exchange failure to the existing unauthorized state", async () => {
    window.history.replaceState({}, "", `/#invite=${INVITE_TOKEN}`);
    const inviteExchanger = vi
      .fn<SessionInviteExchanger>()
      .mockRejectedValue(
        new Error(`upstream leaked invite detail: ${INVITE_TOKEN}`),
      );
    const loader = vi.fn<SessionLoader>(async () => TEST_SESSION);

    render(
      <SessionProvider loader={loader} inviteExchanger={inviteExchanger}>
        <SessionProbe />
      </SessionProvider>,
    );

    await waitFor(() =>
      expect(screen.getByTestId("session-status")).toHaveTextContent(
        "unauthorized",
      ),
    );
    expect(screen.getByTestId("session-role")).toHaveTextContent("none");
    expect(loader).not.toHaveBeenCalled();
    expect(window.location.hash).toBe("");
    expect(document.body).not.toHaveTextContent(INVITE_TOKEN);
    expect(document.body).not.toHaveTextContent("upstream leaked invite detail");
  });

  it("redeems an invite only once under StrictMode", async () => {
    window.history.replaceState({}, "", `/#invite=${INVITE_TOKEN}`);
    const inviteExchanger = vi.fn<SessionInviteExchanger>(async () => undefined);
    const loader = vi.fn<SessionLoader>(async () => INVITED_SESSION);

    render(
      <StrictMode>
        <SessionProvider loader={loader} inviteExchanger={inviteExchanger}>
          <SessionProbe />
        </SessionProvider>
      </StrictMode>,
    );

    await waitFor(() =>
      expect(screen.getByTestId("session-status")).toHaveTextContent(
        "authenticated",
      ),
    );
    expect(inviteExchanger).toHaveBeenCalledTimes(1);
    expect(loader).toHaveBeenCalledTimes(1);
  });

  it("uses the onboarding client without leaking the invite outside its body", async () => {
    window.history.replaceState(
      { destination: "profile" },
      "",
      `/?view=profile#invite=${INVITE_TOKEN}`,
    );
    const fetchMock = vi.fn<typeof fetch>(async (request) => {
      const payload =
        String(request) === "/api/v1/onboarding/invites/redeem"
          ? { status: "authenticated" }
          : INVITED_SESSION;
      return new Response(JSON.stringify(payload), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    });
    const localStorageWrite = vi.spyOn(window.localStorage, "setItem");
    const sessionStorageWrite = vi.spyOn(window.sessionStorage, "setItem");
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
    const consoleLog = vi.spyOn(console, "log").mockImplementation(() => {});
    const consoleWarn = vi.spyOn(console, "warn").mockImplementation(() => {});
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
      "/api/v1/onboarding/invites/redeem",
      expect.objectContaining({
        method: "POST",
        credentials: "include",
        body: JSON.stringify({ token: INVITE_TOKEN }),
      }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/api/v1/me",
      expect.objectContaining({ credentials: "include" }),
    );
    for (const [request] of fetchMock.mock.calls) {
      expect(String(request)).not.toContain(INVITE_TOKEN);
    }
    expect(window.location.search).toBe("?view=profile");
    expect(window.location.href).not.toContain(INVITE_TOKEN);
    expect(document.body).not.toHaveTextContent(INVITE_TOKEN);
    expect(localStorageWrite).not.toHaveBeenCalled();
    expect(sessionStorageWrite).not.toHaveBeenCalled();
    expect(consoleError).not.toHaveBeenCalled();
    expect(consoleLog).not.toHaveBeenCalled();
    expect(consoleWarn).not.toHaveBeenCalled();
  });

  it.each([
    ["an empty", "#invite="],
    ["an invalidly encoded", "#invite=%E0%A4%A"],
    [
      "an invite mixed with a founder grant",
      `#invite=${INVITE_TOKEN}&hxy_session_grant=${SESSION_GRANT}`,
    ],
  ])("cleans %s fragment without exchanging it", async (_case, hash) => {
    window.history.replaceState({}, "", `/workspace?view=tasks${hash}`);
    const inviteExchanger = vi.fn<SessionInviteExchanger>();
    const grantExchanger = vi.fn<SessionGrantExchanger>();
    const loader = vi.fn<SessionLoader>(async () => TEST_SESSION);

    render(
      <SessionProvider
        loader={loader}
        grantExchanger={grantExchanger}
        inviteExchanger={inviteExchanger}
      >
        <SessionProbe />
      </SessionProvider>,
    );

    await waitFor(() =>
      expect(screen.getByTestId("session-status")).toHaveTextContent(
        "unauthorized",
      ),
    );
    expect(inviteExchanger).not.toHaveBeenCalled();
    expect(grantExchanger).not.toHaveBeenCalled();
    expect(loader).not.toHaveBeenCalled();
    expect(window.location.pathname).toBe("/workspace");
    expect(window.location.search).toBe("?view=tasks");
    expect(window.location.hash).toBe("");
    expect(document.body).not.toHaveTextContent(INVITE_TOKEN);
    expect(window.location.href).not.toContain(SESSION_GRANT);
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
