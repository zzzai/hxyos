from __future__ import annotations

from copy import deepcopy
from typing import Any


_MODULES: list[dict[str, Any]] = [
    {
        "key": "brand_strategy",
        "name": "品牌战略库",
        "purpose": "固化荷小悦是谁、替谁解决什么问题、为什么不同、核爆点定位和品牌主张。",
        "source_types": ["项目介绍", "品牌方案", "定位研讨", "BP"],
        "asset_cards": ["品牌定位", "一句话定位", "核心卖点", "目标客群", "品牌主张", "差异化解释"],
        "priority": "P0",
    },
    {
        "key": "product_service",
        "name": "产品服务库",
        "purpose": "沉淀清泡调补养、草本泡脚、按摩项目、服务流程、价格逻辑和禁忌表达。",
        "source_types": ["泡脚菜单", "服务项目设计", "门店模型构思"],
        "asset_cards": ["清泡调补养解释", "项目推荐逻辑", "功效替代表达", "禁忌提醒", "价格口径"],
        "priority": "P0",
    },
    {
        "key": "store_model",
        "name": "门店模型库",
        "purpose": "解释社区小店、面积、房间、人力、投资预算、单店模型和开店验证条件。",
        "source_types": ["小店模型", "单店研讨", "门店具象化构思"],
        "asset_cards": ["社区店理由", "门店面积模型", "人员配置", "投资结构", "复制前置条件"],
        "priority": "P0",
    },
    {
        "key": "operations_sop",
        "name": "运营 SOP 库",
        "purpose": "把接待、服务、收银、回访、投诉、卫生和店长每日动作变成可执行 SOP。",
        "source_types": ["服务流程", "经营构思", "试点 SOP"],
        "asset_cards": ["接待 SOP", "服务 SOP", "回访 SOP", "投诉处理", "店长每日动作"],
        "priority": "P1",
    },
    {
        "key": "customer_insight",
        "name": "客户洞察库",
        "purpose": "在未开店阶段先沉淀目标客户画像、痛点、到店动机、消费心理和复购假设。",
        "source_types": ["目标人群分析", "服务设计", "定位材料"],
        "asset_cards": ["核心客户画像", "客户痛点", "到店动机", "复购假设", "流失假设"],
        "priority": "P1",
    },
    {
        "key": "technician_training",
        "name": "技师训练库",
        "purpose": "将品牌口径、项目推荐、服务礼仪、禁用表达和考核题库转成训练素材。",
        "source_types": ["培训材料", "服务流程", "话术材料"],
        "asset_cards": ["新人训练", "标准话术", "顾客追问", "禁用表达", "店长验收"],
        "priority": "P0",
    },
    {
        "key": "competitor_intelligence",
        "name": "竞品情报库",
        "purpose": "沉淀奈晚、谷小推、郑远元、LANN、足康树等竞品的定位、价格、模型和可借鉴点。",
        "source_types": ["竞品研究", "参考品牌", "公开调研"],
        "asset_cards": ["竞品定位", "价格结构", "门店模型", "优势劣势", "避坑清单"],
        "priority": "P1",
    },
    {
        "key": "franchise_financing",
        "name": "招商融资库",
        "purpose": "把合伙人、投资人、房东和核心员工需要听懂的商业逻辑转成分角色话术。",
        "source_types": ["商业计划书", "融资 BP", "股东合作协议", "招商材料"],
        "asset_cards": ["招商开场", "单店模型", "投资亮点", "反对意见", "风险边界"],
        "priority": "P0",
    },
]


_GOLDEN_QUESTIONS: list[dict[str, str]] = [
    {"question": "荷小悦是什么？", "module": "brand_strategy", "scenario": "统一口径"},
    {"question": "核爆点定位是什么？", "module": "brand_strategy", "scenario": "创始人内部决策"},
    {"question": "荷小悦解决什么问题？", "module": "brand_strategy", "scenario": "品牌定位"},
    {"question": "目标客户是谁？", "module": "customer_insight", "scenario": "品牌定位"},
    {"question": "为什么选择社区小店？", "module": "store_model", "scenario": "创始人内部决策"},
    {"question": "和普通足疗店有什么不同？", "module": "brand_strategy", "scenario": "用户宣传"},
    {"question": "和传统养生馆有什么不同？", "module": "brand_strategy", "scenario": "用户宣传"},
    {"question": "为什么做泡脚加按摩？", "module": "product_service", "scenario": "产品体系"},
    {"question": "清泡调补养怎么讲？", "module": "product_service", "scenario": "门店员工培训"},
    {"question": "清泡适合什么顾客？", "module": "product_service", "scenario": "门店员工培训"},
    {"question": "调泡适合什么顾客？", "module": "product_service", "scenario": "门店员工培训"},
    {"question": "补泡适合什么顾客？", "module": "product_service", "scenario": "门店员工培训"},
    {"question": "养泡适合什么顾客？", "module": "product_service", "scenario": "门店员工培训"},
    {"question": "门店员工怎么推荐泡脚方？", "module": "technician_training", "scenario": "门店员工培训"},
    {"question": "顾客说太贵怎么回答？", "module": "technician_training", "scenario": "门店员工培训"},
    {"question": "顾客说随便泡泡怎么回答？", "module": "technician_training", "scenario": "门店员工培训"},
    {"question": "顾客问能不能治疗失眠怎么回答？", "module": "technician_training", "scenario": "合规复核"},
    {"question": "哪些话不能说？", "module": "technician_training", "scenario": "合规复核"},
    {"question": "品牌对外一句话怎么讲？", "module": "brand_strategy", "scenario": "用户宣传"},
    {"question": "招商怎么讲单店模型？", "module": "franchise_financing", "scenario": "招商话术"},
    {"question": "合伙人最容易质疑什么？", "module": "franchise_financing", "scenario": "招商话术"},
    {"question": "投资人问壁垒怎么回答？", "module": "franchise_financing", "scenario": "融资沟通"},
    {"question": "单店模型开第二家前要验证什么？", "module": "store_model", "scenario": "创始人内部决策"},
    {"question": "100 平方和 150 平方店怎么取舍？", "module": "store_model", "scenario": "创始人内部决策"},
    {"question": "奈晚有什么值得学习？", "module": "competitor_intelligence", "scenario": "竞品分析"},
    {"question": "郑远元有什么值得学习和避开？", "module": "competitor_intelligence", "scenario": "竞品分析"},
    {"question": "谷小推和荷小悦有什么差异？", "module": "competitor_intelligence", "scenario": "竞品分析"},
    {"question": "门店接待第一句话怎么说？", "module": "operations_sop", "scenario": "门店员工培训"},
    {"question": "首次客户服务流程怎么做？", "module": "operations_sop", "scenario": "运营 SOP"},
    {"question": "客户体验后怎么做不推销式推荐？", "module": "operations_sop", "scenario": "门店员工培训"},
    {"question": "差评或投诉怎么处理？", "module": "operations_sop", "scenario": "运营 SOP"},
    {"question": "品牌标准手册应该包含什么？", "module": "brand_strategy", "scenario": "品牌资产"},
]


_DELIVERABLES: list[dict[str, Any]] = [
    {
        "name": "荷小悦品牌标准手册",
        "modules": ["brand_strategy", "customer_insight"],
        "outputs": ["一句话定位", "核心卖点", "品牌主张", "角色化表达", "禁用表达"],
    },
    {
        "name": "荷小悦产品服务手册",
        "modules": ["product_service"],
        "outputs": ["清泡调补养", "服务项目", "推荐逻辑", "禁忌提醒", "价格口径"],
    },
    {
        "name": "荷小悦门店模型说明",
        "modules": ["store_model"],
        "outputs": ["社区小店理由", "面积模型", "人员配置", "投资结构", "验证条件"],
    },
    {
        "name": "荷小悦运营 SOP 手册",
        "modules": ["operations_sop"],
        "outputs": ["接待 SOP", "服务 SOP", "回访 SOP", "投诉处理", "店长每日动作"],
    },
    {
        "name": "荷小悦技师训练手册",
        "modules": ["technician_training"],
        "outputs": ["训练题库", "标准话术", "追问题", "评分标准", "店长验收"],
    },
    {
        "name": "荷小悦竞品情报库",
        "modules": ["competitor_intelligence"],
        "outputs": ["竞品定位", "价格结构", "门店模型", "借鉴点", "避坑清单"],
    },
    {
        "name": "荷小悦招商融资知识库",
        "modules": ["franchise_financing", "store_model"],
        "outputs": ["招商开场", "单店模型", "投资亮点", "反对意见", "风险边界"],
    },
]


_MODULE_CARD_META: dict[str, dict[str, Any]] = {
    "brand_strategy": {
        "intent": "brand_positioning",
        "audience": "founder",
        "forbidden_terms": ["医疗结论", "绝对效果", "行业第一", "无法验证的排名"],
        "next_actions": ["沉淀到品牌标准手册", "拆成内部版、门店版、对外版"],
    },
    "product_service": {
        "intent": "product_system",
        "audience": "product",
        "forbidden_terms": ["医疗结论", "绝对效果", "当天必见效", "药品暗示"],
        "next_actions": ["沉淀到产品服务手册", "转成员工推荐话术和禁忌提醒"],
    },
    "store_model": {
        "intent": "store_model",
        "audience": "founder",
        "forbidden_terms": ["收益承诺", "无风险", "固定周期承诺", "规模幻觉"],
        "next_actions": ["沉淀到门店模型说明", "补齐试点验证指标"],
    },
    "operations_sop": {
        "intent": "operations",
        "audience": "operations",
        "forbidden_terms": ["强推销", "甩锅", "情绪化解释", "口头承诺超出标准"],
        "next_actions": ["沉淀到运营 SOP", "转成店长验收清单"],
    },
    "customer_insight": {
        "intent": "brand_positioning",
        "audience": "founder",
        "forbidden_terms": ["泛人群", "人人都适合", "医疗判断", "夸大痛点"],
        "next_actions": ["沉淀到客户画像库", "开店后用真实反馈校准"],
    },
    "technician_training": {
        "intent": "operations",
        "audience": "store_staff",
        "forbidden_terms": ["医疗结论", "绝对效果", "强推贵项目", "恐吓式销售"],
        "next_actions": ["沉淀到技师训练手册", "进入员工训练题库和店长验收"],
    },
    "competitor_intelligence": {
        "intent": "brand_positioning",
        "audience": "founder",
        "forbidden_terms": ["贬低竞品", "未核实数据", "照抄竞品", "情绪化比较"],
        "next_actions": ["沉淀到竞品情报库", "提炼可借鉴点和避坑清单"],
    },
    "franchise_financing": {
        "intent": "franchise",
        "audience": "franchisee",
        "forbidden_terms": ["收益承诺", "无风险", "固定周期承诺", "夸大规模"],
        "next_actions": ["沉淀到招商融资知识库", "拆成合伙人版和投资人版"],
    },
}


_QUESTION_ANSWERS: dict[str, str] = {
    "荷小悦是什么？": "荷小悦是面向社区生活场景的草本泡脚与轻调理服务品牌。它用清泡、调泡、补泡、养泡把一次泡脚做成顾客能听懂、员工能推荐、门店能复购的标准化体验。",
    "核爆点定位是什么？": "核爆点是把普通泡脚升级为可解释、可训练、可复购的草本调理入口。清泡负责低门槛体验，调补养负责按状态升级，员工话术和 SOP 负责把体验稳定交付出来。",
    "荷小悦解决什么问题？": "荷小悦解决的是社区人群高频疲劳、压力和身体恢复需求缺少轻决策去处的问题。顾客不需要复杂判断，就能在附近获得放松、状态关怀和持续保养建议。",
    "目标客户是谁？": "初期核心客户应聚焦在社区周边有疲劳恢复、睡眠压力、久坐肩颈和轻养生需求的人群，优先吃透一类高频复购客群，再逐步扩展到更多人群。",
    "为什么选择社区小店？": "社区小店的价值是降低到店决策、提高复访便利性，并让门店更容易围绕熟客经营。初期不追求大而全，而是先验证一套可复制的小店服务模型。",
    "和普通足疗店有什么不同？": "普通足疗店多围绕手法和时长销售，荷小悦更强调草本泡脚入口、状态询问、清泡调补养分层和标准化服务话术。差异不是项目更多，而是顾客知道为什么选这一项。",
    "和传统养生馆有什么不同？": "传统养生馆容易显得重、慢、难判断，荷小悦要做轻决策、近距离、可复购的社区轻养生体验。表达要简单，让顾客知道今天为什么来、适合做什么、下次怎么延续。",
    "为什么做泡脚加按摩？": "泡脚负责降低决策门槛和建立身体放松感，按摩负责增强服务感知和客单结构。两者组合后，门店既有低门槛入口，也有可升级的体验路径。",
    "清泡调补养怎么讲？": "清泡是基础放松，调泡按近期状态做针对性调理表达，补泡强调疲劳后的恢复感，养泡面向长期保养。门店讲法要围绕体验和状态，不做医疗结论。",
    "清泡适合什么顾客？": "清泡适合第一次到店、只想放松、对草本泡脚还不熟悉，或暂时没有明确状态诉求的顾客。它是低门槛体验入口，也是员工建立信任的第一步。",
    "调泡适合什么顾客？": "调泡适合能说出近期状态变化的顾客，例如睡眠压力、久坐疲劳、手脚偏凉或精神紧绷。员工要先问状态，再说明为什么这一方更贴近当下需求。",
    "补泡适合什么顾客？": "补泡适合明显疲劳、恢复感需求更强、希望服务更有滋养感的顾客。讲法要强调放松和恢复体验，不把它包装成医疗方案。",
    "养泡适合什么顾客？": "养泡适合愿意长期保养、重视复访节奏、希望把泡脚变成生活习惯的顾客。它的重点是持续性和稳定体验，而不是一次性夸张效果。",
    "门店员工怎么推荐泡脚方？": "员工推荐泡脚方要先问状态，再给理由，不要一上来推高价项目。标准动作是问睡眠、疲劳、手脚温度、压力或久坐情况，再用一句话解释对应泡脚方。",
    "顾客说太贵怎么回答？": "不要反驳顾客，也不要急着降价。先承认顾客在比较价值，再解释差异来自草本方、服务时长、状态匹配和体验完整度，最后给一个低门槛试用选择。",
    "顾客说随便泡泡怎么回答？": "先顺着顾客的轻决策心理，再做一次简单状态询问。可以说先从清泡开始，如果最近确实累、睡不好或手脚偏凉，再按状态升级到更适合的方。",
    "顾客问能不能治疗失眠怎么回答？": "正确回答是：我们不能做医疗判断，也不替代就医。可以根据你最近睡眠压力和放松需求，推荐更适合的泡脚体验，重点是帮助放松和改善体验感受。",
    "哪些话不能说？": "不能说医疗结论、绝对效果、收益承诺和无法验证的行业地位。统一改成体验表达、状态建议、模型假设和复核边界，外部发布前必须由负责人确认。",
    "品牌对外一句话怎么讲？": "荷小悦是一家社区草本泡脚与轻调理服务品牌，帮助顾客在离家近、决策轻、体验舒服的场景里放松身体、恢复状态。",
    "招商怎么讲单店模型？": "招商讲单店模型要讲四件事：客流怎么来，客单怎么升，顾客怎么复访，风险怎么控。具体投资、利润和回收周期必须基于试点数据和清晰假设复核后再讲。",
    "合伙人最容易质疑什么？": "合伙人最容易质疑定位是否清晰、顾客是否复访、员工是否能标准化、单店账是否算得清、总部是否能持续支持。回答必须把假设、证据和风险边界分开。",
    "投资人问壁垒怎么回答？": "壁垒不在大模型本身，而在荷小悦持续沉淀的品牌口径、服务 SOP、员工训练数据、顾客反馈和单店验证经验。越多真实经营闭环进入系统，越难被简单复制。",
    "单店模型开第二家前要验证什么？": "开第二家前要验证定位是否被顾客理解、清泡调补养是否能稳定转化、员工训练是否能复制、基础复访是否成立、成本结构是否可控。没有验证清楚前不急着扩张。",
    "100 平方和 150 平方店怎么取舍？": "取舍不先看面积大小，而看单店模型要验证什么。100 平方更适合低成本试点和快速迭代，150 平方适合在客流、房间利用率和人员组织已更清楚后再考虑。",
    "奈晚有什么值得学习？": "学习重点不是照搬门店风格，而是看它如何做年轻化表达、场景感和轻决策体验。荷小悦要提炼可借鉴的表达方式，同时保留自己的草本泡脚和社区复访逻辑。",
    "郑远元有什么值得学习和避开？": "值得学习的是标准化、门店密度和基础服务效率；需要避开的是只陷入传统足疗心智。荷小悦应把草本泡脚、轻调理和社区体验讲清楚，形成不同心智。",
    "谷小推和荷小悦有什么差异？": "谷小推更偏推拿按摩心智，荷小悦应突出草本泡脚入口、清泡调补养分层和社区复访服务。比较时只讲差异和借鉴点，不做情绪化评价。",
    "门店接待第一句话怎么说？": "第一句话要轻，不要销售感太强。可以说：欢迎来荷小悦，今天是想先放松一下，还是最近有睡眠、疲劳、手脚凉这类状态想调一调？",
    "首次客户服务流程怎么做？": "首次客户流程是接待问候、简单状态询问、推荐清泡或对应泡脚方、说明服务流程、体验中观察反馈、结束后做不推销式建议和复访提醒。",
    "客户体验后怎么做不推销式推荐？": "体验后先问感受，再给建议，不急着成交。可以说：你今天这个状态更适合持续观察，如果觉得泡完轻松，下次可以按这个方向继续做一次。",
    "差评或投诉怎么处理？": "先接住情绪，再确认事实，给出可执行补救，并沉淀为复盘任务。不能争辩，也不能随口承诺超出门店标准的补偿。",
    "品牌标准手册应该包含什么？": "品牌标准手册至少包含一句话定位、目标客群、核心卖点、清泡调补养表达、角色化话术、禁用表达、视觉调性、对外传播边界和版本复核记录。",
}


def _normalize_card_id(value: str) -> str:
    stop_chars = "，。！？?；;：:、（）()[]【】\"'“”‘’"
    normalized = value
    for char in stop_chars:
        normalized = normalized.replace(char, "")
    return "-".join(normalized.split()) or "card"


def _role_versions(question: str, answer: str, module: str) -> dict[str, str]:
    module_name = next((item["name"] for item in _MODULES if item["key"] == module), "品牌知识")
    short_answer = answer if len(answer) <= 88 else answer[:87].rstrip("，。；; ") + "。"
    customer_version = short_answer
    if module in {"franchise_financing", "store_model", "competitor_intelligence"}:
        customer_version = "顾客端不讲内部模型，只讲门店能提供的服务、体验边界和到店价值。"
    return {
        "founder": f"用于判断：{short_answer}",
        "store_staff": f"用于门店：先问顾客状态，再用一句话解释。{short_answer}",
        "franchisee": f"用于合作沟通：这属于{module_name}，要同时讲清价值、条件和边界。",
        "customer": customer_version,
    }


def brand_authority_cards() -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    for item in _GOLDEN_QUESTIONS:
        question = item["question"]
        module = item["module"]
        meta = _MODULE_CARD_META[module]
        answer = _QUESTION_ANSWERS[question]
        cards.append(
            {
                "card_id": f"brand:{_normalize_card_id(question)}",
                "question_pattern": question,
                "aliases": [question.rstrip("？")],
                "intent": meta["intent"],
                "audience": meta["audience"],
                "module": module,
                "answer": answer,
                "role_versions": _role_versions(question, answer, module),
                "forbidden_terms": list(meta["forbidden_terms"]),
                "applicable_scenarios": [item["scenario"]],
                "review_status": "approved_v1",
                "version": "v1.0",
                "status": "approved",
                "source": "brand_assets",
                "reasoning": ["来自开店前品牌黄金问题集，用于统一团队品牌口径。"],
                "evidence": [
                    {
                        "title": "荷小悦品牌资产中心 v1",
                        "domain": module,
                        "strength": "high",
                        "status": "approved",
                        "source_type": "approved_internal_asset",
                        "owner": "品牌负责人",
                        "version": "v1.0",
                    }
                ],
                "corrections": [],
                "next_actions": list(meta["next_actions"]),
            }
        )
    return cards


def build_brand_asset_center() -> dict[str, Any]:
    return {
        "version": "hxy-brand-assets.v1",
        "stage": "pre_open_brand_first",
        "positioning": "先把荷小悦品牌资料变成可问、可审、可复用、可训练、可招商的品牌知识资产。",
        "excluded_now": [
            "客户消费数据开店后再接入",
            "POS 数据开店后再接入",
            "单店净利润等真实经营指标开店后再接入",
        ],
        "modules": deepcopy(_MODULES),
        "golden_questions": deepcopy(_GOLDEN_QUESTIONS),
        "deliverables": deepcopy(_DELIVERABLES),
        "next_build_order": [
            "先固化品牌定位和核爆点口径",
            "再固化清泡调补养产品服务表达",
            "再形成招商融资和门店模型话术",
            "同步生成员工训练题库和禁用表达",
            "最后把竞品资料转成可借鉴点和避坑清单",
        ],
    }
