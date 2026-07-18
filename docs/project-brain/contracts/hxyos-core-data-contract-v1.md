# HXYOS Core Data Contract V1

## 目的

本契约冻结 HXYOS V1 的业务事实、AI建议和异步执行边界。数据库迁移、API、飞书卡片、PWA页面、Worker和指标计算必须遵守本契约。

## 核心原则

1. 原始输入不是经营事实。
2. AI 输出是建议，不是权威状态。
3. 状态变化必须由确定性命令产生。
4. 证据不可被原地覆盖。
5. 指标事实必须从可审计业务记录计算。
6. 正式知识与经营事件、聊天记忆相互隔离。
7. 所有业务对象必须包含 `organization_id`，门店对象必须按需包含 `store_id`。

## 边界对象

### InboundEnvelope

渠道输入的原始账本。

必需字段：

```text
id
organization_id
channel                 feishu | pwa | admin | api
channel_tenant_id
channel_message_id
channel_thread_id
sender_user_id
sender_assignment_id
store_id
intent_hint
raw_text
received_at
idempotency_key
visibility_scope
status                  received | queued | processed | needs_attention | rejected
```

附件通过文件对象关联，不把二进制内容写入数据库。

约束：同一组织、渠道和 `idempotency_key` 只能创建一条有效记录。

### AIProposal

AI 对原始输入或业务对象的提取、分类、建议和风险判断。

必需字段：

```text
id
organization_id
source_envelope_id
target_type
target_id
proposal_type
payload
confidence
risk_level
model_provider
model_name
prompt_version
input_hash
status                  proposed | auto_accepted | accepted | rejected | superseded
created_at
decided_at
decided_by
```

约束：AIProposal 不能直接修改正式字段。接受动作必须由规则引擎或有权限的用户执行并留下状态记录。

### OutboxMessage

业务事务与异步执行之间的可靠交接记录。

必需字段：

```text
id
organization_id
topic
aggregate_type
aggregate_id
payload
idempotency_key
status                  pending | leased | retryable_failed | succeeded | dead_letter
attempt_count
max_attempts
available_at
lease_owner
lease_expires_at
last_error_code
last_error_summary
created_at
completed_at
```

约束：OutboxMessage 必须与触发它的业务记录在同一数据库事务中写入。

## 六个业务核心对象

### OperatingEvent

组织中已经发生、正在发生或需要处理的经营事项。

```text
id
organization_id
store_id
event_type
title
description
source_envelope_id
reporter_assignment_id
owner_assignment_id
severity                low | medium | high | critical
status                  open | active | resolved | closed | cancelled
occurred_at
detected_at
due_at
closed_at
policy_version
created_at
updated_at
```

规则：

- `resolved` 表示责任人已提交结果，尚未完成验收。
- `closed` 必须满足对应工作流的验收策略。
- `high/critical` 事件不能仅由AI关闭。
- 事件字段修改必须产生 StateTransition 或审计记录。

### WorkflowInstance

某个经营事件采用的可版本化处理流程。

```text
id
organization_id
store_id
operating_event_id
workflow_type
workflow_version
status                  pending | running | waiting | completed | cancelled | failed
current_state
started_at
completed_at
created_at
updated_at
```

一个 OperatingEvent 可以有零个或多个 WorkflowInstance，但同一工作流类型和版本只能有一个活动实例。

### Task

需要具体责任人执行的动作。

```text
id
organization_id
store_id
workflow_instance_id
operating_event_id
parent_task_id
task_type
title
details
creator_assignment_id
assignee_assignment_id
status                  open | assigned | in_progress | submitted | accepted | rework | cancelled
priority
due_at
submitted_at
accepted_at
created_at
updated_at
```

规则：

- AI 可以建议责任人，规则可以自动分派，最终分派结果属于正式业务状态。
- `accepted` 必须有验收人和至少一个符合策略的 Evidence。
- 外部施工方没有账号时，由店长记录责任方名称和实际处理结果，不伪造内部身份。

### Evidence

支持任务执行、验收和复盘的不可变证据。

```text
id
organization_id
store_id
operating_event_id
workflow_instance_id
task_id
evidence_type           photo | audio | video | document | text | system_record
object_key
content_hash
source_envelope_id
submitted_by
submitted_at
visibility_scope
scan_status
metadata
supersedes_evidence_id
```

Evidence 不允许原地替换。修正版通过 `supersedes_evidence_id` 形成链路。

### StateTransition

所有正式业务状态变化的追加记录。

```text
id
organization_id
store_id
aggregate_type
aggregate_id
from_state
to_state
command_type
actor_type              user | policy | system
actor_id
reason
policy_version
occurred_at
correlation_id
```

AI 不能作为 `actor_type`。AIProposal 被接受后，实际执行者应为授权用户或有版本的确定性策略。

### MetricFact

从可审计业务记录计算出的原子指标事实。

```text
id
organization_id
store_id
metric_key
subject_type
subject_id
value_numeric
value_text
unit
window_start
window_end
derived_from_transition_ids
calculation_version
calculated_at
```

规则：

- MetricFact 不能由大模型自由生成。
- 关闭时长、逾期时长、返工次数和验收次数必须由 StateTransition 与时间字段计算。
- 指标修正必须生成新版本，不能覆盖历史值。

## 风险与确认策略

```text
low + 高置信度
→ 自动归类、自动分派、店长验收

medium 或低置信度
→ 店长确认必要字段后推进

high
→ 店长处理，总部或授权负责人验收

critical
→ 立即通知总部，禁止AI自动推进关键状态
```

安全、人员受伤、医疗化表达、重大客诉、预算重大变更和品牌核心偏差至少为 `high`。

## 关联关系

```text
InboundEnvelope 1 → 0..N AIProposal
InboundEnvelope 1 → 0..N OperatingEvent
OperatingEvent 1 → 0..N WorkflowInstance
OperatingEvent 1 → 0..N Task
WorkflowInstance 1 → 0..N Task
Task 1 → 0..N Evidence
任一业务聚合 1 → 0..N StateTransition
StateTransition N → 0..N MetricFact
```

## 知识边界

- 群消息、经营事件和AIProposal不自动进入正式知识库。
- 重复问题只能生成标准候选，并保留关联事件和证据。
- 候选标准通过治理流程后，才能形成正式知识版本或工作流版本。
- pgvector仅索引被知识策略明确允许的内容。

