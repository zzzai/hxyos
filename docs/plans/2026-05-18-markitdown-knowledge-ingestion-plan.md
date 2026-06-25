# MarkItDown Knowledge Ingestion Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add MarkItDown as the preferred local-file conversion layer for uploaded knowledge files, while keeping the existing parsers as fallback.

**Architecture:** Integrate at the ingestion/normalization layer only. `build-personal-knowledge-index.ts` and `build-hxy-knowledge-factory.ts` call a shared MarkItDown adapter before legacy parsing; generated indexes and HXY manifests record parser metadata. Project memory, decision log, and active truth state remain unchanged.

**Tech Stack:** TypeScript, Node.js `child_process`, existing personal/HXY knowledge builders, FastAPI upload allowlist, Vitest.

---

### Task 1: Add MarkItDown Adapter

**Files:**
- Create: `src/markitdown-converter.ts`
- Test: `src/markitdown-converter.test.ts`

**Behavior:**
- Run `markitdown <file>` for local files.
- Return Markdown text plus parser metadata when conversion succeeds.
- If MarkItDown is disabled or fails, call the legacy reader and return a warning.
- Allow env overrides: `HETANG_MARKITDOWN_ENABLED`, `HETANG_MARKITDOWN_BIN`, `HETANG_MARKITDOWN_TIMEOUT_SECONDS`.

**Verification:**

```bash
npx vitest run src/markitdown-converter.test.ts
```

### Task 2: Preserve Parser Metadata in Knowledge Index

**Files:**
- Modify: `src/personal-knowledge.ts`
- Test: `src/personal-knowledge.test.ts`

**Behavior:**
- `readSourceText` may return either plain text or `{ text, parser, parserWarnings }`.
- Sources and chunks preserve parser metadata.
- Existing string-return readers remain compatible.

**Verification:**

```bash
npx vitest run src/personal-knowledge.test.ts src/markitdown-converter.test.ts
```

### Task 3: Use MarkItDown in Build Scripts

**Files:**
- Modify: `scripts/build-personal-knowledge-index.ts`
- Modify: `scripts/build-hxy-knowledge-factory.ts`

**Behavior:**
- Prefer MarkItDown for supported uploads.
- Fall back to existing `pdftotext`, `pandoc`, `unzip`, or UTF-8 text parsing.
- For MarkItDown-only binary formats, fail extraction if MarkItDown is unavailable rather than indexing binary garbage.

**Verification:**

```bash
npx tsc --noEmit
```

### Task 4: Expose More Upload Formats Safely

**Files:**
- Modify: `src/personal-knowledge.ts`
- Modify: `api/main.py`
- Modify: `api/requirements.txt`
- Modify: `src/hxy-knowledge-factory.ts`

**Behavior:**
- Allow MarkItDown-supported knowledge uploads such as Excel, CSV, JSON, XML, ZIP, common images, and common audio files.
- Record parser metadata in HXY manifest assets.
- Add `markitdown[all]` to API requirements for deployment.

**Verification:**

```bash
npx vitest run src/markitdown-converter.test.ts src/personal-knowledge.test.ts src/hxy-knowledge-factory.test.ts
npx tsc --noEmit
```
