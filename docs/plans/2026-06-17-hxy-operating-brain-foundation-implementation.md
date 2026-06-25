# HXY Operating Brain Foundation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a tested operating-brain foundation contract that defines HXY capabilities, knowledge fusion, model routing, and no-pretraining strategy.

**Architecture:** Add a pure Python module under `apps/api/hxy_knowledge/operating_brain.py` with static, versioned capability metadata. Expose it through FastAPI as `/api/operating-brain/capabilities`. Keep current answer engine behavior unchanged.

**Tech Stack:** Python, FastAPI, unittest, static HTML docs.

---

### Task 1: Capability Module

**Files:**
- Create: `apps/api/hxy_knowledge/operating_brain.py`
- Modify: `tests/test_hxy_knowledge_service.py`

**Step 1: Write failing tests**

Add tests that import `operating_brain.py` and assert:

- `operating_brain_capabilities()` returns `version == "hxy-operating-brain.v1"`;
- it includes six knowledge categories;
- it includes model routes for reasoning, classification, embedding, vision, and speech;
- `training_strategy["pretraining_required"] is False`;
- `training_strategy["fine_tuning_gate"]` mentions approved answers and correction records.

**Step 2: Run focused service tests**

Run: `python3 -m unittest tests/test_hxy_knowledge_service.py -v`

Expected: fail because the module does not exist.

**Step 3: Implement module**

Create `operating_brain.py` with a single exported `operating_brain_capabilities()` function returning a serializable dict.

**Step 4: Run focused service tests**

Run: `python3 -m unittest tests/test_hxy_knowledge_service.py -v`

Expected: pass.

### Task 2: API Contract

**Files:**
- Modify: `apps/api/hxy_knowledge_api.py`
- Modify: `tests/test_hxy_knowledge_api.py`

**Step 1: Write failing API test**

Add a test for `GET /api/operating-brain/capabilities` that asserts:

- HTTP 200;
- project knowledge and operating data are both present;
- model routing includes `reasoning`;
- pretraining is false.

**Step 2: Run focused API tests**

Run: `python3 -m unittest tests/test_hxy_knowledge_api.py -v`

Expected: fail because route does not exist.

**Step 3: Implement route**

Import `operating_brain_capabilities` and return it from the new endpoint.

**Step 4: Run focused API tests**

Run: `python3 -m unittest tests/test_hxy_knowledge_api.py -v`

Expected: pass.

### Task 3: Docs Contract

**Files:**
- Modify: `docs/architecture/hxy-operating-memory-and-skills.md`
- Modify: `tests/test_hxy_operating_brain_docs.py`

**Step 1: Write failing docs test**

Assert the architecture doc contains:

- `运营大脑不是项目资料问答页`;
- `project_knowledge`;
- `operating_data`;
- `market_intelligence`;
- `operating_methodology`;
- `organizational_memory`;
- `role_context`;
- `不做预训练`.

**Step 2: Run docs tests**

Run: `python3 -m unittest tests/test_hxy_operating_brain_docs.py -v`

Expected: fail until doc is updated.

**Step 3: Update architecture doc**

Append a concise operating-brain foundation section.

**Step 4: Run docs tests**

Run: `python3 -m unittest tests/test_hxy_operating_brain_docs.py -v`

Expected: pass.

### Task 4: Full Verification

Run:

```bash
python3 -m unittest tests/test_hxy_knowledge_api.py tests/test_hxy_knowledge_service.py tests/test_hxy_brain_frontend.py tests/test_hxy_operating_brain_docs.py -v
node - <<'NODE'
const fs = require('fs');
const html = fs.readFileSync('apps/admin-web/brain.html', 'utf8');
const match = html.match(/<script>([\s\S]*)<\/script>/);
if (!match) throw new Error('script block not found');
new Function(match[1]);
console.log('brain.html script syntax OK');
NODE
curl -sS -o /tmp/hxy-operating-brain.json -w '%{http_code}\n' http://127.0.0.1:18081/api/operating-brain/capabilities
```

Expected: all tests pass, JavaScript parses, API returns 200.
