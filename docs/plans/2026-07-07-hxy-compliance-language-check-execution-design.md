# HXY Compliance Language Check Execution Design

## Goal

Build the first executable HXYOS product-object loop: a deterministic compliance-language Skill that checks whether external-facing copy can be used, should be revised, or must be blocked.

This turns the product object layer from a static catalog into a working control surface while preserving the core governance boundary: Skill output is not official knowledge and cannot publish approved answer cards.

## Scope

In scope:

- Add one executable Skill endpoint for `hxy-compliance-language-check`.
- Use existing HXY-owned brand risk rules as the rule source.
- Return business-facing decisions: `allow`, `revise`, or `block`.
- Return source labels without absolute local paths.
- Add a minimal admin execution box to `knowledge.html`.
- Keep all outputs read-only and non-official.

Out of scope:

- No model call in V1.
- No automatic approved answer-card publication.
- No database migration.
- No VI/SI design changes.
- No htops dependency.
- No public release of private brand source material.

## Product Behavior

The user pastes a sentence or paragraph prepared for an external channel, chooses a channel, and runs the check.

The system returns:

- whether the copy can be used;
- the risk level;
- which risk gates were hit;
- why the system made that decision;
- a safer rewrite suggestion;
- which rule source labels informed the decision;
- explicit authority boundaries.

Example response shape:

```json
{
  "version": "hxy-compliance-language-check-result.v1",
  "skill_id": "hxy-compliance-language-check",
  "decision": "block",
  "risk_level": "p0",
  "hit_gates": ["medical_claim"],
  "can_publish": false,
  "official_use_allowed": false,
  "review_required": true,
  "rewrite_suggestion": "可以改成：草本现煮，泡着舒服，适合下班后放松。",
  "evidence": [
    {
      "rule_name": "医疗表达禁用",
      "source": "荷小悦禁用表达库.md"
    }
  ]
}
```

## Rules

V1 is deterministic and uses existing `load_brand_risk_rules`.

Decision mapping:

- `block`: any high-risk medical or guaranteed-effect hit.
- `revise`: warning-level overstatement or weak-risk hit.
- `allow`: no rule hits.

Risk gate mapping:

- `medical_claim`: treatment, diagnosis, cure, disease, medicalized claims.
- `guaranteed_effect`: guaranteed result, immediate effect, fixed timeline promise.
- `overstatement`: absolute superiority, anti-aging, beauty-medical exaggeration.

The exact terms come from existing HXY compliance material and fallback rules. The execution endpoint must not expose absolute paths such as `/root/hxy`.

## API Design

Endpoint:

```text
POST /api/operating-brain/skills/hxy-compliance-language-check/run
```

Request:

```json
{
  "text": "泡脚可以治疗失眠",
  "channel": "朋友圈",
  "audience": "customer"
}
```

Response requirements:

- `decision` is one of `allow`, `revise`, `block`.
- `risk_level` is one of `none`, `low`, `medium`, `high`, `p0`.
- `hit_gates` is a business risk-gate list.
- `can_publish` is always `false`.
- `official_use_allowed` is always `false`.
- `review_required` is `true` unless the decision is `allow`.
- `evidence.source` uses file names or relative labels only.
- The response never includes `chunk_id`, `cluster_member_count`, `sample_claims`, or absolute paths.

## Frontend Design

Add a restrained panel to `apps/admin-web/knowledge.html` near the product object layer:

- title: `对外话语检查`;
- textarea for text;
- select for channel;
- button: `检查`;
- result block showing:
  - `可以发`, `建议改`, or `不要发`;
  - hit risk gates;
  - rewrite suggestion;
  - rule source labels.

The panel is admin-side only. It does not appear in `frontdesk.html`, and it does not include approval or publishing controls.

## Testing

Backend tests:

- `泡脚能治疗失眠` returns `block` and includes `medical_claim`.
- `一周保证见效` returns `block` and includes `guaranteed_effect`.
- `草本现煮，泡着舒服` returns `allow`.
- Response never includes absolute `/root/hxy`.
- Response always has `official_use_allowed: false` and `can_publish: false`.

Frontend tests:

- `knowledge.html` contains the execution panel.
- It calls `/api/operating-brain/skills/hxy-compliance-language-check/run`.
- It renders business labels, not technical internals.
- It does not expose approval controls for this Skill.

## Acceptance Criteria

- Full `npm test` passes.
- The new endpoint works in the running HXY knowledge API.
- The execution result is useful without showing internal compiler artifacts.
- No model token is used in V1.
- No automatic knowledge approval is introduced.
