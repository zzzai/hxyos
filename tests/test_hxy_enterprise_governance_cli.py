import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_governance_run_cli_is_hxy_owned_and_not_htops_coupled() -> None:
    script = (ROOT / "scripts" / "build-hxy-governance-run.py").read_text(encoding="utf-8")

    assert "hxy_knowledge.enterprise_governance" in script
    assert "knowledge/reports" in script
    assert "/root/htops" not in script
    assert "HETANG_" not in script


def test_governance_blocker_resolution_cli_is_hxy_owned_and_not_htops_coupled() -> None:
    script = (ROOT / "scripts" / "resolve-hxy-governance-blockers.py").read_text(encoding="utf-8")

    assert "HXY_DATABASE_URL" in script
    assert "hxy_knowledge.repository" in script
    assert "hxy_knowledge.enterprise_governance" in script
    assert "/root/htops" not in script
    assert "HETANG_" not in script


def test_governance_run_cli_writes_auditable_json_package(tmp_path: Path) -> None:
    inbox = tmp_path / "knowledge" / "raw" / "inbox"
    inbox.mkdir(parents=True)
    (inbox / "brand.md").write_text("荷小悦品牌资料", encoding="utf-8")
    structured = tmp_path / "quarantine" / "knowledge-assets" / "structured"
    structured.mkdir(parents=True)
    (structured / "claims.json").write_text(
        json.dumps(
            [
                {
                    "claim_id": "claim-no-evidence",
                    "claim_type": "brand_positioning",
                    "claim": "荷小悦是社区轻恢复品牌",
                    "status": "current_candidate",
                    "confidence": 0.62,
                    "evidence_ids": [],
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "build-hxy-governance-run.py"),
            "--root",
            str(tmp_path),
            "--run-id",
            "test-run",
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    stdout = json.loads(result.stdout)
    assert stdout["run_id"] == "test-run"
    assert stdout["package_path"] == "knowledge/reports/test-run/run-package.json"
    package_path = tmp_path / stdout["package_path"]
    assert package_path.is_file()
    package = json.loads(package_path.read_text(encoding="utf-8"))
    assert package["version"] == "hxy-governance-run-package.v1"
    assert package["summary"]["added_assets"] == 1
    assert package["summary"]["blocking_issues"] >= 1
    assert (tmp_path / "knowledge" / "reports" / "test-run" / "manifest.json").is_file()
    assert (tmp_path / "knowledge" / "reports" / "test-run" / "incremental-plan.json").is_file()
    assert (tmp_path / "knowledge" / "reports" / "test-run" / "governance-report.json").is_file()


def test_governance_blocker_resolution_cli_dry_run_groups_polluted_cards(tmp_path: Path) -> None:
    package = {
        "version": "hxy-governance-run-package.v1",
        "governance_report": {
            "lint_issues": [
                {
                    "code": "reference_used_as_approved_source",
                    "target_type": "answer_card",
                    "target_id": "card-a",
                    "blocks_release": True,
                },
                {
                    "code": "process_memory_used_as_approved_source",
                    "target_type": "answer_card",
                    "target_id": "card-a",
                    "blocks_release": True,
                },
                {
                    "code": "claim_overclaim_risk",
                    "target_type": "claim",
                    "target_id": "candidate-risk",
                    "blocks_release": False,
                },
            ]
        },
    }
    package_path = tmp_path / "run-package.json"
    package_path.write_text(json.dumps(package, ensure_ascii=False), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "resolve-hxy-governance-blockers.py"),
            "--package",
            str(package_path),
            "--dry-run",
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    stdout = json.loads(result.stdout)
    assert stdout["version"] == "hxy-governance-blocker-resolution.v1"
    assert stdout["dry_run"] is True
    assert stdout["polluted_answer_card_count"] == 1
    assert stdout["polluted_answer_card_ids"] == ["card-a"]
    assert stdout["updated_answer_card_count"] == 0


def test_claim_risk_remediation_cli_dry_run_and_apply_archives_risky_claims(tmp_path: Path) -> None:
    claims_path = tmp_path / "claims.json"
    claims_path.write_text(
        json.dumps(
            [
                {
                    "claim_id": "claim-risk",
                    "claim_type": "brand_positioning",
                    "claim": "三伏天可以说冬病夏治，视觉表达可以说治愈。",
                    "status": "current_candidate",
                    "confidence": 0.76,
                    "evidence_ids": ["e1"],
                },
                {
                    "claim_id": "claim-safe",
                    "claim_type": "brand_positioning",
                    "claim": "荷小悦可以表达为社区轻恢复服务。",
                    "status": "current_candidate",
                    "confidence": 0.76,
                    "evidence_ids": ["e2"],
                },
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    dry_run = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "remediate-hxy-risk-claims.py"),
            "--claims",
            str(claims_path),
            "--dry-run",
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert dry_run.returncode == 0, dry_run.stderr
    dry_body = json.loads(dry_run.stdout)
    assert dry_body["version"] == "hxy-risk-claim-remediation.v1"
    assert dry_body["dry_run"] is True
    assert dry_body["risk_claim_count"] == 1
    assert dry_body["risk_claim_ids"] == ["claim-risk"]
    assert json.loads(claims_path.read_text(encoding="utf-8"))[0]["status"] == "current_candidate"

    applied = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "remediate-hxy-risk-claims.py"),
            "--claims",
            str(claims_path),
            "--target-status",
            "disputed",
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert applied.returncode == 0, applied.stderr
    apply_body = json.loads(applied.stdout)
    assert apply_body["dry_run"] is False
    assert apply_body["updated_claim_count"] == 1
    updated = json.loads(claims_path.read_text(encoding="utf-8"))
    risky = next(item for item in updated if item["claim_id"] == "claim-risk")
    safe = next(item for item in updated if item["claim_id"] == "claim-safe")
    assert risky["status"] == "disputed"
    assert risky["governance_remediation"]["reason"] == "claim_overclaim_risk"
    assert risky["governance_remediation"]["promotion_allowed"] is False
    assert safe["status"] == "current_candidate"
    assert (tmp_path / "claims.json.bak").is_file()
