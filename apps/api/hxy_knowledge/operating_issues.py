from __future__ import annotations

import hashlib
from typing import Any


def _contains_any(text: str, terms: list[str]) -> bool:
    return any(term in text for term in terms)


def _issue_id(seed: str) -> str:
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12]
    return f"hxy-issue:{digest}"


def _priority_rank(value: str) -> int:
    return {"high": 3, "medium": 2, "low": 1}.get(value, 0)


def _memory_target(domain: str, used_by: list[str], issue_type: str) -> str:
    if issue_type == "员工训练纠偏" or "employee_training" in used_by or domain == "training":
        return "training_card"
    if domain == "franchise" or "franchise_pitch" in used_by:
        return "franchise_script"
    if domain in {"product", "product_system"}:
        return "answer_card"
    if issue_type in {"知识过期", "证据不足"}:
        return "decision_log"
    return "operating_memory"


def _issue(
    *,
    title: str,
    issue_type: str,
    domain: str,
    priority: str,
    source: str,
    status: str = "open",
    owner: str = "业务负责人",
    conflict: str = "",
    evidence_gap: str = "",
    risk_boundary: str = "",
    next_actions: list[str] | None = None,
    memory_target: str = "operating_memory",
) -> dict[str, Any]:
    return {
        "version": "hxy-operating-issue.v1",
        "issue_id": _issue_id("|".join([title, issue_type, domain, source])),
        "title": title,
        "issue_type": issue_type,
        "domain": domain,
        "priority": priority,
        "status": status,
        "owner": owner,
        "source": source,
        "conflict": conflict,
        "evidence_gap": evidence_gap,
        "risk_boundary": risk_boundary,
        "next_actions": next_actions or [],
        "memory_target": memory_target,
    }


def issue_from_okf_document(document: dict[str, Any]) -> dict[str, Any] | None:
    title = str(document.get("title") or "未命名知识")
    domain = str(document.get("domain") or "general")
    status = str(document.get("status") or "draft")
    confidence = float(document.get("confidence") or 0)
    used_by = [str(item) for item in (document.get("used_by") or [])]
    owner = str(document.get("owner") or "业务负责人")
    contradictions = [str(item) for item in (document.get("contradicts") or [])]
    source = str(document.get("id") or title)
    memory_target = _memory_target(domain, used_by, "OKF")

    if status == "disputed" or contradictions:
        return _issue(
            title=f"{title}存在口径冲突",
            issue_type="口径冲突",
            domain=domain,
            priority="high",
            owner=owner,
            source=source,
            conflict=" / ".join(contradictions) or "已标记为 disputed",
            risk_boundary="冲突口径复核前，不应进入员工培训、招商外讲或用户宣传。",
            next_actions=[
                "复核冲突来源和当前官方口径",
                "确认保留、替代或废弃的知识版本",
                "更新相关答案卡、培训卡和 SOP",
            ],
            memory_target=memory_target,
        )
    if confidence < 0.65:
        return _issue(
            title=f"{title}证据不足",
            issue_type="证据不足",
            domain=domain,
            priority="medium",
            owner=owner,
            source=source,
            evidence_gap="可信度评分偏低，需要补齐证据或人工确认。",
            risk_boundary="证据不足时只能作为内部草稿，不能作为稳定口径。",
            next_actions=["补齐原始资料、经营数据或负责人确认", "复核通过后更新确认日期和可信度评分"],
            memory_target=memory_target,
        )
    if document.get("is_stale") or status == "superseded":
        return _issue(
            title=f"{title}需要生命周期复核",
            issue_type="知识过期",
            domain=domain,
            priority="medium",
            owner=owner,
            source=source,
            evidence_gap="知识确认时间已过期或已被新版本替代。",
            risk_boundary="过期知识不能默认用于招商、培训或经营决策。",
            next_actions=["确认是否仍然有效", "若已替代，补充替代版本并更新引用关系"],
            memory_target=memory_target,
        )
    return None


def build_operating_issues(documents: list[dict[str, Any]], *, today: str | None = None) -> list[dict[str, Any]]:
    issues = [issue for issue in (issue_from_okf_document(document) for document in documents) if issue]
    return sorted(issues, key=lambda item: (_priority_rank(item["priority"]), item["issue_type"]), reverse=True)


def issue_from_intake(input_text: str, *, scenario: str = "经营问答", role: str = "team") -> dict[str, Any]:
    text = " ".join((input_text or "").split())
    combined = f"{text} {scenario} {role}"
    if _contains_any(combined, ["治疗", "失眠", "保证", "稳赚", "一定回本", "医疗"]) and _contains_any(combined, ["员工", "话术", "培训", "复训", "纠偏"]):
        return _issue(
            title="员工话术存在合规和转化风险",
            issue_type="员工训练纠偏",
            domain="training",
            priority="high",
            owner="运营负责人",
            source="workbench_intake",
            conflict=text,
            risk_boundary="包含治疗、医疗、保证效果或收益承诺等高风险表达。",
            next_actions=[
                "生成复训任务，要求员工改成状态建议和放松体验表达",
                "同步更新清泡调补养禁用表达",
                "复核通过后沉淀为训练卡",
            ],
            memory_target="training_card",
        )
    if _contains_any(combined, ["定位", "战略", "商业模式", "加盟", "单店模型", "回本"]):
        return _issue(
            title="关键经营判断需要证据闭环",
            issue_type="待决策",
            domain="strategy",
            priority="high",
            owner="创始人",
            source="workbench_intake",
            evidence_gap="需要补齐定位、单店模型、回本假设或验证数据。",
            risk_boundary="证据闭环前，不应直接外讲成确定承诺。",
            next_actions=["拆分事实、假设和待验证数据", "形成决策日志和下一步验证任务"],
            memory_target="decision_log",
        )
    return _issue(
        title="新的经营输入待归档",
        issue_type="待归档",
        domain="general",
        priority="low",
        owner="业务负责人",
        source="workbench_intake",
        evidence_gap="需要判断是否沉淀为答案卡、议题或资料记忆。",
        next_actions=["识别业务域", "判断是否高频", "稳定后进入组织记忆"],
        memory_target="operating_memory",
    )
