# HXY Compliance Action Preflight Design

## Context

HXY now has a reusable compliance workflow gate:

```text
POST /api/operating-brain/workflow-gates/compliance/run
```

It answers whether a piece of copy can continue through content publishing, staff script, or project menu workflows. The next step is to connect that gate to real actions before risky text becomes a draft, training artifact, menu copy, or approved answer card.

## Product Decision

Add compliance preflight to real action boundaries, not just standalone checks.

The first version should cover:

1. Brand/content review: `POST /api/operating-brain/brand-decision/review`
2. Staff script training: `POST /api/operating-brain/training/evaluate`
3. Answer card creation: `POST /api/knowledge/answer-cards`
4. Menu draft preflight: a new dry-run endpoint for future menu save flows

## Boundary

The system may automatically run compliance preflight. It must not automatically approve content, menu copy, staff scripts, or answer cards.

```text
preflight = automatic, deterministic, reversible
approval = human, explicit, versioned
publication = separate action
```

## Behavior

### Brand/content review

`brand-decision/review` should include:

```text
compliance_preflight
can_continue
can_publish=false
```

If compliance blocks the text, the brand review can still be recorded, but the result must clearly say the draft cannot be used until rewritten.

### Staff script training

`training/evaluate` should include compliance preflight for `employee_answer`.

If the answer hits a compliance block:

- `needs_retrain=true`
- any generated correction draft remains a training correction asset, not an approved answer-card candidate
- `training_artifact_gate.can_promote_to_answer_card=false`
- correction points include the compliance reason
- review task remains a training/retrain task, not an answer-card candidate

This prevents a polished but risky employee answer from becoming a draft asset.

### Answer card creation

`/api/knowledge/answer-cards` should hard-block risky approved cards.

Rules:

- `status=approved` and compliance cannot continue -> `400`
- `status=draft` and compliance cannot continue -> allowed, but response includes preflight warning
- `status=archived` -> no publishing implication

This protects the authority layer without making drafting painful.

### Menu draft preflight

There is no mature backend menu draft save API yet. Do not fake one.

Add a dry-run endpoint:

```text
POST /api/operating-brain/menu-draft/preflight
```

It checks project/menu copy with `workflow_type=project_menu` and returns whether a future save should be allowed. It writes nothing.

## Alternatives

### A. Only keep the standalone workflow gate

Simple, but users can bypass it by using training or answer-card actions directly.

### B. Hard-block every risky draft

Too rigid. Drafting should allow unsafe material to be captured and improved, while preventing approved/public use.

### C. Preflight real actions and hard-block authority writes

Selected. It preserves creative drafting while protecting public and approved layers.

## Tests

Backend tests should prove:

- brand decision response includes compliance preflight
- risky staff script cannot create answer card draft
- risky approved answer card is rejected
- risky draft answer card is allowed with warning
- menu preflight writes nothing and returns project-menu compliance result

Frontend tests can be added later for richer display. This iteration is backend-first because the product risk sits at action boundaries.
