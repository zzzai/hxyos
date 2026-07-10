from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictProductModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateConversationRequest(StrictProductModel):
    pass


class SendMessageRequest(StrictProductModel):
    content: str = Field(min_length=1, max_length=4000)
    client_message_id: UUID

    @field_validator("content")
    @classmethod
    def normalize_content(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("content must not be blank")
        return normalized


class ProductSource(StrictProductModel):
    title: str
    excerpt: str
    strength: Literal[
        "high",
        "medium",
        "low",
        "reference",
        "candidate",
        "approved",
        "action_asset",
    ]
    url: str | None = None


class ProductMessage(StrictProductModel):
    id: UUID
    conversation_id: UUID
    role: Literal["user", "assistant"]
    content: str
    created_at: datetime
    answer_id: UUID | None
    answer_status: str | None
    confidence: Literal["high", "medium", "low"] | None
    needs_review: bool | None
    sources: list[ProductSource]
    next_actions: list[str]


class ProductConversation(StrictProductModel):
    id: UUID
    title: str
    created_at: datetime
    updated_at: datetime
    last_message_at: datetime | None
    message_count: int = Field(ge=0)
    last_message: ProductMessage | None


class CreateConversationResponse(StrictProductModel):
    conversation: ProductConversation


class ListConversationsResponse(StrictProductModel):
    items: list[ProductConversation]
    count: int = Field(ge=0)


class ConversationDetailResponse(StrictProductModel):
    conversation: ProductConversation
    messages: list[ProductMessage]


class SendMessageResponse(StrictProductModel):
    conversation: ProductConversation
    user_message: ProductMessage
    assistant_message: ProductMessage
