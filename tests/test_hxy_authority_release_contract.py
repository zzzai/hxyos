from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_model_router_example_contains_required_non_secret_routes() -> None:
    config = (ROOT / "ops" / "env" / "hxy-model-router.toml.example").read_text(encoding="utf-8")

    assert 'frontdoor_classification = { model = "qwen-flash"' in config
    assert 'answer_synthesis = { model = "qwen-plus-latest"' in config
    assert 'policy_review = { model = "qwen3.7-max"' in config
    assert "api_key" not in config.lower()


def test_authority_answer_release_runbook_has_ordered_fail_closed_gates() -> None:
    runbook = (ROOT / "docs" / "operations" / "hxy-authority-answer-release.md").read_text(encoding="utf-8")

    required = [
        "## Stop Rule",
        "## Gate 1: Immutable Source",
        "## Gate 2: Full Verification",
        "## Gate 3: Private Readiness",
        "## Gate 4: Source Authority Schema",
        "## Gate 5: Three-Model Canary",
        "## Gate 6: Core-10 Captured Answers",
        "## Gate 7: Atomic Activation",
        "## Gate 8: Public Smoke",
        "## Rollback Boundary",
    ]
    positions = [runbook.index(item) for item in required]
    assert positions == sorted(positions)
    for phrase in [
        "business_readiness_claimed=false",
        "authority_leakage_failures=0",
        "high_risk_interception_rate=1.0",
        "不得自动创建、批准或激活品牌宪法",
        "不得保存回答正文",
        "697",
        "/root/htops",
        "APPLY-HXY-018",
        "旧知识资产不得自动升格",
    ]:
        assert phrase in runbook
