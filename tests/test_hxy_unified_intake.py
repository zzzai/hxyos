from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
import pytest

from apps.api.hxy_knowledge_api import create_app
from apps.api.hxy_product.intake_router import (
    build_model_assisted_route_classifier,
    classify_intake_route,
    generate_general_answer,
)


ACCOUNT_ID = "81000000-0000-0000-0000-000000000001"
ASSIGNMENT_ID = "82000000-0000-0000-0000-000000000001"
ORGANIZATION_ID = "83000000-0000-0000-0000-000000000001"
CONVERSATION_ID = "84000000-0000-0000-0000-000000000001"
SUBMISSION_ID = "85000000-0000-0000-0000-000000000001"
RECORD_ID = "86000000-0000-0000-0000-000000000001"
ASSET_ID = "87000000-0000-0000-0000-000000000001"
NOW = datetime(2026, 7, 21, 8, 0, tzinfo=timezone.utc)


@dataclass(frozen=True)
class FakePrincipal:
    account_id: str = ACCOUNT_ID
    display_name: str = "测试店长"
    assignment_id: str = ASSIGNMENT_ID


@dataclass(frozen=True)
class FakeAssignment:
    assignment_id: str = ASSIGNMENT_ID
    organization_id: str = ORGANIZATION_ID
    organization_name: str = "荷小悦"
    store_id: str | None = "store-1"
    store_name: str | None = "荷小悦测试店"
    role: str = "store_manager"


class FakeIdentityRepository:
    def resolve_session(self, raw_token: str) -> FakePrincipal | None:
        return FakePrincipal() if raw_token == "valid-session" else None

    def list_assignments(self, _account_id: str) -> list[FakeAssignment]:
        return [FakeAssignment()]


class FakeChannelRepository:
    def __init__(
        self,
        events: list[str],
        expected_text: str = "荷小悦第一次接待顾客应该怎么说？",
    ) -> None:
        self.events = events
        self.expected_text = expected_text

    def accept_authenticated_record(
        self,
        payload: dict[str, Any],
        *,
        assignment: FakeAssignment,
    ) -> dict[str, Any]:
        self.events.append("persist_original")
        assert payload["idempotency_key"] == SUBMISSION_ID
        assert payload["raw_text"] == self.expected_text
        assert assignment.assignment_id == ASSIGNMENT_ID
        return {"id": RECORD_ID}


class FakeRecordRepository:
    def get_record(self, *, record_id: str, **_scope: Any) -> dict[str, Any] | None:
        if record_id != RECORD_ID:
            return None
        return {
            "id": RECORD_ID,
            "source_types": ["text"],
            "preview": "荷小悦第一次接待顾客应该怎么说？",
            "submitted_by": "测试店长",
            "store_id": "store-1",
            "captured_at": NOW,
            "occurred_at": None,
            "processing_status": "received",
            "original": {"text": "荷小悦第一次接待顾客应该怎么说？", "assets": []},
            "interpretation": None,
        }


def _message(message_id: str, role: str, content: str) -> dict[str, Any]:
    return {
        "id": message_id,
        "conversation_id": CONVERSATION_ID,
        "role": role,
        "content": content,
        "created_at": NOW,
        "answer_id": None,
        "answer_status": None if role == "user" else "AI 草稿",
        "confidence": None if role == "user" else "medium",
        "needs_review": None if role == "user" else False,
        "sources": [],
        "next_actions": [],
        "result_type": None,
        "actions": [],
    }


class FakeConversationRepository:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.user_message = _message(str(uuid4()), "user", "荷小悦第一次接待顾客应该怎么说？")
        self.assistant_message: dict[str, Any] | None = None

    def reserve_user_message(
        self,
        assignment_id: str,
        conversation_id: str,
        client_message_id: str,
        content: str,
    ) -> dict[str, Any]:
        self.events.append("reserve_message")
        assert (assignment_id, conversation_id, client_message_id) == (
            ASSIGNMENT_ID,
            CONVERSATION_ID,
            SUBMISSION_ID,
        )
        assert content == self.user_message["content"]
        return {
            "state": "reserved",
            "user_message": dict(self.user_message),
            "assistant_message": None,
        }

    def complete_assistant_message(
        self,
        _assignment_id: str,
        _conversation_id: str,
        _user_message_id: str,
        _client_message_id: str,
        payload: dict[str, Any],
        trace_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        assert trace_payload is None
        self.assistant_message = _message(str(uuid4()), "assistant", payload["answer"])
        self.assistant_message.update(payload)
        return dict(self.assistant_message)

    def get_conversation(self, assignment_id: str, conversation_id: str) -> dict[str, Any] | None:
        if (assignment_id, conversation_id) != (ASSIGNMENT_ID, CONVERSATION_ID):
            return None
        return {
            "id": CONVERSATION_ID,
            "assignment_id": ASSIGNMENT_ID,
            "title": "荷小悦第一次接待顾客应该怎么说？",
            "created_at": NOW,
            "updated_at": NOW,
            "last_message_at": NOW,
            "message_count": 2,
            "last_message": self.assistant_message,
        }

    def mark_generation_failed(self, *_args: Any) -> None:
        raise AssertionError("generation should not fail")


def _request(app: Any, method: str, path: str, **kwargs: Any) -> httpx.Response:
    async def run() -> httpx.Response:
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.request(method, path, **kwargs)

    return asyncio.run(run())


def test_unified_intake_persists_original_before_routing_or_answer(tmp_path: Path) -> None:
    events: list[str] = []
    identity = FakeIdentityRepository()
    channel = FakeChannelRepository(events)
    records = FakeRecordRepository()
    conversations = FakeConversationRepository(events)

    def classify_route(text: str, **_kwargs: Any) -> str:
        assert events == ["persist_original", "reserve_message"]
        events.append("classify_route")
        return "service_scenario"

    def generate_answer(*, question: str, answer_route: str, **_kwargs: Any) -> dict[str, Any]:
        assert events == ["persist_original", "reserve_message", "classify_route"]
        events.append("generate_answer")
        assert question == "荷小悦第一次接待顾客应该怎么说？"
        assert answer_route == "service_scenario"
        return {
            "answer": "先问候，再确认顾客今天更希望放松哪个部位。",
            "answer_status": "AI 草稿",
            "confidence": "medium",
            "needs_review": False,
            "sources": [],
            "next_actions": [],
        }

    app = create_app(
        root_dir=tmp_path,
        repository_factory=lambda: object(),
        product_identity_repository_factory=lambda: identity,
        channel_repository_factory=lambda: channel,
        record_repository_factory=lambda: records,
        conversation_repository_factory=lambda: conversations,
        intake_route_classifier=classify_route,
        product_answer_generator=generate_answer,
    )

    response = _request(
        app,
        "POST",
        "/api/v1/intake",
        headers={"Authorization": "Bearer valid-session"},
        json={
            "client_submission_id": SUBMISSION_ID,
            "conversation_id": CONVERSATION_ID,
            "text": "荷小悦第一次接待顾客应该怎么说？",
            "source_asset_ids": [],
        },
    )

    assert response.status_code == 202
    assert events == [
        "persist_original",
        "reserve_message",
        "classify_route",
        "generate_answer",
    ]
    assert response.json()["receipt"] == "已收到，正在处理"
    assert response.json()["record"]["id"] == RECORD_ID
    assert response.json()["assistant_message"]["content"] == (
        "先问候，再确认顾客今天更希望放松哪个部位。"
    )
    assert "answer_route" not in response.text
    assert "service_scenario" not in response.text


def test_file_only_intake_stays_independent_from_answer_generation(tmp_path: Path) -> None:
    events: list[str] = []
    identity = FakeIdentityRepository()
    channel = FakeChannelRepository(events, expected_text="")

    def forbidden(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("file-only intake must not classify or generate an answer")

    app = create_app(
        root_dir=tmp_path,
        repository_factory=lambda: object(),
        product_identity_repository_factory=lambda: identity,
        channel_repository_factory=lambda: channel,
        record_repository_factory=FakeRecordRepository,
        conversation_repository_factory=lambda: FakeConversationRepository(events),
        intake_route_classifier=forbidden,
        product_answer_generator=forbidden,
    )

    response = _request(
        app,
        "POST",
        "/api/v1/intake",
        headers={"Authorization": "Bearer valid-session"},
        json={
            "client_submission_id": SUBMISSION_ID,
            "conversation_id": None,
            "text": "",
            "source_asset_ids": [ASSET_ID],
        },
    )

    assert response.status_code == 202
    assert events == ["persist_original"]
    assert response.json()["conversation"] is None
    assert response.json()["assistant_message"] is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("请用简单的话解释熵增定律。", "general"),
        ("荷小悦的品牌定位是什么？", "hxy_official"),
        ("结合荷小悦定位，分析社区足疗门店怎样提高复购。", "mixed"),
        ("荷小悦为什么叫这个名字？", "hxy_official"),
        ("顾客说按完还是不舒服，我该怎么回应？", "service_scenario"),
        ("判断这位顾客是不是颈椎病，并保证推拿能治好。", "high_risk"),
        ("如何保证门店服务质量？", "general"),
    ],
)
def test_intake_route_classifier_covers_product_routes(text: str, expected: str) -> None:
    assert classify_intake_route(text) == expected


def test_deterministic_high_risk_policy_cannot_be_downgraded_by_model() -> None:
    model_calls: list[str] = []

    def unsafe_model_classifier(_text: str, **_context: Any) -> str:
        model_calls.append("called")
        return "general"

    route = classify_intake_route(
        "这个顾客是不是腰椎病？请保证按摩可以治愈。",
        model_classifier=unsafe_model_classifier,
    )

    assert route == "high_risk"
    assert model_calls == []


class FakeModelRouter:
    def __init__(self, outputs: dict[str, str]) -> None:
        self.outputs = outputs
        self.calls: list[dict[str, Any]] = []

    def generate(self, task_type: str, **kwargs: Any) -> dict[str, Any]:
        self.calls.append({"task_type": task_type, **kwargs})
        return {
            "used_model": True,
            "reason": "ok",
            "output": self.outputs[task_type],
            "route": {
                "task_type": task_type,
                "provider": "test-provider",
                "selected_model": "test-model",
                "should_call_model": True,
            },
            "usage": {"input_tokens": 10, "output_tokens": 20},
        }


def test_model_assists_only_ambiguous_route_classification() -> None:
    router = FakeModelRouter(
        {"classification": '{"route":"service_scenario","confidence":0.93}'}
    )
    classifier = build_model_assisted_route_classifier(router)

    assert classifier("这件事接下来怎么处理？") == "service_scenario"
    assert [call["task_type"] for call in router.calls] == ["classification"]


def test_general_route_uses_model_without_hxy_knowledge_claims() -> None:
    router = FakeModelRouter(
        {"reasoning": "熵增可以理解为：一个系统如果不持续投入整理，通常会越来越无序。"}
    )

    answer = generate_general_answer("请解释熵增定律。", model_router=router)

    assert answer["answer"].startswith("熵增可以理解为")
    assert answer["answer_status"] == "AI 草稿"
    assert answer["sources"] == []
    assert answer["needs_review"] is False
    assert [call["task_type"] for call in router.calls] == ["reasoning"]
    prompt = router.calls[0]["messages"][0]["content"]
    assert "不要声称这是荷小悦正式口径" in prompt
