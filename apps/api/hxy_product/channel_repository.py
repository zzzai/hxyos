from __future__ import annotations

import json
import re
from typing import Any

from .channel_schemas import ChannelIntakePayload
from .outbox_repository import OutboxLeaseLost, lock_outbox_execution_fence

try:
    import psycopg
    from psycopg.rows import dict_row
except Exception:  # pragma: no cover - deployment dependency may be installed later
    psycopg = None
    dict_row = None


class SourceAssetAccessDenied(Exception):
    pass


_CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_HQ_ROLES = frozenset({"founder", "hq_operations", "system_admin"})


def _sanitize_text(value: str) -> str:
    return _CONTROL_CHARACTERS.sub("", value).strip()[:20000]


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


def _envelope_from_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row["envelope_id"]),
        "organization_id": str(row["organization_id"]),
        "channel": str(row["channel"]),
        "assignment_id": (
            str(row["sender_assignment_id"])
            if row.get("sender_assignment_id") is not None
            else None
        ),
        "store_id": str(row["store_id"]) if row.get("store_id") is not None else None,
        "status": str(row["status"]),
        "received_at": row["received_at"],
    }


def _asset_is_visible(asset: dict[str, Any], assignment: dict[str, Any]) -> bool:
    scope = _json_object(asset.get("visibility_scope"))
    role = str(assignment["role"])
    assignment_id = str(assignment["assignment_id"])
    uploader_id = str(asset.get("assignment_id") or "")

    if scope.get("uploader") is True and uploader_id == assignment_id:
        return True
    if scope.get("store_manager") is True and role == "store_manager":
        return True
    if scope.get("hq") is True and role in _HQ_ROLES:
        return True
    if scope.get("store_employee") is True and role == "store_employee":
        return True
    allowed_assignments = scope.get("assignment_ids")
    return isinstance(allowed_assignments, list) and assignment_id in {
        str(value) for value in allowed_assignments
    }


class ChannelRepository:
    def __init__(self, database_url: str):
        if not database_url:
            raise ValueError("database_url is required")
        if psycopg is None:
            raise RuntimeError("psycopg is not installed")
        self.database_url = database_url

    def connect(self):
        return psycopg.connect(self.database_url, row_factory=dict_row)

    def _find_existing(
        self,
        connection: Any,
        intake: ChannelIntakePayload,
    ) -> dict[str, Any] | None:
        return connection.execute(
            """
            SELECT envelope_id::text,
                   organization_id::text,
                   channel,
                   sender_assignment_id::text,
                   store_id,
                   status,
                   received_at,
                   created_at,
                   updated_at
            FROM hxy_inbound_envelopes
            WHERE organization_id = %s::uuid
              AND channel = %s
              AND idempotency_key = %s
            LIMIT 1
            """,
            (
                str(intake.organization_id),
                intake.channel,
                intake.idempotency_key,
            ),
        ).fetchone()

    def _insert_envelope(
        self,
        connection: Any,
        intake: ChannelIntakePayload,
        *,
        assignment_id: str | None,
        store_id: str | None,
        raw_payload: dict[str, Any],
        raw_text: str,
        visibility_scope: dict[str, Any],
        status: str,
    ) -> dict[str, Any] | None:
        return connection.execute(
            """
            INSERT INTO hxy_inbound_envelopes (
              organization_id,
              channel,
              channel_tenant_id,
              channel_message_id,
              channel_thread_id,
              sender_user_id,
              sender_assignment_id,
              store_id,
              intent_hint,
              raw_payload,
              raw_text,
              idempotency_key,
              visibility_scope,
              status
            )
            VALUES (
              %s::uuid, %s, %s, %s, %s, %s, %s::uuid, %s,
              %s, %s::jsonb, %s, %s, %s::jsonb, %s
            )
            ON CONFLICT (organization_id, channel, idempotency_key) DO NOTHING
            RETURNING envelope_id::text,
                      organization_id::text,
                      channel,
                      sender_assignment_id::text,
                      store_id,
                      status,
                      received_at,
                      created_at,
                      updated_at
            """,
            (
                str(intake.organization_id),
                intake.channel,
                intake.channel_tenant_id,
                intake.channel_message_id,
                intake.channel_thread_id,
                intake.channel_user_id,
                assignment_id,
                store_id,
                intake.intent_hint,
                json.dumps(raw_payload, ensure_ascii=False),
                raw_text,
                intake.idempotency_key,
                json.dumps(visibility_scope, ensure_ascii=False),
                status,
            ),
        ).fetchone()

    def _accept_attention_envelope(
        self,
        connection: Any,
        intake: ChannelIntakePayload,
        *,
        assignment_id: str | None = None,
        store_id: str | None = None,
        reason: str,
    ) -> dict[str, Any]:
        existing = self._find_existing(connection, intake)
        if existing is not None:
            return _envelope_from_row(existing)

        row = self._insert_envelope(
            connection,
            intake,
            assignment_id=assignment_id,
            store_id=store_id,
            raw_payload={
                "unmapped_identity": assignment_id is None,
                "attention_reason": reason,
            },
            raw_text=_sanitize_text(intake.raw_text),
            visibility_scope={"system_admin": True},
            status="needs_attention",
        )
        if row is None:
            row = self._find_existing(connection, intake)
        if row is None:  # pragma: no cover - database invariant
            raise RuntimeError("idempotent inbound envelope could not be loaded")
        return _envelope_from_row(row)

    def accept_inbound(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Persist raw input and enqueue understanding atomically."""
        intake = ChannelIntakePayload.model_validate(payload)

        with self.connect() as connection:
            assignment = connection.execute(
                """
                SELECT binding.binding_id::text,
                       assignment.assignment_id::text,
                       assignment.organization_id::text,
                       assignment.store_id,
                       assignment.role
                FROM hxy_channel_identity_bindings AS binding
                JOIN hxy_role_assignments AS assignment
                  ON assignment.organization_id = binding.organization_id
                 AND assignment.assignment_id = binding.assignment_id
                JOIN hxy_organizations AS organization
                  ON organization.organization_id = assignment.organization_id
                WHERE binding.organization_id = %s::uuid
                  AND binding.channel = %s
                  AND binding.channel_tenant_id = %s
                  AND binding.channel_user_id = %s
                  AND binding.status = 'active'
                  AND assignment.status = 'active'
                  AND organization.status = 'active'
                FOR SHARE OF binding, assignment
                """,
                (
                    str(intake.organization_id),
                    intake.channel,
                    intake.channel_tenant_id,
                    intake.channel_user_id,
                ),
            ).fetchone()

            if assignment is None:
                return self._accept_attention_envelope(
                    connection,
                    intake,
                    reason="identity_unmapped",
                )

            store_id = str(assignment["store_id"]) if assignment.get("store_id") else None
            if store_id is None:
                return self._accept_attention_envelope(
                    connection,
                    intake,
                    assignment_id=str(assignment["assignment_id"]),
                    reason="store_scope_unavailable",
                )

            relationship = connection.execute(
                """
                SELECT relationship.relationship_id::text,
                       relationship.relationship_version,
                       relationship.governance_profile_id::text,
                       governance.profile_version AS governance_profile_version
                FROM hxy_store_operating_relationships AS relationship
                JOIN hxy_governance_profiles AS governance
                  ON governance.organization_id = relationship.organization_id
                 AND governance.profile_id = relationship.governance_profile_id
                WHERE relationship.organization_id = %s::uuid
                  AND relationship.store_id = %s
                  AND relationship.status = 'active'
                  AND relationship.effective_from <= NOW()
                  AND (relationship.effective_to IS NULL OR relationship.effective_to > NOW())
                  AND governance.status = 'published'
                  AND governance.effective_from <= NOW()
                  AND (governance.effective_to IS NULL OR governance.effective_to > NOW())
                FOR SHARE OF relationship, governance
                """,
                (str(intake.organization_id), store_id),
            ).fetchone()
            if relationship is None:
                return self._accept_attention_envelope(
                    connection,
                    intake,
                    assignment_id=str(assignment["assignment_id"]),
                    store_id=store_id,
                    reason="governance_scope_unavailable",
                )

            source_asset_ids = tuple(dict.fromkeys(str(value) for value in intake.source_asset_ids))
            if source_asset_ids:
                assets = connection.execute(
                    """
                    SELECT material.material_id::text,
                           material.assignment_id::text,
                           material.visibility_scope
                    FROM hxy_product_materials AS material
                    WHERE material.organization_id = %s::uuid
                      AND material.material_id = ANY(%s::uuid[])
                      AND (material.store_id IS NULL OR material.store_id = %s)
                      AND material.status <> 'archived'
                      AND material.scan_status <> 'blocked'
                    FOR SHARE OF material
                    """,
                    (str(intake.organization_id), list(source_asset_ids), store_id),
                ).fetchall()
                authorized_ids = {
                    str(asset["material_id"])
                    for asset in assets
                    if _asset_is_visible(asset, assignment)
                }
                if authorized_ids != set(source_asset_ids):
                    raise SourceAssetAccessDenied("source asset is outside the intake scope")

            existing = self._find_existing(connection, intake)
            if existing is not None:
                return _envelope_from_row(existing)

            assignment_id = str(assignment["assignment_id"])
            row = self._insert_envelope(
                connection,
                intake,
                assignment_id=assignment_id,
                store_id=store_id,
                raw_payload=intake.raw_payload,
                raw_text=_sanitize_text(intake.raw_text),
                visibility_scope={
                    "assignment_id": assignment_id,
                    "store_id": store_id,
                    "hq": True,
                },
                status="received",
            )
            if row is None:
                existing = self._find_existing(connection, intake)
                if existing is None:  # pragma: no cover - database invariant
                    raise RuntimeError("idempotent inbound envelope could not be loaded")
                return _envelope_from_row(existing)

            envelope_id = str(row["envelope_id"])
            for source_asset_id in source_asset_ids:
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
                      'inbound_envelope', %s::uuid, 'attached_to', %s::uuid
                    )
                    ON CONFLICT DO NOTHING
                    RETURNING binding_id::text
                    """,
                    (
                        str(intake.organization_id),
                        source_asset_id,
                        envelope_id,
                        assignment_id,
                    ),
                ).fetchone()

            outbox_payload = {
                "organization_id": str(intake.organization_id),
                "envelope_id": envelope_id,
                "store_id": store_id,
                "source_asset_ids": list(source_asset_ids),
                "store_operating_relationship_id": str(relationship["relationship_id"]),
                "store_operating_relationship_version": int(
                    relationship["relationship_version"]
                ),
                "governance_profile_id": str(relationship["governance_profile_id"]),
                "governance_profile_version": int(
                    relationship["governance_profile_version"]
                ),
            }
            connection.execute(
                """
                INSERT INTO hxy_outbox_messages (
                  organization_id,
                  topic,
                  aggregate_type,
                  aggregate_id,
                  payload,
                  idempotency_key
                )
                VALUES (
                  %s::uuid,
                  'understand.inbound.issue',
                  'inbound_envelope',
                  %s::uuid,
                  %s::jsonb,
                  %s
                )
                ON CONFLICT (organization_id, topic, idempotency_key) DO NOTHING
                RETURNING outbox_message_id::text
                """,
                (
                    str(intake.organization_id),
                    envelope_id,
                    json.dumps(outbox_payload, ensure_ascii=False),
                    f"{intake.channel}:{intake.idempotency_key}",
                ),
            ).fetchone()
            queued = connection.execute(
                """
                UPDATE hxy_inbound_envelopes
                SET status = 'queued',
                    updated_at = NOW()
                WHERE organization_id = %s::uuid
                  AND envelope_id = %s::uuid
                  AND status = 'received'
                RETURNING envelope_id::text,
                          organization_id::text,
                          channel,
                          sender_assignment_id::text,
                          store_id,
                          status,
                          received_at,
                          created_at,
                          updated_at
                """,
                (str(intake.organization_id), envelope_id),
            ).fetchone()

        return _envelope_from_row(queued or row)

    def load_issue_context(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        organization_id = str(payload.get("organization_id") or "").strip()
        envelope_id = str(payload.get("envelope_id") or "").strip()
        store_id = str(payload.get("store_id") or "").strip()
        relationship_id = str(
            payload.get("store_operating_relationship_id") or ""
        ).strip()
        governance_profile_id = str(payload.get("governance_profile_id") or "").strip()
        if not all(
            (
                organization_id,
                envelope_id,
                store_id,
                relationship_id,
                governance_profile_id,
            )
        ):
            raise ValueError("scoped issue context identifiers are required")

        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT envelope.envelope_id::text,
                       envelope.organization_id::text,
                       envelope.store_id,
                       envelope.sender_assignment_id::text,
                       assignment.status AS assignment_status,
                       envelope.raw_text,
                       envelope.raw_payload,
                       governance.decision_rights
                FROM hxy_inbound_envelopes AS envelope
                JOIN hxy_role_assignments AS assignment
                  ON assignment.organization_id = envelope.organization_id
                 AND assignment.assignment_id = envelope.sender_assignment_id
                JOIN hxy_store_operating_relationships AS relationship
                  ON relationship.organization_id = envelope.organization_id
                 AND relationship.store_id = envelope.store_id
                 AND relationship.relationship_id = %s::uuid
                 AND relationship.relationship_version = %s
                JOIN hxy_governance_profiles AS governance
                  ON governance.organization_id = relationship.organization_id
                 AND governance.profile_id = relationship.governance_profile_id
                 AND governance.profile_id = %s::uuid
                 AND governance.profile_version = %s
                WHERE envelope.organization_id = %s::uuid
                  AND envelope.envelope_id = %s::uuid
                  AND envelope.store_id = %s
                  AND envelope.status IN ('queued', 'processed')
                FOR SHARE OF envelope, assignment, relationship, governance
                """,
                (
                    relationship_id,
                    int(payload.get("store_operating_relationship_version") or 0),
                    governance_profile_id,
                    int(payload.get("governance_profile_version") or 0),
                    organization_id,
                    envelope_id,
                    store_id,
                ),
            ).fetchone()
            if row is None:
                return None

            assets = connection.execute(
                """
                SELECT material.material_id::text AS source_asset_id,
                       material.original_file_name AS file_name,
                       material.extension,
                       material.media_type,
                       material.storage_key,
                       material.status AS material_status,
                       normalized.storage_key AS normalized_storage_key
                FROM hxy_asset_bindings AS binding
                JOIN hxy_product_materials AS material
                  ON material.organization_id = binding.organization_id
                 AND material.material_id = binding.source_id
                LEFT JOIN LATERAL (
                  SELECT artifact.storage_key
                  FROM hxy_material_artifacts AS artifact
                  WHERE artifact.assignment_id = material.assignment_id
                    AND artifact.material_id = material.material_id
                    AND artifact.artifact_type = 'normalized_markdown'
                  ORDER BY artifact.created_at DESC, artifact.artifact_id DESC
                  LIMIT 1
                ) AS normalized ON TRUE
                WHERE binding.organization_id = %s::uuid
                  AND binding.source_type = 'source_asset'
                  AND binding.target_type = 'inbound_envelope'
                  AND binding.target_id = %s::uuid
                  AND binding.relation_type = 'attached_to'
                  AND material.status <> 'archived'
                  AND material.scan_status <> 'blocked'
                ORDER BY binding.created_at, binding.binding_id
                """,
                (organization_id, envelope_id),
            ).fetchall()

        decision_rights = _json_object(row.get("decision_rights"))
        raw_event_types = decision_rights.get("issue_event_types")
        published_event_types = []
        if isinstance(raw_event_types, list):
            published_event_types = [
                str(value).strip()[:100]
                for value in raw_event_types[:100]
                if str(value).strip()
            ]
        return {
            "organization_id": str(row["organization_id"]),
            "envelope_id": str(row["envelope_id"]),
            "store_id": str(row["store_id"]),
            "sender_assignment_id": str(row["sender_assignment_id"]),
            "assignment_is_active": str(row["assignment_status"]) == "active",
            "raw_text": _sanitize_text(str(row.get("raw_text") or "")),
            "raw_payload": _json_object(row.get("raw_payload")),
            "attachments": [dict(asset) for asset in assets],
            "published_event_types": published_event_types,
        }

    def mark_envelope_processed(
        self,
        organization_id: str,
        envelope_id: str,
        *,
        execution_fence: dict[str, Any],
    ) -> None:
        if str(execution_fence.get("organization_id") or "") != organization_id:
            raise OutboxLeaseLost("outbox fence organization does not match envelope")
        with self.connect() as connection:
            lock_outbox_execution_fence(connection, execution_fence)
            updated = connection.execute(
                """
                UPDATE hxy_inbound_envelopes
                SET status = 'processed',
                    processed_at = COALESCE(processed_at, NOW()),
                    updated_at = NOW()
                WHERE organization_id = %s::uuid
                  AND envelope_id = %s::uuid
                  AND status IN ('queued', 'processed')
                RETURNING envelope_id::text
                """,
                (organization_id, envelope_id),
            ).fetchone()
        if updated is None:
            raise ValueError("queued inbound envelope was not found")

    def issue_owner_is_active(
        self,
        organization_id: str,
        store_id: str,
        assignment_id: str,
    ) -> bool:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT EXISTS (
                  SELECT 1
                  FROM hxy_role_assignments
                  WHERE organization_id = %s::uuid
                    AND assignment_id = %s::uuid
                    AND status = 'active'
                    AND (
                      store_id = %s
                      OR role IN ('founder', 'hq_operations', 'system_admin')
                    )
                ) AS is_active
                """,
                (organization_id, assignment_id, store_id),
            ).fetchone()
        return bool(row and row.get("is_active"))

    def mark_envelope_needs_attention(
        self,
        organization_id: str,
        envelope_id: str,
        *,
        reason: str,
    ) -> None:
        del reason  # Failure detail remains in immutable outbox attempts.
        with self.connect() as connection:
            updated = connection.execute(
                """
                UPDATE hxy_inbound_envelopes
                SET status = 'needs_attention',
                    processed_at = NULL,
                    updated_at = NOW()
                WHERE organization_id = %s::uuid
                  AND envelope_id = %s::uuid
                  AND status IN ('received', 'queued', 'needs_attention')
                RETURNING envelope_id::text
                """,
                (organization_id, envelope_id),
            ).fetchone()
        if updated is None:
            raise ValueError("inbound envelope was not available for attention")
