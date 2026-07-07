# HXY Compliance Rule Compiler Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Compile local HXY risk/compliance Markdown into deterministic candidate rules used by the external-language check endpoint without approving or publishing private knowledge.

**Architecture:** Extend `apps/api/hxy_knowledge/compliance_rules.py` with deterministic Markdown parsing for forbidden terms, caution terms, safe replacements, employee script snippets, and project red lines. Keep the output as `candidate_rules`, and keep all private source material local. Tests prove the checker uses the expanded rules while preserving governance flags.

**Tech Stack:** Python stdlib, pytest, existing FastAPI endpoint, existing static admin UI.

---

### Task 1: Add Failing Tests For Expanded Local Rule Sources

**Files:**
- Modify: `tests/test_hxy_knowledge_api.py`

**Step 1: Write failing tests**

Add tests that call `load_brand_risk_rules(root_dir=Path.cwd())` and `check_brand_risk_text(...)`.

Required behaviors:

- loaded rule words include employee forbidden examples such as `你这是湿气重`
- loaded rule words include project red-line terms such as `调理体质`
- loaded artifact includes `safe_replacements`
- checking `艾灸调理体质，改善慢病` returns a risky status and hits a bad rule
- checking `我们不做治疗，也不能替代医院检查` returns `ok`
- returned rules keep `official_use_allowed == False` and `requires_human_review == True`

**Step 2: Run test to verify it fails**

Run:

```bash
.venv/bin/pytest -q tests/test_hxy_knowledge_api.py -k "brand_risk"
```

Expected: FAIL because current rules do not compile all local compliance files or expose replacement artifacts.

**Step 3: Commit failing tests**

Do not commit failing tests alone unless implementation is delayed. Prefer completing Task 2 in the same working interval.

### Task 2: Implement Deterministic Compliance Rule Compiler

**Files:**
- Modify: `apps/api/hxy_knowledge/compliance_rules.py`

**Step 1: Add source constants**

Add paths for:

- `荷小悦禁用表达库.md`
- `荷小悦员工功效问题标准话术.md`
- `荷小悦项目红线卡.md`

**Step 2: Add parser helpers**

Implement helpers that extract:

- fenced code block terms from mapped red sections
- table cell values from `不能怎么说`
- table replacement pairs from `常见错误与替换`
- lines under `员工绝对不能说`
- `不能说` blocks inside employee Q&A

**Step 3: Merge into rule types**

Map extracted terms:

- medical/diagnosis terms -> `医疗`
- guaranteed effect/body-conditioning terms -> `保证`
- exaggerated/medical-beauty terms -> `夸大`

When uncertain, prefer `保证` if the phrase implies outcome or body conditioning.

**Step 4: Preserve governance**

Return:

```python
{
    "status": "candidate_rules",
    "official_use_allowed": False,
    "requires_human_review": True,
    "safe_replacements": [...],
    "source_paths": [...],
}
```

**Step 5: Run focused tests**

Run:

```bash
.venv/bin/pytest -q tests/test_hxy_knowledge_api.py -k "brand_risk"
```

Expected: PASS.

**Step 6: Commit**

```bash
git add apps/api/hxy_knowledge/compliance_rules.py tests/test_hxy_knowledge_api.py
git commit -m "feat: compile hxy compliance rules"
```

### Task 3: Add API Evidence For Replacement Suggestions

**Files:**
- Modify: `apps/api/hxy_knowledge_api.py`
- Modify: `tests/test_hxy_knowledge_api.py`

**Step 1: Write failing API test**

Call `/api/operating-brain/skills/hxy-compliance-language-check/run` with a phrase like `治疗颈椎病`.

Assert the response includes a business rewrite suggestion sourced from the replacement table, such as `久坐肩颈紧，按一按松一点`.

**Step 2: Run test to verify it fails**

Run:

```bash
.venv/bin/pytest -q tests/test_hxy_knowledge_api.py -k "compliance_language_check"
```

Expected: FAIL because the endpoint currently uses generic advice only.

**Step 3: Implement minimal replacement lookup**

Use `safe_replacements` from `load_brand_risk_rules()` and pick the first replacement whose forbidden phrase appears in the input.

**Step 4: Run focused tests**

Run:

```bash
.venv/bin/pytest -q tests/test_hxy_knowledge_api.py -k "compliance_language_check"
```

Expected: PASS.

**Step 5: Commit**

```bash
git add apps/api/hxy_knowledge_api.py tests/test_hxy_knowledge_api.py
git commit -m "feat: suggest safer compliance rewrites"
```

### Task 4: Full Verification

**Files:**
- No code changes expected.

**Step 1: Run full tests**

```bash
npm test
```

Expected: Python and Vitest suites pass.

**Step 2: Run benchmark**

```bash
.venv/bin/python scripts/run-hxy-brain-benchmark.py --benchmark knowledge/benchmarks/hxy-brain-benchmark-v1.json --output /tmp/hxy-brain-benchmark-compliance-rule-compiler.json
```

Expected: `pass_rate >= 0.85`.

**Step 3: Run safety checks**

```bash
python3 scripts/check-hxy-secrets.py
python3 scripts/check-hxy-public-release.py
git diff --check
```

Expected: all pass.

**Step 4: Commit docs**

```bash
git add docs/plans/2026-07-07-hxy-compliance-rule-compiler-design.md docs/plans/2026-07-07-hxy-compliance-rule-compiler.md
git commit -m "docs: plan hxy compliance rule compiler"
```
