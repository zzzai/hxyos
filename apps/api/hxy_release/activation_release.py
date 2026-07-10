from __future__ import annotations

import argparse
import hashlib
import json
import os
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


class ReleaseBoundaryError(ValueError):
    """Raised when a release target is outside the HXY boundary."""


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


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Guarded HXY knowledge activation release")
    parser.add_argument("--root-dir", type=Path, default=Path.cwd())
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("preflight")
    commands.add_parser("backup")
    commands.add_parser("apply")
    commands.add_parser("postflight")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_argument_parser().parse_args(argv)
    database_url = os.getenv("HXY_DATABASE_URL", "").strip()
    if not database_url:
        print(render_result({"status": "failed", "error": "HXY_DATABASE_URL is required"}))
        return 2
    if args.command == "preflight":
        result = run_preflight(args.root_dir, database_url)
    elif args.command == "postflight":
        result = run_postflight(args.root_dir, database_url)
    else:
        result = {"status": "not_implemented", "command": args.command}
    print(render_result(result, sensitive_values=(database_url,)))
    return 0 if result["status"] == "passed" else 2
