from __future__ import annotations

from datetime import datetime, timedelta
from enum import Enum
from typing import Literal
from unicodedata import category

from pydantic import BaseModel, ConfigDict, Field, field_validator


INVITE_LIFETIME = timedelta(hours=24)


class AssignmentRole(str, Enum):
    FOUNDER = "founder"
    HQ_OPERATIONS = "hq_operations"
    STORE_MANAGER = "store_manager"
    STORE_EMPLOYEE = "store_employee"
    SYSTEM_ADMIN = "system_admin"


class InviteRole(str, Enum):
    STORE_MANAGER = "store_manager"
    STORE_EMPLOYEE = "store_employee"


class StrictOnboardingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @field_validator("name", "city", "address", "display_name", check_fields=False)
    @classmethod
    def reject_unsafe_human_readable_text(cls, value: str) -> str:
        if any(category(character) in {"Cc", "Cf"} for character in value):
            raise ValueError("value contains unsupported control or format characters")
        return value


class CreateStoreRequest(StrictOnboardingRequest):
    name: str = Field(min_length=1, max_length=120)
    city: str = Field(min_length=1, max_length=80)
    address: str = Field(min_length=1, max_length=240)


class CreateInviteRequest(StrictOnboardingRequest):
    store_id: str | None = Field(default=None, min_length=1, max_length=120)
    role: InviteRole
    display_name: str = Field(min_length=1, max_length=80)


class RedeemInviteRequest(StrictOnboardingRequest):
    token: str = Field(min_length=43, max_length=256)


class StrictOnboardingResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StoreResponse(StrictOnboardingResponse):
    id: str
    name: str
    city: str
    address: str
    status: str


class MemberResponse(StrictOnboardingResponse):
    assignment_id: str
    store_id: str
    display_name: str
    role: AssignmentRole
    status: str


class InviteResponse(StrictOnboardingResponse):
    id: str
    store_id: str
    role: InviteRole
    display_name: str
    status: Literal["pending", "redeemed", "revoked"]
    expires_at: datetime


class CreateInviteResponse(StrictOnboardingResponse):
    invite: InviteResponse
    one_time_link: str


class AuthenticatedResponse(StrictOnboardingResponse):
    status: Literal["authenticated"]
