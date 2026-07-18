from __future__ import annotations

import copy
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from pydantic import ValidationError


ORGANIZATION_ID = "30000000-0000-0000-0000-000000000001"
STORE_ID = "hxy-pilot-store"
PROPOSAL_ID = "80000000-0000-0000-0000-000000000001"
ENVELOPE_ID = "24000000-0000-0000-0000-000000000001"
RELATIONSHIP_ID = "22000000-0000-0000-0000-000000000001"
GOVERNANCE_ID = "23000000-0000-0000-0000-000000000001"
REPORTER_ID = "20000000-0000-0000-0000-000000000001"
MANAGER_ID = "20000000-0000-0000-0000-000000000002"
EMPLOYEE_ID = "20000000-0000-0000-0000-000000000003"
FOUNDER_ID = "20000000-0000-0000-0000-000000000004"
HQ_ID = "20000000-0000-0000-0000-000000000005"
EVENT_ID = "81000000-0000-0000-0000-000000000001"
WORKFLOW_ID = "82000000-0000-0000-0000-000000000001"
TASK_ID = "83000000-0000-0000-0000-000000000001"
SECOND_TASK_ID = "83000000-0000-0000-0000-000000000002"
EVIDENCE_ID = "84000000-0000-0000-0000-000000000001"
NOW = datetime(2026, 7, 18, 10, 0, tzinfo=timezone.utc)
DECIDED_AT = NOW - timedelta(minutes=15)
OTHER_EVENT_ID = "81000000-0000-0000-0000-000000000099"
OTHER_WORKFLOW_ID = "82000000-0000-0000-0000-000000000099"


def _assignment(assignment_id: str, role: str, store_id: str | None) -> dict[str, Any]:
    return {
        "assignment_id": assignment_id,
        "organization_id": ORGANIZATION_ID,
        "store_id": store_id,
        "role": role,
        "status": "active",
    }


class FakeOperatingTransaction:
    def __init__(self, repository: "FakeOperatingRepository") -> None:
        self.repository = repository

    def lock_proposal_context(
        self, organization_id: str, proposal_id: str
    ) -> dict[str, Any] | None:
        self.repository.lock_calls.append(("proposal", proposal_id))
        proposal = self.repository.proposals.get(proposal_id)
        if proposal is None or proposal["organization_id"] != organization_id:
            return None
        return copy.deepcopy(proposal)

    def load_current_governance_snapshot(
        self, organization_id: str, store_id: str, effective_at: datetime
    ) -> dict[str, Any] | None:
        assert organization_id == ORGANIZATION_ID
        assert store_id == STORE_ID
        assert effective_at == NOW
        return copy.deepcopy(self.repository.governance_snapshot)

    def load_assignment(
        self, organization_id: str, assignment_id: str
    ) -> dict[str, Any] | None:
        assignment = self.repository.assignments.get(assignment_id)
        if assignment is None or assignment["organization_id"] != organization_id:
            return None
        return copy.deepcopy(assignment)

    def insert_operating_event(self, values: dict[str, Any]) -> dict[str, Any]:
        row = {
            **copy.deepcopy(values),
            "operating_event_id": EVENT_ID,
            "created_at": NOW,
            "updated_at": NOW,
        }
        self.repository.events[EVENT_ID] = row
        return copy.deepcopy(row)

    def insert_workflow_instance(self, values: dict[str, Any]) -> dict[str, Any]:
        row = {
            **copy.deepcopy(values),
            "workflow_instance_id": WORKFLOW_ID,
            "created_at": NOW,
            "updated_at": NOW,
        }
        self.repository.workflows[WORKFLOW_ID] = row
        return copy.deepcopy(row)

    def insert_task(self, values: dict[str, Any]) -> dict[str, Any]:
        task_id = values.get("task_id") or TASK_ID
        row = {
            **copy.deepcopy(values),
            "task_id": task_id,
            "submitted_at": None,
            "accepted_at": None,
            "acceptance_assignment_id": None,
            "result": None,
            "created_at": NOW,
            "updated_at": NOW,
        }
        self.repository.tasks[task_id] = row
        return copy.deepcopy(row)

    def link_proposal_to_event(
        self,
        *,
        organization_id: str,
        proposal_id: str,
        event_id: str,
        accepted_by_assignment_id: str | None,
        decision_policy_version: str | None,
    ) -> dict[str, Any]:
        proposal = self.repository.proposals[proposal_id]
        assert proposal["organization_id"] == organization_id
        proposal["target_id"] = event_id
        if proposal["status"] == "proposed":
            proposal["status"] = "accepted"
            proposal["decided_at"] = NOW
            proposal["decided_by_assignment_id"] = accepted_by_assignment_id
            proposal["decision_policy_version"] = decision_policy_version
        return copy.deepcopy(proposal)

    def append_transition(self, values: dict[str, Any]) -> dict[str, Any]:
        assert values["actor_type"] != "ai"
        row = {**copy.deepcopy(values), "transition_id": f"t-{len(self.repository.transitions) + 1}"}
        self.repository.transitions.append(row)
        return copy.deepcopy(row)

    def lock_task_aggregate(
        self, organization_id: str, task_id: str
    ) -> dict[str, Any] | None:
        self.repository.lock_calls.append(("task_aggregate", task_id))
        task = self.repository.tasks.get(task_id)
        if task is None or task["organization_id"] != organization_id:
            return None
        event = self.repository.events[task["operating_event_id"]]
        workflow = self.repository.workflows[task["workflow_instance_id"]]
        workflows = [
            copy.deepcopy(item)
            for item in self.repository.workflows.values()
            if item.get("operating_event_id") == event["operating_event_id"]
        ]
        tasks = [
            copy.deepcopy(item)
            for item in self.repository.tasks.values()
            if item.get("operating_event_id") == event["operating_event_id"]
        ]
        return {
            "task": copy.deepcopy(task),
            "event": copy.deepcopy(event),
            "workflow": copy.deepcopy(workflow),
            "workflows": workflows,
            "tasks": tasks,
            "governance": copy.deepcopy(self.repository.governance_snapshot),
        }

    def lock_event_aggregate(
        self, organization_id: str, event_id: str
    ) -> dict[str, Any] | None:
        self.repository.lock_calls.append(("event_aggregate", event_id))
        event = self.repository.events.get(event_id)
        if event is None or event["organization_id"] != organization_id:
            return None
        workflow = next(
            (
                item
                for item in self.repository.workflows.values()
                if item["operating_event_id"] == event_id
            ),
            None,
        )
        workflows = [
            copy.deepcopy(item)
            for item in self.repository.workflows.values()
            if item.get("operating_event_id") == event_id
        ]
        tasks = [
            copy.deepcopy(item)
            for item in self.repository.tasks.values()
            if item.get("operating_event_id") == event_id
        ]
        return {
            "event": copy.deepcopy(event),
            "workflow": copy.deepcopy(workflow) if workflow else None,
            "workflows": workflows,
            "tasks": tasks,
            "governance": copy.deepcopy(self.repository.governance_snapshot),
        }

    def evidence_ids_are_valid_for_task(
        self,
        *,
        organization_id: str,
        store_id: str,
        event_id: str,
        task_id: str,
        evidence_ids: list[str],
    ) -> bool:
        return bool(evidence_ids) and all(
            self.repository.evidence.get(evidence_id)
            == {
                "organization_id": organization_id,
                "store_id": store_id,
                "operating_event_id": event_id,
                "task_id": task_id,
                "valid": True,
            }
            for evidence_id in evidence_ids
        )

    def task_has_valid_evidence(
        self, *, organization_id: str, store_id: str, event_id: str, task_id: str
    ) -> bool:
        return any(
            evidence
            == {
                "organization_id": organization_id,
                "store_id": store_id,
                "operating_event_id": event_id,
                "task_id": task_id,
                "valid": True,
            }
            for evidence in self.repository.evidence.values()
        )

    def update_task(
        self,
        *,
        organization_id: str,
        task_id: str,
        locked_updated_at: datetime,
        changes: dict[str, Any],
    ) -> dict[str, Any]:
        row = self.repository.tasks[task_id]
        if row["organization_id"] != organization_id or row["updated_at"] != locked_updated_at:
            raise RuntimeError("stale write")
        row.update(copy.deepcopy(changes))
        row["updated_at"] = row["updated_at"] + timedelta(microseconds=1)
        return copy.deepcopy(row)

    def update_event(
        self,
        *,
        organization_id: str,
        event_id: str,
        locked_updated_at: datetime,
        changes: dict[str, Any],
    ) -> dict[str, Any]:
        row = self.repository.events[event_id]
        if row["organization_id"] != organization_id or row["updated_at"] != locked_updated_at:
            raise RuntimeError("stale write")
        row.update(copy.deepcopy(changes))
        row["updated_at"] = row["updated_at"] + timedelta(microseconds=1)
        return copy.deepcopy(row)

    def update_workflow(
        self,
        *,
        organization_id: str,
        workflow_id: str,
        locked_updated_at: datetime,
        changes: dict[str, Any],
    ) -> dict[str, Any]:
        row = self.repository.workflows[workflow_id]
        if row["organization_id"] != organization_id or row["updated_at"] != locked_updated_at:
            raise RuntimeError("stale write")
        row.update(copy.deepcopy(changes))
        row["updated_at"] = row["updated_at"] + timedelta(microseconds=1)
        return copy.deepcopy(row)


class FakeOperatingRepository:
    def __init__(self, *, severity: str = "low", proposal_status: str = "auto_accepted") -> None:
        self.commit_count = 0
        self.rollback_count = 0
        self.lock_calls: list[tuple[str, str]] = []
        self.metric_facts: list[dict[str, Any]] = []
        self.transitions: list[dict[str, Any]] = []
        self.assignments = {
            REPORTER_ID: _assignment(REPORTER_ID, "store_employee", STORE_ID),
            MANAGER_ID: _assignment(MANAGER_ID, "store_manager", STORE_ID),
            EMPLOYEE_ID: _assignment(EMPLOYEE_ID, "store_employee", STORE_ID),
            FOUNDER_ID: _assignment(FOUNDER_ID, "founder", None),
            HQ_ID: _assignment(HQ_ID, "hq_operations", None),
        }
        self.governance_snapshot = {
            "store_operating_relationship_id": RELATIONSHIP_ID,
            "store_operating_relationship_version": 3,
            "governance_profile_id": GOVERNANCE_ID,
            "governance_profile_version": 7,
            "decision_rights": {
                "issue_acceptance_roles": {
                    "low": ["store_manager", "founder", "hq_operations"],
                    "medium": ["store_manager", "founder", "hq_operations"],
                    "high": ["founder", "hq_operations"],
                    "critical": ["hq_operations"],
                }
            },
        }
        self.proposals = {
            PROPOSAL_ID: {
                "proposal_id": PROPOSAL_ID,
                "organization_id": ORGANIZATION_ID,
                "source_envelope_id": ENVELOPE_ID,
                "store_id": STORE_ID,
                "reporter_assignment_id": REPORTER_ID,
                "received_at": NOW,
                "status": proposal_status,
                "target_id": None,
                "decided_at": (
                    DECIDED_AT if proposal_status in {"auto_accepted", "accepted"} else None
                ),
                "decision_policy_version": (
                    "hxy.issue-intake.v1" if proposal_status == "auto_accepted" else None
                ),
                "risk_level": severity,
                "payload": {
                    "event_type": "facility_issue",
                    "title": "前台灯闪烁",
                    "description": "前台主灯持续闪烁",
                    "location": "前台",
                    "impact": "影响开业准备",
                    "acceptance_criteria": "灯光连续稳定运行30分钟",
                    "suggested_owner_assignment_id": EMPLOYEE_ID,
                    "suggested_due_at": (NOW + timedelta(hours=4)).isoformat(),
                },
            }
        }
        self.events: dict[str, dict[str, Any]] = {}
        self.workflows: dict[str, dict[str, Any]] = {}
        self.tasks: dict[str, dict[str, Any]] = {}
        self.evidence: dict[str, dict[str, Any]] = {}

    @contextmanager
    def transaction(self):
        before = copy.deepcopy(
            (
                self.proposals,
                self.events,
                self.workflows,
                self.tasks,
                self.transitions,
                self.metric_facts,
            )
        )
        try:
            yield FakeOperatingTransaction(self)
        except Exception:
            (
                self.proposals,
                self.events,
                self.workflows,
                self.tasks,
                self.transitions,
                self.metric_facts,
            ) = before
            self.rollback_count += 1
            raise
        else:
            self.commit_count += 1

    def add_valid_evidence(self, task_id: str, evidence_id: str = EVIDENCE_ID) -> None:
        self.evidence[evidence_id] = {
            "organization_id": ORGANIZATION_ID,
            "store_id": STORE_ID,
            "operating_event_id": EVENT_ID,
            "task_id": task_id,
            "valid": True,
        }

    def add_task(self, task_id: str, *, status: str) -> None:
        self.tasks[task_id] = {
            **copy.deepcopy(self.tasks[TASK_ID]),
            "task_id": task_id,
            "status": status,
            "updated_at": NOW,
        }


def _service(repository: FakeOperatingRepository):
    from apps.api.hxy_product.operating_service import OperatingService

    return OperatingService(repository, now=lambda: NOW)


def _create_event(repository: FakeOperatingRepository, *, actor_id: str | None = None):
    from apps.api.hxy_product.operating_schemas import CreateEventFromProposalCommand

    return _service(repository).create_event_from_proposal(
        CreateEventFromProposalCommand(
            organization_id=ORGANIZATION_ID,
            proposal_id=PROPOSAL_ID,
            actor_assignment_id=actor_id,
        )
    )


def test_task_state_machine_is_frozen() -> None:
    from apps.api.hxy_product.operating_service import ALLOWED_TASK_TRANSITIONS

    assert ALLOWED_TASK_TRANSITIONS == {
        "open": {"assigned", "in_progress", "cancelled"},
        "assigned": {"in_progress", "cancelled"},
        "in_progress": {"submitted", "cancelled"},
        "submitted": {"accepted", "rework"},
        "rework": {"in_progress", "submitted", "cancelled"},
        "accepted": set(),
        "cancelled": set(),
    }


def test_event_creation_snapshots_governance_and_records_policy_actor() -> None:
    repository = FakeOperatingRepository()

    receipt = _create_event(repository)

    event = repository.events[EVENT_ID]
    assert receipt.event_id == EVENT_ID
    assert event["store_operating_relationship_id"] == RELATIONSHIP_ID
    assert event["store_operating_relationship_version"] == 3
    assert event["governance_profile_id"] == GOVERNANCE_ID
    assert event["governance_profile_version"] == 7
    assert event["policy_version"] == "hxy.operating-workflow.v1"
    proposal_transition = next(
        item for item in repository.transitions if item["aggregate_type"] == "ai_proposal"
    )
    assert proposal_transition["actor_type"] == "policy"
    assert proposal_transition["actor_reference"] == "hxy.issue-intake.v1"
    assert proposal_transition["policy_version"] == "hxy.issue-intake.v1"
    event_transitions = [
        item
        for item in repository.transitions
        if item["aggregate_type"] == "operating_event"
    ]
    assert event["policy_version"] == "hxy.operating-workflow.v1"
    assert event_transitions[0]["policy_version"] == "hxy.operating-workflow.v1"
    assert all(item["actor_type"] != "ai" for item in repository.transitions)
    assert repository.commit_count == 1


def test_already_accepted_proposal_keeps_original_decision_provenance() -> None:
    repository = FakeOperatingRepository(proposal_status="accepted")
    repository.proposals[PROPOSAL_ID]["decided_by_assignment_id"] = MANAGER_ID

    receipt = _create_event(repository, actor_id=FOUNDER_ID)

    assert receipt.event_id == EVENT_ID
    proposal_transition = next(
        item for item in repository.transitions if item["aggregate_type"] == "ai_proposal"
    )
    assert proposal_transition["actor_type"] == "user"
    assert proposal_transition["actor_assignment_id"] == MANAGER_ID
    assert proposal_transition["occurred_at"] == DECIDED_AT
    assert proposal_transition["from_state"] == "proposed"
    assert proposal_transition["to_state"] == "accepted"
    materialization = [
        item
        for item in repository.transitions
        if item["aggregate_type"] == "ai_proposal"
        and item["command_type"] == "materialize_event_from_proposal"
    ]
    assert len(materialization) == 1
    assert materialization[0]["from_state"] == "accepted"
    assert materialization[0]["to_state"] == "accepted"
    assert materialization[0]["occurred_at"] == NOW


def test_inactive_historical_decider_does_not_block_materialization() -> None:
    repository = FakeOperatingRepository(proposal_status="accepted")
    repository.proposals[PROPOSAL_ID]["decided_by_assignment_id"] = MANAGER_ID
    repository.assignments[MANAGER_ID]["status"] = "inactive"

    receipt = _create_event(repository)

    assert receipt.event_id == EVENT_ID
    decision_transition = next(
        item
        for item in repository.transitions
        if item["aggregate_type"] == "ai_proposal"
        and item["command_type"] == "record_proposal_decision"
    )
    assert decision_transition["actor_assignment_id"] == MANAGER_ID


def test_policy_accepted_proposal_can_be_materialized_without_user_actor() -> None:
    repository = FakeOperatingRepository(proposal_status="accepted")
    repository.proposals[PROPOSAL_ID]["decided_by_assignment_id"] = None
    repository.proposals[PROPOSAL_ID]["decision_policy_version"] = "hxy.issue-intake.v1"

    receipt = _create_event(repository)

    assert receipt.event_id == EVENT_ID
    proposal_transition = next(
        item for item in repository.transitions if item["aggregate_type"] == "ai_proposal"
    )
    assert proposal_transition["actor_type"] == "policy"
    assert proposal_transition["actor_reference"] == "hxy.issue-intake.v1"


def test_manual_proposal_acceptance_requires_authorized_user_actor() -> None:
    from apps.api.hxy_product.operating_service import OperatingPermissionDenied

    repository = FakeOperatingRepository(proposal_status="proposed")
    with pytest.raises(OperatingPermissionDenied):
        _create_event(repository, actor_id=EMPLOYEE_ID)

    receipt = _create_event(repository, actor_id=MANAGER_ID)

    assert receipt.event_id == EVENT_ID
    transition = next(
        item for item in repository.transitions if item["aggregate_type"] == "ai_proposal"
    )
    assert transition["actor_type"] == "user"
    assert transition["actor_assignment_id"] == MANAGER_ID
    assert repository.proposals[PROPOSAL_ID]["status"] == "accepted"


def test_acceptance_requires_actor_and_valid_evidence() -> None:
    from apps.api.hxy_product.operating_schemas import AcceptTaskCommand
    from apps.api.hxy_product.operating_service import OperatingRuleViolation

    repository = FakeOperatingRepository()
    _create_event(repository)
    repository.tasks[TASK_ID]["status"] = "submitted"

    with pytest.raises(ValidationError):
        AcceptTaskCommand(
            organization_id=ORGANIZATION_ID,
            task_id=TASK_ID,
            actor_assignment_id=None,
            expected_updated_at=NOW,
        )

    command = AcceptTaskCommand(
        organization_id=ORGANIZATION_ID,
        task_id=TASK_ID,
        actor_assignment_id=MANAGER_ID,
        expected_updated_at=NOW,
    )
    with pytest.raises(OperatingRuleViolation, match="evidence"):
        _service(repository).accept_task(command)

    repository.add_valid_evidence(TASK_ID)
    receipt = _service(repository).accept_task(command)

    assert receipt.task_status == "accepted"
    assert receipt.event_status == "closed"
    assert repository.tasks[TASK_ID]["acceptance_assignment_id"] == MANAGER_ID


def test_evidence_from_another_store_is_not_valid_for_acceptance() -> None:
    from apps.api.hxy_product.operating_schemas import AcceptTaskCommand
    from apps.api.hxy_product.operating_service import OperatingRuleViolation

    repository = FakeOperatingRepository()
    _create_event(repository)
    repository.tasks[TASK_ID]["status"] = "submitted"
    repository.add_valid_evidence(TASK_ID)
    repository.evidence[EVIDENCE_ID]["store_id"] = "another-store"

    with pytest.raises(OperatingRuleViolation, match="evidence"):
        _service(repository).accept_task(
            AcceptTaskCommand(
                organization_id=ORGANIZATION_ID,
                task_id=TASK_ID,
                actor_assignment_id=MANAGER_ID,
                expected_updated_at=NOW,
            )
        )


def test_event_becomes_resolved_only_after_all_active_tasks_are_submitted() -> None:
    from apps.api.hxy_product.operating_schemas import SubmitTaskCommand

    repository = FakeOperatingRepository()
    _create_event(repository)
    repository.tasks[TASK_ID]["status"] = "in_progress"
    repository.add_task(SECOND_TASK_ID, status="in_progress")
    repository.add_valid_evidence(TASK_ID)
    repository.add_valid_evidence(
        SECOND_TASK_ID, "84000000-0000-0000-0000-000000000002"
    )
    service = _service(repository)

    first = service.submit_task(
        SubmitTaskCommand(
            organization_id=ORGANIZATION_ID,
            task_id=TASK_ID,
            actor_assignment_id=EMPLOYEE_ID,
            expected_updated_at=NOW,
            evidence_ids=[EVIDENCE_ID],
            result="已更换灯具",
        )
    )
    second = service.submit_task(
        SubmitTaskCommand(
            organization_id=ORGANIZATION_ID,
            task_id=SECOND_TASK_ID,
            actor_assignment_id=EMPLOYEE_ID,
            expected_updated_at=NOW,
            evidence_ids=["84000000-0000-0000-0000-000000000002"],
            result="已复测线路",
        )
    )

    assert first.event_status == "active"
    assert second.event_status == "resolved"


@pytest.mark.parametrize(
    ("severity", "denied_actor", "allowed_actor"),
    [
        ("medium", EMPLOYEE_ID, MANAGER_ID),
        ("high", MANAGER_ID, FOUNDER_ID),
        ("critical", FOUNDER_ID, HQ_ID),
    ],
)
def test_acceptance_authority_follows_snapshotted_risk_policy(
    severity: str, denied_actor: str, allowed_actor: str
) -> None:
    from apps.api.hxy_product.operating_schemas import AcceptTaskCommand
    from apps.api.hxy_product.operating_service import OperatingPermissionDenied

    repository = FakeOperatingRepository(severity=severity)
    _create_event(repository)
    repository.tasks[TASK_ID]["status"] = "submitted"
    repository.add_valid_evidence(TASK_ID)
    service = _service(repository)

    with pytest.raises(OperatingPermissionDenied):
        service.accept_task(
            AcceptTaskCommand(
                organization_id=ORGANIZATION_ID,
                task_id=TASK_ID,
                actor_assignment_id=denied_actor,
                expected_updated_at=NOW,
            )
        )

    receipt = service.accept_task(
        AcceptTaskCommand(
            organization_id=ORGANIZATION_ID,
            task_id=TASK_ID,
            actor_assignment_id=allowed_actor,
            expected_updated_at=NOW,
        )
    )

    assert receipt.event_status == "closed"


def test_rework_appends_transition_without_writing_metric_fact() -> None:
    from apps.api.hxy_product.operating_schemas import ReturnForReworkCommand

    repository = FakeOperatingRepository()
    _create_event(repository)
    repository.tasks[TASK_ID]["status"] = "submitted"
    repository.events[EVENT_ID]["status"] = "resolved"
    repository.workflows[WORKFLOW_ID]["status"] = "waiting"
    repository.workflows[WORKFLOW_ID]["current_state"] = "waiting_acceptance"

    receipt = _service(repository).return_for_rework(
        ReturnForReworkCommand(
            organization_id=ORGANIZATION_ID,
            task_id=TASK_ID,
            actor_assignment_id=MANAGER_ID,
            expected_updated_at=NOW,
            reason="照片中仍有闪烁",
        )
    )

    assert receipt.task_status == "rework"
    assert receipt.event_status == "active"
    assert any(
        transition["aggregate_type"] == "task"
        and transition["from_state"] == "submitted"
        and transition["to_state"] == "rework"
        for transition in repository.transitions
    )
    assert repository.metric_facts == []


def test_stale_command_raises_409_style_conflict_without_partial_write() -> None:
    from apps.api.hxy_product.operating_schemas import StartTaskCommand
    from apps.api.hxy_product.operating_service import OperatingConflict

    repository = FakeOperatingRepository()
    _create_event(repository)
    transition_count = len(repository.transitions)
    stale_at = NOW - timedelta(minutes=1)

    with pytest.raises(OperatingConflict) as captured:
        _service(repository).start_task(
            StartTaskCommand(
                organization_id=ORGANIZATION_ID,
                task_id=TASK_ID,
                actor_assignment_id=EMPLOYEE_ID,
                expected_updated_at=stale_at,
            )
        )

    assert captured.value.status_code == 409
    assert repository.tasks[TASK_ID]["status"] == "assigned"
    assert len(repository.transitions) == transition_count
    assert repository.rollback_count == 1


def test_assignment_and_start_validate_actor_scope_and_append_transitions() -> None:
    from apps.api.hxy_product.operating_schemas import AssignTaskCommand, StartTaskCommand
    from apps.api.hxy_product.operating_service import OperatingPermissionDenied

    repository = FakeOperatingRepository()
    _create_event(repository)
    repository.tasks[TASK_ID]["status"] = "open"
    repository.tasks[TASK_ID]["assignee_assignment_id"] = None
    repository.tasks[TASK_ID]["visibility"] = "store"
    repository.events[EVENT_ID]["status"] = "open"
    repository.workflows[WORKFLOW_ID]["status"] = "pending"
    repository.workflows[WORKFLOW_ID]["current_state"] = "task_open"
    service = _service(repository)

    with pytest.raises(OperatingPermissionDenied):
        service.assign_task(
            AssignTaskCommand(
                organization_id=ORGANIZATION_ID,
                task_id=TASK_ID,
                actor_assignment_id=EMPLOYEE_ID,
                expected_updated_at=NOW,
                assignee_assignment_id=EMPLOYEE_ID,
            )
        )

    assigned = service.assign_task(
        AssignTaskCommand(
            organization_id=ORGANIZATION_ID,
            task_id=TASK_ID,
            actor_assignment_id=MANAGER_ID,
            expected_updated_at=NOW,
            assignee_assignment_id=EMPLOYEE_ID,
        )
    )
    started = service.start_task(
        StartTaskCommand(
            organization_id=ORGANIZATION_ID,
            task_id=TASK_ID,
            actor_assignment_id=EMPLOYEE_ID,
            expected_updated_at=repository.tasks[TASK_ID]["updated_at"],
        )
    )

    assert assigned.task_status == "assigned"
    assert started.task_status == "in_progress"
    assert started.event_status == "active"
    task_transitions = [
        item for item in repository.transitions if item["aggregate_type"] == "task"
    ]
    assert any(item["command_type"] == "assign_task" for item in task_transitions)
    assert any(item["command_type"] == "start_task" for item in task_transitions)


def test_assignment_roles_can_be_narrowed_by_governance_snapshot() -> None:
    from apps.api.hxy_product.operating_schemas import AssignTaskCommand
    from apps.api.hxy_product.operating_service import OperatingPermissionDenied

    repository = FakeOperatingRepository()
    _create_event(repository)
    repository.tasks[TASK_ID]["status"] = "open"
    repository.tasks[TASK_ID]["assignee_assignment_id"] = None
    repository.governance_snapshot["decision_rights"]["issue_assignment_roles"] = [
        "founder"
    ]

    with pytest.raises(OperatingPermissionDenied):
        _service(repository).assign_task(
            AssignTaskCommand(
                organization_id=ORGANIZATION_ID,
                task_id=TASK_ID,
                actor_assignment_id=MANAGER_ID,
                expected_updated_at=NOW,
                assignee_assignment_id=EMPLOYEE_ID,
            )
        )


def test_rework_roles_can_be_narrowed_by_governance_snapshot() -> None:
    from apps.api.hxy_product.operating_schemas import ReturnForReworkCommand
    from apps.api.hxy_product.operating_service import OperatingPermissionDenied

    repository = FakeOperatingRepository()
    _create_event(repository)
    repository.tasks[TASK_ID]["status"] = "submitted"
    repository.governance_snapshot["decision_rights"]["issue_rework_roles"] = [
        "founder"
    ]

    with pytest.raises(OperatingPermissionDenied):
        _service(repository).return_for_rework(
            ReturnForReworkCommand(
                organization_id=ORGANIZATION_ID,
                task_id=TASK_ID,
                actor_assignment_id=MANAGER_ID,
                expected_updated_at=NOW,
                reason="需总部复核后返工",
            )
        )


def test_escalation_roles_can_be_narrowed_by_governance_snapshot() -> None:
    from apps.api.hxy_product.operating_schemas import EscalateEventCommand
    from apps.api.hxy_product.operating_service import OperatingPermissionDenied

    repository = FakeOperatingRepository(severity="medium")
    _create_event(repository)
    repository.governance_snapshot["decision_rights"]["issue_escalation_roles"] = [
        "founder"
    ]

    with pytest.raises(OperatingPermissionDenied):
        _service(repository).escalate_event(
            EscalateEventCommand(
                organization_id=ORGANIZATION_ID,
                event_id=EVENT_ID,
                actor_assignment_id=MANAGER_ID,
                expected_updated_at=NOW,
                severity="high",
                reason="需总部升级",
            )
        )


def test_cancellation_roles_can_be_narrowed_by_governance_snapshot() -> None:
    from apps.api.hxy_product.operating_schemas import CancelEventCommand
    from apps.api.hxy_product.operating_service import OperatingPermissionDenied

    repository = FakeOperatingRepository()
    _create_event(repository)
    repository.governance_snapshot["decision_rights"]["issue_cancellation_roles"] = [
        "founder"
    ]

    with pytest.raises(OperatingPermissionDenied):
        _service(repository).cancel_event(
            CancelEventCommand(
                organization_id=ORGANIZATION_ID,
                event_id=EVENT_ID,
                actor_assignment_id=MANAGER_ID,
                expected_updated_at=NOW,
                reason="需总部确认取消",
            )
        )


def test_assignment_synchronizes_event_owner() -> None:
    from apps.api.hxy_product.operating_schemas import AssignTaskCommand

    repository = FakeOperatingRepository()
    _create_event(repository)
    repository.tasks[TASK_ID]["status"] = "open"
    repository.tasks[TASK_ID]["assignee_assignment_id"] = None
    repository.events[EVENT_ID]["owner_assignment_id"] = None

    _service(repository).assign_task(
        AssignTaskCommand(
            organization_id=ORGANIZATION_ID,
            task_id=TASK_ID,
            actor_assignment_id=MANAGER_ID,
            expected_updated_at=NOW,
            assignee_assignment_id=EMPLOYEE_ID,
        )
    )

    assert repository.events[EVENT_ID]["owner_assignment_id"] == EMPLOYEE_ID


def test_task_workflow_event_mismatch_fails_closed() -> None:
    from apps.api.hxy_product.operating_schemas import StartTaskCommand
    from apps.api.hxy_product.operating_service import OperatingConflict

    repository = FakeOperatingRepository()
    _create_event(repository)
    repository.workflows[WORKFLOW_ID]["operating_event_id"] = OTHER_EVENT_ID

    with pytest.raises(OperatingConflict, match="aggregate"):
        _service(repository).start_task(
            StartTaskCommand(
                organization_id=ORGANIZATION_ID,
                task_id=TASK_ID,
                actor_assignment_id=EMPLOYEE_ID,
                expected_updated_at=NOW,
            )
        )


def test_multiple_workflows_for_event_fail_closed_in_v1() -> None:
    from apps.api.hxy_product.operating_schemas import StartTaskCommand
    from apps.api.hxy_product.operating_service import OperatingConflict

    repository = FakeOperatingRepository()
    _create_event(repository)
    repository.workflows[OTHER_WORKFLOW_ID] = {
        **copy.deepcopy(repository.workflows[WORKFLOW_ID]),
        "workflow_instance_id": OTHER_WORKFLOW_ID,
        "workflow_type": "secondary_review",
    }

    with pytest.raises(OperatingConflict, match="exactly one workflow"):
        _service(repository).start_task(
            StartTaskCommand(
                organization_id=ORGANIZATION_ID,
                task_id=TASK_ID,
                actor_assignment_id=EMPLOYEE_ID,
                expected_updated_at=NOW,
            )
        )


def test_escalation_only_increases_severity_and_uses_event_lock() -> None:
    from apps.api.hxy_product.operating_schemas import EscalateEventCommand
    from apps.api.hxy_product.operating_service import OperatingRuleViolation

    repository = FakeOperatingRepository(severity="medium")
    _create_event(repository)
    service = _service(repository)

    receipt = service.escalate_event(
        EscalateEventCommand(
            organization_id=ORGANIZATION_ID,
            event_id=EVENT_ID,
            actor_assignment_id=MANAGER_ID,
            expected_updated_at=NOW,
            severity="high",
            reason="涉及开业工期",
        )
    )

    assert receipt.event_status == "active"
    assert repository.events[EVENT_ID]["severity"] == "high"
    assert ("event_aggregate", EVENT_ID) in repository.lock_calls
    with pytest.raises(OperatingRuleViolation):
        service.escalate_event(
            EscalateEventCommand(
                organization_id=ORGANIZATION_ID,
                event_id=EVENT_ID,
                actor_assignment_id=MANAGER_ID,
                expected_updated_at=repository.events[EVENT_ID]["updated_at"],
                severity="low",
                reason="尝试降级",
            )
        )


def test_cancel_event_cancels_active_tasks_and_workflow_atomically() -> None:
    from apps.api.hxy_product.operating_schemas import CancelEventCommand

    repository = FakeOperatingRepository()
    _create_event(repository)
    repository.tasks[TASK_ID]["status"] = "in_progress"
    service = _service(repository)

    receipt = service.cancel_event(
        CancelEventCommand(
            organization_id=ORGANIZATION_ID,
            event_id=EVENT_ID,
            actor_assignment_id=MANAGER_ID,
            expected_updated_at=NOW,
            reason="现场确认并非故障",
        )
    )

    assert receipt.event_status == "cancelled"
    assert repository.tasks[TASK_ID]["status"] == "cancelled"
    assert repository.workflows[WORKFLOW_ID]["status"] == "cancelled"
    assert repository.commit_count == 2  # event creation and cancellation


def test_repository_locks_event_before_task_rows() -> None:
    from apps.api.hxy_product.operating_repository import OperatingRepository

    repository = OperatingRepository("postgresql://workflow.test/hxy")
    calls: list[str] = []

    class Result:
        def __init__(self, row=None, rows=None):
            self.row = row
            self.rows = rows or []

        def fetchone(self):
            return self.row

        def fetchall(self):
            return self.rows

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, sql: str, _params: tuple[Any, ...]):
            normalized = " ".join(sql.split())
            calls.append(normalized)
            if "SELECT operating_event_id::text" in normalized and "FROM hxy_product_tasks" in normalized:
                return Result({"operating_event_id": EVENT_ID})
            if "FROM hxy_operating_events AS event" in normalized and "FOR UPDATE OF event" in normalized:
                return Result(
                    {
                        "operating_event_id": EVENT_ID,
                        "organization_id": ORGANIZATION_ID,
                        "store_id": STORE_ID,
                        "governance_profile_id": GOVERNANCE_ID,
                        "governance_profile_version": 7,
                    }
                )
            if "FROM hxy_product_tasks AS task" in normalized and "FOR UPDATE OF task" in normalized:
                return Result({"task_id": TASK_ID, "workflow_instance_id": WORKFLOW_ID})
            if "FROM hxy_workflow_instances" in normalized and "FOR UPDATE" in normalized:
                return Result({"workflow_instance_id": WORKFLOW_ID})
            if "FROM hxy_product_tasks" in normalized and "FOR UPDATE" in normalized:
                return Result(rows=[{"task_id": TASK_ID}])
            if "FROM hxy_governance_profiles" in normalized and "FOR SHARE" in normalized:
                return Result({"decision_rights": {}})
            raise AssertionError(normalized)

    repository.connect = lambda: Connection()

    with repository.transaction() as transaction:
        aggregate = transaction.lock_task_aggregate(ORGANIZATION_ID, TASK_ID)

    assert aggregate is not None
    event_lock = next(i for i, sql in enumerate(calls) if "FOR UPDATE OF event" in sql)
    task_lock = next(i for i, sql in enumerate(calls) if "FOR UPDATE OF task" in sql)
    assert event_lock < task_lock
    task_list_sql = next(
        sql
        for sql in calls
        if "FROM hxy_product_tasks" in sql
        and "FOR UPDATE" in sql
        and "FOR UPDATE OF task" not in sql
    )
    assert "ORDER BY hxy_product_tasks.task_id" in task_list_sql


def test_repository_evidence_queries_require_clean_same_scope_material() -> None:
    from apps.api.hxy_product.operating_repository import OperatingRepository

    repository = OperatingRepository("postgresql://workflow.test/hxy")
    calls: list[tuple[str, tuple[Any, ...]]] = []

    class Result:
        def fetchone(self):
            return {"valid_count": 1, "has_evidence": True}

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, sql: str, params: tuple[Any, ...]):
            calls.append((" ".join(sql.split()), params))
            return Result()

    repository.connect = lambda: Connection()

    with repository.transaction() as transaction:
        assert transaction.evidence_ids_are_valid_for_task(
            organization_id=ORGANIZATION_ID,
            store_id=STORE_ID,
            event_id=EVENT_ID,
            task_id=TASK_ID,
            evidence_ids=[EVIDENCE_ID],
        )
        assert transaction.task_has_valid_evidence(
            organization_id=ORGANIZATION_ID,
            store_id=STORE_ID,
            event_id=EVENT_ID,
            task_id=TASK_ID,
        )

    assert len(calls) == 2
    for sql, params in calls:
        assert "material.scan_status = 'clean'" in sql
        assert "(material.store_id IS NULL OR material.store_id = %s)" in sql
        assert params[-1] == STORE_ID
