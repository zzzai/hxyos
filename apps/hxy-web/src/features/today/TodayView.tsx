import { AlertTriangle, ArrowRight, CheckCircle2, RefreshCw } from "lucide-react";

import type { TodayBriefItem } from "../../api/today";

interface TodayViewProps {
  items: TodayBriefItem[];
  status: "loading" | "ready" | "error";
  onOpenRecord: (recordId: string) => void;
  onRetry: () => void;
}

function kindLabel(item: TodayBriefItem): string {
  if (item.kind === "risk") return item.severity === "critical" ? "紧急风险" : "风险";
  if (item.kind === "decision") return "决定";
  return "进展";
}

export function TodayView({ items, status, onOpenRecord, onRetry }: TodayViewProps) {
  return (
    <section className="frontstage-view today-view" aria-labelledby="today-title">
      <header className="view-header">
        <div>
          <h1 id="today-title">今日</h1>
          <p>只看与你当前身份有关的关键变化</p>
        </div>
      </header>

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
      ) : items.length === 0 ? (
        <div className="quiet-state">
          <CheckCircle2 aria-hidden="true" />
          <p>现在没有需要特别关注的变化</p>
        </div>
      ) : (
        <ul className="briefing-list" aria-label="今日重点">
          {items.slice(0, 3).map((item) => (
            <li key={item.id}>
              <button
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
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
