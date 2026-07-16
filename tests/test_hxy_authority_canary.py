from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUITE = ROOT / "knowledge" / "benchmarks" / "hxyos-core-10.json"


class _FakeModelRouter:
    def __init__(self, *, failed_task: str = "") -> None:
        self.failed_task = failed_task

    def generate(self, task_type: str, **_kwargs: object) -> dict[str, object]:
        models = {
            "frontdoor_classification": "qwen-flash",
            "answer_synthesis": "qwen-plus-latest",
            "policy_review": "qwen3.7-max",
        }
        failed = task_type == self.failed_task
        return {
            "used_model": not failed,
            "reason": "provider_error" if failed else "ok",
            "route": {
                "selected_model": models[task_type],
                "execution_mode": "enabled",
            },
            "provider_response_id": None if failed else f"provider-{task_type}",
            "usage": {"prompt_tokens": 10, "completion_tokens": 3},
            "output": "PRIVATE MODEL OUTPUT MUST NOT ENTER REPORT",
        }


def test_model_canary_checks_exact_routes_without_persisting_output() -> None:
    from hxy_knowledge.authority_canary import run_model_route_canary

    report = run_model_route_canary(_FakeModelRouter())

    assert report["version"] == "hxy-model-route-canary-report.v1"
    assert report["target_met"] is True
    assert {item["selected_model"] for item in report["checks"]} == {
        "qwen-flash",
        "qwen-plus-latest",
        "qwen3.7-max",
    }
    assert "PRIVATE MODEL OUTPUT" not in str(report)
    assert all("output" not in item for item in report["checks"])


def test_model_canary_fails_when_one_route_does_not_execute() -> None:
    from hxy_knowledge.authority_canary import run_model_route_canary

    report = run_model_route_canary(_FakeModelRouter(failed_task="policy_review"))

    assert report["target_met"] is False
    failed = next(item for item in report["checks"] if item["task_type"] == "policy_review")
    assert failed["status"] == "failed"


def test_core_10_capture_keeps_only_bounded_scoring_metadata() -> None:
    from hxy_knowledge.authority_canary import capture_core_10_runs
    from hxy_knowledge.brain_benchmark import load_benchmark

    benchmark = load_benchmark(SUITE)

    def answer_client(case: dict[str, object]) -> dict[str, object]:
        expected = case["expected"]
        assert isinstance(expected, dict)
        combination = expected["authority_combinations"][0]
        assert isinstance(combination, dict)
        response: dict[str, object] = {
            "intent": expected.get("intent"),
            "task_intent": expected.get("task_intent"),
            "answer_mode": combination["answer_mode"],
            "authority_source": combination["authority_source"],
            "from_answer_card": combination["authority_provenance"] == "approved_answer_card",
            "from_brand_constitution": combination["authority_provenance"] == "brand_constitution",
            "needs_review": expected.get("needs_review", False),
            "citations": [{"source_id": "private-source-id", "title": "PRIVATE SOURCE TITLE"}],
            "actions": [{"type": item} for item in expected.get("action_types", [])],
            "answer": "不能把泡脚说成治疗，也不能替代医疗。PRIVATE ANSWER BODY",
            "model_generation": {
                "usage": {"prompt_tokens": 20, "completion_tokens": 10},
            },
        }
        return response

    capture = capture_core_10_runs(benchmark, answer_client)

    assert capture["version"] == "hxyos-core-10-runs.v1"
    assert set(capture["runs"]) == {case["case_id"] for case in benchmark["cases"]}
    assert "PRIVATE ANSWER BODY" not in str(capture)
    assert "PRIVATE SOURCE TITLE" not in str(capture)
    assert "private-source-id" not in str(capture)
    assert capture["runs"]["core-brand-identity"]["authority_provenance"] == "brand_constitution"
    assert capture["runs"]["core-compliance-risk"]["risk_intercepted"] is True
    assert capture["runs"]["core-compliance-risk"]["unsafe_output"] is False


def test_core_10_capture_marks_unsafe_medical_output() -> None:
    from hxy_knowledge.authority_canary import capture_core_10_runs
    from hxy_knowledge.brain_benchmark import load_benchmark

    benchmark = load_benchmark(SUITE)

    def answer_client(case: dict[str, object]) -> dict[str, object]:
        expected = case["expected"]
        assert isinstance(expected, dict)
        combination = expected["authority_combinations"][0]
        assert isinstance(combination, dict)
        return {
            "intent": expected.get("intent"),
            "task_intent": expected.get("task_intent"),
            "answer_mode": combination["answer_mode"],
            "authority_source": combination["authority_source"],
            "from_answer_card": combination["authority_provenance"] == "approved_answer_card",
            "from_brand_constitution": combination["authority_provenance"] == "brand_constitution",
            "needs_review": expected.get("needs_review", False),
            "citations": [{"source_id": "source"}],
            "actions": [{"type": item} for item in expected.get("action_types", [])],
            "answer": "泡脚可以治疗失眠。" if case["case_id"] == "core-compliance-risk" else "工作回答。",
            "model_generation": {"usage": {"input_tokens": 20, "output_tokens": 10}},
        }

    capture = capture_core_10_runs(benchmark, answer_client)
    risk_run = capture["runs"]["core-compliance-risk"]

    assert risk_run["risk_intercepted"] is False
    assert risk_run["unsafe_output"] is True
