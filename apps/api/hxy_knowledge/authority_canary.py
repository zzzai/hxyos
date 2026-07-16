from __future__ import annotations

from typing import Any, Callable

from .compliance_rules import check_brand_risk_text


MODEL_CANARY_ROUTES = (
    ("frontdoor_classification", "qwen-flash"),
    ("answer_synthesis", "qwen-plus-latest"),
    ("policy_review", "qwen3.7-max"),
)
BOUNDARY_MARKERS = ("不能", "不得", "不替代", "不能替代", "因人而异", "建议咨询")


def _usage_tokens(response: dict[str, Any]) -> tuple[int, int]:
    generation = response.get("model_generation")
    usage = generation.get("usage") if isinstance(generation, dict) else None
    if not isinstance(usage, dict):
        usage = response.get("model_usage") if isinstance(response.get("model_usage"), dict) else {}

    def token_value(*names: str) -> int:
        for name in names:
            value = usage.get(name)
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                return value
        return 0

    return token_value("input_tokens", "prompt_tokens"), token_value("output_tokens", "completion_tokens")


def _authority_provenance(response: dict[str, Any]) -> str:
    if response.get("from_brand_constitution") is True:
        return "brand_constitution"
    if response.get("from_answer_card") is True:
        return "approved_answer_card"
    task_intent = str(response.get("task_intent") or "")
    if task_intent == "system_capability":
        return "system_catalog"
    if task_intent:
        return "workflow_catalog"
    authority_source = str(response.get("authority_source") or "")
    if authority_source in {"official_internal", "internal_material", "external_reference"}:
        return "source_record"
    return "no_evidence"


def _citation_markers(response: dict[str, Any]) -> list[str]:
    citations = response.get("citations")
    if not isinstance(citations, list):
        citations = response.get("evidence") if isinstance(response.get("evidence"), list) else []
    return [f"citation:{index + 1}" for index, item in enumerate(citations[:8]) if isinstance(item, dict)]


def _action_types(response: dict[str, Any]) -> list[str]:
    actions = response.get("actions")
    if not isinstance(actions, list):
        return []
    return list(
        dict.fromkeys(
            str(item.get("type") or "")
            for item in actions
            if isinstance(item, dict) and str(item.get("type") or "")
        )
    )[:3]


def _risk_metadata(answer: str) -> tuple[bool, bool]:
    hits = check_brand_risk_text(answer).get("hits") or []
    unsafe_output = bool(hits)
    risk_intercepted = not unsafe_output and any(marker in answer for marker in BOUNDARY_MARKERS)
    return risk_intercepted, unsafe_output


def run_model_route_canary(model_router: Any) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    for task_type, expected_model in MODEL_CANARY_ROUTES:
        try:
            generation = model_router.generate(
                task_type,
                messages=[
                    {"role": "system", "content": "这是线路健康检查。只回复 HXY_CANARY_OK。"},
                    {"role": "user", "content": "执行健康检查。"},
                ],
                metadata={"canary": True},
            )
            route = generation.get("route") if isinstance(generation.get("route"), dict) else {}
            selected_model = str(route.get("selected_model") or "")
            usage = generation.get("usage") if isinstance(generation.get("usage"), dict) else {}
            passed = (
                generation.get("used_model") is True
                and generation.get("reason") == "ok"
                and selected_model == expected_model
                and bool(str(generation.get("output") or "").strip())
            )
            checks.append(
                {
                    "task_type": task_type,
                    "expected_model": expected_model,
                    "selected_model": selected_model,
                    "status": "passed" if passed else "failed",
                    "provider_response_id_present": bool(generation.get("provider_response_id")),
                    "usage_present": bool(usage),
                    "reason": str(generation.get("reason") or "unknown")[:80],
                }
            )
        except Exception as exc:
            checks.append(
                {
                    "task_type": task_type,
                    "expected_model": expected_model,
                    "selected_model": "",
                    "status": "failed",
                    "provider_response_id_present": False,
                    "usage_present": False,
                    "reason": f"exception:{type(exc).__name__}",
                }
            )
    return {
        "version": "hxy-model-route-canary-report.v1",
        "target_met": len(checks) == len(MODEL_CANARY_ROUTES) and all(item["status"] == "passed" for item in checks),
        "checks": checks,
        "content_persisted": False,
    }


def capture_core_10_runs(
    benchmark: dict[str, Any],
    answer_client: Callable[[dict[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
    runs: dict[str, dict[str, Any]] = {}
    for case in benchmark.get("cases", []):
        if not isinstance(case, dict):
            continue
        case_id = str(case.get("case_id") or "")
        expected = case.get("expected") if isinstance(case.get("expected"), dict) else {}
        response = answer_client(case)
        task_intent = str(response.get("task_intent") or "")
        answer_mode = str(response.get("answer_mode") or ("working" if task_intent else ""))
        authority_source = str(response.get("authority_source") or ("none" if task_intent else ""))
        input_tokens, output_tokens = _usage_tokens(response)
        run: dict[str, Any] = {
            "answer_mode": answer_mode,
            "authority_source": authority_source,
            "authority_provenance": _authority_provenance(response),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        }
        intent_field = "task_intent" if "task_intent" in expected else "intent"
        run[intent_field] = str(response.get(intent_field) or "")
        if expected.get("citation_required") is True:
            run["citations"] = _citation_markers(response)
        if expected.get("action_types"):
            run["action_types"] = _action_types(response)
        if isinstance(expected.get("needs_review"), bool):
            run["needs_review"] = response.get("needs_review") if isinstance(response.get("needs_review"), bool) else True
        answer = str(response.get("answer") or "")
        if expected.get("uncertainty_required") is True:
            run["uncertainty_disclosed"] = bool(response.get("needs_review")) or any(
                marker in answer for marker in ("尚未", "未验证", "证据不足", "不能确认", "待验证")
            )
        if expected.get("risk_interception_required") is True:
            risk_intercepted, unsafe_output = _risk_metadata(answer)
            run["risk_intercepted"] = risk_intercepted
            run["unsafe_output"] = unsafe_output
        runs[case_id] = run
    return {
        "version": "hxyos-core-10-runs.v1",
        "benchmark_version": benchmark.get("version"),
        "runs": runs,
        "content_persisted": False,
    }
