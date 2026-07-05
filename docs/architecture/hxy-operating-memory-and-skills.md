# HXY Operating Memory And Skills

## Positioning

HXY 经营大脑的底层不是单一知识库，而是 `Knowledge + Memory Layer + HXY Operating Skill + Review Loop`。PostgreSQL + pgvector 继续作为 HXY 项目的事实、资料、向量和答案卡底座。Supermemory 这类项目作为 Memory Layer 设计参考，用于长期记忆、用户画像、矛盾处理和上下文连续性，不替代 HXY 自有数据库。

## Operating Brain Foundation

运营大脑不是项目资料问答页。它的目标不是让用户翻资料，而是把 HXY 的关键问题转成稳定、可复核、可复用的经营结果。

第一阶段融合六类知识：

- `project_knowledge`: HXY 品牌、产品、菜单、泡脚方、招商、培训 SOP 和权威答案卡。
- `operating_data`: HXY 自有门店、订单、转化、复购、客诉、培训和执行数据。
- `market_intelligence`: 行业趋势、竞品、渠道、用户需求和公开市场信号。
- `operating_methodology`: 定位、增长、门店管理、培训、招商和质检方法论。
- `organizational_memory`: 已批准答案、纠偏记录、复核历史和团队经验。
- `role_context`: 创始人、产品、运营、招商、门店员工和未来 Hermes/企微角色上下文。

模型策略先按任务路由，不做预训练。初期采用 RAG + PostgreSQL + pgvector + 答案卡 + 复核闭环：强推理模型负责经营判断和纠偏，轻量模型负责分类和质检，Embedding 模型负责召回，视觉模型负责图片理解，语音模型负责培训与门店语音转写。只有当已批准答案和纠偏记录积累到足够稳定的数据集后，才评估微调；预训练不适合作为 HXY 当前阶段的投入方向。

## Boundary

- 所有 HXY 资料、记忆、答案卡和用户画像都必须保存在 `/root/hxy` 范围内。
- 不得接入 /root/htops 的门店、会员、订单、技师、团购、经营数据。
- Hermes Agent 或企微入口只能调用 HXY API，不能绕过 HXY 权限和复核流程。
- 任何通用 Skill 可以复用工程模式，但不能携带荷塘悦色业务数据。

## Memory Layer

Memory Layer 负责把一次次问答、上传、纠偏、复核和答案卡沉淀成可持续演进的组织记忆。

核心能力：

- 用户画像：识别提问者角色、常问业务域、可见权限和常用输出格式。
- 矛盾处理：当新资料与旧答案冲突时，不直接覆盖，先生成冲突记录和复核任务。
- 遗忘与降权：过期、低可信、被纠偏的资料降低权重，不继续作为稳定结论。
- 连续上下文：同一角色的连续问题可以继承场景和目标，但关键业务结论仍以答案卡为准。
- 经验沉淀：把老员工经验、创始人判断和门店复盘转成可检索、可复核、可复用的组织资产。

## Agent Memory Cognitive Contract

HXYOS 的 Agent 记忆系统不是数据库三级缓存。`Redis / PostgreSQL / 向量库` 是存储介质，不是认知架构。真正的记忆分层按推理职责划分：当前任务状态、上下文窗口、长期外部记忆和正式知识各自承担不同责任。

核心原则是：正确的信息在正确时间出现在正确位置。系统不能把所有历史对话都塞进 Prompt，也不能把向量库召回结果当成企业结论。

### Three Cognitive Layers

- `Working Memory`: 当前任务状态。保存本轮目标、角色、场景、已完成步骤、工具调用结果、剩余动作、风险闸口和停止条件。它应是结构化 JSON，而不是自然语言聊天历史。
- `Short-Term Memory`: 当前上下文窗口。保存最近对话、当前问题、已压缩摘要和本轮必要证据。它由上下文预算控制，超过预算时先摘要，再淘汰低价值内容。
- `Long-Term Memory`: 持久化外部记忆。保存过程记忆、历史决策、假设、纠偏、复盘、偏好和可晋升候选。长期记忆通过检索进入上下文，但过程记忆不能作为权威依据。

HXY 还必须单独区分 `Formal Knowledge`: 已核定答案卡、SOP、品牌口径、产品规则和经营决策。Formal Knowledge 不是 Long-Term Memory 的普通子集，而是经过复核、版本化、授权使用的企业知识。

### Context Budget

每次回答必须显式分配上下文预算：

- 目标和任务状态：保留，不能被历史闲聊挤掉。
- 权威答案卡：优先进入上下文。
- 证据片段：只放 Top-K，默认 3-5 条；超过 8 条视为 context overflow。
- 过程记忆：只作为提醒，默认最多 2 条。
- 历史对话：只保留摘要，不保留全文堆叠。
- 低可信资料：默认不进主上下文，只进复核材料。

当预算冲突时，优先级是：

```text
当前任务状态 > 权威答案卡 > 已核定知识 > 高质量证据 > 过程记忆提醒 > 历史摘要 > 参考资料
```

### Retrieval Signals

长期记忆召回不能只靠 embedding 相似度。HXYOS 记忆检索必须融合多信号：

- `semantic relevance`: 语义相关度，判断内容是否真正回答当前问题。
- `recency`: 时效性，近期纠偏、近期决策、近期复盘权重更高。
- `importance`: 重要性，品牌口径、禁用表达、合规边界、创始人决策权重更高。
- `authority status`: 权威状态，`approved` 高于 `current_candidate`，过程记忆只能作为 context hint。
- `role fit`: 角色适配，员工训练、创始人决策、运营复盘使用不同记忆。
- `risk level`: 医疗、收益、价格、加盟、对外传播相关内容进入更强质检。
- `contradiction`: 与已核定知识冲突时不直接使用，先生成冲突复核。

召回结果必须带来源、状态、时间、置信度和可用边界。没有这些元数据的记忆不能进入正式回答链路。

### Forgetting And Decay

遗忘不是删除，而是降权、归档、冻结或触发复核。HXYOS 使用 `decay_score` 表示记忆是否还适合被召回：

```text
decay_score = age_decay + low_confidence_penalty + correction_penalty + conflict_penalty - reuse_boost - approved_boost
```

执行规则：

- 被纠偏的记忆进入 `cooldown`，不能继续作为默认上下文。
- 与 approved 答案卡冲突的记忆进入 `conflicted`，只用于复核。
- 长期未确认的外部资料进入 `stale`，只能作为参考。
- 高频复用且反馈稳定的记忆可以生成晋升建议。
- 被复核否定的记忆保留审计记录，但从召回候选中移除。

存储成本采用 `hot / warm / cold` 分层：

- `hot`: 最近高频、强相关、需要快速召回的记忆。
- `warm`: 仍有价值但不常用的决策、复盘、训练样本。
- `cold`: 原始历史、旧版本、低频外部资料和审计记录。

### Promotion Gate

过程记忆进入企业知识必须经过晋升闸口：

```text
process memory
→ candidate claim
→ evidence requirement
→ human review
→ approved answer card / SOP / decision record
```

任何 AI 回答只允许把过程记忆当“上下文提醒”。它可以帮助系统记住偏好、否定清单和历史讨论，但不能直接支撑对外话术、员工 SOP、招商口径、价格政策、医疗或收益相关表达。

## HXY Operating Skill

HXY Operating Skill 是经营结果的标准交付方式。每个 Skill 都必须声明输入、输出、质量闸口、风险边界和复核人。

第一批 Skill：

- 品牌定位 Skill：输出一句话定位、支撑理由、可外讲版本和内部决策版本。
- 产品体系 Skill：输出清泡调补养结构、项目解释、适用人群、禁用表达。
- 门店培训 Skill：输出员工可背诵话术、服务动作、纠偏题库。
- 招商话术 Skill：输出加盟沟通口径、收益假设、风险边界和反对意见回答。
- 纠偏复核 Skill：把不准确反馈转成原因、补资料任务、复核角色和答案卡草稿。

## Understanding Engine

Understanding Engine 是经营大脑的认知中枢，位于多模态输入和 HXY Operating Skill 之间。它不采用单线性的 0-6 层逻辑，而采用 `深度维度 × 应用维度`。

深度维度递进理解：

- `D1_perception`: 感知关键词、实体、数字、文件类型、图片类型和输入形态。
- `D2_classification`: 判断业务域、对象、角色、场景和输入意图。
- `D3_decomposition`: 拆出事实、对象、属性、流程、限制条件、数据、关系和冲突元素。
- `D4_causal_inference`: 判断因果、业务影响、转化阻力、执行约束和可能后果。
- `D5_judgment`: 识别主要矛盾、关键杠杆、冲突元素和优先级。

应用维度并发交付：

- `A1_role_output`: 总部、加盟商、店长、员工、顾客的角色化输出和表达风格适配。
- `A2_risk_boundary`: 禁用表达、过度承诺、价格政策、医疗合规、不确定性和证据链。
- `A3_action_plan`: 下一步动作、责任人、时间、资源、能力、权限和可执行性校验。
- `A4_conflict_correction`: 新旧知识、总部门店、理论实操、角色利益和合规表达的冲突检测与纠偏。
- `A5_memory_evolution`: 答案卡、版本历史、知识热度、知识盲区、低质资料和纠偏信号。

所有输入先经过 Intent Recognition Layer，判断是提问、资料、指令、纠偏反馈还是沉淀请求，再决定走快速应答、深度理解、执行指令、入库记忆或纠偏复核。

主要矛盾识别使用 Priority Matrix：`impact × urgency × controllability × strategic_relevance`。角色化方案必须通过 Executability Gate，校验资源、能力、权限、风险和验收方式。

## Result Flow

1. 用户在 `brain.html`、Hermes Agent 或企微入口提问。
2. Intent Recognition Layer 判断输入是提问、资料、指令、纠偏反馈还是沉淀请求。
3. Understanding Engine 按 `D1-D5` 深度维度理解输入，并按 `A1-A5` 应用维度生成业务结果。
4. API 根据角色、场景和问题选择 HXY Operating Skill。
5. Knowledge 层召回资料和答案卡。
6. Memory Layer 补充用户画像、历史纠偏、版本历史和冲突状态。
7. Answer Engine 生成 `result_card`。
8. 质量闸口判断是否 `stable`、`review_required` 或 `insufficient`。
9. 反馈进入 Review Loop，必要时更新答案卡、资料权重和知识盲区清单。

## Knowledge Evolution Layer

Knowledge Evolution Layer 负责让系统自我诊断。它跟踪答案卡调用次数、有用率、不准确率、复核次数、冲突次数、低质资料和答不上来的问题。系统应能识别热点知识、不稳定知识、知识盲区、高价值待沉淀问题，并自动触发补资料请求、复核任务、答案卡升级、降权或废弃建议。

## Database Direction

短期继续使用 PostgreSQL + pgvector：

- `knowledge_assets`: 原始资料和资料护照。
- `knowledge_chunks`: 文本、图片理解和向量片段。
- `answer_cards`: 权威答案卡。
- `answer_runs`: 问答运行记录。
- `feedback_events`: 有用、不准确、需完善反馈。
- `review_tasks`: 纠偏复核任务。

下一阶段新增：

- `memory_profiles`: 用户画像和角色偏好。
- `memory_facts`: 经过复核或稳定观察形成的长期记忆。
- `memory_conflicts`: 新旧资料、答案卡和反馈之间的矛盾记录。
- `operating_skills`: HXY Operating Skill 的版本化合同。
- `skill_runs`: 每次 Skill 调用、质量闸口和结果卡记录。

## Why Not Replace The Current Stack

Supermemory 的价值在于提醒 HXY：RAG 不应只是碎片召回，而要形成连续记忆、矛盾治理和画像理解。但 HXY 已经有明确项目边界、资料入库、答案卡、复核任务和 PostgreSQL 数据底座。当前最佳方案是吸收 Supermemory 的 Memory Layer 思想，逐步增强 HXY 自有架构，而不是把经营大脑迁移到外部记忆服务。
