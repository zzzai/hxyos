from __future__ import annotations

from collections import Counter
import re
from typing import Any


INTENT_RULES = [
    ("brand_positioning", "founder", ["品牌定位", "定位", "核爆点", "心智", "战略"]),
    ("product_system", "product", ["产品体系", "清泡调补养", "泡脚方", "sku", "spu", "套餐"]),
    ("store_model", "founder", ["门店模型", "小店模型", "单店模型", "选址", "社区店"]),
    ("operations", "operations", ["门店", "运营", "sop", "培训", "店长", "服务流程"]),
    ("finance", "founder", ["财务", "回本", "roi", "投资", "利润", "营收"]),
    ("franchise", "franchise", ["加盟", "招商", "加盟商", "连锁"]),
]

INTENT_DOMAIN_PRIORITY = {
    "brand_positioning": ["brand", "product", "store_model", "franchise", "finance", "competitor", "external"],
    "product_system": ["product", "brand", "store_model", "operations", "external", "competitor"],
    "operations": ["operations", "store_model", "product", "brand", "external", "competitor"],
    "finance": ["finance", "store_model", "franchise", "brand", "competitor", "external"],
    "franchise": ["franchise", "finance", "store_model", "brand", "product", "competitor"],
    "store_model": ["store_model", "product", "finance", "brand", "operations", "competitor"],
}

PRIMARY_CLAIM_DOMAINS = {
    "brand_positioning": {"brand", "product", "store_model"},
    "product_system": {"product", "brand", "store_model", "operations"},
    "operations": {"operations", "product", "store_model"},
    "finance": {"finance", "store_model", "franchise"},
    "franchise": {"franchise", "finance", "store_model", "brand"},
    "store_model": {"store_model"},
}


def compact_content(content: str, max_length: int = 320) -> str:
    normalized = " ".join(content.split())
    if len(normalized) <= max_length:
        return normalized
    return normalized[: max_length - 1].rstrip() + "..."


def compact_evidence_content(content: str, max_length: int = 260, intent: str = "knowledge_lookup") -> str:
    normalized = " ".join((content or "").split())
    if "图片类型：" not in normalized or "业务摘要：" not in normalized:
        if intent == "product_system":
            anchored = anchored_business_excerpt(normalized, max_length=max_length)
            if anchored:
                return anchored
        return compact_content(normalized, max_length=max_length)

    fields: dict[str, str] = {}
    labels = ["图片类型", "业务摘要", "视觉摘要", "识别实体", "价格信息", "相关知识域", "OCR 文本", "OCR 摘要"]
    pattern = "|".join(re.escape(label) + r"[：:]" for label in labels)
    matches = list(re.finditer(pattern, normalized))
    for index, match in enumerate(matches):
        label = match.group(0).rstrip("：:")
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(normalized)
        value = normalized[start:end].strip(" 。；;")
        if value:
            fields[label] = value

    ordered_parts: list[str] = []
    for label in ["图片类型", "业务摘要", "视觉摘要", "价格信息", "识别实体", "相关知识域", "OCR 摘要"]:
        if label in fields:
            ordered_parts.append(f"{label}：{fields[label]}")
    if not ordered_parts:
        return compact_content(normalized, max_length=max_length)
    return compact_content(" ".join(ordered_parts), max_length=max_length)


def anchored_business_excerpt(content: str, max_length: int = 260) -> str:
    if not content:
        return ""
    product_markers = ["产品体系", "清泡调补养", "荷小悦提供什么产品", "草本泡脚包", "1人1方", "一人一方", "A套餐模式"]
    if not any(marker in content for marker in product_markers):
        return ""
    anchors = [
        "产品体系",
        "清泡调补养",
        "荷小悦提供什么产品",
        "草本泡脚包",
        "A套餐模式",
        "1人1方",
        "一人一方",
        "核心卖点",
        "五行草本",
    ]
    starts = [content.find(anchor) for anchor in anchors if anchor in content]
    if not starts:
        return ""
    start = max(0, min(starts) - 8)
    excerpt = content[start : start + max_length * 2]
    stop_markers = ["逸马", "吉祥物", "昵称", "摸鱼养生", "躺平养生", "模式创新：到店也到家"]
    while any(marker in excerpt[:80] for marker in stop_markers):
        later_starts = [excerpt.find(anchor) for anchor in anchors if anchor in excerpt and excerpt.find(anchor) > 0]
        if not later_starts:
            break
        excerpt = excerpt[min(later_starts) :]
    return compact_content(excerpt, max_length=max_length)


def compact_sentence(content: str, max_length: int = 96) -> str:
    normalized = re.sub(r"[\u200b\u200c\u200d\ufeff]", " ", content or "")
    normalized = " ".join(normalized.split())
    normalized = re.sub(r"^[#>*\\-\\s]+", "", normalized).strip()
    if len(normalized) <= max_length:
        return normalized
    return normalized[: max_length - 1].rstrip(" ，,。；;：:") + "..."


METADATA_NOISE_PATTERNS = [
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


def has_metadata_noise(text: str) -> bool:
    lowered = " ".join((text or "").split()).lower()
    if not lowered:
        return False
    return any(re.search(pattern, lowered) for pattern in METADATA_NOISE_PATTERNS)


def classify_intent(question: str, items: list[dict[str, Any]] | None = None) -> tuple[str, str]:
    lowered = question.lower()
    for intent, audience, keywords in INTENT_RULES:
        if any(keyword.lower() in lowered for keyword in keywords):
            return intent, audience
    if items:
        domains = Counter(item.get("domain") for item in items if item.get("domain"))
        if domains:
            domain = domains.most_common(1)[0][0]
            if domain == "brand":
                return "brand_positioning", "brand"
            if domain == "product":
                return "product_system", "product"
            if domain == "store_model":
                return "store_model", "founder"
            if domain == "finance":
                return "finance", "founder"
            if domain == "franchise":
                return "franchise", "franchise"
            if domain == "operations":
                return "operations", "operations"
    return "knowledge_lookup", "general"


def sort_items_for_intent(items: list[dict[str, Any]], intent: str) -> list[dict[str, Any]]:
    priority = INTENT_DOMAIN_PRIORITY.get(intent, [])

    def item_key(item: dict[str, Any]) -> tuple[int, int]:
        domain = item.get("domain") or ""
        domain_rank = priority.index(domain) if domain in priority else len(priority) + 1
        score = int(item.get("score") or 0)
        return domain_rank, -score

    return sorted(items, key=item_key)


def build_evidence(items: list[dict[str, Any]], intent: str = "knowledge_lookup") -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in sort_items_for_intent(items, intent):
        key = item.get("chunk_id") or item.get("source_path") or item.get("title") or ""
        if key in seen:
            continue
        seen.add(key)
        score = item.get("score") or 0
        evidence.append(
            {
                "chunk_id": item.get("chunk_id"),
                "asset_id": item.get("asset_id"),
                "title": item.get("title"),
                "source_path": item.get("source_path"),
                "normalized_path": item.get("normalized_path"),
                "domain": item.get("domain"),
                "stage": item.get("stage"),
                "score": score,
                "strength": "high" if score >= 30 else "medium" if score >= 10 else "low",
                "excerpt": compact_evidence_content(item.get("content") or "", max_length=260, intent=intent),
            }
        )
    return evidence


def confidence_for(evidence: list[dict[str, Any]], conflicts: list[str]) -> str:
    if not evidence:
        return "low"
    source_count = len({item.get("source_path") for item in evidence if item.get("source_path")})
    domain_count = len({item.get("domain") for item in evidence if item.get("domain")})
    if conflicts:
        return "medium" if source_count >= 3 else "low"
    if source_count >= 3 and domain_count >= 2:
        return "high"
    if source_count >= 2:
        return "medium"
    return "low"


def detect_conflicts(question: str, evidence: list[dict[str, Any]]) -> list[str]:
    excerpts = " ".join(item.get("excerpt") or "" for item in evidence)
    conflicts: list[str] = []
    if "瑞幸" in excerpts and "高质平价" in excerpts and "高端" in excerpts:
        conflicts.append("资料同时出现高质平价和高端表达，使用前需要确认主叙事。")
    if "1000" in excerpts and "10000" in excerpts:
        conflicts.append("资料中同时出现阶段目标和远期万店目标，回答时应区分时间尺度。")
    if "定位" in question and not any("定位" in (item.get("excerpt") or "") for item in evidence):
        conflicts.append("当前证据没有直接命中定位原文，结论需要人工复核。")
    return conflicts


def build_corrections(question: str, evidence: list[dict[str, Any]], intent: str) -> list[str]:
    corrections: list[str] = []
    if len(question) < 8:
        corrections.append("问题过短，建议补充场景，例如用于品牌定位、招商话术还是门店培训。")
    if not evidence:
        corrections.append("当前资料不足，建议先上传或导入相关文件后再问。")
    if intent == "knowledge_lookup":
        corrections.append("这个问题目前更像资料查找。若需要决策，请改问“结论是什么、依据是什么、风险是什么”。")
    return corrections


def build_next_actions(intent: str, confidence: str, conflicts: list[str], scenario: str = "创始人内部决策") -> list[str]:
    actions = {
        "brand_positioning": ["沉淀一版权威品牌定位卡", "把可外讲和内部判断分开", "确认一句话定位和三条支撑证据"],
        "product_system": ["整理产品体系结构表", "标注每个项目的适用人群和价格带", "确认哪些内容可进入用户端话术"],
        "operations": ["转成门店 SOP", "提取培训话术", "标注需要店长复核的动作"],
        "finance": ["核对数据口径", "拆分投资、营收、回本周期", "标注假设条件"],
        "franchise": ["转成招商问答", "提取加盟商关心的风险和收益", "准备反对意见回答"],
        "store_model": ["固化单店模型参数", "区分试点模型和规模化模型", "补齐选址约束"],
    }
    result = list(actions.get(intent, ["补充问题场景", "确认权威来源", "将有效回答沉淀为 FAQ"]))
    if scenario == "招商话术":
        result.insert(0, "改写成招商可用话术，突出确定性、收益逻辑和风险边界")
    elif scenario == "门店员工培训":
        result.insert(0, "改写成门店员工可背诵的话术和服务动作")
    elif scenario == "用户端宣传":
        result.insert(0, "改写成用户能理解且不过度承诺的表达")
    if conflicts:
        result.insert(0, "先处理冲突资料，确认权威版本")
    if confidence == "low":
        result.append("低置信度回答需要人工复核")
    return result


def usage_for(intent: str, scenario: str) -> str:
    if scenario == "招商话术":
        return "用于招商沟通：先讲清定位和确定性，再讲单店模型、收益逻辑、风险边界和反对意见。"
    if scenario == "门店员工培训":
        return "用于门店培训：改写成员工能背诵的标准话术、服务动作和禁用表达。"
    if scenario == "用户端宣传":
        return "用于用户端宣传：只保留顾客听得懂、可外讲、不过度承诺的表达。"
    if intent == "brand_positioning":
        return "用于内部决策：统一一句话定位，并拆分外部话术和内部经营判断。"
    if intent == "product_system":
        return "用于产品工作：沉淀结构、适用人群、价格带和复购逻辑。"
    return "用于经营决策：先固化结论，再分配复核、纠偏和答案卡沉淀动作。"


def applicable_scenarios_for(intent: str, audience: str, scenario: str) -> list[str]:
    scenarios = [scenario]
    if audience and audience not in scenarios:
        scenarios.append(audience)
    if intent == "brand_positioning":
        scenarios.extend(["品牌统一口径", "招商话术", "门店员工培训"])
    elif intent == "product_system":
        scenarios.extend(["产品培训", "用户端宣传", "门店员工培训"])
    elif intent == "franchise":
        scenarios.extend(["招商加盟", "投资模型复核"])
    elif intent == "operations":
        scenarios.extend(["培训 SOP", "店长复核"])
    result: list[str] = []
    for item in scenarios:
        if item and item not in result:
            result.append(item)
    return result


def answer_status_for(confidence: str, needs_review: bool) -> str:
    if needs_review:
        return "待复核"
    if confidence == "high":
        return "AI 草稿"
    return "待复核"


def result_type_for(intent: str, scenario: str) -> str:
    if scenario == "招商话术":
        return "招商话术结果卡"
    if scenario == "门店员工培训":
        return "培训 SOP 结果卡"
    if scenario == "用户端宣传":
        return "用户端宣传结果卡"
    return {
        "brand_positioning": "品牌定位结果卡",
        "product_system": "产品体系结果卡",
        "operations": "门店运营结果卡",
        "finance": "经营财务结果卡",
        "franchise": "招商加盟结果卡",
        "store_model": "门店模型结果卡",
    }.get(intent, "经营判断结果卡")


def review_owner_for(intent: str, scenario: str) -> str:
    if scenario == "门店员工培训":
        return "运营负责人"
    if scenario == "招商话术":
        return "招商负责人"
    if scenario == "用户端宣传":
        return "品牌负责人"
    return {
        "brand_positioning": "创始人/品牌负责人",
        "product_system": "产品负责人",
        "operations": "运营负责人",
        "finance": "财务负责人",
        "franchise": "招商负责人",
        "store_model": "创始人/门店模型负责人",
    }.get(intent, "业务负责人")


def risk_boundary_for(intent: str, scenario: str, confidence: str, conflicts: list[str]) -> str:
    if confidence == "low":
        return "当前结论置信度低，只能作为草稿，不得直接用于对外承诺或员工培训。"
    if conflicts:
        return "当前资料存在冲突，必须先确认权威版本，再用于经营决策。"
    if scenario == "用户端宣传":
        return "仅用于用户可理解的价值表达，不能承诺疗效、收益或未验证结果。"
    if scenario == "招商话术":
        return "可用于招商沟通草稿，但收益、投入、回本周期必须补齐口径和假设。"
    if scenario == "门店员工培训":
        return "可用于员工培训草稿，涉及疗效、价格和承诺的表达必须按门店标准话术复核。"
    return {
        "finance": "财务判断必须保留口径、假设条件和时间尺度，不得直接作为承诺。",
        "franchise": "招商判断必须同时说明风险和边界，不得只讲收益。",
        "store_model": "门店模型判断要区分试点模型和规模化模型。",
    }.get(intent, "用于内部经营判断，外部发布前需要业务负责人复核。")


def business_result_for(intent: str, scenario: str) -> str:
    target = {
        "brand_positioning": "统一品牌定位和表达口径",
        "product_system": "形成产品体系和项目表达",
        "operations": "形成门店可执行动作和 SOP",
        "finance": "形成经营财务判断",
        "franchise": "形成招商加盟沟通口径",
        "store_model": "形成门店模型关键参数判断",
    }.get(intent, "形成可复用经营判断")
    return f"{scenario}：{target}"


def build_quality_gates(
    intent: str,
    scenario: str,
    evidence: list[dict[str, Any]],
    answer: str,
    confidence: str,
    conflicts: list[str],
) -> list[dict[str, Any]]:
    allowed_domains = PRIMARY_CLAIM_DOMAINS.get(intent) or set()
    evidence_domains = {item.get("domain") for item in evidence if item.get("domain")}
    domain_passed = not allowed_domains or bool(evidence_domains & allowed_domains)
    clean_answer = bool(answer) and "当前知识库没有可直接用于回答" not in answer and "无法可靠回答" not in answer
    no_noise = not has_metadata_noise(answer)
    scenario_fit = not (scenario == "用户端宣传" and intent in {"finance", "franchise"})
    no_overclaim = not any(term in answer for term in ["保证", "治愈", "稳赚", "一定回本", "绝对"])
    return [
        {
            "name": "命中正确业务域",
            "passed": domain_passed,
            "detail": "证据域与问题意图匹配。" if domain_passed else "证据域与问题意图不匹配，需要重新召回或人工复核。",
        },
        {
            "name": "使用干净业务结论",
            "passed": clean_answer,
            "detail": "已抽取可用业务结论。" if clean_answer else "缺少可直接使用的业务结论。",
        },
        {
            "name": "无内部噪声",
            "passed": no_noise,
            "detail": "主答案未暴露文件路径、chunk 或文件清单。" if no_noise else "主答案疑似包含内部路径、文件名或 chunk 噪声。",
        },
        {
            "name": "适配当前场景",
            "passed": scenario_fit,
            "detail": f"已按{scenario}输出。" if scenario_fit else "当前意图不适合直接用于该场景。",
        },
        {
            "name": "不过度承诺",
            "passed": no_overclaim,
            "detail": "未发现明显过度承诺。" if no_overclaim else "存在过度承诺风险，需要改写。",
        },
    ]


def stability_level_for(confidence: str, needs_review: bool, quality_gates: list[dict[str, Any]]) -> str:
    if not all(gate.get("passed") for gate in quality_gates):
        return "insufficient"
    if needs_review or confidence != "high":
        return "review_required"
    return "stable"


def build_result_card(
    *,
    intent: str,
    scenario: str,
    answer: str,
    evidence: list[dict[str, Any]],
    confidence: str,
    conflicts: list[str],
    needs_review: bool,
) -> dict[str, Any]:
    quality_gates = build_quality_gates(intent, scenario, evidence, answer, confidence, conflicts)
    return {
        "result_type": result_type_for(intent, scenario),
        "usable_answer": answer,
        "business_result": business_result_for(intent, scenario),
        "risk_boundary": risk_boundary_for(intent, scenario, confidence, conflicts),
        "quality_gates": quality_gates,
        "review_owner": review_owner_for(intent, scenario),
        "stability_level": stability_level_for(confidence, needs_review, quality_gates),
    }


def split_claims(text: str) -> list[str]:
    normalized = " ".join((text or "").split())
    parts = re.split(r"[。！？!?；;]\s*", normalized)
    return [part.strip(" ，,：:") for part in parts if part.strip(" ，,：:")]


def extract_labeled_field(text: str, label: str) -> str:
    labels = ["图片类型", "业务摘要", "视觉摘要", "识别实体", "价格信息", "相关知识域", "OCR 文本", "OCR 摘要"]
    pattern = "|".join(re.escape(item) + r"[：:]" for item in labels)
    normalized = " ".join((text or "").split())
    matches = list(re.finditer(pattern, normalized))
    for index, match in enumerate(matches):
        current_label = match.group(0).rstrip("：:")
        if current_label != label:
            continue
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(normalized)
        return normalized[start:end].strip(" 。；;")
    return ""


def claim_keywords_for(intent: str) -> list[str]:
    return {
        "brand_positioning": ["品牌定位", "核心定位", "定位", "不是在做", "健康耗材", "高质平价", "功效泡脚", "一人一方"],
        "product_system": ["业务摘要", "卖点", "产品体系", "清泡调补养", "泡脚方", "一人一方", "功效", "草本", "复购"],
        "operations": ["SOP", "服务流程", "培训", "门店", "店长"],
        "finance": ["回本", "ROI", "投资", "营收", "利润", "模型"],
        "franchise": ["加盟", "招商", "加盟商", "连锁", "收益", "风险"],
        "store_model": ["小店模型", "单店模型", "社区店", "选址", "坪效", "模型"],
    }.get(intent, ["结论", "判断", "建议"])


def strong_claim_keywords_for(intent: str) -> list[str]:
    return {
        "brand_positioning": ["品牌定位", "核心定位", "不是在做", "而是在做", "健康耗材", "功效泡脚", "一人一方"],
        "product_system": ["产品体系", "清泡调补养", "泡脚方", "一人一方", "草本", "复购"],
        "operations": ["SOP", "服务流程", "培训", "店长", "服务动作", "话术"],
        "finance": ["回本", "ROI", "投资", "营收", "利润", "成本", "模型"],
        "franchise": ["加盟", "招商", "加盟商", "连锁", "收益", "风险"],
        "store_model": ["门店模型", "小店模型", "单店模型", "社区店", "选址", "坪效", "规模化参数", "试点参数"],
    }.get(intent, [])


def can_use_item_for_primary_claim(item: dict[str, Any], intent: str, text: str) -> bool:
    domain = item.get("domain") or ""
    allowed_domains = PRIMARY_CLAIM_DOMAINS.get(intent)
    if allowed_domains and domain in allowed_domains:
        return True
    lowered = (text or "").lower()
    return any(keyword.lower() in lowered for keyword in strong_claim_keywords_for(intent))


def normalize_claim_text(claim: str, intent: str) -> str:
    text = re.sub(r"[\u200b\u200c\u200d\ufeff]", " ", claim or "")
    text = " ".join(text.split())
    text = re.sub(r"^[#>*\\-\\s]+", "", text).strip()
    if "第一性原理" in text and "：" in text:
        text = text.rsplit("：", 1)[1].strip()
    if "核心定位" in text:
        text = text.split("核心定位", 1)[1].strip(" ：:")
    if "不是在做" in text and "而是在做" in text:
        start = text.find("不是在做")
        prefix = "荷小悦" if "荷小悦" in text[:start] else ""
        text = prefix + text[start:]
    text = re.sub(r"^荷小悦品牌定位[：:]\s*", "荷小悦是", text)
    text = re.sub(r"^品牌定位[：:]\s*", "荷小悦是", text)
    text = re.sub(r"^业务摘要[：:]\s*", "", text)
    text = re.sub(r"^视觉摘要[：:]\s*", "", text)
    text = re.sub(r"^核心定位\s*", "", text)
    text = compact_sentence(text)
    if intent == "brand_positioning" and text.startswith("荷小悦是") is False and "荷小悦" not in text:
        text = "荷小悦" + text
    return text


def clean_store_model_parameter_text(text: str) -> str:
    cleaned = re.sub(r"[\u200b\u200c\u200d\ufeff]", " ", text or "")
    cleaned = " ".join(cleaned.split())
    cleaned = re.sub(r"荷小悦到底在解决什么问题[？?]?", "", cleaned)
    cleaned = re.sub(r"不是它想做什么，而是客户为什么必须来[。；;]?", "", cleaned)
    cleaned = re.sub(r"一个核心人群[：:]", "核心人群：", cleaned)
    cleaned = re.sub(r"一个社区里的人，身体累了，情绪也闷着，走出家门5分钟能到达的地方里，他需要什么", "5分钟社区可达，满足身体疲劳和情绪压力下的恢复需求", cleaned)
    cleaned = re.sub(r"他需要恢复元气", "满足恢复元气需求", cleaned)
    cleaned = re.sub(r"\s+([；;。])", r"\1", cleaned)
    cleaned = re.sub(r"[；;]\s*[；;]+", "；", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" ；;。")
    return cleaned


def brand_claim_score(claim: str) -> int:
    text = normalize_claim_text(claim, "brand_positioning")
    positive_patterns = [
        "品牌定位",
        "不是在做",
        "而是在做",
        "健康耗材",
        "功效泡脚",
        "一人一方",
        "解决",
        "要做的事",
        "核心承诺",
        "核心定位",
        "快速恢复",
        "身体疲劳",
    ]
    negative_patterns = [
        "品牌战略汇总",
        "战略蓝图",
        "定位设计",
        "商业模型",
        "选址框架",
        "一、",
        "二、",
        "三、",
        "目录",
        "Slide",
    ]
    score = 0
    for pattern in positive_patterns:
        if pattern in text:
            score += 4
    for pattern in negative_patterns:
        if pattern in text:
            score -= 3
    if len(text) > 160:
        score -= 2
    if len(text) < 12:
        score -= 2
    if text.startswith("荷小悦是"):
        score += 5
    return score


def extract_brand_positioning_claim(claims: list[str]) -> str:
    expanded_claims: list[str] = []
    anchors = ["品牌定位", "核心定位", "第一性原理", "核心承诺", "荷小悦要做的事", "荷小悦不是在做", "解决"]
    for claim in claims:
        expanded_claims.append(claim)
        for anchor in anchors:
            if anchor in claim:
                expanded_claims.append(claim[claim.find(anchor) :])
    scored = [(brand_claim_score(claim), index, claim) for index, claim in enumerate(expanded_claims)]
    viable = [item for item in scored if item[0] > 0]
    if not viable:
        return ""
    _score, _index, claim = max(viable, key=lambda item: (item[0], -item[1]))
    return normalize_claim_text(claim, "brand_positioning")


def extract_store_model_claim(claims: list[str]) -> str:
    parameter_keywords = [
        "两个核心",
        "核心人群",
        "5分钟",
        "五分钟",
        "走出家门",
        "恢复元气",
        "产品结构",
        "引流品",
        "主力品",
        "利润品",
        "高质平价",
        "小店型",
        "社区",
        "目标",
    ]
    negative_keywords = ["具象化构思", "战略定位", "研讨", "市场其他品牌调研", "模板核心模块"]
    selected: list[str] = []
    for claim in claims:
        normalized_claim = normalize_claim_text(claim, "store_model")
        if not normalized_claim or has_metadata_noise(normalized_claim):
            continue
        if any(keyword in normalized_claim for keyword in negative_keywords) and not any(
            keyword in normalized_claim for keyword in parameter_keywords
        ):
            continue
        if any(keyword in normalized_claim for keyword in parameter_keywords):
            selected.append(normalized_claim)
        if len(selected) >= 4:
            break
    if not selected:
        return ""

    compacted: list[str] = []
    for item in selected:
        cleaned_item = clean_store_model_parameter_text(item)
        if cleaned_item and cleaned_item not in compacted:
            compacted.append(cleaned_item)
    return clean_store_model_parameter_text(compact_sentence("；".join(compacted), max_length=180))


def product_claim_score(claim: str) -> int:
    text = normalize_claim_text(claim, "product_system")
    positive_patterns = [
        "产品体系",
        "清泡调补养",
        "草本泡脚",
        "泡脚方",
        "1人1方",
        "一人一方",
        "推拿服务",
        "离店复购",
        "完整体验",
        "核心卖点",
        "五脏泡脚",
    ]
    negative_patterns = [
        "逸马",
        "吉祥物",
        "昵称",
        "摸鱼养生",
        "躺平养生",
        "模式创新",
        "到家服务",
        "家居产品",
        "Slide",
        "文件名",
        "图像元信息",
        "OCR 识别文本",
    ]
    score = 0
    for pattern in positive_patterns:
        if pattern in text:
            score += 4
    for pattern in negative_patterns:
        if pattern in text:
            score -= 4
    if "清泡调补养" in text and "一人一方" in text:
        score += 6
    if "产品体系" in text and "清泡调补养" in text:
        score += 6
    if len(text) > 180:
        score -= 2
    if len(text) < 10:
        score -= 2
    return score


def is_polluted_product_claim(claim: str) -> bool:
    text = normalize_claim_text(claim, "product_system")
    pollution_markers = ["逸马", "吉祥物", "昵称", "泡泡", "摸鱼养生", "躺平养生", "模式创新", "到店也到家", "家居产品"]
    business_markers = ["草本泡脚", "泡脚方", "1人1方", "一人一方", "推拿", "离店复购", "复购", "适用人群", "服务流程"]
    pollution_count = sum(1 for marker in pollution_markers if marker in text)
    business_count = sum(1 for marker in business_markers if marker in text)
    if pollution_count >= 2 and business_count == 0:
        return True
    if pollution_count >= 3 and business_count <= 1:
        return True
    return False


def clean_product_claim_text(claim: str) -> str:
    text = re.sub(r"[\u200b\u200c\u200d\ufeff]", " ", claim or "")
    text = " ".join(text.split())
    text = re.sub(r"^[#>*\\-\\s]+", "", text).strip()
    text = re.sub(r"^业务摘要[：:]\s*", "", text)
    text = re.sub(r"^视觉摘要[：:]\s*", "", text)
    has_ocr_table_noise = bool(
        re.search(r"模式\s+项目\s+时间\s+价格|\b\d{1,2}\s+\d{1,3}\b|草木\s+配方|\d+元-\d+分钟", text)
    )
    if (
        not has_ocr_table_noise
        and "清泡调补养体验" in text
        and any(marker in text for marker in ["组成", "形成", "产品体系"])
    ):
        return compact_sentence(text, max_length=150)
    replacements = [
        (r"\s*模式\s+项目\s+时间\s+价格\s*", " "),
        (r"\s*草木\s+配方\s*", " "),
        (r"\b\d{1,2}\s+\d{1,3}\b", " "),
        (r"\d+元-\d+分钟[：:]?", " "),
    ]
    for pattern, replacement in replacements:
        text = re.sub(pattern, replacement, text)
    text = re.sub(r"\s+", " ", text).strip(" ，,。；;：:")

    structured_parts: list[str] = []
    if "可以喝的泡脚汤" in text:
        structured_parts.append("可以喝的泡脚汤")
    if "A套餐模式+B火锅模式" in text:
        structured_parts.append("A套餐模式+B火锅模式")
    if "草本泡脚包" in text and "套餐按摩" in text:
        structured_parts.append("A模式：草本泡脚包+套餐按摩")
    elif "草本泡脚包" in text:
        structured_parts.append("草本泡脚包")
    if "1人1方" in text and "任选按摩" in text:
        structured_parts.append("B模式：1人1方+任选按摩")
    elif "一人一方" in text and "任选按摩" in text:
        structured_parts.append("B模式：一人一方+任选按摩")
    elif "1人1方" in text:
        structured_parts.append("1人1方")
    elif "一人一方" in text:
        structured_parts.append("一人一方")

    if structured_parts:
        prefix = "清泡调补养" if "清泡调补养" in text else "产品体系"
        return compact_sentence(f"{prefix}：" + "；".join(_dedupe_text_parts(structured_parts)), max_length=150)
    return compact_sentence(text, max_length=150)


def _dedupe_text_parts(parts: list[str]) -> list[str]:
    deduped: list[str] = []
    for part in parts:
        if part and part not in deduped:
            deduped.append(part)
    return deduped


def extract_product_system_claim(claims: list[str]) -> str:
    expanded_claims: list[str] = []
    anchors = ["产品体系", "清泡调补养", "核心卖点", "五行草本", "一人一方", "荷小悦提供什么产品"]
    for claim in claims:
        expanded_claims.append(claim)
        for anchor in anchors:
            if anchor in claim:
                expanded_claims.append(claim[claim.find(anchor) :])
    scored = [
        (product_claim_score(claim), index, claim)
        for index, claim in enumerate(expanded_claims)
        if not is_polluted_product_claim(claim)
    ]
    viable = [item for item in scored if item[0] > 0]
    if not viable:
        return ""
    _score, _index, claim = max(viable, key=lambda item: (item[0], -item[1]))
    result = clean_product_claim_text(claim)
    complement_terms = [
        ("草本泡脚包", ["1人1方", "一人一方"]),
        ("1人1方", ["草本泡脚包", "草本泡脚"]),
        ("一人一方", ["草本泡脚包", "草本泡脚"]),
    ]
    for present_term, missing_terms in complement_terms:
        if present_term not in result:
            continue
        if any(term in result for term in missing_terms):
            continue
        complements = [
            normalize_claim_text(candidate, "product_system")
            for candidate in claims
            if any(term in candidate for term in missing_terms) and product_claim_score(candidate) > 0
        ]
        for complement in complements:
            if complement and complement not in result:
                result = clean_product_claim_text(f"{result}；{complement}")
                break
    return result


def extract_primary_claim(evidence: list[dict[str, Any]], intent: str) -> tuple[str, str]:
    keywords = claim_keywords_for(intent)
    for item in evidence:
        excerpt = item.get("excerpt") or ""
        if has_metadata_noise(excerpt):
            continue
        if not can_use_item_for_primary_claim(item, intent, excerpt):
            continue
        if intent == "product_system" and "图片类型：" in excerpt:
            business_summary = extract_labeled_field(excerpt, "业务摘要")
            if business_summary and not has_metadata_noise(business_summary):
                return business_summary, item.get("title") or "已入库资料"
        claims = split_claims(excerpt)
        if intent == "product_system":
            product_claim = extract_product_system_claim(claims)
            if product_claim and not has_metadata_noise(product_claim):
                return product_claim, item.get("title") or "已入库资料"
        if intent == "brand_positioning":
            brand_claim = extract_brand_positioning_claim(claims)
            if brand_claim and not has_metadata_noise(brand_claim):
                return brand_claim, item.get("title") or "已入库资料"
        if intent == "store_model":
            store_model_claim = extract_store_model_claim(claims)
            if store_model_claim:
                return store_model_claim, item.get("title") or "已入库资料"
        for keyword in keywords:
            for claim in claims:
                normalized_claim = normalize_claim_text(claim, intent)
                if intent == "product_system" and is_polluted_product_claim(normalized_claim):
                    continue
                if keyword.lower() in claim.lower() and not has_metadata_noise(normalized_claim):
                    return normalized_claim, item.get("title") or "已入库资料"
    for item in evidence:
        fallback_claim = compact_sentence(item.get("excerpt") or "")
        if intent == "product_system" and is_polluted_product_claim(fallback_claim):
            continue
        if fallback_claim and not has_metadata_noise(fallback_claim) and can_use_item_for_primary_claim(item, intent, fallback_claim):
            return fallback_claim, item.get("title") or "已入库资料"
    return "", ""


def answer_suffix_for(intent: str, scenario: str) -> str:
    if scenario == "用户端宣传":
        return {
            "brand_positioning": "对外表达应聚焦顾客能感知的价值，不做过度承诺。",
            "product_system": "对外表达应讲清体验、适用场景和可感知价值。",
            "operations": "对外表达应转成顾客听得懂的服务体验，不展示内部流程。",
            "finance": "这类内容不适合直接用于用户端宣传，建议转成人群价值和体验利益点。",
            "franchise": "这类内容不适合直接用于用户端宣传，建议另做招商版本。",
            "store_model": "对外表达可聚焦近、方便、放松恢复和标准化体验。",
        }.get(intent, "对外表达应聚焦顾客能理解的价值。")
    if scenario == "招商话术":
        return {
            "store_model": "招商表达要进一步补齐面积、选址、投入、营收和回本假设。",
            "brand_positioning": "招商表达要把定位、确定性和可复制性讲清楚。",
            "product_system": "招商表达要讲清产品结构、复购逻辑和毛利空间。",
        }.get(intent, "招商表达要同时覆盖价值、风险和反对意见。")
    if scenario == "门店员工培训":
        return {
            "store_model": "培训表达要转成员工能复述的顾客场景和服务动作。",
            "product_system": "培训表达要转成员工能背诵的项目介绍和禁用承诺。",
        }.get(intent, "培训表达要转成标准话术、服务动作和复核点。")
    return {
        "brand_positioning": "这是当前品牌定位判断，应优先沉淀为一句话定位和可外讲支撑话术。",
        "product_system": "产品表达应围绕结构、适用人群和可复购服务来沉淀。",
        "operations": "运营答案应继续转成可执行 SOP、话术和复核点。",
        "finance": "财务类判断必须保留口径、假设条件和时间尺度。",
        "franchise": "招商类回答要同时覆盖价值、风险和反对意见。",
        "store_model": "门店模型类回答要区分试点参数和规模化参数。",
    }.get(intent, "")


def role_specific_answer_for_claim(intent: str, scenario: str, claim: str) -> str:
    if scenario == "门店员工培训":
        if intent == "product_system":
            return (
                f"员工话术：{claim}。"
                "服务动作：先问顾客状态，再介绍对应泡脚方、推拿配合和复购产品。"
                "禁用表达：不要承诺疗效，不要把草本泡脚说成医疗治疗。"
            )
        if intent == "brand_positioning":
            return (
                f"员工话术：{claim}。"
                "服务动作：用一句话讲清荷小悦和普通足疗店的区别，再引导顾客选择项目。"
                "禁用表达：不要夸大效果，不要使用无法验证的绝对化承诺。"
            )
        if intent == "store_model":
            return (
                f"员工话术：{claim}。"
                "服务动作：围绕近、方便、放松恢复和标准服务讲清顾客体验。"
                "禁用表达：不要向顾客讲内部投资模型、坪效或招商承诺。"
            )
        return (
            f"员工话术：{claim}。"
            "服务动作：转成顾客听得懂的一句话说明和标准服务动作。"
            "禁用表达：不要承诺疗效、收益或未确认结果。"
        )

    if scenario == "招商话术":
        if intent == "product_system":
            return (
                f"招商话术：{claim}。"
                "沟通重点：讲清产品结构、复购逻辑、员工可复制话术和门店执行难度。"
                "风险边界：毛利、客单、复购和回本周期必须另用真实经营数据核算。"
            )
        if intent == "brand_positioning":
            return (
                f"招商话术：{claim}。"
                "沟通重点：讲清定位差异、顾客为什么来、门店为什么能复制。"
                "风险边界：不能把定位直接包装成收益承诺。"
            )
        if intent == "store_model":
            return (
                f"招商话术：{claim}。"
                "沟通重点：讲清社区场景、选址约束、产品结构和复制条件。"
                "风险边界：面积、投入、营收和回本周期必须补齐假设。"
            )
        return (
            f"招商话术：{claim}。"
            "沟通重点：先讲价值，再讲执行条件、风险和反对意见。"
            "风险边界：不得把草稿判断当成对加盟商的确定承诺。"
        )

    if scenario == "用户端宣传":
        if intent == "product_system":
            return (
                f"用户表达：{claim}。"
                "适用场景：用于项目介绍、菜单说明和顾客沟通。"
                "注意边界：只讲体验和可感知价值，不承诺疗效。"
            )
        if intent == "brand_positioning":
            return (
                f"用户表达：{claim}。"
                "适用场景：用于门店介绍、品牌简介和线上页面。"
                "注意边界：表达要克制，不使用绝对化承诺。"
            )
        if intent == "store_model":
            return (
                f"用户表达：{claim}。"
                "适用场景：用于说明门店近、方便、放松恢复和标准化体验。"
                "注意边界：不展示内部经营参数和招商信息。"
            )
        return (
            f"用户表达：{claim}。"
            "适用场景：用于顾客能理解的价值说明。"
            "注意边界：不承诺疗效、收益或未验证结果。"
        )

    suffix = answer_suffix_for(intent, scenario)
    return f"结论：{claim}。{suffix}" if suffix else f"结论：{claim}。"


def contextualize_claim_for_question(question: str, intent: str, claim: str) -> str:
    if intent != "product_system":
        return claim
    for topic in ["清泡调补养", "泡脚方", "产品体系", "草本泡脚", "一人一方"]:
        if topic in question and topic not in claim:
            return f"{topic}：{claim}"
    return claim


def build_direct_answer(question: str, intent: str, evidence: list[dict[str, Any]], scenario: str = "创始人内部决策") -> str:
    if not evidence:
        return f"结论：当前知识库无法可靠回答“{question}”。需要补充资料或确认权威版本后再形成判断。"

    claim, _title = extract_primary_claim(evidence, intent)
    if not claim:
        return f"结论：当前知识库没有可直接用于回答“{question}”的干净业务结论。需要补充权威资料或人工复核后再输出。"
    claim = contextualize_claim_for_question(question, intent, claim)
    return role_specific_answer_for_claim(intent, scenario, claim)


def synthesize_answer(question: str, query: str, items: list[dict[str, Any]], scenario: str = "创始人内部决策") -> dict[str, Any]:
    intent, audience = classify_intent(question, items)
    evidence = build_evidence(items, intent=intent)
    conflicts = detect_conflicts(question, evidence)
    confidence = confidence_for(evidence, conflicts)
    corrections = build_corrections(question, evidence, intent)
    next_actions = build_next_actions(intent, confidence, conflicts, scenario=scenario)

    answer = build_direct_answer(question, intent, evidence, scenario=scenario)
    needs_review = confidence != "high" or bool(conflicts)

    reasoning = []
    if evidence:
        reasoning.append(f"检索到 {len(evidence)} 条可引用证据。")
        domains = sorted({item.get("domain") for item in evidence if item.get("domain")})
        if domains:
            reasoning.append("证据覆盖领域：" + "、".join(domains) + "。")
        reasoning.append("回答优先采用来源文件中的明确表述，避免只按关键词堆叠。")
    else:
        reasoning.append("没有可引用证据，不应强行生成确定结论。")
    if conflicts:
        reasoning.append("存在冲突或证据弱点，需要先复核。")

    result_card = build_result_card(
        intent=intent,
        scenario=scenario,
        answer=answer,
        evidence=evidence,
        confidence=confidence,
        conflicts=conflicts,
        needs_review=needs_review,
    )

    return {
        "question": question,
        "query": query,
        "intent": intent,
        "audience": audience,
        "scenario": scenario,
        "answer": answer,
        "usage": usage_for(intent, scenario),
        "applicable_scenarios": applicable_scenarios_for(intent, audience, scenario),
        "answer_status": answer_status_for(confidence, needs_review),
        "result_card": result_card,
        "reasoning": reasoning,
        "evidence": evidence,
        "sources": evidence,
        "conflicts": conflicts,
        "corrections": corrections,
        "confidence": confidence,
        "next_actions": next_actions,
        "needs_review": needs_review,
    }
