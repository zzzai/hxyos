import {
  CircleUserRound,
  BookOpenCheck,
  FileClock,
  MessageSquare,
  NotebookPen,
  Plus,
  Sparkles,
} from "lucide-react";

import type { ConversationSummary } from "../../api/conversations";

export type FrontstageView = "today" | "conversation" | "learning" | "records" | "me";

interface NavigationProps {
  activeView: FrontstageView;
  conversations: ConversationSummary[];
  identityLabel: string;
  scopeLabel: string;
  canAsk: boolean;
  canCreateRecords: boolean;
  canLearn: boolean;
  canReadRecords: boolean;
  onNavigate: (view: FrontstageView) => void;
  onNewInput: () => void;
  onOpenConversation: (conversationId: string) => void;
}

const mobileItems = [
  { id: "today", label: "今日", icon: Sparkles },
  { id: "conversation", label: "对话", icon: MessageSquare },
  { id: "learning", label: "学习", icon: BookOpenCheck },
  { id: "me", label: "我的", icon: CircleUserRound },
] as const;

export function Navigation({
  activeView,
  conversations,
  identityLabel,
  scopeLabel,
  canAsk,
  canCreateRecords,
  canLearn,
  canReadRecords,
  onNavigate,
  onNewInput,
  onOpenConversation,
}: NavigationProps) {
  return (
    <>
      <aside className="desktop-rail" aria-label="HXYOS 导航">
        <div className="rail-brand" aria-label="HXYOS">
          <span className="rail-brand-mark" aria-hidden="true">H</span>
          <span>HXYOS</span>
        </div>

        {canCreateRecords ? (
          <button className="new-record-button" type="button" onClick={onNewInput}>
            <Plus aria-hidden="true" />
            新输入
          </button>
        ) : null}

        <nav className="rail-navigation" aria-label="工作区">
          {canReadRecords ? (
            <>
              <button
                type="button"
                aria-label="打开今日简报"
                aria-current={activeView === "today" ? "page" : undefined}
                onClick={() => onNavigate("today")}
              >
                <Sparkles aria-hidden="true" />
                <span>今日</span>
              </button>
              <button
                type="button"
                aria-label="组织记录"
                aria-current={activeView === "records" ? "page" : undefined}
                onClick={() => onNavigate("records")}
              >
                <FileClock aria-hidden="true" />
                <span>组织记录</span>
              </button>
            </>
          ) : null}
          {canAsk ? (
            <button
              type="button"
              aria-label="打开对话"
              aria-current={activeView === "conversation" ? "page" : undefined}
              onClick={() => onNavigate("conversation")}
            >
              <MessageSquare aria-hidden="true" />
              <span>对话</span>
            </button>
          ) : null}
          {canLearn ? (
            <button
              type="button"
              aria-label="打开学习"
              aria-current={activeView === "learning" ? "page" : undefined}
              onClick={() => onNavigate("learning")}
            >
              <BookOpenCheck aria-hidden="true" />
              <span>学习</span>
            </button>
          ) : null}
        </nav>

        {canAsk ? (
          <section className="recent-conversations" aria-labelledby="recent-heading">
            <div className="rail-section-heading">
              <h2 id="recent-heading">最近对话</h2>
              <MessageSquare aria-hidden="true" />
            </div>
            {conversations.length === 0 ? (
              <p>还没有对话</p>
            ) : (
              <ul>
                {conversations.slice(0, 6).map((conversation) => (
                  <li key={conversation.id}>
                    <button
                      type="button"
                      onClick={() => onOpenConversation(conversation.id)}
                    >
                      {conversation.title || "未命名对话"}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>
        ) : null}

        <button
          className="rail-identity"
          type="button"
          aria-label={`打开我的身份，${identityLabel}，${scopeLabel}`}
          onClick={() => onNavigate("me")}
        >
          <CircleUserRound aria-hidden="true" />
          <span>
            <strong>{identityLabel}</strong>
            <small>{scopeLabel}</small>
          </span>
        </button>
      </aside>

      <nav className="mobile-navigation" aria-label="移动端导航">
        {mobileItems
          .filter((item) => {
            if (item.id === "today") return canReadRecords;
            if (item.id === "conversation") return canAsk;
            if (item.id === "learning") return canLearn;
            return true;
          })
          .map((item) => {
          const Icon = item.icon;
          return (
            <button
              key={item.id}
              type="button"
              aria-label={item.label}
              aria-current={activeView === item.id ? "page" : undefined}
              onClick={() => onNavigate(item.id)}
            >
              <Icon aria-hidden="true" />
              <span>{item.label}</span>
            </button>
          );
          })}
      </nav>

      {canCreateRecords && (activeView === "records" || activeView === "me") ? (
        <button
          className="mobile-record-action"
          type="button"
          aria-label="快速输入"
          onClick={onNewInput}
        >
          <NotebookPen aria-hidden="true" />
        </button>
      ) : null}
    </>
  );
}
