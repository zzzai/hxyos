from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException, status

from .auth import Principal, build_principal_resolver
from .product_event_repository import ProductEventConflict
from .product_event_schemas import ProductEventRequest, ProductEventResponse
from .routes import assignment_for_principal


RepositoryFactory = Callable[[], Any]


def create_product_event_router(
    identity_repository_factory: RepositoryFactory,
    product_event_repository_factory: RepositoryFactory,
) -> APIRouter:
    router = APIRouter()

    def get_identity_repository() -> Any:
        return identity_repository_factory()

    def get_product_event_repository() -> Any:
        return product_event_repository_factory()

    resolve_principal = build_principal_resolver(get_identity_repository)

    @router.post(
        "/api/v1/product-events",
        response_model=ProductEventResponse,
        status_code=status.HTTP_201_CREATED,
    )
    def append_product_event(
        request: ProductEventRequest,
        principal: Principal = Depends(resolve_principal),
        identity_repository: Any = Depends(get_identity_repository),
        event_repository: Any = Depends(get_product_event_repository),
    ) -> dict[str, Any]:
        assignment = assignment_for_principal(principal, identity_repository)
        if not event_repository.briefing_source_is_accessible(
            organization_id=assignment.organization_id,
            store_id=assignment.store_id,
            assignment_id=assignment.assignment_id,
            role=assignment.role,
            subject_id=str(request.subject_id),
        ):
            raise HTTPException(status_code=404, detail="Not Found")
        try:
            event = event_repository.append_event(
                organization_id=assignment.organization_id,
                store_id=assignment.store_id,
                assignment_id=assignment.assignment_id,
                client_event_id=str(request.client_event_id),
                event_name=request.event_name,
                subject_id=str(request.subject_id),
                useful=request.useful,
            )
        except ProductEventConflict as exc:
            raise HTTPException(status_code=409, detail="Product event conflict") from exc
        return {
            "event": {
                "id": event["event_id"],
                "event_name": event["event_name"],
                "created_at": event["created_at"],
            }
        }

    return router
