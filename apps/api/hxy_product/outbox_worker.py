from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from .outbox_repository import OutboxLeaseLost


OutboxHandler = Callable[[dict[str, Any]], dict[str, Any]]


class OutboxHandlerError(Exception):
    def __init__(
        self,
        code: str,
        summary: str,
        *,
        retryable: bool,
    ):
        super().__init__(summary)
        self.code = code.strip()[:100] or "handler_error"
        self.summary = " ".join(summary.split())[:2000] or "outbox handler failed"
        self.retryable = retryable


def process_one_outbox_message(
    repository: Any,
    handlers: Mapping[str, OutboxHandler],
    *,
    worker_id: str,
    lease_seconds: int,
    base_retry_seconds: int,
) -> dict[str, str]:
    repository.reclaim_stale_leases(limit=100)
    message = repository.claim_next(worker_id, lease_seconds=lease_seconds)
    if message is None:
        return {"status": "idle"}

    message_id = str(message["outbox_message_id"])
    topic = str(message["topic"])
    try:
        handler = handlers.get(topic)
        if handler is None:
            raise OutboxHandlerError(
                "handler_not_registered",
                f"no handler is registered for topic {topic}",
                retryable=True,
            )
        result = handler(dict(message.get("payload") or {}))
        if not isinstance(result, dict):
            raise OutboxHandlerError(
                "invalid_handler_result",
                "outbox handler must return an object",
                retryable=False,
            )
        status = repository.complete(message_id, worker_id, result=result)
        return {"status": str(status), "outbox_message_id": message_id}
    except OutboxLeaseLost:
        return {"status": "lost_lease", "outbox_message_id": message_id}
    except OutboxHandlerError as error:
        try:
            status = repository.fail(
                message_id,
                worker_id,
                retryable=error.retryable,
                error_code=error.code,
                error_summary=error.summary,
                base_retry_seconds=base_retry_seconds,
            )
        except OutboxLeaseLost:
            return {"status": "lost_lease", "outbox_message_id": message_id}
        return {
            "status": str(status),
            "outbox_message_id": message_id,
            "error_code": error.code,
        }
    except Exception:
        try:
            status = repository.fail(
                message_id,
                worker_id,
                retryable=True,
                error_code="handler_error",
                error_summary="outbox handler raised an unexpected error",
                base_retry_seconds=base_retry_seconds,
            )
        except OutboxLeaseLost:
            return {"status": "lost_lease", "outbox_message_id": message_id}
        return {
            "status": str(status),
            "outbox_message_id": message_id,
            "error_code": "handler_error",
        }
