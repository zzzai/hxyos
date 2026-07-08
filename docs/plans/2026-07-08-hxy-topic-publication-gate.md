# HXY Topic Publication Gate

## Objective

Add a formal publication gate after `topic-review-decisions.json`.

This gate does not publish official knowledge. It checks whether a `ready_for_manual_approval` decision has enough publication metadata to become a manual publication candidate.

## Required Metadata

Every `ready_for_manual_approval` item must include:

- `approver`
- `approved_at`
- `knowledge_version`
- `effective_scope`
- `source_evidence_summary`

If any field is missing, the item stays blocked.

## Flow

```text
topic-review-decisions.json
-> topic-publication-preflight
-> topic-publication-package
-> pending_manual_publication candidates
-> later explicit manual publication/import gate
```

## Boundary

- The preflight only checks decisions and metadata.
- The package only contains `pending_manual_publication` candidates.
- `official_use_allowed=false`, `publish_allowed=false`, and `write_to_database=false` remain enforced.
- No approved knowledge file or database row is written by this gate.

## Verification

- Compiler tests cover missing metadata, complete metadata, and candidate package output.
- API tests cover read-only preflight and candidate package endpoints.
- Frontend tests cover the backstage publication gate panel without publish actions.
