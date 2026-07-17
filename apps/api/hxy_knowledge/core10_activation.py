from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


PACKET_VERSION = "hxyos-core10-activation-packet.v1"
DECISION_OPTIONS = ("approve", "reject", "request_correction")
AUTHORITY_RULE = "activation_packet_is_a_proposal_not_authority"
ITEM_CASES = {
    "brand_constitution": ("core-brand-identity",),
    "product_system_sources": ("core-product-system",),
    "first_store_operations_sources": (
        "core-operating-decision",
        "core-next-action",
    ),
    "reception_standard_answer_card": ("core-citation",),
}
_UPSTREAM_INPUT_KEYS = (
    "report",
    "constitution_state",
    "constitution_draft",
    "product_sources",
    "operations_sources",
    "reception_draft",
    "existing_answer_cards",
)
_ITEM_UPSTREAM_KEYS = {
    "brand_constitution": (
        "report",
        "constitution_state",
        "constitution_draft",
    ),
    "product_system_sources": ("report", "product_sources"),
    "first_store_operations_sources": ("report", "operations_sources"),
    "reception_standard_answer_card": (
        "report",
        "reception_draft",
        "existing_answer_cards",
        "product_sources",
        "operations_sources",
    ),
}
_PACKET_IDENTITY_EXCLUDED_KEYS = {
    "artifact_fingerprint",
    "generated_at",
    "packet_id",
    "packet_fingerprint",
}
_ARTIFACT_FINGERPRINT_EXCLUDED_KEYS = {"artifact_fingerprint"}
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

_ARTIFACT_FILENAMES = {
    "packet_json": "packet.json",
    "packet_markdown": "packet.md",
    "decision_sample": "decisions.sample.json",
}
_ARTIFACT_ITEM_TITLES = {
    "brand_constitution": "品牌宪法",
    "product_system_sources": "产品体系资料",
    "first_store_operations_sources": "首店经营资料",
    "reception_standard_answer_card": "接待标准答案卡",
}
_ARTIFACT_REDACTION = "（内容已安全隐藏）"
_ARTIFACT_UNSAFE_KEY_TOKENS = {
    "claim_id",
    "chunk_id",
    "command",
    "credential",
    "database_url",
    "db_url",
    "dsn",
    "password",
    "passwd",
    "path",
    "query",
    "secret",
    "shell",
    "sql",
    "token",
}
_ARTIFACT_SENSITIVE_TEXT_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])(?:claim[_-]?id|chunk[_-]?id|credential(?:s)?|"
    r"secret(?:s)?|password|passwd|api[-_ ]?key|access[-_ ]?token|"
    r"database[-_ ]?url|db[-_ ]?url)(?![A-Za-z0-9])",
    re.IGNORECASE,
)
_ARTIFACT_DATABASE_URL_PATTERN = re.compile(
    r"\b(?:postgres(?:ql)?|mysql|mariadb|sqlite|mongodb(?:\+srv)?|redis)"
    r":/{2,3}\S+",
    re.IGNORECASE,
)
_ARTIFACT_CREDENTIAL_URL_PATTERN = re.compile(
    r"\b[a-z][a-z0-9+.-]*://[^\s/@:]+:[^\s/@]+@\S+",
    re.IGNORECASE,
)
_ARTIFACT_POSIX_PATH_PATTERN = re.compile(
    r"(?:^|[\s\"'`(=])/(?:[A-Za-z0-9._~-]+/)*[A-Za-z0-9._~-]+"
)
_ARTIFACT_WINDOWS_PATH_PATTERN = re.compile(
    r"\b[A-Za-z]:[\\/](?:[^\s\\/]+[\\/])*[^\s\\/]+"
)
_ARTIFACT_SQL_WRITE_PATTERN = re.compile(
    r"\b(?:insert\s+into|update\s+[A-Za-z0-9_.]+\s+set|delete\s+from|"
    r"drop\s+(?:table|database|schema)|alter\s+table|"
    r"truncate(?:\s+table)?|create\s+(?:table|database|schema)|"
    r"merge\s+into|grant\s+|revoke\s+)\b",
    re.IGNORECASE,
)
_ARTIFACT_SHELL_WRITE_PATTERN = re.compile(
    r"\b(?:rm|mv|cp|install|mkdir|touch|chmod|chown|tee|dd|truncate|"
    r"curl|wget)\b(?:\s+\S+)+|"
    r"\b(?:bash|sh|zsh|powershell|cmd)(?:\.exe)?\s+(?:-c|/c)\b|"
    r"(?:^|\s)(?:>>?|2>)\s*\S+",
    re.IGNORECASE,
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


def _validate_canonical_json(value: Any) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            if not isinstance(key, str):
                raise TypeError("canonical JSON object keys must be strings")
            _validate_canonical_json(nested)
        return
    if isinstance(value, list):
        for nested in value:
            _validate_canonical_json(nested)
        return
    if value is None or isinstance(value, (str, int, float, bool)):
        return
    raise TypeError(
        f"unsupported canonical JSON value: {type(value).__name__}"
    )


def json_fingerprint(payload: Any) -> dict[str, str]:
    _validate_canonical_json(payload)
    encoded = json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return {
        "algorithm": "sha256",
        "digest": hashlib.sha256(encoded).hexdigest(),
    }


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


def _bounded_constitution_state(
    constitution_state: dict[str, Any],
) -> dict[str, Any]:
    fields = ("status", "active_version", "authority_version")
    return {
        field: _json_safe(constitution_state[field])
        for field in fields
        if field in constitution_state
    }


def _bounded_constitution_draft(
    constitution_draft: dict[str, Any] | None,
) -> Any:
    if not isinstance(constitution_draft, dict):
        return None
    fields = (
        "version",
        "core_statements",
        "role_variants",
        "forbidden_interpretations",
        "source_references",
    )
    return {
        field: _json_safe(constitution_draft[field])
        for field in fields
        if field in constitution_draft
    }


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
    if not isinstance(canonical_draft, dict):
        return None
    safe_draft = {
        field: _json_safe(canonical_draft[field])
        for field in ("question_pattern", "answer")
        if field in canonical_draft
    }
    if "source_ids" in canonical_draft:
        safe_draft["source_ids"] = _safe_reception_source_ids(canonical_draft)
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


def _item_fingerprint(
    item: dict[str, Any],
    *,
    upstream_fingerprints: dict[str, Any],
) -> str:
    item_key = item["item_key"]
    dependencies = {
        key: upstream_fingerprints[key]
        for key in _ITEM_UPSTREAM_KEYS[item_key]
    }
    item_identity = {
        key: value
        for key, value in item.items()
        if key != "item_fingerprint"
    }
    return json_fingerprint(
        {
            "item": item_identity,
            "dependencies": dependencies,
        }
    )["digest"]


def _packet_fingerprint_digest(packet: dict[str, Any]) -> str:
    packet_identity = {
        key: value
        for key, value in packet.items()
        if key not in _PACKET_IDENTITY_EXCLUDED_KEYS
    }
    return json_fingerprint(packet_identity)["digest"]


def _artifact_fingerprint_digest(packet: dict[str, Any]) -> str:
    artifact_identity = {
        key: value
        for key, value in packet.items()
        if key not in _ARTIFACT_FINGERPRINT_EXCLUDED_KEYS
    }
    return json_fingerprint(artifact_identity)["digest"]


def _is_sha256_digest(value: Any) -> bool:
    return isinstance(value, str) and bool(
        re.fullmatch(r"[0-9a-f]{64}", value)
    )


def _artifact_key_is_safe(key: str) -> bool:
    normalized = key.strip().lower().replace("-", "_")
    tokens = set(normalized.split("_"))
    return (
        normalized not in _ARTIFACT_UNSAFE_KEY_TOKENS
        and not normalized.endswith("_path")
        and not tokens.intersection(_ARTIFACT_UNSAFE_KEY_TOKENS)
    )


def _safe_artifact_text(value: str) -> str:
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", " ", value)
    text = re.sub(r"\s+", " ", text).strip()
    unsafe_patterns = (
        _ARTIFACT_SENSITIVE_TEXT_PATTERN,
        _ARTIFACT_DATABASE_URL_PATTERN,
        _ARTIFACT_CREDENTIAL_URL_PATTERN,
        _ARTIFACT_POSIX_PATH_PATTERN,
        _ARTIFACT_WINDOWS_PATH_PATTERN,
        _ARTIFACT_SQL_WRITE_PATTERN,
        _ARTIFACT_SHELL_WRITE_PATTERN,
    )
    if any(pattern.search(text) for pattern in unsafe_patterns):
        return _ARTIFACT_REDACTION
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\\", "\\\\")
        .replace("`", "\\`")
        .replace("*", "\\*")
        .replace("_", "\\_")
        .replace("[", "\\[")
        .replace("]", "\\]")
    )


def _safe_artifact_value(value: Any) -> Any:
    if isinstance(value, dict):
        safe: dict[str, Any] = {}
        for key, nested in value.items():
            key_text = str(key)
            if not _artifact_key_is_safe(key_text):
                continue
            safe_key = _safe_artifact_text(key_text)
            if safe_key == _ARTIFACT_REDACTION:
                continue
            safe[safe_key] = _safe_artifact_value(nested)
        return safe
    if isinstance(value, (list, tuple)):
        return [_safe_artifact_value(nested) for nested in value]
    if isinstance(value, str):
        return _safe_artifact_text(value)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return _safe_artifact_text(str(value))


def _artifact_scalar_text(value: Any) -> str:
    if value is None:
        return "无"
    if value is True:
        return "是"
    if value is False:
        return "否"
    return str(value) if str(value) else "无"


def _artifact_markdown_lines(value: Any, *, depth: int = 0) -> list[str]:
    prefix = "  " * depth
    if isinstance(value, dict):
        if not value:
            return [f"{prefix}- 无"]
        lines: list[str] = []
        for key, nested in value.items():
            if isinstance(nested, (dict, list)):
                lines.append(f"{prefix}- {key}:")
                lines.extend(_artifact_markdown_lines(nested, depth=depth + 1))
            else:
                lines.append(
                    f"{prefix}- {key}: {_artifact_scalar_text(nested)}"
                )
        return lines
    if isinstance(value, list):
        if not value:
            return [f"{prefix}- 无"]
        lines = []
        for index, nested in enumerate(value, start=1):
            if isinstance(nested, (dict, list)):
                lines.append(f"{prefix}- 条目 {index}:")
                lines.extend(_artifact_markdown_lines(nested, depth=depth + 1))
            else:
                lines.append(f"{prefix}- {_artifact_scalar_text(nested)}")
        return lines
    return [f"{prefix}- {_artifact_scalar_text(value)}"]


def _core10_artifact_packet_items(
    packet: Any,
) -> tuple[str, str, list[dict[str, Any]]]:
    if not isinstance(packet, dict):
        raise TypeError("core10 activation packet must be an object")
    packet_id = packet.get("packet_id")
    packet_fingerprint = packet.get("packet_fingerprint")
    if not _is_nonblank_string(packet_id):
        raise ValueError("core10 activation packet id is invalid")
    if not _is_sha256_digest(packet_fingerprint):
        raise ValueError("core10 activation packet fingerprint is invalid")

    raw_items = packet.get("items")
    if not isinstance(raw_items, list) or len(raw_items) != len(ITEM_CASES):
        raise ValueError("core10 activation packet must contain exactly four items")
    items: list[dict[str, Any]] = []
    item_keys: list[str] = []
    for item in raw_items:
        if not isinstance(item, dict):
            raise ValueError("core10 activation packet item is invalid")
        item_key = item.get("item_key")
        if item_key not in ITEM_CASES:
            raise ValueError("core10 activation packet item key is invalid")
        if not _is_sha256_digest(item.get("item_fingerprint")):
            raise ValueError("core10 activation packet item fingerprint is invalid")
        item_keys.append(item_key)
        items.append(item)
    if len(set(item_keys)) != len(ITEM_CASES) or set(item_keys) != set(ITEM_CASES):
        raise ValueError("core10 activation packet items are incomplete")
    return packet_id, packet_fingerprint, items


def _verify_core10_activation_packet_fingerprints(
    packet: dict[str, Any],
) -> None:
    packet_id, packet_fingerprint, items = _core10_artifact_packet_items(packet)
    upstream_fingerprints = packet.get("upstream_fingerprints")
    if not isinstance(upstream_fingerprints, dict):
        raise ValueError("core10 activation packet fingerprint inputs are invalid")

    for item in items:
        try:
            item_fingerprint = _item_fingerprint(
                item,
                upstream_fingerprints=upstream_fingerprints,
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(
                "core10 activation packet item fingerprint inputs are invalid"
            ) from error
        if item["item_fingerprint"] != item_fingerprint:
            raise ValueError("core10 activation packet item fingerprint mismatch")

    if _packet_fingerprint_digest(packet) != packet_fingerprint:
        raise ValueError("core10 activation packet fingerprint mismatch")
    if packet_id != f"core10-activation:{packet_fingerprint[:12]}":
        raise ValueError("core10 activation packet id fingerprint mismatch")
    artifact_fingerprint = packet.get("artifact_fingerprint")
    if not _is_sha256_digest(artifact_fingerprint):
        raise ValueError("core10 activation artifact fingerprint is invalid")
    if _artifact_fingerprint_digest(packet) != artifact_fingerprint:
        raise ValueError("core10 activation artifact fingerprint mismatch")


def _verify_core10_activation_packet_governance(
    packet: dict[str, Any],
) -> None:
    _packet_id, _packet_fingerprint, items = _core10_artifact_packet_items(packet)
    if (
        packet.get("version") != PACKET_VERSION
        or type(packet.get("item_count")) is not int
        or packet.get("item_count") != len(ITEM_CASES)
        or packet.get("preview_only") is not True
        or packet.get("write_to_database") is not False
        or packet.get("publish_allowed") is not False
        or packet.get("official_use_allowed") is not False
        or packet.get("requires_founder_decision") is not True
        or packet.get("authority_rule") != AUTHORITY_RULE
    ):
        raise ValueError("core10 activation packet governance contract is invalid")

    generated_at = packet.get("generated_at")
    if not isinstance(generated_at, str) or not generated_at.strip():
        raise ValueError("core10 activation packet generated_at is invalid")
    try:
        parsed_generated_at = datetime.fromisoformat(
            generated_at.replace("Z", "+00:00")
        )
    except ValueError as error:
        raise ValueError(
            "core10 activation packet generated_at is invalid"
        ) from error
    if (
        parsed_generated_at.tzinfo is None
        or parsed_generated_at.utcoffset() != timedelta(0)
    ):
        raise ValueError("core10 activation packet generated_at must be UTC")

    upstream_fingerprints = packet.get("upstream_fingerprints")
    if not isinstance(upstream_fingerprints, dict) or set(
        upstream_fingerprints
    ) != set(_UPSTREAM_INPUT_KEYS):
        raise ValueError("core10 activation packet governance inputs are invalid")
    for fingerprint in upstream_fingerprints.values():
        if (
            not isinstance(fingerprint, dict)
            or set(fingerprint) != {"algorithm", "digest"}
            or fingerprint.get("algorithm") != "sha256"
            or not _is_sha256_digest(fingerprint.get("digest"))
        ):
            raise ValueError(
                "core10 activation packet governance fingerprint is invalid"
            )

    if any(
        item.get("official_use_allowed") is not False
        or item.get("write_allowed") is not False
        or item.get("decision_options") != list(DECISION_OPTIONS)
        for item in items
    ):
        raise ValueError("core10 activation item governance contract is invalid")


def _append_artifact_markdown_section(
    lines: list[str],
    title: str,
    value: Any,
) -> None:
    lines.extend(["", f"### {title}", ""])
    lines.extend(_artifact_markdown_lines(_safe_artifact_value(value)))


def render_core10_activation_packet_markdown(
    packet: dict[str, Any],
) -> str:
    packet_id, packet_fingerprint, items = _core10_artifact_packet_items(packet)
    lines = [
        "# HXY Core-10 创始人决策包",
        "",
        "> 本决策包仅供创始人审阅，不写库、不发布，也不构成正式权威。",
        "",
        f"- 决策包编号: `{_safe_artifact_text(packet_id)}`",
        f"- 完整指纹: `{_safe_artifact_text(packet_fingerprint)}`",
        "- 状态: 待创始人决策",
    ]
    for index, item in enumerate(items, start=1):
        item_title = _ARTIFACT_ITEM_TITLES[item["item_key"]]
        lines.extend(["", f"## {index}. {item_title}"])
        _append_artifact_markdown_section(
            lines,
            "当前状态",
            item.get("current_state"),
        )
        _append_artifact_markdown_section(
            lines,
            "拟议方案",
            item.get("proposed_authority"),
        )
        _append_artifact_markdown_section(
            lines,
            "需要原因",
            item.get("why_needed"),
        )
        _append_artifact_markdown_section(
            lines,
            "风险",
            {
                "批准风险": item.get("risk_if_approved"),
                "拒绝风险": item.get("risk_if_rejected"),
            },
        )
        _append_artifact_markdown_section(
            lines,
            "证据",
            item.get("source_evidence"),
        )
        _append_artifact_markdown_section(
            lines,
            "阻塞项",
            item.get("blockers"),
        )
    return "\n".join(lines).rstrip() + "\n"


def build_core10_activation_decision_sample(
    packet: dict[str, Any],
) -> dict[str, Any]:
    packet_id, packet_fingerprint, items = _core10_artifact_packet_items(packet)
    decisions = []
    for item in items:
        decisions.append(
            {
                "item_key": item["item_key"],
                "item_fingerprint": item["item_fingerprint"],
                "action": "request_correction",
                "reason": "Replace this placeholder with the founder's decision reason.",
            }
        )
    return {
        "actor": {"id": "founder-placeholder", "role": "founder"},
        "packet_id": packet_id,
        "packet_fingerprint": packet_fingerprint,
        "decisions": decisions,
        "preview_only": True,
        "write_to_database": False,
        "publish_allowed": False,
        "official_use_allowed": False,
    }


def _core10_artifact_paths(target: Path) -> dict[str, Path]:
    return {
        key: target / filename
        for key, filename in _ARTIFACT_FILENAMES.items()
    }


def _existing_core10_artifact_paths(
    target: Path,
    *,
    packet_id: str,
    packet_fingerprint: str,
) -> dict[str, Path]:
    conflict = ValueError("core10 activation artifact target conflict")
    try:
        if target.is_symlink() or not target.is_dir():
            raise conflict
        if stat.S_IMODE(target.stat().st_mode) != 0o700:
            raise conflict
        paths = _core10_artifact_paths(target)
        entries = list(target.iterdir())
        if {entry.name for entry in entries} != set(_ARTIFACT_FILENAMES.values()):
            raise conflict
        if any(path.is_symlink() or not path.is_file() for path in paths.values()):
            raise conflict
        if any(path.stat().st_size == 0 for path in paths.values()):
            raise conflict
        if any(
            stat.S_IMODE(path.stat().st_mode) != 0o600
            for path in paths.values()
        ):
            raise conflict

        packet_payload = json.loads(
            paths["packet_json"].read_text(encoding="utf-8")
        )
        decision_payload = json.loads(
            paths["decision_sample"].read_text(encoding="utf-8")
        )
        markdown = paths["packet_markdown"].read_text(encoding="utf-8")
        if not isinstance(packet_payload, dict) or not isinstance(
            decision_payload,
            dict,
        ):
            raise conflict
        try:
            _verify_core10_activation_packet_governance(packet_payload)
            _verify_core10_activation_packet_fingerprints(packet_payload)
        except (KeyError, TypeError, ValueError) as error:
            raise conflict from error
        if packet_payload.get("packet_id") != packet_id:
            raise conflict
        if packet_payload.get("packet_fingerprint") != packet_fingerprint:
            raise conflict
        if markdown != render_core10_activation_packet_markdown(packet_payload):
            raise conflict
        if decision_payload != build_core10_activation_decision_sample(
            packet_payload
        ):
            raise conflict
        return paths
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise conflict from error


def _write_synced_artifact(path: Path, content: str) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        os.chmod(path, 0o600)
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def write_core10_activation_artifacts(
    private_root: Path,
    packet: dict[str, Any],
) -> dict[str, Path]:
    _verify_core10_activation_packet_governance(packet)
    _verify_core10_activation_packet_fingerprints(packet)
    packet_id, packet_fingerprint, _items = _core10_artifact_packet_items(packet)
    resolved_root = Path(private_root).resolve()
    resolved_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    target = resolved_root / f"core10-activation-{packet_fingerprint[:12]}"

    if os.path.lexists(target):
        return _existing_core10_artifact_paths(
            target,
            packet_id=packet_id,
            packet_fingerprint=packet_fingerprint,
        )

    packet_json = json.dumps(
        packet,
        allow_nan=False,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"
    stored_packet = json.loads(packet_json)
    packet_markdown = render_core10_activation_packet_markdown(stored_packet)
    decision_json = json.dumps(
        build_core10_activation_decision_sample(stored_packet),
        allow_nan=False,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"
    contents = {
        "packet.json": packet_json,
        "packet.md": packet_markdown,
        "decisions.sample.json": decision_json,
    }

    temporary = Path(
        tempfile.mkdtemp(
            prefix=f".{target.name}.tmp-",
            dir=resolved_root,
        )
    )
    try:
        for filename, content in contents.items():
            _write_synced_artifact(temporary / filename, content)
        _fsync_directory(temporary)
        if os.path.lexists(target):
            return _existing_core10_artifact_paths(
                target,
                packet_id=packet_id,
                packet_fingerprint=packet_fingerprint,
            )
        os.replace(temporary, target)
        _fsync_directory(resolved_root)
        return _core10_artifact_paths(target)
    finally:
        if os.path.lexists(temporary):
            shutil.rmtree(temporary)


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
    upstream_payloads = {
        "report": report,
        "constitution_state": constitution_state,
        "constitution_draft": constitution_draft,
        "product_sources": product_sources,
        "operations_sources": operations_sources,
        "reception_draft": reception_draft,
        "existing_answer_cards": existing_answer_cards,
    }
    upstream_fingerprints = {
        key: json_fingerprint(upstream_payloads[key])
        for key in _UPSTREAM_INPUT_KEYS
    }
    approved_card_state = _approved_card_state(
        reception_draft,
        existing_answer_cards,
    )
    resolved_source_ids = _resolved_source_ids(
        product_sources,
        operations_sources,
    )

    item_values = {
        "brand_constitution": {
            "current_state": _bounded_constitution_state(constitution_state),
            "proposed_authority": {
                "authority": "official_internal",
                "draft": _bounded_constitution_draft(constitution_draft),
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
    for item_key, mapped_cases in ITEM_CASES.items():
        affected_cases = [
            case_id for case_id in mapped_cases if case_id in failed_cases
        ]
        blockers: list[str] = []
        write_intents: list[dict[str, Any]] = []
        if affected_cases and item_key == "brand_constitution":
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
        elif affected_cases and item_key == "product_system_sources":
            blockers = _source_blockers(product_sources)
            if not blockers:
                write_intents = _classification_intents(
                    product_sources,
                    reason="Selected source supports the Core-10 product-system case.",
                )
        elif affected_cases and item_key == "first_store_operations_sources":
            blockers = _source_blockers(operations_sources)
            if not blockers:
                write_intents = _classification_intents(
                    operations_sources,
                    reason="Selected source supports the Core-10 first-store cases.",
                )
        elif affected_cases and item_key == "reception_standard_answer_card":
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
            "item_key": item_key,
            **item_values[item_key],
            "affected_core10_cases": affected_cases,
            "exact_write_intents": write_intents,
            "blockers": blockers,
            "decision_options": list(DECISION_OPTIONS),
            "official_use_allowed": False,
            "write_allowed": False,
        }
        item["item_fingerprint"] = _item_fingerprint(
            item,
            upstream_fingerprints=upstream_fingerprints,
        )
        items.append(item)

    packet = {
        "version": PACKET_VERSION,
        "generated_at": timestamp,
        "item_count": len(ITEM_CASES),
        "preview_only": True,
        "write_to_database": False,
        "publish_allowed": False,
        "official_use_allowed": False,
        "requires_founder_decision": True,
        "authority_rule": AUTHORITY_RULE,
        "upstream_fingerprints": upstream_fingerprints,
        "items": items,
    }
    packet_fingerprint = _packet_fingerprint_digest(packet)
    packet["packet_fingerprint"] = packet_fingerprint
    packet["packet_id"] = f"core10-activation:{packet_fingerprint[:12]}"
    packet["artifact_fingerprint"] = _artifact_fingerprint_digest(packet)
    return _json_safe(packet)


def validate_core10_activation_decisions(
    packet: Any,
    decisions: Any,
) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []

    def add_error(
        code: str,
        field: str,
        *,
        item_key: str | None = None,
        index: int | None = None,
    ) -> None:
        error: dict[str, Any] = {"code": code, "field": field}
        if item_key is not None:
            error["item_key"] = item_key
        if index is not None:
            error["index"] = index
        errors.append(error)

    packet_record = packet if isinstance(packet, dict) else {}
    request = decisions if isinstance(decisions, dict) else {}
    if not isinstance(packet, dict):
        add_error("invalid_packet", "packet")
    if not isinstance(decisions, dict):
        add_error("invalid_decision_payload", "decisions")

    packet_id = packet_record.get("packet_id")
    packet_fingerprint = packet_record.get("packet_fingerprint")
    packet_fingerprint_is_valid = _is_sha256_digest(packet_fingerprint)
    if not packet_fingerprint_is_valid:
        add_error("invalid_packet_fingerprint", "packet.packet_fingerprint")
    try:
        recomputed_packet_fingerprint = _packet_fingerprint_digest(
            packet_record
        )
    except (KeyError, TypeError, ValueError):
        recomputed_packet_fingerprint = None
        add_error("invalid_packet_identity", "packet")
    if packet_fingerprint != recomputed_packet_fingerprint:
        add_error(
            "packet_fingerprint_mismatch",
            "packet.packet_fingerprint",
        )

    expected_packet_id = (
        f"core10-activation:{packet_fingerprint[:12]}"
        if packet_fingerprint_is_valid
        else None
    )
    if packet_id != expected_packet_id:
        add_error("invalid_packet_id", "packet.packet_id")
    if request.get("packet_id") != packet_id:
        add_error("packet_id_mismatch", "packet_id")
    submitted_packet_fingerprint = request.get("packet_fingerprint")
    if not _is_sha256_digest(submitted_packet_fingerprint):
        add_error(
            "invalid_submitted_packet_fingerprint",
            "packet_fingerprint",
        )
    if submitted_packet_fingerprint != packet_fingerprint:
        add_error("packet_fingerprint_mismatch", "packet_fingerprint")

    actor = request.get("actor")
    actor_record = actor if isinstance(actor, dict) else {}
    if not _is_nonblank_string(actor_record.get("id")):
        add_error("invalid_actor_id", "actor.id")
    if actor_record.get("role") != "founder":
        add_error("invalid_actor_role", "actor.role")

    packet_items = packet_record.get("items")
    packet_item_records = packet_items if isinstance(packet_items, list) else []
    upstream_fingerprints = packet_record.get("upstream_fingerprints")
    upstream_fingerprint_records = (
        upstream_fingerprints
        if isinstance(upstream_fingerprints, dict)
        else {}
    )
    expected_items: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(packet_item_records):
        if not isinstance(item, dict):
            continue
        item_key = item.get("item_key")
        if not isinstance(item_key, str) or item_key not in ITEM_CASES:
            continue
        expected_items[item_key] = item
        item_fingerprint = item.get("item_fingerprint")
        if not _is_sha256_digest(item_fingerprint):
            add_error(
                "invalid_item_fingerprint",
                f"packet.items[{index}].item_fingerprint",
                item_key=item_key,
                index=index,
            )
        try:
            recomputed_item_fingerprint = _item_fingerprint(
                item,
                upstream_fingerprints=upstream_fingerprint_records,
            )
        except (KeyError, TypeError, ValueError):
            recomputed_item_fingerprint = None
            add_error(
                "invalid_item_identity",
                f"packet.items[{index}]",
                item_key=item_key,
                index=index,
            )
        if item_fingerprint != recomputed_item_fingerprint:
            add_error(
                "item_fingerprint_mismatch",
                f"packet.items[{index}].item_fingerprint",
                item_key=item_key,
                index=index,
            )
    if (
        not isinstance(packet_items, list)
        or len(packet_item_records) != len(ITEM_CASES)
        or set(expected_items) != set(ITEM_CASES)
    ):
        add_error("invalid_packet_items", "packet.items")

    submitted = request.get("decisions")
    if not isinstance(submitted, list):
        add_error("invalid_decisions", "decisions")
        submitted_records: list[Any] = []
    else:
        submitted_records = submitted

    seen: dict[str, int] = {}
    for index, decision in enumerate(submitted_records):
        field = f"decisions[{index}]"
        if not isinstance(decision, dict):
            add_error("invalid_decision", field, index=index)
            continue

        action = decision.get("action")
        if action not in DECISION_OPTIONS:
            add_error("invalid_action", f"{field}.action", index=index)
        if not _is_nonblank_string(decision.get("reason")):
            add_error("missing_reason", f"{field}.reason", index=index)

        item_key = decision.get("item_key")
        if not isinstance(item_key, str) or item_key not in ITEM_CASES:
            add_error("unknown_item_key", f"{field}.item_key", index=index)
            continue

        seen[item_key] = seen.get(item_key, 0) + 1
        if seen[item_key] > 1:
            add_error(
                "duplicate_item_key",
                f"{field}.item_key",
                item_key=item_key,
                index=index,
            )

        expected_item = expected_items.get(item_key)
        if expected_item is None:
            add_error(
                "item_not_in_packet",
                f"{field}.item_key",
                item_key=item_key,
                index=index,
            )
            continue
        submitted_item_fingerprint = decision.get("item_fingerprint")
        if not _is_sha256_digest(submitted_item_fingerprint):
            add_error(
                "invalid_submitted_item_fingerprint",
                f"{field}.item_fingerprint",
                item_key=item_key,
                index=index,
            )
        if submitted_item_fingerprint != expected_item.get("item_fingerprint"):
            add_error(
                "item_fingerprint_mismatch",
                f"{field}.item_fingerprint",
                item_key=item_key,
                index=index,
            )
        if action == "approve" and bool(expected_item.get("blockers")):
            add_error(
                "blocked_item_cannot_be_approved",
                f"{field}.action",
                item_key=item_key,
                index=index,
            )

    for item_key in ITEM_CASES:
        if seen.get(item_key, 0) == 0:
            add_error(
                "missing_item_decision",
                "decisions",
                item_key=item_key,
            )

    errors.sort(
        key=lambda error: (
            str(error.get("field", "")),
            str(error.get("code", "")),
            str(error.get("item_key", "")),
            int(error.get("index", -1)),
        )
    )
    return {
        "valid": not errors,
        "errors": errors,
        "preview_only": True,
        "write_to_database": False,
        "publish_allowed": False,
        "official_use_allowed": False,
    }
