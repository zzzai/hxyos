import json
import subprocess
import sys
from pathlib import Path


def test_review_storefront_copy_scores_clear_first_store_expression():
    from hxy_knowledge.brand_decision import review_brand_artifact

    result = review_brand_artifact(
        {
            "artifact_type": "storefront",
            "stage": "first_store_opening",
            "text": "荷小悦 草本泡脚按摩\n草本真现煮，按出真功夫",
        }
    )

    assert result["version"] == "hxy-brand-decision-review.v1"
    assert result["artifact_type"] == "storefront"
    assert result["score"] >= 85
    assert result["status"] == "usable_draft_requires_review"
    assert result["official_use_allowed"] is False
    assert result["requires_human_review"] is True
    assert "category_clarity" in {item["criterion"] for item in result["criteria"]}


def test_review_brand_artifact_rejects_medicalized_claims():
    from hxy_knowledge.brand_decision import review_brand_artifact

    result = review_brand_artifact(
        {
            "artifact_type": "opening_content",
            "stage": "first_store_opening",
            "text": "荷小悦草本泡脚，治疗失眠，一次见效。",
        }
    )

    assert result["status"] == "reject_for_first_store_use"
    assert "overclaim_risk" in result["risk_flags"]
    assert result["score"] < 70
    assert result["official_use_allowed"] is False


def test_review_design_company_output_respects_vi_si_boundary():
    from hxy_knowledge.brand_decision import review_brand_artifact

    result = review_brand_artifact(
        {
            "artifact_type": "design_company_output",
            "stage": "first_store_opening",
            "text": "设计公司提交门店SI方案，包含色彩、门头、空间导视。",
        }
    )

    assert result["status"] == "requires_design_acceptance_review"
    assert "design_company_owns_visual_design" in result["boundary"]
    assert "hxyos_reviews_operating_fit" in result["boundary"]
    assert result["official_use_allowed"] is False


def test_write_brand_review_record_persists_review(tmp_path):
    from hxy_knowledge.brand_decision import review_brand_artifact, write_brand_review_record

    review = review_brand_artifact(
        {
            "artifact_type": "staff_script",
            "stage": "first_store_opening",
            "text": "第一次来可以先做基础足疗，泡一泡按一按，不强推办卡。",
        }
    )

    path = write_brand_review_record(review, reviews_dir=tmp_path / "knowledge" / "brand" / "reviews")

    assert path.exists()
    assert "hxy-brand-review" in path.name


def test_brand_decision_cli_writes_review(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            "scripts/run-hxy-brand-decision.py",
            "--artifact-type",
            "storefront",
            "--stage",
            "first_store_opening",
            "--text",
            "荷小悦 草本泡脚按摩",
            "--reviews-dir",
            str(tmp_path / "knowledge" / "brand" / "reviews"),
        ],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["version"] == "hxy-brand-decision-cli.v1"
    assert payload["review"]["official_use_allowed"] is False
    assert Path(payload["review_path"]).exists()
