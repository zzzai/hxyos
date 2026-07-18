from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "data" / "migrations" / "020_hxy_data_catalog.sql"


def migration_sql() -> str:
    assert MIGRATION.exists(), "missing 020_hxy_data_catalog.sql"
    return MIGRATION.read_text(encoding="utf-8")


def normalized_sql() -> str:
    return " ".join(migration_sql().split())


def test_data_catalog_separates_assets_datasets_facts_metrics_and_lineage() -> None:
    sql = migration_sql()
    normalized = normalized_sql()

    for table in (
        "hxy_legal_entities",
        "hxy_operating_mode_catalog",
        "hxy_governance_profiles",
        "hxy_store_operating_relationships",
        "hxy_data_sources",
        "hxy_data_connectors",
        "hxy_dataset_snapshots",
        "hxy_business_facts",
        "hxy_metric_definitions",
        "hxy_asset_bindings",
    ):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in normalized

    assert "ALTER TABLE hxy_product_materials" in normalized
    assert "ADD COLUMN IF NOT EXISTS organization_id" in normalized
    assert "ADD COLUMN IF NOT EXISTS store_id" in normalized
    assert "CREATE TABLE IF NOT EXISTS hxy_source_assets" not in normalized
    assert "htops" not in sql.lower()


def test_catalog_keeps_relationships_snapshots_and_metrics_versioned() -> None:
    sql = migration_sql()
    normalized = normalized_sql()

    for phrase in (
        "relationship_version",
        "profile_version",
        "schema_version",
        "normalization_version",
        "metric_key",
        "metric_version",
        "calculation_kind",
        "calculation_ref",
        "configuration_ref",
    ):
        assert phrase in normalized

    assert "api_key" not in sql.lower()
    assert "DROP TABLE" not in sql.upper()
    assert "DELETE FROM" not in sql.upper()


def test_active_store_relationship_periods_cannot_overlap() -> None:
    normalized = normalized_sql().lower()

    assert "create extension if not exists btree_gist" in normalized
    assert "exclude using gist" in normalized
    assert "tstzrange" in normalized
    assert "where (status = 'active')" in normalized


def test_data_catalog_history_is_guarded_from_in_place_mutation() -> None:
    normalized = normalized_sql()

    for table in (
        "hxy_dataset_snapshots",
        "hxy_business_facts",
        "hxy_asset_bindings",
    ):
        assert f"ON {table}" in normalized

    assert "hxy_reject_data_catalog_mutation" in normalized
    assert "BEFORE UPDATE OR DELETE" in normalized
    assert "BEFORE TRUNCATE" in normalized


def test_metric_definitions_only_allow_governed_calculators() -> None:
    normalized = normalized_sql()

    assert "calculation_kind IN ('dsl', 'implementation_ref')" in normalized
    assert "calculation_kind = 'dsl'" in normalized
    assert "calculation_kind = 'implementation_ref'" in normalized
    assert "formula_dsl" in normalized
    assert "calculation_ref" in normalized


def test_existing_materials_are_backfilled_to_organization_scope() -> None:
    normalized = normalized_sql()

    assert "UPDATE hxy_product_materials AS material" in normalized
    assert "FROM hxy_role_assignments AS assignment" in normalized
    assert "material.assignment_id = assignment.assignment_id" in normalized
    assert "ALTER COLUMN organization_id SET NOT NULL" in normalized
    assert "FOREIGN KEY (organization_id, store_id)" in normalized


def test_draft_catalog_delete_returns_old_row_in_trigger() -> None:
    normalized = normalized_sql()

    assert "IF TG_OP = 'DELETE' THEN RETURN OLD;" in normalized
