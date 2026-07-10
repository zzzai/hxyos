from __future__ import annotations

import json
from pathlib import Path
from typing import Any


TEXT_EXTENSIONS = frozenset({".csv", ".json", ".md", ".txt"})

DOMAIN_TERMS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("compliance", ("合规", "风险", "红线", "禁用", "广告法", "医疗")),
    ("brand", ("品牌", "定位", "slogan", "口号", "门头", "话语体系")),
    ("product", ("产品", "项目", "菜单", "清泡", "调泡", "补泡", "养泡", "泡脚方")),
    ("operations", ("运营", "sop", "流程", "接待", "排班", "店长", "员工", "培训")),
    ("store", ("门店", "选址", "装修", "施工", "开业", "巡店")),
    ("customer", ("会员", "顾客", "客户", "反馈", "投诉", "复购", "私域")),
    ("finance", ("财务", "成本", "毛利", "营收", "预算", "估值", "融资")),
    ("organization", ("人员", "岗位", "组织", "会议", "招聘", "绩效")),
    ("external", ("竞品", "行业", "报告", "公众号", "电子书", "课程")),
)


def _decode_text(path: Path) -> str:
    data = path.read_bytes()
    for encoding in ("utf-8", "utf-8-sig", "gb18030"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _clean_preview(text: str, *, limit: int = 260) -> str:
    compact = " ".join(text.replace("\x00", " ").split())
    return compact[:limit]


def _domain_for(corpus: str) -> str:
    lowered = corpus.lower()
    for domain, terms in DOMAIN_TERMS:
        if any(term.lower() in lowered for term in terms):
            return domain
    return "general"


def _origin_for(corpus: str, domain: str) -> str:
    internal_terms = ("荷小悦", "首店", "门店", "会议", "项目进度", "员工", "会员")
    external_terms = ("外部", "行业报告", "公众号", "电子书", "竞品", "课程")
    if any(term in corpus for term in external_terms) or domain == "external":
        return "external"
    if any(term in corpus for term in internal_terms):
        return "internal"
    return "unknown"


def _authority_for(corpus: str, origin: str) -> str:
    if origin == "external":
        return "reference"
    if any(term in corpus for term in ("零碎", "随手", "片段", "截图", "草稿")):
        return "fragment"
    # A filename saying "official" is still not enough to grant formal authority.
    if any(term in corpus for term in ("正式", "定稿", "已批准", "合同")):
        return "claimed_official"
    return "working_material"


def _scale_for(corpus: str) -> str:
    if any(term in corpus for term in ("战略", "定位", "商业模式", "品牌核心", "融资")):
        return "macro"
    if any(term in corpus for term in ("产品", "运营", "选址", "装修", "会员", "组织", "项目")):
        return "meso"
    if any(term in corpus for term in ("sop", "流程", "话术", "日报", "反馈", "会议纪要", "接待")):
        return "micro"
    return "unknown"


def _document_type(extension: str, domain: str) -> str:
    if extension in {".png", ".jpg", ".jpeg", ".webp"}:
        return "图片资料"
    if extension in {".xls", ".xlsx", ".csv"}:
        return "表格资料"
    if extension in {".ppt", ".pptx"}:
        return "演示资料"
    if extension == ".pdf":
        return "PDF 资料"
    labels = {
        "brand": "品牌资料",
        "operations": "门店流程资料",
        "product": "产品资料",
        "finance": "财务资料",
        "compliance": "风险合规资料",
    }
    return labels.get(domain, "文档资料")


def build_material_understanding(
    *,
    path: Path,
    file_name: str,
    media_type: str,
    note: str,
    role: str,
) -> dict[str, Any]:
    del media_type, role
    extension = path.suffix.lower()
    warnings: list[str] = []
    text = ""
    parse_status = "metadata_only"
    if extension in TEXT_EXTENSIONS:
        try:
            text = _decode_text(path)
            if extension == ".json":
                json.loads(text)
            parse_status = "extracted"
        except (OSError, ValueError, json.JSONDecodeError):
            warnings.append("正文未能稳定解析，当前仅按文件信息做初步理解。")
    elif extension in {".png", ".jpg", ".jpeg", ".webp"}:
        parse_status = "needs_multimodal"
        warnings.append("图片还需要 OCR 或多模态理解，当前结论仅来自文件名和上传说明。")
    else:
        parse_status = "needs_deep_parse"
        warnings.append("复杂文档还需要 MarkItDown 或 MinerU 深度解析，当前结论仅为初步理解。")

    preview = _clean_preview(text)
    corpus = f"{file_name}\n{note}\n{preview}"
    domain = _domain_for(corpus)
    origin = _origin_for(corpus, domain)
    authority = _authority_for(corpus, origin)
    scale = _scale_for(corpus)
    if preview:
        summary = preview
    else:
        summary = f"已收到《{Path(file_name).stem}》，当前先归入{_document_type(extension, domain)}。"

    use_boundary = (
        "可作为外部参考，不能直接替代荷小悦的正式判断。"
        if origin == "external"
        else "可用于整理候选知识，未经核定不能作为荷小悦正式口径。"
    )
    return {
        "summary": summary,
        "document_type": _document_type(extension, domain),
        "source_origin": origin,
        "authority_level": authority,
        "knowledge_scale": scale,
        "domain": domain,
        "parse_status": parse_status,
        "confidence": "medium" if preview else "low",
        "warnings": warnings,
        "official_use_allowed": False,
        "use_boundary": use_boundary,
    }
