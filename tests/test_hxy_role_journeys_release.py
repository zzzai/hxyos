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


def _slice_release_runbook_sections(markdown: str) -> dict[str, str]:
    headings = list(re.finditer(r"^## (?P<title>[^\r\n]+)\s*$", markdown, re.MULTILINE))
    sections: dict[str, str] = {}
    for index, heading in enumerate(headings):
        title = heading.group("title").strip()
        if title == "Stop Rule":
            key = "stop_rule"
        else:
            gate = re.fullmatch(r"Gate (?P<number>\d+)(?::.*)?", title)
            if gate is None:
                continue
            key = f"gate_{gate.group('number')}"
        assert key not in sections, f"duplicate release section: {key}"
        end = headings[index + 1].start() if index + 1 < len(headings) else len(markdown)
        sections[key] = markdown[heading.end() : end].strip()
    return sections


def _assert_section_contains(
    sections: dict[str, str],
    section: str,
    required_phrases: tuple[str, ...],
) -> None:
    assert section in sections, f"missing release section: {section}"
    for phrase in required_phrases:
        assert phrase in sections[section], f"{phrase!r} must appear in {section}"


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


def _constraint_rows() -> list[dict[str, Any]]:
    specifications = {
        "parent_store": (
            "hxy_product_tasks",
            ("organization_id", "store_id", "parent_task_id"),
            "hxy_product_tasks",
            ("organization_id", "store_id", "task_id"),
        ),
        "tasks_org_store": (
            "hxy_product_tasks",
            ("organization_id", "store_id"),
            "hxy_organization_stores",
            ("organization_id", "store_id"),
        ),
        "tasks_org": (
            "hxy_product_tasks",
            ("organization_id",),
            "hxy_organizations",
            ("organization_id",),
        ),
        "tasks_creator": (
            "hxy_product_tasks",
            ("creator_assignment_id",),
            "hxy_role_assignments",
            ("assignment_id",),
        ),
        "tasks_creator_org": (
            "hxy_product_tasks",
            ("organization_id", "creator_assignment_id"),
            "hxy_role_assignments",
            ("organization_id", "assignment_id"),
        ),
        "tasks_assignee": (
            "hxy_product_tasks",
            ("assignee_assignment_id",),
            "hxy_role_assignments",
            ("assignment_id",),
        ),
        "tasks_assignee_org": (
            "hxy_product_tasks",
            ("organization_id", "assignee_assignment_id"),
            "hxy_role_assignments",
            ("organization_id", "assignment_id"),
        ),
        "tasks_assignee_store": (
            "hxy_product_tasks",
            ("organization_id", "store_id", "assignee_assignment_id"),
            "hxy_role_assignments",
            ("organization_id", "store_id", "assignment_id"),
        ),
        "events_task_org": (
            "hxy_product_task_events",
            ("organization_id", "task_id"),
            "hxy_product_tasks",
            ("organization_id", "task_id"),
        ),
        "events_org": (
            "hxy_product_task_events",
            ("organization_id",),
            "hxy_organizations",
            ("organization_id",),
        ),
        "events_actor_org": (
            "hxy_product_task_events",
            ("organization_id", "actor_assignment_id"),
            "hxy_role_assignments",
            ("organization_id", "assignment_id"),
        ),
        "training_org_store": (
            "hxy_product_training_sessions",
            ("organization_id", "store_id"),
            "hxy_organization_stores",
            ("organization_id", "store_id"),
        ),
        "training_org": (
            "hxy_product_training_sessions",
            ("organization_id",),
            "hxy_organizations",
            ("organization_id",),
        ),
        "training_assignment_org": (
            "hxy_product_training_sessions",
            ("organization_id", "assignment_id"),
            "hxy_role_assignments",
            ("organization_id", "assignment_id"),
        ),
        "training_assignment_store": (
            "hxy_product_training_sessions",
            ("organization_id", "store_id", "assignment_id"),
            "hxy_role_assignments",
            ("organization_id", "store_id", "assignment_id"),
        ),
    }
    return [
        {
            "marker": marker,
            "current_schema": "public",
            "source_schema": "public",
            "source_table": source_table,
            "source_columns": list(source_columns),
            "target_schema": "public",
            "target_table": target_table,
            "target_columns": list(target_columns),
            "convalidated": True,
            "confdeltype": "r",
        }
        for marker, (
            source_table,
            source_columns,
            target_table,
            target_columns,
        ) in specifications.items()
    ]


def _function_definition(name: str, source: str) -> str:
    return (
        f"CREATE OR REPLACE FUNCTION public.{name}() RETURNS trigger "
        f"LANGUAGE plpgsql AS $function$ {source} $function$"
    )


def _trigger_rows() -> list[dict[str, Any]]:
    task_source = (
        "BEGIN RAISE EXCEPTION "
        "'hxy_product_task_events is append-only'; END;"
    )
    training_source = (
        "BEGIN RAISE EXCEPTION "
        "'hxy_product_training_sessions is append-only'; END;"
    )
    return [
        {
            "table_schema": "public",
            "table_name": "hxy_product_task_events",
            "trigger_name": "trg_hxy_product_task_events_append_only",
            "tgenabled": "O",
            "function_schema": "public",
            "function_name": "hxy_reject_task_event_mutation",
            "tgqual": None,
            "prosrc": task_source,
            "function_definition": _function_definition(
                "hxy_reject_task_event_mutation",
                task_source,
            ),
            "definition": "CREATE TRIGGER x BEFORE UPDATE OR DELETE ON x FOR EACH ROW",
        },
        {
            "table_schema": "public",
            "table_name": "hxy_product_task_events",
            "trigger_name": "trg_hxy_product_task_events_no_truncate",
            "tgenabled": "O",
            "function_schema": "public",
            "function_name": "hxy_reject_task_event_mutation",
            "tgqual": None,
            "prosrc": task_source,
            "function_definition": _function_definition(
                "hxy_reject_task_event_mutation",
                task_source,
            ),
            "definition": "CREATE TRIGGER x BEFORE TRUNCATE ON x FOR EACH STATEMENT",
        },
        {
            "table_schema": "public",
            "table_name": "hxy_product_training_sessions",
            "trigger_name": "trg_hxy_product_training_append_only",
            "tgenabled": "O",
            "function_schema": "public",
            "function_name": "hxy_reject_product_training_mutation",
            "tgqual": None,
            "prosrc": training_source,
            "function_definition": _function_definition(
                "hxy_reject_product_training_mutation",
                training_source,
            ),
            "definition": "CREATE TRIGGER x BEFORE UPDATE OR DELETE ON x FOR EACH ROW",
        },
        {
            "table_schema": "public",
            "table_name": "hxy_product_training_sessions",
            "trigger_name": "trg_hxy_product_training_no_truncate",
            "tgenabled": "O",
            "function_schema": "public",
            "function_name": "hxy_reject_product_training_mutation",
            "tgqual": None,
            "prosrc": training_source,
            "function_definition": _function_definition(
                "hxy_reject_product_training_mutation",
                training_source,
            ),
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
    ("trigger_name", "override", "failed_check"),
    [
        (
            "trg_hxy_product_task_events_append_only",
            {"tgqual": "false"},
            "task_event_append_only",
        ),
        (
            "trg_hxy_product_training_append_only",
            {
                "prosrc": "BEGIN RETURN OLD; END;",
                "function_definition": (
                    "CREATE OR REPLACE FUNCTION "
                    "public.hxy_reject_product_training_mutation() "
                    "RETURNS trigger LANGUAGE plpgsql "
                    "AS $function$ BEGIN RETURN OLD; END; $function$"
                ),
            },
            "training_append_only",
        ),
        (
            "trg_hxy_product_task_events_no_truncate",
            {
                "prosrc": (
                    "BEGIN RAISE EXCEPTION "
                    "'hxy_product_training_sessions is append-only'; END;"
                )
            },
            "task_event_append_only",
        ),
    ],
)
def test_postflight_rejects_trigger_conditions_or_replaced_function_bodies(
    trigger_name: str,
    override: dict[str, Any],
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
    ("marker", "target_columns", "failed_check"),
    [
        (
            "tasks_org_store",
            ["organization_id", "region_id"],
            "task_scope_foreign_keys",
        ),
        (
            "events_actor_org",
            ["organization_id", "role_code"],
            "task_event_foreign_keys",
        ),
        (
            "training_assignment_store",
            ["organization_id", "store_id", "role_code"],
            "training_scope_foreign_keys",
        ),
    ],
)
def test_postflight_rejects_foreign_keys_with_wrong_target_columns(
    marker: str,
    target_columns: list[str],
    failed_check: str,
) -> None:
    connection = FakeInspectionConnection(released=True)
    connection.constraint_overrides[marker] = {"target_columns": target_columns}

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
    ("marker", "override", "failed_check"),
    [
        (
            "tasks_org_store",
            {"target_schema": "shadow"},
            "task_scope_foreign_keys",
        ),
        (
            "events_actor_org",
            {"convalidated": False},
            "task_event_foreign_keys",
        ),
        (
            "training_assignment_store",
            {"confdeltype": "c"},
            "training_scope_foreign_keys",
        ),
    ],
)
def test_postflight_rejects_unsafe_foreign_key_catalog_state(
    marker: str,
    override: dict[str, Any],
    failed_check: str,
) -> None:
    connection = FakeInspectionConnection(released=True)
    connection.constraint_overrides[marker] = override

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


def _initialize_release_git_repository(release_root: Path) -> str:
    (release_root / ".gitignore").write_text("data/backups/\n", encoding="utf-8")
    (release_root / "release-source.txt").write_text("clean\n", encoding="utf-8")
    commands = [
        ["git", "init", "--quiet"],
        ["git", "config", "user.email", "hxy-release@example.invalid"],
        ["git", "config", "user.name", "HXY Release Test"],
        ["git", "add", "."],
        ["git", "commit", "--quiet", "-m", "test release source"],
    ]
    for command in commands:
        subprocess.run(
            command,
            cwd=release_root,
            check=True,
            capture_output=True,
            text=True,
        )
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=release_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


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
        git_inspector=_git(),
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


@pytest.mark.parametrize("dirty_kind", ["tracked", "untracked"])
def test_apply_rechecks_clean_git_state_before_any_runner_command(
    release_root: Path,
    dirty_kind: str,
) -> None:
    git_commit = _initialize_release_git_repository(release_root)
    backup = create_backup(
        release_root,
        DATABASE_URL,
        output_root=release_root / "data" / "backups" / "role-journeys",
        runner=FakeCommandRunner(),
        now=NOW,
        git_commit=git_commit,
        preflight_runner=_passed_preflight,
        trusted_root=release_root,
    )
    if dirty_kind == "tracked":
        (release_root / "release-source.txt").write_text(
            "dirty\n",
            encoding="utf-8",
        )
    else:
        (release_root / "data" / "orders.csv").write_text(
            "business-data\n",
            encoding="utf-8",
        )
    runner = FakeCommandRunner()

    with pytest.raises(ReleaseAuthorizationError, match="clean worktree"):
        apply_role_journeys_migrations(
            release_root,
            DATABASE_URL,
            manifest_path=Path(backup["manifest_path"]),
            confirmation=APPLY_CONFIRMATION,
            runner=runner,
            now=NOW,
            git_commit=git_commit,
            postflight_runner=_passed_postflight,
            trusted_root=release_root,
        )

    assert runner.calls == []


def test_apply_git_gate_allows_explicit_local_dependency_symlink(
    release_root: Path,
    tmp_path: Path,
) -> None:
    git_commit = _initialize_release_git_repository(release_root)
    backup = create_backup(
        release_root,
        DATABASE_URL,
        output_root=release_root / "data" / "backups" / "role-journeys",
        runner=FakeCommandRunner(),
        now=NOW,
        git_commit=git_commit,
        preflight_runner=_passed_preflight,
        trusted_root=release_root,
    )
    dependency_path = release_root / "apps" / "hxy-web"
    dependency_path.mkdir(parents=True)
    (dependency_path / "node_modules").symlink_to(tmp_path / "shared-node-modules")
    runner = FakeCommandRunner()

    result = apply_role_journeys_migrations(
        release_root,
        DATABASE_URL,
        manifest_path=Path(backup["manifest_path"]),
        confirmation=APPLY_CONFIRMATION,
        runner=runner,
        now=NOW,
        git_commit=git_commit,
        postflight_runner=_passed_postflight,
        trusted_root=release_root,
    )

    assert result["status"] == "passed"
    assert [command[0] for command, _env in runner.calls] == [
        "pg_restore",
        "psql",
    ]


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


def test_internal_runbook_enforces_release_stop_gate_order() -> None:
    runbook_path = ROOT / "docs" / "operations" / "hxy-role-journeys-release.md"

    assert runbook_path.is_file(), "role journeys release runbook is required"
    runbook = runbook_path.read_text(encoding="utf-8")
    ordered_gates = [
        "## Gate 1: Immutable Release Source",
        "## Gate 2: Code And Public Preflight",
        "## Gate 3: Read-Only Role Release Preflight",
        "## Gate 4: Verified Restorable Backup",
        "## Gate 5: Transactional Apply 015-016",
        "## Gate 6: Read-Only Postflight",
        "## Gate 7: API Activation From Versioned Release",
        "## Gate 8: Web Activation From Same Commit",
        "## Gate 9: Role Canaries",
        "## Gate 10: Mobile Smoke",
        "## Gate 11: Completion Record",
    ]

    positions = [runbook.index(gate) for gate in ordered_gates]
    assert positions == sorted(positions)
    for phrase in [
        "clean immutable release worktree",
        "exact target commit",
        "python3 scripts/check-hxy-secrets.py",
        "python3 scripts/check-hxy-public-release.py",
        "scripts/hxy-role-journeys-release.py preflight",
        "pg_restore --list",
        "manifest.json",
        "APPLY-HXY-015-016",
        "--single-transaction",
        "scripts/hxy-role-journeys-release.py postflight",
        "versioned release path",
        "API and web from one commit",
    ]:
        assert phrase in runbook


def test_internal_runbook_covers_role_canaries_rollback_and_hxy_boundaries() -> None:
    runbook = (
        ROOT / "docs" / "operations" / "hxy-role-journeys-release.md"
    ).read_text(encoding="utf-8")

    for phrase in [
        "founder question -> evidence -> task",
        "manager task -> issue -> follow-up",
        "employee answer -> practice -> correction -> issue",
        "mobile smoke",
        "application rollback before database restore",
        "independent maintenance confirmation",
        "不得向 /root/htops 写入",
        "不得修改核心知识",
        "`/root/hxy` 当前是脏工作树，不得作为 release source",
        "atomic service switch",
        "保留旧 release",
    ]:
        assert phrase in runbook


def test_internal_runbook_is_private_code_only_and_contains_no_secret_values() -> None:
    runbook = (
        ROOT / "docs" / "operations" / "hxy-role-journeys-release.md"
    ).read_text(encoding="utf-8")

    assert "GitHub 仅用于内部代码仓" in runbook
    assert "不创建公开项目描述" in runbook
    assert "不得记录密码、token、完整 DSN 或私有资料" in runbook
    assert "## 项目介绍" not in runbook
    assert "public roadmap" not in runbook.lower()
    for secret_pattern in [
        r"(?i)password\s*=",
        r"(?i)token\s*=",
        r"(?i)authorization:\s*bearer",
        r"(?i)postgres(?:ql)?://\S+",
        r"(?i)gh[pousr]_[a-z0-9]+",
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    ]:
        assert re.search(secret_pattern, runbook) is None


def test_internal_runbook_places_required_terms_in_exact_release_sections() -> None:
    runbook = (
        ROOT / "docs" / "operations" / "hxy-role-journeys-release.md"
    ).read_text(encoding="utf-8")
    sections = _slice_release_runbook_sections(runbook)

    _assert_section_contains(
        sections,
        "stop_rule",
        (
            "任一命令失败",
            "立即停止",
        ),
    )
    _assert_section_contains(
        sections,
        "gate_2",
        (
            ".venv/bin/pytest tests/test_hxy_role_journeys_release.py -q",
            "npm test",
            "python3 scripts/check-hxy-secrets.py",
            "python3 scripts/check-hxy-public-release.py",
        ),
    )
    _assert_section_contains(
        sections,
        "gate_4",
        (
            ".venv/bin/python scripts/hxy-role-journeys-release.py backup",
            "临时隔离数据库",
            "完整恢复验证",
            "不得只以 `pg_restore --list` 成功代替完整恢复验证",
        ),
    )
    _assert_section_contains(
        sections,
        "gate_11",
        ("只有 Gate 1-10 全部通过后才写 completion record",),
    )


def test_release_section_contract_rejects_requirement_in_the_wrong_gate() -> None:
    misplaced_runbook = """\
## Stop Rule
任一命令失败立即停止。

## Gate 2: Code
临时隔离数据库必须完成完整恢复验证。

## Gate 4: Backup
只运行 backup。
"""
    sections = _slice_release_runbook_sections(misplaced_runbook)

    with pytest.raises(AssertionError, match="gate_4"):
        _assert_section_contains(sections, "gate_4", ("完整恢复验证",))
