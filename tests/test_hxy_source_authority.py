from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from pydantic import ValidationError

from apps.api.hxy_knowledge.reliability import evidence_authority_source
from apps.api.hxy_product.material_repository import (
    MaterialRepository,
    _material_chunk_from_row,
    _material_from_row,
    derive_source_authority,
)
from apps.api.hxy_product.material_routes import _public_material
from apps.api.hxy_product.material_schemas import SourceAuthorityUpdate
from apps.api.hxy_knowledge.reliability import evidence_authority_source


ASSIGNMENT_ID = str(uuid4())
MATERIAL_ID = str(uuid4())
NOW = datetime(2026, 7, 15, tzinfo=timezone.utc)


def _material_row(**overrides: Any) -> dict[str, Any]:
    return {
        "material_id": MATERIAL_ID,
        "assignment_id": ASSIGNMENT_ID,
        "client_upload_id": str(uuid4()),
        "original_file_name": "首店接待流程.md",
        "extension": ".md",
        "media_type": "text/markdown",
        "size_bytes": 128,
        "sha256": "a" * 64,
        "storage_key": f"{ASSIGNMENT_ID}/{MATERIAL_ID}/首店接待流程.md",
        "note": "",
        "status": "ready",
        "understanding_json": {"domain": "operations"},
        "source_origin": "internal",
        "source_authority": "internal_material",
        "authority_version": 1,
        "official_use_allowed": False,
        "created_at": NOW,
        "updated_at": NOW,
        **overrides,
    }


@pytest.mark.parametrize(
    ("origin", "expected"),
    [
        ("internal", "internal_material"),
        ("external", "external_reference"),
        ("unknown", "external_reference"),
        ("", "external_reference"),
    ],
)
def test_upload_source_authority_defaults_safely_from_origin(
    origin: str,
    expected: str,
) -> None:
    assert derive_source_authority(origin) == expected


def test_material_record_exposes_source_level_authority_separately_from_ai_claims() -> None:
    material = _material_from_row(
        _material_row(
            understanding_json={
                "source_origin": "internal",
                "authority_level": "claimed_official",
            }
        )
    )

    assert material["source_origin"] == "internal"
    assert material["source_authority"] == "internal_material"
    assert material["authority_version"] == 1
    assert material["official_use_allowed"] is False


def test_ai_detected_origin_cannot_grant_source_authority_when_governance_origin_is_missing() -> None:
    row = _material_row(
        source_origin="",
        source_authority="",
        understanding_json={
            "source_origin": "internal",
            "authority_level": "claimed_official",
        },
    )

    material = _material_from_row(row)

    assert material["source_origin"] == "unknown"
    assert material["source_authority"] == "external_reference"


def test_chunk_inherits_parent_source_authority_and_source_identity() -> None:
    chunk = _material_chunk_from_row(
        {
            "chunk_id": str(uuid4()),
            "material_id": MATERIAL_ID,
            "original_file_name": "员工培训资料.md",
            "heading": "接待原则",
            "content": "先确认顾客状态，再介绍服务。",
            "domain": "operations",
            "source_origin": "internal",
            "source_authority": "official_internal",
            "authority_version": 3,
            "score": 80,
        }
    )

    assert chunk["source_id"] == MATERIAL_ID
    assert chunk["source_origin"] == "internal"
    assert chunk["origin"] == "internal"
    assert chunk["source_authority"] == "official_internal"
    assert chunk["authority_source"] == "official_internal"
    assert chunk["authority_version"] == 3
    assert chunk["status"] == "active"
    assert chunk["stage"] == "official"


def test_internal_material_chunk_remains_working_authority() -> None:
    chunk = _material_chunk_from_row(
        {
            "chunk_id": str(uuid4()),
            "material_id": MATERIAL_ID,
            "original_file_name": "首店工作资料.md",
            "content": "这是尚未核定为正式口径的内部工作资料。",
            "source_origin": "internal",
            "source_authority": "internal_material",
            "authority_version": 1,
        }
    )

    assert chunk["stage"] == "working_context"
    assert evidence_authority_source(chunk) == "internal_material"


def test_external_chunk_cannot_expose_forged_internal_authority() -> None:
    chunk = _material_chunk_from_row(
        {
            "chunk_id": str(uuid4()),
            "material_id": MATERIAL_ID,
            "original_file_name": "外部文章.md",
            "content": "外部参考观点。",
            "source_origin": "external",
            "source_authority": "official_internal",
            "authority_version": 2,
        }
    )

    assert chunk["source_authority"] == "external_reference"
    assert chunk["authority_source"] == "external_reference"
    assert chunk["stage"] == "reference"
    assert chunk["status"] == "reference"


def test_public_material_cannot_expose_forged_internal_authority() -> None:
    material = _public_material(
        {
            "id": MATERIAL_ID,
            "file_name": "外部文章.md",
            "extension": ".md",
            "media_type": "text/markdown",
            "size_bytes": 128,
            "status": "ready",
            "understanding": {},
            "source_origin": "external",
            "source_authority": "official_internal",
            "authority_version": 2,
            "created_at": NOW,
            "updated_at": NOW,
        }
    )

    assert material["source_origin"] == "external"
    assert material["source_authority"] == "external_reference"


def test_source_authority_contract_cannot_create_answer_card_authority() -> None:
    with pytest.raises(ValidationError):
        SourceAuthorityUpdate(
            source_origin="internal",
            source_authority="approved_answer_card",
            reason="试图绕过答案卡批准流程",
        )


class _Result:
    def __init__(self, row: dict[str, Any] | None = None) -> None:
        self.row = row

    def fetchone(self) -> dict[str, Any] | None:
        return self.row


class _AuthorityConnection:
    def __init__(self, *, role: str = "founder", source_exists: bool = True) -> None:
        self.role = role
        self.source_exists = source_exists
        self.statements: list[tuple[str, tuple[Any, ...]]] = []

    def __enter__(self) -> "_AuthorityConnection":
        return self

    def __exit__(self, *_args: Any) -> None:
        return None

    def execute(self, sql: str, params: tuple[Any, ...]) -> _Result:
        normalized = " ".join(sql.split())
        self.statements.append((normalized, params))
        if "FOR UPDATE OF material" in normalized:
            if not self.source_exists:
                return _Result(None)
            return _Result(
                {
                    **_material_row(),
                    "actor_role": self.role,
                }
            )
        if "INSERT INTO hxy_material_authority_events" in normalized:
            return _Result({"event_id": str(uuid4())})
        if "UPDATE hxy_product_materials" in normalized:
            return _Result(
                _material_row(
                    source_origin=params[0],
                    source_authority=params[1],
                    authority_version=2,
                )
            )
        raise AssertionError(normalized)


def test_founder_can_version_an_existing_internal_source_as_official() -> None:
    repository = MaterialRepository("postgresql://authority.test/hxy")
    connection = _AuthorityConnection(role="founder")
    repository.connect = lambda: connection

    result = repository.update_source_authority(
        ASSIGNMENT_ID,
        MATERIAL_ID,
        source_origin="internal",
        source_authority="official_internal",
        reason="创始人确认这是当前首店内部标准",
    )

    assert result is not None
    assert result["source_authority"] == "official_internal"
    assert result["authority_version"] == 2
    assert any("INSERT INTO hxy_material_authority_events" in sql for sql, _ in connection.statements)
    event_sql, event_params = next(
        item for item in connection.statements if "INSERT INTO hxy_material_authority_events" in item[0]
    )
    assert "previous_authority" in event_sql
    assert "new_authority" in event_sql
    assert "version_no" in event_sql
    assert "internal_material" in event_params
    assert "official_internal" in event_params


def test_store_role_cannot_mark_a_source_official() -> None:
    repository = MaterialRepository("postgresql://authority.test/hxy")
    connection = _AuthorityConnection(role="store_manager")
    repository.connect = lambda: connection

    with pytest.raises(PermissionError, match="source authority"):
        repository.update_source_authority(
            ASSIGNMENT_ID,
            MATERIAL_ID,
            source_origin="internal",
            source_authority="official_internal",
            reason="门店自行声明正式口径",
        )

    assert not any("authority_events" in sql for sql, _ in connection.statements)
    assert not any("UPDATE hxy_product_materials" in sql for sql, _ in connection.statements)


def test_missing_source_cannot_receive_authority() -> None:
    repository = MaterialRepository("postgresql://authority.test/hxy")
    connection = _AuthorityConnection(source_exists=False)
    repository.connect = lambda: connection

    result = repository.update_source_authority(
        ASSIGNMENT_ID,
        MATERIAL_ID,
        source_origin="internal",
        source_authority="internal_material",
        reason="补全来源分类",
    )

    assert result is None
    assert len(connection.statements) == 1


def test_source_authority_migration_is_additive_versioned_and_append_only() -> None:
    migration = (
        Path(__file__).parents[1] / "data" / "migrations" / "018_hxy_source_authority.sql"
    ).read_text(encoding="utf-8")

    assert "ADD COLUMN IF NOT EXISTS source_origin" in migration
    assert "ADD COLUMN IF NOT EXISTS source_authority" in migration
    assert "ADD COLUMN IF NOT EXISTS authority_version" in migration
    assert "CREATE TABLE IF NOT EXISTS hxy_material_authority_events" in migration
    assert "hxy_validate_material_authority_event" in migration
    assert "actor_record.role NOT IN ('founder', 'hq_operations')" in migration
    assert "actor_record.organization_id <> material_record.organization_id" in migration
    assert "hxy_enforce_material_authority_version" in migration
    assert "previous_authority" in migration
    assert "new_authority" in migration
    assert "version_no" in migration
    assert "BEFORE UPDATE OR DELETE" in migration
    assert "BEFORE TRUNCATE" in migration
    assert "material_id UUID NOT NULL REFERENCES hxy_product_materials(material_id) ON DELETE RESTRICT" in migration
    assert "CREATE TRIGGER trg_hxy_product_materials_authority_version_guard" in migration
    assert "NEW.authority_version <> OLD.authority_version + 1" in migration
    assert "previous_authority = OLD.source_authority" in migration
    assert "new_authority = NEW.source_authority" in migration
    assert "source_origin = 'internal' OR source_authority = 'external_reference'" in migration
    assert "approved_answer_card" not in migration
