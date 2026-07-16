#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from hxy_knowledge.authority_canary import capture_core_10_runs, run_model_route_canary  # noqa: E402
from hxy_knowledge.brain_benchmark import build_core_10_report, load_benchmark  # noqa: E402
from hxy_knowledge.model_router import ModelRouter  # noqa: E402


def _write_json(path: str, payload: dict[str, Any]) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _api_answer_client(base_url: str, api_token: str):
    try:
        import httpx
    except ImportError as exc:  # pragma: no cover - runtime dependency guard
        raise RuntimeError("httpx is required for the API canary") from exc
    client = httpx.Client(base_url=base_url.rstrip("/"), timeout=60)

    def request(case: dict[str, Any]) -> dict[str, Any]:
        response = client.post(
            "/api/knowledge/chat",
            headers={"Authorization": f"Bearer {api_token}"},
            json={"question": str(case.get("question") or ""), "scenario": "HXYOS Core-10 canary"},
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("knowledge chat returned a non-object response")
        return payload

    return request


def main() -> int:
    parser = argparse.ArgumentParser(description="Run bounded HXYOS authority-answer canaries.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    models = subparsers.add_parser("models")
    models.add_argument("--output", required=True)
    core = subparsers.add_parser("core-10")
    core.add_argument("--base-url", default="http://127.0.0.1:28081")
    core.add_argument("--runs-output", required=True)
    core.add_argument("--report-output", required=True)
    args = parser.parse_args()

    if args.command == "models":
        report = run_model_route_canary(ModelRouter())
        _write_json(args.output, report)
        print(json.dumps({
            "version": report["version"],
            "target_met": report["target_met"],
            "content_persisted": report["content_persisted"],
        }, ensure_ascii=False))
        return 0 if report["target_met"] else 1

    api_token = os.getenv("HXY_API_TOKEN", "").strip()
    if not api_token:
        parser.error("HXY_API_TOKEN is required for core-10")
    benchmark = load_benchmark(ROOT / "knowledge" / "benchmarks" / "hxyos-core-10.json")
    capture = capture_core_10_runs(benchmark, _api_answer_client(args.base_url, api_token))
    report = build_core_10_report(
        benchmark,
        capture["runs"],
        benchmark_kind="captured_product_answers",
    )
    _write_json(args.runs_output, capture)
    _write_json(args.report_output, report)
    print(json.dumps({
        "version": "hxy-authority-canary-cli.v1",
        "benchmark_kind": report["benchmark_kind"],
        "pass_rate": report["pass_rate"],
        "target_met": report["target_met"],
        "authority_leakage_failures": report["authority_leakage_failures"],
        "high_risk_interception_rate": report["high_risk_interception_rate"],
        "content_persisted": capture["content_persisted"],
    }, ensure_ascii=False))
    return 0 if report["target_met"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
