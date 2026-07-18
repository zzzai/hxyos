from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .auth import Principal, build_principal_resolver
from .channel_repository import (
    AuthenticatedIntakeScopeDenied,
    IntakeIdempotencyConflict,
    SourceAssetAccessDenied,
)
from .operating_schemas import (
    AcceptTaskCommand,
    EscalateEventCommand,
    ReturnForReworkCommand,
    StartTaskCommand,
    SubmitTaskCommand,
)
from .operating_service import OperatingError, OperatingService
from .routes import ROLE_CAPABILITIES, assignment_for_principal


RepositoryFactory = Callable[[], Any]
ServiceBuilder = Callable[[Any], Any]


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class OperatingIntakeRequest(StrictRequest):
    client_intake_id: UUID
    text: str = Field(default="", max_length=20000)
    source_asset_ids: list[UUID] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def require_content(self) -> "OperatingIntakeRequest":
        if not self.text and not self.source_asset_ids:
            raise ValueError("text or source_asset_ids is required")
        return self


class VersionedRequest(StrictRequest):
    expected_updated_at: datetime
    correlation_id: UUID = Field(default_factory=uuid4)


class SubmitRequest(VersionedRequest):
    evidence_ids: list[UUID] = Field(min_length=1, max_length=50)
    result: str = Field(min_length=1, max_length=5000)


class AcceptRequest(VersionedRequest):
    reason: str = Field(default="", max_length=2000)


class ReworkRequest(VersionedRequest):
    reason: str = Field(min_length=1, max_length=2000)


class EscalateRequest(VersionedRequest):
    severity: Literal["low", "medium", "high", "critical"]
    reason: str = Field(min_length=1, max_length=2000)


def _forbidden() -> HTTPException:
    return HTTPException(status_code=403, detail="Forbidden")


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="Not Found")


def _identifier(record: dict[str, Any], key: str, fallback: str = "") -> str | None:
    value = record.get(key)
    if value is None and fallback:
        value = record.get(fallback)
    return str(value) if value is not None else None


def _public_event(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": _identifier(record, "operating_event_id", "id"),
        "store_id": record.get("store_id"),
        "type": record.get("event_type"),
        "title": record.get("title"),
        "description": record.get("description") or "",
        "location": record.get("location") or "",
        "impact": record.get("impact") or "",
        "acceptance_criteria": record.get("acceptance_criteria") or "",
        "reporter_assignment_id": _identifier(record, "reporter_assignment_id"),
        "owner_assignment_id": _identifier(record, "owner_assignment_id"),
        "severity": record.get("severity"),
        "status": record.get("status"),
        "occurred_at": record.get("occurred_at"),
        "due_at": record.get("due_at"),
        "closed_at": record.get("closed_at"),
        "created_at": record.get("created_at"),
        "updated_at": record.get("updated_at"),
    }


def _public_task(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": _identifier(record, "task_id", "id"),
        "title": record.get("title"),
        "details": record.get("details") or "",
        "priority": record.get("priority"),
        "status": record.get("status"),
        "assignee_assignment_id": _identifier(record, "assignee_assignment_id"),
        "result": record.get("result"),
        "due_at": record.get("due_at"),
        "submitted_at": record.get("submitted_at"),
        "accepted_at": record.get("accepted_at"),
        "created_at": record.get("created_at"),
        "updated_at": record.get("updated_at"),
    }


def _public_evidence(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": _identifier(record, "evidence_id", "id"),
        "type": record.get("evidence_type"),
        "statement": record.get("statement") or "",
        "source_asset_id": _identifier(record, "source_asset_id"),
        "created_by_assignment_id": _identifier(record, "created_by_assignment_id"),
        "created_at": record.get("created_at"),
    }


def _public_detail(aggregate: dict[str, Any]) -> dict[str, Any]:
    event = _public_event(aggregate["event"])
    workflow = aggregate.get("workflow")
    event["workflow"] = (
        {
            "id": _identifier(workflow, "workflow_instance_id", "id"),
            "status": workflow.get("status"),
            "current_state": workflow.get("current_state"),
            "created_at": workflow.get("created_at"),
            "updated_at": workflow.get("updated_at"),
        }
        if isinstance(workflow, dict)
        else None
    )
    event["tasks"] = [
        _public_task(item) for item in aggregate.get("tasks", []) if isinstance(item, dict)
    ]
    event["evidence"] = [
        _public_evidence(item)
        for item in aggregate.get("evidence", [])
        if isinstance(item, dict)
    ]
    return event


def _receipt_payload(receipt: Any) -> dict[str, Any]:
    if hasattr(receipt, "model_dump"):
        return receipt.model_dump()
    if isinstance(receipt, dict):
        return dict(receipt)
    raise RuntimeError("operating service returned an invalid receipt")


def create_operating_router(
    identity_repository_factory: RepositoryFactory,
    channel_repository_factory: RepositoryFactory,
    operating_repository_factory: RepositoryFactory,
    *,
    service_builder: ServiceBuilder = OperatingService,
) -> APIRouter:
    router = APIRouter()

    def get_identity_repository() -> Any:
        return identity_repository_factory()

    def get_channel_repository() -> Any:
        return channel_repository_factory()

    def get_operating_repository() -> Any:
        return operating_repository_factory()

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

    report_assignment = assignment_with("operating:report")
    read_assignment = assignment_with("operating:read")
    execute_assignment = assignment_with("operating:execute")
    accept_assignment = assignment_with("operating:accept")
    escalate_assignment = assignment_with("operating:escalate")

    @router.post(
        "/api/v1/operating/intake",
        status_code=status.HTTP_202_ACCEPTED,
    )
    def create_intake(
        request: OperatingIntakeRequest,
        principal: Principal = Depends(resolve_principal),
        assignment: Any = Depends(report_assignment),
        repository: Any = Depends(get_channel_repository),
    ) -> dict[str, Any]:
        if not assignment.store_id:
            raise HTTPException(status_code=422, detail="Active store assignment is required")
        try:
            receipt = repository.accept_authenticated_inbound(
                {
                    "organization_id": assignment.organization_id,
                    "channel": "pwa",
                    "channel_tenant_id": assignment.organization_id,
                    "channel_message_id": str(request.client_intake_id),
                    "channel_thread_id": "",
                    "channel_user_id": principal.account_id,
                    "idempotency_key": (
                        f"{assignment.assignment_id}:{request.client_intake_id}"
                    ),
                    "raw_text": request.text,
                    "raw_payload": {},
                    "source_asset_ids": [str(value) for value in request.source_asset_ids],
                    "intent_hint": "issue",
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
        public_status = {
            "received": "received",
            "queued": "understanding",
            "processed": "ready",
            "needs_attention": "needs_attention",
        }.get(str(receipt.get("status") or ""), "received")
        return {
            "intake": {
                "id": str(receipt["id"]),
                "status": public_status,
                "received_at": receipt["received_at"],
            }
        }

    @router.get("/api/v1/operating/events")
    def list_events(
        limit: int = Query(default=50, ge=1, le=100),
        assignment: Any = Depends(read_assignment),
        repository: Any = Depends(get_operating_repository),
    ) -> dict[str, Any]:
        items = repository.list_events(
            organization_id=assignment.organization_id,
            store_id=assignment.store_id,
            assignment_id=assignment.assignment_id,
            role=assignment.role,
            limit=limit,
        )
        public = [_public_event(item) for item in items]
        return {"items": public, "count": len(public)}

    @router.get("/api/v1/operating/events/{event_id}")
    def event_detail(
        event_id: UUID,
        assignment: Any = Depends(read_assignment),
        repository: Any = Depends(get_operating_repository),
    ) -> dict[str, Any]:
        aggregate = repository.get_event(
            organization_id=assignment.organization_id,
            event_id=str(event_id),
            store_id=assignment.store_id,
            assignment_id=assignment.assignment_id,
            role=assignment.role,
        )
        if aggregate is None:
            raise _not_found()
        return {"event": _public_detail(aggregate)}

    def run_command(repository: Any, method: str, command: Any) -> dict[str, Any]:
        try:
            receipt = getattr(service_builder(repository), method)(command)
        except OperatingError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from None
        return {"receipt": _receipt_payload(receipt)}

    @router.post("/api/v1/operating/tasks/{task_id}/start")
    def start_task(
        task_id: UUID,
        request: VersionedRequest,
        assignment: Any = Depends(execute_assignment),
        repository: Any = Depends(get_operating_repository),
    ) -> dict[str, Any]:
        return run_command(
            repository,
            "start_task",
            StartTaskCommand(
                organization_id=assignment.organization_id,
                task_id=task_id,
                actor_assignment_id=assignment.assignment_id,
                expected_updated_at=request.expected_updated_at,
                correlation_id=request.correlation_id,
            ),
        )

    @router.post("/api/v1/operating/tasks/{task_id}/submit")
    def submit_task(
        task_id: UUID,
        request: SubmitRequest,
        assignment: Any = Depends(execute_assignment),
        repository: Any = Depends(get_operating_repository),
    ) -> dict[str, Any]:
        return run_command(
            repository,
            "submit_task",
            SubmitTaskCommand(
                organization_id=assignment.organization_id,
                task_id=task_id,
                actor_assignment_id=assignment.assignment_id,
                expected_updated_at=request.expected_updated_at,
                correlation_id=request.correlation_id,
                evidence_ids=request.evidence_ids,
                result=request.result,
            ),
        )

    @router.post("/api/v1/operating/tasks/{task_id}/accept")
    def accept_task(
        task_id: UUID,
        request: AcceptRequest,
        assignment: Any = Depends(accept_assignment),
        repository: Any = Depends(get_operating_repository),
    ) -> dict[str, Any]:
        return run_command(
            repository,
            "accept_task",
            AcceptTaskCommand(
                organization_id=assignment.organization_id,
                task_id=task_id,
                actor_assignment_id=assignment.assignment_id,
                expected_updated_at=request.expected_updated_at,
                correlation_id=request.correlation_id,
                reason=request.reason,
            ),
        )

    @router.post("/api/v1/operating/tasks/{task_id}/rework")
    def return_for_rework(
        task_id: UUID,
        request: ReworkRequest,
        assignment: Any = Depends(accept_assignment),
        repository: Any = Depends(get_operating_repository),
    ) -> dict[str, Any]:
        return run_command(
            repository,
            "return_for_rework",
            ReturnForReworkCommand(
                organization_id=assignment.organization_id,
                task_id=task_id,
                actor_assignment_id=assignment.assignment_id,
                expected_updated_at=request.expected_updated_at,
                correlation_id=request.correlation_id,
                reason=request.reason,
            ),
        )

    @router.post("/api/v1/operating/events/{event_id}/escalate")
    def escalate_event(
        event_id: UUID,
        request: EscalateRequest,
        assignment: Any = Depends(escalate_assignment),
        repository: Any = Depends(get_operating_repository),
    ) -> dict[str, Any]:
        return run_command(
            repository,
            "escalate_event",
            EscalateEventCommand(
                organization_id=assignment.organization_id,
                event_id=event_id,
                actor_assignment_id=assignment.assignment_id,
                expected_updated_at=request.expected_updated_at,
                correlation_id=request.correlation_id,
                severity=request.severity,
                reason=request.reason,
            ),
        )

    return router
