from __future__ import annotations

import asyncio
import importlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest

from apps.api.hxy_knowledge_api import create_app


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "data" / "migrations" / "010_hxy_product_conversations.sql"

ACCOUNT_ID = "10000000-0000-0000-0000-000000000001"
ASSIGNMENT_ID = "20000000-0000-0000-0000-000000000001"
FOREIGN_ASSIGNMENT_ID = "20000000-0000-0000-0000-000000000099"
ORGANIZATION_ID = "30000000-0000-0000-0000-000000000001"
CONVERSATION_ID = "50000000-0000-0000-0000-000000000001"
FOREIGN_CONVERSATION_ID = "50000000-0000-0000-0000-000000000099"
CLIENT_MESSAGE_ID = "60000000-0000-0000-0000-000000000001"
NOW = datetime(2026, 7, 10, 9, 0, tzinfo=timezone.utc)


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
    def __init__(self) -> None:
        self.assignment_account_ids: list[str] = []
        self.assignment = FakeAssignment(
            assignment_id=ASSIGNMENT_ID,
            organization_id=ORGANIZATION_ID,
            organization_name="测试组织",
            store_id="test-store",
            store_name="测试门店",
            role="store_manager",
        )

    def resolve_session(self, raw_token: str) -> FakePrincipal | None:
        if raw_token != "valid-session":
            return None
        return FakePrincipal(ACCOUNT_ID, "测试店长", ASSIGNMENT_ID)

    def list_assignments(self, account_id: str) -> list[FakeAssignment]:
        self.assignment_account_ids.append(account_id)
        return [self.assignment]


class FakeConversationRepository:
    def __init__(self) -> None:
        self.conversations: dict[tuple[str, str], dict[str, Any]] = {}
        self.messages: dict[tuple[str, str], list[dict[str, Any]]] = {}
        self.reservations: dict[tuple[str, str], tuple[dict[str, Any], dict[str, Any] | None]] = {}
        self.calls: list[tuple[str, str]] = []
        self.traces: list[dict[str, Any]] = []
        self.create_conversation(ASSIGNMENT_ID, conversation_id=CONVERSATION_ID)
        self.create_conversation(FOREIGN_ASSIGNMENT_ID, conversation_id=FOREIGN_CONVERSATION_ID)

    @staticmethod
    def _conversation(conversation_id: str, assignment_id: str) -> dict[str, Any]:
        return {
            "id": conversation_id,
            "assignment_id": assignment_id,
            "title": "新对话",
            "created_at": NOW,
            "updated_at": NOW,
            "last_message_at": None,
            "message_count": 0,
            "last_message": None,
        }

    def create_conversation(
        self,
        assignment_id: str,
        *,
        conversation_id: str | None = None,
    ) -> dict[str, Any]:
        self.calls.append(("create", assignment_id))
        record = self._conversation(conversation_id or str(uuid4()), assignment_id)
        self.conversations[(assignment_id, record["id"])] = record
        self.messages[(assignment_id, record["id"])] = []
        return dict(record)

    def list_conversations(self, assignment_id: str, *, limit: int) -> list[dict[str, Any]]:
        self.calls.append(("list", assignment_id))
        return [
            dict(record)
            for (owner, _), record in self.conversations.items()
            if owner == assignment_id
        ][:limit]

    def get_conversation(self, assignment_id: str, conversation_id: str) -> dict[str, Any] | None:
        self.calls.append(("get", assignment_id))
        record = self.conversations.get((assignment_id, conversation_id))
        return dict(record) if record else None

    def list_messages(self, assignment_id: str, conversation_id: str) -> list[dict[str, Any]]:
        self.calls.append(("messages", assignment_id))
        return [dict(item) for item in self.messages.get((assignment_id, conversation_id), [])]

    def reserve_user_message(
        self,
        assignment_id: str,
        conversation_id: str,
        client_message_id: str,
        content: str,
    ) -> dict[str, Any] | None:
        self.calls.append(("reserve", assignment_id))
        if (assignment_id, conversation_id) not in self.conversations:
            return None
        key = (assignment_id, client_message_id)
        if key in self.reservations:
            user_message, assistant_message = self.reservations[key]
            return {
                "state": "completed" if assistant_message else "processing",
                "user_message": dict(user_message),
                "assistant_message": dict(assistant_message) if assistant_message else None,
            }
        user_message = {
            "id": str(uuid4()),
            "conversation_id": conversation_id,
            "role": "user",
            "content": content,
            "created_at": NOW,
            "answer_id": None,
            "answer_status": None,
            "confidence": None,
            "needs_review": None,
            "sources": [],
            "next_actions": [],
        }
        self.messages[(assignment_id, conversation_id)].append(user_message)
        self.reservations[key] = (user_message, None)
        return {"state": "reserved", "user_message": dict(user_message), "assistant_message": None}

    def complete_assistant_message(
        self,
        assignment_id: str,
        conversation_id: str,
        user_message_id: str,
        client_message_id: str,
        payload: dict[str, Any],
        trace_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        self.calls.append(("complete", assignment_id))
        key = (assignment_id, client_message_id)
        reservation = self.reservations.get(key)
        if not reservation or reservation[0]["id"] != user_message_id:
            return None
        if reservation[1]:
            return dict(reservation[1])
        assistant_message = {
            "id": str(uuid4()),
            "conversation_id": conversation_id,
            "role": "assistant",
            "content": payload["answer"],
            "created_at": NOW,
            "answer_id": payload.get("answer_id"),
            "answer_status": payload.get("answer_status"),
            "confidence": payload.get("confidence"),
            "needs_review": payload.get("needs_review"),
            "sources": payload.get("sources", []),
            "next_actions": payload.get("next_actions", []),
            "result_type": payload.get("result_type"),
            "actions": payload.get("actions", []),
        }
        self.messages[(assignment_id, conversation_id)].append(assistant_message)
        if trace_payload:
            self.traces.append(dict(trace_payload))
        self.reservations[key] = (reservation[0], assistant_message)
        conversation = self.conversations[(assignment_id, conversation_id)]
        conversation.update(
            {
                "title": reservation[0]["content"][:40],
                "updated_at": NOW,
                "last_message_at": NOW,
                "message_count": 2,
                "last_message": assistant_message,
            }
        )
        return dict(assistant_message)

    def mark_generation_failed(
        self,
        assignment_id: str,
        conversation_id: str,
        user_message_id: str,
    ) -> None:
        self.calls.append(("failed", assignment_id))


class ASGIClient:
    def __init__(self, app) -> None:
        self.app = app

    def request(self, method: str, url: str, **kwargs):
        async def run():
            transport = httpx.ASGITransport(app=self.app, raise_app_exceptions=False)
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                return await client.request(method, url, **kwargs)

        return asyncio.run(run())


def bearer(token: str = "valid-session") -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


class EmptyMaterialRepository:
    def __init__(self) -> None:
        self.search_assignments: list[str] = []

    def search_material_chunks(self, assignment_id: str, *_args, **_kwargs):
        self.search_assignments.append(assignment_id)
        return []


@pytest.fixture
def conversation_context(tmp_path: Path, monkeypatch):
    identity_repository = FakeIdentityRepository()
    conversation_repository = FakeConversationRepository()
    material_repository = EmptyMaterialRepository()
    generated_questions: list[dict[str, Any]] = []

    def fake_generate_answer(*, question: str, **kwargs) -> dict[str, Any]:
        generated_questions.append({"question": question, **kwargs})
        return {
            "answer": "先问顾客当下感受，再按体验需求介绍项目。",
            "answer_status": "待复核",
            "confidence": "medium",
            "needs_review": True,
            "answer_id": "70000000-0000-0000-0000-000000000001",
            "next_actions": ["确认顾客需求"],
            "evidence": [
                {
                    "chunk_id": "internal-chunk",
                    "title": "/root/hxy/knowledge/raw/inbox/接待话术.md",
                    "excerpt": "参考 /root/hxy/knowledge/raw/inbox/接待话术.md 的接待原则。",
                    "strength": "reference",
                    "source_path": "/root/hxy/knowledge/raw/inbox/接待话术.md",
                    "governance": {"raw": True},
                },
                {
                    "title": "C:\\Users\\founder\\Documents\\经营资料.pdf",
                    "excerpt": "另见 /mnt/private/经营资料.pdf 和 C:\\Users\\founder\\Documents\\经营资料.pdf。",
                    "strength": "candidate",
                },
            ],
            "understanding": {"private": True},
            "model_route": {"provider": "internal-provider"},
            "pipeline": {"thinking": "private"},
        }

    answer_service = importlib.import_module("hxy_knowledge.answer_service")
    monkeypatch.setattr(answer_service, "generate_answer", fake_generate_answer)
    app = create_app(
        root_dir=tmp_path,
        repository_factory=lambda: object(),
        product_identity_repository_factory=lambda: identity_repository,
        conversation_repository_factory=lambda: conversation_repository,
        material_repository_factory=lambda: material_repository,
    )
    return (
        ASGIClient(app),
        identity_repository,
        conversation_repository,
        generated_questions,
    )


def test_conversation_endpoints_require_authenticated_session(conversation_context) -> None:
    client, identity_repository, _, _ = conversation_context

    response = client.request("GET", "/api/v1/conversations")

    assert response.status_code == 401
    assert response.json() == {"detail": "Unauthorized"}
    assert identity_repository.assignment_account_ids == []


def test_create_and_list_conversations_use_server_derived_assignment(conversation_context) -> None:
    client, identity_repository, repository, _ = conversation_context

    created = client.request("POST", "/api/v1/conversations", headers=bearer())
    listed = client.request("GET", "/api/v1/conversations", headers=bearer())

    assert created.status_code == 201
    assert set(created.json()) == {"conversation"}
    assert created.json()["conversation"]["title"] == "新对话"
    assert created.json()["conversation"]["last_message"] is None
    assert listed.status_code == 200
    assert listed.json()["count"] == len(listed.json()["items"])
    assert all("assignment_id" not in item for item in listed.json()["items"])
    assert identity_repository.assignment_account_ids == [ACCOUNT_ID, ACCOUNT_ID]
    assert ("create", ASSIGNMENT_ID) in repository.calls
    assert ("list", ASSIGNMENT_ID) in repository.calls


def test_store_employee_answer_has_frontdesk_result_envelope(conversation_context) -> None:
    client, identity_repository, _, _ = conversation_context
    identity_repository.assignment = FakeAssignment(
        assignment_id=ASSIGNMENT_ID,
        organization_id=ORGANIZATION_ID,
        organization_name="测试组织",
        store_id="test-store",
        store_name="测试门店",
        role="store_employee",
    )

    response = client.request(
        "POST",
        f"/api/v1/conversations/{CONVERSATION_ID}/messages",
        headers=bearer(),
        json={
            "content": "顾客问泡脚能不能治疗失眠，我该怎么说？",
            "client_message_id": CLIENT_MESSAGE_ID,
        },
    )

    assert response.status_code == 200
    assistant = response.json()["assistant_message"]
    assert assistant["result_type"] == "frontdesk_answer"
    assert assistant["actions"] == [
        {"type": "training", "label": "练习这个说法"},
        {"type": "issue", "label": "上报现场问题"},
    ]


def test_conversation_create_rejects_browser_supplied_authority(conversation_context) -> None:
    client, _, repository, _ = conversation_context

    response = client.request(
        "POST",
        "/api/v1/conversations",
        headers=bearer(),
        json={
            "role": "founder",
            "store_id": "other-store",
            "organization_id": str(uuid4()),
            "assignment_id": FOREIGN_ASSIGNMENT_ID,
        },
    )

    assert response.status_code == 422
    assert repository.calls.count(("create", ASSIGNMENT_ID)) == 1  # fixture seed only


def test_detail_returns_consistent_message_shape(conversation_context) -> None:
    client, _, _, _ = conversation_context
    sent = client.request(
        "POST",
        f"/api/v1/conversations/{CONVERSATION_ID}/messages",
        headers=bearer(),
        json={"content": "  我该怎么接待第一次到店的顾客？  ", "client_message_id": CLIENT_MESSAGE_ID},
    )

    response = client.request(
        "GET",
        f"/api/v1/conversations/{CONVERSATION_ID}",
        headers=bearer(),
    )

    assert sent.status_code == 200
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"conversation", "messages"}
    assert body["messages"] == [sent.json()["user_message"], sent.json()["assistant_message"]]
    assert set(body["messages"][0]) == set(body["messages"][1])


def test_send_message_returns_pair_and_redacts_internal_answer_metadata(conversation_context) -> None:
    client, identity_repository, repository, generated_questions = conversation_context

    response = client.request(
        "POST",
        f"/api/v1/conversations/{CONVERSATION_ID}/messages",
        headers=bearer(),
        json={"content": "  我该怎么接待第一次到店的顾客？  ", "client_message_id": CLIENT_MESSAGE_ID},
    )

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"conversation", "user_message", "assistant_message"}
    assert body["user_message"]["content"] == "我该怎么接待第一次到店的顾客？"
    assert body["assistant_message"]["content"] == "先问顾客当下感受，再按体验需求介绍项目。"
    assert body["assistant_message"]["sources"] == [
        {
            "title": "接待话术.md",
            "excerpt": "参考 [已隐藏内部路径] 的接待原则。",
            "strength": "reference",
            "url": None,
        },
        {
            "title": "经营资料.pdf",
            "excerpt": "另见 [已隐藏内部路径] 和 [已隐藏内部路径]。",
            "strength": "candidate",
            "url": None,
        },
    ]
    serialized = response.text
    for forbidden in (
        "chunk_id",
        "/root/hxy",
        "source_path",
        "governance",
        "understanding",
        "model_route",
        "provider",
        "pipeline",
        "thinking",
        "assignment_id",
    ):
        assert forbidden not in serialized
    assert [item["question"] for item in generated_questions] == ["我该怎么接待第一次到店的顾客？"]
    assert generated_questions[0]["role"] == "store_manager"
    assert generated_questions[0]["pipeline_role"] == "store_manager"
    assert identity_repository.assignment_account_ids == [ACCOUNT_ID]
    assert ("reserve", ASSIGNMENT_ID) in repository.calls
    assert ("complete", ASSIGNMENT_ID) in repository.calls
    assert len(repository.traces) == 1
    assert repository.traces[0]["assignment_id"] == ASSIGNMENT_ID
    assert repository.traces[0]["role"] == "store_manager"
    assert "content" not in repository.traces[0]


def test_idempotent_retry_returns_same_pair_without_regenerating(conversation_context) -> None:
    client, _, _, generated_questions = conversation_context
    payload = {"content": "怎么接待顾客？", "client_message_id": CLIENT_MESSAGE_ID}

    first = client.request(
        "POST",
        f"/api/v1/conversations/{CONVERSATION_ID}/messages",
        headers=bearer(),
        json=payload,
    )
    retry = client.request(
        "POST",
        f"/api/v1/conversations/{CONVERSATION_ID}/messages",
        headers=bearer(),
        json=payload,
    )

    assert first.status_code == 200
    assert retry.status_code == 200
    assert retry.json()["user_message"] == first.json()["user_message"]
    assert retry.json()["assistant_message"] == first.json()["assistant_message"]
    assert [item["question"] for item in generated_questions] == ["怎么接待顾客？"]


def test_conversation_title_and_message_content_hide_absolute_paths(conversation_context) -> None:
    client, _, _, _ = conversation_context

    response = client.request(
        "POST",
        f"/api/v1/conversations/{CONVERSATION_ID}/messages",
        headers=bearer(),
        json={"content": "/mnt/private/plan.md 怎么用？", "client_message_id": str(uuid4())},
    )

    assert response.status_code == 200
    assert response.json()["conversation"]["title"] == "[已隐藏内部路径] 怎么用？"
    assert response.json()["user_message"]["content"] == "[已隐藏内部路径] 怎么用？"


def test_in_progress_retry_does_not_generate_a_second_answer(conversation_context) -> None:
    client, _, repository, generated_questions = conversation_context
    reservation = repository.reserve_user_message(
        ASSIGNMENT_ID,
        CONVERSATION_ID,
        CLIENT_MESSAGE_ID,
        "正在处理的问题",
    )
    assert reservation is not None

    response = client.request(
        "POST",
        f"/api/v1/conversations/{CONVERSATION_ID}/messages",
        headers=bearer(),
        json={"content": "正在处理的问题", "client_message_id": CLIENT_MESSAGE_ID},
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "Message is processing"}
    assert generated_questions == []


@pytest.mark.parametrize("conversation_id", [FOREIGN_CONVERSATION_ID, str(uuid4())])
def test_cross_assignment_and_missing_conversations_share_generic_404(
    conversation_context,
    conversation_id: str,
) -> None:
    client, _, _, generated_questions = conversation_context

    response = client.request(
        "GET",
        f"/api/v1/conversations/{conversation_id}",
        headers=bearer(),
    )
    send = client.request(
        "POST",
        f"/api/v1/conversations/{conversation_id}/messages",
        headers=bearer(),
        json={"content": "测试", "client_message_id": str(uuid4())},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}
    assert send.status_code == 404
    assert send.json() == {"detail": "Not Found"}
    assert generated_questions == []


@pytest.mark.parametrize(
    "payload",
    [
        {"content": "   ", "client_message_id": CLIENT_MESSAGE_ID},
        {"content": "x" * 4001, "client_message_id": CLIENT_MESSAGE_ID},
        {"content": "有效问题", "client_message_id": "not-a-uuid"},
        {"content": "有效问题", "client_message_id": CLIENT_MESSAGE_ID, "role": "founder"},
    ],
    ids=["blank", "too-long", "invalid-client-id", "forbidden-role"],
)
def test_send_message_validates_product_input(conversation_context, payload: dict[str, Any]) -> None:
    client, _, _, generated_questions = conversation_context

    response = client.request(
        "POST",
        f"/api/v1/conversations/{CONVERSATION_ID}/messages",
        headers=bearer(),
        json=payload,
    )

    assert response.status_code == 422
    assert generated_questions == []


def test_invalid_conversation_uuid_is_rejected_before_repository(conversation_context) -> None:
    client, _, repository, _ = conversation_context
    before = list(repository.calls)

    response = client.request("GET", "/api/v1/conversations/not-a-uuid", headers=bearer())

    assert response.status_code == 422
    assert repository.calls == before


def test_migration_defines_assignment_isolation_idempotency_and_reply_constraints() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    normalized = " ".join(sql.split())

    assert "CREATE TABLE IF NOT EXISTS hxy_product_conversations" in sql
    assert "CREATE TABLE IF NOT EXISTS hxy_product_messages" in sql
    assert "conversation_id UUID PRIMARY KEY" in normalized
    assert "message_id UUID PRIMARY KEY" in normalized
    assert "assignment_id UUID NOT NULL" in normalized
    assert "REFERENCES hxy_role_assignments(assignment_id)" in normalized
    assert "UNIQUE (assignment_id, conversation_id)" in normalized
    assert (
        "FOREIGN KEY (assignment_id, conversation_id) REFERENCES "
        "hxy_product_conversations(assignment_id, conversation_id)" in normalized
    )
    assert "CHECK (role IN ('user', 'assistant'))" in normalized
    assert "client_message_id UUID" in normalized
    assert "UNIQUE (assignment_id, client_message_id)" in normalized
    assert "UNIQUE (assignment_id, conversation_id, reply_to_message_id)" in normalized
    assert "created_at TIMESTAMPTZ NOT NULL" in normalized
    assert "updated_at TIMESTAMPTZ NOT NULL" in normalized
    assert "last_message_at TIMESTAMPTZ" in normalized
    assert "CREATE INDEX IF NOT EXISTS" in normalized
    assert "ON hxy_product_conversations (assignment_id, updated_at DESC)" in normalized
    assert "INSERT INTO" not in sql.upper()


def test_repository_sql_always_scopes_conversation_queries_by_assignment() -> None:
    module = importlib.import_module("apps.api.hxy_product.conversation_repository")
    repository = module.ConversationRepository("postgresql://conversation.test/hxy")
    captured: list[tuple[str, tuple[Any, ...]]] = []

    class Result:
        def fetchone(self):
            return None

        def fetchall(self):
            return []

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, sql: str, params: tuple[Any, ...]):
            captured.append((" ".join(sql.split()), params))
            return Result()

    repository.connect = lambda: Connection()

    repository.list_conversations(ASSIGNMENT_ID, limit=20)
    repository.get_conversation(ASSIGNMENT_ID, CONVERSATION_ID)
    repository.list_messages(ASSIGNMENT_ID, CONVERSATION_ID)

    assert len(captured) == 3
    for sql, params in captured:
        assert "assignment_id = %s::uuid" in sql
        assert params[0] == ASSIGNMENT_ID
    assert "conversation_id = %s::uuid" in captured[1][0]
    assert "conversation_id = %s::uuid" in captured[2][0]


def test_stale_processing_message_is_reclaimed_after_lease_expires() -> None:
    module = importlib.import_module("apps.api.hxy_product.conversation_repository")
    repository = module.ConversationRepository("postgresql://conversation.test/hxy")
    user_row = {
        "message_id": "80000000-0000-0000-0000-000000000001",
        "conversation_id": CONVERSATION_ID,
        "role": "user",
        "content": "同一个问题",
        "answer_id": None,
        "answer_payload": {},
        "generation_status": "processing",
        "generation_started_at": datetime(2020, 1, 1, tzinfo=timezone.utc),
        "created_at": NOW,
    }

    class Result:
        def __init__(self, row=None) -> None:
            self.row = row

        def fetchone(self):
            return self.row

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, sql: str, _params: tuple[Any, ...]):
            normalized = " ".join(sql.split())
            if "FROM hxy_product_conversations" in normalized:
                return Result({"conversation_id": CONVERSATION_ID})
            if "INSERT INTO hxy_product_messages" in normalized:
                return Result(None)
            if "client_message_id = %s::uuid" in normalized:
                return Result(user_row)
            if "reply_to_message_id = %s::uuid" in normalized:
                return Result(None)
            if "UPDATE hxy_product_messages" in normalized:
                return Result(user_row if "INTERVAL '5 minutes'" in normalized else None)
            raise AssertionError(normalized)

    repository.connect = lambda: Connection()

    reservation = repository.reserve_user_message(
        ASSIGNMENT_ID,
        CONVERSATION_ID,
        CLIENT_MESSAGE_ID,
        "同一个问题",
    )

    assert reservation is not None
    assert reservation["state"] == "reserved"


def test_generate_answer_module_has_framework_independent_service_boundary() -> None:
    module = importlib.import_module("hxy_knowledge.answer_service")

    assert callable(module.generate_answer)
    assert "fastapi" not in module.__dict__
    assert "hxy_knowledge_api" not in module.__dict__
    assert all(parameter not in module.generate_answer.__annotations__ for parameter in ("Request", "ChatRequest"))


def test_legacy_chat_delegates_to_generate_answer_without_changing_payload(tmp_path: Path, monkeypatch) -> None:
    api_module = importlib.import_module("apps.api.hxy_knowledge_api")
    monkeypatch.setenv("HXY_API_TOKEN", "test-token")
    expected = {
        "answer": "保持旧接口完整载荷",
        "answer_id": "answer-test-id",
        "understanding": {"visible_on_legacy_inspector": True},
    }
    calls: list[dict[str, Any]] = []

    def fake_generate_answer(**kwargs) -> dict[str, Any]:
        calls.append(kwargs)
        return expected

    monkeypatch.setattr(api_module.answer_service, "generate_answer", fake_generate_answer)
    app = api_module.create_app(root_dir=tmp_path, repository_factory=lambda: object())
    response = ASGIClient(app).request(
        "POST",
        "/api/knowledge/chat",
        headers={"Authorization": "Bearer test-token"},
        json={"question": "  旧接口问题  ", "scenario": "创始人内部决策", "limit": 3},
    )

    assert response.status_code == 200
    assert response.json() == expected
    assert len(calls) == 1
    assert calls[0]["question"] == "旧接口问题"
    assert calls[0]["scenario"] == "创始人内部决策"
    assert calls[0]["limit"] == 3
    assert calls[0]["role"] == "founder"
    assert calls[0]["pipeline_role"] == "team"


def test_client_message_id_is_a_uuid_in_contract() -> None:
    assert str(UUID(CLIENT_MESSAGE_ID)) == CLIENT_MESSAGE_ID


def test_product_answer_payload_normalizes_internal_enum_values() -> None:
    module = importlib.import_module("apps.api.hxy_product.conversation_routes")

    payload = module.product_answer_payload(
        {
            "answer": "正常回答",
            "answer_status": "/root/hxy/internal-status",
            "confidence": "internal-provider",
            "needs_review": False,
            "evidence": [
                {
                    "title": "公开标题",
                    "excerpt": "公开摘要",
                    "strength": "/root/hxy/internal-rank",
                }
            ],
        }
    )

    assert payload["answer_status"] == "AI 草稿"
    assert payload["confidence"] == "low"
    assert payload["sources"][0]["strength"] == "reference"
    assert "/root/hxy" not in str(payload)


def test_product_answer_payload_allows_only_authorized_material_source_urls() -> None:
    module = importlib.import_module("apps.api.hxy_product.conversation_routes")

    payload = module.product_answer_payload(
        {
            "answer": "资料摘要",
            "answer_status": "AI 草稿",
            "confidence": "medium",
            "needs_review": True,
            "evidence": [
                {
                    "title": "首店资料.md",
                    "excerpt": "先了解顾客状态。",
                    "strength": "reference",
                    "source_url": f"/api/v1/materials/{uuid4()}/content",
                },
                {
                    "title": "外部地址",
                    "excerpt": "不能透传。",
                    "strength": "reference",
                    "source_url": "https://evil.example/private",
                },
            ],
        }
    )

    assert payload["sources"][0]["url"].startswith("/api/v1/materials/")
    assert payload["sources"][1]["url"] is None


def test_product_answer_uses_only_active_assignment_private_context(
    tmp_path: Path,
    monkeypatch,
) -> None:
    api_module = importlib.import_module("apps.api.hxy_knowledge_api")
    identity_repository = FakeIdentityRepository()
    conversation_repository = FakeConversationRepository()
    material_calls: list[str] = []
    material_id = "70000000-0000-0000-0000-000000000021"

    class BaseRepository:
        def search(self, *_args, **_kwargs):
            return []

        def find_answer_card(self, *_args, **_kwargs):
            return None

        def save_answer_run(self, _payload):
            return "70000000-0000-0000-0000-000000000031"

    class MaterialRepository:
        def search_material_chunks(self, assignment_id: str, *_args, **_kwargs):
            material_calls.append(assignment_id)
            return [
                {
                    "chunk_id": "private-chunk",
                    "asset_id": material_id,
                    "material_id": material_id,
                    "title": "首店接待资料.md",
                    "source_path": f"material:{material_id}",
                    "source_url": f"/api/v1/materials/{material_id}/content",
                    "domain": "operations",
                    "stage": "working_context",
                    "status": "reference",
                    "source_type": "private_material",
                    "score": 120,
                    "content": "先询问顾客当下状态，再介绍适合的服务。",
                    "official_use_allowed": False,
                }
            ]

    def fake_generate_answer(**kwargs) -> dict[str, Any]:
        items = kwargs["repository"].search(
            kwargs["question"],
            limit=5,
            domain_hint="operations",
        )
        return {
            "answer": "资料中建议先询问顾客当下状态。",
            "answer_status": "已批准",
            "confidence": "medium",
            "needs_review": False,
            "from_answer_card": False,
            "intent": "operations",
            "evidence": items,
            "model_route": {"provider": "test", "model": "test-model"},
        }

    monkeypatch.setattr(api_module.answer_service, "generate_answer", fake_generate_answer)
    app = api_module.create_app(
        root_dir=tmp_path,
        repository_factory=BaseRepository,
        product_identity_repository_factory=lambda: identity_repository,
        conversation_repository_factory=lambda: conversation_repository,
        material_repository_factory=MaterialRepository,
    )

    response = ASGIClient(app).request(
        "POST",
        f"/api/v1/conversations/{CONVERSATION_ID}/messages",
        headers=bearer(),
        json={
            "content": "刚上传的接待资料讲了什么？",
            "client_message_id": str(uuid4()),
        },
    )

    assert response.status_code == 200
    assistant = response.json()["assistant_message"]
    assert assistant["answer_status"] == "AI 草稿"
    assert assistant["needs_review"] is True
    assert assistant["sources"] == [
        {
            "title": "首店接待资料.md",
            "excerpt": "先询问顾客当下状态，再介绍适合的服务。",
            "strength": "reference",
            "url": f"/api/v1/materials/{material_id}/content",
        }
    ]
    assert material_calls == [ASSIGNMENT_ID]
    assert conversation_repository.traces[0]["private_material_count"] == 1
