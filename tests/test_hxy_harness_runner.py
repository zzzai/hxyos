from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


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


def test_run_harness_round_executes_allowlisted_commands_and_writes_report(tmp_path):
    from hxy_knowledge.harness_runner import run_harness_round

    root = tmp_path / "hxy"
    root.mkdir()
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
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    body = json.loads(result.stdout)
    assert body["version"] == "hxy-harness-spec-validation.v1"
    assert body["valid"] is True
