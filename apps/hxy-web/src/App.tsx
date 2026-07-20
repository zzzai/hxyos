import { type FormEvent, useState } from "react";

import {
  logoutSession,
  MeRequestError,
  productOnboardingClient,
  type MeResponse,
  type OnboardingClient,
} from "./api/client";
import {
  productConversationClient,
  type ConversationClient,
} from "./api/conversations";
import { productMaterialClient, type MaterialClient } from "./api/materials";
import { productLearningClient, type LearningClient } from "./api/learning";
import { productServiceClient, type ServiceClient } from "./api/services";
import {
  productRecordClient,
  type OrganizationRecordClient,
} from "./api/records";
import { productTodayClient, type TodayClient } from "./api/today";
import {
  SessionProvider,
  type SessionGrantExchanger,
  type SessionLoader,
  useSession,
} from "./features/session/SessionProvider";
import { ProductShell } from "./features/shell/ProductShell";

function normalizeAccessCode(value: string): string | null {
  const trimmed = value.trim();
  let candidate = trimmed;

  if (trimmed.includes("#")) {
    try {
      const url = new URL(trimmed);
      const params = new URLSearchParams(url.hash.slice(1));
      candidate = params.get("hxy_session_grant") ?? "";
    } catch {
      return null;
    }
  }

  return candidate.length >= 43 &&
    candidate.length <= 256 &&
    /^[A-Za-z0-9._~-]+$/.test(candidate)
    ? candidate
    : null;
}

interface AccessGateProps {
  status: "loading" | "unauthorized" | "error";
  authenticate: (grant: string) => Promise<void>;
  retry: () => void;
}

function AccessGate({ status, authenticate, retry }: AccessGateProps) {
  const [accessCode, setAccessCode] = useState("");
  const [accessError, setAccessError] = useState("");
  const normalizedAccessCode = normalizeAccessCode(accessCode);

  const submitAccessCode = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!normalizedAccessCode || status === "loading") return;

    setAccessError("");
    try {
      await authenticate(normalizedAccessCode);
    } catch (error: unknown) {
      setAccessCode("");
      setAccessError(
        error instanceof MeRequestError &&
          (error.status === 401 || error.status === 403 || error.status === 422)
          ? "访问码无效或已过期，请重新获取"
          : "暂时无法连接，请稍后重试",
      );
    }
  };

  return (
    <main className="access-gate">
      <div className="access-gate-content">
        <div className="access-brand" aria-label="HXYOS">
          <span className="rail-brand-mark" aria-hidden="true">H</span>
          <span>HXYOS</span>
        </div>

        {status === "loading" ? (
          <p className="access-loading" role="status">正在连接 HXYOS</p>
        ) : status === "error" ? (
          <div className="access-state">
            <h1>暂时无法连接 HXYOS</h1>
            <p>请检查网络后重新连接。</p>
            <button className="access-primary-button" type="button" onClick={retry}>
              重新连接
            </button>
          </div>
        ) : (
          <div className="access-state">
            <h1>进入 HXYOS</h1>
            <p>打开管理员发送的一次性访问链接，或输入访问码。</p>
            <form className="access-form" onSubmit={submitAccessCode}>
              <label htmlFor="hxy-access-code">一次性访问码</label>
              <input
                id="hxy-access-code"
                type="password"
                autoComplete="one-time-code"
                spellCheck={false}
                value={accessCode}
                onChange={(event) => {
                  setAccessCode(event.target.value);
                  setAccessError("");
                }}
              />
              {accessError ? <p className="access-error" role="alert">{accessError}</p> : null}
              <button
                className="access-primary-button"
                type="submit"
                disabled={!normalizedAccessCode}
              >
                进入
              </button>
            </form>
          </div>
        )}
      </div>
    </main>
  );
}

interface ApplicationSurfaceProps {
  todayClient: TodayClient;
  recordClient: OrganizationRecordClient;
  conversationClient: ConversationClient;
  materialClient: MaterialClient;
  learningClient: LearningClient;
  serviceClient: ServiceClient;
  onboardingClient: OnboardingClient;
  clientIdFactory: () => string;
  uploadIdFactory: () => string;
  logout: () => Promise<void>;
  onLoggedOut: () => void;
}

function ApplicationSurface(props: ApplicationSurfaceProps) {
  const { authenticate, retry, status } = useSession();
  if (status !== "authenticated") {
    return <AccessGate status={status} authenticate={authenticate} retry={retry} />;
  }
  return <ProductShell {...props} />;
}

interface AppProps {
  initialSession?: MeResponse;
  sessionLoader?: SessionLoader;
  grantExchanger?: SessionGrantExchanger;
  todayClient?: TodayClient;
  recordClient?: OrganizationRecordClient;
  conversationClient?: ConversationClient;
  materialClient?: MaterialClient;
  learningClient?: LearningClient;
  serviceClient?: ServiceClient;
  onboardingClient?: OnboardingClient;
  clientMessageIdFactory?: () => string;
  materialUploadIdFactory?: () => string;
  logout?: () => Promise<void>;
  onLoggedOut?: () => void;
}

function reloadAfterLogout() {
  window.location.reload();
}

export default function App({
  initialSession,
  sessionLoader,
  grantExchanger,
  todayClient = productTodayClient,
  recordClient = productRecordClient,
  conversationClient = productConversationClient,
  materialClient = productMaterialClient,
  learningClient = productLearningClient,
  serviceClient = productServiceClient,
  onboardingClient = productOnboardingClient,
  clientMessageIdFactory = () => crypto.randomUUID(),
  materialUploadIdFactory = () => crypto.randomUUID(),
  logout = logoutSession,
  onLoggedOut = reloadAfterLogout,
}: AppProps) {
  return (
    <SessionProvider
      loader={sessionLoader}
      grantExchanger={grantExchanger}
      initialSession={initialSession}
    >
      <ApplicationSurface
        todayClient={todayClient}
        recordClient={recordClient}
        conversationClient={conversationClient}
        materialClient={materialClient}
        learningClient={learningClient}
        serviceClient={serviceClient}
        onboardingClient={onboardingClient}
        clientIdFactory={clientMessageIdFactory}
        uploadIdFactory={materialUploadIdFactory}
        logout={logout}
        onLoggedOut={onLoggedOut}
      />
    </SessionProvider>
  );
}
