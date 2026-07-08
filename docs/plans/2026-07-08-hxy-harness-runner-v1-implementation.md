# HXY Harness Runner V1 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a file-based HXY Harness Runner that validates bounded autonomous loop specs, runs allowlisted verification commands, and writes evidence reports without approving knowledge or touching htops.

**Architecture:** Add a pure Python `hxy_knowledge.harness_runner` module with spec validation, command allowlisting, one-round execution, repeated-failure detection, and report writing. Add a CLI wrapper in `scripts/run-hxy-harness.py`. Keep V1 local and file-based; no API write path and no formal knowledge import.

**Tech Stack:** Python stdlib, pytest, existing `npm test`, existing benchmark CLI, existing HXY secrets/public-release checks.

---

### Task 1: Add Harness Spec Validation

**Files:**
- Create: `apps/api/hxy_knowledge/harness_runner.py`
- Test: `tests/test_hxy_harness_runner.py`

**Step 1: Write failing tests**

Add:

```python
from pathlib import Path


def test_validate_harness_spec_accepts_safe_verification_only_spec(tmp_path):
    from hxy_knowledge.harness_runner import validate_harness_spec

    spec = {
        "version": "hxy-harness-spec.v1",
        "run_name": "source-quality-gate-v1",
        "target": "source classification accuracy >= 0.85",
        "scope": ["apps/api/hxy_knowledge/ingest_loop.py"],
        "max_rounds": 3,
        "verification_commands": ["npm test"],
        "forbidden_paths": ["/root/htops"],
        "forbidden_actions": ["auto_approve_knowledge", "write_formal_knowledge_store"],
        "success_thresholds": {"npm_test": "pass"},
    }

    result = validate_harness_spec(spec, root_dir=tmp_path)

    assert result["version"] == "hxy-harness-spec-validation.v1"
    assert result["valid"] is True
    assert result["error_count"] == 0
    assert result["write_to_database"] is False
    assert result["official_use_allowed"] is False


def test_validate_harness_spec_rejects_htops_scope_and_unsafe_commands(tmp_path):
    from hxy_knowledge.harness_runner import validate_harness_spec

    spec = {
        "version": "hxy-harness-spec.v1",
        "run_name": "unsafe",
        "target": "do unsafe thing",
        "scope": ["/root/htops/api/main.py"],
        "max_rounds": 5,
        "verification_commands": ["rm -rf /root/hxy/knowledge/wiki"],
        "forbidden_paths": ["/root/htops"],
        "forbidden_actions": ["auto_approve_knowledge"],
        "success_thresholds": {},
    }

    result = validate_harness_spec(spec, root_dir=tmp_path)

    assert result["valid"] is False
    assert {error["code"] for error in result["errors"]} >= {
        "forbidden_scope_path",
        "command_not_allowlisted",
    }
    assert result["write_to_database"] is False
```

**Step 2: Run tests to verify failure**

Run:

```bash
.venv/bin/pytest -q tests/test_hxy_harness_runner.py::test_validate_harness_spec_accepts_safe_verification_only_spec tests/test_hxy_harness_runner.py::test_validate_harness_spec_rejects_htops_scope_and_unsafe_commands
```

Expected: fail because `hxy_knowledge.harness_runner` does not exist.

**Step 3: Implement minimal validation**

Create `apps/api/hxy_knowledge/harness_runner.py`:

```python
from __future__ import annotations

from pathlib import Path
from typing import Any


ALLOWED_COMMAND_PREFIXES = (
    "npm test",
    ".venv/bin/pytest",
    ".venv/bin/python scripts/run-hxy-brain-benchmark.py",
    "python3 scripts/check-hxy-secrets.py",
    "python3 scripts/check-hxy-public-release.py",
)

FORBIDDEN_SCOPE_PREFIXES = ("/root/htops", "root/htops")


def _error(code: str, message: str, **extra: Any) -> dict[str, Any]:
    return {"code": code, "message": message, **extra}


def _is_allowed_command(command: str) -> bool:
    clean = " ".join(str(command or "").strip().split())
    return any(clean == prefix or clean.startswith(f"{prefix} ") for prefix in ALLOWED_COMMAND_PREFIXES)


def validate_harness_spec(spec: dict[str, Any], *, root_dir: str | Path) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    if spec.get("version") != "hxy-harness-spec.v1":
        errors.append(_error("invalid_version", "Harness spec version must be hxy-harness-spec.v1."))
    if not str(spec.get("run_name") or "").strip():
        errors.append(_error("missing_run_name", "run_name is required."))
    if not str(spec.get("target") or "").strip():
        errors.append(_error("missing_target", "target is required."))
    max_rounds = int(spec.get("max_rounds") or 0)
    if max_rounds < 1 or max_rounds > 10:
        errors.append(_error("invalid_max_rounds", "max_rounds must be between 1 and 10."))
    for path in spec.get("scope") or []:
        clean = str(path or "").strip()
        if clean.startswith(FORBIDDEN_SCOPE_PREFIXES):
            errors.append(_error("forbidden_scope_path", "Scope cannot include htops paths.", path=clean))
    commands = spec.get("verification_commands") if isinstance(spec.get("verification_commands"), list) else []
    if not commands:
        errors.append(_error("missing_verification_commands", "At least one verification command is required."))
    for command in commands:
        if not _is_allowed_command(str(command or "")):
            errors.append(_error("command_not_allowlisted", "Command is not allowed for Harness V1.", command=str(command or "")))
    return {
        "version": "hxy-harness-spec-validation.v1",
        "valid": not errors,
        "error_count": len(errors),
        "errors": errors,
        "write_to_database": False,
        "official_use_allowed": False,
        "requires_human_review": True,
        "authority_rule": "harness_spec_validation_does_not_execute_or_publish",
    }
```

**Step 4: Run tests to verify pass**

Run:

```bash
.venv/bin/pytest -q tests/test_hxy_harness_runner.py::test_validate_harness_spec_accepts_safe_verification_only_spec tests/test_hxy_harness_runner.py::test_validate_harness_spec_rejects_htops_scope_and_unsafe_commands
```

Expected: 2 passed.

**Step 5: Commit**

```bash
git add apps/api/hxy_knowledge/harness_runner.py tests/test_hxy_harness_runner.py
git commit -m "feat: add harness spec validation"
```

### Task 2: Execute Allowlisted Verification Commands

**Files:**
- Modify: `apps/api/hxy_knowledge/harness_runner.py`
- Test: `tests/test_hxy_harness_runner.py`

**Step 1: Write failing test**

Add:

```python
def test_run_harness_round_executes_allowlisted_commands_and_writes_report(tmp_path):
    from hxy_knowledge.harness_runner import run_harness_round

    root = tmp_path / "hxy"
    root.mkdir()
    marker = root / "marker.txt"
    command = ".venv/bin/pytest tests/test_fake.py"
    result = run_harness_round(
        {
            "version": "hxy-harness-spec.v1",
            "run_name": "unit",
            "target": "prove runner",
            "scope": [],
            "max_rounds": 3,
            "verification_commands": [command],
            "forbidden_paths": ["/root/htops"],
            "forbidden_actions": [],
            "success_thresholds": {"all_commands": "pass"},
        },
        root_dir=root,
        run_id="harness-unit",
        round_number=1,
        command_runner=lambda cmd, cwd: {"command": cmd, "returncode": 0, "stdout": "ok", "stderr": ""},
    )

    assert result["version"] == "hxy-harness-round-report.v1"
    assert result["round"] == 1
    assert result["status"] == "passed"
    assert result["command_results"][0]["returncode"] == 0
    assert result["write_to_database"] is False
    assert (root / "knowledge" / "runs" / "harness-unit" / "round-1.json").exists()
```

**Step 2: Run test to verify failure**

Run:

```bash
.venv/bin/pytest -q tests/test_hxy_harness_runner.py::test_run_harness_round_executes_allowlisted_commands_and_writes_report
```

Expected: fail because `run_harness_round` does not exist.

**Step 3: Implement command execution**

Add to `harness_runner.py`:

```python
import json
import subprocess


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _default_command_runner(command: str, cwd: Path) -> dict[str, Any]:
    completed = subprocess.run(command.split(), cwd=cwd, text=True, capture_output=True, check=False)
    return {
        "command": command,
        "returncode": completed.returncode,
        "stdout": completed.stdout[-4000:],
        "stderr": completed.stderr[-4000:],
    }


def run_harness_round(
    spec: dict[str, Any],
    *,
    root_dir: str | Path,
    run_id: str,
    round_number: int,
    command_runner: Any | None = None,
) -> dict[str, Any]:
    root = Path(root_dir)
    validation = validate_harness_spec(spec, root_dir=root)
    if not validation["valid"]:
        report = {
            "version": "hxy-harness-round-report.v1",
            "round": round_number,
            "status": "blocked",
            "validation": validation,
            "command_results": [],
            "write_to_database": False,
            "official_use_allowed": False,
        }
        _write_json(root / "knowledge" / "runs" / run_id / f"round-{round_number}.json", report)
        return report
    runner = command_runner or _default_command_runner
    command_results = [runner(str(command), root) for command in spec.get("verification_commands") or []]
    passed = all(int(result.get("returncode") or 0) == 0 for result in command_results)
    report = {
        "version": "hxy-harness-round-report.v1",
        "round": round_number,
        "status": "passed" if passed else "failed",
        "command_results": command_results,
        "write_to_database": False,
        "official_use_allowed": False,
        "requires_human_review": True,
        "authority_rule": "harness_round_reports_evidence_only",
    }
    _write_json(root / "knowledge" / "runs" / run_id / f"round-{round_number}.json", report)
    return report
```

**Step 4: Run tests**

Run:

```bash
.venv/bin/pytest -q tests/test_hxy_harness_runner.py
```

Expected: all harness runner tests pass.

**Step 5: Commit**

```bash
git add apps/api/hxy_knowledge/harness_runner.py tests/test_hxy_harness_runner.py
git commit -m "feat: run harness verification round"
```

### Task 3: Add Harness State And Stop Conditions

**Files:**
- Modify: `apps/api/hxy_knowledge/harness_runner.py`
- Test: `tests/test_hxy_harness_runner.py`

**Step 1: Write failing tests**

Add:

```python
def test_build_harness_state_stops_after_max_rounds(tmp_path):
    from hxy_knowledge.harness_runner import build_harness_state

    state = build_harness_state(
        spec={"version": "hxy-harness-spec.v1", "run_name": "unit", "max_rounds": 2},
        run_id="harness-unit",
        round_reports=[
            {"status": "failed", "failure_signature": "benchmark_failed"},
            {"status": "failed", "failure_signature": "benchmark_failed"},
        ],
        champion_commit="abc123",
    )

    assert state["version"] == "hxy-harness-state.v1"
    assert state["status"] == "blocked"
    assert state["stop_reason"] == "max_rounds_reached"
    assert state["champion_commit"] == "abc123"
    assert state["write_to_database"] is False


def test_build_harness_state_stops_on_repeated_failure_signature(tmp_path):
    from hxy_knowledge.harness_runner import build_harness_state

    state = build_harness_state(
        spec={"version": "hxy-harness-spec.v1", "run_name": "unit", "max_rounds": 5},
        run_id="harness-unit",
        round_reports=[
            {"status": "failed", "failure_signature": "same_error"},
            {"status": "failed", "failure_signature": "same_error"},
            {"status": "failed", "failure_signature": "same_error"},
        ],
        champion_commit="abc123",
    )

    assert state["status"] == "blocked"
    assert state["stop_reason"] == "repeated_failure_requires_root_cause_analysis"
```

**Step 2: Run tests to verify failure**

Run:

```bash
.venv/bin/pytest -q tests/test_hxy_harness_runner.py::test_build_harness_state_stops_after_max_rounds tests/test_hxy_harness_runner.py::test_build_harness_state_stops_on_repeated_failure_signature
```

Expected: fail because `build_harness_state` does not exist.

**Step 3: Implement state builder**

Add:

```python
def build_harness_state(
    *,
    spec: dict[str, Any],
    run_id: str,
    round_reports: list[dict[str, Any]],
    champion_commit: str,
) -> dict[str, Any]:
    max_rounds = int(spec.get("max_rounds") or 1)
    status = "running"
    stop_reason = ""
    if round_reports and round_reports[-1].get("status") == "passed":
        status = "succeeded"
        stop_reason = "verification_passed"
    if len(round_reports) >= max_rounds and status != "succeeded":
        status = "blocked"
        stop_reason = "max_rounds_reached"
    signatures = [str(report.get("failure_signature") or "") for report in round_reports[-3:]]
    if len(signatures) == 3 and signatures[0] and len(set(signatures)) == 1 and status != "succeeded":
        status = "blocked"
        stop_reason = "repeated_failure_requires_root_cause_analysis"
    return {
        "version": "hxy-harness-state.v1",
        "run_id": run_id,
        "run_name": spec.get("run_name") or "",
        "status": status,
        "current_round": len(round_reports),
        "max_rounds": max_rounds,
        "champion_commit": champion_commit,
        "rounds": round_reports,
        "stop_reason": stop_reason,
        "write_to_database": False,
        "official_use_allowed": False,
        "requires_human_review": True,
    }
```

**Step 4: Run tests**

Run:

```bash
.venv/bin/pytest -q tests/test_hxy_harness_runner.py
```

Expected: all pass.

**Step 5: Commit**

```bash
git add apps/api/hxy_knowledge/harness_runner.py tests/test_hxy_harness_runner.py
git commit -m "feat: add harness stop conditions"
```

### Task 4: Add CLI Wrapper

**Files:**
- Create: `scripts/run-hxy-harness.py`
- Test: `tests/test_hxy_harness_runner.py`

**Step 1: Write failing CLI test**

Add:

```python
import json
import subprocess
import sys


def test_run_hxy_harness_cli_validates_spec(tmp_path):
    root = tmp_path / "hxy"
    spec_path = root / "knowledge" / "harness" / "specs" / "unit.json"
    spec_path.parent.mkdir(parents=True)
    spec_path.write_text(
        json.dumps(
            {
                "version": "hxy-harness-spec.v1",
                "run_name": "unit",
                "target": "prove cli",
                "scope": [],
                "max_rounds": 1,
                "verification_commands": ["npm test"],
                "forbidden_paths": ["/root/htops"],
                "forbidden_actions": [],
                "success_thresholds": {"npm_test": "pass"},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "scripts/run-hxy-harness.py",
            "validate",
            "--spec",
            str(spec_path),
            "--root-dir",
            str(root),
        ],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    body = json.loads(result.stdout)
    assert body["version"] == "hxy-harness-spec-validation.v1"
    assert body["valid"] is True
```

**Step 2: Run test to verify failure**

Run:

```bash
.venv/bin/pytest -q tests/test_hxy_harness_runner.py::test_run_hxy_harness_cli_validates_spec
```

Expected: fail because script does not exist.

**Step 3: Implement CLI**

Create `scripts/run-hxy-harness.py`:

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

from hxy_knowledge.harness_runner import validate_harness_spec  # noqa: E402


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Run HXY Harness Runner.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate_parser = subparsers.add_parser("validate", help="Validate a harness spec without executing commands.")
    validate_parser.add_argument("--spec", required=True)
    validate_parser.add_argument("--root-dir", default=".")
    args = parser.parse_args()

    if args.command == "validate":
        result = validate_harness_spec(_load_json(Path(args.spec)), root_dir=Path(args.root_dir).resolve())
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["valid"] else 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
```

**Step 4: Run CLI test**

Run:

```bash
.venv/bin/pytest -q tests/test_hxy_harness_runner.py::test_run_hxy_harness_cli_validates_spec
```

Expected: pass.

**Step 5: Commit**

```bash
git add scripts/run-hxy-harness.py tests/test_hxy_harness_runner.py
git commit -m "feat: add harness runner cli"
```

### Task 5: Add Safety And Reward-Hacking Checks

**Files:**
- Modify: `apps/api/hxy_knowledge/harness_runner.py`
- Test: `tests/test_hxy_harness_runner.py`

**Step 1: Write failing tests**

Add:

```python
def test_validate_harness_spec_rejects_benchmark_case_hardcoding(tmp_path):
    from hxy_knowledge.harness_runner import validate_harness_spec

    spec = {
        "version": "hxy-harness-spec.v1",
        "run_name": "hack",
        "target": "hardcode case brand-001",
        "scope": ["apps/api/hxy_knowledge/answer_pipeline.py"],
        "max_rounds": 1,
        "verification_commands": ["npm test"],
        "forbidden_paths": ["/root/htops"],
        "forbidden_actions": ["hardcode_benchmark_case"],
        "success_thresholds": {"npm_test": "pass"},
        "strategy_notes": "If case brand-001 appears, force exact answer.",
    }

    result = validate_harness_spec(spec, root_dir=tmp_path)

    assert result["valid"] is False
    assert any(error["code"] == "reward_hacking_risk" for error in result["errors"])


def test_validate_harness_spec_rejects_private_knowledge_commit_scope(tmp_path):
    from hxy_knowledge.harness_runner import validate_harness_spec

    spec = {
        "version": "hxy-harness-spec.v1",
        "run_name": "private",
        "target": "touch private knowledge",
        "scope": ["knowledge/raw/inbox/private.md"],
        "max_rounds": 1,
        "verification_commands": ["npm test"],
        "forbidden_paths": ["/root/htops"],
        "forbidden_actions": ["commit_private_knowledge"],
        "success_thresholds": {"npm_test": "pass"},
    }

    result = validate_harness_spec(spec, root_dir=tmp_path)

    assert result["valid"] is False
    assert any(error["code"] == "private_knowledge_scope" for error in result["errors"])
```

**Step 2: Run tests to verify failure**

Run:

```bash
.venv/bin/pytest -q tests/test_hxy_harness_runner.py::test_validate_harness_spec_rejects_benchmark_case_hardcoding tests/test_hxy_harness_runner.py::test_validate_harness_spec_rejects_private_knowledge_commit_scope
```

Expected: fail until checks are implemented.

**Step 3: Implement checks**

Add constants and validations:

```python
PRIVATE_KNOWLEDGE_PREFIXES = (
    "knowledge/raw/",
    "knowledge/wiki/",
    "knowledge/reports/",
    "knowledge/runs/",
)


def _contains_reward_hacking_pattern(spec: dict[str, Any]) -> bool:
    text = json.dumps(spec, ensure_ascii=False).lower()
    return "case " in text and ("force exact" in text or "hardcode" in text or "固定答案" in text)
```

Inside `validate_harness_spec`, after scope loop:

```python
        if clean.startswith(PRIVATE_KNOWLEDGE_PREFIXES):
            errors.append(_error("private_knowledge_scope", "Harness scope cannot include private knowledge artifacts.", path=clean))
```

After command validation:

```python
    if _contains_reward_hacking_pattern(spec):
        errors.append(_error("reward_hacking_risk", "Spec appears to encourage benchmark case hardcoding."))
```

**Step 4: Run all harness tests**

Run:

```bash
.venv/bin/pytest -q tests/test_hxy_harness_runner.py
```

Expected: all pass.

**Step 5: Commit**

```bash
git add apps/api/hxy_knowledge/harness_runner.py tests/test_hxy_harness_runner.py
git commit -m "feat: add harness safety checks"
```

### Task 6: Final Verification And Public-Release Safety

**Files:**
- Modify if needed: `docs/plans/2026-07-08-hxy-harness-runner-v1-design.md`
- Modify if needed: `docs/plans/2026-07-08-hxy-harness-runner-v1-implementation.md`

**Step 1: Run focused tests**

Run:

```bash
.venv/bin/pytest -q tests/test_hxy_harness_runner.py
```

Expected: all pass.

**Step 2: Run full tests**

Run:

```bash
npm test
```

Expected:

```text
529+ Python tests passed
52 TypeScript tests passed
```

**Step 3: Run benchmark**

Run:

```bash
.venv/bin/python scripts/run-hxy-brain-benchmark.py \
  --benchmark knowledge/benchmarks/hxy-brain-benchmark-v1.json \
  --output knowledge/reports/benchmark-harness-runner-v1.json
```

Expected:

```text
pass_rate >= 0.85
```

**Step 4: Run safety checks**

Run:

```bash
python3 scripts/check-hxy-secrets.py
python3 scripts/check-hxy-public-release.py
git ls-tree -r --name-only HEAD | rg '^(knowledge/raw|knowledge/reports|knowledge/runs|knowledge/wiki|node_modules|\.venv)(/|$)' || true
git diff --check
```

Expected:

```text
No committed or commit-eligible HXY secrets found.
public_release_preflight_ok=true
no private knowledge paths listed from HEAD
git diff --check exits 0
```

**Step 5: Commit final docs if changed**

```bash
git add docs/plans/2026-07-08-hxy-harness-runner-v1-design.md docs/plans/2026-07-08-hxy-harness-runner-v1-implementation.md
git commit -m "docs: finalize harness runner implementation plan"
```

Skip commit if no files changed.
