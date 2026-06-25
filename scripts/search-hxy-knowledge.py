#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


def score_text(text: str, query: str) -> int:
    text_lower = text.lower()
    query_lower = query.lower()
    terms = [term for term in re.split(r"\s+", query_lower) if term]
    score = 0
    if query_lower in text_lower:
        score += 20
    for term in terms:
        score += text_lower.count(term) * 5
    return score


def snippet(text: str, query: str, size: int = 120) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    idx = text.lower().find(query.lower())
    if idx < 0:
        idx = 0
    start = max(0, idx - size // 2)
    end = min(len(text), start + size)
    return text[start:end]


def search_chunks(
    chunks: list[dict[str, Any]],
    query: str,
    domain: str | None = None,
    stage: str | None = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for chunk in chunks:
        if domain and chunk.get("knowledge_domain") != domain:
            continue
        if stage and chunk.get("project_stage") != stage:
            continue
        text = str(chunk.get("text") or "")
        score = score_text(" ".join([str(chunk.get("title") or ""), text]), query)
        if score <= 0:
            continue
        results.append(
            {
                "score": score,
                "title": chunk.get("title"),
                "relative_path": chunk.get("relative_path"),
                "knowledge_domain": chunk.get("knowledge_domain"),
                "project_stage": chunk.get("project_stage"),
                "snippet": snippet(text, query),
            }
        )
    return sorted(results, key=lambda item: (-item["score"], item["relative_path"] or ""))[:limit]


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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("query")
    parser.add_argument("--root", default=".")
    parser.add_argument("--run-name", default="inbox-2026-06-11")
    parser.add_argument("--domain")
    parser.add_argument("--stage")
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()
    root = Path(args.root).resolve()
    results = search_chunks(load_chunks(root, args.run_name), args.query, args.domain, args.stage, args.limit)
    for item in results:
        print(f"[{item['score']}] {item['title']} ({item['knowledge_domain']}/{item['project_stage']})")
        print(f"  {item['relative_path']}")
        print(f"  {item['snippet']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
