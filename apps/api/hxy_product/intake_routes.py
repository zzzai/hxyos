from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException, status

from .auth import Principal, build_principal_resolver
from .conversation_routes import AnswerGenerator, RouteClassifier, complete_conversation_message
from .intake_schemas import UnifiedIntakeRequest, UnifiedIntakeResponse
from .record_routes import CreateOrganizationRecordRequest, persist_organization_record
from .routes import ROLE_CAPABILITIES, assignment_for_principal


RepositoryFactory = Callable[[], Any]


def create_intake_router(
    identity_repository_factory: RepositoryFactory,
    channel_repository_factory: RepositoryFactory,
    record_repository_factory: RepositoryFactory,
    conversation_repository_factory: RepositoryFactory,
    answer_generator: AnswerGenerator,
    route_classifier: RouteClassifier,
) -> APIRouter:
    router = APIRouter()

    def get_identity_repository() -> Any:
        return identity_repository_factory()

    resolve_principal = build_principal_resolver(get_identity_repository)

    def resolve_assignment(
        principal: Principal = Depends(resolve_principal),
        repository: Any = Depends(get_identity_repository),
    ) -> Any:
        assignment = assignment_for_principal(principal, repository)
        capabilities = set(ROLE_CAPABILITIES.get(assignment.role, ()))
        if "records:create" not in capabilities:
            raise HTTPException(status_code=403, detail="Forbidden")
        if "conversation:use" not in capabilities:
            raise HTTPException(status_code=403, detail="Forbidden")
        return assignment

    @router.post(
        "/api/v1/intake",
        response_model=UnifiedIntakeResponse,
        status_code=status.HTTP_202_ACCEPTED,
    )
    def submit_intake(
        request: UnifiedIntakeRequest,
        principal: Principal = Depends(resolve_principal),
        assignment: Any = Depends(resolve_assignment),
    ) -> dict[str, Any]:
        record = persist_organization_record(
            CreateOrganizationRecordRequest(
                client_record_id=request.client_submission_id,
                text=request.text,
                source_asset_ids=request.source_asset_ids,
            ),
            principal=principal,
            assignment=assignment,
            channel_repository=channel_repository_factory(),
            record_repository=record_repository_factory(),
        )
        result: dict[str, Any] = {
            "receipt": "已收到，正在处理",
            "record": record,
            "conversation": None,
            "user_message": None,
            "assistant_message": None,
        }
        if request.text and request.conversation_id is not None:
            result.update(
                complete_conversation_message(
                    conversation_id=str(request.conversation_id),
                    client_message_id=str(request.client_submission_id),
                    content=request.text,
                    assignment=assignment,
                    repository=conversation_repository_factory(),
                    answer_generator=answer_generator,
                    route_classifier=route_classifier,
                )
            )
        return result

    return router
