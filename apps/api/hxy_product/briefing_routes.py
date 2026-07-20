from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException, Query

from .auth import Principal, build_principal_resolver
from .briefing_schemas import TodayResponse, project_brief_items
from .record_repository import RecordAccessDenied
from .routes import ROLE_CAPABILITIES, assignment_for_principal


RepositoryFactory = Callable[[], Any]


def create_briefing_router(
    identity_repository_factory: RepositoryFactory,
    briefing_repository_factory: RepositoryFactory,
) -> APIRouter:
    router = APIRouter()

    def get_identity_repository() -> Any:
        return identity_repository_factory()

    def get_briefing_repository() -> Any:
        return briefing_repository_factory()

    resolve_principal = build_principal_resolver(get_identity_repository)

    def read_assignment(
        principal: Principal = Depends(resolve_principal),
        repository: Any = Depends(get_identity_repository),
    ) -> Any:
        assignment = assignment_for_principal(principal, repository)
        if "records:read" not in ROLE_CAPABILITIES.get(assignment.role, ()):
            raise HTTPException(status_code=403, detail="Forbidden")
        return assignment

    @router.get("/api/v1/today", response_model=TodayResponse)
    def get_today(
        limit: int = Query(default=3, ge=1, le=100),
        assignment: Any = Depends(read_assignment),
        repository: Any = Depends(get_briefing_repository),
    ) -> dict[str, Any]:
        try:
            records = repository.list_briefing_records(
                organization_id=assignment.organization_id,
                assignment_id=assignment.assignment_id,
                role=assignment.role,
                store_id=assignment.store_id,
                limit=100,
            )
        except RecordAccessDenied:
            raise HTTPException(status_code=403, detail="Forbidden") from None
        return {"items": project_brief_items(records, limit=limit)}

    return router
