#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


TOPIC_KEYWORDS: dict[str, list[str]] = {
    "positioning": ["定位", "核爆点", "战场", "购买理由", "社区"],
    "product": ["泡脚", "按摩", "菜单", "SPU", "SKU", "草本"],
    "store_model": ["小店模型", "单店", "回本", "坪效", "面积", "技师"],
    "competitor": ["奈晚", "谷小推", "长风拨筋", "帮大爷", "竞品"],
    "finance": ["投资", "成本", "毛利", "回本", "融资", "分账"],
    "technology": ["O2O", "小程序", "AI", "数据", "支付", "IoT"],
    "franchise": ["连锁", "加盟", "万店", "复制", "总部"],
}

TOPIC_LABELS = {
    "positioning": "战略定位",
    "product": "产品服务",
    "store_model": "门店模型",
    "competitor": "竞品情报",
    "finance": "财务模型",
    "technology": "技术系统",
    "franchise": "加盟规模化",
}


def compact_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def evidence_score(text: str, keywords: list[str]) -> int:
    lower = text.lower()
    return sum(lower.count(keyword.lower()) * 5 for keyword in keywords)


def collect_evidence(
    chunks: list[dict[str, Any]],
    topic_keywords: dict[str, list[str]] | None = None,
    limit_per_topic: int = 5,
) -> dict[str, list[dict[str, Any]]]:
    topic_keywords = topic_keywords or TOPIC_KEYWORDS
    output: dict[str, list[dict[str, Any]]] = {}
    for topic, keywords in topic_keywords.items():
        scored: list[dict[str, Any]] = []
        for chunk in chunks:
            text = str(chunk.get("text") or "")
            score = evidence_score(" ".join([str(chunk.get("title") or ""), text]), keywords)
            if score <= 0:
                continue
            scored.append(
                {
                    "score": score,
                    "title": chunk.get("title"),
                    "relative_path": chunk.get("relative_path"),
                    "knowledge_domain": chunk.get("knowledge_domain"),
                    "project_stage": chunk.get("project_stage"),
                    "snippet": compact_text(text)[:220],
                }
            )
        output[topic] = sorted(scored, key=lambda item: (-item["score"], item["relative_path"] or ""))[:limit_per_topic]
    return output


def load_chunks(root: Path, run_name: str) -> list[dict[str, Any]]:
    index_path = root / "knowledge" / "structured" / f"hxy-inbox-search-index-{run_name}.json"
    chunks = json.loads(index_path.read_text(encoding="utf-8")).get("chunks", [])
    ocr_path = root / "knowledge" / "structured" / "ocr" / f"hxy-key-image-ocr-{run_name}.json"
    if ocr_path.exists():
        ocr = json.loads(ocr_path.read_text(encoding="utf-8"))
        for asset in ocr.get("assets", []):
            text = "\n".join(line.get("text", "") for line in asset.get("lines", []))
            if text:
                chunks.append(
                    {
                        "title": f"OCR {asset.get('file_name')}",
                        "relative_path": asset.get("relative_path"),
                        "knowledge_domain": asset.get("knowledge_domain"),
                        "project_stage": asset.get("project_stage"),
                        "text": text,
                    }
                )
    return chunks


def render_report(manifest: dict[str, Any], evidence: dict[str, list[dict[str, Any]]], ocr_summary: dict[str, Any] | None) -> str:
    assets = manifest.get("assets", [])
    by_domain = Counter(asset.get("knowledge_domain") for asset in assets)
    by_stage = Counter(asset.get("project_stage") for asset in assets)
    review = [asset for asset in assets if asset.get("status") == "needs_review"]
    lines = [
        "# 荷小悦智慧大脑 HXY Brain",
        "",
        f"- updated_at: {datetime.now().astimezone().isoformat(timespec='seconds')}",
        f"- source_run: {manifest.get('run_name')}",
        f"- assets: {len(assets)}",
        f"- review_backlog: {len(review)}",
        "",
        "## 知识覆盖",
        "",
        "| 知识域 | 数量 |",
        "|---|---:|",
    ]
    for key, count in sorted(by_domain.items()):
        lines.append(f"| {key} | {count} |")
    lines.extend(["", "| 阶段 | 数量 |", "|---|---:|"])
    for key, count in sorted(by_stage.items()):
        lines.append(f"| {key} | {count} |")
    if ocr_summary:
        lines.extend(
            [
                "",
                "## 重点图片 OCR",
                "",
                f"- selected_count: {ocr_summary.get('selected_count', 0)}",
                f"- text_found_count: {ocr_summary.get('text_found_count', 0)}",
                f"- failed_count: {ocr_summary.get('failed_count', 0)}",
            ]
        )
    for topic, items in evidence.items():
        lines.extend(["", f"## {TOPIC_LABELS.get(topic, topic)}", ""])
        if not items:
            lines.append("- 暂无高置信证据。")
            continue
        for item in items:
            lines.append(f"- `{item['relative_path']}` ({item.get('knowledge_domain')}/{item.get('project_stage')}, score {item['score']})")
            lines.append(f"  {item['snippet']}")
    lines.extend(
        [
            "",
            "## 待复核",
            "",
            "- 图片类资料仍需按业务价值补充人工摘要或分批 OCR。",
            "- 关键经营结论进入决策日志前，需要引用 source_path 和 sha256。",
            "- HXY 输出继续只保存在 `/root/hxy`。",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--run-name", default="inbox-2026-06-11")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    manifest_path = root / "knowledge" / "structured" / f"hxy-inbox-manifest-{args.run_name}.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    chunks = load_chunks(root, args.run_name)
    evidence = collect_evidence(chunks)
    ocr_path = root / "knowledge" / "structured" / "ocr" / f"hxy-key-image-ocr-{args.run_name}.json"
    ocr_summary = None
    if ocr_path.exists():
        ocr_summary = json.loads(ocr_path.read_text(encoding="utf-8")).get("summary")
    report = render_report(manifest, evidence, ocr_summary)
    report_path = root / "knowledge" / "reports" / "HXY-BRAIN.md"
    report_path.write_text(report, encoding="utf-8")
    summary = {
        "version": "hxy-brain-summary.v1",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "run_name": args.run_name,
        "asset_count": len(manifest.get("assets", [])),
        "evidence_counts": {topic: len(items) for topic, items in evidence.items()},
        "ocr_summary": ocr_summary,
    }
    summary_path = root / "knowledge" / "structured" / "hxy-brain-summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(report_path), "summary": str(summary_path)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
