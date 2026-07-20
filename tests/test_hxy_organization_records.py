from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import pytest
from pydantic import ValidationError


ORGANIZATION_ID = "10000000-0000-0000-0000-000000000001"
RECORD_ID = "20000000-0000-0000-0000-000000000001"
ASSET_ID = "30000000-0000-0000-0000-000000000001"
FOUNDER_ID = "40000000-0000-0000-0000-000000000001"
HQ_ID = "40000000-0000-0000-0000-000000000002"
MANAGER_ID = "40000000-0000-0000-0000-000000000003"
EMPLOYEE_ID = "40000000-0000-0000-0000-000000000004"
STORE_ID = "store-1"
CAPTURED_AT = datetime(2026, 7, 20, 8, 30, tzinfo=timezone.utc)
OCCURRED_AT = datetime(2026, 7, 20, 7, 45, tzinfo=timezone.utc)


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
