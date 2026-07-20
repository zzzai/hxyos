from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException, Request

from .auth import Principal, build_principal_resolver
from .journey_schemas import TrainingJourneyRequest
from .learning_schemas import (
    LearningHomeResponse,
    LearningPracticeRequest,
    LearningPracticeResponse,
)
from .learning_service import (
    LEARNING_LIMITATIONS,
    learning_action,
    next_learning_action,
    private_progress,
    safe_attempt,
)
from .routes import ROLE_CAPABILITIES, assignment_for_principal


RepositoryFactory = Callable[[], Any]
TrainingEvaluator = Callable[..., dict[str, Any]]


@dataclass(frozen=True)
class LearningIdentity:
    principal: Principal
    assignment: Any


def create_learning_router(
    identity_repository_factory: RepositoryFactory,
    training_repository_factory: RepositoryFactory,
    training_evaluator: TrainingEvaluator,
) -> APIRouter:
    router = APIRouter()

    def get_identity_repository() -> Any:
        return identity_repository_factory()

    def get_training_repository() -> Any:
        return training_repository_factory()

    resolve_principal = build_principal_resolver(get_identity_repository)

    def resolve_learning_identity(
        principal: Principal = Depends(resolve_principal),
        repository: Any = Depends(get_identity_repository),
    ) -> LearningIdentity:
        assignment = assignment_for_principal(principal, repository)
        if "training:practice" not in ROLE_CAPABILITIES.get(assignment.role, ()):
            raise HTTPException(status_code=403, detail="Forbidden")
        if not assignment.store_id:
            raise HTTPException(status_code=403, detail="Forbidden")
        return LearningIdentity(principal=principal, assignment=assignment)

    def sessions_for(identity: LearningIdentity, repository: Any) -> list[dict[str, Any]]:
        return repository.list_assignment_sessions(
            organization_id=identity.assignment.organization_id,
            assignment_id=identity.assignment.assignment_id,
            limit=20,
        )

    @router.get("/api/v1/learning", response_model=LearningHomeResponse)
    def learning_home(
        request: Request,
        identity: LearningIdentity = Depends(resolve_learning_identity),
        repository: Any = Depends(get_training_repository),
    ) -> dict[str, Any]:
        if request.query_params:
            raise HTTPException(status_code=422, detail="Learning scope comes from session")
        sessions = sessions_for(identity, repository)
        return {
            "next_action": next_learning_action(sessions),
            "progress": private_progress(sessions),
            "limitations": LEARNING_LIMITATIONS,
        }

    @router.post(
        "/api/v1/learning/practice",
        response_model=LearningPracticeResponse,
    )
    def practice(
        request: LearningPracticeRequest,
        identity: LearningIdentity = Depends(resolve_learning_identity),
        repository: Any = Depends(get_training_repository),
    ) -> dict[str, Any]:
        action = learning_action(request.action_id)
        if action is None:
            raise HTTPException(status_code=404, detail="Learning action not found")
        customer_message = str(action["scenario"]["customer_message"])
        result = training_evaluator(
            request=TrainingJourneyRequest(
                customer_question=customer_message,
                employee_answer=request.employee_answer,
            ),
            principal=identity.principal,
            assignment=identity.assignment,
        )
        attempt = safe_attempt(result, "")
        session = repository.save_training_session(
            {
                "organization_id": identity.assignment.organization_id,
                "store_id": identity.assignment.store_id,
                "assignment_id": identity.assignment.assignment_id,
                "customer_question": customer_message,
                "employee_answer": request.employee_answer,
                "score": attempt["score"],
                "level": attempt["level"],
                "needs_retrain": attempt["needs_retrain"],
                "standard_script": attempt["standard_script"],
                "correction_points": attempt["correction_points"],
            }
        )
        attempt["id"] = str(session["id"])
        sessions = sessions_for(identity, repository)
        return {
            "attempt": attempt,
            "next_action": next_learning_action(sessions),
            "progress": private_progress(sessions),
            "limitations": LEARNING_LIMITATIONS,
        }

    return router
