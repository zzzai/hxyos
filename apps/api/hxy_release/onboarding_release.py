from __future__ import annotations

import argparse
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row

from . import role_journeys_release
from .guarded_migration import (
    CommandRunner,
    InspectionRunner,
    MigrationLoader,
    MigrationReleaseSpec,
    ReleaseAppliedError,
    ReleaseAuthorizationError,
    ReleaseBackupError,
    ReleaseBoundaryError,
    ReleaseCleanupError,
    ReleaseExecutionError,
    ReleaseInstanceError,
    ReleasePostflightError,
    apply_release_migrations,
    create_release_backup,
    git_head_migration_loader,
    migration_inventory as guarded_migration_inventory,
    render_result,
    validate_release_backup_manifest,
)


ONBOARDING_MIGRATIONS = ("017_hxy_governed_onboarding.sql",)
APPLY_CONFIRMATION = "APPLY-HXY-017"
BACKUP_VERSION = "hxy-governed-onboarding-backup.v1"
_DEFAULT_TRUSTED_ROOT = Path("/root/hxy")
_DEFAULT_BACKUP_ROOT = _DEFAULT_TRUSTED_ROOT / "data" / "backups" / "onboarding"
_ONBOARDING_TABLES = ("hxy_member_invites", "hxy_member_invite_events")

ONBOARDING_RELEASE = MigrationReleaseSpec(
    release_id="hxy-governed-onboarding-017",
    manifest_version=BACKUP_VERSION,
    migrations=ONBOARDING_MIGRATIONS,
    confirmation=APPLY_CONFIRMATION,
    advisory_lock="hxy-governed-onboarding-017",
    dump_filename="hxy-before-onboarding.dump",
)

ConnectFactory = Callable[[str], Any]
PrerequisiteRunner = Callable[..., dict[str, Any]]


_COLUMN_CONTRACT = {
    "hxy_member_invites": (
        ("invite_id", "uuid", "NO", "gen_random_uuid()"),
        ("organization_id", "uuid", "NO", None),
        ("store_id", "text", "NO", None),
        ("role", "text", "NO", None),
        ("display_name", "text", "NO", None),
        ("token_hash", "text", "NO", None),
        ("created_by_assignment_id", "uuid", "NO", None),
        ("status", "text", "NO", "'pending'::text"),
        ("expires_at", "timestamp with time zone", "NO", None),
        ("redeemed_account_id", "uuid", "YES", None),
        ("redeemed_assignment_id", "uuid", "YES", None),
        ("redeemed_at", "timestamp with time zone", "YES", None),
        ("revoked_at", "timestamp with time zone", "YES", None),
        ("created_at", "timestamp with time zone", "NO", "now()"),
        ("updated_at", "timestamp with time zone", "NO", "now()"),
    ),
    "hxy_member_invite_events": (
        ("event_id", "uuid", "NO", "gen_random_uuid()"),
        ("organization_id", "uuid", "NO", None),
        ("store_id", "text", "NO", None),
        ("invite_id", "uuid", "YES", None),
        ("actor_assignment_id", "uuid", "NO", None),
        ("subject_assignment_id", "uuid", "YES", None),
        ("event_type", "text", "NO", None),
        ("payload", "jsonb", "NO", "'{}'::jsonb"),
        ("created_at", "timestamp with time zone", "NO", "now()"),
    ),
}

_FOREIGN_KEY_CONTRACT = (
    ("hxy_member_invites", ("organization_id",), "hxy_organizations", ("organization_id",)),
    ("hxy_member_invites", ("store_id",), "stores", ("store_id",)),
    ("hxy_member_invites", ("redeemed_account_id",), "staff_accounts", ("id",)),
    ("hxy_member_invites", ("redeemed_assignment_id",), "hxy_role_assignments", ("assignment_id",)),
    ("hxy_member_invites", ("organization_id", "store_id"), "hxy_organization_stores", ("organization_id", "store_id")),
    ("hxy_member_invites", ("organization_id", "created_by_assignment_id"), "hxy_role_assignments", ("organization_id", "assignment_id")),
    (
        "hxy_member_invites",
        ("organization_id", "store_id", "redeemed_assignment_id", "redeemed_account_id"),
        "hxy_role_assignments",
        ("organization_id", "store_id", "assignment_id", "account_id"),
    ),
    ("hxy_member_invite_events", ("organization_id",), "hxy_organizations", ("organization_id",)),
    ("hxy_member_invite_events", ("store_id",), "stores", ("store_id",)),
    ("hxy_member_invite_events", ("organization_id", "store_id"), "hxy_organization_stores", ("organization_id", "store_id")),
    (
        "hxy_member_invite_events",
        ("organization_id", "store_id", "invite_id"),
        "hxy_member_invites",
        ("organization_id", "store_id", "invite_id"),
    ),
    ("hxy_member_invite_events", ("organization_id", "actor_assignment_id"), "hxy_role_assignments", ("organization_id", "assignment_id")),
    (
        "hxy_member_invite_events",
        ("organization_id", "store_id", "subject_assignment_id"),
        "hxy_role_assignments",
        ("organization_id", "store_id", "assignment_id"),
    ),
)

_INDEX_CONTRACT = (
    ("hxy_role_assignments", "uq_hxy_role_assignments_onboarding_identity", ("organization_id", "store_id", "assignment_id", "account_id"), True, None),
    ("hxy_member_invites", "uq_hxy_member_invites_scope_invite", ("organization_id", "store_id", "invite_id"), True, None),
    ("hxy_member_invites", "idx_hxy_member_invites_expires", ("expires_at",), False, None),
    ("hxy_member_invites", "idx_hxy_member_invites_scope_status", ("organization_id", "store_id", "status", "created_at desc"), False, None),
    ("hxy_member_invite_events", "idx_hxy_member_invite_events_invite_created", ("invite_id", "created_at", "event_id"), False, "invite_idisnotnull"),
    ("hxy_member_invite_events", "idx_hxy_member_invite_events_scope_created", ("organization_id", "store_id", "created_at desc"), False, None),
)


def migration_inventory(
    root_dir: Path,
    *,
    trusted_root: Path = _DEFAULT_TRUSTED_ROOT,
    migration_loader: MigrationLoader | None = None,
) -> list[dict[str, str]]:
    return guarded_migration_inventory(
        ONBOARDING_RELEASE,
        root_dir,
        trusted_root=trusted_root,
        migration_loader=migration_loader,
    )


def _prerequisite_result(
    root_dir: Path,
    database_url: str,
    **kwargs: Any,
) -> dict[str, Any]:
    return role_journeys_release.run_postflight(root_dir, database_url, **kwargs)


def _default_connect(database_url: str):
    return psycopg.connect(database_url, row_factory=dict_row)


def _check(name: str, passed: bool, detail: str) -> dict[str, str]:
    return {
        "name": name,
        "status": "passed" if passed else "failed",
        "detail": detail[:200],
    }


def _canonical_default(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return " ".join(str(value).lower().split())


def _canonical_expression(value: Any) -> str:
    normalized = str(value or "").lower().replace('"', "")
    normalized = re.sub(r"::(?:text|jsonb|character varying)", "", normalized)
    return re.sub(r"[\s()]", "", normalized)


def _parse_index_columns(definition: str) -> tuple[str, ...] | None:
    match = re.search(r"\bUSING\s+btree\s*\(([^)]*)\)", definition, re.IGNORECASE)
    if match is None:
        return None
    columns: list[str] = []
    for item in match.group(1).split(","):
        normalized = " ".join(item.replace('"', "").lower().split())
        normalized = re.sub(r"\s+nulls\s+(first|last)$", "", normalized)
        columns.append(normalized)
    return tuple(columns)


def _parse_trigger_definition(
    definition: str,
) -> tuple[str, frozenset[str], str] | None:
    normalized = " ".join(definition.upper().split())
    timing = re.search(r"\b(BEFORE|AFTER|INSTEAD OF)\s+(.+?)\s+ON\s+", normalized)
    level = re.search(r"\bFOR EACH (ROW|STATEMENT)\b", normalized)
    if timing is None or level is None:
        return None
    events = re.split(r"\s+OR\s+", timing.group(2))
    if not events or any(item not in {"INSERT", "UPDATE", "DELETE", "TRUNCATE"} for item in events):
        return None
    return timing.group(1), frozenset(events), level.group(1)


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
    columns_ok = all(
        actual_columns.get((table, name))
        == ("public", data_type, nullable, _canonical_default(default))
        for table, expected in _COLUMN_CONTRACT.items()
        for name, data_type, nullable, default in expected
    )

    def source_columns(row: dict[str, Any]) -> tuple[str, ...]:
        return tuple(str(item) for item in row.get("source_columns") or ())

    def local_constraint(
        constraint_type: str,
        table: str,
        expected_columns: tuple[str, ...],
    ) -> bool:
        return any(
            str(row.get("constraint_type") or "") == constraint_type
            and str(row.get("source_schema") or "") == "public"
            and str(row.get("source_table") or "") == table
            and source_columns(row) == expected_columns
            and row.get("convalidated") is True
            for row in constraints
        )

    keys_ok = all(
        local_constraint(kind, table, expected)
        for kind, table, expected in (
            ("p", "hxy_member_invites", ("invite_id",)),
            ("u", "hxy_member_invites", ("token_hash",)),
            ("p", "hxy_member_invite_events", ("event_id",)),
        )
    )

    check_expressions: dict[str, list[str]] = {}
    for row in constraints:
        if (
            str(row.get("constraint_type") or "") == "c"
            and str(row.get("source_schema") or "") == "public"
            and row.get("convalidated") is True
        ):
            check_expressions.setdefault(str(row.get("source_table") or ""), []).append(
                _canonical_expression(row.get("check_expression"))
            )

    def has_check(table: str, *fragments: str) -> bool:
        canonical_fragments = tuple(_canonical_expression(item) for item in fragments)
        return any(
            all(fragment in expression for fragment in canonical_fragments)
            for expression in check_expressions.get(table, [])
        )

    checks_ok = all(
        (
            has_check("hxy_member_invites", "role=anyarray['store_manager','store_employee']"),
            has_check("hxy_member_invites", "char_length(btrim(display_name))>=1", "char_length(btrim(display_name))<=80"),
            has_check("hxy_member_invites", "token_hash~'^[0-9a-f]{64}$'"),
            has_check("hxy_member_invites", "status=anyarray['pending','redeemed','revoked']"),
            has_check("hxy_member_invites", "expires_at>created_at"),
            has_check(
                "hxy_member_invites",
                "status='pending'andredeemed_account_idisnullandredeemed_assignment_idisnullandredeemed_atisnullandrevoked_atisnull",
                "status='redeemed'andredeemed_account_idisnotnullandredeemed_assignment_idisnotnullandredeemed_atisnotnullandrevoked_atisnull",
                "status='revoked'andredeemed_account_idisnullandredeemed_assignment_idisnullandredeemed_atisnullandrevoked_atisnotnull",
            ),
            has_check("hxy_member_invite_events", "event_type=anyarray['created','redeemed','revoked','member_deactivated']"),
            has_check("hxy_member_invite_events", "payload='{}'"),
            has_check(
                "hxy_member_invite_events",
                "event_type=anyarray['created','revoked']andinvite_idisnotnullandsubject_assignment_idisnull",
                "event_type='redeemed'andinvite_idisnotnullandsubject_assignment_idisnotnull",
                "event_type='member_deactivated'andinvite_idisnullandsubject_assignment_idisnotnull",
            ),
        )
    )

    actual_foreign_keys = {
        (
            str(row.get("source_table") or ""),
            source_columns(row),
            str(row.get("target_table") or ""),
            tuple(str(item) for item in row.get("target_columns") or ()),
        )
        for row in constraints
        if str(row.get("constraint_type") or "") == "f"
        and str(row.get("source_schema") or "") == "public"
        and str(row.get("target_schema") or "") == "public"
        and row.get("convalidated") is True
        and str(row.get("confdeltype") or "") == "r"
    }
    foreign_keys_ok = all(item in actual_foreign_keys for item in _FOREIGN_KEY_CONTRACT)

    def trigger_ok(
        name: str,
        expected_events: frozenset[str],
        expected_level: str,
    ) -> bool:
        source = "BEGIN RAISE EXCEPTION 'hxy_member_invite_events is append-only'; END;"
        normalized_source = " ".join(source.split())
        return any(
            str(row.get("table_schema") or "") == "public"
            and str(row.get("table_name") or "") == "hxy_member_invite_events"
            and str(row.get("trigger_name") or "") == name
            and str(row.get("tgenabled") or "") in {"O", "A"}
            and row.get("tgqual") in (None, "")
            and str(row.get("function_schema") or "") == "public"
            and str(row.get("function_name") or "") == "hxy_reject_member_invite_event_mutation"
            and " ".join(str(row.get("prosrc") or "").split()) == normalized_source
            and normalized_source in " ".join(str(row.get("function_definition") or "").split())
            and "language plpgsql" in str(row.get("function_definition") or "").lower()
            and _parse_trigger_definition(str(row.get("definition") or ""))
            == ("BEFORE", expected_events, expected_level)
            for row in triggers
        )

    triggers_ok = trigger_ok(
        "trg_hxy_member_invite_events_append_only",
        frozenset({"UPDATE", "DELETE"}),
        "ROW",
    ) and trigger_ok(
        "trg_hxy_member_invite_events_no_truncate",
        frozenset({"TRUNCATE"}),
        "STATEMENT",
    )

    def index_ok(
        table: str,
        name: str,
        expected_columns: tuple[str, ...],
        unique: bool,
        predicate: str | None,
    ) -> bool:
        return any(
            str(row.get("table_schema") or "") == "public"
            and str(row.get("table_name") or "") == table
            and str(row.get("index_name") or "") == name
            and row.get("indisvalid") is True
            and row.get("indisunique") is unique
            and _parse_index_columns(str(row.get("index_definition") or "")) == expected_columns
            and (
                _canonical_expression(row.get("predicate"))
                if row.get("predicate") not in (None, "")
                else None
            )
            == predicate
            for row in indexes
        )

    indexes_ok = all(index_ok(*item) for item in _INDEX_CONTRACT)

    return [
        _check("onboarding_tables", not pending_tables, "complete" if not pending_tables else f"missing={','.join(pending_tables)}"),
        _check("onboarding_columns", columns_ok, "complete" if columns_ok else "missing or mismatched"),
        _check("onboarding_keys", keys_ok, "complete" if keys_ok else "missing or mismatched"),
        _check("onboarding_business_checks", checks_ok, "complete" if checks_ok else "missing or mismatched"),
        _check("onboarding_scope_foreign_keys", foreign_keys_ok, "complete" if foreign_keys_ok else "missing or mismatched"),
        _check("onboarding_event_append_only", triggers_ok, "enforced" if triggers_ok else "missing or mismatched"),
        _check("onboarding_indexes", indexes_ok, "complete" if indexes_ok else "missing or mismatched"),
    ]


def run_preflight(
    root_dir: Path,
    database_url: str,
    *,
    connect_factory: Any = None,
    prerequisite_runner: PrerequisiteRunner = _prerequisite_result,
    git_inspector: Any = None,
    trusted_root: Path = _DEFAULT_TRUSTED_ROOT,
    migration_loader: MigrationLoader | None = None,
) -> dict[str, Any]:
    prerequisite = prerequisite_runner(
        root_dir,
        database_url,
        connect_factory=connect_factory,
        trusted_root=trusted_root,
        migration_loader=migration_loader,
    )
    git_state = (git_inspector or role_journeys_release.inspect_git_worktree)(root_dir)
    inventory = migration_inventory(
        root_dir,
        trusted_root=trusted_root,
        migration_loader=migration_loader,
    )
    checks = [
        _check(
            "postgres_major",
            int(prerequisite.get("server_major") or 0) == 16,
            f"major={int(prerequisite.get('server_major') or 0)}",
        ),
        _check(
            "role_journeys_prerequisite",
            prerequisite.get("status") == "passed",
            "009-016 postflight passed"
            if prerequisite.get("status") == "passed"
            else "009-016 postflight failed",
        ),
        _check(
            "git_commit",
            bool(git_state.get("commit_valid")),
            "valid commit" if git_state.get("commit_valid") else "invalid commit",
        ),
        _check(
            "worktree_clean",
            bool(git_state.get("worktree_clean")),
            str(git_state.get("detail") or "unknown"),
        ),
        _check(
            "migration_inventory",
            len(inventory) == 1,
            "017 checksummed" if len(inventory) == 1 else "017 unavailable",
        ),
    ]
    status = "passed" if all(item["status"] == "passed" for item in checks) else "failed"
    return {
        "status": status,
        "phase": "preflight",
        "database": prerequisite.get("database", {}),
        "server_major": prerequisite.get("server_major", 0),
        "git_commit": git_state.get("commit", "unknown"),
        "migration_count": len(inventory),
        "checks": checks,
    }


def run_postflight(
    root_dir: Path,
    database_url: str,
    *,
    connect_factory: Any = None,
    prerequisite_runner: PrerequisiteRunner = _prerequisite_result,
    trusted_root: Path = _DEFAULT_TRUSTED_ROOT,
    migration_loader: MigrationLoader | None = None,
) -> dict[str, Any]:
    prerequisite = prerequisite_runner(
        root_dir,
        database_url,
        connect_factory=connect_factory,
        trusted_root=trusted_root,
        migration_loader=migration_loader,
    )
    inventory = migration_inventory(
        root_dir,
        trusted_root=trusted_root,
        migration_loader=migration_loader,
    )
    connection_factory = connect_factory or _default_connect
    with connection_factory(database_url) as connection:
        connection.read_only = True
        schema_row = connection.execute(
            """
            /* hxy_onboarding_release:schema */
            SELECT current_schema() AS current_schema
            """
        ).fetchone()
        relation_rows = connection.execute(
            """
            /* hxy_onboarding_release:relations */
            SELECT relation_name AS name
            FROM unnest(%s::text[]) AS relation_name
            WHERE to_regclass('public.' || relation_name) IS NOT NULL
            ORDER BY relation_name
            """,
            (list(_ONBOARDING_TABLES),),
        ).fetchall()
        columns = connection.execute(
            """
            /* hxy_onboarding_release:columns */
            SELECT table_schema, table_name, column_name, data_type,
                   is_nullable, column_default
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = ANY(%s::text[])
            ORDER BY table_name, ordinal_position
            """,
            (list(_ONBOARDING_TABLES),),
        ).fetchall()
        constraints = connection.execute(
            """
            /* hxy_onboarding_release:constraints */
            SELECT constraint_row.conname AS constraint_name,
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
            (list(_ONBOARDING_TABLES),),
        ).fetchall()
        triggers = connection.execute(
            """
            /* hxy_onboarding_release:triggers */
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
            JOIN pg_proc AS function_row ON function_row.oid = trigger_row.tgfoid
            JOIN pg_namespace AS function_namespace
              ON function_namespace.oid = function_row.pronamespace
            WHERE namespace_row.nspname = 'public'
              AND relation.relname = ANY(%s::text[])
              AND NOT trigger_row.tgisinternal
            ORDER BY relation.relname, trigger_row.tgname
            """,
            (list(_ONBOARDING_TABLES),),
        ).fetchall()
        indexes = connection.execute(
            """
            /* hxy_onboarding_release:indexes */
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
            (list(_ONBOARDING_TABLES) + ["hxy_role_assignments"],),
        ).fetchall()

    relation_names = {str(row.get("name") or "") for row in relation_rows}
    pending_tables = sorted(set(_ONBOARDING_TABLES) - relation_names)
    checks = [
        _check(
            "postgres_major",
            int(prerequisite.get("server_major") or 0) == 16,
            f"major={int(prerequisite.get('server_major') or 0)}",
        ),
        _check(
            "role_journeys_prerequisite",
            prerequisite.get("status") == "passed",
            "009-016 postflight passed"
            if prerequisite.get("status") == "passed"
            else "009-016 postflight failed",
        ),
        _check(
            "current_schema",
            str((schema_row or {}).get("current_schema") or "") == "public",
            f"schema={str((schema_row or {}).get('current_schema') or 'unknown')}",
        ),
        _check(
            "migration_inventory",
            len(inventory) == 1,
            "017 checksummed" if len(inventory) == 1 else "017 unavailable",
        ),
        *_postflight_checks(
            pending_tables,
            columns,
            constraints,
            triggers,
            indexes,
        ),
    ]
    status = "passed" if all(item["status"] == "passed" for item in checks) else "failed"
    return {
        "status": status,
        "phase": "postflight",
        "database": prerequisite.get("database", {}),
        "server_major": prerequisite.get("server_major", 0),
        "pending_tables": pending_tables,
        "migration_count": len(inventory),
        "checks": checks,
    }


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
    inspector = preflight_runner
    if preflight_runner is run_preflight:
        inspector = lambda root, dsn: run_preflight(
            root,
            dsn,
            migration_loader=migration_loader,
        )
    result = create_release_backup(
        ONBOARDING_RELEASE,
        root_dir,
        database_url,
        output_root=output_root,
        preflight_inspector=inspector,
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
        ONBOARDING_RELEASE,
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


def apply_onboarding_migration(
    root_dir: Path,
    database_url: str,
    *,
    manifest_path: Path,
    confirmation: str,
    runner: CommandRunner | None = None,
    now: datetime | None = None,
    git_commit: str | None = None,
    postflight_runner: InspectionRunner = run_postflight,
    git_inspector: Any = None,
    trusted_root: Path = _DEFAULT_TRUSTED_ROOT,
    migration_loader: MigrationLoader | None = None,
) -> dict[str, Any]:
    if confirmation != APPLY_CONFIRMATION:
        raise ReleaseAuthorizationError("exact migration confirmation is required")
    git_state = (git_inspector or role_journeys_release.inspect_git_worktree)(root_dir)
    if not git_state.get("commit_valid") or not git_state.get("worktree_clean"):
        raise ReleaseAuthorizationError(
            "apply requires a real Git commit and clean worktree"
        )
    inspector = postflight_runner
    if postflight_runner is run_postflight:
        inspector = lambda root, dsn: run_postflight(
            root,
            dsn,
            migration_loader=migration_loader,
        )
    result = apply_release_migrations(
        ONBOARDING_RELEASE,
        root_dir,
        database_url,
        manifest_path=manifest_path,
        confirmation=confirmation,
        postflight_inspector=inspector,
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
    parser = argparse.ArgumentParser(description="Guarded HXY onboarding release")
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


def _database_sensitive_values(database_url: str) -> tuple[str, ...]:
    values = [database_url]
    try:
        parsed = conninfo_to_dict(database_url)
    except Exception:
        return tuple(item for item in values if item)
    values.extend(str(parsed.get(key) or "") for key in ("password", "sslpassword"))
    return tuple(item for item in values if item)


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
            result = apply_onboarding_migration(
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
        if exc.cleanup_failed is not None:
            result["cleanup_failed"] = exc.cleanup_failed
    except (ReleaseInstanceError, ReleaseAppliedError, ReleaseCleanupError) as exc:
        result = {
            "status": "failed",
            "phase": args.command,
            "error_type": "ReleaseExecutionError" if exc.applied else type(exc).__name__,
            "error": str(exc),
            "applied": exc.applied,
        }
        if getattr(exc, "error_code", None):
            result["error_code"] = exc.error_code
        if getattr(exc, "detail", None) is not None:
            result["detail"] = exc.detail
        if getattr(exc, "cleanup_failed", None) is not None:
            result["cleanup_failed"] = exc.cleanup_failed
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
