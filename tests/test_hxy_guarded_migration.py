from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

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
FINGERPRINT_DATABASE_URL = (
    "host=db.internal hostaddr=10.20.30.40 port=55433 "
    "dbname=hxy_release_test user=hxy_app password=release-secret-value "
    "options='-c search_path=hxy,public' sslmode=require "
    "sslrootcert=/run/secrets/root.crt sslcert=/run/secrets/client.crt "
    "sslkey=/run/secrets/client.key target_session_attrs=read-write"
)
NOW = datetime(2026, 7, 12, 2, 0, tzinfo=timezone.utc)
GIT_COMMIT = "a" * 40


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
) -> tuple[dict[str, object], RecordingRunner]:
    command_runner = runner or RecordingRunner()
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
    )
    return result, command_runner


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
        "search_path",
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
        FINGERPRINT_DATABASE_URL.replace(
            "search_path=hxy,public",
            "search_path=other,public",
        ),
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
                "search_path=hxy,public",
                "search_path=other,public",
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


def test_backup_preserves_mapped_libpq_connection_semantics(
    release_root: Path,
    tmp_path: Path,
) -> None:
    database_url = (
        "host=db-a,db-b hostaddr=10.0.0.1,10.0.0.2 port=5432,5433 "
        "dbname=hxy_release_test user=hxy_app password=release-secret-value "
        "options='-c search_path=hxy,public' sslmode=verify-full "
        "sslrootcert=/run/secrets/root.crt sslcert=/run/secrets/client.crt "
        "sslkey=/run/secrets/client.key target_session_attrs=read-write "
        "connect_timeout=7 application_name=hxy-release passfile=/run/secrets/pgpass "
        "channel_binding=require load_balance_hosts=random "
        "ssl_min_protocol_version=TLSv1.2 ssl_max_protocol_version=TLSv1.3"
    )

    _result, runner = make_backup(
        release_root,
        tmp_path,
        database_url=database_url,
    )

    expected = {
        "PGHOST": "db-a,db-b",
        "PGHOSTADDR": "10.0.0.1,10.0.0.2",
        "PGPORT": "5432,5433",
        "PGDATABASE": "hxy_release_test",
        "PGUSER": "hxy_app",
        "PGPASSWORD": "release-secret-value",
        "PGOPTIONS": "-c search_path=hxy,public",
        "PGSSLMODE": "verify-full",
        "PGSSLROOTCERT": "/run/secrets/root.crt",
        "PGSSLCERT": "/run/secrets/client.crt",
        "PGSSLKEY": "/run/secrets/client.key",
        "PGTARGETSESSIONATTRS": "read-write",
        "PGCONNECT_TIMEOUT": "7",
        "PGAPPNAME": "hxy-release",
        "PGPASSFILE": "/run/secrets/pgpass",
        "PGCHANNELBINDING": "require",
        "PGLOADBALANCEHOSTS": "random",
        "PGSSLMINPROTOCOLVERSION": "TLSv1.2",
        "PGSSLMAXPROTOCOLVERSION": "TLSv1.3",
    }
    for command, env in runner.calls:
        assert expected.items() <= env.items()
        assert database_url not in " ".join(command)
        assert "release-secret-value" not in " ".join(command)


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
