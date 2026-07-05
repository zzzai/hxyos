#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from hxy_knowledge.loop_engine import validate_p0_reviewed_answer_cards_import_gate  # noqa: E402


def _load_json(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _load_items(path: Path) -> list[dict]:
    payload = _load_json(path)
    items = payload.get("items")
    return items if isinstance(items, list) else []


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Gate HXY P0 reviewed answer cards before formal import.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    gate_parser = subparsers.add_parser("gate", help="Validate reviewed answer cards and detect conflicts only.")
    gate_parser.add_argument("--reviewed", required=True, help="Path to published-answer-cards.reviewed.json.")
    gate_parser.add_argument("--existing", required=True, help="Path to existing answer cards JSON with an items array.")
    gate_parser.add_argument("--output", required=True, help="Path to write import gate report JSON.")
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    if args.command == "gate":
        reviewed_path = Path(args.reviewed)
        existing_path = Path(args.existing)
        output_path = Path(args.output)
        report = validate_p0_reviewed_answer_cards_import_gate(_load_json(reviewed_path), _load_items(existing_path))
        _write_json(output_path, report)
        print(
            json.dumps(
                {
                    "version": "hxy-p0-reviewed-answer-cards-import-cli.v1",
                    "command": "gate",
                    "valid": report["valid"],
                    "gate_path": str(output_path),
                    "importable_count": report["importable_count"],
                    "conflict_count": report["conflict_count"],
                    "error_count": report["error_count"],
                    "would_import_count": report["would_import_count"],
                    "write_to_database": report["write_to_database"],
                },
                ensure_ascii=False,
            )
        )
        return 0 if report["valid"] else 1

    parser.error(f"unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
