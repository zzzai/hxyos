from __future__ import annotations

import importlib
import importlib.util
import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "data" / "migrations" / "021_hxy_operating_loop.sql"
SCRIPT = ROOT / "scripts" / "run-hxy-outbox-worker.py"
ORGANIZATION_ID = "10000000-0000-0000-0000-000000000001"
MESSAGE_ID = "70000000-0000-0000-0000-000000000001"
AGGREGATE_ID = "71000000-0000-0000-0000-000000000001"
ATTEMPT_ID = "72000000-0000-0000-0000-000000000001"
NOW = datetime(2026, 7, 18, 8, 0, tzinfo=timezone.utc)


class Result:
    def __init__(
        self,
        row: dict[str, Any] | None = None,
        *,
        rows: list[dict[str, Any]] | None = None,
        rowcount: int = 0,
    ):
        self.row = row
        self.rows = rows or []
        self.rowcount = rowcount

    def fetchone(self):
        return self.row

    def fetchall(self):
        return self.rows


def _message_row(
    *,
    attempt_count: int = 0,
    max_attempts: int = 5,
    topic: str = "understand.inbound.issue",
) -> dict[str, Any]:
    return {
        "outbox_message_id": MESSAGE_ID,
        "organization_id": ORGANIZATION_ID,
        "topic": topic,
        "aggregate_type": "inbound_envelope",
        "aggregate_id": AGGREGATE_ID,
        "payload": {"envelope_id": AGGREGATE_ID},
        "idempotency_key": "feishu:event-1",
        "status": "pending",
        "attempt_count": attempt_count,
        "max_attempts": max_attempts,
        "created_at": NOW,
    }


def test_claim_next_uses_skip_locked_and_appends_a_leased_attempt() -> None:
    module = importlib.import_module("apps.api.hxy_product.outbox_repository")
    repository = module.OutboxRepository("postgresql://outbox.test/hxy")
    calls: list[tuple[str, tuple[Any, ...]]] = []

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, sql: str, params: tuple[Any, ...]):
            normalized = " ".join(sql.split())
            calls.append((normalized, params))
            if "FOR UPDATE SKIP LOCKED" in normalized:
                return Result(_message_row())
            if "UPDATE hxy_outbox_messages" in normalized:
                return Result(_message_row(attempt_count=1) | {"status": "leased"})
            if "INSERT INTO hxy_outbox_attempts" in normalized:
                return Result({"attempt_id": ATTEMPT_ID})
            raise AssertionError(normalized)

    repository.connect = lambda: Connection()

    message = repository.claim_next("worker-a", lease_seconds=120)

    assert message is not None
    assert message["outbox_message_id"] == MESSAGE_ID
    assert message["attempt_number"] == 1
    assert message["attempt_id"] == ATTEMPT_ID
    assert any("FOR UPDATE SKIP LOCKED" in sql for sql, _ in calls)
    assert any("status IN ('pending', 'retryable_failed')" in sql for sql, _ in calls)
    attempt_insert = next(
        (sql, params) for sql, params in calls if "INSERT INTO hxy_outbox_attempts" in sql
    )
    assert "'leased'" in attempt_insert[0]
    assert "UPDATE hxy_outbox_attempts" not in " ".join(sql for sql, _ in calls)


def test_complete_requires_current_lease_owner_and_appends_success() -> None:
    module = importlib.import_module("apps.api.hxy_product.outbox_repository")
    repository = module.OutboxRepository("postgresql://outbox.test/hxy")
    calls: list[str] = []

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, sql: str, _params: tuple[Any, ...]):
            normalized = " ".join(sql.split())
            calls.append(normalized)
            if "FOR UPDATE" in normalized and "lease_owner" in normalized:
                return Result(_message_row(attempt_count=1) | {"status": "leased"})
            if "INSERT INTO hxy_outbox_attempts" in normalized:
                return Result({"attempt_id": ATTEMPT_ID})
            if "UPDATE hxy_outbox_messages" in normalized:
                return Result({"status": "succeeded"})
            raise AssertionError(normalized)

    repository.connect = lambda: Connection()

    status = repository.complete(
        MESSAGE_ID,
        "worker-a",
        result={"proposal_id": "proposal-1"},
    )

    assert status == "succeeded"
    assert any("outcome" in sql and "'succeeded'" in sql for sql in calls)
    assert any("status = 'succeeded'" in sql for sql in calls)
    assert not any("UPDATE hxy_outbox_attempts" in sql for sql in calls)


def test_complete_rejects_a_worker_that_does_not_own_the_lease() -> None:
    module = importlib.import_module("apps.api.hxy_product.outbox_repository")
    repository = module.OutboxRepository("postgresql://outbox.test/hxy")

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, sql: str, _params: tuple[Any, ...]):
            normalized = " ".join(sql.split())
            if "FOR UPDATE" in normalized and "lease_owner" in normalized:
                return Result(None)
            raise AssertionError(normalized)

    repository.connect = lambda: Connection()

    try:
        repository.complete(MESSAGE_ID, "worker-b", result={})
    except module.OutboxLeaseLost as error:
        assert "lease" in str(error).lower()
    else:
        raise AssertionError("OutboxLeaseLost was not raised")


def test_renew_lease_requires_current_owner_and_extends_expiry() -> None:
    module = importlib.import_module("apps.api.hxy_product.outbox_repository")
    repository = module.OutboxRepository("postgresql://outbox.test/hxy")
    calls: list[tuple[str, tuple[Any, ...]]] = []

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, sql: str, params: tuple[Any, ...]):
            normalized = " ".join(sql.split())
            calls.append((normalized, params))
            return Result({"status": "leased"})

    repository.connect = lambda: Connection()

    status = repository.renew_lease(MESSAGE_ID, "worker-a", lease_seconds=120)

    assert status == "leased"
    sql, params = calls[0]
    assert "lease_expires_at = NOW() + (%s * INTERVAL '1 second')" in sql
    assert "lease_owner = %s" in sql
    assert "lease_expires_at > NOW()" in sql
    assert params == (120, MESSAGE_ID, "worker-a")


def test_fail_uses_exponential_retry_delay_capped_at_one_hour() -> None:
    module = importlib.import_module("apps.api.hxy_product.outbox_repository")
    repository = module.OutboxRepository("postgresql://outbox.test/hxy")
    calls: list[tuple[str, tuple[Any, ...]]] = []

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, sql: str, params: tuple[Any, ...]):
            normalized = " ".join(sql.split())
            calls.append((normalized, params))
            if "FOR UPDATE" in normalized and "lease_owner" in normalized:
                return Result(_message_row(attempt_count=10, max_attempts=20) | {"status": "leased"})
            if "INSERT INTO hxy_outbox_attempts" in normalized:
                return Result({"attempt_id": ATTEMPT_ID})
            if "UPDATE hxy_outbox_messages" in normalized:
                return Result({"status": "retryable_failed"})
            raise AssertionError(normalized)

    repository.connect = lambda: Connection()

    status = repository.fail(
        MESSAGE_ID,
        "worker-a",
        retryable=True,
        error_code="model_timeout",
        error_summary="model timed out",
        base_retry_seconds=30,
    )

    assert status == "retryable_failed"
    update_params = next(
        params for sql, params in calls if "UPDATE hxy_outbox_messages" in sql
    )
    assert 3600 in update_params
    assert any("'retryable_failed'" in sql for sql, _ in calls)
    assert not any("UPDATE hxy_outbox_attempts" in sql for sql, _ in calls)


@pytest.mark.parametrize(
    "topic",
    ("understand.inbound.issue", "understand.organization_record"),
)
def test_fail_dead_letters_understanding_topics_and_retains_history(
    topic: str,
) -> None:
    module = importlib.import_module("apps.api.hxy_product.outbox_repository")
    repository = module.OutboxRepository("postgresql://outbox.test/hxy")
    calls: list[str] = []

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, sql: str, _params: tuple[Any, ...]):
            normalized = " ".join(sql.split())
            calls.append(normalized)
            if "FOR UPDATE" in normalized and "lease_owner" in normalized:
                return Result(
                    _message_row(
                        attempt_count=5,
                        max_attempts=5,
                        topic=topic,
                    )
                    | {"status": "leased"}
                )
            if "INSERT INTO hxy_outbox_attempts" in normalized:
                return Result({"attempt_id": ATTEMPT_ID})
            if "UPDATE hxy_outbox_messages" in normalized:
                return Result({"status": "dead_letter"})
            if "UPDATE hxy_inbound_envelopes" in normalized:
                return Result({"envelope_id": AGGREGATE_ID})
            raise AssertionError(normalized)

    repository.connect = lambda: Connection()

    status = repository.fail(
        MESSAGE_ID,
        "worker-a",
        retryable=True,
        error_code="still_failing",
        error_summary="attempt budget exhausted",
        base_retry_seconds=15,
    )

    assert status == "dead_letter"
    assert any("'dead_letter'" in sql for sql in calls)
    attention_sql = next(sql for sql in calls if "UPDATE hxy_inbound_envelopes" in sql)
    assert "status = 'needs_attention'" in attention_sql
    assert "status IN ('received', 'queued', 'needs_attention')" in attention_sql
    assert not any("DELETE FROM hxy_outbox_attempts" in sql for sql in calls)
    assert not any("UPDATE hxy_outbox_attempts" in sql for sql in calls)


def test_reclaim_stale_leases_appends_final_attempts_and_requeues_or_dead_letters() -> None:
    module = importlib.import_module("apps.api.hxy_product.outbox_repository")
    repository = module.OutboxRepository("postgresql://outbox.test/hxy")
    calls: list[str] = []

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, sql: str, _params: tuple[Any, ...] = ()):
            normalized = " ".join(sql.split())
            calls.append(normalized)
            if "WITH stale AS" in normalized:
                return Result(
                    rows=[
                        {"outbox_message_id": MESSAGE_ID, "status": "retryable_failed"},
                        {
                            "outbox_message_id": "70000000-0000-0000-0000-000000000002",
                            "status": "dead_letter",
                        },
                    ]
                )
            raise AssertionError(normalized)

    repository.connect = lambda: Connection()

    reclaimed = repository.reclaim_stale_leases(limit=10)

    assert reclaimed == 2
    statement = calls[0]
    assert "FOR UPDATE SKIP LOCKED" in statement
    assert "INSERT INTO hxy_outbox_attempts" in statement
    assert "retryable_failed" in statement
    assert "dead_letter" in statement
    assert "lease_expired" in statement
    assert "UPDATE hxy_inbound_envelopes" in statement
    assert "UPDATE hxy_outbox_attempts" not in statement
    assert "message.topic IN (" in statement
    assert "'understand.inbound.issue'" in statement
    assert "'understand.organization_record'" in statement
    assert "topic LIKE" not in statement


def test_database_and_claim_contract_prevent_duplicate_execution() -> None:
    sql = " ".join(MIGRATION.read_text(encoding="utf-8").split())
    assert "UNIQUE (organization_id, topic, idempotency_key)" in sql

    module = importlib.import_module("apps.api.hxy_product.outbox_repository")
    repository = module.OutboxRepository("postgresql://outbox.test/hxy")
    statements: list[str] = []

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, sql: str, _params: tuple[Any, ...]):
            normalized = " ".join(sql.split())
            statements.append(normalized)
            return Result(None)

    repository.connect = lambda: Connection()

    assert repository.claim_next("worker-a", lease_seconds=60) is None
    assert "status IN ('pending', 'retryable_failed')" in statements[0]
    assert "succeeded" not in statements[0].split("status IN", 1)[1].split(")", 1)[0]


def test_worker_dispatches_by_topic_and_completes_the_message() -> None:
    module = importlib.import_module("apps.api.hxy_product.outbox_worker")
    message = _message_row(attempt_count=1) | {"attempt_number": 1}

    class Repository:
        def __init__(self):
            self.completed: tuple[str, str, dict[str, Any]] | None = None

        def reclaim_stale_leases(self, *, limit: int):
            assert limit == 100
            return 0

        def claim_next(self, worker_id: str, *, lease_seconds: int):
            assert worker_id == "worker-a"
            assert lease_seconds == 120
            return message

        def complete(self, message_id: str, worker_id: str, *, result: dict[str, Any]):
            self.completed = (message_id, worker_id, result)
            return "succeeded"

    repository = Repository()
    seen_payloads: list[dict[str, Any]] = []

    result = module.process_one_outbox_message(
        repository,
        {"understand.inbound.issue": lambda payload: seen_payloads.append(payload) or {"ok": True}},
        worker_id="worker-a",
        lease_seconds=120,
        base_retry_seconds=15,
    )

    assert result == {"status": "succeeded", "outbox_message_id": MESSAGE_ID}
    assert len(seen_payloads) == 1
    assert seen_payloads[0]["envelope_id"] == AGGREGATE_ID
    execution_scope = seen_payloads[0]["_hxy_outbox"]
    assert execution_scope["outbox_message_id"] == MESSAGE_ID
    assert execution_scope["organization_id"] == ORGANIZATION_ID
    assert execution_scope["aggregate_type"] == "inbound_envelope"
    assert execution_scope["aggregate_id"] == AGGREGATE_ID
    assert execution_scope["attempt_number"] == 1
    assert execution_scope["max_attempts"] == 5
    assert execution_scope["worker_id"] == "worker-a"
    assert callable(execution_scope["assert_lease"])
    assert repository.completed == (MESSAGE_ID, "worker-a", {"ok": True})


def test_worker_marks_retryable_handler_errors_without_losing_the_message() -> None:
    module = importlib.import_module("apps.api.hxy_product.outbox_worker")
    message = _message_row(attempt_count=1) | {"attempt_number": 1}

    class Repository:
        def reclaim_stale_leases(self, *, limit: int):
            return 0

        def claim_next(self, _worker_id: str, *, lease_seconds: int):
            return message

        def fail(self, message_id: str, worker_id: str, **kwargs):
            assert message_id == MESSAGE_ID
            assert worker_id == "worker-a"
            assert kwargs == {
                "retryable": True,
                "error_code": "invalid_model_json",
                "error_summary": "model returned invalid JSON",
                "base_retry_seconds": 15,
            }
            return "retryable_failed"

    def failing_handler(_payload: dict[str, Any]):
        raise module.OutboxHandlerError(
            "invalid_model_json",
            "model returned invalid JSON",
            retryable=True,
        )

    result = module.process_one_outbox_message(
        Repository(),
        {"understand.inbound.issue": failing_handler},
        worker_id="worker-a",
        lease_seconds=120,
        base_retry_seconds=15,
    )

    assert result == {
        "status": "retryable_failed",
        "outbox_message_id": MESSAGE_ID,
        "error_code": "invalid_model_json",
    }


def test_worker_renews_the_lease_while_a_long_handler_runs() -> None:
    module = importlib.import_module("apps.api.hxy_product.outbox_worker")
    message = _message_row(attempt_count=1) | {"attempt_number": 1}

    class Repository:
        def __init__(self):
            self.renewals = 0

        def reclaim_stale_leases(self, *, limit: int):
            return 0

        def claim_next(self, _worker_id: str, *, lease_seconds: int):
            return message

        def renew_lease(self, _message_id: str, _worker_id: str, *, lease_seconds: int):
            self.renewals += 1
            return "leased"

        def complete(self, _message_id: str, _worker_id: str, *, result: dict[str, Any]):
            return "succeeded"

    repository = Repository()

    def long_handler(_payload: dict[str, Any]) -> dict[str, Any]:
        time.sleep(0.45)
        return {"ok": True}

    result = module.process_one_outbox_message(
        repository,
        {"understand.inbound.issue": long_handler},
        worker_id="worker-a",
        lease_seconds=1,
        base_retry_seconds=15,
    )

    assert result["status"] == "succeeded"
    assert repository.renewals >= 1


def test_worker_fences_handler_side_effects_after_lease_loss() -> None:
    worker_module = importlib.import_module("apps.api.hxy_product.outbox_worker")
    repository_module = importlib.import_module("apps.api.hxy_product.outbox_repository")
    message = _message_row(attempt_count=1) | {"attempt_number": 1}
    side_effects: list[str] = []

    class Repository:
        def reclaim_stale_leases(self, *, limit: int):
            return 0

        def claim_next(self, _worker_id: str, *, lease_seconds: int):
            return message

        def renew_lease(self, _message_id: str, _worker_id: str, *, lease_seconds: int):
            raise repository_module.OutboxLeaseLost("lease was reclaimed")

        def complete(self, *_args, **_kwargs):
            raise AssertionError("lost lease must not complete")

    def fenced_handler(payload: dict[str, Any]) -> dict[str, Any]:
        time.sleep(0.45)
        payload["_hxy_outbox"]["assert_lease"]()
        side_effects.append("persisted")
        return {"ok": True}

    result = worker_module.process_one_outbox_message(
        Repository(),
        {"understand.inbound.issue": fenced_handler},
        worker_id="worker-a",
        lease_seconds=1,
        base_retry_seconds=15,
    )

    assert result == {"status": "lost_lease", "outbox_message_id": MESSAGE_ID}
    assert side_effects == []


def test_cli_registers_issue_understanding_and_closed_event_metric_handlers() -> None:
    spec = importlib.util.spec_from_file_location("hxy_outbox_worker_cli", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    handlers = module.build_handlers(
        "postgresql://outbox.test/hxy",
        channel_repository=object(),
        operating_repository=object(),
        model_router=object(),
        metrics_repository=object(),
    )

    assert set(handlers) == {
        "understand.inbound.issue",
        "metrics.operating_event.closed",
    }
    assert callable(handlers["understand.inbound.issue"])
    assert callable(handlers["metrics.operating_event.closed"])


def test_cli_fails_closed_with_json_when_database_is_not_configured() -> None:
    environment = dict(os.environ)
    environment.pop("HXY_DATABASE_URL", None)

    completed = subprocess.run(
        [str(SCRIPT), "--once"],
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 2
    assert json.loads(completed.stdout) == {
        "status": "error",
        "error_code": "database_not_configured",
    }
