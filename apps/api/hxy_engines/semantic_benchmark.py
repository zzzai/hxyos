from __future__ import annotations

import hashlib
import json
import random
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Mapping

from apps.api.hxy_knowledge.compliance_rules import (
    check_brand_risk_text,
    load_brand_risk_rules,
)


_ANSWER_AUTHORITIES = {"approved", "candidate", "reference", "insufficient"}
_EVIDENCE_AUTHORITIES = {
    "approved",
    "action_asset",
    "candidate",
    "reference",
    "private_reference",
    "process",
}
_POLICY_ACTIONS = {"answer", "needs_review", "deny"}
_GUARDRAIL_ACTIONS = {"send", "revise_or_review", "deny"}
_SEMANTIC_DIMENSIONS = (
    "factual_correctness",
    "role_usefulness",
    "evidence_alignment",
    "expression_fitness",
    "actionability",
)
_ROLE_ORDER = (
    "founder",
    "brand_operations",
    "store_manager",
    "store_employee",
    "knowledge_data_admin",
)
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}$")
_SHA256 = re.compile(r"^[a-f0-9]{64}$")
_PRIVATE_MARKERS = (
    "/root/",
    "/home/",
    "knowledge/raw",
    "password=",
    "api_key",
    "session_grant",
    "authorization: bearer",
)
_PRIVATE_KEYS = {
    "answer",
    "authorization",
    "content",
    "cookie",
    "credential",
    "path",
    "prompt",
    "query",
    "secret",
    "session",
    "session_grant",
}


def _bounded_text(name: str, value: str, *, maximum: int = 160) -> str:
    normalized = value.strip()
    if not normalized or len(normalized) > maximum:
        raise ValueError(f"{name} is invalid")
    return normalized


@dataclass(frozen=True)
class SemanticAnswerRun:
    case_id: str
    provider_name: str
    provider_version: str
    answer: str = field(repr=False, compare=False)
    identity_aliases: tuple[str, ...] = ()
    answer_authority: str = "insufficient"
    evidence_ids: tuple[str, ...] = ()
    evidence_authorities: tuple[str, ...] = ()
    citations: tuple[str, ...] = ()
    declared_outcomes: tuple[str, ...] = ()
    policy_action: str = "needs_review"
    guardrail_action: str = "revise_or_review"
    latency_ms: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_microunits: int = 0
    safe_trace: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("case_id", "provider_name", "provider_version"):
            object.__setattr__(
                self,
                name,
                _bounded_text(name, str(getattr(self, name))),
            )
        if not isinstance(self.answer, str) or len(self.answer) > 50_000:
            raise ValueError("answer is invalid")
        if not isinstance(self.safe_trace, Mapping):
            raise ValueError("safe_trace must be an object")
        for name in (
            "identity_aliases",
            "evidence_ids",
            "citations",
            "declared_outcomes",
        ):
            values = tuple(
                _bounded_text(name, str(item)) for item in getattr(self, name)
            )
            if len(values) != len(set(values)):
                raise ValueError(f"{name} contains duplicates")
            object.__setattr__(self, name, values)
        if self.answer_authority not in _ANSWER_AUTHORITIES:
            raise ValueError("answer_authority is invalid")
        if any(item not in _EVIDENCE_AUTHORITIES for item in self.evidence_authorities):
            raise ValueError("evidence_authority is invalid")
        if self.policy_action not in _POLICY_ACTIONS:
            raise ValueError("policy_action is invalid")
        if self.guardrail_action not in _GUARDRAIL_ACTIONS:
            raise ValueError("guardrail_action is invalid")
        for name in ("latency_ms", "input_tokens", "output_tokens", "cost_microunits"):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} is invalid")


def build_blind_item_id(
    case_id: str,
    answer_sha256: str,
    review_text_sha256: str,
    benchmark_sha256: str,
    rubric_sha256: str,
) -> str:
    return hashlib.sha256(
        "\n".join(
            (
                case_id,
                answer_sha256,
                review_text_sha256,
                benchmark_sha256,
                rubric_sha256,
            )
        ).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True)
class HumanSemanticReview:
    case_id: str
    reviewer_id: str
    answer_sha256: str
    review_text_sha256: str
    benchmark_sha256: str
    rubric_sha256: str
    blind_item_id: str
    scores: Mapping[str, int]
    reason_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("case_id", "reviewer_id"):
            object.__setattr__(
                self,
                name,
                _bounded_text(name, str(getattr(self, name))),
            )
        for name in (
            "answer_sha256",
            "review_text_sha256",
            "benchmark_sha256",
            "rubric_sha256",
            "blind_item_id",
        ):
            normalized = str(getattr(self, name)).lower()
            if not _SHA256.fullmatch(normalized):
                raise ValueError(f"{name} is invalid")
            object.__setattr__(self, name, normalized)
        if set(self.scores) != set(_SEMANTIC_DIMENSIONS):
            raise ValueError("scores must contain the five semantic dimensions")
        normalized_scores: dict[str, int] = {}
        for dimension in _SEMANTIC_DIMENSIONS:
            score = self.scores[dimension]
            if isinstance(score, bool) or not isinstance(score, int) or not 1 <= score <= 5:
                raise ValueError(f"score for {dimension} is invalid")
            normalized_scores[dimension] = score
        object.__setattr__(self, "scores", normalized_scores)
        object.__setattr__(
            self,
            "reason_codes",
            tuple(
                sorted(
                    {
                        _bounded_text("reason_code", str(item))
                        for item in self.reason_codes
                    }
                )
            ),
        )


def canonical_payload_sha256(payload: Any) -> str:
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def validate_semantic_catalogs(
    benchmark: Mapping[str, Any],
    rubric: Mapping[str, Any],
    calibration: Mapping[str, Any],
) -> None:
    benchmark_sha256 = canonical_payload_sha256(dict(benchmark))
    if (
        rubric.get("version") != "hxy-semantic-rubric.v1"
        or calibration.get("version") != "hxy-semantic-calibration.v1"
        or rubric.get("benchmark_sha256") != benchmark_sha256
        or calibration.get("benchmark_sha256") != benchmark_sha256
    ):
        raise ValueError("catalog benchmark digest mismatch")

    benchmark_cases = [
        case
        for case in benchmark.get("cases") or []
        if isinstance(case, Mapping)
    ]
    rubric_cases = [
        case for case in rubric.get("cases") or [] if isinstance(case, Mapping)
    ]
    rubric_by_id = {
        str(case.get("case_id") or ""): case for case in rubric_cases
    }
    if len(rubric_cases) != len(benchmark_cases) or len(rubric_by_id) != len(benchmark_cases):
        raise ValueError("semantic rubric catalog mismatch")
    for case in benchmark_cases:
        case_id = str(case.get("case_id") or "")
        rubric_case = rubric_by_id.get(case_id)
        if rubric_case is None or (
            rubric_case.get("role") != case.get("role")
            or list(rubric_case.get("required_outcomes") or [])
            != list(case.get("minimum_useful_outcome") or [])
            or list(rubric_case.get("risk_expectations") or [])
            != list(case.get("risk_expectations") or [])
            or list(rubric_case.get("dimensions") or [])
            != list(_SEMANTIC_DIMENSIONS)
            or rubric_case.get("evidence_authority_by_id")
            != {
                str(evidence_id): (
                    "approved"
                    if case.get("expected_authority") == "approved"
                    else "reference"
                )
                for evidence_id in case.get("allowed_evidence_ids") or []
            }
        ):
            raise ValueError("semantic rubric catalog mismatch")

    expected_calibration_ids: list[str] = []
    for role in _ROLE_ORDER:
        role_ids = [
            str(case.get("case_id") or "")
            for case in benchmark_cases
            if case.get("role") == role
        ]
        if len(role_ids) < 2:
            raise ValueError("semantic calibration catalog mismatch")
        expected_calibration_ids.extend((role_ids[0], role_ids[-1]))
    if (
        list(calibration.get("case_ids") or []) != expected_calibration_ids
        or calibration.get("reviews_required_per_case") != 2
    ):
        raise ValueError("semantic calibration catalog mismatch")


def _contains_private(value: Any, *, key: str | None = None) -> bool:
    if key is not None:
        normalized_key = key.lower()
        if normalized_key in _PRIVATE_KEYS or normalized_key.endswith("_path"):
            return True
    if isinstance(value, Mapping):
        return any(
            _contains_private(item, key=str(item_key))
            for item_key, item in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(_contains_private(item) for item in value)
    if isinstance(value, str):
        normalized = value.lower().replace("\\", "/")
        return (
            normalized.startswith("/")
            or normalized.startswith("file:/")
            or bool(re.match(r"^[a-z]:/", normalized))
            or any(marker in normalized for marker in _PRIVATE_MARKERS)
        )
    return False


def _answer_contains_private_marker(answer: str) -> bool:
    normalized = answer.lower().replace("\\", "/")
    return (
        "source_path" in normalized
        or "chunk_id" in normalized
        or _contains_private(normalized)
    )


def _safe_label(value: str, fallback: str = "redacted") -> str:
    normalized = str(value or "").strip()[:160]
    if not _SAFE_ID.fullmatch(normalized) or _contains_private(normalized):
        return fallback
    return normalized


def _safe_known_ids(values: tuple[str, ...], known_ids: set[str]) -> list[str]:
    return [
        value
        for value in values
        if value in known_ids
        and _SAFE_ID.fullmatch(value)
        and not _contains_private(value)
    ]


def _normalize_review_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    return "".join(
        character
        for character in normalized
        if unicodedata.category(character) not in {"Cf", "Cc"}
    )


def _blind_answer(
    answer: str,
    provider_name: str,
    provider_version: str,
    identity_aliases: tuple[str, ...] = (),
) -> str:
    blinded = _normalize_review_text(answer)
    for identity in (
        provider_name.strip(),
        provider_version.strip(),
        *(item.strip() for item in identity_aliases),
    ):
        identity = _normalize_review_text(identity)
        if not identity or re.fullmatch(r"v\d+(?:\.\d+)*", identity, re.IGNORECASE):
            continue
        blinded = re.sub(
            re.escape(identity),
            "[identity redacted]",
            blinded,
            flags=re.IGNORECASE,
        )
    patterns = (
        r"(?i)\b(?:generated|produced|written|answered)\s+by\s+[^。.!?\n]{1,80}\.?",
        r"(?i)\bpowered\s+by\s+[^。.!?\n]{1,80}\.?",
        r"(?i)\bgenerated\s+using\s+[^。.!?\n]{1,80}\.?",
        r"(?i)\b(?:model|provider)\s*[:=]\s*[a-z0-9._:-]+",
        r"(?i)\bi\s+am\s+(?:an?\s+)?(?:ai\s+)?[a-z0-9._:-]+",
        r"(?i)\b(?:gpt|qwen|deepseek|claude|gemini|doubao|kimi|tongyi)[a-z0-9._:-]*\b",
        r"(?:由|来自)(?:阿里云|通义千问|千问|DeepSeek|豆包|GPT|Claude|Gemini|Kimi)[^，。！？\n]{0,16}生成",
        r"我是(?:通义千问|千问|DeepSeek|豆包|GPT|Claude|Gemini|Kimi)[^，。！？\n]{0,16}",
        r"(?:本回答|本答案|本回复)?由[^，。！？\n]{1,40}(?:生成|提供)",
    )
    for pattern in patterns:
        blinded = re.sub(pattern, "[identity redacted]", blinded)
    return blinded


def _has_identity_marker(answer: str) -> bool:
    answer = _normalize_review_text(answer)
    patterns = (
        r"(?i)\b(?:powered\s+by|generated\s+(?:by|using)|produced\s+by|written\s+by|answered\s+by|i\s+am)\b",
        r"(?i)\b(?:openai|anthropic|aliyun|alibaba|azure\s+openai|gpt|qwen|deepseek|claude|gemini|doubao|kimi|tongyi)\b",
        r"(?:模型身份|身份来源|提供方|回答引擎|模型|引擎)\s*[:：]",
        r"(?:本回答|本答案|本回复)?由[^，。！？\n]{1,40}(?:生成|提供)",
        r"(?:本回答|本答案|本回复).{0,8}(?:通过|使用|来自)[^，。！？\n]{1,40}(?:完成|生成|提供)",
        r"我是[^，。！？\n]{1,30}(?:模型|助手|引擎)",
    )
    return any(re.search(pattern, answer) for pattern in patterns)


def _missing_result(case: Mapping[str, Any]) -> dict[str, Any]:
    hard_gates = {
        "answer_present": False,
        "evidence_scope": False,
        "authority_alignment": False,
        "delivery_policy": False,
        "citation_coverage": False,
        "outcome_contract_complete": False,
        "output_risk_pattern_clear": False,
        "trace_privacy": False,
    }
    return {
        "case_id": _safe_label(str(case.get("case_id") or "")),
        "role": _safe_label(str(case.get("role") or "")),
        "structural_status": "failed",
        "reason_codes": ["missing_answer_run"],
        "hard_gates": hard_gates,
        "budget_checks": {"latency": False, "tokens": False, "cost": False},
        "answer_sha256": None,
        "review_text_sha256": None,
        "provider": {"name": "missing", "version": "missing"},
        "answer_authority": "insufficient",
        "evidence_ids": [],
        "redacted_evidence_count": 0,
        "usage": {
            "latency_ms": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "cost_microunits": 0,
        },
    }


def _evaluate_case(
    case: Mapping[str, Any],
    rubric_case: Mapping[str, Any],
    run: SemanticAnswerRun,
) -> dict[str, Any]:
    allowed_ids = {str(item) for item in case.get("allowed_evidence_ids") or []}
    forbidden_ids = {str(item) for item in case.get("forbidden_evidence_ids") or []}
    evidence_ids = set(run.evidence_ids)
    citations = set(run.citations)
    required_outcomes = {
        str(item) for item in rubric_case.get("required_outcomes") or []
    }
    declared_outcomes = set(run.declared_outcomes)
    compliance_hits = check_brand_risk_text(run.answer).get("hits") or []
    expected_authority = str(case.get("expected_authority") or "")
    authority_by_id = {
        str(key): str(value)
        for key, value in (
            rubric_case.get("evidence_authority_by_id") or {}
        ).items()
    }
    evidence_authority_aligned = (
        len(run.evidence_ids) == len(run.evidence_authorities)
        and all(
            authority_by_id.get(evidence_id) == authority
            for evidence_id, authority in zip(
                run.evidence_ids,
                run.evidence_authorities,
                strict=True,
            )
        )
    )
    delivery_policy_aligned = (
        run.policy_action == "answer" and run.guardrail_action == "send"
        if expected_authority == "approved"
        else run.policy_action in {"needs_review", "deny"}
        and run.guardrail_action in {"revise_or_review", "deny"}
    )
    evidence_scope_aligned = (
        (not evidence_ids and not citations)
        or (bool(evidence_ids) and evidence_ids <= allowed_ids)
        if expected_authority == "insufficient"
        else bool(evidence_ids) and evidence_ids <= allowed_ids
    )
    citation_coverage_aligned = (
        (not evidence_ids and not citations)
        or (
            bool(citations)
            and evidence_ids <= citations
            and citations <= allowed_ids
        )
        if expected_authority == "insufficient"
        else bool(citations)
        and evidence_ids <= citations
        and citations <= allowed_ids
    )
    hard_gates = {
        "answer_present": bool(run.answer.strip()),
        "evidence_scope": evidence_scope_aligned,
        "authority_alignment": (
            run.answer_authority == expected_authority
            and evidence_authority_aligned
        ),
        "delivery_policy": delivery_policy_aligned,
        "citation_coverage": citation_coverage_aligned,
        "outcome_contract_complete": (
            bool(required_outcomes)
            and declared_outcomes == required_outcomes
        ),
        "output_risk_pattern_clear": not compliance_hits,
        "trace_privacy": (
            not _contains_private(run.safe_trace)
            and not _answer_contains_private_marker(run.answer)
        ),
    }
    budget = case.get("budget") or {}
    total_tokens = run.input_tokens + run.output_tokens
    budget_checks = {
        "latency": run.latency_ms <= int(budget.get("max_latency_ms") or 0),
        "tokens": total_tokens <= int(budget.get("max_tokens") or 0),
        "cost": run.cost_microunits <= int(budget.get("max_cost_microunits") or 0),
    }
    passed = all(hard_gates.values()) and all(budget_checks.values())
    reason_codes = [name for name, value in hard_gates.items() if not value]
    reason_codes.extend(
        f"budget_{name}" for name, value in budget_checks.items() if not value
    )
    safe_evidence_ids = _safe_known_ids(
        run.evidence_ids,
        allowed_ids | forbidden_ids,
    )
    blinded_answer = _blind_answer(
        run.answer,
        run.provider_name,
        run.provider_version,
        run.identity_aliases,
    )
    return {
        "case_id": _safe_label(run.case_id),
        "role": _safe_label(str(case.get("role") or "")),
        "structural_status": "passed" if passed else "failed",
        "reason_codes": reason_codes,
        "hard_gates": hard_gates,
        "budget_checks": budget_checks,
        "answer_sha256": hashlib.sha256(run.answer.encode("utf-8")).hexdigest(),
        "review_text_sha256": hashlib.sha256(
            blinded_answer.encode("utf-8")
        ).hexdigest(),
        "provider": {
            "name": _safe_label(run.provider_name),
            "version": _safe_label(run.provider_version),
        },
        "answer_authority": run.answer_authority,
        "evidence_ids": safe_evidence_ids,
        "redacted_evidence_count": len(run.evidence_ids) - len(safe_evidence_ids),
        "usage": {
            "latency_ms": run.latency_ms,
            "input_tokens": run.input_tokens,
            "output_tokens": run.output_tokens,
            "total_tokens": total_tokens,
            "cost_microunits": run.cost_microunits,
        },
    }


def evaluate_semantic_preflight(
    benchmark: Mapping[str, Any],
    rubric: Mapping[str, Any],
    answer_runs: Mapping[str, SemanticAnswerRun],
) -> dict[str, Any]:
    rubric_by_case = {
        str(item.get("case_id") or ""): item
        for item in rubric.get("cases") or []
        if isinstance(item, Mapping)
    }
    results: list[dict[str, Any]] = []
    for case in benchmark.get("cases") or []:
        case_id = str(case.get("case_id") or "")
        run = answer_runs.get(case_id)
        rubric_case = rubric_by_case.get(case_id, {})
        if run is None or not rubric_case:
            results.append(_missing_result(case))
            continue
        if run.case_id != case_id:
            results.append(_missing_result(case))
            continue
        results.append(_evaluate_case(case, rubric_case, run))

    pass_count = sum(item["structural_status"] == "passed" for item in results)
    case_count = len(results)
    checker_metadata = check_brand_risk_text("")
    rules = load_brand_risk_rules()
    return {
        "version": "hxy-semantic-benchmark-report.v1",
        "runner_version": "hxy-semantic-benchmark-runner.v1",
        "mode": "structural_semantic_preflight",
        "metric_scope": "structural_preflight_not_semantic_quality",
        "benchmark_sha256": canonical_payload_sha256(dict(benchmark)),
        "rubric_sha256": canonical_payload_sha256(dict(rubric)),
        "policy": {
            "checker_version": checker_metadata["version"],
            "rules_version": checker_metadata["rules_version"],
            "rules_status": checker_metadata["rules_status"],
            "rules_sha256": canonical_payload_sha256(rules.get("rules") or []),
        },
        "case_count": case_count,
        "answer_run_count": len(answer_runs),
        "structural_pass_count": pass_count,
        "structural_fail_count": case_count - pass_count,
        "structural_pass_rate": (
            round(pass_count / case_count, 4) if case_count else 0.0
        ),
        "semantic_status": "deterministic_only",
        "semantic_evaluated_count": 0,
        "quality_claim_allowed": False,
        "cases": results,
    }


def apply_human_calibration(
    deterministic_report: Mapping[str, Any],
    calibration: Mapping[str, Any],
    reviews: list[HumanSemanticReview],
    *,
    judge_results: Mapping[str, Mapping[str, int]] | None = None,
) -> dict[str, Any]:
    calibration_ids = [
        str(item) for item in calibration.get("case_ids") or []
    ]
    report_case_ids = {
        str(item.get("case_id") or "")
        for item in deterministic_report.get("cases") or []
        if isinstance(item, Mapping)
    }
    if (
        calibration.get("version") != "hxy-semantic-calibration.v1"
        or calibration.get("benchmark_sha256")
        != deterministic_report.get("benchmark_sha256")
        or calibration.get("reviews_required_per_case") != 2
        or len(calibration_ids) != 10
        or len(set(calibration_ids)) != 10
        or not set(calibration_ids) <= report_case_ids
        or any(not _SAFE_ID.fullmatch(item) for item in calibration_ids)
    ):
        raise ValueError("semantic calibration catalog mismatch")
    calibration_set = set(calibration_ids)
    reviews_by_case: dict[str, list[HumanSemanticReview]] = {
        case_id: [] for case_id in calibration_ids
    }
    result_by_case = {
        str(item.get("case_id") or ""): item
        for item in deterministic_report.get("cases") or []
        if isinstance(item, Mapping)
    }
    invalid_review_cases: set[str] = set()
    for review in reviews:
        if review.case_id in calibration_set:
            case_result = result_by_case.get(review.case_id, {})
            answer_sha256 = str(case_result.get("answer_sha256") or "")
            review_text_sha256 = str(
                case_result.get("review_text_sha256") or ""
            )
            expected_blind_id = build_blind_item_id(
                review.case_id,
                answer_sha256,
                review_text_sha256,
                str(deterministic_report.get("benchmark_sha256") or ""),
                str(deterministic_report.get("rubric_sha256") or ""),
            )
            if (
                review.answer_sha256 != answer_sha256
                or review.review_text_sha256 != review_text_sha256
                or review.benchmark_sha256
                != deterministic_report.get("benchmark_sha256")
                or review.rubric_sha256
                != deterministic_report.get("rubric_sha256")
                or review.blind_item_id != expected_blind_id
            ):
                invalid_review_cases.add(review.case_id)
                continue
            reviews_by_case[review.case_id].append(review)

    missing_case_ids: list[str] = []
    needs_adjudication_case_ids: list[str] = []
    invalid_review_case_ids: list[str] = []
    case_scores: list[dict[str, Any]] = []
    for case_id in calibration_ids:
        if case_id in invalid_review_cases:
            invalid_review_case_ids.append(case_id)
            continue
        case_reviews = reviews_by_case[case_id]
        reviewer_ids = {review.reviewer_id for review in case_reviews}
        if len(case_reviews) < 2 or len(reviewer_ids) < 2:
            missing_case_ids.append(case_id)
            continue
        if len(case_reviews) != 2 or len(reviewer_ids) != 2:
            invalid_review_case_ids.append(case_id)
            continue
        first, second = case_reviews
        disagreements = [
            dimension
            for dimension in _SEMANTIC_DIMENSIONS
            if abs(first.scores[dimension] - second.scores[dimension]) > 1
        ]
        if disagreements:
            needs_adjudication_case_ids.append(case_id)
            continue
        case_scores.append(
            {
                "case_id": _safe_label(case_id),
                "scores": {
                    dimension: round(
                        (first.scores[dimension] + second.scores[dimension]) / 2,
                        2,
                    )
                    for dimension in _SEMANTIC_DIMENSIONS
                },
            }
        )

    accepted_count = len(case_scores)
    review_files_complete = (
        bool(calibration_ids)
        and accepted_count == len(calibration_ids)
        and not missing_case_ids
        and not needs_adjudication_case_ids
        and not invalid_review_case_ids
    )
    safe_judge_ids = sorted(
        case_id
        for case_id in (judge_results or {})
        if case_id in calibration_set and _SAFE_ID.fullmatch(case_id)
    )
    report = dict(deterministic_report)
    report["semantic_status"] = (
        "review_files_complete_unverified"
        if review_files_complete
        else "awaiting_human_calibration"
    )
    report["semantic_evaluated_count"] = 0
    report["quality_claim_allowed"] = False
    report["human_calibration"] = {
        "version": "hxy-human-semantic-calibration.v1",
        "required_case_count": len(calibration_ids),
        "reviews_required_per_case": 2,
        "reviewer_provenance_verified": False,
        "accepted_case_count": accepted_count,
        "missing_case_ids": [_safe_label(item) for item in missing_case_ids],
        "needs_adjudication_case_ids": [
            _safe_label(item) for item in needs_adjudication_case_ids
        ],
        "invalid_review_case_ids": [
            _safe_label(item) for item in invalid_review_case_ids
        ],
        "case_scores": case_scores,
    }
    report["advisory_judge"] = {
        "version": "hxy-advisory-semantic-judge.v1",
        "authoritative": False,
        "evaluated_case_count": len(safe_judge_ids),
        "case_ids": safe_judge_ids,
    }
    return report


def semantic_answer_runs_from_payload(
    payload: Mapping[str, Any],
) -> dict[str, SemanticAnswerRun]:
    if set(payload) != {"version", "answers"}:
        raise ValueError("semantic answer run fields are invalid")
    if payload.get("version") != "hxy-semantic-answer-run.v1":
        raise ValueError("unsupported semantic answer run version")
    raw_answers = payload.get("answers")
    if not isinstance(raw_answers, list):
        raise ValueError("semantic answers must be an array")
    if len(raw_answers) > 500:
        raise ValueError("semantic answers exceed the maximum")
    runs: dict[str, SemanticAnswerRun] = {}
    required_fields = {
        "case_id",
        "provider_name",
        "provider_version",
        "answer",
        "identity_aliases",
        "answer_authority",
        "evidence_ids",
        "evidence_authorities",
        "citations",
        "declared_outcomes",
        "policy_action",
        "guardrail_action",
        "latency_ms",
        "input_tokens",
        "output_tokens",
        "cost_microunits",
        "safe_trace",
    }
    for raw in raw_answers:
        if not isinstance(raw, Mapping):
            raise ValueError("semantic answer must be an object")
        if set(raw) != required_fields:
            raise ValueError("semantic answer fields are invalid")
        for name in (
            "case_id",
            "provider_name",
            "provider_version",
            "answer",
            "answer_authority",
            "policy_action",
            "guardrail_action",
        ):
            if not isinstance(raw.get(name), str):
                raise ValueError(f"{name} must be a string")
        for name in (
            "evidence_ids",
            "identity_aliases",
            "evidence_authorities",
            "citations",
            "declared_outcomes",
        ):
            value = raw.get(name)
            if not isinstance(value, list) or any(
                not isinstance(item, str) for item in value
            ):
                raise ValueError(f"{name} must be a string array")
        for name in (
            "latency_ms",
            "input_tokens",
            "output_tokens",
            "cost_microunits",
        ):
            value = raw.get(name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"{name} must be an integer")
        if not isinstance(raw.get("safe_trace"), Mapping):
            raise ValueError("safe_trace must be an object")
        run = SemanticAnswerRun(
            case_id=raw["case_id"],
            provider_name=raw["provider_name"],
            provider_version=raw["provider_version"],
            answer=raw["answer"],
            identity_aliases=tuple(raw["identity_aliases"]),
            answer_authority=raw["answer_authority"],
            evidence_ids=tuple(raw["evidence_ids"]),
            evidence_authorities=tuple(
                raw["evidence_authorities"]
            ),
            citations=tuple(raw["citations"]),
            declared_outcomes=tuple(raw["declared_outcomes"]),
            policy_action=raw["policy_action"],
            guardrail_action=raw["guardrail_action"],
            latency_ms=raw["latency_ms"],
            input_tokens=raw["input_tokens"],
            output_tokens=raw["output_tokens"],
            cost_microunits=raw["cost_microunits"],
            safe_trace=raw["safe_trace"],
        )
        if run.case_id in runs:
            raise ValueError(f"duplicate semantic answer case: {run.case_id}")
        runs[run.case_id] = run
    return runs


def human_reviews_from_payload(
    payload: Mapping[str, Any],
) -> list[HumanSemanticReview]:
    if set(payload) != {"version", "reviews"}:
        raise ValueError("semantic review fields are invalid")
    if payload.get("version") != "hxy-semantic-review.v1":
        raise ValueError("unsupported semantic review version")
    raw_reviews = payload.get("reviews")
    if not isinstance(raw_reviews, list):
        raise ValueError("semantic reviews must be an array")
    if len(raw_reviews) > 1000:
        raise ValueError("semantic reviews exceed the maximum")
    required_fields = {
        "case_id",
        "reviewer_id",
        "answer_sha256",
        "review_text_sha256",
        "benchmark_sha256",
        "rubric_sha256",
        "blind_item_id",
        "scores",
        "reason_codes",
    }
    reviews: list[HumanSemanticReview] = []
    for raw in raw_reviews:
        if not isinstance(raw, Mapping) or set(raw) != required_fields:
            raise ValueError("semantic review item fields are invalid")
        for name in (
            "case_id",
            "reviewer_id",
            "answer_sha256",
            "review_text_sha256",
            "benchmark_sha256",
            "rubric_sha256",
            "blind_item_id",
        ):
            if not isinstance(raw.get(name), str):
                raise ValueError(f"{name} must be a string")
        if not isinstance(raw.get("scores"), Mapping):
            raise ValueError("scores must be an object")
        reason_codes = raw.get("reason_codes")
        if not isinstance(reason_codes, list) or any(
            not isinstance(item, str) for item in reason_codes
        ):
            raise ValueError("reason_codes must be a string array")
        reviews.append(
            HumanSemanticReview(
                case_id=str(raw["case_id"]),
                reviewer_id=str(raw["reviewer_id"]),
                answer_sha256=str(raw["answer_sha256"]),
                review_text_sha256=str(raw["review_text_sha256"]),
                benchmark_sha256=str(raw["benchmark_sha256"]),
                rubric_sha256=str(raw["rubric_sha256"]),
                blind_item_id=str(raw["blind_item_id"]),
                scores=raw["scores"],
                reason_codes=tuple(reason_codes),
            )
        )
    return reviews


def build_blind_review_pack(
    benchmark: Mapping[str, Any],
    rubric: Mapping[str, Any],
    calibration: Mapping[str, Any],
    answer_runs: Mapping[str, SemanticAnswerRun],
    *,
    seed: int,
) -> dict[str, Any]:
    validate_semantic_catalogs(benchmark, rubric, calibration)
    cases = {
        str(case.get("case_id") or ""): case
        for case in benchmark.get("cases") or []
        if isinstance(case, Mapping)
    }
    rubric_cases = {
        str(case.get("case_id") or ""): case
        for case in rubric.get("cases") or []
        if isinstance(case, Mapping)
    }
    items: list[dict[str, Any]] = []
    for case_id in calibration.get("case_ids") or []:
        case_id = str(case_id)
        case = cases.get(case_id)
        rubric_case = rubric_cases.get(case_id)
        run = answer_runs.get(case_id)
        if case is None or rubric_case is None or run is None:
            raise ValueError(f"review pack case is incomplete: {case_id}")
        allowed_ids = {str(item) for item in case.get("allowed_evidence_ids") or []}
        answer_sha256 = hashlib.sha256(run.answer.encode("utf-8")).hexdigest()
        review_text = _blind_answer(
            run.answer,
            run.provider_name,
            run.provider_version,
            run.identity_aliases,
        )
        if _has_identity_marker(review_text):
            raise ValueError("blind review identity marker remains")
        review_text_sha256 = hashlib.sha256(
            review_text.encode("utf-8")
        ).hexdigest()
        benchmark_sha256 = str(rubric.get("benchmark_sha256") or "")
        rubric_sha256 = canonical_payload_sha256(dict(rubric))
        items.append(
            {
                "case_id": _safe_label(case_id),
                "blind_item_id": build_blind_item_id(
                    case_id,
                    answer_sha256,
                    review_text_sha256,
                    benchmark_sha256,
                    rubric_sha256,
                ),
                "answer_sha256": answer_sha256,
                "review_text_sha256": review_text_sha256,
                "benchmark_sha256": benchmark_sha256,
                "rubric_sha256": rubric_sha256,
                "role": _safe_label(str(case.get("role") or "")),
                "question": str((case.get("task") or {}).get("input") or ""),
                "answer": review_text,
                "answer_authority": run.answer_authority,
                "evidence_ids": _safe_known_ids(run.evidence_ids, allowed_ids),
                "evidence_authorities": list(run.evidence_authorities),
                "citations": _safe_known_ids(run.citations, allowed_ids),
                "required_outcomes": list(
                    rubric_case.get("required_outcomes") or []
                ),
                "dimensions": list(rubric_case.get("dimensions") or []),
            }
        )
    random.Random(seed).shuffle(items)
    return {
        "version": "hxy-semantic-masked-review-pack.v1",
        "blind": False,
        "blind_status": "identity_redaction_unverified",
        "seed": seed,
        "case_count": len(items),
        "items": items,
    }
