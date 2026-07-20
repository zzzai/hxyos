import { ArrowLeft, File, MessageSquareText, X } from "lucide-react";

import type {
  OrganizationRecord,
  RecordInterpretationItem,
} from "../../api/records";

interface RecordDetailProps {
  record: OrganizationRecord;
  canAsk: boolean;
  onClose: () => void;
  onAsk: (record: OrganizationRecord) => void;
}

function InterpretationGroup({
  title,
  items,
}: {
  title: string;
  items: RecordInterpretationItem[];
}) {
  if (items.length === 0) return null;
  return (
    <section className="interpretation-group">
      <h3>{title}</h3>
      <ul>
        {items.map((item, index) => (
          <li key={`${title}-${index}`}>
            <p>{item.statement}</p>
            {item.evidence.map((evidence, evidenceIndex) => (
              <blockquote key={`${evidence.quote}-${evidenceIndex}`}>
                {evidence.quote}
              </blockquote>
            ))}
          </li>
        ))}
      </ul>
    </section>
  );
}

export function RecordDetail({ record, canAsk, onClose, onAsk }: RecordDetailProps) {
  const interpretation = record.interpretation;
  return (
    <aside className="record-detail" role="region" aria-label="组织记录详情">
      <header>
        <button className="detail-back" type="button" onClick={onClose}>
          <ArrowLeft aria-hidden="true" />
          返回
        </button>
        <button
          className="detail-close"
          type="button"
          aria-label="关闭组织记录详情"
          onClick={onClose}
        >
          <X aria-hidden="true" />
        </button>
      </header>

      <div className="record-detail-scroll">
        <div className="record-detail-heading">
          <span>组织记录</span>
          <h2>{record.interpretation?.summary || record.preview || "未命名记录"}</h2>
          <p>{record.submitted_by}</p>
        </div>

        <section className="record-original">
          <h3>原始内容</h3>
          {record.original.text ? <p>{record.original.text}</p> : null}
          {record.original.assets.length > 0 ? (
            <ul>
              {record.original.assets.map((asset) => (
                <li key={asset.id}>
                  <a
                    href={`/api/v1/materials/${encodeURIComponent(asset.id)}/content`}
                    target="_blank"
                    rel="noreferrer"
                    aria-label={`打开原始资料 ${asset.file_name}`}
                  >
                    <File aria-hidden="true" />
                    <span>{asset.file_name}</span>
                  </a>
                </li>
              ))}
            </ul>
          ) : null}
        </section>

        {interpretation ? (
          <section className="record-understanding">
            <h3>系统理解</h3>
            <p>{interpretation.summary}</p>
            <InterpretationGroup title="事实" items={interpretation.facts} />
            <InterpretationGroup title="决定" items={interpretation.decisions} />
            <InterpretationGroup title="进展" items={interpretation.progress} />
            <InterpretationGroup title="风险" items={interpretation.risks} />
            <small>这是基于原始资料形成的工作理解，不会自动成为正式知识。</small>
          </section>
        ) : (
          <p className="detail-processing">系统正在理解这条记录</p>
        )}
      </div>

      {canAsk ? (
        <footer>
          <button className="ask-record-button" type="button" onClick={() => onAsk(record)}>
            <MessageSquareText aria-hidden="true" />
            基于这条记录提问
          </button>
        </footer>
      ) : null}
    </aside>
  );
}
