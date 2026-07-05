#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from hxy_knowledge.enterprise_governance import _overclaim_terms, _risk_types_for_terms  # noqa: E402


def _load_claims(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("claims file must contain a JSON array")
    return [item for item in payload if isinstance(item, dict)]


def _claim_id(claim: dict[str, Any]) -> str:
    return str(claim.get("claim_id") or claim.get("id") or "")


def _risk_claims(claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [claim for claim in claims if _overclaim_terms(str(claim.get("claim") or claim.get("text") or ""))]


def _remediate_claim(claim: dict[str, Any], *, target_status: str, source: str) -> dict[str, Any]:
    text = str(claim.get("claim") or claim.get("text") or "")
    risk_terms = _overclaim_terms(text)
    updated = dict(claim)
    updated["status"] = target_status
    updated["governance_remediation"] = {
        "version": "hxy-risk-claim-remediation.v1",
        "reason": "claim_overclaim_risk",
        "source": source,
        "remediated_at": datetime.now(timezone.utc).isoformat(),
        "risk_terms": risk_terms,
        "risk_types": _risk_types_for_terms(risk_terms),
        "promotion_allowed": False,
        "recommended_next_action": "archive_or_reextract",
    }
    return updated


def main() -> int:
    parser = argparse.ArgumentParser(description="Archive or mark HXY risky candidate claims with audit metadata.")
    parser.add_argument("--claims", required=True, help="Path to HXY structured claims.json")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--target-status", default="disputed", choices=["disputed", "needs_review", "superseded"])
    args = parser.parse_args()

    claims_path = Path(args.claims)
    claims = _load_claims(claims_path)
    risky = _risk_claims(claims)
    risky_ids = [_claim_id(claim) for claim in risky if _claim_id(claim)]
    updated_count = 0
    if not args.dry_run and risky:
        backup_path = claims_path.with_name(claims_path.name + ".bak")
        shutil.copy2(claims_path, backup_path)
        risky_ids_set = set(risky_ids)
        next_claims: list[dict[str, Any]] = []
        for claim in claims:
            if _claim_id(claim) in risky_ids_set:
                next_claims.append(_remediate_claim(claim, target_status=args.target_status, source=str(claims_path)))
                updated_count += 1
            else:
                next_claims.append(claim)
        claims_path.write_text(json.dumps(next_claims, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(
        json.dumps(
            {
                "version": "hxy-risk-claim-remediation.v1",
                "dry_run": bool(args.dry_run),
                "claims_path": str(claims_path),
                "target_status": args.target_status,
                "risk_claim_count": len(risky),
                "risk_claim_ids": risky_ids,
                "updated_claim_count": updated_count,
                "policy": "风险 claim 保留审计链，禁止直接晋升为 approved；需归档或重新抽取无过度承诺的窄 claim。",
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
