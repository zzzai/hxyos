# HXY Compliance Action Preflight Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Run compliance preflight automatically before content review, employee script training, menu draft save, and approved answer-card creation.

**Architecture:** Reuse the existing `_compliance_workflow_gate_result` helper. Add a small preflight wrapper that maps action types to workflow types, then attach the preflight result to existing responses or block approved authority writes when needed.

**Tech Stack:** Python FastAPI, Pydantic, existing compliance workflow gate, pytest.

---

### Task 1: Backend Failing Tests

**Files:**
- Modify: `tests/test_hxy_knowledge_api.py`

**Step 1: Write tests**

Add tests for:

- `brand-decision/review` includes `compliance_preflight` and blocks risky content from continuing
- `training/evaluate` with risky employee answer returns `needs_retrain=true` and `answer_card_draft=null`
- `POST /api/knowledge/answer-cards` rejects risky `status=approved`
- `POST /api/knowledge/answer-cards` allows risky `status=draft` and returns `compliance_preflight`
- `POST /api/operating-brain/menu-draft/preflight` returns a dry-run project menu preflight and `write_to_database=false`

**Step 2: Verify tests fail**

Run:

```bash
.venv/bin/pytest -q tests/test_hxy_knowledge_api.py -k "compliance_preflight"
```

Expected: FAIL because the behavior does not exist yet.

### Task 2: Implement Preflight Helper

**Files:**
- Modify: `apps/api/hxy_knowledge_api.py`

**Step 1: Add request model**

Add:

```python
class MenuDraftPreflightRequest(BaseModel):
    text: str = ""
    channel: str = "项目菜单"
    audience: str = "customer"
```

**Step 2: Add helper**

Add:

```python
def _compliance_preflight_for_text(text, workflow_type, channel, audience, root_dir):
    ...
```

It calls `_compliance_workflow_gate_result`.

**Step 3: Preserve governance**

The returned object must include:

```text
write_to_database=false
can_publish=false
official_use_allowed=false
```

### Task 3: Attach Preflight To Existing Actions

**Files:**
- Modify: `apps/api/hxy_knowledge_api.py`

**Step 1: Brand decision**

In `operating_brain_brand_decision_review_endpoint`, compute preflight from `request.text`.

Map artifact type:

- `first_order_menu` -> `project_menu`
- `staff_script` -> `staff_script`
- otherwise -> `content_publish`

Add `compliance_preflight` and `can_continue`.

**Step 2: Training evaluate**

Before creating review task:

- compute preflight with `workflow_type=staff_script`
- add it to result
- if `can_continue=false`, set `needs_retrain=true`, `answer_card_draft=None`, append correction point

**Step 3: Answer-card creation**

Compute preflight from `request.answer`.

If `request.status == "approved"` and `can_continue=false`, raise `400`.

If draft, save normally and return the preflight object.

**Step 4: Menu preflight endpoint**

Add:

```python
@app.post("/api/operating-brain/menu-draft/preflight", dependencies=[Depends(require_api_token)])
```

Return dry-run preflight with no write.

### Task 4: Focused Verification And Commit

Run:

```bash
.venv/bin/pytest -q tests/test_hxy_knowledge_api.py -k "compliance_preflight"
```

Expected: PASS.

Commit:

```bash
git add apps/api/hxy_knowledge_api.py tests/test_hxy_knowledge_api.py
git commit -m "feat: enforce compliance preflight before action writes"
```

### Task 5: Full Verification

Run:

```bash
npm test
.venv/bin/python scripts/run-hxy-brain-benchmark.py --benchmark knowledge/benchmarks/hxy-brain-benchmark-v1.json --output /tmp/hxy-brain-benchmark-compliance-action-preflight.json
python3 scripts/check-hxy-secrets.py
python3 scripts/check-hxy-public-release.py
git diff --check
```
