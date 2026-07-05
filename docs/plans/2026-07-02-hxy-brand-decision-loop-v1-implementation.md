# HXY Brand Decision Loop V1 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a deterministic first-store brand decision loop that scores storefront copy, first-order menu copy, opening content, and staff scripts without replacing VI/SI design work or auto-approving official brand standards.

**Architecture:** Add a pure Python brand decision module under `apps/api/hxy_knowledge/`, a CLI runner under `scripts/`, API endpoints under the existing HXY knowledge API, and a small workbench panel. V1 uses deterministic rubric rules and persisted JSON review records under `knowledge/brand/reviews/`; future LLM/RAG layers can enhance evidence retrieval without changing the governance contract.

**Tech Stack:** Python standard library, FastAPI, static HTML/JS, pytest, existing HXY knowledge API patterns.

---

## Constraints

- Do not generate VI or SI.
- Do not replace the design company.
- Do not approve official brand standards automatically.
- Do not use candidate/reference material as authoritative source.
- Do not read or write `/root/htops` business data.
- Keep artifacts under HXY-owned directories.
- Every output must include `official_use_allowed: false`.
- All behavior changes require failing tests first.

## Task 1: Add Brand Decision Rule Tests

**Files:**

- Create: `tests/test_hxy_brand_decision.py`
- Create later: `apps/api/hxy_knowledge/brand_decision.py`

**Step 1: Write the failing storefront scoring test**

Add:

```python
def test_review_storefront_copy_scores_clear_first_store_expression():
    from hxy_knowledge.brand_decision import review_brand_artifact

    result = review_brand_artifact(
        {
            "artifact_type": "storefront",
            "stage": "first_store_opening",
            "text": "荷小悦 草本泡脚按摩\n草本真现煮，按出真功夫",
        }
    )

    assert result["version"] == "hxy-brand-decision-review.v1"
    assert result["artifact_type"] == "storefront"
    assert result["score"] >= 85
    assert result["status"] == "usable_draft_requires_review"
    assert result["official_use_allowed"] is False
    assert result["requires_human_review"] is True
    assert "category_clarity" in {item["criterion"] for item in result["criteria"]}
```

**Step 2: Run test to verify it fails**

Run:

```bash
PATH=/root/hxy/.venv/bin:$PATH PYTHONPATH=/root/hxy/apps/api pytest tests/test_hxy_brand_decision.py::test_review_storefront_copy_scores_clear_first_store_expression -q
```

Expected: FAIL because `hxy_knowledge.brand_decision` does not exist.

**Step 3: Write the failing risk rejection test**

Add:

```python
def test_review_brand_artifact_rejects_medicalized_claims():
    from hxy_knowledge.brand_decision import review_brand_artifact

    result = review_brand_artifact(
        {
            "artifact_type": "opening_content",
            "stage": "first_store_opening",
            "text": "荷小悦草本泡脚，治疗失眠，一次见效。",
        }
    )

    assert result["status"] == "reject_for_first_store_use"
    assert "overclaim_risk" in result["risk_flags"]
    assert result["score"] < 70
    assert result["official_use_allowed"] is False
```

**Step 4: Run tests to verify failure**

Run:

```bash
PATH=/root/hxy/.venv/bin:$PATH PYTHONPATH=/root/hxy/apps/api pytest tests/test_hxy_brand_decision.py -q
```

Expected: FAIL because implementation is missing.

## Task 2: Implement Deterministic Brand Decision Module

**Files:**

- Create: `apps/api/hxy_knowledge/brand_decision.py`
- Test: `tests/test_hxy_brand_decision.py`

**Step 1: Implement constants and scoring**

Create:

```python
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from typing import Any


RISK_TERMS = ["治疗", "治愈", "根治", "排毒", "祛病", "改善疾病", "疗效保证", "一次见效", "包好", "医用", "中医诊疗", "康复治疗"]
CATEGORY_TERMS = ["泡脚", "按摩", "足疗", "草本泡脚", "肩颈"]
SCENARIO_TERMS = ["下班", "脚沉", "肩颈紧", "久坐", "站了一天", "腿酸", "睡前", "周末"]
ACTION_TERMS = ["泡一泡", "按一按", "泡脚", "按摩", "进店", "预约", "体验"]
TRUST_TERMS = ["草本现煮", "草本真现煮", "明码实价", "不强推", "不强推办卡", "干净", "技师", "真功夫"]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _stable_id(*parts: str) -> str:
    return "hxy-brand-review:" + sha256("\n".join(parts).encode("utf-8")).hexdigest()[:16]
```

**Step 2: Implement `review_brand_artifact`**

Add a deterministic function that:

- accepts a dict with `artifact_type`, `stage`, and `text`;
- scores criteria by keyword and rule checks;
- gives `usable_draft_requires_review`, `revise_before_use`, or `reject_for_first_store_use`;
- always returns `official_use_allowed: false`;
- attaches source references to current rule documents.

**Step 3: Run tests**

Run:

```bash
PATH=/root/hxy/.venv/bin:$PATH PYTHONPATH=/root/hxy/apps/api pytest tests/test_hxy_brand_decision.py -q
```

Expected: PASS.

**Step 4: Commit**

```bash
git add apps/api/hxy_knowledge/brand_decision.py tests/test_hxy_brand_decision.py
git commit -m "feat: add hxy brand decision scoring"
```

## Task 3: Add VI/SI Boundary Test

**Files:**

- Modify: `tests/test_hxy_brand_decision.py`
- Modify: `apps/api/hxy_knowledge/brand_decision.py`

**Step 1: Write failing test**

Add:

```python
def test_review_design_company_output_respects_vi_si_boundary():
    from hxy_knowledge.brand_decision import review_brand_artifact

    result = review_brand_artifact(
        {
            "artifact_type": "design_company_output",
            "stage": "first_store_opening",
            "text": "设计公司提交门店SI方案，包含色彩、门头、空间导视。",
        }
    )

    assert result["status"] == "requires_design_acceptance_review"
    assert "design_company_owns_visual_design" in result["boundary"]
    assert "hxyos_reviews_operating_fit" in result["boundary"]
    assert result["official_use_allowed"] is False
```

**Step 2: Run test to verify failure**

Run:

```bash
PATH=/root/hxy/.venv/bin:$PATH PYTHONPATH=/root/hxy/apps/api pytest tests/test_hxy_brand_decision.py::test_review_design_company_output_respects_vi_si_boundary -q
```

Expected: FAIL until boundary logic exists.

**Step 3: Implement boundary branch**

If `artifact_type == "design_company_output"`, return a review result that:

- does not score visual aesthetics;
- states design company owns VI/SI;
- asks for operating acceptance review;
- marks result as not official.

**Step 4: Run tests**

Run:

```bash
PATH=/root/hxy/.venv/bin:$PATH PYTHONPATH=/root/hxy/apps/api pytest tests/test_hxy_brand_decision.py -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add apps/api/hxy_knowledge/brand_decision.py tests/test_hxy_brand_decision.py
git commit -m "feat: preserve vi si design boundary"
```

## Task 4: Add Review Record Writer And CLI

**Files:**

- Modify: `tests/test_hxy_brand_decision.py`
- Modify: `apps/api/hxy_knowledge/brand_decision.py`
- Create: `scripts/run-hxy-brand-decision.py`

**Step 1: Write failing persistence test**

Add:

```python
def test_write_brand_review_record_persists_review(tmp_path):
    from hxy_knowledge.brand_decision import review_brand_artifact, write_brand_review_record

    review = review_brand_artifact(
        {
            "artifact_type": "staff_script",
            "stage": "first_store_opening",
            "text": "第一次来可以先做基础足疗，泡一泡按一按，不强推办卡。",
        }
    )

    path = write_brand_review_record(review, reviews_dir=tmp_path / "knowledge" / "brand" / "reviews")

    assert path.exists()
    assert "hxy-brand-review" in path.name
```

**Step 2: Write failing CLI test**

Add:

```python
import json
import subprocess
import sys
from pathlib import Path


def test_brand_decision_cli_writes_review(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            "scripts/run-hxy-brand-decision.py",
            "--artifact-type",
            "storefront",
            "--stage",
            "first_store_opening",
            "--text",
            "荷小悦 草本泡脚按摩",
            "--reviews-dir",
            str(tmp_path / "knowledge" / "brand" / "reviews"),
        ],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["version"] == "hxy-brand-decision-cli.v1"
    assert payload["review"]["official_use_allowed"] is False
    assert Path(payload["review_path"]).exists()
```

**Step 3: Run tests to verify failure**

Run:

```bash
PATH=/root/hxy/.venv/bin:$PATH PYTHONPATH=/root/hxy/apps/api pytest tests/test_hxy_brand_decision.py -q
```

Expected: FAIL until writer and CLI exist.

**Step 4: Implement writer and CLI**

Add `write_brand_review_record(review, reviews_dir)` to the module.

Create `scripts/run-hxy-brand-decision.py` with args:

- `--artifact-type`
- `--stage`
- `--text`
- `--reviews-dir`

The CLI prints:

```json
{
  "version": "hxy-brand-decision-cli.v1",
  "review": {},
  "review_path": "knowledge/brand/reviews/..."
}
```

**Step 5: Run tests**

Run:

```bash
PATH=/root/hxy/.venv/bin:$PATH PYTHONPATH=/root/hxy/apps/api pytest tests/test_hxy_brand_decision.py -q
```

Expected: PASS.

**Step 6: Commit**

```bash
git add apps/api/hxy_knowledge/brand_decision.py scripts/run-hxy-brand-decision.py tests/test_hxy_brand_decision.py
git commit -m "feat: persist hxy brand decision reviews"
```

## Task 5: Expose Brand Decision API

**Files:**

- Modify: `apps/api/hxy_knowledge_api.py`
- Modify: `tests/test_hxy_knowledge_api.py`

**Step 1: Write failing API test**

Add to `tests/test_hxy_knowledge_api.py`:

```python
def test_operating_brain_brand_decision_review_requires_auth_and_does_not_approve(self):
    response = self.client.post(
        "/api/operating-brain/brand-decision/review",
        json={
            "artifact_type": "storefront",
            "stage": "first_store_opening",
            "text": "荷小悦 草本泡脚按摩\n草本真现煮，按出真功夫",
        },
    )

    self.assertEqual(response.status_code, 200)
    body = response.json()
    self.assertEqual(body["version"], "hxy-brand-decision-review.v1")
    self.assertFalse(body["official_use_allowed"])
```

**Step 2: Run test to verify failure**

Run:

```bash
PATH=/root/hxy/.venv/bin:$PATH PYTHONPATH=/root/hxy/apps/api pytest tests/test_hxy_knowledge_api.py -k "brand_decision" -q
```

Expected: FAIL because endpoint is missing.

**Step 3: Implement request model and endpoint**

In `apps/api/hxy_knowledge_api.py`:

- import `review_brand_artifact` and `write_brand_review_record`;
- add `BrandDecisionRequest`;
- add `POST /api/operating-brain/brand-decision/review` with `Depends(require_api_token)`;
- write records under `knowledge/brand/reviews`.

**Step 4: Run focused API test**

Run:

```bash
PATH=/root/hxy/.venv/bin:$PATH PYTHONPATH=/root/hxy/apps/api pytest tests/test_hxy_knowledge_api.py -k "brand_decision" -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add apps/api/hxy_knowledge_api.py tests/test_hxy_knowledge_api.py
git commit -m "feat: expose hxy brand decision api"
```

## Task 6: Add Workbench Contract

**Files:**

- Modify: `apps/admin-web/knowledge.html`
- Modify: `tests/test_hxy_brain_frontend.py`

**Step 1: Write failing static test**

Add:

```python
def test_knowledge_workbench_renders_brand_decision_loop_panel(self):
    html = (ROOT / "apps" / "admin-web" / "knowledge.html").read_text(encoding="utf-8")

    for marker in [
        "首店品牌决策 Loop",
        "不替代 VI/SI 设计",
        'id="brandDecisionText"',
        'id="runBrandDecision"',
        'id="brandDecisionResult"',
        "renderBrandDecisionReview",
        "/api/operating-brain/brand-decision/review",
    ]:
        self.assertIn(marker, html)
```

**Step 2: Run test to verify failure**

Run:

```bash
PATH=/root/hxy/.venv/bin:$PATH pytest tests/test_hxy_brain_frontend.py -k "brand_decision" -q
```

Expected: FAIL until UI is updated.

**Step 3: Add minimal panel**

Add a panel in `knowledge.html`:

- artifact type select;
- text textarea;
- run button;
- result container;
- copy stating the loop does not replace VI/SI design.

**Step 4: Run frontend test**

Run:

```bash
PATH=/root/hxy/.venv/bin:$PATH pytest tests/test_hxy_brain_frontend.py -k "brand_decision" -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add apps/admin-web/knowledge.html tests/test_hxy_brain_frontend.py
git commit -m "feat: show hxy brand decision loop"
```

## Task 7: Full Verification

**Files:**

- No changes unless verification finds a defect.

**Step 1: Run focused tests**

Run:

```bash
PATH=/root/hxy/.venv/bin:$PATH PYTHONPATH=/root/hxy/apps/api pytest tests/test_hxy_brand_decision.py tests/test_hxy_knowledge_api.py -k "brand_decision" -q
PATH=/root/hxy/.venv/bin:$PATH pytest tests/test_hxy_brain_frontend.py -k "brand_decision" -q
```

Expected: PASS.

**Step 2: Run full suite**

Run:

```bash
npm test
```

Expected: Python and TypeScript suites pass.

**Step 3: Inspect diff**

Run:

```bash
git diff --check
git status --short
```

Expected: no whitespace errors. The worktree may contain older dirty HXYOS files; do not stage unrelated files.

## Execution Notes

The current workspace contains many existing uncommitted HXYOS changes. Do not use `git add .`.

If committing is unsafe because unrelated files are dirty, skip commit steps and report the specific files that should be staged later.
