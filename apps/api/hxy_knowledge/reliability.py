from __future__ import annotations

from typing import Any

try:
    from hxy_knowledge.answer_engine import PRIMARY_CLAIM_DOMAINS, has_metadata_noise
except Exception:  # pragma: no cover - allows direct file loading in tests
    PRIMARY_CLAIM_DOMAINS = {
        "brand_positioning": {"brand", "product", "store_model"},
        "product_system": {"product", "brand", "store_model", "operations"},
        "operations": {"operations", "product", "store_model"},
        "finance": {"finance", "store_model", "franchise"},
        "franchise": {"franchise", "finance", "store_model", "brand"},
        "store_model": {"store_model"},
    }

    def has_metadata_noise(text: str) -> bool:
        lowered = (text or "").lower()
        return any(token in lowered for token in ["source_path", "chunk_id", "asset_id", "knowledge/raw", "/root/hxy"])


OVERCLAIM_TERMS = ["治疗", "治愈", "保证", "稳赚", "一定回本", "绝对", "药到病除", "排毒治病"]
NEGATION_MARKERS = ["不", "不要", "不能", "禁止", "避免", "禁用", "不得", "不要承诺", "不能承诺"]
AUTHORITY_SOURCES = {
    "official_internal",
    "internal_material",
    "external_reference",
}
REFERENCE_STATUSES = {
    "external",
    "raw",
    "reference",
    "ai_structured",
    "current_candidate",
    "draft",
    "needs_review",
    "disputed",
    "superseded",
}
REFERENCE_STAGES = {"reference", "preparation", "draft", "pilot", "ai_structured", "working_context"}


def is_process_memory_evidence(item: dict[str, Any]) -> bool:
    domain = str(item.get("domain") or "").lower()
    status = str(item.get("status") or "").lower()
    source_type = str(item.get("source_type") or "").lower()
    return (
        domain == "process_memory"
        or status == "process"
        or source_type == "process_memory"
    )


def evidence_authority_source(item: dict[str, Any]) -> str:
    if is_process_memory_evidence(item):
        return "none"
    domain = str(item.get("domain") or "").lower()
    status = str(item.get("status") or "").lower()
    stage = str(item.get("stage") or "").lower()
    source_type = str(item.get("source_type") or "").lower()
    origin = str(item.get("origin") or "").lower()
    if (
        domain in {"external", "reference"}
        or source_type in {"external", "external_article", "reference", "reference_material", "external_reference"}
        or origin in {"external", "reference"}
        or status in REFERENCE_STATUSES
        or stage in REFERENCE_STAGES
    ):
        return "external_reference"
    if domain == "approved_answer_card" or status == "approved" and stage == "approved_answer_card":
        return "approved_answer_card"
    explicit = str(item.get("authority_source") or item.get("source_authority") or "").lower()
    if explicit in AUTHORITY_SOURCES:
        return explicit
    return "external_reference"


def _evidence_source_identity(item: dict[str, Any]) -> str:
    for key in ["source_id", "asset_id", "card_id", "document_id", "title"]:
        value = str(item.get(key) or "").strip()
        if value:
            return f"{key}:{value}"
    return ""


def has_corroborated_internal_evidence(evidence: list[dict[str, Any]]) -> bool:
    source_ids = {
        source_id
        for item in evidence
        if evidence_authority_source(item) in {"official_internal", "internal_material"}
        if (source_id := _evidence_source_identity(item))
    }
    return len(source_ids) >= 2


def classify_answer_authority(
    *,
    evidence: list[dict[str, Any]],
    from_answer_card: bool,
    requires_review: bool,
) -> dict[str, Any]:
    citations = [item for item in evidence if not is_process_memory_evidence(item)]
    process_memory = [
        {
            **({"memory_id": item["memory_id"]} if item.get("memory_id") else {}),
            **({"title": item["title"]} if item.get("title") else {}),
            "context_hint_only": True,
        }
        for item in evidence
        if is_process_memory_evidence(item)
    ]
    evidence_authorities = {evidence_authority_source(item) for item in citations}

    if from_answer_card:
        answer_mode = "formal"
        authority_source = "approved_answer_card"
        usage_boundary = "review_required" if requires_review else "team_standard"
    elif "official_internal" in evidence_authorities:
        answer_mode = "working"
        authority_source = "official_internal"
        usage_boundary = "review_required" if requires_review else "internal_working"
    elif "internal_material" in evidence_authorities:
        answer_mode = "working"
        authority_source = "internal_material"
        usage_boundary = "review_required" if requires_review else "internal_working"
    elif "external_reference" in evidence_authorities or "approved_answer_card" in evidence_authorities:
        answer_mode = "reference"
        authority_source = "external_reference"
        usage_boundary = "reference_only"
    else:
        answer_mode = "reference"
        authority_source = "none"
        usage_boundary = "review_required"

    return {
        "answer_mode": answer_mode,
        "authority_source": authority_source,
        "usage_boundary": usage_boundary,
        "citations": citations,
        "context_metadata": {"process_memory": process_memory},
    }


def _dimension(key: str, name: str, passed: bool, detail: str, weight: float) -> dict[str, Any]:
    return {"key": key, "name": name, "passed": passed, "detail": detail, "weight": weight}


def score_answer_quality(
    *,
    question: str,
    intent: str,
    scenario: str,
    answer: str,
    evidence: list[dict[str, Any]],
    confidence: str,
    needs_review: bool,
    from_answer_card: bool = False,
) -> dict[str, Any]:
    allowed_domains = PRIMARY_CLAIM_DOMAINS.get(intent) or set()
    evidence_domains = {item.get("domain") for item in evidence if item.get("domain")}
    domain_match = from_answer_card or not allowed_domains or bool(evidence_domains & allowed_domains)
    usable_conclusion = bool(answer.strip()) and "当前知识库没有可直接用于回答" not in answer and "无法可靠回答" not in answer
    no_noise = not has_metadata_noise(answer)
    overclaim_hits = _overclaim_hits(answer)
    no_overclaim = not overclaim_hits
    usable_evidence = [item for item in evidence if not is_process_memory_evidence(item)]
    evidence_ready = from_answer_card or bool(usable_evidence)
    stable_enough = from_answer_card or (
        has_corroborated_internal_evidence(usable_evidence) and confidence == "high" and not needs_review
    )

    dimensions = [
        _dimension(
            "domain_match",
            "命中正确业务域",
            domain_match,
            "证据或答案卡与问题意图匹配。" if domain_match else "证据域与问题意图不匹配。",
            0.22,
        ),
        _dimension(
            "usable_conclusion",
            "有可用结论",
            usable_conclusion,
            "答案可以直接被团队使用。" if usable_conclusion else "答案缺少明确可用结论。",
            0.22,
        ),
        _dimension(
            "no_metadata_noise",
            "无技术噪声",
            no_noise,
            "未暴露路径、chunk 或内部字段。" if no_noise else "答案暴露了路径、chunk 或内部字段。",
            0.18,
        ),
        _dimension(
            "no_overclaim",
            "不过度承诺",
            no_overclaim,
            "未发现违规或夸大表达。" if no_overclaim else f"包含高风险表达：{'、'.join(overclaim_hits)}。",
            0.18,
        ),
        _dimension(
            "evidence_ready",
            "证据可追溯",
            evidence_ready,
            "有答案卡或证据可追溯。" if evidence_ready else "没有可追溯证据。",
            0.1,
        ),
        _dimension(
            "stable_enough",
            "稳定性足够",
            stable_enough,
            "可作为稳定口径使用。" if stable_enough else "仍需要复核或补资料。",
            0.1,
        ),
    ]
    score = round(sum(item["weight"] for item in dimensions if item["passed"]), 2)
    if score >= 0.9:
        level = "high"
    elif score >= 0.7:
        level = "medium"
    else:
        level = "low"
    should_create_answer_card = not from_answer_card and usable_conclusion and (needs_review or confidence != "high")
    return {
        "version": "hxy-answer-quality.v1",
        "question": question,
        "intent": intent,
        "scenario": scenario,
        "score": score,
        "level": level,
        "dimensions": dimensions,
        "needs_review": needs_review or level != "high",
        "should_create_answer_card": should_create_answer_card,
    }


def insufficient_answer(question: str, reason: str = "当前证据不足") -> str:
    return (
        f"结论：当前知识库没有可直接用于回答“{question}”的干净业务结论，暂时不能可靠回答。"
        f"{reason}。请补充权威资料、适用场景或由业务负责人复核后再沉淀为答案卡。"
    )


def _overclaim_hits(answer: str) -> list[str]:
    if any(marker in answer[:80] for marker in ["不能说", "禁用表达", "避免", "不要说", "不得说"]):
        return []
    hits: list[str] = []
    for term in OVERCLAIM_TERMS:
        start = 0
        while True:
            index = answer.find(term, start)
            if index == -1:
                break
            window = answer[max(0, index - 8) : index]
            if not any(marker in window for marker in NEGATION_MARKERS):
                hits.append(term)
                break
            start = index + len(term)
    return hits
