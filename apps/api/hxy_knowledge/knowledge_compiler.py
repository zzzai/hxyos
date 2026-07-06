from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


OVERCLAIM_TERMS = ["治疗", "治愈", "包好", "保证有效", "一定有效", "稳赚", "一定回本", "药到病除", "医学诊断", "冬病夏治"]
FORBIDDEN_REFERENCE_MARKERS = [
    "禁止",
    "禁用",
    "不能承诺",
    "不能说",
    "不要说",
    "不要把",
    "不能把",
    "不能出现",
    "有没有",
    "如果暗示",
    "必须删除",
    "必须改写",
    "说成治疗",
    "不得",
    "不允许",
    "绝对不能",
    "错误话术",
    "不要这样说",
]
SAFE_BOUNDARY_PATTERNS = [
    "不做治疗",
    "不做诊疗",
    "不说治什么",
    "不是医疗机构",
    "不是药品",
    "不能替代医疗",
    "不能替代治疗",
    "不能替代医院",
    "不能替代药品",
    "不替代医疗",
    "不替代治疗",
    "不替代医院",
    "不替代药品",
]
NOISE_TERMS = ["PDF_TEXT_START", "资料状态：reference", "权威使用：false", "人工复核：required", "---"]
HXY_TERMS = ["荷小悦", "清泡调补养", "清泡", "调泡", "补泡", "养泡", "社区小店", "草本真现煮"]
COMPETITOR_ONLY_TERMS = ["奈晚", "谷小推", "郑远元", "LANN", "蘭泰式", "秀域", "足康树", "素可泰", "长风拨筋", "贡小推"]
REVIEW_DOMAIN_HINTS = {
    "store_model": ["门店模型", "小店", "社区小店", "面积", "房间", "人员配置", "单店模型", "坪效", "人效"],
    "competitor_research": ["竞品", "奈晚", "谷小推", "郑远元", "LANN", "秀域", "足康树", "品牌数据", "排名"],
    "unit_economics": ["投资", "回本", "客单价", "利润", "成本", "租金", "毛利", "现金流"],
    "product_system": ["清泡", "调泡", "补泡", "养泡", "草本", "泡脚", "产品体系"],
    "employee_script": ["员工", "话术", "技师", "接待", "推荐", "培训", "复训"],
    "risk_boundary": ["治疗", "治愈", "保证", "一定有效", "稳赚", "医学", "禁用", "不能承诺"],
    "brand_positioning": ["定位", "品牌", "核爆点", "足疗", "轻养生"],
}


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()
    return f"{prefix}:{digest[:16]}"


def _domain_for(text: str) -> str:
    if any(term in text for term in ["定位", "品牌", "核爆点", "足疗"]):
        return "brand_positioning"
    if any(term in text for term in ["清泡", "调泡", "补泡", "养泡", "产品", "泡脚"]):
        return "product_system"
    if any(term in text for term in ["员工", "话术", "训练", "技师"]):
        return "employee_training"
    if any(term in text for term in ["招商", "回本", "加盟", "收益"]):
        return "franchise_finance"
    if any(term in text for term in ["治疗", "治愈", "医学", "保证有效"]):
        return "risk_boundary"
    return "general"


def _risk_flags(text: str) -> list[str]:
    has_overclaim_term = any(term in text for term in OVERCLAIM_TERMS)
    if not has_overclaim_term:
        return []
    if re.search(r"不做.{0,12}治疗", text):
        return []
    if any(marker in text for marker in FORBIDDEN_REFERENCE_MARKERS):
        if text.startswith("错误话术"):
            return ["overclaim_risk"]
        return ["forbidden_expression_reference"]
    if any(pattern in text for pattern in SAFE_BOUNDARY_PATTERNS):
        return []
    if has_overclaim_term:
        return ["overclaim_risk"]
    return []


def _review_group_for(text: str, domain: str | None = None) -> str:
    haystack = f"{domain or ''}\n{text}"
    if domain == "risk_boundary":
        return "risk_boundary"
    if domain == "product_system":
        return "product_system"
    if domain == "employee_training":
        return "employee_script"
    if domain == "franchise_finance":
        return "unit_economics"
    if domain == "brand_positioning":
        return "brand_positioning"
    for group, terms in REVIEW_DOMAIN_HINTS.items():
        if any(term in haystack for term in terms):
            return group
    return "general"


def _is_noise_claim(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return True
    if any(term in stripped for term in NOISE_TERMS):
        return True
    if "\f" in stripped:
        return True
    digit_count = sum(char.isdigit() for char in stripped)
    chinese_count = sum("\u4e00" <= char <= "\u9fff" for char in stripped)
    if len(stripped) <= 14 and digit_count >= 2:
        return True
    if chinese_count < 4 and digit_count >= 3:
        return True
    return False


def _claim_value_score(claim: dict[str, Any]) -> float:
    text = str(claim.get("claim") or "")
    domain = str(claim.get("domain") or "")
    if _is_noise_claim(text):
        return 0.0
    score = 0.35
    group = _review_group_for(text, domain)
    if group != "general":
        score += 0.2
    if claim.get("risk_flags"):
        score += 0.35
    if any(term in text for terms in REVIEW_DOMAIN_HINTS.values() for term in terms):
        score += 0.15
    if any(term in text for term in HXY_TERMS):
        score += 0.25
    if any(term in text for term in COMPETITOR_ONLY_TERMS) and not any(term in text for term in HXY_TERMS):
        score -= 0.2
    if 18 <= len(text) <= 220:
        score += 0.1
    if claim.get("sources"):
        score += 0.08
    return round(min(score, 1.0), 3)


def _sentences(text: str) -> list[str]:
    candidates = re.split(r"[。！？!?]\s*", text)
    return [item.strip(" \n\t#") for item in candidates if len(item.strip(" \n\t#")) >= 8]


def compile_material(material: dict[str, Any]) -> dict[str, Any]:
    content = str(material.get("content") or "")
    source_path = str(material.get("source_path") or material.get("asset_id") or "")
    title = str(material.get("title") or Path(source_path).stem or "未命名资料")
    extract_id = _stable_id("hxy-extract", source_path, content)
    return {
        "version": "hxy-structured-extract.v1",
        "extract_id": extract_id,
        "asset_id": material.get("asset_id") or extract_id,
        "title": title,
        "content": content,
        "domain": _domain_for(f"{title}\n{content}"),
        "status": "reference",
        "memory_layer": "L1_structured_extract",
        "sources": [source_path] if source_path else [],
        "confidence": 0.5,
        "official_use_allowed": False,
        "requires_human_review": True,
    }


def extract_candidate_claims(extract: dict[str, Any]) -> list[dict[str, Any]]:
    content = str(extract.get("content") or "")
    sources = [str(item) for item in (extract.get("sources") or [])]
    claims = []
    for sentence in _sentences(content):
        claim_id = _stable_id("hxy-claim", str(extract.get("extract_id") or ""), sentence)
        claims.append(
            {
                "version": "hxy-candidate-claim.v1",
                "claim_id": claim_id,
                "claim": sentence,
                "domain": _domain_for(sentence),
                "status": "current_candidate",
                "memory_layer": "L2_candidate_claim",
                "sources": sources,
                "confidence": 0.5,
                "requires_human_review": True,
                "official_use_allowed": False,
                "risk_flags": _risk_flags(sentence),
                "review_group": _review_group_for(sentence),
            }
        )
    return claims


def build_review_queue(claims: list[dict[str, Any]], limit: int = 20) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    noise_count = 0
    for claim in claims:
        text = str(claim.get("claim") or "")
        score = _claim_value_score(claim)
        if score <= 0:
            noise_count += 1
            continue
        group = _review_group_for(text, str(claim.get("domain") or ""))
        risk_flags = list(claim.get("risk_flags") or [])
        priority = "high" if risk_flags or score >= 0.8 else ("medium" if score >= 0.6 else "low")
        reviewer = "运营/合规负责人" if risk_flags or group == "risk_boundary" else "创始人/运营负责人"
        recommended_action = "先复核风险边界，禁止直接发布。" if risk_flags else "复核来源和业务适用范围，通过后生成答案卡。"
        item = {
            "version": "hxy-review-queue-item.v1",
            "claim_id": claim.get("claim_id"),
            "claim": text,
            "domain": claim.get("domain") or "general",
            "review_group": group,
            "priority": priority,
            "score": score,
            "risk_flags": risk_flags,
            "sources": claim.get("sources") or [],
            "status": "needs_review",
            "official_use_allowed": False,
            "requires_human_review": True,
            "recommended_reviewer": reviewer,
            "recommended_action": recommended_action,
        }
        items.append(item)
    priority_order = {"high": 0, "medium": 1, "low": 2}
    items.sort(key=lambda item: (priority_order[item["priority"]], -float(item["score"]), str(item["claim_id"] or "")))
    grouped: dict[str, int] = {}
    for item in items:
        grouped[item["review_group"]] = grouped.get(item["review_group"], 0) + 1
    return {
        "version": "hxy-review-queue.v1",
        "total_claim_count": len(claims),
        "noise_claim_count": noise_count,
        "reviewable_claim_count": len(items),
        "group_counts": grouped,
        "items": items[: max(0, limit)],
    }


def _question_for_review_item(item: dict[str, Any]) -> str:
    group = str(item.get("review_group") or "general")
    templates = {
        "brand_positioning": "荷小悦的品牌定位应该怎么说？",
        "product_system": "清泡调补养或产品体系应该怎么解释？",
        "store_model": "荷小悦门店模型的关键判断是什么？",
        "competitor_research": "这条竞品信息对荷小悦有什么参考价值？",
        "unit_economics": "这条单店模型或投资测算信息能否作为内部判断依据？",
        "employee_script": "员工应该如何按标准口径表达？",
        "risk_boundary": "这条表达有哪些合规风险，应该如何改写？",
    }
    return templates.get(group, "这条候选知识是否可以进入荷小悦标准口径？")


def build_answer_card_drafts(review_items: list[dict[str, Any]], limit: int = 10) -> dict[str, Any]:
    drafts: list[dict[str, Any]] = []
    for item in review_items:
        if item.get("priority") == "low":
            continue
        claim = str(item.get("claim") or "").strip()
        if not claim:
            continue
        risk_flags = list(item.get("risk_flags") or [])
        if risk_flags:
            answer = f"当前为草稿，不能直接发布。候选资料提示存在风险表达：{claim} 复核时需要改写为不承诺疗效、不夸大收益、只说明体验和适用边界。"
        else:
            answer = f"当前为草稿，不能直接发布。候选资料显示：{claim} 复核通过后可整理为荷小悦标准口径，并补充适用场景和引用来源。"
        drafts.append(
            {
                "version": "hxy-answer-card-draft.v1",
                "question_pattern": _question_for_review_item(item),
                "intent": item.get("domain") or "general",
                "audience": "internal",
                "answer": answer,
                "status": "draft",
                "official_use_allowed": False,
                "requires_human_review": True,
                "source_claim_ids": [item.get("claim_id")],
                "sources": item.get("sources") or [],
                "risk_flags": risk_flags,
                "review_group": item.get("review_group") or "general",
                "recommended_reviewer": item.get("recommended_reviewer") or "运营负责人",
            }
        )
        if len(drafts) >= limit:
            break
    return {
        "version": "hxy-answer-card-drafts.v1",
        "draft_count": len(drafts),
        "items": drafts,
    }


def build_compliance_review_pack(review_items: list[dict[str, Any]], limit: int = 20) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for item in review_items:
        review_group = str(item.get("review_group") or "")
        risk_flags = list(item.get("risk_flags") or [])
        sources = [str(source) for source in (item.get("sources") or [])]
        from_risk_source = any("09_风险与合规" in source or "风险与合规" in source for source in sources)
        if review_group != "risk_boundary" and not risk_flags and not from_risk_source:
            continue
        items.append(
            {
                "version": "hxy-compliance-review-item.v1",
                "claim_id": item.get("claim_id"),
                "claim": item.get("claim") or "",
                "risk_level": "P0",
                "risk_flags": risk_flags,
                "sources": sources,
                "recommended_reviewer": item.get("recommended_reviewer") or "运营/合规负责人",
                "review_question": "这条合规边界能否作为员工正式禁用表达或标准话术？",
                "required_decision": "approve_as_rule, needs_revision, or reject",
                "human_checklist": [
                    "核对原始来源和上下文，确认不是 AI 误读。",
                    "确认是否适用于门店员工、对外宣传或招商沟通。",
                    "确认改写后不包含医疗、保证疗效、夸大宣传或收益承诺。",
                    "不能自动进入 approved answer card；必须由负责人明确批准。",
                ],
                "official_use_allowed": False,
                "publish_allowed": False,
                "requires_human_review": True,
            }
        )
    items.sort(
        key=lambda item: (
            0 if item.get("risk_flags") else 1,
            0 if any("09_风险与合规" in source or "风险与合规" in source for source in item.get("sources", [])) else 1,
            str(item.get("claim_id") or ""),
        )
    )
    items = items[: max(0, limit)]
    return {
        "version": "hxy-compliance-review-pack.v1",
        "status": "needs_human_review" if items else "empty",
        "count": len(items),
        "items": items,
        "official_use_allowed": False,
        "publish_allowed": False,
        "requires_human_review": True,
        "authority_rule": "compliance_review_pack_is_not_approved_knowledge",
        "next_actions": [
            "由运营/合规负责人逐条选择 approve_as_rule、needs_revision 或 reject。",
            "批准后仍需进入正式答案卡发布流程，不能由编译器自动发布。",
        ],
    }


def build_knowledge_graph(*, extracts: list[dict[str, Any]], claims: list[dict[str, Any]]) -> dict[str, Any]:
    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, str]] = []

    def add_node(node_id: str, node_type: str, title: str) -> None:
        nodes[node_id] = {"id": node_id, "type": node_type, "title": title}

    for extract in extracts:
        extract_id = str(extract.get("extract_id") or "")
        domain = str(extract.get("domain") or "general")
        if extract_id:
            add_node(extract_id, "extract", str(extract.get("title") or extract_id))
            add_node(f"domain:{domain}", "domain", domain)
            edges.append({"type": "belongs_to", "from": extract_id, "to": f"domain:{domain}"})
            for source in extract.get("sources") or []:
                source_id = f"source:{source}"
                add_node(source_id, "source", str(source))
                edges.append({"type": "supported_by", "from": extract_id, "to": source_id})

    for claim in claims:
        claim_id = str(claim.get("claim_id") or "")
        domain = str(claim.get("domain") or "general")
        if claim_id:
            add_node(claim_id, "claim", str(claim.get("claim") or claim_id))
            add_node(f"domain:{domain}", "domain", domain)
            edges.append({"type": "belongs_to", "from": claim_id, "to": f"domain:{domain}"})
            for source in claim.get("sources") or []:
                source_id = f"source:{source}"
                add_node(source_id, "source", str(source))
                edges.append({"type": "supported_by", "from": claim_id, "to": source_id})
            for risk_flag in claim.get("risk_flags") or []:
                risk_id = f"risk:{risk_flag}"
                add_node(risk_id, "risk_rule", str(risk_flag))
                edges.append({"type": "blocked_by", "from": claim_id, "to": risk_id})

    return {
        "version": "hxy-knowledge-graph.v1",
        "nodes": list(nodes.values()),
        "edges": edges,
    }


def compile_directory(
    raw_dir: str | Path,
    wiki_dir: str | Path,
    *,
    source_paths: list[str | Path] | None = None,
) -> dict[str, Any]:
    raw_root = Path(raw_dir)
    wiki_root = Path(wiki_dir)
    wiki_root.mkdir(parents=True, exist_ok=True)

    extracts: list[dict[str, Any]] = []
    claims: list[dict[str, Any]] = []
    paths = [Path(path) for path in source_paths] if source_paths is not None else sorted(raw_root.rglob("*"))
    for path in sorted(paths, key=lambda item: item.as_posix()):
        if not path.is_file() or path.suffix.lower() not in {".md", ".txt"}:
            continue
        content = path.read_text(encoding="utf-8")
        extract = compile_material({"title": path.stem, "content": content, "source_path": path.as_posix()})
        extracts.append(extract)
        claims.extend(extract_candidate_claims(extract))

    graph = build_knowledge_graph(extracts=extracts, claims=claims)
    review_queue = build_review_queue(claims, limit=20)
    full_review_queue = build_review_queue(claims, limit=max(len(claims), 20))
    answer_card_drafts = build_answer_card_drafts(review_queue["items"], limit=10)
    compliance_review_pack = build_compliance_review_pack(full_review_queue["items"], limit=20)
    (wiki_root / "graph.json").write_text(json.dumps(graph, ensure_ascii=False, indent=2), encoding="utf-8")
    (wiki_root / "index.md").write_text(_render_index(extracts, claims), encoding="utf-8")
    (wiki_root / "review-queue.json").write_text(json.dumps(review_queue, ensure_ascii=False, indent=2), encoding="utf-8")
    (wiki_root / "answer-card-drafts.json").write_text(json.dumps(answer_card_drafts, ensure_ascii=False, indent=2), encoding="utf-8")
    (wiki_root / "compliance-review-pack.json").write_text(json.dumps(compliance_review_pack, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "version": "hxy-knowledge-compiler-report.v1",
        "extract_count": len(extracts),
        "claim_count": len(claims),
        "approved_count": 0,
        "review_queue_count": len(review_queue["items"]),
        "reviewable_claim_count": review_queue["reviewable_claim_count"],
        "noise_claim_count": review_queue["noise_claim_count"],
        "answer_card_draft_count": answer_card_drafts["draft_count"],
        "compliance_review_count": compliance_review_pack["count"],
        "graph_node_count": len(graph["nodes"]),
        "graph_edge_count": len(graph["edges"]),
        "wiki_dir": wiki_root.as_posix(),
        "artifacts": {
            "extracts": extracts,
            "claims": claims,
            "graph": graph,
            "review_queue": review_queue,
            "answer_card_drafts": answer_card_drafts,
            "compliance_review_pack": compliance_review_pack,
        },
    }


def _render_index(extracts: list[dict[str, Any]], claims: list[dict[str, Any]]) -> str:
    lines = [
        "# HXY Compiled Wiki Index",
        "",
        "Compiler output is not approved knowledge. It is reference or candidate material for review.",
        "",
        f"- Extracts: {len(extracts)}",
        f"- Candidate claims: {len(claims)}",
        "",
        "## Domains",
    ]
    domains = sorted({str(item.get("domain") or "general") for item in [*extracts, *claims]})
    for domain in domains:
        lines.append(f"- {domain}")
    lines.append("")
    return "\n".join(lines)


def build_harness_state(
    *,
    run_id: str,
    report: dict[str, Any],
    phase_paths: dict[str, str],
) -> dict[str, Any]:
    extract_count = int(report.get("extract_count") or 0)
    claim_count = int(report.get("claim_count") or 0)
    graph_node_count = int(report.get("graph_node_count") or 0)
    gates = {
        "source_gate": "passed" if extract_count > 0 else "failed",
        "compile_gate": "passed" if extract_count > 0 and claim_count > 0 and graph_node_count > 0 else "failed",
        "evidence_gate": "passed" if claim_count > 0 else "failed",
        "risk_gate": "passed",
        "review_gate": "pending",
    }
    blocked = any(value == "failed" for value in gates.values())
    next_actions: list[str] = []
    if extract_count == 0:
        next_actions.append("当前没有可编译资料，请把 .md/.txt 原始资料放入 knowledge/raw/inbox。")
    if claim_count == 0:
        next_actions.append("当前没有候选 claim，不能进入复核或答案卡生产。")
    next_actions.append("编译产物默认不是 approved，必须经过人工复核。")
    return {
        "version": "hxy-harness-state.v1",
        "run_id": run_id,
        "goal": "compile_hxy_knowledge",
        "current_phase": "final_report",
        "status": "blocked" if blocked else "passed",
        "gates": gates,
        "phase_paths": phase_paths,
        "next_actions": next_actions,
    }


def write_harness_run(
    *,
    run_id: str,
    runs_dir: str | Path,
    raw_dir: str | Path,
    report: dict[str, Any],
) -> dict[str, Any]:
    run_root = Path(runs_dir) / run_id
    phases_dir = run_root / "phases"
    phases_dir.mkdir(parents=True, exist_ok=True)
    artifacts = report.get("artifacts") if isinstance(report.get("artifacts"), dict) else {}
    extracts = artifacts.get("extracts") if isinstance(artifacts.get("extracts"), list) else []
    claims = artifacts.get("claims") if isinstance(artifacts.get("claims"), list) else []
    graph = artifacts.get("graph") if isinstance(artifacts.get("graph"), dict) else {"version": "hxy-knowledge-graph.v1", "nodes": [], "edges": []}

    manifest = {
        "version": "hxy-compiler-manifest.v1",
        "raw_dir": Path(raw_dir).as_posix(),
        "source_count": len(extracts),
        "sources": [source for extract in extracts for source in extract.get("sources", [])],
    }
    gates = {
        "version": "hxy-compiler-gates.v1",
        "extract_count": int(report.get("extract_count") or 0),
        "claim_count": int(report.get("claim_count") or 0),
        "graph_node_count": int(report.get("graph_node_count") or 0),
    }
    phase_payloads = {
        "01_manifest.json": manifest,
        "02_extracts.json": {"version": "hxy-compiler-extracts.v1", "items": extracts},
        "03_claims.json": {"version": "hxy-compiler-claims.v1", "items": claims},
        "04_graph.json": graph,
        "05_gates.json": gates,
        "06_review_queue.json": artifacts.get("review_queue") or {"version": "hxy-review-queue.v1", "items": []},
        "07_answer_card_drafts.json": artifacts.get("answer_card_drafts") or {"version": "hxy-answer-card-drafts.v1", "items": []},
        "08_compliance_review_pack.json": artifacts.get("compliance_review_pack") or {"version": "hxy-compliance-review-pack.v1", "items": []},
    }
    phase_paths: dict[str, str] = {}
    for file_name, payload in phase_payloads.items():
        path = phases_dir / file_name
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        phase_paths[file_name.removesuffix(".json")] = path.as_posix()

    state = build_harness_state(run_id=run_id, report=report, phase_paths=phase_paths)
    (run_root / "state.json").write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    final_report = {
        "version": "hxy-harness-final-report.v1",
        "run_id": run_id,
        "state": state,
        "compiler_report": {key: value for key, value in report.items() if key != "artifacts"},
    }
    (run_root / "final-report.json").write_text(json.dumps(final_report, ensure_ascii=False, indent=2), encoding="utf-8")
    return final_report
