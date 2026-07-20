from __future__ import annotations

import json
import re
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

try:
    import psycopg
    from psycopg.rows import dict_row
except Exception:  # pragma: no cover - deployment dependency may be installed later
    psycopg = None
    dict_row = None


class RecordAccessDenied(PermissionError):
    pass


_STATUS_MAP = {
    "received": "received",
    "queued": "processing",
    "processed": "ready",
    "needs_attention": "needs_attention",
    "rejected": "needs_attention",
}

_ASSET_STATUS_MAP = {
    "received": "processing",
    "understood": "ready",
    "understanding_failed": "needs_attention",
}

_DOCUMENT_MEDIA_TYPES = {
    "application/msword",
    "application/pdf",
    "application/rtf",
    "application/vnd.ms-excel",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/csv",
    "text/markdown",
    "text/plain",
}

_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return []
        return parsed if isinstance(parsed, list) else []
    return []


def _bounded_text(value: Any, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()[:limit]


def _uuid_text(value: Any) -> str | None:
    try:
        return str(UUID(str(value)))
    except (TypeError, ValueError, AttributeError):
        return None


def _public_asset(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    asset_id = _uuid_text(value.get("id") or value.get("material_id"))
    file_name = _bounded_text(
        value.get("file_name") or value.get("original_file_name"),
        180,
    )
    media_type = _bounded_text(value.get("media_type"), 160)
    size_bytes = value.get("size_bytes")
    if (
        asset_id is None
        or not file_name
        or not media_type
        or isinstance(size_bytes, bool)
        or not isinstance(size_bytes, int)
        or size_bytes < 0
    ):
        return None
    return {
        "id": asset_id,
        "file_name": file_name,
        "media_type": media_type,
        "size_bytes": size_bytes,
        "status": _ASSET_STATUS_MAP.get(
            str(value.get("status") or ""),
            "needs_attention",
        ),
    }


def _asset_source_type(asset: dict[str, Any]) -> str:
    media_type = asset["media_type"].lower()
    if media_type.startswith("image/"):
        return "image"
    if media_type.startswith("audio/"):
        return "audio"
    if media_type.startswith("video/"):
        return "video"
    if media_type in _DOCUMENT_MEDIA_TYPES or media_type.startswith("text/"):
        return "document"
    return "file"


def _public_evidence(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    source_record_id = _uuid_text(value.get("source_record_id"))
    quote = _bounded_text(value.get("quote"), 1000)
    if source_record_id is None or not quote:
        return None
    evidence: dict[str, Any] = {
        "source_record_id": source_record_id,
        "quote": quote,
    }
    source_asset_id = _uuid_text(value.get("source_asset_id"))
    if source_asset_id is not None:
        evidence["source_asset_id"] = source_asset_id
    locator = _bounded_text(value.get("locator"), 300)
    if locator:
        evidence["locator"] = locator
    return evidence


def _public_interpretation_items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    items: list[dict[str, Any]] = []
    for candidate in value[:100]:
        if isinstance(candidate, str):
            statement = _bounded_text(candidate, 1000)
            raw_evidence: Any = []
        elif isinstance(candidate, dict):
            statement = _bounded_text(candidate.get("statement"), 1000)
            raw_evidence = candidate.get("evidence")
        else:
            continue
        if not statement:
            continue
        evidence = [
            normalized
            for entry in (_json_list(raw_evidence)[:50])
            if (normalized := _public_evidence(entry)) is not None
        ]
        items.append({"statement": statement, "evidence": evidence})
    return items


def _confidence(value: Any, fallback: Any = None) -> float:
    for candidate in (value, fallback):
        if isinstance(candidate, bool):
            continue
        if isinstance(candidate, (int, float, Decimal)):
            numeric = float(candidate)
            if 0 <= numeric <= 1:
                return numeric
    return 0.0


def _occurred_at(row: dict[str, Any], payload: dict[str, Any]) -> datetime | None:
    value = row.get("occurred_at") or payload.get("occurred_at")
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _public_interpretation(row: dict[str, Any]) -> dict[str, Any] | None:
    raw_payload = row.get("interpretation_payload")
    if raw_payload is None:
        return None
    payload = _json_object(raw_payload)
    missing_information = [
        text
        for item in (_json_list(payload.get("missing_information"))[:100])
        if (text := _bounded_text(item, 1000))
    ]
    version = _bounded_text(
        payload.get("version") or row.get("interpretation_version"),
        100,
    ) or "unknown"
    return {
        "version": version,
        "summary": _bounded_text(payload.get("summary"), 2000),
        "facts": _public_interpretation_items(payload.get("facts")),
        "decisions": _public_interpretation_items(payload.get("decisions")),
        "progress": _public_interpretation_items(payload.get("progress")),
        "risks": _public_interpretation_items(payload.get("risks")),
        "missing_information": missing_information,
        "confidence": _confidence(
            row.get("interpretation_confidence"),
            payload.get("confidence"),
        ),
        "official_knowledge": False,
    }


def public_record(row: dict[str, Any]) -> dict[str, Any]:
    raw_text = (
        row.get("raw_text")[:20_000]
        if isinstance(row.get("raw_text"), str)
        else ""
    )
    assets = [
        normalized
        for candidate in _json_list(row.get("assets"))[:100]
        if (normalized := _public_asset(candidate)) is not None
    ]
    source_types: list[str] = []
    if raw_text.strip():
        source_types.append("text")
    raw_payload = _json_object(row.get("raw_payload"))
    if _URL_RE.search(raw_text) or isinstance(raw_payload.get("url"), str):
        source_types.append("link")
    for asset in assets:
        source_type = _asset_source_type(asset)
        if source_type not in source_types:
            source_types.append(source_type)

    preview = " ".join(raw_text.split())[:240]
    if not preview and assets:
        preview = "、".join(asset["file_name"] for asset in assets)[:240]

    submitted_by = _bounded_text(row.get("submitted_by"), 160)
    if not submitted_by:
        submitted_by = str(row.get("sender_assignment_id") or "")[:160]

    return {
        "id": str(row.get("record_id") or row.get("envelope_id") or ""),
        "source_types": source_types,
        "preview": preview,
        "submitted_by": submitted_by,
        "store_id": str(row["store_id"]) if row.get("store_id") is not None else None,
        "captured_at": row.get("captured_at") or row.get("received_at"),
        "occurred_at": _occurred_at(row, raw_payload),
        "processing_status": _STATUS_MAP.get(
            str(row.get("status") or ""),
            "needs_attention",
        ),
        "original": {"text": raw_text, "assets": assets},
        "interpretation": _public_interpretation(row),
    }


_RECORD_SELECT = """
    SELECT envelope.envelope_id::text AS record_id,
           envelope.channel,
           envelope.raw_text,
           envelope.raw_payload,
           envelope.sender_assignment_id::text,
           submitter_account.display_name AS submitted_by,
           envelope.store_id,
           envelope.status,
           envelope.received_at AS captured_at,
           proposal.payload AS interpretation_payload,
           proposal.prompt_version AS interpretation_version,
           proposal.confidence AS interpretation_confidence,
           COALESCE(attached.assets, '[]'::jsonb) AS assets
    FROM hxy_inbound_envelopes AS envelope
    LEFT JOIN hxy_role_assignments AS submitter_assignment
      ON submitter_assignment.organization_id = envelope.organization_id
     AND submitter_assignment.assignment_id = envelope.sender_assignment_id
    LEFT JOIN staff_accounts AS submitter_account
      ON submitter_account.id = submitter_assignment.account_id
    LEFT JOIN LATERAL (
      SELECT current_proposal.payload,
             current_proposal.prompt_version,
             current_proposal.confidence
      FROM hxy_ai_proposals AS current_proposal
      WHERE current_proposal.organization_id = envelope.organization_id
        AND current_proposal.source_envelope_id = envelope.envelope_id
        AND current_proposal.proposal_type = 'organization_record_understanding'
      ORDER BY current_proposal.created_at DESC,
               current_proposal.proposal_id DESC
      LIMIT 1
    ) AS proposal ON TRUE
    LEFT JOIN LATERAL (
      SELECT COALESCE(
               jsonb_agg(
                 jsonb_build_object(
                   'id', material.material_id::text,
                   'file_name', material.original_file_name,
                   'media_type', material.media_type,
                   'size_bytes', material.size_bytes,
                   'status', material.status
                 )
                 ORDER BY material.created_at, material.material_id
               ),
               '[]'::jsonb
             ) AS assets
      FROM hxy_asset_bindings AS binding
      JOIN hxy_product_materials AS material
        ON material.organization_id = binding.organization_id
       AND material.material_id = binding.source_id
      WHERE binding.organization_id = envelope.organization_id
        AND binding.source_type = 'source_asset'
        AND binding.target_type = 'inbound_envelope'
        AND binding.target_id = envelope.envelope_id
        AND binding.relation_type = 'attached_to'
        AND material.status <> 'archived'
    ) AS attached ON TRUE
"""


class RecordRepository:
    def __init__(self, database_url: str):
        if not database_url:
            raise ValueError("database_url is required")
        if psycopg is None:
            raise RuntimeError("psycopg is not installed")
        self.database_url = database_url

    def connect(self):
        return psycopg.connect(self.database_url, row_factory=dict_row)

    @staticmethod
    def _read_scope(
        role: str,
        store_id: str | None,
        assignment_id: str,
    ) -> tuple[str, tuple[Any, ...]]:
        if role in {"founder", "hq_operations"}:
            return "", ()
        if role == "store_manager" and store_id:
            return " AND envelope.store_id = %s", (store_id,)
        if role == "store_employee" and assignment_id:
            return (
                " AND envelope.sender_assignment_id = %s::uuid",
                (assignment_id,),
            )
        raise RecordAccessDenied("role cannot read organization records")

    def list_records(
        self,
        *,
        organization_id: str,
        assignment_id: str,
        role: str,
        store_id: str | None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        scope_sql, scope_params = self._read_scope(role, store_id, assignment_id)
        sql = (
            _RECORD_SELECT
            + " WHERE envelope.organization_id = %s::uuid"
            + " AND envelope.intent_hint = 'organization_record'"
            + scope_sql
            + " ORDER BY envelope.received_at DESC, envelope.envelope_id DESC LIMIT %s"
        )
        params = (
            organization_id,
            *scope_params,
            max(1, min(int(limit), 100)),
        )
        with self.connect() as connection:
            rows = connection.execute(sql, params).fetchall()
        return [public_record(dict(row)) for row in rows]

    def get_record(
        self,
        *,
        organization_id: str,
        record_id: str,
        assignment_id: str,
        role: str,
        store_id: str | None,
    ) -> dict[str, Any] | None:
        scope_sql, scope_params = self._read_scope(role, store_id, assignment_id)
        sql = (
            _RECORD_SELECT
            + " WHERE envelope.organization_id = %s::uuid"
            + " AND envelope.envelope_id = %s::uuid"
            + " AND envelope.intent_hint = 'organization_record'"
            + scope_sql
            + " LIMIT 1"
        )
        with self.connect() as connection:
            row = connection.execute(
                sql,
                (organization_id, record_id, *scope_params),
            ).fetchone()
        return public_record(dict(row)) if row is not None else None
