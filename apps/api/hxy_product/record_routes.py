from __future__ import annotations

from typing import Any, Callable
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .auth import Principal, build_principal_resolver
from .channel_repository import (
    AuthenticatedIntakeScopeDenied,
    IntakeIdempotencyConflict,
    SourceAssetAccessDenied,
)
from .record_repository import RecordAccessDenied
from .record_schemas import OrganizationRecord
from .routes import ROLE_CAPABILITIES, assignment_for_principal


RepositoryFactory = Callable[[], Any]


class StrictRecordRouteModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class CreateOrganizationRecordRequest(StrictRecordRouteModel):
    client_record_id: UUID
    text: str = Field(default="", max_length=20_000)
    source_asset_ids: list[UUID] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def require_content(self) -> "CreateOrganizationRecordRequest":
        if not self.text and not self.source_asset_ids:
            raise ValueError("text or source_asset_ids is required")
        return self


class OrganizationRecordResponse(StrictRecordRouteModel):
    record: OrganizationRecord


class OrganizationRecordListResponse(StrictRecordRouteModel):
    records: list[OrganizationRecord]


def _forbidden() -> HTTPException:
    return HTTPException(status_code=403, detail="Forbidden")


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="Not Found")


def create_record_router(
    identity_repository_factory: RepositoryFactory,
    channel_repository_factory: RepositoryFactory,
    record_repository_factory: RepositoryFactory,
) -> APIRouter:
    router = APIRouter()

    def get_identity_repository() -> Any:
        return identity_repository_factory()

    def get_channel_repository() -> Any:
        return channel_repository_factory()

    def get_record_repository() -> Any:
        return record_repository_factory()

    resolve_principal = build_principal_resolver(get_identity_repository)

    def assignment_with(capability: str):
        def resolve_assignment(
            principal: Principal = Depends(resolve_principal),
            repository: Any = Depends(get_identity_repository),
        ) -> Any:
            assignment = assignment_for_principal(principal, repository)
            if capability not in ROLE_CAPABILITIES.get(assignment.role, ()):
                raise _forbidden()
            return assignment

        return resolve_assignment

    create_assignment = assignment_with("records:create")
    read_assignment = assignment_with("records:read")

    @router.post(
        "/api/v1/organization-records",
        response_model=OrganizationRecordResponse,
        status_code=status.HTTP_202_ACCEPTED,
    )
    def create_record(
        request: CreateOrganizationRecordRequest,
        principal: Principal = Depends(resolve_principal),
        assignment: Any = Depends(create_assignment),
        channel_repository: Any = Depends(get_channel_repository),
        record_repository: Any = Depends(get_record_repository),
    ) -> dict[str, Any]:
        try:
            receipt = channel_repository.accept_authenticated_record(
                {
                    "organization_id": assignment.organization_id,
                    "channel": "pwa",
                    "channel_tenant_id": assignment.organization_id,
                    "channel_message_id": str(request.client_record_id),
                    "channel_thread_id": "",
                    "channel_user_id": principal.account_id,
                    "idempotency_key": str(request.client_record_id),
                    "raw_text": request.text,
                    "raw_payload": {},
                    "source_asset_ids": [str(value) for value in request.source_asset_ids],
                    "intent_hint": "organization_record",
                },
                assignment=assignment,
            )
        except SourceAssetAccessDenied:
            raise _not_found() from None
        except AuthenticatedIntakeScopeDenied:
            raise _forbidden() from None
        except IntakeIdempotencyConflict:
            raise HTTPException(
                status_code=409,
                detail="Idempotency key conflict",
            ) from None

        record = record_repository.get_record(
            organization_id=assignment.organization_id,
            record_id=str(receipt["id"]),
            assignment_id=assignment.assignment_id,
            role=assignment.role,
            store_id=assignment.store_id,
        )
        if record is None:  # pragma: no cover - committed envelope invariant
            raise HTTPException(status_code=503, detail="Record is temporarily unavailable")
        return {"record": record}

    @router.get(
        "/api/v1/organization-records",
        response_model=OrganizationRecordListResponse,
    )
    def list_records(
        limit: int = Query(default=50, ge=1, le=100),
        assignment: Any = Depends(read_assignment),
        repository: Any = Depends(get_record_repository),
    ) -> dict[str, Any]:
        try:
            records = repository.list_records(
                organization_id=assignment.organization_id,
                assignment_id=assignment.assignment_id,
                role=assignment.role,
                store_id=assignment.store_id,
                limit=limit,
            )
        except RecordAccessDenied:
            raise _forbidden() from None
        return {"records": records}

    @router.get(
        "/api/v1/organization-records/{record_id}",
        response_model=OrganizationRecordResponse,
    )
    def get_record(
        record_id: UUID,
        assignment: Any = Depends(read_assignment),
        repository: Any = Depends(get_record_repository),
    ) -> dict[str, Any]:
        try:
            record = repository.get_record(
                organization_id=assignment.organization_id,
                record_id=str(record_id),
                assignment_id=assignment.assignment_id,
                role=assignment.role,
                store_id=assignment.store_id,
            )
        except RecordAccessDenied:
            raise _not_found() from None
        if record is None:
            raise _not_found()
        return {"record": record}

    return router
