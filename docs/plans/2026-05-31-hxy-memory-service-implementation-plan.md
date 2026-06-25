# HXY Memory Service MVP Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a PostgreSQL-backed HXY Memory Service MVP and import current structured HXY assets into durable memory items.

**Architecture:** Add a dedicated `src/hxy-memory/` owner module with types, store, and importer. Keep the current file-based knowledge factory and HXY chat unchanged. Use PostgreSQL as the truth store and stable memory IDs for idempotent imports.

**Tech Stack:** TypeScript, PostgreSQL `pg` query interface, Vitest, existing `tsx` script style.

---

### Task 1: Add HXY Memory Types

**Files:**
- Create: `src/hxy-memory/types.ts`

**Step 1: Define narrow MVP types**

Add union types for `HxyMemoryType`, `HxyMemoryStatus`, and records for memory items, evidence links, transitions, import runs, import input, and import result.

**Step 2: Keep payloads JSON-safe**

Use `Record<string, unknown>` for structured payloads and `unknown[]` only where unavoidable.

### Task 2: Add HXY Memory Store Tests First

**Files:**
- Create: `src/hxy-memory/store.test.ts`
- Create: `src/hxy-memory/store.ts`

**Step 1: Write failing tests**

Tests should prove:
- `initialize()` creates `hxy_memory_items`, `hxy_memory_evidence_links`, `hxy_memory_transitions`, and `hxy_memory_import_runs`.
- `upsertMemoryItem()` and `listMemoryItems()` persist and return a memory item.
- `transitionMemoryStatus()` updates item status and writes a transition.
- `recordImportRun()` writes import run metadata.

**Step 2: Run tests and verify RED**

Run:

```bash
npx vitest run src/hxy-memory/store.test.ts
```

Expected: fail because store does not exist yet.

**Step 3: Implement minimal store**

Implement:
- `initialize()`
- `upsertMemoryItem()`
- `upsertEvidenceLinks()`
- `listMemoryItems()`
- `getMemoryItem()`
- `transitionMemoryStatus()`
- `recordImportRun()`

**Step 4: Run tests and verify GREEN**

Run:

```bash
npx vitest run src/hxy-memory/store.test.ts
```

Expected: pass.

### Task 3: Add Importer Tests First

**Files:**
- Create: `src/hxy-memory/importer.test.ts`
- Create: `src/hxy-memory/importer.ts`

**Step 1: Write failing tests**

Use temp structured files with small JSON fixtures. Tests should prove:
- decisions import as `decision`
- claims needing validation import as derived `hypothesis`
- governance review queue imports as `review_task`
- conflicts import as `conflict`
- pilot validation items import as `validation_task`
- second import is idempotent by stable memory IDs

**Step 2: Run tests and verify RED**

Run:

```bash
npx vitest run src/hxy-memory/importer.test.ts
```

Expected: fail because importer does not exist yet.

**Step 3: Implement importer**

Implement:
- `buildHxyMemoryImportItemsFromStructuredDir()`
- `importHxyMemoryFromStructuredDir()`
- stable ID helpers
- conservative status normalization
- evidence link extraction

**Step 4: Run tests and verify GREEN**

Run:

```bash
npx vitest run src/hxy-memory/importer.test.ts
```

Expected: pass.

### Task 4: Add CLI Script

**Files:**
- Create: `scripts/import-hxy-memory.ts`

**Step 1: Add script**

Parse:
- `--root <path>`
- `--structured-dir <path>`

Use `HETANG_DATABASE_URL` or `DATABASE_URL`, initialize the memory store, run import, print counts.

**Step 2: Type-check**

Run:

```bash
npx tsc --noEmit
```

Expected: pass.

### Task 5: Verify Full Slice

Run:

```bash
npx vitest run src/hxy-memory/store.test.ts src/hxy-memory/importer.test.ts
npx tsc --noEmit
npm test
```

Expected:
- HXY memory tests pass.
- TypeScript passes.
- Existing test suite passes.

Do not run production import until explicitly requested or until using a local/test database.
