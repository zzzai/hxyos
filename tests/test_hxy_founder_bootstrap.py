from __future__ import annotations

import hashlib
import importlib
import json
from pathlib import Path
from typing import Any

import pytest
import psycopg

from apps.api.hxy_product.founder_bootstrap import (
    BOOTSTRAP_CONFIRMATION,
    FounderBootstrapAuthorizationError,
    FounderBootstrapConflict,
    FounderBootstrapValidationError,
    bootstrap_founder,
    build_argument_parser,
    build_session_link,
)


ROOT = Path(__file__).resolve().parents[1]
RUNBOOK = ROOT / "docs" / "operations" / "hxy-founder-bootstrap.md"
DATABASE_URL = "host=127.0.0.1 dbname=hxy_bootstrap_test user=hxy_app"
RAW_GRANT = "founder-grant-" + "a" * 48


class FakeResult:
    def __init__(self, row: dict[str, Any] | None = None) -> None:
        self.row = row

    def fetchone(self):
        return self.row


class FakeBootstrapConnection:
    def __init__(self, *, counts: dict[str, int] | None = None) -> None:
        self.counts = counts or {
            "account_count": 0,
            "organization_count": 0,
            "assignment_count": 0,
        }
        self.calls: list[tuple[str, tuple[Any, ...]]] = []
        self.entered = False
        self.exited = False

    def __enter__(self):
        self.entered = True
        return self

    def __exit__(self, *_args):
        self.exited = True
        return None

    def execute(self, sql: str, params: tuple[Any, ...] = ()):
        normalized = " ".join(sql.split())
        self.calls.append((normalized, params))
        if "pg_advisory_xact_lock" in normalized:
            return FakeResult({"locked": True})
        if "account_count" in normalized and "organization_count" in normalized:
            return FakeResult(dict(self.counts))
        if "INSERT INTO staff_accounts" in normalized:
            return FakeResult({"id": params[0]})
        if "INSERT INTO hxy_organizations" in normalized:
            return FakeResult({"organization_id": params[0]})
        if "INSERT INTO hxy_role_assignments" in normalized:
            return FakeResult({"assignment_id": params[0]})
        if "INSERT INTO staff_sessions" in normalized:
            return FakeResult({"token_hash": params[0]})
        raise AssertionError(normalized)


def _connect(connection: FakeBootstrapConnection):
    def factory(_database_url: str):
        return connection

    return factory


def _bootstrap(connection: FakeBootstrapConnection, **overrides):
    payload = {
        "database_url": DATABASE_URL,
        "username": "founder",
        "display_name": "荷小悦创始人",
        "organization_slug": "hxy",
        "organization_name": "荷小悦",
        "confirmation": BOOTSTRAP_CONFIRMATION,
        "connect_factory": _connect(connection),
        "token_factory": lambda: RAW_GRANT,
        "password_marker_factory": lambda: "!hxy-gateway-only$" + "b" * 64,
    }
    payload.update(overrides)
    return bootstrap_founder(**payload)


def test_founder_bootstrap_requires_exact_confirmation_before_connecting() -> None:
    connection = FakeBootstrapConnection()

    for confirmation in ("", "yes", "bootstrap-hxy-founder", "BOOTSTRAP-HXY"):
        with pytest.raises(FounderBootstrapAuthorizationError, match="confirmation"):
            _bootstrap(connection, confirmation=confirmation)

    assert connection.calls == []


def test_founder_bootstrap_validates_bounded_identity_metadata() -> None:
    connection = FakeBootstrapConnection()

    invalid = (
        {"username": "含空格 founder"},
        {"display_name": ""},
        {"organization_slug": "HXY INVALID"},
        {"organization_name": "x" * 201},
    )
    for overrides in invalid:
        with pytest.raises(FounderBootstrapValidationError):
            _bootstrap(connection, **overrides)

    assert connection.calls == []


def test_founder_bootstrap_rejects_non_hxy_database_before_connecting() -> None:
    connection = FakeBootstrapConnection()

    with pytest.raises(FounderBootstrapValidationError, match="HXY-owned"):
        _bootstrap(
            connection,
            database_url="host=127.0.0.1 dbname=htops user=hxy_app",
        )

    assert connection.calls == []


def test_founder_bootstrap_is_atomic_and_persists_only_hashed_grant() -> None:
    connection = FakeBootstrapConnection()

    result = _bootstrap(connection)

    assert connection.entered is True
    assert connection.exited is True
    assert result["status"] == "created"
    assert result["session_grant"] == RAW_GRANT
    assert result["grant_ttl_seconds"] == 600
    assert result["role"] == "founder"
    assert result["organization_name"] == "荷小悦"
    assert "password" not in result
    assert "token_hash" not in result

    sql_text = "\n".join(sql for sql, _params in connection.calls)
    assert sql_text.index("pg_advisory_xact_lock") < sql_text.index("account_count")
    assert sql_text.index("INSERT INTO staff_accounts") < sql_text.index(
        "INSERT INTO hxy_organizations"
    )
    assert sql_text.index("INSERT INTO hxy_organizations") < sql_text.index(
        "INSERT INTO hxy_role_assignments"
    )
    assert sql_text.index("INSERT INTO hxy_role_assignments") < sql_text.index(
        "INSERT INTO staff_sessions"
    )

    all_params = [value for _sql, params in connection.calls for value in params]
    assert RAW_GRANT not in all_params
    assert hashlib.sha256(RAW_GRANT.encode("utf-8")).hexdigest() in all_params
    password_markers = [
        value
        for value in all_params
        if isinstance(value, str) and value.startswith("!hxy-gateway-only$")
    ]
    assert len(password_markers) == 1
    assert RAW_GRANT not in password_markers[0]


def test_founder_bootstrap_refuses_any_existing_identity_state() -> None:
    for populated_key in ("account_count", "organization_count", "assignment_count"):
        counts = {
            "account_count": 0,
            "organization_count": 0,
            "assignment_count": 0,
            populated_key: 1,
        }
        connection = FakeBootstrapConnection(counts=counts)

        with pytest.raises(FounderBootstrapConflict, match="not empty"):
            _bootstrap(connection)

        assert not any("INSERT INTO" in sql for sql, _params in connection.calls)


def test_session_link_uses_fragment_and_rejects_unsafe_app_urls() -> None:
    link = build_session_link("https://hxy.example.com/app", RAW_GRANT)

    assert link == f"https://hxy.example.com/app#hxy_session_grant={RAW_GRANT}"
    assert "?" not in link

    local_link = build_session_link("http://127.0.0.1:18084/", RAW_GRANT)
    assert local_link.endswith(f"#hxy_session_grant={RAW_GRANT}")

    for app_url in (
        "http://hxy.example.com",
        "https://hxy.example.com/?existing=1",
        "https://hxy.example.com/#existing",
        "javascript:alert(1)",
    ):
        with pytest.raises(FounderBootstrapValidationError, match="application URL"):
            build_session_link(app_url, RAW_GRANT)


def test_bootstrap_cli_requires_all_founder_metadata() -> None:
    parser = build_argument_parser()
    args = parser.parse_args(
        [
            "--username",
            "founder",
            "--display-name",
            "荷小悦创始人",
            "--organization-slug",
            "hxy",
            "--organization-name",
            "荷小悦",
            "--app-url",
            "https://hxy.example.com",
            "--confirm",
            BOOTSTRAP_CONFIRMATION,
        ]
    )

    assert args.username == "founder"
    assert args.confirm == BOOTSTRAP_CONFIRMATION
    script = (ROOT / "scripts" / "bootstrap-hxy-founder.py").read_text(encoding="utf-8")
    assert "founder_bootstrap" in script
    assert "htops" not in script.lower()


def test_bootstrap_cli_does_not_expose_database_errors_or_dsn_secrets(
    monkeypatch,
    capsys,
) -> None:
    module = importlib.import_module("apps.api.hxy_product.founder_bootstrap")
    secret = "database-secret-value"
    monkeypatch.setenv(
        "HXY_DATABASE_URL",
        f"host=127.0.0.1 dbname=hxy user=hxy_app password={secret}",
    )

    def fail(**_kwargs):
        raise psycopg.OperationalError(f"connection failed password={secret}")

    monkeypatch.setattr(module, "bootstrap_founder", fail)
    exit_code = module.main(
        [
            "--username",
            "founder",
            "--display-name",
            "荷小悦创始人",
            "--organization-slug",
            "hxy",
            "--organization-name",
            "荷小悦",
            "--app-url",
            "https://hxy.example.com",
            "--confirm",
            BOOTSTRAP_CONFIRMATION,
        ]
    )
    output = capsys.readouterr().out

    assert exit_code == 2
    assert secret not in output
    assert "password=" not in output
    assert json.loads(output)["error"] == "database operation failed"


def test_founder_bootstrap_runbook_preserves_release_and_identity_gates() -> None:
    runbook = RUNBOOK.read_text(encoding="utf-8")

    assert "BOOTSTRAP-HXY-FOUNDER" in runbook
    assert "bootstrap-hxy-founder.py" in runbook
    assert "生产备份" in runbook
    assert "--app-url" in runbook
    assert "HTTPS" in runbook
    assert "URL fragment" in runbook
    assert "10 分钟" in runbook
    assert "不创建默认密码" in runbook
    assert "API 先于 worker" in runbook
    assert "本手册不自动执行 founder 初始化" in runbook
    assert "/root/htops" not in runbook
