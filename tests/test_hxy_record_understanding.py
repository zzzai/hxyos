from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable

import pytest
from pydantic import ValidationError

from apps.api.hxy_product.outbox_worker import OutboxHandlerError
from apps.api.hxy_product.record_understanding import (
    OrganizationRecordUnderstandingDraft,
    OrganizationRecordProposalRepository,
    build_record_understanding_handler,
)


RECORD_ID = "22222222-2222-4222-8222-222222222222"
ORGANIZATION_ID = "11111111-1111-4111-8111-111111111111"
ASSET_ID = "33333333-3333-4333-8333-333333333333"
OUTBOX_MESSAGE_ID = "44444444-4444-4444-8444-444444444444"


def _valid_payload() -> dict[str, Any]:
    evidence = {
        "source_record_id": RECORD_ID,
        "quote": "施工方尚未收到最终水电图",
        "locator": "原始文字",
    }
    return {
        "summary": "水电图仍待最终确认。",
        "record_type": "progress_update",
        "occurred_at": None,
        "facts": [{"statement": "施工方缺少最终水电图。", "evidence": [evidence]}],
        "decisions": [],
        "progress": [{"statement": "水电图尚未最终交付。", "evidence": [evidence]}],
        "risks": [
            {
                "statement": "水电施工可能因此延后。",
                "severity": "medium",
                "evidence": [evidence],
            }
        ],
        "missing_information": ["最终水电图的确认时间"],
        "confidence": 0.86,
    }


def test_strict_schema_accepts_the_documented_contract() -> None:
    draft = OrganizationRecordUnderstandingDraft.model_validate(_valid_payload())

    assert draft.record_type == "progress_update"
    assert draft.risks[0].severity == "medium"
    assert draft.facts[0].evidence[0].quote == "施工方尚未收到最终水电图"


@pytest.mark.parametrize(
    "mutation",
    [
        lambda payload: payload.update({"official_knowledge": True}),
        lambda payload: payload.update({"unexpected": "field"}),
        lambda payload: payload["facts"][0]["evidence"][0].update(
            {"quote": "证" * 1001}
        ),
        lambda payload: payload["facts"][0].update(
            {
                "evidence": [
                    {"source_record_id": RECORD_ID, "quote": f"证据{i}"}
                    for i in range(6)
                ]
            }
        ),
        lambda payload: payload["risks"][0].update({"severity": "urgent"}),
        lambda payload: payload.update({"confidence": -0.01}),
        lambda payload: payload.update({"confidence": 1.01}),
        lambda payload: payload.update({"confidence": "0.86"}),
        lambda payload: payload.update({"confidence": True}),
        lambda payload: payload.update({"occurred_at": 1_753_000_000}),
        lambda payload: payload.update({"facts": payload["facts"] * 6}),
        lambda payload: payload.update(
            {"missing_information": [f"缺失{i}" for i in range(6)]}
        ),
    ],
)
def test_strict_schema_rejects_extra_invalid_or_unbounded_values(
    mutation: Callable[[dict[str, Any]], None],
) -> None:
    payload = deepcopy(_valid_payload())
    mutation(payload)

    with pytest.raises(ValidationError):
        OrganizationRecordUnderstandingDraft.model_validate(payload)


@pytest.mark.parametrize("section", ["facts", "decisions", "progress", "risks"])
def test_asserted_items_require_evidence(section: str) -> None:
    payload = _valid_payload()
    item: dict[str, Any] = {"statement": "已经形成明确结论。", "evidence": []}
    if section == "risks":
        item["severity"] = "high"
    payload[section] = [item]

    with pytest.raises(ValidationError):
        OrganizationRecordUnderstandingDraft.model_validate(payload)


def _outbox_payload() -> dict[str, Any]:
    return {
        "organization_id": ORGANIZATION_ID,
        "envelope_id": RECORD_ID,
        "_hxy_outbox": {
            "organization_id": ORGANIZATION_ID,
            "aggregate_type": "inbound_envelope",
            "aggregate_id": RECORD_ID,
            "outbox_message_id": OUTBOX_MESSAGE_ID,
            "worker_id": "record-worker-1",
            "attempt_number": 1,
            "assert_lease": lambda: None,
        },
    }


class FakeChannelRepository:
    def __init__(self) -> None:
        self.completed = False
        self.processed_fences: list[dict[str, Any]] = []

    def load_record_context(self, payload: dict[str, Any]) -> dict[str, Any]:
        assert payload["organization_id"] == ORGANIZATION_ID
        assert payload["envelope_id"] == RECORD_ID
        return {
            "organization_id": ORGANIZATION_ID,
            "envelope_id": RECORD_ID,
            "raw_text": "施工方尚未收到最终水电图，今天需要继续确认。",
            "attachments": [
                {
                    "source_asset_id": ASSET_ID,
                    "file_name": "施工记录.txt",
                    "media_type": "text/plain",
                    "storage_key": "unused-in-test",
                }
            ],
        }

    def mark_envelope_processed(
        self,
        organization_id: str,
        envelope_id: str,
        *,
        execution_fence: dict[str, Any],
    ) -> None:
        assert organization_id == ORGANIZATION_ID
        assert envelope_id == RECORD_ID
        self.completed = True
        self.processed_fences.append(deepcopy(execution_fence))


class FakeProposalRepository:
    def __init__(self) -> None:
        self.saved: dict[str, Any] | None = None
        self.fences: list[dict[str, Any]] = []

    def save_record_proposal(
        self,
        record: dict[str, Any],
        *,
        execution_fence: dict[str, Any],
    ) -> dict[str, Any]:
        self.saved = deepcopy(record)
        self.fences.append(deepcopy(execution_fence))
        return {"proposal_id": "proposal-1", "status": record["status"]}


class FakeModelRouter:
    def __init__(self, output: str, *, used_model: bool = True) -> None:
        self.output = output
        self.used_model = used_model
        self.calls: list[dict[str, Any]] = []

    def generate(self, task_type: str, **kwargs: Any) -> dict[str, Any]:
        self.calls.append({"task_type": task_type, **deepcopy(kwargs)})
        return {
            "output": self.output,
            "used_model": self.used_model,
            "route": {
                "provider": "test-provider",
                "selected_model": "test-model",
            },
        }


def _attachment_adapter(attachment: dict[str, Any], **_: Any) -> dict[str, Any]:
    return {
        "source_asset_id": attachment["source_asset_id"],
        "file_name": attachment["file_name"],
        "media_type": attachment["media_type"],
        "text": "附件确认：施工方尚未收到最终水电图。",
        "adapter": "test",
    }


def _build_handler(model_payload: dict[str, Any] | str, *, used_model: bool = True):
    channel_repository = FakeChannelRepository()
    proposal_repository = FakeProposalRepository()
    output = model_payload if isinstance(model_payload, str) else json.dumps(model_payload)
    model_router = FakeModelRouter(output, used_model=used_model)
    handler = build_record_understanding_handler(
        channel_repository,
        proposal_repository,
        model_router,
        attachment_adapter=_attachment_adapter,
    )
    return handler, channel_repository, proposal_repository, model_router


def test_handler_saves_only_proposed_interpretation_with_verbatim_evidence() -> None:
    handler, channel_repository, proposal_repository, model_router = _build_handler(
        _valid_payload()
    )

    result = handler(_outbox_payload())

    assert result == {"status": "processed", "proposal_id": "proposal-1"}
    assert model_router.calls[0]["task_type"] == "organization_record_understanding"
    assert proposal_repository.saved is not None
    assert proposal_repository.saved["proposal_type"] == "organization_record_understanding"
    assert proposal_repository.saved["status"] == "proposed"
    assert proposal_repository.saved["risk_level"] == "medium"
    assert (
        proposal_repository.saved["payload"]["risks"][0]["evidence"][0]["quote"]
        == "施工方尚未收到最终水电图"
    )
    assert "official_knowledge" not in proposal_repository.saved["payload"]
    assert proposal_repository.fences[0]["outbox_message_id"] == OUTBOX_MESSAGE_ID
    assert channel_repository.processed_fences[0]["outbox_message_id"] == OUTBOX_MESSAGE_ID
    assert channel_repository.completed is True


def test_prompt_forbids_inference_and_requires_bounded_evidence() -> None:
    handler, _channel, _proposal, model_router = _build_handler(_valid_payload())

    handler(_outbox_payload())

    prompt = model_router.calls[0]["prompt"]
    assert "不批准" in prompt
    assert "不编造" in prompt
    assert "无证据则省略" in prompt
    assert "每类最多5项" in prompt
    assert RECORD_ID in prompt


def test_invalid_model_json_is_retryable_and_does_not_complete_envelope() -> None:
    handler, channel_repository, proposal_repository, _ = _build_handler("not-json")

    with pytest.raises(OutboxHandlerError) as error:
        handler(_outbox_payload())

    assert error.value.code == "invalid_record_json"
    assert error.value.retryable is True
    assert proposal_repository.saved is None
    assert channel_repository.completed is False


def test_invalid_model_output_is_retryable_and_does_not_complete_envelope() -> None:
    model_payload = _valid_payload()
    model_payload["confidence"] = 2
    handler, channel_repository, proposal_repository, _ = _build_handler(model_payload)

    with pytest.raises(OutboxHandlerError) as error:
        handler(_outbox_payload())

    assert error.value.code == "invalid_record_output"
    assert error.value.retryable is True
    assert proposal_repository.saved is None
    assert channel_repository.completed is False


def test_model_unavailable_is_retryable_and_does_not_complete_envelope() -> None:
    handler, channel_repository, proposal_repository, _ = _build_handler(
        _valid_payload(), used_model=False
    )

    with pytest.raises(OutboxHandlerError) as error:
        handler(_outbox_payload())

    assert error.value.code == "model_unavailable"
    assert error.value.retryable is True
    assert proposal_repository.saved is None
    assert channel_repository.completed is False


@pytest.mark.parametrize(
    "invalid_evidence",
    [
        {
            "source_record_id": "55555555-5555-4555-8555-555555555555",
            "quote": "施工方尚未收到最终水电图",
        },
        {
            "source_record_id": RECORD_ID,
            "source_asset_id": "66666666-6666-4666-8666-666666666666",
            "quote": "施工方尚未收到最终水电图",
        },
        {
            "source_record_id": RECORD_ID,
            "quote": "原始记录中不存在的伪造证据",
        },
    ],
)
def test_handler_rejects_evidence_outside_the_current_record(invalid_evidence) -> None:
    model_payload = _valid_payload()
    model_payload["facts"][0]["evidence"] = [invalid_evidence]
    handler, channel_repository, proposal_repository, _ = _build_handler(model_payload)

    with pytest.raises(OutboxHandlerError) as error:
        handler(_outbox_payload())

    assert error.value.code == "invalid_record_evidence"
    assert error.value.retryable is True
    assert proposal_repository.saved is None
    assert channel_repository.completed is False


def test_handler_accepts_attachment_quote_after_whitespace_normalization() -> None:
    def whitespace_adapter(attachment: dict[str, Any], **_: Any) -> dict[str, Any]:
        return {
            "source_asset_id": attachment["source_asset_id"],
            "file_name": attachment["file_name"],
            "media_type": attachment["media_type"],
            "text": "附件确认：  施工方尚未收到\n最终水电图。",
            "adapter": "test",
        }

    model_payload = _valid_payload()
    model_payload["facts"][0]["evidence"] = [
        {
            "source_record_id": RECORD_ID,
            "source_asset_id": ASSET_ID,
            "quote": "施工方尚未收到 最终水电图",
        }
    ]
    channel_repository = FakeChannelRepository()
    proposal_repository = FakeProposalRepository()
    handler = build_record_understanding_handler(
        channel_repository,
        proposal_repository,
        FakeModelRouter(json.dumps(model_payload)),
        attachment_adapter=whitespace_adapter,
    )

    result = handler(_outbox_payload())

    assert result["status"] == "processed"
    assert proposal_repository.saved is not None
    assert channel_repository.completed is True


def test_handler_checks_worker_lease_before_persisting_side_effects() -> None:
    from apps.api.hxy_product.outbox_repository import OutboxLeaseLost

    handler, channel_repository, proposal_repository, _ = _build_handler(_valid_payload())
    payload = _outbox_payload()

    def reject_lost_lease() -> None:
        raise OutboxLeaseLost("lease was reclaimed")

    payload["_hxy_outbox"]["assert_lease"] = reject_lost_lease

    with pytest.raises(OutboxLeaseLost):
        handler(payload)

    assert proposal_repository.saved is None
    assert channel_repository.completed is False


def test_handler_rejects_scope_that_disagrees_with_authoritative_outbox() -> None:
    handler, channel_repository, proposal_repository, _ = _build_handler(_valid_payload())
    payload = _outbox_payload()
    payload["organization_id"] = "77777777-7777-4777-8777-777777777777"

    with pytest.raises(OutboxHandlerError) as error:
        handler(payload)

    assert error.value.code == "outbox_scope_mismatch"
    assert error.value.retryable is False
    assert proposal_repository.saved is None
    assert channel_repository.completed is False


def test_channel_repository_loads_record_without_store_governance_dependency() -> None:
    from apps.api.hxy_product.channel_repository import ChannelRepository

    repository = ChannelRepository("postgresql://record.test/hxy")
    calls: list[tuple[str, tuple[Any, ...]]] = []
    envelope_row = {
        "envelope_id": RECORD_ID,
        "organization_id": ORGANIZATION_ID,
        "raw_text": "施工方尚未收到最终水电图。",
    }
    asset_row = {
        "source_asset_id": ASSET_ID,
        "file_name": "施工记录.txt",
        "extension": ".txt",
        "media_type": "text/plain",
        "storage_key": "record.txt",
        "material_status": "received",
        "normalized_storage_key": "normalized/record.md",
    }

    class Result:
        def __init__(self, *, row=None, rows=None):
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
                return Result(row=envelope_row)
            if "FROM hxy_asset_bindings AS binding" in normalized:
                return Result(rows=[asset_row])
            raise AssertionError(normalized)

    repository.connect = lambda: Connection()

    context = repository.load_record_context(_outbox_payload())

    assert context == {
        "organization_id": ORGANIZATION_ID,
        "envelope_id": RECORD_ID,
        "raw_text": "施工方尚未收到最终水电图。",
        "attachments": [asset_row],
    }
    context_sql = calls[0][0]
    assert "envelope.intent_hint = 'organization_record'" in context_sql
    assert "envelope.status IN ('queued', 'processed')" in context_sql
    assert "relationship" not in context_sql.lower()
    assert "governance" not in context_sql.lower()
    assert all(params == (ORGANIZATION_ID, RECORD_ID) for _sql, params in calls)


def test_record_proposal_repository_is_idempotent_proposed_and_fenced() -> None:
    repository = OrganizationRecordProposalRepository("postgresql://proposal.test/hxy")
    calls: list[tuple[str, tuple[Any, ...]]] = []
    saved_row = {
        "proposal_id": "88888888-8888-4888-8888-888888888888",
        "organization_id": ORGANIZATION_ID,
        "source_envelope_id": RECORD_ID,
        "status": "proposed",
        "created_at": "2026-07-20T08:00:00Z",
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
                return Result(saved_row)
            raise AssertionError(normalized)

    repository.connect = lambda: Connection()
    record = {
        "organization_id": ORGANIZATION_ID,
        "source_envelope_id": RECORD_ID,
        "proposal_type": "organization_record_understanding",
        "payload": _valid_payload(),
        "confidence": 0.86,
        "risk_level": "medium",
        "model_provider": "aliyun",
        "model_name": "qwen3.5-plus",
        "prompt_version": "organization-record-understanding.v1",
        "input_hash": "a" * 64,
        "status": "proposed",
    }
    fence = {
        "organization_id": ORGANIZATION_ID,
        "outbox_message_id": OUTBOX_MESSAGE_ID,
        "worker_id": "record-worker-1",
        "attempt_number": 1,
    }

    saved = repository.save_record_proposal(record, execution_fence=fence)

    assert saved["status"] == "proposed"
    assert "FOR UPDATE" in calls[0][0]
    insert_sql, insert_params = calls[1]
    assert "'content_draft'" in insert_sql
    assert (
        "ON CONFLICT (organization_id, source_envelope_id, proposal_type, input_hash)"
        in insert_sql
    )
    assert "proposed" in insert_params
    assert "approved" not in insert_params


def test_model_router_exposes_organization_record_understanding_route(
    tmp_path: Path,
) -> None:
    from apps.api.hxy_knowledge.model_router import ModelRouter

    config = tmp_path / "config.toml"
    config.write_text(
        '\n'.join(
            [
                'model_provider = "aliyun"',
                'model = "qwen3.5-plus"',
                '[model_providers.aliyun]',
                'base_url = "https://example.invalid/v1"',
                'wire_api = "responses"',
            ]
        ),
        encoding="utf-8",
    )

    router = ModelRouter(config)
    route = router.route("organization_record_understanding")

    assert route["task_type"] == "organization_record_understanding"
    assert route["selected_model"] == "qwen3.5-plus"
    assert "组织记录" in route["purpose"]
    assert "organization_record_understanding" in {
        item["task_type"] for item in router.status()["routes"]
    }
