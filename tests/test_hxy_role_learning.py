from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from apps.api.hxy_knowledge_api import create_app


ROOT = Path(__file__).resolve().parents[1]
ACCOUNT_ID = "11000000-0000-0000-0000-000000000001"
ASSIGNMENT_ID = "22000000-0000-0000-0000-000000000001"
ORGANIZATION_ID = "33000000-0000-0000-0000-000000000001"
STORE_ID = "store-one"
SESSION_ID = "55000000-0000-0000-0000-000000000001"
NOW = datetime(2026, 7, 21, 9, 0, tzinfo=timezone.utc)


@dataclass(frozen=True)
class FakePrincipal:
    account_id: str = ACCOUNT_ID
    display_name: str = "测试技师"
    assignment_id: str = ASSIGNMENT_ID


@dataclass(frozen=True)
class FakeAssignment:
    assignment_id: str = ASSIGNMENT_ID
    organization_id: str = ORGANIZATION_ID
    organization_name: str = "荷小悦"
    store_id: str | None = STORE_ID
    store_name: str | None = "首店"
    role: str = "store_employee"


class FakeIdentityRepository:
    def __init__(self, role: str = "store_employee") -> None:
        self.assignment = FakeAssignment(role=role)

    def resolve_session(self, raw_token: str) -> FakePrincipal | None:
        return FakePrincipal() if raw_token == "valid-session" else None

    def list_assignments(self, _account_id: str) -> list[FakeAssignment]:
        return [self.assignment]


class FakeTrainingRepository:
    def __init__(self, sessions: list[dict[str, Any]] | None = None) -> None:
        self.sessions = list(sessions or [])
        self.list_calls: list[dict[str, Any]] = []
        self.saved: list[dict[str, Any]] = []

    def list_assignment_sessions(
        self,
        *,
        organization_id: str,
        assignment_id: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        self.list_calls.append(
            {
                "organization_id": organization_id,
                "assignment_id": assignment_id,
                "limit": limit,
            }
        )
        return [dict(item) for item in self.sessions[:limit]]

    def save_training_session(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.saved.append(dict(payload))
        self.sessions.insert(
            0,
            {
                "id": SESSION_ID,
                **payload,
                "created_at": NOW,
            },
        )
        return {"id": SESSION_ID}


class Client:
    def __init__(self, app: Any) -> None:
        self.app = app

    def request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        async def run() -> httpx.Response:
            transport = httpx.ASGITransport(app=self.app, raise_app_exceptions=False)
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://testserver",
            ) as client:
                return await client.request(method, path, **kwargs)

        return asyncio.run(run())

    def get(self, path: str, **kwargs: Any) -> httpx.Response:
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> httpx.Response:
        return self.request("POST", path, **kwargs)


def bearer() -> dict[str, str]:
    return {"Authorization": "Bearer valid-session"}


def build_client(
    *,
    role: str = "store_employee",
    sessions: list[dict[str, Any]] | None = None,
    evaluation: dict[str, Any] | None = None,
) -> tuple[Client, FakeTrainingRepository, list[dict[str, Any]]]:
    identity = FakeIdentityRepository(role)
    training = FakeTrainingRepository(sessions)
    evaluator_calls: list[dict[str, Any]] = []

    def evaluator(**payload: Any) -> dict[str, Any]:
        evaluator_calls.append(payload)
        return evaluation or {
            "score": 72,
            "level": "retrain",
            "needs_retrain": True,
            "standard_script": "先回应顾客感受，再说明服务边界。",
            "correction_points": ["不能承诺治疗效果"],
            "next_actions": ["再练一次服务边界表达"],
        }

    app = create_app(
        root_dir=ROOT,
        product_identity_repository_factory=lambda: identity,
        product_training_repository_factory=lambda: training,
        journey_training_evaluator=evaluator,
    )
    return Client(app), training, evaluator_calls


def test_learning_returns_one_assignment_scoped_next_action_and_private_progress() -> None:
    client, training, _ = build_client()

    response = client.get("/api/v1/learning", headers=bearer())

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"next_action", "progress", "limitations"}
    assert body["next_action"]["id"] == "service-boundary-v1"
    assert body["next_action"]["scenario"]["customer_message"]
    assert body["next_action"]["response_modes"] == ["text", "voice"]
    assert body["progress"]["visibility"] == "private"
    assert body["progress"]["attempts"] == 0
    assert "leaderboard" not in response.text.lower()
    assert training.list_calls == [
        {
            "organization_id": ORGANIZATION_ID,
            "assignment_id": ASSIGNMENT_ID,
            "limit": 20,
        }
    ]


def test_employee_cannot_request_another_employee_progress() -> None:
    client, training, _ = build_client()

    response = client.get(
        "/api/v1/learning?assignment_id=another-employee",
        headers=bearer(),
    )

    assert response.status_code == 422
    assert training.list_calls == []


def test_scenario_practice_uses_server_scenario_and_authenticated_scope() -> None:
    client, training, calls = build_client()

    response = client.post(
        "/api/v1/learning/practice",
        headers=bearer(),
        json={
            "action_id": "service-boundary-v1",
            "employee_answer": "我先了解一下您现在的感受，再帮您联系店长处理。",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["attempt"]["id"] == SESSION_ID
    assert body["attempt"]["score"] == 72
    assert body["progress"]["visibility"] == "private"
    assert body["next_action"]["id"] == "service-boundary-v1"
    assert calls[0]["assignment"].assignment_id == ASSIGNMENT_ID
    assert calls[0]["request"].customer_question == (
        "顾客说：做完以后还是不舒服，我该怎么办？"
    )
    assert training.saved[0]["organization_id"] == ORGANIZATION_ID
    assert training.saved[0]["store_id"] == STORE_ID
    assert training.saved[0]["assignment_id"] == ASSIGNMENT_ID


def test_learning_rejects_browser_submitted_identity_scope() -> None:
    client, training, calls = build_client()

    response = client.post(
        "/api/v1/learning/practice",
        headers=bearer(),
        json={
            "action_id": "service-boundary-v1",
            "employee_answer": "我的回答",
            "assignment_id": "another-employee",
            "store_id": "another-store",
        },
    )

    assert response.status_code == 422
    assert calls == []
    assert training.saved == []


def test_ai_result_cannot_certify_physical_massage_technique() -> None:
    client, _, _ = build_client(
        evaluation={
            "score": 100,
            "level": "excellent",
            "needs_retrain": False,
            "standard_script": "沟通表达通过。",
            "correction_points": [],
            "next_actions": [],
            "physical_technique_certified": True,
            "certification": "高级推拿手法认证",
        }
    )

    response = client.post(
        "/api/v1/learning/practice",
        headers=bearer(),
        json={
            "action_id": "service-boundary-v1",
            "employee_answer": "我先询问您的感受，不作疗效承诺。",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["attempt"]["physical_technique"] == "not_assessed"
    assert "现场" in "".join(body["limitations"])
    assert "高级推拿手法认证" not in response.text
    assert "physical_technique_certified" not in response.text


def test_non_employee_role_cannot_open_or_submit_personal_learning() -> None:
    client, training, calls = build_client(role="store_manager")

    page = client.get("/api/v1/learning", headers=bearer())
    practice = client.post(
        "/api/v1/learning/practice",
        headers=bearer(),
        json={"action_id": "service-boundary-v1", "employee_answer": "回答"},
    )

    assert page.status_code == 403
    assert practice.status_code == 403
    assert training.list_calls == []
    assert calls == []
