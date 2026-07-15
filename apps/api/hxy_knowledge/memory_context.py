from __future__ import annotations

from typing import Any


DEFAULT_BUDGET = {
    "formal_knowledge": 3,
    "evidence": 5,
    "process_memory": 2,
    "short_term_messages": 6,
}

PROCESS_MEMORY_STATUSES = {"process"}
PROCESS_MEMORY_SOURCE_TYPES = {"process_memory"}
FORMAL_STATUSES = {"approved", "confirmed", "validated"}
FORMAL_SOURCE_TYPES = {"approved_answer_card", "approved_internal_asset", "sop", "decision_record"}
BLOCKED_STATUSES = {"deprecated", "superseded", "disputed", "conflicted"}


def _float_value(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return max(0.0, min(parsed, 1.0))


def _budget_value(budget: dict[str, Any] | None, key: str) -> int:
    value = (budget or {}).get(key, DEFAULT_BUDGET[key])
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = DEFAULT_BUDGET[key]
    return max(0, min(parsed, 20))


def _status(item: dict[str, Any]) -> str:
    return str(item.get("status") or "").lower()


def _source_type(item: dict[str, Any]) -> str:
    return str(item.get("source_type") or "").lower()


def _is_process_memory(item: dict[str, Any]) -> bool:
    return (
        str(item.get("layer") or "").lower() == "process_memory"
        or _status(item) in PROCESS_MEMORY_STATUSES
        or _source_type(item) in PROCESS_MEMORY_SOURCE_TYPES
    )


def _is_formal_knowledge(item: dict[str, Any]) -> bool:
    if _is_process_memory(item):
        return False
    return (
        str(item.get("layer") or "").lower() == "formal_knowledge"
        or _status(item) in FORMAL_STATUSES
        or _source_type(item) in FORMAL_SOURCE_TYPES
    )


def _is_blocked(item: dict[str, Any]) -> bool:
    return (
        _status(item) in BLOCKED_STATUSES
        or bool(item.get("conflict"))
        or bool(item.get("contradicts"))
    )


def compute_decay_score(item: dict[str, Any]) -> float:
    """Return a deterministic decay score: higher means less suitable for recall."""

    confidence = _float_value(item.get("confidence"), 0.7)
    recency = _float_value(item.get("recency"), 0.5)
    reuse = _float_value(item.get("reuse"), 0.0)
    correction_count = max(0, int(item.get("correction_count") or 0))
    conflict_penalty = 0.45 if _is_blocked(item) else 0.0
    status_penalty = 0.25 if _status(item) in {"reference", "draft", "needs_review"} else 0.0
    approved_boost = 0.25 if _is_formal_knowledge(item) else 0.0
    raw_score = (
        (1.0 - recency) * 0.25
        + (1.0 - confidence) * 0.2
        + min(correction_count, 3) * 0.15
        + conflict_penalty
        + status_penalty
        - reuse * 0.1
        - approved_boost
    )
    return round(max(0.0, min(raw_score, 1.0)), 3)


def score_memory_candidate(item: dict[str, Any]) -> float:
    semantic = _float_value(item.get("semantic_relevance"), _float_value(item.get("semantic_score"), 0.0))
    recency = _float_value(item.get("recency"), 0.5)
    importance = _float_value(item.get("importance"), 0.5)
    authority = 1.0 if _is_formal_knowledge(item) else (0.25 if _is_process_memory(item) else 0.45)
    risk_boost = 0.08 if str(item.get("risk_level") or "").lower() == "high" and _is_formal_knowledge(item) else 0.0
    decay = compute_decay_score(item)
    score = semantic * 0.38 + importance * 0.24 + recency * 0.14 + authority * 0.22 + risk_boost - decay * 0.25
    return round(max(0.0, min(score, 1.0)), 4)


def classify_storage_temperature(item: dict[str, Any]) -> str:
    if _is_blocked(item) or _status(item) in {"deprecated", "superseded"}:
        return "cold"
    score = score_memory_candidate(item)
    if _is_process_memory(item) and _float_value(item.get("importance"), 0.5) >= 0.85 and _float_value(
        item.get("semantic_relevance"), _float_value(item.get("semantic_score"), 0.0)
    ) >= 0.6:
        return "hot"
    if score >= 0.72 or (_is_formal_knowledge(item) and score >= 0.62):
        return "hot"
    if score >= 0.38:
        return "warm"
    return "cold"


def _decorate(item: dict[str, Any]) -> dict[str, Any]:
    decorated = dict(item)
    decorated["score"] = score_memory_candidate(item)
    decorated["decay_score"] = compute_decay_score(item)
    decorated["storage_temperature"] = classify_storage_temperature(item)
    if _is_process_memory(item):
        decorated["context_hint_only"] = True
        decorated["official_use_allowed"] = False
    return decorated


def _sort(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        (_decorate(item) for item in items),
        key=lambda item: (
            item.get("score") or 0,
            item.get("importance") or 0,
            item.get("semantic_relevance") or item.get("semantic_score") or 0,
        ),
        reverse=True,
    )


def _blocked_item(item: dict[str, Any]) -> dict[str, Any]:
    blocked = _decorate(item)
    blocked["blocked_reason"] = "conflicted" if _is_blocked(item) else "not_recallable"
    blocked["official_use_allowed"] = False
    return blocked


def build_memory_context(
    *,
    working_memory: dict[str, Any],
    short_term_messages: list[dict[str, Any]],
    retrieved_memories: list[dict[str, Any]],
    budget: dict[str, Any] | None = None,
) -> dict[str, Any]:
    formal_limit = _budget_value(budget, "formal_knowledge")
    evidence_limit = _budget_value(budget, "evidence")
    process_limit = _budget_value(budget, "process_memory")
    short_term_limit = _budget_value(budget, "short_term_messages")

    blocked = [_blocked_item(item) for item in retrieved_memories if _is_blocked(item)]
    usable = [item for item in retrieved_memories if not _is_blocked(item)]
    formal = _sort([item for item in usable if _is_formal_knowledge(item)])[:formal_limit]
    process = _sort([item for item in usable if _is_process_memory(item)])[:process_limit]
    evidence = _sort([item for item in usable if not _is_formal_knowledge(item) and not _is_process_memory(item)])[:evidence_limit]
    short_term = list(short_term_messages or [])[-short_term_limit:] if short_term_limit else []
    storage_temperature = {
        str(item.get("memory_id") or item.get("id") or index): classify_storage_temperature(item)
        for index, item in enumerate(retrieved_memories)
    }
    input_count = len(short_term_messages or []) + len(retrieved_memories or [])
    used_count = len(short_term) + len(formal) + len(evidence) + len(process)
    max_count = short_term_limit + formal_limit + evidence_limit + process_limit

    return {
        "version": "hxy-memory-context.v1",
        "working_memory": {
            "layer": "Working Memory",
            "goal": working_memory.get("goal") or "",
            "role": working_memory.get("role") or "team",
            "scenario": working_memory.get("scenario") or "general",
            "remaining_steps": working_memory.get("remaining_steps") or [],
            "tool_results": working_memory.get("tool_results") or [],
            "stop_condition": working_memory.get("stop_condition") or "answer_or_review_required",
        },
        "short_term_context": short_term,
        "formal_knowledge": formal,
        "retrieval_evidence": evidence,
        "process_memory_hints": process,
        "blocked_memories": blocked,
        "storage_temperature": storage_temperature,
        "context_budget": {
            "limits": {
                "short_term_messages": short_term_limit,
                "formal_knowledge": formal_limit,
                "evidence": evidence_limit,
                "process_memory": process_limit,
            },
            "input_count": input_count,
            "used_count": used_count,
            "max_count": max_count,
            "context_overflow": input_count > max_count or len(short_term_messages or []) > short_term_limit,
        },
        "authority_rule": "process_memory_cannot_be_authority",
        "retrieval_rule": "semantic_relevance_plus_recency_plus_importance_plus_authority_status",
        "forgetting_rule": "forgetting_means_decay_archive_or_review_not_delete",
    }
