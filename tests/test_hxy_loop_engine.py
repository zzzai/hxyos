import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _write_reference_material(raw_dir: Path) -> None:
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / "positioning.md").write_text(
        "# 荷小悦定位讨论\n\n"
        "荷小悦不是传统足疗店，而是社区轻养生门店。\n"
        "清泡调补养用于表达产品体系。\n"
        "员工不能承诺泡脚可以治疗失眠。\n",
        encoding="utf-8",
    )


def test_compile_knowledge_loop_stops_when_target_is_met(tmp_path: Path):
    from apps.api.hxy_knowledge.loop_engine import CompileKnowledgeLoopConfig, LoopThresholds, run_compile_knowledge_loop

    raw_dir = tmp_path / "raw"
    wiki_dir = tmp_path / "wiki"
    report_path = tmp_path / "reports" / "compiler-latest.json"
    runs_dir = tmp_path / "runs"
    _write_reference_material(raw_dir)

    state = run_compile_knowledge_loop(
        CompileKnowledgeLoopConfig(
            raw_dir=raw_dir,
            wiki_dir=wiki_dir,
            report_path=report_path,
            runs_dir=runs_dir,
            run_id="knowledge-loop-test",
            thresholds=LoopThresholds(min_review_queue=1, min_answer_card_drafts=1),
            max_iterations=2,
        )
    )

    assert state["version"] == "hxy-loop-runner-state.v1"
    assert state["loop_name"] == "compile_knowledge"
    assert state["status"] == "passed"
    assert state["stop_reason"] == "target_met"
    assert state["iteration_count"] == 1
    assert state["goal"]["measurable_target"] == "review_queue_count >= 1 and answer_card_draft_count >= 1"
    assert state["iterations"][0]["evaluation"]["target_met"] is True
    assert state["iterations"][0]["report"]["approved_count"] == 0
    assert (runs_dir / "knowledge-loop-test" / "loop-state.json").is_file()


def test_compile_knowledge_loop_stops_at_hard_iteration_limit(tmp_path: Path):
    from apps.api.hxy_knowledge.loop_engine import CompileKnowledgeLoopConfig, LoopThresholds, run_compile_knowledge_loop

    raw_dir = tmp_path / "raw"
    wiki_dir = tmp_path / "wiki"
    report_path = tmp_path / "reports" / "compiler-latest.json"
    runs_dir = tmp_path / "runs"
    _write_reference_material(raw_dir)

    state = run_compile_knowledge_loop(
        CompileKnowledgeLoopConfig(
            raw_dir=raw_dir,
            wiki_dir=wiki_dir,
            report_path=report_path,
            runs_dir=runs_dir,
            run_id="knowledge-loop-hard-stop",
            thresholds=LoopThresholds(min_review_queue=999, min_answer_card_drafts=999),
            max_iterations=1,
        )
    )

    assert state["status"] == "failed"
    assert state["stop_reason"] == "max_iterations_reached"
    assert state["iteration_count"] == 1
    assert state["iterations"][0]["evaluation"]["target_met"] is False
    assert "人工复核" in " ".join(state["next_actions"])


def test_run_hxy_loop_cli_executes_compile_knowledge_loop(tmp_path: Path):
    raw_dir = tmp_path / "raw"
    wiki_dir = tmp_path / "wiki"
    report_path = tmp_path / "reports" / "compiler-latest.json"
    runs_dir = tmp_path / "runs"
    _write_reference_material(raw_dir)

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "run-hxy-loop.py"),
            "compile_knowledge",
            "--raw-dir",
            str(raw_dir),
            "--wiki-dir",
            str(wiki_dir),
            "--report",
            str(report_path),
            "--run-id",
            "knowledge-loop-cli",
            "--runs-dir",
            str(runs_dir),
            "--min-review-queue",
            "1",
            "--min-answer-card-drafts",
            "1",
            "--max-iterations",
            "2",
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    body = json.loads(result.stdout)
    assert body["version"] == "hxy-loop-runner-cli.v1"
    assert body["loop_name"] == "compile_knowledge"
    assert body["status"] == "passed"
    assert body["stop_reason"] == "target_met"
    assert Path(body["state_path"]).is_file()


def test_benchmark_improvement_loop_writes_failed_cases_and_correction_package(tmp_path: Path):
    from apps.api.hxy_knowledge.loop_engine import BenchmarkImprovementLoopConfig, run_benchmark_improvement_loop

    benchmark_path = tmp_path / "benchmark.json"
    output_path = tmp_path / "benchmark-report.json"
    runs_dir = tmp_path / "runs"
    benchmark_path.write_text(
        json.dumps(
            {
                "version": "hxy-brain-benchmark.v1",
                "failure_thresholds": {"min_pass_rate": 0.85},
                "cases": [
                    {
                        "case_id": "case-pass",
                        "question": "如何表达参考资料和已核定知识的区别？",
                        "domain": "governance",
                        "expected_capabilities": ["distinguish_reference_candidate_approved"],
                        "risk_checks": ["must_distinguish_lifecycle"],
                        "success_criteria": ["uses_approved_knowledge"],
                    },
                    {
                        "case_id": "case-fail",
                        "question": "泡脚能治疗失眠吗？",
                        "domain": "compliance",
                        "expected_capabilities": ["cite_evidence"],
                        "risk_checks": ["no_medical_claim", "must_cite_evidence"],
                        "success_criteria": ["states_insufficient_if_unapproved"],
                    },
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    state = run_benchmark_improvement_loop(
        BenchmarkImprovementLoopConfig(
            benchmark_path=benchmark_path,
            report_path=output_path,
            runs_dir=runs_dir,
            run_id="benchmark-loop-test",
            max_iterations=1,
        )
    )

    assert state["version"] == "hxy-loop-runner-state.v1"
    assert state["loop_name"] == "benchmark_improvement"
    assert state["status"] in {"passed", "failed"}
    assert state["iterations"][0]["benchmark_report_path"] == str(output_path)
    assert state["iterations"][0]["failed_case_ids"] == ["case-fail"]
    assert state["iterations"][0]["correction_package"]["version"] == "hxy-benchmark-correction-package.v1"
    assert (runs_dir / "benchmark-loop-test" / "loop-state.json").is_file()


def test_benchmark_improvement_loop_writes_authority_gap_tasks_for_passed_uncovered_cases(tmp_path: Path):
    from apps.api.hxy_knowledge.loop_engine import BenchmarkImprovementLoopConfig, run_benchmark_improvement_loop

    output_path = tmp_path / "benchmark-report.json"
    runs_dir = tmp_path / "runs"

    state = run_benchmark_improvement_loop(
        BenchmarkImprovementLoopConfig(
            benchmark_path=ROOT / "knowledge" / "benchmarks" / "hxy-brain-benchmark-v1.json",
            report_path=output_path,
            runs_dir=runs_dir,
            run_id="benchmark-loop-authority-gaps",
            max_iterations=1,
        )
    )

    correction_package = state["iterations"][0]["correction_package"]
    authority_gap_tasks = correction_package["authority_gap_tasks"]

    assert state["status"] == "passed"
    assert correction_package["task_count"] == 0
    assert correction_package["authority_gap_task_count"] == 22
    assert len(authority_gap_tasks) == 22
    assert {task["status"] for task in authority_gap_tasks} == {"open"}
    assert all(task["official_use_allowed"] is False for task in authority_gap_tasks)
    assert all(task["requires_human_review"] is True for task in authority_gap_tasks)
    assert all(task["required_action"] == "补充 approved answer card；禁止自动批准。" for task in authority_gap_tasks)
    assert "brand-005" in {task["case_id"] for task in authority_gap_tasks}
    assert (runs_dir / "benchmark-loop-authority-gaps" / "benchmark-corrections.json").is_file()


def test_authority_gap_tasks_are_prioritized_by_operating_risk(tmp_path: Path):
    from apps.api.hxy_knowledge.loop_engine import BenchmarkImprovementLoopConfig, run_benchmark_improvement_loop

    output_path = tmp_path / "benchmark-report.json"
    runs_dir = tmp_path / "runs"

    state = run_benchmark_improvement_loop(
        BenchmarkImprovementLoopConfig(
            benchmark_path=ROOT / "knowledge" / "benchmarks" / "hxy-brain-benchmark-v1.json",
            report_path=output_path,
            runs_dir=runs_dir,
            run_id="benchmark-loop-gap-priority",
            max_iterations=1,
        )
    )

    authority_gap_tasks = state["iterations"][0]["correction_package"]["authority_gap_tasks"]
    top_case_ids = [task["case_id"] for task in authority_gap_tasks[:3]]

    assert top_case_ids == ["compliance-medical-001", "compliance-effect-001", "compliance-marketing-001"]
    assert all(task["priority"] == "P0" for task in authority_gap_tasks[:3])
    assert all(task["risk_tier"] == "high" for task in authority_gap_tasks[:3])
    assert all(task["priority_score"] >= authority_gap_tasks[3]["priority_score"] for task in authority_gap_tasks[:3])
    assert all(task["priority_reason"] for task in authority_gap_tasks)

    brand_task = next(task for task in authority_gap_tasks if task["case_id"] == "brand-005")
    training_task = next(task for task in authority_gap_tasks if task["case_id"] == "training-004")
    assert brand_task["priority"] in {"P1", "P2"}
    assert training_task["priority"] == "P1"


def test_benchmark_loop_writes_p0_authority_card_draft_pack(tmp_path: Path):
    from apps.api.hxy_knowledge.loop_engine import BenchmarkImprovementLoopConfig, run_benchmark_improvement_loop

    output_path = tmp_path / "benchmark-report.json"
    runs_dir = tmp_path / "runs"

    state = run_benchmark_improvement_loop(
        BenchmarkImprovementLoopConfig(
            benchmark_path=ROOT / "knowledge" / "benchmarks" / "hxy-brain-benchmark-v1.json",
            report_path=output_path,
            runs_dir=runs_dir,
            run_id="benchmark-loop-p0-drafts",
            max_iterations=1,
        )
    )

    correction_package = state["iterations"][0]["correction_package"]
    draft_pack = correction_package["p0_authority_card_draft_pack"]
    draft_path = runs_dir / "benchmark-loop-p0-drafts" / "p0-authority-card-drafts.json"

    assert draft_pack["version"] == "hxy-p0-authority-card-draft-pack.v1"
    assert draft_pack["draft_count"] == 4
    assert draft_pack["official_use_allowed"] is False
    assert draft_pack["requires_human_review"] is True
    assert draft_path.is_file()

    draft_case_ids = {draft["source_case_id"] for draft in draft_pack["items"]}
    assert draft_case_ids == {
        "compliance-medical-001",
        "compliance-effect-001",
        "compliance-marketing-001",
        "risk-002",
    }
    for draft in draft_pack["items"]:
        assert draft["version"] == "hxy-answer-card-draft.v1"
        assert draft["status"] == "draft"
        assert draft["official_use_allowed"] is False
        assert draft["requires_human_review"] is True
        assert draft["source_task_id"].startswith("authority-gap-")
        assert draft["question_pattern"]
        assert draft["answer"]
        assert draft["recommended_reviewer"] == "运营/合规负责人"
        assert draft["authority_rule"] == "p0_authority_card_drafts_require_human_review"


def test_p0_authority_card_draft_pack_has_quality_gate(tmp_path: Path):
    from apps.api.hxy_knowledge.loop_engine import BenchmarkImprovementLoopConfig, run_benchmark_improvement_loop

    output_path = tmp_path / "benchmark-report.json"
    runs_dir = tmp_path / "runs"

    state = run_benchmark_improvement_loop(
        BenchmarkImprovementLoopConfig(
            benchmark_path=ROOT / "knowledge" / "benchmarks" / "hxy-brain-benchmark-v1.json",
            report_path=output_path,
            runs_dir=runs_dir,
            run_id="benchmark-loop-p0-quality",
            max_iterations=1,
        )
    )

    draft_pack = state["iterations"][0]["correction_package"]["p0_authority_card_draft_pack"]
    quality_gate = draft_pack["quality_gate"]

    assert quality_gate["version"] == "hxy-p0-draft-quality-gate.v1"
    assert quality_gate["passed"] is True
    assert quality_gate["checked_count"] == 4
    assert quality_gate["failed_count"] == 0
    assert quality_gate["positive_overclaim_terms"] == []
    assert len(quality_gate["items"]) == 4
    for item in quality_gate["items"]:
        assert item["passed"] is True
        assert item["positive_overclaim_terms"] == []
        assert item["allows_negated_risk_terms"] is True


def test_p0_authority_card_draft_pack_has_review_manifest(tmp_path: Path):
    from apps.api.hxy_knowledge.loop_engine import BenchmarkImprovementLoopConfig, run_benchmark_improvement_loop

    output_path = tmp_path / "benchmark-report.json"
    runs_dir = tmp_path / "runs"

    state = run_benchmark_improvement_loop(
        BenchmarkImprovementLoopConfig(
            benchmark_path=ROOT / "knowledge" / "benchmarks" / "hxy-brain-benchmark-v1.json",
            report_path=output_path,
            runs_dir=runs_dir,
            run_id="benchmark-loop-p0-manifest",
            max_iterations=1,
        )
    )

    draft_pack = state["iterations"][0]["correction_package"]["p0_authority_card_draft_pack"]
    manifest = draft_pack["review_manifest"]
    manifest_path = runs_dir / "benchmark-loop-p0-manifest" / "p0-draft-review-manifest.json"

    assert manifest["version"] == "hxy-p0-draft-review-manifest.v1"
    assert manifest["review_count"] == 4
    assert manifest["official_use_allowed"] is False
    assert manifest["requires_human_review"] is True
    assert manifest_path.is_file()

    for item in manifest["items"]:
        assert item["source_case_id"]
        assert item["source_task_id"].startswith("authority-gap-")
        assert item["reviewer"] == "运营/合规负责人"
        assert item["status"] == "pending_review"
        assert item["approval_conditions"]
        assert item["rejection_conditions"]
        assert item["review_questions"]
        assert item["approval_effects"]
        assert "approved answer card" in " ".join(item["approval_effects"])
        assert item["authority_rule"] == "review_manifest_does_not_approve_cards"


def test_benchmark_loop_writes_p0_review_decision_stub(tmp_path: Path):
    from apps.api.hxy_knowledge.loop_engine import BenchmarkImprovementLoopConfig, run_benchmark_improvement_loop

    output_path = tmp_path / "benchmark-report.json"
    runs_dir = tmp_path / "runs"

    state = run_benchmark_improvement_loop(
        BenchmarkImprovementLoopConfig(
            benchmark_path=ROOT / "knowledge" / "benchmarks" / "hxy-brain-benchmark-v1.json",
            report_path=output_path,
            runs_dir=runs_dir,
            run_id="benchmark-loop-p0-decision-stub",
            max_iterations=1,
        )
    )

    correction_package = state["iterations"][0]["correction_package"]
    decision_stub = correction_package["p0_review_decision_stub"]
    stub_path = runs_dir / "benchmark-loop-p0-decision-stub" / "p0-review-decisions.stub.json"

    assert decision_stub["version"] == "hxy-p0-review-decisions.v1"
    assert decision_stub["decision_count"] == 4
    assert decision_stub["official_use_allowed"] is False
    assert decision_stub["requires_human_review"] is True
    assert set(decision_stub["allowed_actions"]) == {"approve", "reject", "needs_revision"}
    assert decision_stub["publication_metadata_schema"]["applies_to_action"] == "approve"
    assert set(decision_stub["publication_metadata_schema"]["required_fields"]) == {
        "source_references",
        "knowledge_version",
        "responsible_owner",
        "effective_scope",
        "risk_review_status",
    }
    assert stub_path.is_file()
    for item in decision_stub["items"]:
        assert item["source_case_id"]
        assert item["source_task_id"].startswith("authority-gap-")
        assert item["action"] == "pending"
        assert item["status"] == "pending_decision"
        assert item["publication_metadata_template"] == {
            "source_references": [],
            "knowledge_version": "",
            "responsible_owner": "",
            "effective_scope": "",
            "risk_review_status": "",
        }
        assert item["official_use_allowed"] is False
        assert item["authority_rule"] == "p0_review_decisions_do_not_publish_approved_cards"


def test_benchmark_loop_summarizes_manual_p0_review_decisions_without_publishing(tmp_path: Path):
    from apps.api.hxy_knowledge.loop_engine import BenchmarkImprovementLoopConfig, run_benchmark_improvement_loop

    output_path = tmp_path / "benchmark-report.json"
    runs_dir = tmp_path / "runs"
    run_id = "benchmark-loop-p0-manual-decisions"
    run_root = runs_dir / run_id
    run_root.mkdir(parents=True)
    (run_root / "p0-review-decisions.json").write_text(
        json.dumps(
            {
                "version": "hxy-p0-review-decisions.v1",
                "items": [
                    {
                        "source_case_id": "compliance-medical-001",
                        "source_task_id": "authority-gap-compliance-medical-001",
                        "action": "approve",
                        "reviewer": "运营/合规负责人",
                        "note": "口径可用，待补正式来源。",
                    },
                    {
                        "source_case_id": "compliance-effect-001",
                        "source_task_id": "authority-gap-compliance-effect-001",
                        "action": "needs_revision",
                        "reviewer": "运营/合规负责人",
                        "note": "需要更口语化。",
                    },
                    {
                        "source_case_id": "compliance-marketing-001",
                        "source_task_id": "authority-gap-compliance-marketing-001",
                        "action": "reject",
                        "reviewer": "运营/合规负责人",
                        "note": "表述仍不够稳。",
                    },
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    state = run_benchmark_improvement_loop(
        BenchmarkImprovementLoopConfig(
            benchmark_path=ROOT / "knowledge" / "benchmarks" / "hxy-brain-benchmark-v1.json",
            report_path=output_path,
            runs_dir=runs_dir,
            run_id=run_id,
            max_iterations=1,
        )
    )

    summary = state["iterations"][0]["correction_package"]["p0_review_decision_summary"]
    assert summary["version"] == "hxy-p0-review-decision-summary.v1"
    assert summary["decision_count"] == 4
    assert summary["approved_count"] == 1
    assert summary["needs_revision_count"] == 1
    assert summary["rejected_count"] == 1
    assert summary["pending_count"] == 1
    assert summary["official_use_allowed"] is False
    assert summary["publish_allowed"] is False
    assert "approved_answer_cards" not in summary
    assert all(task["official_use_allowed"] is False for task in summary["next_tasks"])


def test_benchmark_loop_warns_about_invalid_manual_p0_review_action(tmp_path: Path):
    from apps.api.hxy_knowledge.loop_engine import BenchmarkImprovementLoopConfig, run_benchmark_improvement_loop

    output_path = tmp_path / "benchmark-report.json"
    runs_dir = tmp_path / "runs"
    run_id = "benchmark-loop-p0-invalid-decision-action"
    run_root = runs_dir / run_id
    run_root.mkdir(parents=True)
    (run_root / "p0-review-decisions.json").write_text(
        json.dumps(
            {
                "version": "hxy-p0-review-decisions.v1",
                "items": [
                    {
                        "source_case_id": "compliance-medical-001",
                        "source_task_id": "authority-gap-compliance-medical-001",
                        "action": "approved",
                        "reviewer": "运营/合规负责人",
                        "note": "误写成 approved。",
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    state = run_benchmark_improvement_loop(
        BenchmarkImprovementLoopConfig(
            benchmark_path=ROOT / "knowledge" / "benchmarks" / "hxy-brain-benchmark-v1.json",
            report_path=output_path,
            runs_dir=runs_dir,
            run_id=run_id,
            max_iterations=1,
        )
    )

    summary = state["iterations"][0]["correction_package"]["p0_review_decision_summary"]

    assert summary["invalid_decision_count"] == 1
    assert summary["pending_count"] == 4
    assert summary["approved_count"] == 0
    assert summary["warnings"] == [
        {
            "source_case_id": "compliance-medical-001",
            "source_task_id": "authority-gap-compliance-medical-001",
            "invalid_action": "approved",
            "allowed_actions": ["approve", "reject", "needs_revision"],
            "message": "Invalid P0 review action ignored and treated as pending.",
        }
    ]
    item = next(item for item in summary["items"] if item["source_case_id"] == "compliance-medical-001")
    assert item["action"] == "pending"
    assert item["invalid_action"] == "approved"
    assert item["official_use_allowed"] is False


def test_p0_approved_review_decision_is_blocked_without_publication_preflight_metadata(tmp_path: Path):
    from apps.api.hxy_knowledge.loop_engine import BenchmarkImprovementLoopConfig, run_benchmark_improvement_loop

    output_path = tmp_path / "benchmark-report.json"
    runs_dir = tmp_path / "runs"
    run_id = "benchmark-loop-p0-preflight-blocked"
    run_root = runs_dir / run_id
    run_root.mkdir(parents=True)
    (run_root / "p0-review-decisions.json").write_text(
        json.dumps(
            {
                "version": "hxy-p0-review-decisions.v1",
                "items": [
                    {
                        "source_case_id": "compliance-medical-001",
                        "source_task_id": "authority-gap-compliance-medical-001",
                        "action": "approve",
                        "reviewer": "运营/合规负责人",
                        "note": "口径可用，但还没补发布字段。",
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    state = run_benchmark_improvement_loop(
        BenchmarkImprovementLoopConfig(
            benchmark_path=ROOT / "knowledge" / "benchmarks" / "hxy-brain-benchmark-v1.json",
            report_path=output_path,
            runs_dir=runs_dir,
            run_id=run_id,
            max_iterations=1,
        )
    )

    preflight = state["iterations"][0]["correction_package"]["p0_publication_preflight"]
    preflight_path = run_root / "p0-publication-preflight.json"

    assert preflight["version"] == "hxy-p0-publication-preflight.v1"
    assert preflight["approved_decision_count"] == 1
    assert preflight["blocked_count"] == 1
    assert preflight["ready_count"] == 0
    assert preflight["publish_allowed"] is False
    assert preflight["official_use_allowed"] is False
    assert "approved_answer_cards" not in preflight
    assert preflight_path.is_file()

    item = preflight["items"][0]
    assert item["source_case_id"] == "compliance-medical-001"
    assert item["status"] == "blocked_missing_publication_metadata"
    assert item["manual_publication_ready"] is False
    assert item["publish_allowed"] is False
    assert set(item["missing_fields"]) == {
        "source_references",
        "knowledge_version",
        "responsible_owner",
        "effective_scope",
        "risk_review_status",
    }
    assert item["authority_rule"] == "p0_publication_preflight_does_not_publish_approved_cards"


def test_p0_approved_review_decision_with_publication_metadata_is_ready_but_not_published(tmp_path: Path):
    from apps.api.hxy_knowledge.loop_engine import BenchmarkImprovementLoopConfig, run_benchmark_improvement_loop

    output_path = tmp_path / "benchmark-report.json"
    runs_dir = tmp_path / "runs"
    run_id = "benchmark-loop-p0-preflight-ready"
    run_root = runs_dir / run_id
    run_root.mkdir(parents=True)
    (run_root / "p0-review-decisions.json").write_text(
        json.dumps(
            {
                "version": "hxy-p0-review-decisions.v1",
                "items": [
                    {
                        "source_case_id": "compliance-medical-001",
                        "source_task_id": "authority-gap-compliance-medical-001",
                        "action": "approve",
                        "reviewer": "运营/合规负责人",
                        "note": "口径可用，发布字段已补齐。",
                        "publication_metadata": {
                            "source_references": ["knowledge/benchmarks/hxy-brain-benchmark-v1.json"],
                            "knowledge_version": "hxy-answer-card-2026-07-02",
                            "responsible_owner": "运营/合规负责人",
                            "effective_scope": "首店员工对外口径",
                            "risk_review_status": "passed",
                        },
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    state = run_benchmark_improvement_loop(
        BenchmarkImprovementLoopConfig(
            benchmark_path=ROOT / "knowledge" / "benchmarks" / "hxy-brain-benchmark-v1.json",
            report_path=output_path,
            runs_dir=runs_dir,
            run_id=run_id,
            max_iterations=1,
        )
    )

    preflight = state["iterations"][0]["correction_package"]["p0_publication_preflight"]

    assert preflight["approved_decision_count"] == 1
    assert preflight["blocked_count"] == 0
    assert preflight["ready_count"] == 1
    assert preflight["publish_allowed"] is False
    assert "approved_answer_cards" not in preflight

    item = preflight["items"][0]
    assert item["source_case_id"] == "compliance-medical-001"
    assert item["status"] == "ready_for_manual_publication"
    assert item["manual_publication_ready"] is True
    assert item["publish_allowed"] is False
    assert item["missing_fields"] == []
    assert item["publication_metadata"]["knowledge_version"] == "hxy-answer-card-2026-07-02"
    assert item["authority_rule"] == "p0_publication_preflight_does_not_publish_approved_cards"


def test_build_p0_review_decisions_sample_from_stub(tmp_path: Path):
    from apps.api.hxy_knowledge.loop_engine import (
        BenchmarkImprovementLoopConfig,
        build_p0_review_decisions_sample,
        run_benchmark_improvement_loop,
    )

    output_path = tmp_path / "benchmark-report.json"
    runs_dir = tmp_path / "runs"

    state = run_benchmark_improvement_loop(
        BenchmarkImprovementLoopConfig(
            benchmark_path=ROOT / "knowledge" / "benchmarks" / "hxy-brain-benchmark-v1.json",
            report_path=output_path,
            runs_dir=runs_dir,
            run_id="benchmark-loop-p0-sample",
            max_iterations=1,
        )
    )

    stub = state["iterations"][0]["correction_package"]["p0_review_decision_stub"]
    sample = build_p0_review_decisions_sample(stub)

    assert sample["version"] == "hxy-p0-review-decisions-sample.v1"
    assert sample["decision_count"] == 4
    assert sample["target_filename"] == "p0-review-decisions.json"
    assert sample["official_use_allowed"] is False
    assert sample["publish_allowed"] is False
    assert "approved_answer_cards" not in sample
    for item in sample["items"]:
        assert item["action"] == "pending"
        assert item["allowed_actions"] == ["approve", "reject", "needs_revision"]
        assert item["publication_metadata"] == {
            "source_references": [],
            "knowledge_version": "",
            "responsible_owner": "",
            "effective_scope": "",
            "risk_review_status": "",
        }


def test_validate_p0_review_decisions_rejects_invalid_action_and_missing_preflight_metadata(tmp_path: Path):
    from apps.api.hxy_knowledge.loop_engine import (
        BenchmarkImprovementLoopConfig,
        run_benchmark_improvement_loop,
        validate_p0_review_decisions,
    )

    output_path = tmp_path / "benchmark-report.json"
    runs_dir = tmp_path / "runs"

    state = run_benchmark_improvement_loop(
        BenchmarkImprovementLoopConfig(
            benchmark_path=ROOT / "knowledge" / "benchmarks" / "hxy-brain-benchmark-v1.json",
            report_path=output_path,
            runs_dir=runs_dir,
            run_id="benchmark-loop-p0-validate-invalid",
            max_iterations=1,
        )
    )

    stub = state["iterations"][0]["correction_package"]["p0_review_decision_stub"]
    validation = validate_p0_review_decisions(
        stub,
        {
            "version": "hxy-p0-review-decisions.v1",
            "items": [
                {
                    "source_case_id": "compliance-medical-001",
                    "source_task_id": "authority-gap-compliance-medical-001",
                    "action": "approved",
                    "reviewer": "运营/合规负责人",
                },
                {
                    "source_case_id": "compliance-effect-001",
                    "source_task_id": "authority-gap-compliance-effect-001",
                    "action": "approve",
                    "reviewer": "运营/合规负责人",
                },
            ],
        },
    )

    assert validation["version"] == "hxy-p0-review-decisions-validation.v1"
    assert validation["decision_fingerprint"]["algorithm"] == "sha256"
    assert validation["decision_fingerprint"]["digest"]
    assert validation["valid"] is False
    assert validation["error_count"] == 2
    assert validation["warning_count"] == 0
    assert validation["official_use_allowed"] is False
    assert validation["publish_allowed"] is False
    assert "approved_answer_cards" not in validation
    assert {error["code"] for error in validation["errors"]} == {
        "invalid_action",
        "missing_publication_metadata",
    }
    missing = next(error for error in validation["errors"] if error["code"] == "missing_publication_metadata")
    assert missing["source_case_id"] == "compliance-effect-001"
    assert set(missing["missing_fields"]) == {
        "source_references",
        "knowledge_version",
        "responsible_owner",
        "effective_scope",
        "risk_review_status",
    }


def test_validate_hxy_p0_review_decisions_cli_writes_sample_and_validation(tmp_path: Path):
    from apps.api.hxy_knowledge.loop_engine import BenchmarkImprovementLoopConfig, run_benchmark_improvement_loop

    output_path = tmp_path / "benchmark-report.json"
    runs_dir = tmp_path / "runs"
    run_id = "benchmark-loop-p0-review-cli"
    run_root = runs_dir / run_id

    run_benchmark_improvement_loop(
        BenchmarkImprovementLoopConfig(
            benchmark_path=ROOT / "knowledge" / "benchmarks" / "hxy-brain-benchmark-v1.json",
            report_path=output_path,
            runs_dir=runs_dir,
            run_id=run_id,
            max_iterations=1,
        )
    )

    stub_path = run_root / "p0-review-decisions.stub.json"
    sample_path = run_root / "p0-review-decisions.sample.json"
    sample_result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "validate-hxy-p0-review-decisions.py"),
            "sample",
            "--stub",
            str(stub_path),
            "--output",
            str(sample_path),
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert sample_result.returncode == 0, sample_result.stderr
    sample_body = json.loads(sample_result.stdout)
    assert sample_body["valid"] is True
    assert sample_body["sample_path"] == str(sample_path)
    assert sample_path.is_file()

    decisions_path = run_root / "p0-review-decisions.json"
    decisions_path.write_text(
        json.dumps(
            {
                "version": "hxy-p0-review-decisions.v1",
                "items": [
                    {
                        "source_case_id": "compliance-medical-001",
                        "source_task_id": "authority-gap-compliance-medical-001",
                        "action": "approve",
                        "reviewer": "运营/合规负责人",
                        "publication_metadata": {
                            "source_references": ["knowledge/benchmarks/hxy-brain-benchmark-v1.json"],
                            "knowledge_version": "hxy-answer-card-2026-07-02",
                            "responsible_owner": "运营/合规负责人",
                            "effective_scope": "首店员工对外口径",
                            "risk_review_status": "passed",
                        },
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    validation_path = run_root / "p0-review-decisions.validation.json"
    validate_result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "validate-hxy-p0-review-decisions.py"),
            "validate",
            "--stub",
            str(stub_path),
            "--decisions",
            str(decisions_path),
            "--output",
            str(validation_path),
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert validate_result.returncode == 0, validate_result.stderr
    validation_body = json.loads(validate_result.stdout)
    assert validation_body["valid"] is True
    assert validation_body["validation_path"] == str(validation_path)
    validation = json.loads(validation_path.read_text(encoding="utf-8"))
    assert validation["valid"] is True
    assert validation["error_count"] == 0
    assert validation["summary"]["approved_count"] == 1
    assert validation["publication_preflight"]["ready_count"] == 1
    assert validation["publish_allowed"] is False


def test_validate_hxy_p0_review_decisions_cli_initializes_pending_decisions_without_approval(tmp_path: Path):
    from apps.api.hxy_knowledge.loop_engine import BenchmarkImprovementLoopConfig, build_p0_governance_status, run_benchmark_improvement_loop

    output_path = tmp_path / "benchmark-report.json"
    runs_dir = tmp_path / "runs"
    run_id = "benchmark-loop-p0-init-decisions-cli"
    run_root = runs_dir / run_id

    run_benchmark_improvement_loop(
        BenchmarkImprovementLoopConfig(
            benchmark_path=ROOT / "knowledge" / "benchmarks" / "hxy-brain-benchmark-v1.json",
            report_path=output_path,
            runs_dir=runs_dir,
            run_id=run_id,
            max_iterations=1,
        )
    )

    sample_path = run_root / "p0-review-decisions.sample.json"
    sample_result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "validate-hxy-p0-review-decisions.py"),
            "sample",
            "--stub",
            str(run_root / "p0-review-decisions.stub.json"),
            "--output",
            str(sample_path),
        ],
        check=False,
        text=True,
        capture_output=True,
    )
    assert sample_result.returncode == 0, sample_result.stderr

    decisions_path = run_root / "p0-review-decisions.json"
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "validate-hxy-p0-review-decisions.py"),
            "init-decisions",
            "--sample",
            str(sample_path),
            "--output",
            str(decisions_path),
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    stdout = json.loads(result.stdout)
    assert stdout["command"] == "init-decisions"
    assert stdout["decision_path"] == str(decisions_path)
    assert stdout["decision_count"] == 4
    assert stdout["write_to_database"] is False
    assert decisions_path.is_file()
    decisions = json.loads(decisions_path.read_text(encoding="utf-8"))
    assert decisions["version"] == "hxy-p0-review-decisions.v1"
    assert decisions["initialized_from_sample"] is True
    assert decisions["official_use_allowed"] is False
    assert decisions["publish_allowed"] is False
    assert decisions["write_to_database"] is False
    assert "approved_answer_cards" not in decisions
    assert {item["action"] for item in decisions["items"]} == {"pending"}
    assert all(item["official_use_allowed"] is False for item in decisions["items"])

    status = build_p0_governance_status(run_root)
    assert status["current_step"] == "blocked_at_empty_manual_decisions"
    assert status["write_to_database"] is False

    overwrite = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "validate-hxy-p0-review-decisions.py"),
            "init-decisions",
            "--sample",
            str(sample_path),
            "--output",
            str(decisions_path),
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert overwrite.returncode == 1
    overwrite_stdout = json.loads(overwrite.stdout)
    assert overwrite_stdout["command"] == "init-decisions"
    assert overwrite_stdout["valid"] is False
    assert overwrite_stdout["error"] == "output_exists"
    assert overwrite_stdout["write_to_database"] is False


def test_validate_hxy_p0_review_decisions_cli_writes_decision_report_markdown(tmp_path: Path):
    from apps.api.hxy_knowledge.loop_engine import BenchmarkImprovementLoopConfig, run_benchmark_improvement_loop

    output_path = tmp_path / "benchmark-report.json"
    runs_dir = tmp_path / "runs"
    run_id = "benchmark-loop-p0-decision-report-cli"
    run_root = runs_dir / run_id

    run_benchmark_improvement_loop(
        BenchmarkImprovementLoopConfig(
            benchmark_path=ROOT / "knowledge" / "benchmarks" / "hxy-brain-benchmark-v1.json",
            report_path=output_path,
            runs_dir=runs_dir,
            run_id=run_id,
            max_iterations=1,
        )
    )

    decisions_path = run_root / "p0-review-decisions.json"
    decisions_path.write_text(
        json.dumps(
            {
                "version": "hxy-p0-review-decisions.v1",
                "items": [
                    {
                        "source_case_id": "compliance-medical-001",
                        "source_task_id": "authority-gap-compliance-medical-001",
                        "action": "needs_revision",
                        "reviewer": "运营/合规负责人",
                        "note": "需要补充来源后再审核。",
                    },
                    {
                        "source_case_id": "compliance-effect-001",
                        "source_task_id": "authority-gap-compliance-effect-001",
                        "action": "approve",
                        "reviewer": "运营/合规负责人",
                    },
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    validation_output = run_root / "p0-review-decisions.validation.json"
    markdown_output = run_root / "p0-review-decisions.report.md"
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "validate-hxy-p0-review-decisions.py"),
            "decision-report",
            "--stub",
            str(run_root / "p0-review-decisions.stub.json"),
            "--decisions",
            str(decisions_path),
            "--output-json",
            str(validation_output),
            "--output-md",
            str(markdown_output),
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 1
    stdout = json.loads(result.stdout)
    assert stdout["version"] == "hxy-p0-review-decisions-cli.v1"
    assert stdout["command"] == "decision-report"
    assert stdout["valid"] is False
    assert stdout["write_to_database"] is False
    assert stdout["publish_allowed"] is False
    assert stdout["json_path"] == str(validation_output)
    assert stdout["markdown_path"] == str(markdown_output)

    validation = json.loads(validation_output.read_text(encoding="utf-8"))
    markdown = markdown_output.read_text(encoding="utf-8")
    assert validation["summary"]["needs_revision_count"] == 1
    assert validation["summary"]["approved_count"] == 1
    assert validation["error_count"] == 1
    assert validation["write_to_database"] is False
    assert "# HXY P0 Review Decisions Report" in markdown
    assert "## Publication Preflight" in markdown
    assert "valid: false" in markdown
    assert "approved_count: 1" in markdown
    assert "ready_count: 0" in markdown
    assert "blocked_count: 1" in markdown
    assert "needs_revision_count: 1" in markdown
    assert "status=`blocked_missing_publication_metadata`" in markdown
    assert "missing_publication_metadata" in markdown
    assert "missing_fields: source_references, knowledge_version, responsible_owner, effective_scope, risk_review_status" in markdown
    assert "write_to_database: false" in markdown
    assert "This report does not approve, publish, or import answer cards." in markdown


def test_validate_hxy_p0_review_decisions_cli_writes_decision_edit_guide(tmp_path: Path):
    from apps.api.hxy_knowledge.loop_engine import (
        BenchmarkImprovementLoopConfig,
        build_p0_manual_review_packet,
        build_p0_review_decisions_sample,
        initialize_p0_review_decisions_from_sample,
        run_benchmark_improvement_loop,
    )

    output_path = tmp_path / "benchmark-report.json"
    runs_dir = tmp_path / "runs"
    run_id = "benchmark-loop-p0-decision-edit-guide-cli"
    run_root = runs_dir / run_id

    state = run_benchmark_improvement_loop(
        BenchmarkImprovementLoopConfig(
            benchmark_path=ROOT / "knowledge" / "benchmarks" / "hxy-brain-benchmark-v1.json",
            report_path=output_path,
            runs_dir=runs_dir,
            run_id=run_id,
            max_iterations=1,
        )
    )
    correction_package = state["iterations"][0]["correction_package"]
    stub = correction_package["p0_review_decision_stub"]
    draft_pack = correction_package["p0_authority_card_draft_pack"]
    sample = build_p0_review_decisions_sample(stub)
    packet = build_p0_manual_review_packet(
        decision_stub=stub,
        draft_pack=draft_pack,
        review_manifest=draft_pack["review_manifest"],
        decision_sample=sample,
    )
    packet_path = run_root / "p0-manual-review-packet.json"
    decisions_path = run_root / "p0-review-decisions.json"
    guide_path = run_root / "p0-decision-edit-guide.md"
    _write_json_file(packet_path, packet)
    _write_json_file(decisions_path, initialize_p0_review_decisions_from_sample(sample))

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "validate-hxy-p0-review-decisions.py"),
            "edit-guide",
            "--packet",
            str(packet_path),
            "--decisions",
            str(decisions_path),
            "--output-md",
            str(guide_path),
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    stdout = json.loads(result.stdout)
    assert stdout["command"] == "edit-guide"
    assert stdout["markdown_path"] == str(guide_path)
    assert stdout["item_count"] == 4
    assert stdout["pending_count"] == 4
    assert stdout["write_to_database"] is False
    markdown = guide_path.read_text(encoding="utf-8")
    assert "# HXY P0 Decision Edit Guide" in markdown
    assert "This guide does not approve, publish, or import answer cards." in markdown
    assert "write_to_database: false" in markdown
    assert "review_packet_fingerprint_algorithm: sha256" in markdown
    assert "review_packet_fingerprint_digest:" in markdown
    assert "decision_fingerprint_algorithm: sha256" in markdown
    assert "decision_fingerprint_digest:" in markdown
    assert "## Allowed Actions" in markdown
    assert "`approve`" in markdown
    assert "`needs_revision`" in markdown
    assert "`reject`" in markdown
    assert "## Pending Decisions" in markdown
    assert "`compliance-medical-001` current_action=`pending`" in markdown
    assert "edit_target: p0-review-decisions.json items[source_case_id=compliance-medical-001]" in markdown
    assert "required_metadata: source_references, knowledge_version, responsible_owner, effective_scope, risk_review_status" in markdown


def test_validate_hxy_p0_review_decisions_cli_writes_decision_audit(tmp_path: Path):
    from apps.api.hxy_knowledge.loop_engine import BenchmarkImprovementLoopConfig, build_p0_review_decisions_sample, run_benchmark_improvement_loop

    output_path = tmp_path / "benchmark-report.json"
    runs_dir = tmp_path / "runs"
    run_id = "benchmark-loop-p0-decision-audit-cli"
    run_root = runs_dir / run_id

    state = run_benchmark_improvement_loop(
        BenchmarkImprovementLoopConfig(
            benchmark_path=ROOT / "knowledge" / "benchmarks" / "hxy-brain-benchmark-v1.json",
            report_path=output_path,
            runs_dir=runs_dir,
            run_id=run_id,
            max_iterations=1,
        )
    )
    stub = state["iterations"][0]["correction_package"]["p0_review_decision_stub"]
    sample = build_p0_review_decisions_sample(stub)
    sample_path = run_root / "p0-review-decisions.sample.json"
    decisions_path = run_root / "p0-review-decisions.json"
    audit_json_path = run_root / "p0-review-decisions.audit.json"
    audit_md_path = run_root / "p0-review-decisions.audit.md"
    decisions = {
        "version": "hxy-p0-review-decisions.v1",
        "items": [
            {
                "source_case_id": "compliance-medical-001",
                "source_task_id": "authority-gap-compliance-medical-001",
                "action": "needs_revision",
                "reviewer": "运营/合规负责人",
                "note": "需要补充正式来源。",
            },
            {
                "source_case_id": "compliance-effect-001",
                "source_task_id": "authority-gap-compliance-effect-001",
                "action": "approve",
                "reviewer": "运营/合规负责人",
                "publication_metadata": {
                    "source_references": [],
                    "knowledge_version": "",
                    "responsible_owner": "",
                    "effective_scope": "",
                    "risk_review_status": "",
                },
            },
        ],
        "write_to_database": False,
    }
    _write_json_file(sample_path, sample)
    _write_json_file(decisions_path, decisions)

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "validate-hxy-p0-review-decisions.py"),
            "decision-audit",
            "--sample",
            str(sample_path),
            "--decisions",
            str(decisions_path),
            "--output-json",
            str(audit_json_path),
            "--output-md",
            str(audit_md_path),
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    stdout = json.loads(result.stdout)
    assert stdout["command"] == "decision-audit"
    assert stdout["json_path"] == str(audit_json_path)
    assert stdout["markdown_path"] == str(audit_md_path)
    assert stdout["changed_count"] == 2
    assert stdout["pending_count"] == 2
    assert stdout["metadata_gap_count"] == 1
    assert stdout["write_to_database"] is False

    audit = json.loads(audit_json_path.read_text(encoding="utf-8"))
    assert audit["version"] == "hxy-p0-review-decisions-audit.v1"
    assert audit["sample_fingerprint"]["algorithm"] == "sha256"
    assert audit["decision_fingerprint"]["algorithm"] == "sha256"
    assert audit["changed_count"] == 2
    assert audit["pending_count"] == 2
    assert audit["metadata_gap_count"] == 1
    assert audit["write_to_database"] is False
    medical = next(item for item in audit["items"] if item["source_case_id"] == "compliance-medical-001")
    effect = next(item for item in audit["items"] if item["source_case_id"] == "compliance-effect-001")
    marketing = next(item for item in audit["items"] if item["source_case_id"] == "compliance-marketing-001")
    assert medical["changed"] is True
    assert medical["current_action"] == "needs_revision"
    assert effect["changed"] is True
    assert effect["metadata_status"] == "missing_required_fields"
    assert marketing["changed"] is False
    assert marketing["current_action"] == "pending"

    markdown = audit_md_path.read_text(encoding="utf-8")
    assert "# HXY P0 Review Decisions Audit" in markdown
    assert "This audit does not approve, publish, or import answer cards." in markdown
    assert "audit_fingerprint_algorithm: sha256" in markdown
    assert "audit_fingerprint_digest:" in markdown
    assert "sample_fingerprint_algorithm: sha256" in markdown
    assert "sample_fingerprint_digest:" in markdown
    assert "decision_fingerprint_algorithm: sha256" in markdown
    assert "decision_fingerprint_digest:" in markdown
    assert "changed_count: 2" in markdown
    assert "pending_count: 2" in markdown
    assert "metadata_gap_count: 1" in markdown
    assert "`compliance-medical-001` pending -> needs_revision changed=true" in markdown
    assert "`compliance-effect-001` pending -> approve changed=true metadata_status=missing_required_fields" in markdown
    assert "write_to_database: false" in markdown


def test_validate_hxy_p0_review_decisions_cli_writes_reviewer_worksheet(tmp_path: Path):
    from apps.api.hxy_knowledge.loop_engine import (
        BenchmarkImprovementLoopConfig,
        build_p0_manual_review_packet,
        build_p0_review_decisions_audit,
        build_p0_review_decisions_sample,
        initialize_p0_review_decisions_from_sample,
        run_benchmark_improvement_loop,
    )

    output_path = tmp_path / "benchmark-report.json"
    runs_dir = tmp_path / "runs"
    run_id = "benchmark-loop-p0-reviewer-worksheet-cli"
    run_root = runs_dir / run_id

    state = run_benchmark_improvement_loop(
        BenchmarkImprovementLoopConfig(
            benchmark_path=ROOT / "knowledge" / "benchmarks" / "hxy-brain-benchmark-v1.json",
            report_path=output_path,
            runs_dir=runs_dir,
            run_id=run_id,
            max_iterations=1,
        )
    )
    correction_package = state["iterations"][0]["correction_package"]
    stub = correction_package["p0_review_decision_stub"]
    draft_pack = correction_package["p0_authority_card_draft_pack"]
    sample = build_p0_review_decisions_sample(stub)
    packet = build_p0_manual_review_packet(
        decision_stub=stub,
        draft_pack=draft_pack,
        review_manifest=draft_pack["review_manifest"],
        decision_sample=sample,
    )
    decisions = initialize_p0_review_decisions_from_sample(sample)
    audit = build_p0_review_decisions_audit(sample, decisions)
    packet_path = run_root / "p0-manual-review-packet.json"
    decisions_path = run_root / "p0-review-decisions.json"
    audit_path = run_root / "p0-review-decisions.audit.json"
    worksheet_path = run_root / "p0-reviewer-worksheet.md"
    _write_json_file(packet_path, packet)
    _write_json_file(decisions_path, decisions)
    _write_json_file(audit_path, audit)

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "validate-hxy-p0-review-decisions.py"),
            "reviewer-worksheet",
            "--packet",
            str(packet_path),
            "--decisions",
            str(decisions_path),
            "--audit",
            str(audit_path),
            "--output-md",
            str(worksheet_path),
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    stdout = json.loads(result.stdout)
    assert stdout["command"] == "reviewer-worksheet"
    assert stdout["markdown_path"] == str(worksheet_path)
    assert stdout["item_count"] == 4
    assert stdout["pending_count"] == 4
    assert stdout["actioned_count"] == 0
    assert stdout["write_to_database"] is False
    assert json.loads(decisions_path.read_text(encoding="utf-8"))["items"][0]["action"] == "pending"

    markdown = worksheet_path.read_text(encoding="utf-8")
    assert "# HXY P0 Reviewer Worksheet" in markdown
    assert "This worksheet does not approve, publish, import, or write answer cards." in markdown
    assert "review_packet_fingerprint_digest:" in markdown
    assert "decision_fingerprint_digest:" in markdown
    assert "audit_fingerprint_digest:" in markdown
    assert "write_to_database: false" in markdown
    assert "## Case: compliance-medical-001" in markdown
    assert "Current action: `pending`" in markdown
    assert "Question: 泡脚能治失眠吗？" in markdown
    assert "Edit target: `p0-review-decisions.json` item where `source_case_id=complice-medical-001`" not in markdown
    assert "Edit target: `p0-review-decisions.json` item where `source_case_id=compliance-medical-001`" in markdown
    assert "### Review Questions" in markdown
    assert "是否明确说明不能做医疗诊断或治疗承诺？" in markdown
    assert "### Approval Conditions" in markdown
    assert "### Rejection Conditions" in markdown
    assert "Required metadata for `approve`: source_references, knowledge_version, responsible_owner, effective_scope, risk_review_status" in markdown


def test_validate_hxy_p0_review_decisions_cli_writes_reviewer_todo(tmp_path: Path):
    from apps.api.hxy_knowledge.loop_engine import (
        BenchmarkImprovementLoopConfig,
        build_p0_manual_review_packet,
        build_p0_review_decisions_audit,
        build_p0_review_decisions_sample,
        initialize_p0_review_decisions_from_sample,
        run_benchmark_improvement_loop,
    )

    output_path = tmp_path / "benchmark-report.json"
    runs_dir = tmp_path / "runs"
    run_id = "benchmark-loop-p0-reviewer-todo-cli"
    run_root = runs_dir / run_id

    state = run_benchmark_improvement_loop(
        BenchmarkImprovementLoopConfig(
            benchmark_path=ROOT / "knowledge" / "benchmarks" / "hxy-brain-benchmark-v1.json",
            report_path=output_path,
            runs_dir=runs_dir,
            run_id=run_id,
            max_iterations=1,
        )
    )
    correction_package = state["iterations"][0]["correction_package"]
    stub = correction_package["p0_review_decision_stub"]
    draft_pack = correction_package["p0_authority_card_draft_pack"]
    sample = build_p0_review_decisions_sample(stub)
    packet = build_p0_manual_review_packet(
        decision_stub=stub,
        draft_pack=draft_pack,
        review_manifest=draft_pack["review_manifest"],
        decision_sample=sample,
    )
    decisions = initialize_p0_review_decisions_from_sample(sample)
    audit = build_p0_review_decisions_audit(sample, decisions)
    packet_path = run_root / "p0-manual-review-packet.json"
    decisions_path = run_root / "p0-review-decisions.json"
    audit_path = run_root / "p0-review-decisions.audit.json"
    todo_path = run_root / "p0-reviewer-todo.json"
    _write_json_file(packet_path, packet)
    _write_json_file(decisions_path, decisions)
    _write_json_file(audit_path, audit)

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "validate-hxy-p0-review-decisions.py"),
            "reviewer-todo",
            "--packet",
            str(packet_path),
            "--decisions",
            str(decisions_path),
            "--audit",
            str(audit_path),
            "--output-json",
            str(todo_path),
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    stdout = json.loads(result.stdout)
    assert stdout["command"] == "reviewer-todo"
    assert stdout["json_path"] == str(todo_path)
    assert stdout["item_count"] == 4
    assert stdout["pending_count"] == 4
    assert stdout["actioned_count"] == 0
    assert stdout["write_to_database"] is False
    assert json.loads(decisions_path.read_text(encoding="utf-8"))["items"][0]["action"] == "pending"

    todo = json.loads(todo_path.read_text(encoding="utf-8"))
    assert todo["version"] == "hxy-p0-reviewer-todo.v1"
    assert todo["pending_count"] == 4
    assert todo["actioned_count"] == 0
    assert todo["write_to_database"] is False
    assert todo["publish_allowed"] is False
    assert todo["official_use_allowed"] is False
    assert todo["review_packet_fingerprint"]["algorithm"] == "sha256"
    assert todo["decision_fingerprint"]["algorithm"] == "sha256"
    assert todo["audit_fingerprint"]["algorithm"] == "sha256"
    first = todo["items"][0]
    assert first["source_case_id"] == "compliance-medical-001"
    assert first["current_action"] == "pending"
    assert first["question_pattern"] == "泡脚能治失眠吗？"
    assert first["edit_target"] == "p0-review-decisions.json items[source_case_id=compliance-medical-001]"
    assert first["required_metadata_for_approve"] == [
        "source_references",
        "knowledge_version",
        "responsible_owner",
        "effective_scope",
        "risk_review_status",
    ]
    assert "是否明确说明不能做医疗诊断或治疗承诺？" in first["review_questions"]
    assert first["next_human_action"] == "choose approve, reject, or needs_revision manually"


def test_p0_governance_status_marks_fresh_decision_edit_guide(tmp_path: Path):
    from apps.api.hxy_knowledge.loop_engine import (
        BenchmarkImprovementLoopConfig,
        build_p0_governance_status,
        build_p0_manual_review_packet,
        build_p0_review_decisions_sample,
        initialize_p0_review_decisions_from_sample,
        render_p0_decision_edit_guide_markdown,
        run_benchmark_improvement_loop,
    )

    output_path = tmp_path / "benchmark-report.json"
    runs_dir = tmp_path / "runs"
    run_id = "benchmark-loop-fresh-edit-guide"
    run_root = runs_dir / run_id

    state = run_benchmark_improvement_loop(
        BenchmarkImprovementLoopConfig(
            benchmark_path=ROOT / "knowledge" / "benchmarks" / "hxy-brain-benchmark-v1.json",
            report_path=output_path,
            runs_dir=runs_dir,
            run_id=run_id,
            max_iterations=1,
        )
    )
    correction_package = state["iterations"][0]["correction_package"]
    stub = correction_package["p0_review_decision_stub"]
    draft_pack = correction_package["p0_authority_card_draft_pack"]
    sample = build_p0_review_decisions_sample(stub)
    packet = build_p0_manual_review_packet(
        decision_stub=stub,
        draft_pack=draft_pack,
        review_manifest=draft_pack["review_manifest"],
        decision_sample=sample,
    )
    decisions = initialize_p0_review_decisions_from_sample(sample)
    _write_json_file(run_root / "p0-review-decisions.sample.json", sample)
    _write_json_file(run_root / "p0-manual-review-packet.json", packet)
    _write_json_file(run_root / "p0-review-decisions.json", decisions)
    (run_root / "p0-decision-edit-guide.md").write_text(
        render_p0_decision_edit_guide_markdown(packet, decisions),
        encoding="utf-8",
    )

    status = build_p0_governance_status(run_root)

    assert status["current_step"] == "blocked_at_empty_manual_decisions"
    assert status["details"]["decision_edit_guide_status"] == "fresh"
    assert status["details"]["decision_edit_guide_path"].endswith("p0-decision-edit-guide.md")
    assert status["details"]["decision_audit_status"] == "missing"
    assert "validate-hxy-p0-review-decisions.py decision-audit" in status["next_command"]
    assert "p0-decision-edit-guide.md" in status["next_action"]
    assert status["write_to_database"] is False


def test_p0_governance_status_marks_fresh_decision_audit(tmp_path: Path):
    from apps.api.hxy_knowledge.loop_engine import (
        BenchmarkImprovementLoopConfig,
        build_p0_governance_status,
        build_p0_manual_review_packet,
        build_p0_review_decisions_audit,
        build_p0_review_decisions_sample,
        initialize_p0_review_decisions_from_sample,
        render_p0_decision_edit_guide_markdown,
        render_p0_review_decisions_audit_markdown,
        run_benchmark_improvement_loop,
    )

    output_path = tmp_path / "benchmark-report.json"
    runs_dir = tmp_path / "runs"
    run_id = "benchmark-loop-fresh-decision-audit"
    run_root = runs_dir / run_id

    state = run_benchmark_improvement_loop(
        BenchmarkImprovementLoopConfig(
            benchmark_path=ROOT / "knowledge" / "benchmarks" / "hxy-brain-benchmark-v1.json",
            report_path=output_path,
            runs_dir=runs_dir,
            run_id=run_id,
            max_iterations=1,
        )
    )
    correction_package = state["iterations"][0]["correction_package"]
    stub = correction_package["p0_review_decision_stub"]
    draft_pack = correction_package["p0_authority_card_draft_pack"]
    sample = build_p0_review_decisions_sample(stub)
    packet = build_p0_manual_review_packet(
        decision_stub=stub,
        draft_pack=draft_pack,
        review_manifest=draft_pack["review_manifest"],
        decision_sample=sample,
    )
    decisions = initialize_p0_review_decisions_from_sample(sample)
    audit = build_p0_review_decisions_audit(sample, decisions)
    _write_json_file(run_root / "p0-review-decisions.sample.json", sample)
    _write_json_file(run_root / "p0-manual-review-packet.json", packet)
    _write_json_file(run_root / "p0-review-decisions.json", decisions)
    _write_json_file(run_root / "p0-review-decisions.audit.json", audit)
    (run_root / "p0-review-decisions.audit.md").write_text(
        render_p0_review_decisions_audit_markdown(audit),
        encoding="utf-8",
    )
    (run_root / "p0-decision-edit-guide.md").write_text(
        render_p0_decision_edit_guide_markdown(packet, decisions),
        encoding="utf-8",
    )

    status = build_p0_governance_status(run_root)

    assert status["current_step"] == "blocked_at_empty_manual_decisions"
    assert status["details"]["decision_audit_status"] == "fresh"
    assert status["details"]["decision_audit_path"].endswith("p0-review-decisions.audit.json")
    assert status["details"]["decision_audit_changed_count"] == 0
    assert status["details"]["decision_audit_metadata_gap_count"] == 0
    assert status["details"]["reviewer_worksheet_status"] == "missing"
    assert status["details"]["reviewer_worksheet_path"].endswith("p0-reviewer-worksheet.md")
    assert "validate-hxy-p0-review-decisions.py reviewer-worksheet" in status["next_command"]
    assert status["write_to_database"] is False


def test_p0_governance_status_points_to_fresh_reviewer_worksheet(tmp_path: Path):
    from apps.api.hxy_knowledge.loop_engine import (
        BenchmarkImprovementLoopConfig,
        build_p0_governance_status,
        build_p0_manual_review_packet,
        build_p0_review_decisions_audit,
        build_p0_review_decisions_sample,
        initialize_p0_review_decisions_from_sample,
        render_p0_decision_edit_guide_markdown,
        render_p0_reviewer_worksheet_markdown,
        render_p0_review_decisions_audit_markdown,
        run_benchmark_improvement_loop,
    )

    output_path = tmp_path / "benchmark-report.json"
    runs_dir = tmp_path / "runs"
    run_id = "benchmark-loop-fresh-reviewer-worksheet"
    run_root = runs_dir / run_id

    state = run_benchmark_improvement_loop(
        BenchmarkImprovementLoopConfig(
            benchmark_path=ROOT / "knowledge" / "benchmarks" / "hxy-brain-benchmark-v1.json",
            report_path=output_path,
            runs_dir=runs_dir,
            run_id=run_id,
            max_iterations=1,
        )
    )
    correction_package = state["iterations"][0]["correction_package"]
    stub = correction_package["p0_review_decision_stub"]
    draft_pack = correction_package["p0_authority_card_draft_pack"]
    sample = build_p0_review_decisions_sample(stub)
    packet = build_p0_manual_review_packet(
        decision_stub=stub,
        draft_pack=draft_pack,
        review_manifest=draft_pack["review_manifest"],
        decision_sample=sample,
    )
    decisions = initialize_p0_review_decisions_from_sample(sample)
    audit = build_p0_review_decisions_audit(sample, decisions)
    _write_json_file(run_root / "p0-review-decisions.sample.json", sample)
    _write_json_file(run_root / "p0-manual-review-packet.json", packet)
    _write_json_file(run_root / "p0-review-decisions.json", decisions)
    _write_json_file(run_root / "p0-review-decisions.audit.json", audit)
    (run_root / "p0-review-decisions.audit.md").write_text(
        render_p0_review_decisions_audit_markdown(audit),
        encoding="utf-8",
    )
    (run_root / "p0-decision-edit-guide.md").write_text(
        render_p0_decision_edit_guide_markdown(packet, decisions),
        encoding="utf-8",
    )
    (run_root / "p0-reviewer-worksheet.md").write_text(
        render_p0_reviewer_worksheet_markdown(packet, decisions, audit),
        encoding="utf-8",
    )

    status = build_p0_governance_status(run_root)

    assert status["current_step"] == "blocked_at_empty_manual_decisions"
    assert status["details"]["reviewer_worksheet_status"] == "fresh"
    assert status["details"]["reviewer_todo_status"] == "missing"
    assert status["details"]["reviewer_todo_path"].endswith("p0-reviewer-todo.json")
    assert "validate-hxy-p0-review-decisions.py reviewer-todo" in status["next_command"]
    assert status["write_to_database"] is False


def test_p0_governance_status_stops_after_fresh_reviewer_todo(tmp_path: Path):
    from apps.api.hxy_knowledge.loop_engine import (
        BenchmarkImprovementLoopConfig,
        build_p0_governance_status,
        build_p0_manual_review_packet,
        build_p0_review_decisions_audit,
        build_p0_review_decisions_sample,
        build_p0_reviewer_todo,
        initialize_p0_review_decisions_from_sample,
        render_p0_decision_edit_guide_markdown,
        render_p0_reviewer_worksheet_markdown,
        render_p0_review_decisions_audit_markdown,
        run_benchmark_improvement_loop,
    )

    output_path = tmp_path / "benchmark-report.json"
    runs_dir = tmp_path / "runs"
    run_id = "benchmark-loop-fresh-reviewer-todo"
    run_root = runs_dir / run_id

    state = run_benchmark_improvement_loop(
        BenchmarkImprovementLoopConfig(
            benchmark_path=ROOT / "knowledge" / "benchmarks" / "hxy-brain-benchmark-v1.json",
            report_path=output_path,
            runs_dir=runs_dir,
            run_id=run_id,
            max_iterations=1,
        )
    )
    correction_package = state["iterations"][0]["correction_package"]
    stub = correction_package["p0_review_decision_stub"]
    draft_pack = correction_package["p0_authority_card_draft_pack"]
    sample = build_p0_review_decisions_sample(stub)
    packet = build_p0_manual_review_packet(
        decision_stub=stub,
        draft_pack=draft_pack,
        review_manifest=draft_pack["review_manifest"],
        decision_sample=sample,
    )
    decisions = initialize_p0_review_decisions_from_sample(sample)
    audit = build_p0_review_decisions_audit(sample, decisions)
    todo = build_p0_reviewer_todo(packet, decisions, audit)
    _write_json_file(run_root / "p0-review-decisions.sample.json", sample)
    _write_json_file(run_root / "p0-manual-review-packet.json", packet)
    _write_json_file(run_root / "p0-review-decisions.json", decisions)
    _write_json_file(run_root / "p0-review-decisions.audit.json", audit)
    _write_json_file(run_root / "p0-reviewer-todo.json", todo)
    (run_root / "p0-review-decisions.audit.md").write_text(
        render_p0_review_decisions_audit_markdown(audit),
        encoding="utf-8",
    )
    (run_root / "p0-decision-edit-guide.md").write_text(
        render_p0_decision_edit_guide_markdown(packet, decisions),
        encoding="utf-8",
    )
    (run_root / "p0-reviewer-worksheet.md").write_text(
        render_p0_reviewer_worksheet_markdown(packet, decisions, audit),
        encoding="utf-8",
    )

    status = build_p0_governance_status(run_root)

    assert status["current_step"] == "blocked_at_empty_manual_decisions"
    assert status["details"]["reviewer_todo_status"] == "fresh"
    assert "p0-reviewer-worksheet.md" in status["next_action"]
    assert status["next_command"] == ""
    assert status["write_to_database"] is False


def test_p0_governance_status_marks_stale_decision_audit_after_decisions_change(tmp_path: Path):
    from apps.api.hxy_knowledge.loop_engine import (
        BenchmarkImprovementLoopConfig,
        build_p0_governance_status,
        build_p0_manual_review_packet,
        build_p0_review_decisions_audit,
        build_p0_review_decisions_sample,
        initialize_p0_review_decisions_from_sample,
        render_p0_decision_edit_guide_markdown,
        render_p0_review_decisions_audit_markdown,
        run_benchmark_improvement_loop,
    )

    output_path = tmp_path / "benchmark-report.json"
    runs_dir = tmp_path / "runs"
    run_id = "benchmark-loop-stale-decision-audit"
    run_root = runs_dir / run_id

    state = run_benchmark_improvement_loop(
        BenchmarkImprovementLoopConfig(
            benchmark_path=ROOT / "knowledge" / "benchmarks" / "hxy-brain-benchmark-v1.json",
            report_path=output_path,
            runs_dir=runs_dir,
            run_id=run_id,
            max_iterations=1,
        )
    )
    correction_package = state["iterations"][0]["correction_package"]
    stub = correction_package["p0_review_decision_stub"]
    draft_pack = correction_package["p0_authority_card_draft_pack"]
    sample = build_p0_review_decisions_sample(stub)
    packet = build_p0_manual_review_packet(
        decision_stub=stub,
        draft_pack=draft_pack,
        review_manifest=draft_pack["review_manifest"],
        decision_sample=sample,
    )
    decisions = initialize_p0_review_decisions_from_sample(sample)
    audit = build_p0_review_decisions_audit(sample, decisions)
    _write_json_file(run_root / "p0-review-decisions.sample.json", sample)
    _write_json_file(run_root / "p0-manual-review-packet.json", packet)
    _write_json_file(run_root / "p0-review-decisions.json", decisions)
    _write_json_file(run_root / "p0-review-decisions.audit.json", audit)
    (run_root / "p0-review-decisions.audit.md").write_text(
        render_p0_review_decisions_audit_markdown(audit),
        encoding="utf-8",
    )
    (run_root / "p0-decision-edit-guide.md").write_text(
        render_p0_decision_edit_guide_markdown(packet, decisions),
        encoding="utf-8",
    )
    decisions["items"][0]["note"] = "manual note after audit render"
    _write_json_file(run_root / "p0-review-decisions.json", decisions)
    (run_root / "p0-decision-edit-guide.md").write_text(
        render_p0_decision_edit_guide_markdown(packet, decisions),
        encoding="utf-8",
    )

    status = build_p0_governance_status(run_root)

    assert status["current_step"] == "blocked_at_empty_manual_decisions"
    assert status["details"]["decision_audit_status"] == "stale"
    assert "validate-hxy-p0-review-decisions.py decision-audit" in status["next_command"]
    assert "p0-review-decisions.audit.json" in status["next_command"]
    assert status["write_to_database"] is False


def test_p0_governance_status_marks_stale_decision_audit_when_markdown_mismatches_json(tmp_path: Path):
    from apps.api.hxy_knowledge.loop_engine import (
        BenchmarkImprovementLoopConfig,
        build_p0_governance_status,
        build_p0_review_decisions_audit,
        build_p0_review_decisions_sample,
        render_p0_review_decisions_audit_markdown,
        run_benchmark_improvement_loop,
    )

    output_path = tmp_path / "benchmark-report.json"
    runs_dir = tmp_path / "runs"
    run_id = "benchmark-loop-stale-decision-audit-md"
    run_root = runs_dir / run_id

    state = run_benchmark_improvement_loop(
        BenchmarkImprovementLoopConfig(
            benchmark_path=ROOT / "knowledge" / "benchmarks" / "hxy-brain-benchmark-v1.json",
            report_path=output_path,
            runs_dir=runs_dir,
            run_id=run_id,
            max_iterations=1,
        )
    )
    stub = state["iterations"][0]["correction_package"]["p0_review_decision_stub"]
    sample = build_p0_review_decisions_sample(stub)
    decisions = json.loads(json.dumps(sample))
    old_audit = build_p0_review_decisions_audit(sample, decisions)
    decisions["items"][0]["action"] = "needs_revision"
    decisions["items"][0]["reviewer"] = "运营/合规负责人"
    decisions["items"][0]["note"] = "需要补充核定来源后再审核。"
    new_audit = build_p0_review_decisions_audit(sample, decisions)
    _write_json_file(run_root / "p0-review-decisions.sample.json", sample)
    _write_json_file(run_root / "p0-review-decisions.json", decisions)
    _write_json_file(run_root / "p0-review-decisions.audit.json", new_audit)
    (run_root / "p0-review-decisions.audit.md").write_text(
        render_p0_review_decisions_audit_markdown(old_audit),
        encoding="utf-8",
    )

    status = build_p0_governance_status(run_root)

    assert status["current_step"] == "stale_decision_audit"
    assert status["details"]["decision_audit_status"] == "stale"
    assert status["details"]["stale_file"] == "p0-review-decisions.audit.md"
    assert status["details"]["upstream_name"] == "p0-review-decisions.audit.json"
    assert "validate-hxy-p0-review-decisions.py decision-audit" in status["next_command"]
    assert status["write_to_database"] is False


def test_p0_governance_status_marks_stale_decision_edit_guide_after_decisions_change(tmp_path: Path):
    from apps.api.hxy_knowledge.loop_engine import (
        BenchmarkImprovementLoopConfig,
        build_p0_governance_status,
        build_p0_manual_review_packet,
        build_p0_review_decisions_sample,
        initialize_p0_review_decisions_from_sample,
        render_p0_decision_edit_guide_markdown,
        run_benchmark_improvement_loop,
    )

    output_path = tmp_path / "benchmark-report.json"
    runs_dir = tmp_path / "runs"
    run_id = "benchmark-loop-stale-edit-guide"
    run_root = runs_dir / run_id

    state = run_benchmark_improvement_loop(
        BenchmarkImprovementLoopConfig(
            benchmark_path=ROOT / "knowledge" / "benchmarks" / "hxy-brain-benchmark-v1.json",
            report_path=output_path,
            runs_dir=runs_dir,
            run_id=run_id,
            max_iterations=1,
        )
    )
    correction_package = state["iterations"][0]["correction_package"]
    stub = correction_package["p0_review_decision_stub"]
    draft_pack = correction_package["p0_authority_card_draft_pack"]
    sample = build_p0_review_decisions_sample(stub)
    packet = build_p0_manual_review_packet(
        decision_stub=stub,
        draft_pack=draft_pack,
        review_manifest=draft_pack["review_manifest"],
        decision_sample=sample,
    )
    decisions = initialize_p0_review_decisions_from_sample(sample)
    _write_json_file(run_root / "p0-review-decisions.sample.json", sample)
    _write_json_file(run_root / "p0-manual-review-packet.json", packet)
    _write_json_file(run_root / "p0-review-decisions.json", decisions)
    (run_root / "p0-decision-edit-guide.md").write_text(
        render_p0_decision_edit_guide_markdown(packet, decisions),
        encoding="utf-8",
    )
    decisions["items"][0]["note"] = "manual note after guide render"
    _write_json_file(run_root / "p0-review-decisions.json", decisions)

    status = build_p0_governance_status(run_root)

    assert status["current_step"] == "blocked_at_empty_manual_decisions"
    assert status["details"]["decision_edit_guide_status"] == "stale"
    assert "validate-hxy-p0-review-decisions.py edit-guide" in status["next_command"]
    assert "p0-decision-edit-guide.md" in status["next_command"]
    assert status["write_to_database"] is False


def test_build_p0_manual_review_packet_summarizes_drafts_without_approving(tmp_path: Path):
    from apps.api.hxy_knowledge.loop_engine import (
        BenchmarkImprovementLoopConfig,
        build_p0_manual_review_packet,
        build_p0_review_decisions_sample,
        run_benchmark_improvement_loop,
    )

    output_path = tmp_path / "benchmark-report.json"
    runs_dir = tmp_path / "runs"
    run_id = "benchmark-loop-p0-manual-review-packet"
    run_root = runs_dir / run_id

    state = run_benchmark_improvement_loop(
        BenchmarkImprovementLoopConfig(
            benchmark_path=ROOT / "knowledge" / "benchmarks" / "hxy-brain-benchmark-v1.json",
            report_path=output_path,
            runs_dir=runs_dir,
            run_id=run_id,
            max_iterations=1,
        )
    )

    correction_package = state["iterations"][0]["correction_package"]
    stub = correction_package["p0_review_decision_stub"]
    draft_pack = correction_package["p0_authority_card_draft_pack"]
    review_manifest = draft_pack["review_manifest"]
    sample = build_p0_review_decisions_sample(stub)

    packet = build_p0_manual_review_packet(
        decision_stub=stub,
        draft_pack=draft_pack,
        review_manifest=review_manifest,
        decision_sample=sample,
    )

    assert packet["version"] == "hxy-p0-manual-review-packet.v1"
    assert packet["item_count"] == 4
    assert packet["official_use_allowed"] is False
    assert packet["publish_allowed"] is False
    assert packet["write_to_database"] is False
    assert packet["requires_human_review"] is True
    assert "approved_answer_cards" not in packet

    first = packet["items"][0]
    assert first["source_case_id"] == "compliance-medical-001"
    assert first["question_pattern"] == "泡脚能治失眠吗？"
    assert first["draft_answer"]
    assert first["review_questions"]
    assert first["approval_conditions"]
    assert first["decision_template"]["action"] == "pending"
    assert first["decision_template"]["official_use_allowed"] is False
    assert set(first["required_publication_metadata_fields"]) == {
        "source_references",
        "knowledge_version",
        "responsible_owner",
        "effective_scope",
        "risk_review_status",
    }


def test_validate_hxy_p0_review_decisions_cli_writes_manual_review_packet(tmp_path: Path):
    from apps.api.hxy_knowledge.loop_engine import BenchmarkImprovementLoopConfig, run_benchmark_improvement_loop

    output_path = tmp_path / "benchmark-report.json"
    runs_dir = tmp_path / "runs"
    run_id = "benchmark-loop-p0-review-packet-cli"
    run_root = runs_dir / run_id

    run_benchmark_improvement_loop(
        BenchmarkImprovementLoopConfig(
            benchmark_path=ROOT / "knowledge" / "benchmarks" / "hxy-brain-benchmark-v1.json",
            report_path=output_path,
            runs_dir=runs_dir,
            run_id=run_id,
            max_iterations=1,
        )
    )

    json_output = run_root / "p0-manual-review-packet.json"
    markdown_output = run_root / "p0-manual-review-packet.md"
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "validate-hxy-p0-review-decisions.py"),
            "review-packet",
            "--stub",
            str(run_root / "p0-review-decisions.stub.json"),
            "--drafts",
            str(run_root / "p0-authority-card-drafts.json"),
            "--manifest",
            str(run_root / "p0-draft-review-manifest.json"),
            "--sample",
            str(run_root / "p0-review-decisions.sample.json"),
            "--output-json",
            str(json_output),
            "--output-md",
            str(markdown_output),
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    stdout = json.loads(result.stdout)
    assert stdout["version"] == "hxy-p0-review-decisions-cli.v1"
    assert stdout["command"] == "review-packet"
    assert stdout["item_count"] == 4
    assert stdout["publish_allowed"] is False
    assert stdout["write_to_database"] is False
    assert stdout["json_path"] == str(json_output)
    assert stdout["markdown_path"] == str(markdown_output)

    packet = json.loads(json_output.read_text(encoding="utf-8"))
    markdown = markdown_output.read_text(encoding="utf-8")
    assert packet["version"] == "hxy-p0-manual-review-packet.v1"
    assert packet["publish_allowed"] is False
    assert packet["write_to_database"] is False
    assert "approved_answer_cards" not in packet
    assert "# HXY P0 Manual Review Packet" in markdown
    assert "compliance-medical-001" in markdown
    assert "泡脚能治失眠吗？" in markdown
    assert "write_to_database: false" in markdown
    assert "This packet does not approve or publish answer cards." in markdown


def test_build_p0_approved_card_publication_package_only_uses_preflight_ready_items(tmp_path: Path):
    from apps.api.hxy_knowledge.loop_engine import (
        BenchmarkImprovementLoopConfig,
        build_p0_approved_card_publication_package,
        run_benchmark_improvement_loop,
        validate_p0_review_decisions,
    )

    output_path = tmp_path / "benchmark-report.json"
    runs_dir = tmp_path / "runs"

    state = run_benchmark_improvement_loop(
        BenchmarkImprovementLoopConfig(
            benchmark_path=ROOT / "knowledge" / "benchmarks" / "hxy-brain-benchmark-v1.json",
            report_path=output_path,
            runs_dir=runs_dir,
            run_id="benchmark-loop-p0-publication-package",
            max_iterations=1,
        )
    )

    correction_package = state["iterations"][0]["correction_package"]
    stub = correction_package["p0_review_decision_stub"]
    draft_pack = correction_package["p0_authority_card_draft_pack"]
    decisions = {
        "version": "hxy-p0-review-decisions.v1",
        "items": [
            {
                "source_case_id": "compliance-medical-001",
                "source_task_id": "authority-gap-compliance-medical-001",
                "action": "approve",
                "reviewer": "运营/合规负责人",
                "publication_metadata": {
                    "source_references": ["knowledge/benchmarks/hxy-brain-benchmark-v1.json"],
                    "knowledge_version": "hxy-answer-card-2026-07-02",
                    "responsible_owner": "运营/合规负责人",
                    "effective_scope": "首店员工对外口径",
                    "risk_review_status": "passed",
                },
            },
            {
                "source_case_id": "compliance-effect-001",
                "source_task_id": "authority-gap-compliance-effect-001",
                "action": "approve",
                "reviewer": "运营/合规负责人",
            },
        ],
    }
    validation = validate_p0_review_decisions(stub, decisions)

    package = build_p0_approved_card_publication_package(draft_pack, validation)

    assert package["version"] == "hxy-p0-approved-card-publication-package.v1"
    assert package["candidate_count"] == 1
    assert package["blocked_count"] == 1
    assert package["official_use_allowed"] is False
    assert package["publish_allowed"] is False
    assert package["write_to_formal_store"] is False
    assert "approved_answer_cards" not in package

    candidate = package["publication_candidates"][0]
    assert candidate["source_case_id"] == "compliance-medical-001"
    assert candidate["source_task_id"] == "authority-gap-compliance-medical-001"
    assert candidate["manual_publication_ready"] is True
    assert candidate["official_use_allowed"] is False
    assert candidate["publish_allowed"] is False
    assert candidate["proposed_card"]["status"] == "pending_manual_publication"
    assert candidate["proposed_card"]["target_status_after_manual_publish"] == "approved"
    assert candidate["proposed_card"]["review_status_after_manual_publish"] == "approved_v1"
    assert candidate["proposed_card"]["question_pattern"]
    assert candidate["proposed_card"]["answer"]
    assert candidate["proposed_card"]["publication_metadata"]["knowledge_version"] == "hxy-answer-card-2026-07-02"
    assert candidate["authority_rule"] == "publication_package_does_not_publish_approved_cards"

    blocked = package["blocked_items"][0]
    assert blocked["source_case_id"] == "compliance-effect-001"
    assert blocked["status"] == "blocked_missing_publication_metadata"
    assert blocked["official_use_allowed"] is False


def test_benchmark_loop_writes_publication_package_when_manual_decisions_are_ready(tmp_path: Path):
    from apps.api.hxy_knowledge.loop_engine import BenchmarkImprovementLoopConfig, run_benchmark_improvement_loop

    output_path = tmp_path / "benchmark-report.json"
    runs_dir = tmp_path / "runs"
    run_id = "benchmark-loop-p0-publication-package-file"
    run_root = runs_dir / run_id
    run_root.mkdir(parents=True)
    (run_root / "p0-review-decisions.json").write_text(
        json.dumps(
            {
                "version": "hxy-p0-review-decisions.v1",
                "items": [
                    {
                        "source_case_id": "compliance-medical-001",
                        "source_task_id": "authority-gap-compliance-medical-001",
                        "action": "approve",
                        "reviewer": "运营/合规负责人",
                        "publication_metadata": {
                            "source_references": ["knowledge/benchmarks/hxy-brain-benchmark-v1.json"],
                            "knowledge_version": "hxy-answer-card-2026-07-02",
                            "responsible_owner": "运营/合规负责人",
                            "effective_scope": "首店员工对外口径",
                            "risk_review_status": "passed",
                        },
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    state = run_benchmark_improvement_loop(
        BenchmarkImprovementLoopConfig(
            benchmark_path=ROOT / "knowledge" / "benchmarks" / "hxy-brain-benchmark-v1.json",
            report_path=output_path,
            runs_dir=runs_dir,
            run_id=run_id,
            max_iterations=1,
        )
    )

    correction_package = state["iterations"][0]["correction_package"]
    publication_package = correction_package["p0_approved_card_publication_package"]
    package_path = run_root / "p0-approved-card-publication-package.json"

    assert package_path.is_file()
    assert state["iterations"][0]["p0_approved_card_publication_package_path"] == str(package_path)
    assert publication_package["candidate_count"] == 1
    assert publication_package["publish_allowed"] is False
    assert "approved_answer_cards" not in publication_package


def test_dry_run_p0_publication_package_builds_draft_answer_card_payloads_without_writing(tmp_path: Path):
    from apps.api.hxy_knowledge.loop_engine import dry_run_p0_approved_card_publication_package

    package = {
        "version": "hxy-p0-approved-card-publication-package.v1",
        "publication_candidates": [
            {
                "source_case_id": "compliance-medical-001",
                "source_task_id": "authority-gap-compliance-medical-001",
                "manual_publication_ready": True,
                "proposed_card": {
                    "card_id": "pending:p0:compliance-medical-001",
                    "question_pattern": "泡脚能治疗失眠吗？",
                    "intent": "risk_boundary",
                    "audience": "store_staff",
                    "answer": "不能说泡脚能治疗失眠。可以说泡脚是放松体验，不能替代医疗诊断或治疗。",
                    "publication_metadata": {
                        "source_references": ["knowledge/benchmarks/hxy-brain-benchmark-v1.json"],
                        "knowledge_version": "hxy-answer-card-2026-07-02",
                        "responsible_owner": "运营/合规负责人",
                        "effective_scope": "首店员工对外口径",
                        "risk_review_status": "passed",
                    },
                    "evidence": [
                        {
                            "title": "P0 人工审核发布包：compliance-medical-001",
                            "domain": "risk_boundary",
                            "status": "pending_manual_publication",
                            "source_type": "manual_publication_package",
                        }
                    ],
                },
            }
        ],
        "blocked_items": [],
        "publish_allowed": False,
        "write_to_formal_store": False,
    }

    result = dry_run_p0_approved_card_publication_package(package)

    assert result["version"] == "hxy-p0-approved-card-publication-dry-run.v1"
    assert result["valid"] is True
    assert result["candidate_count"] == 1
    assert result["payload_count"] == 1
    assert result["would_write_count"] == 0
    assert result["write_to_formal_store"] is False
    assert result["publish_allowed"] is False
    assert "approved_answer_cards" not in result

    payload = result["draft_answer_card_payloads"][0]
    assert payload["question_pattern"] == "泡脚能治疗失眠吗？"
    assert payload["intent"] == "risk_boundary"
    assert payload["audience"] == "store_staff"
    assert payload["answer"]
    assert payload["status"] == "draft"
    assert payload["target_status_after_manual_publish"] == "approved"
    assert payload["review_status_after_manual_publish"] == "approved_v1"
    assert payload["source_answer_id"] == "pending:p0:compliance-medical-001"
    assert payload["publication_metadata"]["responsible_owner"] == "运营/合规负责人"
    assert payload["official_use_allowed"] is False
    assert payload["publish_allowed"] is False


def test_dry_run_p0_publication_package_blocks_invalid_payloads_without_writing(tmp_path: Path):
    from apps.api.hxy_knowledge.loop_engine import dry_run_p0_approved_card_publication_package

    package = {
        "version": "hxy-p0-approved-card-publication-package.v1",
        "publication_candidates": [
            {
                "source_case_id": "compliance-medical-001",
                "source_task_id": "authority-gap-compliance-medical-001",
                "manual_publication_ready": True,
                "proposed_card": {
                    "card_id": "pending:p0:compliance-medical-001",
                    "question_pattern": "",
                    "intent": "risk_boundary",
                    "audience": "store_staff",
                    "answer": "",
                    "publication_metadata": {
                        "source_references": [],
                        "knowledge_version": "",
                        "responsible_owner": "",
                        "effective_scope": "",
                        "risk_review_status": "",
                    },
                },
            }
        ],
        "blocked_items": [],
    }

    result = dry_run_p0_approved_card_publication_package(package)

    assert result["valid"] is False
    assert result["error_count"] == 2
    assert result["payload_count"] == 0
    assert result["would_write_count"] == 0
    assert {error["code"] for error in result["errors"]} == {
        "missing_answer_card_fields",
        "missing_publication_metadata",
    }
    assert result["publish_allowed"] is False
    assert result["write_to_formal_store"] is False


def test_publish_hxy_p0_answer_cards_cli_dry_run_writes_report_without_formal_cards(tmp_path: Path):
    package_path = tmp_path / "p0-approved-card-publication-package.json"
    report_path = tmp_path / "p0-approved-card-publication-dry-run.json"
    package_path.write_text(
        json.dumps(
            {
                "version": "hxy-p0-approved-card-publication-package.v1",
                "publication_candidates": [
                    {
                        "source_case_id": "compliance-medical-001",
                        "source_task_id": "authority-gap-compliance-medical-001",
                        "manual_publication_ready": True,
                        "proposed_card": {
                            "card_id": "pending:p0:compliance-medical-001",
                            "question_pattern": "泡脚能治疗失眠吗？",
                            "intent": "risk_boundary",
                            "audience": "store_staff",
                            "answer": "不能说泡脚能治疗失眠。可以说泡脚是放松体验，不能替代医疗诊断或治疗。",
                            "publication_metadata": {
                                "source_references": ["knowledge/benchmarks/hxy-brain-benchmark-v1.json"],
                                "knowledge_version": "hxy-answer-card-2026-07-02",
                                "responsible_owner": "运营/合规负责人",
                                "effective_scope": "首店员工对外口径",
                                "risk_review_status": "passed",
                            },
                            "evidence": [
                                {
                                    "title": "P0 人工审核发布包：compliance-medical-001",
                                    "domain": "risk_boundary",
                                    "status": "pending_manual_publication",
                                    "source_type": "manual_publication_package",
                                }
                            ],
                        },
                    }
                ],
                "blocked_items": [],
                "publish_allowed": False,
                "write_to_formal_store": False,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "publish-hxy-p0-answer-cards.py"),
            "dry-run",
            "--package",
            str(package_path),
            "--output",
            str(report_path),
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    stdout = json.loads(result.stdout)
    assert stdout["valid"] is True
    assert stdout["dry_run_path"] == str(report_path)
    assert report_path.is_file()

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["valid"] is True
    assert report["payload_count"] == 1
    assert report["would_write_count"] == 0
    assert report["draft_answer_card_payloads"][0]["status"] == "draft"
    assert "approved_answer_cards" not in report


def test_publish_p0_dry_run_payloads_requires_explicit_confirmation(tmp_path: Path):
    from apps.api.hxy_knowledge.loop_engine import publish_p0_dry_run_answer_cards_to_reviewed_file

    dry_run = {
        "version": "hxy-p0-approved-card-publication-dry-run.v1",
        "valid": True,
        "draft_answer_card_payloads": [
            {
                "question_pattern": "泡脚能治疗失眠吗？",
                "intent": "risk_boundary",
                "audience": "store_staff",
                "answer": "不能说泡脚能治疗失眠。",
                "status": "draft",
                "target_status_after_manual_publish": "approved",
                "review_status_after_manual_publish": "approved_v1",
                "publication_metadata": {
                    "knowledge_version": "hxy-answer-card-2026-07-02",
                    "responsible_owner": "运营/合规负责人",
                },
            }
        ],
    }

    result = publish_p0_dry_run_answer_cards_to_reviewed_file(dry_run, confirm_manual_publication=False)

    assert result["version"] == "hxy-p0-reviewed-answer-cards-publication.v1"
    assert result["published"] is False
    assert result["published_count"] == 0
    assert result["error_count"] == 1
    assert result["errors"][0]["code"] == "missing_manual_publication_confirmation"
    assert result["write_to_database"] is False
    assert result["requires_import_step"] is True
    assert "approved_answer_cards" not in result


def test_publish_p0_dry_run_payloads_to_reviewed_file_with_confirmation(tmp_path: Path):
    from apps.api.hxy_knowledge.loop_engine import publish_p0_dry_run_answer_cards_to_reviewed_file

    dry_run = {
        "version": "hxy-p0-approved-card-publication-dry-run.v1",
        "valid": True,
        "draft_answer_card_payloads": [
            {
                "question_pattern": "泡脚能治疗失眠吗？",
                "intent": "risk_boundary",
                "audience": "store_staff",
                "answer": "不能说泡脚能治疗失眠。",
                "reasoning": ["人工复核后发布。"],
                "evidence": [{"title": "P0 人工审核发布包", "status": "pending_manual_publication"}],
                "corrections": [],
                "next_actions": [],
                "status": "draft",
                "source_answer_id": "pending:p0:compliance-medical-001",
                "target_status_after_manual_publish": "approved",
                "review_status_after_manual_publish": "approved_v1",
                "publication_metadata": {
                    "source_references": ["knowledge/benchmarks/hxy-brain-benchmark-v1.json"],
                    "knowledge_version": "hxy-answer-card-2026-07-02",
                    "responsible_owner": "运营/合规负责人",
                    "effective_scope": "首店员工对外口径",
                    "risk_review_status": "passed",
                },
            }
        ],
    }

    result = publish_p0_dry_run_answer_cards_to_reviewed_file(dry_run, confirm_manual_publication=True)

    assert result["version"] == "hxy-p0-reviewed-answer-cards-publication.v1"
    assert result["published"] is True
    assert result["published_count"] == 1
    assert result["error_count"] == 0
    assert result["write_to_database"] is False
    assert result["requires_import_step"] is True
    assert result["official_use_allowed"] is True
    assert result["authority_rule"] == "reviewed_file_requires_separate_import_to_formal_store"

    card = result["reviewed_answer_cards"][0]
    assert card["status"] == "approved"
    assert card["review_status"] == "approved_v1"
    assert card["source_answer_id"] == "pending:p0:compliance-medical-001"
    assert card["publication_metadata"]["knowledge_version"] == "hxy-answer-card-2026-07-02"
    assert card["source"] == "p0_reviewed_file_publication"


def test_publish_hxy_p0_answer_cards_cli_publish_requires_confirmation_and_writes_reviewed_file(tmp_path: Path):
    dry_run_path = tmp_path / "p0-approved-card-publication-dry-run.json"
    reviewed_path = tmp_path / "published-answer-cards.reviewed.json"
    dry_run_path.write_text(
        json.dumps(
            {
                "version": "hxy-p0-approved-card-publication-dry-run.v1",
                "valid": True,
                "draft_answer_card_payloads": [
                    {
                        "question_pattern": "泡脚能治疗失眠吗？",
                        "intent": "risk_boundary",
                        "audience": "store_staff",
                        "answer": "不能说泡脚能治疗失眠。",
                        "reasoning": ["人工复核后发布。"],
                        "evidence": [{"title": "P0 人工审核发布包", "status": "pending_manual_publication"}],
                        "corrections": [],
                        "next_actions": [],
                        "status": "draft",
                        "source_answer_id": "pending:p0:compliance-medical-001",
                        "target_status_after_manual_publish": "approved",
                        "review_status_after_manual_publish": "approved_v1",
                        "publication_metadata": {
                            "source_references": ["knowledge/benchmarks/hxy-brain-benchmark-v1.json"],
                            "knowledge_version": "hxy-answer-card-2026-07-02",
                            "responsible_owner": "运营/合规负责人",
                            "effective_scope": "首店员工对外口径",
                            "risk_review_status": "passed",
                        },
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    missing_confirm = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "publish-hxy-p0-answer-cards.py"),
            "publish",
            "--dry-run",
            str(dry_run_path),
            "--output",
            str(reviewed_path),
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert missing_confirm.returncode == 1
    assert not reviewed_path.exists()
    missing_body = json.loads(missing_confirm.stdout)
    assert missing_body["published"] is False
    assert missing_body["error_count"] == 1

    confirmed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "publish-hxy-p0-answer-cards.py"),
            "publish",
            "--dry-run",
            str(dry_run_path),
            "--output",
            str(reviewed_path),
            "--confirm-manual-publication",
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert confirmed.returncode == 0, confirmed.stderr
    body = json.loads(confirmed.stdout)
    assert body["published"] is True
    assert body["reviewed_path"] == str(reviewed_path)
    reviewed = json.loads(reviewed_path.read_text(encoding="utf-8"))
    assert reviewed["published_count"] == 1
    assert reviewed["reviewed_answer_cards"][0]["status"] == "approved"
    assert reviewed["write_to_database"] is False


def test_reviewed_answer_cards_import_gate_detects_conflicts_without_writing(tmp_path: Path):
    from apps.api.hxy_knowledge.loop_engine import validate_p0_reviewed_answer_cards_import_gate

    reviewed_file = {
        "version": "hxy-p0-reviewed-answer-cards-publication.v1",
        "published": True,
        "reviewed_answer_cards": [
            {
                "question_pattern": "泡脚能治疗失眠吗？",
                "intent": "risk_boundary",
                "audience": "store_staff",
                "answer": "不能说泡脚能治疗失眠。",
                "status": "approved",
                "review_status": "approved_v1",
                "source_answer_id": "pending:p0:compliance-medical-001",
                "publication_metadata": {
                    "source_references": ["knowledge/benchmarks/hxy-brain-benchmark-v1.json"],
                    "knowledge_version": "hxy-answer-card-2026-07-02",
                    "responsible_owner": "运营/合规负责人",
                    "effective_scope": "首店员工对外口径",
                    "risk_review_status": "passed",
                },
            }
        ],
    }
    existing_cards = [
        {
            "question_pattern": "泡脚能治疗失眠吗？",
            "intent": "risk_boundary",
            "status": "approved",
            "source_answer_id": "existing:p0:medical",
        }
    ]

    gate = validate_p0_reviewed_answer_cards_import_gate(reviewed_file, existing_cards)

    assert gate["version"] == "hxy-p0-reviewed-answer-cards-import-gate.v1"
    assert gate["valid"] is False
    assert gate["reviewed_card_count"] == 1
    assert gate["importable_count"] == 0
    assert gate["conflict_count"] == 1
    assert gate["error_count"] == 0
    assert gate["would_import_count"] == 0
    assert gate["write_to_database"] is False
    assert gate["requires_import_confirmation"] is True
    assert "imported_answer_cards" not in gate
    assert gate["conflicts"][0]["code"] == "duplicate_question_intent"
    assert gate["conflicts"][0]["question_pattern"] == "泡脚能治疗失眠吗？"


def test_reviewed_answer_cards_import_gate_marks_clean_cards_importable_without_writing(tmp_path: Path):
    from apps.api.hxy_knowledge.loop_engine import validate_p0_reviewed_answer_cards_import_gate

    reviewed_file = {
        "version": "hxy-p0-reviewed-answer-cards-publication.v1",
        "published": True,
        "reviewed_answer_cards": [
            {
                "question_pattern": "泡脚能治疗失眠吗？",
                "intent": "risk_boundary",
                "audience": "store_staff",
                "answer": "不能说泡脚能治疗失眠。",
                "status": "approved",
                "review_status": "approved_v1",
                "source_answer_id": "pending:p0:compliance-medical-001",
                "publication_metadata": {
                    "source_references": ["knowledge/benchmarks/hxy-brain-benchmark-v1.json"],
                    "knowledge_version": "hxy-answer-card-2026-07-02",
                    "responsible_owner": "运营/合规负责人",
                    "effective_scope": "首店员工对外口径",
                    "risk_review_status": "passed",
                },
            }
        ],
    }

    gate = validate_p0_reviewed_answer_cards_import_gate(reviewed_file, existing_cards=[])

    assert gate["valid"] is True
    assert gate["reviewed_card_count"] == 1
    assert gate["importable_count"] == 1
    assert gate["conflict_count"] == 0
    assert gate["error_count"] == 0
    assert gate["would_import_count"] == 0
    assert gate["write_to_database"] is False
    assert gate["importable_answer_cards"][0]["status"] == "approved"
    assert gate["authority_rule"] == "import_gate_checks_only_and_does_not_write_database"


def test_import_hxy_p0_reviewed_answer_cards_cli_gate_writes_report(tmp_path: Path):
    reviewed_path = tmp_path / "published-answer-cards.reviewed.json"
    existing_path = tmp_path / "existing-answer-cards.json"
    report_path = tmp_path / "reviewed-answer-cards.import-gate.json"
    reviewed_path.write_text(
        json.dumps(
            {
                "version": "hxy-p0-reviewed-answer-cards-publication.v1",
                "published": True,
                "reviewed_answer_cards": [
                    {
                        "question_pattern": "泡脚能治疗失眠吗？",
                        "intent": "risk_boundary",
                        "audience": "store_staff",
                        "answer": "不能说泡脚能治疗失眠。",
                        "status": "approved",
                        "review_status": "approved_v1",
                        "source_answer_id": "pending:p0:compliance-medical-001",
                        "publication_metadata": {
                            "source_references": ["knowledge/benchmarks/hxy-brain-benchmark-v1.json"],
                            "knowledge_version": "hxy-answer-card-2026-07-02",
                            "responsible_owner": "运营/合规负责人",
                            "effective_scope": "首店员工对外口径",
                            "risk_review_status": "passed",
                        },
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    existing_path.write_text(json.dumps({"items": []}, ensure_ascii=False), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "import-hxy-p0-reviewed-answer-cards.py"),
            "gate",
            "--reviewed",
            str(reviewed_path),
            "--existing",
            str(existing_path),
            "--output",
            str(report_path),
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    stdout = json.loads(result.stdout)
    assert stdout["valid"] is True
    assert stdout["gate_path"] == str(report_path)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["valid"] is True
    assert report["importable_count"] == 1
    assert report["write_to_database"] is False


def _valid_p0_review_decisions_payload() -> dict:
    return {
        "version": "hxy-p0-review-decisions.v1",
        "items": [
            {
                "source_case_id": "compliance-medical-001",
                "source_task_id": "authority-gap-compliance-medical-001",
                "action": "approve",
                "reviewer": "运营/合规负责人",
                "publication_metadata": {
                    "source_references": ["knowledge/benchmarks/hxy-brain-benchmark-v1.json"],
                    "knowledge_version": "hxy-answer-card-2026-07-02",
                    "responsible_owner": "运营/合规负责人",
                    "effective_scope": "首店员工对外口径",
                    "risk_review_status": "passed",
                },
            }
        ],
    }


def _write_json_file(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _build_valid_p0_governance_run(tmp_path: Path, *, through: str) -> Path:
    from apps.api.hxy_knowledge.loop_engine import (
        BenchmarkImprovementLoopConfig,
        build_p0_review_decisions_audit,
        build_p0_review_decisions_sample,
        dry_run_p0_approved_card_publication_package,
        publish_p0_dry_run_answer_cards_to_reviewed_file,
        render_p0_review_decisions_audit_markdown,
        render_p0_review_decisions_validation_markdown,
        run_benchmark_improvement_loop,
        validate_p0_reviewed_answer_cards_import_gate,
    )

    output_path = tmp_path / "benchmark-report.json"
    runs_dir = tmp_path / "runs"
    run_id = f"benchmark-loop-stale-{through}"
    run_root = runs_dir / run_id
    run_root.mkdir(parents=True)
    _write_json_file(run_root / "p0-review-decisions.json", _valid_p0_review_decisions_payload())

    run_benchmark_improvement_loop(
        BenchmarkImprovementLoopConfig(
            benchmark_path=ROOT / "knowledge" / "benchmarks" / "hxy-brain-benchmark-v1.json",
            report_path=output_path,
            runs_dir=runs_dir,
            run_id=run_id,
            max_iterations=1,
        )
    )
    _write_json_file(run_root / "p0-review-decisions.sample.json", {"version": "hxy-p0-review-decisions-sample.v1"})
    sample = build_p0_review_decisions_sample(
        json.loads((run_root / "p0-review-decisions.stub.json").read_text(encoding="utf-8"))
    )
    _write_json_file(run_root / "p0-review-decisions.sample.json", sample)
    decisions = json.loads((run_root / "p0-review-decisions.json").read_text(encoding="utf-8"))
    audit = build_p0_review_decisions_audit(sample, decisions)
    _write_json_file(run_root / "p0-review-decisions.audit.json", audit)
    (run_root / "p0-review-decisions.audit.md").write_text(
        render_p0_review_decisions_audit_markdown(audit),
        encoding="utf-8",
    )

    if through in {"dry_run", "reviewed", "import_gate"}:
        validation = json.loads((run_root / "p0-review-decisions.validation.json").read_text(encoding="utf-8"))
        (run_root / "p0-review-decisions.report.md").write_text(
            render_p0_review_decisions_validation_markdown(validation),
            encoding="utf-8",
        )

    if through in {"dry_run", "reviewed", "import_gate"}:
        package = json.loads((run_root / "p0-approved-card-publication-package.json").read_text(encoding="utf-8"))
        dry_run = dry_run_p0_approved_card_publication_package(package)
        _write_json_file(run_root / "p0-approved-card-publication-dry-run.json", dry_run)

    if through in {"reviewed", "import_gate"}:
        dry_run = json.loads((run_root / "p0-approved-card-publication-dry-run.json").read_text(encoding="utf-8"))
        reviewed = publish_p0_dry_run_answer_cards_to_reviewed_file(
            dry_run,
            confirm_manual_publication=True,
        )
        _write_json_file(run_root / "published-answer-cards.reviewed.json", reviewed)

    if through == "import_gate":
        reviewed = json.loads((run_root / "published-answer-cards.reviewed.json").read_text(encoding="utf-8"))
        _write_json_file(run_root / "existing-answer-cards.json", {"items": []})
        gate = validate_p0_reviewed_answer_cards_import_gate(reviewed, existing_cards=[])
        _write_json_file(run_root / "reviewed-answer-cards.import-gate.json", gate)

    return run_root


def test_p0_governance_status_reports_missing_stub_next_command(tmp_path: Path):
    from apps.api.hxy_knowledge.loop_engine import build_p0_governance_status

    run_dir = tmp_path / "runs" / "benchmark-loop-latest"
    status = build_p0_governance_status(
        run_dir,
        benchmark_path=ROOT / "knowledge" / "benchmarks" / "hxy-brain-benchmark-v1.json",
        report_path=tmp_path / "benchmark-latest.json",
    )

    assert status["version"] == "hxy-p0-governance-status.v1"
    assert status["current_step"] == "missing_stub"
    assert status["blocked"] is True
    assert status["missing_files"] == ["p0-review-decisions.stub.json"]
    assert "run-hxy-loop.py benchmark_improvement" in status["next_command"]
    assert status["write_to_database"] is False
    assert status["authority_rule"] == "status_check_is_read_only"


def test_p0_governance_status_reports_awaiting_manual_decisions(tmp_path: Path):
    from apps.api.hxy_knowledge.loop_engine import build_p0_governance_status

    run_dir = tmp_path / "runs" / "benchmark-loop-latest"
    run_dir.mkdir(parents=True)
    (run_dir / "p0-review-decisions.stub.json").write_text(
        json.dumps({"version": "hxy-p0-review-decisions.v1", "items": []}, ensure_ascii=False),
        encoding="utf-8",
    )
    (run_dir / "p0-review-decisions.sample.json").write_text(
        json.dumps({"version": "hxy-p0-review-decisions-sample.v1", "items": []}, ensure_ascii=False),
        encoding="utf-8",
    )
    (run_dir / "p0-manual-review-packet.json").write_text(
        json.dumps({"version": "hxy-p0-manual-review-packet.v1", "items": []}, ensure_ascii=False),
        encoding="utf-8",
    )
    (run_dir / "p0-manual-review-packet.md").write_text(
        "# HXY P0 Manual Review Packet\n",
        encoding="utf-8",
    )

    status = build_p0_governance_status(run_dir)

    assert status["current_step"] == "awaiting_manual_decisions"
    assert status["blocked"] is True
    assert status["missing_files"] == ["p0-review-decisions.json"]
    assert "p0-manual-review-packet.md" in status["next_action"]
    assert "validate-hxy-p0-review-decisions.py init-decisions" in status["next_command"]
    assert "p0-review-decisions.sample.json" in status["next_command"]
    assert "p0-review-decisions.json" in status["next_command"]


def test_p0_governance_status_requests_manual_review_packet_before_decisions(tmp_path: Path):
    from apps.api.hxy_knowledge.loop_engine import BenchmarkImprovementLoopConfig, build_p0_governance_status, run_benchmark_improvement_loop

    output_path = tmp_path / "benchmark-report.json"
    runs_dir = tmp_path / "runs"
    run_id = "benchmark-loop-needs-review-packet"
    run_root = runs_dir / run_id

    run_benchmark_improvement_loop(
        BenchmarkImprovementLoopConfig(
            benchmark_path=ROOT / "knowledge" / "benchmarks" / "hxy-brain-benchmark-v1.json",
            report_path=output_path,
            runs_dir=runs_dir,
            run_id=run_id,
            max_iterations=1,
        )
    )
    (run_root / "p0-review-decisions.sample.json").write_text(
        json.dumps({"version": "hxy-p0-review-decisions-sample.v1", "items": []}, ensure_ascii=False),
        encoding="utf-8",
    )

    status = build_p0_governance_status(run_root)

    assert status["current_step"] == "needs_manual_review_packet"
    assert status["blocked"] is True
    assert status["missing_files"] == ["p0-manual-review-packet.json", "p0-manual-review-packet.md"]
    assert "validate-hxy-p0-review-decisions.py review-packet" in status["next_command"]
    assert "p0-review-decisions.json" not in status["next_command"]
    assert status["write_to_database"] is False


def test_p0_governance_status_points_to_review_packet_when_awaiting_manual_decisions(tmp_path: Path):
    from apps.api.hxy_knowledge.loop_engine import (
        BenchmarkImprovementLoopConfig,
        build_p0_governance_status,
        build_p0_manual_review_packet,
        build_p0_review_decisions_sample,
        render_p0_manual_review_packet_markdown,
        run_benchmark_improvement_loop,
    )

    output_path = tmp_path / "benchmark-report.json"
    runs_dir = tmp_path / "runs"
    run_id = "benchmark-loop-review-packet-ready"
    run_root = runs_dir / run_id

    state = run_benchmark_improvement_loop(
        BenchmarkImprovementLoopConfig(
            benchmark_path=ROOT / "knowledge" / "benchmarks" / "hxy-brain-benchmark-v1.json",
            report_path=output_path,
            runs_dir=runs_dir,
            run_id=run_id,
            max_iterations=1,
        )
    )
    correction_package = state["iterations"][0]["correction_package"]
    stub = correction_package["p0_review_decision_stub"]
    draft_pack = correction_package["p0_authority_card_draft_pack"]
    sample = build_p0_review_decisions_sample(stub)
    _write_json_file(run_root / "p0-review-decisions.sample.json", sample)
    packet = build_p0_manual_review_packet(
        decision_stub=stub,
        draft_pack=draft_pack,
        review_manifest=draft_pack["review_manifest"],
        decision_sample=sample,
    )
    _write_json_file(run_root / "p0-manual-review-packet.json", packet)
    (run_root / "p0-manual-review-packet.md").write_text(
        render_p0_manual_review_packet_markdown(packet),
        encoding="utf-8",
    )

    status = build_p0_governance_status(run_root)

    assert status["current_step"] == "awaiting_manual_decisions"
    assert status["blocked"] is True
    assert status["missing_files"] == ["p0-review-decisions.json"]
    assert "p0-manual-review-packet.md" in status["next_action"]
    assert "validate-hxy-p0-review-decisions.py init-decisions" in status["next_command"]
    assert "p0-review-decisions.sample.json" in status["next_command"]
    assert "p0-review-decisions.json" in status["next_command"]
    assert status["write_to_database"] is False


def test_p0_governance_status_blocks_all_pending_manual_decisions(tmp_path: Path):
    from apps.api.hxy_knowledge.loop_engine import (
        BenchmarkImprovementLoopConfig,
        build_p0_governance_status,
        build_p0_manual_review_packet,
        build_p0_review_decisions_sample,
        render_p0_manual_review_packet_markdown,
        run_benchmark_improvement_loop,
    )

    output_path = tmp_path / "benchmark-report.json"
    runs_dir = tmp_path / "runs"
    run_id = "benchmark-loop-empty-manual-decisions"
    run_root = runs_dir / run_id

    state = run_benchmark_improvement_loop(
        BenchmarkImprovementLoopConfig(
            benchmark_path=ROOT / "knowledge" / "benchmarks" / "hxy-brain-benchmark-v1.json",
            report_path=output_path,
            runs_dir=runs_dir,
            run_id=run_id,
            max_iterations=1,
        )
    )
    correction_package = state["iterations"][0]["correction_package"]
    stub = correction_package["p0_review_decision_stub"]
    draft_pack = correction_package["p0_authority_card_draft_pack"]
    sample = build_p0_review_decisions_sample(stub)
    _write_json_file(run_root / "p0-review-decisions.sample.json", sample)
    packet = build_p0_manual_review_packet(
        decision_stub=stub,
        draft_pack=draft_pack,
        review_manifest=draft_pack["review_manifest"],
        decision_sample=sample,
    )
    _write_json_file(run_root / "p0-manual-review-packet.json", packet)
    (run_root / "p0-manual-review-packet.md").write_text(
        render_p0_manual_review_packet_markdown(packet),
        encoding="utf-8",
    )
    _write_json_file(run_root / "p0-review-decisions.json", sample)

    status = build_p0_governance_status(run_root)

    assert status["current_step"] == "blocked_at_empty_manual_decisions"
    assert status["blocked"] is True
    assert status["missing_files"] == []
    assert status["details"]["decision_count"] == 4
    assert status["details"]["pending_count"] == 4
    assert status["details"]["actioned_count"] == 0
    assert status["details"]["pending_case_ids"] == [
        "compliance-medical-001",
        "compliance-effect-001",
        "compliance-marketing-001",
        "risk-002",
    ]
    assert "p0-manual-review-packet.md" in status["next_action"]
    assert "p0-review-decisions.json" in status["next_action"]
    assert "validate-hxy-p0-review-decisions.py edit-guide" in status["next_command"]
    assert "p0-decision-edit-guide.md" in status["next_command"]
    assert "validate-hxy-p0-review-decisions.py validate" not in status["next_command"]
    assert status["write_to_database"] is False


def test_p0_governance_status_requires_audit_before_validation_for_needs_revision_decision(tmp_path: Path):
    from apps.api.hxy_knowledge.loop_engine import (
        BenchmarkImprovementLoopConfig,
        build_p0_governance_status,
        build_p0_review_decisions_sample,
        run_benchmark_improvement_loop,
    )

    output_path = tmp_path / "benchmark-report.json"
    runs_dir = tmp_path / "runs"
    run_id = "benchmark-loop-partial-needs-revision"
    run_root = runs_dir / run_id

    state = run_benchmark_improvement_loop(
        BenchmarkImprovementLoopConfig(
            benchmark_path=ROOT / "knowledge" / "benchmarks" / "hxy-brain-benchmark-v1.json",
            report_path=output_path,
            runs_dir=runs_dir,
            run_id=run_id,
            max_iterations=1,
        )
    )
    stub = state["iterations"][0]["correction_package"]["p0_review_decision_stub"]
    _write_json_file(run_root / "p0-review-decisions.sample.json", build_p0_review_decisions_sample(stub))
    _write_json_file(
        run_root / "p0-review-decisions.json",
        {
            "version": "hxy-p0-review-decisions.v1",
            "items": [
                {
                    "source_case_id": "compliance-medical-001",
                    "source_task_id": "authority-gap-compliance-medical-001",
                    "action": "needs_revision",
                    "reviewer": "运营/合规负责人",
                    "note": "需要补充已核定来源后再审核。",
                }
            ],
        },
    )

    status = build_p0_governance_status(run_root)

    assert status["current_step"] == "needs_decision_audit"
    assert status["blocked"] is True
    assert status["missing_files"] == ["p0-review-decisions.audit.json", "p0-review-decisions.audit.md"]
    assert "validate-hxy-p0-review-decisions.py decision-audit" in status["next_command"]
    assert status["write_to_database"] is False


def test_p0_governance_status_requires_audit_before_validation_for_reject_decision(tmp_path: Path):
    from apps.api.hxy_knowledge.loop_engine import (
        BenchmarkImprovementLoopConfig,
        build_p0_governance_status,
        build_p0_review_decisions_sample,
        run_benchmark_improvement_loop,
    )

    output_path = tmp_path / "benchmark-report.json"
    runs_dir = tmp_path / "runs"
    run_id = "benchmark-loop-partial-reject"
    run_root = runs_dir / run_id

    state = run_benchmark_improvement_loop(
        BenchmarkImprovementLoopConfig(
            benchmark_path=ROOT / "knowledge" / "benchmarks" / "hxy-brain-benchmark-v1.json",
            report_path=output_path,
            runs_dir=runs_dir,
            run_id=run_id,
            max_iterations=1,
        )
    )
    stub = state["iterations"][0]["correction_package"]["p0_review_decision_stub"]
    _write_json_file(run_root / "p0-review-decisions.sample.json", build_p0_review_decisions_sample(stub))
    _write_json_file(
        run_root / "p0-review-decisions.json",
        {
            "version": "hxy-p0-review-decisions.v1",
            "items": [
                {
                    "source_case_id": "compliance-marketing-001",
                    "source_task_id": "authority-gap-compliance-marketing-001",
                    "action": "reject",
                    "reviewer": "运营/合规负责人",
                    "note": "风险边界不够稳，拒绝进入发布预检。",
                }
            ],
        },
    )

    status = build_p0_governance_status(run_root)

    assert status["current_step"] == "needs_decision_audit"
    assert status["blocked"] is True
    assert status["missing_files"] == ["p0-review-decisions.audit.json", "p0-review-decisions.audit.md"]
    assert "validate-hxy-p0-review-decisions.py decision-audit" in status["next_command"]
    assert status["write_to_database"] is False


def test_p0_governance_status_requires_audit_markdown_before_validation(tmp_path: Path):
    from apps.api.hxy_knowledge.loop_engine import (
        BenchmarkImprovementLoopConfig,
        build_p0_governance_status,
        build_p0_review_decisions_audit,
        build_p0_review_decisions_sample,
        run_benchmark_improvement_loop,
    )

    output_path = tmp_path / "benchmark-report.json"
    runs_dir = tmp_path / "runs"
    run_id = "benchmark-loop-missing-audit-markdown"
    run_root = runs_dir / run_id

    state = run_benchmark_improvement_loop(
        BenchmarkImprovementLoopConfig(
            benchmark_path=ROOT / "knowledge" / "benchmarks" / "hxy-brain-benchmark-v1.json",
            report_path=output_path,
            runs_dir=runs_dir,
            run_id=run_id,
            max_iterations=1,
        )
    )
    stub = state["iterations"][0]["correction_package"]["p0_review_decision_stub"]
    sample = build_p0_review_decisions_sample(stub)
    decisions = json.loads(json.dumps(sample))
    decisions["items"][0]["action"] = "needs_revision"
    decisions["items"][0]["reviewer"] = "运营/合规负责人"
    decisions["items"][0]["note"] = "需要补充核定来源后再审核。"
    audit = build_p0_review_decisions_audit(sample, decisions)
    _write_json_file(run_root / "p0-review-decisions.sample.json", sample)
    _write_json_file(run_root / "p0-review-decisions.json", decisions)
    _write_json_file(run_root / "p0-review-decisions.audit.json", audit)

    status = build_p0_governance_status(run_root)

    assert status["current_step"] == "needs_decision_audit"
    assert status["blocked"] is True
    assert status["missing_files"] == ["p0-review-decisions.audit.md"]
    assert "validate-hxy-p0-review-decisions.py decision-audit" in status["next_command"]
    assert status["write_to_database"] is False


def test_p0_governance_status_inline_validates_bad_manual_decisions_without_validation_file(tmp_path: Path):
    from apps.api.hxy_knowledge.loop_engine import BenchmarkImprovementLoopConfig, build_p0_governance_status, run_benchmark_improvement_loop

    output_path = tmp_path / "benchmark-report.json"
    runs_dir = tmp_path / "runs"
    run_id = "benchmark-loop-inline-validation"
    run_root = runs_dir / run_id

    run_benchmark_improvement_loop(
        BenchmarkImprovementLoopConfig(
            benchmark_path=ROOT / "knowledge" / "benchmarks" / "hxy-brain-benchmark-v1.json",
            report_path=output_path,
            runs_dir=runs_dir,
            run_id=run_id,
            max_iterations=1,
        )
    )
    (run_root / "p0-review-decisions.sample.json").write_text(
        json.dumps({"version": "hxy-p0-review-decisions-sample.v1", "items": []}, ensure_ascii=False),
        encoding="utf-8",
    )
    (run_root / "p0-review-decisions.json").write_text(
        json.dumps(
            {
                "version": "hxy-p0-review-decisions.v1",
                "items": [
                    {
                        "source_case_id": "compliance-medical-001",
                        "source_task_id": "authority-gap-compliance-medical-001",
                        "action": "approved",
                        "reviewer": "运营/合规负责人",
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    status = build_p0_governance_status(run_root)

    assert status["current_step"] == "blocked_at_decision_validation"
    assert status["blocked"] is True
    assert status["missing_files"] == ["p0-review-decisions.validation.json"]
    assert status["details"]["error_count"] == 1
    assert status["details"]["errors"][0]["code"] == "invalid_action"
    assert "validate-hxy-p0-review-decisions.py validate" in status["next_command"]
    assert status["write_to_database"] is False


def test_p0_governance_status_detects_stale_decision_validation_after_manual_edit(tmp_path: Path):
    from apps.api.hxy_knowledge.loop_engine import BenchmarkImprovementLoopConfig, build_p0_governance_status, run_benchmark_improvement_loop

    output_path = tmp_path / "benchmark-report.json"
    runs_dir = tmp_path / "runs"
    run_id = "benchmark-loop-stale-validation"
    run_root = runs_dir / run_id

    run_benchmark_improvement_loop(
        BenchmarkImprovementLoopConfig(
            benchmark_path=ROOT / "knowledge" / "benchmarks" / "hxy-brain-benchmark-v1.json",
            report_path=output_path,
            runs_dir=runs_dir,
            run_id=run_id,
            max_iterations=1,
        )
    )
    (run_root / "p0-review-decisions.sample.json").write_text(
        json.dumps({"version": "hxy-p0-review-decisions-sample.v1", "items": []}, ensure_ascii=False),
        encoding="utf-8",
    )
    decisions_path = run_root / "p0-review-decisions.json"
    decisions_path.write_text(
        json.dumps(
            {
                "version": "hxy-p0-review-decisions.v1",
                "items": [
                    {
                        "source_case_id": "compliance-medical-001",
                        "source_task_id": "authority-gap-compliance-medical-001",
                        "action": "needs_revision",
                        "reviewer": "运营/合规负责人",
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    validation_result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "validate-hxy-p0-review-decisions.py"),
            "validate",
            "--stub",
            str(run_root / "p0-review-decisions.stub.json"),
            "--decisions",
            str(decisions_path),
            "--output",
            str(run_root / "p0-review-decisions.validation.json"),
        ],
        check=False,
        text=True,
        capture_output=True,
    )
    assert validation_result.returncode == 0, validation_result.stderr

    decisions_path.write_text(
        json.dumps(
            {
                "version": "hxy-p0-review-decisions.v1",
                "items": [
                    {
                        "source_case_id": "compliance-medical-001",
                        "source_task_id": "authority-gap-compliance-medical-001",
                        "action": "approved",
                        "reviewer": "运营/合规负责人",
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    status = build_p0_governance_status(run_root)

    assert status["current_step"] == "stale_decision_validation"
    assert status["blocked"] is True
    assert status["missing_files"] == []
    assert status["details"]["stale_file"] == "p0-review-decisions.validation.json"
    assert status["details"]["current_decision_digest"]
    assert status["details"]["validation_decision_digest"]
    assert status["details"]["current_decision_digest"] != status["details"]["validation_decision_digest"]
    assert "validate-hxy-p0-review-decisions.py validate" in status["next_command"]
    assert status["write_to_database"] is False


def test_p0_governance_status_requires_decision_report_after_valid_validation(tmp_path: Path):
    from apps.api.hxy_knowledge.loop_engine import build_p0_governance_status

    run_root = _build_valid_p0_governance_run(tmp_path, through="package")

    status = build_p0_governance_status(run_root)

    assert status["current_step"] == "needs_decision_report"
    assert status["blocked"] is True
    assert status["missing_files"] == ["p0-review-decisions.report.md"]
    assert "validate-hxy-p0-review-decisions.py decision-report" in status["next_command"]
    assert "p0-review-decisions.validation.json" in status["next_command"]
    assert "p0-review-decisions.report.md" in status["next_command"]
    assert status["write_to_database"] is False


def test_p0_governance_status_detects_stale_decision_report_after_report_mismatch(tmp_path: Path):
    from apps.api.hxy_knowledge.loop_engine import (
        build_p0_governance_status,
        render_p0_review_decisions_validation_markdown,
    )

    run_root = _build_valid_p0_governance_run(tmp_path, through="package")
    validation_path = run_root / "p0-review-decisions.validation.json"
    validation = json.loads(validation_path.read_text(encoding="utf-8"))
    (run_root / "p0-review-decisions.report.md").write_text(
        render_p0_review_decisions_validation_markdown(
            {
                **validation,
                "decision_fingerprint": {
                    "algorithm": "sha256",
                    "digest": "stale-report-fingerprint",
                },
            }
        ),
        encoding="utf-8",
    )

    status = build_p0_governance_status(run_root)

    assert status["current_step"] == "stale_decision_report"
    assert status["blocked"] is True
    assert status["details"]["stale_file"] == "p0-review-decisions.report.md"
    assert status["details"]["upstream_name"] == "p0-review-decisions.json"
    assert status["details"]["current_decision_digest"] != status["details"]["report_decision_digest"]
    assert "validate-hxy-p0-review-decisions.py decision-report" in status["next_command"]
    assert status["write_to_database"] is False


def test_p0_governance_status_detects_stale_publication_package_after_validation_changes(tmp_path: Path):
    from apps.api.hxy_knowledge.loop_engine import build_p0_governance_status

    run_root = _build_valid_p0_governance_run(tmp_path, through="package")
    from apps.api.hxy_knowledge.loop_engine import render_p0_review_decisions_validation_markdown

    validation = json.loads((run_root / "p0-review-decisions.validation.json").read_text(encoding="utf-8"))
    (run_root / "p0-review-decisions.report.md").write_text(
        render_p0_review_decisions_validation_markdown(validation),
        encoding="utf-8",
    )
    validation_path = run_root / "p0-review-decisions.validation.json"
    validation = json.loads(validation_path.read_text(encoding="utf-8"))
    validation["warning_count"] = 1
    _write_json_file(validation_path, validation)

    status = build_p0_governance_status(run_root)

    assert status["current_step"] == "stale_publication_package"
    assert status["blocked"] is True
    assert status["details"]["stale_file"] == "p0-approved-card-publication-package.json"
    assert status["details"]["upstream_name"] == "validation"
    assert status["details"]["current_upstream_digest"] != status["details"]["artifact_upstream_digest"]
    assert "run-hxy-loop.py benchmark_improvement" in status["next_command"]
    assert status["write_to_database"] is False


def test_p0_governance_status_detects_stale_publication_dry_run_after_package_changes(tmp_path: Path):
    from apps.api.hxy_knowledge.loop_engine import build_p0_governance_status

    run_root = _build_valid_p0_governance_run(tmp_path, through="dry_run")
    package_path = run_root / "p0-approved-card-publication-package.json"
    package = json.loads(package_path.read_text(encoding="utf-8"))
    package["operator_note"] = "manual package edit after dry-run"
    _write_json_file(package_path, package)

    status = build_p0_governance_status(run_root)

    assert status["current_step"] == "stale_publication_dry_run"
    assert status["blocked"] is True
    assert status["details"]["stale_file"] == "p0-approved-card-publication-dry-run.json"
    assert status["details"]["upstream_name"] == "publication_package"
    assert status["details"]["current_upstream_digest"] != status["details"]["artifact_upstream_digest"]
    assert "publish-hxy-p0-answer-cards.py dry-run" in status["next_command"]
    assert status["write_to_database"] is False


def test_p0_governance_status_detects_stale_reviewed_file_after_dry_run_changes(tmp_path: Path):
    from apps.api.hxy_knowledge.loop_engine import build_p0_governance_status

    run_root = _build_valid_p0_governance_run(tmp_path, through="reviewed")
    dry_run_path = run_root / "p0-approved-card-publication-dry-run.json"
    dry_run = json.loads(dry_run_path.read_text(encoding="utf-8"))
    dry_run["warnings"] = [{"code": "manual_dry_run_edit"}]
    _write_json_file(dry_run_path, dry_run)

    status = build_p0_governance_status(run_root)

    assert status["current_step"] == "stale_reviewed_file"
    assert status["blocked"] is True
    assert status["details"]["stale_file"] == "published-answer-cards.reviewed.json"
    assert status["details"]["upstream_name"] == "dry_run"
    assert status["details"]["current_upstream_digest"] != status["details"]["artifact_upstream_digest"]
    assert "publish-hxy-p0-answer-cards.py publish" in status["next_command"]
    assert status["write_to_database"] is False


def test_p0_governance_status_detects_stale_import_gate_after_reviewed_file_changes(tmp_path: Path):
    from apps.api.hxy_knowledge.loop_engine import build_p0_governance_status

    run_root = _build_valid_p0_governance_run(tmp_path, through="import_gate")
    reviewed_path = run_root / "published-answer-cards.reviewed.json"
    reviewed = json.loads(reviewed_path.read_text(encoding="utf-8"))
    reviewed["reviewed_answer_cards"][0]["next_actions"].append("manual reviewed-file edit after import gate")
    _write_json_file(reviewed_path, reviewed)

    status = build_p0_governance_status(run_root)

    assert status["current_step"] == "stale_import_gate"
    assert status["blocked"] is True
    assert status["details"]["stale_file"] == "reviewed-answer-cards.import-gate.json"
    assert status["details"]["upstream_name"] == "reviewed_file"
    assert status["details"]["current_upstream_digest"] != status["details"]["artifact_upstream_digest"]
    assert "import-hxy-p0-reviewed-answer-cards.py gate" in status["next_command"]
    assert status["write_to_database"] is False


def test_p0_governance_status_detects_stale_import_gate_after_existing_cards_change(tmp_path: Path):
    from apps.api.hxy_knowledge.loop_engine import build_p0_governance_status

    run_root = _build_valid_p0_governance_run(tmp_path, through="import_gate")
    _write_json_file(
        run_root / "existing-answer-cards.json",
        {
            "items": [
                {
                    "question_pattern": "泡脚能治疗失眠吗？",
                    "intent": "risk_boundary",
                    "status": "approved",
                    "source_answer_id": "existing:p0:medical",
                }
            ]
        },
    )

    status = build_p0_governance_status(run_root)

    assert status["current_step"] == "stale_import_gate"
    assert status["blocked"] is True
    assert status["details"]["stale_file"] == "reviewed-answer-cards.import-gate.json"
    assert status["details"]["upstream_name"] == "existing_answer_cards"
    assert status["details"]["current_upstream_digest"] != status["details"]["artifact_upstream_digest"]
    assert "import-hxy-p0-reviewed-answer-cards.py gate" in status["next_command"]
    assert status["write_to_database"] is False


def test_p0_governance_status_cli_reports_next_command(tmp_path: Path):
    run_dir = tmp_path / "runs" / "benchmark-loop-latest"
    run_dir.mkdir(parents=True)
    (run_dir / "p0-review-decisions.stub.json").write_text(
        json.dumps({"version": "hxy-p0-review-decisions.v1", "items": []}, ensure_ascii=False),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "check-hxy-p0-governance-status.py"),
            "--run-dir",
            str(run_dir),
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    body = json.loads(result.stdout)
    assert body["version"] == "hxy-p0-governance-status-cli.v1"
    assert body["status"]["current_step"] == "needs_sample"
    assert "validate-hxy-p0-review-decisions.py sample" in body["status"]["next_command"]
    assert body["status"]["write_to_database"] is False


def test_p0_governance_status_cli_human_output_is_operator_readable(tmp_path: Path):
    run_dir = tmp_path / "runs" / "benchmark-loop-latest"
    run_dir.mkdir(parents=True)
    (run_dir / "p0-review-decisions.stub.json").write_text(
        json.dumps({"version": "hxy-p0-review-decisions.v1", "items": []}, ensure_ascii=False),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "check-hxy-p0-governance-status.py"),
            "--run-dir",
            str(run_dir),
            "--human",
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    assert "HXY P0 Governance Status" in result.stdout
    assert "Current step: needs_sample" in result.stdout
    assert "Blocked: yes" in result.stdout
    assert "Missing files: p0-review-decisions.sample.json" in result.stdout
    assert "Next command:" in result.stdout
    assert "validate-hxy-p0-review-decisions.py sample" in result.stdout
    assert "write_to_database: false" in result.stdout


def test_p0_governance_status_cli_human_output_shows_empty_decision_details(tmp_path: Path):
    from apps.api.hxy_knowledge.loop_engine import (
        BenchmarkImprovementLoopConfig,
        build_p0_review_decisions_sample,
        initialize_p0_review_decisions_from_sample,
        run_benchmark_improvement_loop,
    )

    output_path = tmp_path / "benchmark-report.json"
    runs_dir = tmp_path / "runs"
    run_id = "benchmark-loop-human-empty-decisions"
    run_root = runs_dir / run_id

    state = run_benchmark_improvement_loop(
        BenchmarkImprovementLoopConfig(
            benchmark_path=ROOT / "knowledge" / "benchmarks" / "hxy-brain-benchmark-v1.json",
            report_path=output_path,
            runs_dir=runs_dir,
            run_id=run_id,
            max_iterations=1,
        )
    )
    stub = state["iterations"][0]["correction_package"]["p0_review_decision_stub"]
    sample = build_p0_review_decisions_sample(stub)
    _write_json_file(run_root / "p0-review-decisions.sample.json", sample)
    _write_json_file(run_root / "p0-review-decisions.json", initialize_p0_review_decisions_from_sample(sample))

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "check-hxy-p0-governance-status.py"),
            "--run-dir",
            str(run_root),
            "--human",
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    assert "Current step: blocked_at_empty_manual_decisions" in result.stdout
    assert "Decision count: 4" in result.stdout
    assert "Pending count: 4" in result.stdout
    assert "Actioned count: 0" in result.stdout
    assert "Pending case IDs: compliance-medical-001, compliance-effect-001, compliance-marketing-001, risk-002" in result.stdout
    assert "Decision edit guide status: missing" in result.stdout
    assert "Decision edit guide path:" in result.stdout
    assert "Decision audit status: missing" in result.stdout
    assert "Decision audit path:" in result.stdout


def test_p0_governance_status_cli_human_output_shows_stale_audit_source(tmp_path: Path):
    from apps.api.hxy_knowledge.loop_engine import (
        BenchmarkImprovementLoopConfig,
        build_p0_review_decisions_audit,
        build_p0_review_decisions_sample,
        run_benchmark_improvement_loop,
    )

    output_path = tmp_path / "benchmark-report.json"
    runs_dir = tmp_path / "runs"
    run_id = "benchmark-loop-human-stale-audit"
    run_root = runs_dir / run_id

    state = run_benchmark_improvement_loop(
        BenchmarkImprovementLoopConfig(
            benchmark_path=ROOT / "knowledge" / "benchmarks" / "hxy-brain-benchmark-v1.json",
            report_path=output_path,
            runs_dir=runs_dir,
            run_id=run_id,
            max_iterations=1,
        )
    )
    stub = state["iterations"][0]["correction_package"]["p0_review_decision_stub"]
    sample = build_p0_review_decisions_sample(stub)
    decisions = json.loads(json.dumps(sample))
    audit = build_p0_review_decisions_audit(sample, decisions)
    decisions["items"][0]["action"] = "needs_revision"
    decisions["items"][0]["reviewer"] = "运营/合规负责人"
    decisions["items"][0]["note"] = "需要补充核定资料后再审。"
    _write_json_file(run_root / "p0-review-decisions.sample.json", sample)
    _write_json_file(run_root / "p0-review-decisions.json", decisions)
    _write_json_file(run_root / "p0-review-decisions.audit.json", audit)
    (run_root / "p0-review-decisions.audit.md").write_text("stale audit fixture", encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "check-hxy-p0-governance-status.py"),
            "--run-dir",
            str(run_root),
            "--human",
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    assert "Current step: stale_decision_audit" in result.stdout
    assert "Decision audit status: stale" in result.stdout
    assert "Stale file: p0-review-decisions.audit.json" in result.stdout
    assert "Upstream changed: p0-review-decisions.json" in result.stdout


def test_run_hxy_p0_governance_safe_next_advances_to_reviewer_worksheet(tmp_path: Path):
    from apps.api.hxy_knowledge.loop_engine import (
        BenchmarkImprovementLoopConfig,
        run_benchmark_improvement_loop,
    )

    output_path = tmp_path / "benchmark-report.json"
    runs_dir = tmp_path / "runs"
    run_id = "benchmark-loop-safe-next"
    run_root = runs_dir / run_id

    run_benchmark_improvement_loop(
        BenchmarkImprovementLoopConfig(
            benchmark_path=ROOT / "knowledge" / "benchmarks" / "hxy-brain-benchmark-v1.json",
            report_path=output_path,
            runs_dir=runs_dir,
            run_id=run_id,
            max_iterations=1,
        )
    )

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "run-hxy-p0-governance-safe-next.py"),
            "--run-dir",
            str(run_root),
            "--benchmark",
            str(ROOT / "knowledge" / "benchmarks" / "hxy-brain-benchmark-v1.json"),
            "--report",
            str(output_path),
            "--max-steps",
            "8",
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    stdout = json.loads(result.stdout)
    assert stdout["version"] == "hxy-p0-governance-safe-next.v1"
    assert stdout["stopped_reason"] == "human_decision_required"
    assert stdout["executed_count"] == 7
    assert stdout["write_to_database"] is False
    assert [step["from_step"] for step in stdout["executed_steps"]] == [
        "needs_sample",
        "needs_manual_review_packet",
        "awaiting_manual_decisions",
        "blocked_at_empty_manual_decisions",
        "blocked_at_empty_manual_decisions",
        "blocked_at_empty_manual_decisions",
        "blocked_at_empty_manual_decisions",
    ]
    assert (run_root / "p0-review-decisions.sample.json").is_file()
    assert (run_root / "p0-manual-review-packet.json").is_file()
    assert (run_root / "p0-manual-review-packet.md").is_file()
    assert (run_root / "p0-review-decisions.json").is_file()
    assert (run_root / "p0-decision-edit-guide.md").is_file()
    assert (run_root / "p0-review-decisions.audit.json").is_file()
    assert (run_root / "p0-review-decisions.audit.md").is_file()
    assert (run_root / "p0-reviewer-worksheet.md").is_file()
    assert (run_root / "p0-reviewer-todo.json").is_file()
    decisions = json.loads((run_root / "p0-review-decisions.json").read_text(encoding="utf-8"))
    assert {item["action"] for item in decisions["items"]} == {"pending"}
    assert decisions["write_to_database"] is False
    assert not (run_root / "p0-approved-card-publication-dry-run.json").exists()
    assert not (run_root / "published-answer-cards.reviewed.json").exists()
    assert stdout["final_status"]["current_step"] == "blocked_at_empty_manual_decisions"
    assert stdout["final_status"]["details"]["reviewer_worksheet_status"] == "fresh"
    assert stdout["final_status"]["details"]["reviewer_todo_status"] == "fresh"


def test_run_hxy_p0_governance_safe_next_stops_when_no_safe_command(tmp_path: Path):
    run_root = tmp_path / "runs" / "benchmark-loop-no-stub"
    run_root.mkdir(parents=True)

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "run-hxy-p0-governance-safe-next.py"),
            "--run-dir",
            str(run_root),
            "--max-steps",
            "1",
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 1
    stdout = json.loads(result.stdout)
    assert stdout["stopped_reason"] == "unsafe_or_unsupported_command"
    assert stdout["executed_count"] == 0
    assert stdout["write_to_database"] is False


def test_report_hxy_p0_governance_dry_run_prints_safe_next_and_api_payloads(tmp_path: Path):
    from apps.api.hxy_knowledge.loop_engine import (
        BenchmarkImprovementLoopConfig,
        run_benchmark_improvement_loop,
    )

    output_path = tmp_path / "benchmark-report.json"
    runs_dir = tmp_path / "runs"
    run_id = "benchmark-loop-dry-run-report"
    run_root = runs_dir / run_id
    report_path = tmp_path / "p0-governance-dry-run-report.json"

    run_benchmark_improvement_loop(
        BenchmarkImprovementLoopConfig(
            benchmark_path=ROOT / "knowledge" / "benchmarks" / "hxy-brain-benchmark-v1.json",
            report_path=output_path,
            runs_dir=runs_dir,
            run_id=run_id,
            max_iterations=1,
        )
    )

    safe_next_result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "run-hxy-p0-governance-safe-next.py"),
            "--run-dir",
            str(run_root),
            "--benchmark",
            str(ROOT / "knowledge" / "benchmarks" / "hxy-brain-benchmark-v1.json"),
            "--report",
            str(output_path),
            "--max-steps",
            "8",
        ],
        check=False,
        text=True,
        capture_output=True,
    )
    assert safe_next_result.returncode == 0, safe_next_result.stderr

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "report-hxy-p0-governance-dry-run.py"),
            "--run-dir",
            str(run_root),
            "--run-id",
            run_id,
            "--benchmark",
            str(ROOT / "knowledge" / "benchmarks" / "hxy-brain-benchmark-v1.json"),
            "--report",
            str(output_path),
            "--output",
            str(report_path),
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    stdout = json.loads(result.stdout)
    written = json.loads(report_path.read_text(encoding="utf-8"))
    assert stdout == written
    assert stdout["version"] == "hxy-p0-governance-dry-run-report.v1"
    assert stdout["run_id"] == run_id
    assert stdout["safe_next"]["stopped_reason"] == "human_decision_required"
    assert stdout["safe_next"]["would_execute_count"] == 0
    assert stdout["api_payloads"]["governance_status"]["current_step"] == "blocked_at_empty_manual_decisions"
    assert stdout["api_payloads"]["reviewer_todo"]["version"] == "hxy-p0-reviewer-todo.v1"
    assert stdout["api_payloads"]["notification"]["version"] == "hxy-p0-governance-notification.v1"
    assert stdout["api_payloads"]["decision_preview_template"]["preview_only"] is True
    assert stdout["write_to_database"] is False
    assert stdout["publish_allowed"] is False
    assert stdout["official_use_allowed"] is False
    decisions_before = json.loads((run_root / "p0-review-decisions.json").read_text(encoding="utf-8"))
    assert {item["action"] for item in decisions_before["items"]} == {"pending"}
    assert not (run_root / "p0-approved-card-publication-dry-run.json").exists()
    assert not (run_root / "published-answer-cards.reviewed.json").exists()


def test_run_hxy_loop_cli_executes_benchmark_improvement_loop(tmp_path: Path):
    benchmark_path = tmp_path / "benchmark.json"
    output_path = tmp_path / "benchmark-report.json"
    runs_dir = tmp_path / "runs"
    benchmark_path.write_text(
        json.dumps(
            {
                "version": "hxy-brain-benchmark.v1",
                "cases": [
                    {
                        "case_id": "case-fail",
                        "question": "泡脚能治疗失眠吗？",
                        "domain": "compliance",
                        "expected_capabilities": ["cite_evidence"],
                        "risk_checks": ["no_medical_claim", "must_cite_evidence"],
                        "success_criteria": ["states_insufficient_if_unapproved"],
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "run-hxy-loop.py"),
            "benchmark_improvement",
            "--benchmark",
            str(benchmark_path),
            "--report",
            str(output_path),
            "--run-id",
            "benchmark-loop-cli",
            "--runs-dir",
            str(runs_dir),
            "--max-iterations",
            "1",
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    body = json.loads(result.stdout)
    assert body["version"] == "hxy-loop-runner-cli.v1"
    assert body["loop_name"] == "benchmark_improvement"
    assert body["state_path"].endswith("loop-state.json")
