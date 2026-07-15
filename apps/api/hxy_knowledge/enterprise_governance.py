from __future__ import annotations

import fnmatch
import hashlib
from collections import Counter, defaultdict, deque
from datetime import date
from pathlib import Path
from typing import Any


AUTHORITATIVE_STATUSES = {"approved", "action_asset"}
REFERENCE_STATUSES = {"raw", "reference", "ai_structured", "draft", "current_candidate", "needs_review", "disputed", "superseded"}
PROCESS_MEMORY_STATUSES = {"process"}
OVERCLAIM_TERMS = ["治疗", "治愈", "包好", "保证有效", "一定有效", "稳赚", "一定回本", "药到病除", "医学诊断", "冬病夏治"]
OVERCLAIM_SAFE_PREFIXES = ["不", "非", "不能", "不得", "禁止", "避免", "不应", "不可", "不可以", "不是", "不做", "不承诺", "不要"]


def _today(value: str | None = None) -> str:
    return (value or date.today().isoformat())[:10]


def _as_list(value: Any) -> list[Any]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return value
    return [value]


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _identity(item: dict[str, Any]) -> str:
    for key in ["asset_id", "claim_id", "evidence_id", "card_id", "id", "relative_path", "source_path"]:
        value = item.get(key)
        if value:
            return str(value)
    return str(abs(hash(str(sorted(item.items())))))


def _relative_path(path: Path, root_dir: Path | None) -> str:
    if root_dir:
        try:
            return path.relative_to(root_dir).as_posix()
        except ValueError:
            pass
    return path.as_posix()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _has_overclaim_risk(text: str) -> bool:
    return bool(_overclaim_terms(text))


def _overclaim_terms(text: str) -> list[str]:
    hits: list[str] = []
    for term in OVERCLAIM_TERMS:
        start = 0
        while True:
            index = text.find(term, start)
            if index < 0:
                break
            prefix = text[max(0, index - 8) : index]
            if not any(prefix.endswith(safe) for safe in OVERCLAIM_SAFE_PREFIXES):
                hits.append(term)
                break
            start = index + len(term)
    return hits


def _risk_types_for_terms(terms: list[str]) -> list[str]:
    risk_types: list[str] = []
    if any(term in terms for term in ["治疗", "治愈", "包好", "保证有效", "一定有效", "药到病除", "医学诊断", "冬病夏治"]):
        risk_types.append("medical_effect")
    if any(term in terms for term in ["稳赚", "一定回本"]):
        risk_types.append("revenue_promise")
    if any(term in terms for term in ["保证有效", "一定有效", "一定回本", "稳赚"]):
        risk_types.append("absolute_promise")
    return risk_types or ["overclaim"]


def _risk_excerpt(text: str, terms: list[str], *, window: int = 90) -> str:
    indexes = [text.find(term) for term in terms if text.find(term) >= 0]
    if not indexes:
        return text[: window * 2]
    index = min(indexes)
    return text[max(0, index - window) : min(len(text), index + window)].strip()


def _asset_index(assets: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for asset in assets:
        asset_id = _identity(asset)
        indexed[asset_id] = asset
        source_path = asset.get("source_path") or asset.get("relative_path")
        if source_path:
            indexed[str(source_path)] = asset
    return indexed


def _issue(
    *,
    code: str,
    severity: str,
    target_type: str,
    target_id: str,
    message: str,
    action: str,
    blocks_release: bool = False,
) -> dict[str, Any]:
    return {
        "code": code,
        "severity": severity,
        "target_type": target_type,
        "target_id": target_id,
        "message": message,
        "action": action,
        "blocks_release": blocks_release,
    }


def _status_of(item: dict[str, Any]) -> str:
    return str(item.get("status") or item.get("lifecycle_status") or "reference")


def _owner_of(item: dict[str, Any]) -> str:
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    return str(item.get("owner") or metadata.get("owner") or "")


def _sources_of(item: dict[str, Any]) -> list[Any]:
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    sources = item.get("sources")
    if sources is None:
        sources = metadata.get("sources")
    return _as_list(sources)


def _is_publishable_status(status: str) -> bool:
    return status in AUTHORITATIVE_STATUSES


def _is_process_memory_evidence(item: dict[str, Any]) -> bool:
    domain = str(item.get("domain") or "").lower()
    status = str(item.get("status") or item.get("lifecycle_status") or "").lower()
    source_type = str(item.get("source_type") or "").lower()
    return (
        domain == "process_memory"
        or source_type == "process_memory"
        or status in PROCESS_MEMORY_STATUSES
    )


def _is_remediated_risk_claim(claim: dict[str, Any]) -> bool:
    remediation = claim.get("governance_remediation")
    if not isinstance(remediation, dict):
        return False
    return (
        str(remediation.get("reason") or "") == "claim_overclaim_risk"
        and remediation.get("promotion_allowed") is False
        and _status_of(claim) in {"disputed", "needs_review", "superseded"}
    )


def classify_memory_layer(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Classify HXY knowledge records into L0-L4 memory layers.

    The classification is intentionally deterministic. It is a governance
    boundary, not an LLM judgment.
    """

    layers = {
        "L0_raw_material": [],
        "L1_structured_extract": [],
        "L2_candidate_claim": [],
        "L3_approved_knowledge": [],
        "L4_action_asset": [],
    }
    for item in items:
        status = _status_of(item)
        if item.get("card_type") in {"training_card", "sop", "decision_record"} or status == "action_asset":
            layer = "L4_action_asset"
        elif status == "approved" or item.get("review_status") in {"approved", "approved_v1"}:
            layer = "L3_approved_knowledge"
        elif item.get("claim_id") or status in {"current_candidate", "draft", "needs_review", "disputed"}:
            layer = "L2_candidate_claim"
        elif status in {"reference", "ai_structured", "extracted"} or item.get("normalized_path"):
            layer = "L1_structured_extract"
        else:
            layer = "L0_raw_material"
        layers[layer].append(_identity(item))

    return {
        "version": "hxy-memory-layer-classification.v1",
        "counts": {key: len(value) for key, value in layers.items()},
        "items": layers,
        "policy": {
            "direct_answer_allowed": ["L3_approved_knowledge", "L4_action_asset"],
            "requires_review": ["L0_raw_material", "L1_structured_extract", "L2_candidate_claim"],
            "ai_can_write": ["L1_structured_extract", "L2_candidate_claim"],
            "human_approval_required_for": ["L3_approved_knowledge", "L4_action_asset"],
        },
    }


def build_file_manifest(
    source_dir: str | Path,
    *,
    root_dir: str | Path | None = None,
    today: str | None = None,
    ignore_globs: list[str] | None = None,
) -> dict[str, Any]:
    """Build a deterministic manifest for raw HXY material files."""

    source_root = Path(source_dir).resolve()
    resolved_root = Path(root_dir).resolve() if root_dir else source_root
    ignored: list[dict[str, Any]] = []
    assets: list[dict[str, Any]] = []
    patterns = ignore_globs or []
    if not source_root.exists():
        return {
            "version": "hxy-file-manifest.v1",
            "generated_at": _today(today),
            "source_dir": _relative_path(source_root, resolved_root),
            "summary": {"asset_count": 0, "ignored_count": 0, "total_bytes": 0},
            "assets": [],
            "ignored": [],
        }

    for path in sorted(item for item in source_root.rglob("*") if item.is_file()):
        relative = _relative_path(path, resolved_root)
        source_relative = path.relative_to(source_root).as_posix()
        if any(fnmatch.fnmatch(path.name, pattern) or fnmatch.fnmatch(source_relative, pattern) for pattern in patterns):
            ignored.append({"relative_path": relative, "reason": "ignored_by_glob"})
            continue
        sha256 = _file_sha256(path)
        assets.append(
            {
                "asset_id": f"hxy-file:{sha256[:16]}",
                "relative_path": relative,
                "source_path": relative,
                "sha256": sha256,
                "size_bytes": path.stat().st_size,
                "status": "raw",
                "memory_layer": "L0_raw_material",
            }
        )

    return {
        "version": "hxy-file-manifest.v1",
        "generated_at": _today(today),
        "source_dir": _relative_path(source_root, resolved_root),
        "summary": {
            "asset_count": len(assets),
            "ignored_count": len(ignored),
            "total_bytes": sum(int(item.get("size_bytes") or 0) for item in assets),
        },
        "assets": assets,
        "ignored": ignored,
    }


def _lint_assets(assets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for asset in assets:
        asset_id = _identity(asset)
        status = _status_of(asset)
        if status == "approved" and not _owner_of(asset):
            issues.append(
                _issue(
                    code="approved_asset_missing_owner",
                    severity="high",
                    target_type="asset",
                    target_id=asset_id,
                    message="已批准资料缺少负责人。",
                    action="补充 owner 后才能作为权威知识使用。",
                    blocks_release=True,
                )
            )
        if status == "approved" and not _sources_of(asset):
            issues.append(
                _issue(
                    code="approved_asset_missing_sources",
                    severity="high",
                    target_type="asset",
                    target_id=asset_id,
                    message="已批准资料缺少来源证据链。",
                    action="补充 sources 或降级为 reference。",
                    blocks_release=True,
                )
            )
        if status in {"reference", "raw"} and str(asset.get("domain") or "") in {"brand", "product", "franchise"}:
            issues.append(
                _issue(
                    code="business_material_still_reference",
                    severity="medium",
                    target_type="asset",
                    target_id=asset_id,
                    message="关键业务资料仍是参考态。",
                    action="进入复核队列，确认是否生成候选 claim 或答案卡草稿。",
                    blocks_release=False,
                )
            )
    return issues


def _lint_claims(claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for claim in claims:
        claim_id = _identity(claim)
        status = _status_of(claim)
        text = str(claim.get("claim") or claim.get("text") or "")
        evidence_ids = _as_list(claim.get("evidence_ids"))
        confidence = _as_float(claim.get("confidence"))
        if not evidence_ids:
            issues.append(
                _issue(
                    code="claim_missing_evidence",
                    severity="high",
                    target_type="claim",
                    target_id=claim_id,
                    message="候选主张缺少证据。",
                    action="补齐 evidence_ids，或把该主张降级为待验证假设。",
                    blocks_release=True,
                )
            )
        if confidence and confidence < 0.65:
            issues.append(
                _issue(
                    code="claim_low_confidence",
                    severity="medium",
                    target_type="claim",
                    target_id=claim_id,
                    message="候选主张置信度低。",
                    action="补证据、复核或降低召回权重。",
                    blocks_release=False,
                )
            )
        if _has_overclaim_risk(text):
            if _is_remediated_risk_claim(claim):
                continue
            publishable = _is_publishable_status(status)
            issues.append(
                _issue(
                    code="claim_overclaim_risk",
                    severity="high",
                    target_type="claim",
                    target_id=claim_id,
                    message="候选主张包含医疗、效果或收益过度承诺。",
                    action="改写为状态建议/体验表达，并提交合规复核。",
                    blocks_release=publishable,
                )
            )
    return issues


def _lint_answer_cards(answer_cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for card in answer_cards:
        card_id = _identity(card)
        if _status_of(card) != "approved":
            continue
        evidence_items = _as_list(card.get("evidence") or card.get("sources"))
        for evidence in evidence_items:
            if isinstance(evidence, dict):
                status = _status_of(evidence)
                source_type = str(evidence.get("source_type") or "")
                evidence_target = str(evidence.get("asset_id") or evidence.get("source_path") or evidence.get("title") or "unknown")
            else:
                status = "reference"
                source_type = ""
                evidence_target = str(evidence)
            if isinstance(evidence, dict) and _is_process_memory_evidence(evidence):
                issues.append(
                    _issue(
                        code="process_memory_used_as_approved_source",
                        severity="critical",
                        target_type="answer_card",
                        target_id=card_id,
                        message="已批准答案卡把过程记忆当成权威依据。",
                        action=f"移除过程记忆依据 {evidence_target}，仅可作为上下文提醒；答案卡复核前降级为 draft。",
                        blocks_release=True,
                    )
                )
                continue
            if status in REFERENCE_STATUSES or source_type == "external_article":
                issues.append(
                    _issue(
                        code="reference_used_as_approved_source",
                        severity="critical",
                        target_type="answer_card",
                        target_id=card_id,
                        message="已批准答案卡引用了未核定参考资料。",
                        action=f"复核 {evidence_target}，通过后创建 approved 证据；否则答案卡降级为 draft。",
                        blocks_release=True,
                    )
                )
    return issues


def lint_okf_documents(documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Lint OKF lifecycle documents before they become approved memory."""

    issues: list[dict[str, Any]] = []
    for document in documents:
        status = _status_of(document)
        if status != "approved":
            continue
        document_id = _identity(document)
        owner = str(document.get("owner") or "").strip()
        if not owner or owner == "未指定":
            issues.append(
                _issue(
                    code="okf_approved_missing_owner",
                    severity="high",
                    target_type="okf_document",
                    target_id=document_id,
                    message="OKF 已批准知识缺少负责人。",
                    action="补充 owner，再允许进入企业权威记忆。",
                    blocks_release=True,
                )
            )
        if not str(document.get("last_confirmed") or "").strip():
            issues.append(
                _issue(
                    code="okf_approved_missing_last_confirmed",
                    severity="high",
                    target_type="okf_document",
                    target_id=document_id,
                    message="OKF 已批准知识缺少 last_confirmed。",
                    action="补充最近确认日期，过期知识不能直接用于权威回答。",
                    blocks_release=True,
                )
            )
        evidence_items = _as_list(document.get("evidence") or document.get("sources"))
        if not evidence_items:
            issues.append(
                _issue(
                    code="okf_approved_missing_evidence",
                    severity="high",
                    target_type="okf_document",
                    target_id=document_id,
                    message="OKF 已批准知识缺少证据链。",
                    action="补充 evidence/sources，或降级为 current_candidate。",
                    blocks_release=True,
                )
            )
        body = str(document.get("body") or "")
        if _has_overclaim_risk(body):
            issues.append(
                _issue(
                    code="okf_approved_overclaim_risk",
                    severity="high",
                    target_type="okf_document",
                    target_id=document_id,
                    message="OKF 已批准知识包含医疗、效果或收益过度承诺。",
                    action="改写为合规表达并重新复核。",
                    blocks_release=True,
                )
            )
    return issues


def lint_compiled_wiki_pages(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Lint compiler-produced HXY Wiki pages before runtime retrieval uses them."""

    issues: list[dict[str, Any]] = []
    for page in pages:
        page_id = _identity(page)
        status = _status_of(page)
        sources = _as_list(page.get("sources") or page.get("evidence"))
        if not sources:
            issues.append(
                _issue(
                    code="wiki_missing_sources",
                    severity="medium",
                    target_type="compiled_wiki_page",
                    target_id=page_id,
                    message="编译后的 Wiki 页面缺少来源，不能进入可信检索。",
                    action="补齐 sources，或将页面留在 raw/pending 等待治理。",
                    blocks_release=status in AUTHORITATIVE_STATUSES,
                )
            )

        if status not in AUTHORITATIVE_STATUSES:
            continue

        owner = str(page.get("owner") or "").strip()
        if not owner or owner == "未指定":
            issues.append(
                _issue(
                    code="wiki_approved_missing_owner",
                    severity="high",
                    target_type="compiled_wiki_page",
                    target_id=page_id,
                    message="已批准 Wiki 页面缺少负责人。",
                    action="补充 owner；否则降级为 current_candidate。",
                    blocks_release=True,
                )
            )
        if not str(page.get("last_confirmed") or "").strip():
            issues.append(
                _issue(
                    code="wiki_approved_missing_last_confirmed",
                    severity="high",
                    target_type="compiled_wiki_page",
                    target_id=page_id,
                    message="已批准 Wiki 页面缺少 last_confirmed。",
                    action="补充最近确认日期；过期知识不能直接用于权威回答。",
                    blocks_release=True,
                )
            )
        body = str(page.get("body") or page.get("content") or "")
        if _has_overclaim_risk(body):
            issues.append(
                _issue(
                    code="wiki_approved_overclaim_risk",
                    severity="high",
                    target_type="compiled_wiki_page",
                    target_id=page_id,
                    message="已批准 Wiki 页面包含医疗、效果或收益过度承诺。",
                    action="改写为合规表达并重新复核。",
                    blocks_release=True,
                )
            )
    return issues


def _evolution_actions(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    mapping = {
        "reference_used_as_approved_source": ("downgrade_to_reference", "将被污染的 approved 答案卡降级，复核后再发布。"),
        "process_memory_used_as_approved_source": ("downgrade_to_reference", "过程记忆不能作为 approved 答案卡依据，先降级复核。"),
        "claim_missing_evidence": ("create_review_task", "为缺证据候选主张创建复核任务。"),
        "claim_overclaim_risk": ("draft_answer_card_revision", "生成安全表达版本的答案卡修订草稿。"),
        "approved_asset_missing_owner": ("create_review_task", "补齐负责人和批准记录。"),
        "approved_asset_missing_sources": ("create_review_task", "补齐证据链或降级资料状态。"),
        "business_material_still_reference": ("compile_candidate_claim", "将关键业务参考资料编译为候选主张。"),
    }
    for issue in issues:
        action_type, description = mapping.get(issue["code"], ("create_review_task", "创建知识治理复核任务。"))
        key = (action_type, issue["target_id"])
        if key in seen:
            continue
        seen.add(key)
        actions.append(
            {
                "version": "hxy-knowledge-evolution-action.v1",
                "action_type": action_type,
                "target_type": issue["target_type"],
                "target_id": issue["target_id"],
                "source_issue_code": issue["code"],
                "description": description,
                "requires_human_approval": True,
            }
        )
    return actions


def summarize_governance_issues(issues: list[dict[str, Any]], *, limit: int = 10) -> dict[str, Any]:
    grouped: dict[str, dict[str, Any]] = {}
    for issue in issues:
        code = str(issue.get("code") or "unknown")
        group = grouped.setdefault(
            code,
            {
                "code": code,
                "count": 0,
                "blocking_count": 0,
                "max_severity": "low",
                "sample_targets": [],
                "message": str(issue.get("message") or ""),
                "recommended_action": str(issue.get("action") or "复核并更新知识状态。"),
            },
        )
        group["count"] += 1
        if issue.get("blocks_release"):
            group["blocking_count"] += 1
        severity = str(issue.get("severity") or "low")
        order = {"critical": 4, "high": 3, "medium": 2, "low": 1}
        if order.get(severity, 0) > order.get(str(group["max_severity"]), 0):
            group["max_severity"] = severity
        target_id = str(issue.get("target_id") or "")
        if target_id and target_id not in group["sample_targets"] and len(group["sample_targets"]) < 5:
            group["sample_targets"].append(target_id)

    def sort_key(item: dict[str, Any]) -> tuple[int, int, int]:
        severity_order = {"critical": 4, "high": 3, "medium": 2, "low": 1}
        return (
            int(item["blocking_count"]),
            severity_order.get(str(item["max_severity"]), 0),
            int(item["count"]),
        )

    top_groups = sorted(grouped.values(), key=sort_key, reverse=True)
    next_actions = [
        {
            "priority": _priority_for_issue({"severity": group["max_severity"]}),
            "issue_code": group["code"],
            "target_count": group["count"],
            "blocking_count": group["blocking_count"],
            "action": group["recommended_action"],
            "sample_targets": group["sample_targets"],
        }
        for group in top_groups[:limit]
    ]
    return {
        "version": "hxy-governance-issue-summary.v1",
        "total_issue_count": len(issues),
        "blocking_issue_count": sum(1 for issue in issues if issue.get("blocks_release")),
        "top_groups": top_groups[:limit],
        "next_actions": next_actions,
    }


def _reviewer_for_issue(issue: dict[str, Any]) -> str:
    code = str(issue.get("code") or "")
    target_type = str(issue.get("target_type") or "")
    if "overclaim" in code:
        return "合规负责人/业务负责人"
    if target_type == "answer_card":
        return "品牌负责人/知识管理员"
    if target_type == "okf_document":
        return "知识管理员/业务负责人"
    if target_type == "asset":
        return "资料负责人/知识管理员"
    return "知识管理员/业务负责人"


def _priority_for_issue(issue: dict[str, Any]) -> str:
    severity = str(issue.get("severity") or "medium")
    if severity in {"critical", "high"}:
        return "high"
    if severity == "low":
        return "low"
    return "medium"


def _issue_sort_key(issue: dict[str, Any]) -> tuple[int, int, int, str]:
    severity_order = {"critical": 4, "high": 3, "medium": 2, "low": 1}
    code_order = {
        "reference_used_as_approved_source": 90,
        "process_memory_used_as_approved_source": 90,
        "claim_overclaim_risk": 80,
        "okf_approved_overclaim_risk": 80,
        "approved_asset_missing_owner": 70,
        "approved_asset_missing_sources": 70,
        "okf_approved_missing_owner": 70,
        "okf_approved_missing_last_confirmed": 70,
        "okf_approved_missing_evidence": 70,
        "claim_missing_evidence": 60,
        "claim_low_confidence": 20,
        "business_material_still_reference": 10,
    }
    code = str(issue.get("code") or "")
    return (
        1 if issue.get("blocks_release") else 0,
        code_order.get(code, 30),
        severity_order.get(str(issue.get("severity") or "low"), 0),
        str(issue.get("target_id") or ""),
    )


def _compact_key(value: str) -> str:
    separators = " ，。！？?；;：:、（）()[]【】\"'“”‘’_—/\\|+·<>《》"
    compact = value
    for char in separators:
        compact = compact.replace(char, "")
    return compact


def _batchable_issue_key(issue: dict[str, Any]) -> str | None:
    code = str(issue.get("code") or "")
    target_type = str(issue.get("target_type") or "")
    if code == "claim_low_confidence" and target_type == "claim":
        return f"{code}:{target_type}"
    return None


def _build_batch_review_task_draft(
    issues: list[dict[str, Any]],
    *,
    run_id: str,
    batch_key: str,
) -> dict[str, Any]:
    first = issues[0]
    code = str(first.get("code") or "knowledge_governance_issue")
    target_type = str(first.get("target_type") or "knowledge")
    target_ids = [str(issue.get("target_id") or "unknown") for issue in issues]
    action = str(first.get("action") or "复核并更新知识状态。")
    message = str(first.get("message") or "知识治理问题需要批量复核。")
    reviewer = _reviewer_for_issue(first)
    normalized_question = _compact_key(f"知识治理批量复核 {code} {target_type}")
    correction_package = {
        "version": "hxy-governance-batch-correction-package.v1",
        "source_run_id": run_id,
        "normalized_question": normalized_question,
        "issue_code": code,
        "target_type": target_type,
        "target_id": f"batch:{batch_key}",
        "target_count": len(issues),
        "sample_target_ids": target_ids[:20],
        "message": message,
        "recommended_reviewer": reviewer,
        "recommended_actions": [
            action,
            "先按业务域和证据强度分组，低质量候选主张不要逐条打扰负责人。",
            "可补证据的进入候选池；不可补证据的降低召回权重或归档。",
        ],
        "requires_human_approval": True,
    }
    return {
        "version": "hxy-governance-review-task-draft.v1",
        "question": f"知识治理批量复核：{target_type} {len(issues)} 项 - {message}",
        "intent": "knowledge_governance",
        "reason": code,
        "priority": _priority_for_issue(first),
        "dedupe_key": f"knowledge_governance_batch:{code}:{target_type}",
        "correction_package": correction_package,
        "payload_json": {
            "source": "enterprise_governance",
            "run_id": run_id,
            "batch_key": batch_key,
            "issues": issues,
            "correction_package": correction_package,
        },
    }


def build_governance_review_task_drafts(report: dict[str, Any], *, run_id: str = "") -> list[dict[str, Any]]:
    """Convert governance lint issues into review task payload drafts."""

    drafts: list[dict[str, Any]] = []
    seen: set[str] = set()
    risk_packages = {
        str(item.get("claim_id") or ""): item
        for item in report.get("risk_correction_packages", [])
        if isinstance(item, dict)
    }
    batch_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    direct_issues: list[dict[str, Any]] = []
    for issue in report.get("lint_issues", []):
        if not isinstance(issue, dict):
            continue
        batch_key = _batchable_issue_key(issue)
        if batch_key:
            batch_groups[batch_key].append(issue)
        else:
            direct_issues.append(issue)
    for issue in sorted(direct_issues, key=_issue_sort_key, reverse=True):
        code = str(issue.get("code") or "knowledge_governance_issue")
        target_type = str(issue.get("target_type") or "knowledge")
        target_id = str(issue.get("target_id") or "unknown")
        dedupe_key = f"knowledge_governance:{code}:{target_type}:{target_id}"
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        action = str(issue.get("action") or "复核并更新知识状态。")
        message = str(issue.get("message") or "知识治理问题需要复核。")
        reviewer = _reviewer_for_issue(issue)
        correction_package = {
            "version": "hxy-governance-correction-package.v1",
            "source_run_id": run_id,
            "normalized_question": _compact_key(f"知识治理复核 {target_type} {target_id}"),
            "issue_code": code,
            "target_type": target_type,
            "target_id": target_id,
            "message": message,
            "recommended_reviewer": reviewer,
            "recommended_actions": [
                action,
                "补齐证据链、负责人、版本或风险边界。",
                "复核通过后再进入 approved/action_asset；未通过则降级为 reference/current_candidate。",
            ],
            "requires_human_approval": True,
        }
        if code == "claim_overclaim_risk" and target_id in risk_packages:
            correction_package["overclaim_correction_package"] = risk_packages[target_id]
        drafts.append(
            {
                "version": "hxy-governance-review-task-draft.v1",
                "question": f"知识治理复核：{target_type} {target_id} - {message}",
                "intent": "knowledge_governance",
                "reason": code,
                "priority": _priority_for_issue(issue),
                "dedupe_key": dedupe_key,
                "correction_package": correction_package,
                "payload_json": {
                    "source": "enterprise_governance",
                    "run_id": run_id,
                    "issue": issue,
                    "correction_package": correction_package,
                },
            }
        )
    for batch_key, issues in sorted(batch_groups.items(), key=lambda item: _issue_sort_key(item[1][0]), reverse=True):
        dedupe_key = f"knowledge_governance_batch:{batch_key}"
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        drafts.append(_build_batch_review_task_draft(issues, run_id=run_id, batch_key=batch_key))
    return drafts


def _workstream(
    *,
    key: str,
    title: str,
    issues: list[dict[str, Any]],
    task_mode: str,
    owner: str,
    action: str,
) -> dict[str, Any]:
    return {
        "key": key,
        "title": title,
        "issue_count": len(issues),
        "task_mode": task_mode,
        "owner": owner,
        "action": action,
        "sample_targets": [str(issue.get("target_id") or "") for issue in issues[:8] if issue.get("target_id")],
    }


def build_governance_triage_plan(report: dict[str, Any]) -> dict[str, Any]:
    """Group many lint issues into a small set of operational workstreams."""

    issues = [issue for issue in report.get("lint_issues", []) if isinstance(issue, dict)]
    release_blockers = [issue for issue in issues if issue.get("blocks_release")]
    risk_review = [
        issue
        for issue in issues
        if not issue.get("blocks_release")
        and str(issue.get("code") or "") in {"claim_overclaim_risk", "okf_approved_overclaim_risk"}
    ]
    quality_backlog = [
        issue
        for issue in issues
        if not issue.get("blocks_release")
        and str(issue.get("code") or "") in {"claim_low_confidence", "business_material_still_reference"}
    ]
    governance_hygiene = [
        issue
        for issue in issues
        if issue not in release_blockers and issue not in risk_review and issue not in quality_backlog
    ]
    workstreams = [
        _workstream(
            key="release_blockers",
            title="发布阻断",
            issues=release_blockers,
            task_mode="one_by_one",
            owner="知识管理员/业务负责人",
            action="先清零，否则不能发布为企业权威知识。",
        ),
        _workstream(
            key="risk_review",
            title="合规风险复核",
            issues=risk_review,
            task_mode="one_by_one",
            owner="合规负责人/业务负责人",
            action="逐条改写医疗、效果、收益过度承诺表达。",
        ),
        _workstream(
            key="quality_backlog",
            title="候选知识质量队列",
            issues=quality_backlog,
            task_mode="batch",
            owner="知识管理员",
            action="批量降权、补证据或归档，不逐条打扰业务负责人。",
        ),
        _workstream(
            key="governance_hygiene",
            title="治理字段补全",
            issues=governance_hygiene,
            task_mode="batch",
            owner="知识管理员",
            action="批量补齐 owner、sources、last_confirmed 等治理字段。",
        ),
    ]
    sequence = [
        item["key"]
        for item in workstreams
        if item["issue_count"] > 0 or item["key"] in {"release_blockers", "risk_review", "quality_backlog"}
    ]
    return {
        "version": "hxy-governance-triage-plan.v1",
        "total_issue_count": len(issues),
        "blocking_issue_count": len(release_blockers),
        "workstreams": workstreams,
        "recommended_sequence": sequence,
        "policy": "发布阻断逐条处理；合规风险逐条复核；低置信度候选主张批量治理。",
    }


def build_enterprise_governance_report(
    *,
    assets: list[dict[str, Any]],
    claims: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    relations: list[dict[str, Any]],
    answer_cards: list[dict[str, Any]],
    okf_documents: list[dict[str, Any]] | None = None,
    today: str | None = None,
) -> dict[str, Any]:
    lint_issues = [
        *_lint_assets(assets),
        *_lint_claims(claims),
        *_lint_answer_cards(answer_cards),
        *lint_okf_documents(okf_documents or []),
    ]
    risk_correction_packages = build_overclaim_correction_packages(claims=claims, evidence=evidence)
    remediated_risk_claims = build_remediated_risk_claims(claims)
    blocking = [issue for issue in lint_issues if issue.get("blocks_release")]
    status_counts = Counter(_status_of(item) for item in [*assets, *claims, *answer_cards])
    severity_counts = Counter(str(item.get("severity") or "low") for item in lint_issues)
    penalty = min(0.92, len(blocking) * 0.12 + (len(lint_issues) - len(blocking)) * 0.035)
    quality_score = round(max(0.0, 1.0 - penalty), 3)
    blocked_statuses = sorted({str(card.get("status") or "") for card in answer_cards if any(i["target_id"] == _identity(card) for i in blocking)})
    report = {
        "version": "hxy-enterprise-knowledge-governance.v1",
        "today": _today(today),
        "summary": {
            "asset_count": len(assets),
            "claim_count": len(claims),
            "evidence_count": len(evidence),
            "relation_count": len(relations),
            "answer_card_count": len(answer_cards),
            "lint_issue_count": len(lint_issues),
            "blocking_issue_count": len(blocking),
            "status_counts": dict(status_counts),
            "severity_counts": dict(severity_counts),
        },
        "quality_score": quality_score,
        "memory_layers": classify_memory_layer([*assets, *claims, *answer_cards]),
        "lint_issues": lint_issues,
        "issue_summary": summarize_governance_issues(lint_issues),
        "triage_plan": {},
        "risk_correction_packages": risk_correction_packages,
        "remediated_risk_claims": remediated_risk_claims,
        "release_gate": {
            "can_publish": not blocking,
            "blocked_statuses": blocked_statuses,
            "reason": "存在阻断级知识治理问题，不能发布为企业权威口径。" if blocking else "通过知识治理闸门。",
        },
        "evolution_actions": _evolution_actions(lint_issues),
    }
    report["triage_plan"] = build_governance_triage_plan(report)
    report["review_task_drafts"] = build_governance_review_task_drafts(report)
    return report


def _manifest_assets(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    assets: dict[str, dict[str, Any]] = {}
    for asset in manifest.get("assets", []):
        key = str(asset.get("relative_path") or asset.get("source_path") or asset.get("asset_id") or "")
        if key:
            assets[key] = asset
    return assets


def _asset_public(asset: dict[str, Any]) -> dict[str, Any]:
    return {
        "asset_id": str(asset.get("asset_id") or _identity(asset)),
        "relative_path": str(asset.get("relative_path") or asset.get("source_path") or ""),
        "sha256": str(asset.get("sha256") or ""),
        "normalized_path": str(asset.get("normalized_path") or ""),
    }


def build_overclaim_correction_packages(
    *,
    claims: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build reviewer-ready correction packages for risky candidate claims."""

    evidence_by_id = {str(item.get("evidence_id") or _identity(item)): item for item in evidence}
    packages: list[dict[str, Any]] = []
    for claim in claims:
        if _is_remediated_risk_claim(claim):
            continue
        text = str(claim.get("claim") or claim.get("text") or "")
        risk_terms = _overclaim_terms(text)
        if not risk_terms:
            continue
        evidence_ids = [str(item) for item in _as_list(claim.get("evidence_ids"))]
        source_titles: list[str] = []
        for evidence_id in evidence_ids:
            evidence_item = evidence_by_id.get(evidence_id)
            if not evidence_item:
                continue
            title = str(evidence_item.get("title") or evidence_item.get("source_path") or evidence_id)
            if title and title not in source_titles:
                source_titles.append(title)
        packages.append(
            {
                "version": "hxy-overclaim-correction-package.v1",
                "claim_id": _identity(claim),
                "claim_type": str(claim.get("claim_type") or claim.get("domain") or "unknown"),
                "claim_status": _status_of(claim),
                "confidence": _as_float(claim.get("confidence")),
                "source_evidence_ids": evidence_ids,
                "source_titles": source_titles,
                "risk_terms": risk_terms,
                "risk_types": _risk_types_for_terms(risk_terms),
                "risk_excerpt": _risk_excerpt(text, risk_terms),
                "promotion_allowed": False,
                "recommended_action": "archive_or_reextract",
                "safe_expression_suggestion": "改为放松、舒缓、体验感、状态建议等表达；不得承诺治疗、治愈、保证有效、冬病夏治或回本收益。",
                "review_notes": [
                    "不能进入 approved；先归档风险候选，或从原资料重新抽取无过度承诺的窄 claim。",
                    "如果只是颜色/视觉风格中的修辞，应改写为温柔、舒缓、亲和，不使用治愈。",
                    "如果涉及节气营销或功效表达，必须按合规口径改为体验建议，不作医疗暗示。",
                ],
            }
        )
    return packages


def build_remediated_risk_claims(claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    remediated: list[dict[str, Any]] = []
    for claim in claims:
        if not _is_remediated_risk_claim(claim):
            continue
        text = str(claim.get("claim") or claim.get("text") or "")
        risk_terms = _overclaim_terms(text)
        remediated.append(
            {
                "version": "hxy-remediated-risk-claim.v1",
                "claim_id": _identity(claim),
                "claim_type": str(claim.get("claim_type") or claim.get("domain") or "unknown"),
                "status": _status_of(claim),
                "risk_terms": risk_terms,
                "risk_types": _risk_types_for_terms(risk_terms),
                "governance_remediation": claim.get("governance_remediation") or {},
                "audit_note": "该风险 claim 已从可晋升候选池移出，仅保留审计链。",
            }
        )
    return remediated


def _build_relation_graph(relations: list[dict[str, Any]]) -> dict[str, list[str]]:
    graph: dict[str, list[str]] = defaultdict(list)
    for relation in relations:
        from_id = str(relation.get("from_id") or "")
        to_id = str(relation.get("to_id") or "")
        if from_id and to_id:
            graph[from_id].append(to_id)
    return graph


def _reachable(graph: dict[str, list[str]], seeds: set[str], max_depth: int = 4) -> list[dict[str, Any]]:
    seen = set(seeds)
    queue = deque((seed, 0) for seed in seeds)
    result: list[dict[str, Any]] = []
    while queue:
        node, depth = queue.popleft()
        if depth >= max_depth:
            continue
        for target in graph.get(node, []):
            if target in seen:
                continue
            seen.add(target)
            result.append({"id": target, "distance": depth + 1})
            queue.append((target, depth + 1))
    return result


def build_incremental_compile_plan(
    *,
    previous_manifest: dict[str, Any],
    current_manifest: dict[str, Any],
    relations: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    previous = _manifest_assets(previous_manifest)
    current = _manifest_assets(current_manifest)
    previous_keys = set(previous)
    current_keys = set(current)
    added = [_asset_public(current[key]) for key in sorted(current_keys - previous_keys)]
    deleted = [_asset_public(previous[key]) for key in sorted(previous_keys - current_keys)]
    changed = [
        _asset_public(current[key])
        for key in sorted(previous_keys & current_keys)
        if str(previous[key].get("sha256") or "") != str(current[key].get("sha256") or "")
    ]
    unchanged = [
        _asset_public(current[key])
        for key in sorted(previous_keys & current_keys)
        if str(previous[key].get("sha256") or "") == str(current[key].get("sha256") or "")
    ]
    changed_seed_ids = {item["asset_id"] for item in [*added, *changed, *deleted] if item.get("asset_id")}
    graph = _build_relation_graph(relations or [])
    affected_nodes = _reachable(graph, changed_seed_ids)
    tasks: list[dict[str, Any]] = []
    if added or changed:
        tasks.append({"stage": "extract", "reason": "新增或变更资料需要重新提取。", "asset_count": len(added) + len(changed)})
        tasks.append({"stage": "compile_claims", "reason": "资料变化后需要重新生成候选主张。", "asset_count": len(added) + len(changed)})
    if deleted or added or changed:
        tasks.append({"stage": "rebuild_relations", "reason": "资产集合变化后需要重建关系图。", "asset_count": len(added) + len(changed) + len(deleted)})
    tasks.append({"stage": "lint", "reason": "每次增量编译后必须跑知识治理 Lint。", "asset_count": len(current)})
    return {
        "version": "hxy-incremental-compile-plan.v1",
        "summary": {
            "added": len(added),
            "changed": len(changed),
            "deleted": len(deleted),
            "unchanged": len(unchanged),
        },
        "added": added,
        "changed": changed,
        "deleted": deleted,
        "unchanged": unchanged,
        "affected_nodes": affected_nodes,
        "tasks": tasks,
        "release_policy": "增量编译产物默认进入 reference/current_candidate，人工复核后才能进入 approved。",
    }


def build_governance_run_package(
    *,
    run_id: str,
    previous_manifest: dict[str, Any],
    current_manifest: dict[str, Any],
    governance_report: dict[str, Any],
    relations: list[dict[str, Any]] | None = None,
    today: str | None = None,
) -> dict[str, Any]:
    plan = build_incremental_compile_plan(
        previous_manifest=previous_manifest,
        current_manifest=current_manifest,
        relations=relations or [],
    )
    release_gate = governance_report.get("release_gate") if isinstance(governance_report.get("release_gate"), dict) else {}
    report_summary = governance_report.get("summary") if isinstance(governance_report.get("summary"), dict) else {}
    base_path = f"knowledge/reports/{run_id}"
    return {
        "version": "hxy-governance-run-package.v1",
        "run_id": run_id,
        "generated_at": _today(today),
        "summary": {
            "added_assets": plan["summary"]["added"],
            "changed_assets": plan["summary"]["changed"],
            "deleted_assets": plan["summary"]["deleted"],
            "unchanged_assets": plan["summary"]["unchanged"],
            "lint_issues": int(report_summary.get("lint_issue_count") or 0),
            "blocking_issues": int(report_summary.get("blocking_issue_count") or 0),
            "quality_score": governance_report.get("quality_score", 0),
        },
        "release_gate": {
            "can_publish": bool(release_gate.get("can_publish")),
            "reason": str(release_gate.get("reason") or ""),
        },
        "incremental_compile_plan": plan,
        "governance_report": governance_report,
        "review_task_drafts": build_governance_review_task_drafts(governance_report, run_id=run_id),
        "recommended_persistence": {
            "manifest_path": f"{base_path}/manifest.json",
            "plan_path": f"{base_path}/incremental-plan.json",
            "report_path": f"{base_path}/governance-report.json",
            "package_path": f"{base_path}/run-package.json",
        },
    }
