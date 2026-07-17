from pathlib import Path

from hxy_knowledge.enterprise_governance import build_enterprise_governance_report
from hxy_knowledge.ingest_loop import run_ingest_loop
from hxy_knowledge.knowledge_compiler import compile_directory
from hxy_knowledge.memory_context import build_memory_context
from hxy_knowledge.process_memory import build_memory_promotion_draft, build_process_memory_record
from hxy_knowledge.workspace_events import create_workspace_event, list_workspace_events


def test_compiler_creates_review_artifacts_without_approval(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    wiki_dir = tmp_path / "wiki"
    raw_dir.mkdir()
    (raw_dir / "note.md").write_text(
        "ExampleCo should validate first-site positioning. Staff must not promise guaranteed results.",
        encoding="utf-8",
    )

    report = compile_directory(raw_dir, wiki_dir)

    assert report["extract_count"] == 1
    assert report["claim_count"] >= 1
    assert report["approved_count"] == 0
    assert (wiki_dir / "review-queue.json").exists()
    assert (wiki_dir / "answer-card-drafts.json").exists()


def test_ingest_loop_keeps_candidates_unpromoted_without_blocking_source_processing(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    (raw_dir / "source.md").write_text("ExampleCo reference material requires review.", encoding="utf-8")

    state = run_ingest_loop(
        raw_dir=raw_dir,
        wiki_dir=tmp_path / "wiki",
        report_path=tmp_path / "reports" / "ingest.json",
        runs_dir=tmp_path / "runs",
        run_id="sample",
        root_dir=tmp_path,
    )

    assert state["status"] == "candidate_ready"
    assert state["official_use_allowed"] is False
    assert state["requires_human_review"] is False
    assert state["promotion_review_pending"] is True


def test_process_memory_is_context_hint_not_authority() -> None:
    record = build_process_memory_record(
        "Do not turn founder preferences into official policy without review.",
        source="test",
        actor="tester",
        confidence=0.8,
    )
    promotion = build_memory_promotion_draft(record, target_domain="governance")

    assert record["official_use_allowed"] is False
    assert promotion["target_status"] == "current_candidate"
    assert promotion["requires_human_review"] is True

    context = build_memory_context(
        working_memory={"goal": "answer with governance"},
        short_term_messages=[],
        retrieved_memories=[
            {
                "id": "approved-1",
                "status": "approved",
                "source_type": "approved_answer_card",
                "semantic_relevance": 0.9,
                "importance": 0.8,
            },
            {
                "id": "process-1",
                "status": "process",
                "source_type": "process_memory",
                "semantic_relevance": 0.9,
                "importance": 0.9,
            },
        ],
    )

    assert context["formal_knowledge"][0]["id"] == "approved-1"
    assert context["process_memory_hints"][0]["context_hint_only"] is True
    assert context["authority_rule"] == "process_memory_cannot_be_authority"


def test_governance_lints_reference_used_by_approved_card() -> None:
    report = build_enterprise_governance_report(
        assets=[],
        claims=[],
        evidence=[],
        relations=[],
        answer_cards=[
            {
                "card_id": "card-1",
                "status": "approved",
                "evidence": [{"status": "reference", "title": "unreviewed note"}],
            }
        ],
    )

    issue_codes = {issue["code"] for issue in report["lint_issues"]}
    assert "reference_used_as_approved_source" in issue_codes
    assert report["release_gate"]["can_publish"] is False


def test_workspace_events_redact_sensitive_private_material(tmp_path: Path) -> None:
    store_path = tmp_path / "events.jsonl"
    event = create_workspace_event(
        {
            "topic": "fundraising note",
            "input": "valuation and token should be restricted",
            "ai_output": {"summary": "contains sensitive terms"},
        },
        store_path=store_path,
        now=lambda: "2026-01-01T00:00:00Z",
    )

    assert event["visibility"] == "restricted_role"

    listed = list_workspace_events(store_path)
    assert listed["count"] == 1
    assert listed["items"][0]["input"] == "[redacted]"
