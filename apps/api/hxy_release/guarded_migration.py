from __future__ import annotations

import hashlib
import json
import os
import secrets
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from psycopg import pq
from psycopg.conninfo import conninfo_to_dict


_MAX_RESULT_STRING = 500
_DEFAULT_TRUSTED_ROOT = Path("/root/hxy")
_CONNINFO_ENVIRONMENT = {
    item.keyword.decode(): item.envvar.decode()
    for item in pq.Conninfo.get_defaults()
    if item.envvar is not None
}

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


class ReleasePostflightError(ReleaseExecutionError):
    """Raised after migrations commit but their postflight inspection fails."""

    def __init__(self, postflight: Any) -> None:
        super().__init__("release postflight failed after migrations committed")
        self.applied = True
        self.postflight = _bounded_value(postflight, ())
        self.detail = self.postflight


def _contains_htops(path: Path) -> bool:
    return any("htops" in part.lower() for part in path.parts)


def _validate_release_root(root_dir: Path, trusted_root: Path) -> Path:
    root = root_dir.resolve()
    trusted = trusted_root.resolve()
    if _contains_htops(root) or not root.is_relative_to(trusted):
        raise ReleaseBoundaryError("release root must be within trusted HXY root")
    return root


def migration_inventory(
    spec: MigrationReleaseSpec,
    root_dir: Path,
    *,
    trusted_root: Path = _DEFAULT_TRUSTED_ROOT,
) -> list[dict[str, str]]:
    migration_dir = (
        _validate_release_root(root_dir, trusted_root) / "data" / "migrations"
    )
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


def validate_hxy_boundary(
    root_dir: Path,
    identity: dict[str, str],
    *,
    trusted_root: Path = _DEFAULT_TRUSTED_ROOT,
) -> None:
    _validate_release_root(root_dir, trusted_root)
    database = str(identity.get("database") or "").strip().lower()
    if not database.startswith("hxy") or "htops" in database:
        raise ReleaseBoundaryError("release database must be HXY-owned")


def _validate_backup_path(path: Path, trusted_root: Path) -> Path:
    resolved = path.resolve()
    backup_root = (trusted_root.resolve() / "data" / "backups").resolve()
    if _contains_htops(resolved) or not resolved.is_relative_to(backup_root):
        raise ReleaseBoundaryError("backup path must be within trusted HXY backups")
    return resolved


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
    unsupported = sorted(
        key
        for key, value in values.items()
        if value not in (None, "") and key not in _CONNINFO_ENVIRONMENT
    )
    if unsupported:
        raise ReleaseExecutionError(
            "libpq parameters cannot be preserved for subprocesses: "
            + ", ".join(unsupported)
        )
    env.update(
        {
            _CONNINFO_ENVIRONMENT[key]: str(value)
            for key, value in values.items()
            if value not in (None, "")
        }
    )
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
    trusted_root: Path = _DEFAULT_TRUSTED_ROOT,
) -> dict[str, Any]:
    identity = database_identity(database_url)
    validate_hxy_boundary(root_dir, identity, trusted_root=trusted_root)
    output_root = _validate_backup_path(output_root, trusted_root)
    if not spec.dump_filename or Path(spec.dump_filename).name != spec.dump_filename:
        raise ReleaseBoundaryError("backup dump path must be a filename")
    command_env = _postgres_environment(database_url)
    preflight = preflight_inspector(root_dir, database_url)
    if preflight.get("status") != "passed":
        raise ReleaseBackupError("preflight must pass before backup")

    created_at = now or _utc_now()
    timestamp = created_at.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_dir = output_root / timestamp
    if backup_dir.exists():
        raise ReleaseBackupError("backup target already exists")
    backup_dir.mkdir(parents=True, mode=0o700)
    backup_dir.chmod(0o700)
    dump_path = backup_dir / spec.dump_filename
    manifest_path = backup_dir / "manifest.json"
    command_runner = runner or _default_command_runner

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

    temporary_database = f"hxy_verify_{secrets.token_hex(8)}"
    maintenance_option = f"--maintenance-db={identity['database']}"
    create_result: subprocess.CompletedProcess[str] | None = None
    restore_result: subprocess.CompletedProcess[str] | None = None
    cleanup_result: subprocess.CompletedProcess[str] | None = None
    verification_error: Exception | None = None
    try:
        create_result = command_runner(
            ["createdb", maintenance_option, temporary_database],
            command_env,
        )
        if create_result.returncode == 0:
            restore_result = command_runner(
                [
                    "pg_restore",
                    "--exit-on-error",
                    "--no-owner",
                    "--no-acl",
                    f"--dbname={temporary_database}",
                    str(dump_path),
                ],
                command_env,
            )
    except Exception as exc:
        verification_error = exc
    finally:
        try:
            cleanup_result = command_runner(
                ["dropdb", "--if-exists", maintenance_option, temporary_database],
                command_env,
            )
        except Exception as exc:
            if verification_error is None:
                verification_error = exc

    if verification_error is not None:
        raise ReleaseBackupError(
            "database backup restore verification failed"
        ) from verification_error
    if create_result is None or create_result.returncode != 0:
        raise ReleaseBackupError("temporary restore database creation failed")
    if restore_result is None or restore_result.returncode != 0:
        raise ReleaseBackupError("database backup restore verification failed")
    if cleanup_result is None or cleanup_result.returncode != 0:
        raise ReleaseBackupError("temporary restore database cleanup failed")

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
        "migrations": migration_inventory(
            spec,
            root_dir,
            trusted_root=trusted_root,
        ),
    }
    temporary_manifest = backup_dir / ".manifest.json.tmp"
    manifest_text = (
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )
    file_descriptor = os.open(
        temporary_manifest,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        0o600,
    )
    with os.fdopen(file_descriptor, "w", encoding="utf-8") as handle:
        handle.write(manifest_text)
        handle.flush()
        os.fsync(handle.fileno())
    temporary_manifest.replace(manifest_path)
    directory_descriptor = os.open(backup_dir, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory_descriptor)
    finally:
        os.close(directory_descriptor)
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
    trusted_root: Path = _DEFAULT_TRUSTED_ROOT,
) -> dict[str, Any]:
    manifest_path = _validate_backup_path(manifest_path, trusted_root)
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
    validate_hxy_boundary(root_dir, identity, trusted_root=trusted_root)
    if manifest.get("database") != identity:
        raise ReleaseBackupError("backup database does not match release target")
    expected_commit = git_commit or _current_git_commit(root_dir)
    if manifest.get("git_commit") != expected_commit:
        raise ReleaseBackupError("backup Git commit does not match release source")
    if manifest.get("migrations") != migration_inventory(
        spec,
        root_dir,
        trusted_root=trusted_root,
    ):
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
    trusted_root: Path = _DEFAULT_TRUSTED_ROOT,
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
        trusted_root=trusted_root,
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

    try:
        postflight = postflight_inspector(root_dir, database_url)
    except Exception as exc:
        raise ReleasePostflightError(
            {"status": "failed", "error": type(exc).__name__}
        ) from exc
    if postflight.get("status") != "passed":
        raise ReleasePostflightError(postflight)
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
