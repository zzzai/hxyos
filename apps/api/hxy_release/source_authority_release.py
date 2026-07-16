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

from . import activation_release, role_journeys_release
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


SOURCE_AUTHORITY_MIGRATIONS = ("018_hxy_source_authority.sql",)
APPLY_CONFIRMATION = "APPLY-HXY-018"
BACKUP_VERSION = "hxy-source-authority-backup.v1"
_DEFAULT_TRUSTED_ROOT = Path("/root/hxy")
_DEFAULT_BACKUP_ROOT = _DEFAULT_TRUSTED_ROOT / "data" / "backups" / "source-authority"

SOURCE_AUTHORITY_RELEASE = MigrationReleaseSpec(
    release_id="hxy-source-authority-018",
    manifest_version=BACKUP_VERSION,
    migrations=SOURCE_AUTHORITY_MIGRATIONS,
    confirmation=APPLY_CONFIRMATION,
    advisory_lock="hxy-source-authority-018",
    dump_filename="hxy-before-source-authority.dump",
)

ConnectFactory = Callable[[str], Any]
PrerequisiteRunner = Callable[..., dict[str, Any]]

_AUTHORITY_COLUMN_CONTRACT = {
    "source_origin": ("text", "NO", "'unknown'::text"),
    "source_authority": ("text", "NO", "'external_reference'::text"),
    "authority_version": ("integer", "NO", "1"),
}

_EVENT_COLUMN_CONTRACT = (
    ("event_id", "uuid", "NO", "gen_random_uuid()"),
    ("material_id", "uuid", "NO", None),
    ("owner_assignment_id", "uuid", "NO", None),
    ("actor_assignment_id", "uuid", "NO", None),
    ("previous_origin", "text", "YES", None),
    ("new_origin", "text", "NO", None),
    ("previous_authority", "text", "YES", None),
    ("new_authority", "text", "NO", None),
    ("version_no", "integer", "NO", None),
    ("reason", "text", "NO", None),
    ("created_at", "timestamp with time zone", "NO", "now()"),
)

_CONSTRAINT_CONTRACT = {
    ("hxy_product_materials", "c", ("source_origin",)),
    ("hxy_product_materials", "c", ("source_authority",)),
    ("hxy_product_materials", "c", ("authority_version",)),
    ("hxy_product_materials", "c", ("source_origin", "source_authority")),
    ("hxy_material_authority_events", "p", ("event_id",)),
    ("hxy_material_authority_events", "u", ("material_id", "version_no")),
    ("hxy_material_authority_events", "f", ("material_id",)),
    ("hxy_material_authority_events", "f", ("owner_assignment_id",)),
    ("hxy_material_authority_events", "f", ("actor_assignment_id",)),
    ("hxy_material_authority_events", "c", ("previous_origin",)),
    ("hxy_material_authority_events", "c", ("new_origin",)),
    ("hxy_material_authority_events", "c", ("previous_authority",)),
    ("hxy_material_authority_events", "c", ("new_authority",)),
    ("hxy_material_authority_events", "c", ("version_no",)),
    ("hxy_material_authority_events", "c", ("reason",)),
}

_TRIGGER_CONTRACT = {
    (
        "hxy_material_authority_events",
        "trg_hxy_material_authority_events_validate",
        "BEFORE",
        ("INSERT",),
        "ROW",
        "hxy_validate_material_authority_event",
    ),
    (
        "hxy_product_materials",
        "trg_hxy_product_materials_initial_authority",
        "AFTER",
        ("INSERT",),
        "ROW",
        "hxy_record_initial_material_authority",
    ),
    (
        "hxy_product_materials",
        "trg_hxy_product_materials_authority_version_guard",
        "BEFORE",
        ("UPDATE",),
        "ROW",
        "hxy_enforce_material_authority_version",
    ),
    (
        "hxy_material_authority_events",
        "trg_hxy_material_authority_events_append_only",
        "BEFORE",
        ("DELETE", "UPDATE"),
        "ROW",
        "hxy_reject_material_authority_event_mutation",
    ),
    (
        "hxy_material_authority_events",
        "trg_hxy_material_authority_events_no_truncate",
        "BEFORE",
        ("TRUNCATE",),
        "STATEMENT",
        "hxy_reject_material_authority_event_mutation",
    ),
}

_ROUTINE_CONTRACT = {
    "hxy_validate_material_authority_event",
    "hxy_record_initial_material_authority",
    "hxy_enforce_material_authority_version",
    "hxy_reject_material_authority_event_mutation",
}

_TRIGGER_UPDATE_COLUMNS_CONTRACT = {
    "trg_hxy_product_materials_authority_version_guard": (
        "authority_version",
        "source_authority",
        "source_origin",
    ),
}

_CHECK_DEFINITION_CONTRACT = {
    ("hxy_product_materials", ("source_origin",)): (
        "CHECK (source_origin = ANY (ARRAY['internal'::text, 'external'::text, 'unknown'::text]))"
    ),
    ("hxy_product_materials", ("source_authority",)): (
        "CHECK (source_authority = ANY (ARRAY['official_internal'::text, "
        "'internal_material'::text, 'external_reference'::text]))"
    ),
    ("hxy_product_materials", ("authority_version",)): "CHECK (authority_version > 0)",
    ("hxy_product_materials", ("source_origin", "source_authority")): (
        "CHECK (source_origin = 'internal'::text OR source_authority = 'external_reference'::text)"
    ),
    ("hxy_material_authority_events", ("previous_origin",)): (
        "CHECK (previous_origin IS NULL OR (previous_origin = ANY "
        "(ARRAY['internal'::text, 'external'::text, 'unknown'::text])))"
    ),
    ("hxy_material_authority_events", ("new_origin",)): (
        "CHECK (new_origin = ANY (ARRAY['internal'::text, 'external'::text, 'unknown'::text]))"
    ),
    ("hxy_material_authority_events", ("previous_authority",)): (
        "CHECK (previous_authority IS NULL OR (previous_authority = ANY "
        "(ARRAY['official_internal'::text, 'internal_material'::text, "
        "'external_reference'::text])))"
    ),
    ("hxy_material_authority_events", ("new_authority",)): (
        "CHECK (new_authority = ANY (ARRAY['official_internal'::text, "
        "'internal_material'::text, 'external_reference'::text]))"
    ),
    ("hxy_material_authority_events", ("version_no",)): "CHECK (version_no > 0)",
    ("hxy_material_authority_events", ("reason",)): (
        "CHECK (char_length(btrim(reason)) >= 4 AND char_length(btrim(reason)) <= 500)"
    ),
}


def migration_inventory(
    root_dir: Path,
    *,
    trusted_root: Path = _DEFAULT_TRUSTED_ROOT,
    migration_loader: MigrationLoader | None = None,
) -> list[dict[str, str]]:
    return guarded_migration_inventory(
        SOURCE_AUTHORITY_RELEASE,
        root_dir,
        trusted_root=trusted_root,
        migration_loader=migration_loader,
    )


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


def _canonical_sql(value: Any) -> str:
    return re.sub(r"[\s\"()]", "", str(value or "").lower())


def _normalized_authority_columns(rows: Any) -> dict[str, tuple[str, str, str | None]]:
    return {
        str(row.get("column_name") or ""): (
            str(row.get("data_type") or ""),
            str(row.get("is_nullable") or ""),
            _canonical_default(row.get("column_default")),
        )
        for row in rows or ()
        if isinstance(row, dict)
    }


def _normalized_event_columns(rows: Any) -> tuple[tuple[str, str, str, str | None], ...]:
    normalized: list[tuple[str, str, str, str | None]] = []
    for row in rows or ():
        if isinstance(row, dict):
            normalized.append(
                (
                    str(row.get("column_name") or ""),
                    str(row.get("data_type") or ""),
                    str(row.get("is_nullable") or ""),
                    _canonical_default(row.get("column_default")),
                )
            )
        elif isinstance(row, (list, tuple)) and len(row) == 4:
            normalized.append(
                (str(row[0]), str(row[1]), str(row[2]), _canonical_default(row[3]))
            )
    return tuple(normalized)


def _normalized_constraints(rows: Any) -> set[tuple[str, str, tuple[str, ...]]]:
    normalized: set[tuple[str, str, tuple[str, ...]]] = set()
    for row in rows or ():
        if isinstance(row, dict):
            if row.get("validated", row.get("convalidated", True)) is not True:
                continue
            if row.get("semantic_valid", True) is not True:
                continue
            normalized.add(
                (
                    str(row.get("table_name") or ""),
                    str(row.get("constraint_type") or ""),
                    tuple(str(item) for item in row.get("columns") or ()),
                )
            )
        elif isinstance(row, (list, tuple)) and len(row) >= 3:
            normalized.add((str(row[0]), str(row[1]), tuple(str(item) for item in row[2])))
    return normalized


def _normalized_triggers(rows: Any) -> set[tuple[str, str, str, tuple[str, ...], str, str]]:
    normalized: set[tuple[str, str, str, tuple[str, ...], str, str]] = set()
    for row in rows or ():
        if isinstance(row, dict):
            if str(row.get("enabled", row.get("tgenabled", "O"))).upper() not in {
                "O",
                "A",
            }:
                continue
            if row.get("predicate", row.get("tgqual")) not in (None, ""):
                continue
            if str(row.get("function_schema", "public")) != "public":
                continue
            if row.get("function_source_valid", True) is not True:
                continue
            if row.get("function_definition_valid", True) is not True:
                continue
            trigger_name = str(row.get("trigger_name") or "")
            update_columns = tuple(
                sorted(str(column).lower() for column in row.get("update_columns") or ())
            )
            if update_columns != _TRIGGER_UPDATE_COLUMNS_CONTRACT.get(trigger_name, ()):
                continue
            item = (
                str(row.get("table_name") or ""),
                trigger_name,
                str(row.get("timing") or "").upper(),
                tuple(sorted(str(event).upper() for event in row.get("events") or ())),
                str(row.get("level") or "").upper(),
                str(row.get("function_name") or ""),
            )
        elif isinstance(row, (list, tuple)) and len(row) == 6:
            item = (
                str(row[0]),
                str(row[1]),
                str(row[2]).upper(),
                tuple(sorted(str(event).upper() for event in row[3])),
                str(row[4]).upper(),
                str(row[5]),
            )
        else:
            continue
        normalized.add(item)
    return normalized


def _normalized_routines(rows: Any) -> set[str]:
    normalized: set[str] = set()
    for row in rows or ():
        if isinstance(row, dict):
            if str(row.get("function_schema") or "") != "public":
                continue
            if row.get("source_valid") is not True:
                continue
            if row.get("definition_valid") is not True:
                continue
            normalized.add(str(row.get("function_name") or ""))
        else:
            normalized.add(str(row))
    return normalized


def _normalized_indexes(rows: Any) -> set[tuple[str, str, tuple[str, ...], bool]]:
    normalized: set[tuple[str, str, tuple[str, ...], bool]] = set()
    for item in rows or ():
        if isinstance(item, dict):
            if item.get("is_valid", item.get("indisvalid", True)) is not True:
                continue
            if item.get("predicate") not in (None, ""):
                continue
            normalized.add(
                (
                    str(item.get("table_name") or ""),
                    str(item.get("index_name") or ""),
                    tuple(str(column) for column in item.get("columns") or ()),
                    bool(item.get("is_unique", item.get("indisunique"))),
                )
            )
        elif isinstance(item, (list, tuple)) and len(item) >= 4:
            normalized.add(
                (str(item[0]), str(item[1]), tuple(str(column) for column in item[2]), bool(item[3]))
            )
    return normalized


def _shape_complete(snapshot: dict[str, Any]) -> bool:
    columns = _normalized_authority_columns(snapshot.get("authority_columns"))
    event_columns = _normalized_event_columns(snapshot.get("event_columns"))
    constraints = _normalized_constraints(snapshot.get("constraints"))
    triggers = _normalized_triggers(snapshot.get("triggers"))
    routines = _normalized_routines(snapshot.get("routines"))
    indexes = _normalized_indexes(snapshot.get("indexes"))
    return (
        columns == {
            name: (data_type, nullable, _canonical_default(default))
            for name, (data_type, nullable, default) in _AUTHORITY_COLUMN_CONTRACT.items()
        }
        and snapshot.get("authority_event_table_present") is True
        and event_columns == tuple(
            (name, data_type, nullable, _canonical_default(default))
            for name, data_type, nullable, default in _EVENT_COLUMN_CONTRACT
        )
        and _CONSTRAINT_CONTRACT.issubset(constraints)
        and _TRIGGER_CONTRACT == triggers
        and _ROUTINE_CONTRACT == routines
        and (
            "hxy_material_authority_events",
            "idx_hxy_material_authority_events_material",
            ("material_id", "version_no desc"),
            False,
        )
        in indexes
    )


def _migration_state(snapshot: dict[str, Any]) -> str:
    no_objects = (
        not snapshot.get("authority_columns")
        and snapshot.get("authority_event_table_present") is False
        and not snapshot.get("event_columns")
        and not snapshot.get("constraints")
        and not snapshot.get("triggers")
        and not snapshot.get("indexes")
        and not snapshot.get("routines")
    )
    if no_objects:
        return "pending"
    if _shape_complete(snapshot):
        return "applied"
    return "partial"


def evaluate_release_snapshot(snapshot: dict[str, Any], *, phase: str) -> dict[str, Any]:
    if phase not in {"preflight", "postflight"}:
        raise ValueError("phase must be preflight or postflight")
    state = _migration_state(snapshot)
    common_checks = [
        _check("postgres_major", snapshot.get("server_major") == 16, f"major={snapshot.get('server_major')}"),
        _check("database_identity", snapshot.get("database_matches") is True, "connected database matches target"),
        _check("current_schema", snapshot.get("current_schema") == "public", f"schema={snapshot.get('current_schema')}"),
        _check("activation_prerequisite", snapshot.get("prerequisite_passed") is True, "009-014 contract is present"),
        _check("migration_inventory", snapshot.get("migration_count", 1) == 1, "018 checksummed"),
    ]
    if phase == "preflight":
        checks = common_checks + [
            _check(
                "git_commit",
                snapshot.get("commit_valid") is True,
                "valid commit" if snapshot.get("commit_valid") is True else "invalid commit",
            ),
            _check(
                "worktree_clean",
                snapshot.get("worktree_clean") is True,
                "clean" if snapshot.get("worktree_clean") is True else "dirty",
            ),
            _check("migration_pending", state == "pending", f"state={state}"),
        ]
    else:
        material_count = int(snapshot.get("material_count") or 0)
        non_default = int(snapshot.get("non_default_material_count") or 0)
        missing_events = int(snapshot.get("missing_current_event_count") or 0)
        invalid_events = int(snapshot.get("invalid_event_count") or 0)
        checks = common_checks + [
            _check("source_authority_schema", state == "applied", f"state={state}"),
            _check("authority_triggers", _TRIGGER_CONTRACT == _normalized_triggers(snapshot.get("triggers")), "all five guarded triggers are present"),
            _check("migration_default_baseline", non_default == 0, f"non_default={non_default}; materials={material_count}"),
            _check("authority_event_baseline", missing_events == 0 and invalid_events == 0, f"missing={missing_events}; invalid={invalid_events}"),
        ]
    status = "passed" if all(item["status"] == "passed" for item in checks) else "failed"
    return {
        "status": status,
        "phase": phase,
        "migration_state": state,
        "material_count": int(snapshot.get("material_count") or 0),
        "checks": checks,
    }


def _parse_trigger_definition(
    definition: str,
) -> tuple[str, tuple[str, ...], str, tuple[str, ...]] | None:
    normalized = " ".join(definition.upper().split())
    timing = re.search(r"\b(BEFORE|AFTER|INSTEAD OF)\s+(.+?)\s+ON\s+", normalized)
    level = re.search(r"\bFOR EACH (ROW|STATEMENT)\b", normalized)
    if timing is None or level is None:
        return None
    parsed_events: list[str] = []
    update_columns: tuple[str, ...] = ()
    for event in re.split(r"\s+OR\s+", timing.group(2)):
        update_match = re.fullmatch(r"UPDATE(?:\s+OF\s+(.+))?", event)
        if update_match is not None:
            parsed_events.append("UPDATE")
            if update_match.group(1):
                update_columns = tuple(
                    sorted(
                        column.strip().replace('"', "").lower()
                        for column in update_match.group(1).split(",")
                    )
                )
            continue
        parsed_events.append(event)
    events = tuple(sorted(parsed_events))
    if not events or any(event not in {"INSERT", "UPDATE", "DELETE", "TRUNCATE"} for event in events):
        return None
    return timing.group(1), events, level.group(1), update_columns


def _parse_index_columns(definition: str) -> tuple[str, ...] | None:
    match = re.search(r"\bUSING\s+btree\s*\(([^)]*)\)", definition, re.IGNORECASE)
    if match is None:
        return None
    return tuple(" ".join(item.replace('"', "").lower().split()) for item in match.group(1).split(","))


def _canonical_plpgsql_source(source: Any) -> str:
    without_block_comments = re.sub(r"/\*.*?\*/", " ", str(source or ""), flags=re.DOTALL)
    without_comments = re.sub(r"--[^\r\n]*", " ", without_block_comments)
    return " ".join(without_comments.lower().split())


def _extract_routine_source_contract(migration_sql: bytes) -> dict[str, str]:
    text = migration_sql.decode("utf-8")
    pattern = re.compile(
        r"CREATE\s+OR\s+REPLACE\s+FUNCTION\s+([a-zA-Z0-9_]+)\s*\(\s*\)"
        r"\s*RETURNS\s+TRIGGER\s+AS\s+\$\$(.*?)\$\$\s+LANGUAGE\s+plpgsql\s*;",
        flags=re.IGNORECASE | re.DOTALL,
    )
    return {
        name: _canonical_plpgsql_source(source)
        for name, source in pattern.findall(text)
        if name in _ROUTINE_CONTRACT
    }


def _routine_semantics(
    name: str,
    source: Any,
    definition: Any,
    *,
    expected_source: str | None = None,
) -> tuple[bool, bool]:
    normalized_source = _canonical_plpgsql_source(source)
    normalized_definition = " ".join(str(definition or "").lower().split())
    source_valid = bool(expected_source) and normalized_source == expected_source
    definition_valid = (
        source_valid
        and normalized_source in normalized_definition
        and "language plpgsql" in normalized_definition
    )
    return source_valid, definition_valid


def _constraint_semantically_valid(row: dict[str, Any]) -> bool:
    if row.get("convalidated") is not True:
        return False
    if str(row.get("source_schema") or "") != "public":
        return False
    table = str(row.get("table_name") or row.get("source_table") or "")
    kind = str(row.get("constraint_type") or "")
    columns = tuple(str(item) for item in row.get("columns") or row.get("source_columns") or ())
    definition = _canonical_sql(row.get("definition") or row.get("check_expression"))
    if kind in {"p", "u"}:
        return True
    if kind == "f":
        expected = {
            ("hxy_material_authority_events", ("material_id",)): (
                "hxy_product_materials",
                ("material_id",),
            ),
            ("hxy_material_authority_events", ("owner_assignment_id",)): (
                "hxy_role_assignments",
                ("assignment_id",),
            ),
            ("hxy_material_authority_events", ("actor_assignment_id",)): (
                "hxy_role_assignments",
                ("assignment_id",),
            ),
        }.get((table, columns))
        return bool(
            expected
            and str(row.get("target_schema") or "") == "public"
            and str(row.get("target_table") or "") == expected[0]
            and tuple(str(item) for item in row.get("target_columns") or ()) == expected[1]
            and str(row.get("confdeltype") or "") == "r"
        )
    if kind != "c":
        return False
    expected_definition = _CHECK_DEFINITION_CONTRACT.get((table, columns))
    return bool(expected_definition and definition == _canonical_sql(expected_definition))


def _default_connect(database_url: str):
    return psycopg.connect(database_url, row_factory=dict_row)


def _default_prerequisite(root_dir: Path, database_url: str, **kwargs: Any) -> dict[str, Any]:
    return activation_release.run_postflight(root_dir, database_url, **kwargs)


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
    routine_source_contract = _extract_routine_source_contract(
        loader(root_dir, SOURCE_AUTHORITY_MIGRATIONS[0])
    )
    prerequisite = prerequisite_runner(
        root_dir,
        database_url,
        migration_loader=migration_loader,
    )
    connection_factory = connect_factory or _default_connect
    with connection_factory(database_url) as connection:
        connection.read_only = True
        server = connection.execute(
            """
            /* hxy_source_authority_release:server */
            SELECT current_setting('server_version_num') AS server_version_num,
                   current_database() AS database,
                   current_schema() AS current_schema
            """
        ).fetchone()
        authority_columns = connection.execute(
            """
            /* hxy_source_authority_release:material_columns */
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'hxy_product_materials'
              AND column_name = ANY(%s::text[])
            ORDER BY ordinal_position
            """,
            (list(_AUTHORITY_COLUMN_CONTRACT),),
        ).fetchall()
        event_table_present = connection.execute(
            """
            /* hxy_source_authority_release:event_table */
            SELECT to_regclass('public.hxy_material_authority_events') IS NOT NULL AS present
            """
        ).fetchone()
        relations_present = bool((event_table_present or {}).get("present"))
        event_columns = connection.execute(
                """
                /* hxy_source_authority_release:event_columns */
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'hxy_material_authority_events'
                ORDER BY ordinal_position
                """
            ).fetchall()
        constraints = connection.execute(
                """
                /* hxy_source_authority_release:constraints */
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
                  AND (
                    relation.relname = 'hxy_material_authority_events'
                    OR constraint_row.conname LIKE 'hxy_product_materials_source%%'
                    OR constraint_row.conname = 'hxy_product_materials_authority_version_check'
                  )
                """,
                (["hxy_product_materials", "hxy_material_authority_events"],),
            ).fetchall()
        constraints = [
            {
                **row,
                "semantic_valid": _constraint_semantically_valid(row),
                "validated": row.get("convalidated") is True,
            }
            for row in constraints
        ]
        trigger_rows = connection.execute(
                """
                /* hxy_source_authority_release:triggers */
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
                  AND trigger_row.tgname LIKE 'trg_hxy_%%authority%%'
                ORDER BY trigger_row.tgname
                """
            ).fetchall()
        triggers: list[dict[str, Any]] = []
        for row in trigger_rows:
            parsed = _parse_trigger_definition(str(row.get("definition") or ""))
            if parsed is not None:
                timing, events, level, update_columns = parsed
                source_valid, definition_valid = _routine_semantics(
                    str(row.get("function_name") or ""),
                    row.get("function_source"),
                    row.get("function_definition"),
                    expected_source=routine_source_contract.get(
                        str(row.get("function_name") or "")
                    ),
                )
                triggers.append(
                    {
                        "table_name": row["table_name"],
                        "trigger_name": row["trigger_name"],
                        "timing": timing,
                        "events": events,
                        "update_columns": update_columns,
                        "level": level,
                        "function_name": row["function_name"],
                        "enabled": row.get("tgenabled"),
                        "predicate": row.get("tgqual"),
                        "function_schema": row.get("function_schema"),
                        "function_source_valid": source_valid,
                        "function_definition_valid": definition_valid,
                    }
                )
        index_rows = connection.execute(
                """
                /* hxy_source_authority_release:indexes */
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
                  AND index_relation.relname = 'idx_hxy_material_authority_events_material'
                """
            ).fetchall()
        indexes = [
                {
                    "table_name": row["table_name"],
                    "index_name": row["index_name"],
                    "columns": _parse_index_columns(str(row.get("definition") or "")) or (),
                    "is_unique": bool(row.get("is_unique")),
                    "is_valid": row.get("is_valid") is True,
                    "predicate": row.get("predicate"),
                }
                for row in index_rows
            ]
        routine_rows = connection.execute(
                """
                /* hxy_source_authority_release:routines */
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
            source_valid, definition_valid = _routine_semantics(
                str(row.get("function_name") or ""),
                row.get("function_source"),
                row.get("function_definition"),
                expected_source=routine_source_contract.get(
                    str(row.get("function_name") or "")
                ),
            )
            routines.append(
                {
                    "function_schema": row.get("function_schema"),
                    "function_name": row.get("function_name"),
                    "source_valid": source_valid,
                    "definition_valid": definition_valid,
                }
            )

        counts = {"material_count": 0, "non_default_material_count": 0, "missing_current_event_count": 0, "invalid_event_count": 0}
        if phase == "postflight" and _normalized_authority_columns(authority_columns) == {
            name: (data_type, nullable, _canonical_default(default))
            for name, (data_type, nullable, default) in _AUTHORITY_COLUMN_CONTRACT.items()
        } and relations_present:
            counts = connection.execute(
                """
                /* hxy_source_authority_release:data_baseline */
                SELECT
                  (SELECT count(*) FROM hxy_product_materials) AS material_count,
                  (SELECT count(*) FROM hxy_product_materials
                   WHERE source_origin <> 'unknown'
                      OR source_authority <> 'external_reference'
                      OR authority_version <> 1) AS non_default_material_count,
                  (SELECT count(*) FROM hxy_product_materials AS material
                   WHERE NOT EXISTS (
                     SELECT 1 FROM hxy_material_authority_events AS event
                     WHERE event.material_id = material.material_id
                       AND event.owner_assignment_id = material.assignment_id
                       AND event.actor_assignment_id = material.assignment_id
                       AND event.previous_origin IS NULL
                       AND event.previous_authority IS NULL
                       AND event.new_origin = material.source_origin
                       AND event.new_authority = material.source_authority
                       AND event.version_no = material.authority_version
                   )) AS missing_current_event_count,
                  (SELECT count(*)
                   FROM hxy_material_authority_events AS event
                   JOIN hxy_product_materials AS material ON material.material_id = event.material_id
                   WHERE event.owner_assignment_id <> material.assignment_id
                      OR event.actor_assignment_id <> material.assignment_id
                      OR event.previous_origin IS NOT NULL
                      OR event.previous_authority IS NOT NULL
                      OR event.new_origin <> material.source_origin
                      OR event.new_authority <> material.source_authority
                      OR event.version_no <> material.authority_version) AS invalid_event_count
                """
            ).fetchone()

    git_state = {
        "commit": "unknown",
        "commit_valid": False,
        "worktree_clean": False,
    }
    if phase == "preflight":
        git_state = (git_inspector or role_journeys_release.inspect_git_worktree)(
            root_dir
        )
    snapshot = {
        "server_major": int(str(server.get("server_version_num") or "0")) // 10000,
        "database_matches": str(server.get("database") or "") == identity["database"],
        "current_schema": str(server.get("current_schema") or ""),
        "prerequisite_passed": prerequisite.get("status") == "passed",
        "migration_count": len(inventory),
        "authority_columns": authority_columns,
        "authority_event_table_present": relations_present,
        "event_columns": event_columns,
        "constraints": constraints,
        "triggers": triggers,
        "indexes": indexes,
        "routines": routines,
        "git_commit": git_state.get("commit", "unknown"),
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
        SOURCE_AUTHORITY_RELEASE,
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
        SOURCE_AUTHORITY_RELEASE,
        root_dir,
        database_url,
        manifest_path,
        now=now,
        max_age=max_age,
        git_commit=git_commit,
        trusted_root=trusted_root,
        migration_loader=migration_loader,
    )


def apply_source_authority_migration(
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
        raise ReleaseAuthorizationError(
            "apply requires a real Git commit and clean worktree"
        )
    inspector = postflight_runner
    if postflight_runner is run_postflight:
        inspector = lambda root, dsn: run_postflight(root, dsn, migration_loader=migration_loader)
    return apply_release_migrations(
        SOURCE_AUTHORITY_RELEASE,
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
    parser = argparse.ArgumentParser(description="Guarded HXY source-authority release")
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
            result = apply_source_authority_migration(
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
    print(render_result(result, sensitive_values=_database_sensitive_values(database_url)))
    return 0 if result["status"] == "passed" else 2
