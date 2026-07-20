from __future__ import annotations

import json
from typing import Any, Callable
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from .auth import Principal, build_principal_resolver
from .routes import ROLE_CAPABILITIES, assignment_for_principal
from .service_repository import (
    ServiceAssetAccessDenied,
    ServiceContextAccessDenied,
    ServiceContextNotFound,
    ServiceIdempotencyConflict,
    ServiceIdentityConflict,
    external_reference_digest,
)
from .service_schemas import (
    AddServiceFeedbackRequest,
    CreateServiceContextRequest,
    ReconcileServiceContextRequest,
    ServiceContextListResponse,
    ServiceContextResponse,
    ServiceFeedbackResponse,
)


RepositoryFactory = Callable[[], Any]


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except ValueError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def public_service_context(row: dict[str, Any]) -> dict[str, Any]:
    hint = _json_object(row.get("original_identity_hint"))
    alias = str(hint.get("alias") or "").strip()[:80]
    suffix = str(hint.get("phone_suffix") or "").strip()
    if len(suffix) != 4 or not suffix.isdigit():
        suffix = ""
    if alias and suffix:
        display = f"{alias} · 尾号 {suffix}"
    elif alias:
        display = alias
    elif suffix:
        display = f"顾客 · 尾号 {suffix}"
    else:
        display = "顾客"
    return {
        "id": str(row.get("id") or row.get("service_context_id")),
        "status": str(row.get("status") or "provisional"),
        "occurred_at": row["occurred_at"],
        "service_label": str(row.get("service_label") or "服务记录")[:120],
        "customer_display": display,
        "feedback_count": max(0, int(row.get("feedback_count") or 0)),
        "created_at": row["created_at"],
    }


def create_service_router(
    identity_repository_factory: RepositoryFactory,
    service_repository_factory: RepositoryFactory,
    *,
    identity_hmac_key: str,
) -> APIRouter:
    router = APIRouter()

    def get_identity_repository() -> Any:
        return identity_repository_factory()

    def get_service_repository() -> Any:
        return service_repository_factory()

    resolve_principal = build_principal_resolver(get_identity_repository)

    def identity_with(capability: str):
        def resolve(
            principal: Principal = Depends(resolve_principal),
            repository: Any = Depends(get_identity_repository),
        ) -> tuple[Principal, Any]:
            assignment = assignment_for_principal(principal, repository)
            if capability not in ROLE_CAPABILITIES.get(assignment.role, ()):
                raise HTTPException(status_code=403, detail="Forbidden")
            if not assignment.store_id:
                raise HTTPException(status_code=403, detail="Forbidden")
            return principal, assignment

        return resolve

    create_identity = identity_with("services:create")
    read_identity = identity_with("services:read")
    feedback_identity = identity_with("services:feedback")
    reconcile_identity = identity_with("services:reconcile")

    @router.post(
        "/api/v1/service-contexts",
        response_model=ServiceContextResponse,
        status_code=status.HTTP_201_CREATED,
    )
    def create_context(
        request: CreateServiceContextRequest,
        identity: tuple[Principal, Any] = Depends(create_identity),
        repository: Any = Depends(get_service_repository),
    ) -> dict[str, Any]:
        _, assignment = identity
        try:
            row = repository.create_context(
                {
                    "organization_id": assignment.organization_id,
                    "store_id": assignment.store_id,
                    "created_by_assignment_id": assignment.assignment_id,
                    "client_context_id": str(request.client_context_id),
                    "occurred_at": request.occurred_at,
                    "service_label": request.service_label,
                    "original_identity_hint": request.customer_hint.model_dump(
                        exclude_none=True
                    ),
                }
            )
        except ServiceIdempotencyConflict:
            raise HTTPException(status_code=409, detail="Idempotency key conflict") from None
        return {"context": public_service_context(row)}

    @router.get(
        "/api/v1/service-contexts/recent",
        response_model=ServiceContextListResponse,
    )
    def list_recent(
        limit: int = Query(default=10, ge=1, le=50),
        identity: tuple[Principal, Any] = Depends(read_identity),
        repository: Any = Depends(get_service_repository),
    ) -> dict[str, Any]:
        _, assignment = identity
        try:
            rows = repository.list_recent_contexts(
                organization_id=assignment.organization_id,
                store_id=assignment.store_id,
                assignment_id=assignment.assignment_id,
                role=assignment.role,
                limit=limit,
            )
        except ServiceContextAccessDenied:
            raise HTTPException(status_code=403, detail="Forbidden") from None
        return {"contexts": [public_service_context(row) for row in rows]}

    @router.post(
        "/api/v1/service-contexts/{context_id}/feedback",
        response_model=ServiceFeedbackResponse,
        status_code=status.HTTP_201_CREATED,
    )
    def add_feedback(
        context_id: UUID,
        request: AddServiceFeedbackRequest,
        identity: tuple[Principal, Any] = Depends(feedback_identity),
        repository: Any = Depends(get_service_repository),
    ) -> dict[str, Any]:
        _, assignment = identity
        try:
            result = repository.add_feedback(
                {
                    "organization_id": assignment.organization_id,
                    "store_id": assignment.store_id,
                    "created_by_assignment_id": assignment.assignment_id,
                    "context_id": str(context_id),
                    "client_feedback_id": str(request.client_feedback_id),
                    "text": request.text,
                    "source_asset_ids": [str(item) for item in request.source_asset_ids],
                },
                assignment_id=assignment.assignment_id,
                role=assignment.role,
            )
        except (ServiceContextNotFound, ServiceAssetAccessDenied):
            raise HTTPException(status_code=404, detail="Not Found") from None
        except ServiceContextAccessDenied:
            raise HTTPException(status_code=403, detail="Forbidden") from None
        except ServiceIdempotencyConflict:
            raise HTTPException(status_code=409, detail="Idempotency key conflict") from None
        return {
            "feedback": result["feedback"],
            "context": public_service_context(result["context"]),
        }

    @router.post(
        "/api/v1/service-contexts/{context_id}/reconcile",
        response_model=ServiceContextResponse,
    )
    def reconcile_context(
        context_id: UUID,
        request: ReconcileServiceContextRequest,
        identity: tuple[Principal, Any] = Depends(reconcile_identity),
        repository: Any = Depends(get_service_repository),
    ) -> dict[str, Any]:
        if not identity_hmac_key.strip():
            raise HTTPException(status_code=503, detail="Identity reconciliation unavailable")
        _, assignment = identity
        payload = {
            "organization_id": assignment.organization_id,
            "store_id": assignment.store_id,
            "context_id": str(context_id),
            "source_system": request.source_system,
            "external_customer_ref_hash": external_reference_digest(
                identity_hmac_key,
                request.source_system,
                "customer",
                request.external_customer_ref,
            ),
            "external_service_ref_hash": (
                external_reference_digest(
                    identity_hmac_key,
                    request.source_system,
                    "service",
                    request.external_service_ref,
                )
                if request.external_service_ref
                else None
            ),
        }
        try:
            row = repository.reconcile_context(
                payload,
                assignment_id=assignment.assignment_id,
                role=assignment.role,
            )
        except ServiceContextNotFound:
            raise HTTPException(status_code=404, detail="Not Found") from None
        except ServiceContextAccessDenied:
            raise HTTPException(status_code=403, detail="Forbidden") from None
        except ServiceIdentityConflict:
            raise HTTPException(status_code=409, detail="Identity mapping conflict") from None
        return {"context": public_service_context(row)}

    return router
