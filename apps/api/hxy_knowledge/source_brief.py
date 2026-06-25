from __future__ import annotations

import re
from typing import Any


_DELIVERABLE_RULES = [
    ("答案卡", ["定位", "口径", "是什么", "怎么讲", "标准答案"]),
    ("训练卡", ["培训", "员工", "门店", "话术", "清泡", "调泡", "补泡", "养泡"]),
    ("招商话术", ["招商", "加盟", "回本", "单店模型", "收益"]),
    ("复盘动作", ["复盘", "执行", "动作", "验收", "店长"]),
    ("资料记忆", ["资料", "上传", "识别", "分类", "记忆"]),
]


_METADATA_NOISE_PATTERNS = [
    r"\.(?:docx?|pdf|pptx?|xlsx?|csv|zip|png|jpe?g|webp|md|txt)(?![a-z0-9])",
    r"\b\d+\s*bytes?\b",
    r"\bfile\s*[:：]",
    r"\bsource_path\s*[:：]",
    r"\bnormalized_path\s*[:：]",
    r"\bchunk_id\s*[:：]",
    r"\basset_id\s*[:：]",
    r"knowledge/(?:raw|normalized|structured|processed|images)",
    r"/root/(?:hxy|htops)/",
    r"\bhxy-inbox:",
]


def _compact(text: str, max_length: int = 120) -> str:
    normalized = " ".join((text or "").split())
    if len(normalized) <= max_length:
        return normalized
    return normalized[: max_length - 1].rstrip(" ，,。；;：:") + "..."


def _has_any(text: str, terms: list[str]) -> bool:
    return any(term in text for term in terms)


def _has_metadata_noise(text: str) -> bool:
    lowered = " ".join((text or "").split()).lower()
    if not lowered:
        return False
    return any(re.search(pattern, lowered) for pattern in _METADATA_NOISE_PATTERNS)


def _is_usable_item(item: dict[str, Any]) -> bool:
    content = str(item.get("content") or "")
    return bool(content.strip()) and not _has_metadata_noise(content)


def _public_source_label(item: dict[str, Any], index: int) -> str:
    title = str(item.get("title") or "").strip()
    if title:
        return title
    domain = item.get("domain") or "资料"
    return f"{domain}资料 {index}"


def _domain_label(value: Any) -> str:
    return {
        "product": "产品体系",
        "brand": "品牌定位",
        "store_model": "门店模型",
        "operations": "门店运营",
        "franchise": "招商加盟",
        "finance": "经营测算",
        "competitor": "竞品资料",
        "external": "外部资料",
        "unknown": "未分类资料",
    }.get(str(value or "unknown"), "未分类资料")


def _context_level_label(level: str) -> str:
    return {
        "full": "可完整引用",
        "summary": "只作背景",
        "exclude": "不进入默认回答",
    }.get(level, "待判断")


def _context_level(item: dict[str, Any]) -> str:
    if not _is_usable_item(item):
        return "exclude"
    score = int(item.get("score") or 0)
    stage = str(item.get("stage") or "")
    if score >= 60 or stage in {"approved", "final", "production"}:
        return "full"
    if score >= 20:
        return "summary"
    return "exclude"


def _context_reason(item: dict[str, Any], level: str) -> str:
    domain = _domain_label(item.get("domain"))
    label = _context_level_label(level)
    if level == "full":
        return f"{domain}相关度高，{label}。"
    if level == "summary":
        return f"{domain}{label}，避免干扰主结论。"
    return f"{domain}相关度低或质量不足，{label}。"


def _source_excerpt(item: dict[str, Any]) -> str:
    if not _is_usable_item(item):
        return "资料清单、路径或文件元数据已排除，不能作为业务结论。"
    return _compact(str(item.get("content") or ""), max_length=150)


def _combined_usable_text(items: list[dict[str, Any]]) -> str:
    return " ".join(str(item.get("content") or "") for item in items if _is_usable_item(item))


def _append_unique(items: list[str], value: str) -> None:
    if value and value not in items:
        items.append(value)


def _build_business_findings(question: str, scenario: str, items: list[dict[str, Any]]) -> list[str]:
    combined = f"{question} {scenario} {_combined_usable_text(items)}"
    findings: list[str] = []
    if _has_any(combined, ["清泡调补养", "泡脚方", "草本泡脚", "一人一方", "五行"]):
        _append_unique(
            findings,
            "清泡调补养应沉淀为门店标准话术：清泡是基础放松，调泡看近期状态，补泡讲疲劳恢复感，养泡讲长期保养。",
        )
        _append_unique(
            findings,
            "员工培训要先问顾客状态，再推荐对应泡脚方；重点问睡眠、疲劳、手脚凉、压力和久坐情况。",
        )
    if _has_any(combined, ["培训", "员工", "门店", "话术", "店长"]):
        _append_unique(
            findings,
            "这批资料适合转成训练卡：标准话术、追问题、禁用表达、店长验收问题和复训动作。",
        )
    if _has_any(combined, ["招商", "加盟", "回本", "单店模型", "收益"]):
        _append_unique(
            findings,
            "招商表达只能讲产品结构、复购逻辑和模型假设，不能承诺收益、稳赚或保证回本。",
        )
    if _has_any(combined, ["定位", "核爆点", "品牌", "心智"]):
        _append_unique(
            findings,
            "定位类资料应先提炼一句话口径，再拆成创始人决策版、员工培训版、招商版和用户端表达。",
        )
    if _has_any(combined, ["治疗", "治愈", "失眠", "排毒", "保证有效"]):
        _append_unique(
            findings,
            "涉及功效的表达必须改成体验、放松和状态建议，不能说治疗、治愈或保证有效。",
        )
    return findings[:5]


def _build_context_plan(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    plan: list[dict[str, Any]] = []
    for index, item in enumerate(items, start=1):
        level = _context_level(item)
        plan.append(
            {
                "source": _public_source_label(item, index),
                "domain": item.get("domain") or "unknown",
                "stage": item.get("stage") or "unknown",
                "context_level": level,
                "reason": _context_reason(item, level),
                "excerpt": _source_excerpt(item),
            }
        )
    return plan


def _build_key_findings(items: list[dict[str, Any]]) -> list[str]:
    findings: list[str] = []
    for item in items:
        if not _is_usable_item(item):
            continue
        excerpt = _source_excerpt(item)
        if excerpt and excerpt not in findings:
            findings.append(excerpt)
    return findings[:5]


def _build_conflict_signals(items: list[dict[str, Any]]) -> list[str]:
    usable_items = [item for item in items if _is_usable_item(item)]
    combined = " ".join(str(item.get("content") or "") for item in usable_items)
    signals: list[str] = []
    if _has_any(combined, ["治疗", "治愈", "失眠", "排毒", "保证有效"]):
        signals.append("出现功效或治疗相关表达，必须转成体验、放松和状态建议。")
    if _has_any(combined, ["稳赚", "保证回本", "一定回本"]):
        signals.append("出现收益承诺表达，招商口径必须改成模型假设和风险边界。")
    domains = {item.get("domain") for item in usable_items if item.get("domain")}
    if "product" in domains and "franchise" in domains:
        signals.append("产品资料和招商资料同时出现，需区分门店外讲、招商沟通和内部经营判断。")
    return signals


def _build_deliverables(question: str, scenario: str, items: list[dict[str, Any]]) -> list[str]:
    combined = f"{question} {scenario} " + " ".join(str(item.get("content") or "") for item in items)
    deliverables: list[str] = ["答案卡"]
    for name, terms in _DELIVERABLE_RULES:
        if name in deliverables:
            continue
        if _has_any(combined, terms):
            deliverables.append(name)
    return deliverables


def _build_transformations(deliverables: list[str]) -> list[dict[str, str]]:
    transformations = [
        {
            "name": "标准口径提取",
            "purpose": "从资料中提取可复用、可复核的权威表达。",
            "output": "标准答案、适用场景、禁用表达、复核状态。",
        },
        {
            "name": "冲突与风险扫描",
            "purpose": "识别治疗承诺、收益承诺、新旧口径冲突和资料不足。",
            "output": "风险边界、冲突信号、需要复核的问题。",
        },
    ]
    if "训练卡" in deliverables:
        transformations.append(
            {
                "name": "训练素材生成",
                "purpose": "把资料转成员工可练、店长可验收的话术训练素材。",
                "output": "标准话术、追问题、评分点、复训动作。",
            }
        )
    if "招商话术" in deliverables:
        transformations.append(
            {
                "name": "招商表达生成",
                "purpose": "把经营逻辑转成招商可讲版本，并保留风险边界。",
                "output": "可讲版本、反对意见、风险边界、待补数据。",
            }
        )
    return transformations


def build_source_brief(
    question: str,
    items: list[dict[str, Any]],
    *,
    scenario: str = "经营问答",
) -> dict[str, Any]:
    deliverables = _build_deliverables(question, scenario, items)
    key_findings = _build_business_findings(question, scenario, items) or _build_key_findings(items)
    return {
        "version": "hxy-source-brief.v1",
        "workflow": "source_brief",
        "question": question,
        "scenario": scenario,
        "open_notebook_patterns": [
            {
                "key": "ask",
                "adaptation": "自动检索相关资料，但回答必须转成荷小悦经营成果。",
            },
            {
                "key": "transformations",
                "adaptation": "把资料套入固定转换模板，生成答案卡、训练卡、招商话术或复盘动作。",
            },
            {
                "key": "context_control",
                "adaptation": "按“可完整引用、只作背景、不进入默认回答”控制资料是否进入回答上下文。",
            },
        ],
        "context_plan": _build_context_plan(items),
        "transformations": _build_transformations(deliverables),
        "key_findings": key_findings,
        "conflict_signals": _build_conflict_signals(items),
        "deliverables": deliverables,
        "next_actions": [
            "优先用可完整引用的资料生成团队可用结果。",
            "只作背景的资料不作为关键结论依据。",
            "不进入默认回答的资料进入复核或补充解析。",
            "把稳定结果沉淀为答案卡、训练卡或招商话术版本。",
        ],
    }
