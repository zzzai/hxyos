from __future__ import annotations

import json
import re
from typing import Any
from uuid import uuid4

try:
    import psycopg
    from psycopg.rows import dict_row
except Exception:  # pragma: no cover - deployment dependency may be installed later
    psycopg = None
    dict_row = None


class EvidenceError(RuntimeError):
    status_code = 400


class EvidenceNotFound(EvidenceError):
    status_code = 404


class EvidencePermissionDenied(EvidenceError):
    status_code = 403


class EvidenceStateConflict(EvidenceError):
    status_code = 409


class EvidenceAssetRejected(EvidenceError):
    status_code = 422


_HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_MANAGEMENT_ROLES = frozenset({"founder", "hq_operations", "store_manager"})
_STORE_ROLES = frozenset({"store_manager", "store_employee"})
_TYPE_RULES = {
    "photo": (
        frozenset({".jpeg", ".jpg", ".png", ".webp"}),
        frozenset({"image/jpeg", "image/png", "image/webp"}),
    ),
    "audio": (
        frozenset({".m4a", ".mp3", ".ogg", ".wav"}),
        frozenset({"audio/mp4", "audio/mpeg", "audio/ogg", "audio/wav", "audio/x-wav"}),
    ),
    "video": (
        frozenset({".mov", ".mp4", ".webm"}),
        frozenset({"video/mp4", "video/quicktime", "video/webm"}),
    ),
    "document": (
        frozenset({".doc", ".docx", ".pdf", ".ppt", ".pptx", ".xls", ".xlsx"}),
        frozenset(
            {
                "application/msword",
                "application/pdf",
                "application/vnd.ms-excel",
                "application/vnd.ms-powerpoint",
                "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            }
        ),
    ),
    "text": (
        frozenset({".csv", ".json", ".md", ".txt"}),
        frozenset({"application/json", "text/csv", "text/markdown", "text/plain"}),
    ),
    "system_record": (
        frozenset({".csv", ".json", ".pdf", ".txt"}),
        frozenset({"application/json", "application/pdf", "text/csv", "text/plain"}),
    ),
}


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


def validate_evidence_asset(
    asset: dict[str, Any],
    *,
    evidence_type: str,
    expected_store_id: str,
    max_bytes: int,
) -> None:
    rules = _TYPE_RULES.get(evidence_type)
    if rules is None:
        raise EvidenceAssetRejected("unsupported evidence type")
    if str(asset.get("status") or "") == "archived":
        raise EvidenceAssetRejected("source asset is archived")
    if str(asset.get("scan_status") or "") != "clean":
        raise EvidenceAssetRejected("source asset has not passed safety scanning")
    asset_store_id = str(asset.get("store_id") or "")
    if asset_store_id and asset_store_id != expected_store_id:
        raise EvidenceAssetRejected("source asset is outside the task store")
    try:
        size_bytes = int(asset.get("size_bytes") or 0)
    except (TypeError, ValueError):
        size_bytes = 0
    if size_bytes <= 0 or size_bytes > max_bytes:
        raise EvidenceAssetRejected("source asset size is invalid")
    extension = str(asset.get("extension") or "").lower()
    media_type = str(asset.get("media_type") or "").lower()
    allowed_extensions, allowed_media_types = rules
    if extension not in allowed_extensions or media_type not in allowed_media_types:
        raise EvidenceAssetRejected("source asset type does not match evidence type")
    if not _HASH_PATTERN.fullmatch(str(asset.get("sha256") or "")):
        raise EvidenceAssetRejected("source asset hash is invalid")


def _asset_is_visible(asset: dict[str, Any], actor: dict[str, Any]) -> bool:
    scope = _json_object(asset.get("visibility_scope"))
    role = str(actor.get("role") or "")
    actor_id = str(actor.get("assignment_id") or "")
    if scope.get("uploader") is True and str(asset.get("assignment_id") or "") == actor_id:
        return True
    if scope.get("store_employee") is True and role == "store_employee":
        return True
    if scope.get("store_manager") is True and role == "store_manager":
        return True
    if scope.get("hq") is True and role in {"founder", "hq_operations"}:
        return True
    allowed = scope.get("assignment_ids")
    return isinstance(allowed, list) and actor_id in {str(value) for value in allowed}


class EvidenceRepository:
    def __init__(self, database_url: str, *, max_evidence_bytes: int) -> None:
        if not database_url:
            raise ValueError("database_url is required")
        if max_evidence_bytes <= 0:
            raise ValueError("max_evidence_bytes must be positive")
        if psycopg is None:
            raise RuntimeError("psycopg is not installed")
        self.database_url = database_url
        self.max_evidence_bytes = max_evidence_bytes

    def connect(self):
        return psycopg.connect(self.database_url, row_factory=dict_row)

    @staticmethod
    def _load_existing(
        connection: Any,
        *,
        organization_id: str,
        actor_assignment_id: str,
        client_evidence_id: str,
    ) -> dict[str, Any] | None:
        return connection.execute(
            """
            SELECT evidence.evidence_id::text,
                   evidence.operating_event_id::text,
                   evidence.workflow_instance_id::text,
                   evidence.task_id::text,
                   evidence.client_evidence_id::text,
                   evidence.evidence_type,
                   evidence.source_asset_id::text,
                   evidence.statement,
                   evidence.created_by_assignment_id::text,
                   evidence.created_at
            FROM hxy_operating_evidence AS evidence
            WHERE evidence.organization_id = %s::uuid
              AND evidence.created_by_assignment_id = %s::uuid
              AND evidence.client_evidence_id = %s::uuid
            LIMIT 1
            """,
            (organization_id, actor_assignment_id, client_evidence_id),
        ).fetchone()

    @staticmethod
    def _return_matching_existing(
        existing: dict[str, Any],
        *,
        task_id: str,
        source_asset_id: str,
        evidence_type: str,
        statement: str,
    ) -> dict[str, Any]:
        expected = (task_id, source_asset_id, evidence_type, statement)
        actual = (
            str(existing.get("task_id") or ""),
            str(existing.get("source_asset_id") or ""),
            str(existing.get("evidence_type") or ""),
            str(existing.get("statement") or ""),
        )
        if actual != expected:
            raise EvidenceStateConflict("client evidence id was already used")
        return dict(existing)

    def create_evidence(
        self,
        *,
        organization_id: str,
        store_id: str,
        task_id: str,
        client_evidence_id: str,
        source_asset_id: str,
        evidence_type: str,
        statement: str,
        actor_assignment_id: str,
    ) -> dict[str, Any]:
        normalized_statement = statement.strip()
        with self.connect() as connection:
            actor = connection.execute(
                """
                SELECT assignment_id::text, organization_id::text, store_id, role, status
                FROM hxy_role_assignments
                WHERE organization_id = %s::uuid
                  AND assignment_id = %s::uuid
                  AND status = 'active'
                FOR SHARE
                """,
                (organization_id, actor_assignment_id),
            ).fetchone()
            if actor is None:
                raise EvidencePermissionDenied("active actor assignment was not found")
            role = str(actor.get("role") or "")
            if role in _STORE_ROLES and str(actor.get("store_id") or "") != store_id:
                raise EvidenceNotFound("operating task was not found")
            if role not in _MANAGEMENT_ROLES and role != "store_employee":
                raise EvidencePermissionDenied("actor role cannot submit evidence")

            existing = self._load_existing(
                connection,
                organization_id=organization_id,
                actor_assignment_id=actor_assignment_id,
                client_evidence_id=client_evidence_id,
            )
            if existing is not None:
                return self._return_matching_existing(
                    dict(existing),
                    task_id=task_id,
                    source_asset_id=source_asset_id,
                    evidence_type=evidence_type,
                    statement=normalized_statement,
                )

            task = connection.execute(
                """
                SELECT task.task_id::text,
                       task.organization_id::text,
                       task.store_id,
                       task.operating_event_id::text,
                       task.workflow_instance_id::text,
                       task.assignee_assignment_id::text,
                       task.status
                FROM hxy_product_tasks AS task
                WHERE task.organization_id = %s::uuid
                  AND task.store_id = %s
                  AND task.task_id = %s::uuid
                  AND task.operating_event_id IS NOT NULL
                  AND task.workflow_instance_id IS NOT NULL
                FOR SHARE OF task
                """,
                (organization_id, store_id, task_id),
            ).fetchone()
            if task is None:
                raise EvidenceNotFound("operating task was not found")
            if str(task.get("status") or "") not in {"in_progress", "rework"}:
                raise EvidenceStateConflict("task is not accepting evidence")
            if role == "store_employee" and str(task.get("assignee_assignment_id") or "") != actor_assignment_id:
                raise EvidencePermissionDenied("actor is not assigned to this task")

            asset = connection.execute(
                """
                SELECT material.material_id::text,
                       material.assignment_id::text,
                       material.organization_id::text,
                       material.store_id,
                       material.extension,
                       material.media_type,
                       material.size_bytes,
                       material.sha256,
                       material.status,
                       material.scan_status,
                       material.visibility_scope
                FROM hxy_product_materials AS material
                WHERE material.organization_id = %s::uuid
                  AND material.material_id = %s::uuid
                FOR SHARE OF material
                """,
                (organization_id, source_asset_id),
            ).fetchone()
            if asset is None:
                raise EvidenceNotFound("source asset was not found")
            validate_evidence_asset(
                dict(asset),
                evidence_type=evidence_type,
                expected_store_id=store_id,
                max_bytes=self.max_evidence_bytes,
            )
            if not _asset_is_visible(dict(asset), dict(actor)):
                raise EvidencePermissionDenied("source asset is outside the actor scope")

            evidence_id = str(uuid4())
            evidence = connection.execute(
                """
                INSERT INTO hxy_operating_evidence (
                  evidence_id,
                  organization_id,
                  store_id,
                  operating_event_id,
                  workflow_instance_id,
                  task_id,
                  evidence_type,
                  source_asset_id,
                  statement,
                  visibility_scope,
                  created_by_assignment_id,
                  client_evidence_id
                )
                VALUES (
                  %s::uuid, %s::uuid, %s, %s::uuid, %s::uuid, %s::uuid,
                  %s, %s::uuid, %s, %s::jsonb, %s::uuid, %s::uuid
                )
                ON CONFLICT (
                  organization_id,
                  created_by_assignment_id,
                  client_evidence_id
                ) WHERE client_evidence_id IS NOT NULL DO NOTHING
                RETURNING evidence_id::text,
                          operating_event_id::text,
                          workflow_instance_id::text,
                          task_id::text,
                          client_evidence_id::text,
                          evidence_type,
                          source_asset_id::text,
                          statement,
                          created_by_assignment_id::text,
                          created_at
                """,
                (
                    evidence_id,
                    organization_id,
                    store_id,
                    str(task["operating_event_id"]),
                    str(task["workflow_instance_id"]),
                    task_id,
                    evidence_type,
                    source_asset_id,
                    normalized_statement,
                    json.dumps(
                        {"store_id": store_id, "hq": True, "task_assignee": True},
                        ensure_ascii=False,
                    ),
                    actor_assignment_id,
                    client_evidence_id,
                ),
            ).fetchone()
            if evidence is None:
                existing = self._load_existing(
                    connection,
                    organization_id=organization_id,
                    actor_assignment_id=actor_assignment_id,
                    client_evidence_id=client_evidence_id,
                )
                if existing is None:  # pragma: no cover - database invariant
                    raise RuntimeError("idempotent evidence could not be loaded")
                return self._return_matching_existing(
                    dict(existing),
                    task_id=task_id,
                    source_asset_id=source_asset_id,
                    evidence_type=evidence_type,
                    statement=normalized_statement,
                )
            connection.execute(
                """
                INSERT INTO hxy_asset_bindings (
                  organization_id,
                  source_type,
                  source_id,
                  target_type,
                  target_id,
                  relation_type,
                  created_by_assignment_id
                )
                VALUES (
                  %s::uuid, 'source_asset', %s::uuid,
                  'evidence', %s::uuid, 'evidence_for', %s::uuid
                )
                ON CONFLICT DO NOTHING
                """,
                (organization_id, source_asset_id, evidence_id, actor_assignment_id),
            )
        return dict(evidence)
