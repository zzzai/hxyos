from __future__ import annotations

import json
from typing import Any

try:
    import psycopg
    from psycopg.rows import dict_row
except Exception:  # pragma: no cover - deployment dependency may be installed later
    psycopg = None
    dict_row = None


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


def _message_from_row(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    payload = _json_object(row.get("answer_payload"))
    message_id = row.get("message_id") or row.get("id")
    return {
        "id": str(message_id),
        "conversation_id": str(row["conversation_id"]),
        "role": str(row["role"]),
        "content": str(row.get("content") or ""),
        "created_at": row["created_at"],
        "answer_id": str(row["answer_id"]) if row.get("answer_id") else None,
        "answer_status": payload.get("answer_status"),
        "confidence": payload.get("confidence"),
        "needs_review": payload.get("needs_review"),
        "sources": payload.get("sources") if isinstance(payload.get("sources"), list) else [],
        "next_actions": (
            payload.get("next_actions") if isinstance(payload.get("next_actions"), list) else []
        ),
    }


def _conversation_from_row(row: dict[str, Any]) -> dict[str, Any]:
    last_message = row.get("last_message")
    if isinstance(last_message, str):
        try:
            last_message = json.loads(last_message)
        except ValueError:
            last_message = None
    return {
        "id": str(row.get("conversation_id") or row.get("id")),
        "assignment_id": str(row["assignment_id"]),
        "title": str(row.get("title") or "新对话"),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "last_message_at": row.get("last_message_at"),
        "message_count": int(row.get("message_count") or 0),
        "last_message": _message_from_row(last_message) if isinstance(last_message, dict) else None,
    }


_CONVERSATION_SELECT = """
    SELECT conversation_id::text,
           assignment_id::text,
           title,
           message_count,
           created_at,
           updated_at,
           last_message_at,
           (
             SELECT jsonb_build_object(
               'message_id', hxy_product_messages.message_id::text,
               'conversation_id', hxy_product_messages.conversation_id::text,
               'role', hxy_product_messages.role,
               'content', hxy_product_messages.content,
               'answer_id', hxy_product_messages.answer_id::text,
               'answer_payload', hxy_product_messages.answer_payload,
               'created_at', hxy_product_messages.created_at
             )
             FROM hxy_product_messages
             WHERE hxy_product_messages.assignment_id = hxy_product_conversations.assignment_id
               AND hxy_product_messages.conversation_id = hxy_product_conversations.conversation_id
             ORDER BY hxy_product_messages.created_at DESC, hxy_product_messages.message_id DESC
             LIMIT 1
           ) AS last_message
    FROM hxy_product_conversations
"""


class ConversationRepository:
    def __init__(self, database_url: str):
        if not database_url:
            raise ValueError("database_url is required")
        if psycopg is None:
            raise RuntimeError("psycopg is not installed")
        self.database_url = database_url

    def connect(self):
        return psycopg.connect(self.database_url, row_factory=dict_row)

    def create_conversation(self, assignment_id: str) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute(
                """
                INSERT INTO hxy_product_conversations (assignment_id)
                VALUES (%s::uuid)
                RETURNING conversation_id::text,
                          assignment_id::text,
                          title,
                          message_count,
                          created_at,
                          updated_at,
                          last_message_at,
                          NULL::jsonb AS last_message
                """,
                (assignment_id,),
            ).fetchone()
        return _conversation_from_row(row)

    def list_conversations(self, assignment_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                _CONVERSATION_SELECT
                + """
                WHERE assignment_id = %s::uuid
                ORDER BY updated_at DESC, conversation_id DESC
                LIMIT %s
                """,
                (assignment_id, limit),
            ).fetchall()
        return [_conversation_from_row(row) for row in rows]

    def get_conversation(
        self,
        assignment_id: str,
        conversation_id: str,
    ) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                _CONVERSATION_SELECT
                + """
                WHERE assignment_id = %s::uuid
                  AND conversation_id = %s::uuid
                LIMIT 1
                """,
                (assignment_id, conversation_id),
            ).fetchone()
        return _conversation_from_row(row) if row else None

    def list_messages(
        self,
        assignment_id: str,
        conversation_id: str,
    ) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT message_id::text,
                       conversation_id::text,
                       role,
                       content,
                       answer_id::text,
                       answer_payload,
                       created_at
                FROM hxy_product_messages
                WHERE assignment_id = %s::uuid
                  AND conversation_id = %s::uuid
                ORDER BY created_at, message_id
                """,
                (assignment_id, conversation_id),
            ).fetchall()
        return [_message_from_row(row) for row in rows]

    def reserve_user_message(
        self,
        assignment_id: str,
        conversation_id: str,
        client_message_id: str,
        content: str,
    ) -> dict[str, Any] | None:
        with self.connect() as connection:
            conversation = connection.execute(
                """
                SELECT conversation_id::text
                FROM hxy_product_conversations
                WHERE assignment_id = %s::uuid
                  AND conversation_id = %s::uuid
                FOR UPDATE
                """,
                (assignment_id, conversation_id),
            ).fetchone()
            if conversation is None:
                return None

            user_row = connection.execute(
                """
                INSERT INTO hxy_product_messages (
                  assignment_id,
                  conversation_id,
                  role,
                  content,
                  client_message_id,
                  generation_status,
                  generation_started_at
                )
                VALUES (%s::uuid, %s::uuid, 'user', %s, %s::uuid, 'processing', NOW())
                ON CONFLICT (assignment_id, client_message_id) DO NOTHING
                RETURNING message_id::text,
                          conversation_id::text,
                          role,
                          content,
                          answer_id::text,
                          answer_payload,
                          generation_status,
                          created_at
                """,
                (assignment_id, conversation_id, content, client_message_id),
            ).fetchone()
            if user_row is not None:
                return {
                    "state": "reserved",
                    "user_message": _message_from_row(user_row),
                    "assistant_message": None,
                }

            user_row = connection.execute(
                """
                SELECT message_id::text,
                       conversation_id::text,
                       role,
                       content,
                       answer_id::text,
                       answer_payload,
                       generation_status,
                       generation_started_at,
                       created_at
                FROM hxy_product_messages
                WHERE assignment_id = %s::uuid
                  AND client_message_id = %s::uuid
                  AND role = 'user'
                FOR UPDATE
                """,
                (assignment_id, client_message_id),
            ).fetchone()
            if user_row is None:
                return {"state": "conflict", "user_message": None, "assistant_message": None}
            if str(user_row["conversation_id"]) != conversation_id or str(user_row["content"]) != content:
                return {
                    "state": "conflict",
                    "user_message": _message_from_row(user_row),
                    "assistant_message": None,
                }

            assistant_row = connection.execute(
                """
                SELECT message_id::text,
                       conversation_id::text,
                       role,
                       content,
                       answer_id::text,
                       answer_payload,
                       created_at
                FROM hxy_product_messages
                WHERE assignment_id = %s::uuid
                  AND conversation_id = %s::uuid
                  AND reply_to_message_id = %s::uuid
                  AND role = 'assistant'
                LIMIT 1
                """,
                (assignment_id, conversation_id, user_row["message_id"]),
            ).fetchone()
            if assistant_row is not None:
                return {
                    "state": "completed",
                    "user_message": _message_from_row(user_row),
                    "assistant_message": _message_from_row(assistant_row),
                }

            reclaimed_row = connection.execute(
                """
                UPDATE hxy_product_messages
                SET generation_status = 'processing',
                    generation_started_at = NOW(),
                    updated_at = NOW()
                WHERE assignment_id = %s::uuid
                  AND conversation_id = %s::uuid
                  AND message_id = %s::uuid
                  AND (
                    generation_status IN ('pending', 'failed')
                    OR (
                      generation_status = 'processing'
                      AND (
                        generation_started_at IS NULL
                        OR generation_started_at < NOW() - INTERVAL '5 minutes'
                      )
                    )
                  )
                RETURNING message_id::text,
                          conversation_id::text,
                          role,
                          content,
                          answer_id::text,
                          answer_payload,
                          generation_status,
                          created_at
                """,
                (assignment_id, conversation_id, user_row["message_id"]),
            ).fetchone()
            if reclaimed_row is not None:
                return {
                    "state": "reserved",
                    "user_message": _message_from_row(reclaimed_row),
                    "assistant_message": None,
                }
            return {
                "state": "processing",
                "user_message": _message_from_row(user_row),
                "assistant_message": None,
            }

    def complete_assistant_message(
        self,
        assignment_id: str,
        conversation_id: str,
        user_message_id: str,
        client_message_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        answer_id = payload.get("answer_id") or None
        with self.connect() as connection:
            user_row = connection.execute(
                """
                SELECT message_id::text, content
                FROM hxy_product_messages
                WHERE assignment_id = %s::uuid
                  AND conversation_id = %s::uuid
                  AND message_id = %s::uuid
                  AND client_message_id = %s::uuid
                  AND role = 'user'
                FOR UPDATE
                """,
                (assignment_id, conversation_id, user_message_id, client_message_id),
            ).fetchone()
            if user_row is None:
                return None

            assistant_row = connection.execute(
                """
                INSERT INTO hxy_product_messages (
                  assignment_id,
                  conversation_id,
                  role,
                  content,
                  reply_to_message_id,
                  answer_id,
                  answer_payload,
                  generation_status
                )
                VALUES (
                  %s::uuid,
                  %s::uuid,
                  'assistant',
                  %s,
                  %s::uuid,
                  %s::uuid,
                  %s::jsonb,
                  'completed'
                )
                ON CONFLICT (assignment_id, conversation_id, reply_to_message_id) DO NOTHING
                RETURNING message_id::text,
                          conversation_id::text,
                          role,
                          content,
                          answer_id::text,
                          answer_payload,
                          created_at
                """,
                (
                    assignment_id,
                    conversation_id,
                    payload["answer"],
                    user_message_id,
                    answer_id,
                    json.dumps(payload, ensure_ascii=False),
                ),
            ).fetchone()
            if assistant_row is None:
                assistant_row = connection.execute(
                    """
                    SELECT message_id::text,
                           conversation_id::text,
                           role,
                           content,
                           answer_id::text,
                           answer_payload,
                           created_at
                    FROM hxy_product_messages
                    WHERE assignment_id = %s::uuid
                      AND conversation_id = %s::uuid
                      AND reply_to_message_id = %s::uuid
                      AND role = 'assistant'
                    LIMIT 1
                    """,
                    (assignment_id, conversation_id, user_message_id),
                ).fetchone()
            if assistant_row is None:
                return None

            connection.execute(
                """
                UPDATE hxy_product_messages
                SET generation_status = 'completed', updated_at = NOW()
                WHERE assignment_id = %s::uuid
                  AND conversation_id = %s::uuid
                  AND message_id = %s::uuid
                """,
                (assignment_id, conversation_id, user_message_id),
            )
            connection.execute(
                """
                UPDATE hxy_product_conversations
                SET title = CASE WHEN title = '新对话' THEN left(%s, 40) ELSE title END,
                    message_count = (
                      SELECT COUNT(*)
                      FROM hxy_product_messages
                      WHERE assignment_id = %s::uuid
                        AND conversation_id = %s::uuid
                    ),
                    last_message_at = %s,
                    updated_at = NOW()
                WHERE assignment_id = %s::uuid
                  AND conversation_id = %s::uuid
                """,
                (
                    str(user_row["content"]),
                    assignment_id,
                    conversation_id,
                    assistant_row["created_at"],
                    assignment_id,
                    conversation_id,
                ),
            )
        return _message_from_row(assistant_row)

    def mark_generation_failed(
        self,
        assignment_id: str,
        conversation_id: str,
        user_message_id: str,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE hxy_product_messages
                SET generation_status = 'failed', updated_at = NOW()
                WHERE assignment_id = %s::uuid
                  AND conversation_id = %s::uuid
                  AND message_id = %s::uuid
                  AND role = 'user'
                  AND generation_status = 'processing'
                """,
                (assignment_id, conversation_id, user_message_id),
            )
