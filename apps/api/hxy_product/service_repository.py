from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime
from typing import Any

try:
    import psycopg
    from psycopg.rows import dict_row
except Exception:  # pragma: no cover - deployment dependency may be installed later
    psycopg = None
    dict_row = None


class ServiceIdempotencyConflict(RuntimeError):
    pass


class ServiceContextNotFound(LookupError):
    pass


class ServiceContextAccessDenied(PermissionError):
    pass


class ServiceAssetAccessDenied(PermissionError):
    pass


class ServiceIdentityConflict(RuntimeError):
    pass


def _canonical_datetime(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value or "").strip()


def service_request_fingerprint(payload: dict[str, Any]) -> str:
    canonical = {
        "organization_id": str(payload.get("organization_id") or ""),
        "store_id": str(payload.get("store_id") or ""),
        "created_by_assignment_id": str(payload.get("created_by_assignment_id") or ""),
        "client_context_id": str(payload.get("client_context_id") or ""),
        "occurred_at": _canonical_datetime(payload.get("occurred_at")),
        "service_label": str(payload.get("service_label") or "").strip(),
        "original_identity_hint": payload.get("original_identity_hint") or {},
    }
    encoded = json.dumps(
        canonical,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def feedback_request_fingerprint(payload: dict[str, Any]) -> str:
    canonical = {
        "organization_id": str(payload.get("organization_id") or ""),
        "store_id": str(payload.get("store_id") or ""),
        "created_by_assignment_id": str(payload.get("created_by_assignment_id") or ""),
        "context_id": str(payload.get("context_id") or ""),
        "client_feedback_id": str(payload.get("client_feedback_id") or ""),
        "text": str(payload.get("text") or "").strip(),
        "source_asset_ids": sorted(str(item) for item in payload.get("source_asset_ids") or []),
        "duration_ms": int(payload.get("duration_ms") or 0),
    }
    encoded = json.dumps(
        canonical,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def external_reference_digest(
    secret: str,
    source_system: str,
    entity_type: str,
    external_ref: str,
) -> str:
    if not secret.strip():
        raise ValueError("service identity HMAC key is required")
    message = "\n".join(
        ("hxy-service-identity-v1", source_system, entity_type, external_ref)
    ).encode("utf-8")
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


_CONTEXT_SELECT = """
    SELECT context.service_context_id::text AS id,
           context.organization_id::text,
           context.store_id,
           context.created_by_assignment_id::text,
           context.status,
           context.occurred_at,
           context.service_label,
           context.original_identity_hint,
           context.customer_subject_id::text,
           context.request_fingerprint,
           context.created_at,
           (
             SELECT COUNT(*)::integer
             FROM hxy_service_feedback AS feedback
             WHERE feedback.organization_id = context.organization_id
               AND feedback.service_context_id = context.service_context_id
           ) AS feedback_count
    FROM hxy_service_contexts AS context
"""


def _row_dict(row: Any) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


class ServiceRepository:
    def __init__(self, database_url: str):
        if not database_url:
            raise ValueError("database_url is required")
        if psycopg is None:
            raise RuntimeError("psycopg is not installed")
        self.database_url = database_url

    def connect(self):
        return psycopg.connect(self.database_url, row_factory=dict_row)

    def create_context(self, payload: dict[str, Any]) -> dict[str, Any]:
        fingerprint = service_request_fingerprint(payload)
        with self.connect() as connection:
            existing = connection.execute(
                _CONTEXT_SELECT
                + """
                WHERE context.organization_id = %s::uuid
                  AND context.created_by_assignment_id = %s::uuid
                  AND context.client_context_id = %s::uuid
                FOR UPDATE OF context
                """,
                (
                    payload["organization_id"],
                    payload["created_by_assignment_id"],
                    payload["client_context_id"],
                ),
            ).fetchone()
            if existing is not None:
                if str(existing["request_fingerprint"]) != fingerprint:
                    raise ServiceIdempotencyConflict()
                return dict(existing)

            row = connection.execute(
                """
                INSERT INTO hxy_service_contexts (
                  organization_id,
                  store_id,
                  created_by_assignment_id,
                  client_context_id,
                  occurred_at,
                  service_label,
                  original_identity_hint,
                  request_fingerprint
                )
                VALUES (%s::uuid, %s, %s::uuid, %s::uuid, %s, %s, %s::jsonb, %s)
                RETURNING service_context_id::text AS id
                """,
                (
                    payload["organization_id"],
                    payload["store_id"],
                    payload["created_by_assignment_id"],
                    payload["client_context_id"],
                    payload["occurred_at"],
                    payload["service_label"],
                    json.dumps(payload.get("original_identity_hint") or {}, ensure_ascii=False),
                    fingerprint,
                ),
            ).fetchone()
            assert row is not None
            created = connection.execute(
                _CONTEXT_SELECT
                + """
                WHERE context.organization_id = %s::uuid
                  AND context.service_context_id = %s::uuid
                """,
                (payload["organization_id"], row["id"]),
            ).fetchone()
        assert created is not None
        return dict(created)

    def list_recent_contexts(
        self,
        *,
        organization_id: str,
        store_id: str,
        assignment_id: str,
        role: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        bounded_limit = min(50, max(1, int(limit)))
        if role == "store_manager":
            access_sql = "context.store_id = %s"
            access_value = store_id
        elif role == "store_employee":
            access_sql = "context.created_by_assignment_id = %s::uuid"
            access_value = assignment_id
        else:
            raise ServiceContextAccessDenied()
        with self.connect() as connection:
            rows = connection.execute(
                _CONTEXT_SELECT
                + f"""
                WHERE context.organization_id = %s::uuid
                  AND {access_sql}
                ORDER BY context.occurred_at DESC, context.service_context_id DESC
                LIMIT %s
                """,
                (organization_id, access_value, bounded_limit),
            ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _access_clause(role: str) -> str:
        if role == "store_manager":
            return "context.store_id = %s"
        if role == "store_employee":
            return "context.created_by_assignment_id = %s::uuid"
        raise ServiceContextAccessDenied()

    def add_feedback(
        self,
        payload: dict[str, Any],
        *,
        assignment_id: str,
        role: str,
    ) -> dict[str, Any]:
        fingerprint = feedback_request_fingerprint(payload)
        access_value = payload["store_id"] if role == "store_manager" else assignment_id
        access_clause = self._access_clause(role)
        with self.connect() as connection:
            context = connection.execute(
                _CONTEXT_SELECT
                + f"""
                WHERE context.organization_id = %s::uuid
                  AND context.service_context_id = %s::uuid
                  AND context.store_id = %s
                  AND {access_clause}
                FOR UPDATE OF context
                """,
                (
                    payload["organization_id"],
                    payload["context_id"],
                    payload["store_id"],
                    access_value,
                ),
            ).fetchone()
            if context is None:
                raise ServiceContextNotFound()

            existing = connection.execute(
                """
                SELECT service_feedback_id::text AS id,
                       service_context_id::text AS context_id,
                       request_fingerprint,
                       created_at
                FROM hxy_service_feedback
                WHERE organization_id = %s::uuid
                  AND created_by_assignment_id = %s::uuid
                  AND client_feedback_id = %s::uuid
                FOR UPDATE
                """,
                (
                    payload["organization_id"],
                    payload["created_by_assignment_id"],
                    payload["client_feedback_id"],
                ),
            ).fetchone()
            if existing is not None:
                if str(existing["request_fingerprint"]) != fingerprint:
                    raise ServiceIdempotencyConflict()
                feedback = dict(existing)
            else:
                source_asset_ids = [str(item) for item in payload.get("source_asset_ids") or []]
                if source_asset_ids:
                    asset_count = connection.execute(
                        """
                        SELECT COUNT(*)::integer AS count
                        FROM hxy_product_materials
                        WHERE organization_id = %s::uuid
                          AND assignment_id = %s::uuid
                          AND material_id = ANY(%s::uuid[])
                          AND status <> 'archived'
                        """,
                        (
                            payload["organization_id"],
                            payload["created_by_assignment_id"],
                            source_asset_ids,
                        ),
                    ).fetchone()
                    if asset_count is None or int(asset_count["count"]) != len(source_asset_ids):
                        raise ServiceAssetAccessDenied()
                inserted = connection.execute(
                    """
                    INSERT INTO hxy_service_feedback (
                      organization_id,
                      store_id,
                      service_context_id,
                      created_by_assignment_id,
                      client_feedback_id,
                      feedback_text,
                      request_fingerprint,
                      duration_ms
                    )
                    VALUES (%s::uuid, %s, %s::uuid, %s::uuid, %s::uuid, %s, %s, %s)
                    RETURNING service_feedback_id::text AS id,
                              service_context_id::text AS context_id,
                              created_at
                    """,
                    (
                        payload["organization_id"],
                        payload["store_id"],
                        payload["context_id"],
                        payload["created_by_assignment_id"],
                        payload["client_feedback_id"],
                        payload["text"],
                        fingerprint,
                        payload["duration_ms"],
                    ),
                ).fetchone()
                assert inserted is not None
                feedback = dict(inserted)
                for asset_id in source_asset_ids:
                    connection.execute(
                        """
                        INSERT INTO hxy_service_feedback_assets (
                          organization_id,
                          service_feedback_id,
                          source_asset_id
                        )
                        VALUES (%s::uuid, %s::uuid, %s::uuid)
                        """,
                        (payload["organization_id"], feedback["id"], asset_id),
                    )
            updated_context = connection.execute(
                _CONTEXT_SELECT
                + """
                WHERE context.organization_id = %s::uuid
                  AND context.service_context_id = %s::uuid
                """,
                (payload["organization_id"], payload["context_id"]),
            ).fetchone()
        assert updated_context is not None
        return {
            "feedback": {
                "id": feedback["id"],
                "context_id": feedback["context_id"],
                "status": "received",
                "created_at": feedback["created_at"],
            },
            "context": dict(updated_context),
        }

    def reconcile_context(
        self,
        payload: dict[str, Any],
        *,
        assignment_id: str,
        role: str,
    ) -> dict[str, Any]:
        if role != "store_manager":
            raise ServiceContextAccessDenied()
        with self.connect() as connection:
            context = connection.execute(
                _CONTEXT_SELECT
                + """
                WHERE context.organization_id = %s::uuid
                  AND context.service_context_id = %s::uuid
                  AND context.store_id = %s
                FOR UPDATE OF context
                """,
                (
                    payload["organization_id"],
                    payload["context_id"],
                    payload["store_id"],
                ),
            ).fetchone()
            if context is None:
                raise ServiceContextNotFound()

            customer_subject_id = context.get("customer_subject_id")
            if not customer_subject_id:
                subject = connection.execute(
                    """
                    INSERT INTO hxy_customer_subjects (organization_id)
                    VALUES (%s::uuid)
                    RETURNING customer_subject_id::text
                    """,
                    (payload["organization_id"],),
                ).fetchone()
                assert subject is not None
                customer_subject_id = subject["customer_subject_id"]

            mappings = [
                ("customer", payload["external_customer_ref_hash"], customer_subject_id, None)
            ]
            if payload.get("external_service_ref_hash"):
                mappings.append(
                    ("service", payload["external_service_ref_hash"], None, payload["context_id"])
                )
            for entity_type, reference_hash, subject_id, context_id in mappings:
                existing = connection.execute(
                    """
                    SELECT customer_subject_id::text, service_context_id::text
                    FROM hxy_external_identity_mappings
                    WHERE organization_id = %s::uuid
                      AND source_system = %s
                      AND entity_type = %s
                      AND external_identifier_hash = %s
                    FOR UPDATE
                    """,
                    (
                        payload["organization_id"],
                        payload["source_system"],
                        entity_type,
                        reference_hash,
                    ),
                ).fetchone()
                if existing is not None and (
                    str(existing.get("customer_subject_id") or "") != str(subject_id or "")
                    or str(existing.get("service_context_id") or "") != str(context_id or "")
                ):
                    raise ServiceIdentityConflict()
                if existing is None:
                    connection.execute(
                        """
                        INSERT INTO hxy_external_identity_mappings (
                          organization_id,
                          source_system,
                          entity_type,
                          external_identifier_hash,
                          customer_subject_id,
                          service_context_id
                        )
                        VALUES (%s::uuid, %s, %s, %s, %s::uuid, %s::uuid)
                        """,
                        (
                            payload["organization_id"],
                            payload["source_system"],
                            entity_type,
                            reference_hash,
                            subject_id,
                            context_id,
                        ),
                    )

            connection.execute(
                """
                UPDATE hxy_service_contexts
                SET customer_subject_id = %s::uuid,
                    status = 'reconciled',
                    updated_at = NOW()
                WHERE organization_id = %s::uuid
                  AND service_context_id = %s::uuid
                """,
                (customer_subject_id, payload["organization_id"], payload["context_id"]),
            )
            connection.execute(
                """
                INSERT INTO hxy_service_context_reconciliations (
                  organization_id,
                  service_context_id,
                  customer_subject_id,
                  source_system,
                  reconciled_by_assignment_id
                )
                VALUES (%s::uuid, %s::uuid, %s::uuid, %s, %s::uuid)
                """,
                (
                    payload["organization_id"],
                    payload["context_id"],
                    customer_subject_id,
                    payload["source_system"],
                    assignment_id,
                ),
            )
            updated = connection.execute(
                _CONTEXT_SELECT
                + """
                WHERE context.organization_id = %s::uuid
                  AND context.service_context_id = %s::uuid
                """,
                (payload["organization_id"], payload["context_id"]),
            ).fetchone()
        assert updated is not None
        return dict(updated)
