from __future__ import annotations

import argparse
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

import psycopg
from psycopg.rows import dict_row

from . import role_journeys_release, source_authority_release
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
    database_identity,
    git_head_migration_loader,
    migration_inventory as guarded_migration_inventory,
    render_result,
    validate_hxy_boundary,
    validate_release_backup_manifest,
)


GLOBAL_SOURCE_AUTHORITY_MIGRATIONS = ("019_hxy_global_source_authority.sql",)
APPLY_CONFIRMATION = "APPLY-HXY-019"
TARGET_RELATIONS = (
    "hxy_knowledge_assets",
    "hxy_knowledge_asset_authority_events",
)
BACKUP_VERSION = "hxy-global-source-authority-backup.v1"
_DEFAULT_TRUSTED_ROOT = Path("/root/hxy")
_DEFAULT_BACKUP_ROOT = _DEFAULT_TRUSTED_ROOT / "data" / "backups" / "global-source-authority"

GLOBAL_SOURCE_AUTHORITY_RELEASE = MigrationReleaseSpec(
    release_id="hxy-global-source-authority-019",
    manifest_version=BACKUP_VERSION,
    migrations=GLOBAL_SOURCE_AUTHORITY_MIGRATIONS,
    confirmation=APPLY_CONFIRMATION,
    advisory_lock="hxy-global-source-authority-019",
    dump_filename="hxy-before-global-source-authority.dump",
)

ConnectFactory = Callable[[str], Any]
PrerequisiteRunner = Callable[..., dict[str, Any]]

_AUTHORITY_COLUMN_CONTRACT = {
    "source_origin": ("text", "NO", "'unknown'::text"),
    "source_authority": ("text", "NO", "'external_reference'::text"),
    "authority_version": ("integer", "NO", "1"),
    "authority_organization_id": ("uuid", "YES", None),
}

_EVENT_COLUMN_CONTRACT = (
    ("event_id", "uuid", "NO", "gen_random_uuid()"),
    ("asset_id", "text", "NO", None),
    ("event_type", "text", "NO", None),
    ("organization_id", "uuid", "YES", None),
    ("actor_assignment_id", "uuid", "YES", None),
    ("previous_origin", "text", "YES", None),
    ("new_origin", "text", "NO", None),
    ("previous_authority", "text", "YES", None),
    ("new_authority", "text", "NO", None),
    ("previous_version", "integer", "YES", None),
    ("version_no", "integer", "NO", None),
    ("reason", "text", "NO", None),
    ("created_at", "timestamp with time zone", "NO", "now()"),
)

_EVENT_STATE_COLUMNS = (
    "event_type",
    "organization_id",
    "actor_assignment_id",
    "previous_origin",
    "previous_authority",
    "previous_version",
    "new_origin",
    "new_authority",
    "version_no",
)

_CONSTRAINT_CONTRACT = {
    ("hxy_knowledge_assets", "p", ("asset_id",)),
    ("hxy_knowledge_assets", "c", ("source_origin",)),
    ("hxy_knowledge_assets", "c", ("source_authority",)),
    ("hxy_knowledge_assets", "c", ("authority_version",)),
    ("hxy_knowledge_assets", "f", ("authority_organization_id",)),
    ("hxy_knowledge_assets", "c", ("source_origin", "source_authority")),
    ("hxy_knowledge_asset_authority_events", "p", ("event_id",)),
    ("hxy_knowledge_asset_authority_events", "u", ("asset_id", "version_no")),
    ("hxy_knowledge_asset_authority_events", "f", ("asset_id",)),
    ("hxy_knowledge_asset_authority_events", "f", ("organization_id",)),
    ("hxy_knowledge_asset_authority_events", "f", ("actor_assignment_id",)),
    ("hxy_knowledge_asset_authority_events", "c", ("event_type",)),
    ("hxy_knowledge_asset_authority_events", "c", ("previous_origin",)),
    ("hxy_knowledge_asset_authority_events", "c", ("new_origin",)),
    ("hxy_knowledge_asset_authority_events", "c", ("previous_authority",)),
    ("hxy_knowledge_asset_authority_events", "c", ("new_authority",)),
    ("hxy_knowledge_asset_authority_events", "c", ("previous_version",)),
    ("hxy_knowledge_asset_authority_events", "c", ("version_no",)),
    ("hxy_knowledge_asset_authority_events", "c", ("reason",)),
    ("hxy_knowledge_asset_authority_events", "c", _EVENT_STATE_COLUMNS),
}

_TRIGGER_CONTRACT = {
    (
        "hxy_knowledge_asset_authority_events",
        "trg_hxy_knowledge_asset_authority_events_validate",
        "BEFORE",
        ("INSERT",),
        "ROW",
        "hxy_validate_knowledge_asset_authority_event",
    ),
    (
        "hxy_knowledge_assets",
        "trg_hxy_knowledge_assets_initial_authority",
        "AFTER",
        ("INSERT",),
        "ROW",
        "hxy_record_initial_knowledge_asset_authority",
    ),
    (
        "hxy_knowledge_assets",
        "trg_hxy_knowledge_assets_authority_version_guard",
        "BEFORE",
        ("UPDATE",),
        "ROW",
        "hxy_enforce_knowledge_asset_authority_version",
    ),
    (
        "hxy_knowledge_asset_authority_events",
        "trg_hxy_knowledge_asset_authority_events_append_only",
        "BEFORE",
        ("DELETE", "UPDATE"),
        "ROW",
        "hxy_reject_knowledge_asset_authority_event_mutation",
    ),
    (
        "hxy_knowledge_asset_authority_events",
        "trg_hxy_knowledge_asset_authority_events_no_truncate",
        "BEFORE",
        ("TRUNCATE",),
        "STATEMENT",
        "hxy_reject_knowledge_asset_authority_event_mutation",
    ),
}

_TRIGGER_UPDATE_COLUMNS_CONTRACT = {
    "trg_hxy_knowledge_assets_authority_version_guard": (
        "authority_organization_id",
        "authority_version",
        "source_authority",
        "source_origin",
    )
}

_ROUTINE_CONTRACT = {
    "hxy_validate_knowledge_asset_authority_event",
    "hxy_record_initial_knowledge_asset_authority",
    "hxy_enforce_knowledge_asset_authority_version",
    "hxy_reject_knowledge_asset_authority_event_mutation",
}

_INDEX_CONTRACT = (
    "hxy_knowledge_asset_authority_events",
    "idx_hxy_knowledge_asset_authority_events_asset",
    ("asset_id", "version_no desc"),
    False,
)

_CHECK_DEFINITION_CONTRACT = {
    ("hxy_knowledge_assets", ("source_origin",)): (
        "CHECK (source_origin = ANY (ARRAY['internal'::text, 'external'::text, 'unknown'::text]))"
    ),
    ("hxy_knowledge_assets", ("source_authority",)): (
        "CHECK (source_authority = ANY (ARRAY['official_internal'::text, "
        "'internal_material'::text, 'external_reference'::text]))"
    ),
    ("hxy_knowledge_assets", ("authority_version",)): "CHECK (authority_version > 0)",
    ("hxy_knowledge_assets", ("source_origin", "source_authority")): (
        "CHECK (source_origin = 'internal'::text OR source_authority = 'external_reference'::text)"
    ),
    ("hxy_knowledge_asset_authority_events", ("event_type",)): (
        "CHECK (event_type = ANY (ARRAY['baseline'::text, 'classification'::text]))"
    ),
    ("hxy_knowledge_asset_authority_events", ("previous_origin",)): (
        "CHECK (previous_origin IS NULL OR (previous_origin = ANY "
        "(ARRAY['internal'::text, 'external'::text, 'unknown'::text])))"
    ),
    ("hxy_knowledge_asset_authority_events", ("new_origin",)): (
        "CHECK (new_origin = ANY (ARRAY['internal'::text, 'external'::text, 'unknown'::text]))"
    ),
    ("hxy_knowledge_asset_authority_events", ("previous_authority",)): (
        "CHECK (previous_authority IS NULL OR (previous_authority = ANY "
        "(ARRAY['official_internal'::text, 'internal_material'::text, "
        "'external_reference'::text])))"
    ),
    ("hxy_knowledge_asset_authority_events", ("new_authority",)): (
        "CHECK (new_authority = ANY (ARRAY['official_internal'::text, "
        "'internal_material'::text, 'external_reference'::text]))"
    ),
    ("hxy_knowledge_asset_authority_events", ("previous_version",)): (
        "CHECK (previous_version IS NULL OR previous_version > 0)"
    ),
    ("hxy_knowledge_asset_authority_events", ("version_no",)): "CHECK (version_no > 0)",
    ("hxy_knowledge_asset_authority_events", ("reason",)): (
        "CHECK (char_length(btrim(reason)) >= 4 AND char_length(btrim(reason)) <= 500)"
    ),
    ("hxy_knowledge_asset_authority_events", _EVENT_STATE_COLUMNS): (
        "CHECK (event_type = 'baseline'::text AND organization_id IS NULL AND "
        "actor_assignment_id IS NULL AND previous_origin IS NULL AND previous_authority IS NULL "
        "AND previous_version IS NULL AND new_origin = 'unknown'::text AND "
        "new_authority = 'external_reference'::text AND version_no = 1 OR "
        "event_type = 'classification'::text AND organization_id IS NOT NULL AND "
        "actor_assignment_id IS NOT NULL AND previous_origin IS NOT NULL AND "
        "previous_authority IS NOT NULL AND previous_version IS NOT NULL AND "
        "version_no = (previous_version + 1))"
    ),
}

_FOREIGN_KEY_CONTRACT = {
    ("hxy_knowledge_assets", ("authority_organization_id",)): (
        "hxy_organizations",
        ("organization_id",),
    ),
    ("hxy_knowledge_asset_authority_events", ("asset_id",)): (
        "hxy_knowledge_assets",
        ("asset_id",),
    ),
    ("hxy_knowledge_asset_authority_events", ("organization_id",)): (
        "hxy_organizations",
        ("organization_id",),
    ),
    ("hxy_knowledge_asset_authority_events", ("actor_assignment_id",)): (
        "hxy_role_assignments",
        ("assignment_id",),
    ),
}


def migration_inventory(
    root_dir: Path,
    *,
    trusted_root: Path = _DEFAULT_TRUSTED_ROOT,
    migration_loader: MigrationLoader | None = None,
) -> list[dict[str, str]]:
    return guarded_migration_inventory(
        GLOBAL_SOURCE_AUTHORITY_RELEASE,
        root_dir,
        trusted_root=trusted_root,
        migration_loader=migration_loader,
    )


def _check(name: str, passed: bool, detail: str) -> dict[str, str]:
    return {"name": name, "status": "passed" if passed else "failed", "detail": detail[:200]}


def _canonical_default(value: Any) -> str | None:
    return source_authority_release._canonical_default(value)


def _canonical_sql(value: Any) -> str:
    return source_authority_release._canonical_sql(value)


def _normalized_columns(rows: Any) -> dict[str, tuple[str, str, str | None]]:
    normalized: dict[str, tuple[str, str, str | None]] = {}
    for row in rows or ():
        if isinstance(row, dict):
            values = (
                row.get("column_name"),
                row.get("data_type"),
                row.get("is_nullable"),
                row.get("column_default"),
            )
        elif isinstance(row, (tuple, list)) and len(row) == 4:
            values = row
        else:
            continue
        normalized[str(values[0])] = (
            str(values[1]),
            str(values[2]),
            _canonical_default(values[3]),
        )
    return normalized


def _normalized_event_columns(rows: Any) -> tuple[tuple[str, str, str, str | None], ...]:
    normalized: list[tuple[str, str, str, str | None]] = []
    for row in rows or ():
        if isinstance(row, dict):
            values = (
                row.get("column_name"),
                row.get("data_type"),
                row.get("is_nullable"),
                row.get("column_default"),
            )
        elif isinstance(row, (tuple, list)) and len(row) == 4:
            values = row
        else:
            continue
        normalized.append(
            (str(values[0]), str(values[1]), str(values[2]), _canonical_default(values[3]))
        )
    return tuple(normalized)


def _normalized_constraints(rows: Any) -> set[tuple[str, str, tuple[str, ...]]]:
    result: set[tuple[str, str, tuple[str, ...]]] = set()
    for row in rows or ():
        if isinstance(row, dict):
            if row.get("convalidated") is not True or row.get("semantic_valid") is not True:
                continue
            result.add(
                (
                    str(row.get("table_name") or ""),
                    str(row.get("constraint_type") or ""),
                    tuple(str(value) for value in row.get("columns") or ()),
                )
            )
        elif isinstance(row, (tuple, list)) and len(row) >= 3:
            result.add((str(row[0]), str(row[1]), tuple(str(value) for value in row[2])))
    return result


def _normalized_triggers(rows: Any) -> set[tuple[str, str, str, tuple[str, ...], str, str]]:
    result: set[tuple[str, str, str, tuple[str, ...], str, str]] = set()
    for row in rows or ():
        if isinstance(row, dict):
            if str(row.get("enabled") or "").upper() not in {"O", "A"}:
                continue
            if row.get("predicate") not in (None, ""):
                continue
            if str(row.get("function_schema") or "") != "public":
                continue
            if row.get("function_source_valid") is not True or row.get("function_definition_valid") is not True:
                continue
            name = str(row.get("trigger_name") or "")
            update_columns = tuple(sorted(str(value).lower() for value in row.get("update_columns") or ()))
            if update_columns != _TRIGGER_UPDATE_COLUMNS_CONTRACT.get(name, ()):
                continue
            item = (
                str(row.get("table_name") or ""),
                name,
                str(row.get("timing") or "").upper(),
                tuple(sorted(str(value).upper() for value in row.get("events") or ())),
                str(row.get("level") or "").upper(),
                str(row.get("function_name") or ""),
            )
        elif isinstance(row, (tuple, list)) and len(row) == 6:
            item = (
                str(row[0]),
                str(row[1]),
                str(row[2]).upper(),
                tuple(sorted(str(value).upper() for value in row[3])),
                str(row[4]).upper(),
                str(row[5]),
            )
        else:
            continue
        result.add(item)
    return result


def _normalized_indexes(rows: Any) -> set[tuple[str, str, tuple[str, ...], bool]]:
    result: set[tuple[str, str, tuple[str, ...], bool]] = set()
    for row in rows or ():
        if isinstance(row, dict):
            if row.get("is_valid") is not True or row.get("predicate") not in (None, ""):
                continue
            item = (
                str(row.get("table_name") or ""),
                str(row.get("index_name") or ""),
                tuple(str(value) for value in row.get("columns") or ()),
                bool(row.get("is_unique")),
            )
        elif isinstance(row, (tuple, list)) and len(row) >= 4:
            item = (str(row[0]), str(row[1]), tuple(str(value) for value in row[2]), bool(row[3]))
        else:
            continue
        result.add(item)
    return result


def _normalized_routines(rows: Any) -> set[str]:
    result: set[str] = set()
    for row in rows or ():
        if isinstance(row, dict):
            if str(row.get("function_schema") or "") != "public":
                continue
            if row.get("source_valid") is not True or row.get("definition_valid") is not True:
                continue
            result.add(str(row.get("function_name") or ""))
        else:
            result.add(str(row))
    return result


def _shape_complete(snapshot: dict[str, Any]) -> bool:
    return (
        _normalized_columns(snapshot.get("authority_columns"))
        == {
            name: (data_type, nullable, _canonical_default(default))
            for name, (data_type, nullable, default) in _AUTHORITY_COLUMN_CONTRACT.items()
        }
        and snapshot.get("event_table_present") is True
        and _normalized_event_columns(snapshot.get("event_columns"))
        == tuple(
            (name, data_type, nullable, _canonical_default(default))
            for name, data_type, nullable, default in _EVENT_COLUMN_CONTRACT
        )
        and _CONSTRAINT_CONTRACT.issubset(_normalized_constraints(snapshot.get("constraints")))
        and _TRIGGER_CONTRACT == _normalized_triggers(snapshot.get("triggers"))
        and _ROUTINE_CONTRACT == _normalized_routines(snapshot.get("routines"))
        and _INDEX_CONTRACT in _normalized_indexes(snapshot.get("indexes"))
    )


def _migration_state(snapshot: dict[str, Any]) -> str:
    no_objects = (
        not snapshot.get("authority_columns")
        and snapshot.get("event_table_present") is False
        and not snapshot.get("event_columns")
        and not snapshot.get("constraints")
        and not snapshot.get("triggers")
        and not snapshot.get("indexes")
        and not snapshot.get("routines")
    )
    if no_objects:
        return "pending"
    return "applied" if _shape_complete(snapshot) else "partial"


def evaluate_release_snapshot(snapshot: dict[str, Any], *, phase: str) -> dict[str, Any]:
    if phase not in {"preflight", "postflight"}:
        raise ValueError("phase must be preflight or postflight")
    state = _migration_state(snapshot)
    checks = [
        _check("postgres_major", snapshot.get("server_major") == 16, f"major={snapshot.get('server_major')}"),
        _check("database_identity", snapshot.get("database_matches") is True, "connected database matches target"),
        _check("current_schema", snapshot.get("current_schema") == "public", f"schema={snapshot.get('current_schema')}"),
        _check("source_authority_prerequisite", snapshot.get("prerequisite_passed") is True, "018 contract is present"),
        _check("migration_inventory", int(snapshot.get("migration_count") or 0) == 1, "019 checksummed"),
    ]
    if phase == "preflight":
        checks.extend(
            [
                _check("git_commit", snapshot.get("commit_valid") is True, "valid commit required"),
                _check("worktree_clean", snapshot.get("worktree_clean") is True, "clean worktree required"),
                _check("migration_pending", state == "pending", f"state={state}"),
            ]
        )
    else:
        checks.extend(
            [
                _check("global_source_authority_schema", state == "applied", f"state={state}"),
                _check(
                    "safe_asset_baseline",
                    int(snapshot.get("unsafe_baseline_asset_count") or 0) == 0,
                    f"unsafe={int(snapshot.get('unsafe_baseline_asset_count') or 0)}",
                ),
                _check(
                    "complete_baseline_events",
                    int(snapshot.get("missing_baseline_event_count") or 0) == 0,
                    f"missing={int(snapshot.get('missing_baseline_event_count') or 0)}",
                ),
                _check(
                    "release_created_only_baselines",
                    int(snapshot.get("invalid_release_event_count") or 0) == 0,
                    f"invalid={int(snapshot.get('invalid_release_event_count') or 0)}",
                ),
            ]
        )
    return {
        "status": "passed" if all(item["status"] == "passed" for item in checks) else "failed",
        "phase": phase,
        "migration_state": state,
        "asset_count": int(snapshot.get("asset_count") or 0),
        "checks": checks,
    }


def _extract_routine_source_contract(migration_sql: bytes) -> dict[str, str]:
    text = migration_sql.decode("utf-8")
    pattern = re.compile(
        r"CREATE\s+OR\s+REPLACE\s+FUNCTION\s+([a-zA-Z0-9_]+)\s*\(\s*\)"
        r"\s*RETURNS\s+TRIGGER\s+AS\s+\$\$(.*?)\$\$\s+LANGUAGE\s+plpgsql\s*;",
        flags=re.IGNORECASE | re.DOTALL,
    )
    return {
        name: source_authority_release._canonical_plpgsql_source(source)
        for name, source in pattern.findall(text)
        if name in _ROUTINE_CONTRACT
    }


def _constraint_semantically_valid(row: dict[str, Any]) -> bool:
    if row.get("convalidated") is not True or str(row.get("source_schema") or "") != "public":
        return False
    table = str(row.get("table_name") or "")
    kind = str(row.get("constraint_type") or "")
    columns = tuple(str(value) for value in row.get("columns") or ())
    if kind in {"p", "u"}:
        return (table, kind, columns) in _CONSTRAINT_CONTRACT
    if kind == "f":
        expected = _FOREIGN_KEY_CONTRACT.get((table, columns))
        return bool(
            expected
            and str(row.get("target_schema") or "") == "public"
            and str(row.get("target_table") or "") == expected[0]
            and tuple(str(value) for value in row.get("target_columns") or ()) == expected[1]
            and str(row.get("confdeltype") or "") == "r"
        )
    expected_definition = _CHECK_DEFINITION_CONTRACT.get((table, columns))
    return bool(kind == "c" and expected_definition and _canonical_sql(row.get("definition")) == _canonical_sql(expected_definition))


def _default_connect(database_url: str):
    return psycopg.connect(database_url, row_factory=dict_row)


def _default_prerequisite(root_dir: Path, database_url: str, **kwargs: Any) -> dict[str, Any]:
    return source_authority_release.run_postflight(root_dir, database_url, **kwargs)


def _inspect_database(
    root_dir: Path,
    database_url: str,
    *,
    phase: str,
    connect_factory: ConnectFactory | None,
    migration_loader: MigrationLoader | None,
    prerequisite_runner: PrerequisiteRunner,
    git_inspector: Callable[[Path], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    identity = database_identity(database_url)
    validate_hxy_boundary(root_dir, identity)
    inventory = migration_inventory(root_dir, migration_loader=migration_loader)
    loader = migration_loader or git_head_migration_loader
    routine_contract = _extract_routine_source_contract(
        loader(root_dir, GLOBAL_SOURCE_AUTHORITY_MIGRATIONS[0])
    )
    prerequisite = prerequisite_runner(
        root_dir,
        database_url,
        migration_loader=migration_loader,
    )
    with (connect_factory or _default_connect)(database_url) as connection:
        connection.read_only = True
        server = connection.execute(
            """
            /* hxy_global_source_authority_release:server */
            SELECT current_setting('server_version_num') AS server_version_num,
                   current_database() AS database,
                   current_schema() AS current_schema
            """
        ).fetchone()
        authority_columns = connection.execute(
            """
            /* hxy_global_source_authority_release:asset_columns */
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'hxy_knowledge_assets'
              AND column_name = ANY(%s::text[])
            ORDER BY ordinal_position
            """,
            (list(_AUTHORITY_COLUMN_CONTRACT),),
        ).fetchall()
        event_table = connection.execute(
            """
            /* hxy_global_source_authority_release:event_table */
            SELECT to_regclass('public.hxy_knowledge_asset_authority_events') IS NOT NULL AS present
            """
        ).fetchone()
        event_table_present = bool((event_table or {}).get("present"))
        event_columns = connection.execute(
            """
            /* hxy_global_source_authority_release:event_columns */
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'hxy_knowledge_asset_authority_events'
            ORDER BY ordinal_position
            """
        ).fetchall()
        constraint_rows = connection.execute(
            """
            /* hxy_global_source_authority_release:constraints */
            SELECT namespace_row.nspname AS source_schema,
                   relation.relname AS table_name,
                   constraint_row.contype AS constraint_type,
                   constraint_row.convalidated,
                   pg_get_constraintdef(constraint_row.oid, true) AS definition,
                   ARRAY(
                     SELECT attribute.attname
                     FROM unnest(constraint_row.conkey) WITH ORDINALITY AS key(attnum, position)
                     JOIN pg_attribute AS attribute
                       ON attribute.attrelid = constraint_row.conrelid
                      AND attribute.attnum = key.attnum
                     ORDER BY key.position
                   ) AS columns,
                   target_namespace.nspname AS target_schema,
                   target_relation.relname AS target_table,
                   ARRAY(
                     SELECT attribute.attname
                     FROM unnest(constraint_row.confkey) WITH ORDINALITY AS key(attnum, position)
                     JOIN pg_attribute AS attribute
                       ON attribute.attrelid = constraint_row.confrelid
                      AND attribute.attnum = key.attnum
                     ORDER BY key.position
                   ) AS target_columns,
                   constraint_row.confdeltype
            FROM pg_constraint AS constraint_row
            JOIN pg_class AS relation ON relation.oid = constraint_row.conrelid
            JOIN pg_namespace AS namespace_row ON namespace_row.oid = relation.relnamespace
            LEFT JOIN pg_class AS target_relation ON target_relation.oid = constraint_row.confrelid
            LEFT JOIN pg_namespace AS target_namespace ON target_namespace.oid = target_relation.relnamespace
            WHERE namespace_row.nspname = 'public'
              AND relation.relname = ANY(%s::text[])
              AND constraint_row.contype IN ('c', 'f', 'p', 'u')
            """,
            (list(TARGET_RELATIONS),),
        ).fetchall()
        constraints = [
            {**row, "semantic_valid": _constraint_semantically_valid(row)}
            for row in constraint_rows
        ]
        trigger_rows = connection.execute(
            """
            /* hxy_global_source_authority_release:triggers */
            SELECT relation.relname AS table_name,
                   trigger_row.tgname AS trigger_name,
                   trigger_row.tgenabled,
                   pg_get_expr(trigger_row.tgqual, trigger_row.tgrelid) AS tgqual,
                   pg_get_triggerdef(trigger_row.oid, true) AS definition,
                   routine_namespace.nspname AS function_schema,
                   routine.proname AS function_name,
                   routine.prosrc AS function_source,
                   pg_get_functiondef(routine.oid) AS function_definition
            FROM pg_trigger AS trigger_row
            JOIN pg_class AS relation ON relation.oid = trigger_row.tgrelid
            JOIN pg_namespace AS namespace_row ON namespace_row.oid = relation.relnamespace
            JOIN pg_proc AS routine ON routine.oid = trigger_row.tgfoid
            JOIN pg_namespace AS routine_namespace ON routine_namespace.oid = routine.pronamespace
            WHERE NOT trigger_row.tgisinternal
              AND namespace_row.nspname = 'public'
              AND trigger_row.tgname LIKE 'trg_hxy_knowledge%%authority%%'
            ORDER BY trigger_row.tgname
            """
        ).fetchall()
        triggers: list[dict[str, Any]] = []
        for row in trigger_rows:
            parsed = source_authority_release._parse_trigger_definition(str(row.get("definition") or ""))
            if parsed is None:
                continue
            timing, events, level, update_columns = parsed
            source_valid, definition_valid = source_authority_release._routine_semantics(
                str(row.get("function_name") or ""),
                row.get("function_source"),
                row.get("function_definition"),
                expected_source=routine_contract.get(str(row.get("function_name") or "")),
            )
            triggers.append(
                {
                    "table_name": row.get("table_name"),
                    "trigger_name": row.get("trigger_name"),
                    "timing": timing,
                    "events": events,
                    "update_columns": update_columns,
                    "level": level,
                    "function_name": row.get("function_name"),
                    "enabled": row.get("tgenabled"),
                    "predicate": row.get("tgqual"),
                    "function_schema": row.get("function_schema"),
                    "function_source_valid": source_valid,
                    "function_definition_valid": definition_valid,
                }
            )
        index_rows = connection.execute(
            """
            /* hxy_global_source_authority_release:indexes */
            SELECT table_relation.relname AS table_name,
                   index_relation.relname AS index_name,
                   pg_get_indexdef(index_relation.oid) AS definition,
                   index_row.indisunique AS is_unique,
                   index_row.indisvalid AS is_valid,
                   pg_get_expr(index_row.indpred, index_row.indrelid) AS predicate
            FROM pg_index AS index_row
            JOIN pg_class AS table_relation ON table_relation.oid = index_row.indrelid
            JOIN pg_class AS index_relation ON index_relation.oid = index_row.indexrelid
            JOIN pg_namespace AS namespace_row ON namespace_row.oid = table_relation.relnamespace
            WHERE namespace_row.nspname = 'public'
              AND index_relation.relname = 'idx_hxy_knowledge_asset_authority_events_asset'
            """
        ).fetchall()
        indexes = [
            {
                "table_name": row.get("table_name"),
                "index_name": row.get("index_name"),
                "columns": source_authority_release._parse_index_columns(str(row.get("definition") or "")) or (),
                "is_unique": bool(row.get("is_unique")),
                "is_valid": row.get("is_valid") is True,
                "predicate": row.get("predicate"),
            }
            for row in index_rows
        ]
        routine_rows = connection.execute(
            """
            /* hxy_global_source_authority_release:routines */
            SELECT namespace_row.nspname AS function_schema,
                   routine.proname AS function_name,
                   routine.prosrc AS function_source,
                   pg_get_functiondef(routine.oid) AS function_definition
            FROM pg_proc AS routine
            JOIN pg_namespace AS namespace_row ON namespace_row.oid = routine.pronamespace
            WHERE namespace_row.nspname = 'public'
              AND routine.proname = ANY(%s::text[])
            """,
            (list(_ROUTINE_CONTRACT),),
        ).fetchall()
        routines: list[dict[str, Any]] = []
        for row in routine_rows:
            source_valid, definition_valid = source_authority_release._routine_semantics(
                str(row.get("function_name") or ""),
                row.get("function_source"),
                row.get("function_definition"),
                expected_source=routine_contract.get(str(row.get("function_name") or "")),
            )
            routines.append(
                {
                    "function_schema": row.get("function_schema"),
                    "function_name": row.get("function_name"),
                    "source_valid": source_valid,
                    "definition_valid": definition_valid,
                }
            )

        counts = {
            "asset_count": 0,
            "unsafe_baseline_asset_count": 0,
            "missing_baseline_event_count": 0,
            "invalid_release_event_count": 0,
        }
        if phase == "postflight" and event_table_present:
            counts = connection.execute(
                """
                /* hxy_global_source_authority_release:data_baseline */
                SELECT
                  (SELECT count(*) FROM hxy_knowledge_assets) AS asset_count,
                  (SELECT count(*) FROM hxy_knowledge_assets
                   WHERE source_origin <> 'unknown'
                      OR source_authority <> 'external_reference'
                      OR authority_version <> 1
                      OR authority_organization_id IS NOT NULL) AS unsafe_baseline_asset_count,
                  (SELECT count(*) FROM hxy_knowledge_assets AS asset
                   WHERE NOT EXISTS (
                     SELECT 1
                     FROM hxy_knowledge_asset_authority_events AS event
                     WHERE event.asset_id = asset.asset_id
                       AND event.event_type = 'baseline'
                       AND event.organization_id IS NULL
                       AND event.actor_assignment_id IS NULL
                       AND event.previous_origin IS NULL
                       AND event.previous_authority IS NULL
                       AND event.previous_version IS NULL
                       AND event.new_origin = 'unknown'
                       AND event.new_authority = 'external_reference'
                       AND event.version_no = 1
                   )) AS missing_baseline_event_count,
                  (SELECT count(*) FROM hxy_knowledge_asset_authority_events AS event
                   WHERE event.event_type <> 'baseline'
                      OR event.organization_id IS NOT NULL
                      OR event.actor_assignment_id IS NOT NULL
                      OR event.previous_origin IS NOT NULL
                      OR event.previous_authority IS NOT NULL
                      OR event.previous_version IS NOT NULL
                      OR event.new_origin <> 'unknown'
                      OR event.new_authority <> 'external_reference'
                      OR event.version_no <> 1) AS invalid_release_event_count
                """
            ).fetchone()

    git_state = {"commit": "unknown", "commit_valid": False, "worktree_clean": False}
    if phase == "preflight":
        git_state = (git_inspector or role_journeys_release.inspect_git_worktree)(root_dir)
    snapshot = {
        "server_major": int(str(server.get("server_version_num") or "0")) // 10000,
        "database_matches": str(server.get("database") or "") == identity["database"],
        "current_schema": str(server.get("current_schema") or ""),
        "prerequisite_passed": prerequisite.get("status") == "passed",
        "migration_count": len(inventory),
        "authority_columns": authority_columns,
        "event_table_present": event_table_present,
        "event_columns": event_columns,
        "constraints": constraints,
        "triggers": triggers,
        "indexes": indexes,
        "routines": routines,
        "commit_valid": git_state.get("commit_valid") is True,
        "worktree_clean": git_state.get("worktree_clean") is True,
        **{key: int(value or 0) for key, value in counts.items()},
    }
    result = evaluate_release_snapshot(snapshot, phase=phase)
    result["database"] = identity
    return result


def run_preflight(
    root_dir: Path,
    database_url: str,
    *,
    connect_factory: ConnectFactory | None = None,
    migration_loader: MigrationLoader | None = None,
    prerequisite_runner: PrerequisiteRunner = _default_prerequisite,
    git_inspector: Callable[[Path], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return _inspect_database(
        root_dir,
        database_url,
        phase="preflight",
        connect_factory=connect_factory,
        migration_loader=migration_loader,
        prerequisite_runner=prerequisite_runner,
        git_inspector=git_inspector,
    )


def run_postflight(
    root_dir: Path,
    database_url: str,
    *,
    connect_factory: ConnectFactory | None = None,
    migration_loader: MigrationLoader | None = None,
    prerequisite_runner: PrerequisiteRunner = _default_prerequisite,
) -> dict[str, Any]:
    return _inspect_database(
        root_dir,
        database_url,
        phase="postflight",
        connect_factory=connect_factory,
        migration_loader=migration_loader,
        prerequisite_runner=prerequisite_runner,
    )


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
        inspector = lambda root, dsn: run_preflight(root, dsn, migration_loader=migration_loader)
    result = create_release_backup(
        GLOBAL_SOURCE_AUTHORITY_RELEASE,
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
    max_age: timedelta = timedelta(hours=2),
    git_commit: str | None = None,
    trusted_root: Path = _DEFAULT_TRUSTED_ROOT,
    migration_loader: MigrationLoader | None = None,
) -> dict[str, Any]:
    return validate_release_backup_manifest(
        GLOBAL_SOURCE_AUTHORITY_RELEASE,
        root_dir,
        database_url,
        manifest_path,
        now=now,
        max_age=max_age,
        git_commit=git_commit,
        trusted_root=trusted_root,
        migration_loader=migration_loader,
    )


def apply_global_source_authority_migration(
    root_dir: Path,
    database_url: str,
    *,
    manifest_path: Path,
    confirmation: str,
    runner: CommandRunner | None = None,
    now: datetime | None = None,
    git_commit: str | None = None,
    postflight_runner: InspectionRunner = run_postflight,
    git_inspector: Callable[[Path], dict[str, Any]] | None = None,
    trusted_root: Path = _DEFAULT_TRUSTED_ROOT,
    migration_loader: MigrationLoader | None = None,
) -> dict[str, Any]:
    if confirmation != APPLY_CONFIRMATION:
        raise ReleaseAuthorizationError("exact migration confirmation is required")
    git_state = (git_inspector or role_journeys_release.inspect_git_worktree)(root_dir)
    if not git_state.get("commit_valid") or not git_state.get("worktree_clean"):
        raise ReleaseAuthorizationError("apply requires a real Git commit and clean worktree")
    inspector = postflight_runner
    if postflight_runner is run_postflight:
        inspector = lambda root, dsn: run_postflight(root, dsn, migration_loader=migration_loader)
    return apply_release_migrations(
        GLOBAL_SOURCE_AUTHORITY_RELEASE,
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


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Guarded HXY global source-authority release")
    parser.add_argument("--root-dir", type=Path, default=Path.cwd())
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("preflight")
    backup = commands.add_parser("backup")
    backup.add_argument("--output-root", type=Path)
    apply = commands.add_parser("apply")
    apply.add_argument("--backup-manifest", type=Path)
    apply.add_argument("--confirm", default="")
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
            result = run_preflight(args.root_dir, database_url, migration_loader=git_head_migration_loader)
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
            result = apply_global_source_authority_migration(
                args.root_dir,
                database_url,
                manifest_path=args.backup_manifest,
                confirmation=args.confirm,
                migration_loader=git_head_migration_loader,
            )
        else:
            result = run_postflight(args.root_dir, database_url, migration_loader=git_head_migration_loader)
    except ReleasePostflightError as exc:
        result = {
            "status": "failed",
            "phase": args.command,
            "error_type": "ReleaseExecutionError",
            "error_code": "postflight_failed_after_apply",
            "error": str(exc),
            "applied": True,
            "postflight": exc.postflight,
        }
    except ReleaseInstanceError as exc:
        result = {
            "status": "failed",
            "phase": args.command,
            "error_type": "ReleaseExecutionError" if exc.applied else type(exc).__name__,
            "error": str(exc),
            "applied": exc.applied,
        }
        if exc.error_code:
            result["error_code"] = exc.error_code
    except (ReleaseAppliedError, ReleaseCleanupError) as exc:
        result = {
            "status": "failed",
            "phase": args.command,
            "error_type": "ReleaseExecutionError" if exc.applied else type(exc).__name__,
            "error_code": exc.error_code,
            "error": str(exc),
            "applied": exc.applied,
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
    print(
        render_result(
            result,
            sensitive_values=source_authority_release._database_sensitive_values(database_url),
        )
    )
    return 0 if result["status"] == "passed" else 2
