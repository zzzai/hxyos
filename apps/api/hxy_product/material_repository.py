from __future__ import annotations

import json
from typing import Any

try:
    import psycopg
    from psycopg.rows import dict_row
except Exception:  # pragma: no cover - deployment dependency may be installed later
    psycopg = None
    dict_row = None


class MaterialStorageQuotaExceeded(Exception):
    pass


class MaterialJobLeaseLost(Exception):
    pass


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except ValueError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _material_from_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row.get("material_id") or row.get("id")),
        "assignment_id": str(row["assignment_id"]),
        "client_upload_id": str(row["client_upload_id"]),
        "file_name": str(row["original_file_name"]),
        "extension": str(row["extension"]),
        "media_type": str(row["media_type"]),
        "size_bytes": int(row["size_bytes"]),
        "sha256": str(row["sha256"]),
        "storage_key": str(row["storage_key"]),
        "note": str(row.get("note") or ""),
        "status": str(row["status"]),
        "understanding": _json_object(row.get("understanding_json")),
        "official_use_allowed": False,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


_MATERIAL_SELECT = """
    SELECT material_id::text,
           assignment_id::text,
           client_upload_id::text,
           original_file_name,
           extension,
           media_type,
           size_bytes,
           sha256,
           storage_key,
           note,
           status,
           understanding_json,
           official_use_allowed,
           created_at,
           updated_at
    FROM hxy_product_materials
"""


class MaterialRepository:
    def __init__(self, database_url: str):
        if not database_url:
            raise ValueError("database_url is required")
        if psycopg is None:
            raise RuntimeError("psycopg is not installed")
        self.database_url = database_url

    def connect(self):
        return psycopg.connect(self.database_url, row_factory=dict_row)

    def create_material(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self.connect() as connection:
            assignment = connection.execute(
                """
                SELECT assignment_id::text
                FROM hxy_role_assignments
                WHERE assignment_id = %s::uuid
                  AND status = 'active'
                FOR UPDATE
                """,
                (payload["assignment_id"],),
            ).fetchone()
            if assignment is None:
                raise ValueError("active assignment is required")

            existing = connection.execute(
                _MATERIAL_SELECT
                + """
                WHERE assignment_id = %s::uuid
                  AND client_upload_id = %s::uuid
                  AND status <> 'archived'
                LIMIT 1
                """,
                (payload["assignment_id"], payload["client_upload_id"]),
            ).fetchone()
            if existing is not None:
                return _material_from_row(existing)

            usage = connection.execute(
                """
                SELECT COALESCE(SUM(size_bytes), 0)::bigint AS used_bytes
                FROM hxy_product_materials
                WHERE assignment_id = %s::uuid
                  AND status <> 'archived'
                """,
                (payload["assignment_id"],),
            ).fetchone()
            used_bytes = int((usage or {}).get("used_bytes") or 0)
            if (
                used_bytes + int(payload["size_bytes"])
                > int(payload["max_assignment_storage_bytes"])
            ):
                raise MaterialStorageQuotaExceeded

            row = connection.execute(
                """
                INSERT INTO hxy_product_materials (
                  material_id,
                  assignment_id,
                  client_upload_id,
                  original_file_name,
                  extension,
                  media_type,
                  size_bytes,
                  sha256,
                  storage_key,
                  note,
                  status,
                  understanding_json,
                  official_use_allowed
                )
                VALUES (
                  %s::uuid,
                  %s::uuid,
                  %s::uuid,
                  %s,
                  %s,
                  %s,
                  %s,
                  %s,
                  %s,
                  %s,
                  %s,
                  %s::jsonb,
                  FALSE
                )
                RETURNING material_id::text,
                          assignment_id::text,
                          client_upload_id::text,
                          original_file_name,
                          extension,
                          media_type,
                          size_bytes,
                          sha256,
                          storage_key,
                          note,
                          status,
                          understanding_json,
                          official_use_allowed,
                          created_at,
                          updated_at
                """,
                (
                    payload["material_id"],
                    payload["assignment_id"],
                    payload["client_upload_id"],
                    payload["file_name"],
                    payload["extension"],
                    payload["media_type"],
                    payload["size_bytes"],
                    payload["sha256"],
                    payload["storage_key"],
                    payload.get("note") or "",
                    payload.get("status") or "understood",
                    json.dumps(payload.get("understanding") or {}, ensure_ascii=False),
                ),
            ).fetchone()
            connection.execute(
                """
                INSERT INTO hxy_material_parser_jobs (
                  material_id,
                  assignment_id,
                  parser_strategy,
                  status,
                  max_attempts
                )
                VALUES (%s::uuid, %s::uuid, 'markitdown', 'queued', %s)
                RETURNING job_id::text
                """,
                (
                    payload["material_id"],
                    payload["assignment_id"],
                    int(payload.get("max_parser_attempts") or 3),
                ),
            ).fetchone()
        return _material_from_row(row)

    def claim_next_job(
        self,
        worker_id: str,
        *,
        lease_seconds: int,
    ) -> dict[str, Any] | None:
        if not worker_id.strip():
            raise ValueError("worker_id is required")
        if lease_seconds < 1:
            raise ValueError("lease_seconds must be positive")
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT job.job_id::text,
                       job.assignment_id::text,
                       job.material_id::text,
                       job.parser_strategy,
                       job.status AS job_status,
                       job.attempt_count,
                       job.max_attempts,
                       material.original_file_name,
                       material.extension,
                       material.media_type,
                       material.size_bytes,
                       material.sha256,
                       material.storage_key,
                       material.note,
                       material.understanding_json
                FROM hxy_material_parser_jobs AS job
                JOIN hxy_product_materials AS material
                  ON material.assignment_id = job.assignment_id
                 AND material.material_id = job.material_id
                WHERE job.status IN ('queued', 'retryable_failed')
                  AND job.available_at <= NOW()
                  AND material.status <> 'archived'
                ORDER BY job.available_at, job.created_at, job.job_id
                FOR UPDATE OF job SKIP LOCKED
                LIMIT 1
                """,
                (),
            ).fetchone()
            if row is None:
                return None

            attempt_number = int(row["attempt_count"]) + 1
            connection.execute(
                """
                UPDATE hxy_material_parser_jobs
                SET lease_owner = %s,
                    lease_expires_at = NOW() + (%s * INTERVAL '1 second'),
                    status = 'running',
                    attempt_count = %s,
                    started_at = COALESCE(started_at, NOW()),
                    completed_at = NULL,
                    last_error_code = NULL,
                    last_error_summary = NULL,
                    updated_at = NOW()
                WHERE job_id = %s::uuid
                RETURNING job_id::text, status AS job_status, attempt_count
                """,
                (worker_id.strip(), lease_seconds, attempt_number, row["job_id"]),
            ).fetchone()
            attempt = connection.execute(
                """
                INSERT INTO hxy_material_job_attempts (
                  job_id,
                  attempt_number,
                  worker_id,
                  outcome
                )
                VALUES (%s::uuid, %s, %s, 'running')
                RETURNING attempt_id::text
                """,
                (row["job_id"], attempt_number, worker_id.strip()),
            ).fetchone()

        return {
            "job_id": str(row["job_id"]),
            "assignment_id": str(row["assignment_id"]),
            "material_id": str(row["material_id"]),
            "parser_strategy": str(row["parser_strategy"]),
            "attempt_id": str(attempt["attempt_id"]),
            "attempt_number": attempt_number,
            "max_attempts": int(row["max_attempts"]),
            "file_name": str(row["original_file_name"]),
            "extension": str(row["extension"]),
            "media_type": str(row["media_type"]),
            "size_bytes": int(row["size_bytes"]),
            "sha256": str(row["sha256"]),
            "storage_key": str(row["storage_key"]),
            "note": str(row.get("note") or ""),
            "understanding": _json_object(row.get("understanding_json")),
        }

    def _lock_owned_job(
        self,
        connection: Any,
        job_id: str,
        worker_id: str,
    ) -> dict[str, Any]:
        row = connection.execute(
            """
            SELECT job_id::text,
                   assignment_id::text,
                   material_id::text,
                   attempt_count,
                   max_attempts
            FROM hxy_material_parser_jobs
            WHERE job_id = %s::uuid
              AND status = 'running'
              AND lease_owner = %s
              AND lease_expires_at > NOW()
            FOR UPDATE
            """,
            (job_id, worker_id),
        ).fetchone()
        if row is None:
            raise MaterialJobLeaseLost("material parser job lease is no longer owned")
        return row

    def complete_job(
        self,
        job_id: str,
        worker_id: str,
        *,
        artifacts: list[dict[str, Any]],
        understanding: dict[str, Any],
        parser_name: str,
        parser_version: str,
    ) -> dict[str, Any]:
        with self.connect() as connection:
            job = self._lock_owned_job(connection, job_id, worker_id)
            for artifact in artifacts:
                connection.execute(
                    """
                    INSERT INTO hxy_material_artifacts (
                      artifact_id,
                      assignment_id,
                      material_id,
                      job_id,
                      artifact_type,
                      storage_key,
                      sha256,
                      size_bytes,
                      metadata_json,
                      official_use_allowed
                    )
                    VALUES (
                      %s::uuid,
                      %s::uuid,
                      %s::uuid,
                      %s::uuid,
                      %s,
                      %s,
                      %s,
                      %s,
                      %s::jsonb,
                      FALSE
                    )
                    RETURNING artifact_id::text
                    """,
                    (
                        artifact["artifact_id"],
                        job["assignment_id"],
                        job["material_id"],
                        job_id,
                        artifact["artifact_type"],
                        artifact["storage_key"],
                        artifact["sha256"],
                        int(artifact["size_bytes"]),
                        json.dumps(artifact.get("metadata") or {}, ensure_ascii=False),
                    ),
                ).fetchone()

            connection.execute(
                """
                UPDATE hxy_material_job_attempts
                SET outcome = 'succeeded',
                    parser_name = %s,
                    parser_version = %s,
                    completed_at = NOW()
                WHERE job_id = %s::uuid
                  AND attempt_number = %s
                  AND outcome = 'running'
                """,
                (parser_name, parser_version, job_id, job["attempt_count"]),
            )
            connection.execute(
                """
                UPDATE hxy_material_parser_jobs
                SET status = 'succeeded',
                    lease_owner = NULL,
                    lease_expires_at = NULL,
                    completed_at = NOW(),
                    updated_at = NOW()
                WHERE job_id = %s::uuid
                """,
                (job_id,),
            )
            row = connection.execute(
                """
                UPDATE hxy_product_materials
                SET status = 'ready',
                    understanding_json = %s::jsonb,
                    updated_at = NOW()
                WHERE assignment_id = %s::uuid
                  AND material_id = %s::uuid
                  AND status <> 'archived'
                RETURNING material_id::text,
                          assignment_id::text,
                          client_upload_id::text,
                          original_file_name,
                          extension,
                          media_type,
                          size_bytes,
                          sha256,
                          storage_key,
                          note,
                          status,
                          understanding_json,
                          official_use_allowed,
                          created_at,
                          updated_at
                """,
                (
                    json.dumps(understanding, ensure_ascii=False),
                    job["assignment_id"],
                    job["material_id"],
                ),
            ).fetchone()
        if row is None:
            raise MaterialJobLeaseLost("material was archived while parser job was running")
        return _material_from_row(row)

    def retry_or_fail_job(
        self,
        job_id: str,
        worker_id: str,
        *,
        retryable: bool,
        error_code: str,
        error_summary: str,
        retry_delay_seconds: int,
        parser_name: str | None = None,
        parser_version: str | None = None,
    ) -> str:
        with self.connect() as connection:
            job = self._lock_owned_job(connection, job_id, worker_id)
            can_retry = retryable and int(job["attempt_count"]) < int(job["max_attempts"])
            outcome = "retryable_failed" if can_retry else "permanent_failed"
            bounded_code = error_code.strip()[:80] or "parser_error"
            bounded_summary = " ".join(error_summary.split())[:500] or "material parsing failed"
            connection.execute(
                """
                UPDATE hxy_material_job_attempts
                SET outcome = %s,
                    parser_name = %s,
                    parser_version = %s,
                    error_code = %s,
                    error_summary = %s,
                    completed_at = NOW()
                WHERE job_id = %s::uuid
                  AND attempt_number = %s
                  AND outcome = 'running'
                """,
                (
                    outcome,
                    parser_name,
                    parser_version,
                    bounded_code,
                    bounded_summary,
                    job_id,
                    job["attempt_count"],
                ),
            )
            updated = connection.execute(
                """
                UPDATE hxy_material_parser_jobs
                SET status = %s,
                    available_at = CASE
                      WHEN %s = 'retryable_failed'
                        THEN NOW() + (%s * INTERVAL '1 second')
                      ELSE available_at
                    END,
                    lease_owner = NULL,
                    lease_expires_at = NULL,
                    last_error_code = %s,
                    last_error_summary = %s,
                    completed_at = CASE
                      WHEN %s = 'permanent_failed' THEN NOW()
                      ELSE NULL
                    END,
                    updated_at = NOW()
                WHERE job_id = %s::uuid
                RETURNING status
                """,
                (
                    outcome,
                    outcome,
                    max(0, retry_delay_seconds),
                    bounded_code,
                    bounded_summary,
                    outcome,
                    job_id,
                ),
            ).fetchone()
            material_status = "processing" if can_retry else "needs_attention"
            connection.execute(
                f"""
                UPDATE hxy_product_materials
                SET status = '{material_status}',
                    updated_at = NOW()
                WHERE assignment_id = %s::uuid
                  AND material_id = %s::uuid
                  AND status <> 'archived'
                """,
                (job["assignment_id"], job["material_id"]),
            )
        return str(updated["status"])

    def reclaim_stale_leases(self, *, limit: int = 100) -> int:
        if limit < 1:
            return 0
        with self.connect() as connection:
            rows = connection.execute(
                """
                WITH stale AS (
                  SELECT job_id,
                         assignment_id,
                         material_id,
                         attempt_count,
                         max_attempts
                  FROM hxy_material_parser_jobs
                  WHERE status = 'running'
                    AND lease_expires_at <= NOW()
                  ORDER BY lease_expires_at, job_id
                  FOR UPDATE SKIP LOCKED
                  LIMIT %s
                ), finished_attempts AS (
                  UPDATE hxy_material_job_attempts AS attempt
                  SET outcome = 'lost_lease',
                      error_code = 'lease_expired',
                      error_summary = 'worker lease expired before completion',
                      completed_at = NOW()
                  FROM stale
                  WHERE attempt.job_id = stale.job_id
                    AND attempt.attempt_number = stale.attempt_count
                    AND attempt.outcome = 'running'
                ), updated_jobs AS (
                  UPDATE hxy_material_parser_jobs AS job
                  SET status = CASE
                        WHEN stale.attempt_count < stale.max_attempts
                          THEN 'retryable_failed'
                        ELSE 'permanent_failed'
                      END,
                      available_at = NOW(),
                      lease_owner = NULL,
                      lease_expires_at = NULL,
                      last_error_code = 'lease_expired',
                      last_error_summary = 'worker lease expired before completion',
                      completed_at = CASE
                        WHEN stale.attempt_count >= stale.max_attempts THEN NOW()
                        ELSE NULL
                      END,
                      updated_at = NOW()
                  FROM stale
                  WHERE job.job_id = stale.job_id
                  RETURNING job.job_id,
                            job.assignment_id,
                            job.material_id,
                            job.status
                ), updated_materials AS (
                  UPDATE hxy_product_materials AS material
                  SET status = CASE
                        WHEN updated_jobs.status = 'permanent_failed'
                          THEN 'needs_attention'
                        ELSE 'processing'
                      END,
                      updated_at = NOW()
                  FROM updated_jobs
                  WHERE material.assignment_id = updated_jobs.assignment_id
                    AND material.material_id = updated_jobs.material_id
                    AND material.status <> 'archived'
                )
                SELECT job_id::text, status
                FROM updated_jobs
                """,
                (min(limit, 1000),),
            ).fetchall()
        return len(rows)

    def get_by_client_upload_id(
        self,
        assignment_id: str,
        client_upload_id: str,
    ) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                _MATERIAL_SELECT
                + """
                WHERE assignment_id = %s::uuid
                  AND client_upload_id = %s::uuid
                  AND status <> 'archived'
                LIMIT 1
                """,
                (assignment_id, client_upload_id),
            ).fetchone()
        return _material_from_row(row) if row else None

    def list_materials(self, assignment_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                _MATERIAL_SELECT
                + """
                WHERE assignment_id = %s::uuid
                  AND status <> 'archived'
                ORDER BY created_at DESC, material_id DESC
                LIMIT %s
                """,
                (assignment_id, limit),
            ).fetchall()
        return [_material_from_row(row) for row in rows]

    def get_material(self, assignment_id: str, material_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                _MATERIAL_SELECT
                + """
                WHERE assignment_id = %s::uuid
                  AND material_id = %s::uuid
                  AND status <> 'archived'
                LIMIT 1
                """,
                (assignment_id, material_id),
            ).fetchone()
        return _material_from_row(row) if row else None

    def update_understanding(
        self,
        assignment_id: str,
        material_id: str,
        *,
        status: str,
        understanding: dict[str, Any],
    ) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                UPDATE hxy_product_materials
                SET status = %s,
                    understanding_json = %s::jsonb,
                    updated_at = NOW()
                WHERE assignment_id = %s::uuid
                  AND material_id = %s::uuid
                  AND status <> 'archived'
                RETURNING material_id::text,
                          assignment_id::text,
                          client_upload_id::text,
                          original_file_name,
                          extension,
                          media_type,
                          size_bytes,
                          sha256,
                          storage_key,
                          note,
                          status,
                          understanding_json,
                          official_use_allowed,
                          created_at,
                          updated_at
                """,
                (
                    status,
                    json.dumps(understanding, ensure_ascii=False),
                    assignment_id,
                    material_id,
                ),
            ).fetchone()
        return _material_from_row(row) if row else None
