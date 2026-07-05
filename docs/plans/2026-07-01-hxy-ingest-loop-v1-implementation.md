# HXY Ingest Loop V1 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a deterministic ingest loop that scans HXY raw materials, runs the existing knowledge compiler, writes replayable loop state, exposes status through the API, and shows it in the knowledge workbench without auto-approving knowledge.

**Architecture:** Add a pure Python `ingest_loop` orchestration module over the existing compiler. The first version uses JSON state files under `knowledge/runs/` and reports under `knowledge/reports/`; later queue/workflow systems can replace the runner without changing the lifecycle contract.

**Tech Stack:** Python standard library, existing HXY knowledge compiler, FastAPI, static HTML/JS, pytest, npm/vitest project test runner.

---

## Constraints

- Do not read or write `/root/htops` business data.
- Do not use `HETANG_*` environment fallback.
- Keep HXY artifacts under `knowledge/`, `docs/`, `data/`, `apps/`, `scripts/`, or `tests/`.
- Raw materials, compiler extracts, candidate claims, answer card drafts, and loop outputs are not approved knowledge.
- V1 stops at human review. It must not create `approved` answer cards or publish formal knowledge.
- Process memory can only be context; it cannot be an authority source.
- All behavior changes require tests first.

## Task 1: Add Ingest Loop Discovery Tests

**Files:**

- Create: `tests/test_hxy_ingest_loop.py`
- Create later: `apps/api/hxy_knowledge/ingest_loop.py`

**Step 1: Write the failing test**

Add:

```python
from pathlib import Path


def test_discover_inbox_materials_returns_hash_stable_tasks(tmp_path):
    from hxy_knowledge.ingest_loop import discover_inbox_materials

    inbox = tmp_path / "knowledge" / "raw" / "inbox"
    inbox.mkdir(parents=True)
    (inbox / "brand.md").write_text("荷小悦是社区轻养生项目。", encoding="utf-8")

    result = discover_inbox_materials(inbox, root_dir=tmp_path)

    assert result["version"] == "hxy-ingest-discovery.v1"
    assert result["count"] == 1
    task = result["items"][0]
    assert task["version"] == "hxy-ingest-task.v1"
    assert task["status"] == "DISCOVERED"
    assert task["source_path"] == "knowledge/raw/inbox/brand.md"
    assert task["content_hash"]
    assert task["official_use_allowed"] is False
    assert task["requires_human_review"] is True
```

**Step 2: Run test to verify it fails**

Run:

```bash
PATH=/root/hxy/.venv/bin:$PATH PYTHONPATH=/root/hxy/apps/api pytest tests/test_hxy_ingest_loop.py::test_discover_inbox_materials_returns_hash_stable_tasks -q
```

Expected: FAIL because `hxy_knowledge.ingest_loop` does not exist.

**Step 3: Implement minimal discovery**

Create `apps/api/hxy_knowledge/ingest_loop.py` with:

```python
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SUPPORTED_SUFFIXES = {".md", ".txt"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relative(path: Path, root_dir: Path) -> str:
    try:
        return path.relative_to(root_dir).as_posix()
    except ValueError:
        return path.as_posix()


def discover_inbox_materials(inbox_dir: Path, *, root_dir: Path) -> dict[str, Any]:
    items = []
    for path in sorted(inbox_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_SUFFIXES:
            continue
        content_hash = _hash_file(path)
        rel_path = _relative(path, root_dir)
        items.append(
            {
                "version": "hxy-ingest-task.v1",
                "task_id": f"hxy-ingest-task:{content_hash[:16]}",
                "source_path": rel_path,
                "source_type": "file",
                "content_hash": content_hash,
                "status": "DISCOVERED",
                "official_use_allowed": False,
                "requires_human_review": True,
                "risk_flags": [],
                "artifact_refs": {},
                "created_at": _utc_now(),
                "updated_at": _utc_now(),
            }
        )
    return {"version": "hxy-ingest-discovery.v1", "count": len(items), "items": items}
```

**Step 4: Run test to verify it passes**

Run:

```bash
PATH=/root/hxy/.venv/bin:$PATH PYTHONPATH=/root/hxy/apps/api pytest tests/test_hxy_ingest_loop.py -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add apps/api/hxy_knowledge/ingest_loop.py tests/test_hxy_ingest_loop.py
git commit -m "feat: add hxy ingest loop discovery"
```

## Task 2: Add Deterministic Loop Runner

**Files:**

- Modify: `tests/test_hxy_ingest_loop.py`
- Modify: `apps/api/hxy_knowledge/ingest_loop.py`

**Step 1: Write the failing test**

Add:

```python
def test_run_ingest_loop_compiles_and_stops_at_review(tmp_path):
    from hxy_knowledge.ingest_loop import run_ingest_loop

    raw_dir = tmp_path / "knowledge" / "raw" / "inbox"
    wiki_dir = tmp_path / "knowledge" / "wiki"
    report_path = tmp_path / "knowledge" / "reports" / "ingest-latest.json"
    runs_dir = tmp_path / "knowledge" / "runs"
    raw_dir.mkdir(parents=True)
    (raw_dir / "brand.md").write_text(
        "荷小悦定位是社区轻养生。员工不能说治疗失眠。",
        encoding="utf-8",
    )

    state = run_ingest_loop(
        raw_dir=raw_dir,
        wiki_dir=wiki_dir,
        report_path=report_path,
        runs_dir=runs_dir,
        run_id="ingest-loop-test",
        root_dir=tmp_path,
    )

    assert state["version"] == "hxy-ingest-loop-state.v1"
    assert state["status"] == "review_required"
    assert state["stop_reason"] == "human_review_required"
    assert state["official_use_allowed"] is False
    assert state["task_count"] == 1
    assert state["claim_count"] >= 1
    assert state["review_queue_count"] >= 1
    assert report_path.exists()
    assert (runs_dir / "ingest-loop-test" / "loop-state.json").exists()
```

**Step 2: Run test to verify it fails**

Run:

```bash
PATH=/root/hxy/.venv/bin:$PATH PYTHONPATH=/root/hxy/apps/api pytest tests/test_hxy_ingest_loop.py::test_run_ingest_loop_compiles_and_stops_at_review -q
```

Expected: FAIL because `run_ingest_loop` is missing.

**Step 3: Implement loop runner**

In `apps/api/hxy_knowledge/ingest_loop.py`, import the compiler:

```python
import json
from hxy_knowledge.knowledge_compiler import compile_directory
```

Add:

```python
def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def run_ingest_loop(
    *,
    raw_dir: Path,
    wiki_dir: Path,
    report_path: Path,
    runs_dir: Path,
    run_id: str,
    root_dir: Path,
) -> dict[str, Any]:
    discovery = discover_inbox_materials(raw_dir, root_dir=root_dir)
    compiler_report = compile_directory(raw_dir, wiki_dir)
    _write_json(report_path, {key: value for key, value in compiler_report.items() if key != "artifacts"})

    state = {
        "version": "hxy-ingest-loop-state.v1",
        "run_id": run_id,
        "status": "review_required",
        "stop_reason": "human_review_required",
        "task_count": discovery["count"],
        "extract_count": int(compiler_report.get("extract_count") or 0),
        "claim_count": int(compiler_report.get("claim_count") or 0),
        "review_queue_count": int(compiler_report.get("review_queue_count") or 0),
        "answer_card_draft_count": int(compiler_report.get("answer_card_draft_count") or 0),
        "tasks": [
            {
                **task,
                "status": "REVIEWING",
                "artifact_refs": {
                    "ingest_report": report_path.as_posix(),
                    "review_queue": (wiki_dir / "review-queue.json").as_posix(),
                    "answer_card_drafts": (wiki_dir / "answer-card-drafts.json").as_posix(),
                },
                "updated_at": _utc_now(),
            }
            for task in discovery["items"]
        ],
        "official_use_allowed": False,
        "requires_human_review": True,
        "authority_rule": "ingest_loop_outputs_are_candidates_until_human_review",
        "next_actions": [
            "在知识工作台复核 review queue。",
            "禁止自动发布 approved answer card。",
            "复核后再决定是否进入正式知识库。",
        ],
    }
    _write_json(Path(runs_dir) / run_id / "loop-state.json", state)
    return state
```

**Step 4: Run tests**

Run:

```bash
PATH=/root/hxy/.venv/bin:$PATH PYTHONPATH=/root/hxy/apps/api pytest tests/test_hxy_ingest_loop.py -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add apps/api/hxy_knowledge/ingest_loop.py tests/test_hxy_ingest_loop.py
git commit -m "feat: run hxy ingest loop to review state"
```

## Task 3: Add CLI Runner

**Files:**

- Create: `scripts/run-hxy-ingest-loop.py`
- Modify: `tests/test_hxy_ingest_loop.py`

**Step 1: Write the failing CLI test**

Add:

```python
import json
import subprocess
import sys


def test_ingest_loop_cli_writes_state(tmp_path):
    raw_dir = tmp_path / "knowledge" / "raw" / "inbox"
    raw_dir.mkdir(parents=True)
    (raw_dir / "brand.md").write_text("荷小悦品牌资料。", encoding="utf-8")
    report_path = tmp_path / "knowledge" / "reports" / "ingest-latest.json"
    runs_dir = tmp_path / "knowledge" / "runs"

    result = subprocess.run(
        [
            sys.executable,
            "scripts/run-hxy-ingest-loop.py",
            "--raw-dir",
            str(raw_dir),
            "--wiki-dir",
            str(tmp_path / "knowledge" / "wiki"),
            "--report",
            str(report_path),
            "--runs-dir",
            str(runs_dir),
            "--run-id",
            "ingest-loop-test",
            "--root-dir",
            str(tmp_path),
        ],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    state = json.loads((runs_dir / "ingest-loop-test" / "loop-state.json").read_text(encoding="utf-8"))
    assert state["status"] == "review_required"
```

**Step 2: Run test to verify it fails**

Run:

```bash
PATH=/root/hxy/.venv/bin:$PATH PYTHONPATH=/root/hxy/apps/api pytest tests/test_hxy_ingest_loop.py::test_ingest_loop_cli_writes_state -q
```

Expected: FAIL because script is missing.

**Step 3: Implement CLI**

Create `scripts/run-hxy-ingest-loop.py`:

```python
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from hxy_knowledge.ingest_loop import run_ingest_loop


def main() -> int:
    parser = argparse.ArgumentParser(description="Run HXY ingest loop to human review state.")
    parser.add_argument("--raw-dir", default="knowledge/raw/inbox")
    parser.add_argument("--wiki-dir", default="knowledge/wiki")
    parser.add_argument("--report", default="knowledge/reports/ingest-latest.json")
    parser.add_argument("--runs-dir", default="knowledge/runs")
    parser.add_argument("--run-id", default="ingest-loop-latest")
    parser.add_argument("--root-dir", default=".")
    args = parser.parse_args()

    root_dir = Path(args.root_dir).resolve()
    state = run_ingest_loop(
        raw_dir=Path(args.raw_dir),
        wiki_dir=Path(args.wiki_dir),
        report_path=Path(args.report),
        runs_dir=Path(args.runs_dir),
        run_id=args.run_id,
        root_dir=root_dir,
    )
    print(json.dumps(state, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

**Step 4: Run tests**

Run:

```bash
PATH=/root/hxy/.venv/bin:$PATH PYTHONPATH=/root/hxy/apps/api pytest tests/test_hxy_ingest_loop.py -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add apps/api/hxy_knowledge/ingest_loop.py scripts/run-hxy-ingest-loop.py tests/test_hxy_ingest_loop.py
git commit -m "feat: add hxy ingest loop cli"
```

## Task 4: Expose Ingest Loop API

**Files:**

- Modify: `apps/api/hxy_knowledge_api.py`
- Modify: `tests/test_hxy_knowledge_api.py`

**Step 1: Write failing API tests**

Add near operating brain tests:

```python
def test_operating_brain_ingest_loop_status_returns_missing_when_not_run(self):
    response = self.client.get("/api/operating-brain/ingest-loop/status")

    self.assertEqual(response.status_code, 200)
    body = response.json()
    self.assertEqual(body["version"], "hxy-ingest-loop-status.v1")
    self.assertEqual(body["status"], "missing")
    self.assertFalse(body["official_use_allowed"])


def test_operating_brain_ingest_loop_run_requires_auth_and_stops_at_review(self):
    (self.root / "knowledge" / "raw" / "inbox" / "brand.md").write_text(
        "荷小悦是社区轻养生品牌。不能说治疗失眠。",
        encoding="utf-8",
    )

    response = self.client.post("/api/operating-brain/ingest-loop/run")

    self.assertEqual(response.status_code, 200)
    body = response.json()
    self.assertEqual(body["version"], "hxy-ingest-loop-state.v1")
    self.assertEqual(body["status"], "review_required")
    self.assertFalse(body["official_use_allowed"])
```

**Step 2: Run tests to verify failure**

Run:

```bash
PATH=/root/hxy/.venv/bin:$PATH PYTHONPATH=/root/hxy/apps/api pytest tests/test_hxy_knowledge_api.py -k "ingest_loop" -q
```

Expected: FAIL because endpoints are missing.

**Step 3: Implement endpoints**

In `apps/api/hxy_knowledge_api.py`, import:

```python
from hxy_knowledge.ingest_loop import run_ingest_loop
```

Inside `create_app`, add:

```python
ingest_loop_state_path = resolved_root / "knowledge" / "runs" / "ingest-loop-latest" / "loop-state.json"
```

Add:

```python
@app.get("/api/operating-brain/ingest-loop/status")
async def operating_brain_ingest_loop_status_endpoint() -> dict[str, Any]:
    payload = _read_json_file(ingest_loop_state_path)
    if not payload:
        return {
            "version": "hxy-ingest-loop-status.v1",
            "status": "missing",
            "official_use_allowed": False,
            "next_actions": ["运行资料入库 Loop，把 inbox 资料编译到人工复核队列。"],
        }
    return {
        "version": "hxy-ingest-loop-status.v1",
        **payload,
        "official_use_allowed": False,
        "authority_rule": "ingest_loop_outputs_are_candidates_until_human_review",
    }


@app.post("/api/operating-brain/ingest-loop/run", dependencies=[Depends(require_api_token)])
async def operating_brain_ingest_loop_run_endpoint() -> dict[str, Any]:
    return run_ingest_loop(
        raw_dir=resolved_root / "knowledge" / "raw" / "inbox",
        wiki_dir=resolved_root / "knowledge" / "wiki",
        report_path=resolved_root / "knowledge" / "reports" / "ingest-latest.json",
        runs_dir=resolved_root / "knowledge" / "runs",
        run_id="ingest-loop-latest",
        root_dir=resolved_root,
    )
```

**Step 4: Run API tests**

Run:

```bash
PATH=/root/hxy/.venv/bin:$PATH PYTHONPATH=/root/hxy/apps/api pytest tests/test_hxy_knowledge_api.py -k "ingest_loop" -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add apps/api/hxy_knowledge/ingest_loop.py apps/api/hxy_knowledge_api.py tests/test_hxy_ingest_loop.py tests/test_hxy_knowledge_api.py scripts/run-hxy-ingest-loop.py
git commit -m "feat: expose hxy ingest loop api"
```

## Task 5: Add Knowledge Workbench UI Contract

**Files:**

- Modify: `tests/test_hxy_brain_frontend.py`
- Modify later: `apps/admin-web/knowledge.html`

**Step 1: Write failing static test**

Add:

```python
def test_knowledge_workbench_renders_ingest_loop_panel(self):
    html = (ROOT / "apps" / "admin-web" / "knowledge.html").read_text(encoding="utf-8")

    for marker in [
        "资料入库 Loop",
        "候选资料不等于正式知识",
        'id="ingestLoopStatus"',
        'id="runIngestLoop"',
        'id="refreshIngestLoop"',
        "renderIngestLoopStatus",
        "/api/operating-brain/ingest-loop/status",
        "/api/operating-brain/ingest-loop/run",
    ]:
        self.assertIn(marker, html)
```

**Step 2: Run test to verify failure**

Run:

```bash
PATH=/root/hxy/.venv/bin:$PATH pytest tests/test_hxy_brain_frontend.py -k "ingest_loop" -q
```

Expected: FAIL until `knowledge.html` is updated.

## Task 6: Add Ingest Loop Panel To `knowledge.html`

**Files:**

- Modify: `apps/admin-web/knowledge.html`
- Test: `tests/test_hxy_brain_frontend.py`

**Step 1: Add panel markup**

Place near the knowledge status / review queue:

```html
<section class="panel">
  <div class="panel-header">
    <div class="panel-title">资料入库 Loop <small>候选资料不等于正式知识</small></div>
    <div class="actions">
      <button class="secondary" id="refreshIngestLoop" type="button">刷新</button>
      <button class="primary" id="runIngestLoop" type="button">运行入库 Loop</button>
    </div>
  </div>
  <div class="panel-body">
    <div id="ingestLoopStatus" class="result">等待读取资料入库 Loop 状态。</div>
  </div>
</section>
```

**Step 2: Add JS helpers**

Add:

```javascript
function renderIngestLoopStatus(payload) {
  const status = payload.status || "missing";
  const count = payload.task_count || 0;
  const reviewCount = payload.review_queue_count || 0;
  const draftCount = payload.answer_card_draft_count || 0;
  ingestLoopStatus.innerHTML = `
    <strong>${escapeHtml(status)}</strong>
    <div>资料：${count} · 待复核：${reviewCount} · 答案卡草稿：${draftCount}</div>
    <div>候选资料不等于正式知识，Loop 自动停在人工审核。</div>
  `;
}

async function refreshIngestLoop() {
  const payload = await requestJson("/api/operating-brain/ingest-loop/status");
  renderIngestLoopStatus(payload);
}

async function runIngestLoop() {
  setResult("正在运行资料入库 Loop...");
  const payload = await requestJson("/api/operating-brain/ingest-loop/run", { method: "POST" });
  renderIngestLoopStatus(payload);
  await refreshReviewQueue();
  setResult("资料入库 Loop 已停在人工复核。", "ok");
}
```

Wire buttons:

```javascript
document.querySelector("#refreshIngestLoop").addEventListener("click", refreshIngestLoop);
document.querySelector("#runIngestLoop").addEventListener("click", runIngestLoop);
refreshIngestLoop();
```

**Step 3: Run frontend tests**

Run:

```bash
PATH=/root/hxy/.venv/bin:$PATH pytest tests/test_hxy_brain_frontend.py -k "ingest_loop" -q
```

Expected: PASS.

**Step 4: Commit**

```bash
git add apps/admin-web/knowledge.html tests/test_hxy_brain_frontend.py
git commit -m "feat: show hxy ingest loop in knowledge workbench"
```

## Task 7: Full Verification

**Files:**

- No code changes unless verification finds a defect.

**Step 1: Run focused tests**

Run:

```bash
PATH=/root/hxy/.venv/bin:$PATH PYTHONPATH=/root/hxy/apps/api pytest tests/test_hxy_ingest_loop.py tests/test_hxy_knowledge_api.py -k "ingest_loop" -q
PATH=/root/hxy/.venv/bin:$PATH pytest tests/test_hxy_brain_frontend.py -k "ingest_loop" -q
```

Expected: PASS.

**Step 2: Run full suite**

Run:

```bash
npm test
```

Expected: Python and TypeScript suites pass.

**Step 3: Inspect git diff**

Run:

```bash
git diff --check
git status --short
```

Expected: no whitespace errors; only intended files are staged/modified for this feature.

**Step 4: Commit any final fixes**

Only if needed:

```bash
git add <specific-files>
git commit -m "test: verify hxy ingest loop v1"
```

## Execution Notes

The current repository may contain unrelated dirty changes from earlier HXYOS work. Do not use broad `git add .`. Stage only the files listed for each task.

If `apps/api/hxy_knowledge_api.py` already contains uncommitted governance/process-memory changes, inspect staged hunks carefully. Do not mix unrelated benchmark, Hermes, or workspace changes into the ingest loop commits unless they are required dependencies and called out in the commit message.
