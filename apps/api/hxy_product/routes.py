from __future__ import annotations

from types import MappingProxyType
from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException, Query

from .auth import Principal, build_principal_resolver
from .schemas import AssignmentContext, MeResponse, OrganizationContext, StoreContext, UserContext


ROLE_LABELS = MappingProxyType(
    {
        "founder": "创始人",
        "hq_operations": "总部运营",
        "store_manager": "店长",
        "store_employee": "门店员工",
        "system_admin": "系统管理员",
    }
)

ROLE_CAPABILITIES = MappingProxyType(
    {
        "founder": (
            "conversation:use",
            "organization:read",
            "stores:read",
            "tasks:manage",
            "tasks:read",
        ),
        "hq_operations": (
            "conversation:use",
            "operations:manage",
            "organization:read",
            "stores:read",
            "tasks:manage",
            "tasks:read",
        ),
        "store_manager": (
            "conversation:use",
            "issues:create",
            "store:operate",
            "store:read",
            "tasks:manage",
            "tasks:read",
        ),
        "store_employee": (
            "conversation:use",
            "issues:create",
            "store:read",
            "tasks:read",
            "training:practice",
        ),
        "system_admin": (
            "conversation:use",
            "identity:admin",
            "system:admin",
        ),
    }
)


def _assignment_context(record: Any) -> AssignmentContext:
    if record.role not in ROLE_CAPABILITIES:
        raise HTTPException(status_code=403, detail="Forbidden")
    store = None
    if record.store_id is not None:
        store = StoreContext(id=record.store_id, name=record.store_name or "")
    return AssignmentContext(
        assignment_id=record.assignment_id,
        organization=OrganizationContext(
            id=record.organization_id,
            name=record.organization_name,
        ),
        store=store,
        role=record.role,
        role_label=ROLE_LABELS[record.role],
        capabilities=list(ROLE_CAPABILITIES[record.role]),
    )


def create_identity_router(repository_factory: Callable[[], Any]) -> APIRouter:
    router = APIRouter()

    def get_repository() -> Any:
        return repository_factory()

    resolve_principal = build_principal_resolver(get_repository)

    @router.get("/api/v1/me", response_model=MeResponse)
    def me(
        principal: Principal = Depends(resolve_principal),
        repository: Any = Depends(get_repository),
        assignment_id: str | None = Query(default=None),
    ) -> MeResponse:
        assignments = [
            _assignment_context(record)
            for record in repository.list_assignments(principal.account_id)
        ]
        if not assignments:
            raise HTTPException(status_code=403, detail="Forbidden")

        active_assignment = assignments[0]
        if assignment_id is not None:
            active_assignment = next(
                (
                    assignment
                    for assignment in assignments
                    if assignment.assignment_id == assignment_id
                ),
                None,
            )
            if active_assignment is None:
                raise HTTPException(status_code=403, detail="Forbidden")

        return MeResponse(
            user=UserContext(
                account_id=principal.account_id,
                display_name=principal.display_name,
            ),
            active_assignment=active_assignment,
            available_assignments=assignments,
        )

    return router
