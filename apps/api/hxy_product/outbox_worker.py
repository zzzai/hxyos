from __future__ import annotations

import threading
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


class _LeaseHeartbeat:
    def __init__(
        self,
        repository: Any,
        message_id: str,
        worker_id: str,
        lease_seconds: int,
    ) -> None:
        self.repository = repository
        self.message_id = message_id
        self.worker_id = worker_id
        self.lease_seconds = lease_seconds
        self.interval_seconds = max(min(lease_seconds / 3, 30), 0.25)
        self._stop = threading.Event()
        self._lost = threading.Event()
        self._thread: threading.Thread | None = None

    def __enter__(self):
        renew = getattr(self.repository, "renew_lease", None)
        if not callable(renew):
            return self
        self._thread = threading.Thread(
            target=self._run,
            name=f"hxy-outbox-heartbeat-{self.message_id}",
            daemon=True,
        )
        self._thread.start()
        return self

    def _run(self) -> None:
        while not self._stop.wait(self.interval_seconds):
            try:
                self.repository.renew_lease(
                    self.message_id,
                    self.worker_id,
                    lease_seconds=self.lease_seconds,
                )
            except OutboxLeaseLost:
                self._lost.set()
                return
            except Exception:
                self._lost.set()
                return

    def assert_owned(self) -> None:
        if self._lost.is_set():
            raise OutboxLeaseLost("outbox message lease was lost during execution")

    def __exit__(self, *_args) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=max(self.interval_seconds, 1))


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
        handler_payload = dict(message.get("payload") or {})
        handler_payload["_hxy_outbox"] = {
            "outbox_message_id": message_id,
            "organization_id": str(message["organization_id"]),
            "aggregate_type": str(message["aggregate_type"]),
            "aggregate_id": str(message["aggregate_id"]),
                "attempt_number": int(message.get("attempt_number") or 0),
                "max_attempts": int(message.get("max_attempts") or 0),
                "worker_id": worker_id,
            }
        with _LeaseHeartbeat(
            repository,
            message_id,
            worker_id,
            lease_seconds,
        ) as heartbeat:
            handler_payload["_hxy_outbox"]["assert_lease"] = heartbeat.assert_owned
            result = handler(handler_payload)
            heartbeat.assert_owned()
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
