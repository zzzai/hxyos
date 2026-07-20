from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import ValidationError

from apps.api.hxy_knowledge_api import create_app


ORGANIZATION_ID = "10000000-0000-0000-0000-000000000001"
ACCOUNT_ID = "11000000-0000-0000-0000-000000000001"
RECORD_ID = "20000000-0000-0000-0000-000000000001"
FOREIGN_RECORD_ID = "20000000-0000-0000-0000-000000000099"
ASSET_ID = "30000000-0000-0000-0000-000000000001"
FOUNDER_ID = "40000000-0000-0000-0000-000000000001"
HQ_ID = "40000000-0000-0000-0000-000000000002"
MANAGER_ID = "40000000-0000-0000-0000-000000000003"
EMPLOYEE_ID = "40000000-0000-0000-0000-000000000004"
STORE_ID = "store-1"
CAPTURED_AT = datetime(2026, 7, 20, 8, 30, tzinfo=timezone.utc)
OCCURRED_AT = datetime(2026, 7, 20, 7, 45, tzinfo=timezone.utc)


@dataclass(frozen=True)
class RoutePrincipal:
    account_id: str = ACCOUNT_ID
    display_name: str = "测试创始人"
    assignment_id: str = FOUNDER_ID


@dataclass(frozen=True)
class RouteAssignment:
    assignment_id: str = FOUNDER_ID
    organization_id: str = ORGANIZATION_ID
    organization_name: str = "荷小悦"
    store_id: str | None = None
    store_name: str | None = None
    role: str = "founder"


class RouteIdentityRepository:
    def __init__(self, assignment: RouteAssignment | None = None) -> None:
        self.assignment = assignment or RouteAssignment()

    def resolve_session(self, raw_token: str) -> RoutePrincipal | None:
        if raw_token != "valid-session":
            return None
        return RoutePrincipal(assignment_id=self.assignment.assignment_id)

    def list_assignments(self, _account_id: str) -> list[RouteAssignment]:
        return [self.assignment]


class RouteChannelRepository:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def accept_authenticated_record(
        self,
        payload: dict[str, Any],
        *,
        assignment: RouteAssignment,
    ) -> dict[str, Any]:
        self.calls.append({"payload": payload, "assignment": assignment})
        return {
            "id": RECORD_ID,
            "organization_id": ORGANIZATION_ID,
            "channel": "pwa",
            "assignment_id": assignment.assignment_id,
            "store_id": assignment.store_id,
            "status": "queued",
            "received_at": CAPTURED_AT,
        }


class RouteRecordRepository:
    def __init__(self) -> None:
        from apps.api.hxy_product.record_repository import public_record

        self.record = public_record(
            record_row(
                raw_text="水电图今天确认",
                status="queued",
                interpretation_payload=None,
                assets=[],
            )
        )

    def list_records(self, **_scope: Any) -> list[dict[str, Any]]:
        return [dict(self.record)]

    def get_record(self, *, record_id: str, **_scope: Any) -> dict[str, Any] | None:
        return dict(self.record) if record_id == RECORD_ID else None


class RouteClient:
    def __init__(self, app: Any, channel_repository: RouteChannelRepository) -> None:
        self.app = app
        self.channel_repository = channel_repository

    def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        async def run() -> httpx.Response:
            transport = httpx.ASGITransport(app=self.app, raise_app_exceptions=False)
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://testserver",
            ) as client:
                return await client.request(method, url, **kwargs)

        return asyncio.run(run())


def record_route_client(
    tmp_path: Path,
    assignment: RouteAssignment | None = None,
) -> RouteClient:
    identity = RouteIdentityRepository(assignment)
    channel = RouteChannelRepository()
    records = RouteRecordRepository()
    app = create_app(
        root_dir=tmp_path,
        repository_factory=lambda: object(),
        product_identity_repository_factory=lambda: identity,
        channel_repository_factory=lambda: channel,
        record_repository_factory=lambda: records,
    )
    return RouteClient(app, channel)


def route_headers() -> dict[str, str]:
    return {"Authorization": "Bearer valid-session"}


def test_post_organization_record_returns_async_receipt(tmp_path: Path) -> None:
    client = record_route_client(tmp_path)

    response = client.request(
        "POST",
        "/api/v1/organization-records",
        headers=route_headers(),
        json={
            "client_record_id": "12000000-0000-0000-0000-000000000001",
            "text": "水电图今天确认",
            "source_asset_ids": [],
        },
    )

    assert response.status_code == 202
    assert response.json()["record"]["processing_status"] in {
        "received",
        "processing",
    }
    call = client.channel_repository.calls[0]
    assert call["payload"]["intent_hint"] == "organization_record"
    assert call["payload"]["idempotency_key"] == (
        "12000000-0000-0000-0000-000000000001"
    )
    assert call["assignment"].store_id is None


def test_list_organization_records_returns_visible_records(tmp_path: Path) -> None:
    client = record_route_client(tmp_path)

    response = client.request(
        "GET",
        "/api/v1/organization-records?limit=50",
        headers=route_headers(),
    )

    assert response.status_code == 200
    assert isinstance(response.json()["records"], list)


def test_detail_returns_visible_record_and_hides_out_of_scope_record(
    tmp_path: Path,
) -> None:
    client = record_route_client(tmp_path)

    visible = client.request(
        "GET",
        f"/api/v1/organization-records/{RECORD_ID}",
        headers=route_headers(),
    )
    hidden = client.request(
        "GET",
        f"/api/v1/organization-records/{FOREIGN_RECORD_ID}",
        headers=route_headers(),
    )

    assert visible.status_code == 200
    assert visible.json()["record"]["id"] == RECORD_ID
    assert hidden.status_code == 404


def test_system_admin_cannot_create_or_read_organization_records(
    tmp_path: Path,
) -> None:
    client = record_route_client(
        tmp_path,
        RouteAssignment(
            assignment_id=HQ_ID,
            role="system_admin",
        ),
    )

    created = client.request(
        "POST",
        "/api/v1/organization-records",
        headers=route_headers(),
        json={
            "client_record_id": "12000000-0000-0000-0000-000000000002",
            "text": "系统管理员不应读取业务记录",
            "source_asset_ids": [],
        },
    )
    listed = client.request(
        "GET",
        "/api/v1/organization-records",
        headers=route_headers(),
    )

    assert created.status_code == 403
    assert listed.status_code == 403
    assert client.channel_repository.calls == []


class RecordIntakeConnection:
    def __init__(
        self,
        assignment: dict[str, Any],
        assets: list[dict[str, Any]],
    ) -> None:
        self.assignment = assignment
        self.assets = assets
        self.executed: list[tuple[str, tuple[Any, ...]]] = []

    def __enter__(self) -> "RecordIntakeConnection":
        return self

    def __exit__(self, *_args: Any) -> None:
        return None

    def execute(self, sql: str, params: tuple[Any, ...]) -> QueryResult:
        normalized = " ".join(sql.split())
        self.executed.append((normalized, params))
        if "FROM hxy_role_assignments AS assignment" in normalized:
            return QueryResult([self.assignment])
        if "SELECT envelope_id::text" in normalized:
            return QueryResult([])
        if "FROM hxy_product_materials AS material" in normalized:
            return QueryResult(self.assets)
        if "INSERT INTO hxy_inbound_envelopes" in normalized:
            return QueryResult(
                [
                    {
                        "envelope_id": RECORD_ID,
                        "organization_id": ORGANIZATION_ID,
                        "channel": "pwa",
                        "sender_assignment_id": self.assignment["assignment_id"],
                        "store_id": self.assignment.get("store_id"),
                        "status": "received",
                        "request_fingerprint": "",
                        "received_at": CAPTURED_AT,
                        "created_at": CAPTURED_AT,
                        "updated_at": CAPTURED_AT,
                    }
                ]
            )
        if "INSERT INTO hxy_asset_bindings" in normalized:
            return QueryResult([])
        if "INSERT INTO hxy_outbox_messages" in normalized:
            return QueryResult([])
        if "UPDATE hxy_inbound_envelopes" in normalized:
            return QueryResult(
                [
                    {
                        "envelope_id": RECORD_ID,
                        "organization_id": ORGANIZATION_ID,
                        "channel": "pwa",
                        "sender_assignment_id": self.assignment["assignment_id"],
                        "store_id": self.assignment.get("store_id"),
                        "status": "queued",
                        "received_at": CAPTURED_AT,
                        "created_at": CAPTURED_AT,
                        "updated_at": CAPTURED_AT,
                    }
                ]
            )
        raise AssertionError(normalized)


def authenticated_record_payload(source_asset_ids: list[str]) -> dict[str, Any]:
    return {
        "organization_id": ORGANIZATION_ID,
        "channel": "pwa",
        "channel_tenant_id": ORGANIZATION_ID,
        "channel_message_id": "12000000-0000-0000-0000-000000000003",
        "channel_thread_id": "",
        "channel_user_id": ACCOUNT_ID,
        "idempotency_key": "12000000-0000-0000-0000-000000000003",
        "raw_text": "水电图今天确认",
        "raw_payload": {},
        "source_asset_ids": source_asset_ids,
        "intent_hint": "organization_record",
    }


def test_founder_record_intake_uses_org_asset_scope_and_dedicated_outbox() -> None:
    from apps.api.hxy_product.channel_repository import ChannelRepository

    assignment = {
        "assignment_id": FOUNDER_ID,
        "organization_id": ORGANIZATION_ID,
        "store_id": None,
        "role": "founder",
    }
    connection = RecordIntakeConnection(
        assignment,
        [
            {
                "material_id": ASSET_ID,
                "assignment_id": FOUNDER_ID,
                "store_id": None,
                "scan_status": "clean",
                "visibility_scope": {"hq": True},
            }
        ],
    )
    repository = ChannelRepository("postgresql://records.test/hxy")
    repository.connect = lambda: connection

    receipt = repository.accept_authenticated_record(
        authenticated_record_payload([ASSET_ID]),
        assignment=RouteAssignment(),
    )

    assert receipt["status"] == "queued"
    asset_sql = next(
        sql for sql, _ in connection.executed if "FROM hxy_product_materials" in sql
    )
    assert "material.organization_id = %s::uuid" in asset_sql
    assert "(material.store_id IS NULL OR material.store_id = %s)" not in asset_sql
    envelope_sql, envelope_params = next(
        (sql, params)
        for sql, params in connection.executed
        if "INSERT INTO hxy_inbound_envelopes" in sql
    )
    assert "intent_hint" in envelope_sql
    assert "organization_record" in envelope_params
    outbox_sql, _ = next(
        (sql, params)
        for sql, params in connection.executed
        if "INSERT INTO hxy_outbox_messages" in sql
    )
    assert "'understand.organization_record'" in outbox_sql
    assert "'inbound_envelope'" in outbox_sql
    assert "LIKE" not in outbox_sql.upper()


def test_store_record_intake_cannot_bind_hq_only_attachment() -> None:
    from apps.api.hxy_product.channel_repository import (
        ChannelRepository,
        SourceAssetAccessDenied,
    )

    assignment = {
        "assignment_id": MANAGER_ID,
        "organization_id": ORGANIZATION_ID,
        "store_id": STORE_ID,
        "role": "store_manager",
    }
    connection = RecordIntakeConnection(
        assignment,
        [
            {
                "material_id": ASSET_ID,
                "assignment_id": FOUNDER_ID,
                "store_id": None,
                "scan_status": "clean",
                "visibility_scope": {"hq": True},
            }
        ],
    )
    repository = ChannelRepository("postgresql://records.test/hxy")
    repository.connect = lambda: connection

    with pytest.raises(SourceAssetAccessDenied):
        repository.accept_authenticated_record(
            authenticated_record_payload([ASSET_ID]),
            assignment=RouteAssignment(
                assignment_id=MANAGER_ID,
                store_id=STORE_ID,
                store_name="首店",
                role="store_manager",
            ),
        )

    assert not any(
        "INSERT INTO hxy_asset_bindings" in sql for sql, _ in connection.executed
    )
    assert not any(
        "INSERT INTO hxy_outbox_messages" in sql for sql, _ in connection.executed
    )


def record_row(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "record_id": RECORD_ID,
        "channel": "pwa",
        "raw_text": "施工群原始记录",
        "raw_payload": {"occurred_at": OCCURRED_AT.isoformat()},
        "sender_assignment_id": MANAGER_ID,
        "submitted_by": "测试店长",
        "store_id": STORE_ID,
        "status": "processed",
        "captured_at": CAPTURED_AT,
        "interpretation_version": "record-understanding-v1",
        "interpretation_confidence": 0.82,
        "interpretation_payload": {
            "summary": "水电图仍缺最终确认",
            "facts": [
                {
                    "statement": "施工方已进群",
                    "evidence": [
                        {
                            "source_record_id": RECORD_ID,
                            "quote": "施工方已进群",
                            "locator": "消息 3",
                        }
                    ],
                }
            ],
            "decisions": [],
            "progress": [],
            "risks": [
                {
                    "statement": "水电图未最终确认",
                    "evidence": [
                        {
                            "source_record_id": RECORD_ID,
                            "source_asset_id": ASSET_ID,
                            "quote": "最终水电图待确认",
                        }
                    ],
                }
            ],
            "missing_information": ["最终水电图确认时间"],
            "official_knowledge": True,
            "internal_trace": {"chain_of_thought": "must not leak"},
        },
        "assets": [
            {
                "id": ASSET_ID,
                "file_name": "门店水电图.png",
                "media_type": "image/png",
                "size_bytes": 2048,
                "status": "understood",
                "storage_key": "must/not/leak.png",
            }
        ],
    }
    row.update(overrides)
    return row


class QueryResult:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def fetchall(self) -> list[dict[str, Any]]:
        return self.rows

    def fetchone(self) -> dict[str, Any] | None:
        return self.rows[0] if self.rows else None


class RecordingConnection:
    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self.rows = rows or []
        self.executed: list[tuple[str, tuple[Any, ...]]] = []

    def __enter__(self) -> "RecordingConnection":
        return self

    def __exit__(self, *_args: Any) -> None:
        return None

    def execute(self, sql: str, params: tuple[Any, ...]) -> QueryResult:
        self.executed.append((" ".join(sql.split()), params))
        return QueryResult(self.rows)


def repository_with(
    rows: list[dict[str, Any]] | None = None,
) -> tuple[Any, RecordingConnection]:
    from apps.api.hxy_product.record_repository import RecordRepository

    connection = RecordingConnection(rows)
    repository = RecordRepository("postgresql://records.test/hxy")
    repository.connect = lambda: connection
    return repository, connection


def test_record_projection_keeps_original_and_interpretation_separate() -> None:
    from apps.api.hxy_product.record_repository import public_record

    record = public_record(record_row())

    assert record["original"]["text"] == "施工群原始记录"
    assert record["interpretation"]["summary"] == "水电图仍缺最终确认"
    assert record["interpretation"]["facts"][0]["statement"] == "施工方已进群"
    assert record["interpretation"]["official_knowledge"] is False
    assert "internal_trace" not in record["interpretation"]
    assert "storage_key" not in record["original"]["assets"][0]


def test_record_projection_bounds_original_text_to_public_contract() -> None:
    from apps.api.hxy_product.record_repository import public_record
    from apps.api.hxy_product.record_schemas import OrganizationRecord

    raw_text = "原" * 20_001

    record = public_record(record_row(raw_text=raw_text))

    assert record["original"]["text"] == raw_text[:20_000]
    OrganizationRecord.model_validate(record)


def test_record_projection_forces_official_knowledge_false_for_json_payload() -> None:
    from apps.api.hxy_product.record_repository import public_record

    row = record_row(
        interpretation_payload=json.dumps(
            {
                "summary": "工作判断",
                "facts": [],
                "decisions": [],
                "progress": [],
                "risks": [],
                "missing_information": [],
                "official_knowledge": True,
                "unexpected": "private implementation field",
            }
        )
    )

    interpretation = public_record(row)["interpretation"]

    assert interpretation["official_knowledge"] is False
    assert "unexpected" not in interpretation


@pytest.mark.parametrize(
    ("internal_status", "public_status"),
    [
        ("received", "received"),
        ("queued", "processing"),
        ("processed", "ready"),
        ("needs_attention", "needs_attention"),
        ("rejected", "needs_attention"),
        ("unknown_status", "needs_attention"),
    ],
)
def test_record_projection_maps_processing_status(
    internal_status: str,
    public_status: str,
) -> None:
    from apps.api.hxy_product.record_repository import public_record

    assert public_record(record_row(status=internal_status))["processing_status"] == (
        public_status
    )


def test_record_projection_derives_source_types_and_safe_assets() -> None:
    from apps.api.hxy_product.record_repository import public_record

    row = record_row(
        assets=json.dumps(
            [
                {
                    "id": ASSET_ID,
                    "file_name": "门店水电图.png",
                    "media_type": "image/png",
                    "size_bytes": 2048,
                    "status": "understood",
                },
                {
                    "id": "30000000-0000-0000-0000-000000000002",
                    "file_name": "施工说明.pdf",
                    "media_type": "application/pdf",
                    "size_bytes": 4096,
                    "status": "received",
                },
            ]
        )
    )

    record = public_record(row)

    assert record["source_types"] == ["text", "image", "document"]
    assert record["original"]["assets"] == [
        {
            "id": ASSET_ID,
            "file_name": "门店水电图.png",
            "media_type": "image/png",
            "size_bytes": 2048,
            "status": "ready",
        },
        {
            "id": "30000000-0000-0000-0000-000000000002",
            "file_name": "施工说明.pdf",
            "media_type": "application/pdf",
            "size_bytes": 4096,
            "status": "processing",
        },
    ]


def test_record_projection_preserves_evidence_and_occurrence_time() -> None:
    from apps.api.hxy_product.record_repository import public_record

    record = public_record(record_row())

    evidence = record["interpretation"]["risks"][0]["evidence"][0]
    assert evidence == {
        "source_record_id": RECORD_ID,
        "source_asset_id": ASSET_ID,
        "quote": "最终水电图待确认",
    }
    assert record["occurred_at"] == OCCURRED_AT
    assert record["captured_at"] == CAPTURED_AT


def test_malformed_interpretation_json_is_normalized_to_safe_empty_fields() -> None:
    from apps.api.hxy_product.record_repository import public_record

    record = public_record(
        record_row(
            interpretation_payload={
                "summary": {"not": "text"},
                "facts": [None, {"statement": "", "evidence": "bad"}],
                "decisions": "bad",
                "progress": [{"statement": "已完成", "internal": "drop"}],
                "risks": [{"statement": 123, "evidence": []}],
                "missing_information": [None, {"private": True}, "补充确认人"],
                "confidence": "not-a-number",
            }
        )
    )

    assert record["interpretation"] == {
        "version": "record-understanding-v1",
        "summary": "",
        "facts": [],
        "decisions": [],
        "progress": [{"statement": "已完成", "evidence": []}],
        "risks": [],
        "missing_information": ["补充确认人"],
        "confidence": 0.82,
        "official_knowledge": False,
    }


def test_strict_record_schema_rejects_extra_public_fields() -> None:
    from apps.api.hxy_product.record_repository import public_record
    from apps.api.hxy_product.record_schemas import OrganizationRecord

    payload = public_record(record_row())
    payload["governance_status"] = "approved"

    with pytest.raises(ValidationError):
        OrganizationRecord.model_validate(payload)


@pytest.mark.parametrize(
    ("role", "assignment_id", "store_id", "required_sql", "params"),
    [
        (
            "founder",
            FOUNDER_ID,
            None,
            "envelope.organization_id = %s::uuid",
            (ORGANIZATION_ID, 20),
        ),
        (
            "hq_operations",
            HQ_ID,
            None,
            "envelope.organization_id = %s::uuid",
            (ORGANIZATION_ID, 20),
        ),
        (
            "store_manager",
            MANAGER_ID,
            STORE_ID,
            "envelope.store_id = %s",
            (ORGANIZATION_ID, STORE_ID, 20),
        ),
        (
            "store_employee",
            EMPLOYEE_ID,
            STORE_ID,
            "envelope.sender_assignment_id = %s::uuid",
            (ORGANIZATION_ID, EMPLOYEE_ID, 20),
        ),
    ],
)
def test_list_records_uses_fixed_role_selected_sql_scope(
    role: str,
    assignment_id: str,
    store_id: str | None,
    required_sql: str,
    params: tuple[Any, ...],
) -> None:
    repository, connection = repository_with()

    assert (
        repository.list_records(
            organization_id=ORGANIZATION_ID,
            assignment_id=assignment_id,
            role=role,
            store_id=store_id,
            limit=20,
        )
        == []
    )

    sql, actual_params = connection.executed[0]
    assert required_sql in sql
    assert "envelope.intent_hint = 'organization_record'" in sql
    assert "proposal.proposal_type = 'organization_record_understanding'" in sql
    assert "FROM hxy_asset_bindings AS binding" in sql
    assert "JOIN hxy_product_materials AS material" in sql
    assert actual_params == params
    if role in {"founder", "hq_operations"}:
        assert "envelope.store_id = %s" not in sql
        assert "envelope.sender_assignment_id = %s::uuid" not in sql


def test_unsupported_role_has_no_record_access() -> None:
    from apps.api.hxy_product.record_repository import RecordAccessDenied

    repository, connection = repository_with()

    with pytest.raises(RecordAccessDenied):
        repository.list_records(
            organization_id=ORGANIZATION_ID,
            assignment_id="50000000-0000-0000-0000-000000000001",
            role="system_admin",
            store_id=None,
            limit=20,
        )

    assert connection.executed == []


def test_manager_without_active_store_has_no_record_access() -> None:
    from apps.api.hxy_product.record_repository import RecordAccessDenied

    repository, connection = repository_with()

    with pytest.raises(RecordAccessDenied):
        repository.list_records(
            organization_id=ORGANIZATION_ID,
            assignment_id=MANAGER_ID,
            role="store_manager",
            store_id=None,
            limit=20,
        )

    assert connection.executed == []


def test_get_record_returns_none_when_not_found_or_out_of_scope() -> None:
    repository, connection = repository_with()

    record = repository.get_record(
        organization_id=ORGANIZATION_ID,
        record_id=RECORD_ID,
        assignment_id=EMPLOYEE_ID,
        role="store_employee",
        store_id=STORE_ID,
    )

    assert record is None
    sql, params = connection.executed[0]
    assert "envelope.envelope_id = %s::uuid" in sql
    assert "envelope.intent_hint = 'organization_record'" in sql
    assert "envelope.sender_assignment_id = %s::uuid" in sql
    assert params == (ORGANIZATION_ID, RECORD_ID, EMPLOYEE_ID)


def test_get_record_projects_visible_row() -> None:
    repository, _ = repository_with([record_row()])

    record = repository.get_record(
        organization_id=ORGANIZATION_ID,
        record_id=RECORD_ID,
        assignment_id=MANAGER_ID,
        role="store_manager",
        store_id=STORE_ID,
    )

    assert record is not None
    assert record["id"] == RECORD_ID
    assert record["submitted_by"] == "测试店长"


def test_record_capabilities_exclude_system_admin() -> None:
    from apps.api.hxy_product.routes import ROLE_CAPABILITIES

    for role in ("founder", "hq_operations", "store_manager", "store_employee"):
        assert "records:create" in ROLE_CAPABILITIES[role]
        assert "records:read" in ROLE_CAPABILITIES[role]

    assert "records:create" not in ROLE_CAPABILITIES["system_admin"]
    assert "records:read" not in ROLE_CAPABILITIES["system_admin"]
