from __future__ import annotations

from typing import Any

import pytest

from apps.api.hxy_release.product_smoke import (
    ProductSmokeError,
    _remove_temporary_identity,
    run_isolated_product_smoke,
)


ACCOUNT_ID = "10000000-0000-0000-0000-000000000001"
ASSIGNMENT_ID = "10000000-0000-0000-0000-000000000002"
ORGANIZATION_ID = "10000000-0000-0000-0000-000000000003"
CONVERSATION_ID = "10000000-0000-0000-0000-000000000004"
TEMP_TOKEN = "temporary-secret-token-for-smoke"


class _Result:
    def __init__(self, row: dict[str, Any] | None = None) -> None:
        self.row = row

    def fetchone(self) -> dict[str, Any] | None:
        return self.row


class _Connection:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...]]] = []
        self.commits = 0
        self.rollbacks = 0
        self.closed = False
        self.account_exists = False

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> _Result:
        normalized = " ".join(sql.split())
        self.calls.append((normalized, params))
        if "FROM hxy_role_assignments AS assignment" in normalized:
            return _Result(
                {
                    "organization_id": ORGANIZATION_ID,
                }
            )
        if "INSERT INTO staff_accounts" in normalized:
            self.account_exists = True
            return _Result({"id": ACCOUNT_ID})
        if "INSERT INTO hxy_role_assignments" in normalized:
            return _Result({"assignment_id": ASSIGNMENT_ID})
        if "DELETE FROM staff_accounts" in normalized:
            self.account_exists = False
            return _Result({"id": ACCOUNT_ID})
        if "SELECT EXISTS" in normalized:
            return _Result({"exists": self.account_exists})
        return _Result()

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1

    def close(self) -> None:
        self.closed = True


def _connector(connection: _Connection):
    def connect(_database_url: str, **_kwargs: Any) -> _Connection:
        return connection

    return connect


def test_isolated_public_smoke_cleans_temporary_identity_after_success() -> None:
    connection = _Connection()
    requests: list[tuple[str, str, dict[str, Any] | None, str]] = []

    def request_json(
        url: str,
        method: str,
        payload: dict[str, Any] | None,
        token: str,
        _timeout: float,
    ) -> dict[str, Any]:
        requests.append((url, method, payload, token))
        if url.endswith("/api/v1/conversations"):
            return {"conversation": {"id": CONVERSATION_ID}}
        return {
            "conversation": {"id": CONVERSATION_ID},
            "assistant_message": {
                "content": "我可以帮你判断经营问题、理解资料、形成任务并持续跟进。",
                "result_type": "system_capability",
            },
        }

    result = run_isolated_product_smoke(
        database_url="postgresql://hxy.test/hxy",
        app_url="https://hxyos.example",
        connector=_connector(connection),
        request_json=request_json,
        token_factory=lambda: TEMP_TOKEN,
        id_factory=iter([ACCOUNT_ID, ASSIGNMENT_ID]).__next__,
    )

    assert result == {
        "status": "passed",
        "conversation_id": CONVERSATION_ID,
        "result_type": "system_capability",
        "temporary_identity_removed": True,
    }
    assert len(requests) == 2
    assert requests[0][0].endswith("/api/v1/conversations")
    assert requests[1][0].endswith(f"/api/v1/conversations/{CONVERSATION_ID}/messages")
    assert all(item[3] == TEMP_TOKEN for item in requests)
    assert connection.commits == 2
    assert connection.closed is True
    assert connection.account_exists is False


def test_temporary_identity_cleanup_binds_like_pattern_as_data() -> None:
    connection = _Connection()
    connection.account_exists = True

    assert _remove_temporary_identity(connection, ACCOUNT_ID) is True

    delete_sql, delete_params = next(
        (sql, params)
        for sql, params in connection.calls
        if "DELETE FROM staff_accounts" in sql
    )
    assert "username LIKE %s" in delete_sql
    assert delete_params == (ACCOUNT_ID, "hxy_release_smoke_%")


def test_isolated_public_smoke_still_cleans_identity_when_http_fails() -> None:
    connection = _Connection()

    def request_json(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("public endpoint unavailable")

    with pytest.raises(ProductSmokeError, match="public endpoint unavailable"):
        run_isolated_product_smoke(
            database_url="postgresql://hxy.test/hxy",
            app_url="https://hxyos.example",
            connector=_connector(connection),
            request_json=request_json,
            token_factory=lambda: TEMP_TOKEN,
            id_factory=iter([ACCOUNT_ID, ASSIGNMENT_ID]).__next__,
        )

    assert connection.account_exists is False
    assert connection.closed is True
    assert any("DELETE FROM staff_accounts" in sql for sql, _params in connection.calls)


def test_isolated_public_smoke_rejects_governance_language() -> None:
    connection = _Connection()

    def request_json(
        url: str,
        _method: str,
        _payload: dict[str, Any] | None,
        _token: str,
        _timeout: float,
    ) -> dict[str, Any]:
        if url.endswith("/api/v1/conversations"):
            return {"conversation": {"id": CONVERSATION_ID}}
        return {
            "conversation": {"id": CONVERSATION_ID},
            "assistant_message": {
                "content": "当前知识库需要人工复核后再沉淀为权威答案卡。",
                "result_type": "system_capability",
            },
        }

    with pytest.raises(ProductSmokeError, match="governance language"):
        run_isolated_product_smoke(
            database_url="postgresql://hxy.test/hxy",
            app_url="https://hxyos.example",
            connector=_connector(connection),
            request_json=request_json,
            token_factory=lambda: TEMP_TOKEN,
            id_factory=iter([ACCOUNT_ID, ASSIGNMENT_ID]).__next__,
        )

    assert connection.account_exists is False
