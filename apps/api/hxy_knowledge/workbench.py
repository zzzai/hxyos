from __future__ import annotations

from typing import Any


def _contains_any(text: str, terms: list[str]) -> bool:
    return any(term in text for term in terms)


def _base_result(
    *,
    input_text: str,
    scenario: str,
    role: str,
    attachments: list[dict[str, Any]],
    input_type: str,
    primary_workflow: str,
    team_value: list[str],
    answer_shape: list[str],
    inspector_shape: list[str],
    memory_action: str,
    next_actions: list[str],
) -> dict[str, Any]:
    return {
        "version": "hxy-team-operating-brain-workbench.v1",
        "input": input_text,
        "scenario": scenario,
        "role": role,
        "attachments": attachments,
        "input_type": input_type,
        "primary_workflow": primary_workflow,
        "team_value": team_value,
        "answer_shape": answer_shape,
        "inspector_shape": inspector_shape,
        "memory_action": memory_action,
        "next_actions": next_actions,
    }


def classify_workbench_intake(
    input_text: str,
    *,
    scenario: str = "经营问答",
    role: str = "team",
    attachments: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    text = " ".join((input_text or "").split())
    attached = attachments or []
    scenario_text = scenario or "经营问答"
    role_text = role or "team"
    combined = f"{text} {scenario_text} {role_text}"

    if attached or _contains_any(combined, ["上传", "文件", "图片", "截图", "资料", "入库", "识别分类", "自动识别", "记忆"]):
        return _base_result(
            input_text=text,
            scenario=scenario_text,
            role=role_text,
            attachments=attached,
            input_type="knowledge_intake",
            primary_workflow="ingest",
            team_value=["资料变记忆", "统一口径", "纠偏进化"],
            answer_shape=["识别到资料", "自动分类", "质量评分", "是否可问答", "下一步动作"],
            inspector_shape=["当前理解", "分类结果", "质量评分", "缺失资料", "冲突检查", "复核建议"],
            memory_action="进入资料记忆流程：自动分类、抽取关键结论、生成复核任务，确认后沉淀为组织记忆。",
            next_actions=[
                "自动分类到品牌、产品、门店、招商、培训或 SOP 业务域",
                "抽取关键结论、价格、话术、流程和限制条件",
                "检查是否和已有权威答案冲突",
                "低置信度内容进入复核，稳定内容进入资料记忆",
            ],
        )

    if _contains_any(combined, ["不准确", "纠偏", "说错", "错了", "需完善", "完善", "修正", "冲突"]):
        return _base_result(
            input_text=text,
            scenario=scenario_text,
            role=role_text,
            attachments=attached,
            input_type="correction",
            primary_workflow="correct",
            team_value=["纠偏进化", "统一口径"],
            answer_shape=["错误点", "正确口径", "影响范围", "下一步复核"],
            inspector_shape=["当前理解", "自动分类结果", "主要矛盾", "风险边界", "纠偏任务", "记忆动作"],
            memory_action="生成纠偏任务；复核后更新答案卡、训练卡或组织记忆版本。",
            next_actions=[
                "定位错误结论或缺失字段",
                "补充权威资料或人工确认口径",
                "判断是否影响已有答案卡和培训话术",
                "复核通过后更新组织记忆",
            ],
        )

    is_explicit_task = _contains_any(combined, ["生成", "安排", "执行", "动作", "验收", "跟进", "复盘"])
    is_practice = _contains_any(combined, ["练习", "练话术", "追问", "打分", "演练", "考试"])
    if is_explicit_task and not is_practice:
        return _base_result(
            input_text=text,
            scenario=scenario_text,
            role=role_text,
            attachments=attached,
            input_type="operating_task",
            primary_workflow="execute",
            team_value=["经营动作交付", "训练团队"],
            answer_shape=["经营动作交付", "负责人", "时间节点", "验收标准", "风险提醒"],
            inspector_shape=["当前理解", "自动分类结果", "主要矛盾", "缺失资料", "执行约束", "记忆动作"],
            memory_action="作为经营任务记录；执行反馈可反哺 SOP、培训卡和答案卡。",
            next_actions=[
                "拆成负责人、时间、动作和验收标准",
                "检查门店是否具备资源、能力和权限",
                "执行后收集反馈，更新 SOP 或培训材料",
            ],
        )

    training_terms = ["培训", "员工", "店长", "门店员工", "练习", "练话术", "追问", "打分", "演练"]
    if _contains_any(combined, training_terms):
        return _base_result(
            input_text=text,
            scenario=scenario_text,
            role=role_text,
            attachments=attached,
            input_type="training",
            primary_workflow="train",
            team_value=["训练团队", "统一口径", "纠偏进化"],
            answer_shape=["标准话术", "场景演练", "追问问题", "评分标准", "纠偏建议"],
            inspector_shape=["当前理解", "自动分类结果", "主要矛盾", "能力缺口", "风险边界", "记忆动作"],
            memory_action="沉淀为训练卡；高频错误进入门店培训复盘和话术版本管理。",
            next_actions=[
                "生成员工可背诵的话术版本",
                "用顾客追问测试员工是否真正理解",
                "按准确性、合规性、转化力和表达清晰度评分",
                "把高频错误沉淀为训练纠偏点",
            ],
        )

    if _contains_any(combined, ["定位", "战略", "商业模式", "加盟", "单店模型", "回本", "取舍", "决策"]):
        return _base_result(
            input_text=text,
            scenario=scenario_text,
            role=role_text,
            attachments=attached,
            input_type="decision_support",
            primary_workflow="decide",
            team_value=["辅助判断", "统一口径"],
            answer_shape=["核心结论", "主要矛盾", "缺失数据", "下一步验证", "是否可进入下一步"],
            inspector_shape=["当前理解", "自动分类结果", "主要矛盾", "缺失资料", "思考镜头", "风险边界", "记忆动作"],
            memory_action="作为经营判断记录；复核后可沉淀为权威答案或决策日志。",
            next_actions=[
                "区分事实、假设和待验证判断",
                "识别主要矛盾和关键杠杆",
                "列出下一步必须补齐的数据",
                "复核稳定后进入决策日志或答案卡",
            ],
        )

    return _base_result(
        input_text=text,
        scenario=scenario_text,
        role=role_text,
        attachments=attached,
        input_type="question",
        primary_workflow="ask",
        team_value=["统一口径", "辅助判断"],
        answer_shape=["结论", "怎么做", "适用对象", "风险提醒", "下一步动作"],
        inspector_shape=["当前理解", "自动分类结果", "主要矛盾", "缺失资料", "风险边界", "记忆动作"],
        memory_action="若问题高频且答案稳定，建议沉淀为权威答案卡。",
        next_actions=[
            "先给团队可直接使用的答案",
            "按角色改写为招商、门店、用户端或内部决策版本",
            "发现不确定或冲突时生成复核任务",
            "高频稳定问题沉淀为权威答案卡",
        ],
    )
