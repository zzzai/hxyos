#!/usr/bin/env python3
"""
Ingest uploaded HXY raw knowledge files from knowledge/raw/inbox.

The script keeps original files untouched. It creates:
- normalized Markdown files under knowledge/normalized/<domain>/<stage>/
- symlink classification shelves under knowledge/raw/classified/<run>/
- structured JSON manifests/search chunks under knowledge/structured/
- review reports under knowledge/reports/
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

try:
    from bs4 import BeautifulSoup
except Exception:  # pragma: no cover - optional local dependency
    BeautifulSoup = None

try:
    from PIL import Image, ImageOps
except Exception:  # pragma: no cover - optional local dependency
    Image = None
    ImageOps = None

try:
    from rapidocr_onnxruntime import RapidOCR
except Exception:  # pragma: no cover - optional local dependency
    RapidOCR = None


DOMAINS: dict[str, str] = {
    "brand": "品牌",
    "product": "产品/服务",
    "store_model": "门店模型",
    "operations": "运营",
    "marketing": "营销",
    "management": "管理",
    "franchise": "加盟/连锁",
    "finance": "财务/支付/融资",
    "competitor": "竞品",
    "technology": "技术/系统",
    "legal": "法务/合同",
    "external": "外部行业/市场",
}

STAGES: dict[str, str] = {
    "preparation": "筹备期",
    "pilot": "试点期",
    "scale": "扩张期",
    "chain": "连锁化",
    "10000_stores": "万店规模",
    "evergreen": "长期通用",
}

DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "brand": [
        "品牌",
        "定位",
        "ip",
        "视觉",
        "vi",
        "设计",
        "超级符号",
        "购买理由",
        "门头",
        "logo",
        "商业方案",
        "策划全案",
        "战略汇总",
    ],
    "product": [
        "产品",
        "服务",
        "套餐",
        "项目",
        "菜单",
        "泡脚",
        "按摩",
        "推拿",
        "理疗",
        "草本",
        "spu",
        "sku",
        "差异化",
        "产品全景",
    ],
    "store_model": [
        "小店模型",
        "单店",
        "店型",
        "门店模型",
        "坪效",
        "房间",
        "面积",
        "选址",
        "人员配置",
        "模型具象化",
    ],
    "operations": [
        "运营",
        "流程",
        "排班",
        "复购",
        "服务流程",
        "到店",
        "会员",
        "技师",
        "店长",
        "员工",
    ],
    "marketing": [
        "营销",
        "获客",
        "活动",
        "投放",
        "私域",
        "团购",
        "转化",
        "抖音",
        "美团",
        "大众点评",
    ],
    "management": [
        "管理",
        "组织",
        "培训",
        "绩效",
        "督导",
        "薪酬",
        "总部",
        "权限",
    ],
    "franchise": [
        "加盟",
        "招商",
        "加盟商",
        "复制",
        "连锁",
        "多门店",
        "万店",
        "全国",
        "拓店",
    ],
    "finance": [
        "财务",
        "成本",
        "毛利",
        "利润",
        "现金流",
        "回本",
        "融资",
        "天使轮",
        "报价单",
        "支付",
        "分账",
        "收单",
        "股东",
    ],
    "competitor": [
        "竞品",
        "参考品牌",
        "对手",
        "同行",
        "奈晚",
        "帮大爷",
        "方松院",
        "满足里",
        "谷小推",
        "长风拨筋",
        "麦悠悠",
        "五个养生品牌",
    ],
    "technology": [
        "技术",
        "系统",
        "小程序",
        "ai",
        "数据",
        "agent",
        "o2o",
        "iot",
        "硬件",
        "权限",
        "实施手册",
    ],
    "legal": [
        "合同",
        "法务",
        "协议",
        "授权",
        "商标",
        "股东合作协议",
    ],
    "external": [
        "行业",
        "政策",
        "市场",
        "人口",
        "商圈",
        "趋势",
        "消费者",
        "洞察",
        "需求逆推",
    ],
}

STAGE_KEYWORDS: dict[str, list[str]] = {
    "preparation": ["筹备", "开业前", "启动", "立项", "准备", "报价", "设计", "合同", "协议", "项目介绍"],
    "pilot": ["试点", "样板店", "验证", "测试", "首店", "单店", "小店模型", "研讨"],
    "scale": ["扩张", "拓店", "规模化", "增长", "潜在收购"],
    "chain": ["连锁", "标准化", "督导", "区域", "多店", "多门店", "总部"],
    "10000_stores": ["10000", "万店", "全国", "平台化", "生态"],
    "evergreen": ["长期", "通用", "方法论", "行业", "趋势", "洞察", "对比分析", "需求逆推"],
}

EXPLICIT_CLASSIFICATION_RULES: list[dict[str, Any]] = [
    {
        "patterns": ["参考品牌/"],
        "domain": "competitor",
        "stage": "preparation",
        "secondary": ["brand", "marketing"],
        "reason": "path:参考品牌资料",
    },
    {
        "patterns": ["奈晚推拿", "五个养生品牌核心维度深度对比分析"],
        "domain": "competitor",
        "stage": "preparation",
        "secondary": ["store_model", "marketing"],
        "reason": "filename:竞品/同行分析",
    },
    {
        "patterns": ["荷小悦-小店模型调研_初步构思", "荷小悦 小店模型", "荷小悦门店模型具象化构思"],
        "domain": "store_model",
        "stage": "pilot",
        "secondary": ["product", "finance", "operations"],
        "reason": "filename:荷小悦门店/小店模型",
    },
    {
        "patterns": ["定位与单店研讨"],
        "domain": "store_model",
        "stage": "pilot",
        "secondary": ["brand", "product", "finance"],
        "reason": "filename:定位与单店研讨",
    },
    {
        "patterns": ["荷小悦-项目介绍"],
        "domain": "product",
        "stage": "preparation",
        "secondary": ["brand", "store_model"],
        "reason": "filename:项目介绍",
    },
    {
        "patterns": ["商业计划书", "天使轮融资", "融资商业计划书"],
        "domain": "finance",
        "stage": "preparation",
        "secondary": ["brand", "franchise", "store_model"],
        "reason": "filename:商业计划/融资",
    },
    {
        "patterns": ["潜在收购方分析"],
        "domain": "finance",
        "stage": "scale",
        "secondary": ["franchise", "external"],
        "reason": "filename:潜在收购方分析",
    },
    {
        "patterns": ["万店连锁战略规划", "万店连锁战略重构"],
        "domain": "franchise",
        "stage": "10000_stores",
        "secondary": ["brand", "store_model", "technology"],
        "reason": "filename:万店连锁战略",
    },
    {
        "patterns": ["品牌战略汇总", "品牌策划全案", "品牌商业方案", "品牌设计报价单"],
        "domain": "brand",
        "stage": "preparation",
        "secondary": ["product", "finance"],
        "reason": "filename:品牌资料",
    },
    {
        "patterns": ["按摩服务行业_消费者需求逆推图", "理疗养生与女性客群"],
        "domain": "external",
        "stage": "evergreen",
        "secondary": ["product", "marketing"],
        "reason": "filename:行业/消费者研究",
    },
    {
        "patterns": ["分账、联合收单"],
        "domain": "finance",
        "stage": "preparation",
        "secondary": ["technology"],
        "reason": "filename:分账/联合收单",
    },
    {
        "patterns": ["desktop.zip"],
        "domain": "external",
        "stage": "preparation",
        "secondary": ["brand", "product", "competitor"],
        "reason": "archive:uploaded_desktop_snapshot",
    },
]

EXTENSIONS_TEXT = {".md", ".txt", ".html", ".htm", ".pdf", ".docx", ".pptx", ".xls", ".csv"}
EXTENSIONS_IMAGE = {".jpg", ".jpeg", ".png", ".webp"}
EXTENSIONS_ARCHIVE = {".zip"}

_OCR_ENGINE: Any = None


def get_ocr_engine() -> Any:
    global _OCR_ENGINE
    if RapidOCR is None:
        return None
    if _OCR_ENGINE is None:
        _OCR_ENGINE = RapidOCR()
    return _OCR_ENGINE


@dataclass
class Extracted:
    parser: str
    text: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    status: str = "extracted"


def rel(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def run_command(args: list[str], timeout: int = 120) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            args,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired as error:
        stdout = error.stdout if isinstance(error.stdout, str) else ""
        stderr = error.stderr if isinstance(error.stderr, str) else ""
        return 124, stdout, stderr or f"timeout after {timeout}s"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha1_text(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", errors="ignore")).hexdigest()


def clean_text(text: str) -> str:
    text = html.unescape(text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[\u0000-\u0008\u000b\u000c\u000e-\u001f]", " ", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    return text.strip()


def safe_read_text(path: Path) -> str:
    for encoding in ("utf-8", "utf-8-sig", "gb18030", "gbk", "latin1"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_bytes().decode("utf-8", errors="ignore")


def strip_ns(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def xml_text_from_paragraph(node: ElementTree.Element) -> str:
    parts: list[str] = []
    for item in node.iter():
        tag = strip_ns(item.tag)
        if tag == "t" and item.text:
            parts.append(item.text)
        elif tag == "tab":
            parts.append("\t")
        elif tag in {"br", "cr"}:
            parts.append("\n")
    return "".join(parts).strip()


def extract_docx(path: Path) -> Extracted:
    texts: list[str] = []
    warnings: list[str] = []
    metadata: dict[str, Any] = {}
    xml_names: list[str] = []
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        xml_names = [
            name
            for name in names
            if name.startswith("word/")
            and name.endswith(".xml")
            and (
                name == "word/document.xml"
                or name.startswith("word/header")
                or name.startswith("word/footer")
                or name.startswith("word/footnotes")
                or name.startswith("word/endnotes")
                or name.startswith("word/comments")
            )
        ]
        for name in xml_names:
            try:
                root = ElementTree.fromstring(archive.read(name))
            except Exception as error:
                warnings.append(f"xml_parse_failed:{name}:{error}")
                continue
            paragraphs = []
            for node in root.iter():
                if strip_ns(node.tag) == "p":
                    para = xml_text_from_paragraph(node)
                    if para:
                        paragraphs.append(para)
            if paragraphs:
                texts.append(f"## {name}\n" + "\n".join(paragraphs))
    metadata["xml_parts"] = xml_names
    text = clean_text("\n\n".join(texts))
    if not text:
        warnings.append("docx_text_empty")
    return Extracted(parser="docx_xml", text=text, metadata=metadata, warnings=warnings)


def slide_sort_key(name: str) -> tuple[int, str]:
    match = re.search(r"slide(\d+)\.xml$", name)
    return (int(match.group(1)) if match else 10**9, name)


def extract_pptx(path: Path) -> Extracted:
    sections: list[str] = []
    warnings: list[str] = []
    metadata: dict[str, Any] = {}
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        slides = sorted(
            [name for name in names if name.startswith("ppt/slides/slide") and name.endswith(".xml")],
            key=slide_sort_key,
        )
        notes = sorted(
            [name for name in names if name.startswith("ppt/notesSlides/notesSlide") and name.endswith(".xml")],
            key=slide_sort_key,
        )
        metadata["slide_count"] = len(slides)
        metadata["notes_count"] = len(notes)
        metadata["media_count"] = len([name for name in names if name.startswith("ppt/media/")])
        for idx, name in enumerate(slides, start=1):
            try:
                root = ElementTree.fromstring(archive.read(name))
            except Exception as error:
                warnings.append(f"xml_parse_failed:{name}:{error}")
                continue
            parts = [node.text for node in root.iter() if strip_ns(node.tag) == "t" and node.text]
            if parts:
                sections.append(f"## Slide {idx}\n" + "\n".join(parts))
        for idx, name in enumerate(notes, start=1):
            try:
                root = ElementTree.fromstring(archive.read(name))
            except Exception:
                continue
            parts = [node.text for node in root.iter() if strip_ns(node.tag) == "t" and node.text]
            if parts:
                sections.append(f"## Notes {idx}\n" + "\n".join(parts))
    text = clean_text("\n\n".join(sections))
    if not text:
        warnings.append("pptx_text_empty")
    return Extracted(parser="pptx_xml", text=text, metadata=metadata, warnings=warnings)


def extract_pdf(path: Path) -> Extracted:
    warnings: list[str] = []
    metadata: dict[str, Any] = {}
    if shutil.which("pdfinfo"):
        code, out, err = run_command(["pdfinfo", str(path)], timeout=60)
        if code == 0:
            for line in out.splitlines():
                if ":" not in line:
                    continue
                key, value = line.split(":", 1)
                key = key.strip().lower().replace(" ", "_")
                metadata[key] = value.strip()
        elif err.strip():
            warnings.append(f"pdfinfo_failed:{err.strip()[:180]}")
    text = ""
    if shutil.which("pdftotext"):
        code, out, err = run_command(["pdftotext", "-layout", "-enc", "UTF-8", str(path), "-"], timeout=180)
        if code == 0:
            text = out
        else:
            warnings.append(f"pdftotext_failed:{err.strip()[:180]}")
    else:
        warnings.append("pdftotext_missing")
    if shutil.which("pdfimages"):
        code, out, err = run_command(["pdfimages", "-list", str(path)], timeout=120)
        if code == 0:
            image_lines = [line for line in out.splitlines() if re.match(r"^\s*\d+", line)]
            metadata["embedded_image_count"] = len(image_lines)
        elif err.strip():
            warnings.append(f"pdfimages_failed:{err.strip()[:180]}")
    text = clean_text(text)
    if not text:
        warnings.append("pdf_text_empty_or_scanned_needs_ocr")
    return Extracted(parser="pdftotext", text=text, metadata=metadata, warnings=warnings)


def extract_html(path: Path) -> Extracted:
    raw = safe_read_text(path)
    metadata: dict[str, Any] = {}
    if BeautifulSoup:
        soup = BeautifulSoup(raw, "lxml")
        if soup.title and soup.title.string:
            metadata["html_title"] = soup.title.string.strip()
        for node in soup(["script", "style", "noscript"]):
            node.extract()
        text = soup.get_text("\n")
    else:
        text = re.sub(r"<[^>]+>", " ", raw)
    return Extracted(parser="html_bs4" if BeautifulSoup else "html_regex", text=clean_text(text), metadata=metadata)


def filter_strings_output(value: str) -> str:
    lines: list[str] = []
    for line in value.splitlines():
        line = line.strip()
        if len(line) < 2:
            continue
        if re.fullmatch(r"[A-Za-z0-9_.$/\\:-]{1,8}", line):
            continue
        lines.append(line)
    seen: set[str] = set()
    deduped: list[str] = []
    for line in lines:
        if line in seen:
            continue
        seen.add(line)
        deduped.append(line)
    return "\n".join(deduped)


def extract_xls(path: Path) -> Extracted:
    warnings: list[str] = []
    outputs: list[str] = []
    if not shutil.which("strings"):
        return Extracted(parser="xls_strings", warnings=["strings_missing"], status="needs_review")
    for args in (["strings", "-n", "2", "-e", "l", str(path)], ["strings", "-n", "3", str(path)]):
        code, out, err = run_command(args, timeout=60)
        if code == 0 and out.strip():
            outputs.append(out)
        elif err.strip():
            warnings.append(f"strings_failed:{err.strip()[:160]}")
    text = clean_text(filter_strings_output("\n".join(outputs)))
    if not text:
        warnings.append("xls_text_low_confidence")
    else:
        warnings.append("xls_extracted_with_strings_low_structure")
    return Extracted(parser="xls_strings", text=text, warnings=warnings)


def prepare_ocr_tiles(path: Path, metadata: dict[str, Any], warnings: list[str]) -> list[Path]:
    if Image is None or ImageOps is None:
        return [path]
    try:
        image = Image.open(path)
        image = ImageOps.exif_transpose(image).convert("RGB")
    except Exception as error:
        warnings.append(f"image_ocr_prepare_failed:{type(error).__name__}:{error}")
        return [path]

    max_width = 900
    if image.width > max_width:
        new_height = max(1, int(image.height * (max_width / image.width)))
        image = image.resize((max_width, new_height))
        metadata["ocr_resized_to"] = {"width": image.width, "height": image.height}

    tile_height = 2200
    overlap = 120
    max_tiles = 5
    if image.height <= tile_height:
        tmp = Path(tempfile.mkdtemp(prefix="hxy-ocr-"))
        out = tmp / "tile-001.jpg"
        image.save(out, quality=90)
        metadata["ocr_tile_count"] = 1
        return [out]

    tmp = Path(tempfile.mkdtemp(prefix="hxy-ocr-"))
    tiles: list[Path] = []
    start = 0
    index = 1
    while start < image.height and len(tiles) < max_tiles:
        end = min(image.height, start + tile_height)
        tile = image.crop((0, start, image.width, end))
        out = tmp / f"tile-{index:03d}.jpg"
        tile.save(out, quality=90)
        tiles.append(out)
        if end >= image.height:
            break
        start = max(0, end - overlap)
        index += 1
    metadata["ocr_tile_count"] = len(tiles)
    if start < image.height and len(tiles) >= max_tiles:
        warnings.append(f"image_ocr_truncated_after_{max_tiles}_tiles")
    return tiles


def extract_image(path: Path, image_ocr_mode: str = "metadata") -> Extracted:
    metadata: dict[str, Any] = {}
    warnings: list[str] = []
    if Image:
        try:
            with Image.open(path) as image:
                metadata.update(
                    {
                        "width": image.width,
                        "height": image.height,
                        "mode": image.mode,
                        "format": image.format,
                    }
                )
                metadata["has_alpha"] = image.mode in {"RGBA", "LA"} or ("transparency" in image.info)
                exif = getattr(image, "getexif", lambda: {})()
                if exif:
                    metadata["exif_keys"] = len(exif)
        except Exception as error:
            warnings.append(f"image_probe_failed:{error}")
    else:
        warnings.append("pillow_missing")
    visual_lines = [
        "图片资料，已记录图像元信息；若 OCR 可用会附加可见文字。",
        f"文件名：{path.name}",
        f"父级目录：{path.parent.name}",
    ]
    if metadata:
        visual_lines.append("图像元信息：" + json.dumps(metadata, ensure_ascii=False, sort_keys=True))

    ocr_texts: list[str] = []
    ocr_scores: list[float] = []
    ocr_engine = get_ocr_engine() if image_ocr_mode != "metadata" else None
    if ocr_engine is None:
        warnings.append("image_ocr_not_run_indexed_by_metadata")
    else:
        try:
            elapsed_by_tile: list[Any] = []
            tiles = prepare_ocr_tiles(path, metadata, warnings)
            temp_dirs = {tile.parent for tile in tiles if tile.parent.name.startswith("hxy-ocr-")}
            try:
                for tile in tiles:
                    result, elapsed = ocr_engine(str(tile))
                    elapsed_by_tile.append(elapsed)
                    for item in result or []:
                        if len(item) < 3:
                            continue
                        text = str(item[1]).strip()
                        try:
                            score = float(item[2])
                        except Exception:
                            score = 0.0
                        if text and score >= 0.45:
                            ocr_texts.append(text)
                            ocr_scores.append(score)
            finally:
                for directory in temp_dirs:
                    shutil.rmtree(directory, ignore_errors=True)
            metadata["ocr_elapsed"] = elapsed_by_tile
            metadata["ocr_line_count"] = len(ocr_texts)
            if ocr_scores:
                metadata["ocr_avg_confidence"] = round(sum(ocr_scores) / len(ocr_scores), 4)
        except Exception as error:
            warnings.append(f"image_ocr_failed:{type(error).__name__}:{error}")

    if ocr_texts:
        visual_lines[0] = "图片资料，已使用 RapidOCR 识别可见文字。"
        visual_lines.extend(["OCR 识别文本：", *ocr_texts])
        status = "extracted"
        parser = "image_metadata_rapidocr"
    else:
        warnings.append("image_ocr_empty_needs_visual_review")
        status = "needs_review"
        parser = "image_metadata"
    return Extracted(parser=parser, text="\n".join(visual_lines), metadata=metadata, warnings=warnings, status=status)


def extract_zip(path: Path) -> Extracted:
    warnings: list[str] = []
    metadata: dict[str, Any] = {}
    lines: list[str] = []
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            files = [info for info in infos if not info.is_dir()]
            metadata["archive_file_count"] = len(files)
            metadata["archive_total_uncompressed_bytes"] = sum(info.file_size for info in files)
            by_ext = Counter(Path(info.filename).suffix.lower() or "[no_ext]" for info in files)
            metadata["archive_extension_counts"] = dict(sorted(by_ext.items()))
            lines.append("ZIP 压缩包清单：")
            for info in infos[:500]:
                marker = "dir" if info.is_dir() else "file"
                lines.append(f"- {marker}: {info.filename} ({info.file_size} bytes)")
            if len(infos) > 500:
                lines.append(f"- ... omitted {len(infos) - 500} entries")
    except Exception as error:
        warnings.append(f"zip_list_failed:{error}")
    return Extracted(parser="zip_manifest", text=clean_text("\n".join(lines)), metadata=metadata, warnings=warnings)


def extract_file(path: Path, image_ocr_mode: str = "metadata") -> Extracted:
    ext = path.suffix.lower()
    try:
        if ext in {".md", ".txt", ".csv"}:
            return Extracted(parser="plain_text", text=clean_text(safe_read_text(path)))
        if ext in {".html", ".htm"}:
            return extract_html(path)
        if ext == ".pdf":
            return extract_pdf(path)
        if ext == ".docx":
            return extract_docx(path)
        if ext == ".pptx":
            return extract_pptx(path)
        if ext == ".xls":
            return extract_xls(path)
        if ext in EXTENSIONS_IMAGE:
            return extract_image(path, image_ocr_mode=image_ocr_mode)
        if ext in EXTENSIONS_ARCHIVE:
            return extract_zip(path)
        return Extracted(parser="unsupported", warnings=["unsupported_file_type"], status="skipped")
    except Exception as error:
        return Extracted(parser="failed", warnings=[f"extract_failed:{type(error).__name__}:{error}"], status="failed")


def score_keywords(corpus: str, keywords: list[str]) -> tuple[int, list[str]]:
    lower = corpus.lower()
    score = 0
    hits: list[str] = []
    for keyword in keywords:
        key = keyword.lower()
        count = lower.count(key)
        if count:
            weight = 4 if key in lower[:1000] else 1
            score += min(count, 8) * weight
            hits.append(keyword)
    return score, hits


def classify(relative_path: str, extracted: Extracted) -> dict[str, Any]:
    corpus = f"{relative_path}\n{Path(relative_path).name}\n{extracted.text[:12000]}"
    normalized_path = relative_path.lower()

    for rule in EXPLICIT_CLASSIFICATION_RULES:
        for pattern in rule["patterns"]:
            if pattern.lower() in normalized_path:
                domain = rule["domain"]
                stage = rule["stage"]
                return {
                    "domain": domain,
                    "domain_label": DOMAINS[domain],
                    "secondary_domains": rule.get("secondary", []),
                    "stage": stage,
                    "stage_label": STAGES[stage],
                    "confidence": 0.97,
                    "reasons": [f"explicit:{rule['reason']}"],
                    "domain_scores": {},
                    "stage_scores": {},
                }

    domain_scores: dict[str, int] = {}
    domain_hits: dict[str, list[str]] = {}
    for domain, keywords in DOMAIN_KEYWORDS.items():
        score, hits = score_keywords(corpus, keywords)
        domain_scores[domain] = score
        domain_hits[domain] = hits

    stage_scores: dict[str, int] = {}
    stage_hits: dict[str, list[str]] = {}
    for stage, keywords in STAGE_KEYWORDS.items():
        score, hits = score_keywords(corpus, keywords)
        stage_scores[stage] = score
        stage_hits[stage] = hits

    ext = Path(relative_path).suffix.lower()

    if "参考品牌" in relative_path or any(brand in relative_path for brand in ["奈晚", "帮大爷", "方松院", "满足里", "谷小推", "长风拨筋", "麦悠悠"]):
        domain_scores["competitor"] += 80
        domain_hits["competitor"].append("path:参考品牌/竞品品牌")
        stage_scores["preparation"] += 20
        stage_hits["preparation"].append("path:参考品牌")

    if any(token in relative_path for token in ["合同", "协议", "股东合作"]):
        domain_scores["legal"] += 80
        domain_hits["legal"].append("path:合同/协议")
        stage_scores["preparation"] += 20
        stage_hits["preparation"].append("path:合同/协议")

    if any(token in relative_path for token in ["支付系统", "O2O系统", "IoT", "AI交互", "小程序"]):
        domain_scores["technology"] += 45
        domain_hits["technology"].append("path:系统/AI/IoT")

    if any(token in relative_path for token in ["菜单", "泡脚", "SPU", "SKU", "项目介绍", "产品"]):
        domain_scores["product"] += 35
        domain_hits["product"].append("path:产品/菜单/项目")

    if any(token in relative_path for token in ["小店模型", "门店模型", "单店研讨", "模型具象化"]):
        domain_scores["store_model"] += 45
        domain_hits["store_model"].append("path:门店/单店模型")
        stage_scores["pilot"] += 20
        stage_hits["pilot"].append("path:单店/小店模型")

    if any(token in relative_path for token in ["商业计划书", "融资", "天使轮", "报价单", "分账", "联合收单"]):
        domain_scores["finance"] += 45
        domain_hits["finance"].append("path:财务/融资/支付")

    if any(token in relative_path for token in ["品牌", "定位", "hxyip", "设计报价"]):
        domain_scores["brand"] += 35
        domain_hits["brand"].append("path:品牌/定位/IP")

    if any(token in relative_path for token in ["万店"]):
        stage_scores["10000_stores"] += 80
        stage_hits["10000_stores"].append("path:万店")

    if any(token in relative_path for token in ["多门店", "连锁", "总部"]):
        stage_scores["chain"] += 45
        stage_hits["chain"].append("path:连锁/多门店/总部")

    if ext in EXTENSIONS_IMAGE and "hxyip" in normalized_path:
        domain_scores["brand"] += 70
        domain_hits["brand"].append("path:hxyip")
        stage_scores["preparation"] += 20
        stage_hits["preparation"].append("image:hxyip")

    domain_rank = sorted(domain_scores.items(), key=lambda item: (-item[1], item[0]))
    stage_rank = sorted(stage_scores.items(), key=lambda item: (-item[1], item[0]))
    domain = domain_rank[0][0] if domain_rank and domain_rank[0][1] > 0 else "external"
    stage = stage_rank[0][0] if stage_rank and stage_rank[0][1] > 0 else "evergreen"
    secondary = [item[0] for item in domain_rank[1:4] if item[1] > 0]
    domain_score = domain_scores.get(domain, 0)
    stage_score = stage_scores.get(stage, 0)
    confidence = min(0.97, max(0.25, (domain_score + stage_score) / 90))
    if domain_score >= 60:
        confidence = max(confidence, 0.85)
    elif domain_score >= 30:
        confidence = max(confidence, 0.65)

    reasons = []
    if domain_hits.get(domain):
        reasons.extend([f"domain:{hit}" for hit in domain_hits[domain][:8]])
    if stage_hits.get(stage):
        reasons.extend([f"stage:{hit}" for hit in stage_hits[stage][:8]])
    if not reasons:
        reasons.append("fallback:insufficient_keywords")

    return {
        "domain": domain,
        "domain_label": DOMAINS[domain],
        "secondary_domains": secondary,
        "stage": stage,
        "stage_label": STAGES[stage],
        "confidence": round(confidence, 3),
        "reasons": reasons,
        "domain_scores": domain_scores,
        "stage_scores": stage_scores,
    }


def clamp_score(value: float) -> float:
    return round(max(0.0, min(1.0, value)), 3)


def quality_grade(overall: float) -> str:
    if overall >= 0.85:
        return "A"
    if overall >= 0.7:
        return "B"
    if overall >= 0.55:
        return "C"
    if overall >= 0.4:
        return "D"
    return "E"


def score_asset_quality(
    relative_path: str,
    extracted: Extracted,
    classification: dict[str, Any],
    duplicate_of: str | None,
    mtime: str,
) -> dict[str, Any]:
    text = extracted.text or ""
    lower_path = relative_path.lower()
    warnings = extracted.warnings or []
    char_count = len(text)
    dimensions: dict[str, float] = {}
    reasons: dict[str, list[str]] = defaultdict(list)

    dimensions["classification_confidence"] = clamp_score(float(classification.get("confidence") or 0.0))
    if classification.get("reasons"):
        reasons["classification_confidence"].extend(classification["reasons"][:8])
    if dimensions["classification_confidence"] < 0.45:
        reasons["classification_confidence"].append("low_confidence_requires_manual_review")

    extraction_score = 0.25
    if extracted.status == "extracted":
        extraction_score += 0.25
    if char_count >= 12000:
        extraction_score += 0.3
    elif char_count >= 3000:
        extraction_score += 0.22
    elif char_count >= 500:
        extraction_score += 0.12
    elif char_count > 0:
        extraction_score += 0.05
    if any("ocr_empty" in warning or "not_run" in warning for warning in warnings):
        extraction_score -= 0.35
        reasons["extraction_quality"].append("image_without_reliable_ocr")
    if any("low_structure" in warning or "low_confidence" in warning for warning in warnings):
        extraction_score -= 0.15
        reasons["extraction_quality"].append("low_structure_or_low_confidence_extraction")
    if not warnings:
        extraction_score += 0.1
        reasons["extraction_quality"].append("clean_extraction")
    reasons["extraction_quality"].append(f"char_count:{char_count}")
    dimensions["extraction_quality"] = clamp_score(extraction_score)

    business_keywords = [
        "品牌定位",
        "核心定位",
        "泡脚",
        "一人一方",
        "功效",
        "小店模型",
        "坪效",
        "复购",
        "spu",
        "sku",
        "万店",
        "加盟",
        "融资",
        "回本",
        "技师",
        "排班",
    ]
    business_hits = [keyword for keyword in business_keywords if keyword.lower() in (lower_path + "\n" + text.lower())]
    business_score = 0.25 + min(0.5, len(business_hits) * 0.07)
    if classification.get("domain") in {"brand", "product", "store_model", "operations", "finance", "franchise"}:
        business_score += 0.15
        reasons["business_value"].append(f"core_domain:{classification.get('domain')}")
    if business_hits:
        reasons["business_value"].extend([f"keyword:{hit}" for hit in business_hits[:8]])
    if "参考品牌" in relative_path or classification.get("domain") == "competitor":
        business_score -= 0.05
        reasons["business_value"].append("competitor_reference_less_authoritative_for_hxy_decision")
    dimensions["business_value"] = clamp_score(business_score)

    authority_score = 0.5
    if "荷小悦" in relative_path or "hxy" in lower_path:
        authority_score += 0.2
        reasons["authority"].append("hxy_owned_source_path")
    if classification.get("domain") in {"brand", "product", "store_model", "operations", "finance", "franchise", "technology", "legal"}:
        authority_score += 0.12
        reasons["authority"].append(f"owned_operating_domain:{classification.get('domain')}")
    if "参考品牌" in relative_path or classification.get("domain") == "competitor":
        authority_score -= 0.25
        reasons["authority"].append("competitor_or_reference_material")
    if duplicate_of:
        authority_score -= 0.1
        reasons["authority"].append("duplicate_binary_file")
    dimensions["authority"] = clamp_score(authority_score)

    recency_score = 0.55
    if any(token in relative_path for token in ["2026", "202605", "202604"]):
        recency_score += 0.25
        reasons["recency"].append("recent_2026_source_signal")
    if classification.get("stage") in {"preparation", "pilot"}:
        recency_score += 0.08
        reasons["recency"].append(f"active_stage:{classification.get('stage')}")
    if classification.get("stage") == "evergreen":
        recency_score += 0.05
        reasons["recency"].append("evergreen_material")
    if mtime:
        reasons["recency"].append(f"mtime:{mtime}")
    dimensions["recency"] = clamp_score(recency_score)

    conflict_score = 0.85
    conflict_terms = ["待确认", "不确定", "草案", "初步", "v1", "v2", "claude", "优化版"]
    found_conflict_terms = [term for term in conflict_terms if term.lower() in (lower_path + "\n" + text.lower())]
    if duplicate_of:
        conflict_score -= 0.1
    if found_conflict_terms:
        conflict_score -= min(0.25, len(found_conflict_terms) * 0.04)
        reasons["conflict_safety"].extend([f"version_or_uncertainty:{term}" for term in found_conflict_terms[:6]])
    if not found_conflict_terms and not duplicate_of:
        reasons["conflict_safety"].append("no_obvious_version_or_conflict_signal")
    dimensions["conflict_safety"] = clamp_score(conflict_score)

    answerability_score = 0.2
    if char_count >= 500:
        answerability_score += 0.2
    if char_count >= 3000:
        answerability_score += 0.15
    if dimensions["extraction_quality"] >= 0.7:
        answerability_score += 0.15
    if dimensions["classification_confidence"] >= 0.7:
        answerability_score += 0.1
    if business_hits:
        answerability_score += min(0.2, len(business_hits) * 0.03)
    if extracted.status == "needs_review":
        answerability_score -= 0.2
        reasons["answerability"].append("needs_review_asset")
    if business_hits:
        reasons["answerability"].extend([f"answer_keyword:{hit}" for hit in business_hits[:6]])
    reasons["answerability"].append(f"char_count:{char_count}")
    dimensions["answerability"] = clamp_score(answerability_score)

    weights = {
        "classification_confidence": 0.14,
        "extraction_quality": 0.18,
        "business_value": 0.2,
        "authority": 0.16,
        "recency": 0.08,
        "conflict_safety": 0.1,
        "answerability": 0.14,
    }
    overall = clamp_score(sum(dimensions[key] * weight for key, weight in weights.items()))
    recommended_action = "approve"
    if overall < 0.55 or extracted.status == "needs_review" or dimensions["extraction_quality"] < 0.45:
        recommended_action = "review"
    if overall < 0.4:
        recommended_action = "repair"

    return {
        "version": "hxy-quality-score.v1",
        "overall": overall,
        "grade": quality_grade(overall),
        "dimensions": dimensions,
        "weights": weights,
        "reasons": dict(reasons),
        "recommended_action": recommended_action,
    }


def mime_type(path: Path) -> str:
    if shutil.which("file"):
        code, out, _ = run_command(["file", "--mime-type", "-b", str(path)], timeout=30)
        if code == 0 and out.strip():
            return out.strip()
    return mimetypes.guess_type(path.name)[0] or "application/octet-stream"


def slug(value: str, max_len: int = 96) -> str:
    value = re.sub(r"[\\/:*?\"<>|]+", "-", value)
    value = re.sub(r"\s+", "-", value.strip())
    value = re.sub(r"-+", "-", value)
    value = value.strip(".-")
    return value[:max_len] or "untitled"


def markdown_escape(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def render_normalized_markdown(asset: dict[str, Any], extracted: Extracted) -> str:
    meta_lines = [
        f"- asset_id: {asset['asset_id']}",
        f"- source_path: {asset['relative_path']}",
        f"- file_name: {asset['file_name']}",
        f"- file_size: {asset['file_size']}",
        f"- sha256: {asset['sha256']}",
        f"- mime_type: {asset['mime_type']}",
        f"- parser: {asset['parser']}",
        f"- knowledge_domain: {asset['knowledge_domain']}",
        f"- knowledge_domain_label: {asset['knowledge_domain_label']}",
        f"- project_stage: {asset['project_stage']}",
        f"- project_stage_label: {asset['project_stage_label']}",
        f"- classification_confidence: {asset['classification_confidence']}",
    ]
    if asset.get("duplicate_of"):
        meta_lines.append(f"- duplicate_of: {asset['duplicate_of']}")
    if asset.get("secondary_domains"):
        meta_lines.append(f"- secondary_domains: {', '.join(asset['secondary_domains'])}")
    if asset.get("quality_scores"):
        meta_lines.append(f"- quality_score: {asset['quality_scores'].get('overall')}")
        meta_lines.append(f"- quality_grade: {asset['quality_scores'].get('grade')}")
        meta_lines.append(f"- quality_recommended_action: {asset['quality_scores'].get('recommended_action')}")
    if extracted.warnings:
        meta_lines.append(f"- warnings: {'; '.join(extracted.warnings)}")
    if extracted.metadata:
        meta_lines.append(f"- extracted_metadata: {json.dumps(extracted.metadata, ensure_ascii=False, sort_keys=True)}")

    body = extracted.text.strip()
    if not body:
        body = "_未抽取到可索引正文；请查看原始文件或后续补 OCR/人工摘要。_"

    return "\n".join(
        [
            f"# {asset['title']}",
            "",
            "## Source Metadata",
            "",
            *meta_lines,
            "",
            "## Classification Reasons",
            "",
            *[f"- {reason}" for reason in asset["classification_reasons"]],
            "",
            "## Extracted Content",
            "",
            body,
            "",
        ]
    )


def chunk_text(text: str, chunk_size: int = 1200, overlap: int = 160) -> list[str]:
    text = clean_text(text)
    if not text:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + chunk_size)
        chunks.append(text[start:end])
        if end >= len(text):
            break
        start = max(0, end - overlap)
    return chunks


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def make_symlink(original: Path, link: Path) -> None:
    link.parent.mkdir(parents=True, exist_ok=True)
    if link.exists() or link.is_symlink():
        if link.is_symlink():
            link.unlink()
        else:
            stem = link.stem
            suffix = link.suffix
            for index in range(2, 999):
                candidate = link.with_name(f"{stem}-{index}{suffix}")
                if not candidate.exists() and not candidate.is_symlink():
                    link = candidate
                    break
    target = os.path.relpath(original, link.parent)
    os.symlink(target, link)


def create_contact_sheets(root: Path, images: list[dict[str, Any]], report_dir: Path) -> list[dict[str, Any]]:
    if not Image or not ImageOps:
        return []
    sheet_dir = report_dir / "assets" / "inbox-contact-sheets"
    sheet_dir.mkdir(parents=True, exist_ok=True)
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for asset in images:
        path_parts = Path(asset["relative_path"]).parts
        group = "misc"
        if "参考品牌" in path_parts:
            idx = path_parts.index("参考品牌")
            group = f"参考品牌-{path_parts[idx + 1]}" if idx + 1 < len(path_parts) else "参考品牌"
        elif "荷小悦相关" in path_parts:
            group = "荷小悦相关"
        elif "荷小悦资料" in path_parts:
            group = "荷小悦资料"
        if "hxyip" in asset["file_name"].lower():
            group = "荷小悦IP"
        groups[group].append(asset)

    outputs: list[dict[str, Any]] = []
    for group, items in sorted(groups.items()):
        cols = 5
        thumb_w, thumb_h = 220, 160
        label_h = 32
        rows = (len(items) + cols - 1) // cols
        sheet = Image.new("RGB", (cols * thumb_w, rows * (thumb_h + label_h)), "white")
        for idx, asset in enumerate(items):
            src = root / asset["relative_path"]
            row, col = divmod(idx, cols)
            x, y = col * thumb_w, row * (thumb_h + label_h)
            try:
                with Image.open(src) as image:
                    image = ImageOps.exif_transpose(image).convert("RGB")
                    image.thumbnail((thumb_w, thumb_h))
                    px = x + (thumb_w - image.width) // 2
                    py = y + (thumb_h - image.height) // 2
                    sheet.paste(image, (px, py))
            except Exception:
                continue
        out = sheet_dir / f"{slug(group)}.jpg"
        sheet.save(out, quality=88)
        outputs.append(
            {
                "group": group,
                "count": len(items),
                "path": rel(out, root),
            }
        )
    return outputs


def cleanup_previous_run(root: Path, structured_root: Path, classified_root: Path, run_name: str) -> None:
    previous_manifest = structured_root / f"hxy-inbox-manifest-{run_name}.json"
    if previous_manifest.exists():
        try:
            payload = json.loads(previous_manifest.read_text(encoding="utf-8"))
            for asset in payload.get("assets", []):
                normalized_path = asset.get("normalized_path")
                if not isinstance(normalized_path, str):
                    continue
                candidate = (root / normalized_path).resolve()
                try:
                    candidate.relative_to(root)
                except ValueError:
                    continue
                if candidate.is_file() and "knowledge/normalized/" in normalized_path:
                    candidate.unlink()
        except Exception as error:
            print(f"warning: previous manifest cleanup skipped: {error}", file=sys.stderr)
    if classified_root.exists():
        try:
            classified_root.relative_to(root / "knowledge" / "raw" / "classified")
            shutil.rmtree(classified_root)
        except Exception as error:
            print(f"warning: classified cleanup skipped: {error}", file=sys.stderr)


def build_report(
    root: Path,
    generated_at: str,
    run_name: str,
    assets: list[dict[str, Any]],
    duplicates: list[dict[str, Any]],
    contact_sheets: list[dict[str, Any]],
) -> str:
    total_size = sum(asset["file_size"] for asset in assets)
    by_ext = Counter(asset["extension"] or "[no_ext]" for asset in assets)
    by_domain = Counter(asset["knowledge_domain"] for asset in assets)
    by_stage = Counter(asset["project_stage"] for asset in assets)
    by_status = Counter(asset["status"] for asset in assets)
    by_quality_grade = Counter((asset.get("quality_scores") or {}).get("grade", "unknown") for asset in assets)
    by_quality_action = Counter((asset.get("quality_scores") or {}).get("recommended_action", "unknown") for asset in assets)
    indexed = sum(1 for asset in assets if asset["char_count"] > 0)
    needs_review = [asset for asset in assets if asset["status"] in {"needs_review", "failed", "skipped"} or asset["warnings"]]

    def counter_table(counter: Counter[str], labels: dict[str, str] | None = None) -> list[str]:
        lines = ["| 项 | 数量 |", "|---|---:|"]
        for key, count in counter.most_common():
            label = f"{key} / {labels[key]}" if labels and key in labels else key
            lines.append(f"| {markdown_escape(label)} | {count} |")
        return lines

    top_assets = sorted(assets, key=lambda item: item["char_count"], reverse=True)[:20]
    lines = [
        "# HXY Inbox 知识库归类报告",
        "",
        f"- generated_at: {generated_at}",
        f"- run: {run_name}",
        f"- source_dir: knowledge/raw/inbox",
        f"- total_files: {len(assets)}",
        f"- total_size_mb: {total_size / 1024 / 1024:.2f}",
        f"- indexed_files_with_text_or_metadata: {indexed}",
        f"- duplicate_binary_files: {sum(len(group['duplicates']) for group in duplicates)}",
        "",
        "## 输出位置",
        "",
        "- 标准化 Markdown：`knowledge/normalized/<domain>/<stage>/`",
        f"- 原始资料分类软链接：`knowledge/raw/classified/{run_name}/`",
        f"- 结构化清单：`knowledge/structured/hxy-inbox-manifest-{run_name}.json`",
        f"- 搜索分块：`knowledge/structured/hxy-inbox-search-index-{run_name}.json`",
        f"- CSV 清单：`data/exports/hxy-inbox-knowledge-assets-{run_name}.csv`",
        "",
        "## 文件类型",
        "",
        *counter_table(by_ext),
        "",
        "## 知识域分布",
        "",
        *counter_table(by_domain, DOMAINS),
        "",
        "## 阶段分布",
        "",
        *counter_table(by_stage, STAGES),
        "",
        "## 处理状态",
        "",
        *counter_table(by_status),
        "",
        "## 科学质量评分",
        "",
        "### 等级分布",
        "",
        *counter_table(by_quality_grade),
        "",
        "### 建议动作",
        "",
        *counter_table(by_quality_action),
        "",
        "评分维度：分类置信度、提取质量、业务价值、权威性、时效性、冲突安全性、可问答性。总分为 0-1，等级 A-E。",
        "",
        "## 正文/元数据最多的资料 Top 20",
        "",
        "| 文件 | 分类 | 阶段 | 字符数 |",
        "|---|---|---|---:|",
    ]
    for asset in top_assets:
        lines.append(
            f"| {markdown_escape(asset['relative_path'])} | {asset['knowledge_domain']} | {asset['project_stage']} | {asset['char_count']} |"
        )

    lines.extend(["", "## 重复文件", ""])
    if duplicates:
        for group in duplicates:
            lines.append(f"- sha256 `{group['sha256'][:12]}` 主文件：`{group['primary']}`")
            for duplicate in group["duplicates"]:
                lines.append(f"  - duplicate: `{duplicate}`")
    else:
        lines.append("- 未发现二进制完全重复文件。")

    lines.extend(["", "## 图片 Contact Sheets", ""])
    if contact_sheets:
        for sheet in contact_sheets:
            lines.append(f"- {sheet['group']} ({sheet['count']}): `{sheet['path']}`")
    else:
        lines.append("- 未生成；本地缺少 Pillow 或没有图片文件。")

    lines.extend(["", "## 需要复核", ""])
    if needs_review:
        lines.append("| 文件 | 状态 | 警告 |")
        lines.append("|---|---|---|")
        for asset in needs_review[:80]:
            warnings = "; ".join(asset["warnings"])[:220]
            lines.append(f"| {markdown_escape(asset['relative_path'])} | {asset['status']} | {markdown_escape(warnings)} |")
        if len(needs_review) > 80:
            lines.append(f"| ... | ... | 另有 {len(needs_review) - 80} 个条目，见 JSON manifest |")
    else:
        lines.append("- 暂无。")

    lines.extend(
        [
            "",
            "## 知识库使用建议",
            "",
            "1. 先用 `knowledge/reports/HXY-KNOWLEDGE-INDEX.md` 作为人工入口。",
            "2. 对图片、扫描型 PDF、品牌参考图补充 OCR 或人工摘要后，可重新运行本脚本。",
            "3. 决策类结论进入 `knowledge/structured/decision-log.md` 前，应引用本次 manifest 的原始路径和哈希。",
            "4. HXY 资料继续只放 `/root/hxy`，不要回写 `/root/htops`。",
            "",
        ]
    )
    return "\n".join(lines)


def build_knowledge_index(generated_at: str, run_name: str, assets: list[dict[str, Any]]) -> str:
    by_domain_stage: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for asset in assets:
        by_domain_stage[asset["knowledge_domain"]][asset["project_stage"]].append(asset)

    lines = [
        "# 荷小悦知识库入口",
        "",
        f"- updated_at: {generated_at}",
        f"- latest_inbox_run: {run_name}",
        "- source_boundary: `/root/hxy` only",
        "",
        "## 快速入口",
        "",
        f"- 本次归类报告：`knowledge/reports/hxy-inbox-knowledge-report-{run_name}.md`",
        f"- 本次结构化清单：`knowledge/structured/hxy-inbox-manifest-{run_name}.json`",
        f"- 本次搜索分块：`knowledge/structured/hxy-inbox-search-index-{run_name}.json`",
        "",
        "## 分类目录",
        "",
    ]
    for domain, label in DOMAINS.items():
        stages = by_domain_stage.get(domain)
        if not stages:
            continue
        total = sum(len(items) for items in stages.values())
        lines.extend([f"### {label} / {domain}", "", f"- files: {total}", ""])
        for stage, stage_label in STAGES.items():
            items = stages.get(stage)
            if not items:
                continue
            lines.append(f"#### {stage_label} / {stage}")
            lines.append("")
            for asset in sorted(items, key=lambda item: item["relative_path"]):
                normalized = asset.get("normalized_path") or ""
                suffix = f" -> `{normalized}`" if normalized else ""
                lines.append(f"- `{asset['relative_path']}`{suffix}")
            lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest HXY inbox knowledge files")
    parser.add_argument("--root", default=".", help="HXY repo root")
    parser.add_argument("--inbox", default="knowledge/raw/inbox", help="Inbox path relative to root")
    parser.add_argument("--run-name", default="", help="Stable run name, default inbox-YYYY-MM-DD")
    parser.add_argument(
        "--image-ocr",
        choices=["metadata", "rapidocr"],
        default="metadata",
        help="Image OCR mode. Default keeps image metadata/contact sheets only.",
    )
    args = parser.parse_args()

    root = Path(args.root).resolve()
    inbox = (root / args.inbox).resolve()
    if not inbox.exists():
        print(f"inbox not found: {inbox}", file=sys.stderr)
        return 2
    try:
        inbox.relative_to(root)
    except ValueError:
        print("inbox must be inside HXY root", file=sys.stderr)
        return 2

    generated_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    run_name = args.run_name or "inbox-2026-06-11"
    normalized_root = root / "knowledge" / "normalized"
    structured_root = root / "knowledge" / "structured"
    report_root = root / "knowledge" / "reports"
    classified_root = root / "knowledge" / "raw" / "classified" / run_name
    export_root = root / "data" / "exports"

    cleanup_previous_run(root, structured_root, classified_root, run_name)

    files = sorted([path for path in inbox.rglob("*") if path.is_file()], key=lambda item: item.as_posix())
    assets: list[dict[str, Any]] = []
    extracts_by_asset: dict[str, Extracted] = {}
    seen_sha: dict[str, str] = {}

    for index, path in enumerate(files, start=1):
        relative_path = rel(path, root)
        file_hash = sha256_file(path)
        extracted = extract_file(path, image_ocr_mode=args.image_ocr)
        classification = classify(relative_path, extracted)
        stat = path.stat()
        title = path.stem
        asset_id = f"hxy-inbox:{file_hash[:16]}"
        normal_name = f"{slug(title)}-{file_hash[:8]}.md"
        normalized_path = normalized_root / classification["domain"] / classification["stage"] / normal_name
        classified_link = classified_root / classification["domain"] / classification["stage"] / f"{file_hash[:8]}-{slug(path.name, 120)}"
        duplicate_of = seen_sha.get(file_hash)
        if not duplicate_of:
            seen_sha[file_hash] = relative_path

        status = extracted.status
        if extracted.warnings and status == "extracted":
            status = "needs_review" if any("empty" in item or "ocr" in item or "low_confidence" in item for item in extracted.warnings) else "extracted"
        if extracted.parser == "unsupported":
            status = "skipped"
        if classification["confidence"] < 0.45 and status == "extracted":
            status = "needs_review"
        quality_scores = score_asset_quality(
            relative_path,
            extracted,
            classification,
            duplicate_of=duplicate_of,
            mtime=datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(timespec="seconds"),
        )

        asset: dict[str, Any] = {
            "asset_id": asset_id,
            "ordinal": index,
            "file_name": path.name,
            "title": title,
            "relative_path": relative_path,
            "extension": path.suffix.lower(),
            "file_size": stat.st_size,
            "mtime": datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(timespec="seconds"),
            "sha256": file_hash,
            "duplicate_of": duplicate_of,
            "mime_type": mime_type(path),
            "parser": extracted.parser,
            "status": status,
            "warnings": extracted.warnings,
            "metadata": extracted.metadata,
            "char_count": len(extracted.text),
            "content_sha1": sha1_text(extracted.text) if extracted.text else "",
            "knowledge_domain": classification["domain"],
            "knowledge_domain_label": classification["domain_label"],
            "secondary_domains": classification["secondary_domains"],
            "project_stage": classification["stage"],
            "project_stage_label": classification["stage_label"],
            "classification_confidence": classification["confidence"],
            "classification_reasons": classification["reasons"],
            "quality_scores": quality_scores,
            "quality_score": quality_scores["overall"],
            "quality_grade": quality_scores["grade"],
            "quality_recommended_action": quality_scores["recommended_action"],
            "normalized_path": rel(normalized_path, root),
            "classified_link": rel(classified_link, root),
        }
        assets.append(asset)
        extracts_by_asset[asset_id] = extracted

        normalized_path.parent.mkdir(parents=True, exist_ok=True)
        normalized_path.write_text(render_normalized_markdown(asset, extracted), encoding="utf-8")
        make_symlink(path, classified_link)

    hash_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for asset in assets:
        hash_groups[asset["sha256"]].append(asset)
    duplicates = []
    for file_hash, group in sorted(hash_groups.items()):
        if len(group) > 1:
            duplicates.append(
                {
                    "sha256": file_hash,
                    "primary": group[0]["relative_path"],
                    "duplicates": [item["relative_path"] for item in group[1:]],
                }
            )

    search_chunks: list[dict[str, Any]] = []
    for asset in assets:
        extracted = extracts_by_asset[asset["asset_id"]]
        for chunk_index, chunk in enumerate(chunk_text(extracted.text), start=1):
            search_chunks.append(
                {
                    "source_id": asset["asset_id"],
                    "chunk_id": f"{asset['asset_id']}:chunk:{chunk_index}",
                    "chunk_index": chunk_index,
                    "relative_path": asset["relative_path"],
                    "normalized_path": asset["normalized_path"],
                    "title": asset["title"],
                    "knowledge_domain": asset["knowledge_domain"],
                    "project_stage": asset["project_stage"],
                    "text": chunk,
                }
            )

    image_assets = [asset for asset in assets if asset["extension"] in EXTENSIONS_IMAGE]
    contact_sheets = create_contact_sheets(root, image_assets, report_root)

    manifest = {
        "version": "hxy-inbox-manifest.v1",
        "generated_at": generated_at,
        "run_name": run_name,
        "root": str(root),
        "source_dir": rel(inbox, root),
        "asset_count": len(assets),
        "assets": assets,
        "duplicates": duplicates,
        "contact_sheets": contact_sheets,
    }
    search_index = {
        "version": "hxy-inbox-search-index.v1",
        "generated_at": generated_at,
        "run_name": run_name,
        "chunk_count": len(search_chunks),
        "chunks": search_chunks,
    }

    structured_root.mkdir(parents=True, exist_ok=True)
    report_root.mkdir(parents=True, exist_ok=True)
    export_root.mkdir(parents=True, exist_ok=True)

    write_json(structured_root / f"hxy-inbox-manifest-{run_name}.json", manifest)
    write_json(structured_root / f"hxy-inbox-search-index-{run_name}.json", search_index)
    write_json(
        structured_root / "hxy-inbox-latest.json",
        {
            "generated_at": generated_at,
            "run_name": run_name,
            "manifest": f"knowledge/structured/hxy-inbox-manifest-{run_name}.json",
            "search_index": f"knowledge/structured/hxy-inbox-search-index-{run_name}.json",
            "report": f"knowledge/reports/hxy-inbox-knowledge-report-{run_name}.md",
        },
    )

    csv_path = export_root / f"hxy-inbox-knowledge-assets-{run_name}.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "asset_id",
                "relative_path",
                "file_name",
                "extension",
                "file_size",
                "sha256",
                "duplicate_of",
                "mime_type",
                "parser",
                "status",
                "char_count",
                "knowledge_domain",
                "knowledge_domain_label",
                "project_stage",
            "project_stage_label",
            "classification_confidence",
                "quality_score",
                "quality_grade",
                "quality_recommended_action",
            "normalized_path",
            "classified_link",
            "warnings",
            ],
        )
        writer.writeheader()
        for asset in assets:
            row = {key: asset.get(key, "") for key in writer.fieldnames or []}
            row["warnings"] = "; ".join(asset.get("warnings") or [])
            writer.writerow(row)

    report = build_report(root, generated_at, run_name, assets, duplicates, contact_sheets)
    (report_root / f"hxy-inbox-knowledge-report-{run_name}.md").write_text(report, encoding="utf-8")
    index_md = build_knowledge_index(generated_at, run_name, assets)
    (report_root / "HXY-KNOWLEDGE-INDEX.md").write_text(index_md, encoding="utf-8")

    summary = {
        "files": len(assets),
        "chunks": len(search_chunks),
        "duplicates": sum(len(group["duplicates"]) for group in duplicates),
        "by_domain": Counter(asset["knowledge_domain"] for asset in assets),
        "by_stage": Counter(asset["project_stage"] for asset in assets),
        "report": f"knowledge/reports/hxy-inbox-knowledge-report-{run_name}.md",
        "index": "knowledge/reports/HXY-KNOWLEDGE-INDEX.md",
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=dict))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
