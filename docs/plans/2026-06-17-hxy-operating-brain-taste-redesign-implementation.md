# HXY Operating Brain Taste Redesign Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the HXY Operating Brain feel like a chat-first operating product where the center answer is primary and technical knowledge controls are progressively disclosed.

**Architecture:** Keep the existing static `brain.html` architecture. Use CSS grid and small vanilla JavaScript state toggles for desktop Inspector and mobile drawers. Do not add frontend dependencies or move this into a build pipeline.

**Tech Stack:** Static HTML, CSS variables, vanilla JavaScript, Python unittest frontend checks.

---

### Task 1: Lock Chat-First Product Shape

**Files:**
- Modify: `tests/test_hxy_brain_frontend.py`
- Modify: `apps/admin-web/brain.html`

**Step 1: Write failing tests**

Add assertions for:

- `class="workspace chat-first"`
- `class="mobile-actions"`
- `data-toggle-status`
- `data-close-inspector`
- `class="answer-detail inspector-panel is-hidden"`
- `openInspector`
- `closeInspector`
- `workspace.classList.toggle("inspector-open"`

**Step 2: Run frontend tests**

Run: `python3 -m unittest tests/test_hxy_brain_frontend.py -v`

Expected: fail because the new UI hooks do not exist yet.

**Step 3: Implement minimal UI hooks**

Update `brain.html` so the workspace starts as chat-first, the Inspector is hidden, and the chat header contains compact mobile controls.

**Step 4: Run frontend tests**

Run: `python3 -m unittest tests/test_hxy_brain_frontend.py -v`

Expected: pass.

### Task 2: Convert Left Controls Into Lightweight Status Rail

**Files:**
- Modify: `tests/test_hxy_brain_frontend.py`
- Modify: `apps/admin-web/brain.html`

**Step 1: Write failing tests**

Assert:

- `panel-disclosure`
- summaries for `连接`, `资料上传`, `复核任务`, and `资料位置`
- visible metrics remain in `knowledge-status`

**Step 2: Run frontend tests**

Run: `python3 -m unittest tests/test_hxy_brain_frontend.py -v`

Expected: fail because left controls are still full blocks.

**Step 3: Implement status rail**

Wrap API, upload, review, and file-location controls in disclosure groups. Keep knowledge metrics visible.

**Step 4: Run frontend tests**

Run: `python3 -m unittest tests/test_hxy_brain_frontend.py -v`

Expected: pass.

### Task 3: Finish Visual Polish And Verification

**Files:**
- Modify: `apps/admin-web/brain.html`

**Step 1: Refine CSS**

Apply chat-first grid sizing, drawer behavior, focus states, restrained shadows, no global page scroll, and mobile chat-first ordering.

**Step 2: Run full tests**

Run:

```bash
python3 -m unittest tests/test_hxy_knowledge_api.py tests/test_hxy_knowledge_service.py tests/test_hxy_brain_frontend.py tests/test_hxy_operating_brain_docs.py -v
```

Expected: all tests pass.

**Step 3: Run HTML/JS smoke checks**

Run a local syntax check over the script block and smoke `/health` and `/brain.html` on the API service if available.

Expected: JavaScript parses and the service returns the page.
