# HXY Topic Review Decisions

## Objective

Add the manual decision recording layer after topic review packets.

The compiler may create review tasks and editable decision templates. It must not approve, publish, or write official knowledge.

## Product Boundary

```text
topic-review-packets.json
-> topic-review-decisions.stub.json
-> topic-review-decisions.sample.json
-> human-edited topic-review-decisions.json
-> preview validation
-> later manual approval workflow
```

`ready_for_manual_approval` means the packet can enter a later approval preflight. It is not approved knowledge.

## Governance Rules

- `pending` is not a manual decision.
- Allowed manual decisions are `needs_more_evidence`, `revise_draft`, `ready_for_manual_approval`, and `reject`.
- Every non-pending decision needs a reviewer and rationale.
- Generated files keep `official_use_allowed=false`, `publish_allowed=false`, and `write_to_database=false`.
- Preview validation never writes `topic-review-decisions.json`.

## Implementation

- `knowledge_compiler.py` builds decision stub/sample files and validates manual decisions.
- `hxy_knowledge_api.py` exposes read-only workflow status and preview validation endpoints.
- `knowledge.html` shows the backstage file workflow, not approval buttons.

## Verification

- Compiler tests cover pending samples, ready-for-manual-approval validation, invalid publish flags, and compile output files.
- API tests cover workflow projection and preview-only validation.
- Frontend static tests cover the backstage decision file panel.
