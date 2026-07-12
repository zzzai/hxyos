from __future__ import annotations

import hashlib
import json
import os
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from psycopg.conninfo import conninfo_to_dict


_MAX_RESULT_STRING = 500

CommandRunner = Callable[[list[str], dict[str, str]], subprocess.CompletedProcess[str]]
InspectionRunner = Callable[[Path, str], dict[str, Any]]


@dataclass(frozen=True)
class MigrationReleaseSpec:
    release_id: str
    manifest_version: str
    migrations: tuple[str, ...]
    confirmation: str
    advisory_lock: str
    dump_filename: str


class ReleaseBoundaryError(ValueError):
    """Raised when a release target is outside the HXY boundary."""


class ReleaseBackupError(RuntimeError):
    """Raised when a release backup is missing, stale or unverifiable."""


class ReleaseAuthorizationError(RuntimeError):
    """Raised when a mutating release command lacks explicit authorization."""


class ReleaseExecutionError(RuntimeError):
    """Raised when a guarded external release command fails."""


def migration_inventory(
    spec: MigrationReleaseSpec,
    root_dir: Path,
) -> list[dict[str, str]]:
    migration_dir = root_dir.resolve() / "data" / "migrations"
    inventory: list[dict[str, str]] = []
    for name in spec.migrations:
        if not name or Path(name).name != name:
            raise ReleaseBoundaryError("migration path must be a filename")
        path = migration_dir / name
        inventory.append({"name": name, "sha256": _sha256_file(path)})
    return inventory


def database_identity(database_url: str) -> dict[str, str]:
    values = conninfo_to_dict(database_url)
    return {
        "host": str(values.get("host") or ""),
        "port": str(values.get("port") or "5432"),
        "database": str(values.get("dbname") or ""),
        "user": str(values.get("user") or ""),
    }


def validate_hxy_boundary(root_dir: Path, identity: dict[str, str]) -> None:
    root = root_dir.resolve()
    parts = {part.lower() for part in root.parts}
    if "htops" in parts or "hxy" not in parts:
        raise ReleaseBoundaryError("release root must be HXY-owned")
    database = str(identity.get("database") or "").strip().lower()
    if not database.startswith("hxy") or "htops" in database:
        raise ReleaseBoundaryError("release database must be HXY-owned")


def _validate_backup_path(path: Path) -> None:
    if "htops" in {part.lower() for part in path.resolve().parts}:
        raise ReleaseBoundaryError("backup path must be HXY-owned")


def _bounded_value(value: Any, sensitive_values: tuple[str, ...]) -> Any:
    if isinstance(value, dict):
        return {
            str(key)[:120]: _bounded_value(item, sensitive_values)
            for key, item in list(value.items())[:100]
        }
    if isinstance(value, (list, tuple)):
        return [_bounded_value(item, sensitive_values) for item in value[:100]]
    if isinstance(value, str):
        bounded = value
        for sensitive in sensitive_values:
            if sensitive:
                bounded = bounded.replace(sensitive, "[redacted]")
        return bounded[:_MAX_RESULT_STRING]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)[:_MAX_RESULT_STRING]


def render_result(
    payload: dict[str, Any],
    *,
    sensitive_values: Iterable[str] = (),
) -> str:
    redacted = _bounded_value(payload, tuple(sensitive_values))
    return json.dumps(redacted, ensure_ascii=False, sort_keys=True)


def _default_command_runner(
    command: list[str],
    env: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )


def _postgres_environment(database_url: str) -> dict[str, str]:
    values = conninfo_to_dict(database_url)
    inherited_keys = (
        "PATH",
        "HOME",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "TZ",
        "TMPDIR",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
    )
    env = {key: os.environ[key] for key in inherited_keys if key in os.environ}
    mappings = {
        "PGHOST": values.get("host") or "",
        "PGPORT": values.get("port") or "5432",
        "PGDATABASE": values.get("dbname") or "",
        "PGUSER": values.get("user") or "",
        "PGPASSWORD": values.get("password") or "",
        "PGSSLMODE": values.get("sslmode") or "prefer",
    }
    env.update({key: str(value) for key, value in mappings.items()})
    return env


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _current_git_commit(root_dir: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(root_dir.resolve()), "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    commit = result.stdout.strip()
    return commit if result.returncode == 0 and len(commit) == 40 else "unknown"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def create_release_backup(
    spec: MigrationReleaseSpec,
    root_dir: Path,
    database_url: str,
    *,
    output_root: Path,
    preflight_inspector: InspectionRunner,
    runner: CommandRunner | None = None,
    now: datetime | None = None,
    git_commit: str | None = None,
) -> dict[str, Any]:
    identity = database_identity(database_url)
    validate_hxy_boundary(root_dir, identity)
    preflight = preflight_inspector(root_dir, database_url)
    if preflight.get("status") != "passed":
        raise ReleaseBackupError("preflight must pass before backup")

    created_at = now or _utc_now()
    _validate_backup_path(output_root)
    if not spec.dump_filename or Path(spec.dump_filename).name != spec.dump_filename:
        raise ReleaseBoundaryError("backup dump path must be a filename")
    timestamp = created_at.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_dir = output_root.resolve() / timestamp
    if backup_dir.exists():
        raise ReleaseBackupError("backup target already exists")
    backup_dir.mkdir(parents=True, mode=0o700)
    backup_dir.chmod(0o700)
    dump_path = backup_dir / spec.dump_filename
    manifest_path = backup_dir / "manifest.json"
    command_runner = runner or _default_command_runner
    command_env = _postgres_environment(database_url)

    dump_result = command_runner(
        [
            "pg_dump",
            "--format=custom",
            "--no-owner",
            "--no-acl",
            "--file",
            str(dump_path),
        ],
        command_env,
    )
    if (
        dump_result.returncode != 0
        or not dump_path.is_file()
        or dump_path.stat().st_size <= 0
    ):
        raise ReleaseBackupError("database backup failed")
    dump_path.chmod(0o600)

    restore_result = command_runner(
        ["pg_restore", "--list", str(dump_path)],
        command_env,
    )
    if restore_result.returncode != 0:
        raise ReleaseBackupError("database backup verification failed")

    manifest = {
        "version": spec.manifest_version,
        "release_id": spec.release_id,
        "created_at": _iso_utc(created_at),
        "database": identity,
        "git_commit": git_commit or _current_git_commit(root_dir),
        "dump": {
            "file": dump_path.name,
            "size_bytes": dump_path.stat().st_size,
            "sha256": _sha256_file(dump_path),
            "verified": True,
        },
        "migrations": migration_inventory(spec, root_dir),
    }
    temporary_manifest = backup_dir / ".manifest.json.tmp"
    temporary_manifest.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary_manifest.chmod(0o600)
    temporary_manifest.replace(manifest_path)
    manifest_path.chmod(0o600)
    return {
        "status": "passed",
        "phase": "backup",
        "release_id": spec.release_id,
        "database": identity,
        "manifest_path": str(manifest_path),
        "dump_size_bytes": manifest["dump"]["size_bytes"],
        "migration_count": len(manifest["migrations"]),
    }


def validate_release_backup_manifest(
    spec: MigrationReleaseSpec,
    root_dir: Path,
    database_url: str,
    manifest_path: Path,
    *,
    now: datetime | None = None,
    max_age: timedelta = timedelta(hours=24),
    git_commit: str | None = None,
) -> dict[str, Any]:
    _validate_backup_path(manifest_path)
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ReleaseBackupError("backup manifest is unreadable") from exc
    if not isinstance(manifest, dict):
        raise ReleaseBackupError("backup manifest is invalid")
    if manifest.get("version") != spec.manifest_version:
        raise ReleaseBackupError("backup manifest version does not match release")
    if manifest.get("release_id") != spec.release_id:
        raise ReleaseBackupError("backup manifest release does not match specification")

    identity = database_identity(database_url)
    validate_hxy_boundary(root_dir, identity)
    if manifest.get("database") != identity:
        raise ReleaseBackupError("backup database does not match release target")
    expected_commit = git_commit or _current_git_commit(root_dir)
    if manifest.get("git_commit") != expected_commit:
        raise ReleaseBackupError("backup Git commit does not match release source")
    if manifest.get("migrations") != migration_inventory(spec, root_dir):
        raise ReleaseBackupError("backup migration inventory does not match release files")

    try:
        created_at = datetime.fromisoformat(
            str(manifest["created_at"]).replace("Z", "+00:00")
        ).astimezone(timezone.utc)
    except (KeyError, ValueError, TypeError) as exc:
        raise ReleaseBackupError("backup creation time is invalid") from exc
    current_time = (now or _utc_now()).astimezone(timezone.utc)
    age = current_time - created_at
    if age > max_age or age < -timedelta(minutes=5):
        raise ReleaseBackupError("backup manifest is stale")

    dump = manifest.get("dump")
    if not isinstance(dump, dict) or dump.get("verified") is not True:
        raise ReleaseBackupError("backup verification marker is missing")
    dump_name = str(dump.get("file") or "")
    if dump_name != spec.dump_filename or Path(dump_name).name != dump_name:
        raise ReleaseBackupError("backup dump path does not match release")
    dump_path = manifest_path.resolve().parent / dump_name
    if not dump_path.is_file():
        raise ReleaseBackupError("backup dump is missing")
    try:
        expected_size = int(dump.get("size_bytes"))
    except (TypeError, ValueError) as exc:
        raise ReleaseBackupError("backup dump size is invalid") from exc
    if dump_path.stat().st_size != expected_size:
        raise ReleaseBackupError("backup dump size does not match manifest")
    if _sha256_file(dump_path) != str(dump.get("sha256") or ""):
        raise ReleaseBackupError("backup dump checksum does not match manifest")
    return {
        "status": "passed",
        "phase": "backup_validation",
        "release_id": spec.release_id,
        "database": identity,
        "manifest_path": str(manifest_path.resolve()),
        "dump_path": str(dump_path),
        "created_at": _iso_utc(created_at),
        "git_commit": expected_commit,
    }


def apply_release_migrations(
    spec: MigrationReleaseSpec,
    root_dir: Path,
    database_url: str,
    *,
    manifest_path: Path,
    confirmation: str,
    postflight_inspector: InspectionRunner,
    runner: CommandRunner | None = None,
    now: datetime | None = None,
    git_commit: str | None = None,
) -> dict[str, Any]:
    if confirmation != spec.confirmation:
        raise ReleaseAuthorizationError("exact migration confirmation is required")
    validated_backup = validate_release_backup_manifest(
        spec,
        root_dir,
        database_url,
        manifest_path,
        now=now,
        git_commit=git_commit,
    )
    command_runner = runner or _default_command_runner
    command_env = _postgres_environment(database_url)
    restore_result = command_runner(
        ["pg_restore", "--list", str(validated_backup["dump_path"])],
        command_env,
    )
    if restore_result.returncode != 0:
        raise ReleaseBackupError("database backup verification failed before migration")

    advisory_lock = spec.advisory_lock.replace("'", "''")
    command = [
        "psql",
        "--no-psqlrc",
        "--set",
        "ON_ERROR_STOP=1",
        "--single-transaction",
        "--command",
        f"SELECT pg_advisory_xact_lock(hashtext('{advisory_lock}'))",
    ]
    for migration in spec.migrations:
        command.extend(
            [
                "--file",
                str(root_dir.resolve() / "data" / "migrations" / migration),
            ]
        )
    result = command_runner(command, command_env)
    if result.returncode != 0:
        raise ReleaseExecutionError("release migration transaction failed")

    postflight = postflight_inspector(root_dir, database_url)
    if postflight.get("status") != "passed":
        raise ReleaseExecutionError("release postflight failed")
    return {
        "status": "passed",
        "phase": "apply",
        "release_id": spec.release_id,
        "database": database_identity(database_url),
        "migration_count": len(spec.migrations),
        "backup_created_at": validated_backup["created_at"],
        "git_commit": validated_backup["git_commit"],
        "postflight": "passed",
    }
