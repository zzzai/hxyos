# HXY Action Preflight Workflow UI Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Upgrade `brand-check.html` from a local forbidden-word checker into a minimal front-stage action preflight workflow.

**Architecture:** Keep the existing static HTML page and route. Add a purpose selector and call the existing HXY-owned compliance workflow gate endpoint. Preserve the local deterministic checker as an offline fallback and keep governance details out of the front-stage UI.

**Tech Stack:** Static HTML/CSS/JS, existing FastAPI endpoint, Python unittest frontend smoke tests, Node VM script execution.

---

### Task 1: Lock the Front-Stage Contract

**Files:**
- Modify: `tests/test_hxy_brain_frontend.py`

**Step 1: Write the failing test**

Update `test_brand_check_is_front_stage_expression_checker_not_review_console` so it expects:

- "动作前预检"
- "能不能继续"
- "为什么"
- "怎么改"
- "下一步"
- `id="brandPurposeSelect"`
- `runBrandPreflight`
- `renderBrandPreflightResult`
- `/api/operating-brain/workflow-gates/compliance/run`
- no raw internal fields or review queue language

Update the boundary-language VM test to call `runBrandPreflight()` and expect `可以继续`.

**Step 2: Run test to verify it fails**

Run:

```bash
.venv/bin/pytest -q tests/test_hxy_brain_frontend.py -k "brand_check"
```

Expected: fail because the current page does not expose the new workflow function and fields.

### Task 2: Implement the Minimal Workflow UI

**Files:**
- Modify: `apps/admin-web/brand-check.html`

**Step 1: Replace the visible product structure**

Keep the page URL and core IDs. Change the visible copy into:

- `动作前预检`
- text area for draft content
- purpose selector
- result blocks for the four workflow answers

**Step 2: Add API-first workflow execution**

Implement `runBrandPreflight()`:

- read `brandTextInput`
- map `brandPurposeSelect` to `workflow_type` and `channel`
- call `/api/operating-brain/workflow-gates/compliance/run`
- render with `renderBrandPreflightResult(payload)`
- on API failure, use local fallback result without official approval language

**Step 3: Preserve compatibility**

Expose `runBrandCheck()` as an alias that calls `runBrandPreflight()` so older tests or bookmarks do not break.

**Step 4: Run focused test**

Run:

```bash
.venv/bin/pytest -q tests/test_hxy_brain_frontend.py -k "brand_check"
```

Expected: pass.

### Task 3: Full Verification and Merge

**Files:**
- No direct product changes unless verification finds a failure.

**Step 1: Run full tests**

```bash
npm test
```

Expected: Python and Vitest pass.

**Step 2: Run benchmark and release guards**

```bash
.venv/bin/python scripts/run-hxy-brain-benchmark.py --benchmark knowledge/benchmarks/hxy-brain-benchmark-v1.json --output /tmp/hxy-brain-benchmark-action-preflight-ui.json
python3 scripts/check-hxy-secrets.py
python3 scripts/check-hxy-public-release.py
git diff --check
```

Expected: benchmark pass rate at least `0.85`, secret and public-release checks pass, whitespace check passes.

**Step 3: Commit and merge**

Commit the changes, merge the feature branch back to `main`, rerun verification on `main`, push to `origin/main`, and remove the worktree.
