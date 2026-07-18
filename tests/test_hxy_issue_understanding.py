from __future__ import annotations

import importlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "data" / "migrations" / "021_hxy_operating_loop.sql"
ORGANIZATION_ID = "10000000-0000-0000-0000-000000000001"
ENVELOPE_ID = "70000000-0000-0000-0000-000000000001"
ASSIGNMENT_ID = "20000000-0000-0000-0000-000000000001"
OWNER_ID = "20000000-0000-0000-0000-000000000002"
RELATIONSHIP_ID = "30000000-0000-0000-0000-000000000001"
PROFILE_ID = "40000000-0000-0000-0000-000000000001"
ASSET_ID = "50000000-0000-0000-0000-000000000001"
OUTBOX_MESSAGE_ID = "60000000-0000-0000-0000-000000000001"


def _outbox_payload(*, attempt_number: int = 1, max_attempts: int = 5) -> dict[str, Any]:
    return {
        "organization_id": ORGANIZATION_ID,
        "envelope_id": ENVELOPE_ID,
        "store_id": "HXY-STORE-001",
        "source_asset_ids": [],
        "store_operating_relationship_id": RELATIONSHIP_ID,
        "store_operating_relationship_version": 1,
        "governance_profile_id": PROFILE_ID,
        "governance_profile_version": 1,
        "_hxy_outbox": {
            "outbox_message_id": OUTBOX_MESSAGE_ID,
            "organization_id": ORGANIZATION_ID,
            "aggregate_type": "inbound_envelope",
            "aggregate_id": ENVELOPE_ID,
            "attempt_number": attempt_number,
            "max_attempts": max_attempts,
            "worker_id": "worker-a",
        },
    }


def _context(*, attachments: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "organization_id": ORGANIZATION_ID,
        "envelope_id": ENVELOPE_ID,
        "store_id": "HXY-STORE-001",
        "sender_assignment_id": ASSIGNMENT_ID,
        "assignment_is_active": True,
        "raw_text": "前台左侧灯带持续闪烁，影响现场观感。",
        "attachments": attachments or [],
        "published_event_types": [
            "facility_defect",
            "service_exception",
            "customer_complaint",
            "safety",
        ],
        "formal_knowledge_corpus": "THIS_FORMAL_CORPUS_MUST_NOT_ENTER_THE_PROMPT",
    }


class FakeChannelRepository:
    def __init__(
        self,
        context: dict[str, Any] | None = None,
        *,
        active_owner_ids: set[str] | None = None,
    ):
        self.context = context or _context()
        self.active_owner_ids = (
            {OWNER_ID} if active_owner_ids is None else active_owner_ids
        )
        self.processed: list[tuple[str, str]] = []
        self.processed_fences: list[dict[str, Any]] = []
        self.needs_attention: list[tuple[str, str, str]] = []

    def load_issue_context(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        assert payload["organization_id"] == ORGANIZATION_ID
        assert payload["envelope_id"] == ENVELOPE_ID
        return deepcopy(self.context)

    def mark_envelope_processed(
        self,
        organization_id: str,
        envelope_id: str,
        *,
        execution_fence: dict[str, Any],
    ) -> None:
        self.processed.append((organization_id, envelope_id))
        self.processed_fences.append(deepcopy(execution_fence))

    def issue_owner_is_active(
        self,
        organization_id: str,
        store_id: str,
        assignment_id: str,
    ) -> bool:
        assert organization_id == ORGANIZATION_ID
        assert store_id == "HXY-STORE-001"
        return assignment_id in self.active_owner_ids

    def mark_envelope_needs_attention(
        self,
        organization_id: str,
        envelope_id: str,
        *,
        reason: str,
    ) -> None:
        self.needs_attention.append((organization_id, envelope_id, reason))


class FakeOperatingRepository:
    def __init__(self):
        self.records: list[dict[str, Any]] = []
        self.fences: list[dict[str, Any]] = []

    def save_issue_proposal(
        self,
        record: dict[str, Any],
        *,
        execution_fence: dict[str, Any],
    ) -> dict[str, Any]:
        saved = deepcopy(record)
        saved["proposal_id"] = "80000000-0000-0000-0000-000000000001"
        self.records.append(saved)
        self.fences.append(deepcopy(execution_fence))
        return saved


class FakeModelRouter:
    def __init__(self, output: str | None, *, used_model: bool = True):
        self.output = output
        self.used_model = used_model
        self.calls: list[dict[str, Any]] = []

    def generate(self, task_type: str, **kwargs: Any) -> dict[str, Any]:
        self.calls.append({"task_type": task_type, **deepcopy(kwargs)})
        return {
            "used_model": self.used_model,
            "reason": "ok" if self.used_model else "disabled",
            "output": self.output,
            "route": {
                "provider": "aliyun",
                "selected_model": "qwen3.5-plus",
            },
        }


def _build_handler(
    output: str | None,
    *,
    context: dict[str, Any] | None = None,
    used_model: bool = True,
    attachment_adapter=None,
    active_owner_ids: set[str] | None = None,
):
    module = importlib.import_module("apps.api.hxy_product.issue_understanding")
    channel = FakeChannelRepository(context, active_owner_ids=active_owner_ids)
    operating = FakeOperatingRepository()
    router = FakeModelRouter(output, used_model=used_model)
    handler = module.build_issue_understanding_handler(
        channel,
        operating,
        router,
        module.evaluate_issue_proposal,
        attachment_adapter=attachment_adapter,
    )
    return module, handler, channel, operating, router


def test_invalid_model_json_is_retryable_and_does_not_mutate_the_envelope() -> None:
    module, handler, channel, operating, _router = _build_handler("{not-json")

    with pytest.raises(module.OutboxHandlerError) as raised:
        handler(_outbox_payload())

    assert raised.value.code == "invalid_model_json"
    assert raised.value.retryable is True
    assert operating.records == []
    assert channel.processed == []
    assert channel.needs_attention == []


def test_handler_rejects_payload_scope_that_disagrees_with_the_outbox_row() -> None:
    module, handler, channel, operating, _router = _build_handler("{}")
    payload = _outbox_payload()
    payload["organization_id"] = "10000000-0000-0000-0000-000000000099"

    with pytest.raises(module.OutboxHandlerError) as raised:
        handler(payload)

    assert raised.value.code == "outbox_scope_mismatch"
    assert raised.value.retryable is False
    assert operating.records == []
    assert channel.processed == []


def test_handler_checks_the_worker_lease_before_persisting_side_effects() -> None:
    repository_module = importlib.import_module("apps.api.hxy_product.outbox_repository")
    output = json.dumps(
        {
            "event_type": "facility_defect",
            "title": "前台灯带闪烁",
            "description": "灯带通电后持续闪烁。",
            "location": "前台左侧",
            "impact": "影响现场观感",
            "acceptance_criteria": "连续运行30分钟无闪烁",
            "suggested_owner_assignment_id": OWNER_ID,
            "risk_flags": [],
            "confidence": 0.99,
        },
        ensure_ascii=False,
    )
    _module, handler, channel, operating, _router = _build_handler(output)
    payload = _outbox_payload()

    def reject_lost_lease() -> None:
        raise repository_module.OutboxLeaseLost("lease was reclaimed")

    payload["_hxy_outbox"]["assert_lease"] = reject_lost_lease

    with pytest.raises(repository_module.OutboxLeaseLost):
        handler(payload)

    assert operating.records == []
    assert channel.processed == []


def test_valid_incomplete_output_is_stored_without_fabricating_missing_facts() -> None:
    output = json.dumps(
        {
            "event_type": "facility_defect",
            "title": "前台灯带闪烁",
            "description": "前台左侧灯带持续闪烁。",
            "risk_flags": [],
            "confidence": 0.91,
        },
        ensure_ascii=False,
    )
    _module, handler, channel, operating, _router = _build_handler(output)

    result = handler(_outbox_payload())

    assert result["decision"] == "request_missing"
    assert channel.processed == [(ORGANIZATION_ID, ENVELOPE_ID)]
    record = operating.records[0]
    assert record["payload"]["location"] == ""
    assert record["payload"]["acceptance_criteria"] == ""
    assert record["payload"]["suggested_owner_assignment_id"] is None
    assert record["decision"]["missing_fields"] == [
        "location",
        "acceptance_criteria",
        "owner_assignment_id",
    ]
    assert record["status"] == "proposed"
    assert operating.fences[0]["outbox_message_id"] == OUTBOX_MESSAGE_ID
    assert operating.fences[0]["attempt_number"] == 1
    assert channel.processed_fences[0] == operating.fences[0]


def test_model_cannot_inject_tenant_actor_status_or_metric_fields() -> None:
    output = json.dumps(
        {
            "event_type": "facility_defect",
            "title": "前台灯带闪烁",
            "description": "灯带通电后持续闪烁。",
            "location": "前台左侧",
            "impact": "影响现场观感",
            "acceptance_criteria": "连续运行30分钟无闪烁",
            "suggested_owner_assignment_id": OWNER_ID,
            "suggested_due_at": None,
            "risk_flags": [],
            "confidence": 0.92,
            "organization_id": "attacker-organization",
            "store_id": "attacker-store",
            "actor_type": "ai",
            "status": "closed",
            "metric_values": {"closed_seconds": 0},
        },
        ensure_ascii=False,
    )
    _module, handler, channel, operating, router = _build_handler(output)

    result = handler(_outbox_payload())

    assert result["decision"] == "auto_accept"
    assert channel.processed == [(ORGANIZATION_ID, ENVELOPE_ID)]
    record = operating.records[0]
    assert record["organization_id"] == ORGANIZATION_ID
    assert record["status"] == "auto_accepted"
    assert set(record["payload"]) == {
        "event_type",
        "title",
        "description",
        "location",
        "impact",
        "acceptance_criteria",
        "suggested_owner_assignment_id",
        "suggested_due_at",
        "risk_flags",
        "confidence",
    }
    assert "actor_type" not in record["payload"]
    assert "metric_values" not in record["payload"]
    assert router.calls[0]["task_type"] == "issue_understanding"


def test_unscoped_or_inactive_suggested_owner_cannot_auto_accept() -> None:
    output = json.dumps(
        {
            "event_type": "facility_defect",
            "title": "前台灯带闪烁",
            "description": "灯带通电后持续闪烁。",
            "location": "前台左侧",
            "impact": "影响现场观感",
            "acceptance_criteria": "连续运行30分钟无闪烁",
            "suggested_owner_assignment_id": OWNER_ID,
            "risk_flags": [],
            "confidence": 0.99,
        },
        ensure_ascii=False,
    )
    _module, handler, _channel, operating, _router = _build_handler(
        output,
        active_owner_ids=set(),
    )

    result = handler(_outbox_payload())

    assert result["decision"] == "require_confirmation"
    assert operating.records[0]["status"] == "proposed"


def test_deterministic_risk_scan_escalates_injury_even_when_model_omits_it() -> None:
    output = json.dumps(
        {
            "event_type": "facility_defect",
            "title": "施工区地面问题",
            "description": "需要处理地面。",
            "location": "施工区",
            "impact": "影响施工",
            "acceptance_criteria": "完成整改",
            "suggested_owner_assignment_id": OWNER_ID,
            "risk_flags": [],
            "confidence": 0.99,
        },
        ensure_ascii=False,
    )
    context = _context()
    context["raw_text"] = "施工区有人摔倒受伤，手臂正在流血。"
    _module, handler, channel, operating, _router = _build_handler(
        output,
        context=context,
    )

    result = handler(_outbox_payload())

    assert result["decision"] == "escalate"
    assert channel.processed == [(ORGANIZATION_ID, ENVELOPE_ID)]
    record = operating.records[0]
    assert record["risk_level"] == "critical"
    assert "person_injury" in record["decision"]["deterministic_risk_flags"]
    assert record["payload"]["risk_flags"] == []


def test_attachment_failure_defers_terminal_attention_to_the_outbox_transaction() -> None:
    module = importlib.import_module("apps.api.hxy_product.issue_understanding")

    def failing_adapter(_attachment: dict[str, Any], *, model_router: Any):
        raise module.AttachmentUnderstandingError(
            "vision_unavailable",
            "vision adapter is unavailable",
            retryable=True,
        )

    context = _context(
        attachments=[
            {
                "source_asset_id": ASSET_ID,
                "file_name": "现场照片.jpg",
                "media_type": "image/jpeg",
                "storage_key": f"{ASSIGNMENT_ID}/{ASSET_ID}/现场照片.jpg",
            }
        ]
    )
    module, handler, channel, operating, _router = _build_handler(
        "{}",
        context=context,
        attachment_adapter=failing_adapter,
    )

    with pytest.raises(module.OutboxHandlerError) as first:
        handler(_outbox_payload(attempt_number=1, max_attempts=3))
    assert first.value.retryable is True
    assert channel.needs_attention == []

    with pytest.raises(module.OutboxHandlerError) as final:
        handler(_outbox_payload(attempt_number=3, max_attempts=3))
    assert final.value.code == "vision_unavailable"
    assert channel.needs_attention == []
    assert operating.records == []
    assert channel.context["raw_text"] == "前台左侧灯带持续闪烁，影响现场观感。"


def test_default_attachment_adapter_wraps_io_errors_as_retryable() -> None:
    module = importlib.import_module("apps.api.hxy_product.issue_understanding")

    def failing_read(_path: Path) -> str:
        raise OSError("temporary storage failure")

    original = module._read_bounded_text
    module._read_bounded_text = failing_read
    try:
        with pytest.raises(module.AttachmentUnderstandingError) as raised:
            module.default_attachment_adapter(
                {
                    "source_asset_id": ASSET_ID,
                    "file_name": "现场说明.md",
                    "extension": ".md",
                    "media_type": "text/markdown",
                    "normalized_storage_key": f"{ASSIGNMENT_ID}/{ASSET_ID}/normalized.md",
                },
                model_router=FakeModelRouter("{}"),
            )
    finally:
        module._read_bounded_text = original

    assert raised.value.code == "attachment_io_error"
    assert raised.value.retryable is True


def test_default_attachment_adapter_transcribes_audio_through_model_router(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = importlib.import_module("apps.api.hxy_product.issue_understanding")
    material_root = tmp_path / "data" / "product-materials"
    audio = material_root / ASSIGNMENT_ID / ASSET_ID / "现场语音.wav"
    audio.parent.mkdir(parents=True)
    audio.write_bytes(b"RIFF-audio-review")
    monkeypatch.setenv("HXY_ROOT_DIR", str(tmp_path))

    class SpeechRouter:
        def __init__(self):
            self.calls: list[dict[str, Any]] = []

        def generate(self, task_type: str, **kwargs: Any) -> dict[str, Any]:
            self.calls.append({"task_type": task_type, **deepcopy(kwargs)})
            return {
                "used_model": True,
                "output": "前台左侧灯带一直闪烁。",
                "route": {"provider": "aliyun", "selected_model": "qwen-audio"},
            }

    router = SpeechRouter()

    result = module.default_attachment_adapter(
        {
            "source_asset_id": ASSET_ID,
            "file_name": "现场语音.wav",
            "extension": ".wav",
            "media_type": "audio/wav",
            "storage_key": f"{ASSIGNMENT_ID}/{ASSET_ID}/现场语音.wav",
        },
        model_router=router,
    )

    assert result["text"] == "前台左侧灯带一直闪烁。"
    assert result["adapter"] == "speech_model"
    assert router.calls[0]["task_type"] == "speech"
    audio_content = router.calls[0]["messages"][0]["content"][1]
    assert audio_content["type"] == "input_audio"
    assert audio_content["input_audio"]["format"] == "wav"
    assert audio_content["input_audio"]["data"]


def test_prompt_contains_governed_taxonomy_and_risk_vocabulary_not_formal_corpus() -> None:
    output = json.dumps(
        {
            "event_type": "facility_defect",
            "title": "灯带闪烁",
            "description": "现场灯带闪烁。",
            "location": "前台",
            "impact": "影响观感",
            "acceptance_criteria": "连续运行30分钟无闪烁",
            "suggested_owner_assignment_id": OWNER_ID,
            "risk_flags": [],
            "confidence": 0.9,
        },
        ensure_ascii=False,
    )
    _module, handler, _channel, _operating, router = _build_handler(output)

    handler(_outbox_payload())

    prompt = router.calls[0]["prompt"]
    assert "facility_defect" in prompt
    assert "customer_complaint" in prompt
    assert "person_injury" in prompt
    assert "medical_claim" in prompt
    assert "THIS_FORMAL_CORPUS_MUST_NOT_ENTER_THE_PROMPT" not in prompt


def test_model_unavailable_is_retryable() -> None:
    module, handler, channel, operating, _router = _build_handler(
        None,
        used_model=False,
    )

    with pytest.raises(module.OutboxHandlerError) as raised:
        handler(_outbox_payload())

    assert raised.value.code == "model_unavailable"
    assert raised.value.retryable is True
    assert operating.records == []
    assert channel.processed == []


def test_channel_repository_loads_tenant_scoped_context_and_authorized_assets() -> None:
    module = importlib.import_module("apps.api.hxy_product.channel_repository")
    repository = module.ChannelRepository("postgresql://channel.test/hxy")
    calls: list[tuple[str, tuple[Any, ...]]] = []

    context_row = {
        "envelope_id": ENVELOPE_ID,
        "organization_id": ORGANIZATION_ID,
        "store_id": "HXY-STORE-001",
        "sender_assignment_id": ASSIGNMENT_ID,
        "assignment_status": "active",
        "raw_text": "前台灯闪烁",
        "raw_payload": {"event": "message"},
        "decision_rights": {
            "issue_event_types": ["facility_defect", "customer_complaint"]
        },
    }
    asset_row = {
        "source_asset_id": ASSET_ID,
        "file_name": "现场照片.jpg",
        "extension": ".jpg",
        "media_type": "image/jpeg",
        "storage_key": f"{ASSIGNMENT_ID}/{ASSET_ID}/现场照片.jpg",
        "material_status": "ready",
        "normalized_storage_key": f"{ASSIGNMENT_ID}/{ASSET_ID}/derived/job/normalized.md",
    }

    class Result:
        def __init__(self, row=None, rows=None):
            self.row = row
            self.rows = rows or []

        def fetchone(self):
            return self.row

        def fetchall(self):
            return self.rows

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, sql: str, params: tuple[Any, ...]):
            normalized = " ".join(sql.split())
            calls.append((normalized, params))
            if "FROM hxy_inbound_envelopes AS envelope" in normalized:
                return Result(row=context_row)
            if "FROM hxy_asset_bindings AS binding" in normalized:
                return Result(rows=[asset_row])
            raise AssertionError(normalized)

    repository.connect = lambda: Connection()

    context = repository.load_issue_context(_outbox_payload())

    assert context is not None
    assert context["organization_id"] == ORGANIZATION_ID
    assert context["assignment_is_active"] is True
    assert context["published_event_types"] == [
        "facility_defect",
        "customer_complaint",
    ]
    assert context["attachments"] == [asset_row]
    assert all(ORGANIZATION_ID in params for _sql, params in calls)
    context_sql = next(
        sql for sql, _params in calls if "FROM hxy_inbound_envelopes AS envelope" in sql
    )
    assert "governance.profile_version = %s" in context_sql
    assert "relationship.status = 'active'" not in context_sql
    assert "governance.status = 'published'" not in context_sql


def test_channel_repository_validates_issue_owner_in_tenant_and_store_scope() -> None:
    module = importlib.import_module("apps.api.hxy_product.channel_repository")
    repository = module.ChannelRepository("postgresql://channel.test/hxy")
    calls: list[tuple[str, tuple[Any, ...]]] = []

    class Result:
        def fetchone(self):
            return {"is_active": True}

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, sql: str, params: tuple[Any, ...]):
            calls.append((" ".join(sql.split()), params))
            return Result()

    repository.connect = lambda: Connection()

    active = repository.issue_owner_is_active(
        ORGANIZATION_ID,
        "HXY-STORE-001",
        OWNER_ID,
    )

    assert active is True
    sql, params = calls[0]
    assert "organization_id = %s::uuid" in sql
    assert "assignment_id = %s::uuid" in sql
    assert "status = 'active'" in sql
    assert "store_id = %s" in sql
    assert "role IN ('founder', 'hq_operations', 'system_admin')" in sql
    assert params == (ORGANIZATION_ID, OWNER_ID, "HXY-STORE-001")


def test_channel_repository_fences_envelope_completion_in_the_same_transaction() -> None:
    module = importlib.import_module("apps.api.hxy_product.channel_repository")
    repository = module.ChannelRepository("postgresql://channel.test/hxy")
    calls: list[tuple[str, tuple[Any, ...]]] = []

    class Result:
        def __init__(self, row: dict[str, Any]):
            self.row = row

        def fetchone(self):
            return self.row

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, sql: str, params: tuple[Any, ...]):
            normalized = " ".join(sql.split())
            calls.append((normalized, params))
            if "FROM hxy_outbox_messages" in normalized:
                return Result({"status": "leased"})
            if "UPDATE hxy_inbound_envelopes" in normalized:
                return Result({"envelope_id": ENVELOPE_ID})
            raise AssertionError(normalized)

    repository.connect = lambda: Connection()
    fence = {
        "organization_id": ORGANIZATION_ID,
        "outbox_message_id": OUTBOX_MESSAGE_ID,
        "worker_id": "worker-a",
        "attempt_number": 1,
    }

    repository.mark_envelope_processed(
        ORGANIZATION_ID,
        ENVELOPE_ID,
        execution_fence=fence,
    )

    assert "FOR UPDATE" in calls[0][0]
    assert "attempt_count = %s" in calls[0][0]
    assert "UPDATE hxy_inbound_envelopes" in calls[1][0]


def test_issue_proposal_retry_is_idempotent_by_input_hash() -> None:
    sql = " ".join(MIGRATION.read_text(encoding="utf-8").split())
    assert "CREATE UNIQUE INDEX IF NOT EXISTS uq_hxy_ai_proposals_input" in sql
    assert "(organization_id, source_envelope_id, proposal_type, input_hash)" in sql


def test_proposal_repository_returns_existing_retry_and_sets_policy_decision_fields() -> None:
    module = importlib.import_module("apps.api.hxy_product.issue_understanding")
    repository = module.IssueProposalRepository("postgresql://proposal.test/hxy")
    calls: list[tuple[str, tuple[Any, ...]]] = []
    existing = {
        "proposal_id": "80000000-0000-0000-0000-000000000001",
        "organization_id": ORGANIZATION_ID,
        "source_envelope_id": ENVELOPE_ID,
        "status": "auto_accepted",
        "created_at": "2026-07-18T08:00:00Z",
    }

    class Result:
        def __init__(self, row=None):
            self.row = row

        def fetchone(self):
            return self.row

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, sql: str, params: tuple[Any, ...]):
            normalized = " ".join(sql.split())
            calls.append((normalized, params))
            if "FROM hxy_outbox_messages" in normalized:
                return Result({"status": "leased"})
            if "INSERT INTO hxy_ai_proposals" in normalized:
                return Result(None)
            if "FROM hxy_ai_proposals" in normalized:
                return Result(existing)
            raise AssertionError(normalized)

    repository.connect = lambda: Connection()
    record = {
        "organization_id": ORGANIZATION_ID,
        "source_envelope_id": ENVELOPE_ID,
        "proposal_type": "issue_understanding",
        "payload": {
            "event_type": "facility_defect",
            "confidence": 0.92,
        },
        "confidence": 0.92,
        "risk_level": "low",
        "model_provider": "aliyun",
        "model_name": "qwen3.5-plus",
        "prompt_version": "issue-understanding.v1",
        "input_hash": "a" * 64,
        "status": "auto_accepted",
        "decision": {
            "action": "auto_accept",
            "severity": "low",
            "missing_fields": [],
            "policy_version": "issue-intake.v1",
            "deterministic_risk_flags": [],
        },
    }

    saved = repository.save_issue_proposal(
        record,
        execution_fence={
            "organization_id": ORGANIZATION_ID,
            "outbox_message_id": OUTBOX_MESSAGE_ID,
            "worker_id": "worker-a",
            "attempt_number": 1,
        },
    )

    assert saved["proposal_id"] == existing["proposal_id"]
    insert_sql, insert_params = next(
        (sql, params) for sql, params in calls if "INSERT INTO hxy_ai_proposals" in sql
    )
    assert "ON CONFLICT (organization_id, source_envelope_id, proposal_type, input_hash)" in insert_sql
    assert "decision_policy_version" in insert_sql
    assert "NOW()" in insert_sql
    assert "issue-intake.v1" in insert_params
    assert not any("UPDATE hxy_ai_proposals" in sql for sql, _params in calls)
    assert "FOR UPDATE" in calls[0][0]


def test_handler_returns_the_persisted_decision_on_idempotent_retry() -> None:
    output = json.dumps(
        {
            "event_type": "facility_defect",
            "title": "灯带闪烁",
            "description": "现场灯带闪烁。",
            "location": "前台",
            "impact": "影响观感",
            "acceptance_criteria": "连续运行30分钟无闪烁",
            "suggested_owner_assignment_id": OWNER_ID,
            "risk_flags": [],
            "confidence": 0.99,
        },
        ensure_ascii=False,
    )
    module = importlib.import_module("apps.api.hxy_product.issue_understanding")
    channel = FakeChannelRepository()
    router = FakeModelRouter(output)

    class ExistingProposalRepository:
        def save_issue_proposal(
            self,
            _record: dict[str, Any],
            *,
            execution_fence: dict[str, Any],
        ) -> dict[str, Any]:
            assert execution_fence["outbox_message_id"] == OUTBOX_MESSAGE_ID
            return {
                "proposal_id": "80000000-0000-0000-0000-000000000099",
                "status": "proposed",
                "decision_action": "require_confirmation",
            }

    handler = module.build_issue_understanding_handler(
        channel,
        ExistingProposalRepository(),
        router,
        module.evaluate_issue_proposal,
    )

    result = handler(_outbox_payload())

    assert result["decision"] == "require_confirmation"


def test_model_router_exposes_a_dedicated_issue_understanding_route(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text(
        '\n'.join(
            [
                'model_provider = "aliyun"',
                'model = "qwen3.5-plus"',
                '',
                '[model_providers.aliyun]',
                'base_url = "https://example.invalid/v1"',
                'wire_api = "chat_completions"',
            ]
        ),
        encoding="utf-8",
    )
    module = importlib.import_module("apps.api.hxy_knowledge.model_router")

    route = module.ModelRouter(config).route("issue_understanding")

    assert route["task_type"] == "issue_understanding"
    assert route["selected_model"] == "qwen3.5-plus"
    assert "经营问题" in route["purpose"]
