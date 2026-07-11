from __future__ import annotations

import json
import re
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


ROOT = Path(__file__).resolve().parents[1]
RUNBOOK = ROOT / "docs" / "operations" / "hxy-knowledge-activation-release.md"


def test_activation_release_allows_only_migrations_009_through_014() -> None:
    assert ACTIVATION_MIGRATIONS == (
        "009_hxy_product_identity.sql",
        "010_hxy_product_conversations.sql",
        "011_hxy_product_materials.sql",
        "012_hxy_assignment_sessions.sql",
        "013_hxy_material_intake_jobs.sql",
        "014_hxy_knowledge_activation.sql",
    )

    inventory = migration_inventory(ROOT)

    assert [item["name"] for item in inventory] == list(ACTIVATION_MIGRATIONS)
    assert all(len(item["sha256"]) == 64 for item in inventory)
    assert all(set(item) == {"name", "sha256"} for item in inventory)


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

    validate_hxy_boundary(ROOT, identity)

    with pytest.raises(ReleaseBoundaryError, match="database"):
        validate_hxy_boundary(ROOT, identity | {"database": "htops"})
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
        "host=127.0.0.1 port=55433 dbname=hxy_release_test user=hxy_app",
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
        "host=127.0.0.1 dbname=hxy_release_test user=hxy_app",
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
        "host=127.0.0.1 port=55433 dbname=hxy_release_test user=hxy_app",
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
        "host=127.0.0.1 dbname=hxy_release_test user=hxy_app",
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
        "host=127.0.0.1 dbname=hxy_release_test user=hxy_app",
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


def _make_backup(tmp_path: Path, runner: FakeCommandRunner):
    return create_backup(
        ROOT,
        DATABASE_URL,
        output_root=tmp_path,
        runner=runner,
        now=NOW,
        git_commit="a" * 40,
        preflight_runner=_passed_preflight,
    )


def test_backup_uses_environment_credentials_and_writes_verified_manifest(
    tmp_path: Path,
) -> None:
    runner = FakeCommandRunner()

    result = _make_backup(tmp_path, runner)

    assert result["status"] == "passed"
    manifest_path = Path(result["manifest_path"])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    dump_path = manifest_path.parent / manifest["dump"]["file"]
    assert manifest["version"] == "hxy-activation-backup.v1"
    assert manifest["database"] == database_identity(DATABASE_URL)
    assert manifest["git_commit"] == "a" * 40
    assert manifest["dump"]["verified"] is True
    assert manifest["dump"]["size_bytes"] == dump_path.stat().st_size
    assert len(manifest["dump"]["sha256"]) == 64
    assert manifest["migrations"] == migration_inventory(ROOT)
    assert manifest_path.parent.stat().st_mode & 0o777 == 0o700
    assert manifest_path.stat().st_mode & 0o777 == 0o600
    assert dump_path.stat().st_mode & 0o777 == 0o600

    for command, env in runner.calls:
        assert "release-secret-value" not in " ".join(command)
        assert env["PGPASSWORD"] == "release-secret-value"
        assert "HXY_DATABASE_URL" not in env
    assert [call[0][0] for call in runner.calls] == ["pg_dump", "pg_restore"]


def test_backup_rejects_an_unverifiable_archive(tmp_path: Path) -> None:
    runner = FakeCommandRunner(restore_returncode=1)

    with pytest.raises(ReleaseBackupError, match="verification"):
        _make_backup(tmp_path, runner)

    assert not list(tmp_path.rglob("manifest.json"))


def test_backup_rejects_cross_project_output_path(tmp_path: Path) -> None:
    output_root = tmp_path / "htops" / "backups"

    with pytest.raises(ReleaseBoundaryError, match="backup"):
        create_backup(
            ROOT,
            DATABASE_URL,
            output_root=output_root,
            runner=FakeCommandRunner(),
            now=NOW,
            git_commit="a" * 40,
            preflight_runner=_passed_preflight,
        )


def test_backup_manifest_rejects_stale_database_or_changed_migrations(
    tmp_path: Path,
) -> None:
    result = _make_backup(tmp_path, FakeCommandRunner())
    manifest_path = Path(result["manifest_path"])

    validated = validate_backup_manifest(ROOT, DATABASE_URL, manifest_path, now=NOW)
    assert validated["status"] == "passed"

    with pytest.raises(ReleaseBackupError, match="stale"):
        validate_backup_manifest(
            ROOT,
            DATABASE_URL,
            manifest_path,
            now=NOW + timedelta(hours=25),
        )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["database"]["database"] = "hxy_other"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ReleaseBackupError, match="database"):
        validate_backup_manifest(ROOT, DATABASE_URL, manifest_path, now=NOW)

    manifest["database"] = database_identity(DATABASE_URL)
    manifest["migrations"][0]["sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ReleaseBackupError, match="migration"):
        validate_backup_manifest(ROOT, DATABASE_URL, manifest_path, now=NOW)


def test_apply_requires_exact_confirmation_and_matching_backup(tmp_path: Path) -> None:
    backup = _make_backup(tmp_path, FakeCommandRunner())
    manifest_path = Path(backup["manifest_path"])

    for confirmation in ("", "yes", "APPLY-HXY", "apply-hxy-009-014"):
        with pytest.raises(ReleaseAuthorizationError, match="confirmation"):
            apply_activation_migrations(
                ROOT,
                DATABASE_URL,
                manifest_path=manifest_path,
                confirmation=confirmation,
                runner=FakeCommandRunner(),
                now=NOW,
                postflight_runner=_passed_postflight,
            )


def test_apply_runs_only_009_014_in_one_locked_transaction(tmp_path: Path) -> None:
    backup = _make_backup(tmp_path, FakeCommandRunner())
    runner = FakeCommandRunner()

    result = apply_activation_migrations(
        ROOT,
        DATABASE_URL,
        manifest_path=Path(backup["manifest_path"]),
        confirmation=APPLY_CONFIRMATION,
        runner=runner,
        now=NOW,
        postflight_runner=_passed_postflight,
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


def test_apply_rejects_backup_that_no_longer_passes_pg_restore(tmp_path: Path) -> None:
    backup = _make_backup(tmp_path, FakeCommandRunner())
    runner = FakeCommandRunner(restore_returncode=1)

    with pytest.raises(ReleaseBackupError, match="verification"):
        apply_activation_migrations(
            ROOT,
            DATABASE_URL,
            manifest_path=Path(backup["manifest_path"]),
            confirmation=APPLY_CONFIRMATION,
            runner=runner,
            now=NOW,
            postflight_runner=_passed_postflight,
        )

    assert [command[0] for command, _env in runner.calls] == ["pg_restore"]


def test_release_subprocesses_do_not_inherit_unrelated_secrets(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DASHSCOPE_API_KEY", "unrelated-model-secret")
    monkeypatch.setenv("HXY_API_TOKEN", "unrelated-api-secret")
    runner = FakeCommandRunner()

    _make_backup(tmp_path, runner)

    for _command, env in runner.calls:
        assert "DASHSCOPE_API_KEY" not in env
        assert "HXY_API_TOKEN" not in env
        assert "unrelated-model-secret" not in env.values()
        assert "unrelated-api-secret" not in env.values()


def test_apply_stops_when_the_migration_transaction_fails(tmp_path: Path) -> None:
    backup = _make_backup(tmp_path, FakeCommandRunner())
    runner = FakeCommandRunner(psql_returncode=1)
    postflight_calls: list[str] = []

    def postflight(_root: Path, _database_url: str):
        postflight_calls.append("called")
        return {"status": "passed"}

    with pytest.raises(ReleaseExecutionError, match="transaction"):
        apply_activation_migrations(
            ROOT,
            DATABASE_URL,
            manifest_path=Path(backup["manifest_path"]),
            confirmation=APPLY_CONFIRMATION,
            runner=runner,
            now=NOW,
            postflight_runner=postflight,
        )

    assert postflight_calls == []


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
