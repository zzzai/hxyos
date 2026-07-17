from __future__ import annotations

import importlib

import pytest


@pytest.mark.parametrize(
    ("source_path", "expected"),
    [
        (
            "extracted-reference/门店模型.reference.txt",
            {
                "material_class": "processing_artifact",
                "derivation": "extracted_copy",
                "retrieval_state": "excluded",
            },
        ),
        (
            "荷小悦资料/scripts/抓取文章.py",
            {
                "material_class": "tool_artifact",
                "derivation": "original",
                "retrieval_state": "excluded",
            },
        ),
        (
            "荷小悦资料/scripts/debug_search.html",
            {
                "material_class": "tool_artifact",
                "retrieval_state": "excluded",
            },
        ),
        (
            "荷小悦资料/06_融资商务/融资_荷小悦股东合作协议_20260605.docx",
            {
                "material_class": "internal_record",
                "sensitivity": "founder_only",
                "business_stage": "financing",
                "authority_state": "unclassified",
            },
        ),
        (
            "荷小悦资料/09_知识库与参考资料/原版书籍/定位.epub",
            {
                "material_class": "external_primary",
                "sensitivity": "public",
                "business_stage": "evergreen",
                "retrieval_state": "eligible_reference",
            },
        ),
        (
            "荷小悦资料/09_知识库与参考资料/品牌增长_核心总结.md",
            {
                "material_class": "ai_derived",
                "derivation": "ai_summary",
                "authority_state": "unclassified",
                "retrieval_state": "eligible_reference",
            },
        ),
        (
            "荷小悦资料/09_知识库与参考资料/定位理论_荷小悦应用笔记.md",
            {
                "material_class": "ai_derived",
                "derivation": "application_draft",
                "authority_state": "unclassified",
            },
        ),
        (
            "荷小悦资料/09_知识库与参考资料/09_风险与合规/荷小悦禁用表达库.md",
            {
                "material_class": "internal_project",
                "lifecycle": "current_candidate",
                "authority_state": "candidate",
                "sensitivity": "internal",
            },
        ),
        (
            "荷小悦资料/03_门店模型/门店_【归档参考】荷小悦小店模型.md",
            {
                "material_class": "internal_project",
                "lifecycle": "historical",
                "authority_state": "unclassified",
                "business_stage": "first_store",
            },
        ),
        (
            "荷小悦资料/02_战略方向/品牌_荷小悦品牌构成.md",
            {
                "material_class": "internal_project",
                "lifecycle": "undetermined",
                "authority_state": "unclassified",
                "retrieval_state": "pending_source_decision",
            },
        ),
    ],
)
def test_path_classifier_applies_safety_first_rules(
    source_path: str,
    expected: dict[str, str],
) -> None:
    module = importlib.import_module("apps.api.hxy_product.source_registry")

    classification = module.classify_source_path(source_path)

    for key, value in expected.items():
        assert classification[key] == value
    assert classification["authority_state"] != "approved"
    assert classification["classification_reasons"]
    assert classification["classification_confidence"] in {"low", "medium", "high"}


def test_financing_sensitivity_precedes_generic_project_classification() -> None:
    module = importlib.import_module("apps.api.hxy_product.source_registry")

    classification = module.classify_source_path(
        "荷小悦资料/06_融资商务/融资_荷小悦股东合作协议_品牌战略版.docx"
    )

    assert classification["sensitivity"] == "founder_only"
    assert {"finance", "legal"}.issubset(classification["scope"])
    assert "official_answer" in classification["blocked_use"]
    assert "automatic_publication" in classification["blocked_use"]
    assert classification["classification_reasons"][0].startswith("sensitivity:")


def test_unknown_source_uses_reference_only_low_confidence_defaults() -> None:
    module = importlib.import_module("apps.api.hxy_product.source_registry")

    classification = module.classify_source_path("未整理/资料.dat")

    assert classification["material_class"] == "external_secondary"
    assert classification["lifecycle"] == "undetermined"
    assert classification["authority_state"] == "unclassified"
    assert classification["scope"] == ["external_method"]
    assert classification["sensitivity"] == "internal"
    assert classification["business_stage"] == "evergreen"
    assert classification["derivation"] == "original"
    assert classification["classification_confidence"] == "low"
    assert classification["retrieval_state"] == "eligible_reference"
    assert classification["official_use_allowed"] is False
