from __future__ import annotations

import json
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any


RISK_TERMS = [
    "治疗",
    "治愈",
    "根治",
    "排毒",
    "祛病",
    "改善疾病",
    "疗效保证",
    "一次见效",
    "包好",
    "医用",
    "中医诊疗",
    "康复治疗",
]
CATEGORY_TERMS = ["泡脚", "按摩", "足疗", "草本泡脚", "肩颈"]
SCENARIO_TERMS = ["下班", "脚沉", "肩颈紧", "久坐", "站了一天", "腿酸", "睡前", "周末", "家门口"]
ACTION_TERMS = ["泡一泡", "按一按", "泡脚", "按摩", "进店", "预约", "体验"]
TRUST_TERMS = ["草本现煮", "草本真现煮", "明码实价", "不强推", "不强推办卡", "干净", "技师", "真功夫"]
HXY_TERMS = ["荷小悦", "社区", "首店", "门店"]

SOURCE_REFS = [
    "knowledge/raw/inbox/荷小悦资料/09_知识库与参考资料/07_品牌与营销/荷小悦品牌表达检查表.md",
    "knowledge/raw/inbox/荷小悦资料/09_知识库与参考资料/07_品牌与营销/荷小悦首店增长实验与复盘模板.md",
    "knowledge/raw/inbox/荷小悦资料/09_知识库与参考资料/07_品牌与营销/荷小悦场景营销Brief模板.md",
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _stable_id(*parts: str) -> str:
    return "hxy-brand-review:" + sha256("\n".join(parts).encode("utf-8")).hexdigest()[:16]


def _contains_any(text: str, terms: list[str]) -> bool:
    return any(term in text for term in terms)


def _criterion(name: str, max_score: int, passed: bool, reason: str) -> dict[str, Any]:
    return {
        "criterion": name,
        "score": max_score if passed else 0,
        "max_score": max_score,
        "passed": passed,
        "reason": reason,
    }


def _risk_flags(text: str) -> list[str]:
    flags: list[str] = []
    if _contains_any(text, RISK_TERMS):
        flags.append("overclaim_risk")
    return flags


def _status_for(score: int, risk_flags: list[str]) -> str:
    if risk_flags:
        return "reject_for_first_store_use"
    if score >= 85:
        return "usable_draft_requires_review"
    if score >= 70:
        return "revise_before_use"
    return "reject_for_first_store_use"


def _reviewer_role(artifact_type: str, risk_flags: list[str]) -> str:
    if risk_flags:
        return "operations_or_compliance_owner"
    if artifact_type in {"storefront", "design_company_output"}:
        return "founder_or_operations_owner"
    if artifact_type in {"staff_script", "first_order_menu"}:
        return "operations_owner"
    return "brand_or_operations_owner"


def _rewrite_direction(text: str, risk_flags: list[str]) -> list[str]:
    directions: list[str] = []
    if risk_flags:
        directions.append("删除治疗、治愈、一次见效等医疗化或保证效果表达。")
        directions.append("改成体验型表达：放松、舒服、身上松一点、泡一泡按一按。")
    if not _contains_any(text, CATEGORY_TERMS):
        directions.append("补明确品类词，例如泡脚按摩或草本泡脚按摩。")
    if not _contains_any(text, TRUST_TERMS):
        directions.append("补可信证据，例如草本真现煮、明码实价、不强推办卡。")
    if not directions:
        directions.append("进入人工复核，确认是否适用于首店门头、物料或员工话术。")
    return directions


def _recommended_version(text: str, artifact_type: str, risk_flags: list[str]) -> str:
    if risk_flags:
        return "下班累了，来荷小悦泡一泡按一按，身上松一点。"
    if artifact_type == "storefront" and "荷小悦" in text:
        return "荷小悦 草本泡脚按摩\n草本真现煮，按出真功夫"
    return text.strip()


def _score_text(text: str) -> tuple[int, list[dict[str, Any]]]:
    compact = " ".join(text.split())
    criteria = [
        _criterion("category_clarity", 15, _contains_any(text, CATEGORY_TERMS), "首店表达必须让用户知道是泡脚/按摩/足疗。"),
        _criterion("scenario_concreteness", 10, _contains_any(text, SCENARIO_TERMS), "优先使用下班、脚沉、肩颈紧、家门口等具体场景。"),
        _criterion("action_clarity", 10, _contains_any(text, ACTION_TERMS), "表达中要有泡一泡、按一按、预约、进店等动作。"),
        _criterion("trust_evidence", 15, _contains_any(text, TRUST_TERMS), "草本真现煮、明码实价、不强推等证据能降低首店信任成本。"),
        _criterion("staff_explainability", 10, len(compact) <= 60 and bool(compact), "员工要能在30秒内讲清。"),
        _criterion("customer_repeatability", 10, len(compact) <= 40 or "，" in text or "\n" in text, "社区用户需要能复述，不像策划案。"),
        _criterion("first_store_operating_fit", 10, _contains_any(text, HXY_TERMS) or _contains_any(text, CATEGORY_TERMS), "首店表达要能落到门店经营。"),
        _criterion("compliance_safety", 15, not _contains_any(text, RISK_TERMS), "不得出现医疗化、绝对化或保证效果表达。"),
        _criterion("copyability", 5, not _contains_any(text, ["第一品牌", "开创者", "唯一"]), "首店口径要能复制到后续门店。"),
    ]
    return sum(int(item["score"]) for item in criteria), criteria


def _design_company_output_review(artifact_type: str, stage: str, text: str) -> dict[str, Any]:
    return {
        "version": "hxy-brand-decision-review.v1",
        "review_id": _stable_id(artifact_type, stage, text),
        "artifact_type": artifact_type,
        "stage": stage,
        "status": "requires_design_acceptance_review",
        "score": 0,
        "criteria": [],
        "risk_flags": _risk_flags(text),
        "matched_rules": ["vi_si_boundary", "first_store_operating_acceptance"],
        "source_refs": SOURCE_REFS,
        "reject_reasons": [],
        "rewrite_direction": [
            "不要在 HXYOS 内评价视觉美术优劣，先等待设计公司提供 VI/SI 标准资料。",
            "将设计成果转成首店运营验收清单：可读性、品类清晰、物料摆放、员工执行、合规风险、复制性。",
        ],
        "recommended_version": "",
        "reviewer_role": "founder_or_operations_owner",
        "boundary": [
            "design_company_owns_visual_design",
            "hxyos_reviews_operating_fit",
            "candidate_design_output_requires_human_review",
        ],
        "official_use_allowed": False,
        "requires_human_review": True,
        "authority_rule": "brand_decision_outputs_are_reviews_not_official_brand_standards",
        "reviewed_at": _utc_now(),
    }


def review_brand_artifact(payload: dict[str, Any]) -> dict[str, Any]:
    artifact_type = str(payload.get("artifact_type") or "opening_content").strip() or "opening_content"
    stage = str(payload.get("stage") or "first_store_opening").strip() or "first_store_opening"
    text = str(payload.get("text") or "").strip()
    if artifact_type == "design_company_output":
        return _design_company_output_review(artifact_type, stage, text)

    risk_flags = _risk_flags(text)
    raw_score, criteria = _score_text(text)
    score = min(raw_score, 45) if risk_flags else raw_score
    status = _status_for(score, risk_flags)
    reviewed_at = _utc_now()

    return {
        "version": "hxy-brand-decision-review.v1",
        "review_id": _stable_id(artifact_type, stage, text),
        "artifact_type": artifact_type,
        "stage": stage,
        "status": status,
        "score": score,
        "criteria": criteria,
        "risk_flags": risk_flags,
        "matched_rules": [
            "first_store_category_clarity",
            "first_store_trust_evidence",
            "first_store_compliance_safety",
        ],
        "source_refs": SOURCE_REFS,
        "reject_reasons": _rewrite_direction(text, risk_flags) if status == "reject_for_first_store_use" else [],
        "rewrite_direction": _rewrite_direction(text, risk_flags),
        "recommended_version": _recommended_version(text, artifact_type, risk_flags),
        "reviewer_role": _reviewer_role(artifact_type, risk_flags),
        "official_use_allowed": False,
        "requires_human_review": True,
        "authority_rule": "brand_decision_outputs_are_reviews_not_official_brand_standards",
        "reviewed_at": reviewed_at,
    }


def write_brand_review_record(review: dict[str, Any], *, reviews_dir: Path) -> Path:
    review_id = str(review.get("review_id") or _stable_id(str(review)))
    safe_name = review_id.replace(":", "-").replace("/", "-")
    path = Path(reviews_dir) / f"{safe_name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(review, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
