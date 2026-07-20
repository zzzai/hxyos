from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictLearningModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class LearningScenario(StrictLearningModel):
    customer_message: str


class LearningAction(StrictLearningModel):
    id: str
    title: str
    purpose: str
    estimated_minutes: int
    scenario: LearningScenario
    response_modes: list[Literal["text", "voice"]]


class PrivateLearningProgress(StrictLearningModel):
    visibility: Literal["private"]
    attempts: int
    mastered: list[str]
    practicing: list[str]
    needs_attention: list[str]


class LearningHomeResponse(StrictLearningModel):
    next_action: LearningAction
    progress: PrivateLearningProgress
    limitations: list[str]


class LearningPracticeRequest(StrictLearningModel):
    action_id: str = Field(min_length=1, max_length=80)
    employee_answer: str = Field(min_length=1, max_length=4000)

    @field_validator("action_id", "employee_answer")
    @classmethod
    def reject_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be blank")
        return value.strip()


class LearningAttempt(StrictLearningModel):
    id: str
    score: int
    level: Literal["excellent", "pass", "retrain"]
    needs_retrain: bool
    standard_script: str
    correction_points: list[str]
    physical_technique: Literal["not_assessed"]


class LearningPracticeResponse(StrictLearningModel):
    attempt: LearningAttempt
    next_action: LearningAction
    progress: PrivateLearningProgress
    limitations: list[str]
