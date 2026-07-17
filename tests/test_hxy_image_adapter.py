from __future__ import annotations

import json
from pathlib import Path

from PIL import Image


class FakeRouter:
    def __init__(self, output: str | None = None, error: Exception | None = None) -> None:
        self.output = output
        self.error = error
        self.calls: list[dict[str, object]] = []

    def generate(self, task_type: str, *, messages, metadata=None):
        self.calls.append(
            {
                "task_type": task_type,
                "messages": messages,
                "metadata": metadata,
            }
        )
        if self.error:
            raise self.error
        return {
            "used_model": True,
            "reason": "ok",
            "route": {"selected_model": "qwen3-vl-flash"},
            "output": self.output or "",
        }


def _write_image(path: Path) -> None:
    image = Image.new("RGB", (120, 80), "white")
    image.save(path, format="PNG")


def test_recognize_image_combines_ocr_and_governed_vision_output(tmp_path: Path) -> None:
    from hxy_knowledge.image_adapter import OcrResult, recognize_image

    source = tmp_path / "menu.png"
    _write_image(source)
    router = FakeRouter(
        output=json.dumps(
            {
                "image_type": "menu",
                "visual_summary": "蓝色标题区域和价格列表。",
                "business_summary": "可作为产品资料候选参考，不可直接作为正式价格口径。",
                "ocr_text": "模型识别文字",
                "detected_entities": ["清泡调补养"],
                "prices": ["68"],
                "related_domains": ["product"],
                "confidence": 0.93,
                "qa_ready": True,
                "needs_review": False,
            },
            ensure_ascii=False,
        )
    )

    result = recognize_image(
        source,
        model_router=router,
        ocr_runner=lambda _path: OcrResult(
            text="本地 OCR 文字",
            confidence=0.88,
            engine="rapidocr",
        ),
    )

    assert result.quality["status"] == "usable"
    assert result.quality["official_use_allowed"] is False
    assert "本地 OCR 文字" in result.text_content
    assert "蓝色标题区域" in result.text_content
    assert result.metadata["image_type"] == "menu"
    assert result.metadata["related_domains"] == ["product"]
    assert router.calls[0]["task_type"] == "vision_understanding"
    image_url = router.calls[0]["messages"][0]["content"][1]["image_url"]["url"]
    assert str(image_url).startswith("data:image/png;base64,")


def test_recognize_image_falls_back_to_ocr_as_review_quality(tmp_path: Path) -> None:
    from hxy_knowledge.image_adapter import OcrResult, recognize_image

    source = tmp_path / "scan.png"
    _write_image(source)
    result = recognize_image(
        source,
        model_router=FakeRouter(error=RuntimeError("model unavailable")),
        ocr_runner=lambda _path: OcrResult(
            text="扫描件中的文字",
            confidence=0.91,
            engine="rapidocr",
        ),
    )

    assert result.quality["status"] == "review"
    assert result.quality["requires_visual_review"] is True
    assert result.metadata["vision_status"] == "failed"
    assert "扫描件中的文字" in result.text_content
    assert result.official_use_allowed is False


def test_model_review_flags_keep_visual_result_in_review_state(tmp_path: Path) -> None:
    from hxy_knowledge.image_adapter import OcrResult, recognize_image

    source = tmp_path / "uncertain.png"
    _write_image(source)
    router = FakeRouter(
        output=json.dumps(
            {
                "image_type": "menu",
                "visual_summary": "图片里可能有菜单信息。",
                "business_summary": "可能与产品资料相关，但需要人工确认。",
                "confidence": 0.95,
                "qa_ready": False,
                "needs_review": True,
            },
            ensure_ascii=False,
        )
    )

    result = recognize_image(source, model_router=router, ocr_runner=lambda _path: OcrResult())

    assert result.quality["status"] == "review"
    assert result.quality["requires_visual_review"] is True
    assert result.official_use_allowed is False


def test_recognize_image_can_run_without_optional_ocr(tmp_path: Path, monkeypatch) -> None:
    import hxy_knowledge.image_adapter as image_adapter

    def missing_rapidocr():
        raise ImportError("rapidocr_onnxruntime is not installed")

    monkeypatch.setattr(image_adapter, "_rapidocr_engine", missing_rapidocr)

    source = tmp_path / "photo.png"
    _write_image(source)
    router = FakeRouter(
        output=json.dumps(
            {
                "image_type": "store_photo",
                "visual_summary": "门店环境照片。",
                "business_summary": "可作为门店设计参考。",
                "confidence": 0.8,
                "qa_ready": True,
            },
            ensure_ascii=False,
        )
    )

    result = image_adapter.recognize_image(source, model_router=router, ocr_runner=None)

    assert result.quality["status"] == "usable"
    assert result.metadata["ocr_status"] == "unavailable"
    assert result.official_use_allowed is False
