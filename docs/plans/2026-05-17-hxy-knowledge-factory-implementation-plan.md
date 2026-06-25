# HXY Knowledge Factory Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a durable HXY project knowledge factory for classification, cleaning, manifest storage, quality checks, and filtered retrieval.

**Architecture:** Extend the existing personal knowledge pipeline instead of creating a second runtime. Add HXY-specific taxonomy, manifest, normalized text output, and doctor reporting in owner modules, then expose lightweight filters through the existing personal knowledge API.

**Tech Stack:** TypeScript, Node.js `fs/path/crypto`, existing `src/personal-knowledge.ts`, FastAPI `api/main.py`, Vitest, Python unittest.

---

### Task 1: Add HXY Taxonomy Model

**Files:**
- Create: `src/hxy-knowledge-taxonomy.ts`
- Test: `src/hxy-knowledge-taxonomy.test.ts`

**Step 1: Write the failing test**

Create tests for:

- `classifyHxyKnowledgeAsset` returns `brand/preparation` for a path/title containing 品牌 and 筹备.
- It returns `store_model/pilot` for content containing 小店模型 and 试点.
- It falls back to `external/evergreen` with low confidence when there is no signal.
- It records classification reasons.

**Step 2: Run test to verify it fails**

```bash
npx vitest run src/hxy-knowledge-taxonomy.test.ts
```

Expected: FAIL because module does not exist.

**Step 3: Implement taxonomy**

Create:

- `HxyKnowledgeDomainKey`
- `HxyProjectStageKey`
- `HXY_KNOWLEDGE_DOMAINS`
- `HXY_PROJECT_STAGES`
- `classifyHxyKnowledgeAsset(params)`

Use deterministic scoring from path, file name, title, and text preview. Do not call an LLM.

**Step 4: Run test to verify it passes**

```bash
npx vitest run src/hxy-knowledge-taxonomy.test.ts
```

Expected: PASS.

**Step 5: Commit**

```bash
git add src/hxy-knowledge-taxonomy.ts src/hxy-knowledge-taxonomy.test.ts
git commit -m "feat: add hxy knowledge taxonomy"
```

### Task 2: Extend Personal Knowledge Index Metadata

**Files:**
- Modify: `src/personal-knowledge.ts`
- Test: `src/personal-knowledge.test.ts`

**Step 1: Write the failing test**

Add a test that builds an HXY index from a temp raw directory and asserts:

- `sources[0].assetId` exists.
- `sources[0].knowledgeDomain === "brand"` for a brand file.
- `sources[0].projectStage === "preparation"` when path/title indicates preparation.
- chunks inherit the same metadata.
- existing non-HXY domains still work without requiring those fields.

**Step 2: Run test to verify it fails**

```bash
npx vitest run src/personal-knowledge.test.ts
```

Expected: FAIL because metadata fields do not exist.

**Step 3: Implement metadata extension**

Add optional fields to `PersonalKnowledgeSource` and `PersonalKnowledgeChunk`:

- `assetId?: string`
- `contentSha1?: string`
- `knowledgeDomain?: string`
- `secondaryKnowledgeDomains?: string[]`
- `projectStage?: string`
- `classificationConfidence?: number`
- `classificationReasons?: string[]`

When `params.domain === "hxy"`, call taxonomy classifier and attach fields to source/chunks. Preserve old JSON compatibility.

**Step 4: Run tests**

```bash
npx vitest run src/personal-knowledge.test.ts src/hxy-knowledge-taxonomy.test.ts
```

Expected: PASS.

**Step 5: Commit**

```bash
git add src/personal-knowledge.ts src/personal-knowledge.test.ts
git commit -m "feat: annotate hxy knowledge index metadata"
```

### Task 3: Build Manifest and Normalized Text Output

**Files:**
- Create: `src/hxy-knowledge-factory.ts`
- Create: `src/hxy-knowledge-factory.test.ts`
- Create: `scripts/build-hxy-knowledge-factory.ts`

**Step 1: Write the failing test**

Test a temp HXY raw directory with:

- one supported markdown file.
- one unsupported image file.
- one duplicate supported file.

Assert the factory writes/returns:

- `manifest.version === "hxy-knowledge-manifest.v1"`
- supported asset status is `indexed` or `normalized`.
- normalized markdown path is under `knowledge/hxy/normalized/<domain>/<stage>/`.
- unsupported file status is `skipped` with reason.
- duplicate warning is present.

**Step 2: Run test to verify it fails**

```bash
npx vitest run src/hxy-knowledge-factory.test.ts
```

Expected: FAIL because module does not exist.

**Step 3: Implement factory**

Implement:

- `buildHxyKnowledgeFactory(params)`
- `writeHxyKnowledgeFactoryOutputs(output, paths)`
- manifest type definitions.
- normalized markdown writer using sanitized filenames.
- doctor summary builder inside the same output.

The factory can reuse `buildPersonalKnowledgeIndex` concepts, but should not duplicate heavy parsing logic when a helper can be extracted safely.

**Step 4: Add CLI**

`scripts/build-hxy-knowledge-factory.ts` should accept:

```text
--root-dir
--raw-dir
--output-dir
--chunk-size
--overlap
```

Default paths are under `knowledge/hxy`.

**Step 5: Run tests**

```bash
npx vitest run src/hxy-knowledge-factory.test.ts src/personal-knowledge.test.ts src/hxy-knowledge-taxonomy.test.ts
```

Expected: PASS.

**Step 6: Commit**

```bash
git add src/hxy-knowledge-factory.ts src/hxy-knowledge-factory.test.ts scripts/build-hxy-knowledge-factory.ts
git commit -m "feat: add hxy knowledge factory manifest"
```

### Task 4: Add Knowledge Doctor Report

**Files:**
- Modify: `src/hxy-knowledge-factory.ts`
- Test: `src/hxy-knowledge-factory.test.ts`

**Step 1: Write the failing test**

Add assertions for `reports/knowledge-doctor.json` content:

- total assets.
- indexed count.
- skipped count.
- failed count.
- low confidence count.
- coverage matrix by domain/stage.
- impact messages when a domain has no indexed assets.

**Step 2: Run test to verify it fails**

```bash
npx vitest run src/hxy-knowledge-factory.test.ts
```

Expected: FAIL on missing doctor fields.

**Step 3: Implement doctor report**

Implement `buildHxyKnowledgeDoctorReport(manifest, taxonomy)` and write to:

```text
knowledge/hxy/reports/knowledge-doctor.json
```

**Step 4: Run tests**

```bash
npx vitest run src/hxy-knowledge-factory.test.ts
```

Expected: PASS.

**Step 5: Commit**

```bash
git add src/hxy-knowledge-factory.ts src/hxy-knowledge-factory.test.ts
git commit -m "feat: add hxy knowledge doctor report"
```

### Task 5: Add API Filters for HXY Chat

**Files:**
- Modify: `api/main.py`
- Test: `api/test_main.py`

**Step 1: Write the failing test**

Add tests that:

- `search_personal_knowledge_index` filters by `knowledge_domain` and `project_stage` when provided.
- `PersonalKnowledgeChatRequest` accepts optional `knowledge_domain` and `project_stage`.
- HXY chat passes filters to search.

**Step 2: Run test to verify it fails**

```bash
python -m unittest api.test_main.MainTests
```

Expected: FAIL because request/filter fields do not exist.

**Step 3: Implement API filter fields**

Add optional fields:

- `knowledge_domain: str | None = None`
- `project_stage: str | None = None`

Update `search_personal_knowledge_index` to skip chunks whose metadata does not match filters. Keep current callers compatible.

**Step 4: Run API tests**

```bash
python -m unittest api.test_main.MainTests
```

Expected: PASS.

**Step 5: Commit**

```bash
git add api/main.py api/test_main.py
git commit -m "feat: filter hxy knowledge chat by taxonomy"
```

### Task 6: Generate Current HXY Factory Outputs

**Files:**
- Generate/update local runtime artifacts:
  - `knowledge/hxy/taxonomy.json`
  - `knowledge/hxy/manifest.json`
  - `knowledge/hxy/reports/knowledge-doctor.json`
  - `knowledge/hxy/normalized/**`
  - `knowledge/hxy/index.json`

**Step 1: Run factory build**

```bash
node --import tsx scripts/build-hxy-knowledge-factory.ts
```

Expected: writes manifest, taxonomy, normalized files, report, and index summary.

**Step 2: Rebuild structured knowledge**

```bash
node --import tsx scripts/build-hxy-structured-knowledge.ts
node --import tsx scripts/build-hxy-knowledge-governance.ts
```

Expected: structured outputs and governance report update successfully.

**Step 3: Verify sources endpoint**

```bash
curl -fsS 'http://127.0.0.1:18890/api/v1/personal-knowledge/sources?domain=hxy' | head -c 1000
```

Expected: endpoint returns HXY source/chunk counts.

**Step 4: Do not commit raw runtime artifacts unless explicitly needed**

Check `.gitignore` and project policy. If `knowledge/` is intentionally local-only, do not add generated outputs. Commit only source/test/docs changes unless user asks to version artifacts.

### Task 7: Final Verification

**Files:**
- No edits unless fixes are required.

**Step 1: Run targeted TypeScript tests**

```bash
npx vitest run src/hxy-knowledge-taxonomy.test.ts src/personal-knowledge.test.ts src/hxy-knowledge-factory.test.ts
```

Expected: PASS.

**Step 2: Run API tests**

```bash
python -m unittest api.test_main.MainTests
```

Expected: PASS.

**Step 3: Run typecheck**

```bash
npx tsc --noEmit
```

Expected: PASS.

**Step 4: Check git boundary**

```bash
git status --short
git diff --cached --name-only
```

Expected: staged files only include intended source/test/docs files. No raw books, normalized local outputs, tmp files, `.env`, or WeCom scripts are staged.
