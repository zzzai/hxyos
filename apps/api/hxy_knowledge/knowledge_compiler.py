from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


OVERCLAIM_TERMS = ["治疗", "治愈", "包好", "保证有效", "一定有效", "稳赚", "一定回本", "药到病除", "医学诊断", "冬病夏治"]
FORBIDDEN_REFERENCE_MARKERS = [
    "禁止",
    "禁用",
    "不能承诺",
    "不能说",
    "不要说",
    "不要把",
    "不能把",
    "不能出现",
    "有没有",
    "如果暗示",
    "必须删除",
    "必须改写",
    "说成治疗",
    "不得",
    "不允许",
    "绝对不能",
    "错误话术",
    "不要这样说",
]
SAFE_BOUNDARY_PATTERNS = [
    "不做治疗",
    "不做诊疗",
    "不说治什么",
    "不是医疗机构",
    "不是药品",
    "不能替代医疗",
    "不能替代治疗",
    "不能替代医院",
    "不能替代药品",
    "不替代医疗",
    "不替代治疗",
    "不替代医院",
    "不替代药品",
]
NOISE_TERMS = ["PDF_TEXT_START", "资料状态：reference", "权威使用：false", "人工复核：required", "---"]
HXY_TERMS = ["荷小悦", "清泡调补养", "清泡", "调泡", "补泡", "养泡", "社区小店", "草本真现煮"]
COMPETITOR_ONLY_TERMS = ["奈晚", "谷小推", "郑远元", "LANN", "蘭泰式", "秀域", "足康树", "素可泰", "长风拨筋", "贡小推"]
TOPIC_HINTS = {
    "risk_medical": ["治疗", "治愈", "医学", "诊断", "疗效", "医院", "药品", "一次见效", "包好", "保证有效"],
    "brand_position": ["定位", "品牌", "核爆点", "品类", "轻养生", "足疗", "社区草本"],
    "product_qing_tiao_bu_yang": ["清泡调补养", "清泡", "调泡", "补泡", "养泡", "草本", "泡脚"],
    "store_model": ["社区小店", "门店模型", "小店", "房间数量", "人员配置", "单店模型", "坪效", "人效"],
    "unit_economics": ["投资", "回本", "客单价", "利润", "成本", "租金", "毛利", "现金流"],
    "employee_script": ["员工", "话术", "技师", "接待", "推荐", "培训", "复训"],
    "competitor": COMPETITOR_ONLY_TERMS,
}
REVIEW_DOMAIN_HINTS = {
    "store_model": ["门店模型", "小店", "社区小店", "面积", "房间", "人员配置", "单店模型", "坪效", "人效"],
    "competitor_research": ["竞品", "奈晚", "谷小推", "郑远元", "LANN", "秀域", "足康树", "品牌数据", "排名"],
    "unit_economics": ["投资", "回本", "客单价", "利润", "成本", "租金", "毛利", "现金流"],
    "product_system": ["清泡", "调泡", "补泡", "养泡", "草本", "泡脚", "产品体系"],
    "employee_script": ["员工", "话术", "技师", "接待", "推荐", "培训", "复训"],
    "risk_boundary": ["治疗", "治愈", "保证", "一定有效", "稳赚", "医学", "禁用", "不能承诺"],
    "brand_positioning": ["定位", "品牌", "核爆点", "足疗", "轻养生"],
}
CORE_DECISION_TOPIC_DEFINITIONS = {
    "brand_positioning": {
        "title": "品牌战略与核爆点定位",
        "decision_question": "这个判断现在能不能作为首店开业和对外口径的依据？",
        "why_it_matters": "定位没定清楚，前台话术、门头、内容和员工训练都会漂。",
        "next_action": "补齐用户原话、复述测试、付费理由和替代方案。",
        "review_owner": "创始人",
        "triggers": ["定位", "品牌", "核爆点", "轻恢复", "轻养生", "足疗", "目标客群"],
    },
    "customer_evidence": {
        "title": "顾客证据与首店验证",
        "decision_question": "这些判断有没有真实顾客原话、复述、付费理由和替代方案支撑？",
        "why_it_matters": "初创阶段最怕自我感觉正确，首店开业前必须先验证顾客是否听得懂、愿意来、愿意付费。",
        "next_action": "把资料转成访谈问题和证据缺口，优先补 8-12 条目标用户原话。",
        "review_owner": "创始人/运营负责人",
        "triggers": ["用户原话", "顾客原话", "访谈", "复述", "付费理由", "替代方案", "首店", "验证"],
    },
    "product_system": {
        "title": "产品服务体系与清泡调补养",
        "decision_question": "清泡调补养、泡脚按摩组合和项目菜单，现在能不能被员工讲清、被顾客理解？",
        "why_it_matters": "产品说不清，菜单、价格、推荐路径和复购都会乱。",
        "next_action": "先确认主服务、组合服务、禁用功效和员工推荐标准话术。",
        "review_owner": "产品/运营负责人",
        "triggers": ["清泡调补养", "清泡", "调泡", "补泡", "养泡", "产品", "项目", "菜单", "泡脚", "按摩"],
    },
    "employee_script": {
        "title": "员工可执行话术与训练",
        "decision_question": "员工是否能不用创始人解释，就把这件事说清楚且不说过头？",
        "why_it_matters": "门店交付靠员工现场表达，话术不稳定会直接造成转化、投诉和合规风险。",
        "next_action": "把可说、慎说、不能说拆成训练题、标准回答和复训任务。",
        "review_owner": "店长/运营培训负责人",
        "triggers": ["员工", "话术", "技师", "接待", "推荐", "培训", "复训", "标准说法"],
    },
    "risk_boundary": {
        "title": "合规与功效表达边界",
        "decision_question": "哪些表达必须禁用，哪些只能作为内部提醒，哪些可以改成安全话术？",
        "why_it_matters": "医疗化、疗效保证和夸大宣传是当前对外传播与员工话术的最高风险。",
        "next_action": "先生成禁用表达、替代表达和发布前预检规则，再进入人工复核。",
        "review_owner": "运营/合规负责人",
        "triggers": ["治疗", "治愈", "疗效", "保证", "见效", "医疗", "诊疗", "药品", "禁用", "不能承诺"],
    },
    "first_store_operations": {
        "title": "首店开业动作与SOP",
        "decision_question": "这些内容能不能转成首店今天要做的动作、SOP 或复盘指标？",
        "why_it_matters": "HXY 当前阶段不是抽象学习资料，而是要服务第一家店开业、训练、验证和复盘。",
        "next_action": "把可执行内容转成今日动作、SOP 草稿、训练任务或开业检查项。",
        "review_owner": "运营负责人",
        "triggers": ["开业", "首店", "SOP", "流程", "接待", "复盘", "今日动作", "门店"],
    },
}
TOPIC_DRAFT_ASSET_TYPES = {
    "brand_positioning": "positioning_card",
    "customer_evidence": "evidence_task",
    "product_system": "script_card",
    "employee_script": "script_card",
    "risk_boundary": "risk_card",
    "first_store_operations": "sop_card",
}
REVIEW_PACKET_DECISION_OPTIONS = [
    "needs_more_evidence",
    "revise_draft",
    "ready_for_manual_approval",
    "reject",
]
TOPIC_PUBLICATION_REQUIRED_METADATA_FIELDS = [
    "approver",
    "approved_at",
    "knowledge_version",
    "effective_scope",
    "source_evidence_summary",
]
PROMOTION_TARGETS = {
    "positioning_card": "approved_positioning_card",
    "script_card": "approved_script_card",
    "sop_card": "approved_sop_card",
    "risk_card": "approved_risk_boundary_card",
    "evidence_task": "evidence_backlog",
}


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()
    return f"{prefix}:{digest[:16]}"


def _json_fingerprint(payload: Any) -> dict[str, str]:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {"algorithm": "sha256", "digest": hashlib.sha256(canonical.encode("utf-8")).hexdigest()}


def _domain_for(text: str) -> str:
    if any(term in text for term in ["定位", "品牌", "核爆点", "足疗"]):
        return "brand_positioning"
    if any(term in text for term in ["清泡", "调泡", "补泡", "养泡", "产品", "泡脚"]):
        return "product_system"
    if any(term in text for term in ["员工", "话术", "训练", "技师"]):
        return "employee_training"
    if any(term in text for term in ["招商", "回本", "加盟", "收益"]):
        return "franchise_finance"
    if any(term in text for term in ["治疗", "治愈", "医学", "保证有效"]):
        return "risk_boundary"
    return "general"


def _risk_flags(text: str) -> list[str]:
    risk_text = re.sub(r"不一定有效[应果]?", "", text)
    has_overclaim_term = any(term in risk_text for term in OVERCLAIM_TERMS)
    if not has_overclaim_term:
        return []
    if re.search(r"不做.{0,12}治疗", text):
        return []
    if any(marker in text for marker in FORBIDDEN_REFERENCE_MARKERS):
        if text.startswith("错误话术"):
            return ["overclaim_risk"]
        return ["forbidden_expression_reference"]
    if any(pattern in text for pattern in SAFE_BOUNDARY_PATTERNS):
        return []
    if has_overclaim_term:
        return ["overclaim_risk"]
    return []


def _review_group_for(text: str, domain: str | None = None) -> str:
    haystack = f"{domain or ''}\n{text}"
    if domain == "risk_boundary":
        return "risk_boundary"
    if domain == "product_system":
        return "product_system"
    if domain == "employee_training":
        return "employee_script"
    if domain == "franchise_finance":
        return "unit_economics"
    if domain == "brand_positioning":
        return "brand_positioning"
    for group, terms in REVIEW_DOMAIN_HINTS.items():
        if any(term in haystack for term in terms):
            return group
    return "general"


def _is_noise_claim(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return True
    if re.fullmatch(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", stripped):
        return True
    if re.fullmatch(r"(?:\+?86[- ]?)?(?:400[- ]?\d{3}[- ]?\d{4}|1\d{2}[- ]?\d{4}[- ]?\d{4})", stripped):
        return True
    if re.fullmatch(r"[\w.-]+\.(?:com|cn|net|org|io)", stripped, flags=re.IGNORECASE):
        return True
    if re.fullmatch(r"\[.*?\]\(.*?\)", stripped):
        return True
    if any(term in stripped for term in NOISE_TERMS):
        return True
    if "\f" in stripped:
        return True
    digit_count = sum(char.isdigit() for char in stripped)
    chinese_count = sum("\u4e00" <= char <= "\u9fff" for char in stripped)
    if len(stripped) <= 14 and digit_count >= 2:
        return True
    if chinese_count < 4 and digit_count >= 3:
        return True
    return False


def _clean_claim_fragment(text: str) -> str:
    cleaned = re.sub(r"!\[[^\]]*]\([^)]+\)", " ", text)
    cleaned = re.sub(r"\[[^\]]*]\([^)]+\)", " ", cleaned)
    cleaned = cleaned.replace("\u0001", " ").replace("\ufeff", " ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" \t\r\n#*-|")
    return cleaned


def _normalise_claim_key(text: str) -> str:
    cleaned = _clean_claim_fragment(text).lower()
    cleaned = re.sub(r"^(?:第?[一二三四五六七八九十百千万\d]+[、.．:：-]?)+", "", cleaned)
    return "".join(char for char in cleaned if char.isalnum())


def _topic_for_claim(text: str, domain: str | None = None) -> str:
    haystack = f"{domain or ''}\n{text}"
    for topic, terms in TOPIC_HINTS.items():
        if any(term in haystack for term in terms):
            return topic
    key = _normalise_claim_key(text)
    return f"literal_{key[:16] or 'general'}"


def _cluster_key_for_review_item(item: dict[str, Any]) -> str:
    group = str(item.get("review_group") or "general")
    source_class = str(item.get("source_class") or "unknown")
    if source_class == "external_reference":
        return f"{group}:external_reference"
    topic = _topic_for_claim(str(item.get("claim") or ""), str(item.get("domain") or ""))
    return f"{group}:{topic}"


def _source_class_for(sources: list[str]) -> str:
    joined = "\n".join(sources)
    if "09_风险与合规" in joined or "风险与合规" in joined:
        return "risk_compliance"
    if "09_知识库与参考资料" in joined:
        return "external_reference"
    if any(
        marker in joined
        for marker in [
            "01_市场洞察",
            "02_战略方向",
            "03_门店模型",
            "04_产品系统",
            "05_运营方法",
            "06_融资商务",
            "07_演示素材",
        ]
    ):
        return "hxy_owned"
    return "general"


def _source_rank(source_class: str) -> int:
    return {
        "risk_compliance": 0,
        "hxy_owned": 1,
        "general": 2,
        "external_reference": 3,
    }.get(source_class, 2)


def _has_project_context(text: str, source_class: str) -> bool:
    if source_class in {"risk_compliance", "hxy_owned"}:
        return True
    if any(term in text for term in HXY_TERMS):
        return True
    return "员工" in text and any(marker in text for marker in FORBIDDEN_REFERENCE_MARKERS)


def _review_item_for_claim(claim: dict[str, Any]) -> dict[str, Any] | None:
    raw_text = str(claim.get("claim") or "")
    if _is_noise_claim(raw_text):
        return None
    text = _clean_claim_fragment(raw_text)
    sources = [str(source) for source in (claim.get("sources") or [])]
    source_class = _source_class_for(sources)
    score = _claim_value_score({**claim, "claim": text, "sources": sources, "source_class": source_class})
    if score <= 0:
        return None
    group = _review_group_for(text, str(claim.get("domain") or ""))
    risk_flags = list(claim.get("risk_flags") or [])
    project_context = _has_project_context(text, source_class)
    priority = "high" if (risk_flags and project_context) or score >= 0.8 else ("medium" if score >= 0.6 else "low")
    reviewer = "运营/合规负责人" if risk_flags or group == "risk_boundary" else "创始人/运营负责人"
    recommended_action = "先复核风险边界，禁止直接发布。" if risk_flags else "复核来源和业务适用范围，通过后生成答案卡。"
    return {
        "version": "hxy-review-queue-item.v1",
        "claim_id": claim.get("claim_id"),
        "claim": text,
        "domain": claim.get("domain") or "general",
        "review_group": group,
        "priority": priority,
        "score": score,
        "source_class": source_class,
        "risk_flags": risk_flags,
        "sources": sources,
        "status": "needs_review",
        "official_use_allowed": False,
        "requires_human_review": True,
        "recommended_reviewer": reviewer,
        "recommended_action": recommended_action,
    }


def _claim_value_score(claim: dict[str, Any]) -> float:
    text = str(claim.get("claim") or "")
    domain = str(claim.get("domain") or "")
    if _is_noise_claim(text):
        return 0.0
    source_class = str(claim.get("source_class") or _source_class_for([str(source) for source in (claim.get("sources") or [])]))
    project_context = _has_project_context(text, source_class)
    score = 0.35
    group = _review_group_for(text, domain)
    if group != "general":
        score += 0.2 if project_context else 0.05
    if claim.get("risk_flags"):
        score += 0.35 if project_context else 0.05
    if any(term in text for terms in REVIEW_DOMAIN_HINTS.values() for term in terms):
        score += 0.15
    if any(term in text for term in HXY_TERMS):
        score += 0.25
    if any(term in text for term in COMPETITOR_ONLY_TERMS) and not any(term in text for term in HXY_TERMS):
        score -= 0.2
    if source_class == "risk_compliance":
        score += 0.25
    elif source_class == "hxy_owned":
        score += 0.18
    elif source_class == "external_reference":
        score -= 0.3
    if 18 <= len(text) <= 220:
        score += 0.1
    if claim.get("sources"):
        score += 0.08
    return round(min(score, 1.0), 3)


def _sentences(text: str) -> list[str]:
    candidates: list[str] = []
    for line in text.splitlines():
        line = _clean_claim_fragment(line)
        if not line:
            continue
        candidates.extend(re.split(r"[。！？!?]\s*", line))
    return [item for item in (_clean_claim_fragment(candidate) for candidate in candidates) if len(item) >= 8 and not _is_noise_claim(item)]


def compile_material(material: dict[str, Any]) -> dict[str, Any]:
    content = str(material.get("content") or "")
    source_path = str(material.get("source_path") or material.get("asset_id") or "")
    title = str(material.get("title") or Path(source_path).stem or "未命名资料")
    extract_id = _stable_id("hxy-extract", source_path, content)
    return {
        "version": "hxy-structured-extract.v1",
        "extract_id": extract_id,
        "asset_id": material.get("asset_id") or extract_id,
        "title": title,
        "content": content,
        "domain": _domain_for(f"{title}\n{content}"),
        "status": "reference",
        "memory_layer": "L1_structured_extract",
        "sources": [source_path] if source_path else [],
        "confidence": 0.5,
        "official_use_allowed": False,
        "requires_human_review": True,
    }


def extract_candidate_claims(extract: dict[str, Any]) -> list[dict[str, Any]]:
    content = str(extract.get("content") or "")
    sources = [str(item) for item in (extract.get("sources") or [])]
    claims = []
    for sentence in _sentences(content):
        claim_id = _stable_id("hxy-claim", str(extract.get("extract_id") or ""), sentence)
        claims.append(
            {
                "version": "hxy-candidate-claim.v1",
                "claim_id": claim_id,
                "claim": sentence,
                "domain": _domain_for(sentence),
                "status": "current_candidate",
                "memory_layer": "L2_candidate_claim",
                "sources": sources,
                "confidence": 0.5,
                "requires_human_review": True,
                "official_use_allowed": False,
                "risk_flags": _risk_flags(sentence),
                "review_group": _review_group_for(sentence),
            }
        )
    return claims


def build_review_queue(claims: list[dict[str, Any]], limit: int = 20) -> dict[str, Any]:
    triage = build_claim_triage(claims, limit=limit)
    items = list(triage["items"])
    grouped: dict[str, int] = {}
    for cluster in triage["clusters"]:
        group = str(cluster.get("review_group") or "general")
        grouped[group] = grouped.get(group, 0) + 1
    return {
        "version": "hxy-review-queue.v1",
        "total_claim_count": len(claims),
        "noise_claim_count": triage["noise_claim_count"],
        "duplicate_claim_count": triage["duplicate_claim_count"],
        "reviewable_claim_count": triage["unique_reviewable_claim_count"],
        "cluster_count": triage["cluster_count"],
        "selected_count": len(items),
        "group_counts": grouped,
        "items": items[: max(0, limit)],
    }


def _core_topic_key_for_item(item: dict[str, Any]) -> str:
    text = str(item.get("claim") or "")
    group = str(item.get("review_group") or "")
    domain = str(item.get("domain") or "")
    source_class = str(item.get("source_class") or "")
    haystack = f"{group}\n{domain}\n{text}"
    if item.get("risk_flags") or group == "risk_boundary" or source_class == "risk_compliance":
        return "risk_boundary"
    for key, definition in CORE_DECISION_TOPIC_DEFINITIONS.items():
        if key == "risk_boundary":
            continue
        if any(term in haystack for term in definition["triggers"]):
            return key
    if group == "brand_positioning":
        return "brand_positioning"
    if group == "product_system":
        return "product_system"
    if group == "employee_script":
        return "employee_script"
    if group == "store_model":
        return "first_store_operations"
    return ""


def build_core_decision_topics(claims: list[dict[str, Any]], limit: int = 12) -> dict[str, Any]:
    topics: dict[str, dict[str, Any]] = {}
    evidence_count = 0
    for claim in claims:
        item = _review_item_for_claim(claim)
        if item is None:
            continue
        source_class = str(item.get("source_class") or "general")
        text = str(item.get("claim") or "")
        has_hxy_context = _has_project_context(text, source_class)
        topic_key = _core_topic_key_for_item(item)
        if not topic_key:
            continue
        if source_class == "external_reference" and not has_hxy_context:
            continue
        definition = CORE_DECISION_TOPIC_DEFINITIONS[topic_key]
        topic = topics.setdefault(
            topic_key,
            {
                "version": "hxy-core-decision-topic.v1",
                "topic_id": f"hxy-core-topic:{topic_key}",
                "topic_key": topic_key,
                "title": definition["title"],
                "decision_question": definition["decision_question"],
                "why_it_matters": definition["why_it_matters"],
                "next_action": definition["next_action"],
                "review_owner": definition["review_owner"],
                "priority": "P1",
                "evidence_count": 0,
                "source_samples": [],
                "source_classes": [],
                "_sort_weight": 0.0,
                "official_use_allowed": False,
                "requires_human_review": True,
            },
        )
        evidence_count += 1
        topic["evidence_count"] += 1
        topic["_sort_weight"] += float(item.get("score") or 0)
        if item.get("risk_flags"):
            topic["priority"] = "P0"
        elif topic["priority"] != "P0" and topic_key in {"brand_positioning", "customer_evidence", "product_system"}:
            topic["priority"] = "P0"
        if source_class and source_class not in topic["source_classes"]:
            topic["source_classes"].append(source_class)
        for source in item.get("sources") or []:
            label = Path(str(source)).name
            if label and label not in topic["source_samples"] and len(topic["source_samples"]) < 4:
                topic["source_samples"].append(label)

    priority_order = {"P0": 0, "P1": 1, "P2": 2}
    items = sorted(
        topics.values(),
        key=lambda topic: (
            priority_order.get(str(topic.get("priority") or "P2"), 3),
            -int(topic.get("evidence_count") or 0),
            -float(topic.get("_sort_weight") or 0),
            str(topic.get("title") or ""),
        ),
    )
    public_items: list[dict[str, Any]] = []
    for item in items[: max(0, limit)]:
        public = dict(item)
        public.pop("_sort_weight", None)
        public_items.append(public)
    return {
        "version": "hxy-core-decision-topics.v1",
        "status": "ready" if public_items else "empty",
        "core_topic_count": len(public_items),
        "total_core_topic_count": len(items),
        "evidence_count": evidence_count,
        "items": public_items,
        "raw_claims_hidden": True,
        "official_use_allowed": False,
        "requires_human_review": True,
        "authority_rule": "core_decision_topics_are_review_objects_claim_triage_is_machine_intermediate",
        "next_actions": [
            "先围绕 P0 核心议题补证据，不人工逐条审核海量 candidate claim。",
            "通过人工复核后，核心议题才能转成定位卡、话术卡、SOP 或风险边界卡。",
        ],
    }


def _topic_draft_asset_type(topic: dict[str, Any]) -> str:
    topic_key = str(topic.get("topic_key") or "")
    if topic_key == "risk_boundary":
        return "risk_card"
    evidence_count = int(topic.get("evidence_count") or 0)
    if evidence_count < 2:
        return "evidence_task"
    return TOPIC_DRAFT_ASSET_TYPES.get(topic_key, "evidence_task")


def _topic_draft_payload(topic: dict[str, Any], asset_type: str) -> dict[str, Any]:
    title = str(topic.get("title") or "核心经营议题")
    next_action = str(topic.get("next_action") or "补齐证据后再复核。")
    if asset_type == "risk_card":
        return {
            "summary": f"{title}必须先拆成禁用表达、替代表达和发布前预检规则。",
            "recommended_use": "仅供内部合规复核，不可作为对外正式口径。",
            "evidence_gaps": ["确认禁用表达来源", "补充安全替代表达", "确认适用渠道"],
            "next_actions": ["整理禁用表达", "生成替代表达", "进入人工合规复核"],
        }
    if asset_type == "evidence_task":
        return {
            "summary": f"{title}当前证据不足，应先补证据，不要急着定稿。",
            "recommended_use": "补证据任务，不可作为正式知识引用。",
            "evidence_gaps": ["补齐真实顾客原话", "补齐员工复述结果", "补齐付费理由或替代方案"],
            "next_actions": [next_action],
        }
    if asset_type == "positioning_card":
        return {
            "summary": f"{title}可以先形成定位卡草稿，但必须用顾客证据和员工复述测试校准。",
            "recommended_use": "内部定位草稿，供创始人复核，不可作为对外正式口径。",
            "evidence_gaps": ["补齐目标用户原话", "完成顾客复述测试", "确认替代方案和付费理由"],
            "next_actions": [next_action],
        }
    if asset_type == "script_card":
        return {
            "summary": f"{title}可以先形成话术卡草稿，但必须确认员工能讲清且不说过头。",
            "recommended_use": "内部话术草稿，供训练和复核，不可直接对外发布。",
            "evidence_gaps": ["确认员工是否能 30 秒讲清", "确认顾客是否能复述", "确认禁用功效表达"],
            "next_actions": [next_action],
        }
    if asset_type == "sop_card":
        return {
            "summary": f"{title}可以先形成 SOP 草稿，但必须经过首店执行验证。",
            "recommended_use": "内部 SOP 草稿，供首店试运行，不可作为正式制度。",
            "evidence_gaps": ["确认适用门店场景", "补齐执行负责人", "补齐复盘指标"],
            "next_actions": [next_action],
        }
    return {
        "summary": f"{title}可以先生成草稿资产，但必须人工复核后才能进入正式知识库。",
        "recommended_use": "内部草稿，供人工复核和改写。",
        "evidence_gaps": ["确认来源是否足够", "确认是否可执行", "确认是否存在合规风险"],
        "next_actions": [next_action],
    }


def build_topic_draft_assets(core_decision_topics: dict[str, Any], limit: int = 12) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for topic in core_decision_topics.get("items") or []:
        if not isinstance(topic, dict):
            continue
        topic_key = str(topic.get("topic_key") or "")
        fallback_key = _stable_id("topic", str(topic.get("title") or ""))
        asset_type = _topic_draft_asset_type(topic)
        priority = "P0" if topic_key == "risk_boundary" else str(topic.get("priority") or "P1")
        items.append(
            {
                "version": "hxy-topic-draft-asset.v1",
                "asset_id": f"hxy-topic-draft:{topic_key or fallback_key}",
                "topic_id": topic.get("topic_id") or "",
                "topic_key": topic_key,
                "asset_type": asset_type,
                "title": topic.get("title") or "",
                "status": "needs_review",
                "priority": priority,
                "review_owner": topic.get("review_owner") or "",
                "decision_question": topic.get("decision_question") or "",
                "draft": _topic_draft_payload(topic, asset_type),
                "source_samples": list(topic.get("source_samples") or []),
                "source_classes": list(topic.get("source_classes") or []),
                "official_use_allowed": False,
                "requires_human_review": True,
                "authority_rule": "draft_assets_are_not_approved_knowledge",
            }
        )
    public_items = items[: max(0, limit)]
    return {
        "version": "hxy-topic-draft-assets.v1",
        "status": "ready" if public_items else "empty",
        "count": len(public_items),
        "total": len(items),
        "items": public_items,
        "official_use_allowed": False,
        "requires_human_review": True,
        "authority_rule": "draft_assets_are_not_approved_knowledge",
    }


def _review_questions_for_asset(asset: dict[str, Any]) -> list[str]:
    asset_type = str(asset.get("asset_type") or "evidence_task")
    if asset_type == "positioning_card":
        return [
            "这个判断是否有真实顾客原话支撑？",
            "员工能否不用创始人解释就讲清？",
            "顾客听完能否复述，并说出为什么愿意付费？",
        ]
    if asset_type == "script_card":
        return [
            "员工能否在 30 秒内讲清且不说过头？",
            "顾客能否复述核心意思？",
            "是否避开医疗、保证效果和夸大表达？",
        ]
    if asset_type == "sop_card":
        return [
            "这套动作是否有明确负责人？",
            "首店现场是否能按步骤执行？",
            "复盘指标和失败处理是否清楚？",
        ]
    if asset_type == "risk_card":
        return [
            "哪些禁用表达必须拦截？",
            "对应的安全替代表达是什么？",
            "适用于哪些渠道和岗位？",
        ]
    return [
        "缺哪些证据？",
        "谁负责补证据？",
        "什么时候回到复核流程？",
    ]


def build_topic_review_packets(topic_draft_assets: dict[str, Any], limit: int = 12) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for asset in topic_draft_assets.get("items") or []:
        if not isinstance(asset, dict):
            continue
        asset_type = str(asset.get("asset_type") or "evidence_task")
        topic_key = str(asset.get("topic_key") or "")
        draft = asset.get("draft") if isinstance(asset.get("draft"), dict) else {}
        packet_key = topic_key or str(asset.get("asset_id") or _stable_id("review-packet", str(asset.get("title") or "")))
        priority = "P0" if asset_type == "risk_card" else str(asset.get("priority") or "P1")
        items.append(
            {
                "version": "hxy-topic-review-packet.v1",
                "packet_id": f"hxy-topic-review-packet:{packet_key}",
                "asset_id": asset.get("asset_id") or "",
                "topic_key": topic_key,
                "asset_type": asset_type,
                "title": asset.get("title") or "",
                "priority": priority,
                "review_owner": asset.get("review_owner") or "运营负责人",
                "status": "open",
                "review_questions": _review_questions_for_asset(asset),
                "evidence_gaps": list(draft.get("evidence_gaps") or []),
                "next_actions": list(draft.get("next_actions") or []),
                "decision_options": list(REVIEW_PACKET_DECISION_OPTIONS),
                "promotion_target": PROMOTION_TARGETS.get(asset_type, "evidence_backlog"),
                "blocked_actions": [
                    "不能作为对外正式口径",
                    "不能写入 approved answer cards",
                    "不能自动发布",
                ],
                "source_samples": list(asset.get("source_samples") or []),
                "official_use_allowed": False,
                "requires_human_review": True,
                "authority_rule": "review_packets_are_tasks_not_approval",
            }
        )
    public_items = items[: max(0, limit)]
    return {
        "version": "hxy-topic-review-packets.v1",
        "status": "ready" if public_items else "empty",
        "count": len(public_items),
        "total": len(items),
        "items": public_items,
        "official_use_allowed": False,
        "requires_human_review": True,
        "authority_rule": "review_packets_are_tasks_not_approval",
    }


def build_topic_review_decisions_stub(topic_review_packets: dict[str, Any], limit: int = 50) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for packet in topic_review_packets.get("items") or []:
        if not isinstance(packet, dict):
            continue
        allowed_decisions = list(packet.get("decision_options") or REVIEW_PACKET_DECISION_OPTIONS)
        items.append(
            {
                "packet_id": packet.get("packet_id") or "",
                "asset_id": packet.get("asset_id") or "",
                "topic_key": packet.get("topic_key") or "",
                "asset_type": packet.get("asset_type") or "evidence_task",
                "title": packet.get("title") or "",
                "priority": packet.get("priority") or "P1",
                "review_owner": packet.get("review_owner") or "运营负责人",
                "promotion_target": packet.get("promotion_target") or "evidence_backlog",
                "decision": "pending",
                "status": "pending_decision",
                "allowed_decisions": allowed_decisions,
                "official_use_allowed": False,
                "requires_human_review": True,
            }
        )
    public_items = items[: max(0, limit)]
    return {
        "version": "hxy-topic-review-decisions-stub.v1",
        "target_filename": "topic-review-decisions.json",
        "decision_count": len(public_items),
        "total": len(items),
        "allowed_decisions": list(REVIEW_PACKET_DECISION_OPTIONS),
        "items": public_items,
        "official_use_allowed": False,
        "publish_allowed": False,
        "write_to_database": False,
        "requires_human_review": True,
        "authority_rule": "topic_review_decisions_do_not_publish_official_knowledge",
    }


def build_topic_review_decisions_sample(decision_stub: dict[str, Any]) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for item in decision_stub.get("items") or []:
        if not isinstance(item, dict):
            continue
        items.append(
            {
                "packet_id": item.get("packet_id") or "",
                "decision": "pending",
                "reviewer": "",
                "rationale": "",
                "evidence_summary": "",
                "next_step": "",
                "allowed_decisions": list(item.get("allowed_decisions") or REVIEW_PACKET_DECISION_OPTIONS),
                "official_use_allowed": False,
                "publish_allowed": False,
            }
        )
    return {
        "version": "hxy-topic-review-decisions-sample.v1",
        "target_filename": decision_stub.get("target_filename") or "topic-review-decisions.json",
        "initialized_from_stub": True,
        "decision_count": len(items),
        "items": items,
        "official_use_allowed": False,
        "publish_allowed": False,
        "write_to_database": False,
        "requires_human_review": True,
        "authority_rule": "topic_review_decisions_sample_is_editable_not_approval",
    }


def validate_topic_review_decisions(topic_review_packets: dict[str, Any], decisions: dict[str, Any] | None) -> dict[str, Any]:
    decisions_payload = decisions if isinstance(decisions, dict) else {}
    packets_by_id = {
        str(packet.get("packet_id") or ""): packet
        for packet in (topic_review_packets.get("items") or [])
        if isinstance(packet, dict) and packet.get("packet_id")
    }
    errors: list[dict[str, Any]] = []
    publish_block_count = 0
    for flag in ["official_use_allowed", "publish_allowed", "write_to_database"]:
        if decisions_payload.get(flag) is True:
            publish_block_count += 1
            errors.append(
                {
                    "code": f"{flag}_must_be_false",
                    "message": f"{flag} 必须为 false；topic review decisions 不能发布或写库。",
                }
            )

    if decisions_payload.get("version") not in {None, "hxy-topic-review-decisions.v1"}:
        errors.append(
            {
                "code": "invalid_version",
                "message": "决策文件版本必须是 hxy-topic-review-decisions.v1。",
            }
        )

    items: list[dict[str, Any]] = []
    manual_decision_count = 0
    pending_count = 0
    invalid_decision_count = 0
    ready_for_manual_approval_count = 0
    for raw_item in decisions_payload.get("items") or []:
        if not isinstance(raw_item, dict):
            continue
        packet_id = str(raw_item.get("packet_id") or "")
        packet = packets_by_id.get(packet_id)
        allowed = list(packet.get("decision_options") or REVIEW_PACKET_DECISION_OPTIONS) if packet else list(REVIEW_PACKET_DECISION_OPTIONS)
        decision = str(raw_item.get("decision") or "pending")
        item_errors: list[str] = []
        if not packet:
            item_errors.append("unknown_packet_id")
        if decision == "pending":
            pending_count += 1
            status = "pending_decision"
        elif decision not in allowed:
            invalid_decision_count += 1
            item_errors.append(f"invalid_decision:{decision}")
            status = "invalid"
        else:
            manual_decision_count += 1
            status = "valid_manual_decision"
            if not str(raw_item.get("reviewer") or "").strip():
                item_errors.append("missing_reviewer")
            if not str(raw_item.get("rationale") or "").strip():
                item_errors.append("missing_rationale")
            if decision == "ready_for_manual_approval":
                ready_for_manual_approval_count += 1
        if item_errors:
            status = "invalid" if decision != "pending" else "pending_decision"
            for error in item_errors:
                errors.append(
                    {
                        "code": error,
                        "packet_id": packet_id,
                        "message": f"{packet_id or 'unknown'} 决策无效：{error}。ready_for_manual_approval 也不是批准。",
                    }
                )
        items.append(
            {
                "packet_id": packet_id,
                "decision": decision,
                "status": status,
                "errors": item_errors,
                "promotion_target": packet.get("promotion_target") if packet else "",
                "official_use_allowed": False,
                "publish_allowed": False,
            }
        )

    valid = not errors and invalid_decision_count == 0
    return {
        "version": "hxy-topic-review-decisions-validation.v1",
        "valid": valid,
        "decision_count": len(items),
        "manual_decision_count": manual_decision_count,
        "pending_count": pending_count,
        "invalid_decision_count": invalid_decision_count,
        "ready_for_manual_approval_count": ready_for_manual_approval_count,
        "approved_count": 0,
        "publish_block_count": publish_block_count,
        "error_count": len(errors),
        "errors": errors,
        "items": items,
        "official_use_allowed": False,
        "publish_allowed": False,
        "write_to_database": False,
        "requires_human_review": True,
        "authority_rule": "ready_for_manual_approval_is_not_approved_knowledge",
    }


def topic_publication_metadata_template() -> dict[str, str]:
    return {field: "" for field in TOPIC_PUBLICATION_REQUIRED_METADATA_FIELDS}


def _missing_topic_publication_metadata_fields(metadata: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    for field in TOPIC_PUBLICATION_REQUIRED_METADATA_FIELDS:
        value = metadata.get(field)
        if value is None or str(value).strip() == "":
            missing.append(field)
    return missing


def build_topic_publication_preflight(topic_review_packets: dict[str, Any], decisions: dict[str, Any] | None) -> dict[str, Any]:
    validation = validate_topic_review_decisions(topic_review_packets, decisions)
    decisions_payload = decisions if isinstance(decisions, dict) else {}
    packets_by_id = {
        str(packet.get("packet_id") or ""): packet
        for packet in (topic_review_packets.get("items") or [])
        if isinstance(packet, dict) and packet.get("packet_id")
    }
    items: list[dict[str, Any]] = []
    for decision in decisions_payload.get("items") or []:
        if not isinstance(decision, dict):
            continue
        if str(decision.get("decision") or "") != "ready_for_manual_approval":
            continue
        packet_id = str(decision.get("packet_id") or "")
        packet = packets_by_id.get(packet_id, {})
        metadata = decision.get("publication_metadata") if isinstance(decision.get("publication_metadata"), dict) else {}
        missing_fields = _missing_topic_publication_metadata_fields(metadata)
        manual_publication_ready = not missing_fields and bool(validation.get("valid"))
        items.append(
            {
                "packet_id": packet_id,
                "asset_id": packet.get("asset_id") or "",
                "topic_key": packet.get("topic_key") or "",
                "asset_type": packet.get("asset_type") or "evidence_task",
                "title": packet.get("title") or "",
                "promotion_target": packet.get("promotion_target") or "evidence_backlog",
                "status": "ready_for_manual_publication" if manual_publication_ready else "blocked_missing_publication_metadata",
                "manual_publication_ready": manual_publication_ready,
                "missing_fields": missing_fields,
                "publication_metadata": metadata,
                "metadata_template": topic_publication_metadata_template(),
                "official_use_allowed": False,
                "publish_allowed": False,
                "write_to_database": False,
                "authority_rule": "topic_publication_preflight_does_not_publish_official_knowledge",
            }
        )
    ready_count = sum(1 for item in items if item.get("manual_publication_ready") is True)
    blocked_count = len(items) - ready_count
    return {
        "version": "hxy-topic-publication-preflight.v1",
        "valid_decisions": bool(validation.get("valid")),
        "decision_validation": validation,
        "ready_decision_count": len(items),
        "ready_count": ready_count,
        "blocked_count": blocked_count,
        "required_metadata_fields": list(TOPIC_PUBLICATION_REQUIRED_METADATA_FIELDS),
        "metadata_template": topic_publication_metadata_template(),
        "items": items,
        "official_use_allowed": False,
        "publish_allowed": False,
        "write_to_database": False,
        "requires_human_review": True,
        "authority_rule": "topic_publication_preflight_does_not_publish_official_knowledge",
    }


def build_topic_publication_package(publication_preflight: dict[str, Any]) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    for item in publication_preflight.get("items") or []:
        if not isinstance(item, dict) or item.get("manual_publication_ready") is not True:
            continue
        candidates.append(
            {
                "version": "hxy-topic-publication-candidate.v1",
                "packet_id": item.get("packet_id") or "",
                "asset_id": item.get("asset_id") or "",
                "topic_key": item.get("topic_key") or "",
                "asset_type": item.get("asset_type") or "evidence_task",
                "title": item.get("title") or "",
                "promotion_target": item.get("promotion_target") or "evidence_backlog",
                "status": "pending_manual_publication",
                "publication_metadata": item.get("publication_metadata") if isinstance(item.get("publication_metadata"), dict) else {},
                "source": "topic_review_publication_preflight",
                "official_use_allowed": False,
                "publish_allowed": False,
                "write_to_database": False,
                "authority_rule": "topic_publication_package_does_not_publish_official_knowledge",
            }
        )
    return {
        "version": "hxy-topic-publication-package.v1",
        "preflight_version": publication_preflight.get("version") or "",
        "candidate_count": len(candidates),
        "blocked_count": int(publication_preflight.get("blocked_count") or 0),
        "publication_candidates": candidates,
        "official_use_allowed": False,
        "publish_allowed": False,
        "write_to_database": False,
        "requires_human_review": True,
        "authority_rule": "topic_publication_package_does_not_publish_official_knowledge",
    }


TOPIC_DRY_RUN_REQUIRED_FIELDS = ["packet_id", "topic_key", "asset_type", "title", "promotion_target"]
TOPIC_REVIEWED_ASSET_REQUIRED_FIELDS = ["asset_id", "topic_key", "asset_type", "title", "promotion_target"]


def _missing_topic_asset_fields(asset: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    for field in TOPIC_DRY_RUN_REQUIRED_FIELDS:
        value = asset.get(field)
        if value is None or str(value).strip() == "":
            missing.append(field)
    return missing


def _missing_reviewed_topic_asset_fields(asset: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    for field in TOPIC_REVIEWED_ASSET_REQUIRED_FIELDS:
        value = asset.get(field)
        if value is None or str(value).strip() == "":
            missing.append(field)
    return missing


def _draft_topic_asset_payload_from_publication_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "packet_id": candidate.get("packet_id") or "",
        "asset_id": candidate.get("asset_id") or "",
        "topic_key": candidate.get("topic_key") or "",
        "asset_type": candidate.get("asset_type") or "evidence_task",
        "title": candidate.get("title") or "",
        "promotion_target": candidate.get("promotion_target") or "evidence_backlog",
        "status": "draft",
        "target_status_after_manual_import": "approved",
        "review_status_after_manual_import": "approved_v1",
        "publication_metadata": candidate.get("publication_metadata") if isinstance(candidate.get("publication_metadata"), dict) else {},
        "source": "topic_publication_dry_run",
        "official_use_allowed": False,
        "publish_allowed": False,
        "write_to_formal_store": False,
    }


def dry_run_topic_publication_package(publication_package: dict[str, Any]) -> dict[str, Any]:
    candidates = (
        publication_package.get("publication_candidates")
        if isinstance(publication_package.get("publication_candidates"), list)
        else []
    )
    errors: list[dict[str, Any]] = []
    payloads: list[dict[str, Any]] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        packet_id = str(candidate.get("packet_id") or "")
        missing_fields = _missing_topic_asset_fields(candidate)
        if missing_fields:
            errors.append(
                {
                    "code": "missing_topic_asset_fields",
                    "packet_id": packet_id,
                    "missing_fields": missing_fields,
                    "message": "Publication candidate cannot become a topic asset payload because required fields are missing.",
                }
            )
        metadata = candidate.get("publication_metadata") if isinstance(candidate.get("publication_metadata"), dict) else {}
        missing_metadata = _missing_topic_publication_metadata_fields(metadata)
        if missing_metadata:
            errors.append(
                {
                    "code": "missing_publication_metadata",
                    "packet_id": packet_id,
                    "missing_fields": missing_metadata,
                    "message": "Publication candidate is missing required publication metadata.",
                }
            )
        if not missing_fields and not missing_metadata:
            payloads.append(_draft_topic_asset_payload_from_publication_candidate(candidate))
    return {
        "version": "hxy-topic-publication-dry-run.v1",
        "publication_package_fingerprint": _json_fingerprint(publication_package),
        "valid": len(errors) == 0,
        "candidate_count": len(candidates),
        "payload_count": len(payloads),
        "would_write_count": 0,
        "error_count": len(errors),
        "errors": errors,
        "draft_topic_asset_payloads": payloads,
        "official_use_allowed": False,
        "publish_allowed": False,
        "write_to_formal_store": False,
        "requires_human_review": True,
        "authority_rule": "topic_publication_dry_run_does_not_publish_official_knowledge",
    }


def _reviewed_topic_asset_from_draft_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "packet_id": payload.get("packet_id") or "",
        "asset_id": payload.get("asset_id") or "",
        "topic_key": payload.get("topic_key") or "",
        "asset_type": payload.get("asset_type") or "evidence_task",
        "title": payload.get("title") or "",
        "promotion_target": payload.get("promotion_target") or "evidence_backlog",
        "status": "reviewed_pending_import",
        "target_status_after_import": payload.get("target_status_after_manual_import") or "approved",
        "review_status_after_import": payload.get("review_status_after_manual_import") or "approved_v1",
        "source": "topic_reviewed_file_publication",
        "publication_metadata": payload.get("publication_metadata") if isinstance(payload.get("publication_metadata"), dict) else {},
    }


def publish_topic_dry_run_assets_to_reviewed_file(
    dry_run: dict[str, Any],
    *,
    confirm_manual_publication: bool,
) -> dict[str, Any]:
    if confirm_manual_publication is not True:
        return {
            "version": "hxy-topic-reviewed-assets-publication.v1",
            "dry_run_fingerprint": _json_fingerprint(dry_run),
            "published": False,
            "published_count": 0,
            "error_count": 1,
            "errors": [
                {
                    "code": "missing_manual_publication_confirmation",
                    "message": "Explicit manual confirmation is required before writing reviewed topic assets.",
                }
            ],
            "reviewed_topic_assets": [],
            "write_to_database": False,
            "requires_import_step": True,
            "official_use_allowed": False,
            "authority_rule": "topic_reviewed_file_requires_separate_import_to_formal_store",
        }
    if dry_run.get("valid") is False:
        return {
            "version": "hxy-topic-reviewed-assets-publication.v1",
            "dry_run_fingerprint": _json_fingerprint(dry_run),
            "published": False,
            "published_count": 0,
            "error_count": 1,
            "errors": [{"code": "invalid_dry_run", "message": "Cannot review topic assets from an invalid dry-run."}],
            "reviewed_topic_assets": [],
            "write_to_database": False,
            "requires_import_step": True,
            "official_use_allowed": False,
            "authority_rule": "topic_reviewed_file_requires_separate_import_to_formal_store",
        }
    payloads = dry_run.get("draft_topic_asset_payloads") if isinstance(dry_run.get("draft_topic_asset_payloads"), list) else []
    reviewed_assets = [
        _reviewed_topic_asset_from_draft_payload(payload)
        for payload in payloads
        if isinstance(payload, dict)
    ]
    return {
        "version": "hxy-topic-reviewed-assets-publication.v1",
        "dry_run_fingerprint": _json_fingerprint(dry_run),
        "published": True,
        "published_count": len(reviewed_assets),
        "error_count": 0,
        "errors": [],
        "reviewed_topic_assets": reviewed_assets,
        "write_to_database": False,
        "requires_import_step": True,
        "official_use_allowed": False,
        "authority_rule": "topic_reviewed_file_requires_separate_import_to_formal_store",
    }


def _normalise_topic_import_key(value: str) -> str:
    return "".join(str(value or "").strip().lower().split())


def _reviewed_topic_asset_errors(asset: dict[str, Any]) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    missing_fields = _missing_reviewed_topic_asset_fields(asset)
    if missing_fields:
        errors.append({"code": "missing_topic_asset_fields", "missing_fields": missing_fields, "topic_key": asset.get("topic_key") or ""})
    if asset.get("status") != "reviewed_pending_import":
        errors.append(
            {
                "code": "invalid_reviewed_topic_status",
                "topic_key": asset.get("topic_key") or "",
                "status": asset.get("status") or "",
            }
        )
    metadata = asset.get("publication_metadata") if isinstance(asset.get("publication_metadata"), dict) else {}
    missing_metadata = _missing_topic_publication_metadata_fields(metadata)
    if missing_metadata:
        errors.append(
            {
                "code": "missing_publication_metadata",
                "topic_key": asset.get("topic_key") or "",
                "missing_fields": missing_metadata,
            }
        )
    return errors


def validate_topic_reviewed_assets_import_gate(
    reviewed_file: dict[str, Any],
    existing_assets: list[dict[str, Any]],
) -> dict[str, Any]:
    reviewed_assets = (
        reviewed_file.get("reviewed_topic_assets")
        if isinstance(reviewed_file.get("reviewed_topic_assets"), list)
        else []
    )
    existing_topic_targets = {
        (
            _normalise_topic_import_key(str(asset.get("topic_key") or "")),
            _normalise_topic_import_key(str(asset.get("promotion_target") or "")),
        )
        for asset in existing_assets
        if isinstance(asset, dict) and str(asset.get("status") or "") == "approved"
    }
    existing_versions = {
        _normalise_topic_import_key(str((asset.get("publication_metadata") or {}).get("knowledge_version") or ""))
        for asset in existing_assets
        if isinstance(asset, dict) and isinstance(asset.get("publication_metadata"), dict)
    }
    seen_topic_targets: set[tuple[str, str]] = set()
    seen_versions: set[str] = set()
    errors: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    importable_assets: list[dict[str, Any]] = []
    for asset in reviewed_assets:
        if not isinstance(asset, dict):
            continue
        asset_errors = _reviewed_topic_asset_errors(asset)
        if asset_errors:
            errors.extend(asset_errors)
            continue
        topic_target = (
            _normalise_topic_import_key(str(asset.get("topic_key") or "")),
            _normalise_topic_import_key(str(asset.get("promotion_target") or "")),
        )
        metadata = asset.get("publication_metadata") if isinstance(asset.get("publication_metadata"), dict) else {}
        knowledge_version = _normalise_topic_import_key(str(metadata.get("knowledge_version") or ""))
        asset_conflicts: list[dict[str, Any]] = []
        if topic_target in existing_topic_targets or topic_target in seen_topic_targets:
            asset_conflicts.append(
                {
                    "code": "duplicate_topic_target",
                    "topic_key": asset.get("topic_key") or "",
                    "promotion_target": asset.get("promotion_target") or "",
                    "message": "Reviewed topic asset conflicts with an existing or same-batch approved topic target.",
                }
            )
        if knowledge_version and (knowledge_version in existing_versions or knowledge_version in seen_versions):
            asset_conflicts.append(
                {
                    "code": "duplicate_knowledge_version",
                    "topic_key": asset.get("topic_key") or "",
                    "knowledge_version": metadata.get("knowledge_version") or "",
                    "message": "Reviewed topic asset conflicts with an existing or same-batch knowledge_version.",
                }
            )
        if asset_conflicts:
            conflicts.extend(asset_conflicts)
            continue
        seen_topic_targets.add(topic_target)
        if knowledge_version:
            seen_versions.add(knowledge_version)
        importable_assets.append(asset)
    valid = not errors and not conflicts
    return {
        "version": "hxy-topic-reviewed-assets-import-gate.v1",
        "reviewed_file_fingerprint": _json_fingerprint(reviewed_file),
        "existing_topic_assets_fingerprint": _json_fingerprint({"items": existing_assets}),
        "valid": valid,
        "reviewed_asset_count": len(reviewed_assets),
        "importable_count": len(importable_assets),
        "conflict_count": len(conflicts),
        "error_count": len(errors),
        "would_import_count": 0,
        "errors": errors,
        "conflicts": conflicts,
        "importable_topic_assets": importable_assets,
        "write_to_database": False,
        "requires_import_confirmation": True,
        "authority_rule": "topic_import_gate_checks_only_and_does_not_write_database",
    }


def build_claim_triage(claims: list[dict[str, Any]], limit: int = 80) -> dict[str, Any]:
    noise_count = 0
    duplicate_count = 0
    by_normalised_claim: dict[str, dict[str, Any]] = {}
    for claim in claims:
        item = _review_item_for_claim(claim)
        if item is None:
            noise_count += 1
            continue
        normalised_key = _normalise_claim_key(str(item.get("claim") or ""))
        if not normalised_key:
            noise_count += 1
            continue
        existing = by_normalised_claim.get(normalised_key)
        if existing is None:
            item["duplicate_count"] = 0
            item["duplicate_claim_ids_sample"] = []
            by_normalised_claim[normalised_key] = item
            continue

        duplicate_count += 1
        existing["duplicate_count"] = int(existing.get("duplicate_count") or 0) + 1
        duplicate_ids = list(existing.get("duplicate_claim_ids_sample") or [])
        if len(duplicate_ids) < 8:
            duplicate_ids.append(str(item.get("claim_id") or ""))
        existing["duplicate_claim_ids_sample"] = duplicate_ids
        existing_sources = list(existing.get("sources") or [])
        for source in item.get("sources") or []:
            if source not in existing_sources:
                existing_sources.append(source)
        existing["sources"] = existing_sources
        if float(item.get("score") or 0) > float(existing.get("score") or 0):
            for key in [
                "claim_id",
                "claim",
                "domain",
                "review_group",
                "priority",
                "score",
                "risk_flags",
                "recommended_reviewer",
                "recommended_action",
            ]:
                existing[key] = item.get(key)

    clusters_by_key: dict[str, list[dict[str, Any]]] = {}
    for item in by_normalised_claim.values():
        clusters_by_key.setdefault(_cluster_key_for_review_item(item), []).append(item)

    priority_order = {"high": 0, "medium": 1, "low": 2}
    clusters: list[dict[str, Any]] = []
    for cluster_key, members in clusters_by_key.items():
        members.sort(
            key=lambda item: (
                priority_order[str(item.get("priority") or "low")],
                -float(item.get("score") or 0),
                _source_rank(str(item.get("source_class") or "general")),
                -int(item.get("duplicate_count") or 0),
                str(item.get("claim_id") or ""),
            )
        )
        representative = dict(members[0])
        source_set: list[str] = []
        duplicate_total = 0
        for member in members:
            duplicate_total += int(member.get("duplicate_count") or 0)
            for source in member.get("sources") or []:
                if source not in source_set:
                    source_set.append(str(source))
        representative["sources"] = source_set
        representative["duplicate_count"] = int(representative.get("duplicate_count") or 0)
        representative["cluster_member_count"] = len(members)
        representative["cluster_duplicate_count"] = duplicate_total
        representative["cluster_id"] = _stable_id("hxy-claim-cluster", cluster_key)
        representative["cluster_key"] = cluster_key
        representative["similar_claim_ids_sample"] = [str(member.get("claim_id") or "") for member in members[1:9]]
        clusters.append(
            {
                "version": "hxy-claim-cluster.v1",
                "cluster_id": representative["cluster_id"],
                "cluster_key": cluster_key,
                "review_group": representative.get("review_group") or "general",
                "priority": representative.get("priority") or "low",
                "score": representative.get("score") or 0,
                "source_class": representative.get("source_class") or "general",
                "representative_claim_id": representative.get("claim_id"),
                "representative_claim": representative.get("claim"),
                "member_count": len(members),
                "duplicate_count": duplicate_total,
                "source_count": len(source_set),
                "sources_sample": source_set[:8],
                "claim_ids_sample": [str(member.get("claim_id") or "") for member in members[:8]],
                "representative_item": representative,
            }
        )

    clusters.sort(
        key=lambda cluster: (
            priority_order[str(cluster.get("priority") or "low")],
            0 if cluster.get("representative_item", {}).get("risk_flags") else 1,
            _source_rank(str(cluster.get("source_class") or "general")),
            -float(cluster.get("score") or 0),
            -int(cluster.get("member_count") or 0),
            str(cluster.get("representative_claim_id") or ""),
        )
    )
    selected_clusters = clusters[: max(0, limit)]
    items = [dict(cluster["representative_item"]) for cluster in selected_clusters]
    group_counts: dict[str, int] = {}
    for cluster in clusters:
        group = str(cluster.get("review_group") or "general")
        group_counts[group] = group_counts.get(group, 0) + 1
    return {
        "version": "hxy-claim-triage.v1",
        "total_claim_count": len(claims),
        "noise_claim_count": noise_count,
        "duplicate_claim_count": duplicate_count,
        "unique_reviewable_claim_count": len(by_normalised_claim),
        "cluster_count": len(clusters),
        "selected_count": len(items),
        "group_counts": group_counts,
        "clusters": [
            {key: value for key, value in cluster.items() if key != "representative_item"}
            for cluster in selected_clusters
        ],
        "items": items,
        "official_use_allowed": False,
        "requires_human_review": True,
        "authority_rule": "claim_triage_is_for_review_prioritization_not_approved_knowledge",
    }


def _question_for_review_item(item: dict[str, Any]) -> str:
    group = str(item.get("review_group") or "general")
    templates = {
        "brand_positioning": "荷小悦的品牌定位应该怎么说？",
        "product_system": "清泡调补养或产品体系应该怎么解释？",
        "store_model": "荷小悦门店模型的关键判断是什么？",
        "competitor_research": "这条竞品信息对荷小悦有什么参考价值？",
        "unit_economics": "这条单店模型或投资测算信息能否作为内部判断依据？",
        "employee_script": "员工应该如何按标准口径表达？",
        "risk_boundary": "这条表达有哪些合规风险，应该如何改写？",
    }
    return templates.get(group, "这条候选知识是否可以进入荷小悦标准口径？")


def build_answer_card_drafts(review_items: list[dict[str, Any]], limit: int = 10) -> dict[str, Any]:
    drafts: list[dict[str, Any]] = []
    for item in review_items:
        if item.get("priority") == "low":
            continue
        claim = str(item.get("claim") or "").strip()
        if not claim:
            continue
        risk_flags = list(item.get("risk_flags") or [])
        if risk_flags:
            answer = f"当前为草稿，不能直接发布。候选资料提示存在风险表达：{claim} 复核时需要改写为不承诺疗效、不夸大收益、只说明体验和适用边界。"
        else:
            answer = f"当前为草稿，不能直接发布。候选资料显示：{claim} 复核通过后可整理为荷小悦标准口径，并补充适用场景和引用来源。"
        drafts.append(
            {
                "version": "hxy-answer-card-draft.v1",
                "question_pattern": _question_for_review_item(item),
                "intent": item.get("domain") or "general",
                "audience": "internal",
                "answer": answer,
                "status": "draft",
                "official_use_allowed": False,
                "requires_human_review": True,
                "source_claim_ids": [item.get("claim_id")],
                "sources": item.get("sources") or [],
                "risk_flags": risk_flags,
                "review_group": item.get("review_group") or "general",
                "recommended_reviewer": item.get("recommended_reviewer") or "运营负责人",
            }
        )
        if len(drafts) >= limit:
            break
    return {
        "version": "hxy-answer-card-drafts.v1",
        "draft_count": len(drafts),
        "items": drafts,
    }


def build_compliance_review_pack(review_items: list[dict[str, Any]], limit: int = 20) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for item in review_items:
        review_group = str(item.get("review_group") or "")
        risk_flags = list(item.get("risk_flags") or [])
        sources = [str(source) for source in (item.get("sources") or [])]
        from_risk_source = any("09_风险与合规" in source or "风险与合规" in source for source in sources)
        if review_group != "risk_boundary" and not risk_flags and not from_risk_source:
            continue
        items.append(
            {
                "version": "hxy-compliance-review-item.v1",
                "claim_id": item.get("claim_id"),
                "claim": item.get("claim") or "",
                "risk_level": "P0",
                "risk_flags": risk_flags,
                "sources": sources,
                "recommended_reviewer": item.get("recommended_reviewer") or "运营/合规负责人",
                "review_question": "这条合规边界能否作为员工正式禁用表达或标准话术？",
                "required_decision": "approve_as_rule, needs_revision, or reject",
                "human_checklist": [
                    "核对原始来源和上下文，确认不是 AI 误读。",
                    "确认是否适用于门店员工、对外宣传或招商沟通。",
                    "确认改写后不包含医疗、保证疗效、夸大宣传或收益承诺。",
                    "不能自动进入 approved answer card；必须由负责人明确批准。",
                ],
                "official_use_allowed": False,
                "publish_allowed": False,
                "requires_human_review": True,
            }
        )
    items.sort(
        key=lambda item: (
            0 if item.get("risk_flags") else 1,
            0 if any("09_风险与合规" in source or "风险与合规" in source for source in item.get("sources", [])) else 1,
            str(item.get("claim_id") or ""),
        )
    )
    items = items[: max(0, limit)]
    return {
        "version": "hxy-compliance-review-pack.v1",
        "status": "needs_human_review" if items else "empty",
        "count": len(items),
        "items": items,
        "official_use_allowed": False,
        "publish_allowed": False,
        "requires_human_review": True,
        "authority_rule": "compliance_review_pack_is_not_approved_knowledge",
        "next_actions": [
            "由运营/合规负责人逐条选择 approve_as_rule、needs_revision 或 reject。",
            "批准后仍需进入正式答案卡发布流程，不能由编译器自动发布。",
        ],
    }


def build_knowledge_graph(*, extracts: list[dict[str, Any]], claims: list[dict[str, Any]]) -> dict[str, Any]:
    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, str]] = []

    def add_node(node_id: str, node_type: str, title: str) -> None:
        nodes[node_id] = {"id": node_id, "type": node_type, "title": title}

    for extract in extracts:
        extract_id = str(extract.get("extract_id") or "")
        domain = str(extract.get("domain") or "general")
        if extract_id:
            add_node(extract_id, "extract", str(extract.get("title") or extract_id))
            add_node(f"domain:{domain}", "domain", domain)
            edges.append({"type": "belongs_to", "from": extract_id, "to": f"domain:{domain}"})
            for source in extract.get("sources") or []:
                source_id = f"source:{source}"
                add_node(source_id, "source", str(source))
                edges.append({"type": "supported_by", "from": extract_id, "to": source_id})

    for claim in claims:
        claim_id = str(claim.get("claim_id") or "")
        domain = str(claim.get("domain") or "general")
        if claim_id:
            add_node(claim_id, "claim", str(claim.get("claim") or claim_id))
            add_node(f"domain:{domain}", "domain", domain)
            edges.append({"type": "belongs_to", "from": claim_id, "to": f"domain:{domain}"})
            for source in claim.get("sources") or []:
                source_id = f"source:{source}"
                add_node(source_id, "source", str(source))
                edges.append({"type": "supported_by", "from": claim_id, "to": source_id})
            for risk_flag in claim.get("risk_flags") or []:
                risk_id = f"risk:{risk_flag}"
                add_node(risk_id, "risk_rule", str(risk_flag))
                edges.append({"type": "blocked_by", "from": claim_id, "to": risk_id})

    return {
        "version": "hxy-knowledge-graph.v1",
        "nodes": list(nodes.values()),
        "edges": edges,
    }


def compile_directory(
    raw_dir: str | Path,
    wiki_dir: str | Path,
    *,
    source_paths: list[str | Path] | None = None,
) -> dict[str, Any]:
    raw_root = Path(raw_dir)
    wiki_root = Path(wiki_dir)
    wiki_root.mkdir(parents=True, exist_ok=True)

    extracts: list[dict[str, Any]] = []
    claims: list[dict[str, Any]] = []
    paths = [Path(path) for path in source_paths] if source_paths is not None else sorted(raw_root.rglob("*"))
    for path in sorted(paths, key=lambda item: item.as_posix()):
        if not path.is_file() or path.suffix.lower() not in {".md", ".txt"}:
            continue
        content = path.read_text(encoding="utf-8")
        extract = compile_material({"title": path.stem, "content": content, "source_path": path.as_posix()})
        extracts.append(extract)
        claims.extend(extract_candidate_claims(extract))

    graph = build_knowledge_graph(extracts=extracts, claims=claims)
    core_decision_topics = build_core_decision_topics(claims, limit=12)
    topic_draft_assets = build_topic_draft_assets(core_decision_topics, limit=12)
    topic_review_packets = build_topic_review_packets(topic_draft_assets, limit=12)
    topic_review_decision_stub = build_topic_review_decisions_stub(topic_review_packets, limit=50)
    topic_review_decision_sample = build_topic_review_decisions_sample(topic_review_decision_stub)
    claim_triage = build_claim_triage(claims, limit=200)
    review_queue = build_review_queue(claims, limit=20)
    answer_card_drafts = build_answer_card_drafts(review_queue["items"], limit=10)
    compliance_review_pack = build_compliance_review_pack(claim_triage["items"], limit=20)
    (wiki_root / "graph.json").write_text(json.dumps(graph, ensure_ascii=False, indent=2), encoding="utf-8")
    (wiki_root / "index.md").write_text(_render_index(extracts, claims), encoding="utf-8")
    (wiki_root / "core-decision-topics.json").write_text(
        json.dumps(core_decision_topics, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (wiki_root / "topic-draft-assets.json").write_text(
        json.dumps(topic_draft_assets, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (wiki_root / "topic-review-packets.json").write_text(
        json.dumps(topic_review_packets, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (wiki_root / "topic-review-decisions.stub.json").write_text(
        json.dumps(topic_review_decision_stub, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (wiki_root / "topic-review-decisions.sample.json").write_text(
        json.dumps(topic_review_decision_sample, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (wiki_root / "claim-triage.json").write_text(json.dumps(claim_triage, ensure_ascii=False, indent=2), encoding="utf-8")
    (wiki_root / "review-queue.json").write_text(json.dumps(review_queue, ensure_ascii=False, indent=2), encoding="utf-8")
    (wiki_root / "answer-card-drafts.json").write_text(json.dumps(answer_card_drafts, ensure_ascii=False, indent=2), encoding="utf-8")
    (wiki_root / "compliance-review-pack.json").write_text(json.dumps(compliance_review_pack, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "version": "hxy-knowledge-compiler-report.v1",
        "extract_count": len(extracts),
        "claim_count": len(claims),
        "approved_count": 0,
        "review_queue_count": len(review_queue["items"]),
        "core_decision_topic_count": core_decision_topics["core_topic_count"],
        "topic_draft_asset_count": topic_draft_assets["count"],
        "topic_review_packet_count": topic_review_packets["count"],
        "topic_review_decision_stub_count": topic_review_decision_stub["decision_count"],
        "human_review_object": "core_decision_topics",
        "reviewable_claim_count": review_queue["reviewable_claim_count"],
        "noise_claim_count": review_queue["noise_claim_count"],
        "duplicate_claim_count": claim_triage["duplicate_claim_count"],
        "claim_triage_cluster_count": claim_triage["cluster_count"],
        "claim_triage_selected_count": claim_triage["selected_count"],
        "claim_triage_reduction_count": max(0, int(claim_triage["unique_reviewable_claim_count"]) - int(claim_triage["cluster_count"])),
        "answer_card_draft_count": answer_card_drafts["draft_count"],
        "compliance_review_count": compliance_review_pack["count"],
        "graph_node_count": len(graph["nodes"]),
        "graph_edge_count": len(graph["edges"]),
        "wiki_dir": wiki_root.as_posix(),
        "artifacts": {
            "extracts": extracts,
            "claims": claims,
            "core_decision_topics": core_decision_topics,
            "topic_draft_assets": topic_draft_assets,
            "topic_review_packets": topic_review_packets,
            "topic_review_decision_stub": topic_review_decision_stub,
            "topic_review_decision_sample": topic_review_decision_sample,
            "claim_triage": claim_triage,
            "graph": graph,
            "review_queue": review_queue,
            "answer_card_drafts": answer_card_drafts,
            "compliance_review_pack": compliance_review_pack,
        },
    }


def _render_index(extracts: list[dict[str, Any]], claims: list[dict[str, Any]]) -> str:
    lines = [
        "# HXY Compiled Wiki Index",
        "",
        "Compiler output is not approved knowledge. It is reference or candidate material for review.",
        "",
        f"- Extracts: {len(extracts)}",
        f"- Candidate claims: {len(claims)}",
        "",
        "## Domains",
    ]
    domains = sorted({str(item.get("domain") or "general") for item in [*extracts, *claims]})
    for domain in domains:
        lines.append(f"- {domain}")
    lines.append("")
    return "\n".join(lines)


def build_harness_state(
    *,
    run_id: str,
    report: dict[str, Any],
    phase_paths: dict[str, str],
) -> dict[str, Any]:
    extract_count = int(report.get("extract_count") or 0)
    claim_count = int(report.get("claim_count") or 0)
    graph_node_count = int(report.get("graph_node_count") or 0)
    gates = {
        "source_gate": "passed" if extract_count > 0 else "failed",
        "compile_gate": "passed" if extract_count > 0 and claim_count > 0 and graph_node_count > 0 else "failed",
        "evidence_gate": "passed" if claim_count > 0 else "failed",
        "risk_gate": "passed",
        "review_gate": "pending",
    }
    blocked = any(value == "failed" for value in gates.values())
    next_actions: list[str] = []
    if extract_count == 0:
        next_actions.append("当前没有可编译资料，请把 .md/.txt 原始资料放入 knowledge/raw/inbox。")
    if claim_count == 0:
        next_actions.append("当前没有候选 claim，不能进入复核或答案卡生产。")
    next_actions.append("编译产物默认不是 approved，必须经过人工复核。")
    return {
        "version": "hxy-harness-state.v1",
        "run_id": run_id,
        "goal": "compile_hxy_knowledge",
        "current_phase": "final_report",
        "status": "blocked" if blocked else "passed",
        "gates": gates,
        "phase_paths": phase_paths,
        "next_actions": next_actions,
    }


def write_harness_run(
    *,
    run_id: str,
    runs_dir: str | Path,
    raw_dir: str | Path,
    report: dict[str, Any],
) -> dict[str, Any]:
    run_root = Path(runs_dir) / run_id
    phases_dir = run_root / "phases"
    phases_dir.mkdir(parents=True, exist_ok=True)
    artifacts = report.get("artifacts") if isinstance(report.get("artifacts"), dict) else {}
    extracts = artifacts.get("extracts") if isinstance(artifacts.get("extracts"), list) else []
    claims = artifacts.get("claims") if isinstance(artifacts.get("claims"), list) else []
    graph = artifacts.get("graph") if isinstance(artifacts.get("graph"), dict) else {"version": "hxy-knowledge-graph.v1", "nodes": [], "edges": []}

    manifest = {
        "version": "hxy-compiler-manifest.v1",
        "raw_dir": Path(raw_dir).as_posix(),
        "source_count": len(extracts),
        "sources": [source for extract in extracts for source in extract.get("sources", [])],
    }
    gates = {
        "version": "hxy-compiler-gates.v1",
        "extract_count": int(report.get("extract_count") or 0),
        "claim_count": int(report.get("claim_count") or 0),
        "graph_node_count": int(report.get("graph_node_count") or 0),
    }
    phase_payloads = {
        "01_manifest.json": manifest,
        "02_extracts.json": {"version": "hxy-compiler-extracts.v1", "items": extracts},
        "03_claims.json": {"version": "hxy-compiler-claims.v1", "items": claims},
        "04_graph.json": graph,
        "05_gates.json": gates,
        "06_review_queue.json": artifacts.get("review_queue") or {"version": "hxy-review-queue.v1", "items": []},
        "07_answer_card_drafts.json": artifacts.get("answer_card_drafts") or {"version": "hxy-answer-card-drafts.v1", "items": []},
        "08_compliance_review_pack.json": artifacts.get("compliance_review_pack") or {"version": "hxy-compliance-review-pack.v1", "items": []},
        "09_claim_triage.json": artifacts.get("claim_triage") or {"version": "hxy-claim-triage.v1", "items": []},
        "10_core_decision_topics.json": artifacts.get("core_decision_topics") or {"version": "hxy-core-decision-topics.v1", "items": []},
        "11_topic_draft_assets.json": artifacts.get("topic_draft_assets") or {"version": "hxy-topic-draft-assets.v1", "items": []},
        "12_topic_review_packets.json": artifacts.get("topic_review_packets") or {"version": "hxy-topic-review-packets.v1", "items": []},
        "13_topic_review_decisions_stub.json": artifacts.get("topic_review_decision_stub")
        or {"version": "hxy-topic-review-decisions-stub.v1", "items": []},
        "14_topic_review_decisions_sample.json": artifacts.get("topic_review_decision_sample")
        or {"version": "hxy-topic-review-decisions-sample.v1", "items": []},
    }
    phase_paths: dict[str, str] = {}
    for file_name, payload in phase_payloads.items():
        path = phases_dir / file_name
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        phase_paths[file_name.removesuffix(".json")] = path.as_posix()

    state = build_harness_state(run_id=run_id, report=report, phase_paths=phase_paths)
    (run_root / "state.json").write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    final_report = {
        "version": "hxy-harness-final-report.v1",
        "run_id": run_id,
        "state": state,
        "compiler_report": {key: value for key, value in report.items() if key != "artifacts"},
    }
    (run_root / "final-report.json").write_text(json.dumps(final_report, ensure_ascii=False, indent=2), encoding="utf-8")
    return final_report
