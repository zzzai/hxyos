from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


CanonicalRole = Literal[
    "founder",
    "hq_operations",
    "store_manager",
    "store_employee",
    "system_admin",
]


class UserContext(BaseModel):
    account_id: str
    display_name: str


class OrganizationContext(BaseModel):
    id: str
    name: str


class StoreContext(BaseModel):
    id: str
    name: str


class AssignmentContext(BaseModel):
    assignment_id: str
    organization: OrganizationContext
    store: StoreContext | None
    role: CanonicalRole
    role_label: str
    capabilities: list[str]


class MeResponse(BaseModel):
    user: UserContext
    active_assignment: AssignmentContext
    available_assignments: list[AssignmentContext]
