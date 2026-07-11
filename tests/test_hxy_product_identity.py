from __future__ import annotations

import asyncio
import hashlib
import hmac
import inspect
import time
from dataclasses import dataclass
from pathlib import Path

import httpx
import pytest
from psycopg.errors import UniqueViolation

from apps.api.hxy_knowledge_api import create_app


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "data" / "migrations" / "009_hxy_product_identity.sql"
SESSION_MIGRATION = ROOT / "data" / "migrations" / "012_hxy_assignment_sessions.sql"


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


EMPLOYEE_ID = "10000000-0000-0000-0000-000000000001"
FOUNDER_ID = "10000000-0000-0000-0000-000000000002"
EMPLOYEE_ASSIGNMENT_ID = "20000000-0000-0000-0000-000000000001"
FOUNDER_ASSIGNMENT_ID = "20000000-0000-0000-0000-000000000002"
FOUNDER_OPERATIONS_ASSIGNMENT_ID = "20000000-0000-0000-0000-000000000003"
FOREIGN_ASSIGNMENT_ID = "20000000-0000-0000-0000-000000000099"
ORGANIZATION_ID = "30000000-0000-0000-0000-000000000001"
UNKNOWN_ACCOUNT_ID = "10000000-0000-0000-0000-000000000099"
GATEWAY_ASSERTION_ID = "40000000-0000-0000-0000-000000000001"
TAMPERED_ASSERTION_ID = "40000000-0000-0000-0000-000000000002"
GATEWAY_SECRET = "gateway-unit-test-key-with-32-bytes"
SESSION_GRANT = "g" * 64


@dataclass(frozen=True)
class FakeProductAuthSettings:
    gateway_secret: str
    assertion_max_age_seconds: int = 60
    session_ttl_seconds: int = 1800
    secure_cookie: bool = True


class FakeIdentityRepository:
    def __init__(self) -> None:
        self.resolver_tokens: list[str] = []
        self.assignment_account_ids: list[str] = []
        self.active_account_ids: list[str] = []
        self.created_sessions: list[tuple[str, str, int]] = []
        self.deleted_sessions: list[str] = []
        self.consumed_assertion_ids: set[str] = set()
        self.session_grants = {
            SESSION_GRANT: FakePrincipal(
                FOUNDER_ID,
                "测试创始人",
                FOUNDER_ASSIGNMENT_ID,
            )
        }
        self.exchanged_session_grants: list[tuple[str, str, int]] = []
        self.principals = {
            "employee-session": FakePrincipal(
                EMPLOYEE_ID,
                "测试店员",
                EMPLOYEE_ASSIGNMENT_ID,
            ),
            "founder-session": FakePrincipal(
                FOUNDER_ID,
                "测试创始人",
                FOUNDER_ASSIGNMENT_ID,
            ),
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
        self.principals_by_account = {
            principal.account_id: principal for principal in self.principals.values()
        }

    def resolve_session(self, raw_token: str) -> FakePrincipal | None:
        self.resolver_tokens.append(raw_token)
        return self.principals.get(raw_token)

    def list_assignments(self, account_id: str) -> list[FakeAssignment]:
        self.assignment_account_ids.append(account_id)
        return list(self.assignments.get(account_id, []))

    def find_active_principal(self, account_id: str) -> FakePrincipal | None:
        self.active_account_ids.append(account_id)
        return self.principals_by_account.get(account_id)

    def exchange_gateway_assertion(
        self,
        account_id: str,
        assertion_id: str,
        assertion_expires_at: int,
        raw_token: str,
        ttl_seconds: int,
    ) -> FakePrincipal | None:
        del assertion_expires_at
        self.active_account_ids.append(account_id)
        if assertion_id in self.consumed_assertion_ids:
            return None
        principal = self.principals_by_account.get(account_id)
        if principal is None:
            return None
        self.consumed_assertion_ids.add(assertion_id)
        self.created_sessions.append((account_id, raw_token, ttl_seconds))
        self.principals[raw_token] = principal
        return principal

    def delete_session(self, raw_token: str) -> None:
        self.deleted_sessions.append(raw_token)
        self.principals.pop(raw_token, None)

    def exchange_session_grant(
        self,
        session_grant: str,
        raw_token: str,
        ttl_seconds: int,
    ) -> FakePrincipal | None:
        principal = self.session_grants.pop(session_grant, None)
        if principal is None:
            return None
        self.exchanged_session_grants.append((session_grant, raw_token, ttl_seconds))
        self.principals[raw_token] = principal
        return principal


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


@pytest.fixture
def auth_session_client(tmp_path: Path):
    repository = FakeIdentityRepository()
    settings = FakeProductAuthSettings(gateway_secret=GATEWAY_SECRET)
    app = create_app(
        root_dir=tmp_path,
        product_identity_repository_factory=lambda: repository,
        product_auth_settings=settings,
    )
    return ASGIClient(app), repository, settings


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def session_cookie(token: str) -> dict[str, str]:
    return {"Cookie": f"hxy_session={token}"}


def gateway_assertion(
    account_id: str,
    timestamp: int,
    assertion_id: str = GATEWAY_ASSERTION_ID,
    secret: str = GATEWAY_SECRET,
) -> dict[str, object]:
    message = f"{account_id}:{timestamp}:{assertion_id}".encode("utf-8")
    signature = hmac.new(
        secret.encode("utf-8"),
        message,
        hashlib.sha256,
    ).hexdigest()
    return {
        "account_id": account_id,
        "timestamp": timestamp,
        "assertion_id": assertion_id,
        "signature": signature,
    }


def test_trusted_gateway_exchange_issues_secure_http_only_cookie(auth_session_client) -> None:
    client, repository, settings = auth_session_client
    assertion = gateway_assertion(EMPLOYEE_ID, int(time.time()))

    response = client.request("POST", "/api/v1/auth/session", json=assertion)

    assert response.status_code == 200
    assert response.json() == {"status": "authenticated"}
    cookie = response.headers["set-cookie"]
    cookie_lower = cookie.lower()
    assert cookie.startswith("hxy_session=")
    assert "httponly" in cookie_lower
    assert "secure" in cookie_lower
    assert "samesite=lax" in cookie_lower
    assert "path=/api/v1" in cookie_lower
    assert f"max-age={settings.session_ttl_seconds}" in cookie_lower
    account_id, raw_token, ttl_seconds = repository.created_sessions[0]
    assert account_id == EMPLOYEE_ID
    assert ttl_seconds == settings.session_ttl_seconds
    assert raw_token not in response.text
    assert "token" not in response.json()


def test_one_time_session_grant_rotates_into_secure_http_only_cookie(
    auth_session_client,
) -> None:
    client, repository, settings = auth_session_client

    response = client.request(
        "POST",
        "/api/v1/auth/session-grant",
        json={"grant": SESSION_GRANT},
    )

    assert response.status_code == 200
    assert response.json() == {"status": "authenticated"}
    assert SESSION_GRANT not in response.text
    assert "token" not in response.json()
    cookie = response.headers["set-cookie"]
    cookie_lower = cookie.lower()
    assert cookie.startswith("hxy_session=")
    assert SESSION_GRANT not in cookie
    assert "httponly" in cookie_lower
    assert "secure" in cookie_lower
    assert "samesite=lax" in cookie_lower
    assert "path=/api/v1" in cookie_lower
    assert f"max-age={settings.session_ttl_seconds}" in cookie_lower
    old_grant, new_token, ttl = repository.exchanged_session_grants[0]
    assert old_grant == SESSION_GRANT
    assert new_token != SESSION_GRANT
    assert len(new_token) >= 43
    assert ttl == settings.session_ttl_seconds


def test_one_time_session_grant_rejects_reuse_and_unknown_grants(
    auth_session_client,
) -> None:
    client, repository, _settings = auth_session_client

    first = client.request(
        "POST",
        "/api/v1/auth/session-grant",
        json={"grant": SESSION_GRANT},
    )
    replay = client.request(
        "POST",
        "/api/v1/auth/session-grant",
        json={"grant": SESSION_GRANT},
    )
    unknown = client.request(
        "POST",
        "/api/v1/auth/session-grant",
        json={"grant": "u" * 64},
    )

    assert first.status_code == 200
    for response in (replay, unknown):
        assert response.status_code == 401
        assert response.json() == {"detail": "Unauthorized"}
        assert "set-cookie" not in response.headers
    assert len(repository.exchanged_session_grants) == 1


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"grant": "short"},
        {"grant": "x" * 257},
        {"grant": SESSION_GRANT, "role": "founder"},
    ],
)
def test_one_time_session_grant_requires_exact_bounded_body(
    auth_session_client,
    payload: dict[str, object],
) -> None:
    client, repository, _settings = auth_session_client

    response = client.request("POST", "/api/v1/auth/session-grant", json=payload)

    assert response.status_code == 422
    assert repository.exchanged_session_grants == []


def test_trusted_gateway_exchange_rejects_replayed_assertion(auth_session_client) -> None:
    client, repository, _ = auth_session_client
    assertion = gateway_assertion(EMPLOYEE_ID, int(time.time()))

    first = client.request("POST", "/api/v1/auth/session", json=assertion)
    replay = client.request("POST", "/api/v1/auth/session", json=assertion)

    assert first.status_code == 200
    assert replay.status_code == 401
    assert replay.json() == {"detail": "Unauthorized"}
    assert "set-cookie" not in replay.headers
    assert len(repository.created_sessions) == 1


def test_trusted_gateway_exchange_rejects_tampered_assertion_id(auth_session_client) -> None:
    client, repository, _ = auth_session_client
    assertion = gateway_assertion(EMPLOYEE_ID, int(time.time()))
    assertion["assertion_id"] = TAMPERED_ASSERTION_ID

    response = client.request("POST", "/api/v1/auth/session", json=assertion)

    assert response.status_code == 401
    assert response.json() == {"detail": "Unauthorized"}
    assert "set-cookie" not in response.headers
    assert repository.created_sessions == []


def test_trusted_gateway_exchange_allows_injected_insecure_dev_cookie(tmp_path: Path) -> None:
    repository = FakeIdentityRepository()
    settings = FakeProductAuthSettings(
        gateway_secret=GATEWAY_SECRET,
        secure_cookie=False,
    )
    app = create_app(
        root_dir=tmp_path,
        product_identity_repository_factory=lambda: repository,
        product_auth_settings=settings,
    )

    response = ASGIClient(app).request(
        "POST",
        "/api/v1/auth/session",
        json=gateway_assertion(EMPLOYEE_ID, int(time.time())),
    )

    assert response.status_code == 200
    assert "secure" not in response.headers["set-cookie"].lower()


@pytest.mark.parametrize(
    "payload",
    [
        {
            "account_id": EMPLOYEE_ID,
            "timestamp": int(time.time()),
            "assertion_id": GATEWAY_ASSERTION_ID,
            "signature": "0" * 64,
        },
        gateway_assertion(EMPLOYEE_ID, int(time.time()) - 61),
        gateway_assertion("not-a-uuid", int(time.time())),
        gateway_assertion(UNKNOWN_ACCOUNT_ID, int(time.time())),
    ],
    ids=["invalid-signature", "stale", "bad-account", "inactive-account"],
)
def test_trusted_gateway_exchange_rejects_invalid_assertions_generically(
    auth_session_client,
    payload: dict[str, object],
) -> None:
    client, repository, _ = auth_session_client

    response = client.request("POST", "/api/v1/auth/session", json=payload)

    assert response.status_code == 401
    assert response.json() == {"detail": "Unauthorized"}
    assert "set-cookie" not in response.headers
    assert repository.created_sessions == []


@pytest.mark.parametrize(
    "weak_secret",
    ["", "too-short", "x" * 32, "ab" * 16],
    ids=["empty", "short", "single-byte-repeat", "short-pattern-repeat"],
)
def test_trusted_gateway_exchange_requires_strong_server_secret(
    tmp_path: Path,
    weak_secret: str,
) -> None:
    repository = FakeIdentityRepository()
    app = create_app(
        root_dir=tmp_path,
        product_identity_repository_factory=lambda: repository,
        product_auth_settings=FakeProductAuthSettings(gateway_secret=weak_secret),
    )

    response = ASGIClient(app).request(
        "POST",
        "/api/v1/auth/session",
        json=gateway_assertion(EMPLOYEE_ID, int(time.time())),
    )

    assert response.status_code == 503
    assert response.json() == {"detail": "Service Unavailable"}
    assert "set-cookie" not in response.headers
    assert repository.active_account_ids == []
    assert repository.created_sessions == []


def test_logout_deletes_session_without_principal_lookup_and_expires_cookie(
    auth_session_client,
) -> None:
    client, repository, _ = auth_session_client
    exchange = client.request(
        "POST",
        "/api/v1/auth/session",
        json=gateway_assertion(EMPLOYEE_ID, int(time.time())),
    )
    raw_token = repository.created_sessions[0][1]

    response = client.request(
        "POST",
        "/api/v1/auth/logout",
        headers=session_cookie(raw_token),
    )

    assert exchange.status_code == 200
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert repository.resolver_tokens == []
    assert repository.deleted_sessions == [raw_token]
    cookie = response.headers["set-cookie"].lower()
    assert "hxy_session=" in cookie
    assert "max-age=0" in cookie
    assert "httponly" in cookie
    assert "secure" in cookie
    assert "samesite=lax" in cookie
    assert "path=/api/v1" in cookie


def test_logout_is_idempotent_for_unknown_or_missing_session(auth_session_client) -> None:
    client, repository, _ = auth_session_client

    unknown = client.request(
        "POST",
        "/api/v1/auth/logout",
        headers=session_cookie("unknown-session-token"),
    )
    missing = client.request("POST", "/api/v1/auth/logout")

    assert unknown.status_code == 200
    assert missing.status_code == 200
    assert repository.deleted_sessions == ["unknown-session-token"]
    assert repository.resolver_tokens == []
    for response in (unknown, missing):
        assert response.json() == {"status": "ok"}
        cookie = response.headers["set-cookie"].lower()
        assert "hxy_session=" in cookie
        assert "max-age=0" in cookie
        assert "path=/api/v1" in cookie


def test_logout_rejects_malformed_bearer_without_using_cookie(auth_session_client) -> None:
    client, repository, _ = auth_session_client

    response = client.request(
        "POST",
        "/api/v1/auth/logout",
        headers={
            "Authorization": "Basic invalid-session",
            **session_cookie("employee-session"),
        },
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Unauthorized"}
    assert repository.deleted_sessions == []
    assert "max-age=0" in response.headers["set-cookie"].lower()


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
                "materials:create",
                "materials:read",
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
                    "materials:create",
                    "materials:read",
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


def test_me_uses_the_assignment_bound_to_the_session_not_list_order(
    identity_client,
) -> None:
    client, repository, _ = identity_client
    repository.principals["founder-session"] = FakePrincipal(
        FOUNDER_ID,
        "测试创始人",
        FOUNDER_OPERATIONS_ASSIGNMENT_ID,
    )

    response = client.get("/api/v1/me", headers=bearer("founder-session"))

    assert response.status_code == 200
    assert response.json()["active_assignment"]["assignment_id"] == (
        FOUNDER_OPERATIONS_ASSIGNMENT_ID
    )
    assert response.json()["active_assignment"]["role"] == "hq_operations"


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


def test_query_parameter_cannot_override_the_session_assignment(identity_client) -> None:
    client, _, _ = identity_client

    response = client.get(
        f"/api/v1/me?assignment_id={FOUNDER_OPERATIONS_ASSIGNMENT_ID}",
        headers=bearer("founder-session"),
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "Forbidden"}


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
    assert "CREATE TABLE IF NOT EXISTS hxy_organization_stores" in sql
    assert "CREATE TABLE IF NOT EXISTS hxy_role_assignments" in sql
    assert "CREATE TABLE IF NOT EXISTS hxy_consumed_gateway_assertions" in sql
    assert "REFERENCES staff_accounts(id)" in normalized
    assert "REFERENCES hxy_organizations(organization_id)" in normalized
    assert "REFERENCES stores(store_id)" in normalized
    assert "PRIMARY KEY (organization_id, store_id)" in normalized
    assert (
        "FOREIGN KEY (organization_id, store_id) REFERENCES "
        "hxy_organization_stores(organization_id, store_id)" in normalized
    )
    assert "assertion_id UUID PRIMARY KEY" in normalized
    assert "expires_at TIMESTAMPTZ NOT NULL" in normalized
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
    assert (
        "role IN ('store_manager', 'store_employee') AND store_id IS NOT NULL"
        in normalized
    )
    assert (
        "role IN ('founder', 'hq_operations', 'system_admin') AND store_id IS NULL"
        in normalized
    )
    assert "ADD CONSTRAINT fk_hxy_role_assignments_organization_store" in normalized
    assert "ADD CONSTRAINT chk_hxy_role_assignments_store_scope" in normalized
    assert "CREATE UNIQUE INDEX IF NOT EXISTS" in normalized
    assert "CREATE INDEX IF NOT EXISTS" in normalized
    assert "INSERT INTO" not in sql.upper()


def test_session_migration_binds_each_session_to_one_assignment() -> None:
    sql = SESSION_MIGRATION.read_text(encoding="utf-8")
    normalized = " ".join(sql.split())

    assert "ALTER TABLE staff_sessions" in normalized
    assert "ADD COLUMN IF NOT EXISTS assignment_id UUID" in normalized
    assert "REFERENCES hxy_role_assignments(assignment_id)" in normalized
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


class GatewayExchangeConnection:
    def __init__(self, *, duplicate: bool = False) -> None:
        self.duplicate = duplicate
        self.calls: list[tuple[str, tuple[object, ...]]] = []
        self.committed = False
        self.rolled_back = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, *_args) -> None:
        self.committed = exc_type is None
        self.rolled_back = exc_type is not None
        return None

    def execute(self, sql: str, params: tuple[object, ...]):
        self.calls.append((sql, params))
        if "FROM staff_accounts" in sql:
            return FakeQueryResult(
                row={
                    "account_id": EMPLOYEE_ID,
                    "display_name": "测试店员",
                    "assignment_id": EMPLOYEE_ASSIGNMENT_ID,
                },
            )
        if "INSERT INTO hxy_consumed_gateway_assertions" in sql and self.duplicate:
            raise UniqueViolation("assertion already consumed")
        return FakeQueryResult()


class SessionGrantExchangeConnection:
    def __init__(self, *, valid: bool = True) -> None:
        self.valid = valid
        self.calls: list[tuple[str, tuple[object, ...]]] = []
        self.committed = False
        self.rolled_back = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, *_args) -> None:
        self.committed = exc_type is None
        self.rolled_back = exc_type is not None
        return None

    def execute(self, sql: str, params: tuple[object, ...]):
        self.calls.append((sql, params))
        if "FOR UPDATE" in sql:
            return FakeQueryResult(
                row={
                    "account_id": FOUNDER_ID,
                    "display_name": "测试创始人",
                    "assignment_id": FOUNDER_ASSIGNMENT_ID,
                }
                if self.valid
                else None
            )
        return FakeQueryResult()


def test_postgres_repository_hashes_raw_token_and_requires_active_identity(monkeypatch) -> None:
    from apps.api.hxy_product.repository import IdentityRepository

    connection = FakeConnection(
        [
            FakeQueryResult(
                row={
                    "account_id": EMPLOYEE_ID,
                    "display_name": "测试店员",
                    "assignment_id": EMPLOYEE_ASSIGNMENT_ID,
                },
            )
        ]
    )
    repository = IdentityRepository("postgresql://identity.test/hxy")
    monkeypatch.setattr(repository, "connect", lambda: connection)

    principal = repository.resolve_session("raw-session-token")

    assert principal is not None
    assert principal.account_id == EMPLOYEE_ID
    assert principal.assignment_id == EMPLOYEE_ASSIGNMENT_ID
    sql, params = connection.calls[0]
    assert "staff_sessions" in sql
    assert "staff_accounts" in sql
    assert "hxy_role_assignments" in sql
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


def test_postgres_repository_finds_only_active_asserted_account(monkeypatch) -> None:
    from apps.api.hxy_product.repository import IdentityRepository

    connection = FakeConnection(
        [
            FakeQueryResult(
                row={
                    "account_id": EMPLOYEE_ID,
                    "display_name": "测试店员",
                    "assignment_id": EMPLOYEE_ASSIGNMENT_ID,
                },
            )
        ]
    )
    repository = IdentityRepository("postgresql://identity.test/hxy")
    monkeypatch.setattr(repository, "connect", lambda: connection)

    principal = repository.find_active_principal(EMPLOYEE_ID)

    assert principal is not None
    assert principal.account_id == EMPLOYEE_ID
    assert principal.display_name == "测试店员"
    assert principal.assignment_id == EMPLOYEE_ASSIGNMENT_ID
    sql, params = connection.calls[0]
    assert "FROM staff_accounts" in sql
    assert "status = 'active'" in sql
    assert "id = %s::uuid" in sql
    assert params == (EMPLOYEE_ID,)


def test_postgres_repository_atomically_consumes_assertion_and_creates_hashed_session(
    monkeypatch,
) -> None:
    from apps.api.hxy_product.repository import IdentityRepository

    connection = GatewayExchangeConnection()
    repository = IdentityRepository("postgresql://identity.test/hxy")
    monkeypatch.setattr(repository, "connect", lambda: connection)

    principal = repository.exchange_gateway_assertion(
        EMPLOYEE_ID,
        GATEWAY_ASSERTION_ID,
        2_000_000_000,
        "new-raw-session",
        1800,
    )

    expected_hash = hashlib.sha256(b"new-raw-session").hexdigest()
    assert principal is not None
    assert connection.committed is True
    assert connection.rolled_back is False
    assert len(connection.calls) == 3
    assertion_sql, assertion_params = connection.calls[1]
    session_sql, session_params = connection.calls[2]
    assert "INSERT INTO hxy_consumed_gateway_assertions" in assertion_sql
    assert assertion_params == (GATEWAY_ASSERTION_ID, 2_000_000_000)
    assert "INSERT INTO staff_sessions" in session_sql
    assert session_params == (
        expected_hash,
        EMPLOYEE_ID,
        EMPLOYEE_ASSIGNMENT_ID,
        1800,
    )
    assert all("new-raw-session" not in sql for sql, _ in connection.calls)
    assert all("new-raw-session" not in params for _, params in connection.calls)


def test_postgres_repository_rolls_back_duplicate_assertion_without_session(
    monkeypatch,
) -> None:
    from apps.api.hxy_product.repository import IdentityRepository

    connection = GatewayExchangeConnection(duplicate=True)
    repository = IdentityRepository("postgresql://identity.test/hxy")
    monkeypatch.setattr(repository, "connect", lambda: connection)

    principal = repository.exchange_gateway_assertion(
        EMPLOYEE_ID,
        GATEWAY_ASSERTION_ID,
        2_000_000_000,
        "new-raw-session",
        1800,
    )

    assert principal is None
    assert connection.committed is False
    assert connection.rolled_back is True
    assert not any("INSERT INTO staff_sessions" in sql for sql, _ in connection.calls)


def test_postgres_repository_atomically_rotates_one_time_session_grant(
    monkeypatch,
) -> None:
    from apps.api.hxy_product.repository import IdentityRepository

    connection = SessionGrantExchangeConnection()
    repository = IdentityRepository("postgresql://identity.test/hxy")
    monkeypatch.setattr(repository, "connect", lambda: connection)

    principal = repository.exchange_session_grant(
        SESSION_GRANT,
        "new-normal-session-token",
        1800,
    )

    grant_hash = hashlib.sha256(SESSION_GRANT.encode()).hexdigest()
    session_hash = hashlib.sha256(b"new-normal-session-token").hexdigest()
    assert principal is not None
    assert principal.account_id == FOUNDER_ID
    assert principal.assignment_id == FOUNDER_ASSIGNMENT_ID
    assert connection.committed is True
    assert connection.rolled_back is False
    assert len(connection.calls) == 3
    select_sql, select_params = connection.calls[0]
    delete_sql, delete_params = connection.calls[1]
    insert_sql, insert_params = connection.calls[2]
    assert "FROM staff_sessions AS session_grant" in select_sql
    assert "session_grant.expires_at > NOW()" in select_sql
    assert "account.status = 'active'" in select_sql
    assert "assignment.status = 'active'" in select_sql
    assert "organization.status = 'active'" in select_sql
    assert "FOR UPDATE" in select_sql
    assert select_params == (grant_hash,)
    assert "DELETE FROM staff_sessions" in delete_sql
    assert delete_params == (grant_hash,)
    assert "INSERT INTO staff_sessions" in insert_sql
    assert insert_params == (
        session_hash,
        FOUNDER_ID,
        FOUNDER_ASSIGNMENT_ID,
        1800,
    )
    assert all(SESSION_GRANT not in params for _sql, params in connection.calls)
    assert all("new-normal-session-token" not in params for _sql, params in connection.calls)


def test_postgres_repository_rejects_unknown_or_expired_session_grant(
    monkeypatch,
) -> None:
    from apps.api.hxy_product.repository import IdentityRepository

    connection = SessionGrantExchangeConnection(valid=False)
    repository = IdentityRepository("postgresql://identity.test/hxy")
    monkeypatch.setattr(repository, "connect", lambda: connection)

    principal = repository.exchange_session_grant(
        "u" * 64,
        "new-normal-session-token",
        1800,
    )

    assert principal is None
    assert connection.committed is True
    assert len(connection.calls) == 1
    assert not any("DELETE FROM" in sql for sql, _params in connection.calls)
    assert not any("INSERT INTO" in sql for sql, _params in connection.calls)


def test_postgres_repository_hash_deletes_unknown_session(monkeypatch) -> None:
    from apps.api.hxy_product.repository import IdentityRepository

    connection = FakeConnection([FakeQueryResult()])
    repository = IdentityRepository("postgresql://identity.test/hxy")
    monkeypatch.setattr(repository, "connect", lambda: connection)

    repository.delete_session("unknown-raw-session")

    sql, params = connection.calls[0]
    assert "DELETE FROM staff_sessions" in sql
    assert params == (hashlib.sha256(b"unknown-raw-session").hexdigest(),)


def test_production_identity_code_contains_no_fixture_token_backdoor() -> None:
    package = ROOT / "apps" / "api" / "hxy_product"
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in package.glob("*.py")
    )

    assert "employee-session" not in source
    assert "founder-session" not in source
    assert "fixture mode" not in source.lower()
