# HXYOS Knowledge Engine Product Refactor Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Upgrade HXYOS from a compiler/review workbench into a productized Knowledge Engine with retrieval apps, intent planning, skill registry, governed memory policies, and automation tasks.

**Architecture:** Keep the existing HXY-owned FastAPI + static admin pages + JSON artifact foundation. Add first-class contracts and endpoints for product objects while hiding raw compiler artifacts from primary UI. Do not approve knowledge automatically.

**Tech Stack:** Python FastAPI, existing `apps/api/hxy_knowledge_api.py`, static HTML/JS admin pages, JSON artifacts under `knowledge/`, pytest, Node-based frontend static tests.

---

## Constraints

- Scope is `/root/hxy` only.
- Do not touch `/root/htops`.
- Do not introduce `HETANG_*` fallback.
- Do not expose brand/private knowledge in public release artifacts.
- Do not change VI/SI design.
- Do not add a new UI framework.
- Do not let chat, Agent, Loop, Skill, or memory publish `approved` knowledge.

## Task 1: Add Product Object Contracts

**Files:**
- Modify: `apps/api/hxy_knowledge_api.py`
- Test: `tests/test_hxy_knowledge_api.py`

**Step 1: Write failing tests**

Add tests that assert the API exposes stable schema contracts:

```python
def test_operating_brain_product_contracts_include_enterprise_objects(self):
    response = client.get("/api/operating-brain/product-contracts")
    self.assertEqual(response.status_code, 200)
    payload = response.json()
    self.assertIn("knowledge_engine", payload)
    self.assertIn("retrieval_apps", payload)
    self.assertIn("intent_planning", payload)
    self.assertIn("skill_registry", payload)
    self.assertIn("memory_policies", payload)
    self.assertIn("automation_tasks", payload)
    self.assertFalse(payload["authority_rules"]["chat_can_publish_approved"])
    self.assertFalse(payload["authority_rules"]["loop_can_publish_approved"])
    self.assertFalse(payload["authority_rules"]["memory_can_publish_approved"])
```

**Step 2: Run test to verify it fails**

Run:

```bash
.venv/bin/pytest -q tests/test_hxy_knowledge_api.py::HxyKnowledgeApiTest::test_operating_brain_product_contracts_include_enterprise_objects
```

Expected: FAIL with route missing.

**Step 3: Implement minimal endpoint**

Add route:

```python
@app.get("/api/operating-brain/product-contracts")
async def operating_brain_product_contracts_endpoint() -> dict[str, Any]:
    return {
        "knowledge_engine": {...},
        "retrieval_apps": {...},
        "intent_planning": {...},
        "skill_registry": {...},
        "memory_policies": {...},
        "automation_tasks": {...},
        "authority_rules": {
            "chat_can_publish_approved": False,
            "agent_can_publish_approved": False,
            "loop_can_publish_approved": False,
            "memory_can_publish_approved": False,
            "skill_output_is_official": False,
        },
    }
```

Use plain dicts first. Do not add database migrations in this task.

**Step 4: Run test to verify it passes**

Run:

```bash
.venv/bin/pytest -q tests/test_hxy_knowledge_api.py::HxyKnowledgeApiTest::test_operating_brain_product_contracts_include_enterprise_objects
```

Expected: PASS.

**Step 5: Commit**

```bash
git add apps/api/hxy_knowledge_api.py tests/test_hxy_knowledge_api.py
git commit -m "feat: expose hxyos product contracts"
```

## Task 2: Add Retrieval App Catalog

**Files:**
- Modify: `apps/api/hxy_knowledge_api.py`
- Test: `tests/test_hxy_knowledge_api.py`

**Step 1: Write failing tests**

Add:

```python
def test_retrieval_apps_are_business_specific_and_do_not_expose_raw_chunks(self):
    response = client.get("/api/operating-brain/retrieval-apps")
    self.assertEqual(response.status_code, 200)
    serialized = json.dumps(response.json(), ensure_ascii=False)
    self.assertIn("employee_standard_answer_search", serialized)
    self.assertIn("brand_language_risk_check", serialized)
    self.assertIn("founder_decision_evidence_search", serialized)
    self.assertNotIn("chunk_id", serialized)
    self.assertNotIn("/root/hxy", serialized)
    self.assertNotIn("cluster_member_count", serialized)
```

**Step 2: Run test to verify it fails**

```bash
.venv/bin/pytest -q tests/test_hxy_knowledge_api.py::HxyKnowledgeApiTest::test_retrieval_apps_are_business_specific_and_do_not_expose_raw_chunks
```

Expected: FAIL with route missing.

**Step 3: Implement catalog**

Create an in-memory catalog for V1:

```python
RETRIEVAL_APP_CATALOG = [
    {
        "retrieval_app_id": "employee_standard_answer_search",
        "name": "员工标准答案检索",
        "allowed_statuses": ["approved", "action_asset"],
        "official_use_allowed": True,
        "status": "draft",
    },
    ...
]
```

Return via:

```python
@app.get("/api/operating-brain/retrieval-apps")
async def operating_brain_retrieval_apps_endpoint() -> dict[str, Any]:
    return {"items": RETRIEVAL_APP_CATALOG, "authority_rule": "..."}
```

**Step 4: Run test to verify it passes**

```bash
.venv/bin/pytest -q tests/test_hxy_knowledge_api.py::HxyKnowledgeApiTest::test_retrieval_apps_are_business_specific_and_do_not_expose_raw_chunks
```

Expected: PASS.

**Step 5: Commit**

```bash
git add apps/api/hxy_knowledge_api.py tests/test_hxy_knowledge_api.py
git commit -m "feat: add retrieval app catalog"
```

## Task 3: Add Intent Definition Catalog

**Files:**
- Modify: `apps/api/hxy_knowledge_api.py`
- Test: `tests/test_hxy_knowledge_api.py`

**Step 1: Write failing tests**

Add:

```python
def test_intent_definitions_have_scope_exclusions_and_risk_gates(self):
    response = client.get("/api/operating-brain/intent-definitions")
    self.assertEqual(response.status_code, 200)
    items = response.json()["items"]
    compliance = next(item for item in items if item["intent_id"] == "intent-compliance-language-check")
    self.assertIn("positive_scope", compliance)
    self.assertIn("excluded_scope", compliance)
    self.assertIn("risk_gates", compliance)
    self.assertIn("medical_claim", compliance["risk_gates"])
```

**Step 2: Run test to verify it fails**

```bash
.venv/bin/pytest -q tests/test_hxy_knowledge_api.py::HxyKnowledgeApiTest::test_intent_definitions_have_scope_exclusions_and_risk_gates
```

Expected: FAIL with route missing.

**Step 3: Implement catalog**

Add `INTENT_DEFINITION_CATALOG` with first intents:

- `intent-approved-answer`
- `intent-material-ingest`
- `intent-compliance-language-check`
- `intent-brand-expression-review`
- `intent-opening-store-workflow`
- `intent-loop-execution`
- `intent-correction-feedback`

**Step 4: Run test to verify it passes**

```bash
.venv/bin/pytest -q tests/test_hxy_knowledge_api.py::HxyKnowledgeApiTest::test_intent_definitions_have_scope_exclusions_and_risk_gates
```

Expected: PASS.

**Step 5: Commit**

```bash
git add apps/api/hxy_knowledge_api.py tests/test_hxy_knowledge_api.py
git commit -m "feat: add intent definition catalog"
```

## Task 4: Add Skill Registry Catalog

**Files:**
- Modify: `apps/api/hxy_knowledge_api.py`
- Test: `tests/test_hxy_knowledge_api.py`

**Step 1: Write failing tests**

Add:

```python
def test_skill_registry_keeps_skill_output_non_official(self):
    response = client.get("/api/operating-brain/skills")
    self.assertEqual(response.status_code, 200)
    payload = response.json()
    self.assertIn("items", payload)
    self.assertFalse(payload["authority_rules"]["skill_output_is_official"])
    for item in payload["items"]:
        self.assertIn("version", item)
        self.assertIn("status", item)
        self.assertIn("owner", item)
        self.assertFalse(item["can_publish_approved"])
```

**Step 2: Run test to verify it fails**

```bash
.venv/bin/pytest -q tests/test_hxy_knowledge_api.py::HxyKnowledgeApiTest::test_skill_registry_keeps_skill_output_non_official
```

Expected: FAIL with route missing.

**Step 3: Implement catalog**

Add `SKILL_REGISTRY_CATALOG` with:

- `hxy-compliance-language-check`
- `hxy-brand-expression-review`
- `hxy-employee-answer-coach`
- `hxy-ingest-material-compiler`
- `hxy-opening-store-checklist`
- `hxy-benchmark-correction-pack`
- `hxy-decision-evidence-pack`
- `hxy-review-topic-generator`

**Step 4: Run test to verify it passes**

```bash
.venv/bin/pytest -q tests/test_hxy_knowledge_api.py::HxyKnowledgeApiTest::test_skill_registry_keeps_skill_output_non_official
```

Expected: PASS.

**Step 5: Commit**

```bash
git add apps/api/hxy_knowledge_api.py tests/test_hxy_knowledge_api.py
git commit -m "feat: add skill registry catalog"
```

## Task 5: Add Admin Product Layer UI

**Files:**
- Modify: `apps/admin-web/knowledge.html`
- Test: `tests/test_hxy_brain_frontend.py`

**Step 1: Write failing frontend test**

Add:

```python
def test_knowledge_page_shows_product_objects_not_raw_artifacts(self):
    html = KNOWLEDGE_HTML.read_text(encoding="utf-8")
    self.assertIn("知识引擎", html)
    self.assertIn("检索应用", html)
    self.assertIn("意图规划", html)
    self.assertIn("Skill 中心", html)
    self.assertIn("自动化任务", html)
    self.assertIn("renderRetrievalApps", html)
    self.assertIn("renderIntentDefinitions", html)
    self.assertIn("renderSkills", html)
    self.assertNotIn("cluster_member_count", html)
    self.assertNotIn("sample_claims", html)
```

**Step 2: Run test to verify it fails**

```bash
.venv/bin/pytest -q tests/test_hxy_brain_frontend.py::HxyBrainFrontendTest::test_knowledge_page_shows_product_objects_not_raw_artifacts
```

Expected: FAIL until UI is updated.

**Step 3: Implement minimal UI panels**

Add restrained admin-only panels:

- Knowledge Engine summary.
- Retrieval Apps list.
- Intent Definitions list.
- Skill Registry list.
- Automation Task placeholder.

Do not put approval controls in frontdesk. Do not expose raw claims as primary content.

**Step 4: Run frontend tests**

```bash
.venv/bin/pytest -q tests/test_hxy_brain_frontend.py::HxyBrainFrontendTest::test_knowledge_page_shows_product_objects_not_raw_artifacts
node - <<'NODE'
const fs = require('fs');
const html = fs.readFileSync('apps/admin-web/knowledge.html','utf8');
const script = html.split('<script>', 2)[1].split('</script>', 1)[0];
new Function(script);
console.log('script_ok');
NODE
```

Expected: PASS and `script_ok`.

**Step 5: Commit**

```bash
git add apps/admin-web/knowledge.html tests/test_hxy_brain_frontend.py
git commit -m "feat: show hxyos product objects in admin"
```

## Task 6: Add Automation Task Catalog

**Files:**
- Modify: `apps/api/hxy_knowledge_api.py`
- Test: `tests/test_hxy_knowledge_api.py`

**Step 1: Write failing tests**

Add:

```python
def test_automation_tasks_are_allowlisted_and_cannot_publish_approved(self):
    response = client.get("/api/operating-brain/automation-tasks")
    self.assertEqual(response.status_code, 200)
    for item in response.json()["items"]:
        self.assertIn("task_type", item)
        self.assertIn("stop_condition", item)
        self.assertFalse(item["can_publish_approved"])
        self.assertTrue(item["allowed_script"].startswith("scripts/") or item["allowed_script"] == "")
```

**Step 2: Run test to verify it fails**

```bash
.venv/bin/pytest -q tests/test_hxy_knowledge_api.py::HxyKnowledgeApiTest::test_automation_tasks_are_allowlisted_and_cannot_publish_approved
```

Expected: FAIL with route missing.

**Step 3: Implement catalog**

Add task definitions:

- `automation_ingest_loop_manual`
- `automation_benchmark_loop_manual`
- `automation_review_topic_refresh`

Keep all disabled by default except manual read-only/status refresh if already safe.

**Step 4: Run test to verify it passes**

```bash
.venv/bin/pytest -q tests/test_hxy_knowledge_api.py::HxyKnowledgeApiTest::test_automation_tasks_are_allowlisted_and_cannot_publish_approved
```

Expected: PASS.

**Step 5: Commit**

```bash
git add apps/api/hxy_knowledge_api.py tests/test_hxy_knowledge_api.py
git commit -m "feat: add automation task catalog"
```

## Task 7: Full Verification

**Files:**
- No new files.

**Step 1: Run backend/frontend tests**

```bash
npm test
```

Expected: all tests pass.

**Step 2: Run HXY benchmark**

```bash
.venv/bin/python scripts/run-hxy-brain-benchmark.py --benchmark knowledge/benchmarks/hxy-brain-benchmark-v1.json --output /tmp/hxy-brain-benchmark-product-refactor.json
```

Expected: pass rate remains `>= 0.85`.

**Step 3: Run release safety checks**

```bash
python3 scripts/check-hxy-secrets.py
python3 scripts/check-hxy-public-release.py
git diff --check
```

Expected: all pass.

**Step 4: Manual API smoke test**

```bash
scripts/start-hxy-knowledge-api.sh --restart
curl -fsS http://127.0.0.1:18081/api/operating-brain/product-contracts | python3 -m json.tool | sed -n '1,120p'
curl -fsS http://127.0.0.1:18081/api/operating-brain/retrieval-apps | python3 -m json.tool | sed -n '1,160p'
```

Expected:

- product objects present;
- no absolute `/root/hxy` paths;
- no raw claim internals.

**Step 5: Final commit if needed**

```bash
git status --short
```

Expected: clean except unrelated user changes. Do not revert unrelated changes.
