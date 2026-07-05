from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any

from hxy_knowledge.brain_benchmark import build_approved_answer_runs, build_benchmark_report, load_benchmark
from hxy_knowledge.knowledge_compiler import compile_directory, write_harness_run


@dataclass(slots=True)
class LoopThresholds:
    min_review_queue: int = 20
    min_answer_card_drafts: int = 10
    min_claim_count: int = 1


@dataclass(slots=True)
class CompileKnowledgeLoopConfig:
    raw_dir: Path
    wiki_dir: Path
    report_path: Path
    runs_dir: Path
    run_id: str
    thresholds: LoopThresholds
    max_iterations: int = 2


@dataclass(slots=True)
class BenchmarkImprovementLoopConfig:
    benchmark_path: Path
    report_path: Path
    runs_dir: Path
    run_id: str
    max_iterations: int = 1
    min_pass_rate: float | None = None


def _public_report(report: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in report.items() if key != "artifacts"}


def _make_goal(thresholds: LoopThresholds) -> dict[str, Any]:
    return {
        "text": "Compile HXY reference materials into governed review artifacts.",
        "measurable_target": (
            f"review_queue_count >= {thresholds.min_review_queue} "
            f"and answer_card_draft_count >= {thresholds.min_answer_card_drafts}"
        ),
    }


def _evaluate_report(report: dict[str, Any], thresholds: LoopThresholds) -> dict[str, Any]:
    extract_count = int(report.get("extract_count") or 0)
    claim_count = int(report.get("claim_count") or 0)
    review_queue_count = int(report.get("review_queue_count") or 0)
    answer_card_draft_count = int(report.get("answer_card_draft_count") or 0)

    evidence_sufficient = extract_count > 0 and claim_count > 0
    target_met = (
        evidence_sufficient
        and review_queue_count >= thresholds.min_review_queue
        and answer_card_draft_count >= thresholds.min_answer_card_drafts
    )
    next_actions: list[str] = []
    if not evidence_sufficient:
        next_actions.append("补充原始资料或调整输入目录，当前证据不足。")
    elif review_queue_count < thresholds.min_review_queue or answer_card_draft_count < thresholds.min_answer_card_drafts:
        next_actions.append("继续人工复核候选 claim，或调整阈值后再跑一轮。")
    if claim_count > 0:
        next_actions.append("人工复核后再决定是否转草稿，禁止自动批准。")
    return {
        "version": "hxy-loop-runner-evaluation.v1",
        "extract_count": extract_count,
        "claim_count": claim_count,
        "review_queue_count": review_queue_count,
        "answer_card_draft_count": answer_card_draft_count,
        "evidence_sufficient": evidence_sufficient,
        "target_met": target_met,
        "next_actions": next_actions,
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _json_fingerprint(payload: dict[str, Any]) -> dict[str, str]:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {
        "algorithm": "sha256",
        "digest": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
    }


def _benchmark_goal(min_pass_rate: float) -> dict[str, Any]:
    return {
        "text": "Run HXY Brain benchmark and convert failures into reviewer-ready correction tasks.",
        "measurable_target": f"benchmark pass_rate >= {min_pass_rate:.2f}",
    }


def _case_by_id(benchmark: dict[str, Any]) -> dict[str, dict[str, Any]]:
    cases = benchmark.get("cases") if isinstance(benchmark.get("cases"), list) else []
    return {str(case.get("case_id") or ""): case for case in cases if str(case.get("case_id") or "")}


def _recommended_reviewer(case: dict[str, Any], score: dict[str, Any]) -> str:
    failed_checks = {str(item) for item in score.get("failed_checks", [])}
    domain = str(case.get("domain") or "")
    if "overclaim_risk" in failed_checks or domain in {"risk_boundary", "compliance"}:
        return "运营/合规负责人"
    if domain in {"brand_positioning", "product_system", "customer_segment"}:
        return "品牌/产品负责人"
    return "知识管理员"


def _authority_gap_priority(case: dict[str, Any]) -> dict[str, Any]:
    case_id = str(case.get("case_id") or "")
    domain = str(case.get("domain") or "")
    question = str(case.get("question") or "")
    risk_checks = {str(item) for item in case.get("risk_checks", [])}
    expected_capabilities = {str(item) for item in case.get("expected_capabilities", [])}

    if case_id == "compliance-medical-001":
        return {"priority": "P0", "risk_tier": "high", "priority_score": 100, "priority_reason": "医疗化表达拦截是最高合规风险。"}
    if case_id == "compliance-effect-001":
        return {"priority": "P0", "risk_tier": "high", "priority_score": 99, "priority_reason": "保证疗效表达必须优先补权威卡。"}
    if case_id == "compliance-marketing-001":
        return {"priority": "P0", "risk_tier": "high", "priority_score": 98, "priority_reason": "夸大宣传表达必须优先补权威卡。"}
    if domain == "risk_boundary" or case_id.startswith("compliance-"):
        return {"priority": "P0", "risk_tier": "high", "priority_score": 94, "priority_reason": "涉及合规、安全边界或过度承诺。"}
    if domain == "employee_training" or expected_capabilities & {"generate_training_item", "role_adapted_answer"}:
        return {"priority": "P1", "risk_tier": "medium", "priority_score": 80, "priority_reason": "员工话术会直接影响首店交付和合规一致性。"}
    if domain == "customer_segment" or "目标客群" in question:
        return {"priority": "P1", "risk_tier": "medium", "priority_score": 76, "priority_reason": "目标客群影响品牌定位、开业动作和首店验证。"}
    if domain == "knowledge_governance":
        return {"priority": "P2", "risk_tier": "medium", "priority_score": 60, "priority_reason": "知识治理规则会影响后续答案卡发布质量。"}
    if domain == "operating_issue":
        return {"priority": "P2", "risk_tier": "medium", "priority_score": 52, "priority_reason": "经营策略题需要权威卡沉淀，但低于合规和一线话术。"}
    return {"priority": "P3", "risk_tier": "low", "priority_score": 40, "priority_reason": "一般知识覆盖缺口，排在高风险任务之后处理。"}


def _p0_draft_answer_for(task: dict[str, Any]) -> str:
    case_id = str(task.get("case_id") or "")
    if case_id == "compliance-medical-001":
        return "不能说泡脚能治疗失眠。标准口径是：泡脚可以作为放松体验，但不能替代医疗诊断或治疗；如果顾客长期睡眠困扰或身体不适，应建议咨询专业人员。"
    if case_id == "compliance-effect-001":
        return "不能承诺泡脚多久见效，也不能说一周见效、一定有效。标准口径是：每个人体感不同，荷小悦只提供放松和状态体验建议，效果需要结合个人状态持续观察。"
    if case_id == "compliance-marketing-001":
        return "不能说荷小悦比所有足浴店都好，也不能使用最好、第一、远超同行这类夸大表达。标准口径是：荷小悦强调社区草本泡脚、清泡调补养分层和员工按状态推荐。"
    if case_id == "risk-002":
        return "不能说泡脚可以治疗失眠。员工应先拦截医疗化表达，再改成安全说法：我们不能做医疗判断，可以根据你的放松需求推荐泡脚体验；如长期失眠建议就医或咨询专业人员。"
    return "当前为 P0 风险草稿，只能作为人工复核材料。正式使用前必须补充来源、负责人和审核记录。"


def _p0_authority_card_draft_from_task(task: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": "hxy-answer-card-draft.v1",
        "source_task_id": task.get("task_id") or "",
        "source_case_id": task.get("case_id") or "",
        "question_pattern": task.get("question") or "",
        "intent": "risk_boundary",
        "audience": "store_staff",
        "answer": _p0_draft_answer_for(task),
        "status": "draft",
        "official_use_allowed": False,
        "requires_human_review": True,
        "risk_flags": ["合规风险", "过度承诺风险"],
        "priority": task.get("priority") or "P0",
        "risk_tier": task.get("risk_tier") or "high",
        "review_group": "risk_boundary",
        "recommended_reviewer": task.get("recommended_reviewer") or "运营/合规负责人",
        "sources": ["knowledge/benchmarks/hxy-brain-benchmark-v1.json"],
        "next_actions": [
            "由运营/合规负责人复核答案边界。",
            "补充正式来源、版本和负责人后，才允许进入 approved answer card。",
            "同步到门店员工禁用表达训练题。",
        ],
        "authority_rule": "p0_authority_card_drafts_require_human_review",
    }


P0_DRAFT_OVERCLAIM_TERMS = ["治疗", "治愈", "保证", "一定有效", "一定见效", "最好", "第一", "远超同行", "替代医疗"]
P0_DRAFT_NEGATION_MARKERS = ["不能", "不应", "不得", "不要", "禁止", "避免", "不替代", "不能替代", "不能承诺", "不能说", "不能使用"]


def _positive_overclaim_terms(text: str) -> list[str]:
    hits: list[str] = []
    normalized = str(text or "")
    for term in P0_DRAFT_OVERCLAIM_TERMS:
        start = 0
        while True:
            index = normalized.find(term, start)
            if index == -1:
                break
            window = normalized[max(0, index - 18) : index + len(term) + 4]
            if not any(marker in window for marker in P0_DRAFT_NEGATION_MARKERS):
                hits.append(term)
                break
            start = index + len(term)
    return hits


def _build_p0_draft_quality_gate(drafts: list[dict[str, Any]]) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    all_hits: list[str] = []
    for draft in drafts:
        hits = _positive_overclaim_terms(str(draft.get("answer") or ""))
        all_hits.extend(hit for hit in hits if hit not in all_hits)
        items.append(
            {
                "source_case_id": draft.get("source_case_id") or "",
                "question_pattern": draft.get("question_pattern") or "",
                "passed": not hits,
                "positive_overclaim_terms": hits,
                "allows_negated_risk_terms": True,
            }
        )
    failed_count = sum(1 for item in items if not item["passed"])
    return {
        "version": "hxy-p0-draft-quality-gate.v1",
        "passed": failed_count == 0,
        "checked_count": len(items),
        "failed_count": failed_count,
        "positive_overclaim_terms": all_hits,
        "items": items,
    }


def _review_questions_for_draft(draft: dict[str, Any]) -> list[str]:
    case_id = str(draft.get("source_case_id") or "")
    common = [
        "这张草稿是否明确拦截了高风险说法？",
        "草稿是否把可说表达和不可说表达分清楚？",
        "门店员工是否能按这张卡直接训练？",
    ]
    if case_id == "compliance-medical-001" or case_id == "risk-002":
        return [
            "是否明确说明不能做医疗诊断或治疗承诺？",
            "是否建议长期不适顾客咨询专业人员？",
            *common,
        ]
    if case_id == "compliance-effect-001":
        return [
            "是否明确禁止承诺见效时间和确定效果？",
            "是否表达了个体差异和持续观察？",
            *common,
        ]
    if case_id == "compliance-marketing-001":
        return [
            "是否明确禁止最好、第一、远超同行等夸大表达？",
            "是否改成可验证的品牌差异表达？",
            *common,
        ]
    return common


def _review_manifest_item_for_draft(draft: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_case_id": draft.get("source_case_id") or "",
        "source_task_id": draft.get("source_task_id") or "",
        "question_pattern": draft.get("question_pattern") or "",
        "reviewer": draft.get("recommended_reviewer") or "运营/合规负责人",
        "status": "pending_review",
        "review_questions": _review_questions_for_draft(draft),
        "approval_conditions": [
            "答案不包含正向医疗、疗效保证或夸大营销承诺。",
            "答案能被门店员工直接理解和复述。",
            "答案补齐正式来源、负责人、版本和适用场景。",
            "审核人确认后再转 approved answer card。",
        ],
        "rejection_conditions": [
            "仍含治疗、治愈、保证见效、最好、第一等正向风险表达。",
            "只给原则，没有可训练的标准话术。",
            "缺少负责人或适用场景，无法进入正式知识库。",
        ],
        "approval_effects": [
            "可创建对应 approved answer card。",
            "可覆盖同 case 的 authority gap task。",
            "可进入门店员工禁用表达训练题。",
        ],
        "authority_rule": "review_manifest_does_not_approve_cards",
    }


def _build_p0_draft_review_manifest(drafts: list[dict[str, Any]]) -> dict[str, Any]:
    items = [_review_manifest_item_for_draft(draft) for draft in drafts]
    return {
        "version": "hxy-p0-draft-review-manifest.v1",
        "review_count": len(items),
        "items": items,
        "official_use_allowed": False,
        "requires_human_review": True,
        "authority_rule": "review_manifest_does_not_approve_cards",
    }


def _build_p0_authority_card_draft_pack(authority_gap_tasks: list[dict[str, Any]]) -> dict[str, Any]:
    p0_tasks = [task for task in authority_gap_tasks if task.get("priority") == "P0" and task.get("risk_tier") == "high"]
    drafts = [_p0_authority_card_draft_from_task(task) for task in p0_tasks]
    return {
        "version": "hxy-p0-authority-card-draft-pack.v1",
        "draft_count": len(drafts),
        "items": drafts,
        "quality_gate": _build_p0_draft_quality_gate(drafts),
        "review_manifest": _build_p0_draft_review_manifest(drafts),
        "official_use_allowed": False,
        "requires_human_review": True,
        "authority_rule": "p0_authority_card_drafts_require_human_review",
    }


P0_REVIEW_DECISION_ALLOWED_ACTIONS = ["approve", "reject", "needs_revision"]
P0_PUBLICATION_REQUIRED_METADATA_FIELDS = [
    "source_references",
    "knowledge_version",
    "responsible_owner",
    "effective_scope",
    "risk_review_status",
]


def _p0_publication_metadata_template() -> dict[str, Any]:
    return {
        "source_references": [],
        "knowledge_version": "",
        "responsible_owner": "",
        "effective_scope": "",
        "risk_review_status": "",
    }


def _build_p0_review_decision_stub(draft_pack: dict[str, Any]) -> dict[str, Any]:
    drafts = draft_pack.get("items") if isinstance(draft_pack.get("items"), list) else []
    items: list[dict[str, Any]] = []
    for draft in drafts:
        items.append(
            {
                "source_case_id": draft.get("source_case_id") or "",
                "source_task_id": draft.get("source_task_id") or "",
                "question_pattern": draft.get("question_pattern") or "",
                "reviewer": draft.get("recommended_reviewer") or "运营/合规负责人",
                "action": "pending",
                "allowed_actions": P0_REVIEW_DECISION_ALLOWED_ACTIONS,
                "status": "pending_decision",
                "note": "",
                "publication_metadata_template": _p0_publication_metadata_template(),
                "official_use_allowed": False,
                "requires_human_review": True,
                "authority_rule": "p0_review_decisions_do_not_publish_approved_cards",
            }
        )
    return {
        "version": "hxy-p0-review-decisions.v1",
        "decision_count": len(items),
        "allowed_actions": P0_REVIEW_DECISION_ALLOWED_ACTIONS,
        "publication_metadata_schema": {
            "applies_to_action": "approve",
            "required_fields": P0_PUBLICATION_REQUIRED_METADATA_FIELDS,
            "template": _p0_publication_metadata_template(),
            "rule": "approve_requires_publication_preflight_metadata",
        },
        "items": items,
        "official_use_allowed": False,
        "requires_human_review": True,
        "publish_allowed": False,
        "authority_rule": "p0_review_decisions_do_not_publish_approved_cards",
    }


def _load_p0_review_decisions(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _manual_decision_by_source(decisions_payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    items = decisions_payload.get("items") if isinstance(decisions_payload.get("items"), list) else []
    by_source: dict[str, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        source_case_id = str(item.get("source_case_id") or "")
        source_task_id = str(item.get("source_task_id") or "")
        if source_case_id:
            by_source[f"case:{source_case_id}"] = item
        if source_task_id:
            by_source[f"task:{source_task_id}"] = item
    return by_source


def _next_task_for_p0_review_decision(stub_item: dict[str, Any], action: str, note: str) -> dict[str, Any]:
    source_case_id = str(stub_item.get("source_case_id") or "")
    source_task_id = str(stub_item.get("source_task_id") or "")
    base = {
        "source_case_id": source_case_id,
        "source_task_id": source_task_id,
        "official_use_allowed": False,
        "publish_allowed": False,
        "requires_human_review": True,
        "review_note": note,
        "authority_rule": "p0_review_decisions_do_not_publish_approved_cards",
    }
    if action == "approve":
        return {
            **base,
            "task_id": f"prepare-authority-card-publication-{source_case_id}",
            "status": "blocked_until_manual_publication",
            "required_action": "人工补齐来源、版本、负责人和生效范围后，再由负责人手动创建 approved answer card；loop 不允许自动发布。",
        }
    if action == "needs_revision":
        return {
            **base,
            "task_id": f"revise-p0-authority-card-draft-{source_case_id}",
            "status": "needs_revision",
            "required_action": "根据审核意见修订 P0 草稿，修订后重新进入人工审核。",
        }
    if action == "reject":
        return {
            **base,
            "task_id": f"replace-p0-authority-card-draft-{source_case_id}",
            "status": "rejected",
            "required_action": "废弃当前草稿，重新补证据或重写安全口径后再提交审核。",
        }
    return {
        **base,
        "task_id": f"review-p0-authority-card-draft-{source_case_id}",
        "status": "pending_review",
        "required_action": "等待运营/合规负责人做 approve、reject 或 needs_revision 决策。",
    }


def _build_p0_review_decision_summary(
    decision_stub: dict[str, Any],
    decisions_payload: dict[str, Any],
) -> dict[str, Any]:
    decision_items = decision_stub.get("items") if isinstance(decision_stub.get("items"), list) else []
    manual_decisions = _manual_decision_by_source(decisions_payload)
    summary_items: list[dict[str, Any]] = []
    next_tasks: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    counts = {"approve": 0, "needs_revision": 0, "reject": 0, "pending": 0}
    for stub_item in decision_items:
        source_case_id = str(stub_item.get("source_case_id") or "")
        source_task_id = str(stub_item.get("source_task_id") or "")
        decision = manual_decisions.get(f"case:{source_case_id}") or manual_decisions.get(f"task:{source_task_id}") or {}
        action = str(decision.get("action") or "pending")
        invalid_action = ""
        if action not in P0_REVIEW_DECISION_ALLOWED_ACTIONS:
            if action != "pending":
                invalid_action = action
                warnings.append(
                    {
                        "source_case_id": source_case_id,
                        "source_task_id": source_task_id,
                        "invalid_action": invalid_action,
                        "allowed_actions": P0_REVIEW_DECISION_ALLOWED_ACTIONS,
                        "message": "Invalid P0 review action ignored and treated as pending.",
                    }
                )
            action = "pending"
        counts[action] += 1
        note = str(decision.get("note") or "")
        summary_item = {
            "source_case_id": source_case_id,
            "source_task_id": source_task_id,
            "action": action,
            "reviewer": decision.get("reviewer") or stub_item.get("reviewer") or "运营/合规负责人",
            "note": note,
            "official_use_allowed": False,
            "publish_allowed": False,
            "authority_rule": "p0_review_decisions_do_not_publish_approved_cards",
        }
        if invalid_action:
            summary_item["invalid_action"] = invalid_action
        summary_items.append(summary_item)
        next_tasks.append(_next_task_for_p0_review_decision(stub_item, action, note))

    return {
        "version": "hxy-p0-review-decision-summary.v1",
        "decision_count": len(summary_items),
        "approved_count": counts["approve"],
        "needs_revision_count": counts["needs_revision"],
        "rejected_count": counts["reject"],
        "pending_count": counts["pending"],
        "invalid_decision_count": len(warnings),
        "warnings": warnings,
        "items": summary_items,
        "next_tasks": next_tasks,
        "official_use_allowed": False,
        "publish_allowed": False,
        "requires_human_review": True,
        "authority_rule": "p0_review_decisions_do_not_publish_approved_cards",
    }


def _missing_publication_metadata_fields(metadata: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    for field in P0_PUBLICATION_REQUIRED_METADATA_FIELDS:
        value = metadata.get(field)
        if value is None or value == "" or value == []:
            missing.append(field)
    return missing


def _build_p0_publication_preflight(
    decision_stub: dict[str, Any],
    decisions_payload: dict[str, Any],
) -> dict[str, Any]:
    stub_items = decision_stub.get("items") if isinstance(decision_stub.get("items"), list) else []
    manual_decisions = _manual_decision_by_source(decisions_payload)
    items: list[dict[str, Any]] = []
    for stub_item in stub_items:
        source_case_id = str(stub_item.get("source_case_id") or "")
        source_task_id = str(stub_item.get("source_task_id") or "")
        decision = manual_decisions.get(f"case:{source_case_id}") or manual_decisions.get(f"task:{source_task_id}") or {}
        if str(decision.get("action") or "") != "approve":
            continue
        metadata = decision.get("publication_metadata") if isinstance(decision.get("publication_metadata"), dict) else {}
        missing_fields = _missing_publication_metadata_fields(metadata)
        manual_publication_ready = not missing_fields
        items.append(
            {
                "source_case_id": source_case_id,
                "source_task_id": source_task_id,
                "reviewer": decision.get("reviewer") or stub_item.get("reviewer") or "运营/合规负责人",
                "status": (
                    "ready_for_manual_publication"
                    if manual_publication_ready
                    else "blocked_missing_publication_metadata"
                ),
                "manual_publication_ready": manual_publication_ready,
                "missing_fields": missing_fields,
                "required_fields": P0_PUBLICATION_REQUIRED_METADATA_FIELDS,
                "publication_metadata": metadata,
                "official_use_allowed": False,
                "publish_allowed": False,
                "requires_human_review": True,
                "authority_rule": "p0_publication_preflight_does_not_publish_approved_cards",
            }
        )
    ready_count = sum(1 for item in items if item["manual_publication_ready"])
    blocked_count = len(items) - ready_count
    return {
        "version": "hxy-p0-publication-preflight.v1",
        "decision_fingerprint": _json_fingerprint(decisions_payload),
        "approved_decision_count": len(items),
        "ready_count": ready_count,
        "blocked_count": blocked_count,
        "items": items,
        "required_fields": P0_PUBLICATION_REQUIRED_METADATA_FIELDS,
        "official_use_allowed": False,
        "publish_allowed": False,
        "requires_human_review": True,
        "authority_rule": "p0_publication_preflight_does_not_publish_approved_cards",
    }


def build_p0_review_decisions_sample(decision_stub: dict[str, Any]) -> dict[str, Any]:
    stub_items = decision_stub.get("items") if isinstance(decision_stub.get("items"), list) else []
    items: list[dict[str, Any]] = []
    for stub_item in stub_items:
        metadata_template = stub_item.get("publication_metadata_template")
        if not isinstance(metadata_template, dict):
            metadata_template = _p0_publication_metadata_template()
        items.append(
            {
                "source_case_id": stub_item.get("source_case_id") or "",
                "source_task_id": stub_item.get("source_task_id") or "",
                "question_pattern": stub_item.get("question_pattern") or "",
                "action": "pending",
                "allowed_actions": P0_REVIEW_DECISION_ALLOWED_ACTIONS,
                "reviewer": stub_item.get("reviewer") or "运营/合规负责人",
                "note": "",
                "publication_metadata": dict(metadata_template),
                "official_use_allowed": False,
                "publish_allowed": False,
                "authority_rule": "p0_review_decisions_sample_does_not_publish_approved_cards",
            }
        )
    return {
        "version": "hxy-p0-review-decisions-sample.v1",
        "target_filename": "p0-review-decisions.json",
        "decision_count": len(items),
        "allowed_actions": P0_REVIEW_DECISION_ALLOWED_ACTIONS,
        "publication_metadata_schema": decision_stub.get("publication_metadata_schema") or {},
        "items": items,
        "official_use_allowed": False,
        "publish_allowed": False,
        "requires_human_review": True,
        "authority_rule": "p0_review_decisions_sample_does_not_publish_approved_cards",
    }


def initialize_p0_review_decisions_from_sample(decision_sample: dict[str, Any]) -> dict[str, Any]:
    sample_items = decision_sample.get("items") if isinstance(decision_sample.get("items"), list) else []
    items: list[dict[str, Any]] = []
    for sample_item in sample_items:
        if not isinstance(sample_item, dict):
            continue
        metadata = (
            sample_item.get("publication_metadata")
            if isinstance(sample_item.get("publication_metadata"), dict)
            else _p0_publication_metadata_template()
        )
        items.append(
            {
                "source_case_id": sample_item.get("source_case_id") or "",
                "source_task_id": sample_item.get("source_task_id") or "",
                "question_pattern": sample_item.get("question_pattern") or "",
                "action": "pending",
                "allowed_actions": P0_REVIEW_DECISION_ALLOWED_ACTIONS,
                "reviewer": sample_item.get("reviewer") or "运营/合规负责人",
                "note": "",
                "publication_metadata": dict(metadata),
                "official_use_allowed": False,
                "publish_allowed": False,
                "write_to_database": False,
                "authority_rule": "initialized_p0_review_decisions_do_not_publish_approved_cards",
            }
        )
    return {
        "version": "hxy-p0-review-decisions.v1",
        "initialized_from_sample": True,
        "sample_fingerprint": _json_fingerprint(decision_sample),
        "decision_count": len(items),
        "allowed_actions": P0_REVIEW_DECISION_ALLOWED_ACTIONS,
        "items": items,
        "official_use_allowed": False,
        "publish_allowed": False,
        "write_to_database": False,
        "requires_human_review": True,
        "authority_rule": "initialized_p0_review_decisions_do_not_publish_approved_cards",
    }


def build_p0_review_decisions_audit(decision_sample: dict[str, Any], decisions_payload: dict[str, Any]) -> dict[str, Any]:
    sample_items = decision_sample.get("items") if isinstance(decision_sample.get("items"), list) else []
    decisions_by_case_id = _items_by_source_case_id(decisions_payload)
    items: list[dict[str, Any]] = []
    changed_count = 0
    pending_count = 0
    metadata_gap_count = 0

    for sample_item in sample_items:
        if not isinstance(sample_item, dict):
            continue
        source_case_id = str(sample_item.get("source_case_id") or "")
        decision = decisions_by_case_id.get(source_case_id, {})
        sample_action = str(sample_item.get("action") or "pending")
        current_action = str(decision.get("action") or sample_action or "pending")
        changed = current_action != sample_action
        if changed:
            changed_count += 1
        if current_action == "pending":
            pending_count += 1

        metadata_status = "not_required"
        missing_fields: list[str] = []
        if current_action == "approve":
            metadata = decision.get("publication_metadata") if isinstance(decision.get("publication_metadata"), dict) else {}
            missing_fields = _missing_publication_metadata_fields(metadata)
            metadata_status = "complete" if not missing_fields else "missing_required_fields"
            if missing_fields:
                metadata_gap_count += 1

        items.append(
            {
                "source_case_id": source_case_id,
                "source_task_id": sample_item.get("source_task_id") or decision.get("source_task_id") or "",
                "sample_action": sample_action,
                "current_action": current_action,
                "changed": changed,
                "metadata_status": metadata_status,
                "missing_fields": missing_fields,
                "official_use_allowed": False,
                "publish_allowed": False,
                "write_to_database": False,
            }
        )

    return {
        "version": "hxy-p0-review-decisions-audit.v1",
        "sample_fingerprint": _json_fingerprint(decision_sample),
        "decision_fingerprint": _json_fingerprint(decisions_payload),
        "item_count": len(items),
        "changed_count": changed_count,
        "pending_count": pending_count,
        "metadata_gap_count": metadata_gap_count,
        "items": items,
        "official_use_allowed": False,
        "publish_allowed": False,
        "write_to_database": False,
        "authority_rule": "p0_review_decisions_audit_does_not_publish_approved_cards",
    }


def _items_by_source_case_id(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    items = payload.get("items") if isinstance(payload.get("items"), list) else []
    return {
        str(item.get("source_case_id") or ""): item
        for item in items
        if isinstance(item, dict) and str(item.get("source_case_id") or "")
    }


def build_p0_manual_review_packet(
    *,
    decision_stub: dict[str, Any],
    draft_pack: dict[str, Any],
    review_manifest: dict[str, Any],
    decision_sample: dict[str, Any],
) -> dict[str, Any]:
    stub_items = decision_stub.get("items") if isinstance(decision_stub.get("items"), list) else []
    drafts_by_case_id = _draft_by_source_case_id(draft_pack)
    manifest_by_case_id = _items_by_source_case_id(review_manifest)
    sample_by_case_id = _items_by_source_case_id(decision_sample)
    items: list[dict[str, Any]] = []

    for stub_item in stub_items:
        if not isinstance(stub_item, dict):
            continue
        source_case_id = str(stub_item.get("source_case_id") or "")
        if not source_case_id:
            continue
        draft = drafts_by_case_id.get(source_case_id, {})
        manifest_item = manifest_by_case_id.get(source_case_id, {})
        decision_template = sample_by_case_id.get(source_case_id, {})
        items.append(
            {
                "source_case_id": source_case_id,
                "source_task_id": stub_item.get("source_task_id") or "",
                "question_pattern": stub_item.get("question_pattern") or draft.get("question_pattern") or "",
                "reviewer": stub_item.get("reviewer") or manifest_item.get("reviewer") or "运营/合规负责人",
                "draft_answer": draft.get("answer") or "",
                "risk_flags": draft.get("risk_flags") if isinstance(draft.get("risk_flags"), list) else [],
                "review_questions": (
                    manifest_item.get("review_questions")
                    if isinstance(manifest_item.get("review_questions"), list)
                    else []
                ),
                "approval_conditions": (
                    manifest_item.get("approval_conditions")
                    if isinstance(manifest_item.get("approval_conditions"), list)
                    else []
                ),
                "rejection_conditions": (
                    manifest_item.get("rejection_conditions")
                    if isinstance(manifest_item.get("rejection_conditions"), list)
                    else []
                ),
                "decision_template": decision_template,
                "allowed_actions": P0_REVIEW_DECISION_ALLOWED_ACTIONS,
                "required_publication_metadata_fields": P0_PUBLICATION_REQUIRED_METADATA_FIELDS,
                "official_use_allowed": False,
                "publish_allowed": False,
                "write_to_database": False,
                "authority_rule": "manual_review_packet_does_not_publish_approved_cards",
            }
        )

    return {
        "version": "hxy-p0-manual-review-packet.v1",
        "item_count": len(items),
        "items": items,
        "decision_stub_fingerprint": _json_fingerprint(decision_stub),
        "draft_pack_fingerprint": _json_fingerprint(draft_pack),
        "review_manifest_fingerprint": _json_fingerprint(review_manifest),
        "decision_sample_fingerprint": _json_fingerprint(decision_sample),
        "official_use_allowed": False,
        "publish_allowed": False,
        "write_to_database": False,
        "requires_human_review": True,
        "authority_rule": "manual_review_packet_does_not_publish_approved_cards",
    }


def render_p0_manual_review_packet_markdown(packet: dict[str, Any]) -> str:
    lines = [
        "# HXY P0 Manual Review Packet",
        "",
        "This packet does not approve or publish answer cards.",
        "",
        f"item_count: {int(packet.get('item_count') or 0)}",
        f"publish_allowed: {'true' if packet.get('publish_allowed') else 'false'}",
        f"write_to_database: {'true' if packet.get('write_to_database') else 'false'}",
        "",
        "## Required Publication Metadata",
        "",
    ]
    for field in P0_PUBLICATION_REQUIRED_METADATA_FIELDS:
        lines.append(f"- `{field}`")

    items = packet.get("items") if isinstance(packet.get("items"), list) else []
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            continue
        lines.extend(
            [
                "",
                f"## {index}. {item.get('source_case_id') or ''}",
                "",
                f"- source_task_id: `{item.get('source_task_id') or ''}`",
                f"- reviewer: {item.get('reviewer') or ''}",
                f"- question: {item.get('question_pattern') or ''}",
                "",
                "### Draft Answer",
                "",
                str(item.get("draft_answer") or ""),
                "",
                "### Review Questions",
                "",
            ]
        )
        review_questions = item.get("review_questions") if isinstance(item.get("review_questions"), list) else []
        for question in review_questions:
            lines.append(f"- {question}")
        lines.extend(["", "### Approval Conditions", ""])
        approval_conditions = item.get("approval_conditions") if isinstance(item.get("approval_conditions"), list) else []
        for condition in approval_conditions:
            lines.append(f"- {condition}")
        lines.extend(["", "### Decision Template", "", "```json"])
        lines.append(json.dumps(item.get("decision_template") or {}, ensure_ascii=False, indent=2))
        lines.append("```")

    lines.append("")
    return "\n".join(lines)


def validate_p0_review_decisions(decision_stub: dict[str, Any], decisions_payload: dict[str, Any]) -> dict[str, Any]:
    summary = _build_p0_review_decision_summary(decision_stub, decisions_payload)
    publication_preflight = _build_p0_publication_preflight(decision_stub, decisions_payload)
    errors: list[dict[str, Any]] = []

    for warning in summary.get("warnings", []):
        if not isinstance(warning, dict):
            continue
        errors.append(
            {
                "code": "invalid_action",
                "source_case_id": warning.get("source_case_id") or "",
                "source_task_id": warning.get("source_task_id") or "",
                "invalid_action": warning.get("invalid_action") or "",
                "allowed_actions": warning.get("allowed_actions") or P0_REVIEW_DECISION_ALLOWED_ACTIONS,
                "message": "Invalid P0 review action. Use approve, reject, or needs_revision.",
            }
        )

    preflight_items = publication_preflight.get("items") if isinstance(publication_preflight.get("items"), list) else []
    for item in preflight_items:
        if not isinstance(item, dict):
            continue
        missing_fields = item.get("missing_fields") if isinstance(item.get("missing_fields"), list) else []
        if missing_fields:
            errors.append(
                {
                    "code": "missing_publication_metadata",
                    "source_case_id": item.get("source_case_id") or "",
                    "source_task_id": item.get("source_task_id") or "",
                    "missing_fields": missing_fields,
                    "message": "Approved P0 review decision is missing required publication metadata.",
                }
            )

    return {
        "version": "hxy-p0-review-decisions-validation.v1",
        "decision_fingerprint": _json_fingerprint(decisions_payload),
        "valid": len(errors) == 0,
        "error_count": len(errors),
        "warning_count": 0,
        "errors": errors,
        "warnings": [],
        "summary": summary,
        "publication_preflight": publication_preflight,
        "official_use_allowed": False,
        "publish_allowed": False,
        "write_to_database": False,
        "requires_human_review": True,
        "authority_rule": "p0_review_decisions_validation_does_not_publish_approved_cards",
    }


def render_p0_review_decisions_validation_markdown(validation: dict[str, Any]) -> str:
    summary = validation.get("summary") if isinstance(validation.get("summary"), dict) else {}
    publication_preflight = (
        validation.get("publication_preflight")
        if isinstance(validation.get("publication_preflight"), dict)
        else {}
    )
    decision_fingerprint = (
        validation.get("decision_fingerprint")
        if isinstance(validation.get("decision_fingerprint"), dict)
        else {}
    )
    lines = [
        "# HXY P0 Review Decisions Report",
        "",
        "This report does not approve, publish, or import answer cards.",
        "",
        f"valid: {'true' if validation.get('valid') else 'false'}",
        f"error_count: {int(validation.get('error_count') or 0)}",
        f"warning_count: {int(validation.get('warning_count') or 0)}",
        f"approved_count: {int(summary.get('approved_count') or 0)}",
        f"needs_revision_count: {int(summary.get('needs_revision_count') or 0)}",
        f"rejected_count: {int(summary.get('rejected_count') or 0)}",
        f"pending_count: {int(summary.get('pending_count') or 0)}",
        f"publish_allowed: {'true' if validation.get('publish_allowed') else 'false'}",
        f"write_to_database: {'true' if validation.get('write_to_database') else 'false'}",
        f"decision_fingerprint_algorithm: {decision_fingerprint.get('algorithm') or ''}",
        f"decision_fingerprint_digest: {decision_fingerprint.get('digest') or ''}",
        "",
        "## Errors",
        "",
    ]
    errors = validation.get("errors") if isinstance(validation.get("errors"), list) else []
    if not errors:
        lines.append("- none")
    for error in errors:
        if not isinstance(error, dict):
            continue
        source_case_id = str(error.get("source_case_id") or error.get("question_pattern") or "")
        lines.append(f"- `{error.get('code') or ''}` {source_case_id}: {error.get('message') or ''}")
        missing_fields = error.get("missing_fields") if isinstance(error.get("missing_fields"), list) else []
        if missing_fields:
            lines.append(f"  - missing_fields: {', '.join(str(field) for field in missing_fields)}")

    lines.extend(["", "## Decisions", ""])
    items = summary.get("items") if isinstance(summary.get("items"), list) else []
    if not items:
        lines.append("- none")
    for item in items:
        if not isinstance(item, dict):
            continue
        lines.append(
            f"- `{item.get('source_case_id') or ''}` action=`{item.get('action') or ''}` "
            f"reviewer={item.get('reviewer') or ''}"
        )
        note = str(item.get("note") or "")
        if note:
            lines.append(f"  - note: {note}")

    lines.extend(
        [
            "",
            "## Publication Preflight",
            "",
            f"approved_decision_count: {int(publication_preflight.get('approved_decision_count') or 0)}",
            f"ready_count: {int(publication_preflight.get('ready_count') or 0)}",
            f"blocked_count: {int(publication_preflight.get('blocked_count') or 0)}",
            f"publish_allowed: {'true' if publication_preflight.get('publish_allowed') else 'false'}",
            "",
        ]
    )
    preflight_items = (
        publication_preflight.get("items")
        if isinstance(publication_preflight.get("items"), list)
        else []
    )
    if not preflight_items:
        lines.append("- none")
    for item in preflight_items:
        if not isinstance(item, dict):
            continue
        lines.append(
            f"- `{item.get('source_case_id') or ''}` status=`{item.get('status') or ''}` "
            f"manual_publication_ready={'true' if item.get('manual_publication_ready') else 'false'}"
        )
        missing_fields = item.get("missing_fields") if isinstance(item.get("missing_fields"), list) else []
        if missing_fields:
            lines.append(f"  - missing_fields: {', '.join(str(field) for field in missing_fields)}")
    lines.append("")
    return "\n".join(lines)


def render_p0_decision_edit_guide_markdown(
    review_packet: dict[str, Any],
    decisions_payload: dict[str, Any],
) -> str:
    packet_items = review_packet.get("items") if isinstance(review_packet.get("items"), list) else []
    review_packet_fingerprint = _json_fingerprint(review_packet)
    decision_fingerprint = _json_fingerprint(decisions_payload)
    decisions_by_case_id = _items_by_source_case_id(decisions_payload)
    pending_items: list[dict[str, Any]] = []
    for item in packet_items:
        if not isinstance(item, dict):
            continue
        source_case_id = str(item.get("source_case_id") or "")
        decision = decisions_by_case_id.get(source_case_id, {})
        action = str(decision.get("action") or "pending")
        if action == "pending":
            pending_items.append(item)

    lines = [
        "# HXY P0 Decision Edit Guide",
        "",
        "This guide does not approve, publish, or import answer cards.",
        "",
        f"item_count: {len(packet_items)}",
        f"pending_count: {len(pending_items)}",
        "publish_allowed: false",
        "write_to_database: false",
        f"review_packet_fingerprint_algorithm: {review_packet_fingerprint['algorithm']}",
        f"review_packet_fingerprint_digest: {review_packet_fingerprint['digest']}",
        f"decision_fingerprint_algorithm: {decision_fingerprint['algorithm']}",
        f"decision_fingerprint_digest: {decision_fingerprint['digest']}",
        "",
        "## Allowed Actions",
        "",
        "- `approve`: only after the answer text and all publication metadata are manually confirmed.",
        "- `needs_revision`: use when the draft is directionally useful but still needs source, wording, or risk fixes.",
        "- `reject`: use when the draft should not move toward publication.",
        "",
        "## Pending Decisions",
        "",
    ]
    if not pending_items:
        lines.append("- none")
    required_metadata = ", ".join(P0_PUBLICATION_REQUIRED_METADATA_FIELDS)
    for item in pending_items:
        source_case_id = str(item.get("source_case_id") or "")
        source_task_id = str(item.get("source_task_id") or "")
        question = str(item.get("question_pattern") or "")
        lines.extend(
            [
                f"- `{source_case_id}` current_action=`pending`",
                f"  - source_task_id: `{source_task_id}`",
                f"  - question: {question}",
                f"  - edit_target: p0-review-decisions.json items[source_case_id={source_case_id}]",
                f"  - required_metadata: {required_metadata}",
                "  - allowed_actions: approve, needs_revision, reject",
            ]
        )
    lines.append("")
    return "\n".join(lines)


def render_p0_review_decisions_audit_markdown(audit: dict[str, Any]) -> str:
    audit_fingerprint = _json_fingerprint(audit)
    sample_fingerprint = audit.get("sample_fingerprint") if isinstance(audit.get("sample_fingerprint"), dict) else {}
    decision_fingerprint = audit.get("decision_fingerprint") if isinstance(audit.get("decision_fingerprint"), dict) else {}
    lines = [
        "# HXY P0 Review Decisions Audit",
        "",
        "This audit does not approve, publish, or import answer cards.",
        "",
        f"audit_fingerprint_algorithm: {audit_fingerprint['algorithm']}",
        f"audit_fingerprint_digest: {audit_fingerprint['digest']}",
        f"sample_fingerprint_algorithm: {sample_fingerprint.get('algorithm') or 'sha256'}",
        f"sample_fingerprint_digest: {sample_fingerprint.get('digest') or ''}",
        f"decision_fingerprint_algorithm: {decision_fingerprint.get('algorithm') or 'sha256'}",
        f"decision_fingerprint_digest: {decision_fingerprint.get('digest') or ''}",
        f"item_count: {int(audit.get('item_count') or 0)}",
        f"changed_count: {int(audit.get('changed_count') or 0)}",
        f"pending_count: {int(audit.get('pending_count') or 0)}",
        f"metadata_gap_count: {int(audit.get('metadata_gap_count') or 0)}",
        f"publish_allowed: {'true' if audit.get('publish_allowed') else 'false'}",
        f"write_to_database: {'true' if audit.get('write_to_database') else 'false'}",
        "",
        "## Items",
        "",
    ]
    items = audit.get("items") if isinstance(audit.get("items"), list) else []
    if not items:
        lines.append("- none")
    for item in items:
        if not isinstance(item, dict):
            continue
        line = (
            f"- `{item.get('source_case_id') or ''}` "
            f"{item.get('sample_action') or ''} -> {item.get('current_action') or ''} "
            f"changed={'true' if item.get('changed') else 'false'}"
        )
        metadata_status = str(item.get("metadata_status") or "")
        if metadata_status and metadata_status != "not_required":
            line = f"{line} metadata_status={metadata_status}"
        lines.append(line)
        missing_fields = item.get("missing_fields") if isinstance(item.get("missing_fields"), list) else []
        if missing_fields:
            lines.append(f"  - missing_fields: {', '.join(str(field) for field in missing_fields)}")
    lines.append("")
    return "\n".join(lines)


def render_p0_reviewer_worksheet_markdown(
    review_packet: dict[str, Any],
    decisions_payload: dict[str, Any],
    audit: dict[str, Any],
) -> str:
    packet_items = review_packet.get("items") if isinstance(review_packet.get("items"), list) else []
    decision_items = decisions_payload.get("items") if isinstance(decisions_payload.get("items"), list) else []
    decisions_by_case_id = _items_by_source_case_id(decisions_payload)
    audit_items = audit.get("items") if isinstance(audit.get("items"), list) else []
    audit_by_case_id = {
        str(item.get("source_case_id") or ""): item
        for item in audit_items
        if isinstance(item, dict) and str(item.get("source_case_id") or "")
    }
    pending_count = len(
        [
            item
            for item in decision_items
            if isinstance(item, dict) and str(item.get("action") or "pending") == "pending"
        ]
    )
    actioned_count = len(
        [
            item
            for item in decision_items
            if isinstance(item, dict) and str(item.get("action") or "pending") in {"approve", "reject", "needs_revision"}
        ]
    )
    review_packet_fingerprint = _json_fingerprint(review_packet)
    decision_fingerprint = _json_fingerprint(decisions_payload)
    audit_fingerprint = _json_fingerprint(audit)
    required_metadata = ", ".join(P0_PUBLICATION_REQUIRED_METADATA_FIELDS)

    lines = [
        "# HXY P0 Reviewer Worksheet",
        "",
        "This worksheet does not approve, publish, import, or write answer cards.",
        "",
        f"item_count: {len(packet_items)}",
        f"pending_count: {pending_count}",
        f"actioned_count: {actioned_count}",
        "publish_allowed: false",
        "write_to_database: false",
        f"review_packet_fingerprint_algorithm: {review_packet_fingerprint['algorithm']}",
        f"review_packet_fingerprint_digest: {review_packet_fingerprint['digest']}",
        f"decision_fingerprint_algorithm: {decision_fingerprint['algorithm']}",
        f"decision_fingerprint_digest: {decision_fingerprint['digest']}",
        f"audit_fingerprint_algorithm: {audit_fingerprint['algorithm']}",
        f"audit_fingerprint_digest: {audit_fingerprint['digest']}",
        "",
    ]

    for item in packet_items:
        if not isinstance(item, dict):
            continue
        source_case_id = str(item.get("source_case_id") or "")
        source_task_id = str(item.get("source_task_id") or "")
        decision = decisions_by_case_id.get(source_case_id, {})
        audit_item = audit_by_case_id.get(source_case_id, {})
        current_action = str(decision.get("action") or "pending")
        question = str(item.get("question_pattern") or "")
        risk_flags = item.get("risk_flags") if isinstance(item.get("risk_flags"), list) else []
        review_questions = item.get("review_questions") if isinstance(item.get("review_questions"), list) else []
        approval_conditions = (
            item.get("approval_conditions") if isinstance(item.get("approval_conditions"), list) else []
        )
        rejection_conditions = (
            item.get("rejection_conditions") if isinstance(item.get("rejection_conditions"), list) else []
        )

        lines.extend(
            [
                f"## Case: {source_case_id}",
                "",
                f"- Source task: `{source_task_id}`",
                f"- Current action: `{current_action}`",
                f"- Audit changed: {'true' if audit_item.get('changed') else 'false'}",
                f"- Metadata status: `{audit_item.get('metadata_status') or 'not_required'}`",
                f"- Question: {question}",
                f"- Edit target: `p0-review-decisions.json` item where `source_case_id={source_case_id}`",
                f"- Allowed actions: {', '.join(P0_REVIEW_DECISION_ALLOWED_ACTIONS)}",
                f"- Required metadata for `approve`: {required_metadata}",
                "",
            ]
        )
        if risk_flags:
            lines.extend(["### Risk Flags", ""])
            lines.extend([f"- {flag}" for flag in risk_flags])
            lines.append("")
        draft_answer = str(item.get("draft_answer") or "")
        if draft_answer:
            lines.extend(["### Draft Answer", "", draft_answer, ""])
        if review_questions:
            lines.extend(["### Review Questions", ""])
            lines.extend([f"- {question}" for question in review_questions])
            lines.append("")
        if approval_conditions:
            lines.extend(["### Approval Conditions", ""])
            lines.extend([f"- {condition}" for condition in approval_conditions])
            lines.append("")
        if rejection_conditions:
            lines.extend(["### Rejection Conditions", ""])
            lines.extend([f"- {condition}" for condition in rejection_conditions])
            lines.append("")
        decision_template = item.get("decision_template") if isinstance(item.get("decision_template"), dict) else {}
        if decision_template:
            lines.extend(
                [
                    "### Decision Template",
                    "",
                    "```json",
                    json.dumps(decision_template, ensure_ascii=False, indent=2),
                    "```",
                    "",
                ]
            )
    return "\n".join(lines)


def build_p0_reviewer_todo(
    review_packet: dict[str, Any],
    decisions_payload: dict[str, Any],
    audit: dict[str, Any],
) -> dict[str, Any]:
    packet_items = review_packet.get("items") if isinstance(review_packet.get("items"), list) else []
    decision_items = decisions_payload.get("items") if isinstance(decisions_payload.get("items"), list) else []
    decisions_by_case_id = _items_by_source_case_id(decisions_payload)
    audit_items = audit.get("items") if isinstance(audit.get("items"), list) else []
    audit_by_case_id = {
        str(item.get("source_case_id") or ""): item
        for item in audit_items
        if isinstance(item, dict) and str(item.get("source_case_id") or "")
    }
    items: list[dict[str, Any]] = []
    for item in packet_items:
        if not isinstance(item, dict):
            continue
        source_case_id = str(item.get("source_case_id") or "")
        source_task_id = str(item.get("source_task_id") or "")
        decision = decisions_by_case_id.get(source_case_id, {})
        audit_item = audit_by_case_id.get(source_case_id, {})
        current_action = str(decision.get("action") or "pending")
        items.append(
            {
                "source_case_id": source_case_id,
                "source_task_id": source_task_id,
                "question_pattern": item.get("question_pattern") or "",
                "current_action": current_action,
                "audit_changed": bool(audit_item.get("changed")),
                "metadata_status": audit_item.get("metadata_status") or "not_required",
                "risk_flags": item.get("risk_flags") if isinstance(item.get("risk_flags"), list) else [],
                "review_questions": (
                    item.get("review_questions") if isinstance(item.get("review_questions"), list) else []
                ),
                "approval_conditions": (
                    item.get("approval_conditions") if isinstance(item.get("approval_conditions"), list) else []
                ),
                "rejection_conditions": (
                    item.get("rejection_conditions") if isinstance(item.get("rejection_conditions"), list) else []
                ),
                "required_metadata_for_approve": P0_PUBLICATION_REQUIRED_METADATA_FIELDS,
                "edit_target": f"p0-review-decisions.json items[source_case_id={source_case_id}]",
                "next_human_action": "choose approve, reject, or needs_revision manually",
                "official_use_allowed": False,
                "publish_allowed": False,
                "write_to_database": False,
            }
        )
    pending_count = len(
        [
            item
            for item in decision_items
            if isinstance(item, dict) and str(item.get("action") or "pending") == "pending"
        ]
    )
    actioned_count = len(
        [
            item
            for item in decision_items
            if isinstance(item, dict) and str(item.get("action") or "pending") in {"approve", "reject", "needs_revision"}
        ]
    )
    return {
        "version": "hxy-p0-reviewer-todo.v1",
        "review_packet_fingerprint": _json_fingerprint(review_packet),
        "decision_fingerprint": _json_fingerprint(decisions_payload),
        "audit_fingerprint": _json_fingerprint(audit),
        "item_count": len(items),
        "pending_count": pending_count,
        "actioned_count": actioned_count,
        "items": items,
        "official_use_allowed": False,
        "publish_allowed": False,
        "write_to_database": False,
        "requires_human_review": True,
        "authority_rule": "p0_reviewer_todo_does_not_publish_approved_cards",
    }


def _draft_by_source_case_id(draft_pack: dict[str, Any]) -> dict[str, dict[str, Any]]:
    drafts = draft_pack.get("items") if isinstance(draft_pack.get("items"), list) else []
    return {str(draft.get("source_case_id") or ""): draft for draft in drafts if isinstance(draft, dict)}


def _publication_candidate_from_preflight_item(
    item: dict[str, Any],
    draft: dict[str, Any],
) -> dict[str, Any]:
    source_case_id = str(item.get("source_case_id") or "")
    source_task_id = str(item.get("source_task_id") or "")
    metadata = item.get("publication_metadata") if isinstance(item.get("publication_metadata"), dict) else {}
    proposed_card = {
        "card_id": f"pending:p0:{source_case_id}",
        "source_case_id": source_case_id,
        "source_task_id": source_task_id,
        "question_pattern": draft.get("question_pattern") or "",
        "aliases": [],
        "intent": draft.get("intent") or "risk_boundary",
        "audience": draft.get("audience") or "store_staff",
        "answer": draft.get("answer") or "",
        "status": "pending_manual_publication",
        "target_status_after_manual_publish": "approved",
        "review_status_after_manual_publish": "approved_v1",
        "source": "p0_approved_card_publication_package",
        "publication_metadata": metadata,
        "evidence": [
            {
                "title": f"P0 人工审核发布包：{source_case_id}",
                "domain": draft.get("intent") or "risk_boundary",
                "status": "pending_manual_publication",
                "source_type": "manual_publication_package",
                "owner": metadata.get("responsible_owner") or "",
                "version": metadata.get("knowledge_version") or "",
                "source_references": metadata.get("source_references") or [],
                "effective_scope": metadata.get("effective_scope") or "",
                "risk_review_status": metadata.get("risk_review_status") or "",
            }
        ],
    }
    return {
        "source_case_id": source_case_id,
        "source_task_id": source_task_id,
        "manual_publication_ready": True,
        "proposed_card": proposed_card,
        "official_use_allowed": False,
        "publish_allowed": False,
        "write_to_formal_store": False,
        "requires_human_review": True,
        "authority_rule": "publication_package_does_not_publish_approved_cards",
    }


def build_p0_approved_card_publication_package(
    draft_pack: dict[str, Any],
    validation: dict[str, Any],
) -> dict[str, Any]:
    preflight = validation.get("publication_preflight") if isinstance(validation.get("publication_preflight"), dict) else {}
    preflight_items = preflight.get("items") if isinstance(preflight.get("items"), list) else []
    drafts_by_case_id = _draft_by_source_case_id(draft_pack)
    publication_candidates: list[dict[str, Any]] = []
    blocked_items: list[dict[str, Any]] = []

    for item in preflight_items:
        if not isinstance(item, dict):
            continue
        source_case_id = str(item.get("source_case_id") or "")
        if item.get("manual_publication_ready") is True:
            draft = drafts_by_case_id.get(source_case_id, {})
            publication_candidates.append(_publication_candidate_from_preflight_item(item, draft))
            continue
        blocked_items.append(
            {
                "source_case_id": source_case_id,
                "source_task_id": item.get("source_task_id") or "",
                "status": item.get("status") or "blocked",
                "missing_fields": item.get("missing_fields") or [],
                "official_use_allowed": False,
                "publish_allowed": False,
                "write_to_formal_store": False,
                "authority_rule": "publication_package_does_not_publish_approved_cards",
            }
        )

    return {
        "version": "hxy-p0-approved-card-publication-package.v1",
        "validation_fingerprint": _json_fingerprint(validation),
        "draft_pack_fingerprint": _json_fingerprint(draft_pack),
        "candidate_count": len(publication_candidates),
        "blocked_count": len(blocked_items),
        "publication_candidates": publication_candidates,
        "blocked_items": blocked_items,
        "official_use_allowed": False,
        "publish_allowed": False,
        "write_to_formal_store": False,
        "requires_human_review": True,
        "authority_rule": "publication_package_does_not_publish_approved_cards",
    }


P0_DRY_RUN_REQUIRED_ANSWER_CARD_FIELDS = ["question_pattern", "intent", "audience", "answer"]


def _missing_answer_card_fields(card: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    for field in P0_DRY_RUN_REQUIRED_ANSWER_CARD_FIELDS:
        value = card.get(field)
        if value is None or value == "" or value == []:
            missing.append(field)
    return missing


def _draft_answer_card_payload_from_publication_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    proposed_card = candidate.get("proposed_card") if isinstance(candidate.get("proposed_card"), dict) else {}
    return {
        "question_pattern": proposed_card.get("question_pattern") or "",
        "intent": proposed_card.get("intent") or "risk_boundary",
        "audience": proposed_card.get("audience") or "store_staff",
        "answer": proposed_card.get("answer") or "",
        "reasoning": ["由 P0 人工发布包 dry-run 生成；未手动写入前不能作为权威答案。"],
        "evidence": proposed_card.get("evidence") if isinstance(proposed_card.get("evidence"), list) else [],
        "corrections": [],
        "next_actions": ["由负责人手动写入正式 answer card 后，再标记 approved。"],
        "status": "draft",
        "source_answer_id": proposed_card.get("card_id") or "",
        "target_status_after_manual_publish": proposed_card.get("target_status_after_manual_publish") or "approved",
        "review_status_after_manual_publish": proposed_card.get("review_status_after_manual_publish") or "approved_v1",
        "publication_metadata": proposed_card.get("publication_metadata") if isinstance(proposed_card.get("publication_metadata"), dict) else {},
        "official_use_allowed": False,
        "publish_allowed": False,
        "write_to_formal_store": False,
    }


def dry_run_p0_approved_card_publication_package(publication_package: dict[str, Any]) -> dict[str, Any]:
    candidates = (
        publication_package.get("publication_candidates")
        if isinstance(publication_package.get("publication_candidates"), list)
        else []
    )
    errors: list[dict[str, Any]] = []
    payloads: list[dict[str, Any]] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        source_case_id = str(candidate.get("source_case_id") or "")
        source_task_id = str(candidate.get("source_task_id") or "")
        proposed_card = candidate.get("proposed_card") if isinstance(candidate.get("proposed_card"), dict) else {}
        missing_card_fields = _missing_answer_card_fields(proposed_card)
        if missing_card_fields:
            errors.append(
                {
                    "code": "missing_answer_card_fields",
                    "source_case_id": source_case_id,
                    "source_task_id": source_task_id,
                    "missing_fields": missing_card_fields,
                    "message": "Publication candidate cannot become an answer card payload because required fields are missing.",
                }
            )
        metadata = proposed_card.get("publication_metadata") if isinstance(proposed_card.get("publication_metadata"), dict) else {}
        missing_metadata = _missing_publication_metadata_fields(metadata)
        if missing_metadata:
            errors.append(
                {
                    "code": "missing_publication_metadata",
                    "source_case_id": source_case_id,
                    "source_task_id": source_task_id,
                    "missing_fields": missing_metadata,
                    "message": "Publication candidate is missing required publication metadata.",
                }
            )
        if not missing_card_fields and not missing_metadata:
            payloads.append(_draft_answer_card_payload_from_publication_candidate(candidate))

    return {
        "version": "hxy-p0-approved-card-publication-dry-run.v1",
        "publication_package_fingerprint": _json_fingerprint(publication_package),
        "valid": len(errors) == 0,
        "candidate_count": len(candidates),
        "payload_count": len(payloads),
        "would_write_count": 0,
        "error_count": len(errors),
        "warning_count": 0,
        "errors": errors,
        "warnings": [],
        "draft_answer_card_payloads": payloads,
        "official_use_allowed": False,
        "publish_allowed": False,
        "write_to_formal_store": False,
        "requires_human_review": True,
        "authority_rule": "publication_dry_run_does_not_publish_approved_cards",
    }


def _reviewed_answer_card_from_draft_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "question_pattern": payload.get("question_pattern") or "",
        "intent": payload.get("intent") or "risk_boundary",
        "audience": payload.get("audience") or "store_staff",
        "answer": payload.get("answer") or "",
        "reasoning": payload.get("reasoning") if isinstance(payload.get("reasoning"), list) else [],
        "evidence": payload.get("evidence") if isinstance(payload.get("evidence"), list) else [],
        "corrections": payload.get("corrections") if isinstance(payload.get("corrections"), list) else [],
        "next_actions": payload.get("next_actions") if isinstance(payload.get("next_actions"), list) else [],
        "status": payload.get("target_status_after_manual_publish") or "approved",
        "review_status": payload.get("review_status_after_manual_publish") or "approved_v1",
        "source_answer_id": payload.get("source_answer_id") or "",
        "source": "p0_reviewed_file_publication",
        "publication_metadata": payload.get("publication_metadata") if isinstance(payload.get("publication_metadata"), dict) else {},
    }


def publish_p0_dry_run_answer_cards_to_reviewed_file(
    dry_run: dict[str, Any],
    *,
    confirm_manual_publication: bool,
) -> dict[str, Any]:
    if confirm_manual_publication is not True:
        return {
            "version": "hxy-p0-reviewed-answer-cards-publication.v1",
            "dry_run_fingerprint": _json_fingerprint(dry_run),
            "published": False,
            "published_count": 0,
            "error_count": 1,
            "errors": [
                {
                    "code": "missing_manual_publication_confirmation",
                    "message": "Pass --confirm-manual-publication to write the reviewed answer cards file.",
                }
            ],
            "reviewed_answer_cards": [],
            "write_to_database": False,
            "requires_import_step": True,
            "official_use_allowed": False,
            "authority_rule": "reviewed_file_requires_separate_import_to_formal_store",
        }

    payloads = dry_run.get("draft_answer_card_payloads") if isinstance(dry_run.get("draft_answer_card_payloads"), list) else []
    reviewed_cards = [
        _reviewed_answer_card_from_draft_payload(payload)
        for payload in payloads
        if isinstance(payload, dict)
    ]
    return {
        "version": "hxy-p0-reviewed-answer-cards-publication.v1",
        "dry_run_fingerprint": _json_fingerprint(dry_run),
        "published": True,
        "published_count": len(reviewed_cards),
        "error_count": 0,
        "errors": [],
        "reviewed_answer_cards": reviewed_cards,
        "write_to_database": False,
        "requires_import_step": True,
        "official_use_allowed": True,
        "authority_rule": "reviewed_file_requires_separate_import_to_formal_store",
    }


def _normalize_import_key(value: str) -> str:
    stop_chars = "，。！？?；;：:、（）()[]【】\"'“”‘’"
    normalized = str(value or "")
    for char in stop_chars:
        normalized = normalized.replace(char, "")
    return "".join(normalized.split()).lower()


def _existing_card_keys(existing_cards: list[dict[str, Any]]) -> tuple[set[tuple[str, str]], set[str]]:
    question_intent_keys: set[tuple[str, str]] = set()
    source_answer_ids: set[str] = set()
    for card in existing_cards:
        if not isinstance(card, dict):
            continue
        if str(card.get("status") or "") != "approved":
            continue
        question_key = _normalize_import_key(str(card.get("question_pattern") or ""))
        intent_key = _normalize_import_key(str(card.get("intent") or ""))
        if question_key or intent_key:
            question_intent_keys.add((question_key, intent_key))
        source_answer_id = str(card.get("source_answer_id") or "")
        if source_answer_id:
            source_answer_ids.add(source_answer_id)
    return question_intent_keys, source_answer_ids


def _reviewed_card_errors(card: dict[str, Any]) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    missing_fields = _missing_answer_card_fields(card)
    if missing_fields:
        errors.append(
            {
                "code": "missing_answer_card_fields",
                "question_pattern": card.get("question_pattern") or "",
                "intent": card.get("intent") or "",
                "missing_fields": missing_fields,
            }
        )
    if card.get("status") != "approved" or card.get("review_status") != "approved_v1":
        errors.append(
            {
                "code": "invalid_reviewed_card_status",
                "question_pattern": card.get("question_pattern") or "",
                "intent": card.get("intent") or "",
                "status": card.get("status") or "",
                "review_status": card.get("review_status") or "",
            }
        )
    metadata = card.get("publication_metadata") if isinstance(card.get("publication_metadata"), dict) else {}
    missing_metadata = _missing_publication_metadata_fields(metadata)
    if missing_metadata:
        errors.append(
            {
                "code": "missing_publication_metadata",
                "question_pattern": card.get("question_pattern") or "",
                "intent": card.get("intent") or "",
                "missing_fields": missing_metadata,
            }
        )
    return errors


def validate_p0_reviewed_answer_cards_import_gate(
    reviewed_file: dict[str, Any],
    existing_cards: list[dict[str, Any]],
) -> dict[str, Any]:
    reviewed_cards = (
        reviewed_file.get("reviewed_answer_cards")
        if isinstance(reviewed_file.get("reviewed_answer_cards"), list)
        else []
    )
    existing_question_intent_keys, existing_source_answer_ids = _existing_card_keys(existing_cards)
    seen_question_intent_keys: set[tuple[str, str]] = set()
    seen_source_answer_ids: set[str] = set()
    errors: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    importable_cards: list[dict[str, Any]] = []

    for card in reviewed_cards:
        if not isinstance(card, dict):
            continue
        card_errors = _reviewed_card_errors(card)
        if card_errors:
            errors.extend(card_errors)
            continue

        question_pattern = str(card.get("question_pattern") or "")
        intent = str(card.get("intent") or "")
        question_intent_key = (_normalize_import_key(question_pattern), _normalize_import_key(intent))
        source_answer_id = str(card.get("source_answer_id") or "")
        card_conflicts: list[dict[str, Any]] = []
        if question_intent_key in existing_question_intent_keys or question_intent_key in seen_question_intent_keys:
            card_conflicts.append(
                {
                    "code": "duplicate_question_intent",
                    "question_pattern": question_pattern,
                    "intent": intent,
                    "message": "Reviewed card conflicts with an existing or same-batch approved question/intent.",
                }
            )
        if source_answer_id and (source_answer_id in existing_source_answer_ids or source_answer_id in seen_source_answer_ids):
            card_conflicts.append(
                {
                    "code": "duplicate_source_answer_id",
                    "question_pattern": question_pattern,
                    "intent": intent,
                    "source_answer_id": source_answer_id,
                    "message": "Reviewed card conflicts with an existing or same-batch source_answer_id.",
                }
            )
        if card_conflicts:
            conflicts.extend(card_conflicts)
            continue
        seen_question_intent_keys.add(question_intent_key)
        if source_answer_id:
            seen_source_answer_ids.add(source_answer_id)
        importable_cards.append(card)

    valid = not errors and not conflicts
    return {
        "version": "hxy-p0-reviewed-answer-cards-import-gate.v1",
        "reviewed_file_fingerprint": _json_fingerprint(reviewed_file),
        "existing_answer_cards_fingerprint": _json_fingerprint({"items": existing_cards}),
        "valid": valid,
        "reviewed_card_count": len(reviewed_cards),
        "importable_count": len(importable_cards),
        "conflict_count": len(conflicts),
        "error_count": len(errors),
        "would_import_count": 0,
        "errors": errors,
        "conflicts": conflicts,
        "importable_answer_cards": importable_cards,
        "write_to_database": False,
        "requires_import_confirmation": True,
        "authority_rule": "import_gate_checks_only_and_does_not_write_database",
    }


def _read_json_if_exists(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_markdown_fingerprints(path: Path) -> dict[str, dict[str, str]]:
    if not path.is_file():
        return {}
    fingerprints: dict[str, dict[str, str]] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        for name in ["audit", "decision", "review_packet", "sample"]:
            algorithm_prefix = f"{name}_fingerprint_algorithm:"
            digest_prefix = f"{name}_fingerprint_digest:"
            if line.startswith(algorithm_prefix):
                fingerprints.setdefault(name, {})["algorithm"] = line.split(":", 1)[1].strip()
            if line.startswith(digest_prefix):
                fingerprints.setdefault(name, {})["digest"] = line.split(":", 1)[1].strip()
    return {
        name: {"algorithm": values.get("algorithm") or "sha256", "digest": values.get("digest") or ""}
        for name, values in fingerprints.items()
        if values.get("digest")
    }


def _read_decision_report_fingerprint(path: Path) -> dict[str, str]:
    return _read_markdown_fingerprints(path).get("decision", {})


def _governance_status_payload(
    *,
    current_step: str,
    missing_files: list[str],
    next_action: str,
    next_command: str,
    blocked: bool = True,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "version": "hxy-p0-governance-status.v1",
        "current_step": current_step,
        "blocked": blocked,
        "missing_files": missing_files,
        "next_action": next_action,
        "next_command": next_command,
        "details": details or {},
        "write_to_database": False,
        "authority_rule": "status_check_is_read_only",
    }


def _stale_governance_artifact_status(
    *,
    current_step: str,
    stale_file: str,
    upstream_name: str,
    current_upstream_payload: dict[str, Any],
    artifact_payload: dict[str, Any],
    artifact_fingerprint_field: str,
    next_action: str,
    next_command: str,
) -> dict[str, Any] | None:
    current_fingerprint = _json_fingerprint(current_upstream_payload)
    artifact_fingerprint = (
        artifact_payload.get(artifact_fingerprint_field)
        if isinstance(artifact_payload.get(artifact_fingerprint_field), dict)
        else {}
    )
    if artifact_fingerprint.get("digest") == current_fingerprint["digest"]:
        return None
    return _governance_status_payload(
        current_step=current_step,
        missing_files=[],
        next_action=next_action,
        next_command=next_command,
        details={
            "stale_file": stale_file,
            "upstream_name": upstream_name,
            "current_upstream_digest": current_fingerprint["digest"],
            "artifact_upstream_digest": artifact_fingerprint.get("digest") or "",
            "artifact_fingerprint_field": artifact_fingerprint_field,
        },
    )


def build_p0_governance_status(
    run_dir: str | Path,
    *,
    benchmark_path: str | Path = "knowledge/benchmarks/hxy-brain-benchmark-v1.json",
    report_path: str | Path = "knowledge/reports/benchmark-latest.json",
) -> dict[str, Any]:
    run_root = Path(run_dir)
    run_id = run_root.name
    runs_dir = run_root.parent
    benchmark = Path(benchmark_path).as_posix()
    report = Path(report_path).as_posix()

    stub = run_root / "p0-review-decisions.stub.json"
    sample = run_root / "p0-review-decisions.sample.json"
    review_packet_json = run_root / "p0-manual-review-packet.json"
    review_packet_md = run_root / "p0-manual-review-packet.md"
    decisions = run_root / "p0-review-decisions.json"
    validation = run_root / "p0-review-decisions.validation.json"
    decision_report = run_root / "p0-review-decisions.report.md"
    decision_audit = run_root / "p0-review-decisions.audit.json"
    decision_audit_md = run_root / "p0-review-decisions.audit.md"
    preflight = run_root / "p0-publication-preflight.json"
    package = run_root / "p0-approved-card-publication-package.json"
    dry_run = run_root / "p0-approved-card-publication-dry-run.json"
    reviewed = run_root / "published-answer-cards.reviewed.json"
    existing = run_root / "existing-answer-cards.json"
    import_gate = run_root / "reviewed-answer-cards.import-gate.json"

    if not stub.is_file():
        return _governance_status_payload(
            current_step="missing_stub",
            missing_files=[stub.name],
            next_action="Run benchmark improvement loop to create the P0 review decision stub.",
            next_command=(
                f".venv/bin/python scripts/run-hxy-loop.py benchmark_improvement "
                f"--benchmark {benchmark} --report {report} --run-id {run_id} "
                f"--runs-dir {runs_dir.as_posix()} --max-iterations 1"
            ),
        )

    if not sample.is_file():
        return _governance_status_payload(
            current_step="needs_sample",
            missing_files=[sample.name],
            next_action="Generate an editable manual decision sample from the stub.",
            next_command=(
                f".venv/bin/python scripts/validate-hxy-p0-review-decisions.py sample "
                f"--stub {stub.as_posix()} --output {sample.as_posix()}"
            ),
        )

    if not decisions.is_file():
        if not review_packet_json.is_file() or not review_packet_md.is_file():
            missing_review_packet = [
                path.name
                for path in [review_packet_json, review_packet_md]
                if not path.is_file()
            ]
            return _governance_status_payload(
                current_step="needs_manual_review_packet",
                missing_files=missing_review_packet,
                next_action="Create a read-only manual review packet before filling p0-review-decisions.json.",
                next_command=(
                    f".venv/bin/python scripts/validate-hxy-p0-review-decisions.py review-packet "
                    f"--stub {stub.as_posix()} "
                    f"--drafts {(run_root / 'p0-authority-card-drafts.json').as_posix()} "
                    f"--manifest {(run_root / 'p0-draft-review-manifest.json').as_posix()} "
                    f"--sample {sample.as_posix()} "
                    f"--output-json {review_packet_json.as_posix()} "
                    f"--output-md {review_packet_md.as_posix()}"
                ),
            )
        return _governance_status_payload(
            current_step="awaiting_manual_decisions",
            missing_files=[decisions.name],
            next_action=(
                f"Review {review_packet_md.as_posix()}, initialize p0-review-decisions.json from the sample, "
                "then edit it manually."
            ),
            next_command=(
                f".venv/bin/python scripts/validate-hxy-p0-review-decisions.py init-decisions "
                f"--sample {sample.as_posix()} --output {decisions.as_posix()}"
            ),
        )

    validate_command = (
        f".venv/bin/python scripts/validate-hxy-p0-review-decisions.py validate "
        f"--stub {stub.as_posix()} --decisions {decisions.as_posix()} "
        f"--output {validation.as_posix()}"
    )
    decision_stub_payload = _read_json_if_exists(stub)
    decisions_payload = _read_json_if_exists(decisions)
    decision_summary = _build_p0_review_decision_summary(decision_stub_payload, decisions_payload)
    decision_report_command = (
        f".venv/bin/python scripts/validate-hxy-p0-review-decisions.py decision-report "
        f"--stub {stub.as_posix()} --decisions {decisions.as_posix()} "
        f"--output-json {validation.as_posix()} --output-md {decision_report.as_posix()}"
    )
    decision_edit_guide = run_root / "p0-decision-edit-guide.md"
    decision_edit_guide_command = (
        f".venv/bin/python scripts/validate-hxy-p0-review-decisions.py edit-guide "
        f"--packet {review_packet_json.as_posix()} --decisions {decisions.as_posix()} "
        f"--output-md {decision_edit_guide.as_posix()}"
    )
    reviewer_worksheet = run_root / "p0-reviewer-worksheet.md"
    reviewer_worksheet_command = (
        f".venv/bin/python scripts/validate-hxy-p0-review-decisions.py reviewer-worksheet "
        f"--packet {review_packet_json.as_posix()} --decisions {decisions.as_posix()} "
        f"--audit {decision_audit.as_posix()} --output-md {reviewer_worksheet.as_posix()}"
    )
    reviewer_todo = run_root / "p0-reviewer-todo.json"
    reviewer_todo_command = (
        f".venv/bin/python scripts/validate-hxy-p0-review-decisions.py reviewer-todo "
        f"--packet {review_packet_json.as_posix()} --decisions {decisions.as_posix()} "
        f"--audit {decision_audit.as_posix()} --output-json {reviewer_todo.as_posix()}"
    )
    decision_audit_command = (
        f".venv/bin/python scripts/validate-hxy-p0-review-decisions.py decision-audit "
        f"--sample {sample.as_posix()} --decisions {decisions.as_posix()} "
        f"--output-json {decision_audit.as_posix()} --output-md {decision_audit_md.as_posix()}"
    )
    actioned_count = (
        int(decision_summary.get("approved_count") or 0)
        + int(decision_summary.get("needs_revision_count") or 0)
        + int(decision_summary.get("rejected_count") or 0)
    )
    sample_payload = _read_json_if_exists(sample)
    current_sample_fingerprint = _json_fingerprint(sample_payload)
    current_decision_fingerprint = _json_fingerprint(decisions_payload)
    audit_payload = _read_json_if_exists(decision_audit)
    audit_decision_fingerprint = (
        audit_payload.get("decision_fingerprint")
        if isinstance(audit_payload.get("decision_fingerprint"), dict)
        else {}
    )
    audit_sample_fingerprint = (
        audit_payload.get("sample_fingerprint")
        if isinstance(audit_payload.get("sample_fingerprint"), dict)
        else {}
    )
    current_audit_fingerprint = _json_fingerprint(audit_payload)
    audit_markdown_fingerprints = _read_markdown_fingerprints(decision_audit_md)
    audit_markdown_audit_fingerprint = audit_markdown_fingerprints.get("audit", {})
    audit_status = "missing"
    audit_stale_file = ""
    audit_stale_upstream_name = ""
    if decision_audit.is_file() and decision_audit_md.is_file():
        audit_status = "fresh"
        if (
            audit_decision_fingerprint.get("digest") != current_decision_fingerprint["digest"]
            or audit_sample_fingerprint.get("digest") != current_sample_fingerprint["digest"]
        ):
            audit_status = "stale"
            stale_upstreams = []
            if audit_decision_fingerprint.get("digest") != current_decision_fingerprint["digest"]:
                stale_upstreams.append("p0-review-decisions.json")
            if audit_sample_fingerprint.get("digest") != current_sample_fingerprint["digest"]:
                stale_upstreams.append("p0-review-decisions.sample.json")
            audit_stale_upstream_name = ", ".join(stale_upstreams)
            audit_stale_file = decision_audit.name
        elif audit_markdown_audit_fingerprint.get("digest") != current_audit_fingerprint["digest"]:
            audit_status = "stale"
            audit_stale_file = decision_audit_md.name
            audit_stale_upstream_name = decision_audit.name
    if (
        int(decision_summary.get("decision_count") or 0) > 0
        and actioned_count == 0
        and int(decision_summary.get("invalid_decision_count") or 0) == 0
    ):
        review_packet_payload = _read_json_if_exists(review_packet_json)
        current_review_packet_fingerprint = _json_fingerprint(review_packet_payload)
        guide_fingerprints = _read_markdown_fingerprints(decision_edit_guide)
        guide_decision_fingerprint = guide_fingerprints.get("decision", {})
        guide_review_packet_fingerprint = guide_fingerprints.get("review_packet", {})
        guide_status = "missing"
        if decision_edit_guide.is_file():
            guide_status = "fresh"
            if (
                guide_decision_fingerprint.get("digest") != current_decision_fingerprint["digest"]
                or guide_review_packet_fingerprint.get("digest") != current_review_packet_fingerprint["digest"]
            ):
                guide_status = "stale"
        worksheet_fingerprints = _read_markdown_fingerprints(reviewer_worksheet)
        worksheet_decision_fingerprint = worksheet_fingerprints.get("decision", {})
        worksheet_review_packet_fingerprint = worksheet_fingerprints.get("review_packet", {})
        worksheet_audit_fingerprint = worksheet_fingerprints.get("audit", {})
        worksheet_status = "missing"
        if reviewer_worksheet.is_file():
            worksheet_status = "fresh"
            if (
                worksheet_decision_fingerprint.get("digest") != current_decision_fingerprint["digest"]
                or worksheet_review_packet_fingerprint.get("digest") != current_review_packet_fingerprint["digest"]
                or worksheet_audit_fingerprint.get("digest") != current_audit_fingerprint["digest"]
            ):
                worksheet_status = "stale"
        reviewer_todo_payload = _read_json_if_exists(reviewer_todo)
        todo_decision_fingerprint = (
            reviewer_todo_payload.get("decision_fingerprint")
            if isinstance(reviewer_todo_payload.get("decision_fingerprint"), dict)
            else {}
        )
        todo_review_packet_fingerprint = (
            reviewer_todo_payload.get("review_packet_fingerprint")
            if isinstance(reviewer_todo_payload.get("review_packet_fingerprint"), dict)
            else {}
        )
        todo_audit_fingerprint = (
            reviewer_todo_payload.get("audit_fingerprint")
            if isinstance(reviewer_todo_payload.get("audit_fingerprint"), dict)
            else {}
        )
        todo_status = "missing"
        if reviewer_todo.is_file():
            todo_status = "fresh"
            if (
                todo_decision_fingerprint.get("digest") != current_decision_fingerprint["digest"]
                or todo_review_packet_fingerprint.get("digest") != current_review_packet_fingerprint["digest"]
                or todo_audit_fingerprint.get("digest") != current_audit_fingerprint["digest"]
            ):
                todo_status = "stale"
        next_command = ""
        if guide_status != "fresh":
            next_command = decision_edit_guide_command
        elif audit_status != "fresh":
            next_command = decision_audit_command
        elif worksheet_status != "fresh":
            next_command = reviewer_worksheet_command
        elif todo_status != "fresh":
            next_command = reviewer_todo_command
        next_action = (
            f"Review {review_packet_md.as_posix()} and edit p0-review-decisions.json with at least one "
            "approve, reject, or needs_revision decision."
        )
        if todo_status == "fresh":
            next_action = (
                f"Use {reviewer_worksheet.as_posix()} or {reviewer_todo.as_posix()} to complete manual review, then edit "
                "p0-review-decisions.json with at least one approve, reject, or needs_revision decision."
            )
        elif worksheet_status == "fresh":
            next_action = f"Generate {reviewer_todo.as_posix()} for UI/Hermes review queues before manual decision."
        elif guide_status == "fresh":
            next_action = (
                f"Use {decision_edit_guide.as_posix()} to edit p0-review-decisions.json with at least one "
                "approve, reject, or needs_revision decision."
            )
        return _governance_status_payload(
            current_step="blocked_at_empty_manual_decisions",
            missing_files=[],
            next_action=next_action,
            next_command=next_command,
            details={
                "decision_count": int(decision_summary.get("decision_count") or 0),
                "pending_count": int(decision_summary.get("pending_count") or 0),
                "actioned_count": actioned_count,
                "pending_case_ids": [
                    str(item.get("source_case_id") or "")
                    for item in decision_summary.get("items", [])
                    if isinstance(item, dict) and item.get("action") == "pending"
                ],
                "decision_edit_guide_status": guide_status,
                "decision_edit_guide_path": decision_edit_guide.as_posix(),
                "decision_audit_status": audit_status,
                "decision_audit_path": decision_audit.as_posix(),
                "stale_file": audit_stale_file,
                "upstream_name": audit_stale_upstream_name,
                "decision_audit_changed_count": int(audit_payload.get("changed_count") or 0),
                "decision_audit_metadata_gap_count": int(audit_payload.get("metadata_gap_count") or 0),
                "reviewer_worksheet_status": worksheet_status,
                "reviewer_worksheet_path": reviewer_worksheet.as_posix(),
                "reviewer_todo_status": todo_status,
                "reviewer_todo_path": reviewer_todo.as_posix(),
            },
        )
    if actioned_count > 0 and audit_status != "fresh":
        missing_audit_files = [
            path.name
            for path in [decision_audit, decision_audit_md]
            if not path.is_file()
        ]
        return _governance_status_payload(
            current_step="needs_decision_audit" if audit_status == "missing" else "stale_decision_audit",
            missing_files=missing_audit_files,
            next_action="Run the read-only decision audit before validation.",
            next_command=decision_audit_command,
            details={
                "decision_audit_status": audit_status,
                "decision_audit_path": decision_audit.as_posix(),
                "stale_file": audit_stale_file,
                "upstream_name": audit_stale_upstream_name,
                "actioned_count": actioned_count,
                "pending_count": int(decision_summary.get("pending_count") or 0),
            },
        )
    if not validation.is_file():
        inline_validation = validate_p0_review_decisions(decision_stub_payload, decisions_payload)
        if inline_validation.get("valid") is False:
            return _governance_status_payload(
                current_step="blocked_at_decision_validation",
                missing_files=[validation.name],
                next_action="Fix p0-review-decisions.json according to inline validation errors.",
                next_command=validate_command,
                details={
                    "error_count": int(inline_validation.get("error_count") or 0),
                    "errors": inline_validation.get("errors") or [],
                },
            )
        return _governance_status_payload(
            current_step="needs_decision_validation",
            missing_files=[validation.name],
            next_action="Validate manual decisions before continuing.",
            next_command=validate_command,
        )

    validation_payload = _read_json_if_exists(validation)
    current_decision_fingerprint = _json_fingerprint(_read_json_if_exists(decisions))
    validation_decision_fingerprint = (
        validation_payload.get("decision_fingerprint")
        if isinstance(validation_payload.get("decision_fingerprint"), dict)
        else {}
    )
    if validation_decision_fingerprint.get("digest") != current_decision_fingerprint["digest"]:
        return _governance_status_payload(
            current_step="stale_decision_validation",
            missing_files=[],
            next_action="Re-run validation because p0-review-decisions.json changed after the validation report was written.",
            next_command=validate_command,
            details={
                "stale_file": validation.name,
                "current_decision_digest": current_decision_fingerprint["digest"],
                "validation_decision_digest": validation_decision_fingerprint.get("digest") or "",
            },
        )
    if validation_payload.get("valid") is False:
        return _governance_status_payload(
            current_step="blocked_at_decision_validation",
            missing_files=[],
            next_action="Fix p0-review-decisions.json according to validation errors.",
            next_command=validate_command,
            details={
                "error_count": int(validation_payload.get("error_count") or 0),
                "errors": validation_payload.get("errors") or [],
            },
        )

    if not decision_report.is_file():
        return _governance_status_payload(
            current_step="needs_decision_report",
            missing_files=[decision_report.name],
            next_action="Render the manual decision report before publication preflight or dry-run.",
            next_command=decision_report_command,
        )
    report_decision_fingerprint = _read_decision_report_fingerprint(decision_report)
    if report_decision_fingerprint.get("digest") != current_decision_fingerprint["digest"]:
        return _governance_status_payload(
            current_step="stale_decision_report",
            missing_files=[],
            next_action="Re-run decision-report because p0-review-decisions.report.md no longer matches current decisions.",
            next_command=decision_report_command,
            details={
                "stale_file": decision_report.name,
                "upstream_name": "p0-review-decisions.json",
                "current_decision_digest": current_decision_fingerprint["digest"],
                "report_decision_digest": report_decision_fingerprint.get("digest") or "",
            },
        )

    if not preflight.is_file() or not package.is_file():
        missing = [path.name for path in [preflight, package] if not path.is_file()]
        return _governance_status_payload(
            current_step="needs_benchmark_loop_after_decisions",
            missing_files=missing,
            next_action="Re-run benchmark loop after valid manual decisions exist.",
            next_command=(
                f".venv/bin/python scripts/run-hxy-loop.py benchmark_improvement "
                f"--benchmark {benchmark} --report {report} --run-id {run_id} "
                f"--runs-dir {runs_dir.as_posix()} --max-iterations 1"
            ),
        )

    preflight_payload = _read_json_if_exists(preflight)
    if int(preflight_payload.get("blocked_count") or 0) > 0:
        return _governance_status_payload(
            current_step="blocked_at_publication_preflight",
            missing_files=[],
            next_action="Fix approved decisions with missing publication metadata.",
            next_command=(
                f".venv/bin/python scripts/validate-hxy-p0-review-decisions.py validate "
                f"--stub {stub.as_posix()} --decisions {decisions.as_posix()} "
                f"--output {validation.as_posix()}"
            ),
            details={"blocked_count": int(preflight_payload.get("blocked_count") or 0)},
        )

    package_payload = _read_json_if_exists(package)
    package_stale_status = _stale_governance_artifact_status(
        current_step="stale_publication_package",
        stale_file=package.name,
        upstream_name="validation",
        current_upstream_payload=validation_payload,
        artifact_payload=package_payload,
        artifact_fingerprint_field="validation_fingerprint",
        next_action="Re-run benchmark loop because the publication package no longer matches current validation.",
        next_command=(
            f".venv/bin/python scripts/run-hxy-loop.py benchmark_improvement "
            f"--benchmark {benchmark} --report {report} --run-id {run_id} "
            f"--runs-dir {runs_dir.as_posix()} --max-iterations 1"
        ),
    )
    if package_stale_status is not None:
        return package_stale_status

    if not dry_run.is_file():
        return _governance_status_payload(
            current_step="needs_publication_dry_run",
            missing_files=[dry_run.name],
            next_action="Render draft answer card payloads without writing formal storage.",
            next_command=(
                f".venv/bin/python scripts/publish-hxy-p0-answer-cards.py dry-run "
                f"--package {package.as_posix()} --output {dry_run.as_posix()}"
            ),
        )

    dry_run_payload = _read_json_if_exists(dry_run)
    dry_run_command = (
        f".venv/bin/python scripts/publish-hxy-p0-answer-cards.py dry-run "
        f"--package {package.as_posix()} --output {dry_run.as_posix()}"
    )
    dry_run_stale_status = _stale_governance_artifact_status(
        current_step="stale_publication_dry_run",
        stale_file=dry_run.name,
        upstream_name="publication_package",
        current_upstream_payload=package_payload,
        artifact_payload=dry_run_payload,
        artifact_fingerprint_field="publication_package_fingerprint",
        next_action="Re-run publication dry-run because the publication package changed.",
        next_command=dry_run_command,
    )
    if dry_run_stale_status is not None:
        return dry_run_stale_status

    if dry_run_payload.get("valid") is False:
        return _governance_status_payload(
            current_step="blocked_at_publication_dry_run",
            missing_files=[],
            next_action="Fix publication package or draft payload errors.",
            next_command=dry_run_command,
            details={"error_count": int(dry_run_payload.get("error_count") or 0), "errors": dry_run_payload.get("errors") or []},
        )

    reviewed_command = (
        f".venv/bin/python scripts/publish-hxy-p0-answer-cards.py publish "
        f"--dry-run {dry_run.as_posix()} --output {reviewed.as_posix()} "
        "--confirm-manual-publication"
    )
    if not reviewed.is_file():
        return _governance_status_payload(
            current_step="needs_confirmed_reviewed_file",
            missing_files=[reviewed.name],
            next_action="After human confirmation, write the reviewed file.",
            next_command=reviewed_command,
        )

    reviewed_payload = _read_json_if_exists(reviewed)
    reviewed_stale_status = _stale_governance_artifact_status(
        current_step="stale_reviewed_file",
        stale_file=reviewed.name,
        upstream_name="dry_run",
        current_upstream_payload=dry_run_payload,
        artifact_payload=reviewed_payload,
        artifact_fingerprint_field="dry_run_fingerprint",
        next_action="Re-run reviewed-file publication because the dry-run payload changed.",
        next_command=reviewed_command,
    )
    if reviewed_stale_status is not None:
        return reviewed_stale_status

    import_gate_command = (
        f".venv/bin/python scripts/import-hxy-p0-reviewed-answer-cards.py gate "
        f"--reviewed {reviewed.as_posix()} --existing {existing.as_posix()} "
        f"--output {import_gate.as_posix()}"
    )
    if not import_gate.is_file():
        missing = [import_gate.name]
        if not existing.is_file():
            missing.insert(0, existing.name)
        return _governance_status_payload(
            current_step="needs_import_gate",
            missing_files=missing,
            next_action="Run import gate before any future formal import.",
            next_command=import_gate_command,
        )

    gate_payload = _read_json_if_exists(import_gate)
    gate_reviewed_stale_status = _stale_governance_artifact_status(
        current_step="stale_import_gate",
        stale_file=import_gate.name,
        upstream_name="reviewed_file",
        current_upstream_payload=reviewed_payload,
        artifact_payload=gate_payload,
        artifact_fingerprint_field="reviewed_file_fingerprint",
        next_action="Re-run import gate because the reviewed answer cards file changed.",
        next_command=import_gate_command,
    )
    if gate_reviewed_stale_status is not None:
        return gate_reviewed_stale_status

    existing_payload = _read_json_if_exists(existing)
    existing_items = existing_payload.get("items") if isinstance(existing_payload.get("items"), list) else []
    gate_existing_stale_status = _stale_governance_artifact_status(
        current_step="stale_import_gate",
        stale_file=import_gate.name,
        upstream_name="existing_answer_cards",
        current_upstream_payload={"items": existing_items},
        artifact_payload=gate_payload,
        artifact_fingerprint_field="existing_answer_cards_fingerprint",
        next_action="Re-run import gate because the existing approved answer card snapshot changed.",
        next_command=import_gate_command,
    )
    if gate_existing_stale_status is not None:
        return gate_existing_stale_status

    if gate_payload.get("valid") is False:
        return _governance_status_payload(
            current_step="blocked_at_import_gate",
            missing_files=[],
            next_action="Resolve conflicts before designing or running a separate import step.",
            next_command=import_gate_command,
            details={
                "conflict_count": int(gate_payload.get("conflict_count") or 0),
                "error_count": int(gate_payload.get("error_count") or 0),
            },
        )

    return _governance_status_payload(
        current_step="ready_for_separate_import_design",
        missing_files=[],
        next_action="All gates passed. A separate formal import procedure is still required before database writes.",
        next_command="",
        blocked=False,
        details={
            "importable_count": int(gate_payload.get("importable_count") or 0),
            "would_import_count": int(gate_payload.get("would_import_count") or 0),
        },
    )


def _build_benchmark_correction_package(benchmark: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
    cases = _case_by_id(benchmark)
    failed_scores = [score for score in report.get("scores", []) if not bool(score.get("passed"))]
    tasks: list[dict[str, Any]] = []
    for score in failed_scores:
        case_id = str(score.get("case_id") or "")
        case = cases.get(case_id, {})
        failed_checks = [str(item) for item in score.get("failed_checks", [])]
        warnings = [str(item) for item in score.get("warnings", [])]
        tasks.append(
            {
                "task_id": f"benchmark-fix-{case_id}",
                "case_id": case_id,
                "domain": case.get("domain") or "",
                "question": case.get("question") or "",
                "failed_checks": failed_checks,
                "warnings": warnings,
                "recommended_reviewer": _recommended_reviewer(case, score),
                "required_action": "补充或修订 approved answer card，并重新运行 benchmark；禁止直接把 reference/candidate 当权威答案。",
                "status": "open",
            }
        )
    authority_coverage = report.get("authority_coverage") if isinstance(report.get("authority_coverage"), dict) else {}
    passed_without_authority_case_ids = [
        str(case_id)
        for case_id in authority_coverage.get("passed_without_authority_case_ids", [])
        if str(case_id)
    ]
    authority_gap_tasks: list[dict[str, Any]] = []
    for case_id in passed_without_authority_case_ids:
        case = cases.get(case_id, {})
        priority = _authority_gap_priority(case)
        authority_gap_tasks.append(
            {
                "task_id": f"authority-gap-{case_id}",
                "case_id": case_id,
                "domain": case.get("domain") or "",
                "question": case.get("question") or "",
                "recommended_reviewer": _recommended_reviewer(case, {}),
                "required_action": "补充 approved answer card；禁止自动批准。",
                "reason": "benchmark_case_passed_without_authority_card",
                "status": "open",
                "official_use_allowed": False,
                "requires_human_review": True,
                **priority,
            }
        )
    authority_gap_tasks = sorted(
        authority_gap_tasks,
        key=lambda task: (-int(task.get("priority_score") or 0), str(task.get("case_id") or "")),
    )
    p0_authority_card_draft_pack = _build_p0_authority_card_draft_pack(authority_gap_tasks)
    return {
        "version": "hxy-benchmark-correction-package.v1",
        "benchmark_version": benchmark.get("version") or "",
        "task_count": len(tasks),
        "tasks": tasks,
        "authority_gap_task_count": len(authority_gap_tasks),
        "authority_gap_tasks": authority_gap_tasks,
        "p0_authority_card_draft_pack": p0_authority_card_draft_pack,
        "authority_coverage": authority_coverage,
    }


def _benchmark_failure_threshold(benchmark: dict[str, Any], override: float | None) -> float:
    if override is not None:
        return float(override)
    failure_thresholds = benchmark.get("failure_thresholds") if isinstance(benchmark.get("failure_thresholds"), dict) else {}
    return float(failure_thresholds.get("min_pass_rate", 0.85))


def run_compile_knowledge_loop(config: CompileKnowledgeLoopConfig) -> dict[str, Any]:
    run_root = Path(config.runs_dir) / config.run_id
    loop_state_path = run_root / "loop-state.json"
    iteration_root = run_root / "iterations"
    iteration_root.mkdir(parents=True, exist_ok=True)

    iterations: list[dict[str, Any]] = []
    status = "failed"
    stop_reason = "max_iterations_reached"
    for iteration_number in range(1, config.max_iterations + 1):
        report = compile_directory(config.raw_dir, config.wiki_dir)
        _write_json(config.report_path, _public_report(report))
        iteration_run_id = f"{config.run_id}-iter-{iteration_number:03d}"
        harness_report = write_harness_run(
            run_id=iteration_run_id,
            runs_dir=iteration_root,
            raw_dir=config.raw_dir,
            report=report,
        )
        evaluation = _evaluate_report(report, config.thresholds)
        iterations.append(
            {
                "iteration": iteration_number,
                "harness_run_id": iteration_run_id,
                "harness_run_path": str(iteration_root / iteration_run_id),
                "report": _public_report(report),
                "harness_state": harness_report["state"],
                "evaluation": evaluation,
            }
        )
        if evaluation["target_met"]:
            status = "passed"
            stop_reason = "target_met"
            break
        if not evaluation["evidence_sufficient"]:
            status = "failed"
            stop_reason = "evidence_insufficient"
            break

    if iterations and stop_reason == "max_iterations_reached" and iterations[-1]["evaluation"]["target_met"] is False:
        status = "failed"

    state = {
        "version": "hxy-loop-runner-state.v1",
        "loop_name": "compile_knowledge",
        "run_id": config.run_id,
        "goal": _make_goal(config.thresholds),
        "context_budget": {
            "raw_dir": Path(config.raw_dir).as_posix(),
            "wiki_dir": Path(config.wiki_dir).as_posix(),
            "max_iterations": int(config.max_iterations),
        },
        "thresholds": {
            "min_review_queue": int(config.thresholds.min_review_queue),
            "min_answer_card_drafts": int(config.thresholds.min_answer_card_drafts),
            "min_claim_count": int(config.thresholds.min_claim_count),
        },
        "iterations": iterations,
        "iteration_count": len(iterations),
        "status": status,
        "stop_reason": stop_reason,
        "next_actions": iterations[-1]["evaluation"]["next_actions"] if iterations else [],
    }
    _write_json(loop_state_path, state)
    return state


def run_benchmark_improvement_loop(config: BenchmarkImprovementLoopConfig) -> dict[str, Any]:
    run_root = Path(config.runs_dir) / config.run_id
    loop_state_path = run_root / "loop-state.json"
    correction_path = run_root / "benchmark-corrections.json"
    p0_draft_pack_path = run_root / "p0-authority-card-drafts.json"
    p0_review_manifest_path = run_root / "p0-draft-review-manifest.json"
    p0_review_decision_stub_path = run_root / "p0-review-decisions.stub.json"
    p0_review_decisions_path = run_root / "p0-review-decisions.json"
    p0_review_decision_summary_path = run_root / "p0-review-decision-summary.json"
    p0_publication_preflight_path = run_root / "p0-publication-preflight.json"
    p0_review_decision_validation_path = run_root / "p0-review-decisions.validation.json"
    p0_approved_card_publication_package_path = run_root / "p0-approved-card-publication-package.json"
    run_root.mkdir(parents=True, exist_ok=True)

    benchmark = load_benchmark(config.benchmark_path)
    min_pass_rate = _benchmark_failure_threshold(benchmark, config.min_pass_rate)
    iterations: list[dict[str, Any]] = []
    status = "failed"
    stop_reason = "max_iterations_reached"

    for iteration_number in range(1, config.max_iterations + 1):
        report = build_benchmark_report(benchmark, build_approved_answer_runs(benchmark))
        _write_json(config.report_path, report)
        correction_package = _build_benchmark_correction_package(benchmark, report)
        p0_draft_pack = correction_package.get("p0_authority_card_draft_pack") or {}
        p0_review_decision_stub = _build_p0_review_decision_stub(p0_draft_pack)
        correction_package["p0_review_decision_stub"] = p0_review_decision_stub
        if p0_review_decisions_path.is_file():
            p0_review_decisions = _load_p0_review_decisions(p0_review_decisions_path)
            p0_review_decision_summary = _build_p0_review_decision_summary(
                p0_review_decision_stub,
                p0_review_decisions,
            )
            p0_publication_preflight = _build_p0_publication_preflight(
                p0_review_decision_stub,
                p0_review_decisions,
            )
            p0_review_decision_validation = validate_p0_review_decisions(
                p0_review_decision_stub,
                p0_review_decisions,
            )
            p0_approved_card_publication_package = build_p0_approved_card_publication_package(
                p0_draft_pack,
                p0_review_decision_validation,
            )
            correction_package["p0_review_decision_summary"] = p0_review_decision_summary
            correction_package["p0_publication_preflight"] = p0_publication_preflight
            correction_package["p0_review_decision_validation"] = p0_review_decision_validation
            correction_package["p0_approved_card_publication_package"] = p0_approved_card_publication_package
            _write_json(p0_review_decision_summary_path, p0_review_decision_summary)
            _write_json(p0_publication_preflight_path, p0_publication_preflight)
            _write_json(p0_review_decision_validation_path, p0_review_decision_validation)
            _write_json(p0_approved_card_publication_package_path, p0_approved_card_publication_package)
        _write_json(correction_path, correction_package)
        _write_json(p0_draft_pack_path, p0_draft_pack)
        _write_json(p0_review_manifest_path, p0_draft_pack.get("review_manifest") or {})
        _write_json(p0_review_decision_stub_path, p0_review_decision_stub)
        failed_case_ids = [task["case_id"] for task in correction_package["tasks"]]
        target_met = float(report.get("pass_rate") or 0.0) >= min_pass_rate
        iterations.append(
            {
                "iteration": iteration_number,
                "benchmark_report_path": str(config.report_path),
                "correction_package_path": str(correction_path),
                "p0_authority_card_draft_pack_path": str(p0_draft_pack_path),
                "p0_draft_review_manifest_path": str(p0_review_manifest_path),
                "p0_review_decision_stub_path": str(p0_review_decision_stub_path),
                "p0_review_decision_summary_path": (
                    str(p0_review_decision_summary_path) if p0_review_decision_summary_path.is_file() else ""
                ),
                "p0_publication_preflight_path": (
                    str(p0_publication_preflight_path) if p0_publication_preflight_path.is_file() else ""
                ),
                "p0_review_decision_validation_path": (
                    str(p0_review_decision_validation_path) if p0_review_decision_validation_path.is_file() else ""
                ),
                "p0_approved_card_publication_package_path": (
                    str(p0_approved_card_publication_package_path)
                    if p0_approved_card_publication_package_path.is_file()
                    else ""
                ),
                "pass_rate": float(report.get("pass_rate") or 0.0),
                "target_met": target_met,
                "failed_case_ids": failed_case_ids,
                "correction_package": correction_package,
            }
        )
        if target_met:
            status = "passed"
            stop_reason = "target_met"
            break

    next_actions = [
        "逐条处理 benchmark correction package，优先修复合规和生命周期混用失败项。",
        "只允许通过 approved answer card 或人工复核流程修正答案，不允许 loop 自动发布正式口径。",
    ]
    if iterations and iterations[-1]["target_met"]:
        next_actions = ["保持当前 benchmark 基线，新增资料后重新运行。"]

    state = {
        "version": "hxy-loop-runner-state.v1",
        "loop_name": "benchmark_improvement",
        "run_id": config.run_id,
        "goal": _benchmark_goal(min_pass_rate),
        "context_budget": {
            "benchmark_path": Path(config.benchmark_path).as_posix(),
            "max_iterations": int(config.max_iterations),
        },
        "iterations": iterations,
        "iteration_count": len(iterations),
        "status": status,
        "stop_reason": stop_reason,
        "next_actions": next_actions,
    }
    _write_json(loop_state_path, state)
    return state
