from __future__ import annotations

import argparse
import os
import re
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row

from . import activation_release
from .guarded_migration import (
    CommandRunner,
    InspectionRunner,
    MigrationReleaseSpec,
    ReleaseAuthorizationError,
    ReleaseBackupError,
    ReleaseBoundaryError,
    ReleaseExecutionError,
    ReleasePostflightError,
    apply_release_migrations,
    create_release_backup,
    database_identity as guarded_database_identity,
    migration_inventory as guarded_migration_inventory,
    render_result,
    validate_hxy_boundary as guarded_validate_hxy_boundary,
    validate_release_backup_manifest,
)


ROLE_JOURNEYS_MIGRATIONS = (
    "015_hxy_product_tasks.sql",
    "016_hxy_product_training.sql",
)
APPLY_CONFIRMATION = "APPLY-HXY-015-016"
BACKUP_VERSION = "hxy-role-journeys-backup.v1"
_DEFAULT_TRUSTED_ROOT = Path("/root/hxy")
_DEFAULT_BACKUP_ROOT = _DEFAULT_TRUSTED_ROOT / "data" / "backups" / "role-journeys"

ROLE_JOURNEYS_RELEASE = MigrationReleaseSpec(
    release_id="hxy-role-journeys-015-016",
    manifest_version=BACKUP_VERSION,
    migrations=ROLE_JOURNEYS_MIGRATIONS,
    confirmation=APPLY_CONFIRMATION,
    advisory_lock="hxy-role-journeys-015-016",
    dump_filename="hxy-before-role-journeys.dump",
)

_ROLE_JOURNEY_TABLES = (
    "hxy_product_tasks",
    "hxy_product_task_events",
    "hxy_product_training_sessions",
)
_ALLOWED_LOCAL_SYMLINKS = (
    Path("apps/hxy-web/node_modules"),
    Path("knowledge/raw"),
)

ConnectFactory = Callable[[str], Any]
ActivationRunner = Callable[..., dict[str, Any]]
GitRunner = Callable[..., subprocess.CompletedProcess[str]]
GitInspector = Callable[[Path], dict[str, Any]]


def migration_inventory(
    root_dir: Path,
    *,
    trusted_root: Path = _DEFAULT_TRUSTED_ROOT,
) -> list[dict[str, str]]:
    return guarded_migration_inventory(
        ROLE_JOURNEYS_RELEASE,
        root_dir,
        trusted_root=trusted_root,
    )


def database_identity(database_url: str) -> dict[str, str]:
    return guarded_database_identity(database_url)


def validate_hxy_boundary(
    root_dir: Path,
    identity: dict[str, str],
    *,
    trusted_root: Path = _DEFAULT_TRUSTED_ROOT,
) -> None:
    guarded_validate_hxy_boundary(root_dir, identity, trusted_root=trusted_root)


def _default_connect(database_url: str):
    return psycopg.connect(database_url, row_factory=dict_row)


def _default_git_runner(
    command: list[str],
    **kwargs: Any,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=False, capture_output=True, text=True, **kwargs)


def inspect_git_worktree(
    root_dir: Path,
    *,
    runner: GitRunner | None = None,
) -> dict[str, Any]:
    command_runner = runner or _default_git_runner
    root = root_dir.resolve()
    commit_result = command_runner(
        ["git", "-C", str(root), "rev-parse", "--verify", "HEAD^{commit}"],
    )
    commit = commit_result.stdout.strip()
    commit_valid = commit_result.returncode == 0 and re.fullmatch(
        r"[0-9a-fA-F]{40}", commit
    ) is not None

    status_result = command_runner(
        [
            "git",
            "-C",
            str(root),
            "status",
            "--porcelain=v1",
            "-z",
            "--untracked-files=all",
            "--ignore-submodules=none",
        ],
    )
    worktree_clean = status_result.returncode == 0 and _status_is_allowed(
        root,
        status_result.stdout,
    )
    status = "passed" if commit_valid and worktree_clean else "failed"
    if not commit_valid:
        detail = "Git HEAD is not a valid commit"
    elif not worktree_clean:
        detail = "worktree has disallowed tracked or untracked changes"
    else:
        detail = "valid commit and clean worktree"
    return {
        "status": status,
        "commit": commit if commit_valid else "unknown",
        "commit_valid": commit_valid,
        "worktree_clean": worktree_clean,
        "detail": detail,
    }


def _status_is_allowed(root_dir: Path, porcelain: str) -> bool:
    records = porcelain.split("\0")
    index = 0
    while index < len(records):
        record = records[index]
        index += 1
        if not record:
            continue
        if len(record) < 4 or record[2] != " ":
            return False
        status = record[:2]
        relative = Path(record[3:])
        if status[0] in {"R", "C"} or status[1] in {"R", "C"}:
            index += 1
            return False
        if (
            status != "??"
            or relative not in _ALLOWED_LOCAL_SYMLINKS
            or not (root_dir / relative).is_symlink()
        ):
            return False
    return True


def _check(name: str, passed: bool, detail: str) -> dict[str, str]:
    return {
        "name": name,
        "status": "passed" if passed else "failed",
        "detail": detail[:200],
    }


def _activation_check(
    activation: dict[str, Any],
    name: str,
) -> dict[str, Any] | None:
    return next(
        (
            item
            for item in activation.get("checks", [])
            if isinstance(item, dict) and item.get("name") == name
        ),
        None,
    )


def _inspect_database(
    root_dir: Path,
    database_url: str,
    *,
    phase: str,
    connect_factory: ConnectFactory | None,
    activation_runner: ActivationRunner,
    git_inspector: GitInspector | None = None,
    trusted_root: Path = _DEFAULT_TRUSTED_ROOT,
) -> dict[str, Any]:
    identity = database_identity(database_url)
    validate_hxy_boundary(root_dir, identity, trusted_root=trusted_root)
    inventory = migration_inventory(root_dir, trusted_root=trusted_root)
    activation = activation_runner(
        root_dir,
        database_url,
        connect_factory=connect_factory,
    )
    assignment_scope = _activation_check(activation, "assignment_session_scope")
    connection_factory = connect_factory or _default_connect
    with connection_factory(database_url) as connection:
        connection.read_only = True
        relation_rows = connection.execute(
            """
            /* hxy_role_release:relations */
            SELECT relation_name AS name
            FROM unnest(%s::text[]) AS relation_name
            WHERE to_regclass(relation_name) IS NOT NULL
            ORDER BY relation_name
            """,
            (list(_ROLE_JOURNEY_TABLES),),
        ).fetchall()
        columns: list[dict[str, Any]] = []
        constraints: list[dict[str, Any]] = []
        triggers: list[dict[str, Any]] = []
        indexes: list[dict[str, Any]] = []
        if phase == "postflight":
            columns = connection.execute(
                """
                /* hxy_role_release:columns */
                SELECT table_name, column_name
                FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND table_name = 'hxy_product_tasks'
                  AND column_name = 'parent_task_id'
                """
            ).fetchall()
            constraints = connection.execute(
                """
                /* hxy_role_release:constraints */
                SELECT relation.relname AS table_name,
                       constraint_row.contype AS constraint_type,
                       pg_get_constraintdef(constraint_row.oid) AS definition
                FROM pg_constraint AS constraint_row
                JOIN pg_class AS relation ON relation.oid = constraint_row.conrelid
                JOIN pg_namespace AS namespace_row
                  ON namespace_row.oid = relation.relnamespace
                WHERE namespace_row.nspname = current_schema()
                  AND relation.relname = ANY(%s::text[])
                ORDER BY relation.relname, constraint_row.contype, constraint_row.conname
                """,
                (list(_ROLE_JOURNEY_TABLES),),
            ).fetchall()
            triggers = connection.execute(
                """
                /* hxy_role_release:triggers */
                SELECT namespace_row.nspname AS table_schema,
                       relation.relname AS table_name,
                       trigger_row.tgname AS trigger_name,
                       trigger_row.tgenabled,
                       function_namespace.nspname AS function_schema,
                       function_row.proname AS function_name,
                       pg_get_triggerdef(trigger_row.oid) AS definition
                FROM pg_trigger AS trigger_row
                JOIN pg_class AS relation ON relation.oid = trigger_row.tgrelid
                JOIN pg_namespace AS namespace_row
                  ON namespace_row.oid = relation.relnamespace
                JOIN pg_proc AS function_row
                  ON function_row.oid = trigger_row.tgfoid
                JOIN pg_namespace AS function_namespace
                  ON function_namespace.oid = function_row.pronamespace
                WHERE namespace_row.nspname = current_schema()
                  AND relation.relname = ANY(%s::text[])
                  AND NOT trigger_row.tgisinternal
                ORDER BY relation.relname, trigger_row.tgname
                """,
                (list(_ROLE_JOURNEY_TABLES),),
            ).fetchall()
            indexes = connection.execute(
                """
                /* hxy_role_release:indexes */
                SELECT table_relation.relname AS table_name,
                       index_relation.relname AS index_name,
                       pg_get_indexdef(index_relation.oid) AS index_definition,
                       index_row.indisvalid,
                       pg_get_expr(index_row.indpred, index_row.indrelid) AS predicate
                FROM pg_index AS index_row
                JOIN pg_class AS table_relation
                  ON table_relation.oid = index_row.indrelid
                JOIN pg_class AS index_relation
                  ON index_relation.oid = index_row.indexrelid
                JOIN pg_namespace AS namespace_row
                  ON namespace_row.oid = table_relation.relnamespace
                WHERE namespace_row.nspname = current_schema()
                  AND table_relation.relname = ANY(%s::text[])
                ORDER BY index_relation.relname
                """,
                (list(_ROLE_JOURNEY_TABLES),),
            ).fetchall()

    relation_names = {str(row.get("name") or "") for row in relation_rows}
    pending_tables = sorted(set(_ROLE_JOURNEY_TABLES) - relation_names)
    server_major = int(activation.get("server_major") or 0)
    checks = [
        _check("postgres_major", server_major == 16, f"major={server_major}"),
        _check("hxy_boundary", True, "repository and database are HXY-owned"),
        _check(
            "activation_postflight",
            activation.get("status") == "passed",
            "009-014 postflight passed"
            if activation.get("status") == "passed"
            else "009-014 postflight failed",
        ),
        _check(
            "assignment_session_scope",
            bool(assignment_scope and assignment_scope.get("status") == "passed"),
            "assignment-scoped staff sessions present"
            if assignment_scope and assignment_scope.get("status") == "passed"
            else "assignment-scoped staff sessions missing",
        ),
        _check("migration_inventory", len(inventory) == 2, "015-016 checksummed"),
    ]

    git_state: dict[str, Any] | None = None
    if phase == "preflight":
        git_state = (git_inspector or inspect_git_worktree)(root_dir)
        commit_valid = bool(
            git_state.get("commit_valid", git_state.get("commit") != "unknown")
        )
        clean = bool(
            git_state.get("worktree_clean", git_state.get("status") == "passed")
        )
        checks.extend(
            [
                _check(
                    "git_commit",
                    commit_valid,
                    "valid commit" if commit_valid else "invalid commit",
                ),
                _check(
                    "worktree_clean",
                    clean,
                    str(git_state.get("detail") or "unknown"),
                ),
            ]
        )
    else:
        checks.extend(
            _postflight_checks(
                pending_tables,
                columns,
                constraints,
                triggers,
                indexes,
            )
        )

    status = "passed" if all(item["status"] == "passed" for item in checks) else "failed"
    result: dict[str, Any] = {
        "status": status,
        "phase": phase,
        "database": identity,
        "server_major": server_major,
        "pending_tables": pending_tables,
        "checks": checks,
        "migration_count": len(inventory),
    }
    if git_state is not None:
        result["git_commit"] = git_state.get("commit", "unknown")
    return result


def _identifier_name(value: str) -> str:
    return value.rsplit(".", 1)[-1].strip().strip('"').replace('""', '"').lower()


def _identifier_columns(value: str) -> tuple[str, ...]:
    return tuple(_identifier_name(item) for item in value.split(","))


def _parse_foreign_key_definition(
    definition: str,
) -> tuple[tuple[str, ...], str, tuple[str, ...]] | None:
    normalized = " ".join(definition.split())
    match = re.match(
        r"^FOREIGN KEY \(([^)]*)\) REFERENCES ([^\s(]+)\(([^)]*)\)",
        normalized,
        re.IGNORECASE,
    )
    if match is None:
        return None
    return (
        _identifier_columns(match.group(1)),
        _identifier_name(match.group(2)),
        _identifier_columns(match.group(3)),
    )


def _parse_index_columns(definition: str) -> tuple[str, ...] | None:
    match = re.search(
        r"\bUSING\s+btree\s*\(([^)]*)\)",
        definition,
        re.IGNORECASE,
    )
    if match is None:
        return None
    columns = []
    for item in match.group(1).split(","):
        normalized = " ".join(item.replace('"', "").lower().split())
        normalized = re.sub(r"\s+nulls\s+(first|last)$", "", normalized)
        columns.append(normalized)
    return tuple(columns)


def _canonical_predicate(predicate: Any) -> str | None:
    if predicate in (None, ""):
        return None
    normalized = str(predicate).lower().replace('"', "")
    normalized = re.sub(r"::(?:text|character varying)", "", normalized)
    normalized = re.sub(r"[\s()]", "", normalized)
    normalized = normalized.replace(
        "statusin'open','in_progress'",
        "status_active",
    )
    normalized = normalized.replace(
        "status=anyarray['open','in_progress']",
        "status_active",
    )
    return normalized


def _postflight_checks(
    pending_tables: list[str],
    columns: list[dict[str, Any]],
    constraints: list[dict[str, Any]],
    triggers: list[dict[str, Any]],
    indexes: list[dict[str, Any]],
) -> list[dict[str, str]]:
    normalized_foreign_keys: set[
        tuple[str, tuple[str, ...], str, tuple[str, ...]]
    ] = set()
    for row in constraints:
        if str(row.get("constraint_type") or "") != "f":
            continue
        parsed = _parse_foreign_key_definition(str(row.get("definition") or ""))
        if parsed is not None:
            source_columns, target_table, target_columns = parsed
            normalized_foreign_keys.add(
                (
                    str(row.get("table_name") or ""),
                    source_columns,
                    target_table,
                    target_columns,
                )
            )

    def has_fk(
        table: str,
        source_columns: tuple[str, ...],
        target_table: str,
        target_columns: tuple[str, ...],
    ) -> bool:
        return (
            table,
            source_columns,
            target_table,
            target_columns,
        ) in normalized_foreign_keys

    task_scope = all(
        has_fk(table, source, target, target_columns)
        for table, source, target, target_columns in (
            (
                "hxy_product_tasks",
                ("organization_id",),
                "hxy_organizations",
                ("organization_id",),
            ),
            (
                "hxy_product_tasks",
                ("organization_id", "store_id"),
                "hxy_organization_stores",
                ("organization_id", "store_id"),
            ),
            (
                "hxy_product_tasks",
                ("creator_assignment_id",),
                "hxy_role_assignments",
                ("assignment_id",),
            ),
            (
                "hxy_product_tasks",
                ("organization_id", "creator_assignment_id"),
                "hxy_role_assignments",
                ("organization_id", "assignment_id"),
            ),
            (
                "hxy_product_tasks",
                ("assignee_assignment_id",),
                "hxy_role_assignments",
                ("assignment_id",),
            ),
            (
                "hxy_product_tasks",
                ("organization_id", "assignee_assignment_id"),
                "hxy_role_assignments",
                ("organization_id", "assignment_id"),
            ),
            (
                "hxy_product_tasks",
                ("organization_id", "store_id", "assignee_assignment_id"),
                "hxy_role_assignments",
                ("organization_id", "store_id", "assignment_id"),
            ),
        )
    )
    event_scope = all(
        has_fk(table, source, target, target_columns)
        for table, source, target, target_columns in (
            (
                "hxy_product_task_events",
                ("organization_id",),
                "hxy_organizations",
                ("organization_id",),
            ),
            (
                "hxy_product_task_events",
                ("organization_id", "task_id"),
                "hxy_product_tasks",
                ("organization_id", "task_id"),
            ),
            (
                "hxy_product_task_events",
                ("organization_id", "actor_assignment_id"),
                "hxy_role_assignments",
                ("organization_id", "assignment_id"),
            ),
        )
    )
    training_scope = all(
        has_fk(table, source, target, target_columns)
        for table, source, target, target_columns in (
            (
                "hxy_product_training_sessions",
                ("organization_id",),
                "hxy_organizations",
                ("organization_id",),
            ),
            (
                "hxy_product_training_sessions",
                ("organization_id", "store_id"),
                "hxy_organization_stores",
                ("organization_id", "store_id"),
            ),
            (
                "hxy_product_training_sessions",
                ("organization_id", "assignment_id"),
                "hxy_role_assignments",
                ("organization_id", "assignment_id"),
            ),
            (
                "hxy_product_training_sessions",
                ("organization_id", "store_id", "assignment_id"),
                "hxy_role_assignments",
                ("organization_id", "store_id", "assignment_id"),
            ),
        )
    )
    parent_fk = has_fk(
        "hxy_product_tasks",
        ("organization_id", "store_id", "parent_task_id"),
        "hxy_product_tasks",
        ("organization_id", "store_id", "task_id"),
    )
    parent_column = any(
        str(row.get("table_name") or "") == "hxy_product_tasks"
        and str(row.get("column_name") or "") == "parent_task_id"
        for row in columns
    )

    normalized_triggers = [
        {
            "table_schema": str(row.get("table_schema") or ""),
            "table": str(row.get("table_name") or ""),
            "name": str(row.get("trigger_name") or ""),
            "enabled": str(row.get("tgenabled") or "").upper(),
            "function_schema": str(row.get("function_schema") or ""),
            "function": str(row.get("function_name") or ""),
            "definition": " ".join(
                str(row.get("definition") or "").lower().split()
            ),
        }
        for row in triggers
    ]

    def has_trigger(
        table: str,
        name: str,
        function: str,
        fragments: tuple[str, ...],
    ) -> bool:
        return any(
            item["table"] == table
            and item["name"] == name
            and item["enabled"] in {"O", "A"}
            and item["table_schema"]
            and item["function_schema"] == item["table_schema"]
            and item["function"] == function
            and all(fragment in item["definition"] for fragment in fragments)
            for item in normalized_triggers
        )

    task_append_only = has_trigger(
        "hxy_product_task_events",
        "trg_hxy_product_task_events_append_only",
        "hxy_reject_task_event_mutation",
        ("before update or delete", "for each row"),
    ) and has_trigger(
        "hxy_product_task_events",
        "trg_hxy_product_task_events_no_truncate",
        "hxy_reject_task_event_mutation",
        ("before truncate", "for each statement"),
    )
    training_append_only = has_trigger(
        "hxy_product_training_sessions",
        "trg_hxy_product_training_append_only",
        "hxy_reject_product_training_mutation",
        ("before update or delete", "for each row"),
    ) and has_trigger(
        "hxy_product_training_sessions",
        "trg_hxy_product_training_no_truncate",
        "hxy_reject_product_training_mutation",
        ("before truncate", "for each statement"),
    )

    def has_index(
        table: str,
        name: str,
        columns: tuple[str, ...],
        predicate: str | None,
    ) -> bool:
        return any(
            str(row.get("table_name") or "") == table
            and str(row.get("index_name") or "") == name
            and row.get("indisvalid") is True
            and _parse_index_columns(str(row.get("index_definition") or ""))
            == columns
            and _canonical_predicate(row.get("predicate")) == predicate
            for row in indexes
        )

    active_task_indexes = has_index(
        "hxy_product_tasks",
        "idx_hxy_product_tasks_assignee_active",
        ("assignee_assignment_id", "priority", "updated_at desc"),
        "status_active",
    ) and has_index(
        "hxy_product_tasks",
        "idx_hxy_product_tasks_store_active",
        ("organization_id", "store_id", "priority", "updated_at desc"),
        "visibility='store'andstatus_active",
    )
    training_indexes = has_index(
        "hxy_product_training_sessions",
        "idx_hxy_product_training_assignment_recent",
        ("assignment_id", "created_at desc"),
        None,
    ) and has_index(
        "hxy_product_training_sessions",
        "idx_hxy_product_training_store_recent",
        ("organization_id", "store_id", "created_at desc"),
        None,
    )

    return [
        _check(
            "role_journey_tables",
            not pending_tables,
            "complete" if not pending_tables else f"missing={','.join(pending_tables)}",
        ),
        _check(
            "parent_task_column",
            parent_column,
            "present" if parent_column else "missing",
        ),
        _check(
            "parent_task_same_store_fk",
            parent_fk,
            "present" if parent_fk else "missing",
        ),
        _check(
            "task_event_append_only",
            task_append_only,
            "enforced" if task_append_only else "missing",
        ),
        _check(
            "training_append_only",
            training_append_only,
            "enforced" if training_append_only else "missing",
        ),
        _check(
            "task_scope_foreign_keys",
            task_scope,
            "complete" if task_scope else "missing",
        ),
        _check(
            "task_event_foreign_keys",
            event_scope,
            "complete" if event_scope else "missing",
        ),
        _check(
            "training_scope_foreign_keys",
            training_scope,
            "complete" if training_scope else "missing",
        ),
        _check(
            "active_task_indexes",
            active_task_indexes,
            "complete" if active_task_indexes else "missing",
        ),
        _check(
            "training_indexes",
            training_indexes,
            "complete" if training_indexes else "missing",
        ),
    ]


def run_preflight(
    root_dir: Path,
    database_url: str,
    *,
    connect_factory: ConnectFactory | None = None,
    activation_runner: ActivationRunner = activation_release.run_postflight,
    git_inspector: GitInspector | None = None,
    trusted_root: Path = _DEFAULT_TRUSTED_ROOT,
) -> dict[str, Any]:
    return _inspect_database(
        root_dir,
        database_url,
        phase="preflight",
        connect_factory=connect_factory,
        activation_runner=activation_runner,
        git_inspector=git_inspector,
        trusted_root=trusted_root,
    )


def run_postflight(
    root_dir: Path,
    database_url: str,
    *,
    connect_factory: ConnectFactory | None = None,
    activation_runner: ActivationRunner = activation_release.run_postflight,
    trusted_root: Path = _DEFAULT_TRUSTED_ROOT,
) -> dict[str, Any]:
    return _inspect_database(
        root_dir,
        database_url,
        phase="postflight",
        connect_factory=connect_factory,
        activation_runner=activation_runner,
        trusted_root=trusted_root,
    )


def _database_sensitive_values(database_url: str) -> tuple[str, ...]:
    sensitive_values = [database_url]
    try:
        values = conninfo_to_dict(database_url)
    except Exception:
        return tuple(value for value in sensitive_values if value)
    sensitive_values.extend(
        str(values.get(key) or "") for key in ("password", "sslpassword")
    )
    return tuple(value for value in sensitive_values if value)


def create_backup(
    root_dir: Path,
    database_url: str,
    *,
    output_root: Path,
    runner: CommandRunner | None = None,
    now: datetime | None = None,
    git_commit: str | None = None,
    preflight_runner: InspectionRunner = run_preflight,
    trusted_root: Path = _DEFAULT_TRUSTED_ROOT,
) -> dict[str, Any]:
    result = create_release_backup(
        ROLE_JOURNEYS_RELEASE,
        root_dir,
        database_url,
        output_root=output_root,
        preflight_inspector=preflight_runner,
        runner=runner,
        now=now,
        git_commit=git_commit,
        trusted_root=trusted_root,
    )
    result.pop("release_id", None)
    return result


def validate_backup_manifest(
    root_dir: Path,
    database_url: str,
    manifest_path: Path,
    *,
    now: datetime | None = None,
    max_age: timedelta = timedelta(hours=24),
    git_commit: str | None = None,
    trusted_root: Path = _DEFAULT_TRUSTED_ROOT,
) -> dict[str, Any]:
    result = validate_release_backup_manifest(
        ROLE_JOURNEYS_RELEASE,
        root_dir,
        database_url,
        manifest_path,
        now=now,
        max_age=max_age,
        git_commit=git_commit,
        trusted_root=trusted_root,
    )
    for key in ("release_id", "git_commit", "connection_fingerprint"):
        result.pop(key, None)
    return result


def apply_role_journeys_migrations(
    root_dir: Path,
    database_url: str,
    *,
    manifest_path: Path,
    confirmation: str,
    runner: CommandRunner | None = None,
    now: datetime | None = None,
    git_commit: str | None = None,
    postflight_runner: InspectionRunner = run_postflight,
    trusted_root: Path = _DEFAULT_TRUSTED_ROOT,
) -> dict[str, Any]:
    result = apply_release_migrations(
        ROLE_JOURNEYS_RELEASE,
        root_dir,
        database_url,
        manifest_path=manifest_path,
        confirmation=confirmation,
        postflight_inspector=postflight_runner,
        runner=runner,
        now=now,
        git_commit=git_commit,
        trusted_root=trusted_root,
    )
    for key in ("release_id", "git_commit"):
        result.pop(key, None)
    return result


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Guarded HXY role journeys release")
    parser.add_argument("--root-dir", type=Path, default=Path.cwd())
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("preflight")
    backup_parser = commands.add_parser("backup")
    backup_parser.add_argument("--output-root", type=Path)
    apply_parser = commands.add_parser("apply")
    apply_parser.add_argument("--backup-manifest", type=Path)
    apply_parser.add_argument("--confirm", default="")
    commands.add_parser("postflight")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_argument_parser().parse_args(argv)
    database_url = os.getenv("HXY_DATABASE_URL", "").strip()
    if not database_url:
        print(render_result({"status": "failed", "error": "HXY_DATABASE_URL is required"}))
        return 2
    try:
        if args.command == "preflight":
            result = run_preflight(args.root_dir, database_url)
        elif args.command == "backup":
            result = create_backup(
                args.root_dir,
                database_url,
                output_root=args.output_root or _DEFAULT_BACKUP_ROOT,
            )
        elif args.command == "apply":
            if args.backup_manifest is None:
                raise ReleaseAuthorizationError("--backup-manifest is required")
            result = apply_role_journeys_migrations(
                args.root_dir,
                database_url,
                manifest_path=args.backup_manifest,
                confirmation=args.confirm,
            )
        else:
            result = run_postflight(args.root_dir, database_url)
    except ReleasePostflightError as exc:
        result = {
            "status": "failed",
            "phase": args.command,
            "error_type": "ReleaseExecutionError",
            "error_code": "postflight_failed_after_apply",
            "error": str(exc),
            "applied": exc.applied,
            "postflight": exc.postflight,
        }
    except (
        ReleaseAuthorizationError,
        ReleaseBackupError,
        ReleaseBoundaryError,
        ReleaseExecutionError,
        OSError,
        psycopg.Error,
    ) as exc:
        result = {
            "status": "failed",
            "phase": args.command,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }
    print(render_result(result, sensitive_values=_database_sensitive_values(database_url)))
    return 0 if result["status"] == "passed" else 2
