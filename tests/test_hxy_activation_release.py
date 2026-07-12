from __future__ import annotations

import json
import os
import re
import stat
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from apps.api.hxy_release.activation_release import (
    ACTIVATION_MIGRATIONS,
    APPLY_CONFIRMATION,
    ReleaseAuthorizationError,
    ReleaseBackupError,
    ReleaseBoundaryError,
    ReleaseExecutionError,
    ReleasePostflightError,
    apply_activation_migrations,
    build_argument_parser,
    create_backup,
    database_identity,
    migration_inventory,
    render_result,
    run_postflight,
    run_preflight,
    validate_hxy_boundary,
    validate_backup_manifest,
)
from apps.api.hxy_release import activation_release, guarded_migration


ROOT = Path(__file__).resolve().parents[1]
RUNBOOK = ROOT / "docs" / "operations" / "hxy-knowledge-activation-release.md"
GIT_COMMIT = "a" * 40


@pytest.fixture
def activation_root(tmp_path: Path) -> Path:
    root = tmp_path / "hxy"
    migration_dir = root / "data" / "migrations"
    migration_dir.mkdir(parents=True)
    for migration in ACTIVATION_MIGRATIONS:
        source = ROOT / "data" / "migrations" / migration
        (migration_dir / migration).write_bytes(source.read_bytes())
    return root


def test_activation_release_allows_only_migrations_009_through_014() -> None:
    assert ACTIVATION_MIGRATIONS == (
        "009_hxy_product_identity.sql",
        "010_hxy_product_conversations.sql",
        "011_hxy_product_materials.sql",
        "012_hxy_assignment_sessions.sql",
        "013_hxy_material_intake_jobs.sql",
        "014_hxy_knowledge_activation.sql",
    )

    inventory = migration_inventory(ROOT, trusted_root=Path("/root/hxy"))

    assert [item["name"] for item in inventory] == list(ACTIVATION_MIGRATIONS)
    assert all(len(item["sha256"]) == 64 for item in inventory)
    assert all(set(item) == {"name", "sha256"} for item in inventory)


def test_activation_wrapper_requires_an_explicit_trusted_root_for_test_roots(
    activation_root: Path,
) -> None:
    with pytest.raises(ReleaseBoundaryError, match="root"):
        migration_inventory(activation_root)

    inventory = migration_inventory(
        activation_root,
        trusted_root=activation_root,
    )

    assert [item["name"] for item in inventory] == list(ACTIVATION_MIGRATIONS)


def test_database_identity_omits_password_and_complete_dsn() -> None:
    password = "release-secret-value"
    dsn = (
        "host=127.0.0.1 port=55433 dbname=hxy_release_test "
        f"user=hxy_app password={password}"
    )

    identity = database_identity(dsn)
    rendered = json.dumps(identity, ensure_ascii=False)

    assert identity == {
        "host": "127.0.0.1",
        "port": "55433",
        "database": "hxy_release_test",
        "user": "hxy_app",
    }
    assert password not in rendered
    assert "password" not in rendered.lower()
    assert dsn not in rendered


def test_release_boundary_rejects_htops_database_or_root() -> None:
    identity = {
        "host": "127.0.0.1",
        "port": "55433",
        "database": "hxy_release_test",
        "user": "hxy_app",
    }

    validate_hxy_boundary(ROOT, identity, trusted_root=Path("/root/hxy"))

    with pytest.raises(ReleaseBoundaryError, match="database"):
        validate_hxy_boundary(
            ROOT,
            identity | {"database": "htops"},
            trusted_root=Path("/root/hxy"),
        )
    with pytest.raises(ReleaseBoundaryError, match="root"):
        validate_hxy_boundary(Path("/root/htops"), identity)


def test_release_result_redacts_secrets_and_bounds_nested_values() -> None:
    password = "release-secret-value"
    full_dsn = f"host=127.0.0.1 dbname=hxy user=hxy_app password={password}"

    rendered = render_result(
        {
            "status": "passed",
            "detail": full_dsn,
            "nested": {"token": password, "long": "x" * 2000},
        },
        sensitive_values=(password, full_dsn),
    )

    assert password not in rendered
    assert full_dsn not in rendered
    assert "[redacted]" in rendered
    assert len(json.loads(rendered)["nested"]["long"]) <= 500


def test_activation_release_cli_exposes_only_guarded_commands() -> None:
    parser = build_argument_parser()

    for command in ("preflight", "backup", "apply", "postflight"):
        assert parser.parse_args([command]).command == command

    with pytest.raises(SystemExit):
        parser.parse_args(["restore"])

    script = (ROOT / "scripts" / "hxy-activation-release.py").read_text(encoding="utf-8")
    assert "apps.api.hxy_release.activation_release" in script
    assert "htops" not in script.lower()


def test_activation_release_cli_preserves_json_status_and_exit_codes(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("HXY_DATABASE_URL", raising=False)

    assert activation_release.main(["preflight"]) == 2
    failed = json.loads(capsys.readouterr().out)
    assert failed["status"] == "failed"
    assert failed["error"] == "HXY_DATABASE_URL is required"

    monkeypatch.setenv("HXY_DATABASE_URL", DATABASE_URL)
    monkeypatch.setattr(
        activation_release,
        "run_preflight",
        lambda _root, _database_url: {"status": "passed", "phase": "preflight"},
    )

    assert activation_release.main(["preflight"]) == 0
    passed = json.loads(capsys.readouterr().out)
    assert passed == {"phase": "preflight", "status": "passed"}


class FakeResult:
    def __init__(self, *, row: dict[str, Any] | None = None, rows=None) -> None:
        self.row = row
        self.rows = rows or []

    def fetchone(self):
        return self.row

    def fetchall(self):
        return self.rows


class FakeInspectionConnection:
    def __init__(self, *, activated: bool) -> None:
        self.activated = activated
        self.read_only = False
        self.queries: list[str] = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, sql: str, _params=None):
        assert self.read_only is True
        normalized = " ".join(sql.split())
        self.queries.append(normalized)
        if "hxy_release:server" in sql:
            return FakeResult(
                row={
                    "server_version_num": "160013",
                    "database": "hxy_release_test",
                    "user": "hxy_app",
                }
            )
        if "hxy_release:relations" in sql:
            baseline = {"staff_accounts", "stores"}
            activated = {
                "hxy_organizations",
                "hxy_role_assignments",
                "hxy_product_conversations",
                "hxy_product_messages",
                "hxy_product_materials",
                "hxy_material_parser_jobs",
                "hxy_material_artifacts",
                "hxy_material_chunks",
                "hxy_product_answer_traces",
            }
            names = baseline | (activated if self.activated else set())
            return FakeResult(rows=[{"name": name} for name in sorted(names)])
        if "hxy_release:columns" in sql:
            return FakeResult(
                rows=[
                    {
                        "table_name": "staff_sessions",
                        "column_name": "assignment_id",
                    }
                ]
                if self.activated
                else []
            )
        if "hxy_release:constraints" in sql:
            return FakeResult(
                rows=[
                    {
                        "table_name": "staff_sessions",
                        "constraint_type": "f",
                        "definition": (
                            "FOREIGN KEY (assignment_id) "
                            "REFERENCES hxy_role_assignments(assignment_id)"
                        ),
                    },
                    {
                        "table_name": "hxy_product_materials",
                        "constraint_type": "c",
                        "definition": "CHECK ((official_use_allowed = false))",
                    },
                    {
                        "table_name": "hxy_material_artifacts",
                        "constraint_type": "c",
                        "definition": "CHECK ((official_use_allowed = false))",
                    },
                    {
                        "table_name": "hxy_material_chunks",
                        "constraint_type": "c",
                        "definition": "CHECK ((official_use_allowed = false))",
                    },
                    {
                        "table_name": "hxy_material_chunks",
                        "constraint_type": "f",
                        "definition": (
                            "FOREIGN KEY (assignment_id, material_id) "
                            "REFERENCES hxy_product_materials(assignment_id, material_id)"
                        ),
                    },
                    {
                        "table_name": "hxy_product_answer_traces",
                        "constraint_type": "u",
                        "definition": "UNIQUE (assistant_message_id)",
                    },
                ]
            )
        if "hxy_release:indexes" in sql:
            return FakeResult(
                rows=[
                    {"index_name": "idx_hxy_material_chunks_content_trgm"},
                    {"index_name": "idx_staff_sessions_assignment_expires"},
                ]
            )
        raise AssertionError(normalized)


def _inspection_factory(connection: FakeInspectionConnection):
    def connect(_database_url: str):
        return connection

    return connect


def _assert_queries_are_read_only(queries: list[str]) -> None:
    forbidden = re.compile(r"\b(INSERT|UPDATE|DELETE|ALTER|CREATE|DROP|TRUNCATE)\b", re.I)
    assert queries
    assert all(forbidden.search(query) is None for query in queries)


def test_preflight_is_read_only_and_reports_activation_as_pending() -> None:
    connection = FakeInspectionConnection(activated=False)
    result = run_preflight(
        ROOT,
        "host=127.0.0.1 port=55433 dbname=hxy_release_test "
        "user=hxy_app password=release-secret-value",
        connect_factory=_inspection_factory(connection),
    )

    assert result["status"] == "passed"
    assert result["phase"] == "preflight"
    assert result["database"]["database"] == "hxy_release_test"
    assert result["server_major"] == 16
    assert result["pending_tables"] == [
        "hxy_material_artifacts",
        "hxy_material_chunks",
        "hxy_material_parser_jobs",
        "hxy_organizations",
        "hxy_product_answer_traces",
        "hxy_product_conversations",
        "hxy_product_materials",
        "hxy_product_messages",
        "hxy_role_assignments",
    ]
    _assert_queries_are_read_only(connection.queries)


def test_preflight_fails_for_wrong_postgres_major_or_missing_baseline() -> None:
    connection = FakeInspectionConnection(activated=False)

    original_execute = connection.execute

    def execute(sql: str, params=None):
        result = original_execute(sql, params)
        if "hxy_release:server" in sql:
            result.row["server_version_num"] = "150009"
        if "hxy_release:relations" in sql:
            result.rows = [row for row in result.rows if row["name"] != "stores"]
        return result

    connection.execute = execute
    result = run_preflight(
        ROOT,
        "host=127.0.0.1 port=5432 dbname=hxy_release_test "
        "user=hxy_app password=release-secret-value",
        connect_factory=_inspection_factory(connection),
    )

    assert result["status"] == "failed"
    failed = {item["name"] for item in result["checks"] if item["status"] == "failed"}
    assert failed == {"postgres_major", "baseline_tables"}
    _assert_queries_are_read_only(connection.queries)


def test_postflight_requires_governed_activation_schema() -> None:
    connection = FakeInspectionConnection(activated=True)
    result = run_postflight(
        ROOT,
        "host=127.0.0.1 port=55433 dbname=hxy_release_test "
        "user=hxy_app password=release-secret-value",
        connect_factory=_inspection_factory(connection),
    )

    assert result["status"] == "passed"
    assert result["phase"] == "postflight"
    assert result["pending_tables"] == []
    assert all(item["status"] == "passed" for item in result["checks"])
    _assert_queries_are_read_only(connection.queries)


def test_postflight_fails_without_private_chunk_governance() -> None:
    connection = FakeInspectionConnection(activated=True)
    original_execute = connection.execute

    def execute(sql: str, params=None):
        result = original_execute(sql, params)
        if "hxy_release:constraints" in sql:
            result.rows = [
                row
                for row in result.rows
                if not (
                    row["table_name"] == "hxy_material_chunks"
                    and row["constraint_type"] == "c"
                )
            ]
        return result

    connection.execute = execute
    result = run_postflight(
        ROOT,
        "host=127.0.0.1 port=5432 dbname=hxy_release_test "
        "user=hxy_app password=release-secret-value",
        connect_factory=_inspection_factory(connection),
    )

    assert result["status"] == "failed"
    failed = {item["name"] for item in result["checks"] if item["status"] == "failed"}
    assert "private_chunk_non_authority" in failed


def test_postflight_fails_without_assignment_scoped_staff_sessions() -> None:
    connection = FakeInspectionConnection(activated=True)
    original_execute = connection.execute

    def execute(sql: str, params=None):
        result = original_execute(sql, params)
        if "hxy_release:columns" in sql:
            result.rows = []
        return result

    connection.execute = execute
    result = run_postflight(
        ROOT,
        "host=127.0.0.1 port=5432 dbname=hxy_release_test "
        "user=hxy_app password=release-secret-value",
        connect_factory=_inspection_factory(connection),
    )

    assert result["status"] == "failed"
    failed = {item["name"] for item in result["checks"] if item["status"] == "failed"}
    assert "assignment_session_scope" in failed


class FakeCommandRunner:
    def __init__(self, *, restore_returncode: int = 0, psql_returncode: int = 0) -> None:
        self.restore_returncode = restore_returncode
        self.psql_returncode = psql_returncode
        self.calls: list[tuple[list[str], dict[str, str]]] = []

    def __call__(self, command: list[str], env: dict[str, str]):
        self.calls.append((list(command), dict(env)))
        if command[0] == "pg_dump":
            output = Path(command[command.index("--file") + 1])
            output.write_bytes(b"PGDMP\x01verified-test-backup")
            return subprocess.CompletedProcess(command, 0, "", "")
        if command[0] == "pg_restore":
            return subprocess.CompletedProcess(
                command,
                self.restore_returncode,
                "archive listing" if self.restore_returncode == 0 else "",
                "invalid archive" if self.restore_returncode else "",
            )
        if command[0] == "createdb":
            return subprocess.CompletedProcess(command, 0, "database created", "")
        if command[0] == "dropdb":
            return subprocess.CompletedProcess(command, 0, "database dropped", "")
        if command[0] == "psql":
            return subprocess.CompletedProcess(
                command,
                self.psql_returncode,
                "migration applied" if self.psql_returncode == 0 else "",
                "migration failed" if self.psql_returncode else "",
            )
        raise AssertionError(command)


DATABASE_URL = (
    "host=127.0.0.1 port=55433 dbname=hxy_release_test "
    "user=hxy_app password=release-secret-value"
)
NOW = datetime(2026, 7, 11, 2, 0, tzinfo=timezone.utc)


def _passed_preflight(_root: Path, _database_url: str):
    return {"status": "passed", "phase": "preflight"}


def _passed_postflight(_root: Path, _database_url: str):
    return {"status": "passed", "phase": "postflight"}


def _make_backup(release_root: Path, runner: FakeCommandRunner):
    return create_backup(
        release_root,
        DATABASE_URL,
        output_root=release_root / "data" / "backups" / "knowledge-activation",
        runner=runner,
        now=NOW,
        git_commit=GIT_COMMIT,
        preflight_runner=_passed_preflight,
        trusted_root=release_root,
    )


def test_backup_uses_environment_credentials_and_writes_verified_manifest(
    activation_root: Path,
) -> None:
    runner = FakeCommandRunner()

    result = _make_backup(activation_root, runner)

    assert result["status"] == "passed"
    manifest_path = Path(result["manifest_path"])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    dump_path = manifest_path.parent / manifest["dump"]["file"]
    assert manifest["version"] == "hxy-activation-backup.v1"
    assert manifest["database"] == database_identity(DATABASE_URL)
    assert manifest["git_commit"] == GIT_COMMIT
    assert manifest["dump"]["verified"] is True
    assert manifest["dump"]["size_bytes"] == dump_path.stat().st_size
    assert len(manifest["dump"]["sha256"]) == 64
    assert manifest["migrations"] == migration_inventory(
        activation_root,
        trusted_root=activation_root,
    )
    assert manifest_path.parent.stat().st_mode & 0o777 == 0o700
    assert manifest_path.stat().st_mode & 0o777 == 0o600
    assert dump_path.stat().st_mode & 0o777 == 0o600

    for command, env in runner.calls:
        assert "release-secret-value" not in " ".join(command)
        assert env["PGPASSWORD"] == "release-secret-value"
        assert "HXY_DATABASE_URL" not in env
    assert [call[0][0] for call in runner.calls] == [
        "pg_dump",
        "createdb",
        "pg_restore",
        "dropdb",
    ]


def test_backup_inherits_guarded_restore_verification_and_manifest_binding(
    activation_root: Path,
) -> None:
    runner = FakeCommandRunner()

    result = _make_backup(activation_root, runner)

    manifest = json.loads(
        Path(result["manifest_path"]).read_text(encoding="utf-8")
    )
    assert manifest["release"] == "009-014"
    assert manifest["release_id"] == "hxy-knowledge-activation-009-014"
    assert manifest["dump"]["file"] == "hxy-before-activation.dump"
    assert len(manifest["connection_fingerprint"]) == 64
    assert [call[0][0] for call in runner.calls] == [
        "pg_dump",
        "createdb",
        "pg_restore",
        "dropdb",
    ]
    restore_command = runner.calls[2][0]
    assert "--exit-on-error" in restore_command
    assert any(item.startswith("--dbname=hxy_verify_") for item in restore_command)


def test_backup_inherits_guarded_manifest_fsync(
    activation_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_fsync = os.fsync
    fsync_targets: list[str] = []

    def recording_fsync(file_descriptor: int) -> None:
        mode = os.fstat(file_descriptor).st_mode
        fsync_targets.append("directory" if stat.S_ISDIR(mode) else "file")
        real_fsync(file_descriptor)

    monkeypatch.setattr(guarded_migration.os, "fsync", recording_fsync)

    _make_backup(activation_root, FakeCommandRunner())

    assert fsync_targets == ["file", "directory"]


def test_backup_rejects_an_unverifiable_archive(activation_root: Path) -> None:
    runner = FakeCommandRunner(restore_returncode=1)

    with pytest.raises(ReleaseBackupError, match="verification"):
        _make_backup(activation_root, runner)

    assert not list(activation_root.rglob("manifest.json"))


def test_backup_rejects_cross_project_output_path(activation_root: Path) -> None:
    output_root = activation_root / "data" / "backups" / "htops-copy"

    with pytest.raises(ReleaseBoundaryError, match="backup"):
        create_backup(
            activation_root,
            DATABASE_URL,
            output_root=output_root,
            runner=FakeCommandRunner(),
            now=NOW,
            git_commit=GIT_COMMIT,
            preflight_runner=_passed_preflight,
            trusted_root=activation_root,
        )


def test_backup_manifest_rejects_stale_database_or_changed_migrations(
    activation_root: Path,
) -> None:
    result = _make_backup(activation_root, FakeCommandRunner())
    manifest_path = Path(result["manifest_path"])

    validated = validate_backup_manifest(
        activation_root,
        DATABASE_URL,
        manifest_path,
        now=NOW,
        git_commit=GIT_COMMIT,
        trusted_root=activation_root,
    )
    assert validated["status"] == "passed"

    with pytest.raises(ReleaseBackupError, match="stale"):
        validate_backup_manifest(
            activation_root,
            DATABASE_URL,
            manifest_path,
            now=NOW + timedelta(hours=25),
            git_commit=GIT_COMMIT,
            trusted_root=activation_root,
        )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["database"]["database"] = "hxy_other"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ReleaseBackupError, match="database"):
        validate_backup_manifest(
            activation_root,
            DATABASE_URL,
            manifest_path,
            now=NOW,
            git_commit=GIT_COMMIT,
            trusted_root=activation_root,
        )

    manifest["database"] = database_identity(DATABASE_URL)
    manifest["migrations"][0]["sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ReleaseBackupError, match="migration"):
        validate_backup_manifest(
            activation_root,
            DATABASE_URL,
            manifest_path,
            now=NOW,
            git_commit=GIT_COMMIT,
            trusted_root=activation_root,
        )


def test_apply_requires_exact_confirmation_and_matching_backup(
    activation_root: Path,
) -> None:
    backup = _make_backup(activation_root, FakeCommandRunner())
    manifest_path = Path(backup["manifest_path"])

    for confirmation in ("", "yes", "APPLY-HXY", "apply-hxy-009-014"):
        with pytest.raises(ReleaseAuthorizationError, match="confirmation"):
            apply_activation_migrations(
                activation_root,
                DATABASE_URL,
                manifest_path=manifest_path,
                confirmation=confirmation,
                runner=FakeCommandRunner(),
                now=NOW,
                git_commit=GIT_COMMIT,
                postflight_runner=_passed_postflight,
                trusted_root=activation_root,
            )


def test_apply_runs_only_009_014_in_one_locked_transaction(
    activation_root: Path,
) -> None:
    backup = _make_backup(activation_root, FakeCommandRunner())
    runner = FakeCommandRunner()

    result = apply_activation_migrations(
        activation_root,
        DATABASE_URL,
        manifest_path=Path(backup["manifest_path"]),
        confirmation=APPLY_CONFIRMATION,
        runner=runner,
        now=NOW,
        git_commit=GIT_COMMIT,
        postflight_runner=_passed_postflight,
        trusted_root=activation_root,
    )

    assert result["status"] == "passed"
    assert len(runner.calls) == 2
    restore_command, restore_env = runner.calls[0]
    assert restore_command[0:2] == ["pg_restore", "--list"]
    assert "release-secret-value" not in " ".join(restore_command)
    assert restore_env["PGPASSWORD"] == "release-secret-value"

    command, env = runner.calls[1]
    command_text = " ".join(command)
    assert command[0] == "psql"
    assert "--single-transaction" in command
    assert "ON_ERROR_STOP=1" in command_text
    assert "pg_advisory_xact_lock" in command_text
    assert [Path(command[index + 1]).name for index, value in enumerate(command) if value == "--file"] == list(
        ACTIVATION_MIGRATIONS
    )
    assert not any("008_" in value or "015_" in value for value in command)
    assert "systemctl" not in command_text
    assert "release-secret-value" not in command_text
    assert env["PGPASSWORD"] == "release-secret-value"
    assert "HXY_DATABASE_URL" not in env


def test_apply_rejects_backup_that_no_longer_passes_pg_restore(
    activation_root: Path,
) -> None:
    backup = _make_backup(activation_root, FakeCommandRunner())
    runner = FakeCommandRunner(restore_returncode=1)

    with pytest.raises(ReleaseBackupError, match="verification"):
        apply_activation_migrations(
            activation_root,
            DATABASE_URL,
            manifest_path=Path(backup["manifest_path"]),
            confirmation=APPLY_CONFIRMATION,
            runner=runner,
            now=NOW,
            git_commit=GIT_COMMIT,
            postflight_runner=_passed_postflight,
            trusted_root=activation_root,
        )

    assert [command[0] for command, _env in runner.calls] == ["pg_restore"]


def test_apply_rejects_manifest_without_connection_fingerprint_before_commands(
    activation_root: Path,
) -> None:
    backup = _make_backup(activation_root, FakeCommandRunner())
    manifest_path = Path(backup["manifest_path"])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.pop("connection_fingerprint", None)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    runner = FakeCommandRunner()

    with pytest.raises(ReleaseBackupError, match="connection fingerprint"):
        apply_activation_migrations(
            activation_root,
            DATABASE_URL,
            manifest_path=manifest_path,
            confirmation=APPLY_CONFIRMATION,
            runner=runner,
            now=NOW,
            git_commit=GIT_COMMIT,
            postflight_runner=_passed_postflight,
            trusted_root=activation_root,
        )

    assert runner.calls == []


def test_release_subprocesses_do_not_inherit_unrelated_secrets(
    activation_root: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DASHSCOPE_API_KEY", "unrelated-model-secret")
    monkeypatch.setenv("HXY_API_TOKEN", "unrelated-api-secret")
    runner = FakeCommandRunner()

    _make_backup(activation_root, runner)

    for _command, env in runner.calls:
        assert "DASHSCOPE_API_KEY" not in env
        assert "HXY_API_TOKEN" not in env
        assert "unrelated-model-secret" not in env.values()
        assert "unrelated-api-secret" not in env.values()


def test_apply_stops_when_the_migration_transaction_fails(
    activation_root: Path,
) -> None:
    backup = _make_backup(activation_root, FakeCommandRunner())
    runner = FakeCommandRunner(psql_returncode=1)
    postflight_calls: list[str] = []

    def postflight(_root: Path, _database_url: str):
        postflight_calls.append("called")
        return {"status": "passed"}

    with pytest.raises(ReleaseExecutionError, match="transaction"):
        apply_activation_migrations(
            activation_root,
            DATABASE_URL,
            manifest_path=Path(backup["manifest_path"]),
            confirmation=APPLY_CONFIRMATION,
            runner=runner,
            now=NOW,
            git_commit=GIT_COMMIT,
            postflight_runner=postflight,
            trusted_root=activation_root,
        )

    assert postflight_calls == []


def test_apply_reports_committed_state_when_activation_postflight_fails(
    activation_root: Path,
) -> None:
    backup = _make_backup(activation_root, FakeCommandRunner())
    postflight = {"status": "failed", "checks": [{"detail": "x" * 2000}]}

    with pytest.raises(ReleasePostflightError, match="postflight") as raised:
        apply_activation_migrations(
            activation_root,
            DATABASE_URL,
            manifest_path=Path(backup["manifest_path"]),
            confirmation=APPLY_CONFIRMATION,
            runner=FakeCommandRunner(),
            now=NOW,
            git_commit=GIT_COMMIT,
            postflight_runner=lambda _root, _dsn: postflight,
            trusted_root=activation_root,
        )

    assert raised.value.applied is True
    assert raised.value.postflight["status"] == "failed"
    assert len(raised.value.postflight["checks"][0]["detail"]) == 500


def test_activation_release_runbook_has_all_guarded_release_gates() -> None:
    runbook = RUNBOOK.read_text(encoding="utf-8")

    assert "hxy-activation-release.py preflight" in runbook
    assert "hxy-activation-release.py backup" in runbook
    assert "hxy-activation-release.py apply" in runbook
    assert "hxy-activation-release.py postflight" in runbook
    assert APPLY_CONFIRMATION in runbook
    assert "009-014" in runbook
    assert "scripts/apply-db-migrations.sh" in runbook
    assert "仅用于开发/全新数据库初始化" in runbook


def test_activation_release_runbook_starts_api_before_worker_and_checks_isolation() -> None:
    runbook = RUNBOOK.read_text(encoding="utf-8")

    api_start = runbook.index("systemctl start hxy-knowledge-api")
    worker_start = runbook.index("systemctl start hxy-material-worker")
    assert api_start < worker_start
    assert "curl --fail --silent http://127.0.0.1:18081/health" in runbook
    assert "AI 草稿" in runbook
    assert "已批准" in runbook
    assert "另一个 assignment" in runbook
    assert "不能召回" in runbook
    assert "archive" in runbook


def test_activation_release_runbook_has_stop_and_rollback_boundaries() -> None:
    runbook = RUNBOOK.read_text(encoding="utf-8")

    assert "任一 Gate 失败立即停止" in runbook
    assert "先停 worker，再回滚 API 代码" in runbook
    assert "不自动执行数据库恢复" in runbook
    assert "不批准答案卡" in runbook
    assert "不修改核心知识" in runbook
    assert "本手册不执行生产部署" in runbook
    assert "/root/htops" not in runbook
    assert "htops-" not in runbook
