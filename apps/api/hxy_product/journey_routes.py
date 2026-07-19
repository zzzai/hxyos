from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException, status

from .auth import Principal, build_principal_resolver
from .journey_schemas import (
    IssueJourneyRequest,
    JourneyResultResponse,
    JourneySuggestionsResponse,
    TrainingJourneyRequest,
)
from .public_safety import redact_internal_paths
from .routes import ROLE_CAPABILITIES, assignment_for_principal
from .task_routes import can_access_task


RepositoryFactory = Callable[[], Any]
TrainingEvaluator = Callable[..., dict[str, Any]]


@dataclass(frozen=True)
class JourneyIdentity:
    principal: Principal
    assignment: Any


SUGGESTIONS: dict[str, list[dict[str, str]]] = {
    "founder": [
        {"type": "ask", "label": "询问当前开业进度", "prompt": "现在开业进度怎么样？"},
        {"type": "tasks", "label": "查看今天的关键事项"},
        {"type": "ask", "label": "核对一个经营判断", "prompt": "当前最需要验证的经营假设是什么？"},
    ],
    "hq_operations": [
        {"type": "tasks", "label": "查看门店待办"},
        {"type": "ask", "label": "分析一个运营问题", "prompt": "这个运营问题应该怎么处理？"},
        {"type": "ask", "label": "分析门店执行问题", "prompt": "当前门店执行最需要解决什么？"},
    ],
    "store_manager": [
        {"type": "tasks", "label": "打开今天的待办"},
        {"type": "issue", "label": "上报一个门店问题"},
        {"type": "ask", "label": "询问门店处理建议", "prompt": "这个门店问题下一步怎么处理？"},
    ],
    "store_employee": [
        {"type": "ask", "label": "询问该怎么说", "prompt": "顾客这样问时我该怎么说？"},
        {"type": "training", "label": "练习一次接待话术"},
        {"type": "issue", "label": "上报一个门店问题"},
    ],
    "system_admin": [
        {"type": "ask", "label": "询问系统状态", "prompt": "当前系统有哪些需要处理的问题？"},
    ],
}


def _forbidden() -> HTTPException:
    return HTTPException(status_code=403, detail="Forbidden")


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="Not Found")


def _public_task(record: dict[str, Any]) -> dict[str, Any]:
    public = {
        key: record.get(key)
        for key in (
            "id",
            "title",
            "details",
            "priority",
            "status",
            "result",
            "due_at",
            "completed_at",
            "created_at",
            "updated_at",
        )
    }
    public["title"] = redact_internal_paths(str(record.get("title") or ""))[:160]
    public["details"] = redact_internal_paths(str(record.get("details") or ""))[:5000]
    public["result"] = (
        redact_internal_paths(str(record.get("result")))[:5000]
        if record.get("result") is not None
        else None
    )
    public["available_actions"] = (
        ["complete"]
        if record.get("operating_event_id") is None
        and record.get("status") in {"open", "in_progress"}
        else []
    )
    return public


def _training_result(result: dict[str, Any]) -> dict[str, Any]:
    try:
        score = min(100, max(0, int(result.get("score") or 0)))
    except (TypeError, ValueError):
        score = 0
    correction_points = [
        redact_internal_paths(str(item).strip())[:500]
        for item in (result.get("correction_points") or [])
        if str(item).strip()
    ][:8]
    next_actions = [
        redact_internal_paths(str(item).strip())[:300]
        for item in (result.get("next_actions") or [])
        if str(item).strip()
    ][:3]
    session_id = str(result.get("training_session_id") or "").strip()
    return {
        "result_type": "training_result",
        "primary_result": {
            "score": score,
            "level": (
                str(result.get("level"))
                if str(result.get("level") or "") in {"excellent", "pass", "retrain"}
                else "retrain"
            ),
            "needs_retrain": bool(result.get("needs_retrain", True)),
            "standard_script": redact_internal_paths(
                str(result.get("standard_script") or "").strip()
            )[:4000],
            "correction_points": correction_points,
        },
        "actions": [
            {"type": "training", "label": action} for action in next_actions
        ],
        "sources": [],
        "limitations": ["训练结果用于岗位练习，不替代店长现场验收。"],
        "artifact": (
            {"type": "training_session", "id": session_id} if session_id else None
        ),
    }


def create_journey_router(
    identity_repository_factory: RepositoryFactory,
    task_repository_factory: RepositoryFactory,
    training_repository_factory: RepositoryFactory,
    training_evaluator: TrainingEvaluator,
) -> APIRouter:
    router = APIRouter()

    def get_identity_repository() -> Any:
        return identity_repository_factory()

    def get_task_repository() -> Any:
        return task_repository_factory()

    def get_training_repository() -> Any:
        return training_repository_factory()

    resolve_principal = build_principal_resolver(get_identity_repository)

    def resolve_identity(
        principal: Principal = Depends(resolve_principal),
        repository: Any = Depends(get_identity_repository),
    ) -> JourneyIdentity:
        return JourneyIdentity(
            principal=principal,
            assignment=assignment_for_principal(principal, repository),
        )

    @router.get(
        "/api/v1/journeys/suggestions",
        response_model=JourneySuggestionsResponse,
    )
    def suggestions(identity: JourneyIdentity = Depends(resolve_identity)) -> dict[str, Any]:
        return {"items": SUGGESTIONS.get(identity.assignment.role, [])[:3]}

    @router.post(
        "/api/v1/journeys/training/evaluate",
        response_model=JourneyResultResponse,
    )
    def evaluate_training(
        request: TrainingJourneyRequest,
        identity: JourneyIdentity = Depends(resolve_identity),
        repository: Any = Depends(get_training_repository),
    ) -> dict[str, Any]:
        if "training:practice" not in ROLE_CAPABILITIES.get(
            identity.assignment.role, ()
        ):
            raise _forbidden()
        result = training_evaluator(
            request=request,
            principal=identity.principal,
            assignment=identity.assignment,
        )
        public_result = _training_result(result)
        primary = public_result["primary_result"]
        session = repository.save_training_session(
            {
                "organization_id": identity.assignment.organization_id,
                "store_id": identity.assignment.store_id,
                "assignment_id": identity.assignment.assignment_id,
                "customer_question": request.customer_question,
                "employee_answer": request.employee_answer,
                "score": primary["score"],
                "level": primary["level"],
                "needs_retrain": primary["needs_retrain"],
                "standard_script": primary["standard_script"],
                "correction_points": primary["correction_points"],
            }
        )
        result["training_session_id"] = session["id"]
        return _training_result(result)

    @router.post(
        "/api/v1/issues",
        status_code=status.HTTP_201_CREATED,
        response_model=JourneyResultResponse,
    )
    def report_issue(
        request: IssueJourneyRequest,
        identity: JourneyIdentity = Depends(resolve_identity),
        repository: Any = Depends(get_task_repository),
    ) -> dict[str, Any]:
        assignment = identity.assignment
        if "issues:create" not in ROLE_CAPABILITIES.get(assignment.role, ()):
            raise _forbidden()
        if not assignment.store_id:
            raise _forbidden()
        parent_task_id = None
        if request.source_task_id is not None:
            parent_task_id = str(request.source_task_id)
            source_task = repository.get_task(parent_task_id)
            if (
                source_task is None
                or not can_access_task(assignment, source_task)
                or source_task.get("store_id") != assignment.store_id
            ):
                raise _not_found()
        high_priority_terms = ("投诉", "安全", "医疗", "受伤", "退款", "紧急")
        priority = "high" if any(term in f"{request.title}{request.details}" for term in high_priority_terms) else "normal"
        task = repository.create_task(
            {
                "organization_id": assignment.organization_id,
                "store_id": assignment.store_id,
                "creator_assignment_id": assignment.assignment_id,
                "assignee_assignment_id": None,
                "source_conversation_id": None,
                "source_message_id": None,
                "parent_task_id": parent_task_id,
                "title": request.title,
                "details": request.details,
                "priority": priority,
                "visibility": "store",
                "due_at": None,
            }
        )
        return {
            "result_type": "issue_report",
            "primary_result": {"task": _public_task(task)},
            "actions": [{"type": "tasks", "label": "查看门店待办"}],
            "sources": [],
            "limitations": ["问题已进入当前门店待办，处理结论需由负责人填写。"],
            "artifact": {"type": "task", "id": str(task["id"])},
        }

    return router
