# HXY Topic Review Packets Design

## Problem

HXYOS can now compile noisy source material into core operating topics and draft assets. That is useful, but the operator still has to infer what to do next.

The next layer should turn every draft asset into a review packet:

```text
draft asset
-> who reviews it
-> what they must check
-> what decision options are allowed
-> what evidence is missing
-> what it may become after later approval
```

This is an operating workflow layer, not an approval layer.

## Product Rule

Review packets are not official knowledge.

They are task packets for humans to decide whether a draft asset needs more evidence, revision, manual approval, or rejection.

## Scope

V1 builds one deterministic workflow:

```text
topic-draft-assets.json
-> topic-review-packets.json
-> read-only API
-> knowledge workbench display
```

It does not store human decisions yet.

## Data Contract

Each packet uses this shape:

```json
{
  "version": "hxy-topic-review-packet.v1",
  "packet_id": "hxy-topic-review-packet:brand_positioning",
  "asset_id": "hxy-topic-draft:brand_positioning",
  "asset_type": "positioning_card",
  "title": "品牌战略与核爆点定位",
  "priority": "P0",
  "review_owner": "创始人",
  "status": "open",
  "review_questions": [
    "这个判断是否有真实顾客原话支撑？",
    "员工能否不用创始人解释就讲清？"
  ],
  "evidence_gaps": ["补齐目标用户原话"],
  "decision_options": [
    "needs_more_evidence",
    "revise_draft",
    "ready_for_manual_approval",
    "reject"
  ],
  "promotion_target": "approved_positioning_card",
  "blocked_actions": [
    "不能作为对外正式口径",
    "不能写入 approved answer cards",
    "不能自动发布"
  ],
  "source_samples": ["brand.md"],
  "official_use_allowed": false,
  "requires_human_review": true,
  "authority_rule": "review_packets_are_tasks_not_approval"
}
```

## Decision Options

V1 allows exactly four decisions:

- `needs_more_evidence`
- `revise_draft`
- `ready_for_manual_approval`
- `reject`

`ready_for_manual_approval` does not mean approved. It only means the packet can move to a later explicit approval workflow.

## Promotion Targets

Promotion targets are labels, not writes:

| Asset type | Promotion target |
|---|---|
| `positioning_card` | `approved_positioning_card` |
| `script_card` | `approved_script_card` |
| `sop_card` | `approved_sop_card` |
| `risk_card` | `approved_risk_boundary_card` |
| `evidence_task` | `evidence_backlog` |

## Review Questions

Questions should be business-facing:

- Positioning: customer words, employee repeatability, replacement choice, payment reason.
- Script: employee clarity, customer repeatability, compliance-safe wording.
- SOP: owner, step clarity, first-store verification metric.
- Risk: prohibited expression, safe replacement, channel scope.
- Evidence task: which evidence is missing, who collects it, when to review again.

No raw claim IDs, chunk IDs, cluster IDs, or internal extraction fields should appear in the user-facing packet.

## API

Add:

```text
GET /api/operating-brain/knowledge-compiler/topic-review-packets?limit=12
```

It reads `knowledge/wiki/topic-review-packets.json`.

If missing, it returns an empty/missing response with:

```json
{
  "official_use_allowed": false,
  "requires_human_review": true
}
```

## UI

Add a knowledge workbench block after "议题转资产":

```text
复核任务包
谁看
看什么
允许的判断
不能做什么
```

The UI must not include approval buttons. It may show the four decision options as labels only.

## Non-Goals

V1 must not:

- write human decisions;
- approve or publish any knowledge;
- modify answer cards, SOP cards, risk rules, or positioning cards;
- add a new database table;
- expose private raw knowledge in Git;
- touch `/root/htops`;
- introduce franchise/招商 flow.

## Acceptance Criteria

- Compiler writes `topic-review-packets.json`.
- API returns sanitized packets with `official_use_allowed=false`.
- UI shows review packet workflow and hides internal fields.
- `npm test` passes.
- Benchmark pass rate remains at least `0.85`.
- Public release check remains `code_only_private_knowledge_local`.
