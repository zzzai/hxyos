from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, Mapping

from .onboarding_schemas import AssignmentRole, InviteRole


@dataclass(frozen=True, slots=True)
class ResolvedAssignment:
    assignment_id: str
    organization_id: str
    store_id: str | None
    role: AssignmentRole


@dataclass(frozen=True, slots=True)
class ResolvedStore:
    organization_id: str
    store_id: str


INVITABLE_ROLES_BY_ACTOR: Final[Mapping[AssignmentRole, frozenset[InviteRole]]] = (
    MappingProxyType(
        {
            AssignmentRole.FOUNDER: frozenset({InviteRole.STORE_MANAGER}),
            AssignmentRole.HQ_OPERATIONS: frozenset(),
            AssignmentRole.STORE_MANAGER: frozenset({InviteRole.STORE_EMPLOYEE}),
            AssignmentRole.STORE_EMPLOYEE: frozenset(),
            AssignmentRole.SYSTEM_ADMIN: frozenset(),
        }
    )
)

DEACTIVATABLE_ROLES_BY_ACTOR: Final[
    Mapping[AssignmentRole, frozenset[AssignmentRole]]
] = MappingProxyType(
    {
        AssignmentRole.FOUNDER: frozenset({AssignmentRole.STORE_MANAGER}),
        AssignmentRole.HQ_OPERATIONS: frozenset(),
        AssignmentRole.STORE_MANAGER: frozenset({AssignmentRole.STORE_EMPLOYEE}),
        AssignmentRole.STORE_EMPLOYEE: frozenset(),
        AssignmentRole.SYSTEM_ADMIN: frozenset(),
    }
)


def can_invite_member(
    actor: ResolvedAssignment,
    target_store: ResolvedStore,
    invite_role: InviteRole,
) -> bool:
    if actor.organization_id != target_store.organization_id:
        return False
    if invite_role not in INVITABLE_ROLES_BY_ACTOR[actor.role]:
        return False
    if actor.role is AssignmentRole.FOUNDER:
        return True
    return (
        actor.role is AssignmentRole.STORE_MANAGER
        and actor.store_id is not None
        and actor.store_id == target_store.store_id
    )


def can_deactivate_member(
    actor: ResolvedAssignment,
    target: ResolvedAssignment,
) -> bool:
    if actor.assignment_id == target.assignment_id:
        return False
    if actor.organization_id != target.organization_id:
        return False
    if target.role not in DEACTIVATABLE_ROLES_BY_ACTOR[actor.role]:
        return False
    if actor.role is AssignmentRole.FOUNDER:
        return True
    return (
        actor.role is AssignmentRole.STORE_MANAGER
        and actor.store_id is not None
        and actor.store_id == target.store_id
    )
