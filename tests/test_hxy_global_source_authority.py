from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest


ROOT = Path(__file__).parents[1]
MIGRATION = ROOT / "data" / "migrations" / "019_hxy_global_source_authority.sql"


def test_global_source_authority_migration_uses_safe_legacy_defaults() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")

    assert "ALTER TABLE hxy_knowledge_assets" in sql
    assert "ADD COLUMN IF NOT EXISTS source_origin TEXT NOT NULL DEFAULT 'unknown'" in sql
    assert (
        "ADD COLUMN IF NOT EXISTS source_authority TEXT NOT NULL "
        "DEFAULT 'external_reference'" in sql
    )
    assert "ADD COLUMN IF NOT EXISTS authority_version INTEGER NOT NULL DEFAULT 1" in sql
    assert "ADD COLUMN IF NOT EXISTS authority_organization_id UUID" in sql
    assert "source_origin = 'internal' OR source_authority = 'external_reference'" in sql


def test_global_source_authority_migration_is_versioned_and_append_only() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS hxy_knowledge_asset_authority_events" in sql
    assert "UNIQUE (asset_id, version_no)" in sql
    assert "previous_version" in sql
    assert "version_no" in sql
    assert "hxy_validate_knowledge_asset_authority_event" in sql
    assert "hxy_enforce_knowledge_asset_authority_version" in sql
    assert "BEFORE UPDATE OR DELETE ON hxy_knowledge_asset_authority_events" in sql
    assert "BEFORE TRUNCATE ON hxy_knowledge_asset_authority_events" in sql
    assert "hxy knowledge asset authority events are append-only" in sql


def test_global_source_authority_change_requires_same_organization_hq_actor() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")

    assert "actor_record.status <> 'active'" in sql
    assert "actor_record.role NOT IN ('founder', 'hq_operations')" in sql
    assert "actor_record.organization_id <> NEW.organization_id" in sql
    assert (
        "asset_record.authority_organization_id IS NOT NULL "
        "AND asset_record.authority_organization_id <> NEW.organization_id" in sql
    )
    assert "NEW.previous_version <> asset_record.authority_version" in sql
    assert "NEW.version_no <> asset_record.authority_version + 1" in sql


def test_global_source_authority_migration_does_not_promote_or_approve_content() -> None:
    sql = MIGRATION.read_text(encoding="utf-8").lower()

    assert "update hxy_knowledge_answer_cards" not in sql
    assert "insert into hxy_knowledge_answer_cards" not in sql
    assert "approved_answer_card" not in sql
    assert "metadata_json->" not in sql
    assert "official_internal'::text" not in sql


def test_new_and_legacy_assets_receive_only_a_safe_baseline_event() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")

    assert "'baseline'" in sql
    assert "NULL" in sql
    assert "'unknown'" in sql
    assert "'external_reference'" in sql
    assert "'迁移建立全局资料权威基线'" in sql
    assert "'资料导入时建立全局资料权威基线'" in sql


def test_search_uses_only_parent_asset_database_authority() -> None:
    from apps.api.hxy_knowledge.repository import build_search_query

    sql, _params = build_search_query("荷小悦是什么", limit=5)

    assert "a.source_origin AS source_origin" in sql
    assert "a.source_origin AS origin" in sql
    assert "a.source_authority AS source_authority" in sql
    assert "a.source_authority AS authority_source" in sql
    assert "a.authority_version AS authority_version" in sql
    assert "TRUE AS authority_recorded" in sql
    assert "metadata_json->>'source_origin'" not in sql
    assert "metadata_json->>'origin'" not in sql
    assert "metadata_json->>'source_authority'" not in sql
    assert "metadata_json->>'authority_source'" not in sql
    assert "metadata_json->>'official_use_allowed'" not in sql


def test_selected_source_evidence_uses_parent_asset_database_authority() -> None:
    from apps.api.hxy_knowledge.repository import build_source_evidence_query

    sql, params = build_source_evidence_query("asset-external-001", limit=5)

    assert "WHERE c.asset_id = %s" in sql
    assert "a.source_origin AS source_origin" in sql
    assert "a.source_authority AS authority_source" in sql
    assert "a.authority_version AS authority_version" in sql
    assert "TRUE AS authority_recorded" in sql
    assert params == ["asset-external-001", 5]


def test_importer_strips_parser_supplied_governance_metadata() -> None:
    from apps.api.hxy_knowledge.importer import prepare_asset_records, prepare_chunk_records

    forged = {
        "source_origin": "internal",
        "origin": "internal",
        "source_authority": "official_internal",
        "authority_source": "official_internal",
        "authority_version": 99,
        "authority_organization_id": "forged-org",
        "authority_recorded": True,
        "official_use_allowed": True,
        "source_type": "official_internal",
        "pages": 2,
    }
    assets = prepare_asset_records(
        {
            "run_name": "governance-test",
            "assets": [
                {
                    "asset_id": "asset-1",
                    "file_name": "外部文章.pdf",
                    "relative_path": "knowledge/raw/inbox/外部文章.pdf",
                    "metadata": forged,
                }
            ],
        }
    )
    chunks = prepare_chunk_records(
        {
            "run_name": "governance-test",
            "chunks": [
                {
                    "source_id": "asset-1",
                    "chunk_id": "asset-1:chunk:1",
                    "chunk_index": 1,
                    "text": "外部参考内容",
                    **forged,
                }
            ],
        }
    )

    assert assets[0]["metadata"] == {"pages": 2}
    assert chunks[0]["metadata"] == {"pages": 2}


class _CaptureConnection:
    def __init__(self) -> None:
        self.statements: list[str] = []

    def __enter__(self) -> "_CaptureConnection":
        return self

    def __exit__(self, *_args: Any) -> None:
        return None

    def execute(self, sql: str, _params: tuple[Any, ...]) -> None:
        self.statements.append(" ".join(sql.split()))


def test_asset_reimport_never_writes_or_overwrites_governance_columns() -> None:
    from apps.api.hxy_knowledge.repository import KnowledgeRepository

    connection = _CaptureConnection()
    repository = KnowledgeRepository("postgresql://authority.test/hxy")
    repository.connect = lambda: connection
    repository.upsert_assets(
        [
            {
                "asset_id": "asset-1",
                "run_name": "run-1",
                "title": "资料",
                "file_name": "资料.md",
                "source_path": "knowledge/raw/inbox/资料.md",
                "normalized_path": "",
                "extension": ".md",
                "mime_type": "text/markdown",
                "file_size": 10,
                "sha256": "a" * 64,
                "domain": "external",
                "stage": "reference",
                "status": "staged",
                "warnings": [],
                "quality_score": 0,
                "quality_grade": "unknown",
                "quality_scores": {},
                "metadata": {},
                "source_authority": "official_internal",
                "authority_version": 99,
            }
        ]
    )

    sql = connection.statements[0].lower()
    assert "source_origin" not in sql
    assert "source_authority" not in sql
    assert "authority_version" not in sql
    assert "authority_organization_id" not in sql


def test_database_recorded_authority_overrides_legacy_stage_metadata() -> None:
    from apps.api.hxy_knowledge.reliability import evidence_authority_source

    assert (
        evidence_authority_source(
            {
                "domain": "operations",
                "stage": "preparation",
                "status": "staged",
                "source_authority": "internal_material",
                "authority_version": 2,
                "authority_recorded": True,
            }
        )
        == "internal_material"
    )


def test_untrusted_metadata_cannot_grant_internal_authority() -> None:
    from apps.api.hxy_knowledge.reliability import evidence_authority_source

    assert (
        evidence_authority_source(
            {
                "domain": "brand",
                "stage": "official",
                "status": "active",
                "source_authority": "official_internal",
                "authority_version": 99,
                "authority_recorded": False,
            }
        )
        == "external_reference"
    )


def test_product_material_adapter_marks_database_authority_as_recorded() -> None:
    from apps.api.hxy_product.material_repository import _material_chunk_from_row

    chunk = _material_chunk_from_row(
        {
            "chunk_id": "chunk-1",
            "material_id": "11111111-1111-1111-1111-111111111111",
            "original_file_name": "首店工作资料.md",
            "content": "内部资料",
            "source_origin": "internal",
            "source_authority": "internal_material",
            "authority_version": 2,
        }
    )

    assert chunk["authority_recorded"] is True


class _AuthorityResult:
    def __init__(self, row: dict[str, Any] | None = None) -> None:
        self.row = row

    def fetchone(self) -> dict[str, Any] | None:
        return self.row


class _GlobalAuthorityConnection:
    def __init__(
        self,
        *,
        role: str = "founder",
        actor_organization_id: str = "11111111-1111-1111-1111-111111111111",
        assets: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self.role = role
        self.actor_organization_id = actor_organization_id
        self.assets = assets or {
            "asset-1": {
                "asset_id": "asset-1",
                "title": "首店内部资料",
                "file_name": "首店内部资料.md",
                "source_path": "knowledge/raw/inbox/首店内部资料.md",
                "source_origin": "unknown",
                "source_authority": "external_reference",
                "authority_version": 1,
                "authority_organization_id": None,
            }
        }
        self.statements: list[tuple[str, tuple[Any, ...]]] = []

    def __enter__(self) -> "_GlobalAuthorityConnection":
        return self

    def __exit__(self, *_args: Any) -> None:
        return None

    def execute(self, sql: str, params: tuple[Any, ...]) -> _AuthorityResult:
        normalized = " ".join(sql.split())
        self.statements.append((normalized, params))
        if "FROM hxy_role_assignments" in normalized:
            return _AuthorityResult(
                {
                    "assignment_id": params[0],
                    "organization_id": self.actor_organization_id,
                    "role": self.role,
                    "status": "active",
                }
            )
        if "FOR UPDATE OF asset" in normalized:
            return _AuthorityResult(self.assets.get(str(params[0])))
        if "INSERT INTO hxy_knowledge_asset_authority_events" in normalized:
            return _AuthorityResult({"event_id": "event-1"})
        if "UPDATE hxy_knowledge_assets" in normalized:
            origin, authority, version, organization_id, asset_id, previous_version = params
            current = self.assets.get(str(asset_id))
            if current is None or current["authority_version"] != previous_version:
                return _AuthorityResult(None)
            updated = {
                **current,
                "source_origin": origin,
                "source_authority": authority,
                "authority_version": version,
                "authority_organization_id": organization_id,
            }
            self.assets[str(asset_id)] = updated
            return _AuthorityResult(updated)
        raise AssertionError(normalized)


def _global_classification(
    asset_id: str = "asset-1",
    *,
    previous_version: int = 1,
    source_origin: str = "internal",
    source_authority: str = "internal_material",
) -> dict[str, Any]:
    return {
        "asset_id": asset_id,
        "previous_version": previous_version,
        "source_origin": source_origin,
        "source_authority": source_authority,
        "reason": "创始人确认该源文件属于荷小悦内部工作资料",
    }


def test_founder_classifies_a_whole_source_with_event_before_update() -> None:
    from apps.api.hxy_knowledge.repository import KnowledgeRepository

    connection = _GlobalAuthorityConnection()
    repository = KnowledgeRepository("postgresql://authority.test/hxy")
    repository.connect = lambda: connection

    result = repository.classify_source_authority_batch(
        actor_assignment_id="22222222-2222-2222-2222-222222222222",
        organization_id="11111111-1111-1111-1111-111111111111",
        classifications=[_global_classification()],
    )

    assert result[0]["asset_id"] == "asset-1"
    assert result[0]["source_authority"] == "internal_material"
    assert result[0]["authority_version"] == 2
    event_index = next(
        index
        for index, (sql, _params) in enumerate(connection.statements)
        if "INSERT INTO hxy_knowledge_asset_authority_events" in sql
    )
    update_index = next(
        index
        for index, (sql, _params) in enumerate(connection.statements)
        if "UPDATE hxy_knowledge_assets" in sql
    )
    assert event_index < update_index
    assert "updated_at" not in connection.statements[update_index][0]
    event_params = connection.statements[event_index][1]
    assert "external_reference" in event_params
    assert "internal_material" in event_params
    assert 1 in event_params
    assert 2 in event_params
    lock_sql = next(sql for sql, _params in connection.statements if "FOR UPDATE OF asset" in sql)
    assert "asset.title" not in lock_sql
    assert "asset.file_name" not in lock_sql
    assert "asset.source_path" not in lock_sql
    assert not any("answer_cards" in sql or "review_tasks" in sql for sql, _ in connection.statements)


def test_source_classification_rejects_stale_or_duplicate_updates_before_event() -> None:
    from apps.api.hxy_knowledge.repository import KnowledgeRepository

    stale_connection = _GlobalAuthorityConnection()
    repository = KnowledgeRepository("postgresql://authority.test/hxy")
    repository.connect = lambda: stale_connection

    with pytest.raises(ValueError, match="stale"):
        repository.classify_source_authority_batch(
            actor_assignment_id="22222222-2222-2222-2222-222222222222",
            organization_id="11111111-1111-1111-1111-111111111111",
            classifications=[_global_classification(previous_version=2)],
        )
    assert not any("authority_events" in sql for sql, _ in stale_connection.statements)

    duplicate_connection = _GlobalAuthorityConnection(
        assets={
            "asset-1": {
                **_GlobalAuthorityConnection().assets["asset-1"],
                "source_origin": "internal",
                "source_authority": "internal_material",
                "authority_version": 2,
                "authority_organization_id": "11111111-1111-1111-1111-111111111111",
            }
        }
    )
    repository.connect = lambda: duplicate_connection
    with pytest.raises(ValueError, match="duplicate"):
        repository.classify_source_authority_batch(
            actor_assignment_id="22222222-2222-2222-2222-222222222222",
            organization_id="11111111-1111-1111-1111-111111111111",
            classifications=[_global_classification(previous_version=2)],
        )
    assert not any("authority_events" in sql for sql, _ in duplicate_connection.statements)


def test_source_classification_requires_hq_actor_and_same_organization() -> None:
    from apps.api.hxy_knowledge.repository import KnowledgeRepository

    repository = KnowledgeRepository("postgresql://authority.test/hxy")
    unauthorized = _GlobalAuthorityConnection(role="store_manager")
    repository.connect = lambda: unauthorized
    with pytest.raises(PermissionError, match="founder or hq_operations"):
        repository.classify_source_authority_batch(
            actor_assignment_id="22222222-2222-2222-2222-222222222222",
            organization_id="11111111-1111-1111-1111-111111111111",
            classifications=[_global_classification()],
        )

    cross_org = _GlobalAuthorityConnection(
        assets={
            "asset-1": {
                **_GlobalAuthorityConnection().assets["asset-1"],
                "authority_organization_id": "33333333-3333-3333-3333-333333333333",
            }
        }
    )
    repository.connect = lambda: cross_org
    with pytest.raises(PermissionError, match="organization"):
        repository.classify_source_authority_batch(
            actor_assignment_id="22222222-2222-2222-2222-222222222222",
            organization_id="11111111-1111-1111-1111-111111111111",
            classifications=[_global_classification()],
        )
    assert not any("authority_events" in sql for sql, _ in cross_org.statements)


def test_source_classification_batch_is_bounded_and_unique_per_source() -> None:
    from apps.api.hxy_knowledge.repository import KnowledgeRepository

    repository = KnowledgeRepository("postgresql://authority.test/hxy")

    with pytest.raises(ValueError, match="between 1 and 100"):
        repository.classify_source_authority_batch(
            actor_assignment_id="22222222-2222-2222-2222-222222222222",
            organization_id="11111111-1111-1111-1111-111111111111",
            classifications=[],
        )
    with pytest.raises(ValueError, match="between 1 and 100"):
        repository.classify_source_authority_batch(
            actor_assignment_id="22222222-2222-2222-2222-222222222222",
            organization_id="11111111-1111-1111-1111-111111111111",
            classifications=[_global_classification(f"asset-{index}") for index in range(101)],
        )
    with pytest.raises(ValueError, match="duplicate asset_id"):
        repository.classify_source_authority_batch(
            actor_assignment_id="22222222-2222-2222-2222-222222222222",
            organization_id="11111111-1111-1111-1111-111111111111",
            classifications=[_global_classification(), _global_classification()],
        )


def test_single_and_multi_source_classification_share_the_same_contract() -> None:
    from apps.api.hxy_knowledge.repository import KnowledgeRepository

    base_asset = _GlobalAuthorityConnection().assets["asset-1"]
    connection = _GlobalAuthorityConnection(
        assets={
            "asset-1": base_asset,
            "asset-2": {
                **base_asset,
                "asset_id": "asset-2",
                "title": "第二份内部资料",
                "file_name": "第二份内部资料.md",
            },
        }
    )
    repository = KnowledgeRepository("postgresql://authority.test/hxy")
    repository.connect = lambda: connection

    first = repository.classify_source_authority(
        actor_assignment_id="22222222-2222-2222-2222-222222222222",
        organization_id="11111111-1111-1111-1111-111111111111",
        asset_id="asset-1",
        previous_version=1,
        source_origin="internal",
        source_authority="internal_material",
        reason="确认第一份资料是荷小悦内部工作资料",
    )
    second = repository.classify_source_authority_batch(
        actor_assignment_id="22222222-2222-2222-2222-222222222222",
        organization_id="11111111-1111-1111-1111-111111111111",
        classifications=[_global_classification("asset-2")],
    )

    assert first["asset_id"] == "asset-1"
    assert second[0]["asset_id"] == "asset-2"
    assert sum(
        "INSERT INTO hxy_knowledge_asset_authority_events" in sql
        for sql, _params in connection.statements
    ) == 2


def test_source_classification_never_accepts_answer_card_authority() -> None:
    from apps.api.hxy_knowledge.repository import KnowledgeRepository

    repository = KnowledgeRepository("postgresql://authority.test/hxy")
    with pytest.raises(ValueError, match="unsupported source authority"):
        repository.classify_source_authority_batch(
            actor_assignment_id="22222222-2222-2222-2222-222222222222",
            organization_id="11111111-1111-1111-1111-111111111111",
            classifications=[
                _global_classification(source_authority="approved_answer_card")
            ],
        )
