from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


Severity = Literal["low", "medium", "high", "critical"]


class StrictOperatingModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class CorrelatedCommand(StrictOperatingModel):
    organization_id: UUID
    correlation_id: UUID = Field(default_factory=uuid4)


class CreateEventFromProposalCommand(CorrelatedCommand):
    proposal_id: UUID
    actor_assignment_id: UUID | None = None


class VersionedTaskCommand(CorrelatedCommand):
    task_id: UUID
    actor_assignment_id: UUID
    expected_updated_at: datetime

    @field_validator("expected_updated_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("expected_updated_at must be timezone-aware")
        return value


class AssignTaskCommand(VersionedTaskCommand):
    assignee_assignment_id: UUID | None = None
    external_responsible_name: str = Field(default="", max_length=160)

    @model_validator(mode="after")
    def require_exactly_one_responsible_party(self) -> "AssignTaskCommand":
        has_assignment = self.assignee_assignment_id is not None
        has_external_name = bool(self.external_responsible_name)
        if has_assignment == has_external_name:
            raise ValueError(
                "exactly one of assignee_assignment_id or external_responsible_name is required"
            )
        return self


class StartTaskCommand(VersionedTaskCommand):
    pass


class SubmitTaskCommand(VersionedTaskCommand):
    evidence_ids: list[UUID] = Field(min_length=1, max_length=50)
    result: str = Field(min_length=1, max_length=5000)


class AcceptTaskCommand(VersionedTaskCommand):
    reason: str = Field(default="", max_length=2000)


class ReturnForReworkCommand(VersionedTaskCommand):
    reason: str = Field(min_length=1, max_length=2000)


class VersionedEventCommand(CorrelatedCommand):
    event_id: UUID
    actor_assignment_id: UUID
    expected_updated_at: datetime

    @field_validator("expected_updated_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("expected_updated_at must be timezone-aware")
        return value


class EscalateEventCommand(VersionedEventCommand):
    severity: Severity
    reason: str = Field(min_length=1, max_length=2000)


class CancelEventCommand(VersionedEventCommand):
    reason: str = Field(min_length=1, max_length=2000)


class OperatingCommandReceipt(StrictOperatingModel):
    event_id: str
    event_status: str
    event_updated_at: datetime
    task_id: str | None = None
    task_status: str | None = None
    task_updated_at: datetime | None = None
    workflow_id: str | None = None
    workflow_status: str | None = None
