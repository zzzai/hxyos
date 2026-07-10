from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row


ACTIVATION_MIGRATIONS = (
    "009_hxy_product_identity.sql",
    "010_hxy_product_conversations.sql",
    "011_hxy_product_materials.sql",
    "012_hxy_assignment_sessions.sql",
    "013_hxy_material_intake_jobs.sql",
    "014_hxy_knowledge_activation.sql",
)
APPLY_CONFIRMATION = "APPLY-HXY-009-014"
BACKUP_VERSION = "hxy-activation-backup.v1"

_MAX_RESULT_STRING = 500
_BASELINE_TABLES = ("staff_accounts", "stores")
_ACTIVATION_TABLES = (
    "hxy_organizations",
    "hxy_role_assignments",
    "hxy_assignment_sessions",
    "hxy_product_conversations",
    "hxy_product_messages",
    "hxy_product_materials",
    "hxy_material_parser_jobs",
    "hxy_material_artifacts",
    "hxy_material_chunks",
    "hxy_product_answer_traces",
)

ConnectFactory = Callable[[str], Any]
CommandRunner = Callable[[list[str], dict[str, str]], subprocess.CompletedProcess[str]]
InspectionRunner = Callable[[Path, str], dict[str, Any]]


class ReleaseBoundaryError(ValueError):
    """Raised when a release target is outside the HXY boundary."""


class ReleaseBackupError(RuntimeError):
    """Raised when a release backup is missing, stale or unverifiable."""


class ReleaseAuthorizationError(RuntimeError):
    """Raised when a mutating release command lacks explicit authorization."""


class ReleaseExecutionError(RuntimeError):
    """Raised when a guarded external release command fails."""


def migration_inventory(root_dir: Path) -> list[dict[str, str]]:
    migration_dir = root_dir.resolve() / "data" / "migrations"
    inventory: list[dict[str, str]] = []
    for name in ACTIVATION_MIGRATIONS:
        path = migration_dir / name
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        inventory.append({"name": name, "sha256": digest})
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


def render_result(payload: dict[str, Any], *, sensitive_values: Iterable[str] = ()) -> str:
    redacted = _bounded_value(payload, tuple(sensitive_values))
    return json.dumps(redacted, ensure_ascii=False, sort_keys=True)


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
        if phase == "postflight":
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
                (list(_ACTIVATION_TABLES),),
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
                (list(_ACTIVATION_TABLES),),
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
        checks.extend(_postflight_checks(pending_tables, constraints, indexes))

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


def _database_sensitive_values(database_url: str) -> tuple[str, ...]:
    values = conninfo_to_dict(database_url)
    return tuple(
        value
        for value in (database_url, str(values.get("password") or ""))
        if value
    )


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


def create_backup(
    root_dir: Path,
    database_url: str,
    *,
    output_root: Path,
    runner: CommandRunner | None = None,
    now: datetime | None = None,
    git_commit: str | None = None,
    preflight_runner: InspectionRunner = run_preflight,
) -> dict[str, Any]:
    identity = database_identity(database_url)
    validate_hxy_boundary(root_dir, identity)
    preflight = preflight_runner(root_dir, database_url)
    if preflight.get("status") != "passed":
        raise ReleaseBackupError("preflight must pass before backup")

    created_at = now or _utc_now()
    timestamp = created_at.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_dir = output_root.resolve() / timestamp
    if backup_dir.exists():
        raise ReleaseBackupError("backup target already exists")
    backup_dir.mkdir(parents=True, mode=0o700)
    backup_dir.chmod(0o700)
    dump_path = backup_dir / "hxy-before-activation.dump"
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
    if dump_result.returncode != 0 or not dump_path.is_file() or dump_path.stat().st_size <= 0:
        raise ReleaseBackupError("database backup failed")
    dump_path.chmod(0o600)

    restore_result = command_runner(
        ["pg_restore", "--list", str(dump_path)],
        command_env,
    )
    if restore_result.returncode != 0:
        raise ReleaseBackupError("database backup verification failed")

    manifest = {
        "version": BACKUP_VERSION,
        "created_at": _iso_utc(created_at),
        "database": identity,
        "git_commit": git_commit or _current_git_commit(root_dir),
        "release": "009-014",
        "dump": {
            "file": dump_path.name,
            "size_bytes": dump_path.stat().st_size,
            "sha256": _sha256_file(dump_path),
            "verified": True,
        },
        "migrations": migration_inventory(root_dir),
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
        "database": identity,
        "manifest_path": str(manifest_path),
        "dump_size_bytes": manifest["dump"]["size_bytes"],
        "migration_count": len(manifest["migrations"]),
    }


def validate_backup_manifest(
    root_dir: Path,
    database_url: str,
    manifest_path: Path,
    *,
    now: datetime | None = None,
    max_age: timedelta = timedelta(hours=24),
) -> dict[str, Any]:
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ReleaseBackupError("backup manifest is unreadable") from exc
    if not isinstance(manifest, dict) or manifest.get("version") != BACKUP_VERSION:
        raise ReleaseBackupError("backup manifest version is invalid")

    identity = database_identity(database_url)
    validate_hxy_boundary(root_dir, identity)
    if manifest.get("database") != identity:
        raise ReleaseBackupError("backup database does not match release target")
    if manifest.get("migrations") != migration_inventory(root_dir):
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
    if not dump_name or Path(dump_name).name != dump_name:
        raise ReleaseBackupError("backup dump path is invalid")
    dump_path = manifest_path.resolve().parent / dump_name
    if not dump_path.is_file():
        raise ReleaseBackupError("backup dump is missing")
    if dump_path.stat().st_size != int(dump.get("size_bytes") or -1):
        raise ReleaseBackupError("backup dump size does not match manifest")
    if _sha256_file(dump_path) != str(dump.get("sha256") or ""):
        raise ReleaseBackupError("backup dump checksum does not match manifest")
    return {
        "status": "passed",
        "phase": "backup_validation",
        "database": identity,
        "manifest_path": str(manifest_path.resolve()),
        "dump_path": str(dump_path),
        "created_at": _iso_utc(created_at),
    }


def apply_activation_migrations(
    root_dir: Path,
    database_url: str,
    *,
    manifest_path: Path,
    confirmation: str,
    runner: CommandRunner | None = None,
    now: datetime | None = None,
    postflight_runner: InspectionRunner = run_postflight,
) -> dict[str, Any]:
    if confirmation != APPLY_CONFIRMATION:
        raise ReleaseAuthorizationError("exact migration confirmation is required")
    validated_backup = validate_backup_manifest(
        root_dir,
        database_url,
        manifest_path,
        now=now,
    )
    command = [
        "psql",
        "--no-psqlrc",
        "--set",
        "ON_ERROR_STOP=1",
        "--single-transaction",
        "--command",
        (
            "SELECT pg_advisory_xact_lock("
            "hashtext('hxy-knowledge-activation-009-014')"
            ")"
        ),
    ]
    for migration in ACTIVATION_MIGRATIONS:
        command.extend(["--file", str(root_dir.resolve() / "data" / "migrations" / migration)])
    command_runner = runner or _default_command_runner
    result = command_runner(command, _postgres_environment(database_url))
    if result.returncode != 0:
        raise ReleaseExecutionError("activation migration transaction failed")

    postflight = postflight_runner(root_dir, database_url)
    if postflight.get("status") != "passed":
        raise ReleaseExecutionError("activation postflight failed")
    return {
        "status": "passed",
        "phase": "apply",
        "database": database_identity(database_url),
        "migration_count": len(ACTIVATION_MIGRATIONS),
        "backup_created_at": validated_backup["created_at"],
        "postflight": "passed",
    }


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
            output_root = args.output_root or (
                args.root_dir / "data" / "backups" / "knowledge-activation"
            )
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
