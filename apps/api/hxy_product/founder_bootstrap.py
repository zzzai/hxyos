from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote, urlsplit, urlunsplit
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row


BOOTSTRAP_CONFIRMATION = "BOOTSTRAP-HXY-FOUNDER"
DEFAULT_GRANT_TTL_SECONDS = 600

_USERNAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,63}$")
_ORGANIZATION_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")

ConnectFactory = Callable[[str], Any]
TokenFactory = Callable[[], str]


class FounderBootstrapAuthorizationError(RuntimeError):
    pass


class FounderBootstrapConflict(RuntimeError):
    pass


class FounderBootstrapValidationError(ValueError):
    pass


def _default_connect(database_url: str):
    return psycopg.connect(database_url, row_factory=dict_row)


def _validate_identity_metadata(
    username: str,
    display_name: str,
    organization_slug: str,
    organization_name: str,
) -> tuple[str, str, str, str]:
    normalized_username = username.strip()
    normalized_display_name = display_name.strip()
    normalized_slug = organization_slug.strip()
    normalized_organization_name = organization_name.strip()
    if not _USERNAME.fullmatch(normalized_username):
        raise FounderBootstrapValidationError("username is invalid")
    if not 1 <= len(normalized_display_name) <= 120:
        raise FounderBootstrapValidationError("display name is invalid")
    if not _ORGANIZATION_SLUG.fullmatch(normalized_slug):
        raise FounderBootstrapValidationError("organization slug is invalid")
    if not 1 <= len(normalized_organization_name) <= 200:
        raise FounderBootstrapValidationError("organization name is invalid")
    return (
        normalized_username,
        normalized_display_name,
        normalized_slug,
        normalized_organization_name,
    )


def build_session_link(app_url: str, session_grant: str) -> str:
    parsed = urlsplit(app_url.strip())
    local_hosts = {"127.0.0.1", "localhost", "::1"}
    if (
        not parsed.netloc
        or parsed.scheme not in {"http", "https"}
        or (parsed.scheme != "https" and parsed.hostname not in local_hosts)
        or parsed.query
        or parsed.fragment
    ):
        raise FounderBootstrapValidationError("application URL is invalid")
    if not 43 <= len(session_grant) <= 256:
        raise FounderBootstrapValidationError("session grant is invalid")
    fragment = f"hxy_session_grant={quote(session_grant, safe='-._~')}"
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path or "/", "", fragment))


def bootstrap_founder(
    *,
    database_url: str,
    username: str,
    display_name: str,
    organization_slug: str,
    organization_name: str,
    confirmation: str,
    grant_ttl_seconds: int = DEFAULT_GRANT_TTL_SECONDS,
    connect_factory: ConnectFactory | None = None,
    token_factory: TokenFactory | None = None,
    password_marker_factory: TokenFactory | None = None,
) -> dict[str, Any]:
    if confirmation != BOOTSTRAP_CONFIRMATION:
        raise FounderBootstrapAuthorizationError("exact bootstrap confirmation is required")
    (
        normalized_username,
        normalized_display_name,
        normalized_slug,
        normalized_organization_name,
    ) = _validate_identity_metadata(
        username,
        display_name,
        organization_slug,
        organization_name,
    )
    if not 60 <= int(grant_ttl_seconds) <= 600:
        raise FounderBootstrapValidationError("grant TTL is invalid")
    if not database_url.strip():
        raise FounderBootstrapValidationError("database URL is required")

    session_grant = (token_factory or (lambda: secrets.token_urlsafe(32)))()
    if not 43 <= len(session_grant) <= 256:
        raise FounderBootstrapValidationError("generated session grant is invalid")
    password_marker = (
        password_marker_factory
        or (lambda: f"!hxy-gateway-only${secrets.token_hex(32)}")
    )()
    if not password_marker.startswith("!hxy-gateway-only$"):
        raise FounderBootstrapValidationError("password marker is invalid")

    token_hash = hashlib.sha256(session_grant.encode("utf-8")).hexdigest()
    account_id = str(uuid4())
    organization_id = str(uuid4())
    assignment_id = str(uuid4())
    factory = connect_factory or _default_connect
    with factory(database_url) as connection:
        connection.execute(
            "SELECT pg_advisory_xact_lock(hashtext('hxy-founder-bootstrap')) AS locked"
        ).fetchone()
        counts = connection.execute(
            """
            SELECT (SELECT count(*) FROM staff_accounts) AS account_count,
                   (SELECT count(*) FROM hxy_organizations) AS organization_count,
                   (SELECT count(*) FROM hxy_role_assignments) AS assignment_count
            """
        ).fetchone()
        if any(
            int(counts.get(name) or 0) > 0
            for name in ("account_count", "organization_count", "assignment_count")
        ):
            raise FounderBootstrapConflict("identity state is not empty")
        connection.execute(
            """
            INSERT INTO staff_accounts (
              id, username, display_name, password_hash, role, status
            )
            VALUES (%s::uuid, %s, %s, %s, 'hq_admin', 'active')
            RETURNING id::text AS id
            """,
            (account_id, normalized_username, normalized_display_name, password_marker),
        ).fetchone()
        connection.execute(
            """
            INSERT INTO hxy_organizations (
              organization_id, slug, name, status
            )
            VALUES (%s::uuid, %s, %s, 'active')
            RETURNING organization_id::text AS organization_id
            """,
            (organization_id, normalized_slug, normalized_organization_name),
        ).fetchone()
        connection.execute(
            """
            INSERT INTO hxy_role_assignments (
              assignment_id, account_id, organization_id, role, status
            )
            VALUES (%s::uuid, %s::uuid, %s::uuid, 'founder', 'active')
            RETURNING assignment_id::text AS assignment_id
            """,
            (assignment_id, account_id, organization_id),
        ).fetchone()
        connection.execute(
            """
            INSERT INTO staff_sessions (
              token_hash, account_id, assignment_id, expires_at
            )
            VALUES (
              %s,
              %s::uuid,
              %s::uuid,
              NOW() + (%s * INTERVAL '1 second')
            )
            RETURNING token_hash
            """,
            (token_hash, account_id, assignment_id, int(grant_ttl_seconds)),
        ).fetchone()

    return {
        "status": "created",
        "account_id": account_id,
        "assignment_id": assignment_id,
        "organization_id": organization_id,
        "username": normalized_username,
        "display_name": normalized_display_name,
        "organization_slug": normalized_slug,
        "organization_name": normalized_organization_name,
        "role": "founder",
        "grant_ttl_seconds": int(grant_ttl_seconds),
        "session_grant": session_grant,
    }


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Bootstrap the first governed HXY founder")
    parser.add_argument("--username", required=True)
    parser.add_argument("--display-name", required=True)
    parser.add_argument("--organization-slug", required=True)
    parser.add_argument("--organization-name", required=True)
    parser.add_argument("--app-url", required=True)
    parser.add_argument("--confirm", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_argument_parser().parse_args(argv)
    database_url = os.getenv("HXY_DATABASE_URL", "").strip()
    try:
        result = bootstrap_founder(
            database_url=database_url,
            username=args.username,
            display_name=args.display_name,
            organization_slug=args.organization_slug,
            organization_name=args.organization_name,
            confirmation=args.confirm,
        )
        session_grant = str(result.pop("session_grant"))
        result["one_time_link"] = build_session_link(args.app_url, session_grant)
        output = result
        exit_code = 0
    except (
        FounderBootstrapAuthorizationError,
        FounderBootstrapConflict,
        FounderBootstrapValidationError,
        psycopg.Error,
    ) as exc:
        output = {
            "status": "failed",
            "error_type": type(exc).__name__,
            "error": str(exc)[:300],
        }
        exit_code = 2
    print(json.dumps(output, ensure_ascii=False, sort_keys=True))
    return exit_code

