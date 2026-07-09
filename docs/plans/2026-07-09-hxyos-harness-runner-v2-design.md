# HXYOS Harness Runner V2 Design

## Core Judgment

HXYOS should not first build a very strong Agent.

It should first build an auditable, pausable, reviewable knowledge and task runtime. Agent is only one executor inside that runtime.

Highest principle:

```text
后台自动推进可以做。
后台自动批准、自动发布、自动改核心知识不可以。
```

The product should be described as:

```text
HXYOS = 受治理的知识自进化系统
```

AI can extract, classify, draft, evaluate, detect conflict, and propose changes. Whether something becomes HXY official knowledge must remain a governed human decision.

## Scope For V2

V2 is not a general autonomous coding Agent.

V2 covers only:

- material intake loop;
- Source Quality Gate;
- Review Queue;
- run records;
- manual approval workflow;
- knowledge version and evidence chain design.

Explicitly out of scope:

- automatic content publishing;
- marketing automation;
- automatic official knowledge import;
- automatic brand/positioning approval;
- automatic VI/SI decisions;
- direct Temporal rollout;
- direct htops integration.

## Correct Product Layers

```text
HXYOS Product Surface
人每天怎么用：问答框、场景工作流、资料入库、审核台、运行记录。

Harness Runner
任务怎么自动推进：目标、范围、命令、轮次、停止条件、报告。

Knowledge Engine
资料怎么变知识：解析、资料身份卡、chunk、claim、asset draft、证据链。

Governance Gate
什么能进正式口径：审核策略、权限、版本、发布闸门、冲突检查。

Observability
每一步为什么这么做：日志、trace、模型调用、成本、benchmark、状态迁移。
```

## Technology Judgment

The current target architecture is valid, but it should be staged.

### Stage 1

Use:

```text
FastAPI
PostgreSQL
Redis + RQ/Celery
MinIO or local file storage
pgvector
OpenTelemetry-compatible logs later
```

Why:

- fewer moving parts;
- enough for current HXY scale;
- fits Python AI/RAG/document tooling;
- easier to test and operate on one server.

### Stage 2

Add LangGraph only for flows that need:

- persistent Agent state;
- pause/resume;
- human-in-the-loop;
- multi-step reasoning with tools.

Do not use LangGraph as a replacement for governance.

### Stage 3

Add Temporal only when background flows become too long or operationally complex for queue workers.

Use Temporal for:

- durable long-running workflows;
- retries and timers;
- distributed workers;
- explicit workflow histories.

Do not introduce Temporal in Stage 1. It would add too much operational complexity before the core governance loop is proven.

## First Loop To Build

Do not build six loops at once.

The first mature loop is:

```text
资料入库 Loop + Source Quality Gate + Review Queue
```

Flow:

```text
raw source
-> parse
-> source card
-> source quality score
-> chunk/index
-> claims draft
-> knowledge asset draft
-> review task
-> human approve/reject
-> approved knowledge version
```

This loop gives HXYOS a real knowledge foundation.

## Source Quality Gate

Every source gets a source card before it can influence downstream knowledge.

Minimum fields:

```text
source_id
source_path or source_url
source_hash
source_type
source_class
business_domain
granularity
authority_level
quality_score
risk_level
allowed_use
blocked_use
review_intensity
classification_reason
created_at
updated_at
```

Source classes:

```text
official_internal
internal_working
external_reference
competitor_reference
process_memory
fragment
data_report
compliance_risk
```

Authority levels:

```text
reference_only
candidate
review_required
approved
restricted_risk
superseded
```

Allowed use examples:

```text
reference
draft
internal_training
risk_check
benchmark_seed
```

Blocked use examples:

```text
official_answer
external_marketing
financing_statement
medical_claim
franchise_commitment
```

## Review Queue

Humans should not review raw claim floods.

Humans review:

- high-risk source cards;
- conflict groups;
- core decision topics;
- draft knowledge assets;
- proposed approved knowledge versions.

Review tasks must include:

```text
task_id
review_type
target_type
target_id
priority
required_role
decision_options
evidence_links
risk_flags
current_status
created_by_run_id
```

Decision options:

```text
approve
reject
needs_more_evidence
revise
supersede
archive
```

Review Queue must never be confused with approved knowledge.

## Approval Policies

Approval should be policy-driven, not hard-coded in prompts.

Examples:

```text
brand_positioning -> founder approval required
external_marketing_copy -> brand + compliance approval required
medical_or_effect_claim -> compliance approval required
price_or_financing_statement -> founder or finance approval required
store_sop -> operations approval required
employee_script -> operations + compliance approval required
```

Policy fields:

```text
policy_id
target_domain
target_asset_type
risk_level
required_roles
min_approval_count
requires_source_quality_min
requires_benchmark_pass
requires_conflict_check
```

## Formal Knowledge Versions

Official knowledge must never be overwritten in place.

Every approved asset becomes a new version:

```text
knowledge_asset_id
version_id
version_number
status
effective_scope
approved_by
approved_at
source_evidence_summary
supersedes_version_id
created_from_review_task_id
created_from_run_id
```

Allowed statuses:

```text
draft
reviewing
approved
published
superseded
rejected
archived
```

Only `approved` and `published` can be used as authority.

## Database Tables

Stage 1 PostgreSQL tables:

```text
hxy_sources
hxy_source_quality_cards
hxy_documents
hxy_chunks
hxy_claims
hxy_knowledge_assets
hxy_knowledge_versions
hxy_asset_links
hxy_review_tasks
hxy_approval_policies
hxy_harness_specs
hxy_harness_runs
hxy_harness_rounds
hxy_run_artifacts
hxy_state_transitions
hxy_model_calls
hxy_eval_cases
hxy_eval_runs
hxy_permissions
hxy_roles
hxy_audit_logs
```

Key additions over the existing plan:

- `approval_policies`: who must approve what;
- `knowledge_versions`: formal knowledge version history;
- `asset_links`: source/claim/asset/evidence chain;
- `run_artifacts`: generated drafts, parser outputs, reports, screenshots;
- `state_transitions`: every status change;
- `permissions` and `roles`: who can read, review, approve, publish.

## Backend Services

```text
hxy-api
FastAPI API service. Handles auth, task creation, status query, review actions, governance gates.

hxy-worker
Queue worker. Runs parse, source quality, chunking, claim extraction, benchmark, harness rounds.

hxy-scheduler
Lightweight scheduler for periodic scans and retryable jobs. Can later be replaced by Temporal schedules.

hxy-model-gateway
Logical module first, service later. Routes model calls, logs cost, enforces timeout and policy.
```

FastAPI must remain the control plane.

It must not directly parse large files, run long benchmark loops, or hold long-running while loops inside request handlers.

## State Machine

Source lifecycle:

```text
uploaded
-> discovered
-> parsing
-> parsed
-> classified
-> indexed
-> candidate_extracted
-> review_required
-> approved_for_reference
-> promoted_to_knowledge_asset
-> archived
```

Knowledge asset lifecycle:

```text
draft
-> review_required
-> approved
-> published
-> superseded
```

Harness run lifecycle:

```text
created
-> validating
-> running
-> waiting_for_review
-> succeeded
-> blocked
-> failed
-> cancelled
```

Every transition writes `hxy_state_transitions`.

## Harness Runner V2 Role

Harness Runner V2 is not an auto-Agent.

It is:

```text
任务运行器
状态机
审计器
报告生成器
人工复核入口
```

It should support:

- `validate` spec;
- `run` bounded loop;
- `pause`;
- `resume`;
- `cancel`;
- write run state;
- write round reports;
- stop on max rounds;
- stop on repeated failure;
- stop on governance gate violation;
- require review for official knowledge promotion.

## Worker Execution Model

Stage 1:

```text
FastAPI creates job
-> PostgreSQL stores run/task
-> Redis queue receives job id
-> Worker loads job
-> Worker writes artifacts and state transitions
-> FastAPI reads status
```

Do not put full run payloads in Redis. Redis only carries ids and lightweight messages.

## Observability

Minimum required records:

- run id;
- round number;
- command;
- model;
- token/cost;
- input summary;
- output summary;
- changed artifact ids;
- benchmark delta;
- stop reason;
- reviewer action;
- state transitions.

Stage 1 can use structured JSON logs and database rows.

Stage 2 adds Langfuse for model traces.

Stage 3 adds OpenTelemetry traces/metrics/logs.

## Safety Rules

The system must reject or block:

- htops paths;
- private raw knowledge in public commits;
- direct writes to formal knowledge without approval;
- benchmark case hardcoding;
- source material with restricted risk being used as authority;
- process memory being used as authority;
- unversioned official knowledge updates;
- deleting source artifacts without backup and manifest.

## Acceptance Criteria

V2 design is ready for implementation when:

1. the first loop scope is limited to intake, source quality, review queue, and approval;
2. database tables are explicit;
3. state machines are explicit;
4. FastAPI remains control plane;
5. worker/queue handles long tasks;
6. official knowledge is versioned;
7. approval policies exist;
8. no automatic official approval exists;
9. run artifacts and state transitions are auditable;
10. Temporal is deferred until Stage 3.

## Implementation Recommendation

Next implementation plan should be:

```text
HXYOS Knowledge Runtime V1
```

Build in this order:

1. PostgreSQL schema for sources, source quality cards, review tasks, run artifacts, state transitions.
2. Source Quality Gate V1 writes source cards.
3. Review Queue V1 reads high-risk cards and draft assets.
4. Harness Runner `run` command writes durable run state.
5. FastAPI read-only endpoints expose run status and review queue.
6. Back-office page shows run records and review tasks.

Do not implement content publishing or automatic official knowledge import in this phase.
