from __future__ import annotations

from datetime import datetime, timezone

import pytest

from apps.api.hxy_product.operating_metrics import (
    CALCULATION_VERSION,
    MetricDefinitionMissing,
    calculate_closed_event_facts,
)


ORGANIZATION_ID = "10000000-0000-0000-0000-000000000001"
STORE_ID = "hxy-store-001"
EVENT_ID = "20000000-0000-0000-0000-000000000001"
OPEN_TRANSITION_ID = "30000000-0000-0000-0000-000000000001"
REWORK_TRANSITION_ID = "30000000-0000-0000-0000-000000000002"
ACCEPT_TRANSITION_ID = "30000000-0000-0000-0000-000000000003"
CLOSE_TRANSITION_ID = "30000000-0000-0000-0000-000000000004"
TASK_ID = "50000000-0000-0000-0000-000000000001"
OTHER_TASK_ID = "50000000-0000-0000-0000-000000000099"


def at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 7, 19, hour, minute, tzinfo=timezone.utc)


def definitions(*, status: str = "published") -> list[dict[str, object]]:
    return [
        {
            "metric_definition_id": f"40000000-0000-0000-0000-00000000000{index}",
            "metric_key": key,
            "metric_version": 1,
            "status": status,
        }
        for index, key in enumerate(
            (
                "issue_closure_duration_seconds",
                "issue_overdue_duration_seconds",
                "issue_rework_count",
                "issue_acceptance_count",
            ),
            start=1,
        )
    ]


def transitions() -> list[dict[str, object]]:
    return [
        {
            "transition_id": OPEN_TRANSITION_ID,
            "aggregate_type": "operating_event",
            "aggregate_id": EVENT_ID,
            "from_state": None,
            "to_state": "open",
            "occurred_at": at(9),
        },
        {
            "transition_id": REWORK_TRANSITION_ID,
            "aggregate_type": "task",
            "aggregate_id": TASK_ID,
            "from_state": "submitted",
            "to_state": "rework",
            "occurred_at": at(9, 10),
        },
        {
            "transition_id": ACCEPT_TRANSITION_ID,
            "aggregate_type": "task",
            "aggregate_id": TASK_ID,
            "from_state": "submitted",
            "to_state": "accepted",
            "occurred_at": at(9, 20),
        },
        {
            "transition_id": CLOSE_TRANSITION_ID,
            "aggregate_type": "operating_event",
            "aggregate_id": EVENT_ID,
            "from_state": "resolved",
            "to_state": "closed",
            "occurred_at": at(9, 20),
        },
    ]


def event() -> dict[str, object]:
    return {
        "organization_id": ORGANIZATION_ID,
        "store_id": STORE_ID,
        "operating_event_id": EVENT_ID,
        "status": "closed",
        "created_at": at(9),
        "due_at": at(9, 15),
        "closed_at": at(9, 20),
    }


def test_closed_event_metrics_are_derived_only_from_timestamps_and_transitions() -> None:
    facts = calculate_closed_event_facts(
        event(), transitions(), definitions(), task_ids={TASK_ID}
    )

    assert {fact.metric_key: fact.value_numeric for fact in facts} == {
        "issue_closure_duration_seconds": 1200,
        "issue_overdue_duration_seconds": 300,
        "issue_rework_count": 1,
        "issue_acceptance_count": 1,
    }
    assert all(fact.subject_type == "operating_event" for fact in facts)
    assert all(fact.subject_id == EVENT_ID for fact in facts)
    assert all(fact.calculation_version == CALCULATION_VERSION for fact in facts)
    assert all(fact.derived_from_transition_ids for fact in facts)
    assert facts[0].window_start == at(9)
    assert facts[0].window_end == at(9, 20)


def test_metric_fact_ids_are_deterministic_for_idempotent_recalculation() -> None:
    first = calculate_closed_event_facts(
        event(), transitions(), definitions(), task_ids={TASK_ID}
    )
    second = calculate_closed_event_facts(
        event(), transitions(), definitions(), task_ids={TASK_ID}
    )

    assert [fact.metric_fact_id for fact in first] == [
        fact.metric_fact_id for fact in second
    ]
    assert len({fact.metric_fact_id for fact in first}) == 4


def test_transitions_for_unrelated_tasks_do_not_change_event_metrics() -> None:
    unrelated = {
        "transition_id": "30000000-0000-0000-0000-000000000099",
        "aggregate_type": "task",
        "aggregate_id": OTHER_TASK_ID,
        "from_state": "submitted",
        "to_state": "rework",
        "occurred_at": at(9, 12),
    }

    facts = calculate_closed_event_facts(
        event(), [*transitions(), unrelated], definitions(), task_ids={TASK_ID}
    )

    values = {fact.metric_key: fact.value_numeric for fact in facts}
    assert values["issue_rework_count"] == 1
    rework = next(fact for fact in facts if fact.metric_key == "issue_rework_count")
    assert unrelated["transition_id"] not in rework.derived_from_transition_ids


def test_overdue_duration_is_zero_when_event_closes_before_due_at() -> None:
    early = event()
    early["due_at"] = at(9, 30)

    facts = calculate_closed_event_facts(early, transitions(), definitions())

    overdue = next(
        fact for fact in facts if fact.metric_key == "issue_overdue_duration_seconds"
    )
    assert overdue.value_numeric == 0


def test_all_required_metric_definitions_must_be_published() -> None:
    with pytest.raises(MetricDefinitionMissing, match="published metric definition"):
        calculate_closed_event_facts(event(), transitions(), definitions(status="draft"))


def test_non_closed_event_does_not_produce_metric_facts() -> None:
    active = event()
    active["status"] = "active"
    active["closed_at"] = None

    assert calculate_closed_event_facts(active, transitions(), definitions()) == []


def test_closed_event_handler_persists_scoped_facts_with_outbox_fence() -> None:
    from apps.api.hxy_product.operating_metrics import (
        build_closed_event_metrics_handler,
    )

    calls: list[dict[str, object]] = []

    class Repository:
        def persist_closed_event_metrics(self, **kwargs):
            calls.append(kwargs)
            return {"inserted_count": 4, "existing_count": 0}

    lease_checks: list[str] = []
    handler = build_closed_event_metrics_handler(Repository())
    result = handler(
        {
            "organization_id": ORGANIZATION_ID,
            "store_id": STORE_ID,
            "operating_event_id": EVENT_ID,
            "calculation_version": CALCULATION_VERSION,
            "_hxy_outbox": {
                "organization_id": ORGANIZATION_ID,
                "aggregate_type": "operating_event",
                "aggregate_id": EVENT_ID,
                "outbox_message_id": "60000000-0000-0000-0000-000000000001",
                "attempt_number": 1,
                "worker_id": "metrics-worker",
                "assert_lease": lambda: lease_checks.append("checked"),
            },
        }
    )

    assert result == {
        "status": "calculated",
        "operating_event_id": EVENT_ID,
        "inserted_count": 4,
        "existing_count": 0,
    }
    assert len(calls) == 1
    assert calls[0]["organization_id"] == ORGANIZATION_ID
    assert calls[0]["operating_event_id"] == EVENT_ID
    assert calls[0]["execution_fence"]["worker_id"] == "metrics-worker"
    assert lease_checks == ["checked", "checked"]


def test_closed_event_handler_rejects_outbox_scope_mismatch() -> None:
    from apps.api.hxy_product.operating_metrics import (
        build_closed_event_metrics_handler,
    )
    from apps.api.hxy_product.outbox_worker import OutboxHandlerError

    class Repository:
        def persist_closed_event_metrics(self, **_kwargs):
            raise AssertionError("scope mismatch must fail before persistence")

    handler = build_closed_event_metrics_handler(Repository())
    with pytest.raises(OutboxHandlerError, match="scope") as raised:
        handler(
            {
                "organization_id": ORGANIZATION_ID,
                "store_id": STORE_ID,
                "operating_event_id": EVENT_ID,
                "calculation_version": CALCULATION_VERSION,
                "_hxy_outbox": {
                    "organization_id": ORGANIZATION_ID,
                    "aggregate_type": "operating_event",
                    "aggregate_id": "20000000-0000-0000-0000-000000000099",
                    "outbox_message_id": "60000000-0000-0000-0000-000000000001",
                    "attempt_number": 1,
                    "worker_id": "metrics-worker",
                    "assert_lease": lambda: None,
                },
            }
        )

    assert raised.value.code == "metric_scope_mismatch"
    assert raised.value.retryable is False
