from __future__ import annotations

import base64
import io
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable


IMAGE_SUFFIXES = frozenset({".bmp", ".gif", ".jpeg", ".jpg", ".png", ".webp"})
_IMAGE_TYPES = frozenset(
    {
        "menu",
        "competitor_reference",
        "store_photo",
        "brand_visual",
        "system_screenshot",
        "general_image",
    }
)
_ALLOWED_DOMAINS = frozenset(
    {
        "brand",
        "competitor",
        "external",
        "finance",
        "franchise",
        "operations",
        "product",
        "store_model",
        "technology",
    }
)
_MAX_SOURCE_BYTES = 30 * 1024 * 1024
_MAX_PIXELS = 40_000_000
_MAX_MODEL_EDGE = 2048
_MAX_SUMMARY_CHARS = 2000
_MAX_OCR_CHARS = 8000
_MAX_LIST_ITEMS = 32
_MAX_LIST_ITEM_CHARS = 240


class ImageAdapterError(ValueError):
    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True)
class OcrResult:
    text: str = ""
    confidence: float = 0.0
    engine: str = "unavailable"
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class ImageRecognitionResult:
    text_content: str
    title: str | None
    parser_name: str
    parser_version: str
    warnings: tuple[str, ...]
    quality: dict[str, Any]
    metadata: dict[str, Any]
    official_use_allowed: bool = False


def _clamp_confidence(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def _bounded_text(value: Any, limit: int = _MAX_SUMMARY_CHARS) -> str:
    text = str(value or "").replace("\x00", " ")
    return " ".join(text.split())[:limit].strip()


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    values: list[str] = []
    for item in value[:_MAX_LIST_ITEMS]:
        normalized = _bounded_text(item, _MAX_LIST_ITEM_CHARS)
        if normalized:
            values.append(normalized)
    return values


def _extract_json_object(value: str) -> dict[str, Any] | None:
    candidate = str(value or "").strip()
    if candidate.startswith("```"):
        candidate = candidate.strip("`").strip()
        if candidate.lower().startswith("json"):
            candidate = candidate[4:].strip()
    try:
        parsed = json.loads(candidate)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            parsed = json.loads(candidate[start : end + 1])
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None


def _validate_image(source: Path) -> None:
    if not source.is_file():
        raise ImageAdapterError("source_missing", "image source does not exist")
    if source.stat().st_size > _MAX_SOURCE_BYTES:
        raise ImageAdapterError("image_too_large", "image exceeds the safe source size")
    try:
        from PIL import Image
    except ImportError as error:
        raise ImageAdapterError(
            "parser_dependency_missing",
            "Pillow is required for image parsing",
            retryable=True,
        ) from error
    try:
        with Image.open(source) as image:
            width, height = image.size
            if width <= 0 or height <= 0 or width * height > _MAX_PIXELS:
                raise ImageAdapterError("image_too_large", "image exceeds the safe pixel budget")
            image.verify()
    except ImageAdapterError:
        raise
    except Exception as error:
        raise ImageAdapterError("invalid_image", "image could not be decoded") from error


def _model_data_url(source: Path) -> str:
    try:
        from PIL import Image, ImageOps
    except ImportError as error:
        raise ImageAdapterError(
            "parser_dependency_missing",
            "Pillow is required for image encoding",
            retryable=True,
        ) from error
    try:
        with Image.open(source) as opened:
            source_format = str(opened.format or "").upper()
            image = ImageOps.exif_transpose(opened).convert("RGB")
            image.thumbnail((_MAX_MODEL_EDGE, _MAX_MODEL_EDGE), Image.Resampling.LANCZOS)
            output = io.BytesIO()
            model_format = "PNG" if source_format == "PNG" else "JPEG"
            if model_format == "PNG":
                image.save(output, format="PNG", optimize=True)
            else:
                image.save(output, format="JPEG", quality=88, optimize=True)
    except Exception as error:
        raise ImageAdapterError("image_encode_failed", "image could not be prepared for visual understanding") from error
    mime_type = "image/png" if model_format == "PNG" else "image/jpeg"
    return f"data:{mime_type};base64," + base64.b64encode(output.getvalue()).decode("ascii")


@lru_cache(maxsize=1)
def _rapidocr_engine() -> Any:
    from rapidocr_onnxruntime import RapidOCR

    return RapidOCR()


def default_ocr_runner(source: Path) -> OcrResult:
    try:
        engine = _rapidocr_engine()
    except ImportError:
        return OcrResult(engine="unavailable", warnings=("rapidocr_dependency_missing",))
    except Exception:
        return OcrResult(engine="unavailable", warnings=("rapidocr_initialization_failed",))

    try:
        raw_lines, _elapsed = engine(str(source))
    except Exception:
        return OcrResult(engine="rapidocr", warnings=("rapidocr_runtime_failed",))

    texts: list[str] = []
    confidences: list[float] = []
    for line in raw_lines or []:
        if not isinstance(line, (list, tuple)) or len(line) < 3:
            continue
        text = str(line[1] or "").strip()
        if not text:
            continue
        texts.append(text)
        confidences.append(_clamp_confidence(line[2]))
    return OcrResult(
        text="\n".join(texts),
        confidence=sum(confidences) / len(confidences) if confidences else 0.0,
        engine="rapidocr",
    )


def _vision_messages(data_url: str, *, file_name: str, ocr_text: str) -> list[dict[str, Any]]:
    prompt = "\n".join(
        [
            "你是荷小悦资料入库的视觉理解器。只做资料识别和候选参考整理，不把图片内容当作荷小悦正式事实。",
            "请严格返回 JSON，不要 Markdown。字段：image_type, visual_summary, business_summary, ocr_text, detected_entities, prices, related_domains, confidence, qa_ready, needs_review。",
            "image_type 只能使用 menu/competitor_reference/store_photo/brand_visual/system_screenshot/general_image。",
            "related_domains 只能使用 product/brand/operations/store_model/franchise/finance/competitor/technology/external。",
            "business_summary 说明图片对荷小悦哪个工作场景有参考价值；不确定时明确写不确定。",
            f"文件名：{_bounded_text(file_name, 200)}",
            f"本地 OCR 候选文字：{ocr_text[:4000] or '无'}",
            "如果图片不清楚或不能稳定判断，qa_ready=false, needs_review=true, confidence 不要虚高。",
        ]
    )
    return [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        }
    ]


def _merge_ocr(local_text: str, model_text: str) -> str:
    values: list[str] = []
    for value in (local_text, model_text):
        compact = str(value or "").replace("\x00", " ").strip()
        if compact and compact not in values:
            values.append(compact)
    return "\n".join(values)[:_MAX_OCR_CHARS]


def _render_reference(
    *,
    title: str,
    payload: dict[str, Any],
    ocr_text: str,
    quality: dict[str, Any],
) -> str:
    def joined(key: str) -> str:
        values = _string_list(payload.get(key))
        return "、".join(values) if values else "无"

    sections = [
        f"# {_bounded_text(title, 200) or 'image'}",
        "",
        f"图片类型：{_bounded_text(payload.get('image_type'), 80) or 'general_image'}",
        f"视觉摘要：{_bounded_text(payload.get('visual_summary')) or '未形成稳定视觉判断。'}",
        f"业务摘要：{_bounded_text(payload.get('business_summary')) or '暂未形成业务用途判断。'}",
        f"识别实体：{joined('detected_entities')}",
        f"价格信息：{joined('prices')}",
        f"相关知识域：{joined('related_domains')}",
        f"OCR 文本：{ocr_text or '无'}",
        "",
        "治理边界：本文件是图片解析衍生参考，不是荷小悦正式知识，不得直接作为对外口径或权威答案。",
        f"解析质量：{quality.get('status')}；置信度：{quality.get('confidence', 0):.2f}；需视觉复核：{quality.get('requires_visual_review')}",
    ]
    return "\n".join(sections).strip() + "\n"


def recognize_image(
    source: Path,
    *,
    model_router: Any | None = None,
    ocr_runner: Callable[[Path], OcrResult] | None = None,
) -> ImageRecognitionResult:
    source = Path(source)
    _validate_image(source)
    ocr = ocr_runner(source) if ocr_runner is not None else default_ocr_runner(source)
    warnings = list(ocr.warnings)
    payload: dict[str, Any] = {}
    vision_status = "not_configured"

    if model_router is None:
        from .model_router import ModelRouter

        model_router = ModelRouter()
    try:
        generation = model_router.generate(
            "vision_understanding",
            messages=_vision_messages(
                _model_data_url(source),
                file_name=source.name,
                ocr_text=ocr.text,
            ),
            metadata={"file_name": source.name, "adapter": "hxy-image-adapter"},
        )
        if generation.get("used_model"):
            payload = _extract_json_object(str(generation.get("output") or "")) or {}
            vision_status = "ok" if payload else "invalid_output"
        else:
            vision_status = str(generation.get("reason") or "unavailable")
    except Exception as error:
        vision_status = "failed"
        warnings.append(f"vision_call_failed:{type(error).__name__}")

    model_ocr = (
        str(payload.get("ocr_text") or "")
        .replace("\x00", " ")
        .strip()[:_MAX_OCR_CHARS]
    )
    combined_ocr = _merge_ocr(ocr.text, model_ocr)
    visual_summary = _bounded_text(payload.get("visual_summary"))
    business_summary = _bounded_text(payload.get("business_summary"))
    confidence = _clamp_confidence(payload.get("confidence"))
    has_visual_content = bool(visual_summary and business_summary)
    model_requires_review = payload.get("needs_review") is True or payload.get("qa_ready") is not True
    has_visual_result = has_visual_content and confidence >= 0.5 and not model_requires_review
    has_ocr_result = bool(combined_ocr.strip())
    quality_status = (
        "usable"
        if has_visual_result
        else ("review" if has_visual_content or has_ocr_result else "unusable")
    )
    quality = {
        "status": quality_status,
        "score": 100 if has_visual_result else (60 if has_visual_content or has_ocr_result else 0),
        "confidence": confidence if has_visual_content else _clamp_confidence(ocr.confidence),
        "requires_visual_review": not has_visual_result,
        "needs_fallback": not has_visual_content and not has_ocr_result,
        "official_use_allowed": False,
    }
    if not has_visual_result:
        warnings.append("visual_understanding_incomplete")

    related_domains = [
        item
        for item in _string_list(payload.get("related_domains"))
        if item in _ALLOWED_DOMAINS
    ]
    image_type = _bounded_text(payload.get("image_type"), 80)
    safe_payload = {
        "image_type": image_type if image_type in _IMAGE_TYPES else "general_image",
        "visual_summary": visual_summary,
        "business_summary": business_summary,
        "detected_entities": _string_list(payload.get("detected_entities")),
        "prices": _string_list(payload.get("prices")),
        "related_domains": related_domains or ["external"],
    }
    title = source.stem or "image"
    metadata = {
        **safe_payload,
        "ocr_status": ocr.engine if ocr.text else (ocr.engine if ocr.warnings else "empty"),
        "ocr_confidence": _clamp_confidence(ocr.confidence),
        "vision_status": vision_status,
        "vision_model": (
            (generation.get("route") or {}).get("selected_model")
            if "generation" in locals()
            else None
        ),
        "qa_ready": payload.get("qa_ready") is True,
        "model_needs_review": payload.get("needs_review") is True,
    }
    return ImageRecognitionResult(
        text_content=_render_reference(
            title=title,
            payload=safe_payload,
            ocr_text=combined_ocr,
            quality=quality,
        ),
        title=title,
        parser_name="hxy-image-adapter",
        parser_version="1.0",
        warnings=tuple(dict.fromkeys(warnings)),
        quality=quality,
        metadata=metadata,
        official_use_allowed=False,
    )
