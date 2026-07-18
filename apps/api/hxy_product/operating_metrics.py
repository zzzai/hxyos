from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Mapping
from uuid import UUID, uuid5

from .outbox_repository import OutboxLeaseLost, lock_outbox_execution_fence
from .outbox_worker import OutboxHandlerError

try:
    import psycopg
    from psycopg.rows import dict_row
except Exception:  # pragma: no cover - deployment dependency may be installed later
    psycopg = None
    dict_row = None


CALCULATION_VERSION = "operating-metrics.v1"
_METRIC_FACT_NAMESPACE = UUID("8f46cccb-fef2-5eca-9254-3f01cf30061a")

METRIC_KEYS = (
    "issue_closure_duration_seconds",
    "issue_overdue_duration_seconds",
    "issue_rework_count",
    "issue_acceptance_count",
)


class MetricDefinitionMissing(ValueError):
    pass


class ClosedEventMetricContextMissing(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class MetricFactDraft:
    metric_fact_id: str
    organization_id: str
    store_id: str | None
    metric_definition_id: str
    metric_definition_version: int
    metric_key: str
    subject_type: str
    subject_id: str
    value_numeric: int
    unit: str
    window_start: datetime | None
    window_end: datetime | None
    derived_from_transition_ids: tuple[str, ...]
    source_snapshot_ids: tuple[str, ...] = ()
    calculation_version: str = CALCULATION_VERSION


def _text(record: dict[str, Any], key: str) -> str:
    return str(record.get(key) or "")


def _datetime(record: dict[str, Any], key: str) -> datetime:
    value = record.get(key)
    if not isinstance(value, datetime):
        raise ValueError(f"{key} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{key} must be timezone-aware")
    return value


def _published_definitions(
    metric_definitions: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    by_key = {
        _text(definition, "metric_key"): definition
        for definition in metric_definitions
        if _text(definition, "metric_key") in METRIC_KEYS
        and _text(definition, "status") == "published"
    }
    missing = [key for key in METRIC_KEYS if key not in by_key]
    if missing:
        raise MetricDefinitionMissing(
            "published metric definition is required: " + ", ".join(missing)
        )
    return by_key


def _transition_ids(
    transitions: list[dict[str, Any]],
    *,
    aggregate_type: str,
    aggregate_id: str,
    from_state: str | None = None,
    to_state: str | None = None,
) -> tuple[str, ...]:
    result: list[str] = []
    for transition in transitions:
        if _text(transition, "aggregate_type") != aggregate_type:
            continue
        if _text(transition, "aggregate_id") != aggregate_id:
            continue
        if from_state is not None and _text(transition, "from_state") != from_state:
            continue
        if to_state is not None and _text(transition, "to_state") != to_state:
            continue
        transition_id = _text(transition, "transition_id")
        if transition_id:
            result.append(transition_id)
    return tuple(result)


def _fact(
    event: dict[str, Any],
    definition: dict[str, Any],
    *,
    value_numeric: int,
    unit: str,
    window_start: datetime | None,
    window_end: datetime | None,
    transition_ids: tuple[str, ...],
) -> MetricFactDraft:
    definition_id = _text(definition, "metric_definition_id")
    if not definition_id:
        raise MetricDefinitionMissing("published metric definition has no id")
    try:
        version = int(definition["metric_version"])
    except (KeyError, TypeError, ValueError) as exc:
        raise MetricDefinitionMissing("published metric definition has no version") from exc
    event_id = _text(event, "operating_event_id")
    metric_key = _text(definition, "metric_key")
    organization_id = _text(event, "organization_id")
    metric_fact_id = str(
        uuid5(
            _METRIC_FACT_NAMESPACE,
            ":".join(
                (
                    organization_id,
                    event_id,
                    metric_key,
                    definition_id,
                    str(version),
                    CALCULATION_VERSION,
                )
            ),
        )
    )
    return MetricFactDraft(
        metric_fact_id=metric_fact_id,
        organization_id=organization_id,
        store_id=_text(event, "store_id") or None,
        metric_definition_id=definition_id,
        metric_definition_version=version,
        metric_key=metric_key,
        subject_type="operating_event",
        subject_id=event_id,
        value_numeric=value_numeric,
        unit=unit,
        window_start=window_start,
        window_end=window_end,
        derived_from_transition_ids=transition_ids,
    )


def calculate_closed_event_facts(
    event: dict[str, Any],
    transitions: list[dict[str, Any]],
    metric_definitions: list[dict[str, Any]],
    *,
    task_ids: set[str] | None = None,
) -> list[MetricFactDraft]:
    if _text(event, "status") != "closed":
        return []

    definitions = _published_definitions(metric_definitions)
    event_id = _text(event, "operating_event_id")
    opened_at = _datetime(event, "created_at")
    closed_at = _datetime(event, "closed_at")
    due_at = event.get("due_at")
    if due_at is not None:
        due_at = _datetime(event, "due_at")
    if not event_id:
        raise ValueError("operating_event_id is required")

    event_transition_ids = _transition_ids(
        transitions,
        aggregate_type="operating_event",
        aggregate_id=event_id,
    )
    close_transition_ids = _transition_ids(
        transitions,
        aggregate_type="operating_event",
        aggregate_id=event_id,
        from_state="resolved",
        to_state="closed",
    )
    lineage = tuple(dict.fromkeys((*event_transition_ids, *close_transition_ids)))
    if not lineage:
        raise ValueError("closed event requires state transition lineage")

    closure_seconds = max(0, int((closed_at - opened_at).total_seconds()))
    overdue_seconds = (
        max(0, int((closed_at - due_at).total_seconds())) if due_at is not None else 0
    )
    # Task transitions are linked to the closed event by the caller's filtered input.
    # Keep all matching task transitions in the lineage and use the close transition
    # as the auditable anchor when a count is zero.
    scoped_task_ids = None if task_ids is None else {str(value) for value in task_ids}
    rework_ids = tuple(
        _text(item, "transition_id")
        for item in transitions
        if _text(item, "aggregate_type") == "task"
        and (
            scoped_task_ids is None
            or _text(item, "aggregate_id") in scoped_task_ids
        )
        and _text(item, "from_state") == "submitted"
        and _text(item, "to_state") == "rework"
        and _text(item, "transition_id")
    )
    acceptance_ids = tuple(
        _text(item, "transition_id")
        for item in transitions
        if _text(item, "aggregate_type") == "task"
        and (
            scoped_task_ids is None
            or _text(item, "aggregate_id") in scoped_task_ids
        )
        and _text(item, "from_state") == "submitted"
        and _text(item, "to_state") == "accepted"
        and _text(item, "transition_id")
    )
    return [
        _fact(
            event,
            definitions["issue_closure_duration_seconds"],
            value_numeric=closure_seconds,
            unit="seconds",
            window_start=opened_at,
            window_end=closed_at,
            transition_ids=lineage,
        ),
        _fact(
            event,
            definitions["issue_overdue_duration_seconds"],
            value_numeric=overdue_seconds,
            unit="seconds",
            window_start=opened_at,
            window_end=closed_at,
            transition_ids=lineage,
        ),
        _fact(
            event,
            definitions["issue_rework_count"],
            value_numeric=len(rework_ids),
            unit="count",
            window_start=opened_at,
            window_end=closed_at,
            transition_ids=rework_ids or lineage,
        ),
        _fact(
            event,
            definitions["issue_acceptance_count"],
            value_numeric=len(acceptance_ids),
            unit="count",
            window_start=opened_at,
            window_end=closed_at,
            transition_ids=acceptance_ids or lineage,
        ),
    ]


class OperatingMetricsRepository:
    def __init__(self, database_url: str):
        if not database_url:
            raise ValueError("database_url is required")
        if psycopg is None:
            raise RuntimeError("psycopg is not installed")
        self.database_url = database_url

    def connect(self):
        return psycopg.connect(self.database_url, row_factory=dict_row)

    def persist_closed_event_metrics(
        self,
        *,
        organization_id: str,
        store_id: str,
        operating_event_id: str,
        calculation_version: str,
        execution_fence: Mapping[str, Any],
    ) -> dict[str, int]:
        if calculation_version != CALCULATION_VERSION:
            raise ValueError("unsupported operating metric calculation version")

        with self.connect() as connection:
            lock_outbox_execution_fence(connection, execution_fence)
            event_row = connection.execute(
                """
                SELECT operating_event_id::text,
                       organization_id::text,
                       store_id,
                       status,
                       due_at,
                       closed_at,
                       created_at
                FROM hxy_operating_events
                WHERE organization_id = %s::uuid
                  AND store_id = %s
                  AND operating_event_id = %s::uuid
                  AND status = 'closed'
                FOR SHARE
                """,
                (organization_id, store_id, operating_event_id),
            ).fetchone()
            if event_row is None:
                raise ClosedEventMetricContextMissing(
                    "scoped closed operating event was not found"
                )
            event = dict(event_row)

            task_rows = connection.execute(
                """
                SELECT task_id::text
                FROM hxy_product_tasks
                WHERE organization_id = %s::uuid
                  AND store_id = %s
                  AND operating_event_id = %s::uuid
                ORDER BY task_id
                """,
                (organization_id, store_id, operating_event_id),
            ).fetchall()
            task_ids = {str(row["task_id"]) for row in task_rows}

            transition_rows = connection.execute(
                """
                SELECT transition.transition_id::text,
                       transition.aggregate_type,
                       transition.aggregate_id::text,
                       transition.from_state,
                       transition.to_state,
                       transition.occurred_at
                FROM hxy_state_transitions AS transition
                WHERE transition.organization_id = %s::uuid
                  AND (
                    (
                      transition.aggregate_type = 'operating_event'
                      AND transition.aggregate_id = %s::uuid
                    )
                    OR (
                      transition.aggregate_type = 'task'
                      AND transition.aggregate_id = ANY(%s::uuid[])
                    )
                  )
                ORDER BY transition.occurred_at, transition.transition_id
                """,
                (organization_id, operating_event_id, list(task_ids)),
            ).fetchall()
            transitions = [dict(row) for row in transition_rows]

            definition_rows = connection.execute(
                """
                SELECT DISTINCT ON (metric_key)
                       metric_definition_id::text,
                       metric_key,
                       metric_version,
                       status
                FROM hxy_metric_definitions
                WHERE organization_id = %s::uuid
                  AND metric_key = ANY(%s::text[])
                  AND status = 'published'
                  AND effective_from <= %s
                  AND (effective_to IS NULL OR effective_to > %s)
                ORDER BY metric_key, metric_version DESC
                """,
                (
                    organization_id,
                    list(METRIC_KEYS),
                    event["closed_at"],
                    event["closed_at"],
                ),
            ).fetchall()
            definitions = [dict(row) for row in definition_rows]
            facts = calculate_closed_event_facts(
                event,
                transitions,
                definitions,
                task_ids=task_ids,
            )

            inserted_count = 0
            for fact in facts:
                inserted = connection.execute(
                    """
                    INSERT INTO hxy_metric_facts (
                      metric_fact_id,
                      organization_id,
                      store_id,
                      metric_definition_id,
                      metric_definition_version,
                      metric_key,
                      subject_type,
                      subject_id,
                      value_numeric,
                      unit,
                      window_start,
                      window_end,
                      derived_from_transition_ids,
                      source_snapshot_ids,
                      calculation_version
                    )
                    VALUES (
                      %s::uuid, %s::uuid, %s, %s::uuid, %s, %s, %s, %s::uuid,
                      %s, %s, %s, %s, %s::uuid[], %s::uuid[], %s
                    )
                    ON CONFLICT (metric_fact_id) DO NOTHING
                    RETURNING metric_fact_id::text
                    """,
                    (
                        fact.metric_fact_id,
                        fact.organization_id,
                        fact.store_id,
                        fact.metric_definition_id,
                        fact.metric_definition_version,
                        fact.metric_key,
                        fact.subject_type,
                        fact.subject_id,
                        fact.value_numeric,
                        fact.unit,
                        fact.window_start,
                        fact.window_end,
                        list(fact.derived_from_transition_ids),
                        list(fact.source_snapshot_ids),
                        fact.calculation_version,
                    ),
                ).fetchone()
                inserted_count += int(inserted is not None)

        return {
            "inserted_count": inserted_count,
            "existing_count": len(facts) - inserted_count,
        }


def _closed_event_payload(payload: Mapping[str, Any]) -> tuple[dict[str, str], dict[str, Any]]:
    organization_id = str(payload.get("organization_id") or "").strip()
    store_id = str(payload.get("store_id") or "").strip()
    event_id = str(payload.get("operating_event_id") or "").strip()
    calculation_version = str(payload.get("calculation_version") or "").strip()
    raw_fence = payload.get("_hxy_outbox")
    fence = dict(raw_fence) if isinstance(raw_fence, Mapping) else {}
    if not all((organization_id, store_id, event_id, calculation_version, fence)):
        raise OutboxHandlerError(
            "invalid_metric_payload",
            "closed event metric payload is incomplete",
            retryable=False,
        )
    if (
        str(fence.get("organization_id") or "") != organization_id
        or str(fence.get("aggregate_type") or "") != "operating_event"
        or str(fence.get("aggregate_id") or "") != event_id
    ):
        raise OutboxHandlerError(
            "metric_scope_mismatch",
            "closed event metric payload crossed the outbox scope",
            retryable=False,
        )
    if calculation_version != CALCULATION_VERSION:
        raise OutboxHandlerError(
            "unsupported_metric_version",
            "closed event metric calculation version is unsupported",
            retryable=False,
        )
    return (
        {
            "organization_id": organization_id,
            "store_id": store_id,
            "operating_event_id": event_id,
            "calculation_version": calculation_version,
        },
        fence,
    )


def build_closed_event_metrics_handler(
    repository: Any,
) -> Callable[[dict[str, Any]], dict[str, Any]]:
    def handle(payload: dict[str, Any]) -> dict[str, Any]:
        trusted, fence = _closed_event_payload(payload)
        assert_lease = fence.get("assert_lease")
        if not callable(assert_lease):
            raise OutboxHandlerError(
                "invalid_metric_fence",
                "closed event metric execution fence is incomplete",
                retryable=False,
            )
        assert_lease()
        execution_fence = {
            key: fence.get(key)
            for key in (
                "organization_id",
                "outbox_message_id",
                "worker_id",
                "attempt_number",
            )
        }
        try:
            result = repository.persist_closed_event_metrics(
                **trusted,
                execution_fence=execution_fence,
            )
        except OutboxLeaseLost:
            raise
        except ClosedEventMetricContextMissing as error:
            raise OutboxHandlerError(
                "closed_event_context_not_found",
                str(error),
                retryable=False,
            ) from error
        except MetricDefinitionMissing as error:
            raise OutboxHandlerError(
                "metric_definition_missing",
                str(error),
                retryable=True,
            ) from error
        except Exception as error:
            raise OutboxHandlerError(
                "metric_persistence_failed",
                "closed event metrics could not be persisted",
                retryable=True,
            ) from error
        assert_lease()
        return {
            "status": "calculated",
            "operating_event_id": trusted["operating_event_id"],
            "inserted_count": int(result.get("inserted_count") or 0),
            "existing_count": int(result.get("existing_count") or 0),
        }

    return handle
