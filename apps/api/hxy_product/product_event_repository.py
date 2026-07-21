from __future__ import annotations

from typing import Any

try:
    import psycopg
    from psycopg.rows import dict_row
except Exception:  # pragma: no cover - deployment dependency may be installed later
    psycopg = None
    dict_row = None


class ProductEventConflict(RuntimeError):
    pass


def _public_event(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "event_id": str(row["product_event_id"]),
        "event_name": str(row["event_name"]),
        "created_at": row["created_at"],
    }


class ProductEventRepository:
    def __init__(self, database_url: str):
        if not database_url:
            raise ValueError("database_url is required")
        if psycopg is None:
            raise RuntimeError("psycopg is not installed")
        self.database_url = database_url

    def connect(self):
        return psycopg.connect(self.database_url, row_factory=dict_row)

    def briefing_source_is_accessible(
        self,
        *,
        organization_id: str,
        store_id: str | None,
        assignment_id: str,
        role: str,
        subject_id: str,
    ) -> bool:
        if role in {"founder", "hq_operations"}:
            scope_sql = ""
            scope_params: tuple[Any, ...] = ()
        elif role == "store_manager" and store_id:
            scope_sql = " AND envelope.store_id = %s"
            scope_params = (store_id,)
        elif role == "store_employee":
            scope_sql = " AND envelope.sender_assignment_id = %s::uuid"
            scope_params = (assignment_id,)
        else:
            return False
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT EXISTS (
                  SELECT 1
                  FROM hxy_inbound_envelopes AS envelope
                  JOIN hxy_ai_proposals AS proposal
                    ON proposal.organization_id = envelope.organization_id
                   AND proposal.source_envelope_id = envelope.envelope_id
                   AND proposal.proposal_type = 'organization_record_understanding'
                   AND proposal.status = 'proposed'
                  WHERE envelope.organization_id = %s::uuid
                    AND envelope.envelope_id = %s::uuid
                    AND envelope.intent_hint = 'organization_record'
                """
                + scope_sql
                + """
                ) AS accessible
                """,
                (organization_id, subject_id, *scope_params),
            ).fetchone()
        return bool(row and row.get("accessible"))

    def append_event(
        self,
        *,
        organization_id: str,
        store_id: str | None,
        assignment_id: str,
        client_event_id: str,
        event_name: str,
        subject_id: str,
        useful: bool | None,
    ) -> dict[str, Any]:
        values = (
            organization_id,
            store_id,
            assignment_id,
            client_event_id,
            event_name,
            subject_id,
            useful,
        )
        with self.connect() as connection:
            row = connection.execute(
                """
                INSERT INTO hxy_product_events (
                  organization_id, store_id, assignment_id, client_event_id,
                  event_name, subject_id, useful
                )
                VALUES (%s::uuid, %s, %s::uuid, %s::uuid, %s, %s::uuid, %s)
                ON CONFLICT DO NOTHING
                RETURNING *
                """,
                values,
            ).fetchone()
            if row is None:
                by_client = connection.execute(
                    """
                    SELECT *
                    FROM hxy_product_events
                    WHERE organization_id = %s::uuid
                      AND assignment_id = %s::uuid
                      AND client_event_id = %s::uuid
                    """,
                    (organization_id, assignment_id, client_event_id),
                ).fetchone()
                row = by_client
                if row is None:
                    row = connection.execute(
                        """
                        SELECT *
                        FROM hxy_product_events
                        WHERE organization_id = %s::uuid
                          AND assignment_id = %s::uuid
                          AND event_name = %s
                          AND subject_id = %s::uuid
                        """,
                        (organization_id, assignment_id, event_name, subject_id),
                    ).fetchone()
                if row is None:
                    raise RuntimeError("product event insert failed")
                existing = (
                    str(row["organization_id"]),
                    str(row["store_id"]) if row.get("store_id") is not None else None,
                    str(row["assignment_id"]),
                    str(row["event_name"]),
                    str(row["subject_id"]),
                    row.get("useful"),
                )
                expected = (
                    organization_id,
                    store_id,
                    assignment_id,
                    event_name,
                    subject_id,
                    useful,
                )
                if existing != expected or (
                    by_client is not None
                    and str(row["client_event_id"]) != client_event_id
                ):
                    raise ProductEventConflict("client event id already has different values")
        return _public_event(row)
