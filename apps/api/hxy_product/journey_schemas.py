from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictJourneyModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class JourneySuggestion(StrictJourneyModel):
    type: Literal["ask", "tasks", "training", "issue"]
    label: str
    prompt: str | None = None


class JourneySuggestionsResponse(StrictJourneyModel):
    items: list[JourneySuggestion]


class TrainingJourneyRequest(StrictJourneyModel):
    customer_question: str = Field(min_length=1, max_length=1000)
    employee_answer: str = Field(min_length=1, max_length=4000)

    @field_validator("customer_question", "employee_answer")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be blank")
        return normalized


class IssueJourneyRequest(StrictJourneyModel):
    title: str = Field(min_length=1, max_length=160)
    details: str = Field(min_length=1, max_length=5000)
    source_task_id: UUID | None = None

    @field_validator("title", "details")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be blank")
        return normalized


class JourneyResultResponse(StrictJourneyModel):
    result_type: Literal["training_result", "issue_report"]
    primary_result: dict[str, Any]
    actions: list[dict[str, str]]
    sources: list[dict[str, Any]]
    limitations: list[str]
    artifact: dict[str, str] | None
