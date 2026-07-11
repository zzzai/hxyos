from __future__ import annotations

import os
from uuid import uuid4

import psycopg
import pytest

from apps.api.hxy_product.founder_bootstrap import (
    BOOTSTRAP_CONFIRMATION,
    bootstrap_founder,
)
from apps.api.hxy_product.repository import IdentityRepository


DATABASE_URL = os.getenv("HXY_TEST_DATABASE_URL", "").strip()


@pytest.mark.skipif(not DATABASE_URL, reason="HXY_TEST_DATABASE_URL is not configured")
def test_postgres_bootstrap_and_one_time_session_rotation() -> None:
    with psycopg.connect(DATABASE_URL) as connection:
        database_name = connection.execute("SELECT current_database()").fetchone()[0]
    assert "test" in database_name.lower(), "founder bootstrap integration requires a test database"

    suffix = uuid4().hex[:12]
    raw_grant = "g" * 48 + suffix
    result = bootstrap_founder(
        database_url=DATABASE_URL,
        username=f"founder-{suffix}",
        display_name="Founder integration test",
        organization_slug=f"hxy-{suffix}",
        organization_name="HXY integration test",
        confirmation=BOOTSTRAP_CONFIRMATION,
        token_factory=lambda: raw_grant,
    )
    repository = IdentityRepository(DATABASE_URL)

    try:
        with psycopg.connect(DATABASE_URL) as connection:
            stored = connection.execute(
                """
                SELECT account.password_hash, session.token_hash
                FROM staff_accounts AS account
                JOIN staff_sessions AS session ON session.account_id = account.id
                WHERE account.id = %s
                """,
                (result["account_id"],),
            ).fetchone()
        assert stored[0].startswith("!hxy-gateway-only$")
        assert raw_grant not in stored

        normal_token = "n" * 64
        principal = repository.exchange_session_grant(raw_grant, normal_token, 1800)
        assert principal is not None
        assert principal.account_id == result["account_id"]
        assert principal.assignment_id == result["assignment_id"]
        assert repository.resolve_session(raw_grant) is None

        resolved = repository.resolve_session(normal_token)
        assert resolved is not None
        assert resolved.account_id == result["account_id"]
        assert resolved.assignment_id == result["assignment_id"]
        assert repository.exchange_session_grant(raw_grant, "x" * 64, 1800) is None

        assignments = repository.list_assignments(result["account_id"])
        assert len(assignments) == 1
        assert assignments[0].role == "founder"
        assert assignments[0].organization_name == "HXY integration test"
    finally:
        with psycopg.connect(DATABASE_URL) as connection:
            connection.execute(
                "DELETE FROM staff_accounts WHERE id = %s",
                (result["account_id"],),
            )
            connection.execute(
                "DELETE FROM hxy_organizations WHERE organization_id = %s",
                (result["organization_id"],),
            )
