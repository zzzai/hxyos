# HXY Knowledge Activation Loop V1 Design

## Product Decision

HXYOS 已经能安全接收和解析资料，但解析产物还不能进入产品问答。V1 要打通最后一段：

```text
上传
-> 深度解析
-> assignment 私有分块
-> 权限内检索
-> 问答引用
-> 最小 Trace
```

核心边界：

```text
资料可被问答使用，不等于资料成为正式知识。
```

上传资料只能作为 `working_context/reference`。只有已批准答案卡可以产生 `已批准` 回答。

## Scope

V1 includes:

- assignment 私有资料分块表；
- Markdown 标题和段落感知分块；
- worker 成功事务内写入分块；
- assignment-scoped 关键词检索；
- 产品问答仓储适配器；
- 正式答案卡优先、私有上下文补充；
- 回答引用材料标题和原文入口；
- Session/Trace 最小运行记录；
- PostgreSQL 16 权限与并发验证。

V1 excludes:

- 自动知识晋升；
- 自动审核或正式发布；
- 向量数据库和 Embedding；
- GraphRAG；
- 跨 assignment 共享上传资料；
- 完整 Agent 运营分析看板；
- 新前台页面。

## Alternatives

### Write into global knowledge tables

Rejected. It would mix private working material with formal enterprise knowledge and make authority filtering fragile.

### Search normalized files at request time

Rejected. It cannot provide stable ranking, assignment isolation, durable citations or observable retrieval behavior.

### Separate private material index

Selected. It preserves governance boundaries and can later replace lexical retrieval with hybrid/vector retrieval without changing the product contract.

## Data Model

### `hxy_material_chunks`

```text
chunk_id
assignment_id
material_id
artifact_id
chunk_index
heading
content
char_count
official_use_allowed=false
created_at
```

Constraints:

- chunk ownership must match material ownership;
- artifact must be the normalized Markdown artifact for the same material;
- each artifact has one ordered chunk sequence;
- chunks can never be marked official;
- deletion of a material removes its chunks.

Indexes:

- assignment/material ordered index;
- assignment recent index;
- trigram content index for lexical recall.

### `hxy_product_answer_traces`

```text
trace_id
assignment_id
conversation_id
user_message_id
assistant_message_id
intent
retrieval_count
private_material_count
authority_card_hit
model_name
input_tokens
output_tokens
latency_ms
outcome
payload_json
created_at
```

Trace rows contain ids and bounded operational metadata, not full raw documents or hidden chain-of-thought.

## Chunking

V1 uses deterministic Markdown-aware chunking:

- preserve nearest heading;
- group complete paragraphs;
- target about 900 Chinese characters;
- overlap the last paragraph up to about 120 characters;
- never create empty or metadata-only chunks;
- cap chunk count per document to protect storage and retrieval cost.

The chunker is a pure function. The worker writes all chunks in the same database transaction that changes the material to `ready`.

## Retrieval

Material retrieval is always called with the active `assignment_id` from the server-side session.

Ranking signals:

```text
full query match
business keyword match
heading match
material recency
domain match
```

Deictic questions such as “刚上传的资料讲了什么” retrieve the latest ready material for the assignment. They never retrieve another assignment's material.

Returned retrieval items use public-safe identifiers:

```text
source_type=private_material
source_path=material:<uuid>
source_url=/api/v1/materials/<uuid>/content
stage=working_context
status=reference
official_use_allowed=false
```

No storage key or local path is returned.

## Answer Policy

Order:

1. resolve active assignment from the signed session;
2. search approved answer cards;
3. search formal knowledge through the existing repository;
4. search assignment-private material chunks;
5. merge and rank evidence;
6. generate answer;
7. persist safe answer and Trace.

Rules:

- approved answer card hit remains `已批准`;
- any answer based only on uploaded material is `AI 草稿` or `待复核`;
- uploaded material may explain “the document says X” but cannot assert “HXY official policy is X”;
- material sources are labeled `reference` in the product;
- medical, return, price and financing claims retain existing risk gates;
- process memory remains context-only and is not added in this slice.

## Product Contract

The main conversation remains unchanged. In the existing answer detail drawer, a material source may include a safe “查看资料” link.

No material library, dashboard, review queue or technical trace is added to the frontstage.

## Minimal Trace

The current article on Agent operations is useful only after real interactions exist. V1 records the minimum fields needed to answer:

- which role asked;
- whether private material was retrieved;
- whether an approved card answered;
- which model route ran;
- latency and available token usage;
- whether generation succeeded.

This schema remains OpenTelemetry/Langfuse/Volcengine compatible at the conceptual level, but no external telemetry platform is required now.

## Failure Handling

- chunk insert failure rolls back material completion;
- missing chunks keep the material from being marked searchable;
- search failure falls back to the governed formal answer path;
- trace write is in the same transaction as assistant message completion;
- a trace failure must not expose an unpersisted assistant answer;
- all retries remain bounded by the material parser job.

## Acceptance Criteria

1. successful parsing writes ordered chunks before material becomes `ready`;
2. a different assignment cannot retrieve those chunks;
3. “刚上传的资料讲了什么” retrieves the current assignment's latest material;
4. keyword questions retrieve matching private chunks;
5. private material answers are never `已批准`;
6. approved answer cards still take precedence;
7. citations contain no storage key or local path;
8. material citations can open the authorized original endpoint;
9. each completed product answer has one bounded Trace row;
10. no new frontstage module is introduced.
