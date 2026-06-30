# HXY Public AI Workspace V1 Design

## Goal

Make HXYOS AI work visible, replayable, governable, and useful to the organization.

The V1 product is not another private chat page. It is a public AI work record that turns questions, answers, corrections, evidence, and follow-up actions into governed organization memory.

## Product Decision

Extend the existing operating brain surface instead of creating a separate workspace page.

The current `apps/admin-web/brain.html` already contains:

- team workbench input
- current operating issues
- source and evidence inspector
- review tasks
- training and correction workflows
- knowledge import and governance links

Adding a new `workspace.html` would duplicate the main product surface and risk becoming another chat UI. V1 should add a workspace event stream to the existing operating brain page and API.

## Product Shape

```text
Public AI Workspace V1 =
  workspace_event model
  + organization-visible event stream
  + visibility levels
  + sensitive-content redaction
  + event replay/search
  + event-to-process-memory route
  + event-to-review-task route
```

The workspace records work. It does not publish truth.

## Core Object

```json
{
  "version": "hxy-workspace-event.v1",
  "event_id": "workspace-event-...",
  "topic": "清泡调补养口径复核",
  "actor": "founder",
  "role": "创始人内部决策",
  "visibility": "public_org",
  "input": "员工这样讲是否有风险？",
  "ai_output": {
    "summary": "存在保证疗效风险，需要改成体验和放松表达。",
    "answer_status": "needs_review"
  },
  "evidence": [],
  "risk_flags": ["efficacy_claim_risk"],
  "corrections": [],
  "generated_tasks": [],
  "memory_action": {
    "type": "process_memory_context_only",
    "allowed_as_authority": false
  },
  "review_action": {
    "type": "create_review_task",
    "required": true
  },
  "created_at": "2026-07-01T00:00:00Z"
}
```

## Visibility Model

| Visibility | Meaning | V1 Behavior |
|---|---|---|
| `public_org` | Normal team-visible AI work | shown in workspace stream |
| `restricted_role` | financing, equity, sensitive management topics | shown only as restricted metadata unless caller has permission |
| `private_draft` | personal draft | not searchable as organization memory and cannot be promoted directly |
| `redacted_public` | public summary of sensitive work | show redacted input/output with sensitive fields removed |

Default visibility is `public_org`.

V1 does not need a full enterprise permission system. It needs deterministic redaction and clear metadata so later RBAC can attach cleanly.

## Redaction Rules

The workspace must redact or restrict content that includes:

- API keys, tokens, passwords, database URLs
- phone numbers and private contact data
- equity structure details
- valuation and financing details
- contracts or legal commitments
- internal system credentials
- private customer health or consumption records

Redaction produces:

```text
original visibility: restricted_role
public mirror: redacted_public
redacted fields: input, ai_output, evidence
visible fields: event_id, topic, role, risk_flags, review_action, created_at
```

## Authority Boundary

Workspace events are episodic memory.

They may:

- help the team replay how a judgment was formed
- create process-memory records
- create review tasks
- create draft answer-card proposals
- explain why an answer is not ready

They must not:

- write approved answer cards
- mutate approved knowledge
- override approved answer cards
- become formal evidence by themselves
- treat process memory as authority

Hard rule:

```text
workspace_event != approved knowledge
workspace_event -> review task -> human approval -> approved knowledge
```

## API Design

Add HXY-owned endpoints:

```text
POST /api/operating-brain/workspace/events
GET  /api/operating-brain/workspace/events
GET  /api/operating-brain/workspace/events/{event_id}
POST /api/operating-brain/workspace/events/{event_id}/review-task
POST /api/operating-brain/workspace/events/{event_id}/process-memory
```

### Create Event

`POST /api/operating-brain/workspace/events`

Input:

```json
{
  "topic": "员工话术风险",
  "actor": "founder",
  "role": "创始人内部决策",
  "visibility": "public_org",
  "input": "泡脚能不能说改善睡眠？",
  "ai_output": {
    "summary": "不能承诺治疗或保证改善。",
    "answer_status": "needs_review"
  },
  "evidence": [],
  "risk_flags": ["medical_claim_risk"],
  "corrections": [],
  "generated_tasks": [],
  "memory_action": {
    "type": "process_memory_context_only"
  },
  "review_action": {
    "type": "create_review_task",
    "required": true
  }
}
```

Output:

```json
{
  "version": "hxy-workspace-event-created.v1",
  "event": {},
  "public_event": {},
  "authority_rule": "workspace_events_are_episodic_memory_not_approved_knowledge"
}
```

### List Events

`GET /api/operating-brain/workspace/events?visibility=public_org&limit=20&q=话术`

Returns latest events with public or redacted payloads. Restricted events should not leak original input/output.

### Create Review Task From Event

`POST /api/operating-brain/workspace/events/{event_id}/review-task`

Creates an existing repository review task. It must include the source workspace event in `payload_json`.

### Create Process Memory From Event

`POST /api/operating-brain/workspace/events/{event_id}/process-memory`

Calls the existing process memory builder. The result remains context-only and promotion still requires review.

## Storage Design

V1 can use a JSONL-backed local store before adding a database table.

Recommended path:

```text
knowledge/workspace/events.jsonl
```

Reasons:

- simple to test
- no migration needed for first product cut
- keeps HXY data inside `/root/hxy`
- matches current file-backed compiler and benchmark artifacts

The store should be wrapped in a Python module so PostgreSQL can replace it later without changing API handlers.

Proposed module:

```text
apps/api/hxy_knowledge/workspace_events.py
```

Main functions:

```python
create_workspace_event(payload, store_path, now)
list_workspace_events(store_path, limit, query, visibility)
get_workspace_event(store_path, event_id)
redact_workspace_event(event)
classify_workspace_visibility(event)
```

## UI Design

Modify `apps/admin-web/brain.html`.

Add a section near the current operating issue queue:

```text
公共 AI 工作间
  最新 AI 工作
  可见性
  风险标签
  复核状态
  记忆动作
```

Each event row should show:

- topic
- role
- visibility badge
- one-line AI summary
- risk flags
- review action
- created time
- buttons:
  - 查看
  - 转复核
  - 记为过程记忆

The primary page remains answer/workflow first. The event stream is a persistence and learning layer, not a hero chat feed.

## Integration With Existing Workflows

When `/api/operating-brain/workbench-intake` classifies an input, the frontend can create a workspace event after an answer/training/intake result is produced.

V1 integration path:

1. User submits work in `brain.html`.
2. Existing workflow returns answer/training/intake result.
3. Frontend calls `POST /api/operating-brain/workspace/events`.
4. Event appears in public workspace stream.
5. User can create review task or process memory from the event.

This avoids changing answer generation first and reduces regression risk.

## Testing Strategy

Backend tests:

- creating an event writes JSONL
- listing events returns newest first
- restricted events do not expose original input/output in public list
- `private_draft` events cannot be routed directly to process-memory promotion
- review-task route creates review tasks but does not approve knowledge
- process-memory route returns context-only boundary

Frontend tests:

- `brain.html` contains public workspace section
- event stream calls `/api/operating-brain/workspace/events`
- UI exposes visibility/risk/review/memory labels
- page does not claim workspace events are official knowledge

Regression tests:

- approved answer cards are not mutated
- process memory remains non-authoritative
- no `/root/htops` path or `htops-*` service name is introduced

## Non-Goals

V1 does not build:

- full Slack/River clone
- full Feishu integration
- full RBAC
- customer data memory
- financing room permissions
- approved knowledge publishing UI
- autonomous Agent that edits core knowledge

## Acceptance Criteria

- Public AI work can be recorded and replayed.
- Sensitive work is restricted or redacted.
- Every event clearly says it is not approved knowledge.
- Events can create review tasks.
- Events can create process-memory records as context-only memory.
- No event route can create or mutate approved knowledge.
- Existing tests continue to pass.
