from __future__ import annotations

from typing import Any

from .public_safety import redact_internal_paths


LEARNING_LIMITATIONS = [
    "AI 只评估沟通表达、服务意识和风险边界。",
    "推拿或按摩手法必须由有资质的培训人员现场评估。",
]

_ACTIONS = {
    "service-boundary-v1": {
        "id": "service-boundary-v1",
        "title": "回应顾客不适",
        "purpose": "练习先回应感受，再守住非医疗服务边界。",
        "estimated_minutes": 3,
        "scenario": {
            "customer_message": "顾客说：做完以后还是不舒服，我该怎么办？",
        },
        "response_modes": ["text", "voice"],
    },
    "service-welcome-v1": {
        "id": "service-welcome-v1",
        "title": "第一次到店接待",
        "purpose": "练习主动了解需求，让顾客清楚接下来的服务安排。",
        "estimated_minutes": 3,
        "scenario": {
            "customer_message": "顾客说：我第一次来，不知道该选什么。",
        },
        "response_modes": ["text", "voice"],
    },
}


def learning_action(action_id: str) -> dict[str, Any] | None:
    action = _ACTIONS.get(action_id)
    return dict(action) if action is not None else None


def next_learning_action(sessions: list[dict[str, Any]]) -> dict[str, Any]:
    if not sessions or bool(sessions[0].get("needs_retrain", True)):
        return dict(_ACTIONS["service-boundary-v1"])
    return dict(_ACTIONS["service-welcome-v1"])


def private_progress(sessions: list[dict[str, Any]]) -> dict[str, Any]:
    mastered: list[str] = []
    needs_attention: list[str] = []
    if any(not bool(item.get("needs_retrain", True)) for item in sessions):
        mastered.append("服务沟通与风险边界")
    for session in sessions:
        if not bool(session.get("needs_retrain", True)):
            continue
        for item in session.get("correction_points") or []:
            point = redact_internal_paths(str(item).strip())[:120]
            if point and point not in needs_attention:
                needs_attention.append(point)
    return {
        "visibility": "private",
        "attempts": len(sessions),
        "mastered": mastered[:3],
        "practicing": [
            "服务边界表达"
            if not sessions or bool(sessions[0].get("needs_retrain", True))
            else "首次到店接待"
        ],
        "needs_attention": needs_attention[:3],
    }


def safe_attempt(result: dict[str, Any], session_id: str) -> dict[str, Any]:
    try:
        score = min(100, max(0, int(result.get("score") or 0)))
    except (TypeError, ValueError):
        score = 0
    level = str(result.get("level") or "")
    if level not in {"excellent", "pass", "retrain"}:
        level = "retrain"
    correction_points = [
        redact_internal_paths(str(item).strip())[:500]
        for item in result.get("correction_points") or []
        if str(item).strip()
    ][:8]
    return {
        "id": session_id,
        "score": score,
        "level": level,
        "needs_retrain": bool(result.get("needs_retrain", True)),
        "standard_script": redact_internal_paths(
            str(result.get("standard_script") or "").strip()
        )[:4000],
        "correction_points": correction_points,
        "physical_technique": "not_assessed",
    }
