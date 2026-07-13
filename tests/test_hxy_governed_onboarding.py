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
    segments = database_name.strip().lower().split("_")
    is_hxy_test_database = (
        len(segments) >= 2
        and segments[0] == "hxy"
        and "test" in segments[1:]
        and all(segment.isalnum() for segment in segments)
    )
    if not is_hxy_test_database:
        raise ValueError(
            "HXY_TEST_DATABASE_URL must name an HXY-owned test database with "
            "'test' as an underscore-delimited segment"
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
        "FOREIGN KEY (organization_id, store_id, redeemed_assignment_id, "
        "redeemed_account_id)"
        in normalized
    )
    assert (
        "REFERENCES hxy_role_assignments(organization_id, store_id, assignment_id, "
        "account_id)"
        in normalized
    )
    assert (
        "ON hxy_role_assignments (organization_id, store_id, assignment_id, account_id)"
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
    assert (
        "event_type IN ('created', 'revoked') AND invite_id IS NOT NULL AND "
        "subject_assignment_id IS NULL"
        in normalized
    )
    assert (
        "event_type = 'redeemed' AND invite_id IS NOT NULL AND "
        "subject_assignment_id IS NOT NULL"
        in normalized
    )
    assert (
        "event_type = 'member_deactivated' AND invite_id IS NULL AND "
        "subject_assignment_id IS NOT NULL"
        in normalized
    )


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
        "postgresql:///contest",
        "postgresql:///hxy_contest",
        "postgresql:///onboarding_test",
    ),
)
def test_postgres_execution_refuses_non_test_database_names(database_url: str) -> None:
    with pytest.raises(ValueError, match="HXY-owned test database"):
        require_safe_test_database_url(database_url)


def test_postgres_execution_accepts_underscore_delimited_hxy_test_name() -> None:
    database_url = "postgresql:///hxy_onboarding_test"

    assert require_safe_test_database_url(database_url) == database_url


@pytest.mark.skipif(not DATABASE_URL, reason="HXY_TEST_DATABASE_URL is not configured")
def test_postgres_enforces_onboarding_storage_contracts() -> None:
    database_url = require_safe_test_database_url(DATABASE_URL)
    schema_name = f"hxy_onboarding_test_{uuid4().hex}"
    suffix = uuid4().hex
    organization_id = uuid4()
    foreign_organization_id = uuid4()
    creator_account_id = uuid4()
    creator_assignment_id = uuid4()
    foreign_creator_account_id = uuid4()
    foreign_creator_assignment_id = uuid4()
    other_store_account_id = uuid4()
    other_store_assignment_id = uuid4()
    main_store_account_id = uuid4()
    main_store_assignment_id = uuid4()
    store_id = f"onboarding-test-store-{suffix}"
    other_store_id = f"onboarding-test-other-store-{suffix}"
    foreign_store_id = f"onboarding-test-foreign-store-{suffix}"
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
            connection.execute(MIGRATION.read_text(encoding="utf-8"))
            idempotent_objects = connection.execute(
                """
                SELECT
                  (
                    SELECT count(*)
                    FROM pg_catalog.pg_class AS relation
                    JOIN pg_catalog.pg_namespace AS namespace
                      ON namespace.oid = relation.relnamespace
                    WHERE namespace.nspname = %s
                      AND relation.relkind = 'r'
                      AND relation.relname IN (
                        'hxy_member_invites',
                        'hxy_member_invite_events'
                      )
                  ),
                  (
                    SELECT count(*)
                    FROM pg_catalog.pg_class AS relation
                    JOIN pg_catalog.pg_namespace AS namespace
                      ON namespace.oid = relation.relnamespace
                    WHERE namespace.nspname = %s
                      AND relation.relkind = 'i'
                      AND relation.relname =
                        'uq_hxy_role_assignments_onboarding_identity'
                  ),
                  (
                    SELECT count(*)
                    FROM pg_catalog.pg_constraint AS constraint_record
                    JOIN pg_catalog.pg_class AS relation
                      ON relation.oid = constraint_record.conrelid
                    JOIN pg_catalog.pg_namespace AS namespace
                      ON namespace.oid = relation.relnamespace
                    WHERE namespace.nspname = %s
                      AND constraint_record.conname =
                        'fk_hxy_member_invites_redeemed_identity_store'
                  )
                """,
                (schema_name, schema_name, schema_name),
            ).fetchone()
            assert idempotent_objects == (2, 1, 1)

            def execute_many(
                statement: str,
                params: tuple[tuple[object, ...], ...],
            ) -> None:
                with connection.cursor() as cursor:
                    cursor.executemany(statement, params)

            execute_many(
                """
                INSERT INTO stores (store_id, name)
                VALUES (%s, %s)
                """,
                (
                    (store_id, f"Onboarding integration test {suffix}"),
                    (other_store_id, f"Other store integration test {suffix}"),
                    (foreign_store_id, f"Foreign store integration test {suffix}"),
                ),
            )
            execute_many(
                """
                INSERT INTO hxy_organizations (organization_id, slug, name)
                VALUES (%s, %s, %s)
                """,
                (
                    (
                        organization_id,
                        f"onboarding-test-{suffix}",
                        f"Onboarding integration test {suffix}",
                    ),
                    (
                        foreign_organization_id,
                        f"onboarding-foreign-test-{suffix}",
                        f"Foreign integration test {suffix}",
                    ),
                ),
            )
            execute_many(
                """
                INSERT INTO hxy_organization_stores (organization_id, store_id)
                VALUES (%s, %s)
                """,
                (
                    (organization_id, store_id),
                    (organization_id, other_store_id),
                    (foreign_organization_id, foreign_store_id),
                ),
            )
            execute_many(
                """
                INSERT INTO staff_accounts (
                  id, username, display_name, password_hash, role, store_id
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    (
                        creator_account_id,
                        f"onboarding-test-{suffix}",
                        "Onboarding integration test",
                        "not-a-login-credential",
                        "hq_admin",
                        None,
                    ),
                    (
                        foreign_creator_account_id,
                        f"onboarding-foreign-test-{suffix}",
                        "Foreign creator integration test",
                        "not-a-login-credential",
                        "hq_admin",
                        None,
                    ),
                    (
                        other_store_account_id,
                        f"onboarding-other-store-test-{suffix}",
                        "Other store integration test",
                        "not-a-login-credential",
                        "store_manager",
                        other_store_id,
                    ),
                    (
                        main_store_account_id,
                        f"onboarding-main-store-test-{suffix}",
                        "Main store integration test",
                        "not-a-login-credential",
                        "store_manager",
                        store_id,
                    ),
                ),
            )
            execute_many(
                """
                INSERT INTO hxy_role_assignments (
                  assignment_id, account_id, organization_id, store_id, role
                )
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    (
                        creator_assignment_id,
                        creator_account_id,
                        organization_id,
                        None,
                        "founder",
                    ),
                    (
                        foreign_creator_assignment_id,
                        foreign_creator_account_id,
                        foreign_organization_id,
                        None,
                        "founder",
                    ),
                    (
                        other_store_assignment_id,
                        other_store_account_id,
                        organization_id,
                        other_store_id,
                        "store_manager",
                    ),
                    (
                        main_store_assignment_id,
                        main_store_account_id,
                        organization_id,
                        store_id,
                        "store_manager",
                    ),
                ),
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

            def assert_rejected(
                error: type[psycopg.Error],
                statement: str,
                params: tuple[object, ...] = (),
            ) -> None:
                with pytest.raises(error):
                    with connection.transaction():
                        connection.execute(statement, params)

            assert_rejected(
                psycopg.errors.CheckViolation,
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

            assert_rejected(
                psycopg.errors.CheckViolation,
                """
                INSERT INTO hxy_member_invites (
                  organization_id, store_id, role, display_name,
                  token_hash, created_by_assignment_id, expires_at
                )
                VALUES (%s, %s, 'founder', %s, %s, %s,
                        NOW() + INTERVAL '1 hour')
                """,
                (
                    organization_id,
                    store_id,
                    "Illegal role test",
                    "b" * 64,
                    creator_assignment_id,
                ),
            )

            assert_rejected(
                psycopg.errors.UniqueViolation,
                """
                INSERT INTO hxy_member_invites (
                  organization_id, store_id, role, display_name,
                  token_hash, created_by_assignment_id, expires_at
                )
                VALUES (%s, %s, 'store_manager', %s, %s, %s,
                        NOW() + INTERVAL '1 hour')
                """,
                (
                    organization_id,
                    store_id,
                    "Duplicate token hash test",
                    "a" * 64,
                    creator_assignment_id,
                ),
            )

            assert_rejected(
                psycopg.errors.ForeignKeyViolation,
                """
                INSERT INTO hxy_member_invites (
                  organization_id, store_id, role, display_name,
                  token_hash, created_by_assignment_id, expires_at
                )
                VALUES (%s, %s, 'store_manager', %s, %s, %s,
                        NOW() + INTERVAL '1 hour')
                """,
                (
                    organization_id,
                    foreign_store_id,
                    "Organization store boundary test",
                    "c" * 64,
                    creator_assignment_id,
                ),
            )

            assert_rejected(
                psycopg.errors.ForeignKeyViolation,
                """
                INSERT INTO hxy_member_invites (
                  organization_id, store_id, role, display_name,
                  token_hash, created_by_assignment_id, status, expires_at,
                  redeemed_account_id, redeemed_assignment_id, redeemed_at
                )
                VALUES (%s, %s, 'store_manager', %s, %s, %s, 'redeemed',
                        NOW() + INTERVAL '1 hour', %s, %s, NOW())
                """,
                (
                    organization_id,
                    store_id,
                    "Mismatched redemption identity test",
                    "3" * 64,
                    creator_assignment_id,
                    other_store_account_id,
                    main_store_assignment_id,
                ),
            )

            assert_rejected(
                psycopg.errors.ForeignKeyViolation,
                """
                INSERT INTO hxy_member_invites (
                  organization_id, store_id, role, display_name,
                  token_hash, created_by_assignment_id, expires_at
                )
                VALUES (%s, %s, 'store_manager', %s, %s, %s,
                        NOW() + INTERVAL '1 hour')
                """,
                (
                    organization_id,
                    store_id,
                    "Foreign creator boundary test",
                    "d" * 64,
                    foreign_creator_assignment_id,
                ),
            )

            assert_rejected(
                psycopg.errors.ForeignKeyViolation,
                """
                INSERT INTO hxy_member_invites (
                  organization_id, store_id, role, display_name,
                  token_hash, created_by_assignment_id, status, expires_at,
                  redeemed_account_id, redeemed_assignment_id, redeemed_at
                )
                VALUES (%s, %s, 'store_manager', %s, %s, %s, 'redeemed',
                        NOW() + INTERVAL '1 hour', %s, %s, NOW())
                """,
                (
                    organization_id,
                    store_id,
                    "Cross-store redemption test",
                    "e" * 64,
                    creator_assignment_id,
                    other_store_account_id,
                    other_store_assignment_id,
                ),
            )

            assert_rejected(
                psycopg.errors.CheckViolation,
                """
                INSERT INTO hxy_member_invites (
                  organization_id, store_id, role, display_name,
                  token_hash, created_by_assignment_id, status, expires_at,
                  redeemed_at
                )
                VALUES (%s, %s, 'store_manager', %s, %s, %s, 'pending',
                        NOW() + INTERVAL '1 hour', NOW())
                """,
                (
                    organization_id,
                    store_id,
                    "Invalid pending state test",
                    "f" * 64,
                    creator_assignment_id,
                ),
            )

            for event_type in ("created", "revoked"):
                assert_rejected(
                    psycopg.errors.CheckViolation,
                    """
                    INSERT INTO hxy_member_invite_events (
                      organization_id, store_id, invite_id, actor_assignment_id,
                      subject_assignment_id, event_type
                    )
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        organization_id,
                        store_id,
                        invite_id,
                        creator_assignment_id,
                        main_store_assignment_id,
                        event_type,
                    ),
                )

            assert_rejected(
                psycopg.errors.CheckViolation,
                """
                INSERT INTO hxy_member_invite_events (
                  organization_id, store_id, invite_id,
                  actor_assignment_id, event_type
                )
                VALUES (%s, %s, %s, %s, 'redeemed')
                """,
                (
                    organization_id,
                    store_id,
                    invite_id,
                    creator_assignment_id,
                ),
            )

            assert_rejected(
                psycopg.errors.CheckViolation,
                """
                INSERT INTO hxy_member_invite_events (
                  organization_id, store_id, invite_id, actor_assignment_id,
                  subject_assignment_id, event_type
                )
                VALUES (%s, %s, %s, %s, %s, 'member_deactivated')
                """,
                (
                    organization_id,
                    store_id,
                    invite_id,
                    creator_assignment_id,
                    main_store_assignment_id,
                ),
            )

            assert_rejected(
                psycopg.errors.CheckViolation,
                """
                INSERT INTO hxy_member_invites (
                  organization_id, store_id, role, display_name,
                  token_hash, created_by_assignment_id, status, expires_at
                )
                VALUES (%s, %s, 'store_manager', %s, %s, %s, 'revoked',
                        NOW() + INTERVAL '1 hour')
                """,
                (
                    organization_id,
                    store_id,
                    "Invalid revoked state test",
                    "1" * 64,
                    creator_assignment_id,
                ),
            )

            assert_rejected(
                psycopg.errors.CheckViolation,
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
                    "Invalid redeemed state test",
                    "2" * 64,
                    creator_assignment_id,
                ),
            )

            assert_rejected(
                psycopg.errors.CheckViolation,
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

            assert_rejected(
                psycopg.errors.RaiseException,
                "UPDATE hxy_member_invite_events SET payload = '{}'::jsonb "
                "WHERE event_id = %s",
                (event_id,),
            )
            assert_rejected(
                psycopg.errors.RaiseException,
                "DELETE FROM hxy_member_invite_events WHERE event_id = %s",
                (event_id,),
            )
            assert_rejected(
                psycopg.errors.RaiseException,
                "TRUNCATE hxy_member_invite_events",
            )

            index_rows = connection.execute(
                """
                SELECT index_relation.relname,
                       array_agg(attribute.attname ORDER BY key_column.ordinality)
                FROM pg_catalog.pg_class AS table_relation
                JOIN pg_catalog.pg_namespace AS namespace
                  ON namespace.oid = table_relation.relnamespace
                JOIN pg_catalog.pg_index AS index_info
                  ON index_info.indrelid = table_relation.oid
                JOIN pg_catalog.pg_class AS index_relation
                  ON index_relation.oid = index_info.indexrelid
                JOIN LATERAL unnest(index_info.indkey) WITH ORDINALITY
                  AS key_column(attnum, ordinality)
                  ON key_column.ordinality <= index_info.indnkeyatts
                JOIN pg_catalog.pg_attribute AS attribute
                  ON attribute.attrelid = table_relation.oid
                 AND attribute.attnum = key_column.attnum
                WHERE namespace.nspname = %s
                  AND table_relation.relname = 'hxy_member_invites'
                  AND index_relation.relname IN (
                    'idx_hxy_member_invites_expires',
                    'idx_hxy_member_invites_scope_status'
                  )
                GROUP BY index_relation.relname
                """,
                (schema_name,),
            ).fetchall()
            assert {name: columns for name, columns in index_rows} == {
                "idx_hxy_member_invites_expires": ["expires_at"],
                "idx_hxy_member_invites_scope_status": [
                    "organization_id",
                    "store_id",
                    "status",
                    "created_at",
                ],
            }
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
