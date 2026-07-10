import {
  ChangeEvent,
  FormEvent,
  KeyboardEvent as ReactKeyboardEvent,
  useEffect,
  useRef,
  useState,
} from "react";
import {
  ArrowUp,
  FileText,
  Info,
  ListTodo,
  MessageSquare,
  PanelLeftClose,
  PanelLeftOpen,
  Paperclip,
  RotateCcw,
  SquarePen,
  Store,
  UserRound,
  X,
} from "lucide-react";

import type { CanonicalRole, MeResponse } from "./api/client";
import {
  type ConversationClient,
  type ConversationMessage,
  productConversationClient,
} from "./api/conversations";
import {
  type MaterialClient,
  type ProductMaterial,
  productMaterialClient,
} from "./api/materials";
import {
  SessionProvider,
  type SessionLoader,
  useSession,
} from "./features/session/SessionProvider";

type PrimaryView = "conversation" | "tasks" | "profile";

const roleSuggestions: Record<CanonicalRole, readonly string[]> = {
  founder: ["询问当前开业进度", "查看今天的关键事项", "创建下一项任务"],
  hq_operations: ["查看门店待办", "跟进一个运营问题", "创建后续事项"],
  store_manager: ["打开今天的待办", "处理一个门店问题", "创建后续事项"],
  store_employee: ["询问该怎么说", "练习一次接待话术", "上报一个门店问题"],
  system_admin: ["查看系统待办", "报告一个系统问题", "创建跟进事项"],
};

const navigationItems = [
  { id: "conversation", label: "对话", icon: MessageSquare },
  { id: "tasks", label: "待办", icon: ListTodo },
  { id: "profile", label: "我的", icon: UserRound },
] as const;

const viewHeadings: Record<PrimaryView, string> = {
  conversation: "今天想先处理什么？",
  tasks: "今天的待办",
  profile: "我的",
};

interface PendingMessage {
  content: string;
  clientMessageId: string;
  localMessageId: string;
}

interface FailedMaterialUpload {
  file: File;
  clientUploadId: string;
}

interface ProductShellProps {
  conversationClient: ConversationClient;
  materialClient: MaterialClient;
  clientMessageIdFactory: () => string;
  materialUploadIdFactory: () => string;
}

function ProductShell({
  conversationClient,
  materialClient,
  clientMessageIdFactory,
  materialUploadIdFactory,
}: ProductShellProps) {
  const { retry, session, status } = useSession();
  const [activeView, setActiveView] = useState<PrimaryView>("conversation");
  const [isRailCompact, setIsRailCompact] = useState(true);
  const [isDetailsOpen, setIsDetailsOpen] = useState(false);
  const [draft, setDraft] = useState("");
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ConversationMessage[]>([]);
  const [isHistoryLoading, setIsHistoryLoading] = useState(false);
  const [isSending, setIsSending] = useState(false);
  const [sendError, setSendError] = useState(false);
  const [pendingMessage, setPendingMessage] = useState<PendingMessage | null>(
    null,
  );
  const [latestMaterial, setLatestMaterial] = useState<ProductMaterial | null>(
    null,
  );
  const [uploadingFileName, setUploadingFileName] = useState<string | null>(
    null,
  );
  const [failedMaterial, setFailedMaterial] =
    useState<FailedMaterialUpload | null>(null);
  const [isRetryingUnderstanding, setIsRetryingUnderstanding] = useState(false);
  const [understandingRetryFailed, setUnderstandingRetryFailed] =
    useState(false);
  const materialInputRef = useRef<HTMLInputElement>(null);
  const detailsTriggerRef = useRef<HTMLButtonElement>(null);
  const detailsDrawerRef = useRef<HTMLElement>(null);
  const detailsCloseRef = useRef<HTMLButtonElement>(null);
  const detailsWasOpen = useRef(false);
  const messageListEndRef = useRef<HTMLDivElement>(null);
  const historyRequestVersionRef = useRef(0);
  const materialRequestVersionRef = useRef(0);
  const assignment = session?.active_assignment;
  const isAuthenticated = status === "authenticated" && assignment !== undefined;
  const suggestions = assignment
    ? roleSuggestions[assignment.role].slice(0, 3)
    : [];
  const canCreateMaterials =
    assignment?.capabilities.includes("materials:create") ?? false;
  const canReadMaterials =
    assignment?.capabilities.includes("materials:read") ?? false;
  const roleLabel =
    assignment?.role_label ??
    (status === "loading"
      ? "正在加载身份"
      : status === "unauthorized"
        ? "登录已失效"
        : "身份加载失败");
  const scopeLabel =
    assignment?.store?.name ??
    assignment?.organization.name ??
    (status === "loading" ? "HXYOS" : "请重试");

  const latestAnswer = [...messages]
    .reverse()
    .find(
      (message) =>
        message.role === "assistant" &&
        (message.answer_status !== null || message.sources.length > 0),
    );

  useEffect(() => {
    if (!isAuthenticated || !assignment) {
      setConversationId(null);
      setMessages([]);
      setIsHistoryLoading(false);
      return;
    }

    let active = true;
    const requestVersion = historyRequestVersionRef.current + 1;
    historyRequestVersionRef.current = requestVersion;
    setIsHistoryLoading(true);
    setConversationId(null);
    setMessages([]);
    setSendError(false);
    setPendingMessage(null);
    void conversationClient
      .listConversations()
      .then(async ({ items }) => {
        if (
          !active ||
          historyRequestVersionRef.current !== requestVersion ||
          items.length === 0
        ) {
          return;
        }
        const conversation = await conversationClient.getConversation(
          items[0].id,
        );
        if (
          !active ||
          historyRequestVersionRef.current !== requestVersion
        ) {
          return;
        }
        setConversationId(conversation.conversation.id);
        setMessages(conversation.messages);
      })
      .catch(() => undefined)
      .finally(() => {
        if (
          active &&
          historyRequestVersionRef.current === requestVersion
        ) {
          setIsHistoryLoading(false);
        }
      });

    return () => {
      active = false;
    };
  }, [assignment?.assignment_id, conversationClient, isAuthenticated]);

  useEffect(() => {
    const requestVersion = materialRequestVersionRef.current + 1;
    materialRequestVersionRef.current = requestVersion;
    setLatestMaterial(null);
    setUploadingFileName(null);
    setFailedMaterial(null);
    setUnderstandingRetryFailed(false);

    if (!isAuthenticated || !canReadMaterials) return;

    let active = true;
    void materialClient
      .listMaterials()
      .then(({ items }) => {
        if (
          active &&
          materialRequestVersionRef.current === requestVersion &&
          items.length > 0
        ) {
          setLatestMaterial(items[0]);
        }
      })
      .catch(() => undefined);

    return () => {
      active = false;
    };
  }, [
    assignment?.assignment_id,
    canReadMaterials,
    isAuthenticated,
    materialClient,
  ]);

  useEffect(() => {
    if (
      !isAuthenticated ||
      !canReadMaterials ||
      latestMaterial?.status !== "processing"
    ) {
      return;
    }
    let active = true;
    const interval = window.setInterval(() => {
      void materialClient
        .getMaterial(latestMaterial.id)
        .then(({ material }) => {
          if (active) setLatestMaterial(material);
        })
        .catch(() => undefined);
    }, 2500);
    return () => {
      active = false;
      window.clearInterval(interval);
    };
  }, [
    canReadMaterials,
    isAuthenticated,
    latestMaterial?.id,
    latestMaterial?.status,
    materialClient,
  ]);

  useEffect(() => {
    if (isDetailsOpen) {
      detailsCloseRef.current?.focus();
    } else if (detailsWasOpen.current) {
      detailsTriggerRef.current?.focus();
    }
    detailsWasOpen.current = isDetailsOpen;
  }, [isDetailsOpen]);

  useEffect(() => {
    const scrollIntoView = messageListEndRef.current?.scrollIntoView;
    if (typeof scrollIntoView === "function") {
      scrollIntoView.call(messageListEndRef.current, { block: "nearest" });
    }
  }, [failedMaterial, isSending, latestMaterial, messages, uploadingFileName]);

  const uploadMaterial = async (file: File, clientUploadId: string) => {
    if (!isAuthenticated || !canCreateMaterials || uploadingFileName) return;
    materialRequestVersionRef.current += 1;
    setActiveView("conversation");
    setUploadingFileName(file.name);
    setFailedMaterial(null);
    try {
      const { material } = await materialClient.uploadMaterial(
        file,
        "",
        clientUploadId,
      );
      setLatestMaterial(material);
    } catch {
      setFailedMaterial({ file, clientUploadId });
    } finally {
      setUploadingFileName(null);
    }
  };

  const handleMaterialSelection = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.currentTarget.files?.[0];
    event.currentTarget.value = "";
    if (file) void uploadMaterial(file, materialUploadIdFactory());
  };

  const retryMaterialUnderstanding = async (material: ProductMaterial) => {
    if (!isAuthenticated || !canCreateMaterials || isRetryingUnderstanding) {
      return;
    }
    setIsRetryingUnderstanding(true);
    setUnderstandingRetryFailed(false);
    try {
      const result = await materialClient.retryUnderstanding(material.id);
      setLatestMaterial(result.material);
    } catch {
      setUnderstandingRetryFailed(true);
    } finally {
      setIsRetryingUnderstanding(false);
    }
  };

  const sendPendingMessage = async (pending: PendingMessage) => {
    historyRequestVersionRef.current += 1;
    setIsHistoryLoading(false);
    setIsSending(true);
    setSendError(false);
    try {
      let targetConversationId = conversationId;
      if (!targetConversationId) {
        const { conversation } = await conversationClient.createConversation();
        targetConversationId = conversation.id;
        setConversationId(targetConversationId);
      }
      const result = await conversationClient.sendMessage(
        targetConversationId,
        {
          content: pending.content,
          client_message_id: pending.clientMessageId,
        },
      );
      setMessages((current) => [
        ...current.filter(
          (message) => message.id !== pending.localMessageId,
        ),
        result.user_message,
        result.assistant_message,
      ]);
      setPendingMessage(null);
    } catch {
      setSendError(true);
    } finally {
      setIsSending(false);
    }
  };

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!isAuthenticated || isSending) return;
    const message = draft.trim();
    if (!message) return;

    const clientMessageId = clientMessageIdFactory();
    const pending = {
      content: message,
      clientMessageId,
      localMessageId: `local:${clientMessageId}`,
    };
    setMessages((current) => [
      ...current,
      {
        id: pending.localMessageId,
        conversation_id: conversationId ?? "local",
        role: "user",
        content: message,
        created_at: new Date().toISOString(),
        answer_id: null,
        answer_status: null,
        confidence: null,
        needs_review: null,
        sources: [],
        next_actions: [],
      },
    ]);
    setPendingMessage(pending);
    setDraft("");
    void sendPendingMessage(pending);
  };

  const startNewConversation = () => {
    historyRequestVersionRef.current += 1;
    setConversationId(null);
    setMessages([]);
    setPendingMessage(null);
    setSendError(false);
    setIsDetailsOpen(false);
  };

  const handleDetailsKeyDown = (event: ReactKeyboardEvent<HTMLElement>) => {
    if (event.key === "Escape") {
      event.preventDefault();
      setIsDetailsOpen(false);
      return;
    }

    if (event.key !== "Tab") return;
    const focusable = Array.from(
      detailsDrawerRef.current?.querySelectorAll<HTMLElement>(
        'button:not([disabled]), [href], input:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
      ) ?? [],
    );
    if (!focusable.length) {
      event.preventDefault();
      detailsDrawerRef.current?.focus();
      return;
    }

    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (
      (event.shiftKey && document.activeElement === first) ||
      (!event.shiftKey && document.activeElement === last)
    ) {
      event.preventDefault();
      (event.shiftKey ? last : first).focus();
    }
  };

  return (
    <div
      className={`app-shell${isRailCompact ? " rail-compact" : ""}${
        isDetailsOpen ? " has-details" : ""
      }`}
    >
      <aside
        className="left-rail"
        aria-label="HXYOS 导航栏"
        inert={isDetailsOpen}
      >
        <div className="rail-header">
          <span className="brand-mark" aria-hidden="true">
            H
          </span>
          <span className="brand-name">HXYOS</span>
          <button
            className="icon-button rail-toggle"
            type="button"
            aria-label={isRailCompact ? "展开导航栏" : "收起导航栏"}
            title={isRailCompact ? "展开导航栏" : "收起导航栏"}
            onClick={() => setIsRailCompact((current) => !current)}
          >
            {isRailCompact ? <PanelLeftOpen /> : <PanelLeftClose />}
          </button>
        </div>

        <nav className="primary-navigation" aria-label="主要导航">
          {navigationItems.map(({ id, label, icon: Icon }) => (
            <button
              className="navigation-item"
              type="button"
              key={id}
              aria-current={activeView === id ? "page" : undefined}
              title={label}
              disabled={!isAuthenticated}
              onClick={() => setActiveView(id)}
            >
              <Icon aria-hidden="true" />
              <span>{label}</span>
            </button>
          ))}
        </nav>
      </aside>

      <main className="conversation-stage" inert={isDetailsOpen}>
        <header className="stage-header">
          <div
            className="context-line"
            aria-label="当前身份和门店"
            role={
              status === "loading"
                ? "status"
                : status === "unauthorized" || status === "error"
                  ? "alert"
                  : undefined
            }
          >
            <Store aria-hidden="true" />
            <span>{roleLabel}</span>
            <span className="context-separator" aria-hidden="true">
              /
            </span>
            <span>{scopeLabel}</span>
            {status === "unauthorized" || status === "error" ? (
              <button
                className="icon-button"
                type="button"
                aria-label="重试身份加载"
                title="重试身份加载"
                onClick={retry}
              >
                <RotateCcw aria-hidden="true" />
              </button>
            ) : null}
          </div>
          <div className="stage-actions">
            {messages.length > 0 ? (
              <button
                className="icon-button stage-icon-button"
                type="button"
                aria-label="新建对话"
                title="新建对话"
                disabled={!isAuthenticated || isSending}
                onClick={startNewConversation}
              >
                <SquarePen aria-hidden="true" />
              </button>
            ) : null}
            <button
              ref={detailsTriggerRef}
              className="source-button"
              type="button"
              aria-label="查看当前对话详情"
              disabled={!isAuthenticated}
              onClick={() => setIsDetailsOpen(true)}
            >
              <Info aria-hidden="true" />
              <span>查看详情</span>
            </button>
          </div>
        </header>

        <section
          className="conversation-content"
          aria-live="polite"
          aria-busy={isHistoryLoading || isSending}
        >
          {activeView !== "conversation" ? (
            <div className="empty-state">
              <div className="empty-symbol" aria-hidden="true">
                <MessageSquare />
              </div>
              <h1>{viewHeadings[activeView]}</h1>
              <p className="empty-note">
                {activeView === "tasks" ? "暂时没有待办" : "个人信息尚未接入"}
              </p>
            </div>
          ) : messages.length === 0 ? (
            <div className="empty-state">
              <div className="empty-symbol" aria-hidden="true">
                <MessageSquare />
              </div>
              <h1>{viewHeadings.conversation}</h1>
              {isAuthenticated ? (
                <div className="suggestions" data-testid="suggestions">
                  {suggestions.map((suggestion) => (
                    <button
                      type="button"
                      key={suggestion}
                      onClick={() => setDraft(suggestion)}
                    >
                      {suggestion}
                    </button>
                  ))}
                </div>
              ) : null}
            </div>
          ) : (
            <div className="message-list" aria-label="当前对话">
              {messages.map((message) =>
                message.role === "user" ? (
                  <p className="user-message" key={message.id}>
                    {message.content}
                  </p>
                ) : (
                  <article
                    className="assistant-message"
                    key={message.id}
                  >
                    <p>{message.content}</p>
                  </article>
                ),
              )}
              {isSending ? (
                <div className="assistant-pending" role="status">
                  <span aria-hidden="true" />
                  <span aria-hidden="true" />
                  <span aria-hidden="true" />
                  <span className="visually-hidden">正在生成回答</span>
                </div>
              ) : null}
              {sendError && pendingMessage ? (
                <div className="message-error" role="alert">
                  <span>回答没有完成</span>
                  <button
                    type="button"
                    onClick={() => void sendPendingMessage(pendingMessage)}
                  >
                    重试
                  </button>
                </div>
              ) : null}
              <div ref={messageListEndRef} />
            </div>
          )}
        </section>

        <div
          className="composer-wrap"
          data-testid="composer-region"
          aria-live="polite"
        >
          {latestMaterial ? (
            <article className="material-receipt">
              <div className="material-receipt-heading">
                <FileText aria-hidden="true" />
                <strong>{latestMaterial.file_name}</strong>
                <span>
                  {latestMaterial.status === "processing"
                    ? "正在理解"
                    : latestMaterial.status === "ready"
                      ? "可以使用"
                      : "需要关注"}
                </span>
              </div>
              <p>{latestMaterial.understanding.summary}</p>
              <a
                href={latestMaterial.original.url}
                target="_blank"
                rel="noreferrer"
              >
                查看原文
              </a>
              {latestMaterial.status === "needs_attention" ? (
                <button
                  className="material-retry-button"
                  type="button"
                  aria-label="重新理解资料"
                  disabled={isRetryingUnderstanding}
                  onClick={() => void retryMaterialUnderstanding(latestMaterial)}
                >
                  {isRetryingUnderstanding ? "正在理解" : "重新理解"}
                </button>
              ) : null}
              {understandingRetryFailed ? (
                <span className="material-retry-error" role="alert">
                  理解没有完成，可稍后重试
                </span>
              ) : null}
            </article>
          ) : null}
          {uploadingFileName ? (
            <div className="material-progress" role="status">
              <span aria-hidden="true" />
              <span>正在接收{uploadingFileName}</span>
            </div>
          ) : null}
          {failedMaterial ? (
            <div className="material-error" role="alert">
              <span>{failedMaterial.file.name} 没有上传完成</span>
              <button
                type="button"
                aria-label="重新上传"
                onClick={() =>
                  void uploadMaterial(
                    failedMaterial.file,
                    failedMaterial.clientUploadId,
                  )
                }
              >
                重试
              </button>
            </div>
          ) : null}
          <form
            className="composer"
            data-testid="composer"
            aria-label="HXYOS 对话输入"
            onSubmit={handleSubmit}
          >
            <textarea
              value={draft}
              rows={2}
              aria-label="告诉 HXYOS 你要做什么"
              placeholder="告诉 HXYOS 你要做什么"
              disabled={!isAuthenticated || isSending}
              onChange={(event) => setDraft(event.target.value)}
            />
            <div className="composer-actions">
              <input
                ref={materialInputRef}
                className="visually-hidden"
                type="file"
                tabIndex={-1}
                accept=".csv,.doc,.docx,.jpeg,.jpg,.json,.md,.pdf,.png,.ppt,.pptx,.txt,.webp,.xls,.xlsx"
                disabled={
                  !isAuthenticated || !canCreateMaterials || !!uploadingFileName
                }
                onChange={handleMaterialSelection}
              />
              <button
                className="icon-button attachment-button"
                type="button"
                aria-label="添加资料"
                title="添加资料"
                disabled={
                  !isAuthenticated || !canCreateMaterials || !!uploadingFileName
                }
                onClick={() => materialInputRef.current?.click()}
              >
                <Paperclip aria-hidden="true" />
              </button>
              <button
                className="icon-button send-button"
                type="submit"
                aria-label="发送"
                title="发送"
                disabled={!isAuthenticated || isSending || !draft.trim()}
              >
                <ArrowUp aria-hidden="true" />
              </button>
            </div>
          </form>
        </div>
      </main>

      {isDetailsOpen ? (
        <aside
          ref={detailsDrawerRef}
          className="details-drawer"
          role="dialog"
          aria-label="当前对话详情"
          aria-modal="true"
          tabIndex={-1}
          onKeyDown={handleDetailsKeyDown}
        >
          <header>
            <div>
              <span className="drawer-eyebrow">当前对话</span>
              <h2>对话详情</h2>
            </div>
            <button
              ref={detailsCloseRef}
              className="icon-button"
              type="button"
              aria-label="关闭当前对话详情"
              title="关闭当前对话详情"
              onClick={() => setIsDetailsOpen(false)}
            >
              <X aria-hidden="true" />
            </button>
          </header>
          {latestAnswer ? (
            <div className="answer-details">
              <dl>
                <div>
                  <dt>状态</dt>
                  <dd>{latestAnswer.answer_status || "待确认"}</dd>
                </div>
                <div>
                  <dt>可靠程度</dt>
                  <dd>
                    {latestAnswer.confidence === "high"
                      ? "较高"
                      : latestAnswer.confidence === "medium"
                        ? "一般"
                        : "需核对"}
                  </dd>
                </div>
              </dl>
              {latestAnswer.sources.length > 0 ? (
                <section aria-label="回答来源">
                  <h3>来源</h3>
                  <ul className="source-list">
                    {latestAnswer.sources.map((source, index) => (
                      <li key={`${source.title}-${index}`}>
                        <strong>{source.title}</strong>
                        {source.excerpt ? <p>{source.excerpt}</p> : null}
                      </li>
                    ))}
                  </ul>
                </section>
              ) : null}
            </div>
          ) : (
            <div className="drawer-empty">
              <Info aria-hidden="true" />
              <p>发送问题后，这里会显示回答状态和来源</p>
            </div>
          )}
        </aside>
      ) : null}
    </div>
  );
}

interface AppProps {
  initialSession?: MeResponse;
  sessionLoader?: SessionLoader;
  conversationClient?: ConversationClient;
  materialClient?: MaterialClient;
  clientMessageIdFactory?: () => string;
  materialUploadIdFactory?: () => string;
}

export default function App({
  initialSession,
  sessionLoader,
  conversationClient = productConversationClient,
  materialClient = productMaterialClient,
  clientMessageIdFactory = () => crypto.randomUUID(),
  materialUploadIdFactory = () => crypto.randomUUID(),
}: AppProps) {
  return (
    <SessionProvider loader={sessionLoader} initialSession={initialSession}>
      <ProductShell
        conversationClient={conversationClient}
        materialClient={materialClient}
        clientMessageIdFactory={clientMessageIdFactory}
        materialUploadIdFactory={materialUploadIdFactory}
      />
    </SessionProvider>
  );
}
