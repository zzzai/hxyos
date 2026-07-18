from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Callable

from .operating_repository import OperatingWriteConflict
from .operating_schemas import (
    AcceptTaskCommand,
    AssignTaskCommand,
    CancelEventCommand,
    CreateEventFromProposalCommand,
    EscalateEventCommand,
    OperatingCommandReceipt,
    ReturnForReworkCommand,
    StartTaskCommand,
    SubmitTaskCommand,
)


ALLOWED_TASK_TRANSITIONS = {
    "open": {"assigned", "in_progress", "cancelled"},
    "assigned": {"in_progress", "cancelled"},
    "in_progress": {"submitted", "cancelled"},
    "submitted": {"accepted", "rework"},
    "rework": {"in_progress", "submitted", "cancelled"},
    "accepted": set(),
    "cancelled": set(),
}

_MANAGEMENT_ROLES = frozenset({"store_manager", "founder", "hq_operations"})
_STORE_ROLES = frozenset({"store_manager", "store_employee"})
_SEVERITY_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}
_ACCEPTANCE_ROLE_CEILINGS = {
    "low": frozenset({"store_manager", "founder", "hq_operations"}),
    "medium": frozenset({"store_manager", "founder", "hq_operations"}),
    "high": frozenset({"founder", "hq_operations"}),
    "critical": frozenset({"hq_operations"}),
}
_WORKFLOW_POLICY_VERSION = "hxy.operating-workflow.v1"


class OperatingError(RuntimeError):
    status_code = 400


class OperatingNotFound(OperatingError):
    status_code = 404


class OperatingPermissionDenied(OperatingError):
    status_code = 403


class OperatingConflict(OperatingError):
    status_code = 409


class OperatingRuleViolation(OperatingError):
    status_code = 422


def _identifier(value: Any) -> str:
    return str(value)


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return dict(parsed) if isinstance(parsed, dict) else {}
    return {}


def _text(payload: dict[str, Any], key: str, maximum: int) -> str:
    return str(payload.get(key) or "").replace("\x00", " ").strip()[:maximum]


def _parse_optional_datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        candidate = str(value).strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(candidate)
        except ValueError:
            return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _priority_for_severity(severity: str) -> str:
    return {
        "low": "normal",
        "medium": "high",
        "high": "urgent",
        "critical": "urgent",
    }[severity]


class OperatingService:
    def __init__(
        self,
        repository: Any,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.repository = repository
        self._now = now or (lambda: datetime.now(timezone.utc))

    def create_event_from_proposal(
        self, command: CreateEventFromProposalCommand
    ) -> OperatingCommandReceipt:
        organization_id = _identifier(command.organization_id)
        proposal_id = _identifier(command.proposal_id)
        correlation_id = _identifier(command.correlation_id)
        with self.repository.transaction() as transaction:
            proposal = transaction.lock_proposal_context(organization_id, proposal_id)
            if proposal is None:
                raise OperatingNotFound("issue proposal was not found")
            existing_event_id = proposal.get("target_id")
            if existing_event_id:
                aggregate = transaction.lock_event_aggregate(
                    organization_id, _identifier(existing_event_id)
                )
                if aggregate is None:
                    raise OperatingConflict("proposal target event is missing")
                self._validate_event_aggregate(aggregate)
                task = aggregate["tasks"][0] if aggregate.get("tasks") else None
                return self._receipt(
                    aggregate["event"], task=task, workflow=aggregate.get("workflow")
                )

            proposal_status = str(proposal.get("status") or "")
            if proposal_status not in {"proposed", "auto_accepted", "accepted"}:
                raise OperatingRuleViolation("proposal is not eligible for event creation")
            store_id = str(proposal.get("store_id") or "")
            reporter_id = str(proposal.get("reporter_assignment_id") or "")
            if not store_id or not reporter_id:
                raise OperatingRuleViolation("proposal source identity is incomplete")

            actor, decision_actor_fields = self._proposal_decision_actor(
                transaction,
                organization_id=organization_id,
                store_id=store_id,
                proposal=proposal,
                actor_assignment_id=(
                    _identifier(command.actor_assignment_id)
                    if command.actor_assignment_id is not None
                    else None
                ),
            )
            occurred_at = proposal.get("received_at")
            if not isinstance(occurred_at, datetime):
                raise OperatingRuleViolation("proposal source time is invalid")
            if proposal_status in {"auto_accepted", "accepted"} and not isinstance(
                proposal.get("decided_at"), datetime
            ):
                raise OperatingRuleViolation("accepted proposal decision time is invalid")
            governance = transaction.load_current_governance_snapshot(
                organization_id, store_id, occurred_at
            )
            if governance is None:
                raise OperatingRuleViolation("no active store governance profile was found")

            payload = _json_object(proposal.get("payload"))
            severity = str(proposal.get("risk_level") or "")
            if severity not in _SEVERITY_ORDER:
                raise OperatingRuleViolation("proposal risk level is invalid")
            title = _text(payload, "title", 160)
            event_type = _text(payload, "event_type", 100)
            acceptance_criteria = _text(payload, "acceptance_criteria", 3000)
            if not title or not event_type or not acceptance_criteria:
                raise OperatingRuleViolation("proposal is missing required operating fields")

            owner_id = self._eligible_suggested_owner(
                transaction,
                organization_id=organization_id,
                store_id=store_id,
                suggested_owner_id=payload.get("suggested_owner_assignment_id"),
            )
            event_status = "active" if owner_id else "open"
            workflow_status = "running" if owner_id else "pending"
            task_status = "assigned" if owner_id else "open"
            now = self._now()
            proposal_policy_version = str(
                proposal.get("decision_policy_version") or ""
            ).strip()
            policy_version = _WORKFLOW_POLICY_VERSION
            event = transaction.insert_operating_event(
                {
                    "organization_id": organization_id,
                    "store_id": store_id,
                    "event_type": event_type,
                    "title": title,
                    "description": _text(payload, "description", 10000),
                    "location": _text(payload, "location", 240),
                    "impact": _text(payload, "impact", 2000),
                    "acceptance_criteria": acceptance_criteria,
                    "source_envelope_id": proposal["source_envelope_id"],
                    "source_proposal_id": proposal_id,
                    "reporter_assignment_id": reporter_id,
                    "owner_assignment_id": owner_id,
                    "severity": severity,
                    "status": event_status,
                    "occurred_at": occurred_at,
                    "detected_at": now,
                    "due_at": _parse_optional_datetime(payload.get("suggested_due_at")),
                    "policy_version": policy_version,
                    "store_operating_relationship_id": governance[
                        "store_operating_relationship_id"
                    ],
                    "store_operating_relationship_version": governance[
                        "store_operating_relationship_version"
                    ],
                    "governance_profile_id": governance["governance_profile_id"],
                    "governance_profile_version": governance[
                        "governance_profile_version"
                    ],
                }
            )
            event_id = _identifier(event["operating_event_id"])
            workflow = transaction.insert_workflow_instance(
                {
                    "organization_id": organization_id,
                    "store_id": store_id,
                    "operating_event_id": event_id,
                    "workflow_type": "store_issue_resolution",
                    "workflow_version": 1,
                    "status": workflow_status,
                    "current_state": "task_assigned" if owner_id else "task_open",
                    "started_at": now if owner_id else None,
                }
            )
            workflow_id = _identifier(workflow["workflow_instance_id"])
            task = transaction.insert_task(
                {
                    "organization_id": organization_id,
                    "store_id": store_id,
                    "creator_assignment_id": reporter_id,
                    "assignee_assignment_id": owner_id,
                    "title": title,
                    "details": _text(payload, "description", 5000),
                    "priority": _priority_for_severity(severity),
                    "visibility": "assignee" if owner_id else "store",
                    "status": task_status,
                    "due_at": _parse_optional_datetime(payload.get("suggested_due_at")),
                    "operating_event_id": event_id,
                    "workflow_instance_id": workflow_id,
                    "task_type": event_type,
                    "external_responsible_name": None,
                }
            )
            transaction.link_proposal_to_event(
                organization_id=organization_id,
                proposal_id=proposal_id,
                event_id=event_id,
                accepted_by_assignment_id=(
                    _identifier(actor["assignment_id"])
                    if actor is not None and proposal_status == "proposed"
                    else None
                ),
                decision_policy_version=(
                    policy_version if proposal_status == "proposed" and actor is None else None
                ),
            )

            if proposal_status == "proposed":
                creation_actor_fields = decision_actor_fields
                self._append_transition(
                    transaction,
                    organization_id=organization_id,
                    store_id=store_id,
                    aggregate_type="ai_proposal",
                    aggregate_id=proposal_id,
                    from_state="proposed",
                    to_state="accepted",
                    command_type="create_event_from_proposal",
                    actor_fields=decision_actor_fields,
                    reason="accepted as governed operating event",
                    policy_version=policy_version,
                    correlation_id=correlation_id,
                    occurred_at=now,
                )
            else:
                creation_actor_fields = self._system_actor_fields(
                    "hxy.operating-workflow.v1"
                )
                self._append_transition(
                    transaction,
                    organization_id=organization_id,
                    store_id=store_id,
                    aggregate_type="ai_proposal",
                    aggregate_id=proposal_id,
                    from_state="proposed",
                    to_state=proposal_status,
                    command_type="record_proposal_decision",
                    actor_fields=decision_actor_fields,
                    reason="recorded original proposal decision during materialization",
                    policy_version=(proposal_policy_version or policy_version),
                    correlation_id=correlation_id,
                    occurred_at=proposal["decided_at"],
                )
                self._append_transition(
                    transaction,
                    organization_id=organization_id,
                    store_id=store_id,
                    aggregate_type="ai_proposal",
                    aggregate_id=proposal_id,
                    from_state=proposal_status,
                    to_state=proposal_status,
                    command_type="materialize_event_from_proposal",
                    actor_fields=creation_actor_fields,
                    reason="materialized previously accepted proposal",
                    policy_version=policy_version,
                    correlation_id=correlation_id,
                    occurred_at=now,
                )
            for aggregate_type, aggregate_id, to_state in (
                ("operating_event", event_id, event_status),
                ("workflow_instance", workflow_id, workflow_status),
                ("task", _identifier(task["task_id"]), task_status),
            ):
                self._append_transition(
                    transaction,
                    organization_id=organization_id,
                    store_id=store_id,
                    aggregate_type=aggregate_type,
                    aggregate_id=aggregate_id,
                    from_state=None,
                    to_state=to_state,
                    command_type="create_event_from_proposal",
                    actor_fields=creation_actor_fields,
                    reason="created from accepted issue proposal",
                    policy_version=policy_version,
                    correlation_id=correlation_id,
                    occurred_at=now,
                )
            return self._receipt(event, task=task, workflow=workflow)

    def assign_task(self, command: AssignTaskCommand) -> OperatingCommandReceipt:
        organization_id = _identifier(command.organization_id)
        with self.repository.transaction() as transaction:
            aggregate = self._require_task_aggregate(
                transaction, organization_id, _identifier(command.task_id)
            )
            task, event, workflow = self._aggregate_rows(aggregate)
            self._require_expected(command.expected_updated_at, task["updated_at"])
            self._require_transition(task, "assigned")
            actor = self._require_actor(
                transaction,
                organization_id=organization_id,
                assignment_id=_identifier(command.actor_assignment_id),
                store_id=str(event["store_id"]),
                allowed_roles=self._action_roles(
                    aggregate["governance"],
                    "issue_assignment_roles",
                    _MANAGEMENT_ROLES,
                ),
            )
            assignee_id = (
                _identifier(command.assignee_assignment_id)
                if command.assignee_assignment_id is not None
                else None
            )
            if assignee_id:
                self._require_actor(
                    transaction,
                    organization_id=organization_id,
                    assignment_id=assignee_id,
                    store_id=str(event["store_id"]),
                    allowed_roles=_STORE_ROLES,
                )
            updated_task = self._update_task(
                transaction,
                organization_id=organization_id,
                task=task,
                changes={
                    "status": "assigned",
                    "assignee_assignment_id": assignee_id,
                    "external_responsible_name": (
                        command.external_responsible_name or None
                    ),
                    "visibility": "assignee" if assignee_id else "store",
                },
            )
            now = self._now()
            actor_fields = self._user_actor_fields(actor)
            self._append_task_transition(
                transaction, command, task, "assigned", actor_fields, now
            )
            event = self._synchronize_event_owner(
                transaction,
                command,
                event,
                assignee_id,
                actor_fields,
                now,
            )
            event = self._advance_event_to_active(
                transaction, command, event, actor_fields, now
            )
            workflow = self._advance_workflow_to_running(
                transaction, command, workflow, actor_fields, now, "task_assigned"
            )
            return self._receipt(event, task=updated_task, workflow=workflow)

    def start_task(self, command: StartTaskCommand) -> OperatingCommandReceipt:
        organization_id = _identifier(command.organization_id)
        with self.repository.transaction() as transaction:
            aggregate = self._require_task_aggregate(
                transaction, organization_id, _identifier(command.task_id)
            )
            task, event, workflow = self._aggregate_rows(aggregate)
            self._require_expected(command.expected_updated_at, task["updated_at"])
            self._require_transition(task, "in_progress")
            actor = self._require_actor(
                transaction,
                organization_id=organization_id,
                assignment_id=_identifier(command.actor_assignment_id),
                store_id=str(event["store_id"]),
            )
            self._require_task_executor(actor, task)
            updated_task = self._update_task(
                transaction,
                organization_id=organization_id,
                task=task,
                changes={"status": "in_progress"},
            )
            now = self._now()
            actor_fields = self._user_actor_fields(actor)
            self._append_task_transition(
                transaction, command, task, "in_progress", actor_fields, now
            )
            event = self._advance_event_to_active(
                transaction, command, event, actor_fields, now
            )
            workflow = self._advance_workflow_to_running(
                transaction, command, workflow, actor_fields, now, "task_in_progress"
            )
            return self._receipt(event, task=updated_task, workflow=workflow)

    def submit_task(self, command: SubmitTaskCommand) -> OperatingCommandReceipt:
        organization_id = _identifier(command.organization_id)
        with self.repository.transaction() as transaction:
            aggregate = self._require_task_aggregate(
                transaction, organization_id, _identifier(command.task_id)
            )
            task, event, workflow = self._aggregate_rows(aggregate)
            self._require_expected(command.expected_updated_at, task["updated_at"])
            self._require_transition(task, "submitted")
            actor = self._require_actor(
                transaction,
                organization_id=organization_id,
                assignment_id=_identifier(command.actor_assignment_id),
                store_id=str(event["store_id"]),
            )
            self._require_task_executor(actor, task)
            evidence_ids = [_identifier(value) for value in command.evidence_ids]
            if not transaction.evidence_ids_are_valid_for_task(
                organization_id=organization_id,
                store_id=str(event["store_id"]),
                event_id=_identifier(event["operating_event_id"]),
                task_id=_identifier(task["task_id"]),
                evidence_ids=evidence_ids,
            ):
                raise OperatingRuleViolation("submitted task requires valid evidence")
            now = self._now()
            updated_task = self._update_task(
                transaction,
                organization_id=organization_id,
                task=task,
                changes={
                    "status": "submitted",
                    "submitted_at": now,
                    "accepted_at": None,
                    "acceptance_assignment_id": None,
                    "result": command.result,
                },
            )
            actor_fields = self._user_actor_fields(actor)
            self._append_task_transition(
                transaction, command, task, "submitted", actor_fields, now
            )
            statuses = self._statuses_after(
                aggregate["tasks"], _identifier(task["task_id"]), "submitted"
            )
            if self._all_active_in(statuses, {"submitted", "accepted"}):
                event = self._set_event_state(
                    transaction,
                    command,
                    event,
                    "resolved",
                    actor_fields,
                    now,
                    closed_at=None,
                )
                workflow = self._set_workflow_state(
                    transaction,
                    command,
                    workflow,
                    status="waiting",
                    current_state="waiting_acceptance",
                    actor_fields=actor_fields,
                    occurred_at=now,
                    completed_at=None,
                )
            else:
                event = self._advance_event_to_active(
                    transaction, command, event, actor_fields, now
                )
                workflow = self._advance_workflow_to_running(
                    transaction, command, workflow, actor_fields, now, "task_in_progress"
                )
            return self._receipt(event, task=updated_task, workflow=workflow)

    def accept_task(self, command: AcceptTaskCommand) -> OperatingCommandReceipt:
        organization_id = _identifier(command.organization_id)
        with self.repository.transaction() as transaction:
            aggregate = self._require_task_aggregate(
                transaction, organization_id, _identifier(command.task_id)
            )
            task, event, workflow = self._aggregate_rows(aggregate)
            self._require_expected(command.expected_updated_at, task["updated_at"])
            self._require_transition(task, "accepted")
            allowed_roles = self._acceptance_roles(
                aggregate["governance"], str(event["severity"])
            )
            actor = self._require_actor(
                transaction,
                organization_id=organization_id,
                assignment_id=_identifier(command.actor_assignment_id),
                store_id=str(event["store_id"]),
                allowed_roles=allowed_roles,
            )
            if not transaction.task_has_valid_evidence(
                organization_id=organization_id,
                store_id=str(event["store_id"]),
                event_id=_identifier(event["operating_event_id"]),
                task_id=_identifier(task["task_id"]),
            ):
                raise OperatingRuleViolation("accepted task requires valid evidence")
            now = self._now()
            updated_task = self._update_task(
                transaction,
                organization_id=organization_id,
                task=task,
                changes={
                    "status": "accepted",
                    "accepted_at": now,
                    "acceptance_assignment_id": _identifier(actor["assignment_id"]),
                },
            )
            actor_fields = self._user_actor_fields(actor)
            self._append_task_transition(
                transaction, command, task, "accepted", actor_fields, now, command.reason
            )
            statuses = self._statuses_after(
                aggregate["tasks"], _identifier(task["task_id"]), "accepted"
            )
            if self._all_active_in(statuses, {"accepted"}):
                event = self._set_event_state(
                    transaction,
                    command,
                    event,
                    "closed",
                    actor_fields,
                    now,
                    closed_at=now,
                )
                workflow = self._set_workflow_state(
                    transaction,
                    command,
                    workflow,
                    status="completed",
                    current_state="accepted",
                    actor_fields=actor_fields,
                    occurred_at=now,
                    completed_at=now,
                )
            elif self._all_active_in(statuses, {"submitted", "accepted"}):
                event = self._set_event_state(
                    transaction,
                    command,
                    event,
                    "resolved",
                    actor_fields,
                    now,
                    closed_at=None,
                )
                workflow = self._set_workflow_state(
                    transaction,
                    command,
                    workflow,
                    status="waiting",
                    current_state="waiting_acceptance",
                    actor_fields=actor_fields,
                    occurred_at=now,
                    completed_at=None,
                )
            return self._receipt(event, task=updated_task, workflow=workflow)

    def return_for_rework(
        self, command: ReturnForReworkCommand
    ) -> OperatingCommandReceipt:
        organization_id = _identifier(command.organization_id)
        with self.repository.transaction() as transaction:
            aggregate = self._require_task_aggregate(
                transaction, organization_id, _identifier(command.task_id)
            )
            task, event, workflow = self._aggregate_rows(aggregate)
            self._require_expected(command.expected_updated_at, task["updated_at"])
            self._require_transition(task, "rework")
            actor = self._require_actor(
                transaction,
                organization_id=organization_id,
                assignment_id=_identifier(command.actor_assignment_id),
                store_id=str(event["store_id"]),
                allowed_roles=self._action_roles(
                    aggregate["governance"],
                    "issue_rework_roles",
                    _MANAGEMENT_ROLES,
                ),
            )
            now = self._now()
            updated_task = self._update_task(
                transaction,
                organization_id=organization_id,
                task=task,
                changes={
                    "status": "rework",
                    "accepted_at": None,
                    "acceptance_assignment_id": None,
                },
            )
            actor_fields = self._user_actor_fields(actor)
            self._append_task_transition(
                transaction,
                command,
                task,
                "rework",
                actor_fields,
                now,
                command.reason,
            )
            event = self._advance_event_to_active(
                transaction, command, event, actor_fields, now
            )
            workflow = self._advance_workflow_to_running(
                transaction, command, workflow, actor_fields, now, "rework"
            )
            return self._receipt(event, task=updated_task, workflow=workflow)

    def escalate_event(self, command: EscalateEventCommand) -> OperatingCommandReceipt:
        organization_id = _identifier(command.organization_id)
        with self.repository.transaction() as transaction:
            aggregate = transaction.lock_event_aggregate(
                organization_id, _identifier(command.event_id)
            )
            if aggregate is None:
                raise OperatingNotFound("operating event was not found")
            self._validate_event_aggregate(aggregate)
            event = aggregate["event"]
            workflow = aggregate.get("workflow")
            self._require_expected(command.expected_updated_at, event["updated_at"])
            if str(event["status"]) in {"closed", "cancelled"}:
                raise OperatingConflict("closed operating event cannot be escalated")
            actor = self._require_actor(
                transaction,
                organization_id=organization_id,
                assignment_id=_identifier(command.actor_assignment_id),
                store_id=str(event["store_id"]),
                allowed_roles=self._action_roles(
                    aggregate["governance"],
                    "issue_escalation_roles",
                    _MANAGEMENT_ROLES,
                ),
            )
            from_severity = str(event["severity"])
            if _SEVERITY_ORDER[command.severity] <= _SEVERITY_ORDER[from_severity]:
                raise OperatingRuleViolation("event escalation must increase severity")
            updated_event = self._update_event(
                transaction,
                organization_id=organization_id,
                event=event,
                changes={"severity": command.severity},
            )
            now = self._now()
            self._append_transition(
                transaction,
                organization_id=organization_id,
                store_id=str(event["store_id"]),
                aggregate_type="operating_event",
                aggregate_id=_identifier(event["operating_event_id"]),
                from_state=str(event["status"]),
                to_state=str(event["status"]),
                command_type="escalate_event",
                actor_fields=self._user_actor_fields(actor),
                reason=f"{from_severity}->{command.severity}: {command.reason}",
                policy_version=str(event["policy_version"]),
                correlation_id=_identifier(command.correlation_id),
                occurred_at=now,
            )
            task = aggregate["tasks"][0] if aggregate.get("tasks") else None
            return self._receipt(updated_event, task=task, workflow=workflow)

    def cancel_event(self, command: CancelEventCommand) -> OperatingCommandReceipt:
        organization_id = _identifier(command.organization_id)
        with self.repository.transaction() as transaction:
            aggregate = transaction.lock_event_aggregate(
                organization_id, _identifier(command.event_id)
            )
            if aggregate is None:
                raise OperatingNotFound("operating event was not found")
            self._validate_event_aggregate(aggregate)
            event = aggregate["event"]
            workflow = aggregate.get("workflow")
            self._require_expected(command.expected_updated_at, event["updated_at"])
            if str(event["status"]) in {"closed", "cancelled"}:
                raise OperatingConflict("operating event is already terminal")
            actor = self._require_actor(
                transaction,
                organization_id=organization_id,
                assignment_id=_identifier(command.actor_assignment_id),
                store_id=str(event["store_id"]),
                allowed_roles=self._action_roles(
                    aggregate["governance"],
                    "issue_cancellation_roles",
                    self._acceptance_roles(
                        aggregate["governance"], str(event["severity"])
                    ),
                ),
            )
            if any(str(task["status"]) == "submitted" for task in aggregate["tasks"]):
                raise OperatingRuleViolation(
                    "submitted task must be returned for rework before cancellation"
                )
            now = self._now()
            actor_fields = self._user_actor_fields(actor)
            updated_tasks: list[dict[str, Any]] = []
            for task in aggregate["tasks"]:
                status = str(task["status"])
                if status in {"accepted", "cancelled"}:
                    updated_tasks.append(task)
                    continue
                if "cancelled" not in ALLOWED_TASK_TRANSITIONS.get(status, set()):
                    raise OperatingRuleViolation(f"task cannot be cancelled from {status}")
                updated = self._update_task(
                    transaction,
                    organization_id=organization_id,
                    task=task,
                    changes={"status": "cancelled"},
                )
                updated_tasks.append(updated)
                self._append_transition(
                    transaction,
                    organization_id=organization_id,
                    store_id=str(event["store_id"]),
                    aggregate_type="task",
                    aggregate_id=_identifier(task["task_id"]),
                    from_state=status,
                    to_state="cancelled",
                    command_type="cancel_event",
                    actor_fields=actor_fields,
                    reason=command.reason,
                    policy_version=str(event["policy_version"]),
                    correlation_id=_identifier(command.correlation_id),
                    occurred_at=now,
                )
            if workflow is not None and str(workflow["status"]) not in {
                "completed",
                "cancelled",
                "failed",
            }:
                workflow = self._set_workflow_state(
                    transaction,
                    command,
                    workflow,
                    status="cancelled",
                    current_state="cancelled",
                    actor_fields=actor_fields,
                    occurred_at=now,
                    completed_at=now,
                )
            updated_event = self._set_event_state(
                transaction,
                command,
                event,
                "cancelled",
                actor_fields,
                now,
                closed_at=now,
                reason=command.reason,
            )
            task = updated_tasks[0] if updated_tasks else None
            return self._receipt(updated_event, task=task, workflow=workflow)

    def _proposal_decision_actor(
        self,
        transaction: Any,
        *,
        organization_id: str,
        store_id: str,
        proposal: dict[str, Any],
        actor_assignment_id: str | None,
    ) -> tuple[dict[str, Any] | None, dict[str, Any]]:
        status = str(proposal["status"])
        if status in {"auto_accepted", "accepted"}:
            decided_by = str(
                proposal.get("decided_by_assignment_id") or ""
            ).strip()
            policy_version = str(proposal.get("decision_policy_version") or "").strip()
            if decided_by:
                return {"assignment_id": decided_by}, {
                    "actor_type": "user",
                    "actor_assignment_id": decided_by,
                    "actor_reference": None,
                }
            if policy_version:
                return None, {
                    "actor_type": "policy",
                    "actor_assignment_id": None,
                    "actor_reference": policy_version,
                }
            raise OperatingRuleViolation(
                "accepted proposal is missing decision provenance"
            )
        if not actor_assignment_id:
            raise OperatingPermissionDenied("proposal acceptance requires an actor")
        actor = self._require_actor(
            transaction,
            organization_id=organization_id,
            assignment_id=actor_assignment_id,
            store_id=store_id,
            allowed_roles=_MANAGEMENT_ROLES,
        )
        return actor, self._user_actor_fields(actor)

    def _eligible_suggested_owner(
        self,
        transaction: Any,
        *,
        organization_id: str,
        store_id: str,
        suggested_owner_id: Any,
    ) -> str | None:
        candidate = str(suggested_owner_id or "").strip()
        if not candidate:
            return None
        assignment = transaction.load_assignment(organization_id, candidate)
        if assignment is None or str(assignment.get("status")) != "active":
            return None
        if str(assignment.get("role")) not in _STORE_ROLES:
            return None
        if str(assignment.get("store_id") or "") != store_id:
            return None
        return candidate

    def _require_task_aggregate(
        self, transaction: Any, organization_id: str, task_id: str
    ) -> dict[str, Any]:
        aggregate = transaction.lock_task_aggregate(organization_id, task_id)
        if aggregate is None:
            raise OperatingNotFound("operating task was not found")
        self._validate_event_aggregate(aggregate, task_required=True)
        if aggregate.get("governance") is None:
            raise OperatingConflict("operating task aggregate is incomplete")
        return aggregate

    @staticmethod
    def _validate_event_aggregate(
        aggregate: dict[str, Any], *, task_required: bool = False
    ) -> None:
        event = aggregate.get("event")
        workflows = aggregate.get("workflows")
        if not isinstance(event, dict) or not isinstance(workflows, list):
            raise OperatingConflict("operating event aggregate is incomplete")
        if len(workflows) == 0:
            raise OperatingConflict("operating event aggregate has no workflow")
        if len(workflows) != 1:
            raise OperatingConflict(
                "operating event aggregate requires exactly one workflow per event"
            )
        workflow = workflows[0]
        event_id = _identifier(event.get("operating_event_id"))
        if _identifier(workflow.get("operating_event_id")) != event_id:
            raise OperatingConflict("operating event aggregate relationship is inconsistent")
        if task_required:
            task = aggregate.get("task")
            if not isinstance(task, dict):
                raise OperatingConflict("operating task aggregate is incomplete")
            if _identifier(task.get("operating_event_id")) != event_id:
                raise OperatingConflict("operating task aggregate relationship is inconsistent")
            if _identifier(task.get("workflow_instance_id")) != _identifier(
                workflow.get("workflow_instance_id")
            ):
                raise OperatingConflict("operating task aggregate relationship is inconsistent")
        for task in aggregate.get("tasks", []):
            if _identifier(task.get("operating_event_id")) != event_id:
                raise OperatingConflict("operating task list relationship is inconsistent")
            if _identifier(task.get("workflow_instance_id")) != _identifier(
                workflow.get("workflow_instance_id")
            ):
                raise OperatingConflict("V1 task workflow relationship is inconsistent")
        aggregate["workflow"] = workflow

    def _action_roles(
        self,
        governance: dict[str, Any],
        key: str,
        ceiling: frozenset[str] | set[str],
    ) -> frozenset[str]:
        decision_rights = _json_object(governance.get("decision_rights"))
        if key not in decision_rights:
            return frozenset(ceiling)
        configured = decision_rights.get(key)
        if not isinstance(configured, list):
            raise OperatingRuleViolation(f"governance {key} is invalid")
        selected = frozenset(ceiling).intersection(str(role) for role in configured)
        if not selected:
            raise OperatingRuleViolation(f"governance {key} defines no safe actor")
        return selected

    @staticmethod
    def _aggregate_rows(
        aggregate: dict[str, Any]
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        return aggregate["task"], aggregate["event"], aggregate["workflow"]

    def _require_actor(
        self,
        transaction: Any,
        *,
        organization_id: str,
        assignment_id: str,
        store_id: str,
        allowed_roles: frozenset[str] | set[str] | None = None,
    ) -> dict[str, Any]:
        actor = transaction.load_assignment(organization_id, assignment_id)
        if actor is None or str(actor.get("status")) != "active":
            raise OperatingPermissionDenied("active actor assignment was not found")
        role = str(actor.get("role") or "")
        if allowed_roles is not None and role not in allowed_roles:
            raise OperatingPermissionDenied("actor role is not authorized")
        actor_store = str(actor.get("store_id") or "")
        if role in _STORE_ROLES and actor_store != store_id:
            raise OperatingPermissionDenied("actor is outside the event store scope")
        if role not in _STORE_ROLES and role not in {
            "founder",
            "hq_operations",
            "system_admin",
        }:
            raise OperatingPermissionDenied("actor role is unsupported")
        return actor

    @staticmethod
    def _require_task_executor(actor: dict[str, Any], task: dict[str, Any]) -> None:
        actor_id = _identifier(actor["assignment_id"])
        assignee_id = str(task.get("assignee_assignment_id") or "")
        role = str(actor.get("role") or "")
        if actor_id == assignee_id:
            return
        if role in _MANAGEMENT_ROLES:
            return
        raise OperatingPermissionDenied("actor is not allowed to execute this task")

    @staticmethod
    def _require_expected(expected: datetime, current: Any) -> None:
        if not isinstance(current, datetime) or current != expected:
            raise OperatingConflict("command version is stale")

    @staticmethod
    def _require_transition(task: dict[str, Any], to_state: str) -> None:
        from_state = str(task.get("status") or "")
        if to_state not in ALLOWED_TASK_TRANSITIONS.get(from_state, set()):
            raise OperatingConflict(
                f"task transition {from_state}->{to_state} is not allowed"
            )

    @staticmethod
    def _acceptance_roles(
        governance: dict[str, Any], severity: str
    ) -> frozenset[str]:
        ceiling = _ACCEPTANCE_ROLE_CEILINGS[severity]
        decision_rights = _json_object(governance.get("decision_rights"))
        configured = decision_rights.get("issue_acceptance_roles")
        if not isinstance(configured, dict) or severity not in configured:
            return ceiling
        raw_roles = configured.get(severity)
        if not isinstance(raw_roles, list):
            raise OperatingRuleViolation("governance acceptance roles are invalid")
        selected = ceiling.intersection(str(role) for role in raw_roles)
        if not selected:
            raise OperatingRuleViolation("governance defines no safe acceptance actor")
        return frozenset(selected)

    @staticmethod
    def _user_actor_fields(actor: dict[str, Any]) -> dict[str, Any]:
        return {
            "actor_type": "user",
            "actor_assignment_id": _identifier(actor["assignment_id"]),
            "actor_reference": None,
        }

    @staticmethod
    def _system_actor_fields(reference: str) -> dict[str, Any]:
        return {
            "actor_type": "system",
            "actor_assignment_id": None,
            "actor_reference": reference,
        }

    def _update_task(
        self,
        transaction: Any,
        *,
        organization_id: str,
        task: dict[str, Any],
        changes: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            return transaction.update_task(
                organization_id=organization_id,
                task_id=_identifier(task["task_id"]),
                locked_updated_at=task["updated_at"],
                changes=changes,
            )
        except OperatingWriteConflict as exc:
            raise OperatingConflict(str(exc)) from exc

    def _update_event(
        self,
        transaction: Any,
        *,
        organization_id: str,
        event: dict[str, Any],
        changes: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            return transaction.update_event(
                organization_id=organization_id,
                event_id=_identifier(event["operating_event_id"]),
                locked_updated_at=event["updated_at"],
                changes=changes,
            )
        except OperatingWriteConflict as exc:
            raise OperatingConflict(str(exc)) from exc

    def _update_workflow(
        self,
        transaction: Any,
        *,
        organization_id: str,
        workflow: dict[str, Any],
        changes: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            return transaction.update_workflow(
                organization_id=organization_id,
                workflow_id=_identifier(workflow["workflow_instance_id"]),
                locked_updated_at=workflow["updated_at"],
                changes=changes,
            )
        except OperatingWriteConflict as exc:
            raise OperatingConflict(str(exc)) from exc

    def _append_transition(
        self,
        transaction: Any,
        *,
        organization_id: str,
        store_id: str,
        aggregate_type: str,
        aggregate_id: str,
        from_state: str | None,
        to_state: str,
        command_type: str,
        actor_fields: dict[str, Any],
        reason: str,
        policy_version: str,
        correlation_id: str,
        occurred_at: datetime,
    ) -> None:
        transaction.append_transition(
            {
                "organization_id": organization_id,
                "store_id": store_id,
                "aggregate_type": aggregate_type,
                "aggregate_id": aggregate_id,
                "from_state": from_state,
                "to_state": to_state,
                "command_type": command_type,
                **actor_fields,
                "reason": reason,
                "policy_version": policy_version,
                "correlation_id": correlation_id,
                "occurred_at": occurred_at,
            }
        )

    def _append_task_transition(
        self,
        transaction: Any,
        command: Any,
        task: dict[str, Any],
        to_state: str,
        actor_fields: dict[str, Any],
        occurred_at: datetime,
        reason: str = "",
    ) -> None:
        self._append_transition(
            transaction,
            organization_id=_identifier(command.organization_id),
            store_id=str(task["store_id"]),
            aggregate_type="task",
            aggregate_id=_identifier(task["task_id"]),
            from_state=str(task["status"]),
            to_state=to_state,
            command_type=self._command_name(command),
            actor_fields=actor_fields,
            reason=reason,
            policy_version=_WORKFLOW_POLICY_VERSION,
            correlation_id=_identifier(command.correlation_id),
            occurred_at=occurred_at,
        )

    def _advance_event_to_active(
        self,
        transaction: Any,
        command: Any,
        event: dict[str, Any],
        actor_fields: dict[str, Any],
        occurred_at: datetime,
    ) -> dict[str, Any]:
        if str(event["status"]) == "active":
            return event
        if str(event["status"]) in {"closed", "cancelled"}:
            raise OperatingConflict("terminal event cannot become active")
        return self._set_event_state(
            transaction,
            command,
            event,
            "active",
            actor_fields,
            occurred_at,
            closed_at=None,
        )

    def _synchronize_event_owner(
        self,
        transaction: Any,
        command: Any,
        event: dict[str, Any],
        owner_assignment_id: str | None,
        actor_fields: dict[str, Any],
        occurred_at: datetime,
    ) -> dict[str, Any]:
        current_owner = str(event.get("owner_assignment_id") or "") or None
        if current_owner == owner_assignment_id:
            return event
        updated = self._update_event(
            transaction,
            organization_id=_identifier(command.organization_id),
            event=event,
            changes={"owner_assignment_id": owner_assignment_id},
        )
        self._append_transition(
            transaction,
            organization_id=_identifier(command.organization_id),
            store_id=str(event["store_id"]),
            aggregate_type="operating_event",
            aggregate_id=_identifier(event["operating_event_id"]),
            from_state=str(event["status"]),
            to_state=str(event["status"]),
            command_type=self._command_name(command),
            actor_fields=actor_fields,
            reason="synchronized event owner with task assignment",
            policy_version=str(event["policy_version"]),
            correlation_id=_identifier(command.correlation_id),
            occurred_at=occurred_at,
        )
        return updated

    def _set_event_state(
        self,
        transaction: Any,
        command: Any,
        event: dict[str, Any],
        status: str,
        actor_fields: dict[str, Any],
        occurred_at: datetime,
        *,
        closed_at: datetime | None,
        reason: str = "",
    ) -> dict[str, Any]:
        if str(event["status"]) == status:
            return event
        updated = self._update_event(
            transaction,
            organization_id=_identifier(command.organization_id),
            event=event,
            changes={"status": status, "closed_at": closed_at},
        )
        self._append_transition(
            transaction,
            organization_id=_identifier(command.organization_id),
            store_id=str(event["store_id"]),
            aggregate_type="operating_event",
            aggregate_id=_identifier(event["operating_event_id"]),
            from_state=str(event["status"]),
            to_state=status,
            command_type=self._command_name(command),
            actor_fields=actor_fields,
            reason=reason,
            policy_version=str(event["policy_version"]),
            correlation_id=_identifier(command.correlation_id),
            occurred_at=occurred_at,
        )
        return updated

    def _advance_workflow_to_running(
        self,
        transaction: Any,
        command: Any,
        workflow: dict[str, Any],
        actor_fields: dict[str, Any],
        occurred_at: datetime,
        current_state: str,
    ) -> dict[str, Any]:
        if (
            str(workflow["status"]) == "running"
            and str(workflow["current_state"]) == current_state
        ):
            return workflow
        if str(workflow["status"]) in {"completed", "cancelled", "failed"}:
            raise OperatingConflict("terminal workflow cannot resume")
        return self._set_workflow_state(
            transaction,
            command,
            workflow,
            status="running",
            current_state=current_state,
            actor_fields=actor_fields,
            occurred_at=occurred_at,
            completed_at=None,
        )

    def _set_workflow_state(
        self,
        transaction: Any,
        command: Any,
        workflow: dict[str, Any],
        *,
        status: str,
        current_state: str,
        actor_fields: dict[str, Any],
        occurred_at: datetime,
        completed_at: datetime | None,
    ) -> dict[str, Any]:
        if (
            str(workflow["status"]) == status
            and str(workflow["current_state"]) == current_state
        ):
            return workflow
        changes: dict[str, Any] = {
            "status": status,
            "current_state": current_state,
            "completed_at": completed_at,
        }
        if status == "running" and workflow.get("started_at") is None:
            changes["started_at"] = occurred_at
        updated = self._update_workflow(
            transaction,
            organization_id=_identifier(command.organization_id),
            workflow=workflow,
            changes=changes,
        )
        event_policy = _WORKFLOW_POLICY_VERSION
        self._append_transition(
            transaction,
            organization_id=_identifier(command.organization_id),
            store_id=str(workflow["store_id"]),
            aggregate_type="workflow_instance",
            aggregate_id=_identifier(workflow["workflow_instance_id"]),
            from_state=str(workflow["status"]),
            to_state=status,
            command_type=self._command_name(command),
            actor_fields=actor_fields,
            reason="",
            policy_version=event_policy,
            correlation_id=_identifier(command.correlation_id),
            occurred_at=occurred_at,
        )
        return updated

    @staticmethod
    def _statuses_after(
        tasks: list[dict[str, Any]], task_id: str, new_status: str
    ) -> list[str]:
        return [
            new_status if _identifier(task["task_id"]) == task_id else str(task["status"])
            for task in tasks
        ]

    @staticmethod
    def _all_active_in(statuses: list[str], allowed: set[str]) -> bool:
        active = [status for status in statuses if status != "cancelled"]
        return bool(active) and all(status in allowed for status in active)

    @staticmethod
    def _command_name(command: Any) -> str:
        name = command.__class__.__name__
        output: list[str] = []
        for index, character in enumerate(name.removesuffix("Command")):
            if character.isupper() and index:
                output.append("_")
            output.append(character.lower())
        return "".join(output)

    @staticmethod
    def _receipt(
        event: dict[str, Any],
        *,
        task: dict[str, Any] | None,
        workflow: dict[str, Any] | None,
    ) -> OperatingCommandReceipt:
        return OperatingCommandReceipt(
            event_id=_identifier(event["operating_event_id"]),
            event_status=str(event["status"]),
            event_updated_at=event["updated_at"],
            task_id=_identifier(task["task_id"]) if task is not None else None,
            task_status=str(task["status"]) if task is not None else None,
            task_updated_at=task["updated_at"] if task is not None else None,
            workflow_id=(
                _identifier(workflow["workflow_instance_id"])
                if workflow is not None
                else None
            ),
            workflow_status=str(workflow["status"]) if workflow is not None else None,
        )
