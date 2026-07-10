from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "data" / "migrations" / "013_hxy_material_intake_jobs.sql"


def test_material_intake_migration_creates_durable_queue_and_artifacts() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    normalized = " ".join(sql.split())

    assert "CREATE TABLE IF NOT EXISTS hxy_material_parser_jobs" in sql
    assert "CREATE TABLE IF NOT EXISTS hxy_material_job_attempts" in sql
    assert "CREATE TABLE IF NOT EXISTS hxy_material_artifacts" in sql
    assert "status IN ('queued', 'running', 'retryable_failed', 'succeeded', 'permanent_failed')" in normalized
    assert "FOREIGN KEY (assignment_id, material_id)" in normalized
    assert "REFERENCES hxy_product_materials(assignment_id, material_id)" in normalized
    assert "CHECK ((status = 'running') = (lease_owner IS NOT NULL AND lease_expires_at IS NOT NULL))" in normalized
    assert "attempt_count <= max_attempts" in normalized
    assert "artifact_type IN ('normalized_markdown', 'source_card')" in normalized
    assert "official_use_allowed BOOLEAN NOT NULL DEFAULT FALSE" in normalized
    assert "CHECK (official_use_allowed = FALSE)" in normalized
    assert "FOR UPDATE" not in sql.upper()


def test_material_intake_migration_adds_product_states_and_claim_indexes() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    normalized = " ".join(sql.split())

    for status in ("processing", "ready", "needs_attention"):
        assert f"'{status}'" in normalized
    assert "idx_hxy_material_parser_jobs_claim" in sql
    assert "idx_hxy_material_parser_jobs_stale_lease" in sql
    assert "idx_hxy_material_artifacts_material" in sql
    assert "INSERT INTO" not in sql.upper()
