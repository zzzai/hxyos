#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))
REPORTS_ROOT = Path("knowledge/reports")

from hxy_knowledge.enterprise_governance import (  # noqa: E402
    build_enterprise_governance_report,
    build_file_manifest,
    build_governance_run_package,
)
from hxy_knowledge.okf import load_okf_documents  # noqa: E402


def load_json_array(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ["items", "assets", "claims", "evidence", "relations"]:
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def load_structured_inputs(root: Path) -> dict[str, list[dict[str, Any]]]:
    result = {"assets": [], "claims": [], "evidence": [], "relations": [], "answer_cards": []}
    structured_roots = [
        root / "quarantine" / "knowledge-assets" / "structured",
        root / "knowledge" / "structured",
    ]
    for structured_root in structured_roots:
        if not structured_root.exists():
            continue
        result["assets"].extend(load_json_array(structured_root / "assets.json"))
        result["claims"].extend(load_json_array(structured_root / "claims.json"))
        result["evidence"].extend(load_json_array(structured_root / "evidence.json"))
        result["relations"].extend(load_json_array(structured_root / "relations.json"))
        result["answer_cards"].extend(load_json_array(structured_root / "answer-cards.json"))
    return result


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build an auditable HXY enterprise knowledge governance run package.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--run-id", default="")
    parser.add_argument("--previous-manifest", default="")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    run_id = args.run_id.strip() or "current"
    inbox = root / "knowledge" / "raw" / "inbox"
    previous_manifest = (
        json.loads(Path(args.previous_manifest).read_text(encoding="utf-8"))
        if args.previous_manifest
        else {}
    )
    current_manifest = build_file_manifest(
        inbox,
        root_dir=root,
        ignore_globs=["*.tmp", "*.part", ".DS_Store", "~$*"],
    )
    structured = load_structured_inputs(root)
    governance_report = build_enterprise_governance_report(
        assets=[*current_manifest["assets"], *structured["assets"]],
        claims=structured["claims"],
        evidence=structured["evidence"],
        relations=structured["relations"],
        answer_cards=structured["answer_cards"],
        okf_documents=load_okf_documents(root / "knowledge" / "okf"),
    )
    package = build_governance_run_package(
        run_id=run_id,
        previous_manifest=previous_manifest,
        current_manifest=current_manifest,
        governance_report=governance_report,
        relations=structured["relations"],
    )

    paths = package["recommended_persistence"]
    write_json(root / paths["manifest_path"], current_manifest)
    write_json(root / paths["plan_path"], package["incremental_compile_plan"])
    write_json(root / paths["report_path"], governance_report)
    write_json(root / paths["package_path"], package)
    print(
        json.dumps(
            {
                "run_id": run_id,
                "package_path": paths["package_path"],
                "quality_score": package["summary"]["quality_score"],
                "blocking_issues": package["summary"]["blocking_issues"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
