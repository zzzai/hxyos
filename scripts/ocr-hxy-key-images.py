#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from PIL import Image, ImageOps
except Exception:  # pragma: no cover
    Image = None
    ImageOps = None

try:
    from rapidocr_onnxruntime import RapidOCR
except Exception:  # pragma: no cover
    RapidOCR = None


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def image_dimensions(root: Path, asset: dict[str, Any]) -> tuple[int, int]:
    metadata = asset.get("metadata") if isinstance(asset.get("metadata"), dict) else {}
    width = int(metadata.get("width") or 0)
    height = int(metadata.get("height") or 0)
    if width and height:
        return width, height
    if Image is None:
        return 0, 0
    try:
        with Image.open(root / asset["relative_path"]) as image:
            return image.width, image.height
    except Exception:
        return 0, 0


def select_ocr_candidates(
    assets: list[dict[str, Any]],
    root: Path | None = None,
    include_long: bool = False,
) -> list[dict[str, Any]]:
    root = root or Path(".")
    selected: list[tuple[int, dict[str, Any]]] = []
    for asset in assets:
        ext = str(asset.get("extension") or Path(str(asset.get("relative_path", ""))).suffix).lower()
        if ext not in IMAGE_EXTENSIONS:
            continue
        path = str(asset.get("relative_path") or "")
        width, height = image_dimensions(root, asset)
        is_long = height >= 3500 or (width > 0 and height / max(width, 1) >= 2.6)
        is_extreme_long = height >= 9000 or (width > 0 and height / max(width, 1) >= 8)
        is_competitor = "参考品牌" in path
        is_hxy_strategy = "荷小悦相关" in path
        is_ip = "hxyip" in path.lower()
        if is_ip and not is_long:
            continue
        if is_extreme_long and not include_long:
            continue
        if not (is_competitor or is_hxy_strategy or is_long):
            continue
        score = 0
        if is_competitor:
            score += 40
        if is_hxy_strategy:
            score += 35
        if is_long:
            score += 30
        score += min(height // 1000, 20)
        selected.append((score, asset))
    return [asset for _, asset in sorted(selected, key=lambda item: (-item[0], item[1].get("relative_path", "")))]


def prepare_tiles(image_path: Path, max_width: int = 900, tile_height: int = 2200, max_tiles: int = 5) -> tuple[list[Path], dict[str, Any], list[str]]:
    metadata: dict[str, Any] = {}
    warnings: list[str] = []
    if Image is None or ImageOps is None:
        return [image_path], metadata, ["pillow_missing"]
    try:
        image = Image.open(image_path)
        image = ImageOps.exif_transpose(image).convert("RGB")
    except Exception as error:
        return [image_path], metadata, [f"image_open_failed:{type(error).__name__}:{error}"]
    metadata.update({"width": image.width, "height": image.height})
    if image.width > max_width:
        resized_height = max(1, int(image.height * (max_width / image.width)))
        image = image.resize((max_width, resized_height))
        metadata["ocr_resized_to"] = {"width": image.width, "height": image.height}
    temp_dir = Path(tempfile.mkdtemp(prefix="hxy-key-ocr-"))
    tiles: list[Path] = []
    start = 0
    while start < image.height and len(tiles) < max_tiles:
        end = min(image.height, start + tile_height)
        tile = image.crop((0, start, image.width, end))
        out = temp_dir / f"tile-{len(tiles) + 1:03d}.jpg"
        tile.save(out, quality=88)
        tiles.append(out)
        if end >= image.height:
            break
        start = end - 120
    metadata["ocr_tile_count"] = len(tiles)
    if start < image.height and len(tiles) >= max_tiles:
        warnings.append(f"truncated_after_{max_tiles}_tiles")
    return tiles, metadata, warnings


def run_ocr_for_image(root: Path, asset: dict[str, Any], engine: Any) -> dict[str, Any]:
    source = root / asset["relative_path"]
    tiles, metadata, warnings = prepare_tiles(source)
    lines: list[dict[str, Any]] = []
    temp_dirs = {tile.parent for tile in tiles if tile.parent.name.startswith("hxy-key-ocr-")}
    try:
        for tile_index, tile in enumerate(tiles, start=1):
            result, elapsed = engine(str(tile))
            metadata.setdefault("ocr_elapsed", []).append(elapsed)
            for item in result or []:
                if len(item) < 3:
                    continue
                text = str(item[1]).strip()
                confidence = float(item[2] or 0)
                if text and confidence >= 0.45:
                    lines.append({"tile": tile_index, "text": text, "confidence": round(confidence, 4)})
    except Exception as error:
        warnings.append(f"ocr_failed:{type(error).__name__}:{error}")
    finally:
        for directory in temp_dirs:
            shutil.rmtree(directory, ignore_errors=True)
    return {
        "asset_id": asset.get("asset_id"),
        "relative_path": asset.get("relative_path"),
        "file_name": asset.get("file_name"),
        "knowledge_domain": asset.get("knowledge_domain"),
        "project_stage": asset.get("project_stage"),
        "metadata": metadata,
        "line_count": len(lines),
        "lines": lines,
        "warnings": warnings,
    }


def render_ocr_markdown(item: dict[str, Any]) -> str:
    body = "\n".join(f"- {line['text']} ({line['confidence']})" for line in item.get("lines", []))
    if not body:
        body = "_未识别到高置信文字。_"
    return "\n".join(
        [
            f"# OCR - {item.get('file_name')}",
            "",
            f"- source_path: {item.get('relative_path')}",
            f"- knowledge_domain: {item.get('knowledge_domain')}",
            f"- project_stage: {item.get('project_stage')}",
            f"- line_count: {item.get('line_count')}",
            f"- warnings: {'; '.join(item.get('warnings') or [])}",
            "",
            "## Lines",
            "",
            body,
            "",
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--run-name", default="inbox-2026-06-11")
    parser.add_argument("--limit", type=int, default=4)
    parser.add_argument("--include-long", action="store_true", help="Include extreme long screenshots.")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    manifest_path = root / "knowledge" / "structured" / f"hxy-inbox-manifest-{args.run_name}.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    candidates = select_ocr_candidates(manifest["assets"], root=root, include_long=args.include_long)
    selected = candidates[: args.limit]
    output_dir = root / "knowledge" / "structured" / "ocr"
    normalized_dir = output_dir / "normalized"
    output_dir.mkdir(parents=True, exist_ok=True)
    normalized_dir.mkdir(parents=True, exist_ok=True)
    if RapidOCR is None:
        results = [
            {
                "asset_id": asset.get("asset_id"),
                "relative_path": asset.get("relative_path"),
                "file_name": asset.get("file_name"),
                "knowledge_domain": asset.get("knowledge_domain"),
                "project_stage": asset.get("project_stage"),
                "metadata": {},
                "line_count": 0,
                "lines": [],
                "warnings": ["rapidocr_not_installed"],
            }
            for asset in selected
        ]
    else:
        engine = RapidOCR()
        results = [run_ocr_for_image(root, asset, engine) for asset in selected]
    for result in results:
        asset_id = str(result.get("asset_id") or "ocr").replace(":", "-")
        (normalized_dir / f"{asset_id}.md").write_text(render_ocr_markdown(result), encoding="utf-8")
    payload = {
        "version": "hxy-key-image-ocr.v1",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "run_name": args.run_name,
        "summary": {
            "candidate_count": len(candidates),
            "selected_count": len(selected),
            "processed_count": len(results),
            "text_found_count": sum(1 for item in results if item["line_count"] > 0),
            "failed_count": sum(1 for item in results if any("failed" in warning for warning in item["warnings"])),
        },
        "assets": results,
    }
    out_path = output_dir / f"hxy-key-image-ocr-{args.run_name}.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
