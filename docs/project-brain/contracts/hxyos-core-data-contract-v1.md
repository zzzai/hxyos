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
8. 结构化经营数据不能伪装成文档，也不能按文档分块后当作交易事实。
9. 资料、数据集、经营事件和正式知识使用同一目录与血缘规则，但走不同处理管线。
10. 原始交易事实、顾客个人信息、群聊和现场事件不能无差别进入 pgvector。
11. 门店身份与经营关系分离，经营模式变化不能覆盖历史事实。
12. 经营模式、指标口径、治理策略和正式知识都必须版本化。

## System of Record 边界

HXYOS 是以下对象的权威系统：

```text
组织与岗位身份
门店经营关系和治理策略
正式知识与版本
经营工作流、任务、证据和状态变化
指标定义、计算版本和价值证据
```

订单、会员、支付、退款、团购核销和平台流量初期继续由来源业务系统保存权威原始记录。HXYOS 通过 `DataConnector` 获得不可变 `DatasetSnapshot`，再生成有来源血缘的 `BusinessFact`。HXYOS 不在 V1 回写或覆盖外部系统原始交易。

## 统一数据目录

统一目录不等于统一存储。HXYOS 至少区分以下对象：

### SourceAsset

文件、图片、音频、视频、网页、短文字或渠道附件。现有 `hxy_product_materials` 是 V1 的上传实现，需要演进为组织级 `SourceAsset`，而不是继续只按上传人私有保存。

必需语义：

```text
id
organization_id
store_id
uploaded_by_assignment_id
asset_kind
source_origin
source_authority
content_hash
object_key
visibility_scope
retention_policy
processing_status
created_at
```

上传仅表示进入“组织资料待处理区”，不表示成为正式知识。

门店员工上传的默认可见范围是上传者、所属门店店长和授权总部岗位，不自动向全组织公开。扩大范围必须经过服务端权限策略。

### DataSource

产生结构化经营数据的逻辑来源，例如 POS、会员系统、支付系统、团购平台或人工经营台账。

```text
id
organization_id
source_type
name
owner
system_of_record
data_classification
status
```

### DataConnector

连接 `DataSource` 的执行配置。支持 API、Webhook、定时同步和文件导入。

```text
id
organization_id
data_source_id
connector_type
configuration_ref
schedule
cursor_state
status
```

密钥只保存在密钥管理或服务环境中，不进入数据库正文、运行日志或模型上下文。

### DatasetSnapshot

一次不可变的数据导入或同步版本。

```text
id
organization_id
store_id
data_source_id
connector_id
schema_version
period_start
period_end
content_hash
record_count
object_key
ingestion_status
created_at
```

同一来源重跑产生新快照，不能覆盖旧快照。

### BusinessFact

由 `DatasetSnapshot` 标准化得到的原子经营事实，例如订单、支付、退款、核销、顾客到店和每日营收事实。

```text
id
organization_id
store_id
fact_type
source_snapshot_id
source_record_key
occurred_at
dimensions
measures
normalization_version
created_at
```

模型不能自由生成 `BusinessFact`。解析失败、口径不明或对账不一致的数据进入异常队列。

### MetricDefinition

受治理的业务指标口径。

```text
id
organization_id
metric_key
version
name
formula
calculation_kind
calculation_ref
required_fact_types
dimensions
effective_from
effective_to
status
approved_by
```

“营收”“复购”“客单”“退款率”等名称不能直接作为计算依据，必须引用明确版本。

`formula` 只能使用受控声明式 DSL；复杂指标使用版本化 `calculation_ref` 指向已测试实现。禁止把任意 SQL、Python 或模型生成代码保存后直接执行。

### AssetBinding

统一记录资料、数据快照、知识、对话、经营事件、任务和证据之间的来源或用途关系。

```text
id
organization_id
source_type
source_id
target_type
target_id
relation_type
created_by
created_at
```

`AssetBinding` 只建立血缘，不改变两端对象的权威状态。

## 经营关系与治理

### LegalEntity

记录参与门店所有、经营或合同关系的公司/个体主体，只保存组织治理所需字段，不保存支付凭证或无关个人信息。

```text
id
organization_id
entity_type
display_name
registration_reference
status
created_at
```

### StoreOperatingRelationship

记录门店在某一有效期内的所有者、经营者和经营模式。

```text
id
organization_id
store_id
relationship_version
mode_code              direct_operated | franchise_operated | joint_venture_operated | managed_operated
owner_entity_id
operator_entity_id
agreement_asset_id
effective_from
effective_to
status                 draft | active | superseded | terminated
```

同一门店同一时点只能有一个活动关系，数据库使用有效时间范围排他约束阻止重叠。新增经营模式通过受治理目录发布，不把所有未来模式固化为数据库枚举。

### GovernanceProfile

记录某类经营关系适用的权责和数据规则。

```text
id
organization_id
profile_key
version
decision_rights
approval_policy_refs
data_access_policy
required_metric_definition_ids
audit_policy
effective_from
effective_to
status
```

直营、加盟、联营和托管可使用不同 `GovernanceProfile`，但品牌核心、服务安全底线和最低审计要求不能被降低。

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

附件通过 `SourceAsset` 和 `AssetBinding` 关联，不把二进制内容写入数据库。

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
metric_definition_id
source_snapshot_ids
calculated_at
```

规则：

- MetricFact 不能由大模型自由生成。
- 关闭时长、逾期时长、返工次数和验收次数必须由 StateTransition 与时间字段计算。
- 营收、客单、复购和退款类 MetricFact 必须引用 `MetricDefinition` 与来源 `BusinessFact` 或 `DatasetSnapshot`。
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
SourceAsset / DatasetSnapshot 1 → 0..N AssetBinding
DatasetSnapshot 1 → 0..N BusinessFact
MetricDefinition 1 → 0..N MetricFact
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
- 历史资料中的“立即开放单店加盟”等扩张表述属于历史参考或待验证假设，不能作为正式战略、招商承诺或默认工作流。
