from __future__ import annotations

import importlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "data" / "migrations" / "013_hxy_material_intake_jobs.sql"
ASSIGNMENT_ID = "20000000-0000-0000-0000-000000000001"
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


def test_create_material_enqueues_parser_job_in_the_same_transaction() -> None:
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
                return Result({"assignment_id": ASSIGNMENT_ID})
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


def test_claim_next_job_uses_skip_locked_and_opens_an_attempt() -> None:
    module = importlib.import_module("apps.api.hxy_product.material_repository")
    repository = module.MaterialRepository("postgresql://materials.test/hxy")
    calls: list[tuple[str, tuple[Any, ...]]] = []
    claimed_row = {
        **_material_row(),
        "job_id": JOB_ID,
        "parser_strategy": "markitdown",
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
    assert any(params[0] == "worker-a" for sql, params in calls if "UPDATE hxy_material_parser_jobs" in sql)


def test_complete_job_requires_the_current_lease_owner_and_records_artifacts() -> None:
    module = importlib.import_module("apps.api.hxy_product.material_repository")
    repository = module.MaterialRepository("postgresql://materials.test/hxy")
    calls: list[str] = []
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

        def execute(self, sql: str, _params: tuple[Any, ...]):
            normalized = " ".join(sql.split())
            calls.append(normalized)
            if "FOR UPDATE" in normalized and "lease_owner" in normalized:
                return Result(lease_row)
            if "INSERT INTO hxy_material_artifacts" in normalized:
                return Result({"artifact_id": str(uuid4())})
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

    material = repository.complete_job(
        JOB_ID,
        "worker-a",
        artifacts=artifacts,
        understanding={"summary": "已完成深度理解。"},
        parser_name="markitdown",
        parser_version="0.1.6",
    )

    assert material["status"] == "ready"
    assert sum("INSERT INTO hxy_material_artifacts" in sql for sql in calls) == 2
    assert any("status = 'succeeded'" in sql for sql in calls)
    assert any("status = 'ready'" in sql for sql in calls)


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
