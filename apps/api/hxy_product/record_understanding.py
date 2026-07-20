from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .issue_understanding import (
    AttachmentAdapter,
    AttachmentUnderstandingError,
    _safe_json_object,
    _understand_attachments,
    default_attachment_adapter,
)
from .outbox_repository import OutboxLeaseLost, lock_outbox_execution_fence
from .outbox_worker import OutboxHandlerError

try:
    import psycopg
    from psycopg.rows import dict_row
except Exception:  # pragma: no cover - deployment dependency may be installed later
    psycopg = None
    dict_row = None


PROMPT_VERSION = "organization-record-understanding.v1"
RecordType = Literal[
    "progress_update",
    "decision",
    "risk",
    "meeting_record",
    "reference",
    "mixed",
    "other",
]
RiskSeverity = Literal["low", "medium", "high", "critical"]


class StrictUnderstandingModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class RecordEvidenceDraft(StrictUnderstandingModel):
    source_record_id: UUID
    source_asset_id: UUID | None = None
    quote: str = Field(min_length=1, max_length=1000)
    locator: str | None = Field(default=None, min_length=1, max_length=300)

    @field_validator("quote", "locator")
    @classmethod
    def remove_control_nulls(cls, value: str | None) -> str | None:
        return value.replace("\x00", " ").strip() if value is not None else None


class RecordStatementDraft(StrictUnderstandingModel):
    statement: str = Field(min_length=1, max_length=1000)
    evidence: list[RecordEvidenceDraft] = Field(min_length=1, max_length=5)

    @field_validator("statement")
    @classmethod
    def remove_statement_control_nulls(cls, value: str) -> str:
        return value.replace("\x00", " ").strip()


class RecordRiskDraft(RecordStatementDraft):
    severity: RiskSeverity


class OrganizationRecordUnderstandingDraft(StrictUnderstandingModel):
    summary: str = Field(max_length=2000)
    record_type: RecordType
    occurred_at: datetime | None
    facts: list[RecordStatementDraft] = Field(max_length=5)
    decisions: list[RecordStatementDraft] = Field(max_length=5)
    progress: list[RecordStatementDraft] = Field(max_length=5)
    risks: list[RecordRiskDraft] = Field(max_length=5)
    missing_information: list[str] = Field(max_length=5)
    confidence: float = Field(ge=0, le=1)

    @field_validator("summary")
    @classmethod
    def remove_summary_control_nulls(cls, value: str) -> str:
        return value.replace("\x00", " ").strip()

    @field_validator("occurred_at", mode="before")
    @classmethod
    def require_iso_datetime_or_null(cls, value: Any) -> Any:
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise ValueError("occurred_at must be an ISO datetime string or null")
        return value.strip()

    @field_validator("confidence", mode="before")
    @classmethod
    def require_numeric_confidence(cls, value: Any) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("confidence must be a JSON number")
        return float(value)

    @field_validator("missing_information")
    @classmethod
    def validate_missing_information(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            item = value.replace("\x00", " ").strip()
            if not item or len(item) > 1000:
                raise ValueError("missing information must contain 1 to 1000 characters")
            normalized.append(item)
        return normalized


class OrganizationRecordProposalRepository:
    def __init__(self, database_url: str):
        if not database_url:
            raise ValueError("database_url is required")
        if psycopg is None:
            raise RuntimeError("psycopg is not installed")
        self.database_url = database_url

    def connect(self):
        return psycopg.connect(self.database_url, row_factory=dict_row)

    def save_record_proposal(
        self,
        record: dict[str, Any],
        *,
        execution_fence: dict[str, Any],
    ) -> dict[str, Any]:
        if str(execution_fence.get("organization_id") or "") != str(
            record["organization_id"]
        ):
            raise OutboxLeaseLost("outbox fence organization does not match proposal")
        if str(record.get("status") or "") != "proposed":
            raise ValueError("organization record interpretation must remain proposed")
        payload = dict(record.get("payload") or {})
        if "official_knowledge" in payload:
            raise ValueError("organization record interpretation cannot approve knowledge")
        params = (
            record["organization_id"],
            record["source_envelope_id"],
            record["proposal_type"],
            json.dumps(payload, ensure_ascii=False),
            float(record["confidence"]),
            record["risk_level"],
            record["model_provider"],
            record["model_name"],
            record["prompt_version"],
            record["input_hash"],
            "proposed",
        )
        with self.connect() as connection:
            lock_outbox_execution_fence(connection, execution_fence)
            row = connection.execute(
                """
                INSERT INTO hxy_ai_proposals (
                  organization_id, source_envelope_id, target_type, proposal_type,
                  payload, confidence, risk_level, model_provider, model_name,
                  prompt_version, input_hash, status
                )
                VALUES (
                  %s::uuid, %s::uuid, 'content_draft', %s, %s::jsonb,
                  %s, %s, %s, %s, %s, %s, %s
                )
                ON CONFLICT (organization_id, source_envelope_id, proposal_type, input_hash)
                DO NOTHING
                RETURNING proposal_id::text, organization_id::text,
                          source_envelope_id::text, status, created_at
                """,
                params,
            ).fetchone()
            if row is None:
                row = connection.execute(
                    """
                    SELECT proposal_id::text, organization_id::text,
                           source_envelope_id::text, status, created_at
                    FROM hxy_ai_proposals
                    WHERE organization_id = %s::uuid
                      AND source_envelope_id = %s::uuid
                      AND proposal_type = %s
                      AND input_hash = %s
                    LIMIT 1
                    """,
                    (
                        record["organization_id"],
                        record["source_envelope_id"],
                        record["proposal_type"],
                        record["input_hash"],
                    ),
                ).fetchone()
        if row is None:  # pragma: no cover - database invariant
            raise RuntimeError("idempotent record proposal could not be loaded")
        return dict(row)


def _trusted_record_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    outbox = payload.get("_hxy_outbox")
    if not isinstance(outbox, Mapping):
        raise OutboxHandlerError(
            "outbox_scope_missing",
            "trusted outbox execution scope is missing",
            retryable=False,
        )
    organization_id = str(outbox.get("organization_id") or "").strip()
    aggregate_type = str(outbox.get("aggregate_type") or "").strip()
    aggregate_id = str(outbox.get("aggregate_id") or "").strip()
    payload_organization_id = str(payload.get("organization_id") or "").strip()
    payload_envelope_id = str(payload.get("envelope_id") or "").strip()
    if (
        not organization_id
        or aggregate_type != "inbound_envelope"
        or not aggregate_id
        or (payload_organization_id and payload_organization_id != organization_id)
        or (payload_envelope_id and payload_envelope_id != aggregate_id)
    ):
        raise OutboxHandlerError(
            "outbox_scope_mismatch",
            "outbox payload disagrees with its authoritative aggregate scope",
            retryable=False,
        )
    trusted = dict(payload)
    trusted["organization_id"] = organization_id
    trusted["envelope_id"] = aggregate_id
    return trusted


def _execution_fence(payload: Mapping[str, Any]) -> dict[str, Any]:
    outbox = payload.get("_hxy_outbox")
    if not isinstance(outbox, Mapping):
        raise OutboxHandlerError(
            "outbox_fence_missing",
            "trusted outbox execution fence is missing",
            retryable=False,
        )
    fence = {
        "organization_id": str(outbox.get("organization_id") or "").strip(),
        "outbox_message_id": str(outbox.get("outbox_message_id") or "").strip(),
        "worker_id": str(outbox.get("worker_id") or "").strip(),
        "attempt_number": int(outbox.get("attempt_number") or 0),
    }
    if not all(
        (
            fence["organization_id"],
            fence["outbox_message_id"],
            fence["worker_id"],
            fence["attempt_number"] > 0,
        )
    ):
        raise OutboxHandlerError(
            "outbox_fence_missing",
            "trusted outbox execution fence is incomplete",
            retryable=False,
        )
    return fence


def _assert_active_lease(payload: Mapping[str, Any]) -> None:
    outbox = payload.get("_hxy_outbox")
    if not isinstance(outbox, Mapping):
        return
    guard = outbox.get("assert_lease")
    if callable(guard):
        guard()


def _build_prompt(
    *,
    envelope_id: str,
    raw_text: str,
    attachments: list[dict[str, Any]],
) -> str:
    attachment_sections = [
        "\n".join(
            [
                f"source_asset_id: {item['source_asset_id']}",
                f"附件: {item['file_name']}",
                str(item["text"]),
            ]
        )
        for item in attachments
    ]
    return "\n".join(
        [
            (
                "你是荷小悦组织记录理解器，"
                "只提取可由当前记录直接证明的派生解释。"
            ),
            (
                "只生成 proposed 候选，不批准正式知识，"
                "不推断正式政策或品牌口径。"
            ),
            "严格返回单个 JSON 对象，不要 Markdown，不要解释，不要额外字段。",
            (
                "允许字段：summary, record_type, occurred_at, facts, decisions, "
                "progress, risks, missing_information, confidence。"
            ),
            (
                "每条事实、决策、进展和风险都必须有 evidence；"
                "无证据则省略；每类最多5项。"
            ),
            (
                "evidence.source_record_id 必须是当前记录；"
                "引用附件时填写 source_asset_id；quote 必须逐字来自相应原文。"
            ),
            "不编造比例、日期、责任人、价格、结果、正式政策或品牌结论。",
            "risk severity 只能是 low、medium、high、critical。",
            f"当前 source_record_id: {envelope_id}",
            f"用户原始文字：{raw_text[:20_000] or '无'}",
            "附件解析结果：",
            "\n\n".join(attachment_sections) if attachment_sections else "无",
        ]
    )


def _normalized_whitespace(value: str) -> str:
    return " ".join(value.replace("\x00", " ").split())


def _validate_evidence_integrity(
    proposal: dict[str, Any],
    *,
    envelope_id: str,
    raw_text: str,
    attachments: list[dict[str, Any]],
) -> None:
    attachment_text = {
        str(item.get("source_asset_id") or ""): _normalized_whitespace(
            str(item.get("text") or "")
        )
        for item in attachments
        if str(item.get("source_asset_id") or "")
    }
    normalized_raw = _normalized_whitespace(raw_text)
    for section in ("facts", "decisions", "progress", "risks"):
        for item in list(proposal.get(section) or []):
            for evidence in list(item.get("evidence") or []):
                if str(evidence.get("source_record_id") or "") != envelope_id:
                    raise ValueError("evidence references another record")
                source_asset_id = str(evidence.get("source_asset_id") or "")
                corpus = normalized_raw
                if source_asset_id:
                    if source_asset_id not in attachment_text:
                        raise ValueError("evidence references an unattached asset")
                    corpus = attachment_text[source_asset_id]
                quote = _normalized_whitespace(str(evidence.get("quote") or ""))
                if not quote or quote not in corpus:
                    raise ValueError("evidence quote is not present in its source")


def _highest_risk(risks: list[dict[str, Any]]) -> str:
    rank = {"low": 0, "medium": 1, "high": 2, "critical": 3}
    return max(
        (str(item.get("severity") or "low") for item in risks),
        key=lambda severity: rank.get(severity, 0),
        default="low",
    )


def build_record_understanding_handler(
    channel_repository: Any,
    proposal_repository: Any,
    model_router: Any,
    *,
    attachment_adapter: AttachmentAdapter | None = None,
) -> Callable[[dict[str, Any]], dict[str, Any]]:
    selected_attachment_adapter = attachment_adapter or default_attachment_adapter

    def handle(payload: dict[str, Any]) -> dict[str, Any]:
        trusted_payload = _trusted_record_payload(payload)
        execution_fence = _execution_fence(trusted_payload)
        organization_id = str(trusted_payload["organization_id"])
        envelope_id = str(trusted_payload["envelope_id"])
        context = channel_repository.load_record_context(trusted_payload)
        if context is None:
            raise OutboxHandlerError(
                "record_context_not_found",
                "scoped organization record context was not found",
                retryable=False,
            )
        if (
            str(context.get("organization_id") or "") != organization_id
            or str(context.get("envelope_id") or "") != envelope_id
        ):
            raise OutboxHandlerError(
                "record_context_scope_mismatch",
                "loaded record context crossed the outbox aggregate scope",
                retryable=False,
            )
        try:
            understood_attachments = _understand_attachments(
                list(context.get("attachments") or []),
                model_router=model_router,
                attachment_adapter=selected_attachment_adapter,
            )
        except AttachmentUnderstandingError as error:
            raise OutboxHandlerError(
                error.code,
                error.summary,
                retryable=error.retryable,
            ) from error

        raw_text = str(context.get("raw_text") or "")
        prompt = _build_prompt(
            envelope_id=envelope_id,
            raw_text=raw_text,
            attachments=understood_attachments,
        )
        try:
            generation = model_router.generate(
                "organization_record_understanding",
                prompt=prompt,
                metadata={
                    "prompt_version": PROMPT_VERSION,
                    "envelope_id": envelope_id,
                    "attachment_count": len(understood_attachments),
                },
            )
        except Exception as error:
            raise OutboxHandlerError(
                "model_call_failed",
                "organization record understanding model call failed",
                retryable=True,
            ) from error
        if not generation.get("used_model"):
            raise OutboxHandlerError(
                "model_unavailable",
                "organization record understanding model is temporarily unavailable",
                retryable=True,
            )
        parsed = _safe_json_object(generation.get("output"))
        if parsed is None:
            raise OutboxHandlerError(
                "invalid_record_json",
                "organization record model returned invalid JSON",
                retryable=True,
            )
        try:
            proposal = OrganizationRecordUnderstandingDraft.model_validate(
                parsed
            ).model_dump(mode="json", exclude_none=True)
        except ValidationError as error:
            raise OutboxHandlerError(
                "invalid_record_output",
                "organization record model returned an invalid interpretation",
                retryable=True,
            ) from error
        try:
            _validate_evidence_integrity(
                proposal,
                envelope_id=envelope_id,
                raw_text=raw_text,
                attachments=understood_attachments,
            )
        except ValueError as error:
            raise OutboxHandlerError(
                "invalid_record_evidence",
                "organization record evidence failed integrity validation",
                retryable=True,
            ) from error

        route = generation.get("route") or {}
        record = {
            "organization_id": organization_id,
            "source_envelope_id": envelope_id,
            "proposal_type": "organization_record_understanding",
            "payload": proposal,
            "confidence": proposal["confidence"],
            "risk_level": _highest_risk(list(proposal.get("risks") or [])),
            "model_provider": str(route.get("provider") or "unknown")[:100],
            "model_name": str(route.get("selected_model") or "unknown")[:160],
            "prompt_version": PROMPT_VERSION,
            "input_hash": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
            "status": "proposed",
        }
        _assert_active_lease(trusted_payload)
        try:
            saved = proposal_repository.save_record_proposal(
                record,
                execution_fence=execution_fence,
            )
        except OutboxLeaseLost:
            raise
        except Exception as error:
            raise OutboxHandlerError(
                "proposal_persistence_failed",
                "organization record interpretation could not be persisted",
                retryable=True,
            ) from error
        _assert_active_lease(trusted_payload)
        try:
            channel_repository.mark_envelope_processed(
                organization_id,
                envelope_id,
                execution_fence=execution_fence,
            )
        except OutboxLeaseLost:
            raise
        except Exception as error:
            raise OutboxHandlerError(
                "envelope_completion_failed",
                "organization record envelope could not be marked processed",
                retryable=True,
            ) from error
        return {"status": "processed", "proposal_id": str(saved["proposal_id"])}

    return handle
