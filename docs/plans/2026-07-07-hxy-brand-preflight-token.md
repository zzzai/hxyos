# HXY Brand Preflight Token Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the brand preflight page call the protected enterprise workflow gate with a bearer token.

**Architecture:** Keep the static page and existing workflow endpoint. Add a minimal password input, reuse existing admin localStorage token keys, and attach `Authorization` in `requestJson`.

**Tech Stack:** Static HTML/CSS/JS, Python frontend smoke tests, Node VM script execution.

---

### Task 1: Write Token Contract Tests

**Files:**
- Modify: `tests/test_hxy_brain_frontend.py`

**Steps:**
1. Add assertions for `brandApiToken`, `hxyActionApiToken`, `hxyBrainApiToken`, `hxyKnowledgeApiToken`, and the Authorization header marker.
2. Add a VM test that sets `brandApiToken.value = "front-token"` and verifies the workflow gate request sends `Bearer front-token`.
3. Add a VM test that only has `hxyBrainApiToken` in localStorage and verifies the page reuses it.
4. Run `.venv/bin/pytest -q tests/test_hxy_brain_frontend.py -k "brand_check"` and verify the new tests fail.

### Task 2: Implement Minimal Token Support

**Files:**
- Modify: `apps/admin-web/brand-check.html`

**Steps:**
1. Add a compact password input labeled `系统口令`.
2. Add `initialApiToken()` that reads the three supported localStorage keys.
3. Set `brandApiToken.value` on page load.
4. In `requestJson`, create `Headers`, set `Authorization` when token exists, and pass headers to `fetch`.
5. In `runBrandPreflight`, save the entered token to `hxyActionApiToken`.
6. Run `.venv/bin/pytest -q tests/test_hxy_brain_frontend.py -k "brand_check"` and verify pass.

### Task 3: Verify and Ship

**Steps:**
1. Run `npm test`.
2. Run the HXY benchmark.
3. Run secret and public release checks.
4. Run `git diff --check`.
5. Merge to `main`, rerun verification, push to `origin/main`, and remove the worktree.
