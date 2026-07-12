from __future__ import annotations

import hashlib
import json
import os
import secrets
import shutil
import stat
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

import psycopg
from psycopg import ProgrammingError, pq
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row


_MAX_RESULT_STRING = 500
_DEFAULT_TRUSTED_ROOT = Path("/root/hxy")
_CONNINFO_ENVIRONMENT = {
    item.keyword.decode(): item.envvar.decode()
    for item in pq.Conninfo.get_defaults()
    if item.envvar is not None
}
_LIBPQ_PROCESS_ENVIRONMENT = frozenset(_CONNINFO_ENVIRONMENT.values()) | {
    "PGKEEPALIVES",
    "PGKEEPALIVESCOUNT",
    "PGKEEPALIVESIDLE",
    "PGKEEPALIVESINTERVAL",
    "PGREPLICATION",
    "PGSERVICEFILE",
    "PGSSLPASSWORD",
    "PGSYSCONFDIR",
    "PGTCPUSER_TIMEOUT",
}

CommandRunner = Callable[[list[str], dict[str, str]], subprocess.CompletedProcess[str]]
InspectionRunner = Callable[[Path, str], dict[str, Any]]
MigrationLoader = Callable[[Path, str], bytes]
InstanceInspector = Callable[[str], dict[str, str]]


@dataclass(frozen=True)
class MigrationReleaseSpec:
    release_id: str
    manifest_version: str
    migrations: tuple[str, ...]
    confirmation: str
    advisory_lock: str
    dump_filename: str
    legacy_release: str | None = None


class ReleaseBoundaryError(ValueError):
    """Raised when a release target is outside the HXY boundary."""


class ReleaseBackupError(RuntimeError):
    """Raised when a release backup is missing, stale or unverifiable."""


class ReleaseAuthorizationError(RuntimeError):
    """Raised when a mutating release command lacks explicit authorization."""


class ReleaseExecutionError(RuntimeError):
    """Raised when a guarded external release command fails."""


class ReleaseInstanceError(ReleaseBackupError, ReleaseExecutionError):
    """Raised when a release moves between PostgreSQL server instances."""

    def __init__(self, message: str, *, applied: bool = False) -> None:
        super().__init__(message)
        self.applied = applied


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
    migration_loader: MigrationLoader | None = None,
) -> list[dict[str, str]]:
    blobs = _load_migration_blobs(
        spec,
        root_dir,
        trusted_root=trusted_root,
        migration_loader=migration_loader,
    )
    return _migration_inventory_from_blobs(spec, blobs)


def _migration_inventory_from_blobs(
    spec: MigrationReleaseSpec,
    blobs: dict[str, bytes],
) -> list[dict[str, str]]:
    return [
        {"name": name, "sha256": hashlib.sha256(blobs[name]).hexdigest()}
        for name in spec.migrations
    ]


def _load_migration_blobs(
    spec: MigrationReleaseSpec,
    root_dir: Path,
    *,
    trusted_root: Path,
    migration_loader: MigrationLoader | None,
) -> dict[str, bytes]:
    release_root = _validate_release_root(root_dir, trusted_root)
    for name in spec.migrations:
        if not name or Path(name).name != name:
            raise ReleaseBoundaryError("migration path must be a filename")
    if migration_loader is None:
        paths = _migration_paths(spec, release_root, trusted_root=trusted_root)
        return {
            name: path.read_bytes()
            for name, path in zip(spec.migrations, paths, strict=True)
        }
    blobs: dict[str, bytes] = {}
    for name in spec.migrations:
        try:
            blob = migration_loader(release_root, name)
        except ReleaseBoundaryError:
            raise
        except Exception as exc:
            raise ReleaseBoundaryError("migration loader failed for release source") from exc
        if not isinstance(blob, bytes) or not blob:
            raise ReleaseBoundaryError("migration loader must return non-empty bytes")
        blobs[name] = blob
    return blobs


def git_head_migration_loader(root_dir: Path, name: str) -> bytes:
    if not name or Path(name).name != name:
        raise ReleaseBoundaryError("migration path must be a filename")
    result = subprocess.run(
        ["git", "-C", str(root_dir.resolve()), "show", f"HEAD:data/migrations/{name}"],
        check=False,
        capture_output=True,
    )
    if result.returncode != 0 or not result.stdout:
        raise ReleaseBoundaryError("migration is unavailable from Git HEAD")
    return bytes(result.stdout)


def _migration_paths(
    spec: MigrationReleaseSpec,
    root_dir: Path,
    *,
    trusted_root: Path,
) -> tuple[Path, ...]:
    release_root = _validate_release_root(root_dir, trusted_root)
    migration_dir = release_root / "data" / "migrations"
    try:
        resolved_migration_dir = migration_dir.resolve(strict=True)
    except OSError as exc:
        raise ReleaseBoundaryError(
            "migration directory must be a real directory within release root"
        ) from exc
    if (
        migration_dir.is_symlink()
        or resolved_migration_dir != migration_dir
        or not resolved_migration_dir.is_dir()
    ):
        raise ReleaseBoundaryError(
            "migration directory must be a real directory within release root"
        )

    paths: list[Path] = []
    for name in spec.migrations:
        if not name or Path(name).name != name:
            raise ReleaseBoundaryError("migration path must be a filename")
        path = migration_dir / name
        if path.is_symlink():
            raise ReleaseBoundaryError(
                "migration must be a real regular file within release root"
            )
        try:
            metadata = path.stat(follow_symlinks=False)
            resolved = path.resolve(strict=True)
        except OSError as exc:
            raise ReleaseBoundaryError(
                "migration must be a real regular file within release root"
            ) from exc
        if (
            not stat.S_ISREG(metadata.st_mode)
            or resolved.parent != resolved_migration_dir
        ):
            raise ReleaseBoundaryError(
                "migration must be a real regular file within release root"
            )
        paths.append(resolved)
    return tuple(paths)


def _reject_implicit_libpq_environment() -> None:
    present = sorted(
        key
        for key in os.environ
        if key in _LIBPQ_PROCESS_ENVIRONMENT or key.startswith("PGSSL")
    )
    if present:
        raise ReleaseExecutionError(
            "libpq process environment is not allowed: " + ", ".join(present)
        )


def _validated_conninfo(database_url: str) -> dict[str, str]:
    _reject_implicit_libpq_environment()
    try:
        values = conninfo_to_dict(database_url)
    except ProgrammingError as exc:
        raise ReleaseExecutionError(
            "database DSN is invalid; service and servicefile are not allowed"
        ) from exc
    if values.get("service") or values.get("servicefile"):
        raise ReleaseExecutionError(
            "database DSN service or servicefile configuration is not allowed"
        )
    if values.get("options"):
        raise ReleaseExecutionError("database DSN options are not allowed")
    for key in ("host", "hostaddr", "port"):
        if "," in str(values.get(key) or ""):
            raise ReleaseExecutionError(
                f"database DSN requires a single {key} target"
            )
    load_balance_hosts = str(values.get("load_balance_hosts") or "disable").lower()
    if load_balance_hosts != "disable":
        raise ReleaseExecutionError(
            "database DSN load_balance_hosts must be disable"
        )
    missing = [
        key
        for key in ("host", "port", "dbname", "user")
        if not values.get(key)
    ]
    if missing:
        raise ReleaseExecutionError(
            "database DSN requires explicit target parameters: " + ", ".join(missing)
        )
    if not values.get("password") and not values.get("passfile"):
        raise ReleaseExecutionError(
            "database DSN requires explicit password or passfile authentication"
        )
    return values


def database_identity(database_url: str) -> dict[str, str]:
    values = _validated_conninfo(database_url)
    return {
        "host": str(values.get("host") or ""),
        "port": str(values.get("port") or "5432"),
        "database": str(values.get("dbname") or ""),
        "user": str(values.get("user") or ""),
    }


def _connection_fingerprint(database_url: str) -> str:
    values = _validated_conninfo(database_url)
    normalized = {
        key: str(value)
        for key, value in values.items()
        if value not in (None, "") and key not in {"password", "sslpassword"}
    }
    encoded = json.dumps(
        normalized,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def database_instance_identity(database_url: str) -> dict[str, str]:
    expected = database_identity(database_url)
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        connection.read_only = True
        row = connection.execute(
            """
            /* hxy_release:instance_identity */
            SELECT CASE
                     WHEN has_function_privilege('pg_control_system()', 'EXECUTE')
                     THEN (pg_control_system()).system_identifier::text
                     ELSE NULL
                   END AS system_identifier,
                   inet_server_addr()::text AS server_addr,
                   inet_server_port()::text AS server_port,
                   current_database() AS database,
                   (current_setting('server_version_num')::integer / 10000)::text
                     AS server_major
            """
        ).fetchone()
    identity = {
        key: str((row or {}).get(key) or "")
        for key in (
            "system_identifier",
            "server_addr",
            "server_port",
            "database",
            "server_major",
        )
    }
    if identity["database"] != expected["database"]:
        raise ReleaseInstanceError("database instance identity has wrong database")
    if not identity["server_addr"] or not identity["server_port"]:
        raise ReleaseInstanceError(
            "database instance identity requires server address and port"
        )
    return identity


def _instance_fingerprint(identity: dict[str, str]) -> str:
    normalized = {
        key: str(identity.get(key) or "")
        for key in (
            "system_identifier",
            "server_addr",
            "server_port",
            "database",
            "server_major",
        )
    }
    if not all(normalized[key] for key in ("server_addr", "server_port", "database", "server_major")):
        raise ReleaseInstanceError("database instance identity is incomplete")
    encoded = json.dumps(
        normalized,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _assert_instance_fingerprint(
    expected: str,
    actual: dict[str, str],
    *,
    phase: str,
    applied: bool = False,
) -> None:
    if _instance_fingerprint(actual) != expected:
        raise ReleaseInstanceError(
            f"database instance changed {phase}",
            applied=applied,
        )


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


def _postgres_environment(
    database_url: str,
    *,
    server_addr: str,
) -> dict[str, str]:
    values = _validated_conninfo(database_url)
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
    env["PGHOSTADDR"] = server_addr
    env["PGOPTIONS"] = "-c search_path=public,pg_catalog"
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
    migration_loader: MigrationLoader | None = None,
    instance_inspector: InstanceInspector | None = None,
) -> dict[str, Any]:
    identity = database_identity(database_url)
    validate_hxy_boundary(root_dir, identity, trusted_root=trusted_root)
    output_root = _validate_backup_path(output_root, trusted_root)
    if not spec.dump_filename or Path(spec.dump_filename).name != spec.dump_filename:
        raise ReleaseBoundaryError("backup dump path must be a filename")
    migration_blobs = _load_migration_blobs(
        spec,
        root_dir,
        trusted_root=trusted_root,
        migration_loader=migration_loader,
    )
    inspect_instance = instance_inspector or database_instance_identity
    instance_before = inspect_instance(database_url)
    instance_fingerprint = _instance_fingerprint(instance_before)
    command_env = _postgres_environment(
        database_url,
        server_addr=instance_before["server_addr"],
    )
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

    instance_after_dump = inspect_instance(database_url)
    _assert_instance_fingerprint(
        instance_fingerprint,
        instance_after_dump,
        phase="during backup",
    )

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
        "connection_fingerprint": _connection_fingerprint(database_url),
        "instance_fingerprint": instance_fingerprint,
        "dump": {
            "file": dump_path.name,
            "size_bytes": dump_path.stat().st_size,
            "sha256": _sha256_file(dump_path),
            "verified": True,
        },
        "migrations": _migration_inventory_from_blobs(spec, migration_blobs),
    }
    if spec.legacy_release is not None:
        manifest["release"] = spec.legacy_release
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
    migration_loader: MigrationLoader | None = None,
    instance_inspector: InstanceInspector | None = None,
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
    if (
        spec.legacy_release is not None
        and manifest.get("release") != spec.legacy_release
    ):
        raise ReleaseBackupError(
            "backup manifest legacy release does not match specification"
        )

    identity = database_identity(database_url)
    validate_hxy_boundary(root_dir, identity, trusted_root=trusted_root)
    if manifest.get("database") != identity:
        raise ReleaseBackupError("backup database does not match release target")
    fingerprint = _connection_fingerprint(database_url)
    if manifest.get("connection_fingerprint") != fingerprint:
        raise ReleaseBackupError(
            "backup connection fingerprint does not match release target"
        )
    inspect_instance = instance_inspector or database_instance_identity
    instance = inspect_instance(database_url)
    instance_fingerprint = str(manifest.get("instance_fingerprint") or "")
    if not instance_fingerprint:
        raise ReleaseBackupError("backup instance fingerprint is missing")
    _assert_instance_fingerprint(
        instance_fingerprint,
        instance,
        phase="before release validation",
    )
    expected_commit = git_commit or _current_git_commit(root_dir)
    if manifest.get("git_commit") != expected_commit:
        raise ReleaseBackupError("backup Git commit does not match release source")
    if manifest.get("migrations") != migration_inventory(
        spec,
        root_dir,
        trusted_root=trusted_root,
        migration_loader=migration_loader,
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
        "connection_fingerprint": fingerprint,
        "instance_fingerprint": instance_fingerprint,
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
    migration_loader: MigrationLoader | None = None,
    instance_inspector: InstanceInspector | None = None,
) -> dict[str, Any]:
    if confirmation != spec.confirmation:
        raise ReleaseAuthorizationError("exact migration confirmation is required")
    migration_blobs = _load_migration_blobs(
        spec,
        root_dir,
        trusted_root=trusted_root,
        migration_loader=migration_loader,
    )

    def verified_loader(_root: Path, name: str) -> bytes:
        return migration_blobs[name]

    inspect_instance = instance_inspector or database_instance_identity
    validated_backup = validate_release_backup_manifest(
        spec,
        root_dir,
        database_url,
        manifest_path,
        now=now,
        git_commit=git_commit,
        trusted_root=trusted_root,
        migration_loader=verified_loader,
        instance_inspector=inspect_instance,
    )
    instance_before = inspect_instance(database_url)
    _assert_instance_fingerprint(
        str(validated_backup["instance_fingerprint"]),
        instance_before,
        phase="before migration apply",
    )
    command_runner = runner or _default_command_runner
    command_env = _postgres_environment(
        database_url,
        server_addr=instance_before["server_addr"],
    )
    release_root = _validate_release_root(root_dir, trusted_root)
    temporary_root = release_root / "data" / "release-tmp"
    if temporary_root.is_symlink():
        raise ReleaseBoundaryError("release temporary root must be a real directory")
    temporary_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary_root.chmod(0o700)
    snapshot_dir = Path(
        tempfile.mkdtemp(prefix=f"{spec.release_id}-", dir=temporary_root)
    )
    snapshot_dir.chmod(0o700)
    try:
        migration_paths: list[Path] = []
        for name in spec.migrations:
            snapshot_path = snapshot_dir / name
            descriptor = os.open(
                snapshot_path,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
            )
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(migration_blobs[name])
                handle.flush()
                os.fsync(handle.fileno())
            migration_paths.append(snapshot_path)

        restore_result = command_runner(
            ["pg_restore", "--list", str(validated_backup["dump_path"])],
            command_env,
        )
        if restore_result.returncode != 0:
            raise ReleaseBackupError(
                "database backup verification failed before migration"
            )

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
        for migration_path in migration_paths:
            command.extend(["--file", str(migration_path)])
        result = command_runner(command, command_env)
        if result.returncode != 0:
            raise ReleaseExecutionError("release migration transaction failed")

        instance_after_apply = inspect_instance(database_url)
        _assert_instance_fingerprint(
            str(validated_backup["instance_fingerprint"]),
            instance_after_apply,
            phase="during migration apply",
            applied=True,
        )

        postflight_error: Exception | None = None
        try:
            postflight = postflight_inspector(root_dir, database_url)
        except Exception as exc:
            postflight_error = exc
            postflight = {"status": "failed", "error": type(exc).__name__}

        instance_after_postflight = inspect_instance(database_url)
        _assert_instance_fingerprint(
            str(validated_backup["instance_fingerprint"]),
            instance_after_postflight,
            phase="during postflight",
            applied=True,
        )
        if postflight_error is not None:
            raise ReleasePostflightError(postflight) from postflight_error
        if postflight.get("status") != "passed":
            raise ReleasePostflightError(postflight)
    finally:
        shutil.rmtree(snapshot_dir)
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
