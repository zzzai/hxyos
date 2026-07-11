#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
for import_root in (ROOT, ROOT / "apps" / "api"):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from apps.api.hxy_engines.benchmark_runner import (  # noqa: E402
    CurrentContractBaselineExecutor,
    run_contract_baseline,
)


VALIDATOR_PATH = ROOT / "scripts" / "validate-hxy-engine-benchmark.py"


def _validate_complete_corpus(path: Path) -> list[str]:
    spec = importlib.util.spec_from_file_location(
        "hxy_engine_benchmark_validator",
        VALIDATOR_PATH,
    )
    if spec is None or spec.loader is None:
        return ["unable to load benchmark validator"]
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    report = module.validate_benchmark_file(path, require_complete=True)
    return list(report.get("errors") or [])


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the HXYOS engine benchmark")
    parser.add_argument("--benchmark", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--mode", choices=("contract",), default="contract")
    args = parser.parse_args()

    corpus_errors = _validate_complete_corpus(args.benchmark)
    if corpus_errors:
        print("; ".join(corpus_errors), file=sys.stderr)
        return 2
    benchmark = json.loads(args.benchmark.read_text(encoding="utf-8"))
    report = run_contract_baseline(benchmark, CurrentContractBaselineExecutor())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    summary = {
        "version": "hxy-engine-benchmark-cli.v1",
        "mode": report["mode"],
        "report_path": str(args.output),
        "case_count": report["case_count"],
        "contract_pass_count": report["contract_pass_count"],
        "semantic_status": report["semantic_status"],
    }
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0 if report["contract_fail_count"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
