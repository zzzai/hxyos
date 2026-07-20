from __future__ import annotations

import json
import re
from typing import Any, Callable, Literal


AnswerRoute = Literal[
    "general",
    "hxy_official",
    "mixed",
    "service_scenario",
    "high_risk",
]
ModelClassifier = Callable[..., str]

_VALID_ROUTES = frozenset(
    {"general", "hxy_official", "mixed", "service_scenario", "high_risk"}
)

_HXY_MARKERS = (
    "荷小悦",
    "hxyos",
    "清泡调补养",
    "品牌宪法",
    "本店标准",
    "门店标准",
    "公司规定",
    "总部规定",
    "你能做什么",
    "我能做什么",
    "怎么上传资料",
    "新对话",
    "历史对话",
    "刚上传",
    "上传的资料",
    "这份资料",
    "组织资料",
    "本店",
    "我们门店",
)
_MIXED_MARKERS = (
    "结合",
    "对比",
    "比较",
    "分析",
    "行业",
    "通常",
    "一般",
    "怎样提高",
    "如何提升",
)
_SERVICE_MARKERS = (
    "顾客说",
    "顾客问",
    "客人说",
    "客人问",
    "我该怎么说",
    "怎么回应",
    "怎么回复",
    "怎么接待",
    "接待顾客",
    "服务话术",
    "客诉",
    "不满意",
    "不舒服",
)
_DIAGNOSIS_MARKERS = (
    "诊断",
    "是不是颈椎病",
    "是不是腰椎病",
    "是不是肩周炎",
    "是不是疾病",
)
_GUARANTEE_MARKERS = (
    "包治",
    "根治",
    "治愈",
    "治好",
    "一定有效",
    "保证疗效",
    "能治疗",
    "保证回本",
    "稳赚",
)
_SENSITIVE_ACTION_MARKERS = (
    "导出手机号",
    "发送手机号",
    "分享身份证",
    "上传病历",
    "公开顾客信息",
)
_CLEAR_GENERAL_MARKERS = (
    "解释",
    "翻译",
    "数学",
    "编程",
    "历史",
    "天气",
    "熵增",
)


def _contains_any(text: str, markers: tuple[str, ...]) -> bool:
    return any(marker in text for marker in markers)


def classify_intake_route(
    text: str,
    *,
    model_classifier: ModelClassifier | None = None,
    **context: Any,
) -> AnswerRoute:
    normalized = " ".join((text or "").strip().lower().split())

    if (
        _contains_any(normalized, _DIAGNOSIS_MARKERS)
        or _contains_any(normalized, _GUARANTEE_MARKERS)
        or _contains_any(normalized, _SENSITIVE_ACTION_MARKERS)
    ):
        return "high_risk"

    if _contains_any(normalized, _SERVICE_MARKERS):
        return "service_scenario"

    has_hxy_scope = _contains_any(normalized, _HXY_MARKERS)
    if has_hxy_scope and _contains_any(normalized, _MIXED_MARKERS):
        return "mixed"
    if has_hxy_scope:
        return "hxy_official"

    if _contains_any(normalized, _CLEAR_GENERAL_MARKERS):
        return "general"

    if model_classifier is not None:
        candidate = str(model_classifier(normalized, **context) or "").strip()
        if candidate in _VALID_ROUTES:
            return candidate  # type: ignore[return-value]

    return "general"


def _json_object(raw: str) -> dict[str, Any] | None:
    text = raw.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(\{.*\})\s*```", text, flags=re.DOTALL)
    if fenced:
        text = fenced.group(1)
    try:
        payload = json.loads(text)
    except (TypeError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def build_model_assisted_route_classifier(model_router: Any) -> Callable[..., AnswerRoute]:
    def classify_with_model(text: str, **context: Any) -> str:
        assignment = context.get("assignment")
        role = str(getattr(assignment, "role", "team"))
        generation = model_router.generate(
            "classification",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "你只判断 HXYOS 输入路由，不回答问题。只返回 JSON："
                        '{"route":"general|hxy_official|mixed|service_scenario|high_risk",'
                        '"confidence":0到1}。涉及诊断、疗效保证、收益保证或敏感信息时必须 high_risk；'
                        "涉及荷小悦事实时不能选 general。"
                    ),
                },
                {"role": "user", "content": text[:4000]},
            ],
            metadata={"role": role, "policy": "hxy-unified-intake.v1"},
        )
        if not generation.get("used_model"):
            return "general"
        payload = _json_object(str(generation.get("output") or ""))
        if payload is None:
            return "general"
        route = str(payload.get("route") or "")
        try:
            confidence = float(payload.get("confidence") or 0)
        except (TypeError, ValueError):
            return "general"
        if route not in _VALID_ROUTES or confidence < 0.75:
            return "general"
        return route

    def classify(text: str, **context: Any) -> AnswerRoute:
        return classify_intake_route(
            text,
            model_classifier=classify_with_model,
            **context,
        )

    return classify


def generate_general_answer(question: str, *, model_router: Any) -> dict[str, Any]:
    generation = model_router.generate(
        "reasoning",
        messages=[
            {
                "role": "system",
                "content": (
                    "你是 HXYOS 中的通用工作助手。直接、简洁、如实回答通用问题。"
                    "不要声称这是荷小悦正式口径，不要虚构公司事实；涉及医疗、收益、"
                    "价格政策或个人敏感信息时，只说明安全边界并建议进入有权限的流程。"
                ),
            },
            {"role": "user", "content": question[:4000]},
        ],
        metadata={"policy": "hxy-general-answer.v1"},
    )
    output = str(generation.get("output") or "").strip()
    used_model = bool(generation.get("used_model") and output)
    return {
        "answer": output[:4000] if used_model else "通用模型暂时不可用，请稍后重试。",
        "answer_status": "AI 草稿",
        "confidence": "medium" if used_model else "low",
        "needs_review": not used_model,
        "sources": [],
        "evidence": [],
        "next_actions": [],
        "model_route": generation.get("route") or {},
        "model_usage": generation.get("usage") or {},
        "intent": "general",
    }
