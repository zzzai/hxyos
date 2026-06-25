from __future__ import annotations

from copy import deepcopy
from typing import Any


_ZERO_TO_ONE_SEQUENCE = ["jtbd_positioning", "niche_focus", "unit_economics"]

_LENSES: list[dict[str, Any]] = [
    {
        "key": "jtbd_positioning",
        "name": "用户雇佣理论定位",
        "source": "Clayton Christensen / Jobs To Be Done",
        "stage": "zero_to_one",
        "trigger_terms": ["定位", "顾客", "为什么来", "为什么买", "替谁", "解决什么", "用户", "客群", "需求"],
        "use_for": ["定位", "用户需求", "替代方案", "竞品真实原因"],
        "structure": [
            "顾客不是购买品类，而是雇佣产品完成任务",
            "先找真实任务，再看替代方案",
            "定位必须落到谁、什么场景、解决什么问题",
        ],
        "base_questions": [
            "顾客上一次来，原本是想解决什么问题？",
            "如果没有荷小悦，他会用什么替代：按摩店、在家泡脚、早点睡觉，还是别的方式？",
            "他开除竞品或替代方案，是因为什么没有被满足？",
            "能否用一句话说清：荷小悦替谁，在什么场景下，解决什么高频痛点？",
        ],
        "anti_patterns": [
            "不要用环境好、服务好、产品好当定位。",
            "不要把泡脚养生这种品类词误当定位。",
        ],
    },
    {
        "key": "niche_focus",
        "name": "垄断利基 + 做减法",
        "source": "Peter Thiel / Zero to One + Steve Jobs / Focus",
        "stage": "zero_to_one",
        "trigger_terms": ["战略", "扩张", "全国", "城市", "人群", "太多", "项目", "选择困难", "聚焦", "小池塘"],
        "use_for": ["初期战略", "资源聚焦", "产品取舍", "小市场打穿"],
        "structure": [
            "初期不要追求覆盖更广，而要在窄切口上做到第一",
            "砍掉会分散验证的客群、区域、项目和叙事",
            "先证明一个小池塘能被打穿，再谈复制",
        ],
        "base_questions": [
            "能不能先在一个城市的一类人群里做到第一，而不是服务所有想泡脚的人？",
            "如果只能押一个核心客群、一个社区类型、一个主力项目，分别选什么？",
            "现在做的事情里，哪些看起来重要，但会分散 0→1 验证？",
            "这个小池塘的边界是什么：城市、社区、人群、价格带、服务场景？",
        ],
        "anti_patterns": [
            "不要在单点没打穿前讲全国布局。",
            "不要用产品丰富掩盖核心场景没有跑通。",
        ],
    },
    {
        "key": "unit_economics",
        "name": "精益验证 + 单元经济",
        "source": "Lean Startup + Unit Economics",
        "stage": "zero_to_one",
        "trigger_terms": ["商业模式", "回本", "加盟", "单店", "客单", "复购", "毛利", "CAC", "LTV", "获客", "利润", "成本", "药材"],
        "use_for": ["商业模式验证", "单店模型", "回本判断", "扩张前置校验"],
        "structure": [
            "先做最小可验证单元，而不是先设计宏大体系",
            "把一个顾客身上的账算清楚",
            "LTV 必须大于 CAC，单点不盈利不能放大",
        ],
        "base_questions": [
            "一个顾客平均贡献多少毛利和净利润？",
            "拉一个顾客进店的 CAC 是多少？来自美团、抖音、私域、自然流量分别是多少？",
            "LTV 是否大于 CAC？差距有多大？",
            "复购率、来店频次、客单价、毛利率分别是多少？",
            "现在谈加盟扩张，是基于真实单店数据，还是基于模型假设？",
        ],
        "anti_patterns": [
            "不要在单店/单客经济没跑通前设计复杂加盟体系。",
            "不要把目标回本周期当成已验证事实。",
        ],
    },
]


def _contains_any(text: str, terms: list[str]) -> bool:
    lowered = text.lower()
    return any(term.lower() in lowered for term in terms)


def _score_lens(text: str, lens: dict[str, Any]) -> int:
    score = 0
    for term in lens["trigger_terms"]:
        if term in text:
            score += 3
    if lens["key"] == "jtbd_positioning" and _contains_any(text, ["定位", "顾客", "客群", "需求", "为什么来"]):
        score += 5
    if lens["key"] == "niche_focus" and _contains_any(text, ["战略", "扩张", "项目", "人群", "城市", "太多"]):
        score += 5
    if lens["key"] == "unit_economics" and _contains_any(text, ["回本", "加盟", "单店", "客单", "复购", "成本", "药材"]):
        score += 5
    return score


def _business_questions_for(text: str, lens_key: str) -> list[str]:
    questions: list[str] = []
    if lens_key == "jtbd_positioning":
        if _contains_any(text, ["泡脚", "身体", "疲劳", "顾客", "定位"]):
            questions.extend(
                [
                    "荷小悦到底替顾客解决的是放松、身体疲劳、调理、社交，还是离家近的即时恢复？",
                    "顾客为什么非来荷小悦不可，而不是去普通按摩店、在家泡脚或早点睡觉？",
                ]
            )
    if lens_key == "niche_focus":
        if _contains_any(text, ["扩张", "城市", "人群", "战略", "项目"]):
            questions.extend(
                [
                    "荷小悦第一个要打穿的小池塘是什么：安阳某类社区、25-40 岁双职工家庭，还是另一个更窄切口？",
                    "如果只能做一个城市、一个社区类型、一个主力项目，分别应该选什么？",
                ]
            )
    if lens_key == "unit_economics":
        if _contains_any(text, ["药材", "成本"]):
            questions.append("药材成本可以拆成哪些底层变量：品种、用量、采购价、损耗、供应链层级？")
        if _contains_any(text, ["回本", "加盟", "单店"]):
            questions.extend(
                [
                    "回本慢的底层瓶颈是客流、客单价、复购、毛利，还是固定成本？",
                    "一个顾客的 LTV、CAC、复购频次和单次毛利分别是多少？",
                ]
            )
    return questions


def _selected_lenses_for_stage(text: str, stage: str, max_lenses: int) -> list[dict[str, Any]]:
    if stage == "zero_to_one":
        return [lens for key in _ZERO_TO_ONE_SEQUENCE for lens in _LENSES if lens["key"] == key][:max_lenses]
    scored = [(_score_lens(text, lens), lens) for lens in _LENSES]
    selected = [lens for score, lens in sorted(scored, key=lambda item: item[0], reverse=True) if score > 0]
    return selected[:max_lenses] or [next(lens for lens in _LENSES if lens["key"] == "jtbd_positioning")]


def apply_thinking_lenses(text: str, max_lenses: int = 3, stage: str = "zero_to_one") -> dict[str, Any]:
    normalized = " ".join((text or "").split())
    selected = _selected_lenses_for_stage(normalized, stage, max_lenses)

    result_lenses: list[dict[str, Any]] = []
    guiding_questions: list[str] = []
    anti_patterns: list[str] = []
    for lens in selected:
        result_lenses.append(
            {
                "key": lens["key"],
                "name": lens["name"],
                "source": lens["source"],
                "stage": lens["stage"],
                "use_for": lens["use_for"],
                "structure": lens["structure"],
            }
        )
        guiding_questions.extend(_business_questions_for(normalized, lens["key"]))
        guiding_questions.extend(lens["base_questions"])
        anti_patterns.extend(lens["anti_patterns"])

    deduped_questions: list[str] = []
    for question in guiding_questions:
        if question not in deduped_questions:
            deduped_questions.append(question)
    deduped_anti_patterns: list[str] = []
    for warning in anti_patterns:
        if warning not in deduped_anti_patterns:
            deduped_anti_patterns.append(warning)

    return {
        "input": normalized,
        "stage": stage,
        "sequence": list(_ZERO_TO_ONE_SEQUENCE) if stage == "zero_to_one" else [item["key"] for item in result_lenses],
        "lenses": result_lenses,
        "guiding_questions": deduped_questions[:14],
        "反模式": deduped_anti_patterns[:8],
        "阶段升级信号": "当单元经济跑通、单点可复制后，再升级到扩张期镜头组：飞轮、组织管理、供应链和标准化复制。",
        "principle": "专家方法只作为提问脚手架，答案必须来自荷小悦真实资料、经营数据和复核结论。",
    }


def thinking_lenses_catalog(stage: str = "zero_to_one") -> dict[str, Any]:
    items = [item for item in deepcopy(_LENSES) if item.get("stage") == stage]
    return {"stage": stage, "sequence": list(_ZERO_TO_ONE_SEQUENCE), "items": items, "count": len(items)}
