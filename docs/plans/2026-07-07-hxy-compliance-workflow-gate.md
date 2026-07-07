# HXY Compliance Workflow Gate Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a reusable compliance workflow gate for content publishing, staff scripts, and project menu copy so risky text stops before release, training, or menu use.

**Architecture:** Keep the existing deterministic language check as the rule engine. Add a new authenticated FastAPI endpoint that wraps the check result into workflow-specific business decisions. Update the existing admin knowledge panel to call the workflow gate with a minimal purpose selector.

**Tech Stack:** Python FastAPI, Pydantic, existing `hxy_knowledge.compliance_rules`, static HTML/JS admin page, pytest, Vitest/static frontend smoke tests.

---

### Task 1: Backend Failing Tests For Workflow Gate

**Files:**
- Modify: `tests/test_hxy_knowledge_api.py`

**Step 1: Write failing tests**

Add tests for:

- `POST /api/operating-brain/workflow-gates/compliance/run`
- `workflow_type=content_publish` with `泡脚能治疗失眠` returns `workflow_status=blocked`, `can_continue=false`, `can_publish=false`
- `workflow_type=staff_script` with `你这是湿气重，要调理几个疗程` returns `workflow_status=blocked`
- `workflow_type=project_menu` with `艾灸调理体质，改善慢病` returns `workflow_status=blocked`
- safe text returns `workflow_status=can_continue`, `can_continue=true`, `can_publish=false`
- unknown workflow type returns `400`

**Step 2: Verify tests fail**

Run:

```bash
.venv/bin/pytest -q tests/test_hxy_knowledge_api.py -k "compliance_workflow_gate"
```

Expected: FAIL because the endpoint does not exist.

### Task 2: Implement Workflow Gate Endpoint

**Files:**
- Modify: `apps/api/hxy_knowledge_api.py`

**Step 1: Add request model**

Add:

```python
class ComplianceWorkflowGateRequest(BaseModel):
    workflow_type: str = "content_publish"
    text: str = ""
    channel: str = "unknown"
    audience: str = "customer"
```

**Step 2: Add workflow metadata**

Add a small mapping for `content_publish`, `staff_script`, and `project_menu`.

Each mapping includes:

- label
- safe next step
- revise next step
- blocked next step
- human owner

**Step 3: Add helper**

Create `_compliance_workflow_gate_result(...)` that:

- validates workflow type
- calls `_compliance_language_check_result(...)`
- maps `decision` to `workflow_status`
- returns business fields
- keeps `can_publish=false` and `official_use_allowed=false`

**Step 4: Add endpoint**

Add:

```python
@app.post("/api/operating-brain/workflow-gates/compliance/run", dependencies=[Depends(require_api_token)])
```

Fail closed if `HXY_API_TOKEN` is missing, same as the skill endpoint.

**Step 5: Verify focused tests pass**

Run:

```bash
.venv/bin/pytest -q tests/test_hxy_knowledge_api.py -k "compliance_workflow_gate"
```

Expected: PASS.

**Step 6: Commit**

```bash
git add apps/api/hxy_knowledge_api.py tests/test_hxy_knowledge_api.py
git commit -m "feat: add compliance workflow gate"
```

### Task 3: Frontend Failing Test

**Files:**
- Modify: `tests/test_hxy_brain_frontend.py`

**Step 1: Update static frontend test**

Assert `apps/admin-web/knowledge.html` contains:

- `id="complianceWorkflowTypeSelect"`
- `内容发布`
- `员工话术`
- `项目菜单`
- `/api/operating-brain/workflow-gates/compliance/run`
- `能不能继续`
- `下一步`
- `负责人`

**Step 2: Verify test fails**

Run:

```bash
npm run test:ts -- tests/test_hxy_brain_frontend.py
```

If this repository routes frontend static tests through pytest, run:

```bash
.venv/bin/pytest -q tests/test_hxy_brain_frontend.py -k "compliance"
```

Expected: FAIL because the UI has not been updated.

### Task 4: Update Minimal Admin Panel

**Files:**
- Modify: `apps/admin-web/knowledge.html`

**Step 1: Add workflow select**

Add a select above/beside scene:

```html
<select id="complianceWorkflowTypeSelect">
  <option value="content_publish">内容发布</option>
  <option value="staff_script">员工话术</option>
  <option value="project_menu">项目菜单</option>
</select>
```

**Step 2: Call workflow gate endpoint**

Change `runComplianceLanguageCheck()` to call:

```text
/api/operating-brain/workflow-gates/compliance/run
```

Include `workflow_type` in the body.

**Step 3: Render business labels**

Update result rendering to show:

- 能不能继续
- 风险等级
- 原因
- 建议改法
- 下一步
- 负责人
- 不会自动发布

**Step 4: Verify frontend tests pass**

Run:

```bash
.venv/bin/pytest -q tests/test_hxy_brain_frontend.py -k "compliance"
```

Expected: PASS.

**Step 5: Commit**

```bash
git add apps/admin-web/knowledge.html tests/test_hxy_brain_frontend.py
git commit -m "feat: connect compliance gate to admin workflows"
```

### Task 5: Full Verification

**Step 1: Run full tests**

```bash
npm test
```

**Step 2: Run benchmark**

```bash
.venv/bin/python scripts/run-hxy-brain-benchmark.py --benchmark knowledge/benchmarks/hxy-brain-benchmark-v1.json --output /tmp/hxy-brain-benchmark-compliance-workflow-gate.json
```

Expected: `pass_rate >= 0.85`.

**Step 3: Run safety checks**

```bash
python3 scripts/check-hxy-secrets.py
python3 scripts/check-hxy-public-release.py
git diff --check
```

Expected: all pass.
