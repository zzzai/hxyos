import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import {
  exchangeSessionGrant,
  loadMe,
  MeRequestError,
  OnboardingRequestError,
  productOnboardingClient,
  type MeResponse,
} from "../../api/client";

export type SessionLoader = () => Promise<MeResponse>;
export type SessionGrantExchanger = (grant: string) => Promise<void>;
export type SessionInviteExchanger = (token: string) => Promise<void>;
export type SessionStatus =
  | "loading"
  | "authenticated"
  | "unauthorized"
  | "error";

interface SessionState {
  status: SessionStatus;
  session: MeResponse | null;
}

interface SessionContextValue extends SessionState {
  retry: () => void;
}

interface SessionProviderProps {
  children: ReactNode;
  loader?: SessionLoader;
  grantExchanger?: SessionGrantExchanger;
  inviteExchanger?: SessionInviteExchanger;
  initialSession?: MeResponse;
}

const SessionContext = createContext<SessionContextValue | null>(null);
const INVALID_INVITE_FRAGMENT = Symbol("invalid-invite-fragment");
const TERMINAL_INVITE_REDEMPTION = Symbol("terminal-invite-redemption");
const RECOVERABLE_INVITE_REDEMPTION = Symbol("recoverable-invite-redemption");

type InviteFragment =
  | { kind: "absent" }
  | { kind: "invalid" }
  | { kind: "valid"; token: string };

interface BootstrapAttempt {
  attempt: number;
  request: Promise<MeResponse>;
}

function redeemSessionInvite(token: string): Promise<void> {
  return productOnboardingClient.redeemInvite(token).then(() => undefined);
}

function takeInviteFromFragment(): InviteFragment {
  if (typeof window === "undefined") {
    return { kind: "absent" };
  }

  const hash = window.location.hash;
  if (!hash) return { kind: "absent" };

  const rawFragment = hash.slice(1);
  if (!new URLSearchParams(rawFragment).has("invite")) {
    return { kind: "absent" };
  }

  window.history.replaceState(
    window.history.state,
    "",
    `${window.location.pathname}${window.location.search}`,
  );

  if (!/^invite=[^&]*$/.test(rawFragment)) {
    return { kind: "invalid" };
  }

  try {
    const token = decodeURIComponent(rawFragment.slice("invite=".length));
    return token.length >= 43 &&
      token.length <= 256 &&
      /^[A-Za-z0-9._~-]+$/.test(token)
      ? { kind: "valid", token }
      : { kind: "invalid" };
  } catch {
    return { kind: "invalid" };
  }
}

function takeSessionGrantFromFragment(): string | null {
  if (typeof window === "undefined" || !window.location.hash) return null;
  const rawFragment = window.location.hash.slice(1);
  const params = new URLSearchParams(rawFragment);
  const values = params.getAll("hxy_session_grant");
  if (values.length === 0) return null;

  window.history.replaceState(
    window.history.state,
    "",
    `${window.location.pathname}${window.location.search}`,
  );
  const keys = [...params.keys()];
  if (
    values.length !== 1 ||
    keys.length !== 1 ||
    keys[0] !== "hxy_session_grant" ||
    values[0].length < 43 ||
    values[0].length > 256
  ) {
    return null;
  }
  return values[0];
}

export function SessionProvider({
  children,
  loader = loadMe,
  grantExchanger = exchangeSessionGrant,
  inviteExchanger = redeemSessionInvite,
  initialSession,
}: SessionProviderProps) {
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<SessionState>(() =>
    initialSession
      ? { status: "authenticated", session: initialSession }
      : { status: "loading", session: null },
  );
  const inviteFragmentRead = useRef(false);
  const inviteFragmentPresent = useRef(false);
  const invalidInvitePending = useRef(false);
  const inviteToken = useRef<string | null>(null);
  const bootstrapAttempt = useRef<BootstrapAttempt | null>(null);

  useEffect(() => {
    if (!inviteFragmentRead.current) {
      inviteFragmentRead.current = true;
      const invite = takeInviteFromFragment();
      if (invite.kind === "valid") {
        inviteFragmentPresent.current = true;
        inviteToken.current = invite.token;
      } else if (invite.kind === "invalid") {
        inviteFragmentPresent.current = true;
        invalidInvitePending.current = true;
      }
    }

    if (initialSession && !inviteFragmentPresent.current) return;

    let active = true;
    setState({ status: "loading", session: null });
    if (bootstrapAttempt.current?.attempt !== attempt) {
      let bootstrap: Promise<void> | null;
      if (inviteToken.current !== null) {
        bootstrap = Promise.resolve()
          .then(() => {
            const token = inviteToken.current;
            if (token === null) throw RECOVERABLE_INVITE_REDEMPTION;
            return inviteExchanger(token);
          })
          .then(
            () => {
              inviteToken.current = null;
            },
            (error: unknown) => {
              if (
                error instanceof OnboardingRequestError &&
                (error.status === 401 || error.status === 422)
              ) {
                inviteToken.current = null;
                throw TERMINAL_INVITE_REDEMPTION;
              }
              throw RECOVERABLE_INVITE_REDEMPTION;
            },
          );
      } else if (invalidInvitePending.current) {
        invalidInvitePending.current = false;
        bootstrap = Promise.reject(INVALID_INVITE_FRAGMENT);
      } else {
        const grant = takeSessionGrantFromFragment();
        bootstrap = grant ? grantExchanger(grant) : null;
      }
      bootstrapAttempt.current = {
        attempt,
        request: bootstrap ? bootstrap.then(() => loader()) : loader(),
      };
    }
    bootstrapAttempt.current.request.then(
      (session) => {
        if (active) setState({ status: "authenticated", session });
      },
      (error: unknown) => {
        if (!active) return;
        setState({
          status:
            error === INVALID_INVITE_FRAGMENT ||
            error === TERMINAL_INVITE_REDEMPTION ||
            (error instanceof MeRequestError && error.status === 401)
              ? "unauthorized"
              : "error",
          session: null,
        });
      },
    );

    return () => {
      active = false;
    };
  }, [attempt, grantExchanger, initialSession, inviteExchanger, loader]);

  const retry = useCallback(() => {
    setState({ status: "loading", session: null });
    setAttempt((current) => current + 1);
  }, []);

  const value = useMemo(
    () => ({ ...state, retry }),
    [retry, state],
  );

  return (
    <SessionContext.Provider value={value}>
      {children}
    </SessionContext.Provider>
  );
}

export function useSession(): SessionContextValue {
  const context = useContext(SessionContext);
  if (!context) {
    throw new Error("useSession must be used within SessionProvider");
  }
  return context;
}
