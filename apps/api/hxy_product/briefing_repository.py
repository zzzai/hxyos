from __future__ import annotations

from typing import Any

from .briefing_schemas import PROGRESS_MAX_AGE_DAYS
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

def _evidenced_item_exists(section: str, severity: str | None = None) -> str:
    if section not in {"risks", "decisions", "progress"}:
        raise ValueError("unsupported briefing section")
    if severity is not None and severity not in {"critical", "high", "medium", "low"}:
        raise ValueError("unsupported risk severity")
    conditions = [
        "item_ordinality <= 5",
        "NULLIF(BTRIM(item ->> 'statement'), '') IS NOT NULL",
    ]
    if severity is not None:
        conditions.append(f"item ->> 'severity' = '{severity}'")
    if section == "progress":
        conditions.append(
            "envelope.received_at >= CURRENT_TIMESTAMP "
            f"- INTERVAL '{PROGRESS_MAX_AGE_DAYS} days'"
        )
    conditions.append(
        """EXISTS (
          SELECT 1
          FROM jsonb_array_elements(
            CASE
              WHEN jsonb_typeof(item -> 'evidence') = 'array'
                THEN item -> 'evidence'
              ELSE '[]'::jsonb
            END
          ) WITH ORDINALITY AS evidence_entries(evidence, evidence_ordinality)
          WHERE evidence_ordinality <= 5
            AND evidence ->> 'source_record_id' = envelope.envelope_id::text
            AND NULLIF(BTRIM(evidence ->> 'quote'), '') IS NOT NULL
        )"""
    )
    where_clause = "\n          AND ".join(conditions)
    return f"""
      EXISTS (
        SELECT 1
        FROM jsonb_array_elements(
          CASE
            WHEN jsonb_typeof(proposal.payload -> '{section}') = 'array'
              THEN proposal.payload -> '{section}'
            ELSE '[]'::jsonb
          END
        ) WITH ORDINALITY AS entries(item, item_ordinality)
        WHERE {where_clause}
      )
    """


_PRIORITY_RULES = (
    ("risks", "critical", 0),
    ("risks", "high", 1),
    ("decisions", None, 2),
    ("progress", None, 3),
    ("risks", "medium", 4),
    ("risks", "low", 5),
)

_BRIEFING_PRIORITY_ORDER = (
    "CASE "
    + " ".join(
        f"WHEN {_evidenced_item_exists(section, severity)} THEN {rank}"
        for section, severity, rank in _PRIORITY_RULES
    )
    + " ELSE 6 END"
)


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

    def has_today_closing_review(
        self,
        *,
        organization_id: str,
        store_id: str,
    ) -> bool:
        sql = """
            SELECT EXISTS (
              SELECT 1
              FROM hxy_inbound_envelopes AS envelope
              JOIN hxy_role_assignments AS assignment
                ON assignment.organization_id = envelope.organization_id
               AND assignment.assignment_id = envelope.sender_assignment_id
              WHERE envelope.organization_id = %s::uuid
                AND envelope.store_id = %s
                AND envelope.intent_hint = 'organization_record'
                AND assignment.role = 'store_manager'
                AND BTRIM(envelope.raw_text) LIKE %s
                AND envelope.received_at >= (
                  date_trunc('day', CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Shanghai')
                  AT TIME ZONE 'Asia/Shanghai'
                )
            ) AS exists
        """
        with self.connect() as connection:
            row = connection.execute(
                sql,
                (organization_id, store_id, "闭店复盘：%"),
            ).fetchone()
        return bool(row and row.get("exists"))
