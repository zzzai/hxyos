from __future__ import annotations

import hashlib
import os
import re
import stat
import tempfile
import time
import traceback
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from queue import Queue
from threading import Barrier, local
from typing import Any, Iterator, TextIO
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

import apps.api.hxy_product.onboarding_repository as onboarding_repository_module
from apps.api.hxy_product.onboarding_repository import (
    InviteRedemptionError,
    OnboardingRepository,
    OnboardingScopeError,
)


ROOT = Path(__file__).resolve().parents[1]
DATABASE_NAME_PATTERN = re.compile(r"hxy_onboarding_test_[0-9a-f]{12}\Z")
DATABASE_COMMENT_SENTINEL = "hxy-onboarding-test-only-v1"
RUNNER_ROLE = "hxy_onboarding_test_runner"
CONNECT_TIMEOUT_SECONDS = 5
STATEMENT_TIMEOUT_MS = 15_000
LOCK_TIMEOUT_MS = 5_000
IDLE_TRANSACTION_TIMEOUT_MS = 10_000
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
    if not DATABASE_NAME_PATTERN.fullmatch(database_name):
        raise ValueError(
            "PostgreSQL integration requires a dedicated onboarding test database"
        )
    return database_name


def _require_database_identity(
    *,
    parsed_database_name: str,
    actual_database_name: str,
    database_comment: str | None,
) -> None:
    _require_safe_database_name(parsed_database_name)
    _require_safe_database_name(actual_database_name)
    if actual_database_name != parsed_database_name:
        raise ValueError("parsed and connected database names differ")
    if database_comment != DATABASE_COMMENT_SENTINEL:
        raise ValueError("dedicated onboarding database sentinel is missing")


class _PasswordSecret:
    __slots__ = ("__value",)

    def __init__(self, value: str):
        if "\n" in value or "\r" in value:
            raise ValueError("test database password cannot contain line breaks")
        self.__value = value

    def __repr__(self) -> str:
        return "<database-password redacted>"

    def write_pgpass(
        self,
        stream: TextIO,
        *,
        host: str,
        port: str,
        database_name: str,
        user: str,
    ) -> None:
        fields = (host, port, database_name, user, self.__value)
        escaped = tuple(
            field.replace("\\", "\\\\").replace(":", "\\:")
            for field in fields
        )
        stream.write(":".join(escaped) + "\n")


@dataclass(frozen=True)
class _SafeDatabaseConfig:
    conninfo: str = field(repr=False)
    database_name: str
    host: str
    port: str
    user: str
    password: _PasswordSecret | None = field(repr=False)


def _parse_safe_database_config(database_url: str) -> _SafeDatabaseConfig:
    try:
        parsed = conninfo_to_dict(database_url)
    except psycopg.Error as exc:
        raise ValueError(
            "HXY_TEST_DATABASE_URL is not valid PostgreSQL conninfo"
        ) from exc
    database_name = _require_safe_database_name(parsed.get("dbname", ""))
    password_value = parsed.pop("password", None)
    required_scope = {
        "host": parsed.get("host", ""),
        "port": parsed.get("port", ""),
        "user": parsed.get("user", ""),
    }
    if not password_value or any(not value for value in required_scope.values()):
        raise ValueError(
            "HXY_TEST_DATABASE_URL must include host, port, user, and password"
        )
    for controlled_parameter in (
        "application_name",
        "connect_timeout",
        "options",
        "passfile",
    ):
        parsed.pop(controlled_parameter, None)
    password = _PasswordSecret(password_value) if password_value is not None else None
    return _SafeDatabaseConfig(
        conninfo=make_conninfo(**parsed),
        database_name=database_name,
        host=required_scope["host"],
        port=required_scope["port"],
        user=required_scope["user"],
        password=password,
    )


def require_safe_test_database_url(database_url: str) -> _SafeDatabaseConfig:
    return _parse_safe_database_config(database_url)


@contextmanager
def _temporary_pgpass(config: _SafeDatabaseConfig) -> Iterator[Path]:
    if config.password is None:
        raise ValueError("test database password is required")
    descriptor, raw_path = tempfile.mkstemp(prefix="hxy-onboarding-pgpass-")
    passfile_path = Path(raw_path)
    stream_open = False
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream_open = True
            config.password.write_pgpass(
                stream,
                host=config.host,
                port=config.port,
                database_name=config.database_name,
                user=config.user,
            )
        yield passfile_path
    finally:
        if not stream_open:
            os.close(descriptor)
        passfile_path.unlink(missing_ok=True)


def _make_connection_url(
    base_conninfo: str,
    *,
    passfile_path: Path,
    application_name: str,
    schema_name: str | None = None,
) -> str:
    options = [
        f"-crole={RUNNER_ROLE}",
        f"-cstatement_timeout={STATEMENT_TIMEOUT_MS}",
        f"-clock_timeout={LOCK_TIMEOUT_MS}",
        f"-cidle_in_transaction_session_timeout={IDLE_TRANSACTION_TIMEOUT_MS}",
    ]
    if schema_name is not None:
        options.insert(1, f"-csearch_path={schema_name},public")
    return make_conninfo(
        base_conninfo,
        connect_timeout=CONNECT_TIMEOUT_SECONDS,
        passfile=str(passfile_path),
        options=" ".join(options),
        application_name=application_name,
    )


def _assert_restricted_database_connection(
    connection: psycopg.Connection[Any],
    config: _SafeDatabaseConfig,
) -> None:
    identity = connection.execute(
        """
        SELECT database_record.datname,
               current_user,
               session_user,
               shobj_description(database_record.oid, 'pg_database'),
               role_record.rolcanlogin,
               role_record.rolsuper,
               role_record.rolcreatedb,
               role_record.rolcreaterole,
               role_record.rolreplication
        FROM pg_database AS database_record
        JOIN pg_roles AS role_record ON role_record.rolname = current_user
        WHERE database_record.datname = current_database()
        """
    ).fetchone()
    if identity is None:
        raise AssertionError("database identity query returned no row")
    _require_database_identity(
        parsed_database_name=config.database_name,
        actual_database_name=identity[0],
        database_comment=identity[3],
    )
    if identity[1:] != (
        RUNNER_ROLE,
        config.user,
        DATABASE_COMMENT_SENTINEL,
        False,
        False,
        False,
        False,
        False,
    ):
        raise AssertionError("database connection is not using the restricted runner")

    timeout_settings = connection.execute(
        """
        SELECT current_setting('statement_timeout'),
               current_setting('lock_timeout'),
               current_setting('idle_in_transaction_session_timeout')
        """
    ).fetchone()
    if timeout_settings != ("15s", "5s", "10s"):
        raise AssertionError("database connection timeouts are not enforced")

    explicit_database_grants = connection.execute(
        """
        SELECT database_record.datname, privilege_record.privilege_type
        FROM pg_database AS database_record
        CROSS JOIN LATERAL aclexplode(
          COALESCE(
            database_record.datacl,
            acldefault('d', database_record.datdba)
          )
        ) AS privilege_record
        JOIN pg_roles AS grantee ON grantee.oid = privilege_record.grantee
        WHERE grantee.rolname = current_user
        ORDER BY database_record.datname, privilege_record.privilege_type
        """
    ).fetchall()
    if explicit_database_grants != [
        (config.database_name, "CONNECT"),
        (config.database_name, "CREATE"),
    ]:
        raise AssertionError(
            "runner database grants exceed the dedicated test database"
        )


@dataclass(frozen=True)
class PostgresHarness:
    database_url: str = field(repr=False)
    repository_url: str = field(repr=False)
    control_url: str = field(repr=False)
    passfile_path: Path = field(repr=False)
    database_name: str
    schema_name: str

    def connect(self, *, autocommit: bool = False) -> psycopg.Connection[Any]:
        return psycopg.connect(self.repository_url, autocommit=autocommit)

    def repository(self) -> OnboardingRepository:
        return OnboardingRepository(self.repository_url)

    def connection_url(self, application_name: str) -> str:
        return _make_connection_url(
            self.database_url,
            passfile_path=self.passfile_path,
            application_name=application_name,
            schema_name=self.schema_name,
        )


class _PidRecordingRepository(OnboardingRepository):
    def __init__(self, database_url: str, backend_pids: Queue[int]):
        super().__init__(database_url)
        self.backend_pids = backend_pids

    def connect(self):
        connection = super().connect()
        self.backend_pids.put(connection.info.backend_pid)
        return connection


@pytest.fixture(scope="module")
def postgres_harness() -> PostgresHarness:
    configured_url = os.getenv("HXY_TEST_DATABASE_URL", "").strip()
    if not configured_url:
        pytest.skip("HXY_TEST_DATABASE_URL is not configured")

    config = require_safe_test_database_url(configured_url)
    del configured_url
    with _temporary_pgpass(config) as passfile_path:
        control_url = _make_connection_url(
            config.conninfo,
            passfile_path=passfile_path,
            application_name="hxy-onboarding-postgres-control-test",
        )
        schema_name = f"hxy_onboarding_test_{uuid4().hex}"
        schema_created = False

        try:
            with psycopg.connect(control_url, autocommit=True) as connection:
                _assert_restricted_database_connection(connection, config)
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

            repository_url = _make_connection_url(
                config.conninfo,
                passfile_path=passfile_path,
                application_name="hxy-onboarding-postgres-test",
                schema_name=schema_name,
            )
            harness = PostgresHarness(
                database_url=config.conninfo,
                repository_url=repository_url,
                control_url=control_url,
                passfile_path=passfile_path,
                database_name=config.database_name,
                schema_name=schema_name,
            )
            with harness.connect() as connection:
                _assert_restricted_database_connection(connection, config)
                current_schema = connection.execute(
                    "SELECT current_schema()"
                ).fetchone()[0]
                assert current_schema == schema_name
            yield harness
        finally:
            if schema_created:
                with psycopg.connect(control_url, autocommit=True) as connection:
                    _assert_restricted_database_connection(connection, config)
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
    backend_pids: list[int],
    expected: int,
    timeout_seconds: float = 5.0,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        with psycopg.connect(harness.control_url, autocommit=True) as connection:
            waiting = connection.execute(
                """
                SELECT count(DISTINCT pid)
                FROM pg_locks
                WHERE pid = ANY(%s::integer[])
                  AND NOT granted
                """,
                (backend_pids,),
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
        "postgresql:///hxy_onboarding_test",
        "postgresql:///hxy_onboarding_test_abcdef12345",
        "postgresql:///hxy_onboarding_test_abcdef1234567",
        "postgresql:///hxy_onboarding_test_ABCDEF123456",
        "postgresql:///hxy_onboarding_test_abcdef12345g",
    ),
)
def test_safe_database_helper_rejects_non_hxy_test_names(database_url: str) -> None:
    with pytest.raises(ValueError, match="dedicated onboarding test database"):
        require_safe_test_database_url(database_url)


@pytest.mark.parametrize("database_comment", (None, "", "wrong-test-sentinel"))
def test_database_identity_rejects_missing_or_wrong_sentinel(
    database_comment: str | None,
) -> None:
    database_name = "hxy_onboarding_test_abcdef123456"

    with pytest.raises(ValueError, match="sentinel"):
        _require_database_identity(
            parsed_database_name=database_name,
            actual_database_name=database_name,
            database_comment=database_comment,
        )


def test_connection_config_scopes_pgpass_and_all_timeouts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    full_database_url = (
        "postgresql://sentinel%3Auser:"
        "sentinel%3Apassword%5Cfor-config-test@invalid.example:6543/"
        "hxy_onboarding_test_abcdef123456"
    )
    monkeypatch.setenv("PGPASSFILE", "/tmp/original-config-pgpass")
    monkeypatch.setenv("PGPASSWORD", "original-config-password")
    original_environment = (
        os.environ["PGPASSFILE"],
        os.environ["PGPASSWORD"],
    )
    config = _parse_safe_database_config(full_database_url)

    with _temporary_pgpass(config) as passfile_path:
        if (
            os.environ["PGPASSFILE"],
            os.environ["PGPASSWORD"],
        ) != original_environment:
            pytest.fail("pgpass helper mutated the process password environment")
        expected_line = (
            "invalid.example:6543:hxy_onboarding_test_abcdef123456:"
            "sentinel\\:user:sentinel\\:password\\\\for-config-test\n"
        )
        if passfile_path.read_text(encoding="utf-8") != expected_line:
            pytest.fail("pgpass entry was not scoped to the parsed connection fields")
        connection_url = _make_connection_url(
            config.conninfo,
            passfile_path=passfile_path,
            application_name="hxy-onboarding-config-test",
            schema_name="hxy_onboarding_test_schema",
        )
        parsed_connection = conninfo_to_dict(connection_url)
        assert parsed_connection["connect_timeout"] == "5"
        assert parsed_connection["passfile"] == str(passfile_path)
        assert parsed_connection["application_name"] == "hxy-onboarding-config-test"
        options = parsed_connection["options"]
        for required_option in (
            "-crole=hxy_onboarding_test_runner",
            "-csearch_path=hxy_onboarding_test_schema,public",
            "-cstatement_timeout=15000",
            "-clock_timeout=5000",
            "-cidle_in_transaction_session_timeout=10000",
        ):
            assert required_option in options
        assert "password" not in parsed_connection
        assert "*" not in expected_line
        created_passfile_path = passfile_path

    assert original_environment == (
        os.environ["PGPASSFILE"],
        os.environ["PGPASSWORD"],
    )
    assert not created_passfile_path.exists()


def test_connection_failure_cannot_render_database_password(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel_password = "sentinel-password-not-for-a-database"
    full_database_url = (
        "postgresql://sentinel-user:"
        f"{sentinel_password}@invalid.example:6543/"
        "hxy_onboarding_test_abcdef123456"
    )
    original_passfile = "/tmp/original-pgpass-for-test"
    original_pgpassword = "original-environment-password"
    monkeypatch.setenv("PGPASSFILE", original_passfile)
    monkeypatch.setenv("PGPASSWORD", original_pgpassword)
    observed: dict[str, object] = {}

    def fail_connect(conninfo: str, *args: object, **kwargs: object) -> None:
        parsed_connection = conninfo_to_dict(conninfo)
        passfile_path = Path(parsed_connection["passfile"])
        observed["conninfo"] = conninfo
        observed["passfile_path"] = passfile_path
        observed["passfile_mode"] = stat.S_IMODE(passfile_path.stat().st_mode)
        observed["password_present"] = (
            sentinel_password in passfile_path.read_text(encoding="utf-8")
        )
        observed["password_environment"] = (
            os.environ["PGPASSFILE"],
            os.environ["PGPASSWORD"],
        )
        raise psycopg.OperationalError(f"simulated connection failure for {conninfo}")

    monkeypatch.setattr(psycopg, "connect", fail_connect)
    config = _parse_safe_database_config(full_database_url)
    with _temporary_pgpass(config) as passfile_path:
        connection_url = _make_connection_url(
            config.conninfo,
            passfile_path=passfile_path,
            application_name="hxy-onboarding-failure-test",
        )
        with pytest.raises(psycopg.OperationalError) as captured:
            psycopg.connect(connection_url)
    rendered = "".join(
        (
            str(captured.value),
            repr(captured.value),
            repr(config),
            "".join(traceback.format_exception(captured.value)),
            str(observed.get("conninfo", "")),
        )
    )

    for forbidden in (sentinel_password, full_database_url):
        if forbidden in rendered:
            pytest.fail("database credential appeared in connection failure output")
    observed_conninfo = conninfo_to_dict(str(observed["conninfo"]))
    if "password" in observed_conninfo:
        pytest.fail("password remained in conninfo passed to psycopg")
    assert observed["passfile_mode"] == 0o600
    assert observed["password_present"] is True
    assert observed["password_environment"] == (
        original_passfile,
        original_pgpassword,
    )
    assert os.environ["PGPASSFILE"] == original_passfile
    assert os.environ["PGPASSWORD"] == original_pgpassword
    assert not Path(observed["passfile_path"]).exists()


def test_concurrent_same_invite_redemption_has_one_winner(
    postgres_harness: PostgresHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario = _seed_scenario(postgres_harness)
    application_name = f"hxy-onboarding-concurrency-test-{uuid4().hex[:8]}"
    repository_url = postgres_harness.connection_url(application_name)
    repository = OnboardingRepository(repository_url)
    raw_invite_token = f"invite-{uuid4().hex}"
    display_name = f"Concurrent manager {uuid4().hex}"
    invite = _create_invite(
        repository,
        scenario,
        raw_token=raw_invite_token,
        display_name=display_name,
    )
    backend_pids: Queue[int] = Queue()
    redemption_repository = _PidRecordingRepository(repository_url, backend_pids)
    barrier = Barrier(2)
    attempts = (
        {
            "account_id": uuid4(),
            "assignment_id": uuid4(),
            "raw_session_token": f"session-a-{uuid4().hex}",
        },
        {
            "account_id": uuid4(),
            "assignment_id": uuid4(),
            "raw_session_token": f"session-b-{uuid4().hex}",
        },
    )
    redemption_ids = local()

    def deterministic_uuid4() -> UUID:
        return next(redemption_ids.values)

    monkeypatch.setattr(
        onboarding_repository_module,
        "uuid4",
        deterministic_uuid4,
    )

    def redeem(attempt: dict[str, Any]) -> dict[str, Any]:
        redemption_ids.values = iter(
            (attempt["account_id"], attempt["assignment_id"])
        )
        barrier.wait(timeout=5)
        return redemption_repository.redeem_invite(
            _hash(raw_invite_token), attempt["raw_session_token"], 1800
        )

    with postgres_harness.connect() as blocker:
        blocker.execute(
            "SELECT invite_id FROM hxy_member_invites "
            "WHERE invite_id = %s FOR UPDATE",
            (invite["id"],),
        )
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = (
                executor.submit(redeem, attempts[0]),
                executor.submit(redeem, attempts[1]),
            )
            waiting_backend_pids = [
                backend_pids.get(timeout=5),
                backend_pids.get(timeout=5),
            ]
            _wait_for_lock_waiters(
                postgres_harness,
                backend_pids=waiting_backend_pids,
                expected=2,
            )
            blocker.commit()
            outcomes = [_future_result(future) for future in futures]

    assert sum(isinstance(item, dict) for item in outcomes) == 1
    assert sum(isinstance(item, InviteRedemptionError) for item in outcomes) == 1
    winner_index = next(
        index for index, outcome in enumerate(outcomes) if isinstance(outcome, dict)
    )
    winning_attempt = attempts[winner_index]
    losing_attempt = attempts[1 - winner_index]
    assert outcomes[winner_index]["assignment_id"] == str(
        winning_attempt["assignment_id"]
    )
    attempted_account_ids = [attempt["account_id"] for attempt in attempts]
    attempted_assignment_ids = [attempt["assignment_id"] for attempt in attempts]
    attempted_session_hashes = [
        _hash(attempt["raw_session_token"]) for attempt in attempts
    ]
    with postgres_harness.connect() as connection:
        invite_row = connection.execute(
            """
            SELECT status, redeemed_account_id, redeemed_assignment_id
            FROM hxy_member_invites
            WHERE invite_id = %s
            """,
            (invite["id"],),
        ).fetchone()
        account_rows = connection.execute(
            """
            SELECT id, display_name
            FROM staff_accounts
            WHERE display_name = %s
               OR id = ANY(%s::uuid[])
            ORDER BY id
            """,
            (display_name, attempted_account_ids),
        ).fetchall()
        assignment_rows = connection.execute(
            """
            SELECT assignment_id, account_id
            FROM hxy_role_assignments
            WHERE assignment_id = ANY(%s::uuid[])
               OR account_id = ANY(%s::uuid[])
            ORDER BY assignment_id
            """,
            (attempted_assignment_ids, attempted_account_ids),
        ).fetchall()
        session_rows = connection.execute(
            """
            SELECT token_hash, account_id, assignment_id
            FROM staff_sessions
            WHERE token_hash = ANY(%s::text[])
            ORDER BY token_hash
            """,
            (attempted_session_hashes,),
        ).fetchall()
        redeemed_events = connection.execute(
            """
            SELECT actor_assignment_id, subject_assignment_id
            FROM hxy_member_invite_events
            WHERE invite_id = %s
              AND event_type = 'redeemed'
            """,
            (invite["id"],),
        ).fetchall()
        orphan_counts = connection.execute(
            """
            SELECT
              (SELECT count(*)
                 FROM staff_accounts AS account
                 LEFT JOIN hxy_role_assignments AS assignment
                   ON assignment.account_id = account.id
                WHERE account.id = ANY(%s::uuid[])
                  AND assignment.assignment_id IS NULL),
              (SELECT count(*)
                 FROM hxy_role_assignments AS assignment
                 LEFT JOIN staff_accounts AS account
                   ON account.id = assignment.account_id
                WHERE assignment.assignment_id = ANY(%s::uuid[])
                  AND account.id IS NULL),
              (SELECT count(*)
                 FROM staff_sessions AS session
                 LEFT JOIN staff_accounts AS account
                   ON account.id = session.account_id
                 LEFT JOIN hxy_role_assignments AS assignment
                   ON assignment.assignment_id = session.assignment_id
                WHERE session.token_hash = ANY(%s::text[])
                  AND (account.id IS NULL OR assignment.assignment_id IS NULL))
            """,
            (
                attempted_account_ids,
                attempted_assignment_ids,
                attempted_session_hashes,
            ),
        ).fetchone()

    assert invite_row == (
        "redeemed",
        winning_attempt["account_id"],
        winning_attempt["assignment_id"],
    )
    assert account_rows == [(winning_attempt["account_id"], display_name)]
    assert assignment_rows == [
        (winning_attempt["assignment_id"], winning_attempt["account_id"])
    ]
    assert session_rows == [
        (
            _hash(winning_attempt["raw_session_token"]),
            winning_attempt["account_id"],
            winning_attempt["assignment_id"],
        )
    ]
    assert _hash(losing_attempt["raw_session_token"]) not in {
        row[0] for row in session_rows
    }
    assert redeemed_events == [
        (
            winning_attempt["assignment_id"],
            winning_attempt["assignment_id"],
        )
    ]
    assert orphan_counts == (0, 0, 0)


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
    repository_url = postgres_harness.connection_url(application_name)
    repository = OnboardingRepository(repository_url)
    raw_invite_token = f"state-race-invite-{uuid4().hex}"
    display_name = f"State race manager {uuid4().hex}"
    invite = _create_invite(
        repository,
        scenario,
        raw_token=raw_invite_token,
        display_name=display_name,
    )
    backend_pids: Queue[int] = Queue()
    redemption_repository = _PidRecordingRepository(repository_url, backend_pids)

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
                redemption_repository.redeem_invite,
                _hash(raw_invite_token),
                f"state-race-session-{uuid4().hex}",
                1800,
            )
            waiting_backend_pid = backend_pids.get(timeout=5)
            _wait_for_lock_waiters(
                postgres_harness,
                backend_pids=[waiting_backend_pid],
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
    second_assignment_id = uuid4()
    second_assignment_hash = _hash(f"deactivate-second-assignment-{uuid4().hex}")
    actor_session_hash = _hash(f"deactivate-actor-session-{uuid4().hex}")

    with postgres_harness.connect() as connection:
        target_account_id = connection.execute(
            "SELECT account_id FROM hxy_role_assignments WHERE assignment_id = %s",
            (target_assignment_id,),
        ).fetchone()[0]
        connection.execute(
            """
            INSERT INTO hxy_role_assignments (
              assignment_id, account_id, organization_id, store_id, role
            )
            VALUES (%s, %s, %s, %s, 'store_employee')
            """,
            (
                second_assignment_id,
                target_account_id,
                scenario.organization_id,
                scenario.store_b,
            ),
        )
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
                        second_assignment_hash,
                        target_account_id,
                        second_assignment_id,
                    ),
                    (
                        actor_session_hash,
                        scenario.manager_a.account_id,
                        scenario.manager_a.assignment_id,
                    ),
                ),
            )
        session_counts = connection.execute(
            """
            SELECT
              (SELECT count(*) FROM staff_sessions WHERE assignment_id = %s),
              (SELECT count(*) FROM staff_sessions WHERE assignment_id = %s)
            """,
            (target_assignment_id, second_assignment_id),
        ).fetchone()
    assert session_counts == (2, 1)

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
                   (SELECT status
                      FROM hxy_role_assignments
                     WHERE assignment_id = %s),
                   (SELECT account_id
                      FROM hxy_role_assignments
                     WHERE assignment_id = %s),
                   (SELECT count(*)
                      FROM staff_sessions
                     WHERE assignment_id = %s),
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
            (
                second_assignment_id,
                second_assignment_id,
                second_assignment_id,
                scenario.manager_a.assignment_id,
                target_assignment_id,
            ),
        ).fetchone()
    assert persisted == (
        "inactive",
        "active",
        0,
        "active",
        target_account_id,
        1,
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
