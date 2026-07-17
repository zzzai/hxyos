from __future__ import annotations

import importlib
import json
from pathlib import Path
import subprocess
import sys

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
            "荷小悦资料/09_知识库与参考资料/行业文章/batch_download.py",
            {
                "material_class": "tool_artifact",
                "retrieval_state": "excluded",
            },
        ),
        (
            "荷小悦资料/09_知识库与参考资料/营销类书籍/desktop.ini",
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


def test_registry_inventories_paths_and_groups_exact_duplicates(tmp_path: Path) -> None:
    module = importlib.import_module("apps.api.hxy_product.source_registry")
    inbox = tmp_path / "inbox"
    internal = inbox / "荷小悦资料" / "02_战略方向" / "品牌核心.md"
    duplicate = inbox / "荷小悦资料" / "09_知识库与参考资料" / "品牌参考.md"
    artifact = inbox / "extracted-reference" / "品牌核心.reference.txt"
    unique = inbox / "未整理" / "raw.bin"
    internal.parent.mkdir(parents=True)
    duplicate.parent.mkdir(parents=True)
    artifact.parent.mkdir(parents=True)
    unique.parent.mkdir(parents=True)
    internal.write_text("同一份品牌内容", encoding="utf-8")
    duplicate.write_text("同一份品牌内容", encoding="utf-8")
    artifact.write_text("同一份品牌内容", encoding="utf-8")
    unique.write_bytes(b"\x00\x01\x02")

    registry = module.build_source_registry(inbox)

    records = registry["path_records"]
    assert [record["source_path"] for record in records] == sorted(
        record["source_path"] for record in records
    )
    assert registry["counts"] == {
        "path_records": 4,
        "content_groups": 2,
        "duplicate_paths": 2,
        "error_records": 0,
        "approved_sources": 0,
    }
    by_path = {record["source_path"]: record for record in records}
    canonical_path = "荷小悦资料/02_战略方向/品牌核心.md"
    duplicate_paths = [
        "extracted-reference/品牌核心.reference.txt",
        "荷小悦资料/09_知识库与参考资料/品牌参考.md",
    ]
    assert by_path[canonical_path]["derivation"] == "original"
    assert by_path[canonical_path]["canonical_source_path"] == canonical_path
    assert by_path[canonical_path]["duplicate_paths"] == duplicate_paths
    assert by_path[duplicate_paths[0]]["derivation"] == "duplicate_copy"
    assert by_path[duplicate_paths[1]]["derivation"] == "duplicate_copy"
    assert all(
        by_path[path]["content_id"] == by_path[canonical_path]["content_id"]
        for path in duplicate_paths
    )

    group = next(
        item
        for item in registry["content_groups"]
        if item["canonical_source_path"] == canonical_path
    )
    assert group["path_count"] == 3
    assert group["effective_sensitivity"] == "internal"
    assert group["effective_retrieval_state"] == "pending_source_decision"
    assert "formal_hxy_fact" in group["blocked_use"]
    assert "retrieval" not in group["blocked_use"]


def test_registry_rejects_symlinks_that_escape_the_inbox(tmp_path: Path) -> None:
    module = importlib.import_module("apps.api.hxy_product.source_registry")
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    (inbox / "outside-link.txt").symlink_to(outside)

    registry = module.build_source_registry(inbox)

    assert registry["counts"]["path_records"] == 1
    assert registry["counts"]["content_groups"] == 0
    assert registry["counts"]["error_records"] == 1
    record = registry["path_records"][0]
    assert record["source_path"] == "outside-link.txt"
    assert record["error"] == {
        "code": "source_outside_inbox",
        "message": "source resolves outside inbox",
    }
    assert record["content_id"] is None
    assert record["retrieval_state"] == "excluded"


def test_registry_record_payload_is_deterministic(tmp_path: Path) -> None:
    module = importlib.import_module("apps.api.hxy_product.source_registry")
    inbox = tmp_path / "inbox"
    source = inbox / "荷小悦资料" / "03_门店模型" / "首店模型.md"
    source.parent.mkdir(parents=True)
    source.write_text("首店验证材料", encoding="utf-8")

    first = module.build_source_registry(inbox)
    second = module.build_source_registry(inbox)

    assert json.dumps(first, ensure_ascii=False, sort_keys=True) == json.dumps(
        second,
        ensure_ascii=False,
        sort_keys=True,
    )


def test_registry_writer_creates_private_stable_json_and_safe_summary(
    tmp_path: Path,
) -> None:
    module = importlib.import_module("apps.api.hxy_product.source_registry")
    inbox = tmp_path / "inbox"
    source = inbox / "荷小悦资料" / "06_融资商务" / "融资_股东合作协议.docx"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"secret agreement content")
    registry = module.build_source_registry(inbox, as_of="2026-07-17")
    output_dir = tmp_path / "data" / "private" / "source-registry"

    paths = module.write_registry_reports(
        registry,
        output_dir,
        report_date="2026-07-17",
    )

    assert paths == {
        "json": output_dir / "2026-07-17-source-registry.json",
        "markdown": output_dir / "2026-07-17-source-registry.md",
    }
    payload = json.loads(paths["json"].read_text(encoding="utf-8"))
    assert payload == registry
    summary = paths["markdown"].read_text(encoding="utf-8")
    assert "HXY Source Registry V2" in summary
    assert "founder_only" in summary
    assert "融资_股东合作协议.docx" in summary
    assert "secret agreement content" not in summary
    assert not list(output_dir.glob("*.tmp"))
    assert not (output_dir / "selection.json").exists()


def test_registry_writer_replaces_previous_artifacts_atomically(tmp_path: Path) -> None:
    module = importlib.import_module("apps.api.hxy_product.source_registry")
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    source = inbox / "first.txt"
    source.write_text("first", encoding="utf-8")
    output_dir = tmp_path / "private"

    first = module.build_source_registry(inbox, as_of="2026-07-17")
    module.write_registry_reports(first, output_dir, report_date="2026-07-17")
    source.write_text("second", encoding="utf-8")
    second = module.build_source_registry(inbox, as_of="2026-07-17")
    module.write_registry_reports(second, output_dir, report_date="2026-07-17")

    payload = json.loads(
        (output_dir / "2026-07-17-source-registry.json").read_text(encoding="utf-8")
    )
    assert payload["path_records"][0]["source_hash"] == second["path_records"][0][
        "source_hash"
    ]


def test_registry_cli_writes_only_requested_private_outputs(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "source.md").write_text("source", encoding="utf-8")
    output_dir = tmp_path / "private"
    script = Path(__file__).parents[1] / "scripts" / "build-hxy-source-registry.py"

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--inbox",
            str(inbox),
            "--output-dir",
            str(output_dir),
            "--as-of",
            "2026-07-17",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "source registry built: 1 paths, 1 content groups" in result.stdout
    assert (output_dir / "2026-07-17-source-registry.json").is_file()
    assert (output_dir / "2026-07-17-source-registry.md").is_file()
    assert not (output_dir / "selection.json").exists()
