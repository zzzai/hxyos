import { FileClock, RefreshCw } from "lucide-react";

import type { OrganizationRecord } from "../../api/records";

interface RecordsViewProps {
  records: OrganizationRecord[];
  status: "loading" | "ready" | "error";
  onOpenRecord: (recordId: string) => void;
  onRetry: () => void;
}

function statusLabel(status: OrganizationRecord["processing_status"]): string {
  if (status === "ready") return "已理解";
  if (status === "needs_attention") return "需要补充";
  if (status === "processing") return "理解中";
  return "已收到";
}

function formatCapturedAt(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

export function RecordsView({ records, status, onOpenRecord, onRetry }: RecordsViewProps) {
  return (
    <section className="frontstage-view records-view" aria-labelledby="records-title">
      <header className="view-header">
        <div>
          <h1 id="records-title">组织记录</h1>
          <p>你提交或有权限查看的原始信息</p>
        </div>
      </header>

      {status === "loading" ? (
        <div className="quiet-state" role="status">正在加载记录</div>
      ) : status === "error" ? (
        <div className="quiet-state" role="alert">
          <p>组织记录暂时没有加载出来</p>
          <button type="button" onClick={onRetry}>
            <RefreshCw aria-hidden="true" />
            重试
          </button>
        </div>
      ) : records.length === 0 ? (
        <div className="quiet-state">
          <FileClock aria-hidden="true" />
          <p>还没有组织记录</p>
        </div>
      ) : (
        <ul className="record-list" aria-label="组织记录列表">
          {records.map((record) => (
            <li key={record.id}>
              <button type="button" onClick={() => onOpenRecord(record.id)}>
                <span className="record-main">
                  <strong>{record.preview || record.original.assets[0]?.file_name || "未命名记录"}</strong>
                  <small>
                    {record.interpretation?.summary || "系统正在理解这条记录"}
                  </small>
                </span>
                <span className="record-meta">
                  <small>{statusLabel(record.processing_status)}</small>
                  <time dateTime={record.captured_at}>{formatCapturedAt(record.captured_at)}</time>
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
