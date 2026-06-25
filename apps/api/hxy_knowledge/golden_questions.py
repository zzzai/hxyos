from __future__ import annotations

from copy import deepcopy
from typing import Any


GOLDEN_QUESTION_CARDS: list[dict[str, Any]] = [
    {
        "question_pattern": "荷小悦是什么？",
        "aliases": ["荷小悦是什么", "荷小悦到底是什么", "一句话介绍荷小悦"],
        "intent": "brand_positioning",
        "audience": "general",
        "answer": "荷小悦是面向社区生活场景的草本泡脚与调理服务品牌，用清泡、调泡、补泡、养泡把一次泡脚做成可感知、可复购、可培训的标准化健康放松体验。",
        "role_versions": {
            "founder": "荷小悦不是普通足疗店，而是以草本泡脚为入口的社区健康放松服务模型。",
            "store_staff": "可以这样说：荷小悦是草本泡脚店，我们会先了解顾客状态，再推荐适合的泡脚方和服务。",
            "franchisee": "荷小悦用标准化泡脚项目、员工话术和社区小店模型，做高频、轻养生、可复购的门店生意。",
            "customer": "荷小悦是一个可以放松、泡草本脚汤，并按状态选择不同泡脚方的门店。",
        },
        "forbidden_terms": ["治疗", "治愈", "包好", "医学诊断", "药到病除"],
        "applicable_scenarios": ["品牌统一口径", "门店员工培训", "招商话术", "用户端宣传"],
        "review_status": "approved_v1",
        "version": "v1.0",
        "next_actions": ["按不同角色改写为一句话介绍", "用于门店员工背诵和招商开场"],
    },
    {
        "question_pattern": "核爆点定位是什么？",
        "aliases": ["核爆点是什么", "核心定位是什么"],
        "intent": "brand_positioning",
        "audience": "founder",
        "answer": "荷小悦的核爆点定位是：把普通泡脚从低决策、低复购的放松项目，升级为顾客能听懂、员工能推荐、门店能持续复购的草本调理入口。核心不是项目更多，而是用清泡调补养建立可解释、可升级、可复制的产品心智。",
        "role_versions": {
            "founder": "核爆点在于把泡脚做成有理由升级、有标准话术、有复购路径的社区健康服务入口。",
            "store_staff": "员工只要讲清顾客为什么适合清泡、调泡、补泡或养泡，就抓住了荷小悦的核心。",
            "franchisee": "加盟视角的核爆点是：清泡引流，调补养提升客单和复购，员工有标准推荐路径。",
            "customer": "顾客感受到的核爆点是：不是随便泡脚，而是按自己最近状态选更适合的草本泡脚。",
        },
        "forbidden_terms": ["颠覆行业", "绝对第一", "治疗", "保证复购", "稳赚"],
        "applicable_scenarios": ["创始人内部决策", "品牌定位", "招商话术", "员工培训"],
        "review_status": "approved_v1",
        "version": "v1.0",
        "next_actions": ["沉淀为品牌定位卡", "拆成招商版、员工版、用户版"],
    },
    {
        "question_pattern": "清泡调补养怎么讲？",
        "aliases": ["清泡调补养产品体系怎么讲", "清泡调补养是什么", "泡脚方怎么讲"],
        "intent": "product_system",
        "audience": "product",
        "answer": "清泡调补养是荷小悦的泡脚产品分层：清泡负责基础放松和清爽体验，调泡根据近期状态做针对性调理表达，补泡强调深度滋养和恢复感，养泡面向长期保养和复购。对外讲时要说体验和状态改善，不说医疗治疗。",
        "role_versions": {
            "founder": "清泡调补养是产品分层，也是客单升级和复购路径。",
            "store_staff": "顾客问区别时这样说：清泡是基础放松，调泡按最近状态调一调，补泡更适合疲劳恢复，养泡适合长期保养。",
            "franchisee": "清泡做引流，调补养做升级和复购，关键是员工能按顾客状态推荐。",
            "customer": "可以理解为：清泡像基础清洁，调补养是按你最近睡眠、疲劳、手脚凉等状态做更适合的泡脚体验。",
        },
        "forbidden_terms": ["治疗失眠", "排毒治病", "药效保证", "祛病", "根治"],
        "applicable_scenarios": ["产品培训", "门店员工培训", "用户端宣传", "招商话术"],
        "review_status": "approved_v1",
        "version": "v1.0",
        "next_actions": ["制作对比表", "拆成顾客问答话术", "标注禁用医疗表达"],
    },
    {
        "question_pattern": "门店员工怎么推荐泡脚方？",
        "aliases": ["员工怎么推荐泡脚方", "门店怎么推荐清泡调补养", "泡脚方推荐话术"],
        "intent": "operations",
        "audience": "operations",
        "answer": "门店员工推荐泡脚方要先问状态，再给建议，不要一上来推贵项目。标准动作是：问最近睡眠、疲劳、手脚凉、压力或久坐情况；判断顾客当前主要需求；用一句话解释对应泡脚方；最后提醒体验感受和注意事项。",
        "role_versions": {
            "founder": "推荐机制要从卖项目变成问状态、给理由、做升级。",
            "store_staff": "话术：您最近睡眠怎么样、累不累、手脚凉不凉？如果只是放松选清泡，如果最近状态明显，可以试试更对应的调泡/补泡/养泡。",
            "franchisee": "员工推荐标准化后，门店才能稳定提升客单和复购，而不是靠个人销售能力。",
            "customer": "员工会先问你的状态，再推荐更适合的泡脚方，不是盲目推项目。",
        },
        "forbidden_terms": ["必须买贵的", "不做没效果", "治疗", "保证当天见效", "医生建议"],
        "applicable_scenarios": ["门店员工培训", "培训 SOP", "店长验收", "用户端沟通"],
        "review_status": "approved_v1",
        "version": "v1.0",
        "next_actions": ["生成员工背诵卡", "设置店长验收问题", "追踪升级项目占比"],
    },
    {
        "question_pattern": "招商怎么讲单店模型？",
        "aliases": ["加盟怎么讲单店模型", "招商单店模型怎么说", "加盟商怎么理解门店模型"],
        "intent": "franchise",
        "audience": "franchise",
        "answer": "招商讲单店模型时，要讲清门店靠什么来客、靠什么提升客单、靠什么复购、靠什么控制风险。荷小悦的表达应是：社区小店降低到店门槛，清泡做引流，调补养和组合服务提升客单，标准话术和 SOP 降低人员依赖。具体投资、利润和回本周期必须基于真实门店数据和假设复核后再讲。",
        "role_versions": {
            "founder": "招商不能先讲宏大规模，要先证明单店来客、客单、复购和成本结构成立。",
            "store_staff": "员工不用讲投资回报，只要把产品和服务做好，让顾客愿意复购。",
            "franchisee": "加盟商要看四件事：客流怎么来、客单怎么升、顾客怎么复购、风险怎么控。",
            "customer": "用户端不讲单店模型，只讲门店服务和体验。",
        },
        "forbidden_terms": ["稳赚", "保证回本", "零风险", "躺赚", "一定盈利"],
        "applicable_scenarios": ["招商话术", "加盟沟通", "创始人内部决策", "投资模型复核"],
        "review_status": "approved_v1",
        "version": "v1.0",
        "next_actions": ["补齐真实门店参数", "把收益和风险分开讲", "形成招商 FAQ"],
    },
    {
        "question_pattern": "哪些话不能说？",
        "aliases": ["禁用表达有哪些", "哪些话术不能说", "门店不能承诺什么"],
        "intent": "operations",
        "audience": "operations",
        "answer": "荷小悦不能说医疗治疗、绝对效果、收益保证和夸大承诺。门店和招商都要避免“治疗、治愈、保证、稳赚、一定回本、药到病除、排毒治病”等表达。正确说法应改为体验、放松、帮助改善感受、需要持续观察、具体以门店标准和复核口径为准。",
        "role_versions": {
            "founder": "禁用表达是经营风险边界，必须进入品牌、招商、门店培训统一口径。",
            "store_staff": "不要说治疗、治愈、保证有效。可以说帮助放松、改善体验、适合你最近这种状态。",
            "franchisee": "招商不能承诺稳赚和保证回本，只能讲模型逻辑、假设条件和风险边界。",
            "customer": "对顾客只讲体验和建议，不讲医疗结论。",
        },
        "forbidden_terms": ["治疗", "治愈", "保证", "稳赚", "一定回本", "药到病除", "排毒治病"],
        "applicable_scenarios": ["门店员工培训", "招商话术", "用户端宣传", "合规复核"],
        "review_status": "approved_v1",
        "version": "v1.0",
        "next_actions": ["同步到员工禁用话术卡", "用于答案质检", "外部发布前复核"],
    },
]


def golden_questions() -> list[dict[str, Any]]:
    return [
        {
            "question": card["question_pattern"],
            "intent": card["intent"],
            "aliases": list(card["aliases"]),
            "applicable_scenarios": list(card["applicable_scenarios"]),
        }
        for card in GOLDEN_QUESTION_CARDS
    ]


def authority_cards() -> list[dict[str, Any]]:
    cards = deepcopy(GOLDEN_QUESTION_CARDS)
    for card in cards:
        card["status"] = "approved"
        card.setdefault("reasoning", ["内置黄金问题权威答案卡 v1，用于稳定团队核心口径。"])
        card.setdefault("evidence", [{"title": "HXY authority card v1", "domain": "approved_answer_card", "strength": "high"}])
        card.setdefault("corrections", [])
    return cards
