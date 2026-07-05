# HXY Ingest Loop V1 Design

## Purpose

HXY Ingest Loop V1 turns new reference materials into governed review artifacts. It does not approve knowledge automatically.

The loop exists to connect the current HXYOS pieces into one executable path:

```text
knowledge/raw/inbox
→ manifest
→ compiler
→ candidate claims
→ review queue
→ answer card drafts
→ human review
→ approved knowledge later
```

This is the first production-style business loop in HXYOS. It should be boring, deterministic, repeatable, and testable before adding Redis, Temporal, Hermes, or Feishu triggers.

## Current Progress Fit

The existing work should be reorganized into five durable tracks:

| Track | Current role | Ingest Loop relationship |
|---|---|---|
| Project foundation | HXY boundary, env, API auth, upload limits | Must remain stable; no `htops` data or service names |
| Knowledge foundation | compiler, benchmark, review queue, wiki artifacts | Ingest Loop V1 orchestrates these |
| Organization memory | workspace events, process memory, decision traces | Used as context only, never authority |
| AI workbench | `brain.html`, `knowledge.html` | Shows loop status and review work |
| Automation loops | loop runner, benchmark loop, future triggers | Ingest Loop becomes the first material loop |

The loop should reuse:

- `knowledge/raw/inbox` as the first material entrance.
- `apps/api/hxy_knowledge/knowledge_compiler.py` for extracts, claims, review queue, drafts, wiki, and graph outputs.
- `apps/api/hxy_knowledge/loop_engine.py` patterns for loop state and stopping rules.
- `knowledge.html` for human review.
- Benchmark reports as a quality gate after compilation.

## Product Boundaries

The loop can automatically:

- discover new files;
- create ingest tasks;
- calculate file hashes and manifest entries;
- run the compiler;
- generate candidate claims;
- generate review queue items;
- generate answer card drafts;
- flag risks, duplicates, and failures;
- write loop state and reports;
- expose status in HXYOS.

The loop must not automatically:

- create `approved` answer cards;
- publish formal brand positioning;
- approve efficacy, medical, pricing, franchise, financing, or investor claims;
- mutate approved knowledge without human review;
- use process memory as authoritative evidence;
- read or write `/root/htops` business data.

## V1 Architecture

V1 should be a deterministic local loop:

```text
scripts/run-hxy-ingest-loop.py
→ apps/api/hxy_knowledge/ingest_loop.py
→ apps/api/hxy_knowledge/knowledge_compiler.py
→ knowledge/runs/ingest-loop-latest/loop-state.json
→ knowledge/reports/ingest-latest.json
→ knowledge/wiki/review-queue.json
```

No queue service is required in V1. The task queue is represented by JSON state files so the loop is easy to inspect, replay, and test.

Later production upgrades can replace the state-file runner with PostgreSQL task rows, Redis/Celery, or Temporal without changing the governance contract.

## State Model

Each material task should move through a narrow state machine:

```text
NEW
DISCOVERED
PARSING
EXTRACTED
SUMMARIZED
CLAIMED
CHECKED
REVIEWING
APPROVED_CANDIDATE
PUBLISHED
REJECTED
ARCHIVED
FAILED
```

V1 should normally stop at `REVIEWING`. `APPROVED_CANDIDATE` and `PUBLISHED` are present to make the lifecycle explicit, but V1 must not auto-enter them.

## Data Contract

An ingest task should include:

```json
{
  "version": "hxy-ingest-task.v1",
  "task_id": "hxy-ingest-task:<hash>",
  "source_path": "knowledge/raw/inbox/example.md",
  "source_type": "file",
  "content_hash": "<sha256>",
  "status": "REVIEWING",
  "official_use_allowed": false,
  "requires_human_review": true,
  "risk_flags": [],
  "artifact_refs": {
    "compiler_report": "knowledge/reports/compiler-latest.json",
    "review_queue": "knowledge/wiki/review-queue.json"
  },
  "created_at": "...",
  "updated_at": "..."
}
```

The loop state should include:

```json
{
  "version": "hxy-ingest-loop-state.v1",
  "run_id": "ingest-loop-latest",
  "status": "review_required",
  "stop_reason": "human_review_required",
  "task_count": 0,
  "review_queue_count": 0,
  "answer_card_draft_count": 0,
  "official_use_allowed": false,
  "authority_rule": "ingest_loop_outputs_are_candidates_until_human_review"
}
```

## Trigger Model

V1 supports only deterministic triggers:

- manual CLI run;
- manual API trigger;
- existing file upload into `knowledge/raw/inbox`;
- later scheduled scan.

V1 explicitly excludes:

- autonomous web crawling;
- AI deciding what to fetch;
- automatic approved publishing;
- background daemon requirements.

## UI Integration

`knowledge.html` should show a small ingest status panel:

```text
资料入库 Loop
最新运行状态
发现资料数
候选 claim 数
待复核数
失败数
最后运行时间
按钮：运行入库 Loop / 刷新状态
```

The UI copy must clearly say:

```text
候选资料不等于正式知识。
Loop 自动停在人工审核。
```

## Success Criteria

V1 is acceptable when:

- new files in `knowledge/raw/inbox` are detected;
- duplicate files are not repeatedly treated as new work;
- compiler artifacts are generated;
- review queue and answer card drafts are produced when content supports them;
- lifecycle status remains candidate/reviewing, not approved;
- loop state is visible through API and UI;
- all loop behavior is covered by tests;
- full project tests still pass.

## Non-Goals

V1 does not implement:

- Feishu/Hermes commands;
- Redis/Celery/Temporal;
- vector index updates;
- full PDF/OCR parsing beyond current compiler capabilities;
- automatic official knowledge publishing;
- Windows real-time sync.

These belong to later phases after the state-file loop proves stable.
