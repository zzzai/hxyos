from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "data" / "migrations" / "023_hxy_material_safety_scan.sql"


def test_material_safety_migration_adds_staged_jobs_and_scan_audit() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    normalized = " ".join(sql.split())

    assert "job_type" in sql
    assert "job_type IN ('scan', 'parse')" in normalized
    assert "UNIQUE (material_id, job_type)" in normalized
    assert "CREATE TABLE IF NOT EXISTS hxy_material_scan_results" in normalized
    assert "result_status IN ('clean', 'blocked')" in normalized
    assert "source_sha256 CHAR(64) NOT NULL" in normalized
    assert "source_size_bytes BIGINT NOT NULL" in normalized
    assert "ALTER TABLE hxy_material_job_attempts" in normalized
    assert "hxy_material_job_attempts_source_identity_check" in normalized
    assert "source_sha256 IS NOT NULL" in normalized
    assert "source_size_bytes IS NOT NULL" in normalized
    assert "UNIQUE (job_id, attempt_number)" in normalized
    assert (
        "job_id UUID NOT NULL REFERENCES hxy_material_parser_jobs(job_id) ON DELETE CASCADE"
        in normalized
    )
    assert (
        "REFERENCES hxy_product_materials(assignment_id, material_id) ON DELETE CASCADE"
        in normalized
    )
    assert "object_key" not in sql
    assert "storage_key" not in sql


def test_material_safety_migration_backfills_scan_jobs_without_deleting_history() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    normalized = " ".join(sql.split())

    assert "INSERT INTO hxy_material_parser_jobs" in normalized
    assert "'scan'" in normalized
    assert "'clamav'" in normalized
    assert "WHERE scan_status = 'legacy_unscanned'" in normalized
    assert "scan_status = 'pending'" in normalized
    assert "DELETE FROM hxy_material" not in normalized


def test_material_safety_migration_adds_immutable_requeue_audit() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    normalized = " ".join(sql.split())

    assert "CREATE TABLE IF NOT EXISTS hxy_material_job_requeue_events" in normalized
    for column in (
        "actor_assignment_id",
        "job_id",
        "from_status",
        "target_job_type",
        "reason",
    ):
        assert column in normalized
    assert "trg_hxy_material_requeue_events_append_only" in normalized
    assert "trg_hxy_material_requeue_events_no_truncate" in normalized
    assert "hxy_reject_operating_history_mutation()" in normalized
