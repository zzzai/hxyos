from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from psycopg.conninfo import conninfo_to_dict

from apps.api.hxy_release import guarded_migration
from apps.api.hxy_release.guarded_migration import (
    MigrationReleaseSpec,
    ReleaseAuthorizationError,
    ReleaseBackupError,
    ReleaseBoundaryError,
    ReleaseExecutionError,
    ReleasePostflightError,
    apply_release_migrations,
    create_release_backup,
    database_identity,
    migration_inventory,
    render_result,
    validate_hxy_boundary,
    validate_release_backup_manifest,
)


SPEC = MigrationReleaseSpec(
    release_id="test-015-016",
    manifest_version="test-backup.v1",
    migrations=("015.sql", "016.sql"),
    confirmation="APPLY-TEST-015-016",
    advisory_lock="test-015-016",
    dump_filename="before-test.dump",
)
OTHER_SPEC = MigrationReleaseSpec(
    release_id="other-release",
    manifest_version=SPEC.manifest_version,
    migrations=SPEC.migrations,
    confirmation="APPLY-OTHER",
    advisory_lock="other-release",
    dump_filename=SPEC.dump_filename,
)
DATABASE_URL = (
    "host=127.0.0.1 port=55433 dbname=hxy_release_test "
    "user=hxy_app password=release-secret-value"
)
HOSTNAME_DATABASE_URL = (
    "host=db.internal port=55433 dbname=hxy_release_test "
    "user=hxy_app password=release-secret-value sslmode=verify-full"
)
FINGERPRINT_DATABASE_URL = (
    "host=db.internal hostaddr=10.20.30.40 port=55433 "
    "dbname=hxy_release_test user=hxy_app password=release-secret-value "
    "sslmode=require "
    "sslrootcert=/run/secrets/root.crt sslcert=/run/secrets/client.crt "
    "sslkey=/run/secrets/client.key target_session_attrs=read-write"
)
NOW = datetime(2026, 7, 12, 2, 0, tzinfo=timezone.utc)
GIT_COMMIT = "a" * 40
INSTANCE_A = {
    "system_identifier": "7400000000000000001",
    "database_oid": "16384",
    "server_addr": "10.20.30.40",
    "server_port": "55433",
    "database": "hxy_release_test",
    "server_version_num": "160013",
    "server_major": "16",
}
INSTANCE_B = INSTANCE_A | {
    "system_identifier": "7400000000000000002",
    "server_addr": "10.20.30.41",
}
INSTANCE_C = INSTANCE_A | {
    "system_identifier": "7400000000000000003",
    "server_addr": "10.20.30.42",
}
INSTANCE_OTHER_DATABASE_OID = INSTANCE_A | {"database_oid": "16385"}
REAL_DATABASE_INSTANCE_IDENTITY = guarded_migration.database_instance_identity


@pytest.fixture(autouse=True)
def fixed_database_instance(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        guarded_migration,
        "database_instance_identity",
        lambda _database_url: dict(INSTANCE_A),
        raising=False,
    )


@pytest.fixture
def release_root(tmp_path: Path) -> Path:
    root = tmp_path / "hxy"
    migration_dir = root / "data" / "migrations"
    migration_dir.mkdir(parents=True)
    (migration_dir / "014.sql").write_text("SELECT 14;\n", encoding="utf-8")
    (migration_dir / "015.sql").write_text("SELECT 15;\n", encoding="utf-8")
    (migration_dir / "016.sql").write_text("SELECT 16;\n", encoding="utf-8")
    (migration_dir / "017.sql").write_text("SELECT 17;\n", encoding="utf-8")
    return root


class RecordingRunner:
    def __init__(
        self,
        *,
        createdb_returncode: int = 0,
        restore_returncode: int = 0,
        dropdb_returncode: int = 0,
        psql_returncode: int = 0,
    ) -> None:
        self.createdb_returncode = createdb_returncode
        self.restore_returncode = restore_returncode
        self.dropdb_returncode = dropdb_returncode
        self.psql_returncode = psql_returncode
        self.calls: list[tuple[list[str], dict[str, str]]] = []

    def __call__(self, command: list[str], env: dict[str, str]):
        self.calls.append((list(command), dict(env)))
        if command[0] == "pg_dump":
            output = Path(command[command.index("--file") + 1])
            output.write_bytes(b"PGDMP\x01generic-release-backup")
            return subprocess.CompletedProcess(command, 0, "", "")
        if command[0] == "createdb":
            return subprocess.CompletedProcess(
                command,
                self.createdb_returncode,
                "database created" if self.createdb_returncode == 0 else "",
                "create failed" if self.createdb_returncode else "",
            )
        if command[0] == "pg_restore":
            return subprocess.CompletedProcess(
                command,
                self.restore_returncode,
                "archive listing" if self.restore_returncode == 0 else "",
                "invalid archive" if self.restore_returncode else "",
            )
        if command[0] == "dropdb":
            return subprocess.CompletedProcess(
                command,
                self.dropdb_returncode,
                "database dropped" if self.dropdb_returncode == 0 else "",
                "drop failed" if self.dropdb_returncode else "",
            )
        if command[0] == "psql":
            return subprocess.CompletedProcess(
                command,
                self.psql_returncode,
                "migrations applied" if self.psql_returncode == 0 else "",
                "migration failed" if self.psql_returncode else "",
            )
        raise AssertionError(command)


def passed_inspector(_root: Path, _database_url: str) -> dict[str, str]:
    return {"status": "passed"}


def make_backup(
    release_root: Path,
    _tmp_path: Path,
    runner: RecordingRunner | None = None,
    *,
    database_url: str = DATABASE_URL,
    migration_loader=None,
    instance_inspector=None,
) -> tuple[dict[str, object], RecordingRunner]:
    command_runner = runner or RecordingRunner()
    kwargs = {}
    if migration_loader is not None:
        kwargs["migration_loader"] = migration_loader
    if instance_inspector is not None:
        kwargs["instance_inspector"] = instance_inspector
    result = create_release_backup(
        SPEC,
        release_root,
        database_url,
        output_root=release_root / "data" / "backups" / "test-release",
        runner=command_runner,
        now=NOW,
        git_commit=GIT_COMMIT,
        preflight_inspector=passed_inspector,
        trusted_root=release_root,
        **kwargs,
    )
    return result, command_runner


class InstanceSequence:
    def __init__(self, *identities: dict[str, str]) -> None:
        self.identities = iter(identities)
        self.calls = 0
        self.database_urls: list[str] = []

    def __call__(self, database_url: str) -> dict[str, str]:
        self.calls += 1
        self.database_urls.append(database_url)
        return dict(next(self.identities))


def test_migration_inventory_is_ordered_and_checksum_bound_to_spec(
    release_root: Path,
) -> None:
    inventory = migration_inventory(SPEC, release_root, trusted_root=release_root)

    assert inventory == [
        {
            "name": "015.sql",
            "sha256": hashlib.sha256(b"SELECT 15;\n").hexdigest(),
        },
        {
            "name": "016.sql",
            "sha256": hashlib.sha256(b"SELECT 16;\n").hexdigest(),
        },
    ]
    assert all(item["name"] != "014.sql" for item in inventory)


@pytest.mark.parametrize(
    "target_kind",
    ["sibling", "htops"],
)
def test_migration_inventory_rejects_symlinks_before_checksum(
    release_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    target_kind: str,
) -> None:
    migration_path = release_root / "data" / "migrations" / "015.sql"
    migration_path.unlink()
    if target_kind == "sibling":
        target = tmp_path / "outside-015.sql"
        target.write_text("SELECT 15;\n", encoding="utf-8")
    else:
        target = Path("/root/htops/never-read-015.sql")
    migration_path.symlink_to(target)
    checksum_calls: list[Path] = []

    def checksum(path: Path) -> str:
        checksum_calls.append(path)
        return "0" * 64

    monkeypatch.setattr(guarded_migration, "_sha256_file", checksum)

    with pytest.raises(ReleaseBoundaryError, match="regular file"):
        migration_inventory(SPEC, release_root, trusted_root=release_root)

    assert checksum_calls == []


def test_migration_inventory_rejects_non_regular_files_before_checksum(
    release_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration_path = release_root / "data" / "migrations" / "015.sql"
    migration_path.unlink()
    migration_path.mkdir()
    checksum_calls: list[Path] = []

    def checksum(path: Path) -> str:
        checksum_calls.append(path)
        return "0" * 64

    monkeypatch.setattr(guarded_migration, "_sha256_file", checksum)

    with pytest.raises(ReleaseBoundaryError, match="regular file"):
        migration_inventory(SPEC, release_root, trusted_root=release_root)

    assert checksum_calls == []


def test_database_identity_and_boundary_are_hxy_owned_without_credentials(
    release_root: Path,
) -> None:
    identity = database_identity(DATABASE_URL)

    assert identity == {
        "host": "127.0.0.1",
        "port": "55433",
        "database": "hxy_release_test",
        "user": "hxy_app",
    }
    validate_hxy_boundary(release_root, identity, trusted_root=release_root)
    with pytest.raises(ReleaseBoundaryError, match="database"):
        validate_hxy_boundary(
            release_root,
            identity | {"database": "htops"},
            trusted_root=release_root,
        )
    with pytest.raises(ReleaseBoundaryError, match="root"):
        validate_hxy_boundary(Path("/root/htops"), identity)


class FakeIdentityConnection:
    def __init__(self, row: dict[str, str]) -> None:
        self.row = row
        self.read_only = False
        self.sql = ""

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, sql: str):
        assert self.read_only is True
        self.sql = sql
        return self

    def fetchone(self) -> dict[str, str]:
        return self.row


def test_database_instance_identity_requires_control_id_and_database_oid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = FakeIdentityConnection(INSTANCE_A)
    monkeypatch.setattr(
        guarded_migration.psycopg,
        "connect",
        lambda *_args, **_kwargs: connection,
    )

    identity = REAL_DATABASE_INSTANCE_IDENTITY(DATABASE_URL)

    assert identity == INSTANCE_A
    assert "pg_control_system()" in connection.sql
    assert "pg_database" in connection.sql
    assert "database_oid" in connection.sql
    assert "host(inet_server_addr())" in connection.sql


@pytest.mark.parametrize(
    "missing_key",
    [
        "system_identifier",
        "database_oid",
        "server_addr",
        "server_port",
        "database",
        "server_version_num",
        "server_major",
    ],
)
def test_database_instance_identity_fails_closed_when_any_field_is_empty(
    monkeypatch: pytest.MonkeyPatch,
    missing_key: str,
) -> None:
    connection = FakeIdentityConnection(INSTANCE_A | {missing_key: ""})
    monkeypatch.setattr(
        guarded_migration.psycopg,
        "connect",
        lambda *_args, **_kwargs: connection,
    )

    with pytest.raises(ReleaseExecutionError, match="instance"):
        REAL_DATABASE_INSTANCE_IDENTITY(DATABASE_URL)


def test_release_root_requires_real_containment_in_trusted_root(
    release_root: Path,
    tmp_path: Path,
) -> None:
    identity = database_identity(DATABASE_URL)
    sibling = tmp_path / "hxy-sibling"
    sibling.mkdir()
    htops_copy = release_root / "htops-copy"
    htops_copy.mkdir()
    outside = tmp_path / "outside" / "hxy"
    outside.mkdir(parents=True)
    symlink = release_root / "linked-release"
    symlink.symlink_to(outside, target_is_directory=True)

    with pytest.raises(ReleaseBoundaryError, match="root"):
        validate_hxy_boundary(Path("/tmp/hxy"), identity)
    with pytest.raises(ReleaseBoundaryError, match="root"):
        validate_hxy_boundary(sibling, identity, trusted_root=release_root)
    with pytest.raises(ReleaseBoundaryError, match="root"):
        validate_hxy_boundary(htops_copy, identity, trusted_root=release_root)
    with pytest.raises(ReleaseBoundaryError, match="root"):
        validate_hxy_boundary(symlink, identity, trusted_root=release_root)


def test_backup_manifest_binds_release_database_git_and_migrations(
    release_root: Path,
    tmp_path: Path,
) -> None:
    result, runner = make_backup(release_root, tmp_path)

    manifest_path = Path(str(result["manifest_path"]))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    dump_path = manifest_path.parent / SPEC.dump_filename
    assert manifest == {
        "version": SPEC.manifest_version,
        "release_id": SPEC.release_id,
        "created_at": "2026-07-12T02:00:00Z",
        "database": database_identity(DATABASE_URL),
        "git_commit": GIT_COMMIT,
        "connection_fingerprint": manifest["connection_fingerprint"],
        "instance_fingerprint": manifest["instance_fingerprint"],
        "dump": {
            "file": SPEC.dump_filename,
            "size_bytes": dump_path.stat().st_size,
            "sha256": hashlib.sha256(dump_path.read_bytes()).hexdigest(),
            "verified": True,
        },
        "migrations": migration_inventory(
            SPEC,
            release_root,
            trusted_root=release_root,
        ),
    }
    assert [command[0] for command, _env in runner.calls] == [
        "pg_dump",
        "createdb",
        "pg_restore",
        "dropdb",
    ]
    createdb_command = runner.calls[1][0]
    restore_command = runner.calls[2][0]
    dropdb_command = runner.calls[3][0]
    temporary_database = createdb_command[-1]
    assert createdb_command[1] == "--maintenance-db=hxy_release_test"
    assert "--exit-on-error" in restore_command
    assert "--no-owner" in restore_command
    assert "--no-acl" in restore_command
    assert f"--dbname={temporary_database}" in restore_command
    assert dropdb_command == [
        "dropdb",
        "--if-exists",
        "--maintenance-db=hxy_release_test",
        temporary_database,
    ]
    assert manifest_path.parent.stat().st_mode & 0o777 == 0o700
    assert manifest_path.stat().st_mode & 0o777 == 0o600
    assert dump_path.stat().st_mode & 0o777 == 0o600
    assert len(manifest["connection_fingerprint"]) == 64
    assert set(manifest["connection_fingerprint"]) <= set("0123456789abcdef")
    assert len(manifest["instance_fingerprint"]) == 64
    assert INSTANCE_A["system_identifier"] not in manifest_path.read_text(
        encoding="utf-8"
    )


def test_connection_fingerprint_binds_nonsecret_libpq_semantics_without_plaintext(
    release_root: Path,
    tmp_path: Path,
) -> None:
    result, _runner = make_backup(
        release_root,
        tmp_path,
        database_url=FINGERPRINT_DATABASE_URL,
    )

    manifest_path = Path(str(result["manifest_path"]))
    manifest_text = manifest_path.read_text(encoding="utf-8")
    manifest = json.loads(manifest_text)
    assert len(manifest["connection_fingerprint"]) == 64
    for plaintext in (
        "release-secret-value",
        "10.20.30.40",
        "/run/secrets/root.crt",
        "/run/secrets/client.crt",
        "/run/secrets/client.key",
        "read-write",
    ):
        assert plaintext not in manifest_text


@pytest.mark.parametrize(
    "changed_database_url",
    [
        FINGERPRINT_DATABASE_URL.replace("10.20.30.40", "10.20.30.41"),
        FINGERPRINT_DATABASE_URL.replace("sslmode=require", "sslmode=verify-ca"),
        FINGERPRINT_DATABASE_URL.replace(
            "target_session_attrs=read-write",
            "target_session_attrs=primary",
        ),
    ],
)
def test_manifest_rejects_changed_nonsecret_connection_semantics(
    release_root: Path,
    tmp_path: Path,
    changed_database_url: str,
) -> None:
    result, _runner = make_backup(
        release_root,
        tmp_path,
        database_url=FINGERPRINT_DATABASE_URL,
    )

    with pytest.raises(ReleaseBackupError, match="connection fingerprint"):
        validate_release_backup_manifest(
            SPEC,
            release_root,
            changed_database_url,
            Path(str(result["manifest_path"])),
            now=NOW,
            git_commit=GIT_COMMIT,
            trusted_root=release_root,
        )


def test_password_rotation_preserves_connection_fingerprint(
    release_root: Path,
    tmp_path: Path,
) -> None:
    result, _runner = make_backup(
        release_root,
        tmp_path,
        database_url=FINGERPRINT_DATABASE_URL,
    )
    rotated_database_url = FINGERPRINT_DATABASE_URL.replace(
        "release-secret-value",
        "rotated-release-secret",
    )

    validated = validate_release_backup_manifest(
        SPEC,
        release_root,
        rotated_database_url,
        Path(str(result["manifest_path"])),
        now=NOW,
        git_commit=GIT_COMMIT,
        trusted_root=release_root,
    )

    manifest = json.loads(
        Path(str(result["manifest_path"])).read_text(encoding="utf-8")
    )
    assert validated["connection_fingerprint"] == manifest["connection_fingerprint"]


def test_apply_rejects_changed_connection_semantics_before_commands(
    release_root: Path,
    tmp_path: Path,
) -> None:
    result, _runner = make_backup(
        release_root,
        tmp_path,
        database_url=FINGERPRINT_DATABASE_URL,
    )
    runner = RecordingRunner()

    with pytest.raises(ReleaseBackupError, match="connection fingerprint"):
        apply_release_migrations(
            SPEC,
            release_root,
            FINGERPRINT_DATABASE_URL.replace(
                "sslmode=require",
                "sslmode=verify-ca",
            ),
            manifest_path=Path(str(result["manifest_path"])),
            confirmation=SPEC.confirmation,
            runner=runner,
            now=NOW,
            git_commit=GIT_COMMIT,
            postflight_inspector=passed_inspector,
            trusted_root=release_root,
        )

    assert runner.calls == []


def test_backup_pins_subprocesses_to_actual_server_and_controlled_search_path(
    release_root: Path,
    tmp_path: Path,
) -> None:
    database_url = (
        "host=db-a hostaddr=10.0.0.1 port=55433 "
        "dbname=hxy_release_test user=hxy_app password=release-secret-value "
        "sslmode=verify-full "
        "sslrootcert=/run/secrets/root.crt sslcert=/run/secrets/client.crt "
        "sslkey=/run/secrets/client.key target_session_attrs=read-write "
        "connect_timeout=7 application_name=hxy-release passfile=/run/secrets/pgpass "
        "channel_binding=require load_balance_hosts=disable "
        "ssl_min_protocol_version=TLSv1.2 ssl_max_protocol_version=TLSv1.3"
    )

    _result, runner = make_backup(
        release_root,
        tmp_path,
        database_url=database_url,
    )

    expected = {
        "PGHOST": "db-a",
        "PGHOSTADDR": INSTANCE_A["server_addr"],
        "PGPORT": "55433",
        "PGDATABASE": "hxy_release_test",
        "PGUSER": "hxy_app",
        "PGPASSWORD": "release-secret-value",
        "PGOPTIONS": "-c search_path=public",
        "PGSSLMODE": "verify-full",
        "PGSSLROOTCERT": "/run/secrets/root.crt",
        "PGSSLCERT": "/run/secrets/client.crt",
        "PGSSLKEY": "/run/secrets/client.key",
        "PGTARGETSESSIONATTRS": "read-write",
        "PGCONNECT_TIMEOUT": "7",
        "PGAPPNAME": "hxy-release",
        "PGPASSFILE": "/run/secrets/pgpass",
        "PGCHANNELBINDING": "require",
        "PGLOADBALANCEHOSTS": "disable",
        "PGSSLMINPROTOCOLVERSION": "TLSv1.2",
        "PGSSLMAXPROTOCOLVERSION": "TLSv1.3",
    }
    for command, env in runner.calls:
        assert expected.items() <= env.items()
        assert database_url not in " ".join(command)
        assert "release-secret-value" not in " ".join(command)


def test_backup_pins_preflight_and_all_commands_after_initial_hostname_lookup(
    release_root: Path,
) -> None:
    instances = InstanceSequence(INSTANCE_A, INSTANCE_A)
    preflight_urls: list[str] = []
    runner = RecordingRunner()

    create_release_backup(
        SPEC,
        release_root,
        HOSTNAME_DATABASE_URL,
        output_root=release_root / "data" / "backups" / "test-release",
        preflight_inspector=lambda _root, dsn: (
            preflight_urls.append(dsn) or {"status": "passed"}
        ),
        runner=runner,
        now=NOW,
        git_commit=GIT_COMMIT,
        trusted_root=release_root,
        instance_inspector=instances,
    )

    assert "hostaddr" not in conninfo_to_dict(instances.database_urls[0])
    pinned = conninfo_to_dict(preflight_urls[0])
    assert pinned["host"] == "db.internal"
    assert pinned["hostaddr"] == INSTANCE_A["server_addr"]
    assert conninfo_to_dict(instances.database_urls[1])["hostaddr"] == pinned["hostaddr"]
    assert all(env["PGHOST"] == "db.internal" for _command, env in runner.calls)
    assert all(
        env["PGHOSTADDR"] == INSTANCE_A["server_addr"]
        for _command, env in runner.calls
    )


@pytest.mark.parametrize(
    ("catalog_address", "expected_address"),
    [
        ("127.0.0.1/32", "127.0.0.1"),
        ("2001:db8::1/128", "2001:db8::1"),
    ],
)
def test_backup_normalizes_host_cidr_before_pinning_inspectors_and_commands(
    release_root: Path,
    catalog_address: str,
    expected_address: str,
) -> None:
    identity = INSTANCE_A | {"server_addr": catalog_address}
    instances = InstanceSequence(identity, identity)
    preflight_urls: list[str] = []
    runner = RecordingRunner()

    create_release_backup(
        SPEC,
        release_root,
        HOSTNAME_DATABASE_URL,
        output_root=release_root / "data" / "backups" / "test-release",
        preflight_inspector=lambda _root, dsn: (
            preflight_urls.append(dsn) or {"status": "passed"}
        ),
        runner=runner,
        now=NOW,
        git_commit=GIT_COMMIT,
        trusted_root=release_root,
        instance_inspector=instances,
    )

    assert conninfo_to_dict(preflight_urls[0])["hostaddr"] == expected_address
    assert conninfo_to_dict(instances.database_urls[1])["hostaddr"] == expected_address
    assert all(env["PGHOSTADDR"] == expected_address for _command, env in runner.calls)
    assert all("/" not in env["PGHOSTADDR"] for _command, env in runner.calls)


@pytest.mark.parametrize("catalog_address", ["127.0.0.1/24", "2001:db8::1/64"])
def test_backup_rejects_non_host_cidr_server_address(
    release_root: Path,
    catalog_address: str,
) -> None:
    runner = RecordingRunner()
    preflight_calls: list[str] = []

    with pytest.raises(ReleaseBackupError, match="server address"):
        create_release_backup(
            SPEC,
            release_root,
            HOSTNAME_DATABASE_URL,
            output_root=release_root / "data" / "backups" / "test-release",
            preflight_inspector=lambda _root, _dsn: preflight_calls.append("called"),
            runner=runner,
            now=NOW,
            git_commit=GIT_COMMIT,
            trusted_root=release_root,
            instance_inspector=InstanceSequence(
                INSTANCE_A | {"server_addr": catalog_address}
            ),
        )

    assert preflight_calls == []
    assert runner.calls == []


@pytest.mark.parametrize(
    "database_url",
    [
        DATABASE_URL + " service=hxy-prod",
        DATABASE_URL + " servicefile=/run/secrets/pg_service.conf",
    ],
)
def test_backup_rejects_service_based_connection_configuration_before_inspection(
    release_root: Path,
    database_url: str,
) -> None:
    runner = RecordingRunner()
    inspector_calls: list[str] = []

    with pytest.raises(ReleaseExecutionError, match="service"):
        create_release_backup(
            SPEC,
            release_root,
            database_url,
            output_root=release_root / "data" / "backups" / "test-release",
            runner=runner,
            now=NOW,
            git_commit=GIT_COMMIT,
            preflight_inspector=lambda _root, _dsn: inspector_calls.append("called"),
            trusted_root=release_root,
        )

    assert inspector_calls == []
    assert runner.calls == []


@pytest.mark.parametrize(
    "database_url",
    [
        DATABASE_URL.replace("host=127.0.0.1", "host=db-a,db-b"),
        DATABASE_URL + " hostaddr=10.0.0.1,10.0.0.2",
        DATABASE_URL.replace("port=55433", "port=55433,55434"),
        DATABASE_URL + " load_balance_hosts=random",
        DATABASE_URL + " options='-c search_path=private,public'",
    ],
)
def test_backup_rejects_multi_target_and_dsn_options_before_inspection(
    release_root: Path,
    database_url: str,
) -> None:
    runner = RecordingRunner()
    inspector_calls: list[str] = []

    with pytest.raises(ReleaseExecutionError, match="single|options|load_balance"):
        create_release_backup(
            SPEC,
            release_root,
            database_url,
            output_root=release_root / "data" / "backups" / "test-release",
            runner=runner,
            now=NOW,
            git_commit=GIT_COMMIT,
            preflight_inspector=lambda _root, _dsn: inspector_calls.append("called"),
            trusted_root=release_root,
        )

    assert inspector_calls == []
    assert runner.calls == []


@pytest.mark.parametrize(
    "database_url",
    [
        DATABASE_URL.replace("host=127.0.0.1 ", ""),
        DATABASE_URL.replace("port=55433 ", ""),
        DATABASE_URL.replace("dbname=hxy_release_test ", ""),
        DATABASE_URL.replace("user=hxy_app ", ""),
        DATABASE_URL.replace(" password=release-secret-value", ""),
    ],
)
def test_backup_requires_explicit_target_and_authentication_parameters(
    release_root: Path,
    database_url: str,
) -> None:
    runner = RecordingRunner()
    inspector_calls: list[str] = []

    with pytest.raises(ReleaseExecutionError, match="explicit"):
        create_release_backup(
            SPEC,
            release_root,
            database_url,
            output_root=release_root / "data" / "backups" / "test-release",
            runner=runner,
            now=NOW,
            git_commit=GIT_COMMIT,
            preflight_inspector=lambda _root, _dsn: inspector_calls.append("called"),
            trusted_root=release_root,
        )

    assert inspector_calls == []
    assert runner.calls == []


@pytest.mark.parametrize("environment_name", ["PGHOST", "PGOPTIONS", "PGSSLROOTCERT"])
def test_backup_rejects_implicit_libpq_process_environment_before_parsing(
    release_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    environment_name: str,
) -> None:
    monkeypatch.setenv(environment_name, "implicit-value")
    runner = RecordingRunner()
    inspector_calls: list[str] = []

    with pytest.raises(ReleaseExecutionError, match="process environment"):
        create_release_backup(
            SPEC,
            release_root,
            "not-a-valid-connection-string",
            output_root=release_root / "data" / "backups" / "test-release",
            runner=runner,
            now=NOW,
            git_commit=GIT_COMMIT,
            preflight_inspector=lambda _root, _dsn: inspector_calls.append("called"),
            trusted_root=release_root,
        )

    assert inspector_calls == []
    assert runner.calls == []


def test_explicit_passfile_is_accepted_as_authentication(
    release_root: Path,
    tmp_path: Path,
) -> None:
    passfile_database_url = DATABASE_URL.replace(
        "password=release-secret-value",
        "passfile=/run/secrets/pgpass",
    )

    _result, runner = make_backup(
        release_root,
        tmp_path,
        database_url=passfile_database_url,
    )

    for _command, env in runner.calls:
        assert env["PGPASSFILE"] == "/run/secrets/pgpass"
        assert "PGPASSWORD" not in env


def test_backup_rejects_nonempty_libpq_parameters_without_environment_mapping(
    release_root: Path,
) -> None:
    runner = RecordingRunner()

    with pytest.raises(ReleaseExecutionError, match="keepalives"):
        create_release_backup(
            SPEC,
            release_root,
            DATABASE_URL + " keepalives=1",
            output_root=release_root / "data" / "backups" / "test-release",
            runner=runner,
            now=NOW,
            git_commit=GIT_COMMIT,
            preflight_inspector=passed_inspector,
            trusted_root=release_root,
        )

    assert runner.calls == []


def test_backup_restore_failure_still_drops_temporary_database(
    release_root: Path,
    tmp_path: Path,
) -> None:
    runner = RecordingRunner(restore_returncode=1)

    with pytest.raises(ReleaseBackupError, match="restore verification"):
        make_backup(release_root, tmp_path, runner)

    assert [command[0] for command, _env in runner.calls] == [
        "pg_dump",
        "createdb",
        "pg_restore",
        "dropdb",
    ]
    assert runner.calls[1][0][-1] == runner.calls[3][0][-1]
    assert not list((release_root / "data" / "backups").rglob("manifest.json"))


def test_backup_rejects_instance_change_after_pg_dump(
    release_root: Path,
    tmp_path: Path,
) -> None:
    runner = RecordingRunner()

    with pytest.raises(ReleaseBackupError, match="instance"):
        make_backup(
            release_root,
            tmp_path,
            runner,
            instance_inspector=InstanceSequence(INSTANCE_A, INSTANCE_B),
        )

    assert [command[0] for command, _env in runner.calls] == ["pg_dump"]
    assert not list((release_root / "data" / "backups").rglob("manifest.json"))


def test_backup_rejects_empty_system_identifier_before_preflight(
    release_root: Path,
) -> None:
    runner = RecordingRunner()
    preflight_calls: list[str] = []

    with pytest.raises(ReleaseBackupError, match="instance"):
        create_release_backup(
            SPEC,
            release_root,
            DATABASE_URL,
            output_root=release_root / "data" / "backups" / "test-release",
            preflight_inspector=lambda _root, _dsn: preflight_calls.append("called"),
            runner=runner,
            now=NOW,
            git_commit=GIT_COMMIT,
            trusted_root=release_root,
            instance_inspector=InstanceSequence(
                INSTANCE_A | {"system_identifier": ""}
            ),
        )

    assert preflight_calls == []
    assert runner.calls == []


def test_manifest_write_fsyncs_file_then_parent_directory(
    release_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_fsync = os.fsync
    fsync_targets: list[str] = []

    def recording_fsync(file_descriptor: int) -> None:
        mode = os.fstat(file_descriptor).st_mode
        fsync_targets.append("directory" if stat.S_ISDIR(mode) else "file")
        real_fsync(file_descriptor)

    monkeypatch.setattr(guarded_migration.os, "fsync", recording_fsync)

    make_backup(release_root, tmp_path)

    assert fsync_targets == ["file", "directory"]


def test_backup_paths_require_real_containment_under_trusted_backup_root(
    release_root: Path,
    tmp_path: Path,
) -> None:
    runner = RecordingRunner()
    backup_root = release_root / "data" / "backups"
    backup_root.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    symlink_output = backup_root / "linked-output"
    symlink_output.symlink_to(outside, target_is_directory=True)
    rejected_outputs = (
        tmp_path / "hxy-backups",
        backup_root / "htops-copy",
        symlink_output,
    )

    for output_root in rejected_outputs:
        with pytest.raises(ReleaseBoundaryError, match="backup"):
            create_release_backup(
                SPEC,
                release_root,
                DATABASE_URL,
                output_root=output_root,
                runner=runner,
                now=NOW,
                git_commit=GIT_COMMIT,
                preflight_inspector=passed_inspector,
                trusted_root=release_root,
            )

    outside_manifest = outside / "manifest.json"
    outside_manifest.write_text("{}", encoding="utf-8")
    linked_manifest = backup_root / "linked-manifest.json"
    linked_manifest.symlink_to(outside_manifest)
    with pytest.raises(ReleaseBoundaryError, match="backup"):
        validate_release_backup_manifest(
            SPEC,
            release_root,
            DATABASE_URL,
            linked_manifest,
            now=NOW,
            git_commit=GIT_COMMIT,
            trusted_root=release_root,
        )

    assert runner.calls == []


def test_manifest_rejects_another_spec_stale_git_database_or_migrations(
    release_root: Path,
    tmp_path: Path,
) -> None:
    result, _runner = make_backup(release_root, tmp_path)
    manifest_path = Path(str(result["manifest_path"]))

    validated = validate_release_backup_manifest(
        SPEC,
        release_root,
        DATABASE_URL,
        manifest_path,
        now=NOW,
        git_commit=GIT_COMMIT,
        trusted_root=release_root,
    )
    assert validated["status"] == "passed"

    with pytest.raises(ReleaseBackupError, match="release"):
        validate_release_backup_manifest(
            OTHER_SPEC,
            release_root,
            DATABASE_URL,
            manifest_path,
            now=NOW,
            git_commit=GIT_COMMIT,
            trusted_root=release_root,
        )
    with pytest.raises(ReleaseBackupError, match="stale"):
        validate_release_backup_manifest(
            SPEC,
            release_root,
            DATABASE_URL,
            manifest_path,
            now=NOW + timedelta(hours=25),
            git_commit=GIT_COMMIT,
            trusted_root=release_root,
        )
    with pytest.raises(ReleaseBackupError, match="Git"):
        validate_release_backup_manifest(
            SPEC,
            release_root,
            DATABASE_URL,
            manifest_path,
            now=NOW,
            git_commit="b" * 40,
            trusted_root=release_root,
        )
    with pytest.raises(ReleaseBackupError, match="database"):
        validate_release_backup_manifest(
            SPEC,
            release_root,
            DATABASE_URL.replace("hxy_release_test", "hxy_other"),
            manifest_path,
            now=NOW,
            git_commit=GIT_COMMIT,
            trusted_root=release_root,
        )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["migrations"][0]["sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ReleaseBackupError, match="migration"):
        validate_release_backup_manifest(
            SPEC,
            release_root,
            DATABASE_URL,
            manifest_path,
            now=NOW,
            git_commit=GIT_COMMIT,
            trusted_root=release_root,
        )


def test_manifest_rejects_tampered_dump(release_root: Path, tmp_path: Path) -> None:
    result, _runner = make_backup(release_root, tmp_path)
    manifest_path = Path(str(result["manifest_path"]))
    dump_path = manifest_path.parent / SPEC.dump_filename
    original = dump_path.read_bytes()
    dump_path.write_bytes(bytes([original[0] ^ 1]) + original[1:])

    with pytest.raises(ReleaseBackupError, match="checksum"):
        validate_release_backup_manifest(
            SPEC,
            release_root,
            DATABASE_URL,
            manifest_path,
            now=NOW,
            git_commit=GIT_COMMIT,
            trusted_root=release_root,
        )


def test_backup_requires_passing_preflight(release_root: Path, tmp_path: Path) -> None:
    runner = RecordingRunner()

    with pytest.raises(ReleaseBackupError, match="preflight"):
        create_release_backup(
            SPEC,
            release_root,
            DATABASE_URL,
            output_root=release_root / "data" / "backups" / "test-release",
            runner=runner,
            now=NOW,
            git_commit=GIT_COMMIT,
            preflight_inspector=lambda _root, _dsn: {"status": "failed"},
            trusted_root=release_root,
        )

    assert runner.calls == []


@pytest.mark.parametrize(
    "confirmation",
    ["", "yes", "APPLY-TEST", "apply-test-015-016", " APPLY-TEST-015-016"],
)
def test_apply_requires_the_exact_confirmation_before_running_commands(
    release_root: Path,
    tmp_path: Path,
    confirmation: str,
) -> None:
    backup, _backup_runner = make_backup(release_root, tmp_path)
    runner = RecordingRunner()

    with pytest.raises(ReleaseAuthorizationError, match="confirmation"):
        apply_release_migrations(
            SPEC,
            release_root,
            DATABASE_URL,
            manifest_path=Path(str(backup["manifest_path"])),
            confirmation=confirmation,
            runner=runner,
            now=NOW,
            git_commit=GIT_COMMIT,
            trusted_root=release_root,
            postflight_inspector=passed_inspector,
        )

    assert runner.calls == []


def test_apply_uses_one_locked_transaction_and_only_profile_migrations(
    release_root: Path,
    tmp_path: Path,
) -> None:
    backup, _backup_runner = make_backup(release_root, tmp_path)
    runner = RecordingRunner()

    result = apply_release_migrations(
        SPEC,
        release_root,
        DATABASE_URL,
        manifest_path=Path(str(backup["manifest_path"])),
        confirmation=SPEC.confirmation,
        runner=runner,
        now=NOW,
        git_commit=GIT_COMMIT,
        trusted_root=release_root,
        postflight_inspector=passed_inspector,
    )

    assert result["status"] == "passed"
    assert [command[0] for command, _env in runner.calls] == ["pg_restore", "psql"]
    command, env = runner.calls[1]
    command_text = " ".join(command)
    assert command[0] == "psql"
    assert "--single-transaction" in command
    assert "ON_ERROR_STOP=1" in command_text
    assert command_text.count("pg_advisory_xact_lock") == 1
    assert SPEC.advisory_lock in command_text
    assert [
        Path(command[index + 1]).name
        for index, value in enumerate(command)
        if value == "--file"
    ] == list(SPEC.migrations)
    assert "014.sql" not in command_text
    assert "017.sql" not in command_text
    assert DATABASE_URL not in command_text
    assert "release-secret-value" not in command_text
    assert env["PGPASSWORD"] == "release-secret-value"
    assert "HXY_DATABASE_URL" not in env


@pytest.mark.parametrize(
    ("instances", "expected_commands", "postflight_calls"),
    [
        ((INSTANCE_B,), [], 0),
        ((INSTANCE_A, INSTANCE_A, INSTANCE_B), ["pg_restore", "psql"], 0),
        ((INSTANCE_A, INSTANCE_A, INSTANCE_A, INSTANCE_C), ["pg_restore", "psql"], 1),
    ],
)
def test_apply_rejects_instance_changes_before_after_and_after_postflight(
    release_root: Path,
    tmp_path: Path,
    instances: tuple[dict[str, str], ...],
    expected_commands: list[str],
    postflight_calls: int,
) -> None:
    backup, _backup_runner = make_backup(release_root, tmp_path)
    runner = RecordingRunner()
    calls: list[str] = []

    with pytest.raises(ReleaseExecutionError, match="instance"):
        apply_release_migrations(
            SPEC,
            release_root,
            DATABASE_URL,
            manifest_path=Path(str(backup["manifest_path"])),
            confirmation=SPEC.confirmation,
            runner=runner,
            now=NOW,
            git_commit=GIT_COMMIT,
            trusted_root=release_root,
            postflight_inspector=lambda _root, _dsn: (
                calls.append("postflight") or {"status": "passed"}
            ),
            instance_inspector=InstanceSequence(*instances),
        )

    assert [command[0] for command, _env in runner.calls] == expected_commands
    assert len(calls) == postflight_calls


def test_apply_rejects_same_cluster_with_different_database_oid_before_commands(
    release_root: Path,
    tmp_path: Path,
) -> None:
    backup, _backup_runner = make_backup(release_root, tmp_path)
    runner = RecordingRunner()

    with pytest.raises(ReleaseExecutionError, match="instance"):
        apply_release_migrations(
            SPEC,
            release_root,
            DATABASE_URL,
            manifest_path=Path(str(backup["manifest_path"])),
            confirmation=SPEC.confirmation,
            runner=runner,
            now=NOW,
            git_commit=GIT_COMMIT,
            trusted_root=release_root,
            postflight_inspector=passed_inspector,
            instance_inspector=InstanceSequence(INSTANCE_OTHER_DATABASE_OID),
        )

    assert runner.calls == []


def test_apply_pins_postflight_and_instance_checks_to_initial_hostname_target(
    release_root: Path,
    tmp_path: Path,
) -> None:
    backup, _backup_runner = make_backup(
        release_root,
        tmp_path,
        database_url=HOSTNAME_DATABASE_URL,
    )
    instances = InstanceSequence(INSTANCE_A, INSTANCE_A, INSTANCE_A, INSTANCE_A)
    postflight_urls: list[str] = []

    result = apply_release_migrations(
        SPEC,
        release_root,
        HOSTNAME_DATABASE_URL,
        manifest_path=Path(str(backup["manifest_path"])),
        confirmation=SPEC.confirmation,
        runner=RecordingRunner(),
        now=NOW,
        git_commit=GIT_COMMIT,
        trusted_root=release_root,
        postflight_inspector=lambda _root, dsn: (
            postflight_urls.append(dsn) or {"status": "passed"}
        ),
        instance_inspector=instances,
    )

    assert result["status"] == "passed"
    assert "hostaddr" not in conninfo_to_dict(instances.database_urls[0])
    pinned_hostaddrs = [
        conninfo_to_dict(dsn).get("hostaddr")
        for dsn in instances.database_urls[1:] + postflight_urls
    ]
    assert pinned_hostaddrs == [INSTANCE_A["server_addr"]] * 4


def test_apply_executes_verified_loader_bytes_from_private_temporary_snapshots(
    release_root: Path,
    tmp_path: Path,
) -> None:
    head_blobs = {
        "015.sql": b"SELECT 'HEAD-15';\n",
        "016.sql": b"SELECT 'HEAD-16';\n",
    }

    def loader(_root: Path, name: str) -> bytes:
        return head_blobs[name]

    backup, _backup_runner = make_backup(
        release_root,
        tmp_path,
        migration_loader=loader,
    )
    manifest = json.loads(
        Path(str(backup["manifest_path"])).read_text(encoding="utf-8")
    )
    assert manifest["migrations"] == [
        {"name": name, "sha256": hashlib.sha256(blob).hexdigest()}
        for name, blob in head_blobs.items()
    ]

    snapshot_paths: list[Path] = []

    def runner(command: list[str], env: dict[str, str]):
        if command[0] == "pg_restore":
            return subprocess.CompletedProcess(command, 0, "archive listing", "")
        if command[0] == "psql":
            paths = [
                Path(command[index + 1])
                for index, value in enumerate(command)
                if value == "--file"
            ]
            snapshot_paths.extend(paths)
            assert [path.read_bytes() for path in paths] == list(head_blobs.values())
            assert all(path.stat().st_mode & 0o777 == 0o600 for path in paths)
            assert all(path.parent.stat().st_mode & 0o777 == 0o700 for path in paths)
            (release_root / "data" / "migrations" / "015.sql").write_text(
                "SELECT 'WORKTREE-REPLACED';\n",
                encoding="utf-8",
            )
            return subprocess.CompletedProcess(command, 0, "migrations applied", "")
        raise AssertionError(command)

    result = apply_release_migrations(
        SPEC,
        release_root,
        DATABASE_URL,
        manifest_path=Path(str(backup["manifest_path"])),
        confirmation=SPEC.confirmation,
        runner=runner,
        now=NOW,
        git_commit=GIT_COMMIT,
        trusted_root=release_root,
        postflight_inspector=passed_inspector,
        migration_loader=loader,
    )

    assert result["status"] == "passed"
    assert snapshot_paths
    assert all(not path.exists() for path in snapshot_paths)
    temporary_root = release_root / "data" / "release-tmp"
    assert temporary_root.is_dir()
    assert not list(temporary_root.iterdir())


def test_apply_uses_trusted_data_root_when_release_tree_is_sealed(
    tmp_path: Path,
) -> None:
    trusted_root = tmp_path / "hxy"
    release_root = trusted_root / ".worktrees" / "sealed-release"
    migration_dir = release_root / "data" / "migrations"
    migration_dir.mkdir(parents=True)
    (migration_dir / "015.sql").write_text("SELECT 15;\n", encoding="utf-8")
    (migration_dir / "016.sql").write_text("SELECT 16;\n", encoding="utf-8")
    backup = create_release_backup(
        SPEC,
        release_root,
        DATABASE_URL,
        output_root=trusted_root / "data" / "backups" / "test-release",
        preflight_inspector=passed_inspector,
        runner=RecordingRunner(),
        now=NOW,
        git_commit=GIT_COMMIT,
        trusted_root=trusted_root,
    )
    release_data = release_root / "data"
    release_data.chmod(0o555)
    runner = RecordingRunner()
    try:
        result = apply_release_migrations(
            SPEC,
            release_root,
            DATABASE_URL,
            manifest_path=Path(str(backup["manifest_path"])),
            confirmation=SPEC.confirmation,
            runner=runner,
            now=NOW,
            git_commit=GIT_COMMIT,
            trusted_root=trusted_root,
            postflight_inspector=passed_inspector,
        )
    finally:
        release_data.chmod(0o755)

    assert result["status"] == "passed"
    psql_command = next(command for command, _env in runner.calls if command[0] == "psql")
    snapshot_paths = [
        Path(psql_command[index + 1])
        for index, value in enumerate(psql_command)
        if value == "--file"
    ]
    temporary_root = trusted_root / "data" / "release-tmp"
    assert snapshot_paths
    assert all(path.parent.parent == temporary_root for path in snapshot_paths)
    assert all(not path.exists() for path in snapshot_paths)
    assert temporary_root.is_dir()
    assert not list(temporary_root.iterdir())
    assert not (release_root / "data" / "release-tmp").exists()


def test_apply_rejects_symlinked_trusted_release_temporary_root(
    tmp_path: Path,
) -> None:
    trusted_root = tmp_path / "hxy"
    release_root = trusted_root / ".worktrees" / "release"
    migration_dir = release_root / "data" / "migrations"
    migration_dir.mkdir(parents=True)
    (migration_dir / "015.sql").write_text("SELECT 15;\n", encoding="utf-8")
    (migration_dir / "016.sql").write_text("SELECT 16;\n", encoding="utf-8")
    backup = create_release_backup(
        SPEC,
        release_root,
        DATABASE_URL,
        output_root=trusted_root / "data" / "backups" / "test-release",
        preflight_inspector=passed_inspector,
        runner=RecordingRunner(),
        now=NOW,
        git_commit=GIT_COMMIT,
        trusted_root=trusted_root,
    )
    temporary_root = trusted_root / "data" / "release-tmp"
    outside = tmp_path / "outside"
    outside.mkdir()
    temporary_root.symlink_to(outside, target_is_directory=True)
    runner = RecordingRunner()

    with pytest.raises(ReleaseBoundaryError, match="temporary root"):
        apply_release_migrations(
            SPEC,
            release_root,
            DATABASE_URL,
            manifest_path=Path(str(backup["manifest_path"])),
            confirmation=SPEC.confirmation,
            runner=runner,
            now=NOW,
            git_commit=GIT_COMMIT,
            trusted_root=trusted_root,
            postflight_inspector=passed_inspector,
        )

    assert runner.calls == []


def test_apply_rejects_migration_symlink_before_any_runner_command(
    release_root: Path,
    tmp_path: Path,
) -> None:
    backup, _backup_runner = make_backup(release_root, tmp_path)
    migration_path = release_root / "data" / "migrations" / "015.sql"
    outside_path = tmp_path / "outside-015.sql"
    migration_path.replace(outside_path)
    migration_path.symlink_to(outside_path)
    runner = RecordingRunner()

    with pytest.raises(ReleaseBoundaryError, match="regular file"):
        apply_release_migrations(
            SPEC,
            release_root,
            DATABASE_URL,
            manifest_path=Path(str(backup["manifest_path"])),
            confirmation=SPEC.confirmation,
            runner=runner,
            now=NOW,
            git_commit=GIT_COMMIT,
            trusted_root=release_root,
            postflight_inspector=passed_inspector,
        )

    assert runner.calls == []


def test_apply_stops_on_migration_failure_without_postflight(
    release_root: Path,
    tmp_path: Path,
) -> None:
    backup, _backup_runner = make_backup(release_root, tmp_path)
    runner = RecordingRunner(psql_returncode=1)
    postflight_calls: list[str] = []

    with pytest.raises(ReleaseExecutionError, match="transaction"):
        apply_release_migrations(
            SPEC,
            release_root,
            DATABASE_URL,
            manifest_path=Path(str(backup["manifest_path"])),
            confirmation=SPEC.confirmation,
            runner=runner,
            now=NOW,
            git_commit=GIT_COMMIT,
            trusted_root=release_root,
            postflight_inspector=lambda _root, _dsn: postflight_calls.append("called"),
        )

    assert postflight_calls == []


def test_apply_reports_committed_state_when_postflight_fails(
    release_root: Path,
    tmp_path: Path,
) -> None:
    backup, _backup_runner = make_backup(release_root, tmp_path)
    postflight = {
        "status": "failed",
        "checks": [{"detail": "x" * 2000} for _index in range(150)],
    }

    with pytest.raises(ReleasePostflightError, match="postflight") as raised:
        apply_release_migrations(
            SPEC,
            release_root,
            DATABASE_URL,
            manifest_path=Path(str(backup["manifest_path"])),
            confirmation=SPEC.confirmation,
            runner=RecordingRunner(),
            now=NOW,
            git_commit=GIT_COMMIT,
            trusted_root=release_root,
            postflight_inspector=lambda _root, _dsn: postflight,
        )

    error = raised.value
    assert isinstance(error, ReleaseExecutionError)
    assert error.applied is True
    assert error.postflight["status"] == "failed"
    assert len(error.postflight["checks"]) == 100
    assert len(error.postflight["checks"][0]["detail"]) == 500


def test_render_result_redacts_full_dsn_and_password() -> None:
    rendered = render_result(
        {
            "status": "failed",
            "detail": DATABASE_URL,
            "nested": {"password": "release-secret-value", "long": "x" * 2000},
        },
        sensitive_values=(DATABASE_URL, "release-secret-value"),
    )

    assert DATABASE_URL not in rendered
    assert "release-secret-value" not in rendered
    assert "[redacted]" in rendered
    assert len(json.loads(rendered)["nested"]["long"]) <= 500
