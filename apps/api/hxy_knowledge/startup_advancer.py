from __future__ import annotations

from typing import Any


_ACTION_CONFIG: dict[str, dict[str, Any]] = {
    "record": {
        "workflow": "evidence_capture",
        "title": "证据记录草稿",
        "focus": "核爆点定位证据",
        "artifact": "定位证据卡",
        "lead": "先把原话和事实存下来，不急着改结论。",
    },
    "revise": {
        "workflow": "conclusion_revision",
        "title": "结论更新草稿",
        "focus": "核爆点定位修订",
        "artifact": "定位结论卡",
        "lead": "只允许被新证据推动的结论变化进入版本。",
    },
    "next": {
        "workflow": "next_validation_step",
        "title": "下一步验证草稿",
        "focus": "核爆点定位验证",
        "artifact": "定位验证任务卡",
        "lead": "下一步必须产出可证伪证据，而不是增加待办。",
    },
    "card": {
        "workflow": "positioning_card_draft",
        "title": "定位卡草稿",
        "focus": "核爆点定位沉淀",
        "artifact": "定位卡",
        "lead": "只有结论、证据、禁用表达都清楚时，才沉淀为团队口径。",
    },
}


def _summary(text: str) -> str:
    normalized = " ".join((text or "").split())
    if not normalized:
        return "暂无新增证据，先按当前假设生成最小验证动作。"
    return normalized[:140]


def _confidence(evidence_input: str, action: str) -> float:
    if not evidence_input.strip():
        return 0.54 if action in {"next", "card"} else 0.5
    signal_terms = ["访谈", "原话", "复述", "愿意", "选择", "替代", "付费", "比例", "人数"]
    signal_count = sum(1 for term in signal_terms if term in evidence_input)
    return min(0.9, 0.6 + signal_count * 0.04)


def build_startup_advance(
    *,
    action: str,
    evidence_input: str = "",
    current_conclusion: str = "",
    main_question: str = "核爆点定位是否成立？",
) -> dict[str, Any]:
    action_key = (action or "").strip()
    if action_key not in _ACTION_CONFIG:
        raise ValueError("unsupported startup action")

    config = _ACTION_CONFIG[action_key]
    conclusion = current_conclusion.strip() or "荷小悦是面向社区高疲劳人群的轻恢复项目。"
    input_summary = _summary(evidence_input)
    has_evidence = bool(evidence_input.strip())

    draft_bullets = [
        f"当前结论：{conclusion}",
        f"新增材料：{input_summary}",
        config["lead"],
    ]
    if action_key == "revise":
        draft_bullets.append("如果新增材料不能改变目标人群、用户任务或表达方式，结论暂不升级版本。")
    elif action_key == "next":
        draft_bullets.append("下一轮只验证一个问题：用户是否能听懂并复述荷小悦解决的具体任务。")
    elif action_key == "card":
        draft_bullets.append("定位卡必须同时包含一句话定位、适用场景、禁用表达和证据状态。")
    else:
        draft_bullets.append("把证据先按用户任务、替代选择、付费理由、表达复述四类归档。")

    evidence_requirements = [
        "至少 8-12 个目标用户访谈或真实观察记录。",
        "每条证据必须保留用户原话、场景和替代选择。",
        "清泡调补养表达要做外部复述测试，低于 70% 复述率不得固化。",
    ]
    if not has_evidence:
        evidence_requirements.insert(0, "当前缺少新增证据，本次输出只能作为验证任务，不能作为定稿。")

    next_actions = [
        "补齐用户真实痛点：最近一次想恢复状态时，他实际选择了什么。",
        "测试一句话定位：让外部用户听完后复述，记录原话而不是主观感觉。",
        "同步产品口径：用同一批用户测试清泡、调泡、补泡、养泡是否听得懂。",
    ]
    if action_key == "card":
        next_actions.append("由负责人复核后再进入品牌答案卡，未复核前标记为 draft。")
    elif action_key == "revise":
        next_actions.append("只更新被证据直接支持的字段，其余字段继续保持待验证。")

    quality_gates = [
        "是否把事实、假设、判断分开。",
        "是否避免疗效承诺、绝对效果和无法验证的表述。",
        "是否能让员工用 30 秒讲清，不依赖创始人解释。",
    ]

    return {
        "version": "hxy-startup-advance.v1",
        "stage": "pre_open_zero_to_one",
        "action": action_key,
        "workflow": config["workflow"],
        "main_question": main_question.strip() or "核爆点定位是否成立？",
        "focus": config["focus"],
        "input_summary": input_summary,
        "confidence": _confidence(evidence_input, action_key),
        "draft": {
            "title": config["title"],
            "bullets": draft_bullets,
        },
        "evidence_requirements": evidence_requirements,
        "next_actions": next_actions,
        "quality_gates": quality_gates,
        "memory_action": {
            "target": "knowledge/okf",
            "artifact": config["artifact"],
            "status": "draft" if action_key == "card" else "needs_evidence",
            "reviewer": "founder_or_brand_owner",
        },
        "boundary": "开店前只推进定位、产品口径和品牌资料沉淀；不把后置经营数据能力放进当前主入口。",
    }
