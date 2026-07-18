from __future__ import annotations

import importlib
from datetime import datetime, timezone
from typing import Any

import pytest
from pydantic import ValidationError


ORGANIZATION_ID = "30000000-0000-0000-0000-000000000001"
ASSIGNMENT_ID = "20000000-0000-0000-0000-000000000001"
BINDING_ID = "21000000-0000-0000-0000-000000000001"
RELATIONSHIP_ID = "22000000-0000-0000-0000-000000000001"
GOVERNANCE_ID = "23000000-0000-0000-0000-000000000001"
ENVELOPE_ID = "24000000-0000-0000-0000-000000000001"
OUTBOX_ID = "25000000-0000-0000-0000-000000000001"
ASSET_ID = "26000000-0000-0000-0000-000000000001"
STORE_ID = "hxy-pilot-store"
NOW = datetime(2026, 7, 18, 10, 0, tzinfo=timezone.utc)


class Result:
    def __init__(self, row: dict[str, Any] | None = None, rows=None, rowcount: int = 0):
        self.row = row
        self.rows = rows or []
        self.rowcount = rowcount

    def fetchone(self):
        return self.row

    def fetchall(self):
        return self.rows


def payload(**overrides: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "organization_id": ORGANIZATION_ID,
        "channel": "feishu",
        "channel_tenant_id": "tenant-key",
        "channel_message_id": "om_xxx",
        "channel_thread_id": "oc_xxx",
        "channel_user_id": "ou_xxx",
        "idempotency_key": "feishu:event-id",
        "raw_text": "前台灯闪烁",
        "raw_payload": {"event_type": "im.message.receive_v1", "secret": "discard-me"},
        "source_asset_ids": [ASSET_ID],
    }
    value.update(overrides)
    return value


def binding_row() -> dict[str, Any]:
    return {
        "binding_id": BINDING_ID,
        "assignment_id": ASSIGNMENT_ID,
        "organization_id": ORGANIZATION_ID,
        "store_id": STORE_ID,
        "role": "store_manager",
    }


def relationship_row() -> dict[str, Any]:
    return {
        "relationship_id": RELATIONSHIP_ID,
        "relationship_version": 1,
        "governance_profile_id": GOVERNANCE_ID,
        "governance_profile_version": 1,
    }


def envelope_row(*, status: str = "received", mapped: bool = True) -> dict[str, Any]:
    return {
        "envelope_id": ENVELOPE_ID,
        "organization_id": ORGANIZATION_ID,
        "channel": "feishu",
        "sender_assignment_id": ASSIGNMENT_ID if mapped else None,
        "store_id": STORE_ID if mapped else None,
        "status": status,
        "received_at": NOW,
        "created_at": NOW,
        "updated_at": NOW,
    }


def test_channel_schema_is_strict_and_requires_text_or_an_attachment() -> None:
    schemas = importlib.import_module("apps.api.hxy_product.channel_schemas")

    with pytest.raises(ValidationError):
        schemas.ChannelIntakePayload.model_validate(payload(unexpected=True))

    with pytest.raises(ValidationError):
        schemas.ChannelIntakePayload.model_validate(
            payload(raw_text=" ", source_asset_ids=[])
        )


def test_mapped_intake_persists_envelope_bindings_and_outbox_in_one_transaction() -> None:
    module = importlib.import_module("apps.api.hxy_product.channel_repository")
    repository = module.ChannelRepository("postgresql://channel.test/hxy")
    calls: list[tuple[str, tuple[Any, ...]]] = []

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, sql: str, params: tuple[Any, ...]):
            normalized = " ".join(sql.split())
            calls.append((normalized, params))
            if "FROM hxy_channel_identity_bindings AS binding" in normalized:
                assert "FOR SHARE OF binding, assignment" in normalized
                return Result(binding_row())
            if "FROM hxy_store_operating_relationships AS relationship" in normalized:
                assert "governance.status = 'published'" in normalized
                return Result(relationship_row())
            if "FROM hxy_product_materials AS material" in normalized:
                assert "material.organization_id = %s::uuid" in normalized
                assert "material.store_id IS NULL OR material.store_id = %s" in normalized
                return Result(rows=[{"material_id": ASSET_ID, "visibility_scope": {"store_manager": True}}])
            if "FROM hxy_inbound_envelopes" in normalized:
                return Result(None)
            if "INSERT INTO hxy_inbound_envelopes" in normalized:
                assert "ON CONFLICT (organization_id, channel, idempotency_key) DO NOTHING" in normalized
                return Result(envelope_row())
            if "INSERT INTO hxy_asset_bindings" in normalized:
                return Result({"binding_id": "27000000-0000-0000-0000-000000000001"})
            if "INSERT INTO hxy_outbox_messages" in normalized:
                assert "'understand.inbound.issue'" in normalized
                return Result({"outbox_message_id": OUTBOX_ID})
            if "UPDATE hxy_inbound_envelopes" in normalized:
                return Result(envelope_row(status="queued"))
            raise AssertionError(normalized)

    repository.connect = lambda: Connection()

    receipt = repository.accept_inbound(payload())

    assert receipt == {
        "id": ENVELOPE_ID,
        "organization_id": ORGANIZATION_ID,
        "channel": "feishu",
        "assignment_id": ASSIGNMENT_ID,
        "store_id": STORE_ID,
        "status": "queued",
        "received_at": NOW,
    }
    envelope_insert = next(i for i, (sql, _) in enumerate(calls) if "INSERT INTO hxy_inbound_envelopes" in sql)
    outbox_insert = next(i for i, (sql, _) in enumerate(calls) if "INSERT INTO hxy_outbox_messages" in sql)
    assert envelope_insert < outbox_insert


def test_duplicate_idempotency_key_returns_existing_envelope_without_requeue() -> None:
    module = importlib.import_module("apps.api.hxy_product.channel_repository")
    repository = module.ChannelRepository("postgresql://channel.test/hxy")
    calls: list[str] = []

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, sql: str, _params: tuple[Any, ...]):
            normalized = " ".join(sql.split())
            calls.append(normalized)
            if "FROM hxy_channel_identity_bindings AS binding" in normalized:
                return Result(binding_row())
            if "FROM hxy_store_operating_relationships AS relationship" in normalized:
                return Result(relationship_row())
            if "FROM hxy_product_materials AS material" in normalized:
                return Result(rows=[{"material_id": ASSET_ID, "visibility_scope": {"store_manager": True}}])
            if "FROM hxy_inbound_envelopes" in normalized:
                return Result(envelope_row(status="queued"))
            raise AssertionError(normalized)

    repository.connect = lambda: Connection()

    receipt = repository.accept_inbound(payload())

    assert receipt["id"] == ENVELOPE_ID
    assert receipt["status"] == "queued"
    assert not any("INSERT INTO hxy_outbox_messages" in sql for sql in calls)


def test_unmapped_identity_records_restricted_attention_envelope_without_outbox() -> None:
    module = importlib.import_module("apps.api.hxy_product.channel_repository")
    repository = module.ChannelRepository("postgresql://channel.test/hxy")
    calls: list[tuple[str, tuple[Any, ...]]] = []

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, sql: str, params: tuple[Any, ...]):
            normalized = " ".join(sql.split())
            calls.append((normalized, params))
            if "FROM hxy_channel_identity_bindings AS binding" in normalized:
                return Result(None)
            if "FROM hxy_inbound_envelopes" in normalized:
                return Result(None)
            if "INSERT INTO hxy_inbound_envelopes" in normalized:
                assert "needs_attention" in params
                raw_payload = next(value for value in params if isinstance(value, str) and "unmapped_identity" in value)
                assert "discard-me" not in raw_payload
                return Result(envelope_row(status="needs_attention", mapped=False))
            raise AssertionError(normalized)

    repository.connect = lambda: Connection()

    receipt = repository.accept_inbound(payload())

    assert receipt["assignment_id"] is None
    assert receipt["status"] == "needs_attention"
    assert not any("INSERT INTO hxy_outbox_messages" in sql for sql, _ in calls)


def test_unauthorized_source_asset_aborts_before_envelope_creation() -> None:
    module = importlib.import_module("apps.api.hxy_product.channel_repository")
    repository = module.ChannelRepository("postgresql://channel.test/hxy")
    calls: list[str] = []

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, sql: str, _params: tuple[Any, ...]):
            normalized = " ".join(sql.split())
            calls.append(normalized)
            if "FROM hxy_channel_identity_bindings AS binding" in normalized:
                return Result(binding_row())
            if "FROM hxy_store_operating_relationships AS relationship" in normalized:
                return Result(relationship_row())
            if "FROM hxy_product_materials AS material" in normalized:
                return Result(rows=[])
            raise AssertionError(normalized)

    repository.connect = lambda: Connection()

    with pytest.raises(module.SourceAssetAccessDenied):
        repository.accept_inbound(payload())

    assert not any("INSERT INTO hxy_inbound_envelopes" in sql for sql in calls)
