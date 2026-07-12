from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from apps.api.hxy_release.guarded_migration import (
    MigrationReleaseSpec,
    ReleaseAuthorizationError,
    ReleaseBackupError,
    ReleaseBoundaryError,
    ReleaseExecutionError,
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
    def __init__(self, *, restore_returncode: int = 0, psql_returncode: int = 0) -> None:
        self.restore_returncode = restore_returncode
        self.psql_returncode = psql_returncode
        self.calls: list[tuple[list[str], dict[str, str]]] = []

    def __call__(self, command: list[str], env: dict[str, str]):
        self.calls.append((list(command), dict(env)))
        if command[0] == "pg_dump":
            output = Path(command[command.index("--file") + 1])
            output.write_bytes(b"PGDMP\x01generic-release-backup")
            return subprocess.CompletedProcess(command, 0, "", "")
        if command[0] == "pg_restore":
            return subprocess.CompletedProcess(
                command,
                self.restore_returncode,
                "archive listing" if self.restore_returncode == 0 else "",
                "invalid archive" if self.restore_returncode else "",
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
    tmp_path: Path,
    runner: RecordingRunner | None = None,
) -> tuple[dict[str, object], RecordingRunner]:
    command_runner = runner or RecordingRunner()
    result = create_release_backup(
        SPEC,
        release_root,
        DATABASE_URL,
        output_root=tmp_path / "hxy-backups",
        runner=command_runner,
        now=NOW,
        git_commit=GIT_COMMIT,
        preflight_inspector=passed_inspector,
    )
    return result, command_runner


def test_migration_inventory_is_ordered_and_checksum_bound_to_spec(
    release_root: Path,
) -> None:
    inventory = migration_inventory(SPEC, release_root)

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
    validate_hxy_boundary(release_root, identity)
    with pytest.raises(ReleaseBoundaryError, match="database"):
        validate_hxy_boundary(release_root, identity | {"database": "htops"})
    with pytest.raises(ReleaseBoundaryError, match="root"):
        validate_hxy_boundary(Path("/root/htops"), identity)


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
        "dump": {
            "file": SPEC.dump_filename,
            "size_bytes": dump_path.stat().st_size,
            "sha256": hashlib.sha256(dump_path.read_bytes()).hexdigest(),
            "verified": True,
        },
        "migrations": migration_inventory(SPEC, release_root),
    }
    assert [command[0] for command, _env in runner.calls] == ["pg_dump", "pg_restore"]
    assert manifest_path.parent.stat().st_mode & 0o777 == 0o700
    assert manifest_path.stat().st_mode & 0o777 == 0o600
    assert dump_path.stat().st_mode & 0o777 == 0o600


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
        )
    with pytest.raises(ReleaseBackupError, match="stale"):
        validate_release_backup_manifest(
            SPEC,
            release_root,
            DATABASE_URL,
            manifest_path,
            now=NOW + timedelta(hours=25),
            git_commit=GIT_COMMIT,
        )
    with pytest.raises(ReleaseBackupError, match="Git"):
        validate_release_backup_manifest(
            SPEC,
            release_root,
            DATABASE_URL,
            manifest_path,
            now=NOW,
            git_commit="b" * 40,
        )
    with pytest.raises(ReleaseBackupError, match="database"):
        validate_release_backup_manifest(
            SPEC,
            release_root,
            DATABASE_URL.replace("hxy_release_test", "hxy_other"),
            manifest_path,
            now=NOW,
            git_commit=GIT_COMMIT,
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
        )


def test_backup_requires_passing_preflight(release_root: Path, tmp_path: Path) -> None:
    runner = RecordingRunner()

    with pytest.raises(ReleaseBackupError, match="preflight"):
        create_release_backup(
            SPEC,
            release_root,
            DATABASE_URL,
            output_root=tmp_path / "hxy-backups",
            runner=runner,
            now=NOW,
            git_commit=GIT_COMMIT,
            preflight_inspector=lambda _root, _dsn: {"status": "failed"},
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
            postflight_inspector=lambda _root, _dsn: postflight_calls.append("called"),
        )

    assert postflight_calls == []


def test_apply_raises_when_postflight_fails(release_root: Path, tmp_path: Path) -> None:
    backup, _backup_runner = make_backup(release_root, tmp_path)

    with pytest.raises(ReleaseExecutionError, match="postflight"):
        apply_release_migrations(
            SPEC,
            release_root,
            DATABASE_URL,
            manifest_path=Path(str(backup["manifest_path"])),
            confirmation=SPEC.confirmation,
            runner=RecordingRunner(),
            now=NOW,
            git_commit=GIT_COMMIT,
            postflight_inspector=lambda _root, _dsn: {"status": "failed"},
        )


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
