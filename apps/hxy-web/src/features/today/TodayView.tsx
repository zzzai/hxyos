import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  ClipboardCheck,
  RefreshCw,
  ThumbsDown,
  ThumbsUp,
} from "lucide-react";
import { type ReactNode, useState } from "react";

import { productEventClient } from "../../api/productEvents";
import type { TodayBriefItem, TodayRoleAction } from "../../api/today";

interface TodayViewProps {
  items: TodayBriefItem[];
  status: "loading" | "ready" | "error";
  leadingAction?: ReactNode;
  leadingActionActive?: boolean;
  roleAction?: TodayRoleAction | null;
  onOpenRecord: (recordId: string) => void;
  onRoleAction?: (action: TodayRoleAction) => void;
  onRetry: () => void;
}

interface BriefFeedbackState {
  clientEventId: string;
  useful: boolean;
  status: "pending" | "saved" | "error";
}

function kindLabel(item: TodayBriefItem): string {
  if (item.kind === "risk") return item.severity === "critical" ? "紧急风险" : "风险";
  if (item.kind === "decision") return "决定";
  return "进展";
}

export function TodayView({
  items,
  status,
  leadingAction,
  leadingActionActive = false,
  roleAction = null,
  onOpenRecord,
  onRoleAction,
  onRetry,
}: TodayViewProps) {
  const [briefFeedback, setBriefFeedback] = useState<Record<string, BriefFeedbackState>>({});
  const occupiedSlots = leadingActionActive || roleAction ? 1 : 0;
  const visibleItems = items.slice(0, Math.max(0, 3 - occupiedSlots));

  const recordBriefFeedback = async (item: TodayBriefItem, useful: boolean) => {
    const existing = briefFeedback[item.id];
    const clientEventId = existing?.clientEventId ?? crypto.randomUUID();
    setBriefFeedback((current) => ({
      ...current,
      [item.id]: { clientEventId, useful, status: "pending" },
    }));
    const saved = await productEventClient.track({
      clientEventId,
      eventName: "briefing_feedback",
      subjectId: item.source_record_id,
      useful,
    });
    setBriefFeedback((current) => ({
      ...current,
      [item.id]: { clientEventId, useful, status: saved ? "saved" : "error" },
    }));
  };

  return (
    <section className="frontstage-view today-view" aria-labelledby="today-title">
      <header className="view-header">
        <div>
          <h1 id="today-title">今日</h1>
          <p>只看与你当前身份有关的关键变化</p>
        </div>
      </header>

      {leadingAction}

      {roleAction ? (
        <button
          className="today-role-action"
          type="button"
          aria-label={roleAction.label}
          onClick={() => onRoleAction?.(roleAction)}
        >
          <ClipboardCheck aria-hidden="true" />
          <span>
            <strong>{roleAction.label}</strong>
            <small>用一句话留下今天最重要的经营情况</small>
          </span>
          <ArrowRight aria-hidden="true" />
        </button>
      ) : null}

      {status === "loading" ? (
        <div className="quiet-state" role="status">正在整理今日重点</div>
      ) : status === "error" ? (
        <div className="quiet-state" role="alert">
          <p>今日重点暂时没有加载出来</p>
          <button type="button" onClick={onRetry}>
            <RefreshCw aria-hidden="true" />
            重试
          </button>
        </div>
      ) : visibleItems.length === 0 && !leadingActionActive && !roleAction ? (
        <div className="quiet-state">
          <CheckCircle2 aria-hidden="true" />
          <p>现在没有需要特别关注的变化</p>
        </div>
      ) : (
        <ul className="briefing-list" aria-label="今日重点">
          {visibleItems.map((item) => (
            <li key={item.id}>
              <button
                className="brief-open-button"
                type="button"
                aria-label={`${item.statement}，查看组织记录`}
                onClick={() => onOpenRecord(item.source_record_id)}
              >
                <span className={`brief-kind is-${item.kind}`}>
                  {item.kind === "risk" ? <AlertTriangle aria-hidden="true" /> : null}
                  {kindLabel(item)}
                </span>
                <span className="brief-copy">
                  <strong>{item.statement}</strong>
                  <small>{item.why_it_matters}</small>
                </span>
                <ArrowRight aria-hidden="true" />
              </button>
              <div className="brief-feedback" aria-label="简报反馈">
                {briefFeedback[item.id]?.status === "saved" ? (
                  <span role="status">已记录</span>
                ) : (
                  <>
                    {briefFeedback[item.id]?.status === "error" ? (
                      <span role="alert">反馈没有记录，请重试</span>
                    ) : null}
                    <button
                      type="button"
                      aria-label={`认为“${item.statement}”有帮助`}
                      title="有帮助"
                      disabled={briefFeedback[item.id]?.status === "pending"}
                      onClick={() => void recordBriefFeedback(item, true)}
                    >
                      <ThumbsUp aria-hidden="true" />
                    </button>
                    <button
                      type="button"
                      aria-label={`认为“${item.statement}”不准确`}
                      title="不准确"
                      disabled={briefFeedback[item.id]?.status === "pending"}
                      onClick={() => void recordBriefFeedback(item, false)}
                    >
                      <ThumbsDown aria-hidden="true" />
                    </button>
                  </>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
