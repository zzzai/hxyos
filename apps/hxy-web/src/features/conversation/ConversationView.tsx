import { MessageSquareText, Plus, RefreshCw } from "lucide-react";

import type { ConversationMessage } from "../../api/conversations";
import type { OrganizationRecord } from "../../api/records";

interface ConversationViewProps {
  messages: ConversationMessage[];
  status: "idle" | "loading" | "sending" | "error";
  contextRecord: OrganizationRecord | null;
  onNewConversation: () => void;
  onRetry: () => void;
}

export function ConversationView({
  messages,
  status,
  contextRecord,
  onNewConversation,
  onRetry,
}: ConversationViewProps) {
  return (
    <section className="frontstage-view conversation-view" aria-labelledby="conversation-title">
      <header className="view-header conversation-header">
        <div>
          <h1 id="conversation-title">对话</h1>
          {contextRecord ? (
            <p className="conversation-context">
              正在基于：{contextRecord.preview || "这条组织记录"}
            </p>
          ) : (
            <p>结合你有权限访问的荷小悦资料回答</p>
          )}
        </div>
        <button
          className="header-icon-button"
          type="button"
          aria-label="开始新对话"
          title="开始新对话"
          onClick={onNewConversation}
        >
          <Plus aria-hidden="true" />
        </button>
      </header>

      {status === "loading" ? (
        <div className="quiet-state" role="status">正在打开对话</div>
      ) : status === "error" && messages.length === 0 ? (
        <div className="quiet-state" role="alert">
          <p>对话暂时没有加载出来</p>
          <button type="button" onClick={onRetry}>
            <RefreshCw aria-hidden="true" />
            重试
          </button>
        </div>
      ) : messages.length === 0 ? (
        <div className="conversation-empty">
          <MessageSquareText aria-hidden="true" />
          <p>直接问一个正在发生的问题</p>
        </div>
      ) : (
        <ol className="message-thread" aria-label="当前对话">
          {messages.map((message) => (
            <li key={message.id} className={`message is-${message.role}`}>
              <div>{message.content}</div>
              {message.role === "assistant" && message.answer_status ? (
                <small>{message.answer_status}</small>
              ) : null}
            </li>
          ))}
          {status === "sending" ? (
            <li className="message is-assistant is-pending" role="status">
              正在结合资料回答
            </li>
          ) : null}
        </ol>
      )}
    </section>
  );
}
