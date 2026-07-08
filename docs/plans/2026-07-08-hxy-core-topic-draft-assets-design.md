# HXY Core Topic Draft Assets Design

## Problem

The knowledge compiler can now reduce noisy candidate claims into a small set of HXY core operating topics. That fixes the review surface, but it does not yet create a usable operating workflow.

The next product step is not more claim review. It is turning each core topic into a concrete draft asset that a human can inspect, edit, approve, reject, or send back for more evidence.

## Product Principle

```text
machine extracts many claims
-> compiler groups them into core decision topics
-> system drafts the next business asset
-> human reviews the asset
-> only approved assets can become authority
```

Core topics are review objects. Draft assets are also review objects.

Neither is approved knowledge.

## Scope

V1 supports one workflow:

```text
core_decision_topic -> draft decision asset -> needs_review
```

The system may produce:

- `positioning_card`: brand positioning or nuclear-point decision draft.
- `script_card`: staff/customer-facing language draft.
- `sop_card`: first-store operating procedure draft.
- `risk_card`: compliance or prohibited-expression boundary draft.
- `evidence_task`: missing-evidence task when the topic is not ready for a card.

## Non-Goals

V1 must not:

- automatically approve knowledge;
- write `approved` answer cards;
- publish brand, product, SOP, or compliance rules;
- expose raw claims, chunk IDs, cluster IDs, or internal triage fields in the front-stage UI;
- change VI/SI work;
- add招商 or franchise workflows;
- write HXY data into htops.

## Decision Rule

The draft type is chosen from the topic key:

| Topic key | Default draft asset |
|---|---|
| `brand_positioning` | `positioning_card` |
| `customer_evidence` | `evidence_task` |
| `product_system` | `script_card` |
| `employee_script` | `script_card` |
| `risk_boundary` | `risk_card` |
| `first_store_operations` | `sop_card` |

If a topic has fewer than two evidence items, V1 should prefer `evidence_task` unless the topic is `risk_boundary`.

Risk topics always remain P0 and always require human review.

## Data Contract

A draft asset uses this public shape:

```json
{
  "version": "hxy-topic-draft-asset.v1",
  "asset_id": "hxy-topic-draft:brand_positioning",
  "topic_id": "hxy-core-topic:brand_positioning",
  "topic_key": "brand_positioning",
  "asset_type": "positioning_card",
  "title": "品牌战略与核爆点定位",
  "status": "needs_review",
  "priority": "P0",
  "review_owner": "创始人",
  "decision_question": "这个判断现在能不能作为首店开业和对外口径的依据？",
  "draft": {
    "summary": "当前应先判断定位是否能被顾客理解、员工讲清、经营数据验证。",
    "recommended_use": "仅供内部复核，不可作为对外正式口径。",
    "evidence_gaps": ["补齐目标用户原话", "完成复述测试"],
    "next_actions": ["完成 8-12 个目标用户访谈", "把话术转成员工复述测试"]
  },
  "source_samples": ["source.md"],
  "official_use_allowed": false,
  "requires_human_review": true,
  "authority_rule": "draft_assets_are_not_approved_knowledge"
}
```

## Storage

V1 writes draft assets to:

```text
knowledge/wiki/topic-draft-assets.json
```

This path is under local knowledge output. It is not expected to be committed with private HXY knowledge.

## API

Add a read API:

```text
GET /api/operating-brain/knowledge-compiler/topic-draft-assets?limit=12
```

It returns existing `topic-draft-assets.json` when present.

If the file is missing but `core-decision-topics.json` exists, it may build a preview response in memory. The response must still say:

```json
{
  "official_use_allowed": false,
  "requires_human_review": true
}
```

V1 does not need a write/approval API.

The compiler should write `topic-draft-assets.json` during `compile_directory`, after core decision topics are created.

## Admin UI

`knowledge.html` should add one workflow block near the core operating topics:

```text
核心经营议题
-> 建议沉淀成什么资产
-> 缺什么证据
-> 下一步动作
-> 待人工复核
```

The UI must show business language only:

- asset type label;
- status `待复核`;
- evidence gaps;
- next actions;
- review owner.

It must not show raw claim text as the main object.

## Testing

Required tests:

1. Compiler converts core topics into topic draft assets.
2. Risk boundary topics become `risk_card`, P0, `needs_review`, never approved.
3. Low-evidence non-risk topics become `evidence_task`.
4. API returns draft assets with `official_use_allowed=false`.
5. Knowledge page renders the workflow labels and hides raw claim/internal fields.
6. Existing benchmark remains at or above `0.85`.

## Acceptance Criteria

The feature is acceptable when:

- `npm test` passes;
- HXY brain benchmark pass rate is at least `0.85`;
- no private knowledge files are committed;
- public release preflight still reports `code_only_private_knowledge_local`;
- the UI presents a small review workflow, not a claim queue.
