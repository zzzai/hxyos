from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from psycopg.conninfo import conninfo_to_dict


ACTIVATION_MIGRATIONS = (
    "009_hxy_product_identity.sql",
    "010_hxy_product_conversations.sql",
    "011_hxy_product_materials.sql",
    "012_hxy_assignment_sessions.sql",
    "013_hxy_material_intake_jobs.sql",
    "014_hxy_knowledge_activation.sql",
)

_MAX_RESULT_STRING = 500


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
    print(render_result({"status": "not_implemented", "command": args.command}))
    return 2

