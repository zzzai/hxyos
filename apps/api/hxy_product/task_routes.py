from __future__ import annotations

from typing import Any, Callable
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from .auth import Principal, build_principal_resolver
from .routes import ROLE_CAPABILITIES, assignment_for_principal
from .task_schemas import CreateTaskRequest, TaskListResponse, TaskResponse, UpdateTaskRequest
from .task_repository import TaskStateConflict


RepositoryFactory = Callable[[], Any]


def _forbidden() -> HTTPException:
    return HTTPException(status_code=403, detail="Forbidden")


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="Not Found")


def _public_task(record: dict[str, Any]) -> dict[str, Any]:
    return {
        key: record.get(key)
        for key in (
            "id",
            "title",
            "details",
            "priority",
            "status",
            "visibility",
            "store_id",
            "assignee_assignment_id",
            "source_conversation_id",
            "source_message_id",
            "result",
            "due_at",
            "completed_at",
            "created_at",
            "updated_at",
        )
    }


def _can_access_task(assignment: Any, task: dict[str, Any]) -> bool:
    if task.get("organization_id") != assignment.organization_id:
        return False
    if assignment.role in {"founder", "hq_operations"}:
        return True
    if assignment.role == "store_manager":
        return bool(
            task.get("creator_assignment_id") == assignment.assignment_id
            or task.get("assignee_assignment_id") == assignment.assignment_id
            or (
                task.get("visibility") == "store"
                and task.get("store_id") == assignment.store_id
            )
        )
    return bool(
        task.get("assignee_assignment_id") == assignment.assignment_id
        or (
            task.get("visibility") == "store"
            and task.get("store_id") == assignment.store_id
        )
    )


def create_task_router(
    identity_repository_factory: RepositoryFactory,
    task_repository_factory: RepositoryFactory,
) -> APIRouter:
    router = APIRouter()

    def get_identity_repository() -> Any:
        return identity_repository_factory()

    def get_task_repository() -> Any:
        return task_repository_factory()

    resolve_principal = build_principal_resolver(get_identity_repository)

    def resolve_assignment(
        principal: Principal = Depends(resolve_principal),
        repository: Any = Depends(get_identity_repository),
    ) -> Any:
        return assignment_for_principal(principal, repository)

    @router.get("/api/v1/tasks", response_model=TaskListResponse)
    def list_tasks(
        limit: int = Query(default=50, ge=1, le=100),
        assignment: Any = Depends(resolve_assignment),
        repository: Any = Depends(get_task_repository),
    ) -> dict[str, Any]:
        if "tasks:read" not in ROLE_CAPABILITIES.get(assignment.role, ()):
            raise _forbidden()
        items = repository.list_tasks(
            assignment_id=assignment.assignment_id,
            organization_id=assignment.organization_id,
            store_id=assignment.store_id,
            role=assignment.role,
            limit=limit,
        )
        public_items = [_public_task(item) for item in items]
        return {"items": public_items, "count": len(public_items)}

    @router.post(
        "/api/v1/tasks",
        status_code=status.HTTP_201_CREATED,
        response_model=TaskResponse,
    )
    def create_task(
        request: CreateTaskRequest,
        assignment: Any = Depends(resolve_assignment),
        identity_repository: Any = Depends(get_identity_repository),
        task_repository: Any = Depends(get_task_repository),
    ) -> dict[str, Any]:
        if "tasks:manage" not in ROLE_CAPABILITIES.get(assignment.role, ()):
            raise _forbidden()

        target = None
        if request.assignee_assignment_id is not None:
            target = identity_repository.get_assignment(str(request.assignee_assignment_id))
            if target is None or target.organization_id != assignment.organization_id:
                raise _forbidden()
            if assignment.role == "store_manager" and target.store_id != assignment.store_id:
                raise _forbidden()

        store_id = request.store_id or (target.store_id if target else assignment.store_id)
        if request.store_id and target and target.store_id != request.store_id:
            raise _forbidden()
        if assignment.role == "store_manager" and store_id != assignment.store_id:
            raise _forbidden()
        if request.visibility == "store" and not store_id:
            raise HTTPException(status_code=422, detail="store_id is required")
        if store_id and not identity_repository.organization_has_store(
            assignment.organization_id,
            store_id,
        ):
            raise _forbidden()
        if request.source_message_id is not None and not task_repository.source_message_owned_by_assignment(
            assignment.assignment_id,
            str(request.source_conversation_id),
            str(request.source_message_id),
        ):
            raise _not_found()

        task = task_repository.create_task(
            {
                "organization_id": assignment.organization_id,
                "store_id": store_id,
                "creator_assignment_id": assignment.assignment_id,
                "assignee_assignment_id": (
                    str(request.assignee_assignment_id)
                    if request.assignee_assignment_id
                    else None
                ),
                "source_conversation_id": (
                    str(request.source_conversation_id)
                    if request.source_conversation_id
                    else None
                ),
                "source_message_id": (
                    str(request.source_message_id) if request.source_message_id else None
                ),
                "title": request.title.strip(),
                "details": request.details.strip(),
                "priority": request.priority,
                "visibility": request.visibility,
                "due_at": request.due_at,
            }
        )
        return {"task": _public_task(task)}

    @router.patch("/api/v1/tasks/{task_id}", response_model=TaskResponse)
    def update_task(
        task_id: UUID,
        request: UpdateTaskRequest,
        assignment: Any = Depends(resolve_assignment),
        repository: Any = Depends(get_task_repository),
    ) -> dict[str, Any]:
        if "tasks:read" not in ROLE_CAPABILITIES.get(assignment.role, ()):
            raise _forbidden()
        task = repository.get_task(str(task_id))
        if task is None or not _can_access_task(assignment, task):
            raise _not_found()
        if request.status == "cancelled" and "tasks:manage" not in ROLE_CAPABILITIES.get(
            assignment.role, ()
        ):
            raise _forbidden()
        if task.get("status") in {"completed", "cancelled"}:
            raise HTTPException(status_code=409, detail="Task is closed")
        try:
            updated = repository.update_task(
                str(task_id),
                actor_assignment_id=assignment.assignment_id,
                status=request.status,
                result=request.result.strip() if request.result else None,
            )
        except TaskStateConflict:
            raise HTTPException(status_code=409, detail="Task is closed") from None
        if updated is None:
            raise _not_found()
        return {"task": _public_task(updated)}

    return router
