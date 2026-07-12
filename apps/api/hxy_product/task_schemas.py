from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


TaskPriority = Literal["low", "normal", "high", "urgent"]
TaskStatus = Literal["open", "in_progress", "completed", "cancelled"]
TaskVisibility = Literal["assignee", "store"]


class CreateTaskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=160)
    details: str = Field(default="", max_length=5000)
    priority: TaskPriority = "normal"
    visibility: TaskVisibility = "assignee"
    assignee_assignment_id: UUID | None = None
    store_id: str | None = Field(default=None, min_length=1, max_length=120)
    source_conversation_id: UUID | None = None
    source_message_id: UUID | None = None
    due_at: datetime | None = None

    @model_validator(mode="after")
    def validate_scope(self) -> "CreateTaskRequest":
        if self.visibility == "assignee" and self.assignee_assignment_id is None:
            raise ValueError("assignee_assignment_id is required")
        if (self.source_conversation_id is None) != (self.source_message_id is None):
            raise ValueError("source conversation and message must be provided together")
        return self


class UpdateTaskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["in_progress", "completed", "cancelled"]
    result: str | None = Field(default=None, max_length=5000)

    @model_validator(mode="after")
    def validate_result(self) -> "UpdateTaskRequest":
        if self.status == "completed" and not str(self.result or "").strip():
            raise ValueError("result is required when completing a task")
        return self


class TaskView(BaseModel):
    id: str
    title: str
    details: str
    priority: TaskPriority
    status: TaskStatus
    visibility: TaskVisibility
    store_id: str | None
    assignee_assignment_id: str | None
    source_conversation_id: str | None
    source_message_id: str | None
    result: str | None
    due_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class TaskResponse(BaseModel):
    task: TaskView


class TaskListResponse(BaseModel):
    items: list[TaskView]
    count: int
