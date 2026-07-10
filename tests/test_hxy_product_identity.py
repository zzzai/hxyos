from __future__ import annotations

import asyncio
import hashlib
import inspect
from dataclasses import dataclass
from pathlib import Path

import httpx
import pytest

from apps.api.hxy_knowledge_api import create_app


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "data" / "migrations" / "009_hxy_product_identity.sql"


@dataclass(frozen=True)
class FakePrincipal:
    account_id: str
    display_name: str


@dataclass(frozen=True)
class FakeAssignment:
    assignment_id: str
    organization_id: str
    organization_name: str
    store_id: str | None
    store_name: str | None
    role: str


EMPLOYEE_ID = "10000000-0000-0000-0000-000000000001"
FOUNDER_ID = "10000000-0000-0000-0000-000000000002"
EMPLOYEE_ASSIGNMENT_ID = "20000000-0000-0000-0000-000000000001"
FOUNDER_ASSIGNMENT_ID = "20000000-0000-0000-0000-000000000002"
FOUNDER_OPERATIONS_ASSIGNMENT_ID = "20000000-0000-0000-0000-000000000003"
FOREIGN_ASSIGNMENT_ID = "20000000-0000-0000-0000-000000000099"
ORGANIZATION_ID = "30000000-0000-0000-0000-000000000001"


class FakeIdentityRepository:
    def __init__(self) -> None:
        self.resolver_tokens: list[str] = []
        self.assignment_account_ids: list[str] = []
        self.principals = {
            "employee-session": FakePrincipal(EMPLOYEE_ID, "测试店员"),
            "founder-session": FakePrincipal(FOUNDER_ID, "测试创始人"),
        }
        self.assignments = {
            EMPLOYEE_ID: [
                FakeAssignment(
                    EMPLOYEE_ASSIGNMENT_ID,
                    ORGANIZATION_ID,
                    "测试组织",
                    "test-store",
                    "测试门店",
                    "store_employee",
                )
            ],
            FOUNDER_ID: [
                FakeAssignment(
                    FOUNDER_ASSIGNMENT_ID,
                    ORGANIZATION_ID,
                    "测试组织",
                    None,
                    None,
                    "founder",
                ),
                FakeAssignment(
                    FOUNDER_OPERATIONS_ASSIGNMENT_ID,
                    ORGANIZATION_ID,
                    "测试组织",
                    None,
                    None,
                    "hq_operations",
                ),
            ],
        }

    def resolve_session(self, raw_token: str) -> FakePrincipal | None:
        self.resolver_tokens.append(raw_token)
        return self.principals.get(raw_token)

    def list_assignments(self, account_id: str) -> list[FakeAssignment]:
        self.assignment_account_ids.append(account_id)
        return list(self.assignments.get(account_id, []))


class ASGIClient:
    """Identity tests must never inherit the legacy client's auth header."""

    def __init__(self, app) -> None:
        self.app = app

    def request(self, method: str, url: str, **kwargs):
        async def run():
            transport = httpx.ASGITransport(app=self.app)
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://testserver",
            ) as client:
                return await client.request(method, url, **kwargs)

        return asyncio.run(run())

    def get(self, url: str, **kwargs):
        return self.request("GET", url, **kwargs)


@pytest.fixture
def identity_client(tmp_path: Path):
    repository = FakeIdentityRepository()
    factory_calls: list[None] = []

    def factory() -> FakeIdentityRepository:
        factory_calls.append(None)
        return repository

    app = create_app(
        root_dir=tmp_path,
        product_identity_repository_factory=factory,
    )
    return ASGIClient(app), repository, factory_calls


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def session_cookie(token: str) -> dict[str, str]:
    return {"Cookie": f"hxy_session={token}"}


def test_employee_session_returns_only_its_assignment_and_capabilities(identity_client) -> None:
    client, repository, factory_calls = identity_client

    response = client.get("/api/v1/me", headers=bearer("employee-session"))

    assert response.status_code == 200
    assert response.json() == {
        "user": {"account_id": EMPLOYEE_ID, "display_name": "测试店员"},
        "active_assignment": {
            "assignment_id": EMPLOYEE_ASSIGNMENT_ID,
            "organization": {"id": ORGANIZATION_ID, "name": "测试组织"},
            "store": {"id": "test-store", "name": "测试门店"},
            "role": "store_employee",
            "role_label": "门店员工",
            "capabilities": [
                "conversation:use",
                "issues:create",
                "store:read",
                "tasks:read",
                "training:practice",
            ],
        },
        "available_assignments": [
            {
                "assignment_id": EMPLOYEE_ASSIGNMENT_ID,
                "organization": {"id": ORGANIZATION_ID, "name": "测试组织"},
                "store": {"id": "test-store", "name": "测试门店"},
                "role": "store_employee",
                "role_label": "门店员工",
                "capabilities": [
                    "conversation:use",
                    "issues:create",
                    "store:read",
                    "tasks:read",
                    "training:practice",
                ],
            }
        ],
    }
    assert factory_calls == [None]
    assert repository.resolver_tokens == ["employee-session"]
    assert repository.assignment_account_ids == [EMPLOYEE_ID]


def test_founder_session_returns_founder_assignment(identity_client) -> None:
    client, _, _ = identity_client

    response = client.get("/api/v1/me", headers=bearer("founder-session"))

    assert response.status_code == 200
    body = response.json()
    assert body["active_assignment"]["assignment_id"] == FOUNDER_ASSIGNMENT_ID
    assert body["active_assignment"]["role"] == "founder"
    assert body["active_assignment"]["role_label"] == "创始人"
    assert body["active_assignment"]["store"] is None
    assert {item["assignment_id"] for item in body["available_assignments"]} == {
        FOUNDER_ASSIGNMENT_ID,
        FOUNDER_OPERATIONS_ASSIGNMENT_ID,
    }


def test_http_only_session_cookie_authenticates(identity_client) -> None:
    client, repository, _ = identity_client

    response = client.get(
        "/api/v1/me",
        headers=session_cookie("employee-session"),
    )

    assert response.status_code == 200
    assert response.json()["active_assignment"]["role"] == "store_employee"
    assert repository.resolver_tokens == ["employee-session"]
    assert repository.assignment_account_ids == [EMPLOYEE_ID]


def test_valid_authorization_header_takes_precedence_over_cookie(identity_client) -> None:
    client, repository, _ = identity_client

    response = client.get(
        "/api/v1/me",
        headers={
            **bearer("founder-session"),
            **session_cookie("employee-session"),
        },
    )

    assert response.status_code == 200
    assert response.json()["active_assignment"]["role"] == "founder"
    assert repository.resolver_tokens == ["founder-session"]


def test_malformed_authorization_does_not_fall_back_to_valid_cookie(identity_client) -> None:
    client, repository, _ = identity_client

    response = client.get(
        "/api/v1/me",
        headers={
            "Authorization": "Basic invalid-session",
            **session_cookie("employee-session"),
        },
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Unauthorized"}
    assert repository.resolver_tokens == []
    assert repository.assignment_account_ids == []


def test_invalid_authorization_does_not_fall_back_to_valid_cookie(identity_client) -> None:
    client, repository, _ = identity_client

    response = client.get(
        "/api/v1/me",
        headers={
            **bearer("invalid-session"),
            **session_cookie("employee-session"),
        },
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Unauthorized"}
    assert repository.resolver_tokens == ["invalid-session"]
    assert repository.assignment_account_ids == []


def test_owned_assignment_can_be_selected_as_active(identity_client) -> None:
    client, _, _ = identity_client

    response = client.get(
        f"/api/v1/me?assignment_id={FOUNDER_OPERATIONS_ASSIGNMENT_ID}",
        headers=bearer("founder-session"),
    )

    assert response.status_code == 200
    assert response.json()["active_assignment"]["role"] == "hq_operations"


def test_foreign_assignment_returns_generic_forbidden(identity_client) -> None:
    client, _, _ = identity_client

    response = client.get(
        f"/api/v1/me?assignment_id={FOREIGN_ASSIGNMENT_ID}",
        headers=bearer("employee-session"),
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "Forbidden"}


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Basic employee-session"},
        {"Authorization": "Bearer"},
        {"Authorization": "Bearer employee-session extra"},
        bearer("invalid-session"),
    ],
)
def test_missing_malformed_and_invalid_sessions_return_generic_unauthorized(
    identity_client,
    headers: dict[str, str],
) -> None:
    client, _, _ = identity_client

    response = client.get("/api/v1/me", headers=headers)

    assert response.status_code == 401
    assert response.json() == {"detail": "Unauthorized"}


def test_browser_supplied_role_or_store_cannot_elevate_permissions(identity_client) -> None:
    client, _, _ = identity_client

    response = client.request(
        "GET",
        "/api/v1/me?role=founder&store_id=another-store",
        headers=bearer("employee-session"),
        json={"role": "system_admin", "store_id": "another-store"},
    )

    assert response.status_code == 200
    assignment = response.json()["active_assignment"]
    assert assignment["role"] == "store_employee"
    assert "system:admin" not in assignment["capabilities"]


def test_invalid_session_never_reaches_assignment_lookup(identity_client) -> None:
    client, repository, _ = identity_client

    response = client.get("/api/v1/me", headers=bearer("invalid-session"))

    assert response.status_code == 401
    assert repository.resolver_tokens == ["invalid-session"]
    assert repository.assignment_account_ids == []


def test_existing_create_app_callers_remain_compatible(tmp_path: Path) -> None:
    assert "product_identity_repository_factory" in inspect.signature(create_app).parameters

    app = create_app(root_dir=tmp_path)
    response = ASGIClient(app).get("/health")

    assert response.status_code == 200


def test_migration_defines_identity_ownership_without_business_seed_data() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    normalized = " ".join(sql.split())

    assert "CREATE TABLE IF NOT EXISTS hxy_organizations" in sql
    assert "CREATE TABLE IF NOT EXISTS hxy_role_assignments" in sql
    assert "REFERENCES staff_accounts(id)" in normalized
    assert "REFERENCES hxy_organizations(organization_id)" in normalized
    assert "REFERENCES stores(store_id)" in normalized
    assert all(
        f"'{role}'" in sql
        for role in (
            "founder",
            "hq_operations",
            "store_manager",
            "store_employee",
            "system_admin",
        )
    )
    assert "CHECK (role IN" in normalized
    assert "CREATE UNIQUE INDEX IF NOT EXISTS" in normalized
    assert "CREATE INDEX IF NOT EXISTS" in normalized
    assert "INSERT INTO" not in sql.upper()


class FakeQueryResult:
    def __init__(self, row=None, rows=None) -> None:
        self.row = row
        self.rows = rows or []

    def fetchone(self):
        return self.row

    def fetchall(self):
        return self.rows


class FakeConnection:
    def __init__(self, results: list[FakeQueryResult]) -> None:
        self.results = results
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def execute(self, sql: str, params: tuple[object, ...]):
        self.calls.append((sql, params))
        return self.results.pop(0)


def test_postgres_repository_hashes_raw_token_and_requires_active_identity(monkeypatch) -> None:
    from apps.api.hxy_product.repository import IdentityRepository

    connection = FakeConnection(
        [
            FakeQueryResult(
                row={"account_id": EMPLOYEE_ID, "display_name": "测试店员"},
            )
        ]
    )
    repository = IdentityRepository("postgresql://identity.test/hxy")
    monkeypatch.setattr(repository, "connect", lambda: connection)

    principal = repository.resolve_session("raw-session-token")

    assert principal is not None
    assert principal.account_id == EMPLOYEE_ID
    sql, params = connection.calls[0]
    assert "staff_sessions" in sql
    assert "staff_accounts" in sql
    assert "expires_at > NOW()" in sql
    assert "status = 'active'" in sql
    assert params == (
        hashlib.sha256(b"raw-session-token").hexdigest(),
    )
    assert "raw-session-token" not in sql


def test_postgres_repository_loads_only_principal_assignments(monkeypatch) -> None:
    from apps.api.hxy_product.repository import IdentityRepository

    connection = FakeConnection(
        [
            FakeQueryResult(
                rows=[
                    {
                        "assignment_id": EMPLOYEE_ASSIGNMENT_ID,
                        "organization_id": ORGANIZATION_ID,
                        "organization_name": "测试组织",
                        "store_id": "test-store",
                        "store_name": "测试门店",
                        "role": "store_employee",
                    }
                ]
            )
        ]
    )
    repository = IdentityRepository("postgresql://identity.test/hxy")
    monkeypatch.setattr(repository, "connect", lambda: connection)

    assignments = repository.list_assignments(EMPLOYEE_ID)

    assert [assignment.assignment_id for assignment in assignments] == [
        EMPLOYEE_ASSIGNMENT_ID
    ]
    sql, params = connection.calls[0]
    assert "ra.account_id = %s::uuid" in sql
    assert "ra.status = 'active'" in sql
    assert "organization.status = 'active'" in sql
    assert params == (EMPLOYEE_ID,)


def test_production_identity_code_contains_no_fixture_token_backdoor() -> None:
    package = ROOT / "apps" / "api" / "hxy_product"
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in package.glob("*.py")
    )

    assert "employee-session" not in source
    assert "founder-session" not in source
    assert "fixture mode" not in source.lower()
