from __future__ import annotations

import json
from typing import Any

try:
    import psycopg
    from psycopg.rows import dict_row
except Exception:  # pragma: no cover - deployment dependency may be installed later
    psycopg = None
    dict_row = None


class TaskStateConflict(RuntimeError):
    pass


def _task_from_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row.get("task_id") or row.get("id")),
        "organization_id": str(row["organization_id"]),
        "store_id": str(row["store_id"]) if row.get("store_id") is not None else None,
        "creator_assignment_id": str(row["creator_assignment_id"]),
        "assignee_assignment_id": (
            str(row["assignee_assignment_id"])
            if row.get("assignee_assignment_id") is not None
            else None
        ),
        "source_conversation_id": (
            str(row["source_conversation_id"])
            if row.get("source_conversation_id") is not None
            else None
        ),
        "source_message_id": (
            str(row["source_message_id"])
            if row.get("source_message_id") is not None
            else None
        ),
        "parent_task_id": (
            str(row["parent_task_id"])
            if row.get("parent_task_id") is not None
            else None
        ),
        "operating_event_id": (
            str(row["operating_event_id"])
            if row.get("operating_event_id") is not None
            else None
        ),
        "workflow_instance_id": (
            str(row["workflow_instance_id"])
            if row.get("workflow_instance_id") is not None
            else None
        ),
        "title": str(row["title"]),
        "details": str(row.get("details") or ""),
        "priority": str(row["priority"]),
        "visibility": str(row["visibility"]),
        "status": str(row["status"]),
        "result": str(row["result"]) if row.get("result") is not None else None,
        "due_at": row.get("due_at"),
        "accepted_at": row.get("accepted_at"),
        "completed_at": row.get("completed_at"),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


class TaskRepository:
    def __init__(self, database_url: str):
        if not database_url:
            raise ValueError("database_url is required")
        if psycopg is None:
            raise RuntimeError("psycopg is not installed")
        self.database_url = database_url

    def connect(self):
        return psycopg.connect(self.database_url, row_factory=dict_row)

    def list_tasks(
        self,
        *,
        assignment_id: str,
        organization_id: str,
        store_id: str | None,
        role: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        organization_wide = role in {"founder", "hq_operations"}
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM hxy_product_tasks
                WHERE organization_id = %s::uuid
                  AND (
                    %s
                    OR creator_assignment_id = %s::uuid
                    OR assignee_assignment_id = %s::uuid
                    OR (visibility = 'store' AND store_id = %s)
                  )
                ORDER BY
                  CASE
                    WHEN status IN ('in_progress', 'submitted', 'rework') THEN 0
                    WHEN status IN ('open', 'assigned') THEN 1
                    ELSE 2
                  END,
                  CASE priority
                    WHEN 'urgent' THEN 4
                    WHEN 'high' THEN 3
                    WHEN 'normal' THEN 2
                    ELSE 1
                  END DESC,
                  updated_at DESC
                LIMIT %s
                """,
                (
                    organization_id,
                    organization_wide,
                    assignment_id,
                    assignment_id,
                    store_id,
                    limit,
                ),
            ).fetchall()
        return [_task_from_row(row) for row in rows]

    def create_task(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute(
                """
                INSERT INTO hxy_product_tasks (
                  organization_id, store_id, creator_assignment_id,
                  assignee_assignment_id, source_conversation_id, source_message_id,
                  parent_task_id, title, details, priority, visibility, due_at
                )
                VALUES (
                  %s::uuid, %s, %s::uuid, %s::uuid, %s::uuid, %s::uuid,
                  %s::uuid, %s, %s, %s, %s, %s
                )
                RETURNING *
                """,
                (
                    payload["organization_id"],
                    payload.get("store_id"),
                    payload["creator_assignment_id"],
                    payload.get("assignee_assignment_id"),
                    payload.get("source_conversation_id"),
                    payload.get("source_message_id"),
                    payload.get("parent_task_id"),
                    payload["title"],
                    payload.get("details") or "",
                    payload["priority"],
                    payload["visibility"],
                    payload.get("due_at"),
                ),
            ).fetchone()
            connection.execute(
                """
                INSERT INTO hxy_product_task_events (
                  organization_id, task_id, actor_assignment_id, event_type, payload
                )
                VALUES (%s::uuid, %s::uuid, %s::uuid, 'created', %s::jsonb)
                """,
                (
                    payload["organization_id"],
                    row["task_id"],
                    payload["creator_assignment_id"],
                    json.dumps({"status": "open"}),
                ),
            )
        return _task_from_row(row)

    def source_message_owned_by_assignment(
        self,
        assignment_id: str,
        source_conversation_id: str,
        source_message_id: str,
    ) -> bool:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT 1
                FROM hxy_product_messages
                WHERE hxy_product_messages.assignment_id = %s::uuid
                  AND hxy_product_messages.conversation_id = %s::uuid
                  AND hxy_product_messages.message_id = %s::uuid
                  AND hxy_product_messages.role = 'assistant'
                LIMIT 1
                """,
                (assignment_id, source_conversation_id, source_message_id),
            ).fetchone()
        return row is not None

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM hxy_product_tasks WHERE task_id = %s::uuid",
                (task_id,),
            ).fetchone()
        return _task_from_row(row) if row else None

    def update_task(
        self,
        task_id: str,
        *,
        actor_assignment_id: str,
        status: str,
        result: str | None,
    ) -> dict[str, Any] | None:
        with self.connect() as connection:
            current = connection.execute(
                "SELECT * FROM hxy_product_tasks WHERE task_id = %s::uuid FOR UPDATE",
                (task_id,),
            ).fetchone()
            if current is None:
                return None
            if current.get("operating_event_id") is not None:
                raise TaskStateConflict("operating task requires governed workflow")
            if current["status"] in {"completed", "cancelled"}:
                raise TaskStateConflict("task is already closed")
            row = connection.execute(
                """
                UPDATE hxy_product_tasks
                SET status = %s,
                    result = %s,
                    completed_at = CASE WHEN %s = 'completed' THEN NOW() ELSE NULL END,
                    updated_at = NOW()
                WHERE task_id = %s::uuid
                RETURNING *
                """,
                (status, result, status, task_id),
            ).fetchone()
            connection.execute(
                """
                INSERT INTO hxy_product_task_events (
                  organization_id, task_id, actor_assignment_id, event_type, payload
                )
                VALUES (%s::uuid, %s::uuid, %s::uuid, %s, %s::jsonb)
                """,
                (
                    current["organization_id"],
                    task_id,
                    actor_assignment_id,
                    status,
                    json.dumps({"from": current["status"], "to": status, "result": result}),
                ),
            )
        return _task_from_row(row)
