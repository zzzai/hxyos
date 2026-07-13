from __future__ import annotations

import hashlib
import os
import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from threading import Barrier
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from apps.api.hxy_product.onboarding_repository import (
    InviteRedemptionError,
    OnboardingRepository,
    OnboardingScopeError,
)


ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = tuple(
    ROOT / "data" / "migrations" / f"{number:03d}_{name}.sql"
    for number, name in (
        (1, "hxy_core"),
        (2, "hxy_knowledge_service"),
        (3, "hxy_answer_engine"),
        (4, "hxy_answer_evolution"),
        (5, "hxy_image_understanding"),
        (6, "hxy_training_system"),
        (7, "hxy_store_daily_metrics"),
        (8, "hxy_training_curriculum"),
        (9, "hxy_product_identity"),
        (10, "hxy_product_conversations"),
        (11, "hxy_product_materials"),
        (12, "hxy_assignment_sessions"),
        (13, "hxy_material_intake_jobs"),
        (14, "hxy_knowledge_activation"),
        (15, "hxy_product_tasks"),
        (16, "hxy_product_training"),
        (17, "hxy_governed_onboarding"),
    )
)


def _require_safe_database_name(database_name: str) -> str:
    normalized = database_name.strip().lower()
    segments = normalized.split("_")
    if (
        len(segments) < 2
        or segments[0] != "hxy"
        or "test" not in segments[1:]
        or any(not segment.isalnum() for segment in segments)
    ):
        raise ValueError(
            "PostgreSQL integration requires an HXY-owned database with "
            "'test' as an exact underscore-delimited segment"
        )
    return normalized


def require_safe_test_database_url(database_url: str) -> tuple[str, str]:
    try:
        parsed = conninfo_to_dict(database_url)
    except psycopg.Error as exc:
        raise ValueError(
            "HXY_TEST_DATABASE_URL is not valid PostgreSQL conninfo"
        ) from exc
    database_name = _require_safe_database_name(parsed.get("dbname", ""))
    return database_url, database_name


@dataclass(frozen=True)
class PostgresHarness:
    database_url: str = field(repr=False)
    repository_url: str = field(repr=False)
    control_url: str = field(repr=False)
    database_name: str
    schema_name: str

    def connect(self, *, autocommit: bool = False) -> psycopg.Connection[Any]:
        return psycopg.connect(self.repository_url, autocommit=autocommit)

    def repository(self) -> OnboardingRepository:
        return TimedOnboardingRepository(self.repository_url)


class TimedOnboardingRepository(OnboardingRepository):
    def connect(self):
        connection = super().connect()
        connection.execute("SET statement_timeout = '8s'")
        connection.execute("SET lock_timeout = '6s'")
        return connection


@pytest.fixture(scope="module")
def postgres_harness() -> PostgresHarness:
    configured_url = os.getenv("HXY_TEST_DATABASE_URL", "").strip()
    if not configured_url:
        pytest.skip("HXY_TEST_DATABASE_URL is not configured")

    database_url, parsed_database_name = require_safe_test_database_url(configured_url)
    control_url = make_conninfo(
        database_url,
        connect_timeout=5,
        application_name="hxy-onboarding-postgres-control-test",
    )
    schema_name = f"hxy_onboarding_test_{uuid4().hex}"
    schema_created = False

    try:
        with psycopg.connect(control_url, autocommit=True) as connection:
            actual_database_name = connection.execute(
                "SELECT current_database()"
            ).fetchone()[0]
            if (
                _require_safe_database_name(actual_database_name)
                != parsed_database_name
            ):
                raise RuntimeError(
                    "HXY_TEST_DATABASE_URL parsed and connected database names differ"
                )
            connection.execute(
                sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema_name))
            )
            schema_created = True
            connection.execute(
                sql.SQL("SET search_path TO {}, public").format(
                    sql.Identifier(schema_name)
                )
            )
            current_schema = connection.execute(
                "SELECT current_schema()"
            ).fetchone()[0]
            assert current_schema == schema_name
            for migration in MIGRATIONS:
                connection.execute(migration.read_text(encoding="utf-8"))

        repository_url = make_conninfo(
            database_url,
            connect_timeout=5,
            options=f"-csearch_path={schema_name},public",
            application_name="hxy-onboarding-postgres-test",
        )
        harness = PostgresHarness(
            database_url=database_url,
            repository_url=repository_url,
            control_url=control_url,
            database_name=parsed_database_name,
            schema_name=schema_name,
        )
        with harness.connect() as connection:
            current_schema = connection.execute(
                "SELECT current_schema()"
            ).fetchone()[0]
            assert current_schema == schema_name
        yield harness
    finally:
        if schema_created:
            with psycopg.connect(control_url, autocommit=True) as connection:
                actual_database_name = connection.execute(
                    "SELECT current_database()"
                ).fetchone()[0]
                if (
                    _require_safe_database_name(actual_database_name)
                    != parsed_database_name
                ):
                    raise RuntimeError(
                        "refusing PostgreSQL cleanup after database identity changed"
                    )
                connection.execute(
                    sql.SQL("DROP SCHEMA {} CASCADE").format(
                        sql.Identifier(schema_name)
                    )
                )
                residue = connection.execute(
                    "SELECT 1 FROM pg_namespace WHERE nspname = %s",
                    (schema_name,),
                ).fetchone()
                assert residue is None, f"test schema cleanup failed: {schema_name}"


@dataclass(frozen=True)
class Identity:
    account_id: UUID
    assignment_id: UUID
    organization_id: UUID
    store_id: str | None
    assignment_role: str


@dataclass(frozen=True)
class Scenario:
    organization_id: UUID
    store_a: str
    store_b: str
    founder: Identity
    manager_a: Identity
    manager_b: Identity


def _insert_identity(
    connection: psycopg.Connection[Any],
    *,
    organization_id: UUID,
    store_id: str | None,
    assignment_role: str,
    account_role: str,
    display_name: str,
) -> Identity:
    account_id = uuid4()
    assignment_id = uuid4()
    connection.execute(
        """
        INSERT INTO staff_accounts (
          id, username, display_name, password_hash, role, store_id
        )
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (
            account_id,
            f"postgres-onboarding-{uuid4().hex}",
            display_name,
            "!integration-test-no-login",
            account_role,
            store_id,
        ),
    )
    connection.execute(
        """
        INSERT INTO hxy_role_assignments (
          assignment_id, account_id, organization_id, store_id, role
        )
        VALUES (%s, %s, %s, %s, %s)
        """,
        (assignment_id, account_id, organization_id, store_id, assignment_role),
    )
    return Identity(
        account_id=account_id,
        assignment_id=assignment_id,
        organization_id=organization_id,
        store_id=store_id,
        assignment_role=assignment_role,
    )


def _seed_scenario(harness: PostgresHarness) -> Scenario:
    suffix = uuid4().hex
    organization_id = uuid4()
    store_a = f"onboarding-test-a-{suffix}"
    store_b = f"onboarding-test-b-{suffix}"
    with harness.connect() as connection:
        connection.execute(
            "INSERT INTO hxy_organizations (organization_id, slug, name) "
            "VALUES (%s, %s, %s)",
            (organization_id, f"onboarding-test-{suffix}", "Onboarding PG test"),
        )
        with connection.cursor() as cursor:
            cursor.executemany(
                "INSERT INTO stores (store_id, name) VALUES (%s, %s)",
                ((store_a, "Onboarding store A"), (store_b, "Onboarding store B")),
            )
            cursor.executemany(
                "INSERT INTO hxy_organization_stores (organization_id, store_id) "
                "VALUES (%s, %s)",
                ((organization_id, store_a), (organization_id, store_b)),
            )
        founder = _insert_identity(
            connection,
            organization_id=organization_id,
            store_id=None,
            assignment_role="founder",
            account_role="hq_admin",
            display_name="Founder PG test",
        )
        manager_a = _insert_identity(
            connection,
            organization_id=organization_id,
            store_id=store_a,
            assignment_role="store_manager",
            account_role="store_manager",
            display_name="Manager A PG test",
        )
        manager_b = _insert_identity(
            connection,
            organization_id=organization_id,
            store_id=store_b,
            assignment_role="store_manager",
            account_role="store_manager",
            display_name="Manager B PG test",
        )
    return Scenario(
        organization_id=organization_id,
        store_a=store_a,
        store_b=store_b,
        founder=founder,
        manager_a=manager_a,
        manager_b=manager_b,
    )


def _hash(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _create_invite(
    repository: OnboardingRepository,
    scenario: Scenario,
    *,
    raw_token: str,
    display_name: str,
    role: str = "store_manager",
    store_id: str | None = None,
    creator: Identity | None = None,
) -> dict[str, Any]:
    return repository.create_invite(
        str(scenario.organization_id),
        store_id or scenario.store_a,
        str((creator or scenario.founder).assignment_id),
        role,
        display_name,
        _hash(raw_token),
    )


def _wait_for_lock_waiters(
    harness: PostgresHarness,
    *,
    application_name: str,
    expected: int,
    timeout_seconds: float = 5.0,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        with psycopg.connect(harness.control_url, autocommit=True) as connection:
            waiting = connection.execute(
                """
                SELECT count(*)
                FROM pg_stat_activity
                WHERE datname = current_database()
                  AND application_name = %s
                  AND state = 'active'
                  AND wait_event_type = 'Lock'
                """,
                (application_name,),
            ).fetchone()[0]
        if waiting >= expected:
            return
        time.sleep(0.05)
    raise AssertionError(
        "timed out waiting for "
        f"{expected} PostgreSQL lock waiter(s); observed {waiting}"
    )


def _future_result(future: Future[Any]) -> Any:
    try:
        return future.result(timeout=10)
    except InviteRedemptionError as exc:
        return exc


@pytest.mark.parametrize(
    "database_url",
    (
        "postgresql:///hxy",
        "postgresql:///postgres",
        "postgresql:///contest",
        "postgresql:///missing",
        "postgresql:///hxy_contest",
        "postgresql:///onboarding_test",
        "postgresql://localhost/",
    ),
)
def test_safe_database_helper_rejects_non_hxy_test_names(database_url: str) -> None:
    with pytest.raises(ValueError, match="exact underscore-delimited segment"):
        require_safe_test_database_url(database_url)


def test_concurrent_same_invite_redemption_has_one_winner(
    postgres_harness: PostgresHarness,
) -> None:
    scenario = _seed_scenario(postgres_harness)
    application_name = f"hxy-onboarding-concurrency-test-{uuid4().hex[:8]}"
    repository_url = make_conninfo(
        postgres_harness.database_url,
        connect_timeout=5,
        options=f"-csearch_path={postgres_harness.schema_name},public",
        application_name=application_name,
    )
    repository = TimedOnboardingRepository(repository_url)
    raw_invite_token = f"invite-{uuid4().hex}"
    invite = _create_invite(
        repository,
        scenario,
        raw_token=raw_invite_token,
        display_name="Concurrent manager",
    )
    barrier = Barrier(2)

    def redeem(raw_session_token: str) -> dict[str, Any]:
        barrier.wait(timeout=5)
        return repository.redeem_invite(
            _hash(raw_invite_token), raw_session_token, 1800
        )

    with postgres_harness.connect() as blocker:
        blocker.execute(
            "SELECT invite_id FROM hxy_member_invites "
            "WHERE invite_id = %s FOR UPDATE",
            (invite["id"],),
        )
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = (
                executor.submit(redeem, f"session-a-{uuid4().hex}"),
                executor.submit(redeem, f"session-b-{uuid4().hex}"),
            )
            _wait_for_lock_waiters(
                postgres_harness,
                application_name=application_name,
                expected=2,
            )
            blocker.commit()
            outcomes = [_future_result(future) for future in futures]

    assert sum(isinstance(item, dict) for item in outcomes) == 1
    assert sum(isinstance(item, InviteRedemptionError) for item in outcomes) == 1
    with postgres_harness.connect() as connection:
        persisted = connection.execute(
            """
            SELECT invite.status,
                   count(DISTINCT assignment.assignment_id),
                   count(DISTINCT session.token_hash)
            FROM hxy_member_invites AS invite
            LEFT JOIN hxy_role_assignments AS assignment
              ON assignment.assignment_id = invite.redeemed_assignment_id
            LEFT JOIN staff_sessions AS session
              ON session.assignment_id = assignment.assignment_id
            WHERE invite.invite_id = %s
            GROUP BY invite.status
            """,
            (invite["id"],),
        ).fetchone()
    assert persisted == ("redeemed", 1, 1)


def test_only_sha256_invite_and_session_hashes_are_stored(
    postgres_harness: PostgresHarness,
) -> None:
    scenario = _seed_scenario(postgres_harness)
    repository = postgres_harness.repository()
    raw_invite_token = f"raw-invite-{uuid4().hex}"
    raw_session_token = f"raw-session-{uuid4().hex}"
    invite = _create_invite(
        repository,
        scenario,
        raw_token=raw_invite_token,
        display_name="Hash-only manager",
    )
    member = repository.redeem_invite(
        _hash(raw_invite_token), raw_session_token, 1800
    )

    with postgres_harness.connect() as connection:
        stored = connection.execute(
            """
            SELECT invite.token_hash, session.token_hash
            FROM hxy_member_invites AS invite
            JOIN staff_sessions AS session
              ON session.assignment_id = invite.redeemed_assignment_id
            WHERE invite.invite_id = %s
              AND invite.redeemed_assignment_id = %s::uuid
            """,
            (invite["id"], member["assignment_id"]),
        ).fetchone()
    assert stored == (_hash(raw_invite_token), _hash(raw_session_token))
    assert raw_invite_token not in stored
    assert raw_session_token not in stored


@pytest.mark.parametrize(
    ("invite_role", "account_role", "creator_kind"),
    (
        ("store_manager", "store_manager", "founder"),
        ("store_employee", "frontdesk", "manager"),
    ),
)
def test_redeemed_identity_shares_scope_and_exact_role_mapping(
    postgres_harness: PostgresHarness,
    invite_role: str,
    account_role: str,
    creator_kind: str,
) -> None:
    scenario = _seed_scenario(postgres_harness)
    repository = postgres_harness.repository()
    creator = scenario.founder if creator_kind == "founder" else scenario.manager_a
    raw_invite_token = f"scope-invite-{uuid4().hex}"
    invite = _create_invite(
        repository,
        scenario,
        raw_token=raw_invite_token,
        display_name=f"Role mapping {invite_role}",
        role=invite_role,
        creator=creator,
    )
    member = repository.redeem_invite(
        _hash(raw_invite_token), f"scope-session-{uuid4().hex}", 1800
    )

    with postgres_harness.connect() as connection:
        linked = connection.execute(
            """
            SELECT invite.organization_id,
                   invite.store_id,
                   invite.role,
                   invite.status,
                   assignment.organization_id,
                   assignment.store_id,
                   assignment.role,
                   assignment.status,
                   account.role,
                   account.store_id,
                   account.status,
                   account.id,
                   session.account_id,
                   session.assignment_id,
                   event.organization_id,
                   event.store_id,
                   event.actor_assignment_id,
                   event.subject_assignment_id,
                   event.event_type
            FROM hxy_member_invites AS invite
            JOIN hxy_role_assignments AS assignment
              ON assignment.assignment_id = invite.redeemed_assignment_id
            JOIN staff_accounts AS account
              ON account.id = invite.redeemed_account_id
            JOIN staff_sessions AS session
              ON session.assignment_id = assignment.assignment_id
            JOIN hxy_member_invite_events AS event
              ON event.invite_id = invite.invite_id
             AND event.event_type = 'redeemed'
            WHERE invite.invite_id = %s
            """,
            (invite["id"],),
        ).fetchone()
    redeemed_account_id = linked[11]
    assert linked == (
        scenario.organization_id,
        scenario.store_a,
        invite_role,
        "redeemed",
        scenario.organization_id,
        scenario.store_a,
        invite_role,
        "active",
        account_role,
        scenario.store_a,
        "active",
        redeemed_account_id,
        redeemed_account_id,
        UUID(member["assignment_id"]),
        scenario.organization_id,
        scenario.store_a,
        UUID(member["assignment_id"]),
        UUID(member["assignment_id"]),
        "redeemed",
    )


@pytest.mark.parametrize("unavailable_state", ("revoked", "expired"))
def test_unavailable_invite_creates_no_identity_or_session(
    postgres_harness: PostgresHarness,
    unavailable_state: str,
) -> None:
    scenario = _seed_scenario(postgres_harness)
    repository = postgres_harness.repository()
    raw_invite_token = f"unavailable-invite-{uuid4().hex}"
    display_name = f"Unavailable {unavailable_state} {uuid4().hex}"

    if unavailable_state == "revoked":
        invite = _create_invite(
            repository,
            scenario,
            raw_token=raw_invite_token,
            display_name=display_name,
        )
        revoked = repository.revoke_invite(
            str(scenario.organization_id),
            scenario.store_a,
            str(scenario.founder.assignment_id),
            invite["id"],
        )
        assert revoked is not None and revoked["status"] == "revoked"
    else:
        invite_id = uuid4()
        with postgres_harness.connect() as connection:
            connection.execute(
                """
                INSERT INTO hxy_member_invites (
                  invite_id, organization_id, store_id, role, display_name,
                  token_hash, created_by_assignment_id, expires_at, created_at
                )
                VALUES (%s, %s, %s, 'store_manager', %s, %s, %s,
                        NOW() - INTERVAL '1 hour', NOW() - INTERVAL '2 hours')
                """,
                (
                    invite_id,
                    scenario.organization_id,
                    scenario.store_a,
                    display_name,
                    _hash(raw_invite_token),
                    scenario.founder.assignment_id,
                ),
            )
            connection.execute(
                """
                INSERT INTO hxy_member_invite_events (
                  organization_id, store_id, invite_id,
                  actor_assignment_id, event_type
                )
                VALUES (%s, %s, %s, %s, 'created')
                """,
                (
                    scenario.organization_id,
                    scenario.store_a,
                    invite_id,
                    scenario.founder.assignment_id,
                ),
            )
        invite = {"id": str(invite_id)}

    with postgres_harness.connect() as connection:
        before = connection.execute(
            """
            SELECT
              (SELECT count(*) FROM staff_accounts WHERE display_name = %s),
              (SELECT count(*)
                 FROM hxy_role_assignments AS assignment
                 JOIN staff_accounts AS account ON account.id = assignment.account_id
                WHERE account.display_name = %s),
              (SELECT count(*)
                 FROM staff_sessions AS session
                 JOIN staff_accounts AS account ON account.id = session.account_id
                WHERE account.display_name = %s),
              (SELECT count(*) FROM hxy_member_invite_events WHERE invite_id = %s)
            """,
            (display_name, display_name, display_name, invite["id"]),
        ).fetchone()

    with pytest.raises(InviteRedemptionError, match="not available"):
        repository.redeem_invite(
            _hash(raw_invite_token), f"unavailable-session-{uuid4().hex}", 1800
        )

    with postgres_harness.connect() as connection:
        after = connection.execute(
            """
            SELECT
              (SELECT count(*) FROM staff_accounts WHERE display_name = %s),
              (SELECT count(*)
                 FROM hxy_role_assignments AS assignment
                 JOIN staff_accounts AS account ON account.id = assignment.account_id
                WHERE account.display_name = %s),
              (SELECT count(*)
                 FROM staff_sessions AS session
                 JOIN staff_accounts AS account ON account.id = session.account_id
                WHERE account.display_name = %s),
              (SELECT count(*) FROM hxy_member_invite_events WHERE invite_id = %s)
            """,
            (display_name, display_name, display_name, invite["id"]),
        ).fetchone()
    assert after == before


def test_late_session_conflict_rolls_back_entire_redemption(
    postgres_harness: PostgresHarness,
) -> None:
    scenario = _seed_scenario(postgres_harness)
    repository = postgres_harness.repository()
    raw_invite_token = f"late-conflict-invite-{uuid4().hex}"
    raw_session_token = f"late-conflict-session-{uuid4().hex}"
    display_name = f"Late conflict manager {uuid4().hex}"
    invite = _create_invite(
        repository,
        scenario,
        raw_token=raw_invite_token,
        display_name=display_name,
    )
    with postgres_harness.connect() as connection:
        connection.execute(
            """
            INSERT INTO staff_sessions (
              token_hash, account_id, assignment_id, expires_at
            )
            VALUES (%s, %s, %s, NOW() + INTERVAL '1 hour')
            """,
            (
                _hash(raw_session_token),
                scenario.founder.account_id,
                scenario.founder.assignment_id,
            ),
        )

    with pytest.raises(InviteRedemptionError, match="not available"):
        repository.redeem_invite(
            _hash(raw_invite_token), raw_session_token, 1800
        )

    with postgres_harness.connect() as connection:
        persisted = connection.execute(
            """
            SELECT invite.status,
                   invite.redeemed_account_id,
                   invite.redeemed_assignment_id,
                   (SELECT count(*)
                      FROM staff_accounts
                     WHERE display_name = %s),
                   (SELECT count(*)
                      FROM hxy_role_assignments AS assignment
                      JOIN staff_accounts AS account
                        ON account.id = assignment.account_id
                     WHERE account.display_name = %s),
                   (SELECT count(*)
                      FROM hxy_member_invite_events
                     WHERE invite_id = invite.invite_id),
                   (SELECT count(*)
                      FROM staff_sessions
                     WHERE token_hash = %s)
            FROM hxy_member_invites AS invite
            WHERE invite.invite_id = %s
            """,
            (
                display_name,
                display_name,
                _hash(raw_session_token),
                invite["id"],
            ),
        ).fetchone()
    assert persisted == ("pending", None, None, 0, 0, 1, 1)


def test_direct_manager_cross_store_writes_are_rejected(
    postgres_harness: PostgresHarness,
) -> None:
    scenario = _seed_scenario(postgres_harness)
    repository = postgres_harness.repository()
    rejected_raw_token = f"cross-store-create-{uuid4().hex}"

    with pytest.raises(OnboardingScopeError, match="not available"):
        _create_invite(
            repository,
            scenario,
            raw_token=rejected_raw_token,
            display_name="Cross-store create rejected",
            role="store_employee",
            store_id=scenario.store_b,
            creator=scenario.manager_a,
        )

    revocable = _create_invite(
        repository,
        scenario,
        raw_token=f"cross-store-revoke-{uuid4().hex}",
        display_name="Cross-store revoke rejected",
        role="store_employee",
        store_id=scenario.store_b,
        creator=scenario.manager_b,
    )
    assert (
        repository.revoke_invite(
            str(scenario.organization_id),
            scenario.store_b,
            str(scenario.manager_a.assignment_id),
            revocable["id"],
        )
        is None
    )

    with postgres_harness.connect() as connection:
        target = _insert_identity(
            connection,
            organization_id=scenario.organization_id,
            store_id=scenario.store_b,
            assignment_role="store_employee",
            account_role="frontdesk",
            display_name="Cross-store deactivate rejected",
        )
        target_session_hash = _hash(f"cross-store-target-session-{uuid4().hex}")
        connection.execute(
            """
            INSERT INTO staff_sessions (
              token_hash, account_id, assignment_id, expires_at
            )
            VALUES (%s, %s, %s, NOW() + INTERVAL '1 hour')
            """,
            (target_session_hash, target.account_id, target.assignment_id),
        )

    assert (
        repository.deactivate_member(
            str(scenario.organization_id),
            scenario.store_b,
            str(scenario.manager_a.assignment_id),
            str(target.assignment_id),
        )
        is None
    )

    with postgres_harness.connect() as connection:
        persisted = connection.execute(
            """
            SELECT
              (SELECT count(*)
                 FROM hxy_member_invites
                WHERE token_hash = %s),
              (SELECT status
                 FROM hxy_member_invites
                WHERE invite_id = %s),
              (SELECT status
                 FROM hxy_role_assignments
                WHERE assignment_id = %s),
              (SELECT count(*)
                 FROM staff_sessions
                WHERE token_hash = %s),
              (SELECT count(*)
                 FROM hxy_member_invite_events
                WHERE actor_assignment_id = %s
                  AND store_id = %s)
            """,
            (
                _hash(rejected_raw_token),
                revocable["id"],
                target.assignment_id,
                target_session_hash,
                scenario.manager_a.assignment_id,
                scenario.store_b,
            ),
        ).fetchone()
    assert persisted == (0, "pending", "active", 1, 0)


@pytest.mark.parametrize("state_change", ("creator_inactive", "store_closed"))
def test_state_change_race_prevents_redemption(
    postgres_harness: PostgresHarness,
    state_change: str,
) -> None:
    scenario = _seed_scenario(postgres_harness)
    application_name = f"hxy-onboarding-state-race-test-{uuid4().hex[:8]}"
    repository_url = make_conninfo(
        postgres_harness.database_url,
        connect_timeout=5,
        options=f"-csearch_path={postgres_harness.schema_name},public",
        application_name=application_name,
    )
    repository = TimedOnboardingRepository(repository_url)
    raw_invite_token = f"state-race-invite-{uuid4().hex}"
    display_name = f"State race manager {uuid4().hex}"
    invite = _create_invite(
        repository,
        scenario,
        raw_token=raw_invite_token,
        display_name=display_name,
    )

    with postgres_harness.connect() as blocker:
        if state_change == "creator_inactive":
            blocker.execute(
                "UPDATE hxy_role_assignments SET status = 'inactive' "
                "WHERE assignment_id = %s",
                (scenario.founder.assignment_id,),
            )
        else:
            blocker.execute(
                "UPDATE stores SET status = 'closed' WHERE store_id = %s",
                (scenario.store_a,),
            )

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                repository.redeem_invite,
                _hash(raw_invite_token),
                f"state-race-session-{uuid4().hex}",
                1800,
            )
            _wait_for_lock_waiters(
                postgres_harness,
                application_name=application_name,
                expected=1,
            )
            blocker.commit()
            with pytest.raises(InviteRedemptionError, match="not available"):
                future.result(timeout=10)

    with postgres_harness.connect() as connection:
        persisted = connection.execute(
            """
            SELECT invite.status,
                   invite.redeemed_account_id,
                   invite.redeemed_assignment_id,
                   (SELECT count(*) FROM staff_accounts WHERE display_name = %s),
                   (SELECT count(*)
                      FROM hxy_member_invite_events
                     WHERE invite_id = invite.invite_id)
            FROM hxy_member_invites AS invite
            WHERE invite.invite_id = %s
            """,
            (display_name, invite["id"]),
        ).fetchone()
    assert persisted == ("pending", None, None, 0, 1)


def test_invite_foreign_keys_reject_cross_boundary_identities(
    postgres_harness: PostgresHarness,
) -> None:
    scenario = _seed_scenario(postgres_harness)
    foreign = _seed_scenario(postgres_harness)

    def assert_fk_violation(statement: str, params: tuple[object, ...]) -> None:
        with postgres_harness.connect() as connection:
            with pytest.raises(psycopg.errors.ForeignKeyViolation):
                connection.execute(statement, params)

    pending_insert = """
        INSERT INTO hxy_member_invites (
          organization_id, store_id, role, display_name,
          token_hash, created_by_assignment_id, expires_at
        )
        VALUES (%s, %s, 'store_manager', %s, %s, %s,
                NOW() + INTERVAL '1 hour')
    """
    assert_fk_violation(
        pending_insert,
        (
            scenario.organization_id,
            foreign.store_a,
            "Foreign store rejected",
            _hash(f"foreign-store-{uuid4().hex}"),
            scenario.founder.assignment_id,
        ),
    )
    assert_fk_violation(
        pending_insert,
        (
            foreign.organization_id,
            scenario.store_a,
            "Foreign organization rejected",
            _hash(f"foreign-org-{uuid4().hex}"),
            foreign.founder.assignment_id,
        ),
    )
    assert_fk_violation(
        pending_insert,
        (
            scenario.organization_id,
            scenario.store_a,
            "Foreign creator rejected",
            _hash(f"foreign-creator-{uuid4().hex}"),
            foreign.founder.assignment_id,
        ),
    )
    assert_fk_violation(
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
            scenario.organization_id,
            scenario.store_a,
            "Cross-store redeemed identity rejected",
            _hash(f"cross-store-redeemed-{uuid4().hex}"),
            scenario.founder.assignment_id,
            scenario.manager_b.account_id,
            scenario.manager_b.assignment_id,
        ),
    )


def test_deactivate_removes_only_target_assignment_sessions(
    postgres_harness: PostgresHarness,
) -> None:
    scenario = _seed_scenario(postgres_harness)
    repository = postgres_harness.repository()
    raw_invite_token = f"deactivate-invite-{uuid4().hex}"
    first_raw_session = f"deactivate-session-a-{uuid4().hex}"
    invite = _create_invite(
        repository,
        scenario,
        raw_token=raw_invite_token,
        display_name="Deactivate employee",
        role="store_employee",
        creator=scenario.manager_a,
    )
    member = repository.redeem_invite(
        _hash(raw_invite_token), first_raw_session, 1800
    )
    target_assignment_id = UUID(member["assignment_id"])
    second_target_hash = _hash(f"deactivate-session-b-{uuid4().hex}")
    actor_session_hash = _hash(f"deactivate-actor-session-{uuid4().hex}")

    with postgres_harness.connect() as connection:
        target_account_id = connection.execute(
            "SELECT account_id FROM hxy_role_assignments WHERE assignment_id = %s",
            (target_assignment_id,),
        ).fetchone()[0]
        with connection.cursor() as cursor:
            cursor.executemany(
                """
                INSERT INTO staff_sessions (
                  token_hash, account_id, assignment_id, expires_at
                )
                VALUES (%s, %s, %s, NOW() + INTERVAL '1 hour')
                """,
                (
                    (second_target_hash, target_account_id, target_assignment_id),
                    (
                        actor_session_hash,
                        scenario.manager_a.account_id,
                        scenario.manager_a.assignment_id,
                    ),
                ),
            )

    deactivated = repository.deactivate_member(
        str(scenario.organization_id),
        scenario.store_a,
        str(scenario.manager_a.assignment_id),
        str(target_assignment_id),
    )
    assert deactivated is not None
    assert deactivated["status"] == "inactive"

    with postgres_harness.connect() as connection:
        persisted = connection.execute(
            """
            SELECT assignment.status,
                   account.status,
                   (SELECT count(*)
                      FROM staff_sessions
                     WHERE assignment_id = assignment.assignment_id),
                   (SELECT count(*)
                      FROM staff_sessions
                     WHERE assignment_id = %s),
                   event.actor_assignment_id,
                   event.subject_assignment_id,
                   event.event_type
            FROM hxy_role_assignments AS assignment
            JOIN staff_accounts AS account ON account.id = assignment.account_id
            JOIN hxy_member_invite_events AS event
              ON event.subject_assignment_id = assignment.assignment_id
             AND event.event_type = 'member_deactivated'
            WHERE assignment.assignment_id = %s
            """,
            (scenario.manager_a.assignment_id, target_assignment_id),
        ).fetchone()
    assert persisted == (
        "inactive",
        "active",
        0,
        1,
        scenario.manager_a.assignment_id,
        target_assignment_id,
        "member_deactivated",
    )


@pytest.mark.parametrize(
    "mutation",
    (
        "UPDATE hxy_member_invite_events SET payload = '{}'::jsonb "
        "WHERE event_id = %s",
        "DELETE FROM hxy_member_invite_events WHERE event_id = %s",
        "TRUNCATE hxy_member_invite_events",
    ),
)
def test_invite_events_reject_update_delete_and_truncate(
    postgres_harness: PostgresHarness,
    mutation: str,
) -> None:
    scenario = _seed_scenario(postgres_harness)
    repository = postgres_harness.repository()
    invite = _create_invite(
        repository,
        scenario,
        raw_token=f"append-only-{uuid4().hex}",
        display_name="Append-only event",
    )
    with postgres_harness.connect() as connection:
        event_id = connection.execute(
            "SELECT event_id FROM hxy_member_invite_events "
            "WHERE invite_id = %s AND event_type = 'created'",
            (invite["id"],),
        ).fetchone()[0]

    params: tuple[object, ...] = () if mutation.startswith("TRUNCATE") else (event_id,)
    with postgres_harness.connect() as connection:
        with pytest.raises(
            psycopg.errors.RaiseException,
            match="hxy_member_invite_events is append-only",
        ):
            connection.execute(mutation, params)

    with postgres_harness.connect() as connection:
        assert connection.execute(
            "SELECT count(*) FROM hxy_member_invite_events WHERE event_id = %s",
            (event_id,),
        ).fetchone()[0] == 1
