# HXY Core Topic Draft Assets Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Convert HXY core decision topics into non-approved draft business assets that humans can review without seeing raw claim queues.

**Architecture:** Extend the existing knowledge compiler after `build_core_decision_topics` to create `topic-draft-assets.json`. Add a protected read API that exposes these draft assets, and update the knowledge workbench to render a small business workflow instead of internal claim machinery. All outputs remain `needs_review` and `official_use_allowed=false`.

**Tech Stack:** Python knowledge compiler and FastAPI-style API in `apps/api`, static admin HTML/JS in `apps/admin-web`, Python unittest/pytest tests, Vitest frontend checks through `npm test`.

---

### Task 1: Add Compiler Tests For Draft Assets

**Files:**
- Modify: `tests/test_hxy_knowledge_compiler.py`

**Step 1: Write failing tests**

Add tests near the existing core decision topic tests:

```python
def test_build_topic_draft_assets_turns_core_topics_into_review_assets():
    from hxy_knowledge.knowledge_compiler import build_topic_draft_assets

    topics = {
        "version": "hxy-core-decision-topics.v1",
        "items": [
            {
                "version": "hxy-core-decision-topic.v1",
                "topic_id": "hxy-core-topic:brand_positioning",
                "topic_key": "brand_positioning",
                "title": "品牌战略与核爆点定位",
                "decision_question": "这个判断现在能不能作为首店开业和对外口径的依据？",
                "why_it_matters": "定位没定清楚，前台话术、门头、内容和员工训练都会漂。",
                "next_action": "补齐用户原话、复述测试、付费理由和替代方案。",
                "review_owner": "创始人",
                "priority": "P0",
                "evidence_count": 4,
                "source_samples": ["brand.md"],
                "source_classes": ["hxy_project"],
                "official_use_allowed": False,
                "requires_human_review": True,
            }
        ],
    }

    result = build_topic_draft_assets(topics)

    assert result["version"] == "hxy-topic-draft-assets.v1"
    assert result["status"] == "ready"
    assert result["count"] == 1
    asset = result["items"][0]
    assert asset["asset_type"] == "positioning_card"
    assert asset["status"] == "needs_review"
    assert asset["official_use_allowed"] is False
    assert asset["requires_human_review"] is True
    assert asset["authority_rule"] == "draft_assets_are_not_approved_knowledge"
    assert "用户原话" in " ".join(asset["draft"]["evidence_gaps"])


def test_build_topic_draft_assets_keeps_risk_boundary_p0_and_unapproved():
    from hxy_knowledge.knowledge_compiler import build_topic_draft_assets

    topics = {
        "version": "hxy-core-decision-topics.v1",
        "items": [
            {
                "topic_id": "hxy-core-topic:risk_boundary",
                "topic_key": "risk_boundary",
                "title": "合规与功效表达边界",
                "decision_question": "哪些表达必须禁用？",
                "why_it_matters": "医疗化、疗效保证和夸大宣传是最高风险。",
                "next_action": "生成禁用表达、替代表达和发布前预检规则。",
                "review_owner": "运营/合规负责人",
                "priority": "P1",
                "evidence_count": 1,
                "source_samples": ["risk.md"],
                "source_classes": ["risk_compliance"],
            }
        ],
    }

    asset = build_topic_draft_assets(topics)["items"][0]

    assert asset["asset_type"] == "risk_card"
    assert asset["priority"] == "P0"
    assert asset["status"] == "needs_review"
    assert asset["official_use_allowed"] is False
    assert "禁用" in " ".join(asset["draft"]["next_actions"])


def test_build_topic_draft_assets_prefers_evidence_task_for_low_evidence_non_risk_topic():
    from hxy_knowledge.knowledge_compiler import build_topic_draft_assets

    topics = {
        "version": "hxy-core-decision-topics.v1",
        "items": [
            {
                "topic_id": "hxy-core-topic:product_system",
                "topic_key": "product_system",
                "title": "产品服务体系与清泡调补养",
                "decision_question": "员工能不能讲清？",
                "why_it_matters": "产品说不清，菜单、价格、推荐路径和复购都会乱。",
                "next_action": "先确认主服务、组合服务、禁用功效和员工推荐标准话术。",
                "review_owner": "产品/运营负责人",
                "priority": "P0",
                "evidence_count": 1,
                "source_samples": ["product.md"],
                "source_classes": ["hxy_project"],
            }
        ],
    }

    asset = build_topic_draft_assets(topics)["items"][0]

    assert asset["asset_type"] == "evidence_task"
    assert asset["status"] == "needs_review"
    assert "补证据" in asset["draft"]["recommended_use"]
```

Add one compile integration assertion to the existing compile-directory test:

```python
    draft_assets_path = wiki_root / "topic-draft-assets.json"
    assert draft_assets_path.exists()
    draft_assets = json.loads(draft_assets_path.read_text(encoding="utf-8"))
    assert draft_assets["version"] == "hxy-topic-draft-assets.v1"
    assert draft_assets["official_use_allowed"] is False
    assert report["topic_draft_asset_count"] == draft_assets["count"]
    assert report["artifacts"]["topic_draft_assets"]["items"]
```

**Step 2: Run tests to verify RED**

Run:

```bash
PATH=/root/hxy/.venv/bin:$PATH PYTHONPATH=/root/hxy/apps/api pytest tests/test_hxy_knowledge_compiler.py -k "topic_draft_assets or compile_directory_writes_core_decision_topics" -q
```

Expected: FAIL because `build_topic_draft_assets` does not exist or `topic-draft-assets.json` is not written.

### Task 2: Implement Draft Asset Compiler

**Files:**
- Modify: `apps/api/hxy_knowledge/knowledge_compiler.py`
- Test: `tests/test_hxy_knowledge_compiler.py`

**Step 1: Add asset type mapping**

Add near `CORE_DECISION_TOPIC_DEFINITIONS`:

```python
TOPIC_DRAFT_ASSET_TYPES = {
    "brand_positioning": "positioning_card",
    "customer_evidence": "evidence_task",
    "product_system": "script_card",
    "employee_script": "script_card",
    "risk_boundary": "risk_card",
    "first_store_operations": "sop_card",
}
```

**Step 2: Add draft helper functions**

Add helper functions after `build_core_decision_topics`:

```python
def _topic_draft_asset_type(topic: dict[str, Any]) -> str:
    topic_key = str(topic.get("topic_key") or "")
    if topic_key == "risk_boundary":
        return "risk_card"
    evidence_count = int(topic.get("evidence_count") or 0)
    if evidence_count < 2:
        return "evidence_task"
    return TOPIC_DRAFT_ASSET_TYPES.get(topic_key, "evidence_task")


def _topic_draft_payload(topic: dict[str, Any], asset_type: str) -> dict[str, Any]:
    title = str(topic.get("title") or "核心经营议题")
    next_action = str(topic.get("next_action") or "补齐证据后再复核。")
    if asset_type == "risk_card":
        return {
            "summary": f"{title}必须先拆成禁用表达、替代表达和发布前预检规则。",
            "recommended_use": "仅供内部合规复核，不可作为对外正式口径。",
            "evidence_gaps": ["确认禁用表达来源", "补充安全替代表达", "确认适用渠道"],
            "next_actions": ["整理禁用表达", "生成替代表达", "进入人工合规复核"],
        }
    if asset_type == "evidence_task":
        return {
            "summary": f"{title}当前证据不足，应先补证据，不要急着定稿。",
            "recommended_use": "补证据任务，不可作为正式知识引用。",
            "evidence_gaps": ["补齐真实顾客原话", "补齐员工复述结果", "补齐付费理由或替代方案"],
            "next_actions": [next_action],
        }
    return {
        "summary": f"{title}可以先生成草稿资产，但必须人工复核后才能进入正式知识库。",
        "recommended_use": "内部草稿，供人工复核和改写。",
        "evidence_gaps": ["确认来源是否足够", "确认是否可执行", "确认是否存在合规风险"],
        "next_actions": [next_action],
    }
```

**Step 3: Add `build_topic_draft_assets`**

```python
def build_topic_draft_assets(core_decision_topics: dict[str, Any], limit: int = 12) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for topic in core_decision_topics.get("items") or []:
        if not isinstance(topic, dict):
            continue
        topic_key = str(topic.get("topic_key") or "")
        asset_type = _topic_draft_asset_type(topic)
        priority = "P0" if topic_key == "risk_boundary" else str(topic.get("priority") or "P1")
        items.append(
            {
                "version": "hxy-topic-draft-asset.v1",
                "asset_id": f"hxy-topic-draft:{topic_key or _stable_id('topic', str(topic.get('title') or ''))}",
                "topic_id": topic.get("topic_id") or "",
                "topic_key": topic_key,
                "asset_type": asset_type,
                "title": topic.get("title") or "",
                "status": "needs_review",
                "priority": priority,
                "review_owner": topic.get("review_owner") or "",
                "decision_question": topic.get("decision_question") or "",
                "draft": _topic_draft_payload(topic, asset_type),
                "source_samples": list(topic.get("source_samples") or []),
                "source_classes": list(topic.get("source_classes") or []),
                "official_use_allowed": False,
                "requires_human_review": True,
                "authority_rule": "draft_assets_are_not_approved_knowledge",
            }
        )
    public_items = items[: max(0, limit)]
    return {
        "version": "hxy-topic-draft-assets.v1",
        "status": "ready" if public_items else "empty",
        "count": len(public_items),
        "total": len(items),
        "items": public_items,
        "official_use_allowed": False,
        "requires_human_review": True,
        "authority_rule": "draft_assets_are_not_approved_knowledge",
    }
```

**Step 4: Write compiler artifact**

In `compile_directory`, after `core_decision_topics = build_core_decision_topics(...)`, add:

```python
topic_draft_assets = build_topic_draft_assets(core_decision_topics, limit=12)
```

Write:

```python
(wiki_root / "topic-draft-assets.json").write_text(
    json.dumps(topic_draft_assets, ensure_ascii=False, indent=2),
    encoding="utf-8",
)
```

Add to report:

```python
"topic_draft_asset_count": topic_draft_assets["count"],
```

Add to artifacts:

```python
"topic_draft_assets": topic_draft_assets,
```

Add to `write_harness_run`:

```python
"11_topic_draft_assets.json": artifacts.get("topic_draft_assets") or {"version": "hxy-topic-draft-assets.v1", "items": []},
```

**Step 5: Run compiler tests**

Run:

```bash
PATH=/root/hxy/.venv/bin:$PATH PYTHONPATH=/root/hxy/apps/api pytest tests/test_hxy_knowledge_compiler.py -k "topic_draft_assets or compile_directory_writes_core_decision_topics" -q
```

Expected: PASS.

**Step 6: Commit**

```bash
git add apps/api/hxy_knowledge/knowledge_compiler.py tests/test_hxy_knowledge_compiler.py
git commit -m "feat: compile core topic draft assets"
```

### Task 3: Add Topic Draft Assets API Tests

**Files:**
- Modify: `tests/test_hxy_knowledge_api.py`

**Step 1: Write failing API test**

Add near `review_topics` tests:

```python
def test_operating_brain_compiler_topic_draft_assets_returns_unapproved_assets(self):
    module, tempdir = self.load_module()
    wiki_root = Path(tempdir.name) / "knowledge" / "wiki"
    wiki_root.mkdir(parents=True, exist_ok=True)
    (wiki_root / "topic-draft-assets.json").write_text(
        json.dumps(
            {
                "version": "hxy-topic-draft-assets.v1",
                "status": "ready",
                "count": 1,
                "total": 1,
                "items": [
                    {
                        "version": "hxy-topic-draft-asset.v1",
                        "asset_id": "hxy-topic-draft:brand_positioning",
                        "topic_id": "hxy-core-topic:brand_positioning",
                        "topic_key": "brand_positioning",
                        "asset_type": "positioning_card",
                        "title": "品牌战略与核爆点定位",
                        "status": "needs_review",
                        "priority": "P0",
                        "review_owner": "创始人",
                        "decision_question": "这个判断现在能不能作为首店开业和对外口径的依据？",
                        "draft": {
                            "summary": "先做内部复核。",
                            "recommended_use": "内部草稿，供人工复核和改写。",
                            "evidence_gaps": ["补齐目标用户原话"],
                            "next_actions": ["完成访谈"],
                        },
                        "source_samples": ["brand.md"],
                        "official_use_allowed": False,
                        "requires_human_review": True,
                        "authority_rule": "draft_assets_are_not_approved_knowledge",
                    }
                ],
                "official_use_allowed": False,
                "requires_human_review": True,
                "authority_rule": "draft_assets_are_not_approved_knowledge",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    response = TestClient(module.app).get("/api/operating-brain/knowledge-compiler/topic-draft-assets?limit=5")
    body = response.json()

    self.assertEqual(response.status_code, 200)
    self.assertEqual(body["version"], "hxy-topic-draft-assets.v1")
    self.assertEqual(body["count"], 1)
    self.assertEqual(body["items"][0]["asset_type"], "positioning_card")
    self.assertEqual(body["items"][0]["status"], "needs_review")
    self.assertFalse(body["official_use_allowed"])
    self.assertTrue(body["requires_human_review"])
```

**Step 2: Run test to verify RED**

Run:

```bash
PATH=/root/hxy/.venv/bin:$PATH PYTHONPATH=/root/hxy/apps/api pytest tests/test_hxy_knowledge_api.py -k "topic_draft_assets" -q
```

Expected: FAIL with 404 or missing route.

### Task 4: Implement Topic Draft Assets API

**Files:**
- Modify: `apps/api/hxy_knowledge_api.py`
- Test: `tests/test_hxy_knowledge_api.py`

**Step 1: Add payload sanitizer**

Near `_compiler_core_decision_topics_from_payload`, add:

```python
def _compiler_topic_draft_assets_from_payload(payload: dict[str, Any] | None, *, limit: int) -> dict[str, Any]:
    if not payload:
        return {
            "version": "hxy-topic-draft-assets.v1",
            "status": "missing",
            "count": 0,
            "total": 0,
            "items": [],
            "official_use_allowed": False,
            "requires_human_review": True,
            "authority_rule": "draft_assets_are_not_approved_knowledge",
            "next_actions": ["运行知识编译器生成 knowledge/wiki/topic-draft-assets.json。"],
        }
    items = []
    for item in payload.get("items") or []:
        if not isinstance(item, dict):
            continue
        public = {
            "version": item.get("version") or "hxy-topic-draft-asset.v1",
            "asset_id": item.get("asset_id") or "",
            "topic_id": item.get("topic_id") or "",
            "topic_key": item.get("topic_key") or "",
            "asset_type": item.get("asset_type") or "evidence_task",
            "title": item.get("title") or "",
            "status": "needs_review",
            "priority": item.get("priority") or "P1",
            "review_owner": item.get("review_owner") or "",
            "decision_question": item.get("decision_question") or "",
            "draft": item.get("draft") if isinstance(item.get("draft"), dict) else {},
            "source_samples": [_source_label(source) for source in (item.get("source_samples") or [])],
            "official_use_allowed": False,
            "requires_human_review": True,
            "authority_rule": "draft_assets_are_not_approved_knowledge",
        }
        items.append(public)
    public_items = items[:limit]
    return {
        "version": "hxy-topic-draft-assets.v1",
        "status": payload.get("status") or ("ready" if items else "empty"),
        "count": len(public_items),
        "total": int(payload.get("total") or len(items)),
        "items": public_items,
        "official_use_allowed": False,
        "requires_human_review": True,
        "authority_rule": "draft_assets_are_not_approved_knowledge",
    }
```

**Step 2: Add GET route**

Near the existing `/api/operating-brain/knowledge-compiler/review-topics` route, add:

```python
@app.get("/api/operating-brain/knowledge-compiler/topic-draft-assets")
def operating_brain_compiler_topic_draft_assets(
    limit: int = Query(12, ge=1, le=50),
    _: None = Depends(require_api_token),
):
    payload = _read_json_file(_knowledge_path("wiki/topic-draft-assets.json"))
    return _compiler_topic_draft_assets_from_payload(payload, limit=limit)
```

**Step 3: Run API tests**

Run:

```bash
PATH=/root/hxy/.venv/bin:$PATH PYTHONPATH=/root/hxy/apps/api pytest tests/test_hxy_knowledge_api.py -k "topic_draft_assets or review_topics" -q
```

Expected: PASS.

**Step 4: Commit**

```bash
git add apps/api/hxy_knowledge_api.py tests/test_hxy_knowledge_api.py
git commit -m "feat: expose core topic draft assets"
```

### Task 5: Add Frontend Test For Draft Asset Workflow

**Files:**
- Modify: `tests/test_hxy_brain_frontend.py`

**Step 1: Write failing frontend test**

Add a test near the knowledge page tests:

```python
def test_knowledge_workbench_renders_core_topic_draft_asset_workflow(self):
    page = ROOT / "apps" / "admin-web" / "knowledge.html"
    html = page.read_text(encoding="utf-8")

    for label in [
        "议题转资产",
        "建议资产",
        "定位卡",
        "话术卡",
        "SOP卡",
        "风险边界卡",
        "补证据任务",
        "待人工复核",
        "renderTopicDraftAssets",
        "loadTopicDraftAssets",
        "/api/operating-brain/knowledge-compiler/topic-draft-assets?limit=12",
    ]:
        self.assertIn(label, html)

    draft_start = html.index("议题转资产")
    draft_end = html.index("合规审核包", draft_start) if "合规审核包" in html[draft_start:] else draft_start + 4000
    draft_html = html[draft_start:draft_end]
    for forbidden in ["raw claim", "chunk_id", "cluster_id", "review queue", "needs_review"]:
        self.assertNotIn(forbidden, draft_html)
```

**Step 2: Run test to verify RED**

Run:

```bash
PATH=/root/hxy/.venv/bin:$PATH pytest tests/test_hxy_brain_frontend.py -k "topic_draft_asset" -q
```

Expected: FAIL because the page does not render the draft asset workflow.

### Task 6: Implement Knowledge Page Draft Asset Workflow

**Files:**
- Modify: `apps/admin-web/knowledge.html`
- Test: `tests/test_hxy_brain_frontend.py`

**Step 1: Add UI block**

Add a section near the core operating topics block:

```html
<section class="panel" id="topicDraftAssetsPanel">
  <div class="panel-head">
    <div>
      <span class="eyebrow">议题转资产</span>
      <h2>核心议题应该沉淀成什么</h2>
      <p>只生成草稿和补证据任务，停在待人工复核，不发布正式知识。</p>
    </div>
    <button type="button" class="ghost" id="refreshTopicDraftAssetsButton">刷新</button>
  </div>
  <div class="topic-draft-assets" id="topicDraftAssetsList">
    <div class="empty">还没有草稿资产。先运行资料编译。</div>
  </div>
</section>
```

Use existing classes where possible. Add small CSS only if needed; do not redesign the page.

**Step 2: Add JavaScript helpers**

Add:

```javascript
const topicDraftAssetsList = document.querySelector("#topicDraftAssetsList");
const refreshTopicDraftAssetsButton = document.querySelector("#refreshTopicDraftAssetsButton");

const assetTypeLabels = {
  positioning_card: "定位卡",
  script_card: "话术卡",
  sop_card: "SOP卡",
  risk_card: "风险边界卡",
  evidence_task: "补证据任务"
};

function renderTopicDraftAssets(payload) {
  if (!topicDraftAssetsList) return;
  const items = payload.items || [];
  if (!items.length) {
    topicDraftAssetsList.innerHTML = `<div class="empty">还没有草稿资产。先运行资料编译。</div>`;
    return;
  }
  topicDraftAssetsList.innerHTML = items.map((item) => {
    const draft = item.draft || {};
    const gaps = draft.evidence_gaps || [];
    const actions = draft.next_actions || [];
    return `
      <article class="review-topic-card">
        <div class="review-topic-topline">
          <span>${escapeHtml(item.priority || "P1")}</span>
          <span>${escapeHtml(assetTypeLabels[item.asset_type] || "补证据任务")}</span>
          <span>待人工复核</span>
        </div>
        <h3>${escapeHtml(item.title || "核心经营议题")}</h3>
        <div class="review-topic-section"><strong>先判断</strong><span>${escapeHtml(item.decision_question || "")}</span></div>
        <div class="review-topic-section"><strong>证据缺口</strong><span>${escapeHtml(gaps.join(" / ") || "暂无")}</span></div>
        <div class="review-topic-section"><strong>下一步</strong><span>${escapeHtml(actions.join(" / ") || "等待复核")}</span></div>
      </article>
    `;
  }).join("");
}

async function loadTopicDraftAssets() {
  const payload = await requestJson("/api/operating-brain/knowledge-compiler/topic-draft-assets?limit=12");
  renderTopicDraftAssets(payload);
}
```

Hook into existing initial load:

```javascript
loadTopicDraftAssets()
```

and refresh button:

```javascript
refreshTopicDraftAssetsButton?.addEventListener("click", loadTopicDraftAssets);
```

**Step 3: Run frontend test**

Run:

```bash
PATH=/root/hxy/.venv/bin:$PATH pytest tests/test_hxy_brain_frontend.py -k "topic_draft_asset or knowledge" -q
```

Expected: PASS.

**Step 4: Commit**

```bash
git add apps/admin-web/knowledge.html tests/test_hxy_brain_frontend.py
git commit -m "feat: show core topic draft asset workflow"
```

### Task 7: Full Verification And Merge Prep

**Files:**
- No code changes expected.

**Step 1: Run full test suite**

```bash
npm test
```

Expected: Python and Vitest pass.

**Step 2: Run benchmark**

```bash
.venv/bin/python scripts/run-hxy-brain-benchmark.py --benchmark knowledge/benchmarks/hxy-brain-benchmark-v1.json --output /tmp/hxy-brain-benchmark-topic-draft-assets.json
```

Expected: command exits 0 and JSON `pass_rate >= 0.85`.

**Step 3: Run release checks**

```bash
python3 scripts/check-hxy-secrets.py
python3 scripts/check-hxy-public-release.py
git diff --check main..HEAD
```

Expected:

```text
No committed or commit-eligible HXY secrets found.
public_release_preflight_ok=true
```

**Step 4: Inspect tracked files**

```bash
git status --short --branch
git ls-tree -r --name-only HEAD | rg '^(knowledge/raw|knowledge/reports|knowledge/runs|knowledge/wiki|node_modules|\\.venv)(/|$)' || true
```

Expected: no private knowledge, virtualenv, or node_modules paths are tracked.

**Step 5: Commit any final docs if needed**

If only the implementation plan is uncommitted:

```bash
git add docs/plans/2026-07-08-hxy-core-topic-draft-assets.md
git commit -m "docs: plan core topic draft assets"
```

**Step 6: Merge and push**

After all tests pass:

```bash
cd /root/hxy
git merge --ff-only feature/hxy-core-topic-draft-assets
npm test
.venv/bin/python scripts/run-hxy-brain-benchmark.py --benchmark knowledge/benchmarks/hxy-brain-benchmark-v1.json --output /tmp/hxy-brain-benchmark-topic-draft-assets-main.json
python3 scripts/check-hxy-secrets.py
python3 scripts/check-hxy-public-release.py
git push origin main
git worktree remove /root/hxy/.worktrees/hxy-core-topic-draft-assets
git branch -d feature/hxy-core-topic-draft-assets
```

Expected: main pushed to `zzzai/hxyos`, worktree removed, feature branch deleted.
