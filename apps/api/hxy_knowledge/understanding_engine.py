from __future__ import annotations

import re
from hashlib import sha256
from typing import Any


_DOMAIN_KEYWORDS = {
    "product": ["清泡调补养", "泡脚方", "草本泡脚", "产品体系", "套餐", "sku", "spu", "项目"],
    "brand": ["品牌", "定位", "核爆点", "心智", "口号", "表达"],
    "store_model": ["门店模型", "小店模型", "单店模型", "选址", "坪效", "社区店"],
    "operations": ["培训", "sop", "服务流程", "店长", "员工", "运营", "执行"],
    "franchise": ["招商", "加盟", "加盟商", "投资", "回本"],
    "finance": ["营收", "利润", "成本", "财务", "roi", "分账"],
    "competitor": ["竞品", "对手", "参考品牌", "奈晚", "谷小推", "郑远元"],
}

_ROLE_KEYWORDS = {
    "store_staff": ["员工", "技师", "服务人员", "门店员工"],
    "store_manager": ["店长", "门店负责人"],
    "franchisee": ["加盟商", "投资人"],
    "headquarters": ["总部", "运营", "产品经理", "管理层"],
    "customer": ["顾客", "客户", "用户端", "消费者"],
    "founder": ["创始人", "战略", "决策"],
}

_RISK_TERMS = ["治疗", "治愈", "保证", "一定", "稳赚", "排毒", "疗效", "药到病除"]


def _contains_any(text: str, terms: list[str]) -> bool:
    lowered = text.lower()
    return any(term.lower() in lowered for term in terms)


def _dedupe(items: list[str]) -> list[str]:
    result: list[str] = []
    for item in items:
        if item and item not in result:
            result.append(item)
    return result


def _classify_domains(text: str) -> list[str]:
    domains = [domain for domain, terms in _DOMAIN_KEYWORDS.items() if _contains_any(text, terms)]
    return domains or ["general"]


def _classify_roles(text: str, fallback_role: str) -> list[str]:
    roles = [role for role, terms in _ROLE_KEYWORDS.items() if _contains_any(text, terms)]
    if fallback_role and fallback_role not in roles:
        roles.append(fallback_role)
    return roles or ["general"]


def _extract_numbers(text: str) -> list[str]:
    return _dedupe(re.findall(r"(?:¥|￥)?\d+(?:\.\d+)?(?:元|万|%|折|家|人|分钟|小时|天|月|年)?", text or ""))


def _extract_entities(text: str) -> list[str]:
    entities: list[str] = []
    for terms in _DOMAIN_KEYWORDS.values():
        for term in terms:
            if term in text:
                entities.append(term)
    for term in ["荷小悦", "清泡", "调泡", "补泡", "养泡", "草本", "顾客", "门店", "员工", "加盟商"]:
        if term in text:
            entities.append(term)
    return _dedupe(entities)


def recognize_intent(text: str, attachments: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    normalized = " ".join((text or "").split())
    attachments = attachments or []
    has_attachment = bool(attachments)
    attachment_kinds = _dedupe([str(item.get("type") or item.get("mime_type") or item.get("file_name") or "file") for item in attachments])

    if _contains_any(normalized, ["上传", "入库", "保存", "记忆", "沉淀"]) or has_attachment:
        action = "ingest"
    elif _contains_any(normalized, ["不准确", "错了", "纠偏", "修正", "完善"]):
        action = "correction"
    elif _contains_any(normalized, ["生成", "制作", "输出", "整理", "改写"]):
        action = "execute"
    else:
        action = "question"

    if has_attachment and normalized:
        action = "analyze_multimodal"

    if _contains_any(normalized, ["培训", "员工", "店长", "话术", "sop"]):
        need = "training"
    elif _contains_any(normalized, ["招商", "加盟", "投资", "回本"]):
        need = "franchise"
    elif _contains_any(normalized, ["战略", "定位", "核爆点", "决策"]):
        need = "decision_support"
    elif action in {"ingest", "analyze_multimodal"}:
        need = "memory_ingestion"
    elif action == "correction":
        need = "correction_review"
    else:
        need = "quick_answer"

    if action in {"ingest", "analyze_multimodal", "correction"} or need in {"training", "franchise", "decision_support"}:
        mode = "deep_understanding"
    else:
        mode = "quick_answer"

    urgency = "high" if _contains_any(normalized, ["紧急", "马上", "今天", "现在", "客诉", "风险"]) else "normal"

    return {
        "action": action,
        "need": need,
        "mode": mode,
        "urgency": urgency,
        "input_types": ["text"] + attachment_kinds if normalized else attachment_kinds or ["text"],
        "domains": _classify_domains(normalized),
    }


def priority_matrix_for(conflict_or_need: str, *, domain: str, scenario: str) -> dict[str, Any]:
    text = f"{conflict_or_need} {domain} {scenario}"
    impact = 5 if _contains_any(text, ["培训", "招商", "定位", "产品", "清泡调补养", "门店"]) else 3
    urgency = 5 if _contains_any(text, ["紧急", "今天", "客诉", "风险", "招商话术", "门店员工培训"]) else 3
    controllability = 5 if _contains_any(text, ["话术", "培训", "sop", "答案卡", "产品"]) else 3
    strategic_relevance = 5 if _contains_any(text, ["清泡调补养", "定位", "门店模型", "招商", "经营大脑"]) else 3
    priority = round((impact * urgency * controllability * strategic_relevance) / 625, 3)
    return {
        "impact": impact,
        "urgency": urgency,
        "controllability": controllability,
        "strategic_relevance": strategic_relevance,
        "priority": priority,
        "reason": "按影响度、紧急度、可控度、战略相关度计算，优先处理高影响且可通过话术/SOP/答案卡改变的问题。",
    }


def executability_gate_for(action: str, *, scenario: str, role: str) -> dict[str, Any]:
    training_like = scenario == "门店员工培训" or role in {"store_staff", "store_manager"}
    return {
        "resources": {
            "passed": True,
            "detail": "第一步只需要标准话术、对比表和店长验收，不依赖额外系统投入。" if training_like else "需要确认资料、负责人和验收标准。",
        },
        "capability": {
            "passed": True,
            "detail": "表达必须压缩为员工能记住的短句。" if training_like else "需要按角色控制信息密度。",
        },
        "permission": {
            "passed": action not in {"change_price", "policy_commitment"},
            "detail": "不涉及门店擅自改价或承诺政策；价格、加盟、医疗表达需总部复核。",
        },
        "risk": {
            "passed": True,
            "detail": "避免治疗、治愈、保证、稳赚等过度承诺。",
        },
        "acceptance": {
            "passed": True,
            "detail": "可用员工背诵通过率、升级项目占比、顾客问题命中率或复核通过率验收。",
        },
    }


def _main_conflict_for(text: str, domains: list[str], scenario: str) -> str:
    if "清泡调补养" in text or "泡脚方" in text:
        if scenario == "门店员工培训" or _contains_any(text, ["员工", "培训", "话术"]):
            return "核心矛盾是员工能否把清泡调补养讲成顾客听得懂、愿意升级的标准话术。"
        return "核心矛盾是产品体系要从项目清单变成顾客可理解、门店可执行的价值表达。"
    if "定位" in text or "核爆点" in text:
        return "核心矛盾是品牌表达必须在内部战略、招商沟通和用户感知之间统一口径。"
    if "招商" in text or "加盟" in text:
        return "核心矛盾是讲清确定性和收益逻辑，同时保留风险边界。"
    if "门店模型" in text or "小店模型" in text:
        return "核心矛盾是单店模型参数必须能被门店真实资源和总部复制能力支撑。"
    if "general" not in domains:
        return f"核心矛盾是把{domains[0]}资料转成可执行、可复核、可沉淀的经营结果。"
    return "核心矛盾是问题场景不够明确，需要先判断用户要快速答案、深度分析还是执行动作。"


def _role_outputs(text: str, scenario: str, roles: list[str]) -> dict[str, str]:
    base = "先讲结论，再讲怎么做，避免内部术语和过度承诺。"
    if "清泡调补养" in text or "泡脚方" in text:
        return {
            "headquarters": "把清泡调补养定义为产品体系，统一价格、适用人群、禁用表达和培训验收口径。",
            "store_manager": "本周抓员工话术演练和升级项目占比，先让每个人能讲清清泡、调泡、补泡、养泡的区别。",
            "store_staff": "顾客说随便泡泡时，先问睡眠、手脚凉、疲劳或压力，再用一句话推荐对应泡脚方。",
            "franchisee": "清泡负责引流，调补养负责提升客单和复购，但必须配套员工培训和标准 SOP。",
            "customer": "清泡是基础放松，调补养是按近期状态做更有针对性的草本泡脚体验。",
        }
    return {role: base for role in roles or ["general"]}


def understand_text(text: str, scenario: str = "创始人内部决策", role: str = "founder") -> dict[str, Any]:
    normalized = " ".join((text or "").split())
    intent = recognize_intent(normalized)
    domains = intent["domains"]
    roles = _classify_roles(normalized, role)
    entities = _extract_entities(normalized)
    numbers = _extract_numbers(normalized)
    main_conflict = _main_conflict_for(normalized, domains, scenario)
    priority = priority_matrix_for(main_conflict, domain=domains[0], scenario=scenario)
    risky_terms = [term for term in _RISK_TERMS if term in normalized]
    certainty = "medium" if intent["mode"] == "deep_understanding" else "low"

    depth = {
        "D1_perception": {
            "keywords": entities[:12],
            "numbers": numbers,
            "input_type": "text",
            "language": "zh",
        },
        "D2_classification": {
            "domains": domains,
            "roles": roles,
            "scenario": scenario,
            "intent": intent,
        },
        "D3_decomposition": {
            "facts": [normalized] if normalized else [],
            "objects": roles,
            "attributes": entities,
            "constraints": ["价格、政策、医疗功效和加盟收益需复核"],
            "conflict_elements": [main_conflict],
        },
        "D4_causal_inference": {
            "causes": ["资料如果只停留在项目清单，门店执行会依赖员工个人理解。"],
            "business_impact": ["影响顾客理解、项目升级、培训一致性和答案卡沉淀。"],
            "execution_constraints": ["员工表达要短，店长要能验收，总部要给标准口径。"],
        },
        "D5_judgment": {
            "main_conflict": main_conflict,
            "key_leverage": "把知识转成标准话术、场景问答、禁用表达和可验收动作。",
            "priority_matrix": priority,
        },
    }

    applications = {
        "A1_role_output": _role_outputs(normalized, scenario, roles),
        "A2_risk_boundary": {
            "forbidden_terms": risky_terms or ["治疗", "治愈", "保证", "稳赚", "绝对"],
            "uncertainty": certainty,
            "needs_review": ["价格", "政策", "医疗功效", "加盟收益"],
        },
        "A3_action_plan": {
            "immediate": ["生成标准话术卡", "列出顾客常见问题", "设置店长验收动作"],
            "short_term": ["追踪员工话术通过率和升级项目占比"],
            "owner": "运营负责人" if scenario == "门店员工培训" else "业务负责人",
        },
        "A4_conflict_correction": {
            "conflicts": [main_conflict],
            "review_trigger": "出现价格、功效、加盟收益、新旧资料不一致时生成复核任务。",
        },
        "A5_memory_evolution": {
            "suggested_memory": "answer_card_candidate" if intent["action"] == "question" else "understanding_record",
            "signals": ["调用频率", "有用率", "不准确率", "复核次数", "知识盲区"],
            "versioning": "形成答案卡后记录版本、适用场景和变更原因。",
        },
    }

    confidence = {
        "score": 0.72 if domains != ["general"] else 0.48,
        "level": "medium" if domains != ["general"] else "low",
        "basis": "基于荷小悦业务关键词、场景和角色的确定性解析；外部模型接入后可增强细节理解。",
    }

    return {
        "understanding_id": sha256(f"{normalized}|{scenario}|{role}".encode("utf-8")).hexdigest()[:16],
        "intent": intent,
        "depth": depth,
        "applications": applications,
        "executability_gate": executability_gate_for(intent["action"], scenario=scenario, role=role),
        "confidence": confidence,
    }
