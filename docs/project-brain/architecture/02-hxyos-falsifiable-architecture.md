# HXYOS 可证伪架构总纲

## 结论

HXYOS 不是聊天机器人、资料搜索页、Dify 包装层，也不是单纯 Agent 记忆系统。

HXYOS 是荷小悦的组织级 AI 操作系统：

```text
把资料编译成可信知识，
把可信知识变成经营动作，
把经营动作和反馈沉淀成组织记忆。
```

当前最优架构假设是：

```text
HXYOS =
  LLM Wiki / OKF 知识编译器
  + 企业知识治理系统
  + Learning Memory Layer
  + Agent / Skill Runtime
  + Hermes / 飞书 / Web 执行面
```

这不是最终真理。它必须通过 benchmark、lint、trace、人工复核和真实使用数据持续证伪。

## 为什么不是纯 RAG

纯 RAG 只解决运行时召回，不解决知识本身的问题。

HXY 当前的核心风险是：

- 资料多，但大部分只是参考，不是核定结论。
- 品牌口径、产品话术、门店模型仍在形成。
- 外部文章和方法论有启发，但不能直接变成荷小悦事实。
- AI 容易把候选判断说成确定结论。
- 医疗功效、收益承诺、招商表达存在合规风险。

因此，HXY 必须先做知识编译和治理，再做 RAG 与 Agent。

## 一线方案的位置

### 阿里 LLM Wiki 方法

位置：知识底座。

吸收：

- 编译时和运行时分离。
- raw / ready / pending / archive 的源材料生命周期。
- Markdown + frontmatter 的结构化知识页。
- `graph.json` 显式关系图。
- index / domain / page 的渐进式披露。
- 生成与判断分离。
- 结构、语义、人工三层校验。
- 增量编译和持续 Lint。

不直接照搬：

- HXY 不是数据仓库，不需要表、DDL、任务代码那套原样 schema。
- HXY 的权威来源不是代码，而是已核定资料、负责人、复核记录、真实用户和门店反馈。

### Engram 式持续学习

位置：Learning Memory Layer。

吸收：

- AI 不应每次从零理解组织。
- 系统应从 trace、反馈、复核、训练、复盘中持续学习。
- 长期目标是让模型越来越懂 HXY 的偏好、禁区、表达方式和业务判断。

边界：

- 过程记忆不能作为权威依据。
- 未核定资料不能进入隐性学习的权威层。
- 任何可发布结论必须能追溯到显性知识和复核记录。

### NotebookLM / ima

位置：资料工作台和源材料交互参考。

吸收：

- 基于源材料的问答。
- 引用和多资料综合。
- 把复杂资料变成摘要、问答、简报。

边界：

- 不能把资料工作台当经营大脑。
- 不能绕过 HXY 的 claim、evidence、review、answer card 生命周期。

### Claude / Codex / OpenAI Agents

位置：Agent / Skill Runtime。

吸收：

- Context engineering。
- Tool use。
- Skills，把稳定流程封装成可复用能力。
- Trace、Eval、Guardrails、Human review。
- 可停止、可评测、可复盘的 Agent Loop。

边界：

- Agent 不能直接批准知识。
- Agent 输出必须经过证据、权限、风险和复核状态检查。

### 阿里云百炼 / OpenSearch / DashScope

位置：可替换基础设施。

可用来做：

- 模型调用。
- embedding / rerank。
- OCR / 文档解析。
- 托管式知识库原型。
- 大规模检索和 OpenAI-compatible API。

边界：

- HXY 的业务语义、知识状态、复核规则和决策闸门必须自有。
- 模型和云服务可以替换，HXY 知识资产不能被平台绑定。

## HXYOS 五层架构

### 1. Knowledge Compiler

目标：把散落资料编译为可治理知识。

输入：

- PPT、PDF、Word、图片、公众号文章、会议记录。
- 外部营销、战略、管理、运营资料。
- HXY 自有品牌、产品、门店、培训资料。

输出：

- raw manifest。
- structured extract。
- claim。
- evidence。
- OKF / Wiki page。
- graph relation。
- lint report。

原则：

- 原始资料不直接回答。
- 生成和判断分离。
- 推断内容只能进入候选层。
- 编译产物默认不是 approved。

### 2. Knowledge Governance

目标：决定什么可以被企业使用。

核心对象：

- `Claim`
- `Evidence`
- `AnswerCard`
- `ReviewTask`
- `DecisionRecord`
- `RiskRule`
- `Version`

状态：

```text
raw
reference
ai_structured
current_candidate
needs_review
approved
action_asset
disputed
superseded
archived
```

发布规则：

- 只有 `approved` 和 `action_asset` 可以作为权威依据。
- `reference`、`current_candidate`、`process` 只能作为上下文或复核输入。
- 过度承诺、医疗功效、收益保证默认阻断发布。

### 3. Learning Memory Layer

目标：让系统越用越懂 HXY，但不污染权威知识。

记忆类型：

- 偏好。
- 否定清单。
- 历史决策。
- 待验证假设。
- 复盘片段。
- 用户反馈。
- 训练结果。
- 质检结果。

规则：

- 过程记忆只能做 context hint。
- 过程记忆晋升必须生成候选 claim 和 review task。
- 被多次证实的反馈可提高检索权重，但不能绕过审核。

### 4. Agent / Skill Runtime

目标：让 AI 不只是回答，而是稳定完成业务流程。

第一批 Loop：

- Knowledge Compile Loop：资料入库、拆 claim、生成证据链。
- Issue Reasoning Loop：围绕经营议题判断证据、冲突和下一步。
- Answer Authority Loop：把已核定知识生成答案卡。
- Skill Production Loop：把答案卡生成 SOP、训练题、话术。
- Quality Gate Loop：检查来源、风险、夸大、缺证据和技术痕迹。
- Feedback Evolution Loop：把不准确反馈变成修订任务。

每个 Loop 必须声明：

```text
goal
context_budget
tools
evidence_policy
evaluation
human_review_point
stop_condition
```

### 5. Execution Surface

目标：让系统进入团队日常工作，而不是停留在演示页面。

入口：

- Web 经营控制台。
- Hermes Agent。
- 飞书。
- 未来员工端 H5 / 小程序。

第一屏不应该是聊天框，而应该是：

```text
当前最重要经营议题
运行中的 AI Loop
待复核知识
今日必须处理动作
风险与冲突提醒
```

## 可证伪机制

HXYOS 必须和替代方案对照测试。

对照组：

```text
A. 纯 RAG 问答
B. NotebookLM / ima 式资料工作台
C. Dify / RAGFlow 快速助手
D. HXYOS：知识编译 + 治理 + Agent Loop
```

HXYOS 只有在关键指标上明显胜出，才值得继续加重。

## Benchmark 指标

第一版 benchmark 至少覆盖：

- 答案准确率。
- 引用可靠性。
- 是否区分参考、候选、核定。
- 冲突发现能力。
- 医疗化表达拦截率，目标 `100%`。
- 保证疗效表达拦截率，目标 `100%`。
- 夸大宣传表达拦截率，目标 `100%`。
- 答案卡 / SOP / 训练题沉淀能力。
- token 成本。
- 人工复核成本。
- 团队使用频率。

## 失败标准

出现任一情况，说明当前方案需要降级、砍掉或重构：

- 30 个黄金问题准确率低于 85%。
- 无法稳定区分参考资料和核定知识。
- 医疗化表达、保证疗效表达、夸大宣传任一合规拦截失败。
- 复核成本高于人工整理。
- 生成的 claim 大量无用，人工不愿审核。
- 团队连续两周不用。
- 简单 RAG 效果接近但成本显著更低。

## 当前执行顺序

### Week 1：对外话术风险

优先编译最高合规风险资料：

- 禁用表达库：医疗化、保证疗效、夸大宣传。
- 员工推荐话术：标准版 + 禁忌版。
- 客户常见问题标准答案：至少 10 个高频问题。
- 对外宣传审核标准。

理由：员工说错话、朋友圈文案写错、宣传语夸大，会直接带来市场监管、消费者投诉和品牌信用风险。

### Week 2：融资材料口径

第二优先级编译融资和股东沟通口径：

- 投后估值 2000 万的支撑逻辑。
- 单店模型数据。
- 当前门店数量与筹备进度。
- 股权结构与无对赌承诺。
- 品牌授权关系。

理由：融资 BP、投资人问答、股东汇报口径不一致，会影响数据可信度、估值支撑和下一轮融资。

### Week 3：经营判断

第三批再编译经营判断和战略资料：

- 荷小悦是什么。
- 核爆点定位。
- 清泡调补养。
- 当前战略判断。

### 外部价值验收

第一阶段不能只看内部技术指标，还必须证明对真实角色有用：

- 员工价值：至少 10 个员工常问问题有标准答案，至少 5 个推荐话术有可复制版本，至少 3 个禁用表达有明确提示。
- 创始人价值：至少 5 个投资人常问问题有标准口径，至少 3 个战略判断有可追溯依据，至少 1 份月度股东报告能自动生成框架。
- 组织价值：至少 1 个对外宣传文案能自动风险检测，至少 1 个新门店 SOP 能自动生成，至少 1 个知识冲突能被系统发现。
- 用户确认：至少 3 个真实用户，员工 / 创始人 / 运营负责人，确认“有帮助”。

## 总原则

```text
外部资料可以启发，不能直接定论。
模型可以推理，不能替代复核。
过程记忆可以提醒，不能作为权威。
平台可以外采，业务语义必须自有。
产品价值必须靠 benchmark 和真实使用自证。
```
