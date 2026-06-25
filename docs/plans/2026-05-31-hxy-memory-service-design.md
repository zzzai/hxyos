# HXY Memory Service MVP Design

## Business Problem

HXY already has file-based project knowledge: raw assets, normalized text, structured claims, governance reports, OSI contracts, a decision log, brand deliverables, and validation matrices. That is enough for retrieval and first-pass reasoning, but it is not yet a durable company memory system. Decisions, hypotheses, experiments, tasks, insights, and evidence cannot be versioned, reviewed, or updated as operational feedback arrives.

The first improvement should turn the current structured HXY JSON assets into a PostgreSQL-backed memory layer without changing the runtime query path or creating a second ontology runtime.

## Options

### Option A: Keep Everything File-Based

Use `knowledge/hxy/structured/*.json` as the only source of truth and regenerate files whenever new information arrives.

Pros:
- Lowest implementation cost.
- Matches the current knowledge factory.
- Easy to inspect manually.

Cons:
- Weak status transitions and review workflow.
- Hard to track updates, feedback, and version history.
- Poor fit for task closure, validation evidence, and future proactive reminders.

### Option B: Add a Bounded PostgreSQL Memory Service

Add an HXY-owned Memory Service with PostgreSQL tables for memory items, evidence links, transitions, and import runs. Import existing JSON assets as the initial source. Keep file assets as upstream artifacts for now.

Pros:
- Gives decisions, hypotheses, tasks, and evidence durable identities and statuses.
- Supports incremental review and feedback without rewriting all JSON files.
- Fits the repo direction: PostgreSQL truth store, modular monolith, Ontos-lite.
- Does not disturb current HXY question answering.

Cons:
- Requires schema and tests.
- Needs import idempotency and provenance discipline.

### Option C: Build Full Company Memory OS Now

Add a large platform: Memory Service, task UI, visual sidecar generator, proactive push, feedback tracking, and sample store data ingestion in one pass.

Pros:
- Closer to the long-term vision.

Cons:
- Too broad and risky.
- Would blur owner boundaries and likely expand runtime responsibilities.
- Hard to verify safely.

## Recommendation

Choose Option B.

The first slice should be a bounded Memory Service MVP:

```text
knowledge/hxy/structured/*.json
  -> HxyMemoryImporter
  -> HxyMemoryStore(PostgreSQL)
  -> query/update APIs for later HXY app and agents
```

This moves the project from static files to durable memory while preserving the current knowledge factory and HXY chat behavior.

## Scope

In scope:
- Create a dedicated `src/hxy-memory/` owner module.
- Create PostgreSQL tables through a store initializer.
- Import current HXY structured assets into memory items.
- Support list/query by type/status/stage and status transitions.
- Record import runs and transition history.
- Add tests for schema, idempotent import, and status transitions.
- Add a CLI script for local import.

Out of scope for this slice:
- Automatic image-to-vision sidecar generation.
- Proactive push.
- UI screens.
- Runtime routing changes.
- Store operating data ingestion.
- Replacing current knowledge factory or HXY chat.

## Data Model

### `hxy_memory_items`

Canonical memory item table.

Core columns:
- `memory_id TEXT PRIMARY KEY`
- `memory_type TEXT NOT NULL`
- `title TEXT NOT NULL`
- `body TEXT NOT NULL`
- `project_stage TEXT`
- `status TEXT NOT NULL`
- `confidence DOUBLE PRECISION`
- `version TEXT NOT NULL`
- `source_kind TEXT NOT NULL`
- `source_path TEXT`
- `source_object_id TEXT`
- `payload_json JSONB NOT NULL`
- `created_at TIMESTAMPTZ NOT NULL`
- `updated_at TIMESTAMPTZ NOT NULL`
- `review_at TIMESTAMPTZ`

Memory types for MVP:
- `claim`
- `decision`
- `hypothesis`
- `validation_task`
- `review_task`
- `conflict`
- `insight`

Statuses for MVP:
- `draft`
- `current_candidate`
- `confirmed`
- `validated`
- `deprecated`
- `conflicted`
- `needs_review`
- `open`
- `closed`

### `hxy_memory_evidence_links`

Evidence association table.

Columns:
- `memory_id TEXT NOT NULL`
- `evidence_id TEXT NOT NULL`
- `source_path TEXT`
- `snippet TEXT`
- `payload_json JSONB NOT NULL`
- Primary key: `(memory_id, evidence_id)`

### `hxy_memory_transitions`

Append-only status transition table.

Columns:
- `transition_id BIGSERIAL PRIMARY KEY`
- `memory_id TEXT NOT NULL`
- `from_status TEXT`
- `to_status TEXT NOT NULL`
- `reason TEXT`
- `actor TEXT`
- `payload_json JSONB NOT NULL`
- `created_at TIMESTAMPTZ NOT NULL`

### `hxy_memory_import_runs`

Import observability table.

Columns:
- `import_id TEXT PRIMARY KEY`
- `source_dir TEXT NOT NULL`
- `started_at TIMESTAMPTZ NOT NULL`
- `finished_at TIMESTAMPTZ`
- `status TEXT NOT NULL`
- `item_count INTEGER NOT NULL DEFAULT 0`
- `payload_json JSONB NOT NULL`

## Import Mapping

Initial import reads:
- `claims.json` -> `claim`
- `decision-log.json` -> `decision`
- `governance-report.json.review_queue` -> `review_task`
- `governance-report.json.conflicts` and `osi-contract.json.governance.open_review_items` -> `conflict`
- `pilot-validation-matrix.json.items` -> `validation_task`

Hypotheses are derived conservatively from claims where `needs_validation = true`, especially claim types related to product, store model, finance, validation metrics, and positioning. Each derived hypothesis keeps the original claim payload and evidence IDs.

Import is idempotent by stable `memory_id`. Re-running the importer updates body, payload, evidence links, confidence, stage, and `updated_at`, but does not delete memory rows that no longer appear.

## Module Boundaries

New owner modules:
- `src/hxy-memory/types.ts`
- `src/hxy-memory/store.ts`
- `src/hxy-memory/importer.ts`

Script:
- `scripts/import-hxy-memory.ts`

Do not add responsibilities to `src/runtime.ts`. Later API wiring can call the owner module directly.

## Error Handling

- Missing optional files are skipped and recorded in import payload.
- Invalid JSON fails the import before writing partial data.
- Unknown status values are normalized to `needs_review`.
- Import writes are upserts, so interrupted reruns are safe.

## Verification

Targeted verification:

```bash
npx vitest run src/hxy-memory/store.test.ts src/hxy-memory/importer.test.ts
npx tsc --noEmit
```

Broader verification before completion:

```bash
npm test
```

## Rollout

1. Land Memory Service tables and tests.
2. Run local import from `knowledge/hxy/structured`.
3. Inspect imported counts and sample records.
4. Later slice: add read API and project brain UI.
5. Later slice: add vision sidecar generator and feedback-driven memory updates.
