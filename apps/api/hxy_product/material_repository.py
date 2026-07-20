from __future__ import annotations

import json
import re
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


_MATERIAL_QUERY_SPLIT = re.compile(r"[\s,，。！？?；;：:、（）()\[\]【】\"'“”‘’/\\|+·\-_<>《》]+")
_MATERIAL_QUERY_TERMS = (
    "品牌",
    "定位",
    "产品",
    "清泡调补养",
    "泡脚",
    "门店",
    "首店",
    "接待",
    "服务",
    "顾客",
    "会员",
    "员工",
    "店长",
    "运营",
    "流程",
    "话术",
    "培训",
    "选址",
    "装修",
    "财务",
    "融资",
    "合规",
    "风险",
)
_DEICTIC_MATERIAL_TERMS = (
    "刚上传",
    "刚才上传",
    "这份资料",
    "这个资料",
    "这个文件",
    "最新资料",
    "上传的资料",
)


def _validate_source_identity(source_sha256: str, source_size_bytes: int) -> None:
    if not re.fullmatch(r"[0-9a-f]{64}", source_sha256):
        raise ValueError("invalid material source digest")
    if source_size_bytes < 0:
        raise ValueError("invalid material source size")


def derive_source_authority(source_origin: str) -> str:
    return "internal_material" if source_origin == "internal" else "external_reference"


def _normalized_source_origin(value: Any) -> str:
    origin = str(value or "").strip().lower()
    return origin if origin in {"internal", "external", "unknown"} else "unknown"


def _validated_source_authority(source_origin: str, source_authority: str) -> str:
    authority = str(source_authority or "").strip().lower()
    if authority not in {"official_internal", "internal_material", "external_reference"}:
        raise ValueError("unsupported source authority")
    if source_origin != "internal" and authority != "external_reference":
        raise ValueError("external or unknown sources must remain reference-only")
    return authority


def _safe_source_authority(source_origin: str, source_authority: Any) -> str:
    try:
        return _validated_source_authority(source_origin, str(source_authority or ""))
    except ValueError:
        return derive_source_authority(source_origin)


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
    understanding = _json_object(row.get("understanding_json"))
    source_origin = _normalized_source_origin(row.get("source_origin"))
    return {
        "id": str(row.get("material_id") or row.get("id")),
        "assignment_id": str(row["assignment_id"]),
        "organization_id": (
            str(row["organization_id"]) if row.get("organization_id") is not None else None
        ),
        "store_id": str(row["store_id"]) if row.get("store_id") is not None else None,
        "client_upload_id": str(row["client_upload_id"]),
        "file_name": str(row["original_file_name"]),
        "extension": str(row["extension"]),
        "media_type": str(row["media_type"]),
        "size_bytes": int(row["size_bytes"]),
        "sha256": str(row["sha256"]),
        "storage_key": str(row["storage_key"]),
        "note": str(row.get("note") or ""),
        "status": str(row["status"]),
        "scan_status": str(row.get("scan_status") or "legacy_unscanned"),
        "understanding": understanding,
        "source_origin": source_origin,
        "source_authority": _safe_source_authority(source_origin, row.get("source_authority")),
        "authority_version": int(row.get("authority_version") or 1),
        "official_use_allowed": False,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _material_query_terms(query: str) -> list[str]:
    terms = [term for term in _MATERIAL_QUERY_TERMS if term in query]
    for part in _MATERIAL_QUERY_SPLIT.sub(" ", query).split():
        if 2 <= len(part) <= 12 and part not in terms:
            terms.append(part)
    return terms[:8]


def _material_chunk_from_row(row: dict[str, Any]) -> dict[str, Any]:
    material_id = str(row["material_id"])
    source_origin = _normalized_source_origin(row.get("source_origin"))
    source_authority = _safe_source_authority(source_origin, row.get("source_authority"))
    if source_authority == "official_internal":
        stage = "official"
        status = "active"
    elif source_authority == "internal_material":
        stage = "working_context"
        status = "active"
    else:
        stage = "reference"
        status = "reference"
    return {
        "chunk_id": str(row["chunk_id"]),
        "source_id": material_id,
        "asset_id": material_id,
        "material_id": material_id,
        "title": str(row.get("original_file_name") or "资料来源")[:180],
        "source_path": f"material:{material_id}",
        "normalized_path": None,
        "source_url": f"/api/v1/materials/{material_id}/content",
        "domain": str(row.get("domain") or "general"),
        "source_origin": source_origin,
        "origin": source_origin,
        "source_authority": source_authority,
        "authority_source": source_authority,
        "authority_version": int(row.get("authority_version") or 1),
        "authority_recorded": True,
        "stage": stage,
        "status": status,
        "source_type": "private_material",
        "score": int(row.get("score") or 0),
        "heading": str(row.get("heading") or "")[:300],
        "content": str(row.get("content") or ""),
        "official_use_allowed": False,
    }


_MATERIAL_SELECT = """
    SELECT material_id::text,
           assignment_id::text,
           organization_id::text,
           store_id,
           client_upload_id::text,
           original_file_name,
           extension,
           media_type,
           size_bytes,
           sha256,
           storage_key,
           note,
           status,
           scan_status,
           understanding_json,
           source_origin,
           source_authority,
           authority_version,
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

    @staticmethod
    def _release_waiting_issue_envelopes(connection: Any, material_id: str) -> None:
        connection.execute(
            """
            WITH released AS (
              UPDATE hxy_outbox_messages AS message
              SET available_at = NOW(),
                  last_error_code = NULL,
                  last_error_summary = NULL,
                  updated_at = NOW()
              WHERE message.topic IN (
                    'understand.inbound.issue',
                    'understand.organization_record'
                  )
                AND message.aggregate_type = 'inbound_envelope'
                AND message.status = 'pending'
                AND message.available_at = 'infinity'::timestamptz
                AND EXISTS (
                  SELECT 1
                  FROM hxy_asset_bindings AS current_binding
                  WHERE current_binding.organization_id = message.organization_id
                    AND current_binding.source_type = 'source_asset'
                    AND current_binding.source_id = %s::uuid
                    AND current_binding.target_type = 'inbound_envelope'
                    AND current_binding.target_id = message.aggregate_id
                    AND current_binding.relation_type = 'attached_to'
                )
                AND NOT EXISTS (
                  SELECT 1
                  FROM hxy_asset_bindings AS pending_binding
                  JOIN hxy_product_materials AS pending_material
                    ON pending_material.organization_id = pending_binding.organization_id
                   AND pending_material.material_id = pending_binding.source_id
                  WHERE pending_binding.organization_id = message.organization_id
                    AND pending_binding.source_type = 'source_asset'
                    AND pending_binding.target_type = 'inbound_envelope'
                    AND pending_binding.target_id = message.aggregate_id
                    AND pending_binding.relation_type = 'attached_to'
                    AND pending_material.scan_status <> 'clean'
                )
              RETURNING message.organization_id, message.aggregate_id
            )
            UPDATE hxy_inbound_envelopes AS envelope
            SET status = 'queued',
                processed_at = NULL,
                updated_at = NOW()
            FROM released
            WHERE envelope.organization_id = released.organization_id
              AND envelope.envelope_id = released.aggregate_id
              AND envelope.status IN ('received', 'needs_attention')
            """,
            (material_id,),
        )

    @staticmethod
    def _hold_waiting_issue_envelopes(
        connection: Any,
        material_id: str,
        *,
        error_code: str,
    ) -> None:
        connection.execute(
            """
            WITH deferred AS (
              UPDATE hxy_outbox_messages AS message
              SET available_at = 'infinity'::timestamptz,
                  last_error_code = %s,
                  last_error_summary = 'an attached material needs attention',
                  updated_at = NOW()
              WHERE message.topic IN (
                    'understand.inbound.issue',
                    'understand.organization_record'
                  )
                AND message.aggregate_type = 'inbound_envelope'
                AND message.status = 'pending'
                AND EXISTS (
                  SELECT 1
                  FROM hxy_asset_bindings AS binding
                  WHERE binding.organization_id = message.organization_id
                    AND binding.source_type = 'source_asset'
                    AND binding.source_id = %s::uuid
                    AND binding.target_type = 'inbound_envelope'
                    AND binding.target_id = message.aggregate_id
                    AND binding.relation_type = 'attached_to'
                )
              RETURNING message.organization_id, message.aggregate_id
            )
            UPDATE hxy_inbound_envelopes AS envelope
            SET status = 'needs_attention',
                processed_at = NULL,
                updated_at = NOW()
            FROM deferred
            WHERE envelope.organization_id = deferred.organization_id
              AND envelope.envelope_id = deferred.aggregate_id
              AND envelope.status = 'received'
            """,
            (error_code[:100], material_id),
        )

    def create_material(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self.connect() as connection:
            assignment = connection.execute(
                """
                SELECT assignment_id::text,
                       organization_id::text,
                       store_id
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
                  organization_id,
                  store_id,
                  client_upload_id,
                  original_file_name,
                  extension,
                  media_type,
                  size_bytes,
                  sha256,
                  storage_key,
                  note,
                  status,
                  scan_status,
                  understanding_json,
                  source_origin,
                  source_authority,
                  official_use_allowed
                )
                VALUES (
                  %s::uuid,
                  %s::uuid,
                  %s::uuid,
                  %s,
                  %s::uuid,
                  %s,
                  %s,
                  %s,
                  %s,
                  %s,
                  %s,
                  %s,
                  %s,
                  %s,
                  %s::jsonb,
                  %s,
                  %s,
                  FALSE
                )
                RETURNING material_id::text,
                          assignment_id::text,
                          organization_id::text,
                          store_id,
                          client_upload_id::text,
                          original_file_name,
                          extension,
                          media_type,
                          size_bytes,
                          sha256,
                          storage_key,
                          note,
                          status,
                          scan_status,
                          understanding_json,
                          source_origin,
                          source_authority,
                          authority_version,
                          official_use_allowed,
                          created_at,
                          updated_at
                """,
                (
                    payload["material_id"],
                    payload["assignment_id"],
                    str(assignment["organization_id"]),
                    assignment.get("store_id"),
                    payload["client_upload_id"],
                    payload["file_name"],
                    payload["extension"],
                    payload["media_type"],
                    payload["size_bytes"],
                    payload["sha256"],
                    payload["storage_key"],
                    payload.get("note") or "",
                    payload.get("status") or "understood",
                    payload.get("scan_status") or "pending",
                    json.dumps(payload.get("understanding") or {}, ensure_ascii=False),
                    _normalized_source_origin(payload.get("source_origin")),
                    _validated_source_authority(
                        _normalized_source_origin(payload.get("source_origin")),
                        payload.get("source_authority")
                        or derive_source_authority(
                            _normalized_source_origin(payload.get("source_origin"))
                        ),
                    ),
                ),
            ).fetchone()
            connection.execute(
                """
                INSERT INTO hxy_material_parser_jobs (
                  material_id,
                  assignment_id,
                  job_type,
                  parser_strategy,
                  status,
                  max_attempts
                )
                VALUES (%s::uuid, %s::uuid, 'scan', 'clamav', 'queued', %s)
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
                       job.job_type,
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
                       material.scan_status,
                       material.understanding_json
                FROM hxy_material_parser_jobs AS job
                JOIN hxy_product_materials AS material
                  ON material.assignment_id = job.assignment_id
                 AND material.material_id = job.material_id
                WHERE job.status IN ('queued', 'retryable_failed')
                  AND job.available_at <= NOW()
                  AND material.status <> 'archived'
                  AND (
                    (job.job_type = 'scan' AND material.scan_status = 'pending')
                    OR (job.job_type = 'parse' AND material.scan_status = 'clean')
                  )
                ORDER BY CASE job.job_type WHEN 'scan' THEN 0 ELSE 1 END,
                         job.available_at,
                         job.created_at,
                         job.job_id
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
            "job_type": str(row["job_type"]),
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
            "scan_status": str(row.get("scan_status") or "legacy_unscanned"),
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
            SELECT job.job_id::text,
                   job.assignment_id::text,
                   job.material_id::text,
                   job.job_type,
                   job.attempt_count,
                   job.max_attempts
            FROM hxy_material_parser_jobs AS job
            WHERE job.job_id = %s::uuid
              AND job.status = 'running'
              AND job.lease_owner = %s
              AND job.lease_expires_at > NOW()
            FOR UPDATE OF job
            """,
            (job_id, worker_id),
        ).fetchone()
        if row is None:
            raise MaterialJobLeaseLost("material parser job lease is no longer owned")
        return row

    def _lock_owned_job_for_source(
        self,
        connection: Any,
        job_id: str,
        worker_id: str,
        *,
        source_sha256: str,
        source_size_bytes: int,
    ) -> dict[str, Any]:
        row = connection.execute(
            """
            SELECT job.job_id::text,
                   job.assignment_id::text,
                   job.material_id::text,
                   job.job_type,
                   job.attempt_count,
                   job.max_attempts
            FROM hxy_material_parser_jobs AS job
            JOIN hxy_product_materials AS material
              ON material.assignment_id = job.assignment_id
             AND material.material_id = job.material_id
            WHERE job.job_id = %s::uuid
              AND job.status = 'running'
              AND job.lease_owner = %s
              AND job.lease_expires_at > NOW()
              AND material.sha256 = %s
              AND material.size_bytes = %s
            FOR UPDATE OF job, material
            """,
            (job_id, worker_id, source_sha256, source_size_bytes),
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
        chunks: list[dict[str, Any]] | None = None,
        understanding: dict[str, Any],
        parser_name: str,
        parser_version: str,
        source_sha256: str,
        source_size_bytes: int,
    ) -> dict[str, Any]:
        _validate_source_identity(source_sha256, source_size_bytes)
        with self.connect() as connection:
            job = self._lock_owned_job_for_source(
                connection,
                job_id,
                worker_id,
                source_sha256=source_sha256,
                source_size_bytes=source_size_bytes,
            )
            if str(job.get("job_type") or "parse") != "parse":
                raise MaterialJobLeaseLost("material parser job lease is no longer owned")
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

            for chunk in chunks or []:
                connection.execute(
                    """
                    INSERT INTO hxy_material_chunks (
                      chunk_id,
                      assignment_id,
                      material_id,
                      artifact_id,
                      artifact_type,
                      chunk_index,
                      heading,
                      content,
                      char_count,
                      official_use_allowed
                    )
                    VALUES (
                      %s::uuid,
                      %s::uuid,
                      %s::uuid,
                      %s::uuid,
                      'normalized_markdown',
                      %s,
                      %s,
                      %s,
                      %s,
                      FALSE
                    )
                    RETURNING chunk_id::text
                    """,
                    (
                        chunk["chunk_id"],
                        job["assignment_id"],
                        job["material_id"],
                        chunk["artifact_id"],
                        int(chunk["chunk_index"]),
                        str(chunk.get("heading") or "")[:300],
                        str(chunk["content"]),
                        int(chunk["char_count"]),
                    ),
                ).fetchone()

            connection.execute(
                """
                UPDATE hxy_material_job_attempts
                SET outcome = 'succeeded',
                    parser_name = %s,
                    parser_version = %s,
                    source_sha256 = %s,
                    source_size_bytes = %s,
                    completed_at = NOW()
                WHERE job_id = %s::uuid
                  AND attempt_number = %s
                  AND outcome = 'running'
                """,
                (
                    parser_name,
                    parser_version,
                    source_sha256,
                    source_size_bytes,
                    job_id,
                    job["attempt_count"],
                ),
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
                  AND sha256 = %s
                  AND size_bytes = %s
                  AND status <> 'archived'
                RETURNING material_id::text,
                          assignment_id::text,
                          organization_id::text,
                          store_id,
                          client_upload_id::text,
                          original_file_name,
                          extension,
                          media_type,
                          size_bytes,
                          sha256,
                          storage_key,
                          note,
                          status,
                          scan_status,
                          understanding_json,
                          source_origin,
                          source_authority,
                          authority_version,
                          official_use_allowed,
                          created_at,
                          updated_at
                """,
                (
                    json.dumps(understanding, ensure_ascii=False),
                    job["assignment_id"],
                    job["material_id"],
                    source_sha256,
                    source_size_bytes,
                ),
            ).fetchone()
        if row is None:
            raise MaterialJobLeaseLost("material was archived while parser job was running")
        return _material_from_row(row)

    def complete_scan_job(
        self,
        job_id: str,
        worker_id: str,
        *,
        result_status: str,
        engine: str,
        engine_version: str,
        signature: str | None,
        source_sha256: str,
        source_size_bytes: int,
    ) -> dict[str, Any]:
        if result_status not in {"clean", "blocked"}:
            raise ValueError("unsupported material scan result")
        bounded_engine = engine.strip()[:80]
        bounded_version = engine_version.strip()[:80]
        bounded_signature = (signature or "").strip()[:160] or None
        if not bounded_engine or not bounded_version:
            raise ValueError("scanner engine and version are required")
        if (result_status == "clean") != (bounded_signature is None):
            raise ValueError("scan signature does not match result")
        _validate_source_identity(source_sha256, source_size_bytes)

        with self.connect() as connection:
            job = self._lock_owned_job_for_source(
                connection,
                job_id,
                worker_id,
                source_sha256=source_sha256,
                source_size_bytes=source_size_bytes,
            )
            if str(job.get("job_type") or "") != "scan":
                raise MaterialJobLeaseLost("material scan job lease is no longer owned")
            connection.execute(
                """
                INSERT INTO hxy_material_scan_results (
                  assignment_id,
                  material_id,
                  job_id,
                  attempt_number,
                  result_status,
                  engine,
                  engine_version,
                  signature,
                  source_sha256,
                  source_size_bytes
                )
                VALUES (
                  %s::uuid, %s::uuid, %s::uuid, %s, %s, %s, %s, %s, %s, %s
                )
                RETURNING scan_result_id::text
                """,
                (
                    job["assignment_id"],
                    job["material_id"],
                    job_id,
                    job["attempt_count"],
                    result_status,
                    bounded_engine,
                    bounded_version,
                    bounded_signature,
                    source_sha256,
                    source_size_bytes,
                ),
            ).fetchone()
            connection.execute(
                """
                UPDATE hxy_material_job_attempts
                SET outcome = 'succeeded',
                    parser_name = %s,
                    parser_version = %s,
                    source_sha256 = %s,
                    source_size_bytes = %s,
                    completed_at = NOW()
                WHERE job_id = %s::uuid
                  AND attempt_number = %s
                  AND outcome = 'running'
                """,
                (
                    bounded_engine,
                    bounded_version,
                    source_sha256,
                    source_size_bytes,
                    job_id,
                    job["attempt_count"],
                ),
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
                SET scan_status = %s,
                    status = CASE
                      WHEN %s = 'blocked' THEN 'needs_attention'
                      WHEN EXISTS (
                        SELECT 1
                        FROM hxy_material_parser_jobs AS parse_job
                        WHERE parse_job.assignment_id = hxy_product_materials.assignment_id
                          AND parse_job.material_id = hxy_product_materials.material_id
                          AND parse_job.job_type = 'parse'
                          AND parse_job.status = 'succeeded'
                      ) THEN 'ready'
                      ELSE 'processing'
                    END,
                    updated_at = NOW()
                WHERE assignment_id = %s::uuid
                  AND material_id = %s::uuid
                  AND sha256 = %s
                  AND size_bytes = %s
                  AND status <> 'archived'
                RETURNING material_id::text,
                          assignment_id::text,
                          organization_id::text,
                          store_id,
                          client_upload_id::text,
                          original_file_name,
                          extension,
                          media_type,
                          size_bytes,
                          sha256,
                          storage_key,
                          note,
                          status,
                          scan_status,
                          understanding_json,
                          source_origin,
                          source_authority,
                          authority_version,
                          official_use_allowed,
                          created_at,
                          updated_at
                """,
                (
                    result_status,
                    result_status,
                    job["assignment_id"],
                    job["material_id"],
                    source_sha256,
                    source_size_bytes,
                ),
            ).fetchone()
            if row is None:
                raise MaterialJobLeaseLost(
                    "material was archived while scan job was running"
                )
            if result_status == "clean":
                connection.execute(
                    """
                    INSERT INTO hxy_material_parser_jobs (
                      assignment_id,
                      material_id,
                      job_type,
                      parser_strategy,
                      status,
                      max_attempts
                    )
                    VALUES (%s::uuid, %s::uuid, 'parse', 'markitdown', 'queued', 3)
                    ON CONFLICT (material_id, job_type) DO UPDATE
                    SET status = CASE
                          WHEN hxy_material_parser_jobs.status = 'succeeded'
                            THEN 'succeeded'
                          ELSE 'queued'
                        END,
                        max_attempts = CASE
                          WHEN hxy_material_parser_jobs.status = 'succeeded'
                            THEN hxy_material_parser_jobs.max_attempts
                          ELSE LEAST(
                            GREATEST(
                              hxy_material_parser_jobs.max_attempts,
                              hxy_material_parser_jobs.attempt_count + 3
                            ),
                            100
                          )
                        END,
                        available_at = CASE
                          WHEN hxy_material_parser_jobs.status = 'succeeded'
                            THEN hxy_material_parser_jobs.available_at
                          ELSE NOW()
                        END,
                        lease_owner = CASE
                          WHEN hxy_material_parser_jobs.status = 'succeeded'
                            THEN hxy_material_parser_jobs.lease_owner
                          ELSE NULL
                        END,
                        lease_expires_at = CASE
                          WHEN hxy_material_parser_jobs.status = 'succeeded'
                            THEN hxy_material_parser_jobs.lease_expires_at
                          ELSE NULL
                        END,
                        last_error_code = CASE
                          WHEN hxy_material_parser_jobs.status = 'succeeded'
                            THEN hxy_material_parser_jobs.last_error_code
                          ELSE NULL
                        END,
                        last_error_summary = CASE
                          WHEN hxy_material_parser_jobs.status = 'succeeded'
                            THEN hxy_material_parser_jobs.last_error_summary
                          ELSE NULL
                        END,
                        completed_at = CASE
                          WHEN hxy_material_parser_jobs.status = 'succeeded'
                            THEN hxy_material_parser_jobs.completed_at
                          ELSE NULL
                        END,
                        updated_at = NOW()
                    RETURNING job_id::text
                    """,
                    (job["assignment_id"], job["material_id"]),
                ).fetchone()
                self._release_waiting_issue_envelopes(
                    connection,
                    str(job["material_id"]),
                )
            else:
                self._hold_waiting_issue_envelopes(
                    connection,
                    str(job["material_id"]),
                    error_code="attachment_scan_blocked",
                )
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
            bounded_code = error_code.strip()[:80] or "material_processing_error"
            bounded_summary = (
                " ".join(error_summary.split())[:500]
                or "material processing failed"
            )
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
            if str(job.get("job_type") or "parse") == "scan" and not can_retry:
                connection.execute(
                    """
                    UPDATE hxy_product_materials
                    SET status = 'needs_attention',
                        scan_status = 'failed',
                        updated_at = NOW()
                    WHERE assignment_id = %s::uuid
                      AND material_id = %s::uuid
                      AND status <> 'archived'
                    """,
                    (job["assignment_id"], job["material_id"]),
                )
                self._hold_waiting_issue_envelopes(
                    connection,
                    str(job["material_id"]),
                    error_code="attachment_scan_failed",
                )
            else:
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
                         job_type,
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
                            job.job_type,
                            job.status
                ), updated_materials AS (
                  UPDATE hxy_product_materials AS material
                  SET status = CASE
                        WHEN updated_jobs.status = 'permanent_failed'
                          THEN 'needs_attention'
                        ELSE 'processing'
                      END,
                      scan_status = CASE
                        WHEN updated_jobs.job_type = 'scan'
                         AND updated_jobs.status = 'permanent_failed'
                          THEN 'failed'
                        ELSE material.scan_status
                      END,
                      updated_at = NOW()
                  FROM updated_jobs
                  WHERE material.assignment_id = updated_jobs.assignment_id
                    AND material.material_id = updated_jobs.material_id
                    AND material.status <> 'archived'
                )
                SELECT job_id::text,
                       material_id::text,
                       job_type,
                       status
                FROM updated_jobs
                """,
                (min(limit, 1000),),
            ).fetchall()
            for row in rows:
                if (
                    str(row.get("job_type") or "") == "scan"
                    and str(row.get("status") or "") == "permanent_failed"
                ):
                    self._hold_waiting_issue_envelopes(
                        connection,
                        str(row["material_id"]),
                        error_code="attachment_scan_failed",
                    )
        return len(rows)

    def requeue_material(
        self,
        assignment_id: str,
        material_id: str,
        *,
        actor_assignment_id: str,
        reason: str,
    ) -> dict[str, Any] | None:
        bounded_reason = " ".join(str(reason or "").split())[:500]
        if len(bounded_reason) < 4:
            raise ValueError("material requeue reason is required")

        with self.connect() as connection:
            material = connection.execute(
                _MATERIAL_SELECT
                + """
                WHERE assignment_id = %s::uuid
                  AND material_id = %s::uuid
                  AND status <> 'archived'
                FOR UPDATE
                """,
                (assignment_id, material_id),
            ).fetchone()
            if material is None:
                return None

            scan_status = str(material.get("scan_status") or "legacy_unscanned")
            target_job_type = "parse" if scan_status == "clean" else "scan"
            parser_strategy = "markitdown" if target_job_type == "parse" else "clamav"
            from_status = "missing"

            job = connection.execute(
                """
                WITH target AS (
                  SELECT job_id, status AS from_status
                  FROM hxy_material_parser_jobs
                  WHERE assignment_id = %s::uuid
                    AND material_id = %s::uuid
                    AND job_type = %s
                    AND status IN ('retryable_failed', 'permanent_failed')
                  FOR UPDATE
                )
                UPDATE hxy_material_parser_jobs AS job
                SET status = 'queued',
                    max_attempts = LEAST(max_attempts + 3, 100),
                    available_at = NOW(),
                    lease_owner = NULL,
                    lease_expires_at = NULL,
                    last_error_code = NULL,
                    last_error_summary = NULL,
                    completed_at = NULL,
                    updated_at = NOW()
                FROM target
                WHERE job.job_id = target.job_id
                RETURNING job.job_id::text, target.from_status
                """,
                (assignment_id, material_id, target_job_type),
            ).fetchone()
            if job is not None:
                from_status = str(job.get("from_status") or "retryable_failed")
            if job is None:
                existing_job = connection.execute(
                    """
                    SELECT job_id::text, status
                    FROM hxy_material_parser_jobs
                    WHERE assignment_id = %s::uuid
                      AND material_id = %s::uuid
                      AND job_type = %s
                    FOR UPDATE
                    """,
                    (assignment_id, material_id, target_job_type),
                ).fetchone()
                if existing_job is None:
                    job = connection.execute(
                        """
                        INSERT INTO hxy_material_parser_jobs (
                          assignment_id,
                          material_id,
                          job_type,
                          parser_strategy,
                          status
                        )
                        VALUES (%s::uuid, %s::uuid, %s, %s, 'queued')
                        RETURNING job_id::text
                        """,
                        (
                            assignment_id,
                            material_id,
                            target_job_type,
                            parser_strategy,
                        ),
                    ).fetchone()
                elif str(existing_job["status"]) == "succeeded":
                    return _material_from_row(material)
                else:
                    job = existing_job
                    from_status = str(existing_job["status"])

            reset_scan_status = (
                ",\n                    scan_status = 'pending'"
                if target_job_type == "scan"
                else ""
            )
            row = connection.execute(
                f"""
                UPDATE hxy_product_materials
                SET status = 'processing'{reset_scan_status},
                    updated_at = NOW()
                WHERE assignment_id = %s::uuid
                  AND material_id = %s::uuid
                  AND status <> 'archived'
                RETURNING material_id::text,
                          assignment_id::text,
                          organization_id::text,
                          store_id,
                          client_upload_id::text,
                          original_file_name,
                          extension,
                          media_type,
                          size_bytes,
                          sha256,
                          storage_key,
                          note,
                          status,
                          scan_status,
                          understanding_json,
                          source_origin,
                          source_authority,
                          authority_version,
                          official_use_allowed,
                          created_at,
                          updated_at
                """,
                (assignment_id, material_id),
            ).fetchone()
            if row is not None and job is not None:
                connection.execute(
                    """
                    INSERT INTO hxy_material_job_requeue_events (
                      organization_id,
                      assignment_id,
                      material_id,
                      actor_assignment_id,
                      job_id,
                      from_status,
                      target_job_type,
                      reason
                    )
                    VALUES (
                      %s::uuid,
                      %s::uuid,
                      %s::uuid,
                      %s::uuid,
                      %s::uuid,
                      %s,
                      %s,
                      %s
                    )
                    RETURNING requeue_event_id::text
                    """,
                    (
                        str(row["organization_id"]),
                        assignment_id,
                        material_id,
                        actor_assignment_id,
                        str(job["job_id"]),
                        from_status,
                        target_job_type,
                        bounded_reason,
                    ),
                ).fetchone()
        return _material_from_row(row) if row else None

    def search_material_chunks(
        self,
        assignment_id: str,
        query: str,
        *,
        domain_hint: str | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        bounded_limit = max(1, min(int(limit), 20))
        latest_mode = any(term in query for term in _DEICTIC_MATERIAL_TERMS)
        common_select = """
            SELECT chunk.chunk_id::text,
                   chunk.material_id::text,
                   material.original_file_name,
                   chunk.heading,
                   chunk.content,
                   COALESCE(material.understanding_json->>'domain', 'general') AS domain,
                   material.source_origin,
                   material.source_authority,
                   material.authority_version
            FROM hxy_material_chunks AS chunk
            JOIN hxy_product_materials AS material
              ON material.assignment_id = chunk.assignment_id
             AND material.material_id = chunk.material_id
            WHERE chunk.assignment_id = %s::uuid
              AND material.status = 'ready'
              AND material.scan_status = 'clean'
        """
        if latest_mode:
            sql = (
                common_select
                + """
                ORDER BY material.updated_at DESC,
                         chunk.material_id DESC,
                         chunk.chunk_index
                LIMIT %s
                """
            )
            params: tuple[Any, ...] = (assignment_id, bounded_limit)
        else:
            terms = _material_query_terms(query)
            domain_clause = ""
            scoped_params: list[Any] = [assignment_id]
            if domain_hint:
                domain_clause = " AND COALESCE(material.understanding_json->>'domain', 'general') = %s"
                scoped_params.append(domain_hint)
            scoped = common_select + domain_clause
            full_pattern = f"%{query.strip()}%"
            term_patterns = [f"%{term}%" for term in terms]
            score_parts = [
                "CASE WHEN content ILIKE %s THEN 100 ELSE 0 END",
                "CASE WHEN heading ILIKE %s THEN 70 ELSE 0 END",
                "CAST(similarity(content, %s) * 50 AS INTEGER)",
            ]
            score_params: list[Any] = [full_pattern, full_pattern, query]
            for _term in terms:
                score_parts.append("CASE WHEN content ILIKE %s OR heading ILIKE %s THEN 15 ELSE 0 END")
            for pattern in term_patterns:
                score_params.extend([pattern, pattern])
            match_clauses = ["content ILIKE %s", "heading ILIKE %s", "similarity(content, %s) >= 0.05"]
            match_params: list[Any] = [full_pattern, full_pattern, query]
            for _term in terms:
                match_clauses.extend(["content ILIKE %s", "heading ILIKE %s"])
            for pattern in term_patterns:
                match_params.extend([pattern, pattern])
            sql = f"""
                WITH scoped AS ({scoped})
                SELECT scoped.*,
                       {' + '.join(score_parts)} AS score
                FROM scoped
                WHERE {' OR '.join(match_clauses)}
                ORDER BY score DESC, material_id DESC, chunk_id
                LIMIT %s
            """
            params = tuple([*scoped_params, *score_params, *match_params, bounded_limit])

        with self.connect() as connection:
            rows = connection.execute(sql, params).fetchall()
        if latest_mode:
            for row in rows:
                row["score"] = 120
        return [_material_chunk_from_row(row) for row in rows]

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

    def update_source_authority(
        self,
        assignment_id: str,
        material_id: str,
        *,
        source_origin: str,
        source_authority: str,
        reason: str,
    ) -> dict[str, Any] | None:
        normalized_origin = _normalized_source_origin(source_origin)
        normalized_authority = _validated_source_authority(
            normalized_origin,
            source_authority,
        )
        bounded_reason = " ".join(str(reason or "").split())[:500]
        if len(bounded_reason) < 4:
            raise ValueError("source authority change reason is required")

        with self.connect() as connection:
            current = connection.execute(
                """
                SELECT material.material_id::text,
                       material.assignment_id::text,
                       material.client_upload_id::text,
                       material.original_file_name,
                       material.extension,
                       material.media_type,
                       material.size_bytes,
                       material.sha256,
                       material.storage_key,
                       material.note,
                       material.status,
                       material.understanding_json,
                       material.source_origin,
                       material.source_authority,
                       material.authority_version,
                       material.official_use_allowed,
                       material.created_at,
                       material.updated_at,
                       actor.role AS actor_role
                FROM hxy_product_materials AS material
                JOIN hxy_role_assignments AS owner
                  ON owner.assignment_id = material.assignment_id
                 AND owner.status = 'active'
                JOIN hxy_role_assignments AS actor
                  ON actor.assignment_id = %s::uuid
                 AND actor.organization_id = owner.organization_id
                 AND actor.status = 'active'
                WHERE material.material_id = %s::uuid
                  AND material.status <> 'archived'
                FOR UPDATE OF material
                """,
                (assignment_id, material_id),
            ).fetchone()
            if current is None:
                return None
            if str(current.get("actor_role") or "") not in {"founder", "hq_operations"}:
                raise PermissionError("role cannot grant official source authority")
            if (
                str(current.get("source_origin") or "") == normalized_origin
                and str(current.get("source_authority") or "") == normalized_authority
            ):
                return _material_from_row(current)

            next_version = int(current.get("authority_version") or 1) + 1
            connection.execute(
                """
                INSERT INTO hxy_material_authority_events (
                  material_id,
                  owner_assignment_id,
                  actor_assignment_id,
                  previous_origin,
                  new_origin,
                  previous_authority,
                  new_authority,
                  version_no,
                  reason
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
                  %s
                )
                RETURNING event_id::text
                """,
                (
                    material_id,
                    str(current["assignment_id"]),
                    assignment_id,
                    str(current.get("source_origin") or "unknown"),
                    normalized_origin,
                    str(current.get("source_authority") or "external_reference"),
                    normalized_authority,
                    next_version,
                    bounded_reason,
                ),
            ).fetchone()
            row = connection.execute(
                """
                UPDATE hxy_product_materials
                SET source_origin = %s,
                    source_authority = %s,
                    authority_version = %s,
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
                          source_origin,
                          source_authority,
                          authority_version,
                          official_use_allowed,
                          created_at,
                          updated_at
                """,
                (
                    normalized_origin,
                    normalized_authority,
                    next_version,
                    str(current["assignment_id"]),
                    material_id,
                ),
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
                          source_origin,
                          source_authority,
                          authority_version,
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
