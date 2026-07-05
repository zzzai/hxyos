# HXYOS Harness Discipline Layer

## 文章判断

来源文章：`https://mp.weixin.qq.com/s/2kWi0Fld09fNMVIUg9ddKQ`

文章核心对 HXY 的启发不是“再加更多 Agent”，而是：

```text
AI 的稳定性不能靠更长 prompt 保证，
必须靠外置流程、状态文件、门禁、评测和失败阻断保证。
```

对 HXYOS 来说，这篇文章应该进入第二层能力：`Agent / Skill Runtime` 的纪律层。

它不替代：

- LLM Wiki / OKF 知识编译器
- 企业知识治理
- Benchmark
- Hermes / 飞书执行入口

它补强：

- AI 工作流怎么不乱跑
- 多步骤任务怎么可恢复
- 过程怎么可审计
- 每次改动怎么知道变好还是变坏

## 对 HXY 当前阶段的价值

HXY 现在最需要的不是复杂 Agent 群，而是让已经开始建设的知识底座具备纪律：

```text
资料入库必须有状态
知识编译必须有产物
候选 claim 必须可追溯
approved 必须过门禁
Benchmark 必须可重复
Agent 执行必须可停止
失败必须响亮
```

因此，当前只吸收四类能力。

## 立即吸收的能力

### 1. Harness 而不是 Prompt

HXY 不能把规则都塞进一个超长系统提示词。

正确做法：

```text
常驻规则：极少，只保留项目边界、知识生命周期、安全红线
按需上下文：知识编译、答案卡、训练题、复核任务分别加载
确定性门禁：用代码检查，不靠模型自觉
```

落到当前项目：

- `AGENTS.md` 只保留项目边界和硬规则。
- `docs/project-brain/architecture/02-hxyos-falsifiable-architecture.md` 作为架构总纲。
- `knowledge/schema/` 定义机器可检查的契约。
- `tests/` 和 CLI report 作为确定性验证层。

### 2. 状态外置

AI 不能靠聊天历史记住流程状态。

HXY 应把每次知识底座运行状态写成文件：

```text
knowledge/reports/benchmark-latest.json
knowledge/reports/compiler-latest.json
knowledge/reports/governance-*/run-package.json
knowledge/wiki/graph.json
```

下一步应该新增：

```text
knowledge/runs/{run_id}/state.json
knowledge/runs/{run_id}/phases/
```

用于记录：

- 当前 run 到哪一步
- 哪些资料已编译
- 哪些 claim 待复核
- 哪些门禁未通过
- 是否允许进入下一阶段

### 3. 门禁阻断

HXY 的门禁必须是确定性代码，不是“AI 建议”。

当前已有门禁：

- Benchmark pass rate 低于 `0.85` 暴露失败。
- Compiler 输出默认不是 approved。
- compiled wiki page 缺 `sources`、缺 `owner`、有过度承诺会进入 lint。
- 过程记忆不能作为权威依据。

下一步建议补 HXYOS G1-G7 门禁：

```text
G1 Source Gate
原始资料必须有 source_path、hash、类型、进入时间。

G2 Compile Gate
资料必须产出 extract / claim / graph，否则不能说已入库。

G3 Evidence Gate
claim 必须有 sources/evidence，否则只能进入质量 backlog。

G4 Risk Gate
医疗功效、收益承诺、绝对化表达必须阻断。

G5 Review Gate
approved 必须有 owner、last_confirmed、sources、review_status。

G6 Runtime Gate
回答必须区分 reference / candidate / approved。

G7 Eval Gate
回答必须跑 benchmark 或 quality score，失败进入修复队列。
```

### 4. 评测驱动

HXYOS 是否更好，不能靠感觉判断。

当前已经有：

- `knowledge/benchmarks/hxy-brain-benchmark-v1.json`
- `scripts/run-hxy-brain-benchmark.py`
- `/api/operating-brain/benchmark`

下一步要做的是把评测从“空答案基线”升级为“真实回答评测”：

```text
纯 RAG 输出
答案卡输出
HXYOS 编译 + 治理输出
```

同一组黄金问题同时跑，比较：

- 准确率
- 引用率
- 生命周期区分
- 风险拦截
- token 成本
- 人工复核成本

## 暂不吸收的能力

### 不立即做 19 节点长流程

文章中的研发流程适合 AI Coding，不适合 HXY 当前知识底座。

HXY 现在只需要 7 个知识门禁，不需要完整研发链路。

### 不立即做 20+ Agent

HXY 当前不缺 Agent 数量，缺的是：

- 状态
- 契约
- 证据
- 门禁
- 评测

Agent 多了会增加协调成本和上下文污染。

### 不立即做复杂 hook 系统

当前先用：

- CLI
- API endpoint
- pytest
- JSON report

后续如果 Hermes / 飞书开始执行真实任务，再考虑运行时 hook。

## HXY Harness v1

当前最小可行的 HXY Harness 是：

```text
1. run_id
2. state.json
3. phases/
4. gates/
5. reports/
6. benchmark
7. governance lint
```

建议目录：

```text
knowledge/runs/{run_id}/
├── state.json
├── phases/
│   ├── 01_manifest.json
│   ├── 02_extracts.json
│   ├── 03_claims.json
│   ├── 04_graph.json
│   ├── 05_lint.json
│   └── 06_benchmark.json
└── final-report.json
```

`state.json` 最小字段：

```json
{
  "version": "hxy-harness-state.v1",
  "run_id": "knowledge-run-2026-06-28",
  "goal": "compile_hxy_knowledge",
  "current_phase": "lint",
  "status": "blocked",
  "gates": {
    "source_gate": "passed",
    "compile_gate": "passed",
    "evidence_gate": "failed",
    "risk_gate": "passed",
    "review_gate": "pending"
  },
  "next_actions": []
}
```

## 当前落地优先级

### P0：知识底座 Harness

先把知识编译流程变成可恢复、可审计、可阻断。

任务：

- 给 `compile-hxy-knowledge.py` 增加 `--run-id`。
- 输出 `knowledge/runs/{run_id}/state.json`。
- 每个阶段产物进入 `phases/`。
- 任一 gate 失败时状态为 `blocked`。

### P1：真实答案 Benchmark

任务：

- 让 benchmark 支持 answer run 输入。
- 记录每题的 answer、evidence_statuses、citations、flags。
- 输出 failed case 修复队列。

### P2：Hermes / 飞书执行纪律

当 Hermes 开始承接真实任务后，必须遵守：

- 只能调用 HXY API。
- 不能绕过 governance gate。
- 不能把过程记忆当权威证据。
- 执行任务必须带 run_id。

## 结论

这篇文章对 HXY 的价值是把“AI 能力建设”升级为“AI 流程纪律建设”。

HXYOS 当前应该吸收它的底层模式：

```text
分层上下文
状态外置
门禁阻断
确定性评测
失败响亮
```

但不能照搬它的 AI Coding 长流程和大量 Agent。

HXY 当前最正确的动作是：

```text
先给 Knowledge Compiler 和 Benchmark 加 Harness，
让知识底座每次运行都可恢复、可审计、可证伪。
```
