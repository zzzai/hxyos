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

from hxy_knowledge.harness_runner import validate_harness_spec  # noqa: E402


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Run HXY Harness Runner.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate_parser = subparsers.add_parser("validate", help="Validate a harness spec without executing commands.")
    validate_parser.add_argument("--spec", required=True)
    validate_parser.add_argument("--root-dir", default=".")
    args = parser.parse_args()

    if args.command == "validate":
        result = validate_harness_spec(_load_json(Path(args.spec)), root_dir=Path(args.root_dir).resolve())
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["valid"] else 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
