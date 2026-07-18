from __future__ import annotations

import importlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "data" / "migrations" / "013_hxy_material_intake_jobs.sql"
ASSIGNMENT_ID = "20000000-0000-0000-0000-000000000001"
ORGANIZATION_ID = "30000000-0000-0000-0000-000000000001"
STORE_ID = "hxy-pilot-store"
MATERIAL_ID = "70000000-0000-0000-0000-000000000001"
JOB_ID = "80000000-0000-0000-0000-000000000001"
ATTEMPT_ID = "90000000-0000-0000-0000-000000000001"
NOW = datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc)


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


def _material_row() -> dict[str, Any]:
    return {
        "material_id": MATERIAL_ID,
        "assignment_id": ASSIGNMENT_ID,
        "organization_id": ORGANIZATION_ID,
        "store_id": STORE_ID,
        "client_upload_id": "60000000-0000-0000-0000-000000000001",
        "original_file_name": "首店资料.docx",
        "extension": ".docx",
        "media_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "size_bytes": 1024,
        "sha256": "a" * 64,
        "storage_key": f"{ASSIGNMENT_ID}/{MATERIAL_ID}/首店资料.docx",
        "note": "首店内部资料",
        "status": "processing",
        "understanding_json": {"domain": "operations"},
        "official_use_allowed": False,
        "created_at": NOW,
        "updated_at": NOW,
    }


def _material_payload() -> dict[str, Any]:
    row = _material_row()
    return {
        "material_id": MATERIAL_ID,
        "assignment_id": ASSIGNMENT_ID,
        "client_upload_id": row["client_upload_id"],
        "file_name": row["original_file_name"],
        "extension": row["extension"],
        "media_type": row["media_type"],
        "size_bytes": row["size_bytes"],
        "sha256": row["sha256"],
        "storage_key": row["storage_key"],
        "note": row["note"],
        "status": "processing",
        "understanding": row["understanding_json"],
        "max_assignment_storage_bytes": 10_000,
    }


class Result:
    def __init__(self, row: dict[str, Any] | None = None, rows=None, rowcount: int = 0):
        self.row = row
        self.rows = rows or []
        self.rowcount = rowcount

    def fetchone(self):
        return self.row

    def fetchall(self):
        return self.rows


def test_create_material_enqueues_scan_job_in_the_same_transaction() -> None:
    module = importlib.import_module("apps.api.hxy_product.material_repository")
    repository = module.MaterialRepository("postgresql://materials.test/hxy")
    calls: list[str] = []

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, sql: str, _params: tuple[Any, ...]):
            normalized = " ".join(sql.split())
            calls.append(normalized)
            if "FOR UPDATE" in normalized and "hxy_role_assignments" in normalized:
                return Result(
                    {
                        "assignment_id": ASSIGNMENT_ID,
                        "organization_id": ORGANIZATION_ID,
                        "store_id": STORE_ID,
                    }
                )
            if "client_upload_id =" in normalized:
                return Result(None)
            if "COALESCE(SUM(size_bytes), 0)" in normalized:
                return Result({"used_bytes": 0})
            if "INSERT INTO hxy_product_materials" in normalized:
                return Result(_material_row())
            if "INSERT INTO hxy_material_parser_jobs" in normalized:
                return Result({"job_id": JOB_ID})
            raise AssertionError(normalized)

    connection = Connection()
    repository.connect = lambda: connection

    material = repository.create_material(_material_payload())

    assert material["id"] == MATERIAL_ID
    material_insert = next(i for i, sql in enumerate(calls) if "INSERT INTO hxy_product_materials" in sql)
    job_insert = next(i for i, sql in enumerate(calls) if "INSERT INTO hxy_material_parser_jobs" in sql)
    assert material_insert < job_insert
    assert calls[job_insert].count("official_use_allowed") == 0
    assert "job_type" in calls[job_insert]
    assert "'scan'" in calls[job_insert]
    assert "'clamav'" in calls[job_insert]
    assert "organization_id" in calls[material_insert]
    assert "store_id" in calls[material_insert]
    assert "scan_status" in calls[material_insert]


def test_claim_next_job_uses_skip_locked_and_opens_an_attempt() -> None:
    module = importlib.import_module("apps.api.hxy_product.material_repository")
    repository = module.MaterialRepository("postgresql://materials.test/hxy")
    calls: list[tuple[str, tuple[Any, ...]]] = []
    claimed_row = {
        **_material_row(),
        "job_id": JOB_ID,
        "parser_strategy": "markitdown",
        "job_type": "parse",
        "scan_status": "clean",
        "job_status": "queued",
        "attempt_count": 0,
        "max_attempts": 3,
    }

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, sql: str, params: tuple[Any, ...]):
            normalized = " ".join(sql.split())
            calls.append((normalized, params))
            if "FOR UPDATE OF job SKIP LOCKED" in normalized:
                return Result(claimed_row)
            if "UPDATE hxy_material_parser_jobs" in normalized:
                return Result({**claimed_row, "job_status": "running", "attempt_count": 1})
            if "INSERT INTO hxy_material_job_attempts" in normalized:
                return Result({"attempt_id": ATTEMPT_ID})
            raise AssertionError(normalized)

    repository.connect = lambda: Connection()

    job = repository.claim_next_job("worker-a", lease_seconds=90)

    assert job is not None
    assert job["job_id"] == JOB_ID
    assert job["attempt_id"] == ATTEMPT_ID
    assert job["attempt_number"] == 1
    assert any("SKIP LOCKED" in sql for sql, _ in calls)
    claim_sql = next(sql for sql, _ in calls if "SKIP LOCKED" in sql)
    assert "material.scan_status = 'clean'" in claim_sql
    assert "material.scan_status = 'pending'" in claim_sql
    assert any(params[0] == "worker-a" for sql, params in calls if "UPDATE hxy_material_parser_jobs" in sql)


def test_complete_clean_scan_records_audit_and_enqueues_parse_job() -> None:
    module = importlib.import_module("apps.api.hxy_product.material_repository")
    repository = module.MaterialRepository("postgresql://materials.test/hxy")
    calls: list[tuple[str, tuple[Any, ...]]] = []
    lease_row = {
        "job_id": JOB_ID,
        "material_id": MATERIAL_ID,
        "assignment_id": ASSIGNMENT_ID,
        "attempt_count": 1,
        "max_attempts": 3,
        "job_type": "scan",
    }

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, sql: str, params: tuple[Any, ...]):
            normalized = " ".join(sql.split())
            calls.append((normalized, params))
            if "FOR UPDATE" in normalized and "lease_owner" in normalized:
                return Result(lease_row)
            if "INSERT INTO hxy_material_scan_results" in normalized:
                return Result({"scan_result_id": str(uuid4())})
            if "UPDATE hxy_material_job_attempts" in normalized:
                return Result(rowcount=1)
            if "UPDATE hxy_material_parser_jobs" in normalized:
                return Result(rowcount=1)
            if "UPDATE hxy_product_materials" in normalized:
                return Result(_material_row() | {"scan_status": "clean"})
            if "INSERT INTO hxy_material_parser_jobs" in normalized:
                return Result({"job_id": str(uuid4())})
            if "UPDATE hxy_outbox_messages" in normalized:
                return Result(rowcount=1)
            raise AssertionError(normalized)

    repository.connect = lambda: Connection()

    material = repository.complete_scan_job(
        JOB_ID,
        "worker-a",
        result_status="clean",
        engine="clamav",
        engine_version="1.4.2",
        signature=None,
        source_sha256="a" * 64,
        source_size_bytes=100,
    )

    assert material["scan_status"] == "clean"
    lock_sql, lock_params = next(
        (sql, params)
        for sql, params in calls
        if "FOR UPDATE OF job, material" in sql
    )
    assert "material.sha256 = %s" in lock_sql
    assert "material.size_bytes = %s" in lock_sql
    assert lock_params == (JOB_ID, "worker-a", "a" * 64, 100)
    scan_insert = next(
        sql for sql, _ in calls if "INSERT INTO hxy_material_scan_results" in sql
    )
    assert "source_sha256" in scan_insert
    assert "source_size_bytes" in scan_insert
    material_update = next(
        sql for sql, _ in calls if "UPDATE hxy_product_materials" in sql
    )
    assert "sha256 = %s" in material_update
    assert "size_bytes = %s" in material_update
    parse_insert = next(
        sql
        for sql, _ in calls
        if "INSERT INTO hxy_material_parser_jobs" in sql
        and "hxy_material_scan_results" not in sql
    )
    assert "'parse'" in parse_insert
    assert "'markitdown'" in parse_insert
    release_sql = next(
        sql for sql, _ in calls if "UPDATE hxy_outbox_messages" in sql
    )
    assert "available_at = NOW()" in release_sql
    assert "NOT EXISTS" in release_sql
    assert any(
        "UPDATE hxy_inbound_envelopes" in sql and "status = 'queued'" in sql
        for sql, _ in calls
    )


def test_clean_scan_preserves_an_existing_succeeded_parse_job() -> None:
    module = importlib.import_module("apps.api.hxy_product.material_repository")
    repository = module.MaterialRepository("postgresql://materials.test/hxy")
    calls: list[str] = []
    lease_row = {
        "job_id": JOB_ID,
        "material_id": MATERIAL_ID,
        "assignment_id": ASSIGNMENT_ID,
        "attempt_count": 1,
        "max_attempts": 3,
        "job_type": "scan",
    }

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, sql: str, _params: tuple[Any, ...]):
            normalized = " ".join(sql.split())
            calls.append(normalized)
            if "FOR UPDATE" in normalized and "lease_owner" in normalized:
                return Result(lease_row)
            if "INSERT INTO hxy_material_scan_results" in normalized:
                return Result({"scan_result_id": str(uuid4())})
            if "UPDATE hxy_material_job_attempts" in normalized:
                return Result(rowcount=1)
            if "UPDATE hxy_material_parser_jobs" in normalized:
                return Result(rowcount=1)
            if "UPDATE hxy_product_materials" in normalized:
                return Result(
                    _material_row()
                    | {"status": "ready", "scan_status": "clean"}
                )
            if "INSERT INTO hxy_material_parser_jobs" in normalized:
                return Result({"job_id": str(uuid4()), "status": "succeeded"})
            if "UPDATE hxy_outbox_messages" in normalized:
                return Result(rowcount=1)
            raise AssertionError(normalized)

    repository.connect = lambda: Connection()

    material = repository.complete_scan_job(
        JOB_ID,
        "worker-a",
        result_status="clean",
        engine="clamav",
        engine_version="1.4.2",
        signature=None,
        source_sha256="a" * 64,
        source_size_bytes=100,
    )

    assert material["status"] == "ready"
    material_update = next(
        sql for sql in calls if "UPDATE hxy_product_materials" in sql
    )
    assert "EXISTS" in material_update
    assert "parse_job.job_type = 'parse'" in material_update
    assert "parse_job.status = 'succeeded'" in material_update
    parse_upsert = next(
        sql
        for sql in calls
        if "INSERT INTO hxy_material_parser_jobs" in sql
        and "hxy_material_scan_results" not in sql
    )
    assert "WHEN hxy_material_parser_jobs.status = 'succeeded'" in parse_upsert


def test_material_search_requires_a_clean_safety_scan() -> None:
    module = importlib.import_module("apps.api.hxy_product.material_repository")
    repository = module.MaterialRepository("postgresql://materials.test/hxy")
    calls: list[str] = []

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, sql: str, _params: tuple[Any, ...]):
            calls.append(" ".join(sql.split()))
            return Result(rows=[])

    repository.connect = lambda: Connection()

    assert repository.search_material_chunks(ASSIGNMENT_ID, "首店接待") == []
    assert "material.scan_status = 'clean'" in calls[0]


def test_permanent_scan_failure_marks_material_failed() -> None:
    module = importlib.import_module("apps.api.hxy_product.material_repository")
    repository = module.MaterialRepository("postgresql://materials.test/hxy")
    calls: list[str] = []
    lease_row = {
        "job_id": JOB_ID,
        "material_id": MATERIAL_ID,
        "assignment_id": ASSIGNMENT_ID,
        "attempt_count": 3,
        "max_attempts": 3,
        "job_type": "scan",
    }

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, sql: str, _params: tuple[Any, ...]):
            normalized = " ".join(sql.split())
            calls.append(normalized)
            if "FOR UPDATE" in normalized and "lease_owner" in normalized:
                return Result(lease_row)
            if "UPDATE hxy_material_job_attempts" in normalized:
                return Result(rowcount=1)
            if "UPDATE hxy_material_parser_jobs" in normalized:
                return Result({"status": "permanent_failed"})
            if "UPDATE hxy_product_materials" in normalized:
                return Result(rowcount=1)
            if "UPDATE hxy_outbox_messages" in normalized:
                return Result(rowcount=1)
            raise AssertionError(normalized)

    repository.connect = lambda: Connection()

    outcome = repository.retry_or_fail_job(
        JOB_ID,
        "worker-a",
        retryable=True,
        error_code="scanner_unavailable",
        error_summary="file safety scanner is unavailable",
        retry_delay_seconds=60,
        parser_name="clamav",
    )

    assert outcome == "permanent_failed"
    material_update = next(sql for sql in calls if "UPDATE hxy_product_materials" in sql)
    assert "scan_status = 'failed'" in material_update
    assert any(
        "UPDATE hxy_inbound_envelopes" in sql and "needs_attention" in sql
        for sql in calls
    )
    assert any(
        "UPDATE hxy_outbox_messages" in sql and "available_at = 'infinity'::timestamptz" in sql
        for sql in calls
    )


def test_complete_job_requires_the_current_lease_owner_and_records_artifacts() -> None:
    module = importlib.import_module("apps.api.hxy_product.material_repository")
    repository = module.MaterialRepository("postgresql://materials.test/hxy")
    calls: list[tuple[str, tuple[Any, ...]]] = []
    lease_row = {
        "job_id": JOB_ID,
        "material_id": MATERIAL_ID,
        "assignment_id": ASSIGNMENT_ID,
        "attempt_count": 1,
    }

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, sql: str, params: tuple[Any, ...]):
            normalized = " ".join(sql.split())
            calls.append((normalized, params))
            if "FOR UPDATE" in normalized and "lease_owner" in normalized:
                return Result(lease_row)
            if "INSERT INTO hxy_material_artifacts" in normalized:
                return Result({"artifact_id": str(uuid4())})
            if "INSERT INTO hxy_material_chunks" in normalized:
                return Result({"chunk_id": str(uuid4())})
            if "UPDATE hxy_material_job_attempts" in normalized:
                return Result(rowcount=1)
            if "UPDATE hxy_material_parser_jobs" in normalized:
                return Result(rowcount=1)
            if "UPDATE hxy_product_materials" in normalized:
                return Result(_material_row() | {"status": "ready"})
            raise AssertionError(normalized)

    repository.connect = lambda: Connection()
    artifacts = [
        {
            "artifact_id": str(uuid4()),
            "artifact_type": "normalized_markdown",
            "storage_key": f"{ASSIGNMENT_ID}/{MATERIAL_ID}/{JOB_ID}/normalized.md",
            "sha256": "b" * 64,
            "size_bytes": 100,
            "metadata": {"parser": "markitdown"},
        },
        {
            "artifact_id": str(uuid4()),
            "artifact_type": "source_card",
            "storage_key": f"{ASSIGNMENT_ID}/{MATERIAL_ID}/{JOB_ID}/source-card.json",
            "sha256": "c" * 64,
            "size_bytes": 200,
            "metadata": {"version": "hxy-source-card.v1"},
        },
    ]
    chunks = [
        {
            "chunk_id": str(uuid4()),
            "artifact_id": artifacts[0]["artifact_id"],
            "chunk_index": 0,
            "heading": "首店接待",
            "content": "先问顾客状态，再介绍服务。",
            "char_count": 14,
            "official_use_allowed": False,
        }
    ]

    material = repository.complete_job(
        JOB_ID,
        "worker-a",
        artifacts=artifacts,
        chunks=chunks,
        understanding={"summary": "已完成深度理解。"},
        parser_name="markitdown",
        parser_version="0.1.6",
        source_sha256="a" * 64,
        source_size_bytes=100,
    )

    assert material["status"] == "ready"
    lock_sql, lock_params = next(
        (sql, params)
        for sql, params in calls
        if "FOR UPDATE OF job, material" in sql
    )
    assert "material.sha256 = %s" in lock_sql
    assert "material.size_bytes = %s" in lock_sql
    assert lock_params == (JOB_ID, "worker-a", "a" * 64, 100)
    assert sum("INSERT INTO hxy_material_artifacts" in sql for sql, _ in calls) == 2
    assert sum("INSERT INTO hxy_material_chunks" in sql for sql, _ in calls) == 1
    assert any("status = 'succeeded'" in sql for sql, _ in calls)
    assert any("status = 'ready'" in sql for sql, _ in calls)
    material_update = next(
        sql for sql, _ in calls if "UPDATE hxy_product_materials" in sql
    )
    assert "sha256 = %s" in material_update
    assert "size_bytes = %s" in material_update


def test_retry_or_fail_job_stops_after_max_attempts() -> None:
    module = importlib.import_module("apps.api.hxy_product.material_repository")
    repository = module.MaterialRepository("postgresql://materials.test/hxy")
    calls: list[str] = []
    lease_row = {
        "job_id": JOB_ID,
        "material_id": MATERIAL_ID,
        "assignment_id": ASSIGNMENT_ID,
        "attempt_count": 3,
        "max_attempts": 3,
    }

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, sql: str, _params: tuple[Any, ...]):
            normalized = " ".join(sql.split())
            calls.append(normalized)
            if "FOR UPDATE" in normalized and "lease_owner" in normalized:
                return Result(lease_row)
            if "UPDATE hxy_material_job_attempts" in normalized:
                return Result(rowcount=1)
            if "UPDATE hxy_material_parser_jobs" in normalized:
                return Result({"status": "permanent_failed"})
            if "UPDATE hxy_product_materials" in normalized:
                return Result(rowcount=1)
            raise AssertionError(normalized)

    repository.connect = lambda: Connection()

    outcome = repository.retry_or_fail_job(
        JOB_ID,
        "worker-a",
        retryable=True,
        error_code="parser_timeout",
        error_summary="parser timed out",
        retry_delay_seconds=60,
    )

    assert outcome == "permanent_failed"
    assert any("status = 'needs_attention'" in sql for sql in calls)


def test_reclaim_stale_leases_returns_expired_work_to_retryable_state() -> None:
    module = importlib.import_module("apps.api.hxy_product.material_repository")
    repository = module.MaterialRepository("postgresql://materials.test/hxy")
    calls: list[str] = []

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, sql: str, _params: tuple[Any, ...] = ()):
            normalized = " ".join(sql.split())
            calls.append(normalized)
            if "WITH stale AS" in normalized:
                return Result(rows=[{"job_id": JOB_ID, "status": "retryable_failed"}])
            raise AssertionError(normalized)

    repository.connect = lambda: Connection()

    reclaimed = repository.reclaim_stale_leases(limit=10)

    assert reclaimed == 1
    assert any("SKIP LOCKED" in sql for sql in calls)
    assert any("lost_lease" in sql for sql in calls)


def test_reclaim_exhausted_scan_lease_marks_material_scan_failed() -> None:
    module = importlib.import_module("apps.api.hxy_product.material_repository")
    repository = module.MaterialRepository("postgresql://materials.test/hxy")
    calls: list[str] = []

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, sql: str, _params: tuple[Any, ...] = ()):
            normalized = " ".join(sql.split())
            calls.append(normalized)
            if "WITH stale AS" in normalized:
                return Result(
                    rows=[
                        {
                            "job_id": JOB_ID,
                            "material_id": MATERIAL_ID,
                            "job_type": "scan",
                            "status": "permanent_failed",
                        }
                    ]
                )
            if "UPDATE hxy_outbox_messages" in normalized:
                return Result(rowcount=1)
            raise AssertionError(normalized)

    repository.connect = lambda: Connection()

    reclaimed = repository.reclaim_stale_leases(limit=10)

    assert reclaimed == 1
    reclaim_sql = next(sql for sql in calls if "WITH stale AS" in sql)
    assert "job_type" in reclaim_sql
    assert "scan_status = CASE" in reclaim_sql
    assert "updated_jobs.job_type = 'scan'" in reclaim_sql
    assert "THEN 'failed'" in reclaim_sql
    assert any(
        "UPDATE hxy_inbound_envelopes" in sql and "needs_attention" in sql
        for sql in calls
    )


def test_requeue_clean_material_targets_parse_without_deleting_history() -> None:
    module = importlib.import_module("apps.api.hxy_product.material_repository")
    repository = module.MaterialRepository("postgresql://materials.test/hxy")
    calls: list[tuple[str, tuple[Any, ...]]] = []

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, sql: str, params: tuple[Any, ...]):
            normalized = " ".join(sql.split())
            calls.append((normalized, params))
            if "FROM hxy_product_materials" in normalized and "FOR UPDATE" in normalized:
                return Result(
                    _material_row()
                    | {"status": "needs_attention", "scan_status": "clean"}
                )
            if "UPDATE hxy_material_parser_jobs" in normalized:
                return Result({"job_id": JOB_ID})
            if "UPDATE hxy_product_materials" in normalized:
                return Result(
                    _material_row()
                    | {"status": "processing", "scan_status": "clean"}
                )
            if "INSERT INTO hxy_material_job_requeue_events" in normalized:
                return Result({"requeue_event_id": str(uuid4())})
            raise AssertionError(normalized)

    repository.connect = lambda: Connection()

    material = repository.requeue_material(
        ASSIGNMENT_ID,
        MATERIAL_ID,
        actor_assignment_id=ASSIGNMENT_ID,
        reason="manual_retry",
    )

    assert material is not None
    assert material["status"] == "processing"
    job_update, job_params = next(
        (sql, params)
        for sql, params in calls
        if "UPDATE hxy_material_parser_jobs" in sql
    )
    assert "max_attempts = LEAST(max_attempts + 3, 100)" in job_update
    assert "job_type = %s" in job_update
    assert "parse" in job_params
    assert not any("DELETE FROM hxy_material_job_attempts" in sql for sql, _ in calls)
    material_update = next(
        sql for sql, _ in calls if "UPDATE hxy_product_materials" in sql
    )
    assert "organization_id::text" in material_update
    assert "store_id" in material_update
    audit_sql, audit_params = next(
        (sql, params)
        for sql, params in calls
        if "INSERT INTO hxy_material_job_requeue_events" in sql
    )
    assert "actor_assignment_id" in audit_sql
    assert "from_status" in audit_sql
    assert ASSIGNMENT_ID in audit_params
    assert "parse" in audit_params
    assert "manual_retry" in audit_params


def test_requeue_failed_scan_targets_scan_and_resets_material_to_pending() -> None:
    module = importlib.import_module("apps.api.hxy_product.material_repository")
    repository = module.MaterialRepository("postgresql://materials.test/hxy")
    calls: list[tuple[str, tuple[Any, ...]]] = []

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, sql: str, params: tuple[Any, ...]):
            normalized = " ".join(sql.split())
            calls.append((normalized, params))
            if "FROM hxy_product_materials" in normalized and "FOR UPDATE" in normalized:
                return Result(
                    _material_row()
                    | {"status": "needs_attention", "scan_status": "failed"}
                )
            if "UPDATE hxy_material_parser_jobs" in normalized:
                return Result({"job_id": JOB_ID})
            if "UPDATE hxy_product_materials" in normalized:
                return Result(
                    _material_row()
                    | {"status": "processing", "scan_status": "pending"}
                )
            if "INSERT INTO hxy_material_job_requeue_events" in normalized:
                return Result({"requeue_event_id": str(uuid4())})
            raise AssertionError(normalized)

    repository.connect = lambda: Connection()

    material = repository.requeue_material(
        ASSIGNMENT_ID,
        MATERIAL_ID,
        actor_assignment_id=ASSIGNMENT_ID,
        reason="scanner recovered",
    )

    assert material is not None
    assert material["scan_status"] == "pending"
    job_update, job_params = next(
        (sql, params)
        for sql, params in calls
        if "UPDATE hxy_material_parser_jobs" in sql
    )
    assert "job_type = %s" in job_update
    assert "scan" in job_params
    material_update = next(
        sql for sql, _ in calls if "UPDATE hxy_product_materials" in sql
    )
    assert "scan_status = 'pending'" in material_update
