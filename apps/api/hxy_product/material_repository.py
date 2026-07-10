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
        return _material_from_row(row)

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
