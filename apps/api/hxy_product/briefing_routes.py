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
        limit: int = Query(default=3, ge=1, le=3),
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
        role_action = None
        if assignment.role == "store_manager" and assignment.store_id:
            already_reviewed = repository.has_today_closing_review(
                organization_id=assignment.organization_id,
                store_id=assignment.store_id,
            )
            if not already_reviewed:
                role_action = {
                    "type": "closing_review",
                    "label": "记录闭店复盘",
                    "prompt": "闭店复盘：",
                }
        item_limit = limit - (1 if role_action else 0)
        return {
            "items": (
                project_brief_items(records, limit=item_limit)
                if item_limit > 0
                else []
            ),
            "role_action": role_action,
        }

    return router
