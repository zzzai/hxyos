# HXYOS Authority-Aware Answer V1 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Turn the HXYOS conversation into a useful, governed answer surface by adding semantic entry intent, source-level authority, three answer modes, a small local Brand Constitution, and a ten-question acceptance benchmark without creating a per-claim review queue.

**Architecture:** Keep approved answer cards as the only authoritative external/team standard. Add source-level authority metadata to distinguish official internal sources, working internal material, and external reference material. Answers expose one of `formal`, `working`, or `reference` modes with evidence and usage boundaries; process memory remains context-only. The model router handles semantic classification and evidence-constrained synthesis, while deterministic gates remain the final authority for risk and publication.

**Tech Stack:** Python 3.12, FastAPI, PostgreSQL, existing HXY answer pipeline, Qwen model router, pytest, existing JSON benchmark runner, React/Vite product shell.

---

### Task 1: Define authority and answer-mode contracts

**Files:**
- Modify: `apps/api/hxy_knowledge/answer_pipeline.py`
- Modify: `apps/api/hxy_knowledge/reliability.py`
- Modify: `apps/api/hxy_knowledge/answer_service.py`
- Test: `tests/test_hxy_answer_authority.py`

**Step 1: Write failing tests**

Cover these behaviors:

- approved answer card returns `formal`, `authority_source=approved_answer_card`, and no model override;
- corroborated internal evidence returns `working`, citations, and an internal-use boundary;
- external/reference-only evidence returns `reference`, never `formal`, and cannot be used as an official answer;
- process-memory evidence is excluded from authority and can only appear as context metadata;
- high-risk or insufficient evidence remains `needs_review` regardless of model confidence.

**Step 2: Run the focused tests and verify they fail**

Run:

```bash
.venv/bin/pytest tests/test_hxy_answer_authority.py -q
```

Expected: failure because the answer mode and authority fields do not exist.

**Step 3: Implement the smallest contract**

Add explicit fields to the answer envelope:

```text
answer_mode: formal | working | reference
authority_source: approved_answer_card | official_internal | internal_material | external_reference | none
usage_boundary: team_standard | internal_working | reference_only | review_required
```

Do not change the meaning of `process_memory`; it cannot satisfy an evidence or authority gate.

**Step 4: Run focused and regression tests**

Run the new test and the existing answer pipeline tests. Confirm approved cards still bypass model generation.

**Step 5: Commit**

```bash
git add apps/api/hxy_knowledge/answer_pipeline.py apps/api/hxy_knowledge/reliability.py apps/api/hxy_knowledge/answer_service.py tests/test_hxy_answer_authority.py
git commit -m "feat: add governed answer authority modes"
```

### Task 2: Add source-level authority classification

**Files:**
- Modify: `apps/api/hxy_product/material_repository.py`
- Modify: `apps/api/hxy_product/materials_routes.py` or the current material route module
- Modify: `apps/api/hxy_knowledge/repository.py`
- Create: `data/migrations/018_hxy_source_authority.sql`
- Test: `tests/test_hxy_source_authority.py`

**Step 1: Write failing tests**

Test that source metadata is assigned once per source, inherited by its chunks, and defaults safely:

- explicit `official_internal` requires an allowed owner and source record;
- ordinary uploads default to `internal_material` or `external_reference` based on origin;
- no source-level classification can directly create an approved answer card;
- changing source classification creates a version/event rather than overwriting the prior value;
- chunk retrieval returns authority metadata.

**Step 2: Run the tests and verify the expected failure**

```bash
.venv/bin/pytest tests/test_hxy_source_authority.py -q
```

**Step 3: Implement source-level metadata**

Use one source record and inheritance rather than claim-by-claim approval. Preserve source status, owner, origin, effective dates, supersession, and review event. Keep raw files and private source content under `/root/hxy`; never move private business data into `htops` or public release files.

**Step 4: Verify migration and repository tests**

Run unit tests plus the existing PostgreSQL repository tests. Use an additive migration and do not modify existing authority data in place.

**Step 5: Commit**

```bash
git add apps/api/hxy_product apps/api/hxy_knowledge data/migrations/018_hxy_source_authority.sql tests/test_hxy_source_authority.py
git commit -m "feat: classify knowledge at source level"
```

### Task 3: Add semantic system-capability and task-intent routing

**Files:**
- Modify: `apps/api/hxy_knowledge_api.py`
- Modify: `apps/api/hxy_knowledge/answer_service.py`
- Modify: `apps/api/hxy_knowledge/answer_engine.py`
- Test: `tests/test_hxy_system_intent.py`
- Test: `apps/hxy-web/src/App.test.tsx`

**Step 1: Write failing tests**

Cover:

- “你会什么” and equivalent questions route to `system_capability`;
- “我要练接待”“我要上传资料”“我要反馈门店问题” route to the correct workbench workflow;
- semantic model classification is used only when the deterministic rule is uncertain;
- model failure falls back to deterministic routing;
- system-capability answers do not query private business knowledge or create misleading review tasks.

**Step 2: Run focused tests and verify failure**

```bash
.venv/bin/pytest tests/test_hxy_system_intent.py -q
npm --prefix apps/hxy-web test -- --run src/App.test.tsx
```

**Step 3: Implement routing**

Add a small deterministic capability catalog and let `qwen-flash` classify uncertain task intent. Keep the user-facing answer concise and role-aware. Do not expose model route names, token data, or governance internals in the normal foreground answer.

**Step 4: Verify model-disabled and model-enabled paths**

Use a fake model client for unit tests, then run one real canary only after the test suite passes.

**Step 5: Commit**

```bash
git add apps/api/hxy_knowledge_api.py apps/api/hxy_knowledge apps/hxy-web/src/App.test.tsx tests/test_hxy_system_intent.py
git commit -m "feat: route system capabilities and work intents"
```

### Task 4: Add the local Brand Constitution V1 adapter

**Files:**
- Create: `apps/api/hxy_knowledge/brand_constitution.py`
- Modify: `apps/api/hxy_knowledge/answer_service.py`
- Modify: `apps/api/hxy_knowledge_api.py`
- Create: `tests/fixtures/brand-constitution-v1.example.json`
- Test: `tests/test_hxy_brand_constitution.py`
- Documentation: `docs/operations/hxy-brand-constitution.md`

**Step 1: Write failing tests**

Test a local constitution with a version, owner, effective date, core statements, forbidden interpretations, role variants, and source references. Test that:

- only a valid, active, owner-approved constitution can produce `formal` brand answers;
- chat and process memory cannot mutate it;
- the adapter returns `working` when the constitution is absent or superseded;
- external/reference material cannot override it;
- the adapter supports rollback to the previous version.

**Step 2: Run tests and verify failure**

```bash
.venv/bin/pytest tests/test_hxy_brand_constitution.py -q
```

**Step 3: Implement the adapter**

Read the private constitution from the HXY data root, not from the GitHub release. Keep the initial constitution intentionally small: one brand sentence, a few concrete service/category facts, expression boundaries, and role-specific renderings. Do not copy the full raw knowledge folder into code.

**Step 4: Add operational review rules**

Document the single source-level approval action. A constitution update is versioned and auditable; ordinary conversation can propose a change but cannot publish it.

**Step 5: Commit code and docs only**

```bash
git add apps/api/hxy_knowledge apps/api/hxy_knowledge_api.py tests docs/operations/hxy-brand-constitution.md
git commit -m "feat: add local brand constitution adapter"
```

The real private constitution file remains outside Git.

### Task 5: Build the ten-question acceptance benchmark

**Files:**
- Create: `knowledge/benchmarks/hxyos-core-10.json`
- Modify: `apps/api/hxy_knowledge/brain_benchmark.py`
- Modify: `scripts/run-hxy-benchmark.py` or the current benchmark entrypoint
- Test: `tests/test_hxy_core_10_benchmark.py`

**Step 1: Define the questions and expected behavior**

The set must include system capability, brand identity, product system, employee practice, source classification, operating decision, compliance risk, citation, uncertainty, and next action. Each case asserts answer mode, evidence boundary, risk behavior, and whether a task should be offered.

**Step 2: Write failing benchmark assertions**

The benchmark must fail while the constitution is absent or the answer mode is missing. No pass rate claim is valid until all ten cases have deterministic expected dimensions.

**Step 3: Implement scoring**

Report separate metrics for intent accuracy, authority-mode correctness, citation presence, compliance interception, useful action, and token cost. Do not collapse all quality into one opaque score.

**Step 4: Run the benchmark**

```bash
.venv/bin/pytest tests/test_hxy_core_10_benchmark.py -q
.venv/bin/python scripts/run-hxy-benchmark.py --suite hxyos-core-10
```

Target: `>= 0.85` overall, `100%` for authority leakage and high-risk expression interception.

**Step 5: Commit**

```bash
git add knowledge/benchmarks apps/api/hxy_knowledge scripts tests/test_hxy_core_10_benchmark.py
git commit -m "test: add core ten-question acceptance benchmark"
```

### Task 6: Release and canary the first useful answer loop

**Files:**
- Modify: `docs/operations/hxy-role-journeys-release.md` or create the current release runbook for this profile
- Modify: `ops/env/hxy-model-router.toml` as a non-secret route configuration
- Test: existing Python, TypeScript, Web, Playwright, secret, and public-release checks

**Step 1: Run all tests and scans**

Run Python, TypeScript, Web, Playwright, build, secret scan, public-release scan, and `git diff --check` from the clean release worktree.

**Step 2: Verify live model routing**

Use a dedicated canary request to confirm `qwen-flash`, `qwen-plus-latest`, and `qwen3.7-max` route correctly. Do not use a real user conversation as a canary.

**Step 3: Publish an immutable release**

Keep the private Brand Constitution and source files outside the release artifact. Switch API, Web, and material worker atomically to the same release commit.

**Step 4: Verify the ten real questions**

Run them through the product API and record only bounded evaluation metadata, citations, answer mode, and failure reason. Do not auto-approve any candidate knowledge.

**Step 5: Stop before bulk ingestion**

697-file governance begins only after the benchmark passes and source-level classification is visible in retrieval. Store the batch as queued work; do not expose it to store employees yet.
