# HXY Compliance Language Check Execution Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add an executable `hxy-compliance-language-check` Skill that checks external-facing copy and returns a governed business decision without using a model or publishing approved knowledge.

**Architecture:** Reuse the existing HXY-owned FastAPI service and `hxy_knowledge.compliance_rules.check_brand_risk_text`. Add a read-only Skill run endpoint that maps deterministic rule hits into `allow`, `revise`, or `block`, then expose it in the existing admin knowledge page as a minimal execution panel. Keep all results non-official and non-publishing.

**Tech Stack:** Python FastAPI, existing `apps/api/hxy_knowledge_api.py`, existing `apps/api/hxy_knowledge/compliance_rules.py`, static HTML/JS admin page, pytest, Node syntax smoke test.

---

## Constraints

- Scope is `/root/hxy` only.
- Do not touch `/root/htops`.
- Do not introduce `HETANG_*` fallback.
- Do not call an LLM in V1.
- Do not write to database or files from the Skill run endpoint.
- Do not publish or modify approved answer cards.
- Do not expose absolute `/root/hxy` paths.
- Do not expose raw compiler artifacts such as `chunk_id`, `cluster_member_count`, or `sample_claims`.
- Keep frontend changes minimal and admin-only.

## Task 1: Add Backend Skill Execution Endpoint

**Files:**
- Modify: `apps/api/hxy_knowledge_api.py`
- Test: `tests/test_hxy_knowledge_api.py`

**Step 1: Write failing tests**

Add tests near the product object API tests in `tests/test_hxy_knowledge_api.py`:

```python
    def test_compliance_language_check_blocks_medical_claims(self):
        response = self.client.post(
            "/api/operating-brain/skills/hxy-compliance-language-check/run",
            json={
                "text": "泡脚能治疗失眠，睡不好来做一次就能好。",
                "channel": "朋友圈",
                "audience": "customer",
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["version"], "hxy-compliance-language-check-result.v1")
        self.assertEqual(body["skill_id"], "hxy-compliance-language-check")
        self.assertEqual(body["decision"], "block")
        self.assertIn("medical_claim", body["hit_gates"])
        self.assertFalse(body["can_publish"])
        self.assertFalse(body["official_use_allowed"])
        self.assertTrue(body["review_required"])
        self.assertIn("rewrite_suggestion", body)
        self.assertNotIn("/root/hxy", json.dumps(body, ensure_ascii=False))

    def test_compliance_language_check_blocks_guaranteed_effect(self):
        response = self.client.post(
            "/api/operating-brain/skills/hxy-compliance-language-check/run",
            json={
                "text": "这个项目一周保证见效，调理一次就有疗效。",
                "channel": "团购页",
                "audience": "customer",
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["decision"], "block")
        self.assertIn("guaranteed_effect", body["hit_gates"])
        self.assertFalse(body["can_publish"])
        self.assertFalse(body["official_use_allowed"])

    def test_compliance_language_check_allows_low_risk_copy(self):
        response = self.client.post(
            "/api/operating-brain/skills/hxy-compliance-language-check/run",
            json={
                "text": "草本现煮，泡着舒服，适合下班后来放松一下。",
                "channel": "海报",
                "audience": "customer",
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["decision"], "allow")
        self.assertEqual(body["risk_level"], "none")
        self.assertEqual(body["hit_gates"], [])
        self.assertFalse(body["can_publish"])
        self.assertFalse(body["official_use_allowed"])
        self.assertFalse(body["review_required"])
```

**Step 2: Run tests to verify they fail**

Run:

```bash
.venv/bin/pytest -q tests/test_hxy_knowledge_api.py -k "compliance_language_check"
```

Expected: FAIL with `404 != 200` for the new endpoint.

**Step 3: Add request model**

In `apps/api/hxy_knowledge_api.py`, add a Pydantic model near other request models:

```python
class ComplianceLanguageCheckRequest(BaseModel):
    text: str = ""
    channel: str = "unknown"
    audience: str = "customer"
```

**Step 4: Import the deterministic checker**

Change the compliance import:

```python
from hxy_knowledge.compliance_rules import check_brand_risk_text, load_brand_risk_rules
```

**Step 5: Add mapper helper**

Add helper functions near the product object catalog helpers:

```python
RISK_GATE_BY_RULE_TYPE = {
    "医疗": "medical_claim",
    "保证": "guaranteed_effect",
    "夸大": "overstatement",
}


def _source_label_for_rule(source: Any) -> str:
    value = str(source or "").strip()
    return Path(value).name if value else "默认风险规则"


def _compliance_language_check_result(
    request: ComplianceLanguageCheckRequest,
    *,
    root_dir: Path,
) -> dict[str, Any]:
    raw_result = check_brand_risk_text(request.text, root_dir=root_dir)
    hits = raw_result.get("hits") or []
    hit_gates = []
    evidence = []
    for hit in hits:
        gate = RISK_GATE_BY_RULE_TYPE.get(str(hit.get("type") or ""), "language_risk")
        if gate not in hit_gates:
            hit_gates.append(gate)
        evidence.append(
            {
                "rule_name": f"{hit.get('type') or '表达'}风险规则",
                "level": hit.get("level") or "warn",
                "matched_terms": hit.get("words") or [],
                "advice": hit.get("advice") or "",
            }
        )

    has_bad = any(str(hit.get("level") or "") == "bad" for hit in hits)
    has_medical = "medical_claim" in hit_gates
    if has_medical:
        risk_level = "p0"
    elif has_bad:
        risk_level = "high"
    elif hits:
        risk_level = "medium"
    else:
        risk_level = "none"
    decision = "block" if has_bad else "revise" if hits else "allow"
    review_required = decision != "allow"
    rewrite_suggestion = (
        "可以改成：草本现煮，泡着舒服，适合下班后放松。不要承诺治疗、见效或保证结果。"
        if decision != "allow"
        else "当前表达相对克制。正式发布前仍建议按渠道负责人要求复核。"
    )

    rule_payload = load_brand_risk_rules(root_dir=root_dir)
    source_labels = [_source_label_for_rule(source) for source in rule_payload.get("source_paths") or []]
    if not source_labels:
        source_labels = ["默认风险规则"]
    for item in evidence:
        item["source"] = source_labels[0]

    return {
        "version": "hxy-compliance-language-check-result.v1",
        "skill_id": "hxy-compliance-language-check",
        "channel": request.channel,
        "audience": request.audience,
        "decision": decision,
        "risk_level": risk_level,
        "hit_gates": hit_gates,
        "can_publish": False,
        "official_use_allowed": False,
        "review_required": review_required,
        "rewrite_suggestion": rewrite_suggestion,
        "evidence": evidence,
        "authority_rule": "skill_output_is_not_official_and_cannot_publish_approved_knowledge",
    }
```

**Step 6: Add endpoint**

Near the existing `/api/operating-brain/skills` endpoint, add:

```python
    @app.post("/api/operating-brain/skills/hxy-compliance-language-check/run")
    async def operating_brain_compliance_language_check_run_endpoint(
        request: ComplianceLanguageCheckRequest,
    ) -> dict[str, Any]:
        if not request.text.strip():
            raise HTTPException(status_code=400, detail="text is required")
        return _compliance_language_check_result(request, root_dir=resolved_root)
```

**Step 7: Run tests to verify they pass**

Run:

```bash
.venv/bin/pytest -q tests/test_hxy_knowledge_api.py -k "compliance_language_check"
```

Expected: PASS.

**Step 8: Commit**

```bash
git add apps/api/hxy_knowledge_api.py tests/test_hxy_knowledge_api.py
git commit -m "feat: run compliance language check skill"
```

## Task 2: Add Admin Execution Panel

**Files:**
- Modify: `apps/admin-web/knowledge.html`
- Test: `tests/test_hxy_brain_frontend.py`

**Step 1: Write failing frontend test**

Add to `tests/test_hxy_brain_frontend.py` near the knowledge page tests:

```python
    def test_knowledge_page_exposes_compliance_language_check_execution_panel(self):
        html = (ROOT / "apps" / "admin-web" / "knowledge.html").read_text(encoding="utf-8")

        for label in [
            "对外话语检查",
            "这句话能不能发",
            "id=\"complianceTextInput\"",
            "id=\"complianceChannelSelect\"",
            "id=\"complianceLanguageCheckResult\"",
            "id=\"runComplianceLanguageCheck\"",
            "runComplianceLanguageCheck",
            "renderComplianceLanguageCheckResult",
            "/api/operating-brain/skills/hxy-compliance-language-check/run",
            "可以发",
            "建议改",
            "不要发",
        ]:
            self.assertIn(label, html)

        for forbidden in [
            "批准为正式知识",
            "发布 approved",
            "cluster_member_count",
            "sample_claims",
            "chunk_id",
        ]:
            self.assertNotIn(forbidden, html)
```

**Step 2: Run test to verify it fails**

Run:

```bash
.venv/bin/pytest -q tests/test_hxy_brain_frontend.py::HxyBrainFrontendTest::test_knowledge_page_exposes_compliance_language_check_execution_panel
```

Expected: FAIL because the panel does not exist.

**Step 3: Add panel markup**

In `apps/admin-web/knowledge.html`, add a panel near the top of the advanced tool grid, before the ingest loop panels:

```html
      <div class="panel full">
        <div class="panel-header">
          <div class="panel-title">对外话语检查 <small>这句话能不能发</small></div>
          <button class="primary" id="runComplianceLanguageCheck" type="button">检查</button>
        </div>
        <div class="panel-body actions">
          <div class="search-tools">
            <label style="grid-column: span 3;">
              待检查内容
              <textarea id="complianceTextInput">草本现煮，泡着舒服，适合下班后来放松一下。</textarea>
            </label>
            <label>
              使用场景
              <select id="complianceChannelSelect">
                <option value="朋友圈">朋友圈</option>
                <option value="团购页">团购页</option>
                <option value="海报">海报</option>
                <option value="员工话术">员工话术</option>
              </select>
            </label>
          </div>
          <div id="complianceLanguageCheckResult" class="result">粘贴准备发出去的话，系统只做风险检查，不发布正式知识。</div>
        </div>
      </div>
```

**Step 4: Add DOM constants and render function**

In the script constants area:

```javascript
    const complianceLanguageCheckResult = document.querySelector("#complianceLanguageCheckResult");
```

Add:

```javascript
    function renderComplianceLanguageCheckResult(payload) {
      const labelByDecision = {
        allow: "可以发",
        revise: "建议改",
        block: "不要发",
      };
      const gates = (payload.hit_gates || []).join("、") || "无命中";
      const evidence = (payload.evidence || []).slice(0, 3).map((item) => (
        `<span class="tag">${escapeHtml(item.rule_name || "")} · ${escapeHtml(item.source || "")}</span>`
      )).join("");
      complianceLanguageCheckResult.className = `result ${payload.decision === "allow" ? "ok" : payload.decision === "block" ? "error" : ""}`;
      complianceLanguageCheckResult.innerHTML = `
        <strong>${escapeHtml(labelByDecision[payload.decision] || "建议改")} · ${escapeHtml(payload.risk_level || "")}</strong>
        <div>风险门：${escapeHtml(gates)}</div>
        <div>${escapeHtml(payload.rewrite_suggestion || "")}</div>
        <div>can_publish: ${String(Boolean(payload.can_publish))} · official_use_allowed: ${String(Boolean(payload.official_use_allowed))}</div>
        ${evidence ? `<div class="review-actions">${evidence}</div>` : ""}
      `;
    }
```

**Step 5: Add run function and listener**

Add:

```javascript
    async function runComplianceLanguageCheck() {
      const text = document.querySelector("#complianceTextInput").value.trim();
      if (!text) {
        complianceLanguageCheckResult.className = "result error";
        complianceLanguageCheckResult.textContent = "请输入待检查内容";
        return;
      }
      try {
        const payload = await requestJson("/api/operating-brain/skills/hxy-compliance-language-check/run", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            text,
            channel: document.querySelector("#complianceChannelSelect").value,
            audience: "customer",
          }),
        });
        renderComplianceLanguageCheckResult(payload);
        setResult("对外话语检查完成。结果不是正式知识，不能自动发布。", "ok");
      } catch (error) {
        complianceLanguageCheckResult.className = "result error";
        complianceLanguageCheckResult.textContent = error.message;
        setResult(error.message, "error");
      }
    }
```

Add listener:

```javascript
    document.querySelector("#runComplianceLanguageCheck").addEventListener("click", runComplianceLanguageCheck);
```

**Step 6: Run frontend test and script syntax check**

Run:

```bash
.venv/bin/pytest -q tests/test_hxy_brain_frontend.py::HxyBrainFrontendTest::test_knowledge_page_exposes_compliance_language_check_execution_panel
node - <<'NODE'
const fs = require('fs');
const html = fs.readFileSync('apps/admin-web/knowledge.html','utf8');
const script = html.split('<script>', 2)[1].split('</script>', 1)[0];
new Function(script);
console.log('script_ok');
NODE
```

Expected: PASS and `script_ok`.

**Step 7: Commit**

```bash
git add apps/admin-web/knowledge.html tests/test_hxy_brain_frontend.py
git commit -m "feat: add compliance language check panel"
```

## Task 3: End-To-End Verification

**Files:**
- No new files.

**Step 1: Restore local test symlinks if needed**

If the worktree does not have local ignored runtime assets, run:

```bash
test -e .venv || ln -s /root/hxy/.venv .venv
test -e knowledge/raw || ln -s /root/hxy/knowledge/raw knowledge/raw
```

These are ignored local symlinks and must not be committed.

**Step 2: Run full test suite**

Run:

```bash
npm test
```

Expected: all pytest and vitest tests pass.

**Step 3: Run benchmark**

Run:

```bash
.venv/bin/python scripts/run-hxy-brain-benchmark.py --benchmark knowledge/benchmarks/hxy-brain-benchmark-v1.json --output /tmp/hxy-brain-benchmark-compliance-language-check.json
python3 - <<'PY'
import json
from pathlib import Path
report = json.loads(Path('/tmp/hxy-brain-benchmark-compliance-language-check.json').read_text(encoding='utf-8'))
print(report.get('pass_rate'))
PY
```

Expected: pass rate is `>= 0.85`.

**Step 4: Run safety checks**

Run:

```bash
python3 scripts/check-hxy-secrets.py
python3 scripts/check-hxy-public-release.py
git diff --check
```

Expected: all pass.

**Step 5: Manual API smoke**

Run:

```bash
scripts/start-hxy-knowledge-api.sh --restart
curl -fsS http://127.0.0.1:18081/api/operating-brain/skills/hxy-compliance-language-check/run \
  -H 'Content-Type: application/json' \
  -d '{"text":"泡脚能治疗失眠","channel":"朋友圈","audience":"customer"}' \
  | python3 -m json.tool | sed -n '1,120p'
```

Expected:

- `decision` is `block`;
- `hit_gates` includes `medical_claim`;
- `can_publish` is `false`;
- `official_use_allowed` is `false`;
- no absolute `/root/hxy` appears.

**Step 6: Commit any final verification-only adjustments**

If no files changed, do not commit. If small test/documentation corrections were required, commit them with:

```bash
git add <files>
git commit -m "test: verify compliance language check execution"
```
