from __future__ import annotations

import inspect
import json
import os
import re
import base64
import hashlib
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal
from uuid import uuid4

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field

from hxy_knowledge import answer_service
from hxy_knowledge.answer_service import AnswerServiceHooks
from hxy_knowledge.answer_pipeline import build_answer_pipeline, enforce_intake_route_policy
from hxy_knowledge.brand_decision import review_brand_artifact, write_brand_review_record
from hxy_knowledge.brand_assets import brand_authority_cards, build_brand_asset_center
from hxy_knowledge.brand_constitution import BrandConstitutionAdapter
from hxy_knowledge.answer_engine import (
    answer_status_for,
    applicable_scenarios_for,
    build_result_card,
    compact_content,
    has_metadata_noise,
    model_task_intent_supported,
    PRIMARY_CLAIM_DOMAINS,
    usage_for,
)
from hxy_knowledge.answer_engine import classify_intent
from hxy_knowledge.config import get_settings
from hxy_knowledge.compliance_rules import check_brand_risk_text, load_brand_risk_rules
from hxy_knowledge.core10_activation import (
    load_core10_activation_artifact_from_dir_fd,
    validate_core10_activation_decisions,
)
from hxy_knowledge.eval_runner import run_golden_evals
from hxy_knowledge.enterprise_governance import (
    build_enterprise_governance_report,
    build_file_manifest,
    build_governance_run_package,
    build_incremental_compile_plan,
)
from hxy_knowledge.golden_questions import authority_cards
from hxy_knowledge.golden_questions import golden_questions
from hxy_knowledge.ingest_loop import run_ingest_loop
from hxy_knowledge.importer import load_current_records
from hxy_knowledge.knowledge_compiler import (
    build_topic_publication_package,
    build_topic_publication_preflight,
    build_topic_review_decisions_sample,
    build_topic_review_decisions_stub,
    dry_run_topic_publication_package,
    validate_topic_reviewed_assets_import_gate,
    validate_topic_review_decisions,
)
from hxy_knowledge.loop_engine import build_p0_governance_status, validate_p0_review_decisions
from hxy_knowledge.memory_ingest import build_instant_memory_records
from hxy_knowledge.model_router import ModelRouter
from hxy_knowledge.okf import load_okf_documents, summarize_okf_lifecycle
from hxy_knowledge.operating_brain import operating_brain_capabilities
from hxy_knowledge.operating_issues import build_operating_issues, issue_from_intake
from hxy_knowledge.process_memory import build_memory_promotion_draft, build_process_memory_record
from hxy_knowledge.reliability import is_process_memory_evidence, score_answer_quality
from hxy_knowledge.repository import KnowledgeRepository
from hxy_knowledge.source_brief import build_source_brief
from hxy_knowledge.startup_advancer import build_startup_advance
from hxy_knowledge.store_metrics import diagnose_store_daily_metrics
from hxy_knowledge.thinking_lenses import apply_thinking_lenses
from hxy_knowledge.training_curriculum import (
    build_adaptive_retrain_plan,
    build_recommended_training_plan,
    build_training_capability_profile,
    filter_training_questions,
)
from hxy_knowledge.understanding_engine import understand_text
from hxy_knowledge.workbench import classify_workbench_intake
from hxy_knowledge.workspace_events import (
    create_workspace_event,
    get_workspace_event,
    list_workspace_events,
    redact_workspace_event,
)
from hxy_product.auth import Principal, ProductAuthSettings, build_principal_resolver
from hxy_product.briefing_repository import BriefingRepository
from hxy_product.briefing_routes import create_briefing_router
from hxy_product.knowledge_context import AssignmentKnowledgeRepository
from hxy_product.journey_routes import create_journey_router
from hxy_product.learning_routes import create_learning_router
from hxy_product.conversation_repository import ConversationRepository
from hxy_product.conversation_routes import create_conversation_router
from hxy_product.intake_router import (
    build_model_assisted_route_classifier,
    generate_general_answer,
)
from hxy_product.intake_routes import create_intake_router
from hxy_product.channel_repository import ChannelRepository
from hxy_product.evidence_repository import EvidenceRepository
from hxy_product.evidence_routes import create_evidence_router
from hxy_product.material_repository import MaterialRepository
from hxy_product.material_routes import create_material_router
from hxy_product.onboarding_repository import OnboardingRepository
from hxy_product.onboarding_routes import create_onboarding_router, validate_public_app_url
from hxy_product.operating_repository import OperatingRepository
from hxy_product.operating_routes import create_operating_router
from hxy_product.operating_service import OperatingService
from hxy_product.record_repository import RecordRepository
from hxy_product.record_routes import create_record_router
from hxy_product.repository import IdentityRepository
from hxy_product.routes import assignment_for_principal, create_identity_router
from hxy_product.service_repository import ServiceRepository
from hxy_product.service_routes import create_service_router
from hxy_product.task_repository import TaskRepository
from hxy_product.task_routes import create_task_router
from hxy_product.training_repository import ProductTrainingRepository


RepositoryFactory = Callable[[], Any]

_CORE10_ARTIFACT_DIRECTORY_PATTERN = re.compile(
    r"core10-activation-[a-f0-9]{12}"
)
_CORE10_PUBLIC_PACKET_FIELDS = {
    "version",
    "generated_at",
    "item_count",
    "preview_only",
    "write_to_database",
    "publish_allowed",
    "official_use_allowed",
    "requires_founder_decision",
    "authority_rule",
    "upstream_fingerprints",
    "items",
    "packet_fingerprint",
    "packet_id",
    "artifact_fingerprint",
}
_CORE10_PUBLIC_ITEM_FIELDS = {
    "item_key",
    "current_state",
    "proposed_authority",
    "why_needed",
    "risk_if_approved",
    "risk_if_rejected",
    "affected_core10_cases",
    "source_evidence",
    "blockers",
    "exact_write_intents",
    "decision_options",
    "official_use_allowed",
    "write_allowed",
    "item_fingerprint",
}
_CORE10_SOURCE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9:._-]{0,127}$")
_CORE10_CANONICAL_PUBLIC_ASSET_ID_PATTERN = re.compile(
    r"^hxy-(?:inbox|file):[a-f0-9]{16}(?::path:[a-f0-9]{10})?$"
)
_CORE10_PUBLIC_SOURCE_ORIGINS = {"internal"}
_CORE10_PUBLIC_SOURCE_AUTHORITIES = {
    "approved_answer_card",
    "internal_material",
    "official_internal",
}
_CORE10_UNSAFE_KEY_TOKENS = {
    "claim_id",
    "chunk_id",
    "credential",
    "credentials",
    "database_url",
    "db_url",
    "dsn",
    "password",
    "passwd",
    "secret",
    "token",
}
_CORE10_PUBLIC_NESTED_FIELDS = {
    "active_version",
    "algorithm",
    "answer",
    "approved_conflict_count",
    "approved_match_count",
    "asset_id",
    "asset_ids",
    "authority",
    "authority_version",
    "blocked_terms",
    "brand_identity",
    "constitution_draft",
    "constitution_state",
    "core_statements",
    "digest",
    "draft",
    "draft_present",
    "draft_version",
    "existing_answer_card_count",
    "existing_answer_cards",
    "expected_previous_version",
    "forbidden_interpretations",
    "founder",
    "headquarters",
    "operation",
    "operations_sources",
    "payload_sha256",
    "product_sources",
    "question_pattern",
    "reception_draft",
    "report",
    "role_variants",
    "selected_source_count",
    "service_facts",
    "source_id",
    "source_ids",
    "source_references",
    "statement",
    "status",
    "store_manager",
    "store_staff",
    "version",
}
_CORE10_SENSITIVE_TEXT_PATTERN = re.compile(
    r"(?:api[-_ ]?key|access[-_ ]?token|client[-_ ]?secret|password|"
    r"passwd|credential|database[-_ ]?url|db[-_ ]?url)\s*[:=]",
    re.IGNORECASE,
)
_CORE10_DATABASE_URL_PATTERN = re.compile(
    r"\b(?:postgres(?:ql)?|mysql|mariadb|mongodb(?:\+srv)?|redis)://\S+",
    re.IGNORECASE,
)
_CORE10_CREDENTIAL_URL_PATTERN = re.compile(
    r"\b[a-z][a-z0-9+.-]*://[^\s/:@]+:[^\s/@]+@",
    re.IGNORECASE,
)
_CORE10_BEARER_TOKEN_PATTERN = re.compile(
    r"\b(?:authorization\s*:\s*)?bearer\s+[A-Za-z0-9._~+/=-]+",
    re.IGNORECASE,
)
_CORE10_PRIVATE_KEY_PATTERN = re.compile(
    r"-----BEGIN(?: [A-Z0-9]+)* PRIVATE KEY-----",
    re.IGNORECASE,
)
_CORE10_EMBEDDED_POSIX_PATH_PATTERN = re.compile(
    r"(?:^|[\s\"'`(=])/(?:[A-Za-z0-9._~-]+/)*[A-Za-z0-9._~-]+"
)
_CORE10_EMBEDDED_WINDOWS_PATH_PATTERN = re.compile(
    r"\b[A-Za-z]:[\\/](?:[^\s\\/]+[\\/])*[^\s\\/]+"
)
_CORE10_REDACTION = "[redacted]"


class Core10ActivationDecisionItemRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    item_key: Literal[
        "brand_constitution",
        "product_system_sources",
        "first_store_operations_sources",
        "reception_standard_answer_card",
    ]
    item_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    action: Literal["approve", "reject", "request_correction"]
    reason: str = Field(min_length=1, max_length=2000)


class Core10ActivationDecisionPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    packet_id: str = Field(pattern=r"^core10-activation:[0-9a-f]{12}$")
    packet_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    decisions: list[Core10ActivationDecisionItemRequest] = Field(
        min_length=4,
        max_length=4,
    )


def _core10_public_text(value: str, *, max_length: int = 4000) -> str:
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", " ", value)
    text = re.sub(r"\s+", " ", text).strip()
    if (
        _CORE10_SENSITIVE_TEXT_PATTERN.search(text)
        or _CORE10_DATABASE_URL_PATTERN.search(text)
        or _CORE10_CREDENTIAL_URL_PATTERN.search(text)
        or _CORE10_BEARER_TOKEN_PATTERN.search(text)
        or _CORE10_PRIVATE_KEY_PATTERN.search(text)
        or _CORE10_EMBEDDED_POSIX_PATH_PATTERN.search(text)
        or _CORE10_EMBEDDED_WINDOWS_PATH_PATTERN.search(text)
    ):
        return _CORE10_REDACTION
    return text[:max_length]


def _core10_public_value(value: Any) -> Any:
    if isinstance(value, dict):
        public: dict[str, Any] = {}
        for key, nested in value.items():
            key_text = str(key)
            normalized_key = key_text.strip().lower().replace("-", "_")
            if (
                normalized_key in _CORE10_UNSAFE_KEY_TOKENS
                or normalized_key.endswith("_path")
                or normalized_key not in _CORE10_PUBLIC_NESTED_FIELDS
            ):
                continue
            if normalized_key in {"asset_id", "source_id"}:
                asset_id = _core10_public_asset_id(nested)
                if asset_id is not None:
                    public[key_text] = asset_id
                continue
            if normalized_key in {"asset_ids", "source_ids"}:
                if isinstance(nested, list):
                    public[key_text] = [
                        asset_id
                        for item in nested
                        if (asset_id := _core10_public_asset_id(item)) is not None
                    ]
                continue
            public[key_text] = _core10_public_value(nested)
        return public
    if isinstance(value, list):
        return [_core10_public_value(nested) for nested in value]
    if isinstance(value, str):
        return _core10_public_text(value)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return _core10_public_text(str(value))


def _core10_public_asset_id(value: Any) -> str | None:
    if not isinstance(value, str) or not _CORE10_SOURCE_ID_PATTERN.fullmatch(value):
        return None
    if _CORE10_CANONICAL_PUBLIC_ASSET_ID_PATTERN.fullmatch(value):
        return value
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:32]
    return f"asset-ref:{digest}"


def _core10_public_evidence(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    public: dict[str, Any] = {}
    asset_id = _core10_public_asset_id(value.get("asset_id"))
    if asset_id is not None:
        public["asset_id"] = asset_id
    source_origin = value.get("source_origin")
    if (
        isinstance(source_origin, str)
        and source_origin in _CORE10_PUBLIC_SOURCE_ORIGINS
    ):
        public["source_origin"] = source_origin
    source_authority = value.get("source_authority")
    if (
        isinstance(source_authority, str)
        and source_authority in _CORE10_PUBLIC_SOURCE_AUTHORITIES
    ):
        public["source_authority"] = source_authority
    authority_version = value.get("authority_version")
    if type(authority_version) is int and authority_version >= 1:
        public["authority_version"] = authority_version
    return public or None


def _core10_public_packet(packet: dict[str, Any]) -> dict[str, Any]:
    public = {
        key: _core10_public_value(value)
        for key, value in packet.items()
        if key in _CORE10_PUBLIC_PACKET_FIELDS and key != "items"
    }
    items = []
    for raw_item in packet.get("items", []):
        if not isinstance(raw_item, dict):
            continue
        item = {
            key: _core10_public_value(value)
            for key, value in raw_item.items()
            if key in _CORE10_PUBLIC_ITEM_FIELDS and key != "source_evidence"
        }
        source_evidence = raw_item.get("source_evidence")
        if not isinstance(source_evidence, list):
            source_evidence = []
        item["source_evidence"] = [
            projected
            for evidence in source_evidence
            if (projected := _core10_public_evidence(evidence)) is not None
        ]
        items.append(item)
    public["items"] = items
    return public


def _latest_core10_activation_packet(root_dir: Path) -> dict[str, Any] | None:
    if not hasattr(os, "O_NOFOLLOW"):
        return None
    flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_CLOEXEC", 0)
        | os.O_NOFOLLOW
    )
    directory_fd = -1
    try:
        directory_fd = os.open(root_dir, flags)
        for segment in ("data", "private", "core10-activation"):
            next_fd = os.open(segment, flags, dir_fd=directory_fd)
            os.close(directory_fd)
            directory_fd = next_fd
        candidates = os.listdir(directory_fd)
    except OSError:
        if directory_fd >= 0:
            os.close(directory_fd)
        return None

    valid_packets: list[tuple[datetime, str, dict[str, Any]]] = []
    try:
        for candidate in candidates:
            if not _CORE10_ARTIFACT_DIRECTORY_PATTERN.fullmatch(candidate):
                continue
            try:
                packet = load_core10_activation_artifact_from_dir_fd(
                    directory_fd,
                    candidate,
                )
                generated_at = datetime.fromisoformat(
                    str(packet["generated_at"]).replace("Z", "+00:00")
                )
                if (
                    generated_at.tzinfo is None
                    or generated_at.utcoffset()
                    != timezone.utc.utcoffset(generated_at)
                ):
                    continue
                valid_packets.append(
                    (generated_at, str(packet["packet_fingerprint"]), packet)
                )
            except (
                KeyError,
                TypeError,
                ValueError,
                OSError,
                UnicodeError,
                RecursionError,
            ):
                continue
    finally:
        os.close(directory_fd)
    if not valid_packets:
        return None
    return max(valid_packets, key=lambda record: (record[0], record[1]))[2]


class ChatRequest(BaseModel):
    question: str = Field(default="")
    scenario: str = Field(default="创始人内部决策")
    domain: str | None = None
    stage: str | None = None
    limit: int = Field(default=5, ge=1, le=10)
    source_asset_id: str | None = Field(default=None, max_length=200)


class FeedbackRequest(BaseModel):
    answer_id: str | None = None
    question: str = ""
    rating: str
    note: str = ""


class AnswerCardRequest(BaseModel):
    question_pattern: str
    intent: str = "unknown"
    audience: str = "general"
    answer: str
    reasoning: list[Any] = Field(default_factory=list)
    evidence: list[Any] = Field(default_factory=list)
    corrections: list[Any] = Field(default_factory=list)
    next_actions: list[Any] = Field(default_factory=list)
    status: str = "draft"
    source_answer_id: str | None = None


class UnderstandRequest(BaseModel):
    input: str
    scenario: str = "创始人内部决策"
    role: str = "founder"
    attachments: list[dict[str, Any]] = Field(default_factory=list)


class ThinkingLensRequest(BaseModel):
    input: str
    scenario: str = "创始人内部决策"
    stage: str = "zero_to_one"
    max_lenses: int = Field(default=3, ge=1, le=5)


class WorkbenchIntakeRequest(BaseModel):
    input: str = ""
    scenario: str = "经营问答"
    role: str = "team"
    attachments: list[dict[str, Any]] = Field(default_factory=list)


class OperatingIssueIntakeRequest(BaseModel):
    input: str = ""
    scenario: str = "经营问答"
    role: str = "team"


class IncrementalCompilePlanRequest(BaseModel):
    previous_manifest: dict[str, Any] = Field(default_factory=dict)
    current_manifest: dict[str, Any] = Field(default_factory=dict)
    relations: list[dict[str, Any]] = Field(default_factory=list)


class CompilerReviewDecisionRequest(BaseModel):
    action: str
    reviewer: str = "unknown"
    note: str = ""
    revised_claim: str = ""


class TopicReviewDecisionPreviewRequest(BaseModel):
    decisions: dict[str, Any] = Field(default_factory=dict)


class ProcessMemoryRequest(BaseModel):
    text: str = ""
    source: str = "chat"
    actor: str = "unknown"
    observed_at: str | None = None
    confidence: float = Field(default=0.5, ge=0, le=1)
    target_domain: str = "general"


class WorkspaceEventRequest(BaseModel):
    topic: str = ""
    actor: str = "unknown"
    role: str = "team"
    visibility: str = "public_org"
    input: str = ""
    ai_output: dict[str, Any] = Field(default_factory=dict)
    evidence: list[Any] = Field(default_factory=list)
    risk_flags: list[Any] = Field(default_factory=list)
    corrections: list[Any] = Field(default_factory=list)
    generated_tasks: list[Any] = Field(default_factory=list)
    memory_action: dict[str, Any] = Field(default_factory=dict)
    review_action: dict[str, Any] = Field(default_factory=dict)


class WorkspaceEventReviewTaskRequest(BaseModel):
    reviewer: str = "unknown"
    note: str = ""


class WorkspaceEventProcessMemoryRequest(BaseModel):
    actor: str = "unknown"
    target_domain: str = "general"
    confidence: float = Field(default=0.5, ge=0, le=1)


class BrandDecisionRequest(BaseModel):
    artifact_type: str = "opening_content"
    stage: str = "first_store_opening"
    text: str = ""


class ComplianceLanguageCheckRequest(BaseModel):
    text: str = ""
    channel: str = "unknown"
    audience: str = "customer"


class ComplianceWorkflowGateRequest(BaseModel):
    workflow_type: str = "content_publish"
    text: str = ""
    channel: str = "unknown"
    audience: str = "customer"


class MenuDraftPreflightRequest(BaseModel):
    text: str = ""
    channel: str = "项目菜单"
    audience: str = "customer"


class SourceBriefRequest(BaseModel):
    question: str = ""
    scenario: str = "经营问答"
    domain: str | None = None
    stage: str | None = None
    limit: int = Field(default=8, ge=1, le=20)


class StartupAdvanceRequest(BaseModel):
    action: str
    evidence_input: str = ""
    current_conclusion: str = ""
    main_question: str = "核爆点定位是否成立？"


class TrainingEvaluateRequest(BaseModel):
    training_item: str = "清泡调补养门店推荐话术"
    customer_question: str = "顾客问：清泡调补养有什么区别？"
    employee_answer: str
    scenario: str = "门店员工培训"
    role: str = "门店员工"
    employee_id: str = "employee-local"
    employee_name: str = "门店员工"
    store_id: str = "pilot-store"
    store_name: str = "荷小悦试点门店"


class StoreDailyMetricsRequest(BaseModel):
    store_id: str = "pilot-store"
    store_name: str = "荷小悦试点门店"
    business_date: str
    revenue: float = 0
    target_revenue: float = 0
    orders: int = 0
    average_ticket: float = 0
    target_average_ticket: float = 0
    repeat_rate: float = 0
    target_repeat_rate: float = 0
    product_mix: dict[str, float] = Field(default_factory=dict)
    training_retrain_count: int = 0
    customer_complaints: int = 0


class TrainingManagerAcceptanceRequest(BaseModel):
    session_id: str = ""
    training_session_id: str = ""
    manager_id: str = "manager-local"
    manager_name: str = "店长"
    accepted: bool = False
    onsite_verified: bool = False
    score: int = Field(default=0, ge=0, le=100)
    note: str = ""
    operating_metric_links: list[dict[str, Any]] = Field(default_factory=list)


class P0DecisionPreviewRequest(BaseModel):
    decisions: dict[str, Any] = Field(default_factory=dict)


def _safe_inbox_destination(inbox_dir: Path, file_name: str) -> Path:
    if not file_name or "/" in file_name or "\\" in file_name:
        raise HTTPException(status_code=400, detail="Invalid file name")
    destination = (inbox_dir / Path(file_name).name).resolve()
    inbox_root = inbox_dir.resolve()
    if not destination.is_relative_to(inbox_root):
        raise HTTPException(status_code=400, detail="Invalid upload path")
    return destination


def _require_api_token(expected_token: str):
    async def dependency(authorization: str | None = Header(default=None)) -> None:
        if not expected_token:
            return
        scheme, _, value = (authorization or "").partition(" ")
        if scheme.lower() != "bearer" or not secrets.compare_digest(value.strip(), expected_token):
            raise HTTPException(status_code=401, detail="Unauthorized")

    return dependency


async def _validated_upload_file(
    file: UploadFile,
    *,
    inbox_dir: Path,
    root_dir: Path,
    max_bytes: int,
    allowed_extensions: set[str],
) -> dict[str, Any]:
    destination = _safe_inbox_destination(inbox_dir, file.filename or "")
    extension = destination.suffix.lower()
    if extension not in allowed_extensions:
        raise HTTPException(status_code=415, detail=f"Unsupported upload file type: {extension or 'none'}")

    size = 0
    with destination.open("wb") as output:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > max_bytes:
                output.close()
                destination.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="Upload file is too large")
            output.write(chunk)

    return {
        "file_name": destination.name,
        "relative_path": str(destination.relative_to(root_dir)),
        "size": size,
        "mime_type": file.content_type or "",
        "status": "uploaded",
    }


def _default_repository_factory(database_url: str) -> RepositoryFactory:
    def make_repository() -> KnowledgeRepository:
        if not database_url:
            raise HTTPException(status_code=503, detail="HXY_DATABASE_URL is not configured")
        return KnowledgeRepository(database_url)

    return make_repository


def _default_product_identity_repository_factory(database_url: str) -> RepositoryFactory:
    def make_repository() -> IdentityRepository:
        if not database_url:
            raise HTTPException(status_code=503, detail="HXY_DATABASE_URL is not configured")
        return IdentityRepository(database_url)

    return make_repository


def _default_onboarding_repository_factory(database_url: str) -> RepositoryFactory:
    def make_repository() -> OnboardingRepository:
        if not database_url:
            raise HTTPException(status_code=503, detail="HXY_DATABASE_URL is not configured")
        return OnboardingRepository(database_url)

    return make_repository


def _default_conversation_repository_factory(database_url: str) -> RepositoryFactory:
    def make_repository() -> ConversationRepository:
        if not database_url:
            raise HTTPException(status_code=503, detail="HXY_DATABASE_URL is not configured")
        return ConversationRepository(database_url)

    return make_repository


def _default_material_repository_factory(database_url: str) -> RepositoryFactory:
    def make_repository() -> MaterialRepository:
        if not database_url:
            raise HTTPException(status_code=503, detail="HXY_DATABASE_URL is not configured")
        return MaterialRepository(database_url)

    return make_repository


def _default_task_repository_factory(database_url: str) -> RepositoryFactory:
    def make_repository() -> TaskRepository:
        if not database_url:
            raise HTTPException(status_code=503, detail="HXY_DATABASE_URL is not configured")
        return TaskRepository(database_url)

    return make_repository


def _default_channel_repository_factory(database_url: str) -> RepositoryFactory:
    def make_repository() -> ChannelRepository:
        if not database_url:
            raise HTTPException(status_code=503, detail="HXY_DATABASE_URL is not configured")
        return ChannelRepository(database_url)

    return make_repository


def _default_record_repository_factory(database_url: str) -> RepositoryFactory:
    def make_repository() -> RecordRepository:
        if not database_url:
            raise HTTPException(status_code=503, detail="HXY_DATABASE_URL is not configured")
        return RecordRepository(database_url)

    return make_repository


def _default_briefing_repository_factory(database_url: str) -> RepositoryFactory:
    def make_repository() -> BriefingRepository:
        if not database_url:
            raise HTTPException(status_code=503, detail="HXY_DATABASE_URL is not configured")
        return BriefingRepository(database_url)

    return make_repository


def _default_operating_repository_factory(database_url: str) -> RepositoryFactory:
    def make_repository() -> OperatingRepository:
        if not database_url:
            raise HTTPException(status_code=503, detail="HXY_DATABASE_URL is not configured")
        return OperatingRepository(database_url)

    return make_repository


def _default_evidence_repository_factory(
    database_url: str,
    *,
    max_evidence_bytes: int,
) -> RepositoryFactory:
    def make_repository() -> EvidenceRepository:
        if not database_url:
            raise HTTPException(status_code=503, detail="HXY_DATABASE_URL is not configured")
        return EvidenceRepository(
            database_url,
            max_evidence_bytes=max_evidence_bytes,
        )

    return make_repository


def _default_product_training_repository_factory(database_url: str) -> RepositoryFactory:
    def make_repository() -> ProductTrainingRepository:
        if not database_url:
            raise HTTPException(status_code=503, detail="HXY_DATABASE_URL is not configured")
        return ProductTrainingRepository(database_url)

    return make_repository


def _default_service_repository_factory(database_url: str) -> RepositoryFactory:
    def make_repository() -> ServiceRepository:
        if not database_url:
            raise HTTPException(status_code=503, detail="HXY_DATABASE_URL is not configured")
        return ServiceRepository(database_url)

    return make_repository


def _fallback_queries(question: str) -> list[str]:
    stop_chars = "，。！？?；;：:、（）()[]【】\"'“”‘’"
    cleaned = question
    for char in stop_chars:
        cleaned = cleaned.replace(char, " ")
    phrase_stop_words = [
        "是什么",
        "有什么",
        "有哪些",
        "怎么讲",
        "怎么说",
        "请问",
        "荷小悦",
        "知识库",
    ]
    compact = cleaned.replace(" ", "")
    queries: list[str] = []
    for word in phrase_stop_words:
        compact = compact.replace(word, "")
    if any(term in question for term in ("首店", "开业")):
        queries.append("小店模型 门店 运营")
    image_question_terms = ["图片", "图", "视觉", "画面", "海报", "菜单图", "表达", "卖点"]
    if any(term in question for term in image_question_terms):
        image_query_parts = ["图片类型", "视觉摘要", "业务摘要"]
        for term in ["草本泡脚", "泡脚", "菜单", "产品", "卖点", "复购话术", "品牌", "竞品", "背书", "价格", "视觉风格"]:
            if term in question and term not in image_query_parts:
                image_query_parts.append(term)
        queries.insert(0, " ".join(image_query_parts))

    known_terms = [
        "泡脚方",
        "泡脚",
        "清泡调补养",
        "核爆点",
        "定位",
        "产品体系",
        "草本",
        "一人一方",
        "小店模型",
    ]
    for term in known_terms:
        if term in question and term not in queries:
            queries.append(term)

    if compact and compact != question:
        queries.append(compact)

    product_system_synonyms = {
        "清泡调补养": ["草本泡脚", "泡脚方", "一人一方", "产品体系"],
        "产品体系": ["草本泡脚", "泡脚方", "一人一方"],
        "泡脚方": ["草本泡脚", "一人一方", "五脏泡脚"],
    }
    for trigger, synonyms in product_system_synonyms.items():
        if trigger not in question:
            continue
        for synonym in synonyms:
            if synonym not in queries:
                queries.append(synonym)

    token_stop_words = {"什么", "怎么", "如何", "为什么", "多少", "有没有", "请问", "荷小悦", "知识库"}
    parts = [part.strip() for part in cleaned.split() if part.strip()]
    keywords = [part for part in parts if part not in token_stop_words]
    if keywords:
        joined = " ".join(keywords[:3])
        if joined not in queries:
            queries.append(joined)
    return [query for query in queries if query and query != question]


def _repository_search(
    repo: Any,
    query: str,
    *,
    domain: str | None,
    stage: str | None,
    limit: int,
    domain_hint: str | None,
) -> list[dict[str, Any]]:
    search = repo.search
    if "domain_hint" in inspect.signature(search).parameters:
        return search(query, domain=domain, stage=stage, limit=limit, domain_hint=domain_hint)
    return search(query, domain=domain, stage=stage, limit=limit)


def _items_need_better_retrieval(items: list[dict[str, Any]], intent: str) -> bool:
    if not items:
        return True
    allowed_domains = PRIMARY_CLAIM_DOMAINS.get(intent) or set()
    domains = {item.get("domain") for item in items if item.get("domain")}
    if allowed_domains and not (domains & allowed_domains):
        return True
    top_items = items[: min(3, len(items))]
    if top_items and all(has_metadata_noise(item.get("content") or "") for item in top_items):
        return True
    return False


def _retrieval_item_quality(item: dict[str, Any], intent: str) -> int:
    content = str(item.get("content") or "")
    if not content.strip():
        return -40
    allowed_domains = PRIMARY_CLAIM_DOMAINS.get(intent) or set()
    domain = str(item.get("domain") or "")
    stage = str(item.get("stage") or "")
    score = int(item.get("score") or 0)
    quality = min(max(score, 0), 100) // 5
    if domain in allowed_domains:
        quality += 40
    elif allowed_domains:
        quality -= 12
    preferred_domains = {
        "product_system": {"product"},
        "brand_positioning": {"brand"},
        "operations": {"operations"},
        "finance": {"finance"},
        "franchise": {"franchise"},
        "store_model": {"store_model"},
    }.get(intent, set())
    if domain in preferred_domains:
        quality += 48
    if stage in {"approved", "final", "production"}:
        quality += 22
    elif stage == "pilot":
        quality += 8
    elif stage in {"draft", "preparation"}:
        quality -= 4
    if has_metadata_noise(content):
        quality -= 90
    for keyword in ["清泡调补养", "泡脚方", "产品体系", "草本泡脚", "一人一方", "门店员工", "培训", "话术"]:
        if keyword in content:
            quality += 8
    return quality


def _retrieval_domain_rank(domain: str, intent: str) -> int:
    priority = {
        "product_system": ["product", "brand", "operations", "store_model", "franchise", "finance", "competitor", "external"],
        "brand_positioning": ["brand", "product", "store_model", "franchise", "finance", "competitor", "external"],
        "operations": ["operations", "product", "store_model", "brand", "franchise", "finance", "competitor", "external"],
        "finance": ["finance", "store_model", "franchise", "brand", "product", "competitor", "external"],
        "franchise": ["franchise", "finance", "store_model", "brand", "product", "competitor", "external"],
        "store_model": ["store_model", "product", "finance", "brand", "operations", "competitor", "external"],
    }.get(intent, [])
    if domain in priority:
        return len(priority) - priority.index(domain)
    return 0


def _sort_retrieval_items(items: list[dict[str, Any]], intent: str) -> list[dict[str, Any]]:
    return sorted(
        items,
        key=lambda item: (
            _retrieval_item_quality(item, intent),
            _retrieval_domain_rank(str(item.get("domain") or ""), intent),
            int(item.get("score") or 0),
        ),
        reverse=True,
    )


def _retrieval_set_quality(items: list[dict[str, Any]], intent: str) -> int:
    if not items:
        return -1000
    sorted_items = _sort_retrieval_items(items, intent)
    qualities = [_retrieval_item_quality(item, intent) for item in sorted_items]
    usable_count = sum(1 for value in qualities if value >= 45)
    noisy_count = sum(1 for item in items if has_metadata_noise(str(item.get("content") or "")))
    top_quality = sum(sorted(qualities, reverse=True)[:3])
    return top_quality + usable_count * 25 - noisy_count * 20


def _best_retrieval_candidate(
    repo: Any,
    question: str,
    *,
    domain: str | None,
    stage: str | None,
    limit: int,
    domain_hint: str | None,
) -> tuple[str, list[dict[str, Any]]]:
    candidates = [question, *_fallback_queries(question)]
    seen: set[str] = set()
    best_query = question
    best_items: list[dict[str, Any]] = []
    best_quality = -1001
    for query in candidates:
        if query in seen:
            continue
        seen.add(query)
        items = _repository_search(
            repo,
            query,
            domain=domain,
            stage=stage,
            limit=limit,
            domain_hint=domain_hint,
        )
        quality = _retrieval_set_quality(items, domain_hint or "")
        if quality > best_quality:
            best_query = query
            best_items = _sort_retrieval_items(items, domain_hint or "")
            best_quality = quality
        if best_quality >= 180 and not _items_need_better_retrieval(best_items, domain_hint or ""):
            break
    return best_query, best_items


_IMAGE_UPLOAD_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def _is_image_upload(file_info: dict[str, Any]) -> bool:
    mime_type = str(file_info.get("mime_type") or "").lower()
    file_name = str(file_info.get("file_name") or "")
    return mime_type.startswith("image/") or Path(file_name).suffix.lower() in _IMAGE_UPLOAD_EXTENSIONS


_FRONTDOOR_INTENTS = {
    "brand_positioning",
    "product_system",
    "operations",
    "finance",
    "franchise",
    "store_model",
    "knowledge_lookup",
}
_FRONTDOOR_TASK_INTENTS = {
    "conversation_navigation",
    "system_capability",
    "training",
    "material_ingestion",
    "issue_reporting",
}
_FRONTDOOR_TASK_WORKFLOWS = {
    "conversation_navigation": "ask",
    "system_capability": "ask",
    "training": "train",
    "material_ingestion": "ingest",
    "issue_reporting": "correct",
}
_FRONTDOOR_WORKFLOWS = {"ask", "train", "ingest", "correct", "decide", "review"}
_WORKBENCH_INPUT_TYPES = {
    "question",
    "knowledge_intake",
    "correction",
    "operating_task",
    "training",
    "decision_support",
}
_WORKBENCH_WORKFLOWS = {"ask", "train", "ingest", "correct", "execute", "decide"}


def _frontdoor_messages(question: str, scenario: str, rule_intent: str) -> list[dict[str, str]]:
    system = (
        "你是荷小悦经营大脑的前门意图判断器。你的任务不是回答问题，而是判断这次输入应该走哪条业务路径。"
        "必须基于语义和场景判断，不要只按关键词匹配。只返回 JSON，不要 Markdown。"
        "JSON 字段：intent, audience, primary_workflow, confidence, reason。"
        "intent 只能是 brand_positioning/product_system/operations/finance/franchise/store_model/knowledge_lookup/"
        "system_capability/training/material_ingestion/issue_reporting。"
        "primary_workflow 只能是 ask/train/ingest/correct/decide/review。"
        "如果问题模糊但场景明确，要结合场景判断；如果仍不确定，intent 用 knowledge_lookup。"
    )
    user = "\n".join(
        [
            f"问题：{question}",
            f"场景：{scenario}",
            f"规则兜底意图：{rule_intent}",
            "判断目标：识别业务域、使用角色和工作流，让后续检索进入正确知识域。",
        ]
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _frontdoor_classification_from_generation(
    generation: dict[str, Any],
    *,
    question: str,
) -> dict[str, Any] | None:
    if not generation.get("used_model"):
        return None
    payload = _extract_json_object(str(generation.get("output") or ""))
    if not payload:
        return None
    intent = str(payload.get("intent") or "").strip()
    workflow = str(payload.get("primary_workflow") or "").strip()
    if intent not in (_FRONTDOOR_INTENTS | _FRONTDOOR_TASK_INTENTS):
        return None
    if workflow not in _FRONTDOOR_WORKFLOWS:
        workflow = "ask"
    confidence = 0.0
    try:
        confidence = float(payload.get("confidence") or 0)
    except (TypeError, ValueError):
        confidence = 0.0
    if confidence > 1:
        confidence = confidence / 100
    if intent in _FRONTDOOR_TASK_INTENTS:
        if confidence < 0.85 or not model_task_intent_supported(question, intent):
            return None
    elif confidence < 0.65:
        return None
    return {
        "version": "hxy-frontdoor-classification.v1",
        "mode": "ai",
        "intent": intent,
        "audience": str(payload.get("audience") or "general").strip() or "general",
        "primary_workflow": workflow,
        "confidence": round(max(0.0, min(1.0, confidence)), 2),
        "reason": str(payload.get("reason") or "").strip(),
        "model_reason": generation.get("reason") or "ok",
    }


def _classify_frontdoor(
    *,
    model_router: Any,
    question: str,
    scenario: str,
    rule_intent: str,
    rule_audience: str,
    rule_task_intent: str | None = None,
) -> dict[str, Any]:
    route = model_router.route("frontdoor_classification")
    if rule_task_intent in _FRONTDOOR_TASK_INTENTS:
        return {
            "version": "hxy-frontdoor-classification.v1",
            "mode": "deterministic",
            "intent": rule_task_intent,
            "audience": rule_audience,
            "primary_workflow": _FRONTDOOR_TASK_WORKFLOWS[rule_task_intent],
            "confidence": 0.98,
            "reason": "明确的产品任务指令。",
            "model_reason": "not_used",
            "route": route,
        }
    fallback = {
        "version": "hxy-frontdoor-classification.v1",
        "mode": "rule_fallback",
        "intent": rule_intent,
        "audience": rule_audience,
        "primary_workflow": "ask",
        "confidence": 0.55 if rule_intent == "knowledge_lookup" else 0.75,
        "reason": "使用本地规则判断；模型未启用或当前规则已足够明确。",
        "model_reason": "not_used",
    }
    if rule_intent != "knowledge_lookup" or not route.get("should_call_model"):
        fallback["route"] = route
        return fallback
    try:
        generation = model_router.generate(
            "frontdoor_classification",
            messages=_frontdoor_messages(question, scenario, rule_intent),
            metadata={
                "scenario": scenario,
                "rule_intent": rule_intent,
                "task": "frontdoor_classification",
            },
        )
    except Exception as exc:
        fallback["model_reason"] = f"model_error:{type(exc).__name__}"
        fallback["route"] = route
        return fallback
    classification = _frontdoor_classification_from_generation(
        generation,
        question=question,
    )
    if not classification:
        fallback["model_reason"] = generation.get("reason") or "invalid_model_output"
        fallback["route"] = route
        return fallback
    classification["route"] = route
    return classification


def _workbench_intake_messages(
    input_text: str,
    scenario: str,
    role: str,
    attachments: list[dict[str, Any]],
    rule_result: dict[str, Any],
) -> list[dict[str, str]]:
    system = (
        "你是荷小悦经营大脑的工作台入口判断器。你不回答问题，只判断这次输入应该进入哪个工作流。"
        "必须基于语义、场景、角色和附件综合判断，不要只按关键词匹配。只返回 JSON，不要 Markdown。"
        "JSON 字段：input_type, primary_workflow, team_value, answer_shape, inspector_shape, memory_action, next_actions, confidence, reason。"
        "input_type 只能是 question/knowledge_intake/correction/operating_task/training/decision_support。"
        "primary_workflow 只能是 ask/train/ingest/correct/execute/decide。"
        "team_value、answer_shape、inspector_shape、next_actions 必须是短字符串数组。"
        "如果用户是在说上一条不对、重做、按最新口径改，即使没有出现“纠偏”二字，也应判断为 correction/correct。"
    )
    user = "\n".join(
        [
            f"输入：{input_text}",
            f"场景：{scenario}",
            f"角色：{role}",
            f"附件：{json.dumps(attachments, ensure_ascii=False)}",
            f"规则兜底结果：{json.dumps({key: rule_result.get(key) for key in ['input_type', 'primary_workflow', 'team_value', 'answer_shape', 'inspector_shape', 'memory_action', 'next_actions']}, ensure_ascii=False)}",
            "判断目标：让聊天框同时支持问经营、练员工、传资料、纠偏和派任务，并保持主回答简洁。",
        ]
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _bounded_string_list(value: Any, fallback: list[str], *, limit: int = 5) -> list[str]:
    if not isinstance(value, list):
        return fallback
    cleaned = [str(item).strip() for item in value if str(item).strip()]
    return cleaned[:limit] or fallback


def _workbench_intake_from_generation(
    generation: dict[str, Any],
    *,
    base_result: dict[str, Any],
    route: dict[str, Any],
) -> dict[str, Any] | None:
    if not generation.get("used_model"):
        return None
    payload = _extract_json_object(str(generation.get("output") or ""))
    if not payload:
        return None
    input_type = str(payload.get("input_type") or "").strip()
    workflow = str(payload.get("primary_workflow") or "").strip()
    if input_type not in _WORKBENCH_INPUT_TYPES or workflow not in _WORKBENCH_WORKFLOWS:
        return None
    confidence = 0.0
    try:
        confidence = float(payload.get("confidence") or 0)
    except (TypeError, ValueError):
        confidence = 0.0
    if confidence > 1:
        confidence = confidence / 100
    if confidence < 0.7:
        return None
    result = dict(base_result)
    result.update(
        {
            "input_type": input_type,
            "primary_workflow": workflow,
            "team_value": _bounded_string_list(payload.get("team_value"), base_result.get("team_value") or [], limit=4),
            "answer_shape": _bounded_string_list(payload.get("answer_shape"), base_result.get("answer_shape") or [], limit=6),
            "inspector_shape": _bounded_string_list(payload.get("inspector_shape"), base_result.get("inspector_shape") or [], limit=7),
            "memory_action": str(payload.get("memory_action") or base_result.get("memory_action") or "").strip(),
            "next_actions": _bounded_string_list(payload.get("next_actions"), base_result.get("next_actions") or [], limit=5),
            "intake_judgment": {
                "version": "hxy-workbench-intake-judgment.v1",
                "mode": "ai",
                "task_type": "workbench_intake",
                "confidence": round(max(0.0, min(1.0, confidence)), 2),
                "reason": str(payload.get("reason") or "").strip(),
                "model_reason": generation.get("reason") or "ok",
                "route": route,
            },
        }
    )
    return result


def _classify_workbench_intake_with_model(
    *,
    model_router: Any,
    input_text: str,
    scenario: str,
    role: str,
    attachments: list[dict[str, Any]],
) -> dict[str, Any]:
    rule_result = classify_workbench_intake(input_text, scenario=scenario, role=role, attachments=attachments)
    route = model_router.route("workbench_intake")
    fallback = dict(rule_result)
    fallback["intake_judgment"] = {
        "version": "hxy-workbench-intake-judgment.v1",
        "mode": "rule_fallback",
        "task_type": "workbench_intake",
        "confidence": 0.62,
        "reason": "使用本地工作台规则；模型未启用、未配置或输出未通过白名单校验。",
        "model_reason": "not_used",
        "route": route,
    }
    if not route.get("should_call_model"):
        return fallback
    try:
        generation = model_router.generate(
            "workbench_intake",
            messages=_workbench_intake_messages(input_text, scenario, role, attachments, rule_result),
            metadata={
                "scenario": scenario,
                "role": role,
                "attachment_count": len(attachments),
                "rule_input_type": rule_result.get("input_type"),
                "rule_primary_workflow": rule_result.get("primary_workflow"),
            },
        )
    except Exception as exc:
        fallback["intake_judgment"]["model_reason"] = f"model_error:{type(exc).__name__}"
        return fallback
    ai_result = _workbench_intake_from_generation(generation, base_result=rule_result, route=route)
    if not ai_result:
        fallback["intake_judgment"]["model_reason"] = generation.get("reason") or "invalid_model_output"
        return fallback
    return ai_result


def _vision_messages_for_upload(file_info: dict[str, Any], data_url: str, input_text: str, scenario: str) -> list[dict[str, Any]]:
    instruction = (
        "你是荷小悦经营大脑的图片资料理解器。请深度识别图片里的业务信息，不要只做普通 caption。"
        "必须返回 JSON，不要 Markdown。字段：image_type, visual_summary, business_summary, ocr_text, "
        "detected_entities, prices, related_domains, confidence, qa_ready, needs_review。"
        "image_type 可用 menu/competitor_reference/store_photo/brand_visual/system_screenshot/general_image。"
        "business_summary 要说明这张图应该沉淀到哪个经营知识里，以及团队如何使用。"
        "related_domains 只能使用 product/brand/operations/store_model/franchise/finance/competitor/technology/external。"
        "如果图片不清楚或无法稳定识别，qa_ready=false, needs_review=true。"
    )
    prompt = "\n".join(
        [
            instruction,
            f"上传文件：{file_info.get('file_name') or ''}",
            f"上传场景：{scenario}",
            f"用户说明：{input_text or '无'}",
        ]
    )
    return [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        }
    ]


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _image_understanding_from_generation(
    *,
    generation: dict[str, Any],
    file_info: dict[str, Any],
    asset_id: str,
) -> dict[str, Any] | None:
    if not generation.get("used_model"):
        return None
    payload = _extract_json_object(str(generation.get("output") or ""))
    if not payload:
        return None
    image_type = str(payload.get("image_type") or "general_image").strip() or "general_image"
    visual_summary = str(payload.get("visual_summary") or "").strip()
    business_summary = str(payload.get("business_summary") or "").strip()
    if not visual_summary or not business_summary:
        return None
    confidence = max(0.0, min(1.0, _safe_float(payload.get("confidence"), 0.0)))
    qa_ready = bool(payload.get("qa_ready")) and confidence >= 0.5
    needs_review = bool(payload.get("needs_review", not qa_ready)) or not qa_ready
    related_domains = _string_list(payload.get("related_domains")) or ["external"]
    normalized_domains = [
        domain
        for domain in related_domains
        if domain in {"product", "brand", "operations", "store_model", "franchise", "finance", "competitor", "technology", "external"}
    ] or ["external"]
    record = {
        "asset_id": asset_id,
        "run_name": "workbench-instant",
        "source_path": file_info.get("relative_path") or "",
        "normalized_path": file_info.get("relative_path") or "",
        "title": Path(str(file_info.get("file_name") or "")).stem,
        "image_type": image_type,
        "visual_summary": visual_summary,
        "business_summary": business_summary,
        "ocr_text": str(payload.get("ocr_text") or "").strip(),
        "detected_entities": _string_list(payload.get("detected_entities")),
        "prices": _string_list(payload.get("prices")),
        "related_domains": normalized_domains,
        "confidence": confidence,
        "qa_ready": qa_ready,
        "needs_review": needs_review,
        "payload": {
            **payload,
            "model_reason": generation.get("reason") or "ok",
            "provider_response_id": generation.get("provider_response_id"),
        },
    }
    return record


def _image_understanding_text(record: dict[str, Any]) -> str:
    parts = [
        f"图片类型：{record.get('image_type') or 'general_image'}",
        f"视觉摘要：{record.get('visual_summary') or ''}",
        f"业务摘要：{record.get('business_summary') or ''}",
    ]
    if record.get("detected_entities"):
        parts.append("识别实体：" + "、".join(record["detected_entities"]))
    if record.get("prices"):
        parts.append("价格信息：" + "、".join(record["prices"]))
    if record.get("ocr_text"):
        parts.append("OCR 文本：" + str(record["ocr_text"])[:1000])
    parts.append("相关知识域：" + "、".join(record.get("related_domains") or []))
    return "\n".join(parts)


def _chunk_for_image_understanding(record: dict[str, Any]) -> dict[str, Any]:
    primary_domain = (record.get("related_domains") or ["external"])[0]
    return {
        "chunk_id": f"{record['asset_id']}:image-understanding:0",
        "asset_id": record["asset_id"],
        "run_name": record.get("run_name") or "workbench-instant",
        "chunk_index": 900000,
        "title": record.get("title") or "",
        "source_path": record.get("source_path") or "",
        "normalized_path": record.get("normalized_path") or "",
        "domain": primary_domain,
        "stage": "workbench",
        "content": _image_understanding_text(record),
        "metadata": {
            "chunk_type": "image_understanding",
            "image_type": record.get("image_type") or "general_image",
            "confidence": record.get("confidence") or 0,
            "qa_ready": bool(record.get("qa_ready")),
        },
    }


def _understand_uploaded_images(
    *,
    root_dir: Path,
    uploaded_files: list[dict[str, Any]],
    memory_assets: list[dict[str, Any]],
    model_router: Any,
    input_text: str,
    scenario: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    asset_by_path = {asset.get("source_path"): asset for asset in memory_assets}
    records: list[dict[str, Any]] = []
    chunks: list[dict[str, Any]] = []
    tasks: list[dict[str, Any]] = []
    for file_info in uploaded_files:
        if not _is_image_upload(file_info):
            continue
        relative_path = file_info.get("relative_path") or ""
        path = (root_dir / relative_path).resolve()
        asset = asset_by_path.get(relative_path) or {}
        asset_id = asset.get("asset_id") or f"hxy-workbench:image:{Path(relative_path).name}"
        task = {
            "file_name": file_info.get("file_name") or "",
            "relative_path": relative_path,
            "asset_id": asset_id,
            "status": "needs_review",
            "reason": "vision_model_unavailable",
        }
        if not path.exists() or not path.is_relative_to(root_dir.resolve()):
            task["reason"] = "file_not_found"
            tasks.append(task)
            continue
        route = model_router.route("vision_understanding")
        if not route.get("should_call_model"):
            tasks.append(task)
            continue
        mime_type = file_info.get("mime_type") or "image/png"
        data_url = f"data:{mime_type};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"
        try:
            generation = model_router.generate(
                "vision_understanding",
                messages=_vision_messages_for_upload(file_info, data_url, input_text, scenario),
                metadata={
                    "file_name": file_info.get("file_name") or "",
                    "mime_type": mime_type,
                    "scenario": scenario,
                },
            )
        except Exception as exc:
            task["reason"] = f"model_error:{type(exc).__name__}"
            tasks.append(task)
            continue
        record = _image_understanding_from_generation(generation=generation, file_info=file_info, asset_id=asset_id)
        if not record:
            task["reason"] = generation.get("reason") or "invalid_model_output"
            tasks.append(task)
            continue
        records.append(record)
        if record.get("qa_ready"):
            chunks.append(_chunk_for_image_understanding(record))
        else:
            task["reason"] = "needs_human_review"
            tasks.append(task)
    return records, chunks, tasks


def _normalize_question_pattern(question: str) -> str:
    stop_chars = "，。！？?；;：:、（）()[]【】\"'“”‘’"
    normalized = question or ""
    for char in stop_chars:
        normalized = normalized.replace(char, "")
    return "".join(normalized.split())


def _builtin_authority_card(question: str, intent: str) -> dict[str, Any] | None:
    normalized_question = _normalize_question_pattern(question)
    for card in [*authority_cards(), *brand_authority_cards()]:
        if intent != "any" and card.get("intent") != intent:
            continue
        candidates = [card.get("question_pattern") or "", *(card.get("aliases") or [])]
        normalized_candidates = [_normalize_question_pattern(candidate) for candidate in candidates if candidate]
        if normalized_question in normalized_candidates:
            result = dict(card)
            result["card_id"] = f"builtin:{normalized_candidates[0]}"
            result["builtin"] = True
            return result
    return None


def _public_answer_card(card: dict[str, Any], *, source: str) -> dict[str, Any]:
    public = dict(card)
    public.setdefault("card_id", f"builtin:{_normalize_question_pattern(str(card.get('question_pattern') or ''))}")
    public.setdefault("review_status", "approved_v1" if public.get("status") == "approved" else public.get("status", "draft"))
    public.setdefault("version", "v1.0")
    public.setdefault("role_versions", {})
    public.setdefault("forbidden_terms", [])
    public.setdefault("applicable_scenarios", [])
    public.setdefault("aliases", [])
    public["builtin"] = source == "builtin"
    public["source"] = source
    return public


def _list_repository_answer_cards(repo: Any, *, status: str | None, limit: int) -> list[dict[str, Any]]:
    list_cards = getattr(repo, "list_answer_cards", None)
    if not callable(list_cards):
        return []
    return list_cards(status=status, limit=limit)


def _load_json_array(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ["items", "assets", "claims", "evidence", "relations"]:
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def _load_structured_governance_inputs(root_dir: Path) -> dict[str, list[dict[str, Any]]]:
    structured_roots = [
        root_dir / "quarantine" / "knowledge-assets" / "structured",
        root_dir / "knowledge" / "structured",
    ]
    result = {"claims": [], "evidence": [], "relations": []}
    for structured_root in structured_roots:
        if not structured_root.exists():
            continue
        result["claims"].extend(_load_json_array(structured_root / "claims.json"))
        result["evidence"].extend(_load_json_array(structured_root / "evidence.json"))
        result["relations"].extend(_load_json_array(structured_root / "relations.json"))
    return result


def _answer_from_authority_card(
    *,
    question: str,
    used_query: str,
    scenario: str,
    understanding: dict[str, Any],
    card: dict[str, Any],
) -> dict[str, Any]:
    card_intent = card.get("intent") or "unknown"
    card_audience = card.get("audience") or "general"
    card_answer = card.get("answer") or ""
    card_evidence = card.get("evidence") or []
    result_card_evidence = card_evidence or [
        {
            "domain": "approved_answer_card",
            "title": card.get("question_pattern") or question,
            "strength": "high",
            "excerpt": "已批准权威答案卡",
        }
    ]
    result_card = build_result_card(
        intent=card_intent,
        scenario=scenario,
        answer=card_answer,
        evidence=result_card_evidence,
        confidence="high",
        conflicts=[],
        needs_review=False,
    )
    for gate in result_card["quality_gates"]:
        if gate["name"] == "命中正确业务域":
            gate["passed"] = True
            gate["detail"] = "已命中批准后的权威答案卡。"
    result_card["stability_level"] = "stable"
    quality_score = score_answer_quality(
        question=question,
        intent=card_intent,
        scenario=scenario,
        answer=card_answer,
        evidence=result_card_evidence,
        confidence="high",
        needs_review=False,
        from_answer_card=True,
    )
    return {
        "answer_id": None,
        "card_id": card.get("card_id"),
        "authority_card": {
            "builtin": bool(card.get("builtin")),
            "card_id": card.get("card_id"),
            "source": card.get("source") or "builtin",
            "module": card.get("module"),
        },
        "from_answer_card": True,
        "question": question,
        "query": used_query,
        "intent": card_intent,
        "audience": card_audience,
        "scenario": scenario,
        "answer": card_answer,
        "usage": usage_for(card_intent, scenario),
        "applicable_scenarios": card.get("applicable_scenarios")
        or applicable_scenarios_for(card_intent, card_audience, scenario),
        "role_versions": card.get("role_versions") or {},
        "forbidden_terms": card.get("forbidden_terms") or [],
        "review_status": card.get("review_status") or "approved",
        "version": card.get("version") or "v1.0",
        "answer_status": "已批准",
        "reasoning": card.get("reasoning") or [],
        "evidence": card_evidence,
        "sources": card_evidence,
        "conflicts": [],
        "corrections": card.get("corrections") or [],
        "confidence": "high",
        "quality_score": quality_score,
        "quality_dimensions": quality_score["dimensions"],
        "next_actions": card.get("next_actions") or [],
        "needs_review": False,
        "result_card": result_card,
        "understanding": understanding,
    }


def _attach_model_route(answer: dict[str, Any], route: dict[str, Any]) -> dict[str, Any]:
    answer["model_route"] = route
    understanding = answer.get("understanding")
    if isinstance(understanding, dict):
        understanding["model_route"] = route
    return answer


def _attach_answer_pipeline(answer: dict[str, Any], *, role: str = "team") -> dict[str, Any]:
    route = answer.get("model_route") or {}
    pipeline = build_answer_pipeline(
        question=answer.get("question") or "",
        scenario=answer.get("scenario") or "经营问答",
        role=role,
        intent=answer.get("intent") or "unknown",
        answer=answer.get("answer") or "",
        evidence=answer.get("evidence") or [],
        confidence=answer.get("confidence") or "low",
        needs_review=bool(answer.get("needs_review", True)),
        from_answer_card=bool(answer.get("from_answer_card", False)),
        model_route=route,
    )
    answer["answer_pipeline"] = pipeline
    understanding = answer.get("understanding")
    if isinstance(understanding, dict):
        understanding["answer_pipeline"] = pipeline
    return answer


def _apply_frontdoor_to_answer(answer: dict[str, Any], frontdoor: dict[str, Any]) -> dict[str, Any]:
    if frontdoor.get("mode") != "ai":
        return answer
    frontdoor_intent = str(frontdoor.get("intent") or "")
    if frontdoor_intent in _FRONTDOOR_INTENTS and frontdoor_intent != "knowledge_lookup":
        answer["intent"] = frontdoor_intent
        answer["audience"] = frontdoor.get("audience") or answer.get("audience") or "general"
    understanding = answer.get("understanding")
    if isinstance(understanding, dict):
        understanding["frontdoor_classification"] = frontdoor
    return answer


def _model_answer_messages(question: str, answer: dict[str, Any]) -> list[dict[str, str]]:
    def bounded_text(value: Any, limit: int) -> str:
        normalized = " ".join(str(value or "").split())
        if len(normalized) <= limit:
            return normalized
        return normalized[: limit - 3].rstrip() + "..."

    evidence_lines = []
    evidence = [
        item
        for item in answer.get("evidence") or []
        if not is_process_memory_evidence(item)
    ][:1]
    for index, item in enumerate(evidence, start=1):
        title = bounded_text(item.get("title") or "未命名资料", 28)
        domain = bounded_text(item.get("domain") or "unknown", 16)
        excerpt = bounded_text(item.get("excerpt") or "", 100)
        evidence_lines.append(f"{index}. {title} [{domain}]：{excerpt}")
    system = (
        "你是荷小悦经营大脑的答案生成器。只能基于给定证据和已生成草稿回答。"
        "输出给团队直接使用的中文答案，不要展示来源、路径、chunk、技术字段。"
        "不得承诺治疗、治愈、保证回本、稳赚或绝对效果。"
    )
    user = "\n".join(
        [
            f"问题：{bounded_text(question, 48)}",
            f"场景：{bounded_text(answer.get('scenario') or '经营问答', 32)}",
            f"意图：{bounded_text(answer.get('intent') or 'unknown', 24)}",
            f"当前草稿：{bounded_text(answer.get('answer') or '', 160)}",
            "最高相关证据：",
            "\n".join(evidence_lines) or "无",
            "请输出更清晰、可执行、克制的可用答案，不超过 120 个汉字。",
        ]
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _policy_review_messages(question: str, answer: dict[str, Any], candidate_answer: str) -> list[dict[str, str]]:
    evidence_lines = []
    evidence = [item for item in answer.get("evidence") or [] if not is_process_memory_evidence(item)]
    for index, item in enumerate(evidence, start=1):
        title = item.get("title") or "未命名资料"
        domain = item.get("domain") or "unknown"
        excerpt = item.get("excerpt") or ""
        evidence_lines.append(f"{index}. {title} [{domain}]：{excerpt}")
    system = (
        "你是荷小悦经营大脑的质检守门员。你不负责美化答案，只判断候选答案能不能交付给团队使用。"
        "只返回 JSON，不要 Markdown。字段：passed, action, risk_flags, reason, confidence。"
        "action 只能是 pass/needs_review/reject。"
        "必须检查：是否有可用结论、是否符合证据、是否暴露技术痕迹、是否夸大疗效或收益、是否需要人工复核。"
        "你只能收紧质量要求，不能放宽本地安全规则。"
    )
    user = "\n".join(
        [
            f"问题：{question}",
            f"场景：{answer.get('scenario') or '经营问答'}",
            f"意图：{answer.get('intent') or 'unknown'}",
            f"候选答案：{candidate_answer}",
            "证据：",
            "\n".join(evidence_lines) or "无",
            "请判断这条候选答案是否可以直接给团队使用。",
        ]
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _policy_review_from_generation(generation: dict[str, Any]) -> dict[str, Any] | None:
    if not generation.get("used_model"):
        return None
    payload = _extract_json_object(str(generation.get("output") or ""))
    if not payload:
        return None
    action = str(payload.get("action") or "").strip()
    if action not in {"pass", "needs_review", "reject"}:
        return None
    confidence = 0.0
    try:
        confidence = float(payload.get("confidence") or 0)
    except (TypeError, ValueError):
        confidence = 0.0
    if confidence > 1:
        confidence = confidence / 100
    if confidence < 0.6:
        return None
    return {
        "version": "hxy-policy-review.v1",
        "mode": "ai",
        "passed": bool(payload.get("passed")) and action == "pass",
        "action": action,
        "risk_flags": _bounded_string_list(payload.get("risk_flags"), [], limit=6),
        "reason": str(payload.get("reason") or "").strip(),
        "confidence": round(max(0.0, min(1.0, confidence)), 2),
        "model_reason": generation.get("reason") or "ok",
        "route": generation.get("route") or {},
    }


def _review_model_candidate_answer(
    *,
    model_router: Any,
    question: str,
    answer: dict[str, Any],
    candidate_answer: str,
) -> dict[str, Any]:
    route = model_router.route("policy_review")
    fallback = {
        "version": "hxy-policy-review.v1",
        "mode": "rule_fallback",
        "passed": True,
        "action": "pass",
        "risk_flags": [],
        "reason": "模型质检未启用；已由本地质量闸口判断。",
        "confidence": 0.0,
        "model_reason": "not_used",
        "route": route,
    }
    if not route.get("should_call_model"):
        return fallback
    try:
        generation = model_router.generate(
            "policy_review",
            messages=_policy_review_messages(question, answer, candidate_answer),
            metadata={
                "intent": answer.get("intent") or "unknown",
                "scenario": answer.get("scenario") or "经营问答",
                "confidence": answer.get("confidence") or "low",
                "evidence_count": len(answer.get("evidence") or []),
            },
        )
    except Exception as exc:
        fallback["passed"] = False
        fallback["action"] = "needs_review"
        fallback["risk_flags"] = ["policy_review_model_error"]
        fallback["reason"] = "模型质检异常，按需复核处理。"
        fallback["model_reason"] = f"model_error:{type(exc).__name__}"
        return fallback
    review = _policy_review_from_generation(generation)
    if not review:
        fallback["passed"] = False
        fallback["action"] = "needs_review"
        fallback["risk_flags"] = ["policy_review_invalid_output"]
        fallback["reason"] = "模型质检输出未通过结构化校验，按需复核处理。"
        fallback["model_reason"] = generation.get("reason") or "invalid_model_output"
        return fallback
    return review


def _maybe_apply_model_answer(
    *,
    model_router: Any,
    question: str,
    answer: dict[str, Any],
) -> dict[str, Any]:
    route = answer.get("model_route") or model_router.route("rag_answer")
    if not route.get("should_call_model"):
        answer["model_generation"] = {
            "used_model": False,
            "reason": "disabled",
            "route": route,
        }
        return answer
    if bool(answer.get("needs_review")) and answer.get("confidence") == "low":
        answer["model_generation"] = {
            "used_model": False,
            "reason": "quality_gate_blocked",
            "route": route,
        }
        return answer
    original_answer = answer.get("answer") or ""
    result = model_router.generate(
        "answer_synthesis",
        messages=_model_answer_messages(question, answer),
        metadata={
            "intent": answer.get("intent") or "unknown",
            "scenario": answer.get("scenario") or "经营问答",
            "confidence": answer.get("confidence") or "low",
            "evidence_count": len(answer.get("evidence") or []),
        },
    )
    output = str(result.get("output") or "").strip()
    if not result.get("used_model") or not output:
        answer["model_generation"] = result
        return answer
    candidate_quality = score_answer_quality(
        question=question,
        intent=answer.get("intent") or "unknown",
        scenario=answer.get("scenario") or "经营问答",
        answer=output,
        evidence=answer.get("evidence") or [],
        confidence=answer.get("confidence") or "low",
        needs_review=bool(answer.get("needs_review", True)),
        from_answer_card=False,
    )
    if candidate_quality["needs_review"] or candidate_quality["level"] == "low" or has_metadata_noise(output):
        answer["model_generation"] = {
            **result,
            "used_model": False,
            "reason": "quality_gate_rejected",
        }
        answer["needs_review"] = True
        return answer
    policy_review = _review_model_candidate_answer(
        model_router=model_router,
        question=question,
        answer=answer,
        candidate_answer=output,
    )
    answer["policy_review"] = policy_review
    if not policy_review.get("passed", True):
        answer["model_generation"] = {
            **result,
            "used_model": False,
            "reason": "policy_review_rejected",
        }
        answer["needs_review"] = True
        answer["quality_score"] = candidate_quality
        answer["quality_dimensions"] = candidate_quality["dimensions"]
        return answer
    answer["answer"] = output
    answer["quality_score"] = candidate_quality
    answer["quality_dimensions"] = candidate_quality["dimensions"]
    answer["result_card"] = build_result_card(
        intent=answer.get("intent") or "unknown",
        scenario=answer.get("scenario") or "经营问答",
        answer=output,
        evidence=answer.get("evidence") or [],
        confidence=answer.get("confidence") or "low",
        conflicts=answer.get("conflicts") or [],
        needs_review=bool(answer.get("needs_review", True)),
    )
    answer["model_generation"] = result
    if not original_answer:
        answer["reasoning"] = [*answer.get("reasoning", []), "模型在证据约束下生成了可用答案。"]
    return answer


def _has_any(text: str, terms: list[str]) -> bool:
    return any(term in text for term in terms)


def _training_dimension(key: str, name: str, score: int, detail: str) -> dict[str, Any]:
    bounded_score = max(0, min(100, score))
    return {
        "key": key,
        "name": name,
        "score": bounded_score,
        "passed": bounded_score >= 75,
        "detail": detail,
    }


def _score_training_accuracy(answer: str) -> dict[str, Any]:
    product_terms = ["清泡", "调泡", "补泡", "养泡"]
    mentioned = [term for term in product_terms if term in answer]
    role_terms = ["基础放松", "基础", "放松", "调理", "针对", "恢复", "疲劳", "保养", "长期"]
    score = 20 + len(mentioned) * 12
    if len(mentioned) >= 4:
        score += 18
    if _has_any(answer, role_terms):
        score += 14
    if "便宜" in answer and "贵" in answer and not _has_any(answer, ["基础", "状态", "调理", "恢复", "保养"]):
        score -= 24
    detail = (
        "能区分清泡、调泡、补泡、养泡，并表达基础放松、状态调理、恢复和保养。"
        if score >= 75
        else "没有讲清清泡、调泡、补泡、养泡的差异，容易被顾客理解成价格差。"
    )
    return _training_dimension("accuracy", "产品准确性", score, detail)


def _score_training_discovery(answer: str) -> dict[str, Any]:
    discovery_terms = ["问", "了解", "最近", "睡眠", "疲劳", "累", "手脚凉", "压力", "状态", "需求", "情况"]
    hit_count = sum(1 for term in discovery_terms if term in answer)
    score = min(100, hit_count * 16)
    if _has_any(answer, ["睡眠", "疲劳", "手脚凉", "压力"]) and _has_any(answer, ["问", "了解", "最近", "情况"]):
        score = max(score, 95)
    detail = (
        "先探询顾客近期状态，再推荐泡脚方。"
        if score >= 75
        else "缺少需求探询，员工应先问睡眠、疲劳、手脚凉、压力等状态。"
    )
    return _training_dimension("discovery", "需求探询", score, detail)


def _score_training_compliance(answer: str) -> tuple[dict[str, Any], list[str]]:
    correction_points: list[str] = []
    score = 100
    overclaim_terms = ["治愈", "治好", "保证", "肯定有效", "一定有效", "药到病除", "根治"]
    treatment_claim = (
        "治疗" in answer
        and not _has_any(answer, ["不承诺治疗", "不能承诺治疗", "不说治疗", "不可说治疗", "不讲治疗"])
    )
    insomnia_claim = "失眠" in answer and not _has_any(answer, ["不承诺", "不能承诺", "不说", "不可说", "不讲"])
    if treatment_claim or insomnia_claim or _has_any(answer, overclaim_terms):
        score = 20
        correction_points.append("不能承诺治疗、治愈、保证或肯定有效，只能表达放松、改善体验和状态建议。")
    if "排毒" in answer:
        score = min(score, 60)
        correction_points.append("不要使用排毒等容易夸大功效的表达。")
    detail = (
        "已避开治疗、治愈、保证有效等高风险表达。"
        if score >= 75
        else "存在治疗、保证或绝对化承诺，必须复训。"
    )
    return _training_dimension("compliance", "合规边界", score, detail), correction_points


def _score_training_conversion(answer: str) -> dict[str, Any]:
    score = 45
    if _has_any(answer, ["根据", "适合", "建议", "推荐", "针对"]):
        score += 18
    if _has_any(answer, ["睡眠", "疲劳", "手脚凉", "压力", "状态", "需求"]):
        score += 22
    if _has_any(answer, ["清泡", "调泡", "补泡", "养泡"]) and _has_any(answer, ["放松", "调理", "恢复", "保养"]):
        score += 15
    if "便宜" in answer and "贵" in answer and not _has_any(answer, ["适合", "建议", "状态", "需求"]):
        score -= 35
    detail = (
        "能把顾客状态连接到推荐理由。"
        if score >= 75
        else "推荐逻辑偏价格解释，缺少按顾客状态转化。"
    )
    return _training_dimension("conversion", "推荐转化", score, detail)


def _score_training_clarity(answer: str) -> dict[str, Any]:
    length = len(answer.strip())
    score = 45
    if length >= 45:
        score += 20
    if length >= 80:
        score += 10
    if _has_any(answer, ["先", "再", "清泡", "调泡", "补泡", "养泡"]):
        score += 15
    if "。" in answer or "；" in answer:
        score += 10
    detail = "表达清楚，能直接作为训练示例。" if score >= 75 else "表达过短或结构不清，员工复述后仍可能跑偏。"
    return _training_dimension("clarity", "表达清晰度", score, detail)


_TRAINING_SAFETY_TERMS = [
    "治疗失眠",
    "治疗",
    "治愈",
    "治好",
    "根治",
    "保证有效",
    "保证",
    "肯定有效",
    "一定有效",
    "包好",
    "当天见效",
    "药到病除",
    "排毒治病",
    "稳赚",
    "保证回本",
    "一定回本",
    "零风险",
]
_TRAINING_SAFETY_NEGATIONS = [
    "不",
    "不能",
    "不得",
    "不要",
    "禁止",
    "避免",
    "不可",
    "不说",
    "不讲",
    "不承诺",
    "不能承诺",
    "不得承诺",
    "不要承诺",
    "禁用",
]
_TRAINING_SAFETY_CORRECTION = "不能承诺治疗、治愈、保证或肯定有效，只能表达放松、改善体验和状态建议。"


def _training_term_is_negated(text: str, index: int, term: str) -> bool:
    before = text[max(0, index - 12) : index]
    around = text[max(0, index - 12) : index + len(term) + 4]
    return any(marker in before or marker in around for marker in _TRAINING_SAFETY_NEGATIONS)


def _training_safety_violations(text: str) -> list[str]:
    normalized = (text or "").strip()
    if not normalized:
        return []
    hits: list[str] = []
    for term in _TRAINING_SAFETY_TERMS:
        start = 0
        while True:
            index = normalized.find(term, start)
            if index < 0:
                break
            if not _training_term_is_negated(normalized, index, term):
                hits.append(term)
                break
            start = index + len(term)
    return hits


def _default_store_staff_standard_script() -> str:
    return (
        "您好，我先了解一下您最近的状态：睡眠怎么样，身体会不会容易累，手脚有没有发凉，压力大不大？"
        "如果只是想放松，清泡就够用；如果最近状态比较紧、睡眠或疲劳感明显，可以选调泡，做更有针对性的放松调理体验；"
        "如果最近比较累，补泡会更适合恢复感；如果想长期保养，养泡更适合持续养护。"
        "我们主要帮您做放松、体验和状态调理建议，不替代医疗治疗。"
    )


_TRAINING_DIMENSION_NAMES = {
    "accuracy": "产品准确性",
    "discovery": "需求探询",
    "compliance": "合规边界",
    "conversion": "推荐转化",
    "clarity": "表达清晰度",
}


def _training_level_for_score(score: int) -> tuple[str, str, bool]:
    if score >= 90:
        level = "excellent"
    elif score >= 75:
        level = "pass"
    else:
        level = "retrain"
    level_label = {"excellent": "优秀", "pass": "通过", "retrain": "需复训"}[level]
    return level, level_label, level == "retrain"


def _rule_training_dimensions_and_corrections(employee_answer: str) -> tuple[list[dict[str, Any]], list[str]]:
    dimensions: list[dict[str, Any]] = [
        _score_training_accuracy(employee_answer),
        _score_training_discovery(employee_answer),
    ]
    compliance_dimension, correction_points = _score_training_compliance(employee_answer)
    dimensions.extend(
        [
            compliance_dimension,
            _score_training_conversion(employee_answer),
            _score_training_clarity(employee_answer),
        ]
    )
    dimension_scores = {item["key"]: int(item["score"]) for item in dimensions}
    if dimension_scores["accuracy"] < 75:
        correction_points.append("不要把调泡、补泡、养泡讲成只是更贵；要讲清各自适用状态和价值。")
    if dimension_scores["discovery"] < 75:
        correction_points.append("推荐前先问顾客最近睡眠、疲劳、手脚凉、压力或身体状态。")
    if dimension_scores["conversion"] < 75:
        correction_points.append("用顾客状态推荐泡脚方，不要只从价格高低解释。")
    if dimension_scores["clarity"] < 75:
        correction_points.append("话术要短、清楚、可复述，建议控制在 30 秒内。")
    return dimensions, correction_points


def _replace_dimension(dimensions: list[dict[str, Any]], replacement: dict[str, Any]) -> list[dict[str, Any]]:
    replaced = False
    next_dimensions: list[dict[str, Any]] = []
    for item in dimensions:
        if item.get("key") == replacement["key"]:
            next_dimensions.append(replacement)
            replaced = True
        else:
            next_dimensions.append(item)
    if not replaced:
        next_dimensions.append(replacement)
    return next_dimensions


def _append_unique(items: list[str], value: str) -> list[str]:
    if value and value not in items:
        items.append(value)
    return items


def _apply_training_safety_gate(result: dict[str, Any], request: TrainingEvaluateRequest) -> dict[str, Any]:
    employee_violations = _training_safety_violations(request.employee_answer)
    standard_violations = _training_safety_violations(result.get("standard_script") or "")
    final_standard_script = str(result.get("standard_script") or "")
    standard_script_rewritten = False
    if standard_violations:
        final_standard_script = _default_store_staff_standard_script()
        result["standard_script"] = final_standard_script
        standard_script_rewritten = True
        if isinstance(result.get("answer_card_draft"), dict):
            result["answer_card_draft"]["answer"] = final_standard_script
        correction_package = result.get("correction_package") or {}
        package_draft = correction_package.get("answer_card_draft")
        if isinstance(package_draft, dict):
            package_draft["answer"] = final_standard_script
        if isinstance(result.get("role_versions"), dict):
            result["role_versions"]["store_staff"] = final_standard_script
        if standard_violations and not employee_violations:
            _append_unique(
                result.setdefault("correction_points", []),
                "AI生成的标准话术包含高风险表达，已替换为安全标准话术，需运营负责人复核后再沉淀。",
            )

    safety_gate = {
        "passed": not employee_violations,
        "employee_claim_violations": employee_violations,
        "standard_script_violations": standard_violations,
        "standard_script_rewritten": standard_script_rewritten,
    }
    result.setdefault("training_judgment", {})["safety_gate"] = safety_gate
    if not employee_violations:
        return result

    violation_text = "、".join(employee_violations)
    correction = f"员工话术包含高风险承诺：{violation_text}。{_TRAINING_SAFETY_CORRECTION}"
    _append_unique(result.setdefault("correction_points", []), correction)
    result["corrections"] = result["correction_points"]
    result["dimensions"] = _replace_dimension(
        result.get("dimensions") or [],
        _training_dimension(
            "compliance",
            "合规边界",
            20,
            f"员工话术包含高风险承诺：{violation_text}，必须复训。",
        ),
    )
    result["score"] = min(int(result.get("score") or 0), 60)
    result["level"] = "retrain"
    result["level_label"] = "需复训"
    result["needs_retrain"] = True
    result["answer_card_draft"] = None
    result["review_status"] = "待复训"
    result["confidence"] = "high"
    retraining_task = result.get("retraining_task") or {}
    retraining_actions = retraining_task.get("actions") or []
    result["next_actions"] = retraining_actions
    result["reasoning"] = [item.get("detail") for item in result["dimensions"] if item.get("detail")]
    result["answer"] = (
        "训练结果：需要复训。员工话术出现治疗、保证有效或绝对化承诺，不能对顾客这样表达。"
        "正确做法是先问睡眠、疲劳、手脚凉、压力，再讲清泡基础放松、调泡按状态调理、补泡强调恢复感、养泡强调长期保养。"
    )
    result_card = result.get("result_card") or {}
    result_card["usable_answer"] = result["answer"]
    result_card["business_result"] = f"员工话术评分 {result['score']} 分，等级：需复训。"
    result_card["stability_level"] = "review_required"
    quality_gates = []
    for item in result["dimensions"]:
        quality_gates.append(
            {
                "name": item["name"],
                "passed": bool(item["passed"]),
                "detail": f"{item['score']} 分：{item['detail']}",
            }
        )
    result_card["quality_gates"] = quality_gates
    result["result_card"] = result_card
    correction_package = result.get("correction_package") or {}
    correction_package["failure_type"] = "training_gap"
    correction_package["recommended_actions"] = retraining_actions
    result["correction_package"] = correction_package
    workbench_intake = result.get("workbench_intake") or {}
    workbench_intake["next_actions"] = retraining_actions
    workbench_intake["memory_action"] = "违规话术进入复训任务；复训通过前不能沉淀为权威答案卡。"
    result["workbench_intake"] = workbench_intake
    return result


def _attach_training_curriculum(result: dict[str, Any], request: TrainingEvaluateRequest) -> dict[str, Any]:
    employee_id = request.employee_id.strip() or "employee-local"
    capability_profile = build_training_capability_profile(result, employee_id=employee_id)
    adaptive_retrain_plan = build_adaptive_retrain_plan(result, employee_id=employee_id)
    result["capability_profile"] = capability_profile
    result["adaptive_retrain_plan"] = adaptive_retrain_plan
    result["operating_metric_links"] = adaptive_retrain_plan.get("operating_metric_links") or []
    result["follow_up_questions"] = [
        item.get("customer_question") or ""
        for item in adaptive_retrain_plan.get("next_questions") or []
        if item.get("customer_question")
    ] or result.get("follow_up_questions") or []
    result["next_actions"] = result.get("next_actions") or []
    if result.get("needs_retrain"):
        result["next_actions"] = [
            f"优先复训：{capability_profile.get('summary') or '基础话术'}",
            *result["next_actions"],
        ]
    result_card = result.get("result_card") or {}
    gates = result_card.get("quality_gates") or []
    gates.append(
        {
            "name": "能力等级",
            "passed": capability_profile.get("level") != "newbie" or not result.get("needs_retrain"),
            "detail": f"{capability_profile.get('level')} · {capability_profile.get('summary')}",
        }
    )
    result_card["quality_gates"] = gates
    result["result_card"] = result_card
    workbench_intake = result.get("workbench_intake") or {}
    workbench_intake["team_value"] = [
        "训练团队",
        "能力等级",
        "自适应复训",
        "经营结果关联",
    ]
    workbench_intake["next_actions"] = result.get("next_actions") or []
    result["workbench_intake"] = workbench_intake
    return result


def _build_training_result(
    request: TrainingEvaluateRequest,
    *,
    dimensions: list[dict[str, Any]],
    correction_points: list[str],
    standard_script: str | None = None,
    usable_answer_override: str | None = None,
    judgment: dict[str, Any] | None = None,
) -> dict[str, Any]:
    employee_answer = request.employee_answer.strip()
    dimension_scores = {item["key"]: int(item["score"]) for item in dimensions}
    score = round(sum(dimension_scores.values()) / len(dimension_scores)) if dimensions else 0
    if judgment and isinstance(judgment.get("score"), int):
        score = max(0, min(100, int(judgment["score"])))
    level, level_label, needs_retrain = _training_level_for_score(score)
    standard_script = standard_script or (employee_answer if level == "excellent" else _default_store_staff_standard_script())
    answer_card_draft = {
        "question_pattern": _normalize_question_pattern(request.customer_question or request.training_item),
        "intent": "product_system",
        "audience": "store_staff",
        "answer": standard_script,
        "reasoning": [
            "来自门店员工训练评估。",
            "通过产品准确性、需求探询、合规边界、推荐转化和表达清晰度五项评分。",
        ],
        "evidence": [],
        "corrections": correction_points,
        "next_actions": ["运营负责人复核", "通过后纳入门店培训标准话术", "沉淀为权威答案卡"],
        "status": "draft",
        "source_answer_id": None,
    }
    retraining_task = {
        "title": f"{request.training_item.strip() or '门店话术'}复训",
        "owner": "店长/运营负责人",
        "deadline": "下次班前会",
        "actions": [
            "删除治疗、保证有效、只是更贵等错误表达",
            "按顾客状态做一次追问演练",
            "用清泡、调泡、补泡、养泡四句话重新录制话术",
            "店长按五项评分表复核",
        ],
    }
    follow_up_questions = [
        f"{request.customer_question.strip() or '顾客问：清泡调补养有什么区别？'} 请用 30 秒重新回答，先问状态，再推荐。",
        "顾客说最近很累但只想随便泡泡，你怎么引导？",
        "顾客问能不能治疗失眠，你怎么合规表达？",
    ]
    usable_answer = (
        "训练结果：优秀，可作为答案卡候选。保留“先问顾客状态，再讲清泡基础放松、调泡针对状态、补泡恢复感、养泡长期保养，并避免治疗承诺”的结构。"
        if level == "excellent"
        else "训练结果：需要复训。先删掉“治疗失眠、肯定有效、只是更贵”等表达；正确做法是先问睡眠、疲劳、手脚凉、压力，再讲清泡基础放松、调泡按状态调理、补泡强调恢复感、养泡强调长期保养。"
        if needs_retrain
        else "训练结果：通过。建议继续压缩话术，把顾客状态和推荐理由说得更直接。"
    )
    if usable_answer_override:
        usable_answer = usable_answer_override
    training_judgment = {
        "mode": "ai" if judgment else "rule_fallback",
        "model_reason": (judgment or {}).get("model_reason") or "not_used",
    }
    result = {
        "version": "hxy-training-evaluation.v1",
        "status": "evaluated",
        "training_item": request.training_item.strip() or "清泡调补养门店推荐话术",
        "customer_question": request.customer_question.strip() or "顾客问：清泡调补养有什么区别？",
        "employee_answer": employee_answer,
        "scenario": request.scenario.strip() or "门店员工培训",
        "role": request.role.strip() or "门店员工",
        "intent": "training",
        "audience": "store_staff",
        "score": score,
        "level": level,
        "level_label": level_label,
        "dimensions": dimensions,
        "needs_retrain": needs_retrain,
        "correction_points": correction_points,
        "follow_up_questions": follow_up_questions,
        "standard_script": standard_script,
        "training_judgment": training_judgment,
        "retraining_task": retraining_task,
        "answer_card_draft": answer_card_draft if level == "excellent" else None,
        "correction_package": {
            "version": "hxy-training-correction.v1",
            "failure_type": "training_gap",
            "target": f"{request.training_item.strip() or '门店话术'}复训并复核后替代旧训练口径",
            "normalized_question": _normalize_question_pattern(request.customer_question or request.training_item),
            "recommended_reviewer": "运营负责人",
            "recommended_actions": retraining_task["actions"],
            "answer_card_draft": answer_card_draft,
        },
        "answer": usable_answer,
        "usage": "用于门店员工训练、店长验收和优秀话术沉淀。",
        "applicable_scenarios": ["门店员工培训", "店长验收", "标准话术沉淀"],
        "role_versions": {
            "store_staff": answer_card_draft["answer"],
            "store_manager": "按五项评分表验收员工话术，低于 75 分进入复训，高于 90 分提交为答案卡候选。",
        },
        "forbidden_terms": ["治疗失眠", "治愈", "保证有效", "肯定有效", "只是更贵"],
        "review_status": "待复训" if needs_retrain else "待复核",
        "confidence": "high",
        "evidence": [],
        "sources": [],
        "reasoning": [item["detail"] for item in dimensions],
        "corrections": correction_points,
        "next_actions": retraining_task["actions"] if needs_retrain else answer_card_draft["next_actions"],
        "needs_review": True,
        "result_card": {
            "result_type": "门店训练评分卡",
            "usable_answer": usable_answer,
            "business_result": f"员工话术评分 {score} 分，等级：{level_label}。",
            "risk_boundary": "训练反馈只用于内部培训；对顾客不得承诺治疗、治愈、保证或绝对效果。",
            "quality_gates": [
                {
                    "name": item["name"],
                    "passed": bool(item["passed"]),
                    "detail": f"{item['score']} 分：{item['detail']}",
                }
                for item in dimensions
            ],
            "review_owner": "运营负责人",
            "stability_level": "review_required" if needs_retrain else "candidate",
        },
        "workbench_intake": {
            "input_type": "training_script",
            "primary_workflow": "training_evaluation",
            "scenario": request.scenario.strip() or "门店员工培训",
            "team_value": ["训练团队", "统一话术", "纠偏复训", "沉淀优秀样本"],
            "next_actions": retraining_task["actions"] if needs_retrain else answer_card_draft["next_actions"],
            "memory_action": "优秀话术经复核后沉淀为权威答案卡；低分话术进入复训任务。",
        },
    }
    result = _apply_training_safety_gate(result, request)
    return _attach_training_curriculum(result, request)


def evaluate_training_script(request: TrainingEvaluateRequest) -> dict[str, Any]:
    dimensions, correction_points = _rule_training_dimensions_and_corrections(request.employee_answer.strip())
    return _build_training_result(request, dimensions=dimensions, correction_points=correction_points)


def _training_evaluation_messages(request: TrainingEvaluateRequest, rule_result: dict[str, Any]) -> list[dict[str, str]]:
    system = (
        "你是荷小悦门店员工训练评分官。你的任务是判断员工话术是否能在真实门店对顾客使用，"
        "不要只按关键词命中打分，要根据语义、业务意图、合规边界和顾客沟通效果综合判断。"
        "必须只返回 JSON，不要 Markdown，不要解释 JSON 以外的内容。"
        "JSON 字段：score(int 0-100), level(excellent/pass/retrain), dimensions(list), "
        "correction_points(list), standard_script(string), usable_answer(string)。"
        "dimensions 必须包含 accuracy, discovery, compliance, conversion, clarity 五项，每项包含 key, name, score, detail。"
        "standard_script 必须是员工可以直接对顾客说的话，不要写“建议、先问顾客、不要”等内部教练指令。"
        "不得承诺治疗、治愈、保证有效、肯定有效、稳赚或绝对结果。"
    )
    user = "\n".join(
        [
            f"训练项目：{request.training_item.strip() or '清泡调补养门店推荐话术'}",
            f"顾客问题：{request.customer_question.strip() or '顾客问：清泡调补养有什么区别？'}",
            f"员工话术：{request.employee_answer.strip()}",
            f"规则兜底评分：{rule_result.get('score')} 分，仅供校准，不得机械照搬。",
            "评分标准：",
            "1. 产品准确性：是否理解清泡、调泡、补泡、养泡的真实差异，而不是只讲价格。",
            "2. 需求探询：是否先理解顾客状态、睡眠、疲劳、手脚凉、压力等信息。",
            "3. 合规边界：是否避开治疗、治愈、保证有效等表达。",
            "4. 推荐转化：是否能把顾客状态连接到合适方案。",
            "5. 表达清晰度：是否短、清楚、顾客听得懂、员工可复述。",
        ]
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _extract_json_object(text: str) -> dict[str, Any] | None:
    stripped = (text or "").strip()
    if not stripped:
        return None
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, flags=re.DOTALL)
    candidate = fenced.group(1) if fenced else stripped
    if not candidate.startswith("{"):
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start >= 0 and end > start:
            candidate = candidate[start : end + 1]
    try:
        parsed = json.loads(candidate)
    except Exception:
        return None
    return parsed if isinstance(parsed, dict) else None


def _bounded_int(value: Any, default: int = 0) -> int:
    try:
        return max(0, min(100, int(value)))
    except (TypeError, ValueError):
        return default


def _training_judgment_from_model_generation(generation: dict[str, Any]) -> dict[str, Any] | None:
    if not generation.get("used_model"):
        return None
    payload = _extract_json_object(str(generation.get("output") or ""))
    if not payload:
        return None
    raw_dimensions = payload.get("dimensions")
    if not isinstance(raw_dimensions, list):
        return None
    by_key = {str(item.get("key") or ""): item for item in raw_dimensions if isinstance(item, dict)}
    dimensions: list[dict[str, Any]] = []
    for key, name in _TRAINING_DIMENSION_NAMES.items():
        item = by_key.get(key)
        if not item:
            return None
        dimensions.append(
            _training_dimension(
                key,
                str(item.get("name") or name),
                _bounded_int(item.get("score")),
                str(item.get("detail") or "AI 已完成该项判断。"),
            )
        )
    standard_script = str(payload.get("standard_script") or "").strip()
    if not standard_script:
        return None
    raw_corrections = payload.get("correction_points") or []
    correction_points = [str(item).strip() for item in raw_corrections if str(item).strip()] if isinstance(raw_corrections, list) else []
    usable_answer = str(payload.get("usable_answer") or "").strip()
    return {
        "score": _bounded_int(payload.get("score")),
        "dimensions": dimensions,
        "correction_points": correction_points,
        "standard_script": standard_script,
        "usable_answer": usable_answer,
        "model_reason": generation.get("reason") or "ok",
        "model_usage": generation.get("usage") or {},
    }


def _evaluate_training_with_model(
    *,
    model_router: Any,
    request: TrainingEvaluateRequest,
    rule_result: dict[str, Any],
) -> dict[str, Any]:
    try:
        generation = model_router.generate(
            "training_evaluation",
            messages=_training_evaluation_messages(request, rule_result),
            metadata={
                "scenario": request.scenario.strip() or "门店员工培训",
                "role": request.role.strip() or "门店员工",
                "training_item": request.training_item.strip() or "清泡调补养门店推荐话术",
            },
        )
    except Exception as exc:
        rule_result["training_judgment"] = {
            "mode": "rule_fallback",
            "model_reason": f"model_error:{type(exc).__name__}",
        }
        return rule_result

    judgment = _training_judgment_from_model_generation(generation)
    if not judgment:
        rule_result["training_judgment"] = {
            "mode": "rule_fallback",
            "model_reason": generation.get("reason") or "invalid_model_output",
        }
        return rule_result
    return _build_training_result(
        request,
        dimensions=judgment["dimensions"],
        correction_points=judgment["correction_points"],
        standard_script=judgment["standard_script"],
        usable_answer_override=judgment["usable_answer"],
        judgment=judgment,
    )


def build_correction_package(question: str, rating: str, note: str) -> dict[str, Any]:
    normalized_question = _normalize_question_pattern(question)
    failure_type = "incorrect_answer" if rating == "incorrect" else "incomplete_answer"
    target = "修正答案并沉淀权威答案卡" if rating == "incorrect" else "补充缺失信息并更新答案卡草稿"
    review_notes = [note] if note else []
    error_type = _correction_error_type(question, note, rating)
    missing_information = _correction_missing_information(question, note)
    recommended_reviewer = _correction_reviewer(question)
    replacement_action = "复核通过后替代旧答案；旧答案保留历史记录但不再作为默认口径。"
    actions = [
        "复核原答案和证据来源是否匹配",
        "补充或替换权威资料后重新提问",
        "将确认后的结论沉淀为答案卡草稿",
        "复核通过后替代旧答案",
    ]
    if rating == "incorrect":
        actions.insert(0, "定位错误结论，标注正确说法")
    else:
        actions.insert(0, "列出缺失字段、适用场景或证据口径")
    corrections = review_notes[:]
    if error_type == "overclaim_or_wrong_conclusion":
        corrections.append("不能承诺稳赚、保证回本、治疗或绝对效果；必须补充风险边界。")
    return {
        "version": "hxy-correction-package.v1",
        "failure_type": failure_type,
        "error_type": error_type,
        "target": target,
        "normalized_question": normalized_question,
        "review_notes": review_notes,
        "missing_information": missing_information,
        "recommended_reviewer": recommended_reviewer,
        "replacement_action": replacement_action,
        "recommended_actions": actions,
        "answer_card_draft": {
            "question_pattern": normalized_question,
            "intent": "unknown",
            "audience": "general",
            "answer": "",
            "reasoning": [],
            "evidence": [],
            "corrections": corrections,
            "next_actions": actions,
            "status": "draft",
            "source_answer_id": None,
        },
    }


def _correction_error_type(question: str, note: str, rating: str) -> str:
    text = f"{question} {note}"
    if any(term in text for term in ["保证", "稳赚", "一定回本", "治疗", "治愈", "绝对", "承诺"]):
        return "overclaim_or_wrong_conclusion"
    if rating == "needs_work" or any(term in text for term in ["缺少", "不完整", "没说", "需要补"]):
        return "missing_context_or_incomplete_answer"
    if any(term in text for term in ["冲突", "不一致", "新旧"]):
        return "knowledge_conflict"
    return "wrong_or_unverified_answer"


def _correction_missing_information(question: str, note: str) -> list[str]:
    text = f"{question} {note}"
    missing: list[str] = []
    if any(term in text for term in ["回本", "招商", "加盟", "单店模型"]):
        missing.extend(["真实门店数据", "投资成本", "客流来源", "客单价", "复购率", "风险边界"])
    if any(term in text for term in ["定位", "核爆点", "品牌"]):
        missing.extend(["权威定位原文", "适用场景", "外部话术边界"])
    if any(term in text for term in ["清泡", "调补养", "泡脚方", "产品"]):
        missing.extend(["产品定义", "适用人群", "禁用表达", "门店话术"])
    if "风险边界" in text and "风险边界" not in missing:
        missing.append("风险边界")
    if not missing:
        missing.append("权威资料或业务负责人复核结论")
    deduped: list[str] = []
    for item in missing:
        if item not in deduped:
            deduped.append(item)
    return deduped


def _correction_reviewer(question: str) -> str:
    if any(term in question for term in ["招商", "加盟", "回本", "单店模型"]):
        return "招商负责人"
    if any(term in question for term in ["清泡", "调补养", "泡脚方", "产品"]):
        return "产品负责人"
    if any(term in question for term in ["员工", "门店", "SOP", "话术"]):
        return "运营负责人"
    if any(term in question for term in ["定位", "核爆点", "品牌"]):
        return "创始人/品牌负责人"
    return "业务负责人"


def _review_task_dedupe_key(task: dict[str, Any]) -> str:
    reason = str(task.get("reason") or "")
    payload = task.get("payload_json") or {}
    if isinstance(payload, dict):
        reason = str(payload.get("reason") or reason)
        correction_package = payload.get("correction_package") or {}
        if isinstance(correction_package, dict):
            normalized = correction_package.get("normalized_question")
            if normalized:
                return f"{normalized}:{reason}" if reason else str(normalized)
    normalized_question = _normalize_question_pattern(str(task.get("question") or ""))
    return f"{normalized_question}:{reason}" if reason else normalized_question


def dedupe_review_tasks(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        key = _review_task_dedupe_key(item)
        if not key:
            key = str(item.get("task_id") or "")
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _read_json_file(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _benchmark_status_from_report(report: dict[str, Any] | None) -> dict[str, Any]:
    if not report:
        return {
            "version": "hxy-brain-benchmark-status.v1",
            "status": "missing",
            "summary": {"case_count": 0, "passed_count": 0, "failed_count": 0, "pass_rate": 0.0},
            "next_actions": [
                "运行 scripts/run-hxy-brain-benchmark.py 生成 knowledge/reports/benchmark-latest.json。",
                "用真实答案运行 benchmark，和纯 RAG / 资料工作台做对照。",
            ],
        }
    pass_rate = float(report.get("pass_rate") or 0)
    min_pass_rate = float((report.get("failure_thresholds") or {}).get("min_pass_rate") or 0.85)
    next_actions = []
    if pass_rate < min_pass_rate:
        next_actions.append("Benchmark 通过率低于阈值，优先处理失败 case。")
    next_actions.append("保留每次 benchmark report，作为 HXYOS 是否有效的证伪证据。")
    return {
        "version": "hxy-brain-benchmark-status.v1",
        "status": "ready",
        "summary": {
            "case_count": int(report.get("case_count") or 0),
            "passed_count": int(report.get("passed_count") or 0),
            "failed_count": int(report.get("failed_count") or 0),
            "pass_rate": pass_rate,
            "min_pass_rate": min_pass_rate,
        },
        "next_actions": next_actions,
        "report": report,
    }


def _compiler_status_from_report(report: dict[str, Any] | None) -> dict[str, Any]:
    if not report:
        return {
            "version": "hxy-knowledge-compiler-status.v1",
            "status": "missing",
            "summary": {
                "extract_count": 0,
                "claim_count": 0,
                "approved_count": 0,
                "graph_node_count": 0,
                "graph_edge_count": 0,
            },
            "next_actions": [
                "将 HXY 原始资料放入 knowledge/raw/inbox。",
                "运行 scripts/compile-hxy-knowledge.py 生成 knowledge/wiki 和 compiler report。",
            ],
        }
    next_actions = [
        "编译产物默认只能作为 reference/current_candidate，复核后才允许 approved。",
        "运行知识治理 lint，检查缺来源、缺负责人、过度承诺和生命周期错误。",
    ]
    if int(report.get("extract_count") or 0) == 0:
        next_actions.insert(0, "当前没有可编译资料，先把 .md/.txt 原始资料放入 knowledge/raw/inbox。")
    return {
        "version": "hxy-knowledge-compiler-status.v1",
        "status": "ready",
        "summary": {
            "extract_count": int(report.get("extract_count") or 0),
            "claim_count": int(report.get("claim_count") or 0),
            "approved_count": int(report.get("approved_count") or 0),
            "graph_node_count": int(report.get("graph_node_count") or 0),
            "graph_edge_count": int(report.get("graph_edge_count") or 0),
        },
        "next_actions": next_actions,
        "report": report,
    }


def _compiler_review_queue_from_payload(payload: dict[str, Any] | None, *, limit: int) -> dict[str, Any]:
    if not payload:
        return {
            "version": "hxy-review-queue.v1",
            "status": "missing",
            "count": 0,
            "items": [],
            "next_actions": ["运行知识编译器生成 knowledge/wiki/review-queue.json。"],
        }
    items = []
    for item in payload.get("items") or []:
        if not isinstance(item, dict):
            continue
        public = dict(item)
        public.setdefault("status", "needs_review")
        public["official_use_allowed"] = False
        public["requires_human_review"] = True
        items.append(public)
    return {
        "version": "hxy-review-queue.v1",
        "status": "ready",
        "count": len(items[:limit]),
        "total": len(items),
        "reviewable_claim_count": int(payload.get("reviewable_claim_count") or len(items)),
        "noise_claim_count": int(payload.get("noise_claim_count") or 0),
        "group_counts": payload.get("group_counts") or {},
        "items": items[:limit],
        "authority_rule": "review_queue_items_are_candidates_not_approved_knowledge",
    }


def _compiler_claim_triage_from_payload(payload: dict[str, Any] | None, *, limit: int) -> dict[str, Any]:
    if not payload:
        return {
            "version": "hxy-claim-triage.v1",
            "status": "missing",
            "count": 0,
            "total": 0,
            "total_claim_count": 0,
            "noise_claim_count": 0,
            "duplicate_claim_count": 0,
            "unique_reviewable_claim_count": 0,
            "cluster_count": 0,
            "selected_count": 0,
            "items": [],
            "official_use_allowed": False,
            "requires_human_review": True,
            "next_actions": ["运行知识编译器生成 knowledge/wiki/claim-triage.json。"],
            "authority_rule": "claim_triage_items_are_prioritized_candidates_not_approved_knowledge",
        }
    items = []
    for item in payload.get("items") or []:
        if not isinstance(item, dict):
            continue
        public = dict(item)
        public.setdefault("status", "needs_review")
        public["official_use_allowed"] = False
        public["requires_human_review"] = True
        items.append(public)
    return {
        "version": payload.get("version") or "hxy-claim-triage.v1",
        "status": payload.get("status") or ("ready" if items else "empty"),
        "count": len(items[:limit]),
        "total": len(items),
        "total_claim_count": int(payload.get("total_claim_count") or 0),
        "noise_claim_count": int(payload.get("noise_claim_count") or 0),
        "duplicate_claim_count": int(payload.get("duplicate_claim_count") or 0),
        "unique_reviewable_claim_count": int(payload.get("unique_reviewable_claim_count") or 0),
        "cluster_count": int(payload.get("cluster_count") or 0),
        "selected_count": int(payload.get("selected_count") or len(items)),
        "items": items[:limit],
        "official_use_allowed": False,
        "requires_human_review": True,
        "authority_rule": "claim_triage_items_are_prioritized_candidates_not_approved_knowledge",
    }


def _compiler_core_decision_topics_from_payload(payload: dict[str, Any] | None, *, limit: int) -> dict[str, Any] | None:
    if not payload:
        return None
    items = []
    for item in payload.get("items") or []:
        if not isinstance(item, dict):
            continue
        public = {
            "version": item.get("version") or "hxy-core-decision-topic.v1",
            "topic_id": item.get("topic_id") or "",
            "topic_key": item.get("topic_key") or "",
            "title": item.get("title") or "",
            "decision_question": item.get("decision_question") or "",
            "why_it_matters": item.get("why_it_matters") or "",
            "next_action": item.get("next_action") or "",
            "review_owner": item.get("review_owner") or "",
            "priority": item.get("priority") or "P1",
            "evidence_count": int(item.get("evidence_count") or 0),
            "source_samples": [_source_label(source) for source in (item.get("source_samples") or [])],
            "source_classes": list(item.get("source_classes") or []),
            "official_use_allowed": False,
            "requires_human_review": True,
        }
        items.append(public)
    public_items = items[:limit]
    return {
        "version": "hxy-review-topics.v1",
        "source": "core_decision_topics",
        "status": payload.get("status") or ("ready" if items else "empty"),
        "count": len(public_items),
        "total": int(payload.get("total_core_topic_count") or len(items)),
        "core_topic_count": int(payload.get("core_topic_count") or len(items)),
        "evidence_count": int(payload.get("evidence_count") or 0),
        "items": public_items,
        "raw_claims_hidden": True,
        "official_use_allowed": False,
        "requires_human_review": True,
        "authority_rule": payload.get("authority_rule")
        or "core_decision_topics_are_review_objects_claim_triage_is_machine_intermediate",
    }


def _compiler_topic_draft_assets_from_payload(payload: dict[str, Any] | None, *, limit: int) -> dict[str, Any]:
    if not payload:
        return {
            "version": "hxy-topic-draft-assets.v1",
            "status": "missing",
            "count": 0,
            "total": 0,
            "items": [],
            "official_use_allowed": False,
            "requires_human_review": True,
            "authority_rule": "draft_assets_are_not_approved_knowledge",
            "next_actions": ["运行知识编译器生成 knowledge/wiki/topic-draft-assets.json。"],
        }
    items = []
    for item in payload.get("items") or []:
        if not isinstance(item, dict):
            continue
        draft = item.get("draft") if isinstance(item.get("draft"), dict) else {}
        public = {
            "version": item.get("version") or "hxy-topic-draft-asset.v1",
            "asset_id": item.get("asset_id") or "",
            "topic_id": item.get("topic_id") or "",
            "topic_key": item.get("topic_key") or "",
            "asset_type": item.get("asset_type") or "evidence_task",
            "title": item.get("title") or "",
            "status": "needs_review",
            "priority": item.get("priority") or "P1",
            "review_owner": item.get("review_owner") or "",
            "decision_question": item.get("decision_question") or "",
            "draft": draft,
            "source_samples": [_source_label(source) for source in (item.get("source_samples") or [])],
            "official_use_allowed": False,
            "requires_human_review": True,
            "authority_rule": "draft_assets_are_not_approved_knowledge",
        }
        items.append(public)
    public_items = items[:limit]
    return {
        "version": "hxy-topic-draft-assets.v1",
        "status": payload.get("status") or ("ready" if items else "empty"),
        "count": len(public_items),
        "total": int(payload.get("total") or len(items)),
        "items": public_items,
        "official_use_allowed": False,
        "requires_human_review": True,
        "authority_rule": "draft_assets_are_not_approved_knowledge",
    }


def _compiler_topic_review_packets_from_payload(payload: dict[str, Any] | None, *, limit: int) -> dict[str, Any]:
    if not payload:
        return {
            "version": "hxy-topic-review-packets.v1",
            "status": "missing",
            "count": 0,
            "total": 0,
            "items": [],
            "official_use_allowed": False,
            "requires_human_review": True,
            "authority_rule": "review_packets_are_tasks_not_approval",
            "next_actions": ["运行知识编译器生成 knowledge/wiki/topic-review-packets.json。"],
        }
    items = []
    for item in payload.get("items") or []:
        if not isinstance(item, dict):
            continue
        public = {
            "version": item.get("version") or "hxy-topic-review-packet.v1",
            "packet_id": item.get("packet_id") or "",
            "asset_id": item.get("asset_id") or "",
            "topic_key": item.get("topic_key") or "",
            "asset_type": item.get("asset_type") or "evidence_task",
            "title": item.get("title") or "",
            "priority": item.get("priority") or "P1",
            "review_owner": item.get("review_owner") or "",
            "status": "open",
            "review_questions": list(item.get("review_questions") or []),
            "evidence_gaps": list(item.get("evidence_gaps") or []),
            "next_actions": list(item.get("next_actions") or []),
            "decision_options": list(item.get("decision_options") or []),
            "promotion_target": item.get("promotion_target") or "evidence_backlog",
            "blocked_actions": list(item.get("blocked_actions") or []),
            "source_samples": [_source_label(source) for source in (item.get("source_samples") or [])],
            "official_use_allowed": False,
            "requires_human_review": True,
            "authority_rule": "review_packets_are_tasks_not_approval",
        }
        items.append(public)
    public_items = items[:limit]
    return {
        "version": "hxy-topic-review-packets.v1",
        "status": payload.get("status") or ("ready" if items else "empty"),
        "count": len(public_items),
        "total": int(payload.get("total") or len(items)),
        "items": public_items,
        "official_use_allowed": False,
        "requires_human_review": True,
        "authority_rule": "review_packets_are_tasks_not_approval",
    }


def _compiler_topic_review_decisions_workflow_from_payloads(
    *,
    packet_payload: dict[str, Any] | None,
    stub_payload: dict[str, Any] | None,
    sample_payload: dict[str, Any] | None,
    decisions_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    packets = packet_payload if isinstance(packet_payload, dict) else {"version": "hxy-topic-review-packets.v1", "items": []}
    stub = stub_payload if isinstance(stub_payload, dict) else build_topic_review_decisions_stub(packets)
    sample = sample_payload if isinstance(sample_payload, dict) else build_topic_review_decisions_sample(stub)
    validation = validate_topic_review_decisions(packets, decisions_payload) if decisions_payload else None
    decision_count = int(stub.get("decision_count") or len(stub.get("items") or []))
    if not packet_payload:
        current_step = "missing_review_packets"
        next_action = "先运行知识编译器生成 topic-review-packets.json。"
    elif not decisions_payload:
        current_step = "awaiting_manual_decisions"
        next_action = "复制 sample 到 topic-review-decisions.json，由负责人填写人工判断后再做 preview 校验。"
    elif validation and not validation.get("valid"):
        current_step = "blocked_at_decision_validation"
        next_action = "修正 topic-review-decisions.json；ready_for_manual_approval 不是批准，不能发布。"
    elif validation and int(validation.get("manual_decision_count") or 0) <= 0:
        current_step = "blocked_at_empty_manual_decisions"
        next_action = "至少填写一条 needs_more_evidence、revise_draft、ready_for_manual_approval 或 reject。"
    else:
        current_step = "manual_decisions_ready_for_next_review"
        next_action = "进入下一步人工批准前检查；仍不能写入正式知识库。"
    return {
        "version": "hxy-topic-review-decisions-workflow.v1",
        "current_step": current_step,
        "decision_count": decision_count,
        "manual_decision_count": int((validation or {}).get("manual_decision_count") or 0),
        "pending_count": int((validation or {}).get("pending_count") or decision_count),
        "ready_for_manual_approval_count": int((validation or {}).get("ready_for_manual_approval_count") or 0),
        "stub": stub,
        "sample": sample,
        "validation": validation,
        "files": {
            "packets": "knowledge/wiki/topic-review-packets.json",
            "stub": "knowledge/wiki/topic-review-decisions.stub.json",
            "sample": "knowledge/wiki/topic-review-decisions.sample.json",
            "decisions": "knowledge/wiki/topic-review-decisions.json",
        },
        "next_action": next_action,
        "official_use_allowed": False,
        "publish_allowed": False,
        "write_to_database": False,
        "requires_human_review": True,
        "authority_rule": "topic_review_decisions_are_manual_records_not_approved_knowledge",
    }


REVIEW_TOPIC_DEFINITIONS: dict[str, dict[str, str]] = {
    "risk_boundary": {
        "title": "医疗与功效表达边界",
        "decision_question": "先判断：哪些表达必须禁用，哪些只能作为内部提醒，哪些可以转成员工标准话术？",
        "why_it_matters": "这会直接影响门头、海报、团购页、员工推荐和顾客投诉风险。",
        "next_action": "先复核禁用表达和标准话术，再决定是否进入正式答案卡。",
    },
    "employee_script": {
        "title": "员工对外话术边界",
        "decision_question": "先判断：员工面对功效、价格、项目选择问题时，能说到什么程度？",
        "why_it_matters": "员工说错一句，比后台知识库写错一页更危险。",
        "next_action": "把可说、慎说、不能说拆成训练题和前台标准回答。",
    },
    "brand_positioning": {
        "title": "品牌定位与主推表达",
        "decision_question": "先判断：这些说法能不能代表荷小悦，而不是普通足疗、理疗或高端 SPA？",
        "why_it_matters": "定位口径会进入门头、菜单、开业内容和员工介绍。",
        "next_action": "只保留能被顾客复述、员工讲清、合规使用的表达。",
    },
    "product_system": {
        "title": "产品体系与服务项目边界",
        "decision_question": "先判断：哪些项目是主推服务，哪些只是组合、复购或参考项？",
        "why_it_matters": "项目边界会影响菜单、价格、交付 SOP 和员工推荐路径。",
        "next_action": "先确认主服务、组合服务和禁用功效，再进入产品答案卡。",
    },
    "store_model": {
        "title": "首店模型与复制前提",
        "decision_question": "先判断：这些门店模型假设有没有真实数据或首店验证支撑？",
        "why_it_matters": "未经验证的门店模型不能变成扩店、融资或对外承诺。",
        "next_action": "把假设转成待验证指标，开店后用经营数据复盘。",
    },
    "unit_economics": {
        "title": "经营数据与财务口径",
        "decision_question": "先判断：这些收入、成本、回本和估值口径是否有来源、版本和负责人？",
        "why_it_matters": "财务口径不一致会影响股东沟通、融资材料和内部决策。",
        "next_action": "先补来源和版本，再决定能否进入融资或经营材料。",
    },
    "general": {
        "title": "未归类资料清理",
        "decision_question": "先判断：这批内容到底属于品牌、产品、运营、合规还是外部参考？",
        "why_it_matters": "不归类的资料会污染搜索结果，让系统把参考材料误当企业结论。",
        "next_action": "先分流到正确知识域；没有业务价值的内容直接归档。",
    },
}


def _review_topic_key(item: dict[str, Any]) -> str:
    group = str(item.get("review_group") or "general")
    source_class = str(item.get("source_class") or "")
    if group in REVIEW_TOPIC_DEFINITIONS and group != "general":
        return group
    if source_class == "risk_compliance":
        return "risk_boundary"
    if group in REVIEW_TOPIC_DEFINITIONS:
        return group
    return "general"


def _source_label(source: Any) -> str:
    value = str(source or "").strip()
    if not value:
        return ""
    return Path(value).name or value


def _priority_rank(priority: str) -> int:
    return {"high": 0, "medium": 1, "low": 2}.get(priority, 3)


HXYOS_AUTHORITY_RULES: dict[str, bool] = {
    "chat_can_publish_approved": False,
    "agent_can_publish_approved": False,
    "loop_can_publish_approved": False,
    "memory_can_publish_approved": False,
    "skill_output_is_official": False,
}


RETRIEVAL_APP_CATALOG: list[dict[str, Any]] = [
    {
        "retrieval_app_id": "employee_standard_answer_search",
        "name": "员工标准答案检索",
        "purpose": "帮助前台和员工只检索已核定话术、禁用表达和高频问答。",
        "primary_users": ["frontdesk", "store_staff", "trainer"],
        "allowed_statuses": ["approved", "action_asset"],
        "blocked_statuses": ["raw", "reference", "candidate", "needs_review"],
        "output_contract": ["standard_answer", "do_not_say", "source_title", "review_status"],
        "official_use_allowed": True,
        "can_publish_approved": False,
        "requires_human_review_for_updates": True,
        "status": "draft",
    },
    {
        "retrieval_app_id": "brand_language_risk_check",
        "name": "对外话语风险检查",
        "purpose": "检查朋友圈、团购页、海报和员工表达是否触碰医疗化、保证疗效或夸大宣传。",
        "primary_users": ["founder", "operator", "store_manager"],
        "allowed_statuses": ["approved", "action_asset"],
        "blocked_statuses": ["raw", "reference", "candidate", "needs_review"],
        "output_contract": ["risk_level", "risk_reason", "rewrite_suggestion", "forbidden_terms"],
        "official_use_allowed": False,
        "can_publish_approved": False,
        "requires_human_review_for_updates": True,
        "status": "draft",
    },
    {
        "retrieval_app_id": "founder_decision_evidence_search",
        "name": "创始人决策证据检索",
        "purpose": "把战略、开业、产品和融资相关判断拆成依据、缺口和下一步验证动作。",
        "primary_users": ["founder", "operator"],
        "allowed_statuses": ["approved", "action_asset", "current_candidate"],
        "blocked_statuses": ["raw"],
        "output_contract": ["decision_question", "known_evidence", "evidence_gap", "next_validation"],
        "official_use_allowed": False,
        "can_publish_approved": False,
        "requires_human_review_for_updates": True,
        "status": "draft",
    },
]


INTENT_DEFINITION_CATALOG: list[dict[str, Any]] = [
    {
        "intent_id": "intent-approved-answer",
        "name": "已核定答案调用",
        "positive_scope": ["员工标准问答", "前台速查", "品牌标准口径"],
        "excluded_scope": ["生成新结论", "修改正式知识", "批准候选资料"],
        "risk_gates": ["status_must_be_approved", "source_required"],
        "default_retrieval_app": "employee_standard_answer_search",
    },
    {
        "intent_id": "intent-material-ingest",
        "name": "资料入库整理",
        "positive_scope": ["新文件解析", "外部参考整理", "候选知识提取"],
        "excluded_scope": ["自动发布", "替代人工复核", "改写已核定口径"],
        "risk_gates": ["raw_material_is_not_official", "human_review_required"],
        "default_retrieval_app": "",
    },
    {
        "intent_id": "intent-compliance-language-check",
        "name": "合规表达检查",
        "positive_scope": ["医疗化表达", "疗效保证", "夸大宣传", "对外文案风险"],
        "excluded_scope": ["医疗建议", "诊断结论", "功效承诺", "自动放行对外发布"],
        "risk_gates": ["medical_claim", "guaranteed_effect", "overstatement", "external_publish_review"],
        "default_retrieval_app": "brand_language_risk_check",
    },
    {
        "intent_id": "intent-brand-expression-review",
        "name": "品牌表达评审",
        "positive_scope": ["门头文字", "开业文案", "品牌一句话", "员工介绍"],
        "excluded_scope": ["VI/SI 设计定稿", "未审核资料发布", "招商承诺"],
        "risk_gates": ["brand_consistency", "customer_comprehension", "forbidden_terms"],
        "default_retrieval_app": "brand_language_risk_check",
    },
    {
        "intent_id": "intent-opening-store-workflow",
        "name": "首店开业动作规划",
        "positive_scope": ["开业前任务", "首店验证", "员工训练", "资料缺口"],
        "excluded_scope": ["多店经营看板", "正式扩店承诺", "加盟主线"],
        "risk_gates": ["stage_match", "resource_match", "evidence_gap"],
        "default_retrieval_app": "founder_decision_evidence_search",
    },
    {
        "intent_id": "intent-loop-execution",
        "name": "开发与知识 Loop 执行",
        "positive_scope": ["测试驱动修复", "benchmark 改进", "入库任务推进"],
        "excluded_scope": ["越权写入 approved", "跳过测试", "修改 htops"],
        "risk_gates": ["stop_condition_required", "hxy_boundary_required", "verification_required"],
        "default_retrieval_app": "",
    },
    {
        "intent_id": "intent-correction-feedback",
        "name": "纠错与复盘反馈",
        "positive_scope": ["AI 答错纠正", "员工说错纠正", "资料冲突记录"],
        "excluded_scope": ["私自覆盖正式知识", "删除历史版本", "直接对外发布"],
        "risk_gates": ["versioning_required", "review_required", "source_required"],
        "default_retrieval_app": "founder_decision_evidence_search",
    },
]


SKILL_REGISTRY_CATALOG: list[dict[str, Any]] = [
    {
        "skill_id": "hxy-compliance-language-check",
        "name": "合规话语检查",
        "version": "0.1.0",
        "status": "draft",
        "owner": "HXYOS",
        "input_contract": ["text", "channel", "audience"],
        "output_contract": ["risk_level", "risk_reason", "rewrite_suggestion"],
        "can_publish_approved": False,
    },
    {
        "skill_id": "hxy-brand-expression-review",
        "name": "品牌表达评审",
        "version": "0.1.0",
        "status": "draft",
        "owner": "HXYOS",
        "input_contract": ["artifact", "scenario", "target_user"],
        "output_contract": ["scorecard", "reject_reasons", "recommended_version"],
        "can_publish_approved": False,
    },
    {
        "skill_id": "hxy-employee-answer-coach",
        "name": "员工标准回答教练",
        "version": "0.1.0",
        "status": "draft",
        "owner": "HXYOS",
        "input_contract": ["customer_question", "employee_answer"],
        "output_contract": ["standard_answer", "correction_points", "practice_task"],
        "can_publish_approved": False,
    },
    {
        "skill_id": "hxy-ingest-material-compiler",
        "name": "资料入库编译",
        "version": "0.1.0",
        "status": "draft",
        "owner": "HXYOS",
        "input_contract": ["material_id", "source_type", "content"],
        "output_contract": ["summary", "candidate_cards", "risk_flags"],
        "can_publish_approved": False,
    },
    {
        "skill_id": "hxy-opening-store-checklist",
        "name": "首店开业清单",
        "version": "0.1.0",
        "status": "draft",
        "owner": "HXYOS",
        "input_contract": ["stage", "evidence", "blockers"],
        "output_contract": ["today_action", "evidence_gap", "stop_condition"],
        "can_publish_approved": False,
    },
    {
        "skill_id": "hxy-benchmark-correction-pack",
        "name": "Benchmark 修正包",
        "version": "0.1.0",
        "status": "draft",
        "owner": "HXYOS",
        "input_contract": ["benchmark_result", "failed_cases"],
        "output_contract": ["fix_plan", "affected_cards", "verification_commands"],
        "can_publish_approved": False,
    },
    {
        "skill_id": "hxy-decision-evidence-pack",
        "name": "决策证据包",
        "version": "0.1.0",
        "status": "draft",
        "owner": "HXYOS",
        "input_contract": ["decision_question", "available_evidence"],
        "output_contract": ["known_evidence", "missing_evidence", "next_validation"],
        "can_publish_approved": False,
    },
    {
        "skill_id": "hxy-review-topic-generator",
        "name": "待判断议题生成",
        "version": "0.1.0",
        "status": "draft",
        "owner": "HXYOS",
        "input_contract": ["candidate_claims", "triage_report"],
        "output_contract": ["review_topics", "priority", "next_action"],
        "can_publish_approved": False,
    },
]


RISK_GATE_BY_RULE_TYPE = {
    "医疗": "medical_claim",
    "保证": "guaranteed_effect",
    "夸大": "overstatement",
}


COMPLIANCE_WORKFLOW_GATES: dict[str, dict[str, str]] = {
    "content_publish": {
        "label": "内容发布",
        "safe_next_step": "进入发布前人工确认。",
        "revise_next_step": "先按建议改写，再复检。",
        "blocked_next_step": "停止发布，重写表达。",
        "human_owner": "内容/运营负责人",
    },
    "staff_script": {
        "label": "员工话术",
        "safe_next_step": "进入店长/运营复核。",
        "revise_next_step": "改成标准话术后复训。",
        "blocked_next_step": "禁止进入员工培训。",
        "human_owner": "店长/运营培训负责人",
    },
    "project_menu": {
        "label": "项目菜单",
        "safe_next_step": "进入菜单负责人复核。",
        "revise_next_step": "改项目名或项目介绍后复检。",
        "blocked_next_step": "停止上架该表达。",
        "human_owner": "产品/菜单负责人",
    },
}


def _source_label_for_rule(source: Any) -> str:
    value = str(source or "").strip()
    return Path(value).name if value else "默认风险规则"


def _safe_replacement_for_text(text: str, replacements: list[dict[str, Any]]) -> str:
    for replacement in replacements:
        unsafe = str(replacement.get("unsafe") or "").strip()
        safe = str(replacement.get("safe") or "").strip()
        if unsafe and safe and unsafe in text:
            return safe
    return ""


def _compliance_language_check_result(
    request: ComplianceLanguageCheckRequest,
    *,
    root_dir: Path,
) -> dict[str, Any]:
    rule_payload = load_brand_risk_rules(root_dir=root_dir)
    source_labels = [_source_label_for_rule(source) for source in rule_payload.get("source_paths") or []]
    if not source_labels:
        source_labels = ["默认风险规则"]

    raw_result = check_brand_risk_text(request.text, root_dir=root_dir)
    hits = raw_result.get("hits") or []
    hit_gates: list[str] = []
    evidence: list[dict[str, Any]] = []
    for hit in hits:
        gate = RISK_GATE_BY_RULE_TYPE.get(str(hit.get("type") or ""), "language_risk")
        if gate not in hit_gates:
            hit_gates.append(gate)
        evidence.append(
            {
                "rule_name": f"{hit.get('type') or '表达'}风险规则",
                "level": hit.get("level") or "warn",
                "matched_terms": hit.get("words") or [],
                "advice": hit.get("advice") or "",
            }
        )

    has_bad = any(str(hit.get("level") or "") == "bad" for hit in hits)
    has_medical = "medical_claim" in hit_gates
    if has_medical:
        risk_level = "p0"
    elif has_bad:
        risk_level = "high"
    elif hits:
        risk_level = "medium"
    else:
        risk_level = "none"

    decision = "block" if has_bad else "revise" if hits else "allow"
    review_required = decision != "allow"
    safe_replacement = _safe_replacement_for_text(request.text, list(rule_payload.get("safe_replacements") or []))
    rewrite_suggestion = (
        f"可以改成：{safe_replacement}。不要承诺治疗、见效或保证结果。"
        if review_required and safe_replacement
        else "可以改成：草本现煮，泡着舒服，适合下班后放松。不要承诺治疗、见效或保证结果。"
        if review_required
        else "当前表达相对克制。正式发布前仍建议按渠道负责人要求复核。"
    )
    risk_reason = (
        "未命中禁用表达。"
        if not hits
        else "；".join(
            f"命中{hit.get('type') or '表达'}风险：{hit.get('advice') or '需要负责人复核。'}" for hit in hits
        )
    )
    for item in evidence:
        item["source"] = source_labels[0]

    return {
        "version": "hxy-compliance-language-check-result.v1",
        "skill_id": "hxy-compliance-language-check",
        "channel": request.channel,
        "audience": request.audience,
        "decision": decision,
        "risk_level": risk_level,
        "hit_gates": hit_gates,
        "can_publish": False,
        "official_use_allowed": False,
        "review_required": review_required,
        "risk_reason": risk_reason,
        "rewrite_suggestion": rewrite_suggestion,
        "evidence": evidence,
        "authority_rule": "skill_output_is_not_official_and_cannot_publish_approved_knowledge",
    }


def _compliance_workflow_gate_result(
    request: ComplianceWorkflowGateRequest,
    *,
    root_dir: Path,
) -> dict[str, Any]:
    workflow_type = request.workflow_type.strip()
    config = COMPLIANCE_WORKFLOW_GATES.get(workflow_type)
    if config is None:
        allowed = "、".join(COMPLIANCE_WORKFLOW_GATES)
        raise HTTPException(status_code=400, detail=f"workflow_type must be one of: {allowed}")

    check_result = _compliance_language_check_result(
        ComplianceLanguageCheckRequest(text=request.text, channel=request.channel, audience=request.audience),
        root_dir=root_dir,
    )
    decision = str(check_result.get("decision") or "revise")
    workflow_status_by_decision = {
        "allow": "can_continue",
        "revise": "revise_before_continue",
        "block": "blocked",
    }
    next_step_key_by_decision = {
        "allow": "safe_next_step",
        "revise": "revise_next_step",
        "block": "blocked_next_step",
    }
    workflow_status = workflow_status_by_decision.get(decision, "revise_before_continue")
    next_step = config[next_step_key_by_decision.get(decision, "revise_next_step")]
    can_continue = workflow_status == "can_continue"

    return {
        "version": "hxy-compliance-workflow-gate-result.v1",
        "workflow_type": workflow_type,
        "workflow_label": config["label"],
        "workflow_status": workflow_status,
        "decision": decision,
        "risk_level": check_result.get("risk_level") or "unknown",
        "hit_gates": check_result.get("hit_gates") or [],
        "risk_reason": check_result.get("risk_reason") or "",
        "rewrite_suggestion": check_result.get("rewrite_suggestion") or "",
        "next_step": next_step,
        "human_owner": config["human_owner"],
        "can_continue": can_continue,
        "can_publish": False,
        "official_use_allowed": False,
        "review_required": True,
        "evidence": check_result.get("evidence") or [],
        "authority_rule": "workflow_gate_does_not_publish_or_approve_business_knowledge",
    }


def _compliance_preflight_for_text(
    text: str,
    *,
    workflow_type: str,
    channel: str,
    audience: str,
    root_dir: Path,
) -> dict[str, Any]:
    preflight = _compliance_workflow_gate_result(
        ComplianceWorkflowGateRequest(
            workflow_type=workflow_type,
            text=text,
            channel=channel,
            audience=audience,
        ),
        root_dir=root_dir,
    )
    return {
        **preflight,
        "preflight": True,
        "write_to_database": False,
        "can_publish": False,
        "official_use_allowed": False,
    }


def _workflow_type_for_brand_artifact(artifact_type: str) -> str:
    if artifact_type == "first_order_menu":
        return "project_menu"
    if artifact_type == "staff_script":
        return "staff_script"
    return "content_publish"


def _workflow_type_for_answer_card(request: AnswerCardRequest) -> str:
    combined = f"{request.intent} {request.audience} {request.question_pattern}"
    if any(term in combined for term in ["menu", "菜单", "product", "产品", "project_menu"]):
        return "project_menu"
    if any(term in combined for term in ["staff", "员工", "training", "训练", "话术"]):
        return "staff_script"
    return "content_publish"


def _apply_training_compliance_preflight(result: dict[str, Any], preflight: dict[str, Any]) -> None:
    can_continue = bool(preflight.get("can_continue"))
    result["compliance_preflight"] = preflight
    result["training_artifact_gate"] = {
        "version": "hxy-training-artifact-gate.v1",
        "can_promote_to_answer_card": can_continue and not bool(result.get("needs_retrain")),
        "official_use_allowed": False,
        "requires_human_review": True,
        "reason": "通过员工话术合规预检后，仍需店长/运营复核。" if can_continue else "员工话术未通过合规预检，不能晋升为权威答案卡。",
    }
    if can_continue:
        return

    result["needs_retrain"] = True
    result["level"] = "retrain"
    result["level_label"] = "需复训"
    try:
        result["score"] = min(int(result.get("score") or 0), 70)
    except (TypeError, ValueError):
        result["score"] = 70
    correction_points = list(result.get("correction_points") or [])
    reason = str(preflight.get("risk_reason") or "命中合规风险，需要改写后复训。")
    if reason and reason not in correction_points:
        correction_points.append(reason)
    result["correction_points"] = correction_points
    package = result.get("correction_package") or {}
    package["compliance_preflight"] = preflight
    package["can_promote_to_answer_card"] = False
    result["correction_package"] = package
    dimensions = list(result.get("dimensions") or [])
    for dimension in dimensions:
        if dimension.get("key") == "compliance":
            dimension["score"] = min(int(dimension.get("score") or 0), 60)
            dimension["passed"] = False
            dimension["detail"] = reason
    result["dimensions"] = dimensions


def _evaluate_training_content(
    *,
    request: TrainingEvaluateRequest,
    model_router: Any,
    root_dir: Path,
) -> dict[str, Any]:
    if not request.employee_answer.strip():
        raise HTTPException(status_code=400, detail="employee_answer is required")
    rule_result = evaluate_training_script(request)
    result = _evaluate_training_with_model(
        model_router=model_router,
        request=request,
        rule_result=rule_result,
    )
    training_preflight = _compliance_preflight_for_text(
        request.employee_answer,
        workflow_type="staff_script",
        channel="员工话术",
        audience="staff",
        root_dir=root_dir,
    )
    _apply_training_compliance_preflight(result, training_preflight)
    return result


def _run_training_evaluation(
    *,
    request: TrainingEvaluateRequest,
    model_router: Any,
    root_dir: Path,
    repository: Any,
) -> dict[str, Any]:
    result = _evaluate_training_content(
        request=request,
        model_router=model_router,
        root_dir=root_dir,
    )
    review_task_id = repository.create_review_task(
        {
            "answer_id": None,
            "question": result["customer_question"],
            "intent": "training",
            "reason": (
                "training_retrain"
                if result["needs_retrain"]
                else "training_answer_card_candidate"
            ),
            "priority": "high" if result["needs_retrain"] else "low",
            "note": result["employee_answer"],
            "correction_package": result["correction_package"],
            "answer_card_draft": (
                None if result["needs_retrain"] else result["answer_card_draft"]
            ),
            "training_evaluation": {
                "score": result["score"],
                "level": result["level"],
                "dimensions": result["dimensions"],
            },
        }
    )
    result["review_task_id"] = review_task_id
    result["training_session_id"] = repository.save_training_session(
        {
            "employee_id": request.employee_id.strip() or "employee-local",
            "employee_name": request.employee_name.strip() or "门店员工",
            "store_id": request.store_id.strip() or "pilot-store",
            "store_name": request.store_name.strip() or "荷小悦试点门店",
            "training_item": result["training_item"],
            "customer_question": result["customer_question"],
            "employee_answer": result["employee_answer"],
            "scenario": result["scenario"],
            "role": result["role"],
            "score": result["score"],
            "level": result["level"],
            "needs_retrain": result["needs_retrain"],
            "dimensions": result["dimensions"],
            "correction_points": result["correction_points"],
            "follow_up_questions": result["follow_up_questions"],
            "retraining_task": result["retraining_task"],
            "answer_card_draft": result["answer_card_draft"],
            "capability_profile": result.get("capability_profile") or {},
            "adaptive_retrain_plan": result.get("adaptive_retrain_plan") or {},
            "operating_metric_links": result.get("operating_metric_links") or [],
            "review_task_id": review_task_id,
            "payload": result,
        }
    )
    return result


AUTOMATION_TASK_CATALOG: list[dict[str, Any]] = [
    {
        "task_id": "automation_ingest_loop_manual",
        "task_type": "material_ingest_loop",
        "name": "资料入库 Loop",
        "trigger": "manual_or_inbox_scan",
        "allowed_script": "scripts/run-hxy-ingest-loop.py",
        "stop_condition": "生成待审核产物后停止，不能进入 approved。",
        "can_publish_approved": False,
        "enabled_by_default": False,
        "requires_human_review": True,
    },
    {
        "task_id": "automation_benchmark_loop_manual",
        "task_type": "benchmark_improvement_loop",
        "name": "Benchmark 改进 Loop",
        "trigger": "manual",
        "allowed_script": "scripts/run-hxy-brain-benchmark.py",
        "stop_condition": "达到目标 pass_rate 或命中轮次上限后停止。",
        "can_publish_approved": False,
        "enabled_by_default": False,
        "requires_human_review": True,
    },
    {
        "task_id": "automation_review_topic_refresh",
        "task_type": "review_topic_refresh",
        "name": "待判断议题刷新",
        "trigger": "manual_or_after_ingest",
        "allowed_script": "",
        "stop_condition": "只刷新只读议题视图，不写入正式知识。",
        "can_publish_approved": False,
        "enabled_by_default": True,
        "requires_human_review": True,
    },
]


def _product_contracts() -> dict[str, Any]:
    return {
        "version": "hxyos-product-contracts.v1",
        "knowledge_engine": {
            "name": "企业知识引擎",
            "purpose": "把资料加工成可追溯、可复核、可引用、可执行的企业知识资产。",
            "canonical_statuses": ["raw", "reference", "candidate", "needs_review", "approved", "action_asset", "superseded"],
            "official_answer_statuses": ["approved", "action_asset"],
            "raw_material_can_answer_directly": False,
        },
        "retrieval_apps": {
            "name": "检索应用层",
            "count": len(RETRIEVAL_APP_CATALOG),
            "contract": ["retrieval_app_id", "allowed_statuses", "output_contract", "authority_boundary"],
        },
        "intent_planning": {
            "name": "意图规划引擎",
            "count": len(INTENT_DEFINITION_CATALOG),
            "contract": ["intent_id", "positive_scope", "excluded_scope", "risk_gates"],
        },
        "skill_registry": {
            "name": "Skill 中心",
            "count": len(SKILL_REGISTRY_CATALOG),
            "contract": ["skill_id", "version", "status", "owner", "can_publish_approved"],
        },
        "memory_policies": {
            "name": "受治理的长期记忆",
            "process_memory_types": ["preference", "negative_list", "historical_decision", "hypothesis", "retrospective_fragment"],
            "can_be_authority_source": False,
            "allowed_use": "context_reminder_only",
            "promotion_required": True,
        },
        "automation_tasks": {
            "name": "自动化任务层",
            "count": len(AUTOMATION_TASK_CATALOG),
            "contract": ["task_id", "task_type", "allowed_script", "stop_condition", "can_publish_approved"],
        },
        "authority_rules": HXYOS_AUTHORITY_RULES,
    }


def _compiler_review_topics_from_payload(payload: dict[str, Any] | None, *, limit: int) -> dict[str, Any]:
    if not payload:
        return {
            "version": "hxy-review-topics.v1",
            "status": "missing",
            "count": 0,
            "total": 0,
            "items": [],
            "raw_claims_hidden": True,
            "official_use_allowed": False,
            "requires_human_review": True,
            "next_actions": ["运行知识编译器生成 claim-triage.json，再由系统聚合成待判断议题。"],
            "authority_rule": "review_topics_summarize_raw_claims_without_approving_knowledge",
        }
    topics: dict[str, dict[str, Any]] = {}
    for item in payload.get("items") or []:
        if not isinstance(item, dict):
            continue
        key = _review_topic_key(item)
        definition = REVIEW_TOPIC_DEFINITIONS[key]
        topic = topics.setdefault(
            key,
            {
                "version": "hxy-review-topic.v1",
                "topic_id": f"hxy-review-topic:{key}",
                "topic_key": key,
                "title": definition["title"],
                "decision_question": definition["decision_question"],
                "why_it_matters": definition["why_it_matters"],
                "next_action": definition["next_action"],
                "priority": "low",
                "evidence_count": 0,
                "_sort_weight": 0,
                "source_samples": [],
                "source_classes": [],
                "official_use_allowed": False,
                "requires_human_review": True,
            },
        )
        priority = str(item.get("priority") or "low")
        if _priority_rank(priority) < _priority_rank(str(topic["priority"])):
            topic["priority"] = priority
        topic["evidence_count"] += 1
        topic["_sort_weight"] += int(item.get("cluster_member_count") or 0)
        source_class = str(item.get("source_class") or "")
        if source_class and source_class not in topic["source_classes"]:
            topic["source_classes"].append(source_class)
        for source in item.get("sources") or []:
            label = _source_label(source)
            if label and label not in topic["source_samples"] and len(topic["source_samples"]) < 4:
                topic["source_samples"].append(label)

    items = sorted(
        topics.values(),
        key=lambda topic: (_priority_rank(str(topic.get("priority") or "")), -int(topic.get("_sort_weight") or 0), topic["title"]),
    )
    public_items = []
    for item in items[:limit]:
        public = dict(item)
        public.pop("_sort_weight", None)
        public_items.append(public)
    return {
        "version": "hxy-review-topics.v1",
        "source": "claim_triage",
        "status": payload.get("status") or ("ready" if items else "empty"),
        "count": len(public_items),
        "total": len(items),
        "raw_selected_count": len(payload.get("items") or []),
        "total_claim_count": int(payload.get("total_claim_count") or 0),
        "cluster_count": int(payload.get("cluster_count") or 0),
        "items": public_items,
        "raw_claims_hidden": True,
        "official_use_allowed": False,
        "requires_human_review": True,
        "authority_rule": "review_topics_summarize_raw_claims_without_approving_knowledge",
    }


def _compiler_compliance_review_pack_from_payload(payload: dict[str, Any] | None, *, limit: int) -> dict[str, Any]:
    if not payload:
        return {
            "version": "hxy-compliance-review-pack.v1",
            "status": "missing",
            "count": 0,
            "total": 0,
            "items": [],
            "official_use_allowed": False,
            "publish_allowed": False,
            "requires_human_review": True,
            "next_actions": ["运行知识编译器生成 knowledge/wiki/compliance-review-pack.json。"],
            "authority_rule": "compliance_review_pack_is_not_approved_knowledge",
        }
    items = []
    for item in payload.get("items") or []:
        if not isinstance(item, dict):
            continue
        public = dict(item)
        public["official_use_allowed"] = False
        public["publish_allowed"] = False
        public["requires_human_review"] = True
        public.setdefault("risk_level", "P0")
        public.setdefault("required_decision", "approve_as_rule, needs_revision, or reject")
        items.append(public)
    return {
        **payload,
        "version": payload.get("version") or "hxy-compliance-review-pack.v1",
        "status": payload.get("status") or ("needs_human_review" if items else "empty"),
        "count": len(items[:limit]),
        "total": len(items),
        "items": items[:limit],
        "official_use_allowed": False,
        "publish_allowed": False,
        "requires_human_review": True,
        "authority_rule": "compliance_review_pack_is_not_approved_knowledge",
    }


def _p0_reviewer_todo_from_payload(payload: dict[str, Any] | None, *, run_id: str) -> dict[str, Any]:
    if not payload:
        return {
            "version": "hxy-p0-reviewer-todo.v1",
            "status": "missing",
            "run_id": run_id,
            "item_count": 0,
            "pending_count": 0,
            "actioned_count": 0,
            "items": [],
            "official_use_allowed": False,
            "publish_allowed": False,
            "write_to_database": False,
            "requires_human_review": True,
            "next_actions": [
                "运行 scripts/run-hxy-p0-governance-safe-next.py 生成 p0-reviewer-todo.json。",
                "生成后仍需人工编辑 p0-review-decisions.json，不能由 API 自动批准。",
            ],
            "authority_rule": "p0_reviewer_todo_does_not_publish_approved_cards",
        }
    items = []
    for item in payload.get("items") or []:
        if not isinstance(item, dict):
            continue
        public = dict(item)
        public["official_use_allowed"] = False
        public["publish_allowed"] = False
        public["write_to_database"] = False
        public.setdefault("next_human_action", "choose approve, reject, or needs_revision manually")
        items.append(public)
    return {
        **payload,
        "version": payload.get("version") or "hxy-p0-reviewer-todo.v1",
        "status": "ready",
        "run_id": run_id,
        "item_count": int(payload.get("item_count") or len(items)),
        "pending_count": int(payload.get("pending_count") or 0),
        "actioned_count": int(payload.get("actioned_count") or 0),
        "items": items,
        "official_use_allowed": False,
        "publish_allowed": False,
        "write_to_database": False,
        "requires_human_review": True,
        "authority_rule": "p0_reviewer_todo_does_not_publish_approved_cards",
    }


def _p0_governance_notification_from_status(status: dict[str, Any], *, run_id: str) -> dict[str, Any]:
    details = status.get("details") if isinstance(status.get("details"), dict) else {}
    pending_count = int(details.get("pending_count") or 0)
    actioned_count = int(details.get("actioned_count") or 0)
    status_api = f"/api/v1/hxy/p0/governance-status?run_id={run_id}"
    reviewer_todo_api = f"/api/v1/hxy/p0/reviewer-todo?run_id={run_id}"
    lines = [
        "HXY P0 Governance Status",
        f"Run: {run_id}",
        f"Current step: {status.get('current_step') or 'unknown'}",
        f"Blocked: {'yes' if status.get('blocked') else 'no'}",
        f"Pending: {pending_count}",
        f"Actioned: {actioned_count}",
        "write_to_database: false",
        "publish_allowed: false",
        f"Next action: {status.get('next_action') or ''}",
        f"Status API: {status_api}",
        f"Reviewer todo API: {reviewer_todo_api}",
    ]
    return {
        "version": "hxy-p0-governance-notification.v1",
        "channel": "hermes_feishu",
        "run_id": run_id,
        "text": "\n".join(lines),
        "links": {
            "status_api": status_api,
            "reviewer_todo_api": reviewer_todo_api,
        },
        "current_step": status.get("current_step") or "unknown",
        "blocked": bool(status.get("blocked")),
        "pending_count": pending_count,
        "actioned_count": actioned_count,
        "send_allowed": False,
        "official_use_allowed": False,
        "publish_allowed": False,
        "write_to_database": False,
        "requires_human_review": True,
        "authority_rule": "notification_payload_is_read_only_and_does_not_send_messages",
    }


def _benchmark_corrections_from_payload(payload: dict[str, Any] | None, *, limit: int) -> dict[str, Any]:
    if not payload:
        return {
            "version": "hxy-benchmark-corrections.v1",
            "status": "missing",
            "count": 0,
            "total": 0,
            "items": [],
            "next_actions": ["运行 scripts/run-hxy-loop.py benchmark_improvement 生成 benchmark-corrections.json。"],
        }
    items = []
    for task in payload.get("tasks") or []:
        if not isinstance(task, dict):
            continue
        public = dict(task)
        public.setdefault("status", "open")
        public["official_use_allowed"] = False
        public["requires_human_review"] = True
        public["correction_package"] = {
            "version": payload.get("version") or "hxy-benchmark-correction-package.v1",
            "benchmark_version": payload.get("benchmark_version") or "",
            "source_task_id": public.get("task_id") or "",
            "required_action": public.get("required_action") or "",
            "failed_checks": public.get("failed_checks") or [],
            "warnings": public.get("warnings") or [],
        }
        items.append(public)
    return {
        "version": "hxy-benchmark-corrections.v1",
        "status": "ready",
        "count": len(items[:limit]),
        "total": len(items),
        "benchmark_version": payload.get("benchmark_version") or "",
        "items": items[:limit],
        "authority_rule": "benchmark_corrections_are_review_tasks_not_approved_knowledge",
        "next_actions": [
            "优先处理 missing_citation、lifecycle_not_explicit 和合规失败项。",
            "修正必须进入人工复核或 approved answer card 流程。",
        ],
    }


def _answer_card_draft_from_review_item(item: dict[str, Any], revised_claim: str = "") -> dict[str, Any]:
    claim = (revised_claim or str(item.get("claim") or "")).strip()
    review_group = str(item.get("review_group") or "general")
    question_by_group = {
        "brand_positioning": "荷小悦的品牌定位应该怎么说？",
        "product_system": "清泡调补养或产品体系应该怎么解释？",
        "store_model": "荷小悦门店模型的关键判断是什么？",
        "competitor_research": "这条竞品信息对荷小悦有什么参考价值？",
        "unit_economics": "这条单店模型或投资测算信息能否作为内部判断依据？",
        "employee_script": "员工应该如何按标准口径表达？",
        "risk_boundary": "这条表达有哪些合规风险，应该如何改写？",
    }
    answer = (
        f"当前为草稿，不能直接发布。候选复核内容：{claim} "
        "需要负责人确认来源、适用范围和风险边界后，才可进入 approved 答案卡。"
    )
    return {
        "version": "hxy-answer-card-draft.v1",
        "question_pattern": question_by_group.get(review_group, "这条候选知识是否可以进入荷小悦标准口径？"),
        "intent": item.get("domain") or review_group,
        "audience": "internal",
        "answer": answer,
        "status": "draft",
        "official_use_allowed": False,
        "requires_human_review": True,
        "source_claim_ids": [item.get("claim_id")],
        "sources": item.get("sources") or [],
        "risk_flags": item.get("risk_flags") or [],
        "review_group": review_group,
        "recommended_reviewer": item.get("recommended_reviewer") or "运营负责人",
    }


def _append_compiler_review_decision(path: Path, decision: dict[str, Any]) -> dict[str, Any]:
    payload = _read_json_file(path) or {"version": "hxy-compiler-review-decisions.v1", "items": []}
    items = payload.get("items") if isinstance(payload.get("items"), list) else []
    items.append(decision)
    next_payload = {
        "version": "hxy-compiler-review-decisions.v1",
        "count": len(items),
        "items": items,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(next_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return next_payload


def create_app(
    root_dir: Path | None = None,
    repository_factory: RepositoryFactory | None = None,
    model_router: Any | None = None,
    product_identity_repository_factory: RepositoryFactory | None = None,
    onboarding_repository_factory: RepositoryFactory | None = None,
    onboarding_public_app_url: str | None = None,
    conversation_repository_factory: RepositoryFactory | None = None,
    material_repository_factory: RepositoryFactory | None = None,
    task_repository_factory: RepositoryFactory | None = None,
    channel_repository_factory: RepositoryFactory | None = None,
    record_repository_factory: RepositoryFactory | None = None,
    briefing_repository_factory: RepositoryFactory | None = None,
    operating_repository_factory: RepositoryFactory | None = None,
    evidence_repository_factory: RepositoryFactory | None = None,
    operating_service_builder: Callable[[Any], Any] | None = None,
    product_training_repository_factory: RepositoryFactory | None = None,
    service_repository_factory: RepositoryFactory | None = None,
    service_identity_hmac_key: str | None = None,
    journey_training_evaluator: Callable[..., dict[str, Any]] | None = None,
    material_understanding_builder: Callable[..., dict[str, Any]] | None = None,
    product_auth_settings: ProductAuthSettings | None = None,
    intake_route_classifier: Callable[..., str] | None = None,
    product_answer_generator: Callable[..., dict[str, Any]] | None = None,
) -> FastAPI:
    settings = get_settings()
    resolved_root = (root_dir or settings.root_dir).resolve()
    project_root = Path(__file__).resolve().parents[2]
    inbox_dir = resolved_root / "knowledge" / "raw" / "inbox"
    inbox_dir.mkdir(parents=True, exist_ok=True)
    workspace_event_store = resolved_root / "knowledge" / "workspace" / "events.jsonl"
    ingest_loop_state_path = resolved_root / "knowledge" / "runs" / "ingest-loop-latest" / "loop-state.json"
    make_repository = repository_factory or _default_repository_factory(settings.database_url)
    make_product_identity_repository = (
        product_identity_repository_factory
        or _default_product_identity_repository_factory(settings.database_url)
    )

    def get_product_identity_repository() -> Any:
        return make_product_identity_repository()

    resolve_product_principal = build_principal_resolver(
        get_product_identity_repository
    )
    make_onboarding_repository = onboarding_repository_factory
    if make_onboarding_repository is None and settings.database_url.strip():
        make_onboarding_repository = _default_onboarding_repository_factory(
            settings.database_url
        )
    resolved_onboarding_public_app_url = (
        onboarding_public_app_url
        if onboarding_public_app_url is not None
        else os.environ.get("HXY_PUBLIC_APP_URL", "")
    )
    validated_onboarding_public_app_url = ""
    if resolved_onboarding_public_app_url.strip():
        validated_onboarding_public_app_url, _ = validate_public_app_url(
            resolved_onboarding_public_app_url
        )
    make_conversation_repository = (
        conversation_repository_factory
        or _default_conversation_repository_factory(settings.database_url)
    )
    make_material_repository = (
        material_repository_factory
        or _default_material_repository_factory(settings.database_url)
    )
    make_task_repository = (
        task_repository_factory or _default_task_repository_factory(settings.database_url)
    )
    make_channel_repository = (
        channel_repository_factory
        or _default_channel_repository_factory(settings.database_url)
    )
    make_record_repository = (
        record_repository_factory
        or _default_record_repository_factory(settings.database_url)
    )
    make_briefing_repository = (
        briefing_repository_factory
        or _default_briefing_repository_factory(settings.database_url)
    )
    make_operating_repository = (
        operating_repository_factory
        or _default_operating_repository_factory(settings.database_url)
    )
    make_evidence_repository = (
        evidence_repository_factory
        or _default_evidence_repository_factory(
            settings.database_url,
            max_evidence_bytes=settings.max_upload_bytes,
        )
    )
    build_operating_service = operating_service_builder or OperatingService
    make_product_training_repository = (
        product_training_repository_factory
        or _default_product_training_repository_factory(settings.database_url)
    )
    make_service_repository = (
        service_repository_factory
        or _default_service_repository_factory(settings.database_url)
    )
    resolved_service_identity_hmac_key = (
        service_identity_hmac_key
        if service_identity_hmac_key is not None
        else os.environ.get("HXY_SERVICE_IDENTITY_HMAC_KEY", "")
    )
    del material_understanding_builder
    resolved_product_auth_settings = product_auth_settings or ProductAuthSettings.from_environment()
    model_router = model_router or ModelRouter()
    brand_constitution = BrandConstitutionAdapter(resolved_root)
    require_api_token = _require_api_token(settings.api_token)
    allowed_upload_extensions = {extension.lower() for extension in settings.allowed_upload_extensions}

    app = FastAPI(title="HXY Knowledge API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(
        create_identity_router(
            make_product_identity_repository,
            resolved_product_auth_settings,
        )
    )
    if make_onboarding_repository is not None and validated_onboarding_public_app_url:
        app.include_router(
            create_onboarding_router(
                make_product_identity_repository,
                make_onboarding_repository,
                resolved_product_auth_settings,
                validated_onboarding_public_app_url,
            )
        )

    def evaluate_journey_training(*, request: Any, principal: Any, assignment: Any) -> dict[str, Any]:
        legacy_request = TrainingEvaluateRequest(
            employee_answer=request.employee_answer,
            customer_question=request.customer_question,
            employee_id=principal.account_id,
            employee_name=principal.display_name,
            store_id=assignment.store_id or "organization",
            store_name=assignment.store_name or assignment.organization_name,
        )
        return _evaluate_training_content(
            request=legacy_request,
            model_router=model_router,
            root_dir=resolved_root,
        )

    resolved_journey_training_evaluator = (
        journey_training_evaluator or evaluate_journey_training
    )
    answer_hooks = AnswerServiceHooks(
        classify_frontdoor=_classify_frontdoor,
        repository_search=_repository_search,
        items_need_better_retrieval=_items_need_better_retrieval,
        fallback_queries=_fallback_queries,
        answer_from_authority_card=_answer_from_authority_card,
        attach_model_route=_attach_model_route,
        attach_answer_pipeline=_attach_answer_pipeline,
        apply_frontdoor_to_answer=_apply_frontdoor_to_answer,
        maybe_apply_model_answer=_maybe_apply_model_answer,
    )

    def generate_product_answer(
        *,
        question: str,
        assignment: Any,
        answer_route: str = "hxy_official",
    ) -> dict[str, Any]:
        scenario_by_role = {
            "founder": "创始人内部决策",
            "hq_operations": "总部运营工作问答",
            "store_manager": "店长现场经营",
            "store_employee": "门店员工工作问答",
            "system_admin": "系统管理内部问答",
        }
        answer_role_by_role = {
            "founder": "founder",
            "hq_operations": "headquarters",
            "store_manager": "store_manager",
            "store_employee": "store_staff",
            "system_admin": "system_admin",
        }
        answer_role = answer_role_by_role.get(assignment.role, "team")
        started_at = time.perf_counter()
        retrieval_trace: dict[str, Any] = {}
        if answer_route == "general":
            answer = generate_general_answer(question, model_router=model_router)
        else:
            context_repository = AssignmentKnowledgeRepository(
                make_repository(),
                make_material_repository(),
                assignment_id=assignment.assignment_id,
            )
            answer = answer_service.generate_answer(
                question=question,
                scenario=scenario_by_role.get(assignment.role, "组织内部工作问答"),
                domain=None,
                stage=None,
                limit=5,
                repository=context_repository,
                model_router=model_router,
                hooks=answer_hooks,
                role=answer_role,
                pipeline_role=answer_role,
                brand_constitution=brand_constitution,
            )
            retrieval_trace = context_repository.retrieval_trace()
            answer = enforce_intake_route_policy(
                answer,
                question=question,
                answer_route=answer_route,
            )
        private_evidence = [
            item
            for item in (answer.get("evidence") or answer.get("sources") or [])
            if isinstance(item, dict) and item.get("source_type") == "private_material"
        ]
        private_count = max(
            int(retrieval_trace.get("private_material_count") or 0),
            len(private_evidence),
        )
        authority_card_hit = bool(answer.get("from_answer_card"))
        if private_count and not authority_card_hit:
            answer["answer_status"] = "AI 草稿"
            answer["needs_review"] = True
            if answer.get("confidence") == "high":
                answer["confidence"] = "medium"

        model_route = answer.get("model_route") if isinstance(answer.get("model_route"), dict) else {}
        model_name = str(
            model_route.get("model")
            or model_route.get("model_name")
            or model_route.get("provider")
            or ""
        )
        usage = answer.get("model_usage") if isinstance(answer.get("model_usage"), dict) else {}
        answer["_product_trace"] = {
            "trace_id": str(uuid4()),
            "assignment_id": assignment.assignment_id,
            "role": assignment.role,
            "intent": str(answer.get("intent") or "unknown")[:120],
            "retrieval_count": int(retrieval_trace.get("retrieval_count") or 0),
            "private_material_count": private_count,
            "authority_card_hit": authority_card_hit,
            "model_name": model_name[:120],
            "input_tokens": usage.get("input_tokens"),
            "output_tokens": usage.get("output_tokens"),
            "latency_ms": max(0, round((time.perf_counter() - started_at) * 1000)),
            "payload": {
                "source_types": sorted(
                    {
                        str(item.get("source_type") or "unknown")[:80]
                        for item in (answer.get("evidence") or answer.get("sources") or [])
                        if isinstance(item, dict)
                    }
                ),
                "private_material_ids": sorted(
                    {
                        str(item.get("material_id") or item.get("asset_id") or "")
                        for item in private_evidence
                        if item.get("material_id") or item.get("asset_id")
                    }
                )[:20],
            },
        }
        return answer

    resolved_route_classifier = (
        intake_route_classifier or build_model_assisted_route_classifier(model_router)
    )
    resolved_answer_generator = product_answer_generator or generate_product_answer

    app.include_router(
        create_conversation_router(
            make_product_identity_repository,
            make_conversation_repository,
            resolved_answer_generator,
            resolved_route_classifier,
        )
    )
    app.include_router(
        create_intake_router(
            make_product_identity_repository,
            make_channel_repository,
            make_record_repository,
            make_conversation_repository,
            resolved_answer_generator,
            resolved_route_classifier,
        )
    )
    app.include_router(
        create_material_router(
            make_product_identity_repository,
            make_material_repository,
            material_root=resolved_root / "data" / "product-materials",
            max_upload_bytes=settings.max_upload_bytes,
            max_assignment_storage_bytes=settings.max_material_storage_bytes,
            min_material_free_bytes=settings.min_material_free_bytes,
            allowed_extensions=allowed_upload_extensions,
        )
    )
    app.include_router(
        create_task_router(
            make_product_identity_repository,
            make_task_repository,
        )
    )
    app.include_router(
        create_operating_router(
            make_product_identity_repository,
            make_channel_repository,
            make_operating_repository,
            service_builder=build_operating_service,
        )
    )
    app.include_router(
        create_record_router(
            make_product_identity_repository,
            make_channel_repository,
            make_record_repository,
        )
    )
    app.include_router(
        create_briefing_router(
            make_product_identity_repository,
            make_briefing_repository,
        )
    )
    app.include_router(
        create_evidence_router(
            make_product_identity_repository,
            make_evidence_repository,
        )
    )
    app.include_router(
        create_journey_router(
            make_product_identity_repository,
            make_task_repository,
            make_product_training_repository,
            resolved_journey_training_evaluator,
        )
    )
    app.include_router(
        create_learning_router(
            make_product_identity_repository,
            make_product_training_repository,
            resolved_journey_training_evaluator,
        )
    )
    app.include_router(
        create_service_router(
            make_product_identity_repository,
            make_service_repository,
            identity_hmac_key=resolved_service_identity_hmac_key,
        )
    )

    def _resolve_p0_run_dir(run_id: str) -> tuple[str, Path]:
        normalized_run_id = run_id.strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", normalized_run_id):
            raise HTTPException(status_code=400, detail="Invalid run_id")
        runs_root = (resolved_root / "knowledge" / "runs").resolve()
        run_dir = (runs_root / normalized_run_id).resolve()
        if not run_dir.is_relative_to(runs_root):
            raise HTTPException(status_code=400, detail="Invalid run_id")
        return normalized_run_id, run_dir

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {
            "service": "hxy-knowledge-api",
            "status": "ok",
            "root_dir": str(resolved_root),
            "inbox_path": str(inbox_dir),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    @app.get("/brain.html")
    async def brain_page() -> HTMLResponse:
        for page in [
            resolved_root / "apps" / "admin-web" / "brain.html",
            project_root / "apps" / "admin-web" / "brain.html",
        ]:
            if page.exists():
                return HTMLResponse(page.read_text(encoding="utf-8"))
        raise HTTPException(status_code=404, detail="brain.html not found")

    @app.get("/startup.html")
    async def startup_stage_page() -> HTMLResponse:
        for page in [
            resolved_root / "apps" / "admin-web" / "startup.html",
            project_root / "apps" / "admin-web" / "startup.html",
        ]:
            if page.exists():
                return HTMLResponse(page.read_text(encoding="utf-8"))
        raise HTTPException(status_code=404, detail="startup.html not found")

    @app.get("/knowledge.html")
    async def knowledge_page() -> HTMLResponse:
        for page in [
            resolved_root / "apps" / "admin-web" / "knowledge.html",
            project_root / "apps" / "admin-web" / "knowledge.html",
        ]:
            if page.exists():
                return HTMLResponse(page.read_text(encoding="utf-8"))
        raise HTTPException(status_code=404, detail="knowledge.html not found")

    @app.get("/employee/training")
    async def employee_training_page() -> HTMLResponse:
        for page in [
            resolved_root / "apps" / "employee-web" / "training.html",
            project_root / "apps" / "employee-web" / "training.html",
        ]:
            if page.exists():
                return HTMLResponse(page.read_text(encoding="utf-8"))
        raise HTTPException(status_code=404, detail="employee training page not found")

    @app.get("/manager/training")
    async def manager_training_page() -> HTMLResponse:
        for page in [
            resolved_root / "apps" / "manager-web" / "training.html",
            project_root / "apps" / "manager-web" / "training.html",
        ]:
            if page.exists():
                return HTMLResponse(page.read_text(encoding="utf-8"))
        raise HTTPException(status_code=404, detail="manager training page not found")

    @app.get("/api/knowledge/summary")
    async def knowledge_summary() -> dict[str, Any]:
        return make_repository().summary()

    @app.get("/api/knowledge/assets")
    async def knowledge_assets(limit: int = Query(default=100, ge=1, le=500)) -> dict[str, Any]:
        items = make_repository().assets(limit=limit)
        return {"items": items, "count": len(items)}

    @app.get("/api/knowledge/search")
    async def knowledge_search(
        q: str = Query(min_length=1),
        domain: str | None = None,
        stage: str | None = None,
        limit: int = Query(default=20, ge=1, le=100),
    ) -> dict[str, Any]:
        items = make_repository().search(q, domain=domain, stage=stage, limit=limit)
        return {"items": items, "count": len(items), "query": q}

    @app.get("/api/operating-brain/capabilities")
    async def operating_brain_capabilities_endpoint() -> dict[str, Any]:
        return operating_brain_capabilities()

    @app.get("/api/operating-brain/core10-activation-packet")
    async def operating_brain_core10_activation_packet_endpoint(
        principal: Principal = Depends(resolve_product_principal),
        repository: Any = Depends(get_product_identity_repository),
    ) -> dict[str, Any]:
        assignment = assignment_for_principal(principal, repository)
        if assignment.role != "founder":
            raise HTTPException(status_code=403, detail="Forbidden")
        packet = _latest_core10_activation_packet(resolved_root)
        if packet is None:
            raise HTTPException(
                status_code=404,
                detail="Core-10 activation packet not found",
            )
        return _core10_public_packet(packet)

    @app.post("/api/operating-brain/core10-activation-decision-preview")
    async def operating_brain_core10_activation_decision_preview_endpoint(
        request: Core10ActivationDecisionPreviewRequest,
        principal: Principal = Depends(resolve_product_principal),
        repository: Any = Depends(get_product_identity_repository),
    ) -> dict[str, Any]:
        assignment = assignment_for_principal(principal, repository)
        if assignment.role != "founder":
            raise HTTPException(status_code=403, detail="Forbidden")
        packet = _latest_core10_activation_packet(resolved_root)
        if packet is None:
            raise HTTPException(
                status_code=404,
                detail="Core-10 activation packet not found",
            )
        payload = request.model_dump()
        payload["actor"] = {
            "id": principal.account_id,
            "role": assignment.role,
        }
        return validate_core10_activation_decisions(packet, payload)

    @app.get("/api/operating-brain/model-router")
    async def operating_brain_model_router_endpoint() -> dict[str, Any]:
        return model_router.status()

    @app.get("/api/operating-brain/product-contracts")
    async def operating_brain_product_contracts_endpoint() -> dict[str, Any]:
        return _product_contracts()

    @app.get("/api/operating-brain/retrieval-apps")
    async def operating_brain_retrieval_apps_endpoint() -> dict[str, Any]:
        return {
            "version": "hxyos-retrieval-app-catalog.v1",
            "items": RETRIEVAL_APP_CATALOG,
            "count": len(RETRIEVAL_APP_CATALOG),
            "authority_rules": HXYOS_AUTHORITY_RULES,
            "authority_rule": "retrieval_apps_can_surface_evidence_but_cannot_publish_approved_knowledge",
        }

    @app.get("/api/operating-brain/intent-definitions")
    async def operating_brain_intent_definitions_endpoint() -> dict[str, Any]:
        return {
            "version": "hxyos-intent-definition-catalog.v1",
            "items": INTENT_DEFINITION_CATALOG,
            "count": len(INTENT_DEFINITION_CATALOG),
            "authority_rules": HXYOS_AUTHORITY_RULES,
            "authority_rule": "intent_planning_routes_work_but_does_not_override_knowledge_governance",
        }

    @app.get("/api/operating-brain/skills")
    async def operating_brain_skills_endpoint() -> dict[str, Any]:
        return {
            "version": "hxyos-skill-registry.v1",
            "items": SKILL_REGISTRY_CATALOG,
            "count": len(SKILL_REGISTRY_CATALOG),
            "authority_rules": HXYOS_AUTHORITY_RULES,
            "authority_rule": "skill_outputs_are_drafts_until_human_review_promotes_them",
        }

    @app.post(
        "/api/operating-brain/skills/hxy-compliance-language-check/run",
        dependencies=[Depends(require_api_token)],
    )
    async def operating_brain_compliance_language_check_run_endpoint(
        request: ComplianceLanguageCheckRequest,
    ) -> dict[str, Any]:
        if not settings.api_token:
            raise HTTPException(status_code=503, detail="HXY_API_TOKEN is required for compliance language check")
        if not request.text.strip():
            raise HTTPException(status_code=400, detail="text is required")
        return _compliance_language_check_result(request, root_dir=resolved_root)

    @app.post(
        "/api/operating-brain/workflow-gates/compliance/run",
        dependencies=[Depends(require_api_token)],
    )
    async def operating_brain_compliance_workflow_gate_run_endpoint(
        request: ComplianceWorkflowGateRequest,
    ) -> dict[str, Any]:
        if not settings.api_token:
            raise HTTPException(status_code=503, detail="HXY_API_TOKEN is required for compliance workflow gate")
        if not request.text.strip():
            raise HTTPException(status_code=400, detail="text is required")
        return _compliance_workflow_gate_result(request, root_dir=resolved_root)

    @app.get("/api/operating-brain/automation-tasks")
    async def operating_brain_automation_tasks_endpoint() -> dict[str, Any]:
        return {
            "version": "hxyos-automation-task-catalog.v1",
            "items": AUTOMATION_TASK_CATALOG,
            "count": len(AUTOMATION_TASK_CATALOG),
            "authority_rules": HXYOS_AUTHORITY_RULES,
            "authority_rule": "automation_tasks_must_stop_before_approved_publication",
        }

    @app.get("/api/operating-brain/evals/golden")
    async def operating_brain_golden_eval_endpoint() -> dict[str, Any]:
        return run_golden_evals(
            questions=golden_questions(),
            cards=authority_cards(),
            model_router=model_router,
        )

    @app.get("/api/operating-brain/brand-assets")
    async def operating_brain_brand_assets_endpoint() -> dict[str, Any]:
        return build_brand_asset_center()

    @app.get("/api/operating-brain/brand-risk-rules")
    async def operating_brain_brand_risk_rules_endpoint() -> dict[str, Any]:
        return load_brand_risk_rules(root_dir=resolved_root)

    @app.get("/api/operating-brain/brand-answer-cards")
    async def operating_brain_brand_answer_cards_endpoint(
        limit: int = Query(default=100, ge=1, le=200),
    ) -> dict[str, Any]:
        items = [_public_answer_card(card, source="brand_assets") for card in brand_authority_cards()]
        return {
            "version": "hxy-brand-answer-cards.v1",
            "stage": "pre_open_brand_first",
            "items": items[:limit],
            "count": len(items[:limit]),
            "total": len(items),
        }

    @app.post("/api/operating-brain/startup-advance", dependencies=[Depends(require_api_token)])
    async def operating_brain_startup_advance_endpoint(request: StartupAdvanceRequest) -> dict[str, Any]:
        try:
            return build_startup_advance(
                action=request.action,
                evidence_input=request.evidence_input,
                current_conclusion=request.current_conclusion,
                main_question=request.main_question,
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.get("/api/operating-brain/okf/summary")
    async def operating_brain_okf_summary_endpoint() -> dict[str, Any]:
        okf_root = resolved_root / "knowledge" / "okf"
        documents = load_okf_documents(okf_root)
        summary = summarize_okf_lifecycle(documents)
        summary["root"] = "knowledge/okf"
        summary["documents"] = [
            {
                key: value
                for key, value in document.items()
                if key not in {"body", "path"}
            }
            for document in documents[:50]
        ]
        return summary

    @app.get("/api/operating-brain/knowledge-governance")
    async def operating_brain_knowledge_governance_endpoint() -> dict[str, Any]:
        repo = make_repository()
        list_assets = getattr(repo, "assets", None)
        assets = list_assets(limit=500) if callable(list_assets) else []
        structured = _load_structured_governance_inputs(resolved_root)
        answer_cards = [
            _public_answer_card(card, source="brand_assets")
            for card in brand_authority_cards()
        ]
        answer_cards.extend(
            _public_answer_card(card, source="repository")
            for card in _list_repository_answer_cards(repo, status=None, limit=500)
        )
        okf_documents = load_okf_documents(resolved_root / "knowledge" / "okf")
        report = build_enterprise_governance_report(
            assets=assets,
            claims=structured["claims"],
            evidence=structured["evidence"],
            relations=structured["relations"],
            answer_cards=answer_cards,
            okf_documents=okf_documents,
        )
        report["source"] = {
            "assets": "repository",
            "structured": "quarantine/knowledge-assets/structured + knowledge/structured",
            "answer_cards": "brand_assets + repository",
        }
        return report

    @app.post("/api/operating-brain/incremental-compile-plan")
    async def operating_brain_incremental_compile_plan_endpoint(request: IncrementalCompilePlanRequest) -> dict[str, Any]:
        return build_incremental_compile_plan(
            previous_manifest=request.previous_manifest,
            current_manifest=request.current_manifest,
            relations=request.relations,
        )

    @app.get("/api/operating-brain/file-manifest")
    async def operating_brain_file_manifest_endpoint() -> dict[str, Any]:
        return build_file_manifest(
            inbox_dir,
            root_dir=resolved_root,
            ignore_globs=["*.tmp", "*.part", ".DS_Store", "~$*"],
        )

    @app.get("/api/operating-brain/benchmark")
    async def operating_brain_benchmark_endpoint() -> dict[str, Any]:
        report = _read_json_file(resolved_root / "knowledge" / "reports" / "benchmark-latest.json")
        return _benchmark_status_from_report(report)

    @app.get("/api/operating-brain/benchmark/corrections")
    async def operating_brain_benchmark_corrections_endpoint(
        limit: int = Query(default=20, ge=1, le=100),
    ) -> dict[str, Any]:
        payload = _read_json_file(
            resolved_root / "knowledge" / "runs" / "benchmark-loop-latest" / "benchmark-corrections.json"
        )
        return _benchmark_corrections_from_payload(payload, limit=limit)

    @app.get("/api/v1/hxy/p0/reviewer-todo")
    async def hxy_p0_reviewer_todo_endpoint(
        run_id: str = Query(default="benchmark-loop-latest", min_length=1, max_length=80),
    ) -> dict[str, Any]:
        normalized_run_id, run_dir = _resolve_p0_run_dir(run_id)
        payload = _read_json_file(run_dir / "p0-reviewer-todo.json")
        return _p0_reviewer_todo_from_payload(payload, run_id=normalized_run_id)

    @app.get("/api/v1/hxy/p0/governance-status")
    async def hxy_p0_governance_status_endpoint(
        run_id: str = Query(default="benchmark-loop-latest", min_length=1, max_length=80),
    ) -> dict[str, Any]:
        normalized_run_id, run_dir = _resolve_p0_run_dir(run_id)
        status = build_p0_governance_status(
            run_dir,
            benchmark_path=resolved_root / "knowledge" / "benchmarks" / "hxy-brain-benchmark-v1.json",
            report_path=resolved_root / "knowledge" / "reports" / "benchmark-latest.json",
        )
        return {
            **status,
            "run_id": normalized_run_id,
            "p0_reviewer_todo_url": f"/api/v1/hxy/p0/reviewer-todo?run_id={normalized_run_id}",
            "official_use_allowed": False,
            "publish_allowed": False,
            "write_to_database": False,
        }

    @app.get("/api/v1/hxy/p0/notification")
    async def hxy_p0_notification_endpoint(
        run_id: str = Query(default="benchmark-loop-latest", min_length=1, max_length=80),
    ) -> dict[str, Any]:
        normalized_run_id, run_dir = _resolve_p0_run_dir(run_id)
        status = build_p0_governance_status(
            run_dir,
            benchmark_path=resolved_root / "knowledge" / "benchmarks" / "hxy-brain-benchmark-v1.json",
            report_path=resolved_root / "knowledge" / "reports" / "benchmark-latest.json",
        )
        return _p0_governance_notification_from_status(status, run_id=normalized_run_id)

    @app.post("/api/v1/hxy/p0/decision-preview")
    async def hxy_p0_decision_preview_endpoint(
        request: P0DecisionPreviewRequest,
        run_id: str = Query(default="benchmark-loop-latest", min_length=1, max_length=80),
    ) -> dict[str, Any]:
        normalized_run_id, run_dir = _resolve_p0_run_dir(run_id)
        stub = _read_json_file(run_dir / "p0-review-decisions.stub.json")
        if not stub:
            raise HTTPException(status_code=404, detail="p0-review-decisions.stub.json not found")
        validation = validate_p0_review_decisions(stub, request.decisions)
        return {
            "version": "hxy-p0-decision-preview.v1",
            "run_id": normalized_run_id,
            "preview_only": True,
            "valid": bool(validation.get("valid")),
            "validation": validation,
            "official_use_allowed": False,
            "publish_allowed": False,
            "write_to_database": False,
            "requires_human_review": True,
            "authority_rule": "decision_preview_validates_payload_without_writing_manual_decisions",
        }

    @app.get("/api/operating-brain/knowledge-compiler/status")
    async def operating_brain_knowledge_compiler_status_endpoint() -> dict[str, Any]:
        report = _read_json_file(resolved_root / "knowledge" / "reports" / "compiler-latest.json")
        return _compiler_status_from_report(report)

    @app.get("/api/operating-brain/knowledge-compiler/review-queue")
    async def operating_brain_knowledge_compiler_review_queue_endpoint(
        limit: int = Query(default=20, ge=1, le=100),
    ) -> dict[str, Any]:
        payload = _read_json_file(resolved_root / "knowledge" / "wiki" / "review-queue.json")
        return _compiler_review_queue_from_payload(payload, limit=limit)

    @app.get("/api/operating-brain/knowledge-compiler/claim-triage")
    async def operating_brain_knowledge_compiler_claim_triage_endpoint(
        limit: int = Query(default=200, ge=1, le=200),
    ) -> dict[str, Any]:
        payload = _read_json_file(resolved_root / "knowledge" / "wiki" / "claim-triage.json")
        return _compiler_claim_triage_from_payload(payload, limit=limit)

    @app.get("/api/operating-brain/knowledge-compiler/review-topics")
    async def operating_brain_knowledge_compiler_review_topics_endpoint(
        limit: int = Query(default=12, ge=1, le=50),
    ) -> dict[str, Any]:
        core_payload = _read_json_file(resolved_root / "knowledge" / "wiki" / "core-decision-topics.json")
        core_topics = _compiler_core_decision_topics_from_payload(core_payload, limit=limit)
        if core_topics is not None:
            return core_topics
        payload = _read_json_file(resolved_root / "knowledge" / "wiki" / "claim-triage.json")
        return _compiler_review_topics_from_payload(payload, limit=limit)

    @app.get("/api/operating-brain/knowledge-compiler/topic-draft-assets")
    async def operating_brain_knowledge_compiler_topic_draft_assets_endpoint(
        limit: int = Query(default=12, ge=1, le=50),
    ) -> dict[str, Any]:
        payload = _read_json_file(resolved_root / "knowledge" / "wiki" / "topic-draft-assets.json")
        return _compiler_topic_draft_assets_from_payload(payload, limit=limit)

    @app.get("/api/operating-brain/knowledge-compiler/topic-review-packets")
    async def operating_brain_knowledge_compiler_topic_review_packets_endpoint(
        limit: int = Query(default=12, ge=1, le=50),
    ) -> dict[str, Any]:
        payload = _read_json_file(resolved_root / "knowledge" / "wiki" / "topic-review-packets.json")
        return _compiler_topic_review_packets_from_payload(payload, limit=limit)

    @app.get("/api/operating-brain/knowledge-compiler/topic-review-decisions")
    async def operating_brain_knowledge_compiler_topic_review_decisions_endpoint() -> dict[str, Any]:
        wiki_root = resolved_root / "knowledge" / "wiki"
        packet_payload = _read_json_file(wiki_root / "topic-review-packets.json")
        stub_payload = _read_json_file(wiki_root / "topic-review-decisions.stub.json")
        sample_payload = _read_json_file(wiki_root / "topic-review-decisions.sample.json")
        decisions_payload = _read_json_file(wiki_root / "topic-review-decisions.json")
        return _compiler_topic_review_decisions_workflow_from_payloads(
            packet_payload=packet_payload,
            stub_payload=stub_payload,
            sample_payload=sample_payload,
            decisions_payload=decisions_payload,
        )

    @app.post("/api/operating-brain/knowledge-compiler/topic-review-decision-preview")
    async def operating_brain_knowledge_compiler_topic_review_decision_preview_endpoint(
        request: TopicReviewDecisionPreviewRequest,
    ) -> dict[str, Any]:
        packet_payload = _read_json_file(resolved_root / "knowledge" / "wiki" / "topic-review-packets.json")
        if not packet_payload:
            raise HTTPException(status_code=404, detail="topic-review-packets.json not found")
        validation = validate_topic_review_decisions(packet_payload, request.decisions)
        return {
            "version": "hxy-topic-review-decision-preview.v1",
            "preview_only": True,
            "valid": bool(validation.get("valid")),
            "validation": validation,
            "official_use_allowed": False,
            "publish_allowed": False,
            "write_to_database": False,
            "requires_human_review": True,
            "authority_rule": "topic_review_decision_preview_validates_payload_without_writing",
        }

    @app.get("/api/operating-brain/knowledge-compiler/topic-publication-preflight")
    async def operating_brain_knowledge_compiler_topic_publication_preflight_endpoint() -> dict[str, Any]:
        wiki_root = resolved_root / "knowledge" / "wiki"
        packet_payload = _read_json_file(wiki_root / "topic-review-packets.json") or {
            "version": "hxy-topic-review-packets.v1",
            "items": [],
        }
        decisions_payload = _read_json_file(wiki_root / "topic-review-decisions.json")
        return build_topic_publication_preflight(packet_payload, decisions_payload)

    @app.get("/api/operating-brain/knowledge-compiler/topic-publication-package")
    async def operating_brain_knowledge_compiler_topic_publication_package_endpoint() -> dict[str, Any]:
        wiki_root = resolved_root / "knowledge" / "wiki"
        packet_payload = _read_json_file(wiki_root / "topic-review-packets.json") or {
            "version": "hxy-topic-review-packets.v1",
            "items": [],
        }
        decisions_payload = _read_json_file(wiki_root / "topic-review-decisions.json")
        preflight = build_topic_publication_preflight(packet_payload, decisions_payload)
        return build_topic_publication_package(preflight)

    @app.get("/api/operating-brain/knowledge-compiler/topic-publication-dry-run")
    async def operating_brain_knowledge_compiler_topic_publication_dry_run_endpoint() -> dict[str, Any]:
        wiki_root = resolved_root / "knowledge" / "wiki"
        packet_payload = _read_json_file(wiki_root / "topic-review-packets.json") or {
            "version": "hxy-topic-review-packets.v1",
            "items": [],
        }
        decisions_payload = _read_json_file(wiki_root / "topic-review-decisions.json")
        preflight = build_topic_publication_preflight(packet_payload, decisions_payload)
        publication_package = build_topic_publication_package(preflight)
        return dry_run_topic_publication_package(publication_package)

    @app.get("/api/operating-brain/knowledge-compiler/topic-reviewed-assets-import-gate")
    async def operating_brain_knowledge_compiler_topic_reviewed_assets_import_gate_endpoint() -> dict[str, Any]:
        wiki_root = resolved_root / "knowledge" / "wiki"
        reviewed_file = _read_json_file(wiki_root / "topic-reviewed-assets.json") or {
            "version": "hxy-topic-reviewed-assets-publication.v1",
            "reviewed_topic_assets": [],
        }
        existing_payload = _read_json_file(wiki_root / "topic-approved-assets.json") or {"items": []}
        existing_assets = existing_payload.get("items") if isinstance(existing_payload.get("items"), list) else []
        return validate_topic_reviewed_assets_import_gate(reviewed_file, existing_assets)

    @app.get("/api/operating-brain/knowledge-compiler/compliance-review-pack")
    async def operating_brain_knowledge_compiler_compliance_review_pack_endpoint(
        limit: int = Query(default=20, ge=1, le=100),
    ) -> dict[str, Any]:
        payload = _read_json_file(resolved_root / "knowledge" / "wiki" / "compliance-review-pack.json")
        return _compiler_compliance_review_pack_from_payload(payload, limit=limit)

    @app.get("/api/operating-brain/ingest-loop/status")
    async def operating_brain_ingest_loop_status_endpoint() -> dict[str, Any]:
        payload = _read_json_file(ingest_loop_state_path)
        if not payload:
            return {
                "version": "hxy-ingest-loop-status.v1",
                "status": "missing",
                "official_use_allowed": False,
                "next_actions": ["运行资料入库 Loop，把 inbox 资料编译到人工复核队列。"],
            }
        return {
            "version": "hxy-ingest-loop-status.v1",
            **payload,
            "official_use_allowed": False,
            "authority_rule": "ingest_loop_outputs_are_candidates_until_human_review",
        }

    @app.post("/api/operating-brain/ingest-loop/run", dependencies=[Depends(require_api_token)])
    async def operating_brain_ingest_loop_run_endpoint() -> dict[str, Any]:
        return run_ingest_loop(
            raw_dir=resolved_root / "knowledge" / "raw" / "inbox",
            wiki_dir=resolved_root / "knowledge" / "wiki",
            report_path=resolved_root / "knowledge" / "reports" / "ingest-latest.json",
            runs_dir=resolved_root / "knowledge" / "runs",
            run_id="ingest-loop-latest",
            root_dir=resolved_root,
        )

    @app.post("/api/operating-brain/brand-decision/review", dependencies=[Depends(require_api_token)])
    async def operating_brain_brand_decision_review_endpoint(request: BrandDecisionRequest) -> dict[str, Any]:
        review = review_brand_artifact(request.model_dump())
        preflight = _compliance_preflight_for_text(
            request.text,
            workflow_type=_workflow_type_for_brand_artifact(request.artifact_type),
            channel=request.artifact_type,
            audience="customer",
            root_dir=resolved_root,
        )
        review["compliance_preflight"] = preflight
        review["can_continue"] = bool(preflight.get("can_continue"))
        review["can_publish"] = False
        review_path = write_brand_review_record(review, reviews_dir=resolved_root / "knowledge" / "brand" / "reviews")
        return {**review, "review_path": review_path.as_posix()}

    @app.post("/api/operating-brain/menu-draft/preflight", dependencies=[Depends(require_api_token)])
    async def operating_brain_menu_draft_preflight_endpoint(request: MenuDraftPreflightRequest) -> dict[str, Any]:
        if not request.text.strip():
            raise HTTPException(status_code=400, detail="text is required")
        preflight = _compliance_preflight_for_text(
            request.text,
            workflow_type="project_menu",
            channel=request.channel,
            audience=request.audience,
            root_dir=resolved_root,
        )
        return {
            "version": "hxy-menu-draft-compliance-preflight.v1",
            "compliance_preflight": preflight,
            "can_save_draft": bool(preflight.get("can_continue")),
            "write_to_database": False,
            "can_publish": False,
            "official_use_allowed": False,
            "authority_rule": "menu_draft_preflight_is_dry_run_and_does_not_save_menu_data",
        }

    @app.post(
        "/api/operating-brain/knowledge-compiler/review-queue/{claim_id}/decision",
        dependencies=[Depends(require_api_token)],
    )
    async def operating_brain_knowledge_compiler_review_decision_endpoint(
        claim_id: str,
        request: CompilerReviewDecisionRequest,
    ) -> dict[str, Any]:
        action = request.action.strip()
        if action not in {"pass_to_draft", "reject", "needs_revision"}:
            raise HTTPException(status_code=400, detail="action must be pass_to_draft, reject, or needs_revision")
        queue = _compiler_review_queue_from_payload(
            _read_json_file(resolved_root / "knowledge" / "wiki" / "review-queue.json"),
            limit=100,
        )
        item = next((entry for entry in queue.get("items", []) if str(entry.get("claim_id")) == claim_id), None)
        if not item:
            raise HTTPException(status_code=404, detail="review queue claim not found")
        answer_card_draft = _answer_card_draft_from_review_item(item, request.revised_claim) if action == "pass_to_draft" else None
        decision = {
            "version": "hxy-compiler-review-decision.v1",
            "claim_id": claim_id,
            "action": action,
            "reviewer": request.reviewer.strip() or "unknown",
            "note": request.note.strip(),
            "revised_claim": request.revised_claim.strip(),
            "decided_at": datetime.now(timezone.utc).isoformat(),
            "source_item": item,
            "answer_card_draft": answer_card_draft,
            "official_use_allowed": False,
            "authority_rule": "compiler_review_decision_never_auto_approves_knowledge",
        }
        _append_compiler_review_decision(
            resolved_root / "knowledge" / "wiki" / "review-decisions.json",
            decision,
        )
        return {
            "version": "hxy-compiler-review-decision.v1",
            "decision": decision,
            "answer_card_draft": answer_card_draft,
            "status": "recorded",
        }

    def _build_current_governance_run_package(run_id: str) -> tuple[dict[str, Any], Any]:
        repo = make_repository()
        list_assets = getattr(repo, "assets", None)
        assets = list_assets(limit=500) if callable(list_assets) else []
        structured = _load_structured_governance_inputs(resolved_root)
        answer_cards = [
            _public_answer_card(card, source="brand_assets")
            for card in brand_authority_cards()
        ]
        answer_cards.extend(
            _public_answer_card(card, source="repository")
            for card in _list_repository_answer_cards(repo, status=None, limit=500)
        )
        okf_documents = load_okf_documents(resolved_root / "knowledge" / "okf")
        governance_report = build_enterprise_governance_report(
            assets=assets,
            claims=structured["claims"],
            evidence=structured["evidence"],
            relations=structured["relations"],
            answer_cards=answer_cards,
            okf_documents=okf_documents,
        )
        current_manifest = build_file_manifest(
            inbox_dir,
            root_dir=resolved_root,
            ignore_globs=["*.tmp", "*.part", ".DS_Store", "~$*"],
        )
        package = build_governance_run_package(
            run_id=run_id,
            previous_manifest={},
            current_manifest=current_manifest,
            governance_report=governance_report,
            relations=structured["relations"],
        )
        return package, repo

    @app.get("/api/operating-brain/governance-run-package")
    async def operating_brain_governance_run_package_endpoint(
        run_id: str = Query(default="current", min_length=1, max_length=80),
    ) -> dict[str, Any]:
        package, _repo = _build_current_governance_run_package(run_id)
        return package

    @app.post("/api/operating-brain/governance-run-package/review-tasks", dependencies=[Depends(require_api_token)])
    async def operating_brain_governance_run_package_review_tasks_endpoint(
        run_id: str = Query(default="current", min_length=1, max_length=80),
    ) -> dict[str, Any]:
        if not settings.api_token:
            raise HTTPException(status_code=503, detail="HXY_API_TOKEN is required for governance review task creation")
        package, repo = _build_current_governance_run_package(run_id)
        created = []
        for draft in package.get("review_task_drafts", [])[:20]:
            task_id = repo.create_review_task(
                {
                    "question": draft.get("question") or "",
                    "intent": draft.get("intent") or "knowledge_governance",
                    "reason": draft.get("reason") or "knowledge_governance",
                    "priority": draft.get("priority") or "medium",
                    "correction_package": draft.get("correction_package") or {},
                    "payload_json": draft.get("payload_json") or {},
                }
            )
            created.append(
                {
                    "task_id": task_id,
                    "dedupe_key": draft.get("dedupe_key") or "",
                    "reason": draft.get("reason") or "",
                    "priority": draft.get("priority") or "medium",
                }
            )
        package["created_review_tasks"] = created
        return package

    def _build_process_memory_preview(request: ProcessMemoryRequest) -> dict[str, Any]:
        text = request.text.strip()
        if not text:
            raise HTTPException(status_code=400, detail="text is required")
        record = build_process_memory_record(
            text,
            source=request.source.strip() or "chat",
            actor=request.actor.strip() or "unknown",
            observed_at=request.observed_at,
            confidence=request.confidence,
        )
        promotion_draft = build_memory_promotion_draft(
            record,
            target_domain=request.target_domain.strip() or "general",
        )
        return {
            "version": "hxy-process-memory-preview.v1",
            "record": record,
            "promotion_draft": promotion_draft,
            "boundary": "过程记忆只能作为上下文和晋升候选，不能直接作为企业正式知识使用。",
        }

    @app.post("/api/operating-brain/process-memory/preview")
    async def operating_brain_process_memory_preview_endpoint(request: ProcessMemoryRequest) -> dict[str, Any]:
        return _build_process_memory_preview(request)

    @app.post("/api/operating-brain/process-memory/promote", dependencies=[Depends(require_api_token)])
    async def operating_brain_process_memory_promote_endpoint(request: ProcessMemoryRequest) -> dict[str, Any]:
        if not settings.api_token:
            raise HTTPException(status_code=503, detail="HXY_API_TOKEN is required for process memory promotion")
        preview = _build_process_memory_preview(request)
        review_task = preview["promotion_draft"]["review_task"]
        repo = make_repository()
        review_task_id = repo.create_review_task(
            {
                "question": review_task["question"],
                "intent": review_task["intent"],
                "reason": review_task["reason"],
                "priority": review_task["priority"],
                "correction_package": review_task["correction_package"],
                "payload_json": {
                    "source": "process_memory",
                    "record": preview["record"],
                    "promotion_draft": preview["promotion_draft"],
                    "correction_package": review_task["correction_package"],
                },
            }
        )
        return {
            "version": "hxy-process-memory-promotion-result.v1",
            "record": preview["record"],
            "promotion_draft": preview["promotion_draft"],
            "review_task_id": review_task_id,
            "status": "review_task_created",
        }

    @app.post("/api/operating-brain/workspace/events", dependencies=[Depends(require_api_token)])
    async def operating_brain_workspace_event_create_endpoint(request: WorkspaceEventRequest) -> dict[str, Any]:
        event = create_workspace_event(request.model_dump(), store_path=workspace_event_store)
        return {
            "version": "hxy-workspace-event-created.v1",
            "event": event,
            "public_event": redact_workspace_event(event),
            "authority_rule": "workspace_events_are_episodic_memory_not_approved_knowledge",
        }

    @app.get("/api/operating-brain/workspace/events")
    async def operating_brain_workspace_event_list_endpoint(
        limit: int = Query(default=20, ge=1, le=100),
        q: str = "",
        visibility: str | None = None,
    ) -> dict[str, Any]:
        return list_workspace_events(workspace_event_store, limit=limit, query=q, visibility=visibility)

    @app.get("/api/operating-brain/workspace/events/{event_id}")
    async def operating_brain_workspace_event_get_endpoint(event_id: str) -> dict[str, Any]:
        event = get_workspace_event(workspace_event_store, event_id)
        if not event or event.get("visibility") == "private_draft":
            raise HTTPException(status_code=404, detail="workspace event not found")
        return {
            "version": "hxy-workspace-event-detail.v1",
            "event": redact_workspace_event(event),
            "authority_rule": "workspace_events_are_episodic_memory_not_approved_knowledge",
        }

    @app.post(
        "/api/operating-brain/workspace/events/{event_id}/review-task",
        dependencies=[Depends(require_api_token)],
    )
    async def operating_brain_workspace_event_review_task_endpoint(
        event_id: str,
        request: WorkspaceEventReviewTaskRequest | None = None,
    ) -> dict[str, Any]:
        event = get_workspace_event(workspace_event_store, event_id)
        if not event:
            raise HTTPException(status_code=404, detail="workspace event not found")
        if event.get("visibility") == "private_draft":
            raise HTTPException(status_code=400, detail="private_draft cannot be converted to review task directly")
        request = request or WorkspaceEventReviewTaskRequest()
        task_id = make_repository().create_review_task(
            {
                "question": event.get("topic") or "公共 AI 工作间复核任务",
                "intent": "workspace_event_review",
                "reason": "workspace_event_review",
                "priority": "high" if event.get("risk_flags") else "medium",
                "correction_package": {
                    "source": "workspace_event",
                    "event_id": event_id,
                    "risk_flags": event.get("risk_flags") or [],
                    "reviewer": request.reviewer,
                    "note": request.note,
                    "authority_rule": "workspace_event_review_task_is_not_approved_knowledge",
                },
                "payload_json": {
                    "source": "workspace_event",
                    "event": event,
                    "official_use_allowed": False,
                },
            }
        )
        return {
            "version": "hxy-workspace-event-review-task-result.v1",
            "status": "review_task_created",
            "review_task_id": task_id,
            "official_use_allowed": False,
            "authority_rule": "review_task_is_not_approved_knowledge",
        }

    @app.post(
        "/api/operating-brain/workspace/events/{event_id}/process-memory",
        dependencies=[Depends(require_api_token)],
    )
    async def operating_brain_workspace_event_process_memory_endpoint(
        event_id: str,
        request: WorkspaceEventProcessMemoryRequest | None = None,
    ) -> dict[str, Any]:
        event = get_workspace_event(workspace_event_store, event_id)
        if not event:
            raise HTTPException(status_code=404, detail="workspace event not found")
        if event.get("visibility") == "private_draft":
            raise HTTPException(status_code=400, detail="private_draft cannot be converted to process memory directly")
        request = request or WorkspaceEventProcessMemoryRequest()
        ai_output = event.get("ai_output") if isinstance(event.get("ai_output"), dict) else {}
        text = "\n".join(
            part
            for part in [
                str(event.get("topic") or ""),
                str(event.get("input") or ""),
                str(ai_output.get("summary") or ""),
            ]
            if part
        )
        preview = _build_process_memory_preview(
            ProcessMemoryRequest(
                text=text,
                source=f"workspace_event:{event_id}",
                actor=request.actor,
                confidence=request.confidence,
                target_domain=request.target_domain,
            )
        )
        preview["source_event_id"] = event_id
        preview["status"] = "process_memory_preview_created"
        preview["authority_rule"] = "process_memory_is_context_only_not_approved_knowledge"
        preview["boundary"] = (
            f"{preview['boundary']} process memory cannot be formal knowledge without human review."
        )
        return preview

    @app.get("/api/operating-brain/issues")
    async def operating_brain_issues_endpoint() -> dict[str, Any]:
        okf_root = resolved_root / "knowledge" / "okf"
        documents = load_okf_documents(okf_root)
        issues = build_operating_issues(documents)
        return {
            "version": "hxy-operating-issue-queue.v1",
            "source": "okf_lifecycle",
            "count": len(issues),
            "items": issues,
            "empty_state": "暂无经营议题。上传资料、纠偏反馈或 OKF 生命周期异常会进入这里。",
        }

    @app.post("/api/operating-brain/issues/intake", dependencies=[Depends(require_api_token)])
    async def operating_brain_issue_intake_endpoint(request: OperatingIssueIntakeRequest) -> dict[str, Any]:
        input_text = request.input.strip()
        if not input_text:
            raise HTTPException(status_code=400, detail="input is required")
        return issue_from_intake(
            input_text,
            scenario=request.scenario.strip() or "经营问答",
            role=request.role.strip() or "team",
        )

    @app.post("/api/operating-brain/understand")
    async def operating_brain_understand(request: UnderstandRequest) -> dict[str, Any]:
        input_text = request.input.strip()
        if not input_text and not request.attachments:
            raise HTTPException(status_code=400, detail="input or attachments are required")
        result = understand_text(input_text, scenario=request.scenario.strip() or "创始人内部决策", role=request.role.strip() or "founder")
        result["thinking_lenses"] = apply_thinking_lenses(input_text, stage="zero_to_one")
        return result

    @app.post("/api/operating-brain/thinking-lenses")
    async def operating_brain_thinking_lenses(request: ThinkingLensRequest) -> dict[str, Any]:
        input_text = request.input.strip()
        if not input_text:
            raise HTTPException(status_code=400, detail="input is required")
        result = apply_thinking_lenses(input_text, max_lenses=request.max_lenses, stage=request.stage.strip() or "zero_to_one")
        result["scenario"] = request.scenario.strip() or "创始人内部决策"
        return result

    @app.post("/api/operating-brain/workbench-intake")
    async def operating_brain_workbench_intake(request: WorkbenchIntakeRequest) -> dict[str, Any]:
        input_text = request.input.strip()
        if not input_text and not request.attachments:
            raise HTTPException(status_code=400, detail="input or attachments are required")
        return _classify_workbench_intake_with_model(
            model_router=model_router,
            input_text=input_text,
            scenario=request.scenario.strip() or "经营问答",
            role=request.role.strip() or "team",
            attachments=request.attachments,
        )

    @app.post("/api/operating-brain/source-brief")
    async def operating_brain_source_brief(request: SourceBriefRequest) -> dict[str, Any]:
        question = request.question.strip()
        scenario = request.scenario.strip() or "经营问答"
        if not question:
            raise HTTPException(status_code=400, detail="question is required")
        domain_hint, _hint_audience = classify_intent(question)
        repo = make_repository()
        used_query, items = _best_retrieval_candidate(
            repo,
            question,
            domain=request.domain,
            stage=request.stage,
            limit=request.limit,
            domain_hint=domain_hint,
        )
        result = build_source_brief(question, items, scenario=scenario)
        result["query"] = used_query
        result["retrieval"] = {
            "count": len(items),
            "domain_hint": domain_hint,
            "mode": "keyword_plus_domain_hint",
            "used_query": used_query,
        }
        return result

    @app.post("/api/operating-brain/store-daily-metrics", dependencies=[Depends(require_api_token)])
    async def operating_brain_store_daily_metrics(request: StoreDailyMetricsRequest) -> dict[str, Any]:
        if not request.store_id.strip():
            raise HTTPException(status_code=400, detail="store_id is required")
        if not request.business_date.strip():
            raise HTTPException(status_code=400, detail="business_date is required")
        payload = request.model_dump()
        payload["store_id"] = request.store_id.strip()
        payload["store_name"] = request.store_name.strip() or payload["store_id"]
        payload["business_date"] = request.business_date.strip()
        diagnosis = diagnose_store_daily_metrics(payload)
        metrics_id = make_repository().save_store_daily_metrics({**payload, "diagnosis": diagnosis})
        return {**diagnosis, "metrics_id": metrics_id}

    @app.get("/api/operating-brain/training/question-bank")
    async def operating_brain_training_question_bank(
        level: str | None = None,
        module: str | None = None,
    ) -> dict[str, Any]:
        items = filter_training_questions(level=level, module=module)
        return {
            "version": "hxy-training-question-bank.v1",
            "level": level or "all",
            "module": module or "all",
            "count": len(items),
            "items": items,
        }

    @app.post("/api/operating-brain/training/manager-acceptance", dependencies=[Depends(require_api_token)])
    async def operating_brain_training_manager_acceptance(request: TrainingManagerAcceptanceRequest) -> dict[str, Any]:
        session_id = (request.session_id or request.training_session_id).strip()
        if not session_id:
            raise HTTPException(status_code=400, detail="session_id is required")
        repo = make_repository()
        acceptance_evidence = repo.training_acceptance_evidence(session_id, pass_score=75, required_pass_count=2)
        onsite_verified = bool(request.onsite_verified)
        can_accept = bool(request.accepted) and bool(acceptance_evidence.get("eligible")) and onsite_verified and request.score >= 75
        payload = request.model_dump()
        payload["session_id"] = session_id
        payload["manager_id"] = request.manager_id.strip() or "manager-local"
        payload["manager_name"] = request.manager_name.strip() or "店长"
        payload["accepted"] = can_accept
        payload["onsite_verified"] = onsite_verified
        payload["acceptance_rule"] = {
            **acceptance_evidence,
            "onsite_verified": onsite_verified,
            "manager_score": request.score,
        }
        payload["requires_retrain"] = not can_accept
        metric_names = [str(item.get("metric") or "").strip() for item in request.operating_metric_links if str(item.get("metric") or "").strip()]
        payload["operating_summary"] = (
            f"本次验收关联经营指标：{'、'.join(metric_names)}。"
            if metric_names
            else "本次验收未关联具体经营指标。"
        )
        acceptance_id = repo.save_training_manager_acceptance(payload)
        capability_upgrade = None
        if can_accept:
            capability_upgrade = repo.upsert_training_capability_level(
                {
                    "employee_id": acceptance_evidence.get("employee_id") or "",
                    "store_id": acceptance_evidence.get("store_id") or "",
                    "training_item": acceptance_evidence.get("training_item") or "",
                    "current_level": "standard",
                    "accepted_count": acceptance_evidence.get("consecutive_pass_count") or 0,
                    "last_acceptance_id": acceptance_id,
                    "acceptance_evidence": payload["acceptance_rule"],
                }
            )
        next_actions = (
            [
                "通过验收后可进入下一等级训练。",
                "店长每周复盘训练结果与客单价、调补养占比、投诉风险的关系。",
            ]
            if can_accept
            else [
                "现场复述通过、同一训练项目连续 2 次达到 75 分后，才能通过验收。",
                acceptance_evidence.get("reason") or "未达到验收规则。",
                "未通过验收则回到自适应复训题库继续练习。",
            ]
        )
        return {
            "version": "hxy-training-manager-acceptance.v1",
            "acceptance_id": acceptance_id,
            "session_id": payload["session_id"],
            "accepted": can_accept,
            "requires_retrain": payload["requires_retrain"],
            "acceptance_rule": payload["acceptance_rule"],
            "capability_upgrade": capability_upgrade,
            "operating_summary": payload["operating_summary"],
            "next_actions": next_actions,
        }

    @app.post("/api/operating-brain/training/evaluate", dependencies=[Depends(require_api_token)])
    async def operating_brain_training_evaluate(request: TrainingEvaluateRequest) -> dict[str, Any]:
        return _run_training_evaluation(
            request=request,
            model_router=model_router,
            root_dir=resolved_root,
            repository=make_repository(),
        )

    @app.get("/api/operating-brain/training/manager-summary")
    async def operating_brain_training_manager_summary(
        store_id: str | None = None,
        days: int = Query(default=7, ge=1, le=90),
    ) -> dict[str, Any]:
        return make_repository().training_manager_summary(store_id=store_id, days=days)

    @app.get("/api/operating-brain/training/sessions")
    async def operating_brain_training_sessions(
        store_id: str | None = None,
        employee_id: str | None = None,
        limit: int = Query(default=50, ge=1, le=200),
    ) -> dict[str, Any]:
        items = make_repository().training_sessions(store_id=store_id, employee_id=employee_id, limit=limit)
        return {
            "version": "hxy-training-sessions.v1",
            "store_id": store_id or "all",
            "employee_id": employee_id or "all",
            "count": len(items),
            "items": items,
        }

    @app.get("/api/operating-brain/training/capability-levels")
    async def operating_brain_training_capability_levels(
        store_id: str | None = None,
        employee_id: str | None = None,
        limit: int = Query(default=50, ge=1, le=200),
    ) -> dict[str, Any]:
        items = make_repository().training_capability_levels(store_id=store_id, employee_id=employee_id, limit=limit)
        return {
            "version": "hxy-training-capability-levels.v1",
            "store_id": store_id or "all",
            "employee_id": employee_id or "all",
            "count": len(items),
            "items": items,
        }

    @app.get("/api/operating-brain/training/recommended-plan")
    async def operating_brain_training_recommended_plan(
        store_id: str | None = None,
        employee_id: str | None = None,
    ) -> dict[str, Any]:
        store = (store_id or "pilot-store").strip() or "pilot-store"
        employee = (employee_id or "employee-local").strip() or "employee-local"
        repo = make_repository()
        recent_sessions = repo.training_sessions(store_id=store, employee_id=employee, limit=1)
        capability_levels = repo.training_capability_levels(store_id=store, employee_id=employee, limit=1)
        return build_recommended_training_plan(
            capability_levels,
            employee_id=employee,
            store_id=store,
            recent_sessions=recent_sessions,
        )

    @app.post("/api/operating-brain/workbench-submit", dependencies=[Depends(require_api_token)])
    async def operating_brain_workbench_submit(
        input: str = Form(default=""),
        scenario: str = Form(default="经营问答"),
        role: str = Form(default="team"),
        files: list[UploadFile] = File(default=[]),
    ) -> dict[str, Any]:
        input_text = input.strip()
        if not input_text and not files:
            raise HTTPException(status_code=400, detail="input or files are required")
        uploaded_files: list[dict[str, Any]] = []
        for file in files:
            uploaded_files.append(
                await _validated_upload_file(
                    file,
                    inbox_dir=inbox_dir,
                    root_dir=resolved_root,
                    max_bytes=settings.max_upload_bytes,
                    allowed_extensions=allowed_upload_extensions,
                )
            )
        intake = _classify_workbench_intake_with_model(
            model_router=model_router,
            input_text=input_text,
            scenario=scenario.strip() or "经营问答",
            role=role.strip() or "team",
            attachments=uploaded_files,
        )
        memory_result = build_instant_memory_records(resolved_root, uploaded_files)
        image_understandings, image_chunks, image_tasks = _understand_uploaded_images(
            root_dir=resolved_root,
            uploaded_files=uploaded_files,
            memory_assets=memory_result["assets"],
            model_router=model_router,
            input_text=input_text,
            scenario=scenario.strip() or "经营问答",
        )
        if image_chunks:
            memory_result["chunks"].extend(image_chunks)
            memory_result["chunk_count"] = len(memory_result["chunks"])
            memory_result["status"] = "indexed"
        memory_result["image_understanding_count"] = len(image_understandings)
        memory_result["image_understanding_task_count"] = len(image_tasks)
        if memory_result["asset_count"]:
            repo = make_repository()
            repo.upsert_run(
                memory_result["run_name"],
                "knowledge/raw/inbox",
                "workbench-instant",
                memory_result["asset_count"],
                memory_result["chunk_count"],
                status="completed",
            )
            repo.upsert_assets(memory_result["assets"])
            repo.upsert_chunks(memory_result["chunks"])
            if image_understandings and hasattr(repo, "upsert_image_understandings"):
                repo.upsert_image_understandings(image_understandings)
            for task in image_tasks:
                repo.create_review_task(
                    {
                        "answer_id": None,
                        "question": f"图片资料需要多模态理解：{task.get('file_name') or task.get('relative_path')}",
                        "intent": "knowledge_intake",
                        "reason": "image_understanding_needed",
                        "priority": "medium",
                        "note": input_text,
                        "correction_package": {
                            "version": "hxy-image-understanding-task.v1",
                            "failure_type": "image_understanding_gap",
                            "target": "完成图片 OCR/多模态理解并沉淀为可检索业务知识",
                            "file": task,
                            "recommended_reviewer": "运营负责人",
                            "recommended_actions": [
                                "确认图片所属业务域",
                                "补充图片中的文字、价格、项目和业务含义",
                                "通过后重新入库为图片理解记录",
                            ],
                        },
                    }
                )
        next_message = (
            f"已进入组织记忆：{memory_result['asset_count']} 份资料，"
            f"{memory_result['chunk_count']} 个可检索片段。"
            if memory_result["chunk_count"]
            else "资料已上传并进入复核；图片和复杂文件需要后续多模态理解后才能稳定问答。"
        )
        if image_understandings:
            next_message = (
                f"已完成图片多模态理解并进入组织记忆：{len(image_understandings)} 张图片，"
                f"{memory_result['chunk_count']} 个可检索片段。"
            )
        elif image_tasks:
            next_message = "图片已上传，正在等待多模态理解或人工复核；完成前不能作为稳定问答依据。"
        return {
            "intake": intake,
            "uploaded_files": uploaded_files,
            "memory_result": {
                key: value
                for key, value in memory_result.items()
                if key not in {"assets", "chunks"}
            },
            "image_understandings": image_understandings,
            "image_understanding_tasks": image_tasks,
            "next_message": next_message,
            "status": "submitted",
        }

    @app.post("/api/knowledge/chat", dependencies=[Depends(require_api_token)])
    async def knowledge_chat(request: ChatRequest) -> dict[str, Any]:
        if not settings.api_token:
            raise HTTPException(status_code=503, detail="Knowledge chat authentication is not configured")
        question = request.question.strip()
        scenario = request.scenario.strip() or "创始人内部决策"
        if not question:
            raise HTTPException(status_code=400, detail="question is required")
        return answer_service.generate_answer(
            question=question,
            scenario=scenario,
            domain=request.domain,
            stage=request.stage,
            limit=request.limit,
            repository=make_repository(),
            model_router=model_router,
            hooks=answer_hooks,
            role="founder",
            pipeline_role="team",
            brand_constitution=brand_constitution,
            source_asset_id=request.source_asset_id,
        )

    @app.post("/api/knowledge/feedback", dependencies=[Depends(require_api_token)])
    async def knowledge_feedback(request: FeedbackRequest) -> dict[str, Any]:
        if request.rating not in {"useful", "incorrect", "needs_work"}:
            raise HTTPException(status_code=400, detail="rating must be useful, incorrect, or needs_work")
        repo = make_repository()
        payload = {
            "answer_id": request.answer_id,
            "question": request.question.strip(),
            "rating": request.rating,
            "note": request.note.strip(),
        }
        feedback_id = repo.save_feedback(payload)
        review_task_id = None
        correction_package = None
        if request.rating in {"incorrect", "needs_work"}:
            correction_package = build_correction_package(
                request.question.strip(),
                request.rating,
                request.note.strip(),
            )
            correction_package["answer_card_draft"]["source_answer_id"] = request.answer_id
            review_task_id = repo.create_review_task(
                {
                    "answer_id": request.answer_id,
                    "feedback_id": feedback_id,
                    "question": request.question.strip(),
                    "intent": "unknown",
                    "reason": request.rating,
                    "priority": "high" if request.rating == "incorrect" else "medium",
                    "note": request.note.strip(),
                    "correction_package": correction_package,
                }
            )
        return {
            "feedback_id": feedback_id,
            "review_task_id": review_task_id,
            "correction_package": correction_package,
            "status": "recorded",
        }

    @app.get("/api/knowledge/review-tasks")
    async def knowledge_review_tasks(status: str = "open", limit: int = Query(default=50, ge=1, le=200)) -> dict[str, Any]:
        items = dedupe_review_tasks(make_repository().review_tasks(status=status, limit=200))
        return {"items": items[:limit], "count": len(items[:limit])}

    @app.post("/api/knowledge/review-tasks/{task_id}/resolve", dependencies=[Depends(require_api_token)])
    async def resolve_review_task(task_id: str) -> dict[str, Any]:
        resolved = make_repository().resolve_review_task(task_id, status="resolved")
        if not resolved:
            raise HTTPException(status_code=404, detail="review task not found")
        return {"task_id": task_id, "status": "resolved"}

    @app.get("/api/knowledge/answer-cards")
    async def list_answer_cards(status: str | None = "approved", limit: int = Query(default=100, ge=1, le=500)) -> dict[str, Any]:
        repo_items = [
            _public_answer_card(card, source="repository")
            for card in _list_repository_answer_cards(make_repository(), status=status, limit=limit)
        ]
        builtin_items = [
            _public_answer_card(card, source="builtin")
            for card in [*authority_cards(), *brand_authority_cards()]
            if status is None or card.get("status") == status
        ]
        seen_patterns = {
            _normalize_question_pattern(str(item.get("question_pattern") or ""))
            for item in repo_items
        }
        items = [
            *repo_items,
            *[
                item
                for item in builtin_items
                if _normalize_question_pattern(str(item.get("question_pattern") or "")) not in seen_patterns
            ],
        ]
        return {"items": items[:limit], "count": len(items[:limit])}

    @app.post("/api/knowledge/answer-cards", dependencies=[Depends(require_api_token)])
    async def create_answer_card(request: AnswerCardRequest) -> dict[str, Any]:
        if request.status not in {"draft", "approved", "archived"}:
            raise HTTPException(status_code=400, detail="status must be draft, approved, or archived")
        if not request.question_pattern.strip():
            raise HTTPException(status_code=400, detail="question_pattern is required")
        if not request.answer.strip():
            raise HTTPException(status_code=400, detail="answer is required")
        preflight = _compliance_preflight_for_text(
            request.answer,
            workflow_type=_workflow_type_for_answer_card(request),
            channel="answer_card",
            audience=request.audience,
            root_dir=resolved_root,
        )
        if request.status == "approved" and not bool(preflight.get("can_continue")):
            raise HTTPException(
                status_code=400,
                detail={
                    "message": "approved answer card failed compliance preflight",
                    "compliance_preflight": preflight,
                },
            )
        payload = request.model_dump()
        payload["question_pattern"] = request.question_pattern.strip()
        payload["answer"] = request.answer.strip()
        payload["compliance_preflight"] = preflight
        card_id = make_repository().create_answer_card(payload)
        return {"card_id": card_id, "status": "created", "compliance_preflight": preflight}

    @app.post("/api/knowledge/upload", dependencies=[Depends(require_api_token)])
    async def upload_knowledge_file(file: UploadFile = File(...)) -> dict[str, Any]:
        return await _validated_upload_file(
            file,
            inbox_dir=inbox_dir,
            root_dir=resolved_root,
            max_bytes=settings.max_upload_bytes,
            allowed_extensions=allowed_upload_extensions,
        )

    @app.post("/api/knowledge/import", dependencies=[Depends(require_api_token)])
    async def import_knowledge() -> dict[str, Any]:
        run_name = settings.run_name
        repo = make_repository()
        manifest, assets, chunks = load_current_records(resolved_root, run_name)
        manifest_path = f"knowledge/structured/hxy-inbox-manifest-{run_name}.json"
        index_path = f"knowledge/structured/hxy-inbox-search-index-{run_name}.json"
        repo.clear_run(run_name)
        repo.upsert_run(run_name, manifest_path, index_path, len(assets), len(chunks), status="completed")
        repo.upsert_assets(assets)
        repo.upsert_chunks(chunks)
        return {
            "run_name": manifest.get("run_name") or run_name,
            "assets": len(assets),
            "chunks": len(chunks),
            "status": "imported",
        }

    return app


app = create_app()
