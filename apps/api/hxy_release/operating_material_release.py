from __future__ import annotations

import argparse
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

import psycopg
from psycopg.rows import dict_row

from . import global_source_authority_release, role_journeys_release
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


OPERATING_MATERIAL_MIGRATIONS = (
    "020_hxy_data_catalog.sql",
    "021_hxy_operating_loop.sql",
    "022_hxy_operating_api_hardening.sql",
    "023_hxy_material_safety_scan.sql",
)
APPLY_CONFIRMATION = "APPLY-HXY-020-023"
BACKUP_VERSION = "hxy-operating-material-backup.v1"
_DEFAULT_TRUSTED_ROOT = Path("/root/hxy")
_DEFAULT_BACKUP_ROOT = _DEFAULT_TRUSTED_ROOT / "data" / "backups" / "operating-material"

OPERATING_MATERIAL_RELEASE = MigrationReleaseSpec(
    release_id="hxy-operating-material-020-023",
    manifest_version=BACKUP_VERSION,
    migrations=OPERATING_MATERIAL_MIGRATIONS,
    confirmation=APPLY_CONFIRMATION,
    advisory_lock="hxy-operating-material-020-023",
    dump_filename="hxy-before-operating-material.dump",
)

_TARGET_RELATIONS = frozenset(
    {
        "hxy_legal_entities",
        "hxy_operating_mode_catalog",
        "hxy_governance_profiles",
        "hxy_store_operating_relationships",
        "hxy_data_sources",
        "hxy_data_connectors",
        "hxy_dataset_snapshots",
        "hxy_business_facts",
        "hxy_metric_definitions",
        "hxy_asset_bindings",
        "hxy_channel_identity_bindings",
        "hxy_inbound_envelopes",
        "hxy_ai_proposals",
        "hxy_outbox_messages",
        "hxy_outbox_attempts",
        "hxy_operating_events",
        "hxy_workflow_instances",
        "hxy_operating_evidence",
        "hxy_state_transitions",
        "hxy_metric_facts",
        "hxy_operating_command_receipts",
        "hxy_material_scan_results",
        "hxy_material_job_requeue_events",
    }
)

_REQUIRED_COLUMNS = {
    "hxy_product_materials": frozenset({"organization_id", "store_id"}),
    "hxy_product_tasks": frozenset(
        {
            "operating_event_id",
            "workflow_instance_id",
            "task_type",
            "submitted_at",
            "accepted_at",
            "acceptance_assignment_id",
        }
    ),
    "hxy_inbound_envelopes": frozenset({"request_fingerprint"}),
    "hxy_material_parser_jobs": frozenset({"job_type"}),
    "hxy_material_job_attempts": frozenset(
        {"source_sha256", "source_size_bytes"}
    ),
}

ConnectFactory = Callable[[str], Any]
PrerequisiteRunner = Callable[..., dict[str, Any]]


def migration_inventory(
    root_dir: Path,
    *,
    trusted_root: Path = _DEFAULT_TRUSTED_ROOT,
    migration_loader: MigrationLoader | None = None,
) -> list[dict[str, str]]:
    return guarded_migration_inventory(
        OPERATING_MATERIAL_RELEASE,
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


def _normalized_relations(value: Any) -> set[str]:
    return {str(item) for item in value or ()}


def _normalized_columns(value: Any) -> dict[str, set[str]]:
    if not isinstance(value, dict):
        return {}
    return {
        str(table): {str(column) for column in columns or ()}
        for table, columns in value.items()
    }


def _required_columns_complete(columns: dict[str, set[str]]) -> bool:
    return all(
        expected.issubset(columns.get(table, set()))
        for table, expected in _REQUIRED_COLUMNS.items()
    )


def _migration_state(snapshot: dict[str, Any]) -> str:
    relations = _normalized_relations(snapshot.get("relation_names"))
    columns = _normalized_columns(snapshot.get("required_columns"))
    has_signature_column = any(
        expected.intersection(columns.get(table, set()))
        for table, expected in _REQUIRED_COLUMNS.items()
    )
    if not relations.intersection(_TARGET_RELATIONS) and not has_signature_column:
        return "pending"
    if (
        _TARGET_RELATIONS.issubset(relations)
        and _required_columns_complete(columns)
        and snapshot.get("material_identity_check") is True
    ):
        return "applied"
    return "partial"


def evaluate_release_snapshot(
    snapshot: dict[str, Any],
    *,
    phase: str,
) -> dict[str, Any]:
    if phase not in {"preflight", "postflight"}:
        raise ValueError("phase must be preflight or postflight")
    state = _migration_state(snapshot)
    columns = _normalized_columns(snapshot.get("required_columns"))
    checks = [
        _check(
            "postgres_major",
            snapshot.get("server_major") == 16,
            f"major={snapshot.get('server_major')}",
        ),
        _check(
            "database_identity",
            snapshot.get("database_matches") is True,
            "connected database matches HXY target",
        ),
        _check(
            "current_schema",
            snapshot.get("current_schema") == "public",
            f"schema={snapshot.get('current_schema')}",
        ),
        _check(
            "global_source_authority_prerequisite",
            snapshot.get("prerequisite_passed") is True,
            "019 postflight passed",
        ),
        _check(
            "migration_inventory",
            int(snapshot.get("migration_count") or 0) == 4,
            "020-023 checksummed",
        ),
    ]
    if phase == "preflight":
        checks.extend(
            [
                _check(
                    "git_commit",
                    snapshot.get("commit_valid") is True,
                    "valid commit required",
                ),
                _check(
                    "worktree_clean",
                    snapshot.get("worktree_clean") is True,
                    "clean immutable source required",
                ),
                _check("migration_pending", state == "pending", f"state={state}"),
            ]
        )
    else:
        missing_relations = sorted(
            _TARGET_RELATIONS - _normalized_relations(snapshot.get("relation_names"))
        )
        missing_columns = {
            table: sorted(expected - columns.get(table, set()))
            for table, expected in _REQUIRED_COLUMNS.items()
            if not expected.issubset(columns.get(table, set()))
        }
        checks.extend(
            [
                _check("migration_applied", state == "applied", f"state={state}"),
                _check(
                    "required_relations",
                    not missing_relations,
                    f"missing={','.join(missing_relations)}",
                ),
                _check(
                    "required_columns",
                    not missing_columns,
                    f"missing_tables={','.join(sorted(missing_columns))}",
                ),
                _check(
                    "material_source_identity",
                    snapshot.get("material_identity_check") is True,
                    "hash and size must be present together",
                ),
            ]
        )
    return {
        "status": "passed"
        if all(item["status"] == "passed" for item in checks)
        else "failed",
        "phase": phase,
        "migration_state": state,
        "checks": checks,
    }


def _default_connect(database_url: str):
    return psycopg.connect(database_url, row_factory=dict_row)


def _default_prerequisite(
    root_dir: Path,
    database_url: str,
    **kwargs: Any,
) -> dict[str, Any]:
    return global_source_authority_release.run_postflight(
        root_dir,
        database_url,
        **kwargs,
    )


def _prerequisite_contract_passed(result: dict[str, Any]) -> bool:
    required_checks = {
        "postgres_major",
        "database_identity",
        "current_schema",
        "source_authority_prerequisite",
        "migration_inventory",
        "global_source_authority_schema",
        "complete_baseline_events",
    }
    passed_checks = {
        str(item.get("name") or "")
        for item in result.get("checks", ())
        if isinstance(item, dict) and item.get("status") == "passed"
    }
    return required_checks.issubset(passed_checks)


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
    prerequisite = prerequisite_runner(
        root_dir,
        database_url,
        migration_loader=migration_loader,
    )
    with (connect_factory or _default_connect)(database_url) as connection:
        connection.read_only = True
        server = connection.execute(
            """
            /* hxy_operating_material_release:server */
            SELECT current_setting('server_version_num') AS server_version_num,
                   current_database() AS database,
                   current_schema() AS current_schema
            """
        ).fetchone()
        relation_rows = connection.execute(
            """
            /* hxy_operating_material_release:relations */
            SELECT relation_name AS name
            FROM unnest(%s::text[]) AS relation_name
            WHERE to_regclass('public.' || relation_name) IS NOT NULL
            ORDER BY relation_name
            """,
            (sorted(_TARGET_RELATIONS),),
        ).fetchall()
        column_rows = connection.execute(
            """
            /* hxy_operating_material_release:columns */
            SELECT table_name, column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = ANY(%s::text[])
              AND column_name = ANY(%s::text[])
            ORDER BY table_name, column_name
            """,
            (
                sorted(_REQUIRED_COLUMNS),
                sorted({column for values in _REQUIRED_COLUMNS.values() for column in values}),
            ),
        ).fetchall()
        identity_row = connection.execute(
            """
            /* hxy_operating_material_release:identity_constraint */
            SELECT COALESCE(bool_or(
              constraint_row.convalidated
              AND pg_get_constraintdef(constraint_row.oid) ILIKE '%%source_sha256 IS NOT NULL%%'
              AND pg_get_constraintdef(constraint_row.oid) ILIKE '%%source_size_bytes IS NOT NULL%%'
            ), false) AS valid
            FROM pg_constraint AS constraint_row
            JOIN pg_class AS relation ON relation.oid = constraint_row.conrelid
            JOIN pg_namespace AS namespace_row ON namespace_row.oid = relation.relnamespace
            WHERE namespace_row.nspname = 'public'
              AND relation.relname = 'hxy_material_job_attempts'
              AND constraint_row.conname = 'hxy_material_job_attempts_source_identity_check'
            """
        ).fetchone()

    columns: dict[str, list[str]] = {table: [] for table in _REQUIRED_COLUMNS}
    for row in column_rows:
        table_name = str(row.get("table_name") or "")
        column_name = str(row.get("column_name") or "")
        if column_name in _REQUIRED_COLUMNS.get(table_name, frozenset()):
            columns[table_name].append(column_name)
    git_state = {"commit": "unknown", "commit_valid": False, "worktree_clean": False}
    if phase == "preflight":
        git_state = (git_inspector or role_journeys_release.inspect_git_worktree)(
            root_dir
        )
    snapshot = {
        "server_major": int(str(server.get("server_version_num") or "0")) // 10000,
        "database_matches": str(server.get("database") or "") == identity["database"],
        "current_schema": str(server.get("current_schema") or ""),
        "prerequisite_passed": _prerequisite_contract_passed(prerequisite),
        "migration_count": len(inventory),
        "relation_names": [str(row.get("name") or "") for row in relation_rows],
        "required_columns": columns,
        "material_identity_check": bool((identity_row or {}).get("valid")),
        "git_commit": git_state.get("commit", "unknown"),
        "commit_valid": git_state.get("commit_valid") is True,
        "worktree_clean": git_state.get("worktree_clean") is True,
    }
    result = evaluate_release_snapshot(snapshot, phase=phase)
    result["database"] = identity
    if phase == "preflight":
        result["git_commit"] = snapshot["git_commit"]
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
        inspector = lambda root, dsn: run_preflight(
            root,
            dsn,
            migration_loader=migration_loader,
        )
    return create_release_backup(
        OPERATING_MATERIAL_RELEASE,
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
        OPERATING_MATERIAL_RELEASE,
        root_dir,
        database_url,
        manifest_path,
        now=now,
        max_age=max_age,
        git_commit=git_commit,
        trusted_root=trusted_root,
        migration_loader=migration_loader,
    )


def apply_operating_material_migrations(
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
        inspector = lambda root, dsn: run_postflight(
            root,
            dsn,
            migration_loader=migration_loader,
        )
    return apply_release_migrations(
        OPERATING_MATERIAL_RELEASE,
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
    parser = argparse.ArgumentParser(
        description="Guarded HXY operating and material release"
    )
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
            result = apply_operating_material_migrations(
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
            sensitive_values=global_source_authority_release.source_authority_release._database_sensitive_values(
                database_url
            ),
        )
    )
    return 0 if result["status"] == "passed" else 2
