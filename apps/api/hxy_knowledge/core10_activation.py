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
_PUBLIC_ASSET_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9:._-]{0,127}$")
_CONSTITUTION_VERSION_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
_CONSTITUTION_SOURCE_AUTHORITIES = {
    "approved_answer_card",
    "official_internal",
}
_REQUIRED_ROLE_VARIANTS = (
    "founder",
    "headquarters",
    "store_manager",
    "store_staff",
)
_RESOLVED_SOURCE_AUTHORITIES = {"internal_material", "official_internal"}
_SENSITIVE_ASSET_ID_HINTS = (
    "credential",
    "password",
    "passwd",
    "secret",
    "api_key",
    "apikey",
)
_UNSAFE_ASSET_ID_TOKENS = {
    "alter",
    "bash",
    "cmd",
    "command",
    "curl",
    "delete",
    "drop",
    "exec",
    "execute",
    "insert",
    "key",
    "powershell",
    "rm",
    "select",
    "sql",
    "truncate",
    "token",
    "update",
    "wget",
}

# This is a conservative activation preflight, not the complete compliance engine.
_HIGH_RISK_ANSWER_PATTERNS = (
    re.compile(
        r"(?:保证|承诺|确保)[^。！？.!?；;\n]{0,16}"
        r"(?:效果|有效|疗效|结果|治愈|治疗)"
    ),
    re.compile(
        r"(?:效果|有效|疗效|结果|治愈|治疗)[^。！？.!?；;\n]{0,16}"
        r"(?:保证|承诺|确保)"
    ),
    re.compile(r"治疗|治愈|治好|根治|诊断|包好"),
    re.compile(r"(?:一次|立刻)见效"),
    re.compile(r"(?:100\s*%|百分之百)\s*(?:有效|见效)"),
    re.compile(
        r"\b(?:guarantee|ensure|promise|commit)(?:s|d)?\b"
        r"[^.!?;；\n]{0,32}"
        r"\b(?:cure|treat|diagnos(?:e|is)|effective|efficacy|results?)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b100\s*%\s*effective\b", re.IGNORECASE),
    re.compile(
        r"\b(?:diagnos(?:e|is|ed|es|ing)|treat(?:s|ed|ing|ment)?|"
        r"cure(?:s|d|ing)?)\b",
        re.IGNORECASE,
    ),
)
_NEGATIVE_SCOPE_PATTERNS = (
    re.compile(r"(?:不会|不能|不可|不得|不要|不承诺|无法|并非|不是|不)"
               r"(?:\s*用于)?\s*$"),
    re.compile(
        r"(?:not|cannot|can't|does not|do not|is not|are not|"
        r"not intended to|not used to)\s*$",
        re.IGNORECASE,
    ),
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
        and _is_safe_public_asset_id(source.get("asset_id"))
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
        if isinstance(reference, dict)
        and _is_safe_public_asset_id(reference.get("source_id"))
    ]


def _reception_evidence(
    reception_draft: dict[str, Any] | None,
    resolved_source_ids: set[str],
) -> list[dict[str, Any]]:
    if not isinstance(reception_draft, dict):
        return []
    return [
        {"asset_id": source_id}
        for source_id in _safe_reception_source_ids(reception_draft)
        if source_id in resolved_source_ids
    ]


def _safe_reception_source_ids(reception_draft: dict[str, Any]) -> list[str]:
    source_ids = reception_draft.get("source_ids")
    if not isinstance(source_ids, list):
        return []
    return [
        source_id
        for source_id in source_ids
        if _is_safe_public_asset_id(source_id)
    ]


def _safe_reception_draft(
    reception_draft: dict[str, Any] | None,
) -> Any:
    canonical_draft = _canonical_reception_draft(reception_draft)
    safe_draft = _json_safe(canonical_draft)
    if isinstance(safe_draft, dict) and isinstance(canonical_draft, dict):
        if "source_ids" in canonical_draft:
            safe_draft["source_ids"] = _safe_reception_source_ids(
                canonical_draft
            )
    return safe_draft


def _reception_question_pattern(reception_draft: dict[str, Any]) -> Any:
    if "question_pattern" in reception_draft:
        return reception_draft.get("question_pattern")
    return reception_draft.get("question")


def _canonical_reception_draft(
    reception_draft: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not isinstance(reception_draft, dict):
        return None
    canonical = dict(reception_draft)
    canonical["question_pattern"] = _reception_question_pattern(reception_draft)
    canonical.pop("question", None)
    return canonical


def _reception_source_blockers(
    reception_draft: dict[str, Any],
    resolved_source_ids: set[str],
) -> list[str]:
    source_ids = reception_draft.get("source_ids")
    if not isinstance(source_ids, list) or not source_ids:
        return ["missing_source_selection"]
    blockers: list[str] = []
    safe_source_ids = _safe_reception_source_ids(reception_draft)
    if len(safe_source_ids) != len(source_ids):
        blockers.append("invalid_source_record")
    if any(source_id not in resolved_source_ids for source_id in safe_source_ids):
        blockers.append("unresolved_source_evidence")
    return blockers


def _resolved_source_ids(
    product_sources: list[dict[str, Any]],
    operations_sources: list[dict[str, Any]],
) -> set[str]:
    return {
        str(source["asset_id"])
        for sources in (product_sources, operations_sources)
        for source in sources
        if _is_valid_resolved_source_snapshot(source)
    }


def _is_valid_resolved_source_snapshot(source: Any) -> bool:
    if not isinstance(source, dict):
        return False
    authority_version = source.get("authority_version")
    return (
        _is_safe_public_asset_id(source.get("asset_id"))
        and str(source.get("source_origin") or "").strip().lower() == "internal"
        and str(source.get("source_authority") or "").strip().lower()
        in _RESOLVED_SOURCE_AUTHORITIES
        and isinstance(authority_version, int)
        and not isinstance(authority_version, bool)
        and authority_version >= 1
    )


def _is_nonblank_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_valid_constitution_draft(
    constitution_draft: dict[str, Any],
) -> bool:
    core_statements = constitution_draft.get("core_statements")
    if not (
        isinstance(constitution_draft.get("version"), str)
        and _CONSTITUTION_VERSION_PATTERN.fullmatch(
            constitution_draft["version"]
        )
        and isinstance(core_statements, dict)
        and _is_nonblank_string(core_statements.get("brand_identity"))
        and _is_nonblank_string_list(core_statements.get("service_facts"))
    ):
        return False

    role_variants = constitution_draft.get("role_variants")
    if not isinstance(role_variants, dict) or any(
        not _is_nonblank_string(role_variants.get(role))
        for role in _REQUIRED_ROLE_VARIANTS
    ):
        return False

    forbidden = constitution_draft.get("forbidden_interpretations")
    if not isinstance(forbidden, list) or not forbidden or any(
        not isinstance(item, dict)
        or not _is_nonblank_string(item.get("statement"))
        or not _is_nonblank_string_list(item.get("blocked_terms"))
        for item in forbidden
    ):
        return False

    references = constitution_draft.get("source_references")
    return (
        isinstance(references, list)
        and bool(references)
        and all(
            isinstance(reference, dict)
            and _is_safe_public_asset_id(reference.get("source_id"))
            and reference.get("authority") in _CONSTITUTION_SOURCE_AUTHORITIES
            for reference in references
        )
    )


def _is_nonblank_string_list(value: Any) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(_is_nonblank_string(item) for item in value)
    )


def _is_valid_reception_draft(reception_draft: dict[str, Any]) -> bool:
    return _is_nonblank_string(
        _reception_question_pattern(reception_draft)
    ) and _is_nonblank_string(reception_draft.get("answer"))


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
        or not _is_safe_public_asset_id(source.get("asset_id"))
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


def _is_safe_public_asset_id(value: Any) -> bool:
    if not isinstance(value, str) or not _PUBLIC_ASSET_ID_PATTERN.fullmatch(value):
        return False
    normalized = value.lower()
    if any(hint in normalized for hint in _SENSITIVE_ASSET_ID_HINTS):
        return False
    tokens = set(re.split(r"[:._-]+", normalized))
    return not tokens.intersection(_UNSAFE_ASSET_ID_TOKENS)


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
    normalized = " ".join(answer.split())
    for pattern in _HIGH_RISK_ANSWER_PATTERNS:
        for match in pattern.finditer(normalized):
            prefix = normalized[max(0, match.start() - 64) : match.start()]
            clause = re.split(r"[。！？.!?；;，,\n]", prefix)[-1]
            if not any(pattern.search(clause) for pattern in _NEGATIVE_SCOPE_PATTERNS):
                return True
    return False


def _normalized_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().lower()


def _approved_card_state(
    reception_draft: dict[str, Any] | None,
    existing_answer_cards: list[dict[str, Any]],
) -> dict[str, int]:
    if not isinstance(reception_draft, dict):
        return {"approved_match_count": 0, "approved_conflict_count": 0}
    question = _normalized_text(_reception_question_pattern(reception_draft))
    answer = _normalized_text(reception_draft.get("answer"))
    matching = 0
    conflicting = 0
    for card in existing_answer_cards:
        if not isinstance(card, dict) or card.get("status") != "approved":
            continue
        card_question = card.get("question_pattern") or card.get("question")
        if _normalized_text(card_question) != question:
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
    resolved_source_ids = _resolved_source_ids(
        product_sources,
        operations_sources,
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
                    if isinstance(source, dict)
                    and _is_safe_public_asset_id(source.get("asset_id"))
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
                    if isinstance(source, dict)
                    and _is_safe_public_asset_id(source.get("asset_id"))
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
                "draft": _safe_reception_draft(reception_draft),
            },
            "source_evidence": _reception_evidence(
                reception_draft,
                resolved_source_ids,
            ),
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
            elif not _is_valid_constitution_draft(constitution_draft):
                blockers.append("invalid_constitution_draft")
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
                if not _is_valid_reception_draft(reception_draft):
                    blockers.append("invalid_reception_draft")
                blockers.extend(
                    _reception_source_blockers(
                        reception_draft,
                        resolved_source_ids,
                    )
                )
                answer = reception_draft.get("answer")
                if isinstance(answer, str) and _answer_has_unsafe_wording(answer):
                    blockers.append("unsafe_answer_wording")
                if approved_card_state["approved_conflict_count"]:
                    blockers.append("approved_answer_card_conflict")
            if not blockers and not approved_card_state["approved_match_count"]:
                payload = {
                    "operation": "create_approved_answer_card",
                    "question_pattern": _reception_question_pattern(
                        reception_draft
                    ),
                    "source_ids": _safe_reception_source_ids(reception_draft),
                }
                canonical_reception_draft = _canonical_reception_draft(
                    reception_draft
                )
                write_intents.append(
                    {
                        **payload,
                        "payload_sha256": _payload_sha256(
                            canonical_reception_draft
                        ),
                    }
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
