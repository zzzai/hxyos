from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import urllib.error
import urllib.request
from typing import Any, Callable
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row


_FORBIDDEN_FOREGROUND_TERMS = ("知识库", "权威", "复核", "答案卡")


class ProductSmokeError(RuntimeError):
    pass


def _request_json(
    url: str,
    method: str,
    payload: dict[str, Any] | None,
    token: str,
    timeout: float,
) -> dict[str, Any]:
    body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            parsed = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, UnicodeError, json.JSONDecodeError) as exc:
        raise ProductSmokeError(f"public request failed: {type(exc).__name__}") from exc
    if not isinstance(parsed, dict):
        raise ProductSmokeError("public response is not a JSON object")
    return parsed


def _create_temporary_identity(
    connection: Any,
    *,
    token: str,
    id_factory: Callable[[], Any],
) -> tuple[str, str]:
    organization = connection.execute(
        """
        SELECT assignment.organization_id::text AS organization_id
        FROM hxy_role_assignments AS assignment
        JOIN hxy_organizations AS organization
          ON organization.organization_id = assignment.organization_id
        WHERE assignment.role = 'founder'
          AND assignment.status = 'active'
          AND organization.status = 'active'
        ORDER BY assignment.created_at, assignment.assignment_id
        LIMIT 1
        """
    ).fetchone()
    if organization is None:
        raise ProductSmokeError("no active HXY founder organization is available")

    account_id = str(id_factory())
    assignment_id = str(id_factory())
    username = f"hxy_release_smoke_{account_id.replace('-', '')}"
    account = connection.execute(
        """
        INSERT INTO staff_accounts (
          id, username, display_name, password_hash, role, status
        )
        VALUES (%s::uuid, %s, 'HXY Release Smoke', '!', 'readonly', 'active')
        RETURNING id::text AS id
        """,
        (account_id, username),
    ).fetchone()
    if account is None:
        raise ProductSmokeError("temporary smoke account was not created")
    assignment = connection.execute(
        """
        INSERT INTO hxy_role_assignments (
          assignment_id, account_id, organization_id, role, status
        )
        VALUES (%s::uuid, %s::uuid, %s::uuid, 'founder', 'active')
        RETURNING assignment_id::text AS assignment_id
        """,
        (assignment_id, account_id, organization["organization_id"]),
    ).fetchone()
    if assignment is None:
        raise ProductSmokeError("temporary smoke assignment was not created")
    connection.execute(
        """
        INSERT INTO staff_sessions (
          token_hash, account_id, assignment_id, expires_at
        )
        VALUES (%s, %s::uuid, %s::uuid, NOW() + INTERVAL '10 minutes')
        """,
        (hashlib.sha256(token.encode("utf-8")).hexdigest(), account_id, assignment_id),
    )
    connection.commit()
    return account_id, assignment_id


def _remove_temporary_identity(connection: Any, account_id: str) -> bool:
    connection.rollback()
    deleted = connection.execute(
        """
        DELETE FROM staff_accounts
        WHERE id = %s::uuid
          AND username LIKE 'hxy_release_smoke_%'
        RETURNING id::text AS id
        """,
        (account_id,),
    ).fetchone()
    if deleted is None:
        connection.rollback()
        return False
    connection.commit()
    remaining = connection.execute(
        "SELECT EXISTS(SELECT 1 FROM staff_accounts WHERE id = %s::uuid) AS exists",
        (account_id,),
    ).fetchone()
    return bool(remaining is not None and not remaining["exists"])


def run_isolated_product_smoke(
    *,
    database_url: str,
    app_url: str,
    connector: Callable[..., Any] = psycopg.connect,
    request_json: Callable[[str, str, dict[str, Any] | None, str, float], dict[str, Any]] = _request_json,
    token_factory: Callable[[], str] = lambda: secrets.token_urlsafe(32),
    id_factory: Callable[[], Any] = uuid4,
    timeout: float = 20.0,
) -> dict[str, Any]:
    if not database_url:
        raise ProductSmokeError("HXY_DATABASE_URL is required")
    base_url = app_url.strip().rstrip("/")
    if not base_url.startswith(("https://", "http://")):
        raise ProductSmokeError("app_url must be an HTTP origin")

    connection = connector(database_url, row_factory=dict_row)
    account_id: str | None = None
    conversation_id: str | None = None
    result_type = ""
    failure: Exception | None = None
    cleanup_ok = False
    try:
        token = token_factory()
        if len(token) < 24:
            raise ProductSmokeError("temporary session token is too short")
        account_id, _assignment_id = _create_temporary_identity(
            connection,
            token=token,
            id_factory=id_factory,
        )
        created = request_json(
            f"{base_url}/api/v1/conversations",
            "POST",
            {},
            token,
            timeout,
        )
        conversation_id = str((created.get("conversation") or {}).get("id") or "")
        if not conversation_id:
            raise ProductSmokeError("conversation smoke did not return an id")
        response = request_json(
            f"{base_url}/api/v1/conversations/{conversation_id}/messages",
            "POST",
            {"content": "你会什么？", "client_message_id": str(uuid4())},
            token,
            timeout,
        )
        if str((response.get("conversation") or {}).get("id") or "") != conversation_id:
            raise ProductSmokeError("conversation smoke returned a mismatched id")
        assistant = response.get("assistant_message") or {}
        result_type = str(assistant.get("result_type") or "")
        answer = str(assistant.get("content") or "").strip()
        if result_type != "system_capability" or not answer:
            raise ProductSmokeError("conversation smoke returned an invalid capability answer")
        if any(term in answer for term in _FORBIDDEN_FOREGROUND_TERMS):
            raise ProductSmokeError("conversation smoke exposed governance language")
    except Exception as exc:  # cleanup must run for HTTP, assertion and database failures
        failure = exc
    finally:
        if account_id is not None:
            try:
                cleanup_ok = _remove_temporary_identity(connection, account_id)
            except Exception as cleanup_exc:
                if failure is None:
                    failure = ProductSmokeError(
                        f"temporary identity cleanup failed: {type(cleanup_exc).__name__}"
                    )
        connection.close()

    if failure is not None:
        if not cleanup_ok and account_id is not None:
            raise ProductSmokeError(
                f"{failure}; temporary identity cleanup was not verified"
            ) from failure
        if isinstance(failure, ProductSmokeError):
            raise failure
        raise ProductSmokeError(str(failure)) from failure
    if not cleanup_ok:
        raise ProductSmokeError("temporary identity cleanup was not verified")
    return {
        "status": "passed",
        "conversation_id": conversation_id,
        "result_type": result_type,
        "temporary_identity_removed": True,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run an isolated HXYOS public product smoke")
    parser.add_argument("--app-url", required=True)
    parser.add_argument("--timeout", type=float, default=20.0)
    args = parser.parse_args(argv)
    try:
        result = run_isolated_product_smoke(
            database_url=os.getenv("HXY_DATABASE_URL", "").strip(),
            app_url=args.app_url,
            timeout=args.timeout,
        )
    except (ProductSmokeError, psycopg.Error) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0
