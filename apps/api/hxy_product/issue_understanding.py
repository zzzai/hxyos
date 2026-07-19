from __future__ import annotations

import base64
import hashlib
import json
import os
from collections.abc import Callable, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    ValidationError,
    field_validator,
)

from hxy_knowledge.image_adapter import IMAGE_SUFFIXES, ImageAdapterError, recognize_image

from .material_parser import MaterialParseError, parse_material
from .operating_policy import (
    CRITICAL_RISK_MARKERS,
    HIGH_RISK_MARKERS,
    PolicyDecision,
    evaluate_issue_proposal,
)
from .outbox_repository import OutboxLeaseLost, lock_outbox_execution_fence
from .outbox_worker import OutboxHandlerError

try:
    import psycopg
    from psycopg.rows import dict_row
except Exception:  # pragma: no cover - deployment dependency may be installed later
    psycopg = None
    dict_row = None


PROMPT_VERSION = "issue-understanding.v1"
_MAX_ATTACHMENT_TEXT = 12_000
_MAX_TOTAL_ATTACHMENT_TEXT = 24_000
_MAX_AUDIO_BYTES = 20 * 1024 * 1024
_AUDIO_SUFFIXES = frozenset({".aac", ".flac", ".m4a", ".mp3", ".ogg", ".wav"})
_DETERMINISTIC_RISK_KEYWORDS: dict[str, tuple[str, ...]] = {
    "person_injury": (
        "人员受伤",
        "有人受伤",
        "摔倒受伤",
        "摔伤",
        "流血",
        "骨折",
        "烫伤",
        "砸伤",
        "割伤",
    ),
    "safety": (
        "安全事故",
        "施工安全",
        "火灾",
        "着火",
        "漏电",
        "触电",
        "燃气泄漏",
    ),
    "permit": ("无证经营", "许可证", "证照缺失", "消防验收"),
    "compliance": ("监管处罚", "市场监管", "广告法", "违法"),
    "major_budget": ("重大超预算", "大额追加预算", "工程停工"),
    "major_complaint": ("重大投诉", "媒体曝光", "报警", "12315"),
    "medical_claim": ("保证疗效", "包治", "根治", "治愈", "治疗疾病"),
    "core_brand_conflict": ("品牌核心冲突", "违反品牌宪法"),
}


class AttachmentUnderstandingError(Exception):
    def __init__(self, code: str, summary: str, *, retryable: bool) -> None:
        super().__init__(summary)
        self.code = code.strip()[:100] or "attachment_understanding_failed"
        self.summary = " ".join(summary.split())[:2000] or "attachment understanding failed"
        self.retryable = retryable


class IssueProposalDraft(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    event_type: str = Field(default="", max_length=100)
    title: str = Field(default="", max_length=160)
    description: str = Field(default="", max_length=10_000)
    location: str = Field(default="", max_length=240)
    impact: str = Field(default="", max_length=2_000)
    acceptance_criteria: str = Field(default="", max_length=3_000)
    suggested_owner_assignment_id: UUID | None = None
    suggested_due_at: datetime | None = None
    risk_flags: list[str] = Field(default_factory=list, max_length=32)
    confidence: float = Field(ge=0, le=1)

    @field_validator("event_type", "title", "description", "location", "impact", "acceptance_criteria")
    @classmethod
    def remove_control_nulls(cls, value: str) -> str:
        return value.replace("\x00", " ").strip()

    @field_validator("risk_flags")
    @classmethod
    def normalize_risk_flags(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            marker = str(value).strip().lower()[:100]
            if marker and marker not in normalized:
                normalized.append(marker)
        return normalized


_OPTIONAL_MODEL_FIELD_ADAPTERS = {
    "suggested_owner_assignment_id": TypeAdapter(UUID),
    "suggested_due_at": TypeAdapter(datetime),
}


class IssueProposalRepository:
    def __init__(self, database_url: str):
        if not database_url:
            raise ValueError("database_url is required")
        if psycopg is None:
            raise RuntimeError("psycopg is not installed")
        self.database_url = database_url

    def connect(self):
        return psycopg.connect(self.database_url, row_factory=dict_row)

    def save_issue_proposal(
        self,
        record: dict[str, Any],
        *,
        execution_fence: dict[str, Any],
    ) -> dict[str, Any]:
        if str(execution_fence.get("organization_id") or "") != str(
            record["organization_id"]
        ):
            raise OutboxLeaseLost("outbox fence organization does not match proposal")
        decision = dict(record.get("decision") or {})
        status = str(record.get("status") or "proposed")
        if status not in {"proposed", "auto_accepted"}:
            raise ValueError("unsupported issue proposal status")
        policy_version = (
            str(decision.get("policy_version") or "").strip()[:100]
            if status == "auto_accepted"
            else None
        )
        if status == "auto_accepted" and not policy_version:
            raise ValueError("auto-accepted proposal requires a policy version")
        stored_payload = {
            **dict(record.get("payload") or {}),
            "_governance": {
                "decision_action": str(decision.get("action") or "")[:100],
                "deterministic_risk_flags": list(
                    decision.get("deterministic_risk_flags") or []
                )[:32],
            },
        }
        params = (
            record["organization_id"],
            record["source_envelope_id"],
            record["proposal_type"],
            json.dumps(stored_payload, ensure_ascii=False),
            float(record["confidence"]),
            record["risk_level"],
            record["model_provider"],
            record["model_name"],
            record["prompt_version"],
            record["input_hash"],
            status,
            status,
            policy_version,
        )
        with self.connect() as connection:
            lock_outbox_execution_fence(connection, execution_fence)
            row = connection.execute(
                """
                INSERT INTO hxy_ai_proposals (
                  organization_id,
                  source_envelope_id,
                  target_type,
                  proposal_type,
                  payload,
                  confidence,
                  risk_level,
                  model_provider,
                  model_name,
                  prompt_version,
                  input_hash,
                  status,
                  decided_at,
                  decision_policy_version
                )
                VALUES (
                  %s::uuid, %s::uuid, 'operating_event', %s, %s::jsonb,
                  %s, %s, %s, %s, %s, %s, %s,
                  CASE WHEN %s = 'auto_accepted' THEN NOW() ELSE NULL END,
                  %s
                )
                ON CONFLICT (organization_id, source_envelope_id, proposal_type, input_hash)
                DO NOTHING
                RETURNING proposal_id::text,
                          organization_id::text,
                          source_envelope_id::text,
                          status,
                          payload #>> '{_governance,decision_action}' AS decision_action,
                          decision_policy_version,
                          created_at
                """,
                params,
            ).fetchone()
            if row is None:
                row = connection.execute(
                    """
                    SELECT proposal_id::text,
                           organization_id::text,
                           source_envelope_id::text,
                           status,
                           payload #>> '{_governance,decision_action}' AS decision_action,
                           decision_policy_version,
                           created_at
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
            raise RuntimeError("idempotent issue proposal could not be loaded")
        return dict(row)


AttachmentAdapter = Callable[..., dict[str, Any]]
IssuePolicy = Callable[..., PolicyDecision]


def _safe_json_object(value: Any) -> dict[str, Any] | None:
    candidate = str(value or "").strip()
    if candidate.startswith("```"):
        lines = candidate.splitlines()
        if lines and lines[0].strip().lower() in {"```", "```json"}:
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        candidate = "\n".join(lines).strip()
    try:
        parsed = json.loads(candidate)
    except (TypeError, json.JSONDecodeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _normalize_optional_model_fields(payload: Mapping[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    for field_name, adapter in _OPTIONAL_MODEL_FIELD_ADAPTERS.items():
        value = normalized.get(field_name)
        if not isinstance(value, str):
            continue
        candidate = value.strip()
        if not candidate:
            normalized[field_name] = None
            continue
        try:
            adapter.validate_python(candidate)
        except ValidationError:
            normalized[field_name] = None
    return normalized


def _trusted_issue_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
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


def _assert_active_lease(payload: Mapping[str, Any]) -> None:
    outbox = payload.get("_hxy_outbox")
    if not isinstance(outbox, Mapping):
        return
    guard = outbox.get("assert_lease")
    if callable(guard):
        guard()


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


def _material_root() -> Path:
    project_root = Path(os.getenv("HXY_ROOT_DIR", Path(__file__).resolve().parents[3]))
    return (project_root / "data" / "product-materials").resolve()


def _safe_material_path(storage_key: str) -> Path | None:
    root = _material_root()
    candidate = (root / storage_key).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate


def _read_bounded_text(path: Path) -> str:
    if not path.is_file():
        return ""
    with path.open("r", encoding="utf-8", errors="replace") as source:
        return source.read(_MAX_ATTACHMENT_TEXT).replace("\x00", " ").strip()


def _transcribe_audio(path: Path, *, extension: str, model_router: Any) -> str:
    try:
        size = path.stat().st_size
        if size > _MAX_AUDIO_BYTES:
            raise AttachmentUnderstandingError(
                "audio_too_large",
                "audio attachment exceeds the transcription limit",
                retryable=False,
            )
        audio_data = base64.b64encode(path.read_bytes()).decode("ascii")
    except AttachmentUnderstandingError:
        raise
    except OSError as error:
        raise AttachmentUnderstandingError(
            "attachment_io_error",
            "audio attachment could not be read",
            retryable=True,
        ) from error
    try:
        generation = model_router.generate(
            "speech",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "请忠实转写这段门店语音，只返回转写文本，不做总结。",
                        },
                        {
                            "type": "input_audio",
                            "input_audio": {
                                "data": audio_data,
                                "format": extension.lstrip(".") or "wav",
                            },
                        },
                    ],
                }
            ],
            metadata={"purpose": "governed_issue_attachment_transcription"},
        )
    except Exception as error:
        raise AttachmentUnderstandingError(
            "audio_transcription_failed",
            "audio transcription model call failed",
            retryable=True,
        ) from error
    transcript = str(generation.get("output") or "").replace("\x00", " ").strip()
    if not generation.get("used_model") or not transcript:
        raise AttachmentUnderstandingError(
            "audio_transcript_unavailable",
            "audio attachment has no usable transcript",
            retryable=True,
        )
    return transcript[:_MAX_ATTACHMENT_TEXT]


def default_attachment_adapter(
    attachment: dict[str, Any],
    *,
    model_router: Any,
) -> dict[str, Any]:
    file_name = str(attachment.get("file_name") or "attachment")[:240]
    extension = str(attachment.get("extension") or Path(file_name).suffix).lower()
    media_type = str(attachment.get("media_type") or "application/octet-stream")[:160]
    normalized_key = str(attachment.get("normalized_storage_key") or "").strip()
    if normalized_key:
        normalized_path = _safe_material_path(normalized_key)
        if normalized_path is None:
            raise AttachmentUnderstandingError(
                "invalid_storage_path",
                "normalized attachment path is outside material storage",
                retryable=False,
            )
        try:
            normalized_text = _read_bounded_text(normalized_path)
        except OSError as error:
            raise AttachmentUnderstandingError(
                "attachment_io_error",
                "normalized attachment could not be read",
                retryable=True,
            ) from error
        if normalized_text:
            return {
                "source_asset_id": str(attachment.get("source_asset_id") or ""),
                "file_name": file_name,
                "media_type": media_type,
                "text": normalized_text,
                "adapter": "normalized_markdown",
            }

    storage_key = str(attachment.get("storage_key") or "").strip()
    source = _safe_material_path(storage_key)
    if source is None:
        raise AttachmentUnderstandingError(
            "invalid_storage_path",
            "attachment path is outside material storage",
            retryable=False,
        )
    if extension in _AUDIO_SUFFIXES or media_type.startswith("audio/"):
        return {
            "source_asset_id": str(attachment.get("source_asset_id") or ""),
            "file_name": file_name,
            "media_type": media_type,
            "text": _transcribe_audio(
                source,
                extension=extension,
                model_router=model_router,
            ),
            "adapter": "speech_model",
        }
    try:
        if extension in IMAGE_SUFFIXES or media_type.startswith("image/"):
            recognized = recognize_image(source, model_router=model_router)
            if recognized.quality.get("status") == "unusable":
                vision_status = str(recognized.metadata.get("vision_status") or "")
                raise AttachmentUnderstandingError(
                    "image_quality_gate_failed",
                    "image understanding produced no usable reference",
                    retryable=vision_status != "ok",
                )
            text = recognized.text_content
            adapter_name = recognized.parser_name
        else:
            parsed = parse_material(source)
            text = parsed.text_content
            adapter_name = parsed.parser_name
    except AttachmentUnderstandingError:
        raise
    except ImageAdapterError as error:
        raise AttachmentUnderstandingError(
            error.code,
            "image understanding did not complete",
            retryable=error.retryable,
        ) from error
    except MaterialParseError as error:
        raise AttachmentUnderstandingError(
            error.code,
            "attachment parsing did not complete",
            retryable=error.retryable,
        ) from error
    except OSError as error:
        raise AttachmentUnderstandingError(
            "attachment_io_error",
            "attachment could not be read",
            retryable=True,
        ) from error
    return {
        "source_asset_id": str(attachment.get("source_asset_id") or ""),
        "file_name": file_name,
        "media_type": media_type,
        "text": str(text or "")[:_MAX_ATTACHMENT_TEXT],
        "adapter": adapter_name,
    }


def _understand_attachments(
    attachments: list[dict[str, Any]],
    *,
    model_router: Any,
    attachment_adapter: AttachmentAdapter,
) -> list[dict[str, Any]]:
    understood: list[dict[str, Any]] = []
    remaining = _MAX_TOTAL_ATTACHMENT_TEXT
    for attachment in attachments[:16]:
        try:
            result = attachment_adapter(attachment, model_router=model_router)
        except AttachmentUnderstandingError:
            raise
        except Exception as error:
            raise AttachmentUnderstandingError(
                "attachment_adapter_error",
                "attachment adapter raised an unexpected error",
                retryable=True,
            ) from error
        text = str(result.get("text") or "").replace("\x00", " ").strip()
        if not text:
            raise AttachmentUnderstandingError(
                "empty_attachment_output",
                "attachment adapter produced no usable text",
                retryable=False,
            )
        bounded = text[: min(_MAX_ATTACHMENT_TEXT, remaining)]
        remaining -= len(bounded)
        understood.append(
            {
                "source_asset_id": str(result.get("source_asset_id") or ""),
                "file_name": str(result.get("file_name") or "attachment")[:240],
                "media_type": str(result.get("media_type") or "")[:160],
                "adapter": str(result.get("adapter") or "unknown")[:100],
                "text": bounded,
            }
        )
        if remaining <= 0:
            break
    return understood


def _build_prompt(
    *,
    raw_text: str,
    attachments: list[dict[str, Any]],
    event_types: list[str],
) -> str:
    risk_vocabulary = sorted(CRITICAL_RISK_MARKERS | HIGH_RISK_MARKERS)
    attachment_sections = []
    for attachment in attachments:
        attachment_sections.append(
            "\n".join(
                [
                    f"附件：{attachment['file_name']}",
                    f"解析器：{attachment['adapter']}",
                    str(attachment["text"]),
                ]
            )
        )
    return "\n".join(
        [
            "你是荷小悦门店经营问题提取器。你只生成候选提案，不批准、不关闭事件、不生成经营指标。",
            "严格返回一个 JSON 对象，不要 Markdown，不要解释。",
            "允许字段仅为：event_type, title, description, location, impact, acceptance_criteria, suggested_owner_assignment_id, suggested_due_at, risk_flags, confidence。",
            "不知道的事实使用空字符串或 null，禁止猜测组织、门店、人员、状态、指标和正式知识。",
            f"当前已发布经营问题类型：{json.dumps(event_types, ensure_ascii=False)}",
            f"风险词表：{json.dumps(risk_vocabulary, ensure_ascii=False)}",
            f"用户原始文字：{raw_text[:20_000] or '无'}",
            "附件解析结果：",
            "\n\n".join(attachment_sections) if attachment_sections else "无",
        ]
    )


def _deterministic_risk_flags(texts: list[str]) -> list[str]:
    corpus = "\n".join(str(value or "").lower() for value in texts)
    return [
        marker
        for marker, keywords in _DETERMINISTIC_RISK_KEYWORDS.items()
        if any(keyword.lower() in corpus for keyword in keywords)
    ]


def build_issue_understanding_handler(
    channel_repository: Any,
    operating_repository: Any,
    model_router: Any,
    policy: IssuePolicy,
    *,
    attachment_adapter: AttachmentAdapter | None = None,
) -> Callable[[dict[str, Any]], dict[str, Any]]:
    selected_attachment_adapter = attachment_adapter or default_attachment_adapter

    def handle(payload: dict[str, Any]) -> dict[str, Any]:
        trusted_payload = _trusted_issue_payload(payload)
        execution_fence = _execution_fence(trusted_payload)
        organization_id = str(trusted_payload["organization_id"])
        envelope_id = str(trusted_payload["envelope_id"])
        context = channel_repository.load_issue_context(trusted_payload)
        if context is None:
            raise OutboxHandlerError(
                "issue_context_not_found",
                "scoped inbound issue context was not found",
                retryable=False,
            )
        if (
            str(context["organization_id"]) != organization_id
            or str(context["envelope_id"]) != envelope_id
        ):
            raise OutboxHandlerError(
                "issue_context_scope_mismatch",
                "loaded issue context crossed the outbox aggregate scope",
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

        event_types = [
            str(value).strip()[:100]
            for value in list(context.get("published_event_types") or [])[:100]
            if str(value).strip()
        ]
        prompt = _build_prompt(
            raw_text=str(context.get("raw_text") or ""),
            attachments=understood_attachments,
            event_types=event_types,
        )
        try:
            generation = model_router.generate(
                "issue_understanding",
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
                "issue understanding model call failed",
                retryable=True,
            ) from error
        if not generation.get("used_model"):
            raise OutboxHandlerError(
                "model_unavailable",
                "issue understanding model is temporarily unavailable",
                retryable=True,
            )

        parsed = _safe_json_object(generation.get("output"))
        if parsed is None:
            raise OutboxHandlerError(
                "invalid_model_json",
                "issue understanding model returned invalid JSON",
                retryable=True,
            )
        try:
            proposal = IssueProposalDraft.model_validate(
                _normalize_optional_model_fields(parsed)
            ).model_dump(mode="json")
        except ValidationError as error:
            raise OutboxHandlerError(
                "invalid_model_output",
                "issue understanding model returned an invalid proposal",
                retryable=True,
            ) from error

        deterministic_risk_flags = _deterministic_risk_flags(
            [
                str(context.get("raw_text") or ""),
                *[str(item.get("text") or "") for item in understood_attachments],
            ]
        )
        policy_proposal = {
            **proposal,
            "risk_flags": list(
                dict.fromkeys(
                    [*list(proposal.get("risk_flags") or []), *deterministic_risk_flags]
                )
            ),
        }
        suggested_owner_assignment_id = str(
            proposal.get("suggested_owner_assignment_id") or ""
        ).strip()
        suggested_owner_is_active = False
        if suggested_owner_assignment_id:
            try:
                suggested_owner_is_active = channel_repository.issue_owner_is_active(
                    organization_id,
                    str(context["store_id"]),
                    suggested_owner_assignment_id,
                )
            except Exception as error:
                raise OutboxHandlerError(
                    "owner_scope_check_failed",
                    "suggested owner scope could not be verified",
                    retryable=True,
                ) from error
        decision = policy(
            proposal=policy_proposal,
            published_event_types=event_types,
            assignment_is_active=bool(context.get("assignment_is_active")),
            suggested_owner_is_active=suggested_owner_is_active,
        )
        route = generation.get("route") or {}
        input_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        record = {
            "organization_id": organization_id,
            "source_envelope_id": envelope_id,
            "proposal_type": "issue_understanding",
            "payload": proposal,
            "confidence": proposal["confidence"],
            "risk_level": decision.severity,
            "model_provider": str(route.get("provider") or "unknown")[:100],
            "model_name": str(route.get("selected_model") or "unknown")[:160],
            "prompt_version": PROMPT_VERSION,
            "input_hash": input_hash,
            "status": "auto_accepted" if decision.action == "auto_accept" else "proposed",
            "decision": {
                "action": decision.action,
                "severity": decision.severity,
                "missing_fields": list(decision.missing_fields),
                "policy_version": decision.policy_version,
                "deterministic_risk_flags": deterministic_risk_flags,
            },
        }
        _assert_active_lease(trusted_payload)
        try:
            saved = operating_repository.save_issue_proposal(
                record,
                execution_fence=execution_fence,
            )
        except OutboxLeaseLost:
            raise
        except Exception as error:
            raise OutboxHandlerError(
                "proposal_persistence_failed",
                "issue proposal could not be persisted",
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
                "issue envelope could not be marked processed",
                retryable=True,
            ) from error
        stored_decision = str(saved.get("decision_action") or "").strip()
        if not stored_decision:
            saved_decision = saved.get("decision")
            if isinstance(saved_decision, Mapping):
                stored_decision = str(saved_decision.get("action") or "").strip()
        if not stored_decision:
            stored_decision = (
                "auto_accept"
                if str(saved.get("status") or "") == "auto_accepted"
                else decision.action
            )
        return {
            "status": "processed",
            "proposal_id": str(saved["proposal_id"]),
            "decision": stored_decision,
        }

    return handle
