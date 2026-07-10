import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

import { loadMe, MeRequestError, type MeResponse } from "../../api/client";

export type SessionLoader = () => Promise<MeResponse>;
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
  initialSession?: MeResponse;
}

const SessionContext = createContext<SessionContextValue | null>(null);

export function SessionProvider({
  children,
  loader = loadMe,
  initialSession,
}: SessionProviderProps) {
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<SessionState>(() =>
    initialSession
      ? { status: "authenticated", session: initialSession }
      : { status: "loading", session: null },
  );

  useEffect(() => {
    if (initialSession) return;

    let active = true;
    setState({ status: "loading", session: null });
    loader().then(
      (session) => {
        if (active) setState({ status: "authenticated", session });
      },
      (error: unknown) => {
        if (!active) return;
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
  }, [attempt, initialSession, loader]);

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
