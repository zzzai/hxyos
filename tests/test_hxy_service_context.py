from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx

from apps.api.hxy_knowledge_api import create_app
from hxy_product.service_repository import (
    ServiceIdempotencyConflict,
    external_reference_digest,
    service_request_fingerprint,
)


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "data" / "migrations" / "024_hxy_service_context.sql"
FEEDBACK_MIGRATION = (
    ROOT / "data" / "migrations" / "025_hxy_service_feedback_optional_text.sql"
)
ACCOUNT_ID = "11000000-0000-0000-0000-000000000001"
ASSIGNMENT_ID = "22000000-0000-0000-0000-000000000001"
ORGANIZATION_ID = "33000000-0000-0000-0000-000000000001"
STORE_ID = "store-one"
CONTEXT_ID = "66000000-0000-0000-0000-000000000001"
FEEDBACK_ID = "77000000-0000-0000-0000-000000000001"
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


def context_row(*, status: str = "provisional") -> dict[str, Any]:
    return {
        "id": CONTEXT_ID,
        "organization_id": ORGANIZATION_ID,
        "store_id": STORE_ID,
        "created_by_assignment_id": ASSIGNMENT_ID,
        "status": status,
        "occurred_at": NOW,
        "service_label": "足部舒缓服务",
        "original_identity_hint": {"phone_suffix": "1234", "alias": "王女士"},
        "feedback_count": 0,
        "created_at": NOW,
        "request_fingerprint": "must-not-leak",
        "customer_subject_id": "must-not-leak",
        "external_customer_ref_hash": "must-not-leak",
    }


class FakeServiceRepository:
    def __init__(self) -> None:
        self.create_calls: list[dict[str, Any]] = []
        self.list_calls: list[dict[str, Any]] = []
        self.feedback_calls: list[dict[str, Any]] = []
        self.reconcile_calls: list[dict[str, Any]] = []
        self.create_error: Exception | None = None

    def create_context(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.create_calls.append(dict(payload))
        if self.create_error is not None:
            raise self.create_error
        return context_row()

    def list_recent_contexts(self, **kwargs: Any) -> list[dict[str, Any]]:
        self.list_calls.append(dict(kwargs))
        return [context_row()]

    def add_feedback(self, payload: dict[str, Any], **scope: Any) -> dict[str, Any]:
        self.feedback_calls.append({"payload": dict(payload), **scope})
        return {
            "feedback": {
                "id": FEEDBACK_ID,
                "context_id": CONTEXT_ID,
                "status": "received",
                "created_at": NOW,
            },
            "context": {**context_row(), "feedback_count": 1},
        }

    def reconcile_context(self, payload: dict[str, Any], **scope: Any) -> dict[str, Any]:
        self.reconcile_calls.append({"payload": dict(payload), **scope})
        return context_row(status="reconciled")


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


def bearer() -> dict[str, str]:
    return {"Authorization": "Bearer valid-session"}


def build_client(
    *, role: str = "store_employee", identity_key: str = "test-identity-key"
) -> tuple[Client, FakeServiceRepository]:
    identity = FakeIdentityRepository(role)
    repository = FakeServiceRepository()
    app = create_app(
        root_dir=ROOT,
        product_identity_repository_factory=lambda: identity,
        service_repository_factory=lambda: repository,
        service_identity_hmac_key=identity_key,
    )
    return Client(app), repository


def test_create_service_context_uses_authenticated_scope_and_masks_identity() -> None:
    client, repository = build_client()
    client_context_id = str(uuid4())

    response = client.request(
        "POST",
        "/api/v1/service-contexts",
        headers=bearer(),
        json={
            "client_context_id": client_context_id,
            "occurred_at": NOW.isoformat(),
            "service_label": "足部舒缓服务",
            "customer_hint": {"phone_suffix": "1234", "alias": "王女士"},
        },
    )

    assert response.status_code == 201
    assert response.json() == {
        "context": {
            "id": CONTEXT_ID,
            "status": "provisional",
            "occurred_at": NOW.isoformat().replace("+00:00", "Z"),
            "service_label": "足部舒缓服务",
            "customer_display": "王女士 · 尾号 1234",
            "feedback_count": 0,
            "created_at": NOW.isoformat().replace("+00:00", "Z"),
        }
    }
    assert repository.create_calls == [
        {
            "organization_id": ORGANIZATION_ID,
            "store_id": STORE_ID,
            "created_by_assignment_id": ASSIGNMENT_ID,
            "client_context_id": client_context_id,
            "occurred_at": NOW,
            "service_label": "足部舒缓服务",
            "original_identity_hint": {"phone_suffix": "1234", "alias": "王女士"},
        }
    ]
    assert "request_fingerprint" not in response.text
    assert "customer_subject_id" not in response.text


def test_phone_suffix_is_only_an_ambiguous_hint_and_plain_phone_is_rejected() -> None:
    client, repository = build_client()

    response = client.request(
        "POST",
        "/api/v1/service-contexts",
        headers=bearer(),
        json={
            "client_context_id": str(uuid4()),
            "occurred_at": NOW.isoformat(),
            "service_label": "足部舒缓服务",
            "customer_hint": {"phone_suffix": "13800138000"},
        },
    )

    assert response.status_code == 422
    assert repository.create_calls == []
    assert "ambiguous" not in response.text.lower()


def test_service_text_rejects_plain_mainland_mobile_numbers() -> None:
    client, repository = build_client()

    response = client.request(
        "POST",
        "/api/v1/service-contexts",
        headers=bearer(),
        json={
            "client_context_id": str(uuid4()),
            "occurred_at": NOW.isoformat(),
            "service_label": "联系顾客 13800138000",
            "customer_hint": {},
        },
    )

    assert response.status_code == 422
    assert repository.create_calls == []


def test_recent_contexts_are_assignment_scoped_for_employee() -> None:
    client, repository = build_client()

    response = client.request(
        "GET",
        "/api/v1/service-contexts/recent?limit=5",
        headers=bearer(),
    )

    assert response.status_code == 200
    assert len(response.json()["contexts"]) == 1
    assert repository.list_calls == [
        {
            "organization_id": ORGANIZATION_ID,
            "store_id": STORE_ID,
            "assignment_id": ASSIGNMENT_ID,
            "role": "store_employee",
            "limit": 5,
        }
    ]


def test_browser_cannot_override_service_scope() -> None:
    client, repository = build_client()

    response = client.request(
        "POST",
        "/api/v1/service-contexts",
        headers=bearer(),
        json={
            "client_context_id": str(uuid4()),
            "occurred_at": NOW.isoformat(),
            "service_label": "足部舒缓服务",
            "customer_hint": {},
            "organization_id": "another-organization",
            "store_id": "another-store",
            "assignment_id": "another-assignment",
        },
    )

    assert response.status_code == 422
    assert repository.create_calls == []


def test_idempotency_conflict_is_public_http_409() -> None:
    client, repository = build_client()
    repository.create_error = ServiceIdempotencyConflict()

    response = client.request(
        "POST",
        "/api/v1/service-contexts",
        headers=bearer(),
        json={
            "client_context_id": str(uuid4()),
            "occurred_at": NOW.isoformat(),
            "service_label": "足部舒缓服务",
            "customer_hint": {},
        },
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "Idempotency key conflict"}


def test_feedback_is_linked_without_exposing_or_accepting_identity_scope() -> None:
    client, repository = build_client()
    client_feedback_id = str(uuid4())

    response = client.request(
        "POST",
        f"/api/v1/service-contexts/{CONTEXT_ID}/feedback",
        headers=bearer(),
        json={
            "client_feedback_id": client_feedback_id,
            "text": "顾客反馈力度合适，肩颈仍有些紧。",
            "source_asset_ids": [],
        },
    )

    assert response.status_code == 201
    assert response.json()["feedback"]["status"] == "received"
    assert response.json()["context"]["feedback_count"] == 1
    assert repository.feedback_calls[0] == {
        "payload": {
            "organization_id": ORGANIZATION_ID,
            "store_id": STORE_ID,
            "created_by_assignment_id": ASSIGNMENT_ID,
            "context_id": CONTEXT_ID,
            "client_feedback_id": client_feedback_id,
            "text": "顾客反馈力度合适，肩颈仍有些紧。",
            "source_asset_ids": [],
        },
        "assignment_id": ASSIGNMENT_ID,
        "role": "store_employee",
    }


def test_voice_only_feedback_is_accepted_as_a_protected_asset() -> None:
    client, repository = build_client()
    client_feedback_id = str(uuid4())
    source_asset_id = str(uuid4())

    response = client.request(
        "POST",
        f"/api/v1/service-contexts/{CONTEXT_ID}/feedback",
        headers=bearer(),
        json={
            "client_feedback_id": client_feedback_id,
            "text": "",
            "source_asset_ids": [source_asset_id],
        },
    )

    assert response.status_code == 201
    assert repository.feedback_calls[0]["payload"]["text"] == ""
    assert repository.feedback_calls[0]["payload"]["source_asset_ids"] == [
        source_asset_id
    ]


def test_feedback_requires_text_or_a_protected_asset() -> None:
    client, repository = build_client()

    response = client.request(
        "POST",
        f"/api/v1/service-contexts/{CONTEXT_ID}/feedback",
        headers=bearer(),
        json={
            "client_feedback_id": str(uuid4()),
            "text": "",
            "source_asset_ids": [],
        },
    )

    assert response.status_code == 422
    assert repository.feedback_calls == []


def test_manager_reconciliation_hashes_external_refs_before_repository() -> None:
    client, repository = build_client(role="store_manager")

    response = client.request(
        "POST",
        f"/api/v1/service-contexts/{CONTEXT_ID}/reconcile",
        headers=bearer(),
        json={
            "source_system": "future-pos",
            "external_customer_ref": "customer-13800138000",
            "external_service_ref": "service-order-001",
        },
    )

    assert response.status_code == 200
    assert response.json()["context"]["status"] == "reconciled"
    call = repository.reconcile_calls[0]
    assert call["assignment_id"] == ASSIGNMENT_ID
    assert call["role"] == "store_manager"
    assert call["payload"]["source_system"] == "future-pos"
    assert call["payload"]["external_customer_ref_hash"] == external_reference_digest(
        "test-identity-key", "future-pos", "customer", "customer-13800138000"
    )
    assert call["payload"]["external_service_ref_hash"] == external_reference_digest(
        "test-identity-key", "future-pos", "service", "service-order-001"
    )
    assert "external_customer_ref" not in call["payload"]
    assert "external_service_ref" not in call["payload"]
    assert "13800138000" not in response.text


def test_employee_cannot_reconcile_customer_identity() -> None:
    client, repository = build_client(role="store_employee")

    response = client.request(
        "POST",
        f"/api/v1/service-contexts/{CONTEXT_ID}/reconcile",
        headers=bearer(),
        json={
            "source_system": "future-pos",
            "external_customer_ref": "customer-001",
        },
    )

    assert response.status_code == 403
    assert repository.reconcile_calls == []


def test_repository_fingerprints_are_stable_and_external_refs_are_keyed() -> None:
    payload = {
        "organization_id": ORGANIZATION_ID,
        "store_id": STORE_ID,
        "created_by_assignment_id": ASSIGNMENT_ID,
        "client_context_id": str(uuid4()),
        "occurred_at": NOW,
        "service_label": "足部舒缓服务",
        "original_identity_hint": {"alias": "王女士", "phone_suffix": "1234"},
    }

    assert service_request_fingerprint(payload) == service_request_fingerprint(
        {**payload, "original_identity_hint": {"phone_suffix": "1234", "alias": "王女士"}}
    )
    assert external_reference_digest("key-a", "pos", "customer", "1234") != (
        external_reference_digest("key-b", "pos", "customer", "1234")
    )
    assert "1234" not in external_reference_digest("key-a", "pos", "customer", "1234")


def test_migration_defines_reconcilable_contexts_and_immutable_identity_hints() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")

    for table in (
        "hxy_customer_subjects",
        "hxy_service_contexts",
        "hxy_service_feedback",
        "hxy_service_feedback_assets",
        "hxy_external_identity_mappings",
        "hxy_service_context_reconciliations",
    ):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in sql
    assert "client_context_id" in sql
    assert "request_fingerprint" in sql
    assert "original_identity_hint" in sql
    assert "prevent_hxy_service_identity_hint_update" in sql
    assert "external_identifier_hash" in sql
    assert "external_identifier" not in sql.replace("external_identifier_hash", "")
    assert "phone" not in sql.lower()
    assert "/root/htops" not in sql


def test_followup_migration_allows_asset_only_feedback_text() -> None:
    sql = FEEDBACK_MIGRATION.read_text(encoding="utf-8")

    assert "ALTER TABLE hxy_service_feedback" in sql
    assert "char_length(btrim(feedback_text)) BETWEEN 0 AND 4000" in sql
    assert "/root/htops" not in sql
