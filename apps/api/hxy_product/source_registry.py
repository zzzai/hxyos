from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any

from .source_card import build_source_use_policy


_COMPLIANCE_CANDIDATES = {
    "索引_风险与合规.md",
    "荷小悦项目红线卡.md",
    "荷小悦员工功效问题标准话术.md",
    "荷小悦禁用表达库.md",
}
_AI_APPLICATION_SIGNALS = ("应用笔记", "应用稿", "荷小悦应用", "实践草稿")
_AI_SUMMARY_SIGNALS = (
    "核心总结",
    "总结",
    "阅读笔记",
    "精读",
    "ai摘要",
    "ai_摘要",
    "ai总结",
)
_FOUNDER_ONLY_SIGNALS = (
    "股东",
    "合作协议",
    "投资人",
    "商业计划书",
    "天使轮",
    "估值",
    "收购方",
)
_RESTRICTED_SIGNALS = ("报价", "合同", "协议", "法务", "融资", "分账", "支付")


def _normalized_path(value: str) -> str:
    return PurePosixPath(str(value).replace("\\", "/")).as_posix().lstrip("./")


def _contains_any(value: str, signals: tuple[str, ...]) -> bool:
    return any(signal in value for signal in signals)


def _scopes(path: str) -> list[str]:
    scopes: list[str] = []
    rules = (
        (("02_战略方向", "品牌", "定位"), ("brand", "strategy")),
        (("03_门店模型", "首店", "小店", "单店", "门店"), ("first_store",)),
        (("04_产品系统", "产品", "菜单", "服务", "泡脚"), ("product",)),
        (("05_运营方法", "运营", "接待", "员工", "培训"), ("operations",)),
        (("客户", "消费者", "会员", "用户"), ("customer",)),
        (("06_融资商务", "融资", "股东", "财务", "报价"), ("finance",)),
        (("协议", "合同", "法务", "合规"), ("legal",)),
        (("系统", "技术", "ai", "小程序", "o2o", "iot"), ("technology",)),
        (("07_演示素材", "08_原始素材", "设计", "视觉", "vi", "si"), ("design",)),
        (("风险与合规", "禁用表达", "红线", "功效问题"), ("compliance",)),
    )
    lowered = path.lower()
    for signals, values in rules:
        if any(signal.lower() in lowered for signal in signals):
            scopes.extend(values)
    if "09_知识库与参考资料" in path or not scopes:
        scopes.append("external_method")
    return list(dict.fromkeys(scopes))


def _business_stage(path: str, material_class: str) -> str:
    if _contains_any(path, ("万店", "未来", "全国扩张")):
        return "future_vision"
    if "06_融资商务" in path or _contains_any(path, ("融资", "投资人", "股东")):
        return "financing"
    if _contains_any(path, ("连锁", "多门店", "总部", "督导")):
        return "chain"
    if "03_门店模型" in path or _contains_any(path, ("首店", "小店", "单店")):
        return "first_store"
    if _contains_any(path, ("试点", "验证", "样板店")):
        return "pilot"
    if material_class in {"external_primary", "external_secondary", "ai_derived"}:
        return "evergreen"
    return "pilot"


def classify_source_path(source_path: str) -> dict[str, Any]:
    path = _normalized_path(source_path)
    lowered = path.lower()
    name = PurePosixPath(path).name
    reasons: list[str] = []

    lifecycle = "undetermined"
    authority_state = "unclassified"
    sensitivity = "internal"
    derivation = "original"
    confidence = "medium"

    if path.startswith("extracted-reference/"):
        material_class = "processing_artifact"
        derivation = "extracted_copy"
        confidence = "high"
        reasons.append("material_class:extracted-reference")
    elif "/scripts/" in f"/{path}" or (
        path.startswith("荷小悦资料/scripts/")
        and PurePosixPath(path).suffix.lower() in {".py", ".html", ".json"}
    ):
        material_class = "tool_artifact"
        confidence = "high"
        reasons.append("material_class:tool-directory")
    elif name in _COMPLIANCE_CANDIDATES and "09_风险与合规" in path:
        material_class = "internal_project"
        lifecycle = "current_candidate"
        authority_state = "candidate"
        confidence = "high"
        reasons.append("material_class:explicit-compliance-candidate")
    elif "06_融资商务" in path or _contains_any(path, _RESTRICTED_SIGNALS):
        material_class = "internal_record"
        if _contains_any(path, _FOUNDER_ONLY_SIGNALS):
            sensitivity = "founder_only"
            reasons.append("sensitivity:founder-financing-or-agreement")
        else:
            sensitivity = "restricted"
            reasons.append("sensitivity:restricted-finance-or-legal")
        confidence = "high"
        reasons.append("material_class:internal-finance-record")
    elif "09_知识库与参考资料" in path:
        sensitivity = "public"
        if _contains_any(lowered, tuple(signal.lower() for signal in _AI_APPLICATION_SIGNALS)):
            material_class = "ai_derived"
            derivation = "application_draft"
            reasons.append("material_class:application-note-signal")
        elif _contains_any(lowered, tuple(signal.lower() for signal in _AI_SUMMARY_SIGNALS)):
            material_class = "ai_derived"
            derivation = "ai_summary"
            reasons.append("material_class:summary-or-reading-note-signal")
        elif _contains_any(path, ("原版书籍", "原文", "原始报告")):
            material_class = "external_primary"
            reasons.append("material_class:external-original-directory")
        else:
            material_class = "external_secondary"
            reasons.append("material_class:external-reference-directory")
        confidence = "high"
    elif any(f"/{prefix}_" in f"/{path}" for prefix in ("00", "01", "02", "03", "04", "05", "07", "08")):
        material_class = "internal_project"
        reasons.append("material_class:hxy-project-working-set")
    else:
        material_class = "external_secondary"
        confidence = "low"
        reasons.append("material_class:conservative-unmatched-default")

    if _contains_any(path, ("归档", "旧版", "_旧", "历史参考")):
        lifecycle = "historical"
        reasons.append("lifecycle:explicit-archive-or-old-marker")
    elif _contains_any(path, ("已废止", "废止", "superseded")):
        lifecycle = "superseded"
        reasons.append("lifecycle:explicit-superseded-marker")

    policy = build_source_use_policy(material_class)
    return {
        "material_class": material_class,
        "lifecycle": lifecycle,
        "authority_state": authority_state,
        "scope": _scopes(path),
        "sensitivity": sensitivity,
        "business_stage": _business_stage(path, material_class),
        "derivation": derivation,
        "classification_confidence": confidence,
        "classification_reasons": reasons,
        **policy,
    }
