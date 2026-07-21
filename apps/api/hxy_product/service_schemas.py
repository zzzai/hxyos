from __future__ import annotations

import re
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


_MAINLAND_MOBILE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")


def reject_plain_mobile(value: str) -> str:
    normalized = value.strip()
    if _MAINLAND_MOBILE.search(normalized):
        raise ValueError("plain mobile numbers are not accepted")
    return normalized


class StrictServiceModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class CustomerIdentityHint(StrictServiceModel):
    phone_suffix: str | None = Field(default=None, pattern=r"^\d{4}$")
    alias: str | None = Field(default=None, max_length=80)

    @field_validator("alias")
    @classmethod
    def validate_alias(cls, value: str | None) -> str | None:
        return reject_plain_mobile(value) if value else value


class CreateServiceContextRequest(StrictServiceModel):
    client_context_id: UUID
    occurred_at: datetime
    service_label: str = Field(min_length=1, max_length=120)
    customer_hint: CustomerIdentityHint = Field(default_factory=CustomerIdentityHint)

    @field_validator("occurred_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("occurred_at must include a timezone")
        return value

    @field_validator("service_label")
    @classmethod
    def validate_service_label(cls, value: str) -> str:
        return reject_plain_mobile(value)


class PublicServiceContext(StrictServiceModel):
    id: UUID
    status: Literal["provisional", "reconciled", "closed"]
    occurred_at: datetime
    service_label: str
    customer_display: str
    feedback_count: int = Field(ge=0)
    created_at: datetime


class ServiceContextResponse(StrictServiceModel):
    context: PublicServiceContext


class ServiceContextListResponse(StrictServiceModel):
    contexts: list[PublicServiceContext]


class AddServiceFeedbackRequest(StrictServiceModel):
    client_feedback_id: UUID
    text: str = Field(default="", max_length=4000)
    source_asset_ids: list[UUID] = Field(default_factory=list, max_length=10)
    duration_ms: int = Field(ge=0, le=86_400_000)

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        return reject_plain_mobile(value)

    @model_validator(mode="after")
    def require_feedback_content(self) -> "AddServiceFeedbackRequest":
        if not self.text and not self.source_asset_ids:
            raise ValueError("feedback text or a protected asset is required")
        return self


class PublicServiceFeedbackReceipt(StrictServiceModel):
    id: UUID
    context_id: UUID
    status: Literal["received"]
    created_at: datetime


class ServiceFeedbackResponse(StrictServiceModel):
    feedback: PublicServiceFeedbackReceipt
    context: PublicServiceContext


class ReconcileServiceContextRequest(StrictServiceModel):
    source_system: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{1,79}$")
    external_customer_ref: str = Field(min_length=1, max_length=240)
    external_service_ref: str | None = Field(default=None, min_length=1, max_length=240)
