from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any


PROCESS_MEMORY_TYPES = {
    "preference": "偏好",
    "rejection": "否定清单",
    "historical_decision": "历史决策",
    "hypothesis": "待验证假设",
    "retrospective": "复盘片段",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _bounded_confidence(value: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = 0.5
    return round(max(0.0, min(parsed, 1.0)), 3)


def _compact_key(value: str) -> str:
    separators = " ，。！？?；;、（）()[]【】\"'“”‘’_—/\\|+·<>《》"
    compact = value
    for char in separators:
        compact = compact.replace(char, "")
    return compact


def classify_process_memory(text: str) -> str:
    if any(term in text for term in ["不要", "不能", "否定", "不好", "别再", "禁用", "不许"]):
        return "rejection"
    if any(term in text for term in ["历史决策", "已经决定", "当时决定", "决定：", "定下来"]):
        return "historical_decision"
    if any(term in text for term in ["待验证", "假设", "需要验证", "验证："]):
        return "hypothesis"
    if any(term in text for term in ["复盘", "反馈", "结果发现", "教训", "问题是"]):
        return "retrospective"
    return "preference"


def _memory_id(text: str, source: str, actor: str, observed_at: str) -> str:
    digest = hashlib.sha256(f"{source}\n{actor}\n{observed_at}\n{text}".encode("utf-8")).hexdigest()
    return f"hxy-process-memory:{digest[:16]}"


def build_process_memory_record(
    text: str,
    *,
    source: str = "chat",
    actor: str = "unknown",
    observed_at: str | None = None,
    confidence: float = 0.5,
    reviewed: bool = False,
    promotable: bool | None = None,
) -> dict[str, Any]:
    content = text.strip()
    timestamp = observed_at or _now()
    memory_type = classify_process_memory(content)
    bounded_confidence = _bounded_confidence(confidence)
    can_promote = bool(promotable) if promotable is not None else memory_type in {
        "preference",
        "rejection",
        "historical_decision",
        "hypothesis",
        "retrospective",
    }
    return {
        "version": "hxy-process-memory.v1",
        "memory_id": _memory_id(content, source, actor, timestamp),
        "memory_type": memory_type,
        "memory_type_label": PROCESS_MEMORY_TYPES[memory_type],
        "content": content,
        "source": source,
        "actor": actor,
        "observed_at": timestamp,
        "confidence": bounded_confidence,
        "status": "process",
        "reviewed": bool(reviewed),
        "promotable": can_promote,
        "official_use_allowed": False,
        "governance": {
            "formal_knowledge_status": "not_official",
            "promotion_required": True,
            "requires_human_review": True,
            "usage_boundary": "过程记忆不能直接作为企业正式结论，只能作为上下文提醒或晋升候选。",
            "allowed_use": ["context_hint", "preference_hint", "review_input"],
            "blocked_use": ["approved_answer_source", "external_claim", "sop_without_review"],
        },
    }


def _promotion_priority(record: dict[str, Any]) -> str:
    if record.get("memory_type") in {"rejection", "historical_decision"}:
        return "high"
    if float(record.get("confidence") or 0) < 0.65:
        return "low"
    return "medium"


def build_memory_promotion_draft(record: dict[str, Any], *, target_domain: str = "general") -> dict[str, Any]:
    memory_id = str(record.get("memory_id") or "")
    content = str(record.get("content") or "")
    correction_package = {
        "version": "hxy-memory-promotion-correction-package.v1",
        "source_memory_id": memory_id,
        "normalized_question": _compact_key(f"过程记忆晋升{memory_id}"),
        "target_domain": target_domain,
        "memory_type": record.get("memory_type") or "preference",
        "recommended_actions": [
            "判断这条过程记忆是否只是偏好/讨论轨迹，还是应该升级为企业知识。",
            "补齐来源、证据、适用场景、负责人和版本。",
            "复核通过后只能进入 current_candidate；二次审核后才允许 approved。",
        ],
        "requires_human_approval": True,
    }
    return {
        "version": "hxy-memory-promotion-draft.v1",
        "source_memory_id": memory_id,
        "source_memory_type": record.get("memory_type") or "preference",
        "content": content,
        "target_domain": target_domain,
        "target_status": "current_candidate",
        "official_use_allowed": False,
        "requires_human_review": True,
        "risk_boundary": "过程记忆不能直接进入 approved，必须先成为候选知识并经过人工复核。",
        "candidate_claim": {
            "claim_id": f"hxy-process-claim:{hashlib.sha256(memory_id.encode('utf-8')).hexdigest()[:16]}",
            "claim": content,
            "domain": target_domain,
            "status": "current_candidate",
            "source_memory_id": memory_id,
            "confidence": record.get("confidence") or 0.5,
            "needs_validation": True,
        },
        "review_task": {
            "question": f"过程记忆晋升复核：{memory_id}",
            "intent": "process_memory_promotion",
            "reason": "promote_process_memory",
            "priority": _promotion_priority(record),
            "correction_package": correction_package,
        },
    }
