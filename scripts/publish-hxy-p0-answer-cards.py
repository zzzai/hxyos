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
    dry_run_p0_approved_card_publication_package,
    publish_p0_dry_run_answer_cards_to_reviewed_file,
)


def _load_json(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepare HXY P0 answer card publication artifacts.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    dry_run_parser = subparsers.add_parser("dry-run", help="Validate and render draft answer card payloads only.")
    dry_run_parser.add_argument("--package", required=True, help="Path to p0-approved-card-publication-package.json.")
    dry_run_parser.add_argument("--output", required=True, help="Path to write dry-run report JSON.")

    publish_parser = subparsers.add_parser("publish", help="Write reviewed answer cards to a standalone JSON file.")
    publish_parser.add_argument("--dry-run", required=True, help="Path to p0-approved-card-publication-dry-run.json.")
    publish_parser.add_argument("--output", required=True, help="Path to write published-answer-cards.reviewed.json.")
    publish_parser.add_argument(
        "--confirm-manual-publication",
        action="store_true",
        help="Required explicit confirmation for file-level publication.",
    )
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    if args.command == "dry-run":
        package_path = Path(args.package)
        output_path = Path(args.output)
        report = dry_run_p0_approved_card_publication_package(_load_json(package_path))
        _write_json(output_path, report)
        print(
            json.dumps(
                {
                    "version": "hxy-p0-answer-card-publication-cli.v1",
                    "command": "dry-run",
                    "valid": report["valid"],
                    "dry_run_path": str(output_path),
                    "payload_count": report["payload_count"],
                    "would_write_count": report["would_write_count"],
                    "error_count": report["error_count"],
                    "warning_count": report["warning_count"],
                },
                ensure_ascii=False,
            )
        )
        return 0 if report["valid"] else 1

    if args.command == "publish":
        dry_run_path = Path(args.dry_run)
        output_path = Path(args.output)
        report = publish_p0_dry_run_answer_cards_to_reviewed_file(
            _load_json(dry_run_path),
            confirm_manual_publication=bool(args.confirm_manual_publication),
        )
        if report["published"]:
            _write_json(output_path, report)
        print(
            json.dumps(
                {
                    "version": "hxy-p0-answer-card-publication-cli.v1",
                    "command": "publish",
                    "published": report["published"],
                    "reviewed_path": str(output_path) if report["published"] else "",
                    "published_count": report["published_count"],
                    "error_count": report["error_count"],
                    "write_to_database": report["write_to_database"],
                },
                ensure_ascii=False,
            )
        )
        return 0 if report["published"] else 1

    parser.error(f"unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
