from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
from typing import Any, Callable

import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row

from .founder_bootstrap import build_session_link


REISSUE_CONFIRMATION = "REISSUE-HXY-SESSION-LINK"
DEFAULT_GRANT_TTL_SECONDS = 600

_USERNAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,63}$")

ConnectFactory = Callable[[str], Any]
TokenFactory = Callable[[], str]


class SessionLinkReissueAuthorizationError(RuntimeError):
    pass


class SessionLinkReissueConflict(RuntimeError):
    pass


class SessionLinkReissueValidationError(ValueError):
    pass


def _default_connect(database_url: str):
    return psycopg.connect(database_url, row_factory=dict_row)


def reissue_founder_session_grant(
    *,
    database_url: str,
    username: str,
    confirmation: str,
    grant_ttl_seconds: int = DEFAULT_GRANT_TTL_SECONDS,
    connect_factory: ConnectFactory | None = None,
    token_factory: TokenFactory | None = None,
) -> dict[str, Any]:
    if confirmation != REISSUE_CONFIRMATION:
        raise SessionLinkReissueAuthorizationError(
            "exact reissue confirmation is required"
        )

    normalized_username = username.strip()
    if not _USERNAME.fullmatch(normalized_username):
        raise SessionLinkReissueValidationError("username is invalid")
    if not 60 <= int(grant_ttl_seconds) <= 600:
        raise SessionLinkReissueValidationError("grant TTL is invalid")
    if not database_url.strip():
        raise SessionLinkReissueValidationError("database URL is required")
    database_name = str(conninfo_to_dict(database_url).get("dbname") or "").lower()
    if not database_name.startswith("hxy") or "htops" in database_name:
        raise SessionLinkReissueValidationError("database must be HXY-owned")

    session_grant = (token_factory or (lambda: secrets.token_urlsafe(32)))()
    if not 43 <= len(session_grant) <= 256:
        raise SessionLinkReissueValidationError("generated session grant is invalid")
    token_hash = hashlib.sha256(session_grant.encode("utf-8")).hexdigest()

    factory = connect_factory or _default_connect
    with factory(database_url) as connection:
        connection.execute(
            "SELECT pg_advisory_xact_lock(hashtext('hxy-session-link-reissue')) AS locked"
        ).fetchone()
        founder = connection.execute(
            """
            SELECT account.id::text AS account_id,
                   account.display_name,
                   assignment.assignment_id::text AS assignment_id,
                   organization.organization_id::text AS organization_id,
                   organization.name AS organization_name
            FROM staff_accounts AS account
            JOIN hxy_role_assignments AS assignment
              ON assignment.account_id = account.id
            JOIN hxy_organizations AS organization
              ON organization.organization_id = assignment.organization_id
            WHERE account.username = %s
              AND assignment.role = 'founder'
              AND account.status = 'active'
              AND assignment.status = 'active'
              AND organization.status = 'active'
            LIMIT 1
            FOR UPDATE OF account, assignment
            """,
            (normalized_username,),
        ).fetchone()
        if founder is None:
            raise SessionLinkReissueConflict("active founder assignment was not found")
        connection.execute(
            """
            INSERT INTO staff_sessions (
              token_hash,
              account_id,
              assignment_id,
              expires_at
            )
            VALUES (
              %s,
              %s::uuid,
              %s::uuid,
              NOW() + (%s * INTERVAL '1 second')
            )
            RETURNING token_hash
            """,
            (
                token_hash,
                founder["account_id"],
                founder["assignment_id"],
                int(grant_ttl_seconds),
            ),
        ).fetchone()

    return {
        "status": "issued",
        "account_id": str(founder["account_id"]),
        "assignment_id": str(founder["assignment_id"]),
        "display_name": str(founder["display_name"]),
        "organization_id": str(founder["organization_id"]),
        "organization_name": str(founder["organization_name"]),
        "username": normalized_username,
        "role": "founder",
        "grant_ttl_seconds": int(grant_ttl_seconds),
        "session_grant": session_grant,
    }


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Reissue a governed HXY founder session link"
    )
    parser.add_argument("--username", required=True)
    parser.add_argument("--app-url", required=True)
    parser.add_argument("--confirm", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_argument_parser().parse_args(argv)
    database_url = os.getenv("HXY_DATABASE_URL", "").strip()
    try:
        result = reissue_founder_session_grant(
            database_url=database_url,
            username=args.username,
            confirmation=args.confirm,
        )
        session_grant = str(result.pop("session_grant"))
        result["one_time_link"] = build_session_link(args.app_url, session_grant)
        output = result
        exit_code = 0
    except psycopg.Error:
        output = {
            "status": "failed",
            "error_type": "DatabaseError",
            "error": "database operation failed",
        }
        exit_code = 2
    except (
        SessionLinkReissueAuthorizationError,
        SessionLinkReissueConflict,
        SessionLinkReissueValidationError,
        ValueError,
    ) as exc:
        output = {
            "status": "failed",
            "error_type": type(exc).__name__,
            "error": str(exc)[:300],
        }
        exit_code = 2
    print(json.dumps(output, ensure_ascii=False, sort_keys=True))
    return exit_code
