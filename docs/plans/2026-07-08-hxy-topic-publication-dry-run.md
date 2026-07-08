# HXY Topic Publication Dry Run

## Objective

Add a read-only dry-run stage after `topic-publication-package`.

This stage prepares the reviewed asset payload shape and validates import readiness, but it must not publish official knowledge, update approved assets, or write to any database.

## Flow

```text
topic-review-decisions.json
-> topic-publication-preflight
-> topic-publication-package
-> topic-publication-dry-run
-> topic-reviewed-assets.json
-> topic-reviewed-assets-import-gate
-> later explicit manual import
```

## Dry-Run Rules

`topic-publication-dry-run` accepts only complete publication candidates and returns draft topic asset payloads.

The response must keep these boundaries:

- `official_use_allowed=false`
- `publish_allowed=false`
- `write_to_formal_store=false`
- `would_write_count=0`

The dry-run payload is a preview for a human-reviewed file. It is not approved knowledge.

## Reviewed File Rules

`topic-reviewed-assets.json` can only be created by explicit manual publication confirmation.

Even after confirmation, reviewed assets stay in `reviewed_pending_import` and still require a separate import gate. The reviewed file write is not a database import and not an official knowledge release.

## Import Gate Rules

`topic-reviewed-assets-import-gate` validates import readiness only.

It checks:

- required reviewed asset fields
- required publication metadata
- duplicate `(topic_key, promotion_target)`
- duplicate `knowledge_version`

It must keep:

- `write_to_database=false`
- `requires_import_confirmation=true`
- `would_import_count=0`

## Boundary

AI can draft, group, route, and prepare publication payloads.

Only humans can approve official knowledge. Reviewed files still need an explicit import step before any formal store can be updated.

## Verification

- Compiler tests cover dry-run payload generation, explicit manual publication confirmation, conflict detection, and clean importable assets.
- API tests cover read-only dry-run and import-gate endpoints.
- Frontend tests cover the backstage dry-run/import-gate panel.
- Full test run: `npm test`
- Benchmark: `knowledge/benchmarks/hxy-brain-benchmark-v1.json`
