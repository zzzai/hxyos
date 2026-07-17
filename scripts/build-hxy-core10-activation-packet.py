#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from hxy_knowledge.brand_constitution import BrandConstitutionAdapter  # noqa: E402
from hxy_knowledge.core10_activation import (  # noqa: E402
    build_core10_activation_packet,
    write_core10_activation_artifacts,
)
from hxy_knowledge.repository import KnowledgeRepository  # noqa: E402


_SELECTION_KEYS = {
    "constitution_draft_path",
    "product_asset_ids",
    "operations_asset_ids",
    "reception_draft_path",
}
_ENV_NAME_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
_MAX_JSON_BYTES = 16 * 1024 * 1024


class PrivateInputError(ValueError):
    pass


class DatabaseConfigurationError(ValueError):
    pass


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a read-only HXY Core-10 founder activation packet.",
    )
    parser.add_argument("--report", required=True)
    parser.add_argument("--selection", required=True)
    parser.add_argument(
        "--output-root",
        default="data/private/core10-activation",
    )
    parser.add_argument(
        "--database-url-env",
        default="HXY_DATABASE_URL",
    )
    return parser


def _lexical_path(value: str) -> Path:
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = ROOT / candidate
    return Path(os.path.abspath(candidate))


def _path_has_symlink(candidate: Path, boundary: Path) -> bool:
    current = candidate
    while True:
        if current.is_symlink():
            return True
        if current == boundary or current.parent == current:
            return False
        current = current.parent


def _is_below(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _private_root() -> Path:
    return (ROOT / "data" / "private").resolve()


def _resolve_input_file(
    value: Any,
    *,
    allowed_roots: tuple[Path, ...],
) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise PrivateInputError("invalid input path")
    lexical = _lexical_path(value.strip())
    project_root = ROOT.resolve()
    if not _is_below(lexical, project_root):
        raise PrivateInputError("input path is outside the project")
    if _path_has_symlink(lexical, project_root):
        raise PrivateInputError("symlink input is not allowed")
    try:
        resolved = lexical.resolve(strict=True)
    except OSError as error:
        raise PrivateInputError("input file is unavailable") from error
    resolved_roots = tuple(root.resolve() for root in allowed_roots)
    if not any(_is_below(resolved, root) for root in resolved_roots):
        raise PrivateInputError("input path is outside its allowlist")
    if not resolved.is_file() or resolved.is_symlink():
        raise PrivateInputError("input must be a regular file")
    return resolved


def _resolve_output_root(value: Any) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise PrivateInputError("invalid output path")
    lexical = _lexical_path(value.strip())
    project_root = ROOT.resolve()
    if not _is_below(lexical, project_root):
        raise PrivateInputError("output path is outside the project")
    if _path_has_symlink(lexical, project_root):
        raise PrivateInputError("symlink output is not allowed")
    resolved = lexical.resolve(strict=False)
    if not _is_below(resolved, _private_root()):
        raise PrivateInputError("output path must remain private")
    return resolved


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        if path.stat().st_size > _MAX_JSON_BYTES:
            raise PrivateInputError("JSON input is too large")
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise PrivateInputError("invalid JSON input") from error
    if not isinstance(payload, dict):
        raise PrivateInputError("JSON input must be an object")
    return payload


def _validate_asset_ids(value: Any) -> list[str]:
    if not isinstance(value, list) or any(
        not isinstance(asset_id, str) or not asset_id.strip()
        for asset_id in value
    ):
        raise PrivateInputError("asset ids must be a string list")
    return [asset_id.strip() for asset_id in value]


def _load_selection(selection_path: Path) -> dict[str, Any]:
    selection = _read_json_object(selection_path)
    if set(selection) != _SELECTION_KEYS:
        raise PrivateInputError("selection fields are invalid")
    private_root = _private_root()
    return {
        "constitution_draft_path": _resolve_input_file(
            selection["constitution_draft_path"],
            allowed_roots=(private_root,),
        ),
        "product_asset_ids": _validate_asset_ids(
            selection["product_asset_ids"],
        ),
        "operations_asset_ids": _validate_asset_ids(
            selection["operations_asset_ids"],
        ),
        "reception_draft_path": _resolve_input_file(
            selection["reception_draft_path"],
            allowed_roots=(private_root,),
        ),
    }


def _constitution_state(adapter: BrandConstitutionAdapter) -> dict[str, Any]:
    loaded = adapter.load_active()
    payload = loaded.payload if isinstance(loaded.payload, dict) else None
    version = payload.get("version") if payload else None
    return {
        "status": "active" if payload is not None else str(loaded.reason),
        "active_version": version if isinstance(version, str) else None,
        "authority_version": 1 if payload is not None else 0,
    }


def _database_url(env_name: str) -> str:
    if not _ENV_NAME_PATTERN.fullmatch(env_name):
        raise DatabaseConfigurationError("invalid database environment name")
    value = os.environ.get(env_name, "").strip()
    if not value:
        raise DatabaseConfigurationError("missing database configuration")
    return value


def _timestamp() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _relative_artifact_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError as error:
        raise PrivateInputError("artifact escaped the project") from error


def _print_summary(
    packet: dict[str, Any],
    artifact_paths: dict[str, Path],
) -> None:
    print(f"packet_id={packet['packet_id']}")
    print(f"item_count={packet['item_count']}")
    print("write_to_database=false")
    print("publish_allowed=false")
    for item in packet["items"]:
        status = (
            "blocked"
            if item.get("blockers")
            else "ready_for_founder_decision"
        )
        print(f"item={item['item_key']} status={status}")
    for key in ("packet_json", "packet_markdown", "decision_sample"):
        print(f"artifact_{key}={_relative_artifact_path(artifact_paths[key])}")


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        private_root = _private_root()
        selection_path = _resolve_input_file(
            args.selection,
            allowed_roots=(private_root,),
        )
        report_path = _resolve_input_file(
            args.report,
            allowed_roots=(
                private_root,
                ROOT / "data" / "releases" / "authority-answer",
            ),
        )
        output_root = _resolve_output_root(args.output_root)
        selection = _load_selection(selection_path)
        report = _read_json_object(report_path)
        constitution_draft = _read_json_object(
            selection["constitution_draft_path"],
        )
        reception_draft = _read_json_object(
            selection["reception_draft_path"],
        )
        database_url = _database_url(args.database_url_env)
    except DatabaseConfigurationError:
        print("error: database configuration is unavailable", file=sys.stderr)
        return 2
    except PrivateInputError:
        print("error: invalid private input", file=sys.stderr)
        return 2

    try:
        snapshot = KnowledgeRepository(database_url).core10_activation_snapshot(
            product_asset_ids=selection["product_asset_ids"],
            operations_asset_ids=selection["operations_asset_ids"],
        )
        packet = build_core10_activation_packet(
            report=report,
            constitution_state=_constitution_state(
                BrandConstitutionAdapter(ROOT),
            ),
            constitution_draft=constitution_draft,
            product_sources=snapshot["product_sources"],
            operations_sources=snapshot["operations_sources"],
            reception_draft=reception_draft,
            existing_answer_cards=snapshot["approved_answer_cards"],
            generated_at=_timestamp(),
        )
        artifact_paths = write_core10_activation_artifacts(
            output_root,
            packet,
        )
        _print_summary(packet, artifact_paths)
    except Exception:  # Fail closed without echoing private data or connection errors.
        print("error: core10 activation packet build failed", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
