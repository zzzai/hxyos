from __future__ import annotations

from typing import Any


_DIMENSION_TO_MODULE = {
    "accuracy": "basic_knowledge",
    "discovery": "customer_discovery",
    "compliance": "compliance_risk",
    "conversion": "business_conversion",
    "clarity": "objection_handling",
}

_MODULE_LABELS = {
    "basic_knowledge": "基础认知",
    "customer_discovery": "顾客状态探询",
    "product_recommendation": "产品推荐",
    "objection_handling": "异议处理",
    "compliance_risk": "合规与风险",
    "business_conversion": "经营转化",
}


def training_question_bank() -> list[dict[str, Any]]:
    return [
        {
            "question_id": "newbie-basic-qing-tiao-bu-yang",
            "module": "basic_knowledge",
            "module_label": _MODULE_LABELS["basic_knowledge"],
            "level": "newbie",
            "title": "清泡调补养怎么讲",
            "customer_question": "顾客问：清泡调补养有什么区别？",
            "capability_targets": ["产品准确性", "表达清晰度"],
            "risk_boundary": "不能讲成只是价格差，不能承诺治疗效果。",
        },
        {
            "question_id": "newbie-basic-product-value",
            "module": "basic_knowledge",
            "module_label": _MODULE_LABELS["basic_knowledge"],
            "level": "newbie",
            "title": "清泡不是低端项目",
            "customer_question": "顾客问：清泡是不是最普通、最便宜的？",
            "capability_targets": ["产品准确性", "推荐转化"],
            "risk_boundary": "不能贬低清泡，也不能强行推高价。",
        },
        {
            "question_id": "newbie-discovery-status",
            "module": "customer_discovery",
            "module_label": _MODULE_LABELS["customer_discovery"],
            "level": "newbie",
            "title": "先问顾客状态",
            "customer_question": "顾客说：我就随便泡泡，你帮我选一个。",
            "capability_targets": ["需求探询", "表达清晰度"],
            "risk_boundary": "先问状态再推荐，不要直接按价格推。",
        },
        {
            "question_id": "newbie-compliance-insomnia",
            "module": "compliance_risk",
            "module_label": _MODULE_LABELS["compliance_risk"],
            "level": "newbie",
            "title": "失眠问题合规表达",
            "customer_question": "顾客问：这个能不能治疗失眠？",
            "capability_targets": ["合规边界", "表达清晰度"],
            "risk_boundary": "不能说治疗、治愈、保证有效，只能说放松和状态建议。",
        },
        {
            "question_id": "standard-recommend-fatigue",
            "module": "product_recommendation",
            "module_label": _MODULE_LABELS["product_recommendation"],
            "level": "standard",
            "title": "疲劳顾客推荐",
            "customer_question": "顾客说：最近很累，睡醒也不轻松，但不想被推销。",
            "capability_targets": ["需求探询", "产品推荐", "推荐转化"],
            "risk_boundary": "不能制造焦虑，推荐必须基于顾客状态。",
        },
        {
            "question_id": "standard-recommend-cold",
            "module": "product_recommendation",
            "module_label": _MODULE_LABELS["product_recommendation"],
            "level": "standard",
            "title": "手脚凉顾客推荐",
            "customer_question": "顾客说：我经常手脚凉，泡哪个更合适？",
            "capability_targets": ["产品推荐", "合规边界"],
            "risk_boundary": "不能承诺改善疾病，只能表达体验和状态调理建议。",
        },
        {
            "question_id": "standard-objection-expensive",
            "module": "objection_handling",
            "module_label": _MODULE_LABELS["objection_handling"],
            "level": "standard",
            "title": "太贵了怎么办",
            "customer_question": "顾客说：这个太贵了，我在家也能泡。",
            "capability_targets": ["异议处理", "推荐转化"],
            "risk_boundary": "不能贬低顾客选择，不能硬推。",
        },
        {
            "question_id": "standard-objection-no-effect",
            "module": "objection_handling",
            "module_label": _MODULE_LABELS["objection_handling"],
            "level": "standard",
            "title": "顾客担心没效果",
            "customer_question": "顾客问：如果泡完没感觉怎么办？",
            "capability_targets": ["异议处理", "合规边界"],
            "risk_boundary": "不能保证效果，要讲体验预期和复盘方式。",
        },
        {
            "question_id": "advanced-conversion-upgrade",
            "module": "business_conversion",
            "module_label": _MODULE_LABELS["business_conversion"],
            "level": "advanced",
            "title": "清泡顾客升级引导",
            "customer_question": "老顾客每次只选清泡，店长希望你自然引导他体验调泡。",
            "capability_targets": ["经营转化", "产品推荐", "需求探询"],
            "risk_boundary": "不能为了客单价强行升级，要基于真实状态。",
        },
        {
            "question_id": "advanced-conversion-revisit",
            "module": "business_conversion",
            "module_label": _MODULE_LABELS["business_conversion"],
            "level": "advanced",
            "title": "复访提醒",
            "customer_question": "服务结束后，顾客说下次再看，你怎么做复访提醒？",
            "capability_targets": ["经营转化", "表达清晰度"],
            "risk_boundary": "不能制造压力，要给出自然下次到店理由。",
        },
        {
            "question_id": "advanced-compliance-special-crowd",
            "module": "compliance_risk",
            "module_label": _MODULE_LABELS["compliance_risk"],
            "level": "advanced",
            "title": "特殊人群提醒",
            "customer_question": "顾客说自己怀孕了/有基础病，还能不能泡？",
            "capability_targets": ["合规边界", "风险识别"],
            "risk_boundary": "必须提示先咨询专业医生或遵循门店禁忌，不做医疗判断。",
        },
        {
            "question_id": "advanced-complaint-repair",
            "module": "objection_handling",
            "module_label": _MODULE_LABELS["objection_handling"],
            "level": "advanced",
            "title": "体验不满修复",
            "customer_question": "顾客说：上次泡完没什么感觉，这次不想做升级项目。",
            "capability_targets": ["异议处理", "顾客状态探询", "经营转化"],
            "risk_boundary": "不能否定顾客体验，要先复盘上次感受。",
        },
    ]


def filter_training_questions(level: str | None = None, module: str | None = None) -> list[dict[str, Any]]:
    items = training_question_bank()
    if level:
        items = [item for item in items if item["level"] == level]
    if module:
        items = [item for item in items if item["module"] == module]
    return items


def _question_by_id() -> dict[str, dict[str, Any]]:
    return {item["question_id"]: item for item in training_question_bank()}


def _normalize_next_questions(next_questions: list[dict[str, Any]], level: str) -> list[dict[str, Any]]:
    bank = _question_by_id()
    normalized: list[dict[str, Any]] = []
    for item in next_questions:
        question_id = str(item.get("question_id") or "").strip()
        if question_id and question_id in bank:
            normalized.append({**bank[question_id], **item})
        elif item.get("title") and item.get("customer_question"):
            normalized.append(item)
    if normalized:
        return normalized
    return filter_training_questions(level=level)[:3]


def build_recommended_training_plan(
    capability_levels: list[dict[str, Any]],
    *,
    employee_id: str = "",
    store_id: str = "",
    recent_sessions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    valid_levels = {"newbie", "standard", "advanced"}
    sessions = recent_sessions or []
    latest_session = sessions[0] if sessions else {}
    if latest_session and bool(latest_session.get("needs_retrain")):
        plan = latest_session.get("adaptive_retrain_plan_json") or latest_session.get("adaptive_retrain_plan") or {}
        recommended_level = str(plan.get("target_level") or "newbie").strip()
        if recommended_level not in valid_levels:
            recommended_level = "newbie"
        items = _normalize_next_questions(plan.get("next_questions") or [], recommended_level)
        return {
            "version": "hxy-training-recommended-plan.v1",
            "employee_id": employee_id or str(latest_session.get("employee_id") or "employee-local"),
            "store_id": store_id or str(latest_session.get("store_id") or "pilot-store"),
            "recommended_level": recommended_level,
            "source": "adaptive_retrain",
            "reason": "上次训练未达标，先完成系统安排的短板复训。",
            "count": len(items),
            "items": items,
            "capability_snapshot": capability_levels[0] if capability_levels else {},
            "session_signal": {
                "needs_retrain": True,
                "score": latest_session.get("score"),
                "training_item": latest_session.get("training_item"),
            },
        }
    capability = capability_levels[0] if capability_levels else {}
    current_level = str(capability.get("current_level") or "").strip()
    if current_level in valid_levels:
        recommended_level = current_level
        source = "capability_level"
        reason = f"员工能力档案显示当前为{recommended_level}，系统安排同等级场景继续巩固。"
    else:
        recommended_level = "newbie"
        source = "default_new_employee"
        reason = "暂无员工能力档案，先打基础：产品认知、顾客探询和合规表达。"
    items = filter_training_questions(level=recommended_level)
    return {
        "version": "hxy-training-recommended-plan.v1",
        "employee_id": employee_id or str(capability.get("employee_id") or "employee-local"),
        "store_id": store_id or str(capability.get("store_id") or "pilot-store"),
        "recommended_level": recommended_level,
        "source": source,
        "reason": reason,
        "count": len(items),
        "items": items,
        "capability_snapshot": capability,
    }


def _score_by_key(training_result: dict[str, Any]) -> dict[str, int]:
    scores: dict[str, int] = {}
    for item in training_result.get("dimensions") or []:
        key = str(item.get("key") or "")
        if not key:
            continue
        try:
            scores[key] = int(item.get("score") or 0)
        except (TypeError, ValueError):
            scores[key] = 0
    return scores


def _level_for_average(average_score: float, needs_retrain: bool) -> str:
    if needs_retrain or average_score < 75:
        return "newbie"
    if average_score < 90:
        return "standard"
    return "advanced"


def build_training_capability_profile(training_result: dict[str, Any], *, employee_id: str = "") -> dict[str, Any]:
    scores = _score_by_key(training_result)
    average = sum(scores.values()) / len(scores) if scores else float(training_result.get("score") or 0)
    needs_retrain = bool(training_result.get("needs_retrain")) or average < 75
    weak_dimensions = [key for key, score in scores.items() if score < 75]
    weak_modules = []
    for key in weak_dimensions:
        module = _DIMENSION_TO_MODULE.get(key)
        if module and module not in weak_modules:
            weak_modules.append(module)
    if not weak_modules and needs_retrain:
        weak_modules.append("basic_knowledge")
    strong_dimensions = [key for key, score in scores.items() if score >= 90]
    return {
        "version": "hxy-training-capability-profile.v1",
        "employee_id": employee_id or "employee-local",
        "level": _level_for_average(average, needs_retrain),
        "average_score": round(average),
        "weak_dimensions": weak_dimensions,
        "weak_modules": weak_modules,
        "strong_dimensions": strong_dimensions,
        "summary": " · ".join(_MODULE_LABELS.get(module, module) for module in weak_modules) or "基础训练通过，可进入更高阶场景。",
    }


def build_adaptive_retrain_plan(training_result: dict[str, Any], *, employee_id: str = "") -> dict[str, Any]:
    profile = build_training_capability_profile(training_result, employee_id=employee_id)
    weak_modules = profile["weak_modules"] or ["product_recommendation"]
    level = profile["level"]
    questions: list[dict[str, Any]] = []
    for module in weak_modules:
        for item in training_question_bank():
            if item["module"] == module and (item["level"] == level or level == "newbie"):
                questions.append(item)
    if len(questions) < 3:
        for item in training_question_bank():
            if item not in questions and item["level"] in {level, "newbie", "standard"}:
                questions.append(item)
            if len(questions) >= 3:
                break
    metric_links = []
    if "business_conversion" in weak_modules or "product_recommendation" in weak_modules:
        metric_links.append({"metric": "客单价", "direction": "negative", "reason": "推荐和升级表达不足会拖低客单价。"})
        metric_links.append({"metric": "调补养占比", "direction": "negative", "reason": "员工讲不清升级价值时，顾客容易只选清泡。"})
    if "customer_discovery" in weak_modules:
        metric_links.append({"metric": "复购率", "direction": "negative", "reason": "没有记录顾客状态，就缺少下次复访理由。"})
    if "compliance_risk" in weak_modules:
        metric_links.append({"metric": "投诉风险", "direction": "positive", "reason": "高风险承诺会增加投诉和合规风险。"})
    if not metric_links:
        metric_links.append({"metric": "训练通过率", "direction": "positive", "reason": "可进入更高阶成交和复购训练。"})
    return {
        "version": "hxy-adaptive-retrain-plan.v1",
        "employee_id": employee_id or "employee-local",
        "target_level": level,
        "focus_modules": weak_modules,
        "next_questions": questions[:3],
        "manager_acceptance": {
            "method": "店长验收：员工连续 2 次同模块训练达到 75 分以上，并现场复述标准话术。",
            "pass_score": 75,
            "required_pass_count": 2,
        },
        "operating_metric_links": metric_links,
    }
