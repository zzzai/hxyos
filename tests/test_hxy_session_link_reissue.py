from __future__ import annotations

import hashlib
import importlib
import json
from pathlib import Path
from typing import Any

import psycopg
import pytest

from apps.api.hxy_product.session_link_reissue import (
    REISSUE_CONFIRMATION,
    SessionLinkReissueAuthorizationError,
    SessionLinkReissueConflict,
    SessionLinkReissueValidationError,
    build_argument_parser,
    reissue_founder_session_grant,
)


ROOT = Path(__file__).resolve().parents[1]
DATABASE_URL = "host=127.0.0.1 dbname=hxy user=hxy_app"
RAW_GRANT = "reissue-grant-" + "r" * 48


class FakeResult:
    def __init__(self, row: dict[str, Any] | None = None) -> None:
        self.row = row

    def fetchone(self):
        return self.row


class FakeReissueConnection:
    def __init__(self, founder: dict[str, Any] | None = None) -> None:
        self.founder = founder
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
        if "FROM staff_accounts AS account" in normalized:
            return FakeResult(self.founder)
        if "INSERT INTO staff_sessions" in normalized:
            return FakeResult({"token_hash": params[0]})
        raise AssertionError(normalized)


def _connect(connection: FakeReissueConnection):
    def factory(_database_url: str):
        return connection

    return factory


def _founder() -> dict[str, str]:
    return {
        "account_id": "10000000-0000-0000-0000-000000000001",
        "display_name": "荷小悦创始人",
        "assignment_id": "10000000-0000-0000-0000-000000000002",
        "organization_id": "10000000-0000-0000-0000-000000000003",
        "organization_name": "荷小悦",
    }


def _reissue(connection: FakeReissueConnection, **overrides):
    payload = {
        "database_url": DATABASE_URL,
        "username": "founder",
        "confirmation": REISSUE_CONFIRMATION,
        "connect_factory": _connect(connection),
        "token_factory": lambda: RAW_GRANT,
    }
    payload.update(overrides)
    return reissue_founder_session_grant(**payload)


def test_reissue_requires_exact_confirmation_before_connecting() -> None:
    connection = FakeReissueConnection(_founder())

    for confirmation in ("", "yes", "REISSUE", "reissue-hxy-session-link"):
        with pytest.raises(SessionLinkReissueAuthorizationError, match="confirmation"):
            _reissue(connection, confirmation=confirmation)

    assert connection.calls == []


def test_reissue_rejects_non_hxy_database_before_connecting() -> None:
    connection = FakeReissueConnection(_founder())

    with pytest.raises(SessionLinkReissueValidationError, match="HXY-owned"):
        _reissue(
            connection,
            database_url="host=127.0.0.1 dbname=htops user=hxy_app",
        )

    assert connection.calls == []


def test_reissue_targets_active_founder_and_persists_only_hashed_grant() -> None:
    connection = FakeReissueConnection(_founder())

    result = _reissue(connection)

    assert connection.entered is True
    assert connection.exited is True
    assert result == {
        "status": "issued",
        "account_id": _founder()["account_id"],
        "assignment_id": _founder()["assignment_id"],
        "display_name": "荷小悦创始人",
        "organization_id": _founder()["organization_id"],
        "organization_name": "荷小悦",
        "username": "founder",
        "role": "founder",
        "grant_ttl_seconds": 600,
        "session_grant": RAW_GRANT,
    }

    sql_text = "\n".join(sql for sql, _params in connection.calls)
    assert "assignment.role = 'founder'" in sql_text
    assert "account.status = 'active'" in sql_text
    assert "assignment.status = 'active'" in sql_text
    assert "organization.status = 'active'" in sql_text
    assert "INSERT INTO staff_sessions" in sql_text
    assert "INSERT INTO staff_accounts" not in sql_text
    assert "UPDATE staff_accounts" not in sql_text
    assert "DELETE FROM staff_sessions" not in sql_text

    all_params = [value for _sql, params in connection.calls for value in params]
    assert RAW_GRANT not in all_params
    assert hashlib.sha256(RAW_GRANT.encode("utf-8")).hexdigest() in all_params


def test_reissue_refuses_missing_or_inactive_founder() -> None:
    connection = FakeReissueConnection(None)

    with pytest.raises(SessionLinkReissueConflict, match="active founder"):
        _reissue(connection)

    assert not any("INSERT INTO staff_sessions" in sql for sql, _ in connection.calls)


def test_reissue_validates_username_and_bounded_ttl() -> None:
    connection = FakeReissueConnection(_founder())

    result = _reissue(connection, grant_ttl_seconds=86400)

    assert result["grant_ttl_seconds"] == 86400

    for overrides in (
        {"username": "x"},
        {"username": "包含空格"},
        {"grant_ttl_seconds": 59},
        {"grant_ttl_seconds": 86401},
    ):
        with pytest.raises(SessionLinkReissueValidationError):
            _reissue(connection, **overrides)

    assert len(connection.calls) == 3


def test_reissue_cli_requires_username_app_url_and_confirmation() -> None:
    args = build_argument_parser().parse_args(
        [
            "--username",
            "founder",
            "--app-url",
            "https://hxyos.hexiaoyue.com/",
            "--confirm",
            REISSUE_CONFIRMATION,
        ]
    )

    assert args.username == "founder"
    assert args.confirm == REISSUE_CONFIRMATION
    script = (ROOT / "scripts" / "reissue-hxy-session-link.py").read_text(
        encoding="utf-8"
    )
    assert "session_link_reissue" in script
    assert "htops" not in script.lower()


def test_reissue_cli_does_not_expose_database_errors_or_dsn_secrets(
    monkeypatch,
    capsys,
) -> None:
    module = importlib.import_module("apps.api.hxy_product.session_link_reissue")
    secret = "database-secret-value"
    monkeypatch.setenv(
        "HXY_DATABASE_URL",
        f"host=127.0.0.1 dbname=hxy user=hxy_app password={secret}",
    )

    def fail(**_kwargs):
        raise psycopg.OperationalError(f"connection failed password={secret}")

    monkeypatch.setattr(module, "reissue_founder_session_grant", fail)
    exit_code = module.main(
        [
            "--username",
            "founder",
            "--app-url",
            "https://hxyos.hexiaoyue.com/",
            "--confirm",
            REISSUE_CONFIRMATION,
        ]
    )
    output = capsys.readouterr().out

    assert exit_code == 2
    assert secret not in output
    assert "password=" not in output
    assert json.loads(output)["error"] == "database operation failed"


def test_reissue_cli_reads_separate_founder_grant_ttl_environment(
    monkeypatch,
    capsys,
) -> None:
    module = importlib.import_module("apps.api.hxy_product.session_link_reissue")
    captured: dict[str, Any] = {}
    monkeypatch.setenv("HXY_DATABASE_URL", DATABASE_URL)
    monkeypatch.setenv("HXY_FOUNDER_GRANT_TTL_SECONDS", "86400")

    def succeed(**kwargs):
        captured.update(kwargs)
        return {
            "status": "issued",
            "session_grant": RAW_GRANT,
            "grant_ttl_seconds": kwargs["grant_ttl_seconds"],
        }

    monkeypatch.setattr(module, "reissue_founder_session_grant", succeed)

    exit_code = module.main(
        [
            "--username",
            "founder",
            "--app-url",
            "https://hxyos.hexiaoyue.com/",
            "--confirm",
            REISSUE_CONFIRMATION,
        ]
    )

    assert exit_code == 0
    assert captured["grant_ttl_seconds"] == 86400
    assert json.loads(capsys.readouterr().out)["grant_ttl_seconds"] == 86400
