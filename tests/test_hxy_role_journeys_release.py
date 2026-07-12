from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from apps.api.hxy_release import role_journeys_release
from apps.api.hxy_release.guarded_migration import (
    ReleaseAuthorizationError,
    ReleasePostflightError,
)
from apps.api.hxy_release.role_journeys_release import (
    APPLY_CONFIRMATION,
    BACKUP_VERSION,
    ROLE_JOURNEYS_MIGRATIONS,
    ROLE_JOURNEYS_RELEASE,
    apply_role_journeys_migrations,
    build_argument_parser,
    create_backup,
    migration_inventory,
    run_postflight,
    run_preflight,
)


ROOT = Path(__file__).resolve().parents[1]
DATABASE_URL = (
    "host=127.0.0.1 port=55433 dbname=hxy_release_test "
    "user=hxy_app password=release-secret-value"
)
GIT_COMMIT = "a" * 40
NOW = datetime(2026, 7, 12, 2, 0, tzinfo=timezone.utc)


@pytest.fixture
def release_root(tmp_path: Path) -> Path:
    root = tmp_path / "hxy"
    migration_dir = root / "data" / "migrations"
    migration_dir.mkdir(parents=True)
    for migration in ROLE_JOURNEYS_MIGRATIONS:
        source = ROOT / "data" / "migrations" / migration
        (migration_dir / migration).write_bytes(source.read_bytes())
    return root


def test_release_profile_is_isolated_to_015_and_016() -> None:
    assert ROLE_JOURNEYS_RELEASE.release_id == "hxy-role-journeys-015-016"
    assert BACKUP_VERSION == "hxy-role-journeys-backup.v1"
    assert APPLY_CONFIRMATION == "APPLY-HXY-015-016"
    assert ROLE_JOURNEYS_RELEASE.advisory_lock == "hxy-role-journeys-015-016"
    assert ROLE_JOURNEYS_RELEASE.dump_filename == "hxy-before-role-journeys.dump"
    assert ROLE_JOURNEYS_MIGRATIONS == (
        "015_hxy_product_tasks.sql",
        "016_hxy_product_training.sql",
    )

    inventory = migration_inventory(ROOT, trusted_root=Path("/root/hxy"))

    assert [item["name"] for item in inventory] == list(ROLE_JOURNEYS_MIGRATIONS)
    assert all(len(item["sha256"]) == 64 for item in inventory)


def test_cli_exposes_guarded_commands_and_expected_wrapper() -> None:
    parser = build_argument_parser()

    for command in ("preflight", "backup", "apply", "postflight"):
        assert parser.parse_args([command]).command == command
    with pytest.raises(SystemExit):
        parser.parse_args(["restore"])

    script = (ROOT / "scripts" / "hxy-role-journeys-release.py").read_text(
        encoding="utf-8"
    )
    assert "apps.api.hxy_release.role_journeys_release" in script
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
    def __init__(self, *, released: bool = False) -> None:
        self.released = released
        self.read_only = False
        self.queries: list[str] = []
        self.omit: set[str] = set()
        self.constraint_overrides: dict[str, dict[str, Any]] = {}
        self.trigger_overrides: dict[str, dict[str, Any]] = {}
        self.index_overrides: dict[str, dict[str, Any]] = {}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, sql: str, _params=None):
        assert self.read_only is True
        normalized = " ".join(sql.split())
        self.queries.append(normalized)
        if "hxy_role_release:relations" in sql:
            names = {
                "hxy_product_tasks",
                "hxy_product_task_events",
                "hxy_product_training_sessions",
            }
            if not self.released:
                names = set()
            return FakeResult(rows=[{"name": name} for name in sorted(names - self.omit)])
        if "hxy_role_release:columns" in sql:
            rows = [
                {"table_name": "hxy_product_tasks", "column_name": "parent_task_id"}
            ]
            if "parent_task_id" in self.omit:
                rows = []
            return FakeResult(rows=rows if self.released else [])
        if "hxy_role_release:constraints" in sql:
            rows = []
            for row in _constraint_rows():
                updated = dict(row)
                updated.update(self.constraint_overrides.get(row["marker"], {}))
                rows.append(updated)
            return FakeResult(
                rows=[row for row in rows if row["marker"] not in self.omit]
                if self.released
                else []
            )
        if "hxy_role_release:triggers" in sql:
            rows = []
            for row in _trigger_rows():
                updated = dict(row)
                updated.update(self.trigger_overrides.get(row["trigger_name"], {}))
                rows.append(updated)
            return FakeResult(
                rows=[row for row in rows if row["trigger_name"] not in self.omit]
                if self.released
                else []
            )
        if "hxy_role_release:indexes" in sql:
            rows = []
            for row in _index_rows():
                updated = dict(row)
                updated.update(self.index_overrides.get(row["index_name"], {}))
                rows.append(updated)
            return FakeResult(
                rows=[row for row in rows if row["index_name"] not in self.omit]
                if self.released
                else []
            )
        raise AssertionError(normalized)


def _constraint_rows() -> list[dict[str, str]]:
    definitions = {
        "parent_store": (
            "hxy_product_tasks",
            "FOREIGN KEY (organization_id, store_id, parent_task_id) "
            "REFERENCES hxy_product_tasks(organization_id, store_id, task_id)",
        ),
        "tasks_org_store": (
            "hxy_product_tasks",
            "FOREIGN KEY (organization_id, store_id) "
            "REFERENCES hxy_organization_stores(organization_id, store_id)",
        ),
        "tasks_org": (
            "hxy_product_tasks",
            "FOREIGN KEY (organization_id) "
            "REFERENCES hxy_organizations(organization_id)",
        ),
        "tasks_creator": (
            "hxy_product_tasks",
            "FOREIGN KEY (creator_assignment_id) "
            "REFERENCES hxy_role_assignments(assignment_id)",
        ),
        "tasks_creator_org": (
            "hxy_product_tasks",
            "FOREIGN KEY (organization_id, creator_assignment_id) "
            "REFERENCES hxy_role_assignments(organization_id, assignment_id)",
        ),
        "tasks_assignee": (
            "hxy_product_tasks",
            "FOREIGN KEY (assignee_assignment_id) "
            "REFERENCES hxy_role_assignments(assignment_id)",
        ),
        "tasks_assignee_org": (
            "hxy_product_tasks",
            "FOREIGN KEY (organization_id, assignee_assignment_id) "
            "REFERENCES hxy_role_assignments(organization_id, assignment_id)",
        ),
        "tasks_assignee_store": (
            "hxy_product_tasks",
            "FOREIGN KEY (organization_id, store_id, assignee_assignment_id) "
            "REFERENCES hxy_role_assignments(organization_id, store_id, assignment_id)",
        ),
        "events_task_org": (
            "hxy_product_task_events",
            "FOREIGN KEY (organization_id, task_id) "
            "REFERENCES hxy_product_tasks(organization_id, task_id)",
        ),
        "events_org": (
            "hxy_product_task_events",
            "FOREIGN KEY (organization_id) "
            "REFERENCES hxy_organizations(organization_id)",
        ),
        "events_actor_org": (
            "hxy_product_task_events",
            "FOREIGN KEY (organization_id, actor_assignment_id) "
            "REFERENCES hxy_role_assignments(organization_id, assignment_id)",
        ),
        "training_org_store": (
            "hxy_product_training_sessions",
            "FOREIGN KEY (organization_id, store_id) "
            "REFERENCES hxy_organization_stores(organization_id, store_id)",
        ),
        "training_org": (
            "hxy_product_training_sessions",
            "FOREIGN KEY (organization_id) "
            "REFERENCES hxy_organizations(organization_id)",
        ),
        "training_assignment_org": (
            "hxy_product_training_sessions",
            "FOREIGN KEY (organization_id, assignment_id) "
            "REFERENCES hxy_role_assignments(organization_id, assignment_id)",
        ),
        "training_assignment_store": (
            "hxy_product_training_sessions",
            "FOREIGN KEY (organization_id, store_id, assignment_id) "
            "REFERENCES hxy_role_assignments(organization_id, store_id, assignment_id)",
        ),
    }
    return [
        {
            "marker": marker,
            "table_name": table,
            "constraint_type": "f",
            "definition": definition,
        }
        for marker, (table, definition) in definitions.items()
    ]


def _trigger_rows() -> list[dict[str, str]]:
    return [
        {
            "table_schema": "public",
            "table_name": "hxy_product_task_events",
            "trigger_name": "trg_hxy_product_task_events_append_only",
            "tgenabled": "O",
            "function_schema": "public",
            "function_name": "hxy_reject_task_event_mutation",
            "definition": "CREATE TRIGGER x BEFORE UPDATE OR DELETE ON x FOR EACH ROW",
        },
        {
            "table_schema": "public",
            "table_name": "hxy_product_task_events",
            "trigger_name": "trg_hxy_product_task_events_no_truncate",
            "tgenabled": "O",
            "function_schema": "public",
            "function_name": "hxy_reject_task_event_mutation",
            "definition": "CREATE TRIGGER x BEFORE TRUNCATE ON x FOR EACH STATEMENT",
        },
        {
            "table_schema": "public",
            "table_name": "hxy_product_training_sessions",
            "trigger_name": "trg_hxy_product_training_append_only",
            "tgenabled": "O",
            "function_schema": "public",
            "function_name": "hxy_reject_product_training_mutation",
            "definition": "CREATE TRIGGER x BEFORE UPDATE OR DELETE ON x FOR EACH ROW",
        },
        {
            "table_schema": "public",
            "table_name": "hxy_product_training_sessions",
            "trigger_name": "trg_hxy_product_training_no_truncate",
            "tgenabled": "O",
            "function_schema": "public",
            "function_name": "hxy_reject_product_training_mutation",
            "definition": "CREATE TRIGGER x BEFORE TRUNCATE ON x FOR EACH STATEMENT",
        },
    ]


def _index_rows() -> list[dict[str, Any]]:
    return [
        {
            "table_name": "hxy_product_tasks",
            "index_name": "idx_hxy_product_tasks_assignee_active",
            "index_definition": (
                "CREATE INDEX idx_hxy_product_tasks_assignee_active "
                "ON public.hxy_product_tasks USING btree "
                "(assignee_assignment_id, priority, updated_at DESC)"
            ),
            "indisvalid": True,
            "predicate": (
                "status = ANY (ARRAY['open'::text, 'in_progress'::text])"
            ),
        },
        {
            "table_name": "hxy_product_tasks",
            "index_name": "idx_hxy_product_tasks_store_active",
            "index_definition": (
                "CREATE INDEX idx_hxy_product_tasks_store_active "
                "ON public.hxy_product_tasks USING btree "
                "(organization_id, store_id, priority, updated_at DESC)"
            ),
            "indisvalid": True,
            "predicate": (
                "(visibility = 'store'::text) AND "
                "(status = ANY (ARRAY['open'::text, 'in_progress'::text]))"
            ),
        },
        {
            "table_name": "hxy_product_training_sessions",
            "index_name": "idx_hxy_product_training_assignment_recent",
            "index_definition": (
                "CREATE INDEX idx_hxy_product_training_assignment_recent "
                "ON public.hxy_product_training_sessions USING btree "
                "(assignment_id, created_at DESC)"
            ),
            "indisvalid": True,
            "predicate": None,
        },
        {
            "table_name": "hxy_product_training_sessions",
            "index_name": "idx_hxy_product_training_store_recent",
            "index_definition": (
                "CREATE INDEX idx_hxy_product_training_store_recent "
                "ON public.hxy_product_training_sessions USING btree "
                "(organization_id, store_id, created_at DESC)"
            ),
            "indisvalid": True,
            "predicate": None,
        },
    ]


def _inspection_factory(connection: FakeInspectionConnection):
    def connect(_database_url: str):
        return connection

    return connect


def _activation(status: str = "passed"):
    def inspect(_root: Path, _database_url: str, **_kwargs):
        return {
            "status": status,
            "phase": "postflight",
            "server_major": 16,
            "checks": [
                {
                    "name": "assignment_session_scope",
                    "status": status,
                    "detail": "complete",
                }
            ],
        }

    return inspect


def _git(status: str = "passed", detail: str = "clean"):
    def inspect(_root: Path):
        return {
            "status": status,
            "commit": GIT_COMMIT if status == "passed" else "unknown",
            "detail": detail,
        }

    return inspect


def _assert_queries_are_read_only(queries: list[str]) -> None:
    forbidden = re.compile(r"\b(INSERT|UPDATE|DELETE|ALTER|CREATE|DROP|TRUNCATE)\b", re.I)
    assert queries
    assert all(forbidden.search(query) is None for query in queries)


def test_preflight_is_read_only_and_requires_activation_and_clean_commit() -> None:
    connection = FakeInspectionConnection(released=False)

    result = run_preflight(
        ROOT,
        DATABASE_URL,
        connect_factory=_inspection_factory(connection),
        activation_runner=_activation(),
        git_inspector=_git(),
    )

    assert result["status"] == "passed"
    assert result["phase"] == "preflight"
    assert result["migration_count"] == 2
    assert result["pending_tables"] == [
        "hxy_product_task_events",
        "hxy_product_tasks",
        "hxy_product_training_sessions",
    ]
    assert {check["name"] for check in result["checks"]} >= {
        "postgres_major",
        "hxy_boundary",
        "activation_postflight",
        "assignment_session_scope",
        "migration_inventory",
        "git_commit",
        "worktree_clean",
    }
    _assert_queries_are_read_only(connection.queries)


def test_preflight_accepts_an_explicit_trusted_root_for_isolated_tests(
    release_root: Path,
) -> None:
    result = run_preflight(
        release_root,
        DATABASE_URL,
        connect_factory=_inspection_factory(FakeInspectionConnection()),
        activation_runner=_activation(),
        git_inspector=_git(),
        trusted_root=release_root,
    )

    assert result["status"] == "passed"
    assert result["migration_count"] == 2


@pytest.mark.parametrize(
    ("activation_status", "git_status", "failed_check"),
    [
        ("failed", "passed", "activation_postflight"),
        ("passed", "failed", "worktree_clean"),
    ],
)
def test_preflight_fails_closed_on_prerequisite_or_git_failure(
    activation_status: str,
    git_status: str,
    failed_check: str,
) -> None:
    result = run_preflight(
        ROOT,
        DATABASE_URL,
        connect_factory=_inspection_factory(FakeInspectionConnection()),
        activation_runner=_activation(activation_status),
        git_inspector=_git(git_status, "dirty tracked file"),
    )

    assert result["status"] == "failed"
    failed = {item["name"] for item in result["checks"] if item["status"] == "failed"}
    assert failed_check in failed


def test_git_inspection_allows_only_explicit_untracked_dependency_symlinks(
    tmp_path: Path,
) -> None:
    root = tmp_path / "hxy"
    (root / "apps" / "hxy-web").mkdir(parents=True)
    (root / "knowledge").mkdir()
    (root / "apps" / "hxy-web" / "node_modules").symlink_to(tmp_path / "deps")
    (root / "knowledge" / "raw").symlink_to(tmp_path / "private-raw")

    passed = role_journeys_release.inspect_git_worktree(
        root,
        runner=_fake_git_runner(
            status="?? apps/hxy-web/node_modules\0?? knowledge/raw\0"
        ),
    )
    dirty = role_journeys_release.inspect_git_worktree(
        root,
        runner=_fake_git_runner(status=" M apps/api/main.py\0"),
    )
    business_file = role_journeys_release.inspect_git_worktree(
        root,
        runner=_fake_git_runner(status="?? data/orders.csv\0"),
    )

    assert passed["status"] == "passed"
    assert dirty["status"] == "failed"
    assert business_file["status"] == "failed"


def test_git_inspection_rejects_a_non_commit_head(tmp_path: Path) -> None:
    root = tmp_path / "hxy"
    root.mkdir()

    result = role_journeys_release.inspect_git_worktree(
        root,
        runner=_fake_git_runner(status="", commit="unknown"),
    )

    assert result["status"] == "failed"
    assert result["commit_valid"] is False
    assert result["worktree_clean"] is True


def _fake_git_runner(*, status: str, commit: str = GIT_COMMIT):
    def run(command: list[str], **_kwargs):
        if "rev-parse" in command:
            return subprocess.CompletedProcess(command, 0, commit + "\n", "")
        if "status" in command:
            return subprocess.CompletedProcess(command, 0, status, "")
        raise AssertionError(command)

    return run


def test_postflight_verifies_role_journey_schema_guards() -> None:
    connection = FakeInspectionConnection(released=True)

    result = run_postflight(
        ROOT,
        DATABASE_URL,
        connect_factory=_inspection_factory(connection),
        activation_runner=_activation(),
    )

    assert result["status"] == "passed"
    assert result["phase"] == "postflight"
    expected = {
        "role_journey_tables",
        "parent_task_column",
        "parent_task_same_store_fk",
        "task_event_append_only",
        "training_append_only",
        "task_scope_foreign_keys",
        "task_event_foreign_keys",
        "training_scope_foreign_keys",
        "active_task_indexes",
        "training_indexes",
    }
    assert expected <= {item["name"] for item in result["checks"]}
    assert all(item["status"] == "passed" for item in result["checks"])
    _assert_queries_are_read_only(connection.queries)


@pytest.mark.parametrize(
    ("omitted", "failed_check"),
    [
        ("parent_store", "parent_task_same_store_fk"),
        ("trg_hxy_product_task_events_no_truncate", "task_event_append_only"),
        ("trg_hxy_product_training_append_only", "training_append_only"),
        ("training_assignment_store", "training_scope_foreign_keys"),
        ("idx_hxy_product_tasks_store_active", "active_task_indexes"),
        ("idx_hxy_product_training_store_recent", "training_indexes"),
    ],
)
def test_postflight_fails_when_a_required_guard_is_missing(
    omitted: str,
    failed_check: str,
) -> None:
    connection = FakeInspectionConnection(released=True)
    connection.omit.add(omitted)

    result = run_postflight(
        ROOT,
        DATABASE_URL,
        connect_factory=_inspection_factory(connection),
        activation_runner=_activation(),
    )

    failed = {item["name"] for item in result["checks"] if item["status"] == "failed"}
    assert result["status"] == "failed"
    assert failed_check in failed


@pytest.mark.parametrize(
    ("trigger_name", "override", "failed_check"),
    [
        (
            "trg_hxy_product_task_events_append_only",
            {"table_name": "hxy_product_training_sessions"},
            "task_event_append_only",
        ),
        (
            "trg_hxy_product_task_events_no_truncate",
            {"tgenabled": "D"},
            "task_event_append_only",
        ),
        (
            "trg_hxy_product_training_append_only",
            {"function_name": "hxy_reject_task_event_mutation"},
            "training_append_only",
        ),
        (
            "trg_hxy_product_training_no_truncate",
            {"function_schema": "untrusted"},
            "training_append_only",
        ),
    ],
)
def test_postflight_rejects_misbound_or_disabled_append_only_triggers(
    trigger_name: str,
    override: dict[str, str],
    failed_check: str,
) -> None:
    connection = FakeInspectionConnection(released=True)
    connection.trigger_overrides[trigger_name] = override

    result = run_postflight(
        ROOT,
        DATABASE_URL,
        connect_factory=_inspection_factory(connection),
        activation_runner=_activation(),
    )

    failed = {item["name"] for item in result["checks"] if item["status"] == "failed"}
    assert result["status"] == "failed"
    assert failed_check in failed


@pytest.mark.parametrize(
    ("trigger_name", "table_name", "function_name"),
    [
        (
            "trg_hxy_product_task_events_append_only",
            "hxy_product_task_events",
            "hxy_reject_task_event_mutation",
        ),
        (
            "trg_hxy_product_training_append_only",
            "hxy_product_training_sessions",
            "hxy_reject_product_training_mutation",
        ),
    ],
)
def test_postflight_accepts_delete_or_update_event_order(
    trigger_name: str,
    table_name: str,
    function_name: str,
) -> None:
    connection = FakeInspectionConnection(released=True)
    connection.trigger_overrides[trigger_name] = {
        "definition": (
            f"CREATE TRIGGER {trigger_name} BEFORE DELETE OR UPDATE "
            f"ON public.{table_name} FOR EACH ROW "
            f"EXECUTE FUNCTION public.{function_name}()"
        )
    }

    result = run_postflight(
        ROOT,
        DATABASE_URL,
        connect_factory=_inspection_factory(connection),
        activation_runner=_activation(),
    )

    assert result["status"] == "passed"


@pytest.mark.parametrize(
    ("trigger_name", "definition", "failed_check"),
    [
        (
            "trg_hxy_product_task_events_append_only",
            "CREATE TRIGGER x BEFORE UPDATE ON public.hxy_product_task_events "
            "FOR EACH ROW EXECUTE FUNCTION public.hxy_reject_task_event_mutation()",
            "task_event_append_only",
        ),
        (
            "trg_hxy_product_task_events_append_only",
            "CREATE TRIGGER x BEFORE DELETE ON public.hxy_product_task_events "
            "FOR EACH ROW EXECUTE FUNCTION public.hxy_reject_task_event_mutation()",
            "task_event_append_only",
        ),
        (
            "trg_hxy_product_task_events_append_only",
            "CREATE TRIGGER x AFTER DELETE OR UPDATE "
            "ON public.hxy_product_task_events FOR EACH ROW "
            "EXECUTE FUNCTION public.hxy_reject_task_event_mutation()",
            "task_event_append_only",
        ),
        (
            "trg_hxy_product_task_events_append_only",
            "CREATE TRIGGER x BEFORE DELETE OR UPDATE "
            "ON public.hxy_product_task_events FOR EACH STATEMENT "
            "EXECUTE FUNCTION public.hxy_reject_task_event_mutation()",
            "task_event_append_only",
        ),
        (
            "trg_hxy_product_training_append_only",
            "CREATE TRIGGER x BEFORE DELETE "
            "ON public.hxy_product_training_sessions FOR EACH ROW "
            "EXECUTE FUNCTION public.hxy_reject_product_training_mutation()",
            "training_append_only",
        ),
        (
            "trg_hxy_product_training_append_only",
            "CREATE TRIGGER x BEFORE UPDATE "
            "ON public.hxy_product_training_sessions FOR EACH ROW "
            "EXECUTE FUNCTION public.hxy_reject_product_training_mutation()",
            "training_append_only",
        ),
        (
            "trg_hxy_product_training_append_only",
            "CREATE TRIGGER x AFTER DELETE OR UPDATE "
            "ON public.hxy_product_training_sessions FOR EACH ROW "
            "EXECUTE FUNCTION public.hxy_reject_product_training_mutation()",
            "training_append_only",
        ),
        (
            "trg_hxy_product_training_append_only",
            "CREATE TRIGGER x BEFORE DELETE OR UPDATE "
            "ON public.hxy_product_training_sessions FOR EACH STATEMENT "
            "EXECUTE FUNCTION public.hxy_reject_product_training_mutation()",
            "training_append_only",
        ),
    ],
)
def test_postflight_rejects_wrong_trigger_timing_level_or_event_set(
    trigger_name: str,
    definition: str,
    failed_check: str,
) -> None:
    connection = FakeInspectionConnection(released=True)
    connection.trigger_overrides[trigger_name] = {"definition": definition}

    result = run_postflight(
        ROOT,
        DATABASE_URL,
        connect_factory=_inspection_factory(connection),
        activation_runner=_activation(),
    )

    failed = {item["name"] for item in result["checks"] if item["status"] == "failed"}
    assert result["status"] == "failed"
    assert failed_check in failed


@pytest.mark.parametrize(
    ("marker", "definition", "failed_check"),
    [
        (
            "tasks_org_store",
            "FOREIGN KEY (organization_id, store_id) "
            "REFERENCES hxy_organization_stores(organization_id, region_id)",
            "task_scope_foreign_keys",
        ),
        (
            "events_actor_org",
            "FOREIGN KEY (organization_id, actor_assignment_id) "
            "REFERENCES hxy_role_assignments(organization_id, role_code)",
            "task_event_foreign_keys",
        ),
        (
            "training_assignment_store",
            "FOREIGN KEY (organization_id, store_id, assignment_id) "
            "REFERENCES hxy_role_assignments(organization_id, store_id, role_code)",
            "training_scope_foreign_keys",
        ),
    ],
)
def test_postflight_rejects_foreign_keys_with_wrong_target_columns(
    marker: str,
    definition: str,
    failed_check: str,
) -> None:
    connection = FakeInspectionConnection(released=True)
    connection.constraint_overrides[marker] = {"definition": definition}

    result = run_postflight(
        ROOT,
        DATABASE_URL,
        connect_factory=_inspection_factory(connection),
        activation_runner=_activation(),
    )

    failed = {item["name"] for item in result["checks"] if item["status"] == "failed"}
    assert result["status"] == "failed"
    assert failed_check in failed


@pytest.mark.parametrize(
    ("index_name", "override", "failed_check"),
    [
        (
            "idx_hxy_product_tasks_assignee_active",
            {"table_name": "hxy_product_training_sessions"},
            "active_task_indexes",
        ),
        (
            "idx_hxy_product_tasks_store_active",
            {
                "index_definition": (
                    "CREATE INDEX idx_hxy_product_tasks_store_active "
                    "ON public.hxy_product_tasks USING btree "
                    "(store_id, organization_id, priority, updated_at DESC)"
                )
            },
            "active_task_indexes",
        ),
        (
            "idx_hxy_product_tasks_assignee_active",
            {"indisvalid": False},
            "active_task_indexes",
        ),
        (
            "idx_hxy_product_tasks_store_active",
            {"predicate": None},
            "active_task_indexes",
        ),
        (
            "idx_hxy_product_training_assignment_recent",
            {
                "index_definition": (
                    "CREATE INDEX idx_hxy_product_training_assignment_recent "
                    "ON public.hxy_product_training_sessions USING btree "
                    "(assignment_id, created_at)"
                )
            },
            "training_indexes",
        ),
        (
            "idx_hxy_product_training_store_recent",
            {"indisvalid": False},
            "training_indexes",
        ),
    ],
)
def test_postflight_rejects_misdefined_or_invalid_indexes(
    index_name: str,
    override: dict[str, Any],
    failed_check: str,
) -> None:
    connection = FakeInspectionConnection(released=True)
    connection.index_overrides[index_name] = override

    result = run_postflight(
        ROOT,
        DATABASE_URL,
        connect_factory=_inspection_factory(connection),
        activation_runner=_activation(),
    )

    failed = {item["name"] for item in result["checks"] if item["status"] == "failed"}
    assert result["status"] == "failed"
    assert failed_check in failed


class FakeCommandRunner:
    def __init__(self) -> None:
        self.calls: list[tuple[list[str], dict[str, str]]] = []

    def __call__(self, command: list[str], env: dict[str, str]):
        self.calls.append((list(command), dict(env)))
        if command[0] == "pg_dump":
            Path(command[command.index("--file") + 1]).write_bytes(b"PGDMP-role")
        return subprocess.CompletedProcess(command, 0, "ok", "")


def _passed_preflight(_root: Path, _database_url: str):
    return {"status": "passed", "phase": "preflight"}


def _passed_postflight(_root: Path, _database_url: str):
    return {"status": "passed", "phase": "postflight"}


def _make_backup(release_root: Path, runner: FakeCommandRunner):
    return create_backup(
        release_root,
        DATABASE_URL,
        output_root=release_root / "data" / "backups" / "role-journeys",
        runner=runner,
        now=NOW,
        git_commit=GIT_COMMIT,
        preflight_runner=_passed_preflight,
        trusted_root=release_root,
    )


def test_backup_and_apply_reuse_guarded_core_for_only_015_016(
    release_root: Path,
) -> None:
    backup_runner = FakeCommandRunner()
    backup = _make_backup(release_root, backup_runner)
    manifest = json.loads(Path(backup["manifest_path"]).read_text(encoding="utf-8"))

    assert manifest["version"] == BACKUP_VERSION
    assert manifest["release_id"] == "hxy-role-journeys-015-016"
    assert manifest["dump"]["file"] == "hxy-before-role-journeys.dump"
    assert [item["name"] for item in manifest["migrations"]] == list(
        ROLE_JOURNEYS_MIGRATIONS
    )

    runner = FakeCommandRunner()
    result = apply_role_journeys_migrations(
        release_root,
        DATABASE_URL,
        manifest_path=Path(backup["manifest_path"]),
        confirmation=APPLY_CONFIRMATION,
        runner=runner,
        now=NOW,
        git_commit=GIT_COMMIT,
        postflight_runner=_passed_postflight,
        trusted_root=release_root,
    )

    assert result["status"] == "passed"
    psql = runner.calls[1][0]
    command_text = " ".join(psql)
    assert "pg_advisory_xact_lock" in command_text
    assert ROLE_JOURNEYS_RELEASE.advisory_lock in command_text
    assert [
        Path(psql[index + 1]).name
        for index, value in enumerate(psql)
        if value == "--file"
    ] == list(ROLE_JOURNEYS_MIGRATIONS)
    assert not any("014_" in item or "017_" in item for item in psql)


def test_apply_requires_exact_confirmation(release_root: Path) -> None:
    backup = _make_backup(release_root, FakeCommandRunner())

    with pytest.raises(ReleaseAuthorizationError, match="confirmation"):
        apply_role_journeys_migrations(
            release_root,
            DATABASE_URL,
            manifest_path=Path(backup["manifest_path"]),
            confirmation="apply-hxy-015-016",
            runner=FakeCommandRunner(),
            now=NOW,
            git_commit=GIT_COMMIT,
            postflight_runner=_passed_postflight,
            trusted_root=release_root,
        )


def test_cli_defaults_backup_root_and_preserves_post_apply_failure_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    captured: dict[str, Path] = {}
    monkeypatch.setenv("HXY_DATABASE_URL", DATABASE_URL)

    def backup(_root: Path, _dsn: str, *, output_root: Path):
        captured["output_root"] = output_root
        return {"status": "passed", "phase": "backup"}

    monkeypatch.setattr(role_journeys_release, "create_backup", backup)
    assert role_journeys_release.main(["backup"]) == 0
    assert captured["output_root"] == Path(
        "/root/hxy/data/backups/role-journeys"
    )
    capsys.readouterr()

    monkeypatch.setattr(
        role_journeys_release,
        "apply_role_journeys_migrations",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ReleasePostflightError(
                {
                    "status": "failed",
                    "detail": DATABASE_URL,
                    "long": "x" * 2000,
                }
            )
        ),
    )
    exit_code = role_journeys_release.main(
        [
            "apply",
            "--backup-manifest",
            str(tmp_path / "manifest.json"),
            "--confirm",
            APPLY_CONFIRMATION,
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert payload["status"] == "failed"
    assert payload["applied"] is True
    assert payload["error_code"] == "postflight_failed_after_apply"
    assert payload["postflight"]["detail"] == "[redacted]"
    assert len(payload["postflight"]["long"]) == 500
    assert "release-secret-value" not in json.dumps(payload)


def test_cli_requires_database_url(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    monkeypatch.delenv("HXY_DATABASE_URL", raising=False)

    assert role_journeys_release.main(["preflight"]) == 2
    assert json.loads(capsys.readouterr().out) == {
        "error": "HXY_DATABASE_URL is required",
        "status": "failed",
    }


def test_cli_invalid_dsn_returns_redacted_bounded_json_without_traceback(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    invalid_dsn = "not-a-dsn release-secret-value " + "x" * 1000
    monkeypatch.setenv("HXY_DATABASE_URL", invalid_dsn)

    exit_code = role_journeys_release.main(["preflight"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 2
    assert payload["status"] == "failed"
    assert payload["error_type"] == "ReleaseExecutionError"
    assert len(payload["error"]) <= 500
    assert invalid_dsn not in captured.out
    assert "release-secret-value" not in captured.out
    assert captured.err == ""
    assert "Traceback" not in captured.out


def test_sensitive_values_include_password_and_sslpassword() -> None:
    database_url = (
        "host=127.0.0.1 port=5432 dbname=hxy user=hxy "
        "password=database-secret sslpassword=tls-secret"
    )

    sensitive = role_journeys_release._database_sensitive_values(database_url)

    assert sensitive == (database_url, "database-secret", "tls-secret")


def test_cli_wrapper_runs_outside_the_repository(tmp_path: Path) -> None:
    env = dict(os.environ)
    env.pop("HXY_DATABASE_URL", None)

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "hxy-role-journeys-release.py"),
            "preflight",
        ],
        cwd=tmp_path,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert json.loads(result.stdout)["error"] == "HXY_DATABASE_URL is required"
