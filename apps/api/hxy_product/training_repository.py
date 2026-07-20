from __future__ import annotations

import json
from typing import Any

try:
    import psycopg
    from psycopg.rows import dict_row
except Exception:  # pragma: no cover - deployment dependency may be installed later
    psycopg = None
    dict_row = None


class ProductTrainingRepository:
    def __init__(self, database_url: str):
        if not database_url:
            raise ValueError("database_url is required")
        if psycopg is None:
            raise RuntimeError("psycopg is not installed")
        self.database_url = database_url

    def connect(self):
        return psycopg.connect(self.database_url, row_factory=dict_row)

    def save_training_session(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self.connect() as connection:
            assignment = connection.execute(
                """
                SELECT assignment_id::text
                FROM hxy_role_assignments
                WHERE organization_id = %s::uuid
                  AND store_id = %s
                  AND assignment_id = %s::uuid
                  AND status = 'active'
                FOR UPDATE
                """,
                (
                    payload["organization_id"],
                    payload["store_id"],
                    payload["assignment_id"],
                ),
            ).fetchone()
            if assignment is None:
                raise ValueError("active store assignment is required")

            row = connection.execute(
                """
                INSERT INTO hxy_product_training_sessions (
                  organization_id, store_id, assignment_id,
                  customer_question, employee_answer,
                  score, level, needs_retrain,
                  standard_script, correction_points
                )
                VALUES (
                  %s::uuid, %s, %s::uuid,
                  %s, %s,
                  %s, %s, %s,
                  %s, %s::jsonb
                )
                RETURNING training_session_id::text
                """,
                (
                    payload["organization_id"],
                    payload["store_id"],
                    payload["assignment_id"],
                    payload["customer_question"],
                    payload["employee_answer"],
                    payload["score"],
                    payload["level"],
                    payload["needs_retrain"],
                    payload["standard_script"],
                    json.dumps(payload["correction_points"], ensure_ascii=False),
                ),
            ).fetchone()
        return {"id": str(row["training_session_id"])}

    def list_assignment_sessions(
        self,
        *,
        organization_id: str,
        assignment_id: str,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        bounded_limit = min(100, max(1, int(limit)))
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT training_session_id::text AS id,
                       customer_question,
                       employee_answer,
                       score,
                       level,
                       needs_retrain,
                       standard_script,
                       correction_points,
                       created_at
                FROM hxy_product_training_sessions
                WHERE organization_id = %s::uuid
                  AND assignment_id = %s::uuid
                ORDER BY created_at DESC, training_session_id DESC
                LIMIT %s
                """,
                (organization_id, assignment_id, bounded_limit),
            ).fetchall()
        return [dict(row) for row in rows]
