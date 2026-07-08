# HXY Topic Review Packets Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Turn HXY topic draft assets into read-only review packets that tell humans who reviews, what to check, which decisions are allowed, and what cannot be done.

**Architecture:** Extend the existing knowledge compiler after `build_topic_draft_assets` to write `topic-review-packets.json`. Add a read-only API endpoint and a small knowledge workbench panel. V1 does not store human decisions and cannot approve or publish knowledge.

**Tech Stack:** Python compiler and API in `apps/api`, static HTML/JS workbench in `apps/admin-web/knowledge.html`, pytest/unittest, Vitest through `npm test`.

---

### Task 1: Add Compiler Tests For Review Packets

**Files:**
- Modify: `tests/test_hxy_knowledge_compiler.py`

**Step 1: Write failing tests**

Add tests near the existing topic draft asset tests:

```python
def test_build_topic_review_packets_turns_draft_assets_into_human_tasks():
    from apps.api.hxy_knowledge.knowledge_compiler import build_topic_review_packets

    draft_assets = {
        "version": "hxy-topic-draft-assets.v1",
        "items": [
            {
                "version": "hxy-topic-draft-asset.v1",
                "asset_id": "hxy-topic-draft:brand_positioning",
                "topic_key": "brand_positioning",
                "asset_type": "positioning_card",
                "title": "品牌战略与核爆点定位",
                "status": "needs_review",
                "priority": "P0",
                "review_owner": "创始人",
                "decision_question": "这个判断现在能不能作为首店开业和对外口径的依据？",
                "draft": {
                    "evidence_gaps": ["补齐目标用户原话"],
                    "next_actions": ["完成访谈"],
                },
                "source_samples": ["brand.md"],
            }
        ],
    }

    packets = build_topic_review_packets(draft_assets)

    assert packets["version"] == "hxy-topic-review-packets.v1"
    assert packets["status"] == "ready"
    assert packets["count"] == 1
    packet = packets["items"][0]
    assert packet["version"] == "hxy-topic-review-packet.v1"
    assert packet["packet_id"] == "hxy-topic-review-packet:brand_positioning"
    assert packet["status"] == "open"
    assert packet["promotion_target"] == "approved_positioning_card"
    assert packet["decision_options"] == [
        "needs_more_evidence",
        "revise_draft",
        "ready_for_manual_approval",
        "reject",
    ]
    assert "真实顾客原话" in " ".join(packet["review_questions"])
    assert "不能自动发布" in packet["blocked_actions"]
    assert packet["official_use_allowed"] is False
    assert packet["requires_human_review"] is True


def test_build_topic_review_packets_keeps_risk_cards_blocked_and_p0():
    from apps.api.hxy_knowledge.knowledge_compiler import build_topic_review_packets

    draft_assets = {
        "version": "hxy-topic-draft-assets.v1",
        "items": [
            {
                "asset_id": "hxy-topic-draft:risk_boundary",
                "topic_key": "risk_boundary",
                "asset_type": "risk_card",
                "title": "合规与功效表达边界",
                "priority": "P1",
                "review_owner": "运营/合规负责人",
                "decision_question": "哪些表达必须禁用？",
                "draft": {
                    "evidence_gaps": ["确认禁用表达来源"],
                    "next_actions": ["整理禁用表达"],
                },
                "source_samples": ["risk.md"],
            }
        ],
    }

    packet = build_topic_review_packets(draft_assets)["items"][0]

    assert packet["priority"] == "P0"
    assert packet["promotion_target"] == "approved_risk_boundary_card"
    assert "禁用表达" in " ".join(packet["review_questions"])
    assert "不能写入 approved answer cards" in packet["blocked_actions"]
    assert packet["official_use_allowed"] is False
```

Add integration assertions to `test_compile_directory_writes_core_decision_topics_before_claim_review_queue`:

```python
assert (wiki_dir / "topic-review-packets.json").is_file()
review_packets = json.loads((wiki_dir / "topic-review-packets.json").read_text(encoding="utf-8"))
assert review_packets["version"] == "hxy-topic-review-packets.v1"
assert review_packets["official_use_allowed"] is False
assert report["topic_review_packet_count"] == review_packets["count"]
assert report["artifacts"]["topic_review_packets"]["items"]
```

**Step 2: Run tests to verify RED**

```bash
PATH=/root/hxy/.venv/bin:$PATH PYTHONPATH=/root/hxy/apps/api pytest tests/test_hxy_knowledge_compiler.py -k "topic_review_packets or compile_directory_writes_core_decision_topics" -q
```

Expected: FAIL because `build_topic_review_packets` and artifact writing do not exist.

### Task 2: Implement Review Packet Compiler

**Files:**
- Modify: `apps/api/hxy_knowledge/knowledge_compiler.py`
- Test: `tests/test_hxy_knowledge_compiler.py`

**Step 1: Add constants and helpers**

Add near topic draft asset constants:

```python
REVIEW_PACKET_DECISION_OPTIONS = [
    "needs_more_evidence",
    "revise_draft",
    "ready_for_manual_approval",
    "reject",
]

PROMOTION_TARGETS = {
    "positioning_card": "approved_positioning_card",
    "script_card": "approved_script_card",
    "sop_card": "approved_sop_card",
    "risk_card": "approved_risk_boundary_card",
    "evidence_task": "evidence_backlog",
}
```

Add helper:

```python
def _review_questions_for_asset(asset: dict[str, Any]) -> list[str]:
    asset_type = str(asset.get("asset_type") or "evidence_task")
    if asset_type == "positioning_card":
        return [
            "这个判断是否有真实顾客原话支撑？",
            "员工能否不用创始人解释就讲清？",
            "顾客听完能否复述，并说出为什么愿意付费？",
        ]
    if asset_type == "script_card":
        return [
            "员工能否在 30 秒内讲清且不说过头？",
            "顾客能否复述核心意思？",
            "是否避开医疗、保证效果和夸大表达？",
        ]
    if asset_type == "sop_card":
        return [
            "这套动作是否有明确负责人？",
            "首店现场是否能按步骤执行？",
            "复盘指标和失败处理是否清楚？",
        ]
    if asset_type == "risk_card":
        return [
            "哪些表达必须禁用？",
            "对应的安全替代表达是什么？",
            "适用于哪些渠道和岗位？",
        ]
    return [
        "缺哪些证据？",
        "谁负责补证据？",
        "什么时候回到复核流程？",
    ]
```

**Step 2: Add `build_topic_review_packets`**

```python
def build_topic_review_packets(topic_draft_assets: dict[str, Any], limit: int = 12) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for asset in topic_draft_assets.get("items") or []:
        if not isinstance(asset, dict):
            continue
        asset_type = str(asset.get("asset_type") or "evidence_task")
        topic_key = str(asset.get("topic_key") or "")
        draft = asset.get("draft") if isinstance(asset.get("draft"), dict) else {}
        packet_key = topic_key or str(asset.get("asset_id") or _stable_id("review-packet", str(asset.get("title") or "")))
        priority = "P0" if asset_type == "risk_card" else str(asset.get("priority") or "P1")
        items.append(
            {
                "version": "hxy-topic-review-packet.v1",
                "packet_id": f"hxy-topic-review-packet:{packet_key}",
                "asset_id": asset.get("asset_id") or "",
                "topic_key": topic_key,
                "asset_type": asset_type,
                "title": asset.get("title") or "",
                "priority": priority,
                "review_owner": asset.get("review_owner") or "运营负责人",
                "status": "open",
                "review_questions": _review_questions_for_asset(asset),
                "evidence_gaps": list(draft.get("evidence_gaps") or []),
                "next_actions": list(draft.get("next_actions") or []),
                "decision_options": list(REVIEW_PACKET_DECISION_OPTIONS),
                "promotion_target": PROMOTION_TARGETS.get(asset_type, "evidence_backlog"),
                "blocked_actions": [
                    "不能作为对外正式口径",
                    "不能写入 approved answer cards",
                    "不能自动发布",
                ],
                "source_samples": list(asset.get("source_samples") or []),
                "official_use_allowed": False,
                "requires_human_review": True,
                "authority_rule": "review_packets_are_tasks_not_approval",
            }
        )
    public_items = items[: max(0, limit)]
    return {
        "version": "hxy-topic-review-packets.v1",
        "status": "ready" if public_items else "empty",
        "count": len(public_items),
        "total": len(items),
        "items": public_items,
        "official_use_allowed": False,
        "requires_human_review": True,
        "authority_rule": "review_packets_are_tasks_not_approval",
    }
```

**Step 3: Write compiler artifact**

In `compile_directory`, after `topic_draft_assets`, add `topic_review_packets = build_topic_review_packets(topic_draft_assets, limit=12)`.

Write `topic-review-packets.json`, add `topic_review_packet_count` to the report, add `topic_review_packets` to artifacts, and add `12_topic_review_packets.json` to `write_harness_run`.

**Step 4: Run tests**

```bash
PATH=/root/hxy/.venv/bin:$PATH PYTHONPATH=/root/hxy/apps/api pytest tests/test_hxy_knowledge_compiler.py -k "topic_review_packets or compile_directory_writes_core_decision_topics" -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add apps/api/hxy_knowledge/knowledge_compiler.py tests/test_hxy_knowledge_compiler.py
git commit -m "feat: compile topic review packets"
```

### Task 3: Add Review Packet API Tests

**Files:**
- Modify: `tests/test_hxy_knowledge_api.py`

**Step 1: Write failing test**

Add near topic draft asset API test:

```python
def test_operating_brain_compiler_topic_review_packets_returns_unapproved_tasks(self):
    wiki_dir = self.root / "knowledge" / "wiki"
    wiki_dir.mkdir(parents=True)
    (wiki_dir / "topic-review-packets.json").write_text(
        json.dumps(
            {
                "version": "hxy-topic-review-packets.v1",
                "status": "ready",
                "count": 1,
                "total": 1,
                "items": [
                    {
                        "version": "hxy-topic-review-packet.v1",
                        "packet_id": "hxy-topic-review-packet:brand_positioning",
                        "asset_id": "hxy-topic-draft:brand_positioning",
                        "asset_type": "positioning_card",
                        "title": "品牌战略与核爆点定位",
                        "priority": "P0",
                        "review_owner": "创始人",
                        "status": "open",
                        "review_questions": ["这个判断是否有真实顾客原话支撑？"],
                        "evidence_gaps": ["补齐目标用户原话"],
                        "decision_options": ["needs_more_evidence", "revise_draft", "ready_for_manual_approval", "reject"],
                        "promotion_target": "approved_positioning_card",
                        "blocked_actions": ["不能自动发布"],
                        "source_samples": ["brand.md"],
                        "official_use_allowed": False,
                        "requires_human_review": True,
                        "authority_rule": "review_packets_are_tasks_not_approval",
                    }
                ],
                "official_use_allowed": False,
                "requires_human_review": True,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    response = self.client.get("/api/operating-brain/knowledge-compiler/topic-review-packets?limit=5")
    body = response.json()

    self.assertEqual(response.status_code, 200)
    self.assertEqual(body["version"], "hxy-topic-review-packets.v1")
    self.assertEqual(body["count"], 1)
    self.assertEqual(body["items"][0]["status"], "open")
    self.assertEqual(body["items"][0]["promotion_target"], "approved_positioning_card")
    self.assertIn("ready_for_manual_approval", body["items"][0]["decision_options"])
    self.assertFalse(body["official_use_allowed"])
    self.assertTrue(body["requires_human_review"])
```

**Step 2: Run RED**

```bash
PATH=/root/hxy/.venv/bin:$PATH PYTHONPATH=/root/hxy/apps/api pytest tests/test_hxy_knowledge_api.py -k "topic_review_packets" -q
```

Expected: FAIL with 404.

### Task 4: Implement Review Packet API

**Files:**
- Modify: `apps/api/hxy_knowledge_api.py`
- Test: `tests/test_hxy_knowledge_api.py`

**Step 1: Add sanitizer**

Near `_compiler_topic_draft_assets_from_payload`, add `_compiler_topic_review_packets_from_payload`. It should:

- return missing response when no payload;
- force every item to `status="open"`;
- force `official_use_allowed=False`;
- force `requires_human_review=True`;
- keep only business fields.

**Step 2: Add route**

```python
@app.get("/api/operating-brain/knowledge-compiler/topic-review-packets")
async def operating_brain_knowledge_compiler_topic_review_packets_endpoint(
    limit: int = Query(default=12, ge=1, le=50),
) -> dict[str, Any]:
    payload = _read_json_file(resolved_root / "knowledge" / "wiki" / "topic-review-packets.json")
    return _compiler_topic_review_packets_from_payload(payload, limit=limit)
```

**Step 3: Run tests**

```bash
PATH=/root/hxy/.venv/bin:$PATH PYTHONPATH=/root/hxy/apps/api pytest tests/test_hxy_knowledge_api.py -k "topic_review_packets or topic_draft_assets" -q
```

Expected: PASS.

**Step 4: Commit**

```bash
git add apps/api/hxy_knowledge_api.py tests/test_hxy_knowledge_api.py
git commit -m "feat: expose topic review packets"
```

### Task 5: Add Frontend Test For Review Packets

**Files:**
- Modify: `tests/test_hxy_brain_frontend.py`

**Step 1: Write failing test**

Add near topic draft asset frontend test:

```python
def test_knowledge_workbench_renders_topic_review_packets_without_approval_buttons(self):
    html = (ROOT / "apps" / "admin-web" / "knowledge.html").read_text(encoding="utf-8")

    for label in [
        "复核任务包",
        "谁看",
        "看什么",
        "允许的判断",
        "不能做什么",
        "needs_more_evidence",
        "revise_draft",
        "ready_for_manual_approval",
        "reject",
        "id=\"topicReviewPacketsList\"",
        "renderTopicReviewPackets",
        "loadTopicReviewPackets",
        "/api/operating-brain/knowledge-compiler/topic-review-packets?limit=12",
    ]:
        self.assertIn(label, html)

    panel_start = html.index("复核任务包")
    panel_end = html.index("合规审核包", panel_start)
    panel_html = html[panel_start:panel_end]
    for forbidden in ["批准发布", "一键批准", "写入 approved", "chunk_id", "cluster_id", "raw claim"]:
        self.assertNotIn(forbidden, panel_html)
```

**Step 2: Run RED**

```bash
PATH=/root/hxy/.venv/bin:$PATH pytest tests/test_hxy_brain_frontend.py -k "topic_review_packets" -q
```

Expected: FAIL because UI block does not exist.

### Task 6: Implement Knowledge Workbench Review Packet Panel

**Files:**
- Modify: `apps/admin-web/knowledge.html`
- Test: `tests/test_hxy_brain_frontend.py`

**Step 1: Add panel after "议题转资产"**

Panel title: `复核任务包`

Display:

- 谁看
- 看什么
- 允许的判断
- 不能做什么

No approval button.

**Step 2: Add JS**

Add:

- `topicReviewPacketsList`
- `renderTopicReviewPackets(payload)`
- `loadTopicReviewPackets()`
- include API call in `refreshAll`
- refresh after ingest loop
- button event listener

Render decision options as labels only.

**Step 3: Run frontend tests**

```bash
PATH=/root/hxy/.venv/bin:$PATH pytest tests/test_hxy_brain_frontend.py -k "topic_review_packets or knowledge" -q
```

Expected: PASS.

**Step 4: Commit**

```bash
git add apps/admin-web/knowledge.html tests/test_hxy_brain_frontend.py
git commit -m "feat: show topic review packets"
```

### Task 7: Full Verification, Merge, Push

**Step 1: Use local private knowledge only for tests**

If this worktree lacks local private raw knowledge, create temporary symlinks before `npm test`:

```bash
for p in .venv node_modules; do if [ ! -e "$p" ]; then ln -s "/root/hxy/$p" "$p"; fi; done
if [ ! -e knowledge/raw ]; then ln -s /root/hxy/knowledge/raw knowledge/raw; fi
```

Remove symlinks before commit/merge:

```bash
for p in node_modules .venv knowledge/raw; do if [ -L "$p" ]; then rm "$p"; fi; done
```

**Step 2: Run full tests**

```bash
npm test
```

Expected: Python and Vitest pass.

**Step 3: Run benchmark and release checks**

```bash
/root/hxy/.venv/bin/python scripts/run-hxy-brain-benchmark.py --benchmark knowledge/benchmarks/hxy-brain-benchmark-v1.json --output /tmp/hxy-brain-benchmark-topic-review-packets.json
python3 scripts/check-hxy-secrets.py
python3 scripts/check-hxy-public-release.py
git diff --check main..HEAD
```

Expected: benchmark pass rate at least `0.85`, release check reports `code_only_private_knowledge_local`.

**Step 4: Confirm no private/generated paths are tracked**

```bash
git status --short --branch
git ls-tree -r --name-only HEAD | rg '^(knowledge/raw|knowledge/reports|knowledge/runs|knowledge/wiki|node_modules|\\.venv)(/|$)' || true
```

Expected: no output from `rg`.

**Step 5: Merge and push**

```bash
cd /root/hxy
git merge --ff-only feature/hxy-topic-review-packets
npm test
/root/hxy/.venv/bin/python scripts/run-hxy-brain-benchmark.py --benchmark knowledge/benchmarks/hxy-brain-benchmark-v1.json --output /tmp/hxy-brain-benchmark-topic-review-packets-main.json
python3 scripts/check-hxy-secrets.py
python3 scripts/check-hxy-public-release.py
git push origin main
git worktree remove /root/hxy/.worktrees/hxy-topic-review-packets
git branch -d feature/hxy-topic-review-packets
```
