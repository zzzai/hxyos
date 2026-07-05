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

from hxy_knowledge.loop_engine import (  # noqa: E402
    build_p0_reviewer_todo,
    build_p0_review_decisions_audit,
    build_p0_manual_review_packet,
    build_p0_review_decisions_sample,
    initialize_p0_review_decisions_from_sample,
    render_p0_decision_edit_guide_markdown,
    render_p0_manual_review_packet_markdown,
    render_p0_reviewer_worksheet_markdown,
    render_p0_review_decisions_audit_markdown,
    render_p0_review_decisions_validation_markdown,
    validate_p0_review_decisions,
)


def _load_json(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Sample or validate HXY P0 review decisions.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    sample_parser = subparsers.add_parser("sample", help="Create a p0-review-decisions.json sample from a stub.")
    sample_parser.add_argument("--stub", required=True, help="Path to p0-review-decisions.stub.json.")
    sample_parser.add_argument("--output", required=True, help="Path to write p0-review-decisions.sample.json.")

    init_parser = subparsers.add_parser("init-decisions", help="Create a pending-only p0-review-decisions.json from a sample.")
    init_parser.add_argument("--sample", required=True, help="Path to p0-review-decisions.sample.json.")
    init_parser.add_argument("--output", required=True, help="Path to write p0-review-decisions.json.")

    validate_parser = subparsers.add_parser("validate", help="Validate p0-review-decisions.json against a stub.")
    validate_parser.add_argument("--stub", required=True, help="Path to p0-review-decisions.stub.json.")
    validate_parser.add_argument("--decisions", required=True, help="Path to p0-review-decisions.json.")
    validate_parser.add_argument("--output", required=True, help="Path to write validation report JSON.")

    report_parser = subparsers.add_parser("decision-report", help="Validate decisions and render a Markdown report.")
    report_parser.add_argument("--stub", required=True, help="Path to p0-review-decisions.stub.json.")
    report_parser.add_argument("--decisions", required=True, help="Path to p0-review-decisions.json.")
    report_parser.add_argument("--output-json", required=True, help="Path to write validation report JSON.")
    report_parser.add_argument("--output-md", required=True, help="Path to write validation report Markdown.")

    edit_guide_parser = subparsers.add_parser("edit-guide", help="Render a pending-decision edit guide.")
    edit_guide_parser.add_argument("--packet", required=True, help="Path to p0-manual-review-packet.json.")
    edit_guide_parser.add_argument("--decisions", required=True, help="Path to p0-review-decisions.json.")
    edit_guide_parser.add_argument("--output-md", required=True, help="Path to write edit guide Markdown.")

    audit_parser = subparsers.add_parser("decision-audit", help="Audit manual decisions against the sample.")
    audit_parser.add_argument("--sample", required=True, help="Path to p0-review-decisions.sample.json.")
    audit_parser.add_argument("--decisions", required=True, help="Path to p0-review-decisions.json.")
    audit_parser.add_argument("--output-json", required=True, help="Path to write decision audit JSON.")
    audit_parser.add_argument("--output-md", required=True, help="Path to write decision audit Markdown.")

    worksheet_parser = subparsers.add_parser("reviewer-worksheet", help="Render a read-only reviewer worksheet.")
    worksheet_parser.add_argument("--packet", required=True, help="Path to p0-manual-review-packet.json.")
    worksheet_parser.add_argument("--decisions", required=True, help="Path to p0-review-decisions.json.")
    worksheet_parser.add_argument("--audit", required=True, help="Path to p0-review-decisions.audit.json.")
    worksheet_parser.add_argument("--output-md", required=True, help="Path to write reviewer worksheet Markdown.")

    todo_parser = subparsers.add_parser("reviewer-todo", help="Render a machine-readable reviewer todo JSON.")
    todo_parser.add_argument("--packet", required=True, help="Path to p0-manual-review-packet.json.")
    todo_parser.add_argument("--decisions", required=True, help="Path to p0-review-decisions.json.")
    todo_parser.add_argument("--audit", required=True, help="Path to p0-review-decisions.audit.json.")
    todo_parser.add_argument("--output-json", required=True, help="Path to write reviewer todo JSON.")

    packet_parser = subparsers.add_parser("review-packet", help="Create a read-only P0 manual review packet.")
    packet_parser.add_argument("--stub", required=True, help="Path to p0-review-decisions.stub.json.")
    packet_parser.add_argument("--drafts", required=True, help="Path to p0-authority-card-drafts.json.")
    packet_parser.add_argument("--manifest", required=True, help="Path to p0-draft-review-manifest.json.")
    packet_parser.add_argument("--sample", help="Optional path to p0-review-decisions.sample.json.")
    packet_parser.add_argument("--output-json", required=True, help="Path to write review packet JSON.")
    packet_parser.add_argument("--output-md", required=True, help="Path to write review packet Markdown.")
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    if args.command == "sample":
        stub_path = Path(args.stub)
        output_path = Path(args.output)
        sample = build_p0_review_decisions_sample(_load_json(stub_path))
        _write_json(output_path, sample)
        print(
            json.dumps(
                {
                    "version": "hxy-p0-review-decisions-cli.v1",
                    "command": "sample",
                    "valid": True,
                    "sample_path": str(output_path),
                    "decision_count": sample["decision_count"],
                },
                ensure_ascii=False,
            )
        )
        return 0

    if args.command == "init-decisions":
        sample_path = Path(args.sample)
        output_path = Path(args.output)
        if output_path.exists():
            print(
                json.dumps(
                    {
                        "version": "hxy-p0-review-decisions-cli.v1",
                        "command": "init-decisions",
                        "valid": False,
                        "error": "output_exists",
                        "decision_path": str(output_path),
                        "write_to_database": False,
                    },
                    ensure_ascii=False,
                )
            )
            return 1
        decisions = initialize_p0_review_decisions_from_sample(_load_json(sample_path))
        _write_json(output_path, decisions)
        print(
            json.dumps(
                {
                    "version": "hxy-p0-review-decisions-cli.v1",
                    "command": "init-decisions",
                    "valid": True,
                    "decision_path": str(output_path),
                    "decision_count": decisions["decision_count"],
                    "write_to_database": decisions["write_to_database"],
                },
                ensure_ascii=False,
            )
        )
        return 0

    if args.command == "validate":
        stub_path = Path(args.stub)
        decisions_path = Path(args.decisions)
        output_path = Path(args.output)
        validation = validate_p0_review_decisions(_load_json(stub_path), _load_json(decisions_path))
        _write_json(output_path, validation)
        print(
            json.dumps(
                {
                    "version": "hxy-p0-review-decisions-cli.v1",
                    "command": "validate",
                    "valid": validation["valid"],
                    "validation_path": str(output_path),
                    "error_count": validation["error_count"],
                    "warning_count": validation["warning_count"],
                },
                ensure_ascii=False,
            )
        )
        return 0 if validation["valid"] else 1

    if args.command == "decision-report":
        stub_path = Path(args.stub)
        decisions_path = Path(args.decisions)
        output_json_path = Path(args.output_json)
        output_md_path = Path(args.output_md)
        validation = validate_p0_review_decisions(_load_json(stub_path), _load_json(decisions_path))
        _write_json(output_json_path, validation)
        output_md_path.parent.mkdir(parents=True, exist_ok=True)
        output_md_path.write_text(render_p0_review_decisions_validation_markdown(validation), encoding="utf-8")
        print(
            json.dumps(
                {
                    "version": "hxy-p0-review-decisions-cli.v1",
                    "command": "decision-report",
                    "valid": validation["valid"],
                    "json_path": str(output_json_path),
                    "markdown_path": str(output_md_path),
                    "error_count": validation["error_count"],
                    "warning_count": validation["warning_count"],
                    "publish_allowed": validation["publish_allowed"],
                    "write_to_database": validation["write_to_database"],
                },
                ensure_ascii=False,
            )
        )
        return 0 if validation["valid"] else 1

    if args.command == "edit-guide":
        packet_path = Path(args.packet)
        decisions_path = Path(args.decisions)
        output_md_path = Path(args.output_md)
        packet = _load_json(packet_path)
        decisions = _load_json(decisions_path)
        output_md_path.parent.mkdir(parents=True, exist_ok=True)
        output_md_path.write_text(render_p0_decision_edit_guide_markdown(packet, decisions), encoding="utf-8")
        items = packet.get("items") if isinstance(packet.get("items"), list) else []
        decision_items = decisions.get("items") if isinstance(decisions.get("items"), list) else []
        pending_case_ids = {
            str(item.get("source_case_id") or "")
            for item in decision_items
            if isinstance(item, dict) and str(item.get("action") or "pending") == "pending"
        }
        print(
            json.dumps(
                {
                    "version": "hxy-p0-review-decisions-cli.v1",
                    "command": "edit-guide",
                    "markdown_path": str(output_md_path),
                    "item_count": len(items),
                    "pending_count": len([case_id for case_id in pending_case_ids if case_id]),
                    "write_to_database": False,
                },
                ensure_ascii=False,
            )
        )
        return 0

    if args.command == "decision-audit":
        sample_path = Path(args.sample)
        decisions_path = Path(args.decisions)
        output_json_path = Path(args.output_json)
        output_md_path = Path(args.output_md)
        audit = build_p0_review_decisions_audit(_load_json(sample_path), _load_json(decisions_path))
        _write_json(output_json_path, audit)
        output_md_path.parent.mkdir(parents=True, exist_ok=True)
        output_md_path.write_text(render_p0_review_decisions_audit_markdown(audit), encoding="utf-8")
        print(
            json.dumps(
                {
                    "version": "hxy-p0-review-decisions-cli.v1",
                    "command": "decision-audit",
                    "json_path": str(output_json_path),
                    "markdown_path": str(output_md_path),
                    "changed_count": audit["changed_count"],
                    "pending_count": audit["pending_count"],
                    "metadata_gap_count": audit["metadata_gap_count"],
                    "write_to_database": audit["write_to_database"],
                },
                ensure_ascii=False,
            )
        )
        return 0

    if args.command == "reviewer-worksheet":
        packet_path = Path(args.packet)
        decisions_path = Path(args.decisions)
        audit_path = Path(args.audit)
        output_md_path = Path(args.output_md)
        packet = _load_json(packet_path)
        decisions = _load_json(decisions_path)
        audit = _load_json(audit_path)
        output_md_path.parent.mkdir(parents=True, exist_ok=True)
        output_md_path.write_text(render_p0_reviewer_worksheet_markdown(packet, decisions, audit), encoding="utf-8")
        items = packet.get("items") if isinstance(packet.get("items"), list) else []
        decision_items = decisions.get("items") if isinstance(decisions.get("items"), list) else []
        pending_count = len(
            [
                item
                for item in decision_items
                if isinstance(item, dict) and str(item.get("action") or "pending") == "pending"
            ]
        )
        actioned_count = len(
            [
                item
                for item in decision_items
                if isinstance(item, dict)
                and str(item.get("action") or "pending") in {"approve", "reject", "needs_revision"}
            ]
        )
        print(
            json.dumps(
                {
                    "version": "hxy-p0-review-decisions-cli.v1",
                    "command": "reviewer-worksheet",
                    "markdown_path": str(output_md_path),
                    "item_count": len(items),
                    "pending_count": pending_count,
                    "actioned_count": actioned_count,
                    "write_to_database": False,
                },
                ensure_ascii=False,
            )
        )
        return 0

    if args.command == "reviewer-todo":
        packet_path = Path(args.packet)
        decisions_path = Path(args.decisions)
        audit_path = Path(args.audit)
        output_json_path = Path(args.output_json)
        todo = build_p0_reviewer_todo(_load_json(packet_path), _load_json(decisions_path), _load_json(audit_path))
        _write_json(output_json_path, todo)
        print(
            json.dumps(
                {
                    "version": "hxy-p0-review-decisions-cli.v1",
                    "command": "reviewer-todo",
                    "json_path": str(output_json_path),
                    "item_count": todo["item_count"],
                    "pending_count": todo["pending_count"],
                    "actioned_count": todo["actioned_count"],
                    "write_to_database": todo["write_to_database"],
                },
                ensure_ascii=False,
            )
        )
        return 0

    if args.command == "review-packet":
        output_json_path = Path(args.output_json)
        output_md_path = Path(args.output_md)
        decision_stub = _load_json(Path(args.stub))
        sample = _load_json(Path(args.sample)) if args.sample and Path(args.sample).is_file() else build_p0_review_decisions_sample(decision_stub)
        packet = build_p0_manual_review_packet(
            decision_stub=decision_stub,
            draft_pack=_load_json(Path(args.drafts)),
            review_manifest=_load_json(Path(args.manifest)),
            decision_sample=sample,
        )
        _write_json(output_json_path, packet)
        output_md_path.parent.mkdir(parents=True, exist_ok=True)
        output_md_path.write_text(render_p0_manual_review_packet_markdown(packet), encoding="utf-8")
        print(
            json.dumps(
                {
                    "version": "hxy-p0-review-decisions-cli.v1",
                    "command": "review-packet",
                    "json_path": str(output_json_path),
                    "markdown_path": str(output_md_path),
                    "item_count": packet["item_count"],
                    "publish_allowed": packet["publish_allowed"],
                    "write_to_database": packet["write_to_database"],
                },
                ensure_ascii=False,
            )
        )
        return 0

    parser.error(f"unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
