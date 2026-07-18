from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


Channel = Literal["feishu", "pwa", "admin", "api"]


class StrictChannelModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ChannelIntakePayload(StrictChannelModel):
    organization_id: UUID
    channel: Channel
    channel_tenant_id: str = Field(min_length=1, max_length=160)
    channel_message_id: str = Field(default="", max_length=240)
    channel_thread_id: str = Field(default="", max_length=240)
    channel_user_id: str = Field(min_length=1, max_length=160)
    idempotency_key: str = Field(min_length=1, max_length=240)
    raw_text: str = Field(default="", max_length=20000)
    raw_payload: dict[str, Any] = Field(default_factory=dict)
    source_asset_ids: list[UUID] = Field(default_factory=list, max_length=20)
    intent_hint: str = Field(default="issue", max_length=100)

    @field_validator(
        "channel_tenant_id",
        "channel_message_id",
        "channel_thread_id",
        "channel_user_id",
        "idempotency_key",
        "intent_hint",
    )
    @classmethod
    def normalize_identifier(cls, value: str) -> str:
        return value.strip()

    @field_validator("raw_text")
    @classmethod
    def normalize_raw_text(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def require_content(self) -> "ChannelIntakePayload":
        if not self.raw_text and not self.source_asset_ids:
            raise ValueError("raw_text or source_asset_ids is required")
        return self
