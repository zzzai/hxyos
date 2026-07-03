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

from hxy_knowledge.ingest_loop import run_ingest_loop


def main() -> int:
    parser = argparse.ArgumentParser(description="Run HXY ingest loop to human review state.")
    parser.add_argument("--raw-dir", default="knowledge/raw/inbox")
    parser.add_argument("--wiki-dir", default="knowledge/wiki")
    parser.add_argument("--report", default="knowledge/reports/ingest-latest.json")
    parser.add_argument("--runs-dir", default="knowledge/runs")
    parser.add_argument("--run-id", default="ingest-loop-latest")
    parser.add_argument("--root-dir", default=".")
    args = parser.parse_args()

    root_dir = Path(args.root_dir).resolve()
    state = run_ingest_loop(
        raw_dir=Path(args.raw_dir),
        wiki_dir=Path(args.wiki_dir),
        report_path=Path(args.report),
        runs_dir=Path(args.runs_dir),
        run_id=args.run_id,
        root_dir=root_dir,
    )
    print(json.dumps(state, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
