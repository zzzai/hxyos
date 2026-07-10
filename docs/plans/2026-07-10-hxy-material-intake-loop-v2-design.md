# HXY Material Intake Loop V2 Design

## Product Decision

资料上传后的后台处理必须自动推进，但不能自动把资料变成荷小悦正式知识。

```text
上传原件
-> 初步理解
-> 原子创建解析任务
-> 后台深度解析
-> Source Card
-> 产品态更新
```

V2 只解决“资料可靠地被系统接住并理解”。它不生成大批 claims，不创建审核洪水，也不触碰正式知识版本。

## Scope

V2 includes:

- PostgreSQL 持久解析任务；
- worker 租约、超时回收、有限重试；
- MarkItDown 深度解析 PDF、Word、PowerPoint、Excel 和文本文件；
- 原件、标准化 Markdown、Source Card 三者的证据链；
- assignment 隔离和私有衍生产物路径；
- 前台仅显示 `processing`、`ready`、`needs_attention`；
- 运行尝试和错误摘要可审计。

V2 excludes:

- 自动批准正式知识；
- 自动晋升长期记忆；
- 自动生成 claims 或 Review Queue；
- MinerU、图片 OCR 和多模态理解；
- 新前端模块、后台仪表盘或治理页面；
- Redis、Celery、LangGraph、Temporal。

## Why PostgreSQL Queue First

当前规模是一台服务器上的单类解析任务。PostgreSQL 已经是事实与权限的主存储，使用 `FOR UPDATE SKIP LOCKED` 可以提供：

- 上传和入队同一事务提交；
- 多 worker 不重复领取；
- worker 崩溃后通过租约回收；
- 不新增 Redis 运维面；
- 状态、尝试和产物可直接审计。

当任务类型、吞吐量或跨服务编排明显增长时，再把队列执行层替换为 Redis/Temporal；业务状态和治理边界不变。

## Data Model

### `hxy_material_parser_jobs`

One active parser job per material.

```text
job_id
material_id
assignment_id
parser_strategy
status: queued | running | retryable_failed | succeeded | permanent_failed
attempt_count
max_attempts
available_at
lease_owner
lease_expires_at
last_error_code
last_error_summary
created_at
started_at
completed_at
updated_at
```

The database enforces:

- material and assignment ownership match through a composite foreign key;
- one active/non-archived job per material;
- running jobs have a lease owner and expiry;
- official knowledge flags do not exist on jobs.

### `hxy_material_artifacts`

```text
artifact_id
material_id
assignment_id
job_id
artifact_type: normalized_markdown | source_card
storage_key
sha256
size_bytes
metadata_json
official_use_allowed = false
created_at
```

Artifacts are immutable. A retry writes a new artifact only after parsing succeeds. Derived storage keys are generated from assignment/material/job ids, never from a user-controlled path.

### `hxy_material_job_attempts`

Each claim writes one attempt row with start/end, outcome, parser version and bounded error summary. This is the V2 run record; a general Harness run table is not required for this slice.

### Material status

The existing internal material status constraint is extended to:

```text
processing
ready
needs_attention
archived
```

Legacy values remain readable during migration. API output maps both old and new internal values to the three product states.

## Transaction Boundaries

Upload performs:

1. validate and write the original to a temporary file;
2. atomically rename the original into private storage;
3. open one database transaction;
4. lock the assignment and enforce quota;
5. insert material with preliminary understanding;
6. insert parser job in `queued` state;
7. commit.

If database work fails, the newly written untracked file is removed. Replaying the same `client_upload_id` returns the existing material and does not create another job.

Worker performs:

1. claim one available job using `FOR UPDATE SKIP LOCKED`;
2. mark it `running`, assign a lease and create an attempt;
3. resolve the original through a storage-root containment check;
4. parse with MarkItDown outside the database transaction;
5. write normalized Markdown and Source Card to temporary files;
6. atomically rename artifacts;
7. complete job, insert artifact metadata and update material to `ready` in one transaction.

Failures are classified as retryable or permanent. Retryable failures use bounded exponential backoff. After `max_attempts`, the job becomes `permanent_failed` and the material becomes `needs_attention`.

## Parser Contract

The parser adapter receives a trusted local path and returns:

```text
text_content
title when available
parser_name
parser_version
warnings
```

It does not classify authority and does not write files. Empty output is a permanent parse failure. Missing dependency, timeout and transient I/O failures are retryable.

## Source Card

The Source Card is a governed description of the source, not extracted company truth.

Required fields:

```text
version
source_id
material_id
source_hash
file_name
document_type
source_origin
authority_level
domain
knowledge_scale
quality_signals
allowed_use
blocked_use
official_use_allowed=false
understanding_summary
parser
created_at
```

Rules:

- `claimed_official` remains a claim about the file, never formal authority;
- external sources are reference-only;
- all cards block `official_answer`, `external_marketing`, `financing_statement` and `medical_claim` until a later governed promotion;
- no chat or process memory can mutate Source Cards or official knowledge.

## Product Contract

Frontstage language:

```text
processing      正在理解
ready           可以使用
needs_attention 需要关注
```

The UI must not expose parser jobs, leases, chunks, claims, review queues or governance internals. The latest upload receipt remains above the main composer. Polling the existing material detail endpoint is sufficient; no new page is introduced.

Manual retry keeps the same endpoint but requeues the saved original. It does not run a parser inside the API process.

## Security And Isolation

- original and derived files remain under HXY-owned private directories;
- every database read/write is assignment-scoped;
- workers resolve paths through containment checks;
- errors returned to the product never contain local paths, command output or stack traces;
- artifacts have `official_use_allowed = false` enforced by the database;
- no HXY data is written to `/root/htops` or htops databases.

## Acceptance Criteria

1. upload and parser enqueue commit atomically;
2. two workers cannot claim the same job;
3. stale leases are reclaimable;
4. retries stop at the configured maximum;
5. MarkItDown produces private normalized Markdown for supported documents;
6. successful parsing creates an immutable Source Card and updates product state to `ready`;
7. permanent failure preserves the original and updates product state to `needs_attention`;
8. no parser output or Source Card can be official knowledge;
9. assignment boundaries hold for materials, jobs and artifacts;
10. existing conversation-first frontend remains minimal.
