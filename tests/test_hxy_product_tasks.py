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
from apps.api.hxy_product.task_repository import TaskRepository, TaskStateConflict


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "data" / "migrations" / "015_hxy_product_tasks.sql"
TASK_LINK_MIGRATION = ROOT / "data" / "migrations" / "016_hxy_product_training.sql"

ACCOUNT_ID = "10000000-0000-0000-0000-000000000001"
MANAGER_ASSIGNMENT_ID = "20000000-0000-0000-0000-000000000001"
EMPLOYEE_ASSIGNMENT_ID = "20000000-0000-0000-0000-000000000002"
FOREIGN_EMPLOYEE_ASSIGNMENT_ID = "20000000-0000-0000-0000-000000000099"
ORGANIZATION_ID = "30000000-0000-0000-0000-000000000001"
STORE_ID = "store-one"
TASK_ID = "40000000-0000-0000-0000-000000000001"
MESSAGE_ID = "50000000-0000-0000-0000-000000000001"
CONVERSATION_ID = "60000000-0000-0000-0000-000000000001"
NOW = datetime(2026, 7, 12, 11, 0, tzinfo=timezone.utc)


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
    def __init__(self, active_role: str = "store_manager") -> None:
        self.active = FakeAssignment(
            assignment_id=MANAGER_ASSIGNMENT_ID,
            organization_id=ORGANIZATION_ID,
            organization_name="荷小悦",
            store_id=STORE_ID,
            store_name="首店",
            role=active_role,
        )
        if active_role in {"founder", "hq_operations"}:
            self.active = FakeAssignment(
                assignment_id=MANAGER_ASSIGNMENT_ID,
                organization_id=ORGANIZATION_ID,
                organization_name="荷小悦",
                store_id=None,
                store_name=None,
                role=active_role,
            )
        if active_role == "store_employee":
            self.active = FakeAssignment(
                assignment_id=EMPLOYEE_ASSIGNMENT_ID,
                organization_id=ORGANIZATION_ID,
                organization_name="荷小悦",
                store_id=STORE_ID,
                store_name="首店",
                role=active_role,
            )
        self.assignments = {
            MANAGER_ASSIGNMENT_ID: FakeAssignment(
                MANAGER_ASSIGNMENT_ID,
                ORGANIZATION_ID,
                "荷小悦",
                STORE_ID,
                "首店",
                "store_manager",
            ),
            EMPLOYEE_ASSIGNMENT_ID: FakeAssignment(
                EMPLOYEE_ASSIGNMENT_ID,
                ORGANIZATION_ID,
                "荷小悦",
                STORE_ID,
                "首店",
                "store_employee",
            ),
            FOREIGN_EMPLOYEE_ASSIGNMENT_ID: FakeAssignment(
                FOREIGN_EMPLOYEE_ASSIGNMENT_ID,
                ORGANIZATION_ID,
                "荷小悦",
                "store-two",
                "二店",
                "store_employee",
            ),
        }

    def resolve_session(self, raw_token: str) -> FakePrincipal | None:
        if raw_token != "valid-session":
            return None
        return FakePrincipal(ACCOUNT_ID, "测试用户", self.active.assignment_id)

    def list_assignments(self, _account_id: str) -> list[FakeAssignment]:
        return [self.active]

    def get_assignment(self, assignment_id: str) -> FakeAssignment | None:
        return self.assignments.get(assignment_id)

    def organization_has_store(self, organization_id: str, store_id: str) -> bool:
        return organization_id == ORGANIZATION_ID and store_id == STORE_ID


class FakeTaskRepository:
    def __init__(self) -> None:
        self.tasks: dict[str, dict[str, Any]] = {}
        self.events: list[dict[str, Any]] = []
        self.list_scopes: list[dict[str, Any]] = []
        self.owned_source_messages = {(CONVERSATION_ID, MESSAGE_ID)}

    def source_message_owned_by_assignment(
        self,
        assignment_id: str,
        source_conversation_id: str,
        source_message_id: str,
    ) -> bool:
        return (
            assignment_id == MANAGER_ASSIGNMENT_ID
            and (source_conversation_id, source_message_id) in self.owned_source_messages
        )

    def list_tasks(self, **scope: Any) -> list[dict[str, Any]]:
        self.list_scopes.append(scope)
        return list(self.tasks.values())

    def create_task(self, payload: dict[str, Any]) -> dict[str, Any]:
        task = {
            "id": TASK_ID,
            "title": payload["title"],
            "details": payload.get("details") or "",
            "priority": payload["priority"],
            "status": "open",
            "visibility": payload["visibility"],
            "organization_id": payload["organization_id"],
            "store_id": payload.get("store_id"),
            "creator_assignment_id": payload["creator_assignment_id"],
            "assignee_assignment_id": payload.get("assignee_assignment_id"),
            "source_conversation_id": payload.get("source_conversation_id"),
            "source_message_id": payload.get("source_message_id"),
            "result": None,
            "due_at": payload.get("due_at"),
            "completed_at": None,
            "created_at": NOW,
            "updated_at": NOW,
        }
        self.tasks[TASK_ID] = task
        self.events.append({"event_type": "created", "actor_assignment_id": payload["creator_assignment_id"]})
        return dict(task)

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        task = self.tasks.get(task_id)
        return dict(task) if task else None

    def update_task(
        self,
        task_id: str,
        *,
        actor_assignment_id: str,
        status: str,
        result: str | None,
    ) -> dict[str, Any] | None:
        task = self.tasks.get(task_id)
        if task is None:
            return None
        task.update(
            {
                "status": status,
                "result": result,
                "completed_at": NOW if status == "completed" else None,
                "updated_at": NOW,
            }
        )
        self.events.append(
            {
                "event_type": status,
                "actor_assignment_id": actor_assignment_id,
                "result": result,
            }
        )
        return dict(task)


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

    def patch(self, url: str, **kwargs):
        return self.request("PATCH", url, **kwargs)


def bearer() -> dict[str, str]:
    return {"Authorization": "Bearer valid-session"}


def build_client(active_role: str = "store_manager"):
    identity = FakeIdentityRepository(active_role)
    tasks = FakeTaskRepository()
    app = create_app(
        root_dir=ROOT,
        product_identity_repository_factory=lambda: identity,
        task_repository_factory=lambda: tasks,
    )
    return ASGIClient(app), identity, tasks


def task_payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "title": "复核今日接待话术",
        "details": "完成后记录顾客是否听懂。",
        "priority": "high",
        "visibility": "assignee",
        "assignee_assignment_id": EMPLOYEE_ASSIGNMENT_ID,
        "source_conversation_id": CONVERSATION_ID,
        "source_message_id": MESSAGE_ID,
    }
    payload.update(overrides)
    return payload


def test_manager_can_create_same_store_task_from_an_answer() -> None:
    client, _, repository = build_client()

    response = client.post("/api/v1/tasks", headers=bearer(), json=task_payload())

    assert response.status_code == 201
    body = response.json()["task"]
    assert body["title"] == "复核今日接待话术"
    assert body["source_message_id"] == MESSAGE_ID
    assert "creator_assignment_id" not in body
    assert repository.events == [
        {"event_type": "created", "actor_assignment_id": MANAGER_ASSIGNMENT_ID}
    ]


def test_manager_cannot_assign_task_to_another_store() -> None:
    client, _, repository = build_client()

    response = client.post(
        "/api/v1/tasks",
        headers=bearer(),
        json=task_payload(assignee_assignment_id=FOREIGN_EMPLOYEE_ASSIGNMENT_ID),
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "Forbidden"}
    assert repository.tasks == {}


def test_headquarters_cannot_create_task_for_store_outside_organization() -> None:
    client, _, repository = build_client("founder")

    response = client.post(
        "/api/v1/tasks",
        headers=bearer(),
        json=task_payload(
            visibility="store",
            assignee_assignment_id=None,
            store_id="store-two",
            source_conversation_id=None,
            source_message_id=None,
        ),
    )

    assert response.status_code == 403
    assert repository.tasks == {}


def test_task_source_message_must_belong_to_current_assignment() -> None:
    client, _, repository = build_client()
    foreign_message_id = "50000000-0000-0000-0000-000000000099"

    response = client.post(
        "/api/v1/tasks",
        headers=bearer(),
        json=task_payload(source_message_id=foreign_message_id),
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}
    assert repository.tasks == {}


def test_task_source_message_must_belong_to_source_conversation() -> None:
    client, _, repository = build_client()

    response = client.post(
        "/api/v1/tasks",
        headers=bearer(),
        json=task_payload(
            source_conversation_id="60000000-0000-0000-0000-000000000099",
        ),
    )

    assert response.status_code == 404
    assert repository.tasks == {}


def test_employee_cannot_create_tasks_but_can_read_visible_tasks() -> None:
    client, _, repository = build_client("store_employee")
    repository.create_task(
        {
            "title": "完成开店检查",
            "priority": "normal",
            "visibility": "store",
            "organization_id": ORGANIZATION_ID,
            "store_id": STORE_ID,
            "creator_assignment_id": MANAGER_ASSIGNMENT_ID,
            "assignee_assignment_id": None,
        }
    )

    create_response = client.post("/api/v1/tasks", headers=bearer(), json=task_payload())
    list_response = client.get("/api/v1/tasks", headers=bearer())

    assert create_response.status_code == 403
    assert list_response.status_code == 200
    assert list_response.json()["count"] == 1
    assert repository.list_scopes[-1]["assignment_id"] == EMPLOYEE_ASSIGNMENT_ID
    assert repository.list_scopes[-1]["store_id"] == STORE_ID


def test_assignee_completion_records_actor_time_and_result() -> None:
    client, _, repository = build_client("store_employee")
    repository.create_task(
        {
            "title": "完成接待练习",
            "priority": "normal",
            "visibility": "assignee",
            "organization_id": ORGANIZATION_ID,
            "store_id": STORE_ID,
            "creator_assignment_id": MANAGER_ASSIGNMENT_ID,
            "assignee_assignment_id": EMPLOYEE_ASSIGNMENT_ID,
        }
    )

    response = client.patch(
        f"/api/v1/tasks/{TASK_ID}",
        headers=bearer(),
        json={"status": "completed", "result": "已完成两轮接待练习。"},
    )

    assert response.status_code == 200
    body = response.json()["task"]
    assert body["status"] == "completed"
    assert body["result"] == "已完成两轮接待练习。"
    assert body["completed_at"] is not None
    assert repository.events[-1] == {
        "event_type": "completed",
        "actor_assignment_id": EMPLOYEE_ASSIGNMENT_ID,
        "result": "已完成两轮接待练习。",
    }


def test_manager_cannot_modify_same_store_private_task_not_visible_to_manager() -> None:
    client, _, repository = build_client()
    repository.create_task(
        {
            "title": "员工私人待办",
            "priority": "normal",
            "visibility": "assignee",
            "organization_id": ORGANIZATION_ID,
            "store_id": STORE_ID,
            "creator_assignment_id": EMPLOYEE_ASSIGNMENT_ID,
            "assignee_assignment_id": EMPLOYEE_ASSIGNMENT_ID,
        }
    )

    response = client.patch(
        f"/api/v1/tasks/{TASK_ID}",
        headers=bearer(),
        json={"status": "completed", "result": "不应允许店长代为完成。"},
    )

    assert response.status_code == 404
    assert repository.tasks[TASK_ID]["status"] == "open"


def test_task_migration_defines_scoped_tasks_and_append_only_events() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    normalized = " ".join(sql.split())

    assert "CREATE TABLE IF NOT EXISTS hxy_product_tasks" in normalized
    assert "organization_id UUID NOT NULL" in normalized
    assert "FOREIGN KEY (organization_id, store_id)" in normalized
    assert "REFERENCES hxy_organization_stores(organization_id, store_id)" in normalized
    assert "FOREIGN KEY (organization_id, assignee_assignment_id)" in normalized
    assert "FOREIGN KEY (organization_id, store_id, assignee_assignment_id)" in normalized
    assert "creator_assignment_id UUID NOT NULL" in normalized
    assert "assignee_assignment_id UUID" in normalized
    assert "source_message_id UUID" in normalized
    assert "FOREIGN KEY (creator_assignment_id, source_conversation_id)" in normalized
    assert "REFERENCES hxy_product_conversations(assignment_id, conversation_id)" in normalized
    assert "FOREIGN KEY (creator_assignment_id, source_conversation_id, source_message_id)" in normalized
    assert "REFERENCES hxy_product_messages(assignment_id, conversation_id, message_id)" in normalized
    assert "visibility IN ('assignee', 'store')" in normalized
    assert "status IN ('open', 'in_progress', 'completed', 'cancelled')" in normalized
    assert "CREATE TABLE IF NOT EXISTS hxy_product_task_events" in normalized
    assert "organization_id UUID NOT NULL" in normalized
    assert "FOREIGN KEY (organization_id, actor_assignment_id)" in normalized
    assert "FOREIGN KEY (organization_id, task_id)" in normalized
    assert "ON DELETE RESTRICT" in normalized
    assert "BEFORE UPDATE OR DELETE ON hxy_product_task_events" in normalized
    assert "BEFORE TRUNCATE ON hxy_product_task_events" in normalized
    assert "actor_assignment_id UUID NOT NULL" in normalized
    assert "event_type" in normalized
    assert "htops" not in sql.lower()
    assert "hetang" not in sql.lower()


def test_task_link_upgrade_adds_same_store_parent_constraint() -> None:
    sql = TASK_LINK_MIGRATION.read_text(encoding="utf-8")
    normalized = " ".join(sql.split())

    assert "ALTER TABLE hxy_product_tasks ADD COLUMN IF NOT EXISTS parent_task_id UUID" in normalized
    assert "ON hxy_product_tasks (organization_id, store_id, task_id)" in normalized
    assert "FOREIGN KEY (organization_id, store_id, parent_task_id)" in normalized
    assert "REFERENCES hxy_product_tasks(organization_id, store_id, task_id)" in normalized


def test_task_repository_queries_are_assignment_and_organization_scoped() -> None:
    source = (ROOT / "apps" / "api" / "hxy_product" / "task_repository.py").read_text(
        encoding="utf-8"
    )

    assert "organization_id = %s::uuid" in source
    assert "assignment_id" in source
    assert "store_id" in source
    assert "INSERT INTO hxy_product_task_events" in source
    assert "hxy_product_messages.assignment_id = %s::uuid" in source
    assert "hxy_product_messages.conversation_id = %s::uuid" in source
    assert "hxy_product_messages.role = 'assistant'" in source
    assert "current[\"status\"] in {\"completed\", \"cancelled\"}" in source


def test_repository_rechecks_closed_state_after_acquiring_row_lock() -> None:
    class Result:
        def __init__(self, row):
            self.row = row

        def fetchone(self):
            return self.row

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, sql, _params):
            assert "FOR UPDATE" in sql
            return Result({"status": "completed"})

    repository = TaskRepository.__new__(TaskRepository)
    repository.connect = lambda: Connection()

    with pytest.raises(TaskStateConflict, match="already closed"):
        repository.update_task(
            TASK_ID,
            actor_assignment_id=EMPLOYEE_ASSIGNMENT_ID,
            status="in_progress",
            result=None,
        )
