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

from hxy_knowledge.knowledge_compiler import compile_directory  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Compile HXY raw materials into governed wiki artifacts.")
    parser.add_argument("--raw-dir", required=True, help="Directory containing raw .md/.txt HXY materials.")
    parser.add_argument("--wiki-dir", required=True, help="Directory for compiled wiki artifacts.")
    parser.add_argument("--report", required=True, help="Path to compiler report JSON.")
    parser.add_argument("--run-id", default="", help="Optional HXY Harness run id.")
    parser.add_argument("--runs-dir", default="", help="Optional directory for HXY Harness run artifacts.")
    args = parser.parse_args()

    report = compile_directory(args.raw_dir, args.wiki_dir)
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    public_report = {key: value for key, value in report.items() if key != "artifacts"}
    report_path.write_text(json.dumps(public_report, ensure_ascii=False, indent=2), encoding="utf-8")
    response = {"version": "hxy-knowledge-compiler-cli.v1", "report_path": str(report_path)}
    if args.run_id:
        from hxy_knowledge.knowledge_compiler import write_harness_run

        runs_dir = args.runs_dir or str(ROOT / "knowledge" / "runs")
        final_report = write_harness_run(run_id=args.run_id, runs_dir=runs_dir, raw_dir=args.raw_dir, report=report)
        response["run_id"] = args.run_id
        response["run_status"] = final_report["state"]["status"]
        response["run_path"] = str(Path(runs_dir) / args.run_id)
    print(json.dumps(response, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
