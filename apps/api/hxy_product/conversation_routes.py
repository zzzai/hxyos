from __future__ import annotations

import re
from pathlib import PurePath
from typing import Any, Callable
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status

from .auth import Principal, build_principal_resolver
from .conversation_schemas import (
    ConversationDetailResponse,
    CreateConversationRequest,
    CreateConversationResponse,
    ListConversationsResponse,
    SendMessageRequest,
    SendMessageResponse,
)
from .routes import ROLE_CAPABILITIES, assignment_for_principal


RepositoryFactory = Callable[[], Any]
AnswerGenerator = Callable[..., dict[str, Any]]

_ANSWER_STATUSES = frozenset({"已批准", "AI 草稿", "待复核", "资料不足"})
_CONFIDENCE_LEVELS = frozenset({"high", "medium", "low"})
_SOURCE_STRENGTHS = frozenset(
    {"high", "medium", "low", "reference", "candidate", "approved", "action_asset"}
)

_ABSOLUTE_PATH_RE = re.compile(
    r"(?<![:/\w])(?:[A-Za-z]:[\\/]|/(?!/))[^\s，。；;]+"
)
_HXY_RELATIVE_PATH_RE = re.compile(
    r"(?<!\w)(?:knowledge|data|apps|packages|ops|scripts|tests)/(?:[^\s，。；;]+)"
)
_MATERIAL_SOURCE_URL_RE = re.compile(
    r"^/api/v1/materials/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/content$",
    re.IGNORECASE,
)


def _redact_internal_paths(value: str) -> str:
    redacted = _ABSOLUTE_PATH_RE.sub("[已隐藏内部路径]", value)
    return _HXY_RELATIVE_PATH_RE.sub("[已隐藏内部路径]", redacted)


def _safe_title(value: Any) -> str:
    title = str(value or "资料来源").strip() or "资料来源"
    normalized = title.replace("\\", "/")
    if "/" in normalized:
        title = PurePath(normalized).name or "资料来源"
    return _redact_internal_paths(title)[:160]


def _safe_enum(value: Any, allowed: frozenset[str], default: str) -> str:
    normalized = str(value or "").strip()
    return normalized if normalized in allowed else default


def _safe_source_url(value: Any) -> str | None:
    candidate = str(value or "").strip()
    return candidate if _MATERIAL_SOURCE_URL_RE.fullmatch(candidate) else None


def _safe_sources(answer: dict[str, Any]) -> list[dict[str, str]]:
    raw_sources = answer.get("evidence") or answer.get("sources") or []
    if not isinstance(raw_sources, list):
        return []
    sources: list[dict[str, str]] = []
    for item in raw_sources[:8]:
        if not isinstance(item, dict):
            continue
        excerpt = _redact_internal_paths(str(item.get("excerpt") or item.get("content") or "").strip())
        strength = _safe_enum(
            item.get("strength") or item.get("status"),
            _SOURCE_STRENGTHS,
            "reference",
        )
        sources.append(
            {
                "title": _safe_title(item.get("title")),
                "excerpt": excerpt[:500],
                "strength": strength,
                "url": _safe_source_url(item.get("source_url") or item.get("url")),
            }
        )
    return sources


def _safe_answer_id(value: Any) -> str | None:
    if not value:
        return None
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        return None


def product_answer_payload(answer: dict[str, Any]) -> dict[str, Any]:
    raw_actions = answer.get("next_actions") or []
    next_actions = [
        _redact_internal_paths(str(action).strip())[:300]
        for action in raw_actions
        if str(action).strip()
    ][:3]
    return {
        "answer": _redact_internal_paths(str(answer.get("answer") or "").strip()),
        "answer_status": _safe_enum(answer.get("answer_status"), _ANSWER_STATUSES, "AI 草稿"),
        "confidence": _safe_enum(answer.get("confidence"), _CONFIDENCE_LEVELS, "low"),
        "needs_review": bool(answer.get("needs_review", True)),
        "sources": _safe_sources(answer),
        "next_actions": next_actions,
        "answer_id": _safe_answer_id(answer.get("answer_id")),
    }


def _public_message(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": record["id"],
        "conversation_id": record["conversation_id"],
        "role": record["role"],
        "content": _redact_internal_paths(str(record.get("content") or "")),
        "created_at": record["created_at"],
        "answer_id": _safe_answer_id(record.get("answer_id")),
        "answer_status": (
            _safe_enum(record.get("answer_status"), _ANSWER_STATUSES, "AI 草稿")
            if record.get("answer_status") is not None
            else None
        ),
        "confidence": (
            _safe_enum(record.get("confidence"), _CONFIDENCE_LEVELS, "low")
            if record.get("confidence") is not None
            else None
        ),
        "needs_review": record.get("needs_review"),
        "sources": [
            {
                "title": _safe_title(item.get("title")),
                "excerpt": _redact_internal_paths(str(item.get("excerpt") or ""))[:500],
                "strength": _safe_enum(
                    item.get("strength"),
                    _SOURCE_STRENGTHS,
                    "reference",
                ),
                "url": _safe_source_url(item.get("url")),
            }
            for item in record.get("sources") or []
            if isinstance(item, dict)
        ][:8],
        "next_actions": [
            _redact_internal_paths(str(item))[:300] for item in (record.get("next_actions") or [])
        ][:3],
    }


def _public_conversation(record: dict[str, Any]) -> dict[str, Any]:
    last_message = record.get("last_message")
    return {
        "id": record["id"],
        "title": _redact_internal_paths(str(record.get("title") or "新对话"))[:120],
        "created_at": record["created_at"],
        "updated_at": record["updated_at"],
        "last_message_at": record.get("last_message_at"),
        "message_count": int(record.get("message_count") or 0),
        "last_message": _public_message(last_message) if isinstance(last_message, dict) else None,
    }


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="Not Found")


def create_conversation_router(
    identity_repository_factory: RepositoryFactory,
    conversation_repository_factory: RepositoryFactory,
    answer_generator: AnswerGenerator,
) -> APIRouter:
    router = APIRouter()

    def get_identity_repository() -> Any:
        return identity_repository_factory()

    def get_conversation_repository() -> Any:
        return conversation_repository_factory()

    resolve_principal = build_principal_resolver(get_identity_repository)

    def resolve_assignment(
        principal: Principal = Depends(resolve_principal),
        identity_repository: Any = Depends(get_identity_repository),
    ) -> Any:
        assignment = assignment_for_principal(principal, identity_repository)
        if "conversation:use" not in ROLE_CAPABILITIES.get(assignment.role, ()):
            raise HTTPException(status_code=403, detail="Forbidden")
        return assignment

    @router.post(
        "/api/v1/conversations",
        status_code=status.HTTP_201_CREATED,
        response_model=CreateConversationResponse,
    )
    def create_conversation(
        _request: CreateConversationRequest | None = Body(default=None),
        assignment: Any = Depends(resolve_assignment),
        repository: Any = Depends(get_conversation_repository),
    ) -> dict[str, Any]:
        conversation = repository.create_conversation(assignment.assignment_id)
        return {"conversation": _public_conversation(conversation)}

    @router.get(
        "/api/v1/conversations",
        response_model=ListConversationsResponse,
    )
    def list_conversations(
        limit: int = Query(default=50, ge=1, le=100),
        assignment: Any = Depends(resolve_assignment),
        repository: Any = Depends(get_conversation_repository),
    ) -> dict[str, Any]:
        conversations = repository.list_conversations(assignment.assignment_id, limit=limit)
        items = [_public_conversation(item) for item in conversations]
        return {"items": items, "count": len(items)}

    @router.get(
        "/api/v1/conversations/{conversation_id}",
        response_model=ConversationDetailResponse,
    )
    def conversation_detail(
        conversation_id: UUID,
        assignment: Any = Depends(resolve_assignment),
        repository: Any = Depends(get_conversation_repository),
    ) -> dict[str, Any]:
        conversation_key = str(conversation_id)
        conversation = repository.get_conversation(assignment.assignment_id, conversation_key)
        if conversation is None:
            raise _not_found()
        messages = repository.list_messages(assignment.assignment_id, conversation_key)
        return {
            "conversation": _public_conversation(conversation),
            "messages": [_public_message(item) for item in messages],
        }

    @router.post(
        "/api/v1/conversations/{conversation_id}/messages",
        response_model=SendMessageResponse,
    )
    def send_message(
        conversation_id: UUID,
        request: SendMessageRequest,
        assignment: Any = Depends(resolve_assignment),
        repository: Any = Depends(get_conversation_repository),
    ) -> dict[str, Any]:
        conversation_key = str(conversation_id)
        client_message_id = str(request.client_message_id)
        reservation = repository.reserve_user_message(
            assignment.assignment_id,
            conversation_key,
            client_message_id,
            request.content,
        )
        if reservation is None:
            raise _not_found()
        state = reservation.get("state")
        if state == "conflict":
            raise HTTPException(status_code=409, detail="client_message_id conflict")
        if state == "processing":
            raise HTTPException(status_code=409, detail="Message is processing")

        user_message = reservation["user_message"]
        assistant_message = reservation.get("assistant_message")
        if state != "completed":
            try:
                answer = answer_generator(question=request.content, assignment=assignment)
                safe_payload = product_answer_payload(answer)
                assistant_message = repository.complete_assistant_message(
                    assignment.assignment_id,
                    conversation_key,
                    user_message["id"],
                    client_message_id,
                    safe_payload,
                    trace_payload=answer.get("_product_trace"),
                )
            except Exception:
                repository.mark_generation_failed(
                    assignment.assignment_id,
                    conversation_key,
                    user_message["id"],
                )
                raise
            if assistant_message is None:
                repository.mark_generation_failed(
                    assignment.assignment_id,
                    conversation_key,
                    user_message["id"],
                )
                raise HTTPException(status_code=409, detail="Message completion conflict")

        conversation = repository.get_conversation(assignment.assignment_id, conversation_key)
        if conversation is None or assistant_message is None:
            raise _not_found()
        return {
            "conversation": _public_conversation(conversation),
            "user_message": _public_message(user_message),
            "assistant_message": _public_message(assistant_message),
        }

    return router
