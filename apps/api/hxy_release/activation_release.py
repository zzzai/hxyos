from __future__ import annotations

import argparse
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row

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
) -> list[dict[str, str]]:
    return guarded_migration_inventory(
        ACTIVATION_RELEASE,
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
) -> dict[str, Any]:
    identity = database_identity(database_url)
    validate_hxy_boundary(root_dir, identity)
    inventory = migration_inventory(root_dir)
    connection_factory = connect_factory or _default_connect
    with connection_factory(database_url) as connection:
        connection.read_only = True
        server = connection.execute(
            """
            /* hxy_release:server */
            SELECT current_setting('server_version_num') AS server_version_num,
                   current_database() AS database,
                   current_user AS user
            """
        ).fetchone()
        relation_rows = connection.execute(
            """
            /* hxy_release:relations */
            SELECT relation_name AS name
            FROM unnest(%s::text[]) AS relation_name
            WHERE to_regclass(relation_name) IS NOT NULL
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
                WHERE table_schema = current_schema()
                  AND table_name = 'staff_sessions'
                  AND column_name = 'assignment_id'
                """
            ).fetchall()
            constraints = connection.execute(
                """
                /* hxy_release:constraints */
                SELECT relation.relname AS table_name,
                       constraint_row.contype AS constraint_type,
                       pg_get_constraintdef(constraint_row.oid) AS definition
                FROM pg_constraint AS constraint_row
                JOIN pg_class AS relation ON relation.oid = constraint_row.conrelid
                JOIN pg_namespace AS namespace_row ON namespace_row.oid = relation.relnamespace
                WHERE namespace_row.nspname = current_schema()
                  AND relation.relname = ANY(%s::text[])
                ORDER BY relation.relname, constraint_row.contype, constraint_row.conname
                """,
                (list(_ACTIVATION_TABLES + ("staff_sessions",)),),
            ).fetchall()
            indexes = connection.execute(
                """
                /* hxy_release:indexes */
                SELECT indexname AS index_name
                FROM pg_indexes
                WHERE schemaname = current_schema()
                  AND tablename = ANY(%s::text[])
                ORDER BY indexname
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
    normalized_constraints = [
        {
            "table": str(row.get("table_name") or ""),
            "type": str(row.get("constraint_type") or ""),
            "definition": " ".join(str(row.get("definition") or "").lower().split()),
        }
        for row in constraints
    ]

    def has_constraint(table: str, constraint_type: str, required: tuple[str, ...]) -> bool:
        return any(
            item["table"] == table
            and item["type"] == constraint_type
            and all(fragment in item["definition"] for fragment in required)
            for item in normalized_constraints
        )

    official_checks = [
        (
            "material_non_authority",
            has_constraint(
                "hxy_product_materials",
                "c",
                ("official_use_allowed", "false"),
            ),
        ),
        (
            "artifact_non_authority",
            has_constraint(
                "hxy_material_artifacts",
                "c",
                ("official_use_allowed", "false"),
            ),
        ),
        (
            "private_chunk_non_authority",
            has_constraint(
                "hxy_material_chunks",
                "c",
                ("official_use_allowed", "false"),
            ),
        ),
    ]
    chunk_owner = has_constraint(
        "hxy_material_chunks",
        "f",
        ("foreign key (assignment_id, material_id)", "hxy_product_materials"),
    )
    trace_unique = has_constraint(
        "hxy_product_answer_traces",
        "u",
        ("unique (assistant_message_id)",),
    )
    index_names = {str(row.get("index_name") or "") for row in indexes}
    assignment_session_column = any(
        str(row.get("table_name") or "") == "staff_sessions"
        and str(row.get("column_name") or "") == "assignment_id"
        for row in columns
    )
    assignment_session_fk = has_constraint(
        "staff_sessions",
        "f",
        ("foreign key (assignment_id)", "hxy_role_assignments(assignment_id)"),
    )
    assignment_session_index = "idx_staff_sessions_assignment_expires" in index_names
    assignment_session_scope = (
        assignment_session_column and assignment_session_fk and assignment_session_index
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
            "idx_hxy_material_chunks_content_trgm" in index_names,
            "index present"
            if "idx_hxy_material_chunks_content_trgm" in index_names
            else "index missing",
        ),
    ]


def run_preflight(
    root_dir: Path,
    database_url: str,
    *,
    connect_factory: ConnectFactory | None = None,
) -> dict[str, Any]:
    return _inspect_database(
        root_dir,
        database_url,
        phase="preflight",
        connect_factory=connect_factory,
    )


def run_postflight(
    root_dir: Path,
    database_url: str,
    *,
    connect_factory: ConnectFactory | None = None,
) -> dict[str, Any]:
    return _inspect_database(
        root_dir,
        database_url,
        phase="postflight",
        connect_factory=connect_factory,
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
) -> dict[str, Any]:
    result = create_release_backup(
        ACTIVATION_RELEASE,
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
        ACTIVATION_RELEASE,
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
) -> dict[str, Any]:
    result = apply_release_migrations(
        ACTIVATION_RELEASE,
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
            result = run_preflight(args.root_dir, database_url)
        elif args.command == "backup":
            output_root = args.output_root or _DEFAULT_BACKUP_ROOT
            result = create_backup(
                args.root_dir,
                database_url,
                output_root=output_root,
            )
        elif args.command == "apply":
            if args.backup_manifest is None:
                raise ReleaseAuthorizationError("--backup-manifest is required")
            result = apply_activation_migrations(
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
