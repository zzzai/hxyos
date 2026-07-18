from __future__ import annotations

import json
from typing import Any

try:
    import psycopg
    from psycopg.rows import dict_row
except Exception:  # pragma: no cover - deployment dependency may be installed later
    psycopg = None
    dict_row = None


class OutboxLeaseLost(Exception):
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


def _message_from_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "outbox_message_id": str(row["outbox_message_id"]),
        "organization_id": str(row["organization_id"]),
        "topic": str(row["topic"]),
        "aggregate_type": str(row["aggregate_type"]),
        "aggregate_id": str(row["aggregate_id"]),
        "payload": _json_object(row.get("payload")),
        "idempotency_key": str(row["idempotency_key"]),
        "status": str(row["status"]),
        "attempt_count": int(row["attempt_count"]),
        "max_attempts": int(row["max_attempts"]),
        "created_at": row.get("created_at"),
    }


class OutboxRepository:
    def __init__(self, database_url: str):
        if not database_url:
            raise ValueError("database_url is required")
        if psycopg is None:
            raise RuntimeError("psycopg is not installed")
        self.database_url = database_url

    def connect(self):
        return psycopg.connect(self.database_url, row_factory=dict_row)

    def claim_next(
        self,
        worker_id: str,
        *,
        lease_seconds: int,
    ) -> dict[str, Any] | None:
        normalized_worker_id = worker_id.strip()
        if not normalized_worker_id:
            raise ValueError("worker_id is required")
        if lease_seconds < 1:
            raise ValueError("lease_seconds must be positive")

        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT outbox_message_id::text,
                       organization_id::text,
                       topic,
                       aggregate_type,
                       aggregate_id::text,
                       payload,
                       idempotency_key,
                       status,
                       attempt_count,
                       max_attempts,
                       created_at
                FROM hxy_outbox_messages
                WHERE status IN ('pending', 'retryable_failed')
                  AND available_at <= NOW()
                  AND attempt_count < max_attempts
                ORDER BY available_at, created_at, outbox_message_id
                FOR UPDATE SKIP LOCKED
                LIMIT 1
                """,
                (),
            ).fetchone()
            if row is None:
                return None

            attempt_number = int(row["attempt_count"]) + 1
            connection.execute(
                """
                UPDATE hxy_outbox_messages
                SET status = 'leased',
                    attempt_count = %s,
                    lease_owner = %s,
                    lease_expires_at = NOW() + (%s * INTERVAL '1 second'),
                    last_error_code = NULL,
                    last_error_summary = NULL,
                    updated_at = NOW()
                WHERE organization_id = %s::uuid
                  AND outbox_message_id = %s::uuid
                RETURNING outbox_message_id::text, status, attempt_count
                """,
                (
                    attempt_number,
                    normalized_worker_id,
                    lease_seconds,
                    row["organization_id"],
                    row["outbox_message_id"],
                ),
            ).fetchone()
            attempt = connection.execute(
                """
                INSERT INTO hxy_outbox_attempts (
                  organization_id,
                  outbox_message_id,
                  attempt_number,
                  worker_id,
                  outcome
                )
                VALUES (%s::uuid, %s::uuid, %s, %s, 'leased')
                RETURNING attempt_id::text
                """,
                (
                    row["organization_id"],
                    row["outbox_message_id"],
                    attempt_number,
                    normalized_worker_id,
                ),
            ).fetchone()

        return {
            **_message_from_row(row),
            "status": "leased",
            "attempt_count": attempt_number,
            "attempt_number": attempt_number,
            "attempt_id": str(attempt["attempt_id"]),
        }

    def _lock_owned_message(
        self,
        connection: Any,
        outbox_message_id: str,
        worker_id: str,
    ) -> dict[str, Any]:
        row = connection.execute(
            """
            SELECT outbox_message_id::text,
                   organization_id::text,
                   attempt_count,
                   max_attempts,
                   lease_owner
            FROM hxy_outbox_messages
            WHERE outbox_message_id = %s::uuid
              AND status = 'leased'
              AND lease_owner = %s
              AND lease_expires_at > NOW()
            FOR UPDATE
            """,
            (outbox_message_id, worker_id.strip()),
        ).fetchone()
        if row is None:
            raise OutboxLeaseLost("outbox message lease is no longer owned")
        return row

    def complete(
        self,
        outbox_message_id: str,
        worker_id: str,
        *,
        result: dict[str, Any],
    ) -> str:
        with self.connect() as connection:
            message = self._lock_owned_message(connection, outbox_message_id, worker_id)
            connection.execute(
                """
                INSERT INTO hxy_outbox_attempts (
                  organization_id,
                  outbox_message_id,
                  attempt_number,
                  worker_id,
                  started_at,
                  finished_at,
                  outcome,
                  result
                )
                SELECT leased.organization_id,
                       leased.outbox_message_id,
                       leased.attempt_number,
                       leased.worker_id,
                       leased.started_at,
                       NOW(),
                       'succeeded',
                       %s::jsonb
                FROM hxy_outbox_attempts AS leased
                WHERE leased.organization_id = %s::uuid
                  AND leased.outbox_message_id = %s::uuid
                  AND leased.attempt_number = %s
                  AND leased.worker_id = %s
                  AND leased.outcome = 'leased'
                RETURNING attempt_id::text
                """,
                (
                    json.dumps(result, ensure_ascii=False),
                    message["organization_id"],
                    outbox_message_id,
                    message["attempt_count"],
                    worker_id.strip(),
                ),
            ).fetchone()
            updated = connection.execute(
                """
                UPDATE hxy_outbox_messages
                SET status = 'succeeded',
                    lease_owner = NULL,
                    lease_expires_at = NULL,
                    completed_at = NOW(),
                    updated_at = NOW()
                WHERE organization_id = %s::uuid
                  AND outbox_message_id = %s::uuid
                RETURNING status
                """,
                (message["organization_id"], outbox_message_id),
            ).fetchone()
        return str(updated["status"])

    def fail(
        self,
        outbox_message_id: str,
        worker_id: str,
        *,
        retryable: bool,
        error_code: str,
        error_summary: str,
        base_retry_seconds: int,
    ) -> str:
        with self.connect() as connection:
            message = self._lock_owned_message(connection, outbox_message_id, worker_id)
            attempt_number = int(message["attempt_count"])
            can_retry = retryable and attempt_number < int(message["max_attempts"])
            outcome = "retryable_failed" if can_retry else "dead_letter"
            retry_delay = min(
                max(base_retry_seconds, 1) * (2 ** min(max(attempt_number - 1, 0), 31)),
                3600,
            )
            bounded_code = error_code.strip()[:100] or "handler_error"
            bounded_summary = " ".join(error_summary.split())[:2000] or "outbox handler failed"
            connection.execute(
                f"""
                INSERT INTO hxy_outbox_attempts (
                  organization_id,
                  outbox_message_id,
                  attempt_number,
                  worker_id,
                  started_at,
                  finished_at,
                  outcome,
                  error_code,
                  error_summary
                )
                SELECT leased.organization_id,
                       leased.outbox_message_id,
                       leased.attempt_number,
                       leased.worker_id,
                       leased.started_at,
                       NOW(),
                       '{outcome}',
                       %s,
                       %s
                FROM hxy_outbox_attempts AS leased
                WHERE leased.organization_id = %s::uuid
                  AND leased.outbox_message_id = %s::uuid
                  AND leased.attempt_number = %s
                  AND leased.worker_id = %s
                  AND leased.outcome = 'leased'
                RETURNING attempt_id::text
                """,
                (
                    bounded_code,
                    bounded_summary,
                    message["organization_id"],
                    outbox_message_id,
                    attempt_number,
                    worker_id.strip(),
                ),
            ).fetchone()
            updated = connection.execute(
                """
                UPDATE hxy_outbox_messages
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
                    completed_at = CASE WHEN %s = 'dead_letter' THEN NOW() ELSE NULL END,
                    updated_at = NOW()
                WHERE organization_id = %s::uuid
                  AND outbox_message_id = %s::uuid
                RETURNING status
                """,
                (
                    outcome,
                    outcome,
                    retry_delay,
                    bounded_code,
                    bounded_summary,
                    outcome,
                    message["organization_id"],
                    outbox_message_id,
                ),
            ).fetchone()
        return str(updated["status"])

    def reclaim_stale_leases(self, *, limit: int = 100) -> int:
        if limit < 1:
            return 0
        with self.connect() as connection:
            rows = connection.execute(
                """
                WITH stale AS (
                  SELECT outbox_message_id,
                         organization_id,
                         attempt_count,
                         max_attempts,
                         lease_owner
                  FROM hxy_outbox_messages
                  WHERE status = 'leased'
                    AND lease_expires_at <= NOW()
                  ORDER BY lease_expires_at, outbox_message_id
                  FOR UPDATE SKIP LOCKED
                  LIMIT %s
                ), final_attempts AS (
                  INSERT INTO hxy_outbox_attempts (
                    organization_id,
                    outbox_message_id,
                    attempt_number,
                    worker_id,
                    started_at,
                    finished_at,
                    outcome,
                    error_code,
                    error_summary
                  )
                  SELECT stale.organization_id,
                         stale.outbox_message_id,
                         stale.attempt_count,
                         stale.lease_owner,
                         leased.started_at,
                         NOW(),
                         CASE
                           WHEN stale.attempt_count < stale.max_attempts
                             THEN 'retryable_failed'
                           ELSE 'dead_letter'
                         END,
                         'lease_expired',
                         'worker lease expired before completion'
                  FROM stale
                  JOIN hxy_outbox_attempts AS leased
                    ON leased.organization_id = stale.organization_id
                   AND leased.outbox_message_id = stale.outbox_message_id
                   AND leased.attempt_number = stale.attempt_count
                   AND leased.worker_id = stale.lease_owner
                   AND leased.outcome = 'leased'
                  ON CONFLICT (organization_id, outbox_message_id, attempt_number, outcome)
                    DO NOTHING
                  RETURNING outbox_message_id
                ), updated_messages AS (
                  UPDATE hxy_outbox_messages AS message
                  SET status = CASE
                        WHEN stale.attempt_count < stale.max_attempts
                          THEN 'retryable_failed'
                        ELSE 'dead_letter'
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
                  WHERE message.organization_id = stale.organization_id
                    AND message.outbox_message_id = stale.outbox_message_id
                  RETURNING message.outbox_message_id::text, message.status
                )
                SELECT outbox_message_id, status
                FROM updated_messages
                """,
                (min(limit, 1000),),
            ).fetchall()
        return len(rows)

    def list_attempts(
        self,
        organization_id: str,
        outbox_message_id: str,
    ) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT attempt_id::text,
                       attempt_number,
                       worker_id,
                       started_at,
                       finished_at,
                       outcome,
                       error_code,
                       error_summary,
                       result
                FROM hxy_outbox_attempts
                WHERE organization_id = %s::uuid
                  AND outbox_message_id = %s::uuid
                ORDER BY attempt_number, started_at, attempt_id
                """,
                (organization_id, outbox_message_id),
            ).fetchall()
        return [dict(row) for row in rows]
