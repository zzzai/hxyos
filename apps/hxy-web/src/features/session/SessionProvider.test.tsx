import { StrictMode } from "react";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  MeRequestError,
  OnboardingRequestError,
  type MeResponse,
} from "../../api/client";
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
const INVITE_TOKEN = "invite-token-that-must-remain-confidentialx";
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

function watchInviteLeakSinks() {
  return {
    localStorageWrite: vi.spyOn(window.localStorage, "setItem"),
    sessionStorageWrite: vi.spyOn(window.sessionStorage, "setItem"),
    consoleError: vi.spyOn(console, "error").mockImplementation(() => {}),
    consoleLog: vi.spyOn(console, "log").mockImplementation(() => {}),
    consoleWarn: vi.spyOn(console, "warn").mockImplementation(() => {}),
  };
}

function expectInviteNotLeaked(
  token: string,
  sinks: ReturnType<typeof watchInviteLeakSinks>,
) {
  expect(window.location.href).not.toContain(token);
  expect(document.body).not.toHaveTextContent(token);
  for (const sink of Object.values(sinks)) {
    expect(sink).not.toHaveBeenCalled();
  }
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

  it("redeems a cleaned invite before replacing an injected initial session", async () => {
    const order: string[] = [];
    window.history.replaceState({}, "", `/#invite=${INVITE_TOKEN}`);
    const inviteExchanger = vi.fn<SessionInviteExchanger>(async () => {
      order.push("invite");
    });
    const loader = vi.fn<SessionLoader>(async () => {
      order.push("me");
      return INVITED_SESSION;
    });

    render(
      <SessionProvider
        initialSession={TEST_SESSION}
        loader={loader}
        inviteExchanger={inviteExchanger}
      >
        <SessionProbe />
      </SessionProvider>,
    );

    await waitFor(() =>
      expect(screen.getByTestId("session-role")).toHaveTextContent(
        "store_employee",
      ),
    );
    expect(order).toEqual(["invite", "me"]);
    expect(inviteExchanger).toHaveBeenCalledWith(INVITE_TOKEN);
    expect(window.location.hash).toBe("");
    expect(document.body).not.toHaveTextContent(INVITE_TOKEN);
  });

  it("cleans an invalid invite before rejecting an injected initial session", async () => {
    const token = "a".repeat(42);
    window.history.replaceState({}, "", `/#invite=${token}`);
    const inviteExchanger = vi.fn<SessionInviteExchanger>();
    const loader = vi.fn<SessionLoader>(async () => INVITED_SESSION);

    render(
      <SessionProvider
        initialSession={TEST_SESSION}
        loader={loader}
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
    expect(loader).not.toHaveBeenCalled();
    expect(window.location.hash).toBe("");
    expect(document.body).not.toHaveTextContent(token);
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

  it.each([401, 422])(
    "discards a terminal invite after status %i and does not exchange on retry",
    async (status) => {
      const user = userEvent.setup();
      const sinks = watchInviteLeakSinks();
      window.history.replaceState({}, "", `/#invite=${INVITE_TOKEN}`);
      const inviteExchanger = vi
        .fn<SessionInviteExchanger>()
        .mockRejectedValue(new OnboardingRequestError(status));
      const loader = vi
        .fn<SessionLoader>()
        .mockRejectedValue(new MeRequestError(401, "Unauthorized"));

      render(
        <StrictMode>
          <SessionProvider loader={loader} inviteExchanger={inviteExchanger}>
            <SessionProbe />
          </SessionProvider>
        </StrictMode>,
      );

      await waitFor(() =>
        expect(screen.getByTestId("session-status")).toHaveTextContent(
          "unauthorized",
        ),
      );
      expect(inviteExchanger).toHaveBeenCalledOnce();
      expect(loader).not.toHaveBeenCalled();
      expectInviteNotLeaked(INVITE_TOKEN, sinks);

      await user.click(screen.getByRole("button", { name: "重试身份" }));

      await waitFor(() => expect(loader).toHaveBeenCalledOnce());
      expect(screen.getByTestId("session-status")).toHaveTextContent(
        "unauthorized",
      );
      expect(inviteExchanger).toHaveBeenCalledOnce();
      expectInviteNotLeaked(INVITE_TOKEN, sinks);
    },
  );

  it.each([
    ["transport", new OnboardingRequestError(0)],
    ["server", new OnboardingRequestError(503)],
    ["unknown", new Error(`operational invite failure ${INVITE_TOKEN}`)],
  ])(
    "retains a token across a recoverable %s failure and exchanges once on retry",
    async (_case, failure) => {
      const user = userEvent.setup();
      const sinks = watchInviteLeakSinks();
      const order: string[] = [];
      let exchangeCount = 0;
      window.history.replaceState({}, "", `/#invite=${INVITE_TOKEN}`);
      const inviteExchanger = vi.fn<SessionInviteExchanger>(async () => {
        exchangeCount += 1;
        order.push(`invite-${exchangeCount}`);
        if (exchangeCount === 1) throw failure;
      });
      const loader = vi.fn<SessionLoader>(async () => {
        order.push("me");
        return INVITED_SESSION;
      });

      render(
        <StrictMode>
          <SessionProvider loader={loader} inviteExchanger={inviteExchanger}>
            <SessionProbe />
          </SessionProvider>
        </StrictMode>,
      );

      await waitFor(() =>
        expect(screen.getByTestId("session-status")).toHaveTextContent("error"),
      );
      expect(inviteExchanger).toHaveBeenCalledOnce();
      expect(loader).not.toHaveBeenCalled();
      expectInviteNotLeaked(INVITE_TOKEN, sinks);

      await user.click(screen.getByRole("button", { name: "重试身份" }));

      await waitFor(() =>
        expect(screen.getByTestId("session-status")).toHaveTextContent(
          "authenticated",
        ),
      );
      expect(inviteExchanger).toHaveBeenCalledTimes(2);
      expect(inviteExchanger).toHaveBeenNthCalledWith(1, INVITE_TOKEN);
      expect(inviteExchanger).toHaveBeenNthCalledWith(2, INVITE_TOKEN);
      expect(loader).toHaveBeenCalledOnce();
      expect(order).toEqual(["invite-1", "invite-2", "me"]);
      expect(screen.getByTestId("session-role")).toHaveTextContent(
        "store_employee",
      );
      expectInviteNotLeaked(INVITE_TOKEN, sinks);
    },
  );

  it("clears a redeemed invite before retrying a failed me load", async () => {
    const user = userEvent.setup();
    window.history.replaceState({}, "", `/#invite=${INVITE_TOKEN}`);
    const inviteExchanger = vi.fn<SessionInviteExchanger>(async () => undefined);
    const loader = vi
      .fn<SessionLoader>()
      .mockRejectedValueOnce(new Error("me unavailable"))
      .mockResolvedValueOnce(INVITED_SESSION);

    render(
      <SessionProvider loader={loader} inviteExchanger={inviteExchanger}>
        <SessionProbe />
      </SessionProvider>,
    );

    await waitFor(() =>
      expect(screen.getByTestId("session-status")).toHaveTextContent("error"),
    );
    await user.click(screen.getByRole("button", { name: "重试身份" }));

    await waitFor(() =>
      expect(screen.getByTestId("session-status")).toHaveTextContent(
        "authenticated",
      ),
    );
    expect(inviteExchanger).toHaveBeenCalledOnce();
    expect(loader).toHaveBeenCalledTimes(2);
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

  it.each([42, 257])(
    "rejects a URL-safe invite token with length %i before exchange",
    async (length) => {
      const token = "a".repeat(length);
      window.history.replaceState({}, "", `/#invite=${token}`);
      const inviteExchanger = vi.fn<SessionInviteExchanger>();
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
      expect(inviteExchanger).not.toHaveBeenCalled();
      expect(loader).not.toHaveBeenCalled();
      expect(window.location.hash).toBe("");
      expect(document.body).not.toHaveTextContent(token);
    },
  );

  it.each([43, 256])(
    "accepts and exchanges a URL-safe invite token with length %i",
    async (length) => {
      const token = "a".repeat(length);
      window.history.replaceState({}, "", `/#invite=${token}`);
      const inviteExchanger = vi.fn<SessionInviteExchanger>(async () => undefined);
      const loader = vi.fn<SessionLoader>(async () => INVITED_SESSION);

      render(
        <SessionProvider loader={loader} inviteExchanger={inviteExchanger}>
          <SessionProbe />
        </SessionProvider>,
      );

      await waitFor(() =>
        expect(screen.getByTestId("session-status")).toHaveTextContent(
          "authenticated",
        ),
      );
      expect(inviteExchanger).toHaveBeenCalledOnce();
      expect(inviteExchanger).toHaveBeenCalledWith(token);
      expect(loader).toHaveBeenCalledOnce();
      expect(window.location.hash).toBe("");
    },
  );

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
