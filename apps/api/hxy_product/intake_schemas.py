from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .conversation_schemas import ProductConversation, ProductMessage
from .record_schemas import OrganizationRecord


class StrictIntakeModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class UnifiedIntakeRequest(StrictIntakeModel):
    client_submission_id: UUID
    conversation_id: UUID | None = None
    text: str = Field(default="", max_length=4000)
    source_asset_ids: list[UUID] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def validate_content_and_conversation(self) -> "UnifiedIntakeRequest":
        if not self.text and not self.source_asset_ids:
            raise ValueError("text or source_asset_ids is required")
        if self.text and self.conversation_id is None:
            raise ValueError("conversation_id is required when text is present")
        return self


class UnifiedIntakeResponse(StrictIntakeModel):
    receipt: Literal["已收到，正在处理"]
    record: OrganizationRecord
    conversation: ProductConversation | None = None
    user_message: ProductMessage | None = None
    assistant_message: ProductMessage | None = None
