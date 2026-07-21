from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


ProductEventName = Literal[
    "intake_succeeded",
    "service_feedback_completed",
    "briefing_feedback",
    "learning_completed",
    "closing_review_completed",
]


class StrictProductEventModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProductEventRequest(StrictProductEventModel):
    client_event_id: UUID
    event_name: Literal["briefing_feedback"]
    subject_id: UUID
    useful: bool


class PublicProductEvent(StrictProductEventModel):
    id: UUID
    event_name: ProductEventName
    created_at: datetime


class ProductEventResponse(StrictProductEventModel):
    event: PublicProductEvent
