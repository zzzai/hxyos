from __future__ import annotations

import json
from pathlib import Path


def test_routing_report_uses_only_canonical_non_artifact_sources(tmp_path: Path) -> None:
    from hxy_knowledge.source_routing import build_source_routing_report

    inbox = tmp_path / "inbox"
    (inbox / "brand.md").parent.mkdir(parents=True)
    (inbox / "brand.md").write_text("品牌核心", encoding="utf-8")
    (inbox / "copy.md").write_text("品牌核心", encoding="utf-8")
    artifact = inbox / "extracted-reference" / "brand.reference.txt"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("解析产物", encoding="utf-8")
    registry = {
        "version": "hxy-source-registry.v2",
        "path_records": [
            {
                "source_path": "brand.md",
                "canonical_source_path": "brand.md",
                "material_class": "internal_project",
                "authority_state": "unclassified",
                "sensitivity": "internal",
                "scope": ["brand"],
                "error": None,
            },
            {
                "source_path": "copy.md",
                "canonical_source_path": "brand.md",
                "material_class": "internal_project",
                "authority_state": "unclassified",
                "sensitivity": "internal",
                "scope": ["brand"],
                "error": None,
            },
            {
                "source_path": "extracted-reference/brand.reference.txt",
                "canonical_source_path": "extracted-reference/brand.reference.txt",
                "material_class": "processing_artifact",
                "authority_state": "unclassified",
                "sensitivity": "internal",
                "scope": ["brand"],
                "error": None,
            },
        ],
    }

    report = build_source_routing_report(inbox, registry, as_of="2026-07-17")

    assert report["version"] == "hxy-source-routing-report.v1"
    assert report["counts"]["routed_sources"] == 1
    assert report["counts"]["excluded_duplicates"] == 1
    assert report["counts"]["excluded_artifacts"] == 1
    assert report["counts"]["by_primary"] == {"hxy_text_compiler": 1}
    item = report["items"][0]
    assert item["source_path"] == "brand.md"
    assert item["parser_plan"]["primary"] == "hxy_text_compiler"
    assert item["official_use_allowed"] is False
    assert item["requires_human_review"] is False
    assert report["requires_human_review"] is False
    assert report["counts"]["pending_adapters"] == 0


def test_routing_report_separates_missing_adapter_from_human_attention(tmp_path: Path) -> None:
    from hxy_knowledge.source_routing import build_source_routing_report

    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "store-photo.png").write_bytes(b"image")
    registry = {
        "version": "hxy-source-registry.v2",
        "path_records": [
            {
                "source_path": "store-photo.png",
                "canonical_source_path": "store-photo.png",
                "material_class": "internal_record",
                "authority_state": "unclassified",
                "sensitivity": "internal",
                "scope": ["first_store"],
                "error": None,
            }
        ],
    }

    report = build_source_routing_report(inbox, registry, as_of="2026-07-17")

    assert report["counts"]["pending_adapters"] == 1
    assert report["counts"]["needs_attention"] == 0
    assert report["requires_human_review"] is False
    assert report["items"][0]["automation_state"] == "pending_adapter"


def test_routing_report_writer_keeps_details_in_private_json(tmp_path: Path) -> None:
    from hxy_knowledge.source_routing import write_source_routing_report

    report = {
        "version": "hxy-source-routing-report.v1",
        "as_of": "2026-07-17",
        "counts": {
            "routed_sources": 2,
            "excluded_duplicates": 0,
            "excluded_artifacts": 0,
            "error_sources": 0,
            "by_primary": {"markitdown": 1, "mineru": 1},
            "by_complexity": {"simple": 1, "high": 1},
        },
        "items": [{"source_path": "private/融资材料.pdf"}],
        "errors": [],
        "official_use_allowed": False,
    }
    output_dir = tmp_path / "data" / "private" / "source-routing"

    paths = write_source_routing_report(report, output_dir, report_date="2026-07-17")

    assert json.loads(paths["json"].read_text(encoding="utf-8")) == report
    summary = paths["markdown"].read_text(encoding="utf-8")
    assert "HXY Source Routing Report" in summary
    assert "mineru" in summary
    assert "Need human attention: `0`" in summary
    assert "Pending adapters: `0`" in summary
    assert "融资材料.pdf" not in summary
    assert not list(output_dir.glob("*.tmp"))
