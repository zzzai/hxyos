import {
  FormEvent,
  KeyboardEvent as ReactKeyboardEvent,
  useEffect,
  useRef,
  useState,
} from "react";
import {
  ArrowUp,
  Info,
  ListTodo,
  MessageSquare,
  PanelLeftClose,
  PanelLeftOpen,
  Paperclip,
  Store,
  UserRound,
  X,
} from "lucide-react";

type HxyRole = "founder" | "store_manager" | "store_employee";
type PrimaryView = "conversation" | "tasks" | "profile";

interface MeBootstrap {
  user: {
    role: HxyRole;
    roleLabel: string;
  };
  store: {
    id: string | null;
    displayName: string;
  };
  suggestions: readonly string[];
}

// Temporary local equivalent of the future /api/v1/me response.
export const localBootstrap: MeBootstrap = {
  user: {
    role: "store_manager",
    roleLabel: "店长",
  },
  store: {
    id: null,
    displayName: "当前门店",
  },
  suggestions: ["打开今天的待办", "顾客反馈了一个问题", "练习一次接待话术"],
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

export default function App() {
  const [activeView, setActiveView] = useState<PrimaryView>("conversation");
  const [isRailCompact, setIsRailCompact] = useState(true);
  const [isDetailsOpen, setIsDetailsOpen] = useState(false);
  const [draft, setDraft] = useState("");
  const [messages, setMessages] = useState<string[]>([]);
  const detailsTriggerRef = useRef<HTMLButtonElement>(null);
  const detailsDrawerRef = useRef<HTMLElement>(null);
  const detailsCloseRef = useRef<HTMLButtonElement>(null);
  const detailsWasOpen = useRef(false);

  useEffect(() => {
    if (isDetailsOpen) {
      detailsCloseRef.current?.focus();
    } else if (detailsWasOpen.current) {
      detailsTriggerRef.current?.focus();
    }
    detailsWasOpen.current = isDetailsOpen;
  }, [isDetailsOpen]);

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const message = draft.trim();
    if (!message) return;

    setMessages((current) => [...current, message]);
    setDraft("");
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
      <aside className="left-rail" aria-label="HXYOS 导航栏">
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
              onClick={() => setActiveView(id)}
            >
              <Icon aria-hidden="true" />
              <span>{label}</span>
            </button>
          ))}
        </nav>
      </aside>

      <main className="conversation-stage">
        <header className="stage-header">
          <div className="context-line" aria-label="当前身份和门店">
            <Store aria-hidden="true" />
            <span>{localBootstrap.user.roleLabel}</span>
            <span className="context-separator" aria-hidden="true">
              /
            </span>
            <span>{localBootstrap.store.displayName}</span>
          </div>
          <button
            ref={detailsTriggerRef}
            className="source-button"
            type="button"
            aria-label="查看当前对话详情"
            onClick={() => setIsDetailsOpen(true)}
          >
            <Info aria-hidden="true" />
            <span>查看详情</span>
          </button>
        </header>

        <section className="conversation-content" aria-live="polite">
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
              <div className="suggestions" data-testid="suggestions">
                {localBootstrap.suggestions.map((suggestion) => (
                  <button
                    type="button"
                    key={suggestion}
                    onClick={() => setDraft(suggestion)}
                  >
                    {suggestion}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="message-list" aria-label="当前对话">
              {messages.map((message, index) => (
                <p className="user-message" key={`${message}-${index}`}>
                  {message}
                </p>
              ))}
            </div>
          )}
        </section>

        <div className="composer-wrap">
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
              onChange={(event) => setDraft(event.target.value)}
            />
            <div className="composer-actions">
              <button
                className="icon-button attachment-button"
                type="button"
                aria-label="添加附件（即将开放）"
                title="附件功能即将开放"
                disabled
              >
                <Paperclip aria-hidden="true" />
              </button>
              <button
                className="icon-button send-button"
                type="submit"
                aria-label="发送"
                title="发送"
                disabled={!draft.trim()}
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
          <div className="drawer-empty">
            <Info aria-hidden="true" />
            <p>回答服务尚未接入，当前没有可显示的回答详情</p>
          </div>
        </aside>
      ) : null}
    </div>
  );
}
