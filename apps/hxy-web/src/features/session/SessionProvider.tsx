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
  type MeResponse,
} from "../../api/client";

export type SessionLoader = () => Promise<MeResponse>;
export type SessionGrantExchanger = (grant: string) => Promise<void>;
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
  initialSession?: MeResponse;
}

const SessionContext = createContext<SessionContextValue | null>(null);

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
  initialSession,
}: SessionProviderProps) {
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<SessionState>(() =>
    initialSession
      ? { status: "authenticated", session: initialSession }
      : { status: "loading", session: null },
  );
  const bootstrapPromise = useRef<Promise<void> | null | undefined>(undefined);

  useEffect(() => {
    if (initialSession) return;

    let active = true;
    setState({ status: "loading", session: null });
    if (bootstrapPromise.current === undefined) {
      const grant = takeSessionGrantFromFragment();
      bootstrapPromise.current = grant ? grantExchanger(grant) : null;
    }
    const sessionRequest = bootstrapPromise.current
      ? bootstrapPromise.current.then(() => {
          bootstrapPromise.current = null;
          return active ? loader() : null;
        })
      : loader();
    sessionRequest.then(
      (session) => {
        if (active && session) setState({ status: "authenticated", session });
      },
      (error: unknown) => {
        if (!active) return;
        bootstrapPromise.current = null;
        setState({
          status:
            error instanceof MeRequestError && error.status === 401
              ? "unauthorized"
              : "error",
          session: null,
        });
      },
    );

    return () => {
      active = false;
    };
  }, [attempt, grantExchanger, initialSession, loader]);

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
