from __future__ import annotations

from pathlib import Path
from zipfile import ZipFile


def test_text_material_uses_native_compiler_without_external_parser(tmp_path: Path) -> None:
    from hxy_knowledge.document_router import build_parser_plan

    source = tmp_path / "brand.md"
    source.write_text("荷小悦品牌核心。", encoding="utf-8")

    plan = build_parser_plan(source)

    assert plan["primary"] == "hxy_text_compiler"
    assert plan["fallbacks"] == []
    assert plan["complexity"] == "simple"
    assert plan["requires_visual_review"] is False
    assert plan["requires_human_review"] is False
    assert plan["automation_state"] == "ready"


def test_sparse_image_heavy_pdf_routes_to_mineru_with_markitdown_fallback(
    tmp_path: Path,
) -> None:
    from hxy_knowledge.document_router import build_parser_plan

    source = tmp_path / "scanned.pdf"
    source.write_bytes(b"%PDF-1.7 fake")

    plan = build_parser_plan(
        source,
        preflight={
            "page_count": 120,
            "sample_text_chars": 80,
            "image_page_count": 118,
            "table_signal": False,
        },
    )

    assert plan["primary"] == "mineru"
    assert plan["fallbacks"] == ["markitdown"]
    assert plan["complexity"] == "high"
    assert plan["requires_visual_review"] is True
    assert "sparse_text" in plan["signals"]
    assert "image_heavy" in plan["signals"]


def test_text_rich_pdf_prefers_light_parser_and_keeps_high_fidelity_fallback(
    tmp_path: Path,
) -> None:
    from hxy_knowledge.document_router import build_parser_plan

    source = tmp_path / "text-report.pdf"
    source.write_bytes(b"%PDF-1.7 fake")

    plan = build_parser_plan(
        source,
        preflight={
            "page_count": 20,
            "sample_text_chars": 8000,
            "image_page_count": 0,
            "table_signal": True,
        },
    )

    assert plan["primary"] == "markitdown"
    assert plan["fallbacks"] == ["mineru"]
    assert plan["complexity"] == "medium"
    assert "table_signal" in plan["signals"]


def test_large_structured_office_document_can_use_mineru_without_forcing_it(
    tmp_path: Path,
) -> None:
    from hxy_knowledge.document_router import build_parser_plan

    source = tmp_path / "deck.pptx"
    source.write_bytes(b"x" * (2 * 1024 * 1024))

    plan = build_parser_plan(
        source,
        preflight={"has_media": True, "table_signal": False},
    )

    assert plan["primary"] == "mineru"
    assert plan["fallbacks"] == ["markitdown"]
    assert plan["complexity"] == "high"
    assert "large_file" in plan["signals"]
    assert "embedded_media" in plan["signals"]


def test_legacy_office_document_never_routes_to_unsupported_mineru(tmp_path: Path) -> None:
    from hxy_knowledge.document_router import build_parser_plan

    source = tmp_path / "legacy-plan.ppt"
    source.write_bytes(b"x" * (2 * 1024 * 1024))

    plan = build_parser_plan(source)

    assert plan["primary"] == "manual_review"
    assert plan["fallbacks"] == []
    assert "legacy_office_format" in plan["signals"]
    assert plan["requires_human_review"] is True
    assert plan["automation_state"] == "manual_attention"


def test_legacy_xls_uses_supported_markitdown_without_mineru_fallback(tmp_path: Path) -> None:
    from hxy_knowledge.document_router import build_parser_plan

    source = tmp_path / "legacy-data.xls"
    source.write_bytes(b"x" * (2 * 1024 * 1024))

    plan = build_parser_plan(source)

    assert plan["primary"] == "markitdown"
    assert plan["fallbacks"] == ["manual_review"]
    assert "legacy_office_format" in plan["signals"]


def test_table_only_docx_keeps_light_parser_and_high_fidelity_fallback(tmp_path: Path) -> None:
    from hxy_knowledge.document_router import build_parser_plan

    source = tmp_path / "table-report.docx"
    source.write_bytes(b"PK placeholder")

    plan = build_parser_plan(source, preflight={"table_signal": True, "has_media": False})

    assert plan["primary"] == "markitdown"
    assert plan["fallbacks"] == ["mineru"]
    assert plan["complexity"] == "medium"
    assert plan["signals"] == ["table_signal"]


def test_text_rich_pdf_with_images_does_not_trigger_ocr_first(tmp_path: Path) -> None:
    from hxy_knowledge.document_router import build_parser_plan

    source = tmp_path / "illustrated-report.pdf"
    source.write_bytes(b"%PDF-1.7 fake")

    plan = build_parser_plan(
        source,
        preflight={
            "page_count": 80,
            "sampled_page_count": 4,
            "sample_text_chars": 2400,
            "image_page_count": 4,
        },
    )

    assert plan["primary"] == "markitdown"
    assert plan["fallbacks"] == ["mineru"]
    assert plan["complexity"] == "medium"
    assert "images_present" in plan["signals"]
    assert "image_heavy" not in plan["signals"]


def test_image_material_uses_ocr_or_vision_and_never_mineru_as_text_parser(
    tmp_path: Path,
) -> None:
    from hxy_knowledge.document_router import build_parser_plan

    source = tmp_path / "门店照片.png"
    source.write_bytes(b"image")

    plan = build_parser_plan(source)

    assert plan["primary"] == "ocr_or_vision"
    assert plan["fallbacks"] == ["manual_review"]
    assert plan["requires_visual_review"] is True
    assert plan["requires_human_review"] is False
    assert plan["automation_state"] == "pending_adapter"


def test_office_container_preflight_detects_embedded_media_without_model_call(tmp_path: Path) -> None:
    from hxy_knowledge.document_router import build_parser_plan

    source = tmp_path / "visual-deck.pptx"
    with ZipFile(source, "w") as archive:
        archive.writestr("ppt/slides/slide1.xml", "<p:sld></p:sld>")
        archive.writestr("ppt/media/image1.png", b"image")

    plan = build_parser_plan(source)

    assert plan["primary"] == "mineru"
    assert "embedded_media" in plan["signals"]
    assert plan["preflight"]["has_media"] is True
    assert plan["preflight"]["item_count"] == 1


def test_pdf_preflight_samples_structure_before_selecting_parser(tmp_path: Path) -> None:
    from pypdf import PdfWriter

    from hxy_knowledge.document_router import build_parser_plan

    source = tmp_path / "blank-scan.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.add_blank_page(width=100, height=100)
    with source.open("wb") as output:
        writer.write(output)

    plan = build_parser_plan(source)

    assert plan["primary"] == "mineru"
    assert "sparse_text" in plan["signals"]
    assert plan["preflight"]["page_count"] == 2
    assert plan["preflight"]["sampled_page_count"] == 2
    assert plan["preflight"]["sample_text_chars"] == 0
