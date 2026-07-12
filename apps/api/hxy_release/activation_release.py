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

from .guarded_migration import (
    CommandRunner,
    InspectionRunner,
    MigrationLoader,
    MigrationReleaseSpec,
    ReleaseAuthorizationError,
    ReleaseBackupError,
    ReleaseBoundaryError,
    ReleaseExecutionError,
    ReleaseInstanceError,
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


ACTIVATION_MIGRATIONS = (
    "009_hxy_product_identity.sql",
    "010_hxy_product_conversations.sql",
    "011_hxy_product_materials.sql",
    "012_hxy_assignment_sessions.sql",
    "013_hxy_material_intake_jobs.sql",
    "014_hxy_knowledge_activation.sql",
)
APPLY_CONFIRMATION = "APPLY-HXY-009-014"
BACKUP_VERSION = "hxy-activation-backup.v2"
_DEFAULT_TRUSTED_ROOT = Path("/root/hxy")
_DEFAULT_BACKUP_ROOT = (
    _DEFAULT_TRUSTED_ROOT / "data" / "backups" / "knowledge-activation"
)

ACTIVATION_RELEASE = MigrationReleaseSpec(
    release_id="hxy-knowledge-activation-009-014",
    manifest_version=BACKUP_VERSION,
    migrations=ACTIVATION_MIGRATIONS,
    confirmation=APPLY_CONFIRMATION,
    advisory_lock="hxy-knowledge-activation-009-014",
    dump_filename="hxy-before-activation.dump",
    legacy_release="009-014",
)

_BASELINE_TABLES = ("staff_accounts", "stores")
_ACTIVATION_TABLES = (
    "hxy_organizations",
    "hxy_role_assignments",
    "hxy_product_conversations",
    "hxy_product_messages",
    "hxy_product_materials",
    "hxy_material_parser_jobs",
    "hxy_material_artifacts",
    "hxy_material_chunks",
    "hxy_product_answer_traces",
)

ConnectFactory = Callable[[str], Any]


def migration_inventory(
    root_dir: Path,
    *,
    trusted_root: Path = _DEFAULT_TRUSTED_ROOT,
    migration_loader: MigrationLoader | None = None,
) -> list[dict[str, str]]:
    return guarded_migration_inventory(
        ACTIVATION_RELEASE,
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
    guarded_validate_hxy_boundary(
        root_dir,
        identity,
        trusted_root=trusted_root,
    )


def _default_connect(database_url: str):
    return psycopg.connect(database_url, row_factory=dict_row)


def _check(name: str, passed: bool, detail: str) -> dict[str, str]:
    return {
        "name": name,
        "status": "passed" if passed else "failed",
        "detail": detail[:200],
    }


def _inspect_database(
    root_dir: Path,
    database_url: str,
    *,
    phase: str,
    connect_factory: ConnectFactory | None,
    migration_loader: MigrationLoader | None,
) -> dict[str, Any]:
    identity = database_identity(database_url)
    validate_hxy_boundary(root_dir, identity)
    inventory = migration_inventory(root_dir, migration_loader=migration_loader)
    connection_factory = connect_factory or _default_connect
    with connection_factory(database_url) as connection:
        connection.read_only = True
        server = connection.execute(
            """
            /* hxy_release:server */
            SELECT current_setting('server_version_num') AS server_version_num,
                   current_database() AS database,
                   current_user AS user,
                   current_schema() AS current_schema
            """
        ).fetchone()
        relation_rows = connection.execute(
            """
            /* hxy_release:relations */
            SELECT relation_name AS name
            FROM unnest(%s::text[]) AS relation_name
            WHERE to_regclass('public.' || relation_name) IS NOT NULL
            ORDER BY relation_name
            """,
            (list(_BASELINE_TABLES + _ACTIVATION_TABLES),),
        ).fetchall()
        constraints: list[dict[str, Any]] = []
        indexes: list[dict[str, Any]] = []
        columns: list[dict[str, Any]] = []
        if phase == "postflight":
            columns = connection.execute(
                """
                /* hxy_release:columns */
                SELECT table_name, column_name
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'staff_sessions'
                  AND column_name = 'assignment_id'
                """
            ).fetchall()
            constraints = connection.execute(
                """
                /* hxy_release:constraints */
                SELECT constraint_row.contype AS constraint_type,
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
                  AND constraint_row.contype IN ('c', 'f', 'u')
                ORDER BY source_relation.relname, constraint_row.contype,
                         constraint_row.conname
                """,
                (list(_ACTIVATION_TABLES + ("staff_sessions",)),),
            ).fetchall()
            indexes = connection.execute(
                """
                /* hxy_release:indexes */
                SELECT namespace_row.nspname AS table_schema,
                       table_relation.relname AS table_name,
                       index_relation.relname AS index_name,
                       access_method.amname AS access_method,
                       ARRAY(
                         SELECT pg_get_indexdef(index_relation.oid, position, true)
                         FROM generate_series(1, index_row.indnkeyatts) AS position
                         ORDER BY position
                       ) AS index_columns,
                       ARRAY(
                         SELECT operator_class.opcname
                         FROM unnest(index_row.indclass::oid[]) WITH ORDINALITY
                           AS class_key(opclass_oid, position)
                         JOIN pg_opclass AS operator_class
                           ON operator_class.oid = class_key.opclass_oid
                         ORDER BY class_key.position
                       ) AS opclasses,
                       pg_get_expr(index_row.indpred, index_row.indrelid) AS predicate,
                       index_row.indisvalid,
                       index_row.indisunique
                FROM pg_index AS index_row
                JOIN pg_class AS table_relation
                  ON table_relation.oid = index_row.indrelid
                JOIN pg_class AS index_relation
                  ON index_relation.oid = index_row.indexrelid
                JOIN pg_namespace AS namespace_row
                  ON namespace_row.oid = table_relation.relnamespace
                JOIN pg_am AS access_method
                  ON access_method.oid = index_relation.relam
                WHERE namespace_row.nspname = 'public'
                  AND table_relation.relname = ANY(%s::text[])
                ORDER BY index_relation.relname
                """,
                (list(_ACTIVATION_TABLES + ("staff_sessions",)),),
            ).fetchall()

    server_version = str(server.get("server_version_num") or "0")
    server_major = int(server_version) // 10000
    relation_names = {str(row["name"]) for row in relation_rows}
    missing_baseline = sorted(set(_BASELINE_TABLES) - relation_names)
    pending_tables = sorted(set(_ACTIVATION_TABLES) - relation_names)
    checks = [
        _check("postgres_major", server_major == 16, f"major={server_major}"),
        _check(
            "database_identity",
            str(server.get("database") or "") == identity["database"],
            "connected database matches target identity",
        ),
        _check(
            "current_schema",
            str(server.get("current_schema") or "") == "public",
            f"schema={str(server.get('current_schema') or 'unknown')}",
        ),
        _check(
            "baseline_tables",
            not missing_baseline,
            "complete" if not missing_baseline else f"missing={','.join(missing_baseline)}",
        ),
        _check("migration_inventory", len(inventory) == 6, "009-014 checksummed"),
    ]

    if phase == "postflight":
        checks.extend(_postflight_checks(pending_tables, columns, constraints, indexes))

    status = "passed" if all(check["status"] == "passed" for check in checks) else "failed"
    return {
        "status": status,
        "phase": phase,
        "database": identity,
        "server_major": server_major,
        "pending_tables": pending_tables,
        "checks": checks,
        "migration_count": len(inventory),
    }


def _postflight_checks(
    pending_tables: list[str],
    columns: list[dict[str, Any]],
    constraints: list[dict[str, Any]],
    indexes: list[dict[str, Any]],
) -> list[dict[str, str]]:
    def row_columns(row: dict[str, Any], key: str) -> tuple[str, ...]:
        return tuple(str(item) for item in row.get(key) or ())

    def exact_check(table: str) -> bool:
        return any(
            str(row.get("constraint_type") or "") == "c"
            and str(row.get("source_schema") or "") == "public"
            and str(row.get("source_table") or "") == table
            and row_columns(row, "source_columns") == ("official_use_allowed",)
            and row.get("convalidated") is True
            and _canonical_check_expression(row.get("check_expression"))
            == "official_use_allowed=false"
            for row in constraints
        )

    def exact_constraint(
        constraint_type: str,
        source_table: str,
        source_columns: tuple[str, ...],
        target_table: str = "",
        target_columns: tuple[str, ...] = (),
        delete_action: str = " ",
    ) -> bool:
        return any(
            str(row.get("constraint_type") or "") == constraint_type
            and str(row.get("source_schema") or "") == "public"
            and str(row.get("source_table") or "") == source_table
            and row_columns(row, "source_columns") == source_columns
            and str(row.get("target_schema") or "")
            == ("public" if target_table else "")
            and str(row.get("target_table") or "") == target_table
            and row_columns(row, "target_columns") == target_columns
            and row.get("convalidated") is True
            and str(row.get("confdeltype") or " ") == delete_action
            for row in constraints
        )

    official_checks = [
        (
            "material_non_authority",
            exact_check("hxy_product_materials"),
        ),
        (
            "artifact_non_authority",
            exact_check("hxy_material_artifacts"),
        ),
        (
            "private_chunk_non_authority",
            exact_check("hxy_material_chunks"),
        ),
    ]
    chunk_owner = exact_constraint(
        "f",
        "hxy_material_chunks",
        ("assignment_id", "material_id"),
        "hxy_product_materials",
        ("assignment_id", "material_id"),
        "c",
    )
    trace_unique = exact_constraint(
        "u",
        "hxy_product_answer_traces",
        ("assistant_message_id",),
    )
    assignment_session_column = any(
        str(row.get("table_name") or "") == "staff_sessions"
        and str(row.get("column_name") or "") == "assignment_id"
        for row in columns
    )
    assignment_session_fk = exact_constraint(
        "f",
        "staff_sessions",
        ("assignment_id",),
        "hxy_role_assignments",
        ("assignment_id",),
        "c",
    )
    assignment_session_index = any(
        str(row.get("table_schema") or "") == "public"
        and str(row.get("table_name") or "") == "staff_sessions"
        and str(row.get("index_name") or "")
        == "idx_staff_sessions_assignment_expires"
        and str(row.get("access_method") or "") == "btree"
        and row_columns(row, "index_columns") == ("assignment_id", "expires_at")
        and _canonical_predicate(row.get("predicate"))
        == "assignment_idisnotnull"
        and row.get("indisvalid") is True
        and row.get("indisunique") is False
        for row in indexes
    )
    assignment_session_scope = (
        assignment_session_column and assignment_session_fk and assignment_session_index
    )
    trigram_index = any(
        str(row.get("table_schema") or "") == "public"
        and str(row.get("table_name") or "") == "hxy_material_chunks"
        and str(row.get("index_name") or "")
        == "idx_hxy_material_chunks_content_trgm"
        and str(row.get("access_method") or "") == "gin"
        and row_columns(row, "index_columns") == ("content",)
        and row_columns(row, "opclasses") == ("gin_trgm_ops",)
        and row.get("predicate") in (None, "")
        and row.get("indisvalid") is True
        for row in indexes
    )
    return [
        _check(
            "activation_tables",
            not pending_tables,
            "complete" if not pending_tables else f"missing={','.join(pending_tables)}",
        ),
        *[
            _check(name, passed, "constraint present" if passed else "constraint missing")
            for name, passed in official_checks
        ],
        _check(
            "assignment_session_scope",
            assignment_session_scope,
            "column, constraint and index present"
            if assignment_session_scope
            else "column, constraint or index missing",
        ),
        _check(
            "private_chunk_assignment_owner",
            chunk_owner,
            "constraint present" if chunk_owner else "constraint missing",
        ),
        _check(
            "answer_trace_one_per_assistant",
            trace_unique,
            "constraint present" if trace_unique else "constraint missing",
        ),
        _check(
            "private_chunk_trigram_index",
            trigram_index,
            "index present" if trigram_index else "index missing",
        ),
    ]


def _canonical_check_expression(value: Any) -> str:
    normalized = str(value or "").lower().replace('"', "")
    normalized = re.sub(r"::(?:boolean|bool)", "", normalized)
    return re.sub(r"[\s()]", "", normalized)


def _canonical_predicate(value: Any) -> str | None:
    if value in (None, ""):
        return None
    normalized = str(value).lower().replace('"', "")
    normalized = re.sub(r"::[a-z ]+", "", normalized)
    return re.sub(r"[\s()]", "", normalized)


def run_preflight(
    root_dir: Path,
    database_url: str,
    *,
    connect_factory: ConnectFactory | None = None,
    migration_loader: MigrationLoader | None = None,
) -> dict[str, Any]:
    return _inspect_database(
        root_dir,
        database_url,
        phase="preflight",
        connect_factory=connect_factory,
        migration_loader=migration_loader,
    )


def run_postflight(
    root_dir: Path,
    database_url: str,
    *,
    connect_factory: ConnectFactory | None = None,
    migration_loader: MigrationLoader | None = None,
) -> dict[str, Any]:
    return _inspect_database(
        root_dir,
        database_url,
        phase="postflight",
        connect_factory=connect_factory,
        migration_loader=migration_loader,
    )


def _database_sensitive_values(database_url: str) -> tuple[str, ...]:
    values = conninfo_to_dict(database_url)
    return tuple(
        value
        for value in (database_url, str(values.get("password") or ""))
        if value
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
    preflight_inspector = preflight_runner
    if preflight_runner is run_preflight:
        preflight_inspector = lambda root, dsn: run_preflight(
            root,
            dsn,
            migration_loader=migration_loader,
        )
    result = create_release_backup(
        ACTIVATION_RELEASE,
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
        ACTIVATION_RELEASE,
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


def apply_activation_migrations(
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
    migration_loader: MigrationLoader | None = None,
) -> dict[str, Any]:
    postflight_inspector = postflight_runner
    if postflight_runner is run_postflight:
        postflight_inspector = lambda root, dsn: run_postflight(
            root,
            dsn,
            migration_loader=migration_loader,
        )
    result = apply_release_migrations(
        ACTIVATION_RELEASE,
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
    parser = argparse.ArgumentParser(description="Guarded HXY knowledge activation release")
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
            output_root = args.output_root or _DEFAULT_BACKUP_ROOT
            result = create_backup(
                args.root_dir,
                database_url,
                output_root=output_root,
                migration_loader=git_head_migration_loader,
            )
        elif args.command == "apply":
            if args.backup_manifest is None:
                raise ReleaseAuthorizationError("--backup-manifest is required")
            result = apply_activation_migrations(
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
    except ReleaseInstanceError as exc:
        result = {
            "status": "failed",
            "phase": args.command,
            "error_type": (
                "ReleaseExecutionError" if exc.applied else type(exc).__name__
            ),
            "error": str(exc),
            "applied": exc.applied,
        }
        if exc.applied:
            result["error_code"] = "instance_changed_after_apply"
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
