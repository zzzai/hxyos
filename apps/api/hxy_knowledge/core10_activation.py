from __future__ import annotations

import hashlib
import json
import re
from typing import Any


PACKET_VERSION = "hxyos-core10-activation-packet.v1"
DECISION_OPTIONS = ("approve", "reject", "request_correction")
GROUP_CASES = {
    "brand_constitution": ("core-brand-identity",),
    "product_system_sources": ("core-product-system",),
    "first_store_operations_sources": (
        "core-operating-decision",
        "core-next-action",
    ),
    "reception_standard_answer_card": ("core-citation",),
}
_FORBIDDEN_KEYS = {"claim_id", "chunk_id"}
_UNSAFE_ANSWER_TERMS = (
    "治疗",
    "治愈",
    "治好",
    "根治",
    "保证有效",
    "保证疗效",
    "一次见效",
    "立刻见效",
    "包好",
    "guarantees efficacy",
)
_BOUNDARY_MARKERS = (
    "不能",
    "不可",
    "不得",
    "不要",
    "不承诺",
    "无法保证",
    "不能保证",
    "不保证",
    "not ",
    "cannot ",
    "does not ",
)


def _failed_case_ids(report: dict[str, Any]) -> set[str]:
    return {
        str(score["case_id"])
        for score in report.get("scores", [])
        if isinstance(score, dict)
        and score.get("case_id")
        and score.get("passed") is False
    }


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _json_safe(nested)
            for key, nested in value.items()
            if str(key).lower() not in _FORBIDDEN_KEYS
        }
    if isinstance(value, (list, tuple)):
        return [_json_safe(nested) for nested in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _payload_sha256(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        _json_safe(payload),
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _source_evidence(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    fields = (
        "asset_id",
        "title",
        "source_origin",
        "source_authority",
        "authority_version",
    )
    return [
        {field: _json_safe(source[field]) for field in fields if field in source}
        for source in sources
        if isinstance(source, dict)
    ]


def _constitution_evidence(
    constitution_draft: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if not isinstance(constitution_draft, dict):
        return []
    references = constitution_draft.get("source_references", [])
    return [
        {"asset_id": _json_safe(reference["source_id"])}
        for reference in references
        if isinstance(reference, dict) and reference.get("source_id")
    ]


def _reception_evidence(
    reception_draft: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if not isinstance(reception_draft, dict):
        return []
    return [
        {"asset_id": source_id}
        for source_id in reception_draft.get("source_ids", [])
        if isinstance(source_id, str) and source_id.strip()
    ]


def _source_blockers(sources: list[dict[str, Any]]) -> list[str]:
    if not sources:
        return ["missing_source_selection"]
    blockers: list[str] = []
    if any(
        isinstance(source, dict)
        and str(source.get("source_origin") or "").strip().lower() == "external"
        for source in sources
    ):
        blockers.append("external_source_not_eligible")
    if any(
        not isinstance(source, dict)
        or not str(source.get("asset_id") or "").strip()
        or not isinstance(source.get("authority_version"), int)
        or source.get("authority_version", 0) < 1
        or str(source.get("source_origin") or "").strip().lower()
        not in {"internal", "external", "unknown"}
        or str(source.get("source_authority") or "").strip().lower()
        not in {"official_internal", "internal_material", "external_reference"}
        or (
            str(source.get("source_origin") or "").strip().lower()
            != "internal"
            and str(source.get("source_authority") or "").strip().lower()
            != "external_reference"
        )
        for source in sources
    ):
        blockers.append("invalid_source_record")
    return blockers


def _classification_intents(
    sources: list[dict[str, Any]],
    *,
    reason: str,
) -> list[dict[str, Any]]:
    intents: list[dict[str, Any]] = []
    for source in sources:
        origin = str(source.get("source_origin") or "").strip().lower()
        authority = str(source.get("source_authority") or "").strip().lower()
        if origin not in {"unknown", "internal"}:
            continue
        if authority != "external_reference":
            continue
        payload = {
            "operation": "classify_source_authority",
            "asset_id": str(source["asset_id"]),
            "expected_previous_version": source["authority_version"],
            "source_origin": "internal",
            "source_authority": "internal_material",
            "reason": reason,
        }
        intents.append({**payload, "payload_sha256": _payload_sha256(payload)})
    return intents


def _answer_has_unsafe_wording(answer: str) -> bool:
    normalized = " ".join(answer.split()).lower()
    for term in _UNSAFE_ANSWER_TERMS:
        term_lower = term.lower()
        start = 0
        while True:
            index = normalized.find(term_lower, start)
            if index < 0:
                break
            prefix = normalized[max(0, index - 12) : index]
            if not any(marker in prefix for marker in _BOUNDARY_MARKERS):
                return True
            start = index + len(term_lower)
    return False


def _normalized_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().lower()


def _approved_card_state(
    reception_draft: dict[str, Any] | None,
    existing_answer_cards: list[dict[str, Any]],
) -> dict[str, int]:
    if not isinstance(reception_draft, dict):
        return {"approved_match_count": 0, "approved_conflict_count": 0}
    question = _normalized_text(reception_draft.get("question"))
    answer = _normalized_text(reception_draft.get("answer"))
    matching = 0
    conflicting = 0
    for card in existing_answer_cards:
        if not isinstance(card, dict) or card.get("status") != "approved":
            continue
        if _normalized_text(card.get("question")) != question:
            continue
        if _normalized_text(card.get("answer")) == answer:
            matching += 1
        else:
            conflicting += 1
    return {
        "approved_match_count": matching,
        "approved_conflict_count": conflicting,
    }


def build_core10_activation_packet(
    *,
    report: dict[str, Any],
    constitution_state: dict[str, Any],
    constitution_draft: dict[str, Any] | None,
    product_sources: list[dict[str, Any]],
    operations_sources: list[dict[str, Any]],
    reception_draft: dict[str, Any] | None,
    existing_answer_cards: list[dict[str, Any]],
    generated_at: str | None = None,
) -> dict[str, Any]:
    failed_cases = _failed_case_ids(report)
    timestamp = generated_at
    approved_card_state = _approved_card_state(
        reception_draft,
        existing_answer_cards,
    )

    group_values = {
        "brand_constitution": {
            "current_state": _json_safe(constitution_state),
            "proposed_authority": {
                "authority": "official_internal",
                "draft": _json_safe(constitution_draft),
            },
            "source_evidence": _constitution_evidence(constitution_draft),
            "why_needed": "The brand identity case requires an approved constitution.",
            "risk_if_approved": "An incorrect constitution would become a formal brand boundary.",
            "risk_if_rejected": "The brand identity case remains without formal authority.",
        },
        "product_system_sources": {
            "current_state": {"selected_source_count": len(product_sources)},
            "proposed_authority": {
                "authority": "internal_material",
                "asset_ids": [
                    str(source.get("asset_id"))
                    for source in product_sources
                    if isinstance(source, dict) and source.get("asset_id")
                ],
            },
            "source_evidence": _source_evidence(product_sources),
            "why_needed": "The product-system case requires selected internal evidence.",
            "risk_if_approved": "Misclassified sources could influence product guidance.",
            "risk_if_rejected": "The product-system case remains reference-only.",
        },
        "first_store_operations_sources": {
            "current_state": {"selected_source_count": len(operations_sources)},
            "proposed_authority": {
                "authority": "internal_material",
                "asset_ids": [
                    str(source.get("asset_id"))
                    for source in operations_sources
                    if isinstance(source, dict) and source.get("asset_id")
                ],
            },
            "source_evidence": _source_evidence(operations_sources),
            "why_needed": "The first-store cases require selected operating evidence.",
            "risk_if_approved": "Misclassified sources could distort first-store actions.",
            "risk_if_rejected": "The first-store cases remain without cited evidence.",
        },
        "reception_standard_answer_card": {
            "current_state": {
                "draft_present": isinstance(reception_draft, dict),
                "existing_answer_card_count": len(existing_answer_cards),
                **approved_card_state,
            },
            "proposed_authority": {
                "authority": "approved_answer_card",
                "draft": _json_safe(reception_draft),
            },
            "source_evidence": _reception_evidence(reception_draft),
            "why_needed": "The reception case requires one approved standard answer.",
            "risk_if_approved": "Unsafe or conflicting wording could become formal guidance.",
            "risk_if_rejected": "The reception case remains without a formal cited answer.",
        },
    }

    items = []
    for group_id, mapped_cases in GROUP_CASES.items():
        affected_cases = [
            case_id for case_id in mapped_cases if case_id in failed_cases
        ]
        blockers: list[str] = []
        write_intents: list[dict[str, Any]] = []
        if affected_cases and group_id == "brand_constitution":
            if not isinstance(constitution_draft, dict) or not constitution_draft:
                blockers.append("missing_constitution_draft")
            if not blockers:
                payload = {
                    "operation": "activate_brand_constitution",
                    "expected_previous_version": constitution_state.get(
                        "active_version"
                    ),
                    "draft_version": constitution_draft.get("version"),
                }
                write_intents.append(
                    {**payload, "payload_sha256": _payload_sha256(constitution_draft)}
                )
        elif affected_cases and group_id == "product_system_sources":
            blockers = _source_blockers(product_sources)
            if not blockers:
                write_intents = _classification_intents(
                    product_sources,
                    reason="Selected source supports the Core-10 product-system case.",
                )
        elif affected_cases and group_id == "first_store_operations_sources":
            blockers = _source_blockers(operations_sources)
            if not blockers:
                write_intents = _classification_intents(
                    operations_sources,
                    reason="Selected source supports the Core-10 first-store cases.",
                )
        elif affected_cases and group_id == "reception_standard_answer_card":
            if not isinstance(reception_draft, dict) or not reception_draft:
                blockers.append("missing_reception_draft")
            else:
                if _answer_has_unsafe_wording(
                    str(reception_draft.get("answer") or "")
                ):
                    blockers.append("unsafe_answer_wording")
                if approved_card_state["approved_conflict_count"]:
                    blockers.append("approved_answer_card_conflict")
            if not blockers and not approved_card_state["approved_match_count"]:
                payload = {
                    "operation": "create_approved_answer_card",
                    "question": reception_draft.get("question"),
                    "source_ids": list(reception_draft.get("source_ids") or []),
                }
                write_intents.append(
                    {**payload, "payload_sha256": _payload_sha256(reception_draft)}
                )
        item = {
            "group_id": group_id,
            **group_values[group_id],
            "affected_core10_cases": affected_cases,
            "exact_write_intents": write_intents,
            "blockers": blockers,
            "decision_options": list(DECISION_OPTIONS),
            "official_use_allowed": False,
            "write_allowed": False,
        }
        items.append(item)

    return _json_safe(
        {
            "version": PACKET_VERSION,
            "generated_at": timestamp,
            "item_count": 4,
            "write_to_database": False,
            "publish_allowed": False,
            "items": items,
        }
    )
