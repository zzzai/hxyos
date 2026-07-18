from __future__ import annotations

from typing import Any, Callable, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from .auth import Principal, build_principal_resolver
from .evidence_repository import EvidenceError
from .routes import ROLE_CAPABILITIES, assignment_for_principal


RepositoryFactory = Callable[[], Any]


class EvidenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    client_evidence_id: UUID
    source_asset_id: UUID
    evidence_type: Literal["photo", "audio", "video", "document", "text", "system_record"]
    statement: str = Field(default="", max_length=5000)


def create_evidence_router(
    identity_repository_factory: RepositoryFactory,
    evidence_repository_factory: RepositoryFactory,
) -> APIRouter:
    router = APIRouter()

    def get_identity_repository() -> Any:
        return identity_repository_factory()

    def get_evidence_repository() -> Any:
        return evidence_repository_factory()

    resolve_principal = build_principal_resolver(get_identity_repository)

    def resolve_submitter(
        principal: Principal = Depends(resolve_principal),
        identity_repository: Any = Depends(get_identity_repository),
    ) -> Any:
        assignment = assignment_for_principal(principal, identity_repository)
        if "operating:execute" not in ROLE_CAPABILITIES.get(assignment.role, ()):
            raise HTTPException(status_code=403, detail="Forbidden")
        if not assignment.store_id:
            raise HTTPException(status_code=422, detail="Active store assignment is required")
        return assignment

    @router.post(
        "/api/v1/operating/tasks/{task_id}/evidence",
        status_code=status.HTTP_201_CREATED,
    )
    def create_evidence(
        task_id: UUID,
        request: EvidenceRequest,
        assignment: Any = Depends(resolve_submitter),
        repository: Any = Depends(get_evidence_repository),
    ) -> dict[str, Any]:
        try:
            record = repository.create_evidence(
                organization_id=assignment.organization_id,
                store_id=assignment.store_id,
                task_id=str(task_id),
                client_evidence_id=str(request.client_evidence_id),
                source_asset_id=str(request.source_asset_id),
                evidence_type=request.evidence_type,
                statement=request.statement,
                actor_assignment_id=assignment.assignment_id,
            )
        except EvidenceError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from None
        return {
            "evidence": {
                "id": str(record["evidence_id"]),
                "task_id": str(record["task_id"]),
                "event_id": str(record["operating_event_id"]),
                "type": str(record["evidence_type"]),
                "statement": str(record.get("statement") or ""),
                "source_asset_id": str(record["source_asset_id"]),
                "created_at": record["created_at"],
            }
        }

    return router
