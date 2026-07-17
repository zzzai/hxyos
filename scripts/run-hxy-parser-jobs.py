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

from hxy_knowledge.parser_adapter import run_parser_jobs  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run HXY parser jobs from an ingest loop state file.")
    parser.add_argument("--state", default="knowledge/runs/ingest-loop-latest/loop-state.json")
    parser.add_argument("--output-dir", default="knowledge/raw/inbox/extracted-reference")
    parser.add_argument("--root-dir", default=".")
    parser.add_argument("--strategy", action="append")
    parser.add_argument("--timeout-seconds", type=int, default=120)
    args = parser.parse_args()

    root_dir = Path(args.root_dir).resolve()
    state_path = (root_dir / args.state).resolve()
    state = json.loads(state_path.read_text(encoding="utf-8"))
    parser_jobs = state.get("parser_jobs") if isinstance(state.get("parser_jobs"), list) else []
    result = run_parser_jobs(
        parser_jobs,
        root_dir=root_dir,
        output_dir=(root_dir / args.output_dir).resolve(),
        strategies=set(args.strategy) if args.strategy else None,
        timeout_seconds=args.timeout_seconds,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
