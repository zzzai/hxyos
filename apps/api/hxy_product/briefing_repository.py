from __future__ import annotations

from typing import Any

from .record_repository import RecordAccessDenied

try:
    import psycopg
    from psycopg.rows import dict_row
except Exception:  # pragma: no cover - deployment dependency may be installed later
    psycopg = None
    dict_row = None


_BRIEFING_SELECT = """
    SELECT envelope.envelope_id::text AS id,
           envelope.received_at AS captured_at,
           proposal.payload AS interpretation
    FROM hxy_inbound_envelopes AS envelope
    JOIN LATERAL (
      SELECT current_proposal.payload
      FROM hxy_ai_proposals AS current_proposal
      WHERE current_proposal.organization_id = envelope.organization_id
        AND current_proposal.source_envelope_id = envelope.envelope_id
        AND current_proposal.proposal_type = 'organization_record_understanding'
        AND current_proposal.status = 'proposed'
      ORDER BY current_proposal.created_at DESC,
               current_proposal.proposal_id DESC
      LIMIT 1
    ) AS proposal ON TRUE
"""

_BRIEFING_PRIORITY_ORDER = """
    CASE
      WHEN EXISTS (
        SELECT 1
        FROM jsonb_array_elements(
          COALESCE(proposal.payload -> 'risks', '[]'::jsonb)
        ) AS item
        WHERE item ->> 'severity' = 'critical'
          AND jsonb_array_length(
            COALESCE(item -> 'evidence', '[]'::jsonb)
          ) > 0
      ) THEN 0
      WHEN EXISTS (
        SELECT 1
        FROM jsonb_array_elements(
          COALESCE(proposal.payload -> 'risks', '[]'::jsonb)
        ) AS item
        WHERE item ->> 'severity' = 'high'
          AND jsonb_array_length(
            COALESCE(item -> 'evidence', '[]'::jsonb)
          ) > 0
      ) THEN 1
      WHEN EXISTS (
        SELECT 1
        FROM jsonb_array_elements(
          COALESCE(proposal.payload -> 'decisions', '[]'::jsonb)
        ) AS item
        WHERE jsonb_array_length(
          COALESCE(item -> 'evidence', '[]'::jsonb)
        ) > 0
      ) THEN 2
      WHEN EXISTS (
        SELECT 1
        FROM jsonb_array_elements(
          COALESCE(proposal.payload -> 'progress', '[]'::jsonb)
        ) AS item
        WHERE jsonb_array_length(
          COALESCE(item -> 'evidence', '[]'::jsonb)
        ) > 0
      ) THEN 3
      WHEN EXISTS (
        SELECT 1
        FROM jsonb_array_elements(
          COALESCE(proposal.payload -> 'risks', '[]'::jsonb)
        ) AS item
        WHERE item ->> 'severity' = 'medium'
          AND jsonb_array_length(
            COALESCE(item -> 'evidence', '[]'::jsonb)
          ) > 0
      ) THEN 4
      WHEN EXISTS (
        SELECT 1
        FROM jsonb_array_elements(
          COALESCE(proposal.payload -> 'risks', '[]'::jsonb)
        ) AS item
        WHERE item ->> 'severity' = 'low'
          AND jsonb_array_length(
            COALESCE(item -> 'evidence', '[]'::jsonb)
          ) > 0
      ) THEN 5
      ELSE 6
    END
"""


class BriefingRepository:
    def __init__(self, database_url: str):
        if not database_url:
            raise ValueError("database_url is required")
        if psycopg is None:
            raise RuntimeError("psycopg is not installed")
        self.database_url = database_url

    def connect(self):
        return psycopg.connect(self.database_url, row_factory=dict_row)

    @staticmethod
    def _read_scope(
        role: str,
        store_id: str | None,
        assignment_id: str,
    ) -> tuple[str, tuple[Any, ...]]:
        if role in {"founder", "hq_operations"}:
            return "", ()
        if role == "store_manager" and store_id:
            return " AND envelope.store_id = %s", (store_id,)
        if role == "store_employee" and assignment_id:
            return " AND envelope.sender_assignment_id = %s::uuid", (assignment_id,)
        raise RecordAccessDenied("role cannot read organization briefings")

    def list_briefing_records(
        self,
        *,
        organization_id: str,
        assignment_id: str,
        role: str,
        store_id: str | None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        scope_sql, scope_params = self._read_scope(role, store_id, assignment_id)
        sql = (
            _BRIEFING_SELECT
            + " WHERE envelope.organization_id = %s::uuid"
            + " AND envelope.intent_hint = 'organization_record'"
            + scope_sql
            + " ORDER BY "
            + _BRIEFING_PRIORITY_ORDER
            + ", envelope.received_at DESC, envelope.envelope_id DESC LIMIT %s"
        )
        params = (
            organization_id,
            *scope_params,
            max(1, min(int(limit), 100)),
        )
        with self.connect() as connection:
            rows = connection.execute(sql, params).fetchall()
        return [dict(row) for row in rows]
