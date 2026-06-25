#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def normalized_text(root: Path, asset: dict[str, Any]) -> str:
    path = root / (asset.get("normalized_path") or "")
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")


def extract_ocr_text(text: str) -> str:
    marker = "OCR 识别文本："
    if marker not in text:
        return clean_text(text)
    return clean_text(text.split(marker, 1)[1])


def detect_image_type(asset: dict[str, Any], ocr_text: str) -> str:
    corpus = f"{asset.get('relative_path', '')} {asset.get('title', '')} {ocr_text}".lower()
    if any(token in corpus for token in ["菜单", "项目", "套餐", "¥", "￥", "泡脚", "草本"]):
        return "menu"
    if any(token in corpus for token in ["参考品牌", "竞品", "奈晚", "帮大爷", "方松院", "满足里", "谷小推", "长风拨筋", "麦悠悠"]):
        return "competitor_reference"
    if any(token in corpus for token in ["门头", "空间", "店", "前台", "房间", "门店"]):
        return "store_photo"
    if any(token in corpus for token in ["ip", "logo", "vi", "视觉", "品牌", "荷小悦"]):
        return "brand_visual"
    if any(token in corpus for token in ["系统", "小程序", "数据", "后台", "权限"]):
        return "system_screenshot"
    return "general_image"


def detect_entities(asset: dict[str, Any], ocr_text: str) -> list[str]:
    corpus = f"{asset.get('relative_path', '')} {asset.get('title', '')} {ocr_text}"
    entities = [
        "荷小悦",
        "草本泡脚",
        "一人一方",
        "清泡调补养",
        "技师",
        "小店模型",
        "奈晚",
        "帮大爷",
        "方松院",
        "满足里",
        "谷小推",
        "长风拨筋",
        "麦悠悠",
    ]
    return [entity for entity in entities if entity.lower() in corpus.lower()]


def detect_prices(ocr_text: str) -> list[str]:
    prices = re.findall(r"(?:¥|￥)\s?\d+(?:\.\d+)?|\d+\s?元", ocr_text)
    return list(dict.fromkeys(prices))[:20]


def related_domains_for(asset: dict[str, Any], image_type: str, entities: list[str]) -> list[str]:
    domains = [asset.get("knowledge_domain") or "external"]
    if image_type == "menu":
        domains.extend(["product", "brand"])
    if image_type == "competitor_reference":
        domains.extend(["competitor", "brand", "marketing"])
    if image_type == "store_photo":
        domains.extend(["store_model", "operations", "brand"])
    if image_type == "brand_visual":
        domains.extend(["brand", "product"])
    if image_type == "system_screenshot":
        domains.extend(["technology", "operations"])
    if "草本泡脚" in entities or "一人一方" in entities:
        domains.append("product")
    return list(dict.fromkeys(domain for domain in domains if domain))


def summarize_visual(asset: dict[str, Any], image_type: str, ocr_text: str, entities: list[str], prices: list[str]) -> str:
    title = asset.get("title") or "图片"
    if image_type == "menu":
        base = f"{title} 是一张产品/菜单类图片，核心可见信息包括 {', '.join(entities[:5]) or '项目与服务信息'}。"
    elif image_type == "competitor_reference":
        base = f"{title} 是一张竞品或参考品牌图片，用于观察外部品牌表达、门店/项目/背书信息。"
    elif image_type == "brand_visual":
        base = f"{title} 是一张品牌视觉图片，用于识别荷小悦的品牌符号、视觉表达或传播话术。"
    elif image_type == "store_photo":
        base = f"{title} 是一张门店/空间相关图片，可用于判断门店形象、场景和运营触点。"
    elif image_type == "system_screenshot":
        base = f"{title} 是一张系统或数据界面图片，可用于识别产品功能、后台流程或数据字段。"
    else:
        base = f"{title} 是一张通用图片资料，需结合 OCR 文本和来源路径理解。"
    if prices:
        base += " 可见价格信息：" + "、".join(prices[:8]) + "。"
    if ocr_text:
        base += " OCR 摘要：" + clean_text(ocr_text)[:180] + "。"
    return base


def summarize_business(asset: dict[str, Any], image_type: str, entities: list[str], ocr_text: str) -> str:
    domain = asset.get("knowledge_domain") or "external"
    if image_type == "menu":
        return "这张图片应作为产品/服务知识使用，重点关注项目名称、价格、功效表达、草本泡脚和复购话术。"
    if image_type == "competitor_reference":
        return "这张图片应作为竞品参考使用，重点提取竞品定位、背书、价格、项目设计和视觉风格，不直接当作荷小悦权威资料。"
    if image_type == "brand_visual":
        return "这张图片应作为品牌视觉资料使用，重点关注荷小悦品牌符号、用户可感知卖点和可复用传播表达。"
    if image_type == "store_photo":
        return "这张图片应作为门店模型/运营资料使用，重点关注空间结构、服务触点、门头和坪效相关线索。"
    if image_type == "system_screenshot":
        return "这张图片应作为技术/运营系统资料使用，重点关注功能模块、数据字段、角色权限和业务流程。"
    if domain == "product" or any(entity in entities for entity in ["草本泡脚", "一人一方"]):
        return "这张图片与产品体系相关，适合用于补充产品卖点、项目结构和用户端话术。"
    return "这张图片可作为辅助证据，需要结合上游文档和人工复核后再形成权威判断。"


def confidence_for(asset: dict[str, Any], ocr_text: str, image_type: str) -> float:
    metadata = asset.get("metadata") or {}
    score = 0.35
    if image_type != "general_image":
        score += 0.15
    if len(ocr_text) >= 40:
        score += 0.2
    elif ocr_text:
        score += 0.08
    if metadata.get("ocr_avg_confidence"):
        score += min(0.2, float(metadata["ocr_avg_confidence"]) * 0.18)
    if asset.get("quality_score"):
        score += min(0.1, float(asset["quality_score"]) * 0.1)
    return round(max(0.0, min(0.98, score)), 3)


def understand_image(asset: dict[str, Any], text: str) -> dict[str, Any]:
    ocr_text = extract_ocr_text(text)
    image_type = detect_image_type(asset, ocr_text)
    entities = detect_entities(asset, ocr_text)
    prices = detect_prices(ocr_text)
    related_domains = related_domains_for(asset, image_type, entities)
    confidence = confidence_for(asset, ocr_text, image_type)
    visual_summary = summarize_visual(asset, image_type, ocr_text, entities, prices)
    business_summary = summarize_business(asset, image_type, entities, ocr_text)
    needs_review = confidence < 0.55 or not ocr_text or asset.get("status") == "needs_review"
    qa_ready = confidence >= 0.55 and bool(ocr_text)
    return {
        "asset_id": asset.get("asset_id"),
        "source_path": asset.get("relative_path"),
        "normalized_path": asset.get("normalized_path"),
        "title": asset.get("title"),
        "image_type": image_type,
        "ocr_text": ocr_text,
        "visual_summary": visual_summary,
        "business_summary": business_summary,
        "detected_entities": entities,
        "prices": prices,
        "related_domains": related_domains,
        "source_domain": asset.get("knowledge_domain"),
        "source_stage": asset.get("project_stage"),
        "confidence": confidence,
        "qa_ready": qa_ready,
        "needs_review": needs_review,
        "metadata": asset.get("metadata") or {},
        "quality_score": asset.get("quality_score"),
        "quality_grade": asset.get("quality_grade"),
    }


def understanding_to_text(item: dict[str, Any]) -> str:
    parts = [
        f"图片类型：{item['image_type']}",
        f"视觉摘要：{item['visual_summary']}",
        f"业务摘要：{item['business_summary']}",
    ]
    if item.get("detected_entities"):
        parts.append("识别实体：" + "、".join(item["detected_entities"]))
    if item.get("prices"):
        parts.append("价格信息：" + "、".join(item["prices"]))
    if item.get("ocr_text"):
        parts.append("OCR 文本：" + item["ocr_text"][:1000])
    parts.append("相关知识域：" + "、".join(item.get("related_domains") or []))
    return "\n".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build HXY image understanding records")
    parser.add_argument("--root", default=".")
    parser.add_argument("--run-name", default="inbox-2026-06-11")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    structured = root / "knowledge" / "structured"
    manifest_path = structured / f"hxy-inbox-manifest-{args.run_name}.json"
    index_path = structured / f"hxy-inbox-search-index-{args.run_name}.json"
    manifest = load_json(manifest_path)
    search_index = load_json(index_path)

    records: list[dict[str, Any]] = []
    chunks: list[dict[str, Any]] = []
    for asset in manifest.get("assets", []):
        if asset.get("extension") not in IMAGE_EXTENSIONS:
            continue
        item = understand_image(asset, normalized_text(root, asset))
        records.append(item)
        chunks.append(
            {
                "source_id": asset.get("asset_id"),
                "chunk_id": f"{asset.get('asset_id')}:image-understanding:1",
                "chunk_index": 900001,
                "relative_path": asset.get("relative_path"),
                "normalized_path": asset.get("normalized_path"),
                "title": asset.get("title"),
                "knowledge_domain": (item.get("related_domains") or [asset.get("knowledge_domain") or "external"])[0],
                "project_stage": asset.get("project_stage") or "evergreen",
                "text": understanding_to_text(item),
                "chunk_type": "image_understanding",
                "image_type": item["image_type"],
                "confidence": item["confidence"],
            }
        )

    payload = {
        "version": "hxy-image-understanding.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_name": args.run_name,
        "count": len(records),
        "items": records,
    }
    write_json(structured / f"hxy-image-understandings-{args.run_name}.json", payload)
    search_index["image_understanding_chunks"] = chunks
    merged_chunks = [chunk for chunk in search_index.get("chunks", []) if chunk.get("chunk_type") != "image_understanding"]
    search_index["chunks"] = merged_chunks + chunks
    search_index["chunk_count"] = len(search_index["chunks"])
    write_json(index_path, search_index)
    print(json.dumps({"images": len(records), "image_understanding_chunks": len(chunks), "total_chunks": len(search_index["chunks"])}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
