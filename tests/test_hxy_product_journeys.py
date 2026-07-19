from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import pytest

from apps.api.hxy_knowledge_api import create_app


ROOT = Path(__file__).resolve().parents[1]
TRAINING_MIGRATION = ROOT / "data" / "migrations" / "016_hxy_product_training.sql"
ACCOUNT_ID = "10000000-0000-0000-0000-000000000001"
ASSIGNMENT_ID = "20000000-0000-0000-0000-000000000001"
ORGANIZATION_ID = "30000000-0000-0000-0000-000000000001"
STORE_ID = "store-one"
TASK_ID = "40000000-0000-0000-0000-000000000001"
SOURCE_TASK_ID = "40000000-0000-0000-0000-000000000099"
NOW = datetime(2026, 7, 12, 12, 0, tzinfo=timezone.utc)


@dataclass(frozen=True)
class FakePrincipal:
    account_id: str
    display_name: str
    assignment_id: str


@dataclass(frozen=True)
class FakeAssignment:
    assignment_id: str
    organization_id: str
    organization_name: str
    store_id: str | None
    store_name: str | None
    role: str


class FakeIdentityRepository:
    def __init__(self, role: str) -> None:
        store_id = STORE_ID if role in {"store_manager", "store_employee"} else None
        self.assignment = FakeAssignment(
            assignment_id=ASSIGNMENT_ID,
            organization_id=ORGANIZATION_ID,
            organization_name="荷小悦",
            store_id=store_id,
            store_name="首店" if store_id else None,
            role=role,
        )

    def resolve_session(self, raw_token: str) -> FakePrincipal | None:
        if raw_token != "valid-session":
            return None
        return FakePrincipal(ACCOUNT_ID, "测试用户", ASSIGNMENT_ID)

    def list_assignments(self, _account_id: str) -> list[FakeAssignment]:
        return [self.assignment]


class FakeTaskRepository:
    def __init__(self) -> None:
        self.created: list[dict[str, Any]] = []
        self.records = {
            SOURCE_TASK_ID: {
                "id": SOURCE_TASK_ID,
                "organization_id": ORGANIZATION_ID,
                "store_id": STORE_ID,
                "creator_assignment_id": ASSIGNMENT_ID,
                "assignee_assignment_id": None,
                "visibility": "store",
                "status": "open",
            }
        }

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        record = self.records.get(task_id)
        return dict(record) if record else None

    def create_task(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.created.append(dict(payload))
        return {
            "id": TASK_ID,
            "organization_id": payload["organization_id"],
            "store_id": payload["store_id"],
            "creator_assignment_id": payload["creator_assignment_id"],
            "assignee_assignment_id": None,
            "source_conversation_id": None,
            "source_message_id": None,
            "title": payload["title"],
            "details": payload["details"],
            "priority": payload["priority"],
            "status": "open",
            "visibility": "store",
            "result": None,
            "due_at": None,
            "completed_at": None,
            "created_at": NOW,
            "updated_at": NOW,
            "parent_task_id": payload.get("parent_task_id"),
        }


class FakeTrainingRepository:
    def __init__(self) -> None:
        self.saved: list[dict[str, Any]] = []

    def save_training_session(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.saved.append(dict(payload))
        return {"id": "50000000-0000-0000-0000-000000000001"}


class ASGIClient:
    def __init__(self, app) -> None:
        self.app = app

    def request(self, method: str, url: str, **kwargs):
        async def run():
            transport = httpx.ASGITransport(app=self.app, raise_app_exceptions=False)
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                return await client.request(method, url, **kwargs)

        return asyncio.run(run())

    def get(self, url: str, **kwargs):
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs):
        return self.request("POST", url, **kwargs)


def bearer() -> dict[str, str]:
    return {"Authorization": "Bearer valid-session"}


def build_client(role: str, evaluation: dict[str, Any] | None = None):
    identity = FakeIdentityRepository(role)
    tasks = FakeTaskRepository()
    training = FakeTrainingRepository()
    training_calls: list[dict[str, Any]] = []

    def evaluate_training(**payload: Any) -> dict[str, Any]:
        training_calls.append(payload)
        return evaluation or {
            "score": 68,
            "level": "retrain",
            "needs_retrain": True,
            "standard_script": "可以说泡脚有助于放松，但不能替代医疗诊断或治疗。",
            "correction_points": ["不要承诺治疗效果", "先回应顾客感受"],
            "next_actions": ["再练一次合规表达"],
        }

    app = create_app(
        root_dir=ROOT,
        product_identity_repository_factory=lambda: identity,
        task_repository_factory=lambda: tasks,
        product_training_repository_factory=lambda: training,
        journey_training_evaluator=evaluate_training,
    )
    return ASGIClient(app), identity, tasks, training, training_calls


@pytest.mark.parametrize(
    ("role", "expected_types"),
    [
        ("founder", ["ask", "tasks", "ask"]),
        ("store_manager", ["tasks", "issue", "ask"]),
        ("store_employee", ["ask", "training", "issue"]),
        ("hq_operations", ["tasks", "ask", "ask"]),
    ],
)
def test_suggestions_are_server_derived_and_limited_by_role(
    role: str,
    expected_types: list[str],
) -> None:
    client, _, _, _, _ = build_client(role)

    response = client.get("/api/v1/journeys/suggestions?role=founder", headers=bearer())

    assert response.status_code == 200
    body = response.json()
    assert [item["type"] for item in body["items"]] == expected_types
    assert len(body["items"]) <= 3
    assert "role" not in body


def test_employee_training_uses_authenticated_employee_and_store_context() -> None:
    client, _, _, training, calls = build_client("store_employee")

    response = client.post(
        "/api/v1/journeys/training/evaluate",
        headers=bearer(),
        json={
            "customer_question": "这个能治疗失眠吗？",
            "employee_answer": "肯定能治好。",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["result_type"] == "training_result"
    assert body["primary_result"]["score"] == 68
    assert body["primary_result"]["correction_points"]
    assert body["artifact"] == {
        "type": "training_session",
        "id": "50000000-0000-0000-0000-000000000001",
    }
    assert calls[0]["principal"].account_id == ACCOUNT_ID
    assert calls[0]["assignment"].store_id == STORE_ID
    assert training.saved[0]["organization_id"] == ORGANIZATION_ID
    assert training.saved[0]["assignment_id"] == ASSIGNMENT_ID
    assert training.saved[0]["store_id"] == STORE_ID
    assert training.saved[0]["customer_question"] == "这个能治疗失眠吗？"
    assert training.saved[0]["employee_answer"] == "肯定能治好。"
    assert "review_task_id" not in training.saved[0]


def test_training_result_redacts_internal_paths_and_limits_levels() -> None:
    client, _, _, _, _ = build_client(
        "store_employee",
        {
            "score": 88,
            "level": "/root/hxy/private-level",
            "needs_retrain": False,
            "standard_script": "参考 /root/hxy/knowledge/private.md 和 data/private.json",
            "correction_points": ["删除 knowledge/raw/private.md"],
            "next_actions": ["打开 /root/hxy/ops/private.env"],
        },
    )

    response = client.post(
        "/api/v1/journeys/training/evaluate",
        headers=bearer(),
        json={"customer_question": "怎么说？", "employee_answer": "我的回答"},
    )

    assert response.status_code == 200
    body_text = response.text
    assert "/root/hxy" not in body_text
    assert "knowledge/raw" not in body_text
    assert "data/private" not in body_text
    assert response.json()["primary_result"]["level"] == "retrain"


def test_training_rejects_browser_submitted_identity_or_store_scope() -> None:
    client, _, _, training, calls = build_client("store_employee")

    response = client.post(
        "/api/v1/journeys/training/evaluate",
        headers=bearer(),
        json={
            "customer_question": "怎么说？",
            "employee_answer": "我的回答",
            "employee_id": "another-employee",
            "store_id": "another-store",
        },
    )

    assert response.status_code == 422
    assert calls == []
    assert training.saved == []


def test_role_without_training_capability_cannot_use_training_journey() -> None:
    client, _, _, training, calls = build_client("store_manager")

    response = client.post(
        "/api/v1/journeys/training/evaluate",
        headers=bearer(),
        json={"customer_question": "怎么说？", "employee_answer": "我的回答"},
    )

    assert response.status_code == 403
    assert calls == []
    assert training.saved == []


def test_employee_issue_report_becomes_current_store_visible_work() -> None:
    client, _, tasks, _, _ = build_client("store_employee")

    response = client.post(
        "/api/v1/issues",
        headers=bearer(),
        json={
            "title": "顾客对项目区别听不懂",
            "details": "今天连续两位顾客问清泡和调泡有什么区别。",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["result_type"] == "issue_report"
    assert body["primary_result"]["task"]["title"] == "顾客对项目区别听不懂"
    assert body["primary_result"]["task"]["available_actions"] == ["complete"]
    assert "creator_assignment_id" not in str(body)
    assert tasks.created[0]["organization_id"] == ORGANIZATION_ID
    assert tasks.created[0]["store_id"] == STORE_ID
    assert tasks.created[0]["creator_assignment_id"] == ASSIGNMENT_ID
    assert tasks.created[0]["visibility"] == "store"
    for forbidden in (
        "store_id",
        "assignee_assignment_id",
        "source_conversation_id",
        "source_message_id",
        "parent_task_id",
    ):
        assert forbidden not in body["primary_result"]["task"]


def test_manager_issue_can_link_to_a_visible_source_task() -> None:
    client, _, tasks, _, _ = build_client("store_manager")

    response = client.post(
        "/api/v1/issues",
        headers=bearer(),
        json={
            "title": "物料不足",
            "details": "缺少顾客须知。",
            "source_task_id": SOURCE_TASK_ID,
        },
    )

    assert response.status_code == 201
    assert tasks.created[0]["parent_task_id"] == SOURCE_TASK_ID


def test_issue_cannot_link_to_a_task_outside_the_active_store() -> None:
    client, _, tasks, _, _ = build_client("store_manager")
    tasks.records[SOURCE_TASK_ID]["store_id"] = "another-store"

    response = client.post(
        "/api/v1/issues",
        headers=bearer(),
        json={
            "title": "跨店问题",
            "details": "不能关联其他门店任务。",
            "source_task_id": SOURCE_TASK_ID,
        },
    )

    assert response.status_code == 404
    assert tasks.created == []


def test_role_without_issue_capability_cannot_report_store_issue() -> None:
    client, _, tasks, _, _ = build_client("founder")

    response = client.post(
        "/api/v1/issues",
        headers=bearer(),
        json={"title": "测试问题", "details": "不能跨角色创建门店事项。"},
    )

    assert response.status_code == 403
    assert tasks.created == []


def test_product_training_migration_is_tenant_and_assignment_scoped() -> None:
    sql = TRAINING_MIGRATION.read_text(encoding="utf-8")
    normalized = " ".join(sql.split())

    assert "CREATE TABLE IF NOT EXISTS hxy_product_training_sessions" in normalized
    assert "organization_id UUID NOT NULL" in normalized
    assert "assignment_id UUID NOT NULL" in normalized
    assert "store_id TEXT NOT NULL" in normalized
    assert "FOREIGN KEY (organization_id, assignment_id)" in normalized
    assert "REFERENCES hxy_role_assignments(organization_id, assignment_id)" in normalized
    assert "FOREIGN KEY (organization_id, store_id, assignment_id)" in normalized
    assert "REFERENCES hxy_role_assignments(organization_id, store_id, assignment_id)" in normalized
    assert "hxy_training_sessions" not in sql
    assert "hxy_review_tasks" not in sql
    assert "htops" not in sql.lower()


def test_product_training_repository_inserts_only_scoped_session_fields() -> None:
    from apps.api.hxy_product.training_repository import ProductTrainingRepository

    captured: list[tuple[str, tuple[Any, ...]]] = []

    class Result:
        def fetchone(self):
            return {"training_session_id": "50000000-0000-0000-0000-000000000001"}

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, sql: str, params: tuple[Any, ...]):
            captured.append((" ".join(sql.split()), params))
            return Result()

    repository = ProductTrainingRepository.__new__(ProductTrainingRepository)
    repository.connect = lambda: Connection()
    result = repository.save_training_session(
        {
            "organization_id": ORGANIZATION_ID,
            "assignment_id": ASSIGNMENT_ID,
            "store_id": STORE_ID,
            "customer_question": "这个能治疗失眠吗？",
            "employee_answer": "肯定能治好。",
            "score": 68,
            "level": "retrain",
            "needs_retrain": True,
            "standard_script": "不能承诺治疗效果。",
            "correction_points": ["不要承诺治疗效果"],
        }
    )

    lock_sql, lock_params = captured[0]
    sql, params = captured[1]
    assert "FROM hxy_role_assignments" in lock_sql
    assert "organization_id = %s::uuid" in lock_sql
    assert "store_id = %s" in lock_sql
    assert "assignment_id = %s::uuid" in lock_sql
    assert "status = 'active'" in lock_sql
    assert "FOR UPDATE" in lock_sql
    assert lock_params == (ORGANIZATION_ID, STORE_ID, ASSIGNMENT_ID)
    assert "INSERT INTO hxy_product_training_sessions" in sql
    assert "organization_id" in sql
    assert "assignment_id" in sql
    assert "store_id" in sql
    assert ORGANIZATION_ID in params
    assert ASSIGNMENT_ID in params
    assert STORE_ID in params
    assert result == {"id": "50000000-0000-0000-0000-000000000001"}


def test_default_product_training_does_not_write_legacy_knowledge_repository(
    monkeypatch,
) -> None:
    identity = FakeIdentityRepository("store_employee")
    tasks = FakeTaskRepository()
    training = FakeTrainingRepository()
    legacy_calls: list[str] = []

    def legacy_repository():
        legacy_calls.append("called")
        raise AssertionError("legacy knowledge repository must not be used")

    monkeypatch.setattr(
        "apps.api.hxy_knowledge_api._evaluate_training_content",
        lambda **_kwargs: {
            "score": 80,
            "level": "pass",
            "needs_retrain": False,
            "standard_script": "先回应顾客感受，再说明服务边界。",
            "correction_points": [],
            "next_actions": [],
        },
    )
    app = create_app(
        root_dir=ROOT,
        repository_factory=legacy_repository,
        product_identity_repository_factory=lambda: identity,
        task_repository_factory=lambda: tasks,
        product_training_repository_factory=lambda: training,
    )

    response = ASGIClient(app).post(
        "/api/v1/journeys/training/evaluate",
        headers=bearer(),
        json={"customer_question": "怎么说？", "employee_answer": "我的回答"},
    )

    assert response.status_code == 200
    assert legacy_calls == []
    assert len(training.saved) == 1
