from __future__ import annotations

import argparse
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import psycopg
from psycopg.conninfo import conninfo_to_dict

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

ONBOARDING_RELEASE = MigrationReleaseSpec(
    release_id="hxy-governed-onboarding-017",
    manifest_version=BACKUP_VERSION,
    migrations=ONBOARDING_MIGRATIONS,
    confirmation=APPLY_CONFIRMATION,
    advisory_lock="hxy-governed-onboarding-017",
    dump_filename="hxy-before-onboarding.dump",
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


def run_preflight(
    root_dir: Path,
    database_url: str,
    *,
    connect_factory: Any = None,
    git_inspector: Any = None,
    trusted_root: Path = _DEFAULT_TRUSTED_ROOT,
    migration_loader: MigrationLoader | None = None,
) -> dict[str, Any]:
    prerequisite = _prerequisite_result(
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
        {
            "name": "role_journeys_prerequisite",
            "status": "passed" if prerequisite.get("status") == "passed" else "failed",
            "detail": "009-016 postflight passed"
            if prerequisite.get("status") == "passed"
            else "009-016 postflight failed",
        },
        {
            "name": "git_commit",
            "status": "passed" if git_state.get("commit_valid") else "failed",
            "detail": "valid commit" if git_state.get("commit_valid") else "invalid commit",
        },
        {
            "name": "worktree_clean",
            "status": "passed" if git_state.get("worktree_clean") else "failed",
            "detail": str(git_state.get("detail") or "unknown")[:200],
        },
        {
            "name": "migration_inventory",
            "status": "passed" if len(inventory) == 1 else "failed",
            "detail": "017 checksummed" if len(inventory) == 1 else "017 unavailable",
        },
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
    trusted_root: Path = _DEFAULT_TRUSTED_ROOT,
    migration_loader: MigrationLoader | None = None,
) -> dict[str, Any]:
    prerequisite = _prerequisite_result(
        root_dir,
        database_url,
        connect_factory=connect_factory,
        trusted_root=trusted_root,
        migration_loader=migration_loader,
    )
    return {
        "status": prerequisite.get("status", "failed"),
        "phase": "postflight",
        "database": prerequisite.get("database", {}),
        "server_major": prerequisite.get("server_major", 0),
        "checks": [
            {
                "name": "role_journeys_prerequisite",
                "status": prerequisite.get("status", "failed"),
                "detail": "009-016 postflight passed"
                if prerequisite.get("status") == "passed"
                else "009-016 postflight failed",
            }
        ],
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
