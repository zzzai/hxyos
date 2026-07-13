from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "data" / "migrations" / "017_hxy_governed_onboarding.sql"
DATABASE_URL = os.getenv("HXY_TEST_DATABASE_URL", "").strip()
REQUIRED_MIGRATIONS = tuple(
    ROOT / "data" / "migrations" / name
    for name in (
        "001_hxy_core.sql",
        "002_hxy_knowledge_service.sql",
        "003_hxy_answer_engine.sql",
        "004_hxy_answer_evolution.sql",
        "005_hxy_image_understanding.sql",
        "006_hxy_training_system.sql",
        "007_hxy_store_daily_metrics.sql",
        "008_hxy_training_curriculum.sql",
        "009_hxy_product_identity.sql",
        "010_hxy_product_conversations.sql",
        "011_hxy_product_materials.sql",
        "012_hxy_assignment_sessions.sql",
        "013_hxy_material_intake_jobs.sql",
        "014_hxy_knowledge_activation.sql",
        "015_hxy_product_tasks.sql",
        "016_hxy_product_training.sql",
        "017_hxy_governed_onboarding.sql",
    )
)


def migration_sql() -> tuple[str, str]:
    sql = MIGRATION.read_text(encoding="utf-8")
    return sql, " ".join(sql.split())


def require_safe_test_database_url(database_url: str) -> str:
    try:
        database_name = conninfo_to_dict(database_url).get("dbname", "")
    except psycopg.Error as exc:
        raise ValueError("HXY_TEST_DATABASE_URL must be a valid PostgreSQL URL") from exc
    if "test" not in database_name.strip().lower():
        raise ValueError(
            "HXY_TEST_DATABASE_URL must explicitly name a database containing 'test'"
        )
    return database_url


def test_onboarding_migration_scopes_invites_to_hxy_boundaries() -> None:
    sql, normalized = migration_sql()

    assert "CREATE TABLE IF NOT EXISTS hxy_member_invites" in normalized
    assert "CREATE TABLE IF NOT EXISTS hxy_member_invite_events" in normalized
    assert "CHECK (role IN ('store_manager', 'store_employee'))" in normalized
    assert "FOREIGN KEY (organization_id, store_id)" in normalized
    assert (
        "REFERENCES hxy_organization_stores(organization_id, store_id)"
        in normalized
    )
    assert (
        "FOREIGN KEY (organization_id, created_by_assignment_id)" in normalized
    )
    assert (
        "REFERENCES hxy_role_assignments(organization_id, assignment_id)"
        in normalized
    )
    assert (
        "FOREIGN KEY (organization_id, store_id, redeemed_assignment_id)"
        in normalized
    )
    assert (
        "REFERENCES hxy_role_assignments(organization_id, store_id, assignment_id)"
        in normalized
    )
    assert "UNIQUE (token_hash)" in normalized
    assert "token_hash ~ '^[0-9a-f]{64}$'" in normalized


def test_onboarding_migration_enforces_invite_state_shapes() -> None:
    _, normalized = migration_sql()

    assert "status IN ('pending', 'redeemed', 'revoked')" in normalized
    assert (
        "status = 'pending' AND redeemed_account_id IS NULL AND "
        "redeemed_assignment_id IS NULL AND redeemed_at IS NULL AND revoked_at IS NULL"
        in normalized
    )
    assert (
        "status = 'redeemed' AND redeemed_account_id IS NOT NULL AND "
        "redeemed_assignment_id IS NOT NULL AND redeemed_at IS NOT NULL AND "
        "revoked_at IS NULL"
        in normalized
    )
    assert (
        "status = 'revoked' AND redeemed_account_id IS NULL AND "
        "redeemed_assignment_id IS NULL AND redeemed_at IS NULL AND "
        "revoked_at IS NOT NULL"
        in normalized
    )


def test_onboarding_migration_indexes_expiry_and_status() -> None:
    _, normalized = migration_sql()

    assert "CREATE INDEX IF NOT EXISTS idx_hxy_member_invites_expires" in normalized
    assert "ON hxy_member_invites (expires_at)" in normalized
    assert "CREATE INDEX IF NOT EXISTS idx_hxy_member_invites_scope_status" in normalized
    assert (
        "ON hxy_member_invites (organization_id, store_id, status, created_at DESC)"
        in normalized
    )


def test_onboarding_invite_events_are_append_only() -> None:
    _, normalized = migration_sql()

    assert "hxy_member_invite_events is append-only" in normalized
    assert "BEFORE UPDATE OR DELETE ON hxy_member_invite_events" in normalized
    assert "BEFORE TRUNCATE ON hxy_member_invite_events" in normalized
    assert "payload JSONB NOT NULL DEFAULT '{}'::jsonb" in normalized
    assert "CHECK (payload = '{}'::jsonb)" in normalized


def test_onboarding_migration_contains_no_seed_rows_or_foreign_brand_data() -> None:
    sql, normalized = migration_sql()

    assert "INSERT INTO" not in normalized
    assert "htops" not in sql.lower()
    assert "hetang" not in sql.lower()


@pytest.mark.parametrize(
    "database_url",
    (
        "postgresql:///hxy",
        "postgresql:///postgres",
        "dbname=hxy",
        "postgresql://localhost/",
    ),
)
def test_postgres_execution_refuses_non_test_database_names(database_url: str) -> None:
    with pytest.raises(ValueError, match="database containing 'test'"):
        require_safe_test_database_url(database_url)


@pytest.mark.skipif(not DATABASE_URL, reason="HXY_TEST_DATABASE_URL is not configured")
def test_postgres_enforces_onboarding_storage_contracts() -> None:
    database_url = require_safe_test_database_url(DATABASE_URL)
    schema_name = f"hxy_onboarding_test_{uuid4().hex}"
    suffix = uuid4().hex
    organization_id = uuid4()
    creator_account_id = uuid4()
    creator_assignment_id = uuid4()
    store_id = f"onboarding-test-store-{suffix}"
    invite_id = uuid4()
    event_id = uuid4()

    with psycopg.connect(database_url, autocommit=True) as connection:
        connection.execute(
            sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema_name))
        )
        try:
            connection.execute(
                sql.SQL("SET search_path TO {}, public").format(
                    sql.Identifier(schema_name)
                )
            )
            for migration in REQUIRED_MIGRATIONS:
                connection.execute(migration.read_text(encoding="utf-8"))

            connection.execute(
                """
                INSERT INTO stores (store_id, name)
                VALUES (%s, %s)
                """,
                (store_id, f"Onboarding integration test {suffix}"),
            )
            connection.execute(
                """
                INSERT INTO hxy_organizations (organization_id, slug, name)
                VALUES (%s, %s, %s)
                """,
                (
                    organization_id,
                    f"onboarding-test-{suffix}",
                    f"Onboarding integration test {suffix}",
                ),
            )
            connection.execute(
                """
                INSERT INTO hxy_organization_stores (organization_id, store_id)
                VALUES (%s, %s)
                """,
                (organization_id, store_id),
            )
            connection.execute(
                """
                INSERT INTO staff_accounts (
                  id, username, display_name, password_hash, role
                )
                VALUES (%s, %s, %s, %s, 'hq_admin')
                """,
                (
                    creator_account_id,
                    f"onboarding-test-{suffix}",
                    "Onboarding integration test",
                    "not-a-login-credential",
                ),
            )
            connection.execute(
                """
                INSERT INTO hxy_role_assignments (
                  assignment_id, account_id, organization_id, role
                )
                VALUES (%s, %s, %s, 'founder')
                """,
                (creator_assignment_id, creator_account_id, organization_id),
            )
            connection.execute(
                """
                INSERT INTO hxy_member_invites (
                  invite_id, organization_id, store_id, role, display_name,
                  token_hash, created_by_assignment_id, expires_at
                )
                VALUES (%s, %s, %s, 'store_manager', %s, %s, %s,
                        NOW() + INTERVAL '1 hour')
                """,
                (
                    invite_id,
                    organization_id,
                    store_id,
                    "Onboarding integration test",
                    "a" * 64,
                    creator_assignment_id,
                ),
            )
            connection.execute(
                """
                INSERT INTO hxy_member_invite_events (
                  event_id, organization_id, store_id, invite_id,
                  actor_assignment_id, event_type
                )
                VALUES (%s, %s, %s, %s, %s, 'created')
                """,
                (
                    event_id,
                    organization_id,
                    store_id,
                    invite_id,
                    creator_assignment_id,
                ),
            )

            with pytest.raises(psycopg.errors.CheckViolation):
                connection.execute(
                    """
                    INSERT INTO hxy_member_invites (
                      organization_id, store_id, role, display_name,
                      token_hash, created_by_assignment_id, expires_at
                    )
                    VALUES (%s, %s, 'store_manager', %s, 'not-a-sha256', %s,
                            NOW() + INTERVAL '1 hour')
                    """,
                    (
                        organization_id,
                        store_id,
                        "Invalid hash test",
                        creator_assignment_id,
                    ),
                )

            with pytest.raises(psycopg.errors.CheckViolation):
                connection.execute(
                    """
                    INSERT INTO hxy_member_invites (
                      organization_id, store_id, role, display_name,
                      token_hash, created_by_assignment_id, status, expires_at
                    )
                    VALUES (%s, %s, 'store_manager', %s, %s, %s, 'redeemed',
                            NOW() + INTERVAL '1 hour')
                    """,
                    (
                        organization_id,
                        store_id,
                        "Invalid state test",
                        "b" * 64,
                        creator_assignment_id,
                    ),
                )

            with pytest.raises(psycopg.errors.CheckViolation):
                connection.execute(
                    """
                    INSERT INTO hxy_member_invite_events (
                      organization_id, store_id, invite_id,
                      actor_assignment_id, event_type, payload
                    )
                    VALUES (%s, %s, %s, %s, 'created', %s::jsonb)
                    """,
                    (
                        organization_id,
                        store_id,
                        invite_id,
                        creator_assignment_id,
                        '{"nested":{"token":"must-not-persist"}}',
                    ),
                )

            with pytest.raises(psycopg.errors.RaiseException):
                connection.execute(
                    "UPDATE hxy_member_invite_events SET payload = '{}'::jsonb "
                    "WHERE event_id = %s",
                    (event_id,),
                )
            with pytest.raises(psycopg.errors.RaiseException):
                connection.execute(
                    "DELETE FROM hxy_member_invite_events WHERE event_id = %s",
                    (event_id,),
                )
            with pytest.raises(psycopg.errors.RaiseException):
                connection.execute("TRUNCATE hxy_member_invite_events")
        finally:
            connection.execute("RESET search_path")
            connection.execute(
                sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(
                    sql.Identifier(schema_name)
                )
            )
        remaining_schema = connection.execute(
            "SELECT 1 FROM pg_namespace WHERE nspname = %s",
            (schema_name,),
        ).fetchone()
        assert remaining_schema is None
