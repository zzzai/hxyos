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
    MigrationLoader,
    MigrationReleaseSpec,
    ReleaseAuthorizationError,
    ReleaseBackupError,
    ReleaseBoundaryError,
    ReleaseExecutionError,
    ReleasePostflightError,
    apply_release_migrations,
    create_release_backup,
    database_identity as guarded_database_identity,
    git_head_migration_loader,
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
    migration_loader: MigrationLoader | None = None,
) -> list[dict[str, str]]:
    return guarded_migration_inventory(
        ROLE_JOURNEYS_RELEASE,
        root_dir,
        trusted_root=trusted_root,
        migration_loader=migration_loader,
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
    migration_loader: MigrationLoader | None = None,
) -> dict[str, Any]:
    identity = database_identity(database_url)
    validate_hxy_boundary(root_dir, identity, trusted_root=trusted_root)
    inventory = migration_inventory(
        root_dir,
        trusted_root=trusted_root,
        migration_loader=migration_loader,
    )
    activation = activation_runner(
        root_dir,
        database_url,
        connect_factory=connect_factory,
        migration_loader=migration_loader,
    )
    assignment_scope = _activation_check(activation, "assignment_session_scope")
    connection_factory = connect_factory or _default_connect
    with connection_factory(database_url) as connection:
        connection.read_only = True
        schema_row = connection.execute(
            """
            /* hxy_role_release:schema */
            SELECT current_schema() AS current_schema
            """
        ).fetchone()
        relation_rows = connection.execute(
            """
            /* hxy_role_release:relations */
            SELECT relation_name AS name
            FROM unnest(%s::text[]) AS relation_name
            WHERE to_regclass('public.' || relation_name) IS NOT NULL
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
                SELECT table_schema, table_name, column_name, data_type,
                       is_nullable, column_default
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = ANY(%s::text[])
                ORDER BY table_name, ordinal_position
                """,
                (list(_ROLE_JOURNEY_TABLES),),
            ).fetchall()
            constraints = connection.execute(
                """
                /* hxy_role_release:constraints */
                SELECT current_schema() AS current_schema,
                       constraint_row.contype AS constraint_type,
                       source_namespace.nspname AS source_schema,
                       source_relation.relname AS source_table,
                       ARRAY(
                         SELECT source_attribute.attname
                         FROM unnest(constraint_row.conkey) WITH ORDINALITY
                           AS source_key(attnum, position)
                         JOIN pg_attribute AS source_attribute
                           ON source_attribute.attrelid = constraint_row.conrelid
                          AND source_attribute.attnum = source_key.attnum
                         ORDER BY source_key.position
                       ) AS source_columns,
                       COALESCE(target_namespace.nspname, '') AS target_schema,
                       COALESCE(target_relation.relname, '') AS target_table,
                       COALESCE(ARRAY(
                         SELECT target_attribute.attname
                         FROM unnest(constraint_row.confkey) WITH ORDINALITY
                           AS target_key(attnum, position)
                         JOIN pg_attribute AS target_attribute
                           ON target_attribute.attrelid = constraint_row.confrelid
                          AND target_attribute.attnum = target_key.attnum
                         ORDER BY target_key.position
                       ), ARRAY[]::name[]) AS target_columns,
                       constraint_row.convalidated,
                       constraint_row.confdeltype,
                       CASE WHEN constraint_row.contype = 'c'
                         THEN pg_get_expr(constraint_row.conbin, constraint_row.conrelid)
                         ELSE NULL
                       END AS check_expression
                FROM pg_constraint AS constraint_row
                JOIN pg_class AS source_relation
                  ON source_relation.oid = constraint_row.conrelid
                JOIN pg_namespace AS source_namespace
                  ON source_namespace.oid = source_relation.relnamespace
                LEFT JOIN pg_class AS target_relation
                  ON target_relation.oid = constraint_row.confrelid
                LEFT JOIN pg_namespace AS target_namespace
                  ON target_namespace.oid = target_relation.relnamespace
                WHERE source_namespace.nspname = 'public'
                  AND source_relation.relname = ANY(%s::text[])
                  AND constraint_row.contype IN ('p', 'u', 'c', 'f')
                ORDER BY source_relation.relname, constraint_row.conname
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
                       pg_get_expr(trigger_row.tgqual, trigger_row.tgrelid) AS tgqual,
                       function_namespace.nspname AS function_schema,
                       function_row.proname AS function_name,
                       function_row.prosrc,
                       pg_get_functiondef(function_row.oid) AS function_definition,
                       pg_get_triggerdef(trigger_row.oid) AS definition
                FROM pg_trigger AS trigger_row
                JOIN pg_class AS relation ON relation.oid = trigger_row.tgrelid
                JOIN pg_namespace AS namespace_row
                  ON namespace_row.oid = relation.relnamespace
                JOIN pg_proc AS function_row
                  ON function_row.oid = trigger_row.tgfoid
                JOIN pg_namespace AS function_namespace
                  ON function_namespace.oid = function_row.pronamespace
                WHERE namespace_row.nspname = 'public'
                  AND relation.relname = ANY(%s::text[])
                  AND NOT trigger_row.tgisinternal
                ORDER BY relation.relname, trigger_row.tgname
                """,
                (list(_ROLE_JOURNEY_TABLES),),
            ).fetchall()
            indexes = connection.execute(
                """
                /* hxy_role_release:indexes */
                SELECT namespace_row.nspname AS table_schema,
                       table_relation.relname AS table_name,
                       index_relation.relname AS index_name,
                       pg_get_indexdef(index_relation.oid) AS index_definition,
                       index_row.indisvalid,
                       index_row.indisunique,
                       pg_get_expr(index_row.indpred, index_row.indrelid) AS predicate
                FROM pg_index AS index_row
                JOIN pg_class AS table_relation
                  ON table_relation.oid = index_row.indrelid
                JOIN pg_class AS index_relation
                  ON index_relation.oid = index_row.indexrelid
                JOIN pg_namespace AS namespace_row
                  ON namespace_row.oid = table_relation.relnamespace
                WHERE namespace_row.nspname = 'public'
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
            "current_schema",
            str((schema_row or {}).get("current_schema") or "") == "public",
            f"schema={str((schema_row or {}).get('current_schema') or 'unknown')}",
        ),
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


def _parse_trigger_definition(
    definition: str,
) -> tuple[str, frozenset[str], str] | None:
    normalized = " ".join(definition.upper().split())
    timing_match = re.search(
        r"\b(BEFORE|AFTER|INSTEAD OF)\s+(.+?)\s+ON\s+",
        normalized,
    )
    level_match = re.search(r"\bFOR EACH (ROW|STATEMENT)\b", normalized)
    if timing_match is None or level_match is None:
        return None
    event_parts = re.split(r"\s+OR\s+", timing_match.group(2))
    allowed_events = {"INSERT", "UPDATE", "DELETE", "TRUNCATE"}
    if (
        not event_parts
        or any(event not in allowed_events for event in event_parts)
        or len(event_parts) != len(set(event_parts))
    ):
        return None
    return (
        timing_match.group(1),
        frozenset(event_parts),
        level_match.group(1),
    )


def _normalize_function_source(value: Any) -> str:
    return " ".join(str(value or "").split())


def _function_definition_matches(definition: Any, expected_source: str) -> bool:
    normalized = _normalize_function_source(definition)
    return (
        expected_source in normalized
        and "language plpgsql" in normalized.lower()
    )


_ROLE_COLUMN_CONTRACT = {
    "hxy_product_tasks": (
        ("task_id", "uuid", "NO", "gen_random_uuid()"),
        ("organization_id", "uuid", "NO", None),
        ("store_id", "text", "YES", None),
        ("creator_assignment_id", "uuid", "NO", None),
        ("assignee_assignment_id", "uuid", "YES", None),
        ("source_conversation_id", "uuid", "YES", None),
        ("source_message_id", "uuid", "YES", None),
        ("title", "text", "NO", None),
        ("details", "text", "NO", "''::text"),
        ("priority", "text", "NO", "'normal'::text"),
        ("visibility", "text", "NO", "'assignee'::text"),
        ("status", "text", "NO", "'open'::text"),
        ("result", "text", "YES", None),
        ("due_at", "timestamp with time zone", "YES", None),
        ("completed_at", "timestamp with time zone", "YES", None),
        ("created_at", "timestamp with time zone", "NO", "now()"),
        ("updated_at", "timestamp with time zone", "NO", "now()"),
        ("parent_task_id", "uuid", "YES", None),
    ),
    "hxy_product_task_events": (
        ("event_id", "uuid", "NO", "gen_random_uuid()"),
        ("organization_id", "uuid", "NO", None),
        ("task_id", "uuid", "NO", None),
        ("actor_assignment_id", "uuid", "NO", None),
        ("event_type", "text", "NO", None),
        ("payload", "jsonb", "NO", "'{}'::jsonb"),
        ("created_at", "timestamp with time zone", "NO", "now()"),
    ),
    "hxy_product_training_sessions": (
        ("training_session_id", "uuid", "NO", "gen_random_uuid()"),
        ("organization_id", "uuid", "NO", None),
        ("store_id", "text", "NO", None),
        ("assignment_id", "uuid", "NO", None),
        ("customer_question", "text", "NO", None),
        ("employee_answer", "text", "NO", None),
        ("score", "integer", "NO", None),
        ("level", "text", "NO", None),
        ("needs_retrain", "boolean", "NO", None),
        ("standard_script", "text", "NO", "''::text"),
        ("correction_points", "jsonb", "NO", "'[]'::jsonb"),
        ("created_at", "timestamp with time zone", "NO", "now()"),
    ),
}

_BUSINESS_CHECK_CONTRACT = {
    "hxy_product_tasks": (
        ("char_length(btrim(title)) BETWEEN 1 AND 160", "char_length(btrim(title)) >= 1 AND char_length(btrim(title)) <= 160"),
        ("char_length(details) <= 5000",),
        ("priority IN ('low', 'normal', 'high', 'urgent')", "priority = ANY (ARRAY['low', 'normal', 'high', 'urgent'])"),
        ("visibility IN ('assignee', 'store')", "visibility = ANY (ARRAY['assignee', 'store'])"),
        ("status IN ('open', 'in_progress', 'completed', 'cancelled')", "status = ANY (ARRAY['open', 'in_progress', 'completed', 'cancelled'])"),
        ("result IS NULL OR char_length(result) <= 5000",),
        ("(visibility = 'assignee' AND assignee_assignment_id IS NOT NULL) OR (visibility = 'store' AND store_id IS NOT NULL)",),
        ("(status = 'completed' AND completed_at IS NOT NULL) OR (status <> 'completed' AND completed_at IS NULL)",),
    ),
    "hxy_product_task_events": (
        ("event_type IN ('created', 'in_progress', 'completed', 'cancelled')", "event_type = ANY (ARRAY['created', 'in_progress', 'completed', 'cancelled'])"),
    ),
    "hxy_product_training_sessions": (
        ("char_length(btrim(customer_question)) BETWEEN 1 AND 1000", "char_length(btrim(customer_question)) >= 1 AND char_length(btrim(customer_question)) <= 1000"),
        ("char_length(btrim(employee_answer)) BETWEEN 1 AND 4000", "char_length(btrim(employee_answer)) >= 1 AND char_length(btrim(employee_answer)) <= 4000"),
        ("score BETWEEN 0 AND 100", "score >= 0 AND score <= 100"),
        ("char_length(btrim(level)) BETWEEN 1 AND 80", "char_length(btrim(level)) >= 1 AND char_length(btrim(level)) <= 80"),
        ("char_length(standard_script) <= 4000",),
        ("jsonb_typeof(correction_points) = 'array'",),
    ),
}


def _canonical_contract_expression(value: Any) -> str:
    normalized = str(value or "").lower().replace('"', "")
    normalized = re.sub(r"::(?:text|character varying)", "", normalized)
    return re.sub(r"[\s()]", "", normalized)


def _canonical_default(value: Any) -> str | None:
    if value is None:
        return None
    return "".join(str(value).lower().replace("public.", "").split())


def _postflight_checks(
    pending_tables: list[str],
    columns: list[dict[str, Any]],
    constraints: list[dict[str, Any]],
    triggers: list[dict[str, Any]],
    indexes: list[dict[str, Any]],
) -> list[dict[str, str]]:
    actual_columns = {
        (str(row.get("table_name") or ""), str(row.get("column_name") or "")): (
            str(row.get("table_schema") or ""),
            str(row.get("data_type") or ""),
            str(row.get("is_nullable") or ""),
            _canonical_default(row.get("column_default")),
        )
        for row in columns
    }
    column_contract = all(
        actual_columns.get((table, name))
        == ("public", data_type, nullable, _canonical_default(default))
        for table, expected_columns in _ROLE_COLUMN_CONTRACT.items()
        for name, data_type, nullable, default in expected_columns
    )

    def constraint_columns(row: dict[str, Any], key: str) -> tuple[str, ...]:
        return tuple(str(item) for item in row.get(key) or ())

    def has_local_constraint(
        constraint_type: str,
        table: str,
        expected_columns: tuple[str, ...],
    ) -> bool:
        return any(
            str(row.get("constraint_type") or "") == constraint_type
            and str(row.get("source_schema") or "") == "public"
            and str(row.get("source_table") or "") == table
            and constraint_columns(row, "source_columns") == expected_columns
            and row.get("convalidated") is True
            for row in constraints
        )

    primary_keys = all(
        has_local_constraint("p", table, expected_columns)
        for table, expected_columns in (
            ("hxy_product_tasks", ("task_id",)),
            ("hxy_product_task_events", ("event_id",)),
            ("hxy_product_training_sessions", ("training_session_id",)),
        )
    )

    def has_unique_index(
        name: str,
        expected_columns: tuple[str, ...],
    ) -> bool:
        return any(
            str(row.get("table_schema") or "") == "public"
            and str(row.get("table_name") or "") == "hxy_product_tasks"
            and str(row.get("index_name") or "") == name
            and row.get("indisvalid") is True
            and row.get("indisunique") is True
            and _parse_index_columns(str(row.get("index_definition") or ""))
            == expected_columns
            and row.get("predicate") in (None, "")
            for row in indexes
        )

    key_contract = primary_keys and has_unique_index(
        "uq_hxy_product_tasks_organization_task",
        ("organization_id", "task_id"),
    ) and has_unique_index(
        "uq_hxy_product_tasks_organization_store_task",
        ("organization_id", "store_id", "task_id"),
    )

    actual_checks: dict[str, set[str]] = {}
    for row in constraints:
        if (
            str(row.get("constraint_type") or "") == "c"
            and str(row.get("source_schema") or "") == "public"
            and row.get("convalidated") is True
        ):
            actual_checks.setdefault(str(row.get("source_table") or ""), set()).add(
                _canonical_contract_expression(row.get("check_expression"))
            )
    business_checks = all(
        any(
            _canonical_contract_expression(variant) in actual_checks.get(table, set())
            for variant in variants
        )
        for table, expected_checks in _BUSINESS_CHECK_CONTRACT.items()
        for variants in expected_checks
    )

    normalized_foreign_keys: set[
        tuple[str, tuple[str, ...], str, tuple[str, ...]]
    ] = set()
    for row in constraints:
        if (
            str(row.get("constraint_type") or "") != "f"
            or str(row.get("source_schema") or "") != "public"
            or str(row.get("target_schema") or "") != "public"
            or row.get("convalidated") is not True
            or str(row.get("confdeltype") or "") != "r"
        ):
            continue
        normalized_foreign_keys.add(
            (
                str(row.get("source_table") or ""),
                tuple(str(item) for item in row.get("source_columns") or ()),
                str(row.get("target_table") or ""),
                tuple(str(item) for item in row.get("target_columns") or ()),
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
                ("store_id",),
                "stores",
                ("store_id",),
            ),
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
            (
                "hxy_product_tasks",
                ("creator_assignment_id", "source_conversation_id"),
                "hxy_product_conversations",
                ("assignment_id", "conversation_id"),
            ),
            (
                "hxy_product_tasks",
                (
                    "creator_assignment_id",
                    "source_conversation_id",
                    "source_message_id",
                ),
                "hxy_product_messages",
                ("assignment_id", "conversation_id", "message_id"),
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

    normalized_triggers = []
    for row in triggers:
        parsed_definition = _parse_trigger_definition(
            str(row.get("definition") or "")
        )
        normalized_triggers.append(
            {
                "table_schema": str(row.get("table_schema") or ""),
                "table": str(row.get("table_name") or ""),
                "name": str(row.get("trigger_name") or ""),
                "enabled": str(row.get("tgenabled") or "").upper(),
                "condition": row.get("tgqual"),
                "function_schema": str(row.get("function_schema") or ""),
                "function": str(row.get("function_name") or ""),
                "function_source": _normalize_function_source(
                    row.get("prosrc")
                ),
                "function_definition": row.get("function_definition"),
                "timing": parsed_definition[0] if parsed_definition else "",
                "events": parsed_definition[1] if parsed_definition else frozenset(),
                "level": parsed_definition[2] if parsed_definition else "",
            }
        )

    def has_trigger(
        table: str,
        name: str,
        function: str,
        function_source: str,
        timing: str,
        events: frozenset[str],
        level: str,
    ) -> bool:
        return any(
            item["table"] == table
            and item["name"] == name
            and item["enabled"] in {"O", "A"}
            and item["condition"] is None
            and item["table_schema"] == "public"
            and item["function_schema"] == "public"
            and item["function"] == function
            and item["function_source"] == function_source
            and _function_definition_matches(
                item["function_definition"],
                function_source,
            )
            and item["timing"] == timing
            and item["events"] == events
            and item["level"] == level
            for item in normalized_triggers
        )

    task_append_only = has_trigger(
        "hxy_product_task_events",
        "trg_hxy_product_task_events_append_only",
        "hxy_reject_task_event_mutation",
        "BEGIN RAISE EXCEPTION 'hxy_product_task_events is append-only'; END;",
        "BEFORE",
        frozenset({"UPDATE", "DELETE"}),
        "ROW",
    ) and has_trigger(
        "hxy_product_task_events",
        "trg_hxy_product_task_events_no_truncate",
        "hxy_reject_task_event_mutation",
        "BEGIN RAISE EXCEPTION 'hxy_product_task_events is append-only'; END;",
        "BEFORE",
        frozenset({"TRUNCATE"}),
        "STATEMENT",
    )
    training_append_only = has_trigger(
        "hxy_product_training_sessions",
        "trg_hxy_product_training_append_only",
        "hxy_reject_product_training_mutation",
        "BEGIN RAISE EXCEPTION 'hxy_product_training_sessions is append-only'; END;",
        "BEFORE",
        frozenset({"UPDATE", "DELETE"}),
        "ROW",
    ) and has_trigger(
        "hxy_product_training_sessions",
        "trg_hxy_product_training_no_truncate",
        "hxy_reject_product_training_mutation",
        "BEGIN RAISE EXCEPTION 'hxy_product_training_sessions is append-only'; END;",
        "BEFORE",
        frozenset({"TRUNCATE"}),
        "STATEMENT",
    )

    def has_index(
        table: str,
        name: str,
        columns: tuple[str, ...],
        predicate: str | None,
    ) -> bool:
        return any(
            str(row.get("table_schema") or "") == "public"
            and str(row.get("table_name") or "") == table
            and str(row.get("index_name") or "") == name
            and row.get("indisvalid") is True
            and row.get("indisunique") is False
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
            "role_journey_columns",
            column_contract,
            "complete" if column_contract else "missing or mismatched",
        ),
        _check(
            "role_journey_keys",
            key_contract,
            "complete" if key_contract else "missing or mismatched",
        ),
        _check(
            "role_journey_business_checks",
            business_checks,
            "complete" if business_checks else "missing or mismatched",
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
    migration_loader: MigrationLoader | None = None,
) -> dict[str, Any]:
    return _inspect_database(
        root_dir,
        database_url,
        phase="preflight",
        connect_factory=connect_factory,
        activation_runner=activation_runner,
        git_inspector=git_inspector,
        trusted_root=trusted_root,
        migration_loader=migration_loader,
    )


def run_postflight(
    root_dir: Path,
    database_url: str,
    *,
    connect_factory: ConnectFactory | None = None,
    activation_runner: ActivationRunner = activation_release.run_postflight,
    trusted_root: Path = _DEFAULT_TRUSTED_ROOT,
    migration_loader: MigrationLoader | None = None,
) -> dict[str, Any]:
    return _inspect_database(
        root_dir,
        database_url,
        phase="postflight",
        connect_factory=connect_factory,
        activation_runner=activation_runner,
        trusted_root=trusted_root,
        migration_loader=migration_loader,
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
    migration_loader: MigrationLoader | None = None,
) -> dict[str, Any]:
    preflight_inspector = preflight_runner
    if preflight_runner is run_preflight:
        preflight_inspector = lambda root, dsn: run_preflight(
            root,
            dsn,
            migration_loader=migration_loader,
        )
    result = create_release_backup(
        ROLE_JOURNEYS_RELEASE,
        root_dir,
        database_url,
        output_root=output_root,
        preflight_inspector=preflight_inspector,
        runner=runner,
        now=now,
        git_commit=git_commit,
        trusted_root=trusted_root,
        migration_loader=migration_loader,
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
    migration_loader: MigrationLoader | None = None,
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
        migration_loader=migration_loader,
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
    git_inspector: GitInspector | None = None,
    trusted_root: Path = _DEFAULT_TRUSTED_ROOT,
    migration_loader: MigrationLoader | None = None,
) -> dict[str, Any]:
    if confirmation != APPLY_CONFIRMATION:
        raise ReleaseAuthorizationError("exact migration confirmation is required")
    git_state = (git_inspector or inspect_git_worktree)(root_dir)
    commit_valid = bool(
        git_state.get("commit_valid", git_state.get("commit") != "unknown")
    )
    worktree_clean = bool(
        git_state.get("worktree_clean", git_state.get("status") == "passed")
    )
    if not commit_valid or not worktree_clean:
        raise ReleaseAuthorizationError(
            "apply requires a real Git commit and clean worktree"
        )
    postflight_inspector = postflight_runner
    if postflight_runner is run_postflight:
        postflight_inspector = lambda root, dsn: run_postflight(
            root,
            dsn,
            migration_loader=migration_loader,
        )
    result = apply_release_migrations(
        ROLE_JOURNEYS_RELEASE,
        root_dir,
        database_url,
        manifest_path=manifest_path,
        confirmation=confirmation,
        postflight_inspector=postflight_inspector,
        runner=runner,
        now=now,
        git_commit=git_commit,
        trusted_root=trusted_root,
        migration_loader=migration_loader,
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
            result = run_preflight(
                args.root_dir,
                database_url,
                migration_loader=git_head_migration_loader,
            )
        elif args.command == "backup":
            result = create_backup(
                args.root_dir,
                database_url,
                output_root=args.output_root or _DEFAULT_BACKUP_ROOT,
                migration_loader=git_head_migration_loader,
            )
        elif args.command == "apply":
            if args.backup_manifest is None:
                raise ReleaseAuthorizationError("--backup-manifest is required")
            result = apply_role_journeys_migrations(
                args.root_dir,
                database_url,
                manifest_path=args.backup_manifest,
                confirmation=args.confirm,
                migration_loader=git_head_migration_loader,
            )
        else:
            result = run_postflight(
                args.root_dir,
                database_url,
                migration_loader=git_head_migration_loader,
            )
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
