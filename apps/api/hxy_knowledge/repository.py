from __future__ import annotations

import json
import re
from typing import Any

try:
    import psycopg
    from psycopg.rows import dict_row
except Exception:  # pragma: no cover - dependency may be installed later
    psycopg = None
    dict_row = None


_TOKEN_SPLIT_RE = re.compile(r"[\s,，。！？?；;：:、（）()\[\]【】\"'“”‘’/\\|+·\-—_<>《》]+")
_TOKEN_STOP_WORDS = {
    "荷小悦",
    "知识库",
    "什么",
    "怎么",
    "如何",
    "为什么",
    "有没有",
    "请问",
    "一下",
}
_BUSINESS_TOKEN_LEXICON = [
    "清泡调补养",
    "草本泡脚",
    "一人一方",
    "门店模型",
    "小店模型",
    "单店模型",
    "关键参数",
    "规模化参数",
    "试点参数",
    "高质平价",
    "功效泡脚",
    "对症推拿",
    "复购话术",
    "视觉风格",
    "产品体系",
    "社区小店",
    "泡脚方",
    "竞品",
    "参考",
    "品牌",
    "图片",
    "菜单",
    "产品",
    "草本",
    "泡脚",
    "复购",
    "话术",
    "背书",
    "价格",
    "视觉",
    "风格",
    "功效",
    "五行",
    "定位",
    "门店",
    "技师",
    "套餐",
    "推拿",
    "按摩",
    "药材",
    "非遗",
    "卖点",
]


def _dedupe_tokens(tokens: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for token in tokens:
        normalized = token.strip()
        if not normalized or normalized in _TOKEN_STOP_WORDS or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped


def _search_tokens(query: str, max_tokens: int = 8) -> list[str]:
    rough_parts = [part for part in _TOKEN_SPLIT_RE.sub(" ", query).split(" ") if part.strip()]
    tokens: list[str] = []
    for part in rough_parts:
        lexicon_hits = [term for term in _BUSINESS_TOKEN_LEXICON if term in part]
        tokens.extend(lexicon_hits)
        if len(lexicon_hits) < 2 and 2 <= len(part) <= 12:
            tokens.append(part)
    return _dedupe_tokens(tokens)[:max_tokens]


def build_search_query(
    query: str,
    domain: str | None = None,
    stage: str | None = None,
    limit: int = 20,
    domain_hint: str | None = None,
) -> tuple[str, list[Any]]:
    tokens = _search_tokens(query)
    full_pattern = f"%{query}%"
    token_patterns = [f"%{token}%" for token in tokens]
    score_parts = ["CASE WHEN content ILIKE %s THEN 100 ELSE 0 END"]
    score_params: list[Any] = [full_pattern]
    if domain_hint:
        score_parts.append("CASE WHEN domain = %s THEN 40 ELSE 0 END")
        score_params.append(domain_hint)
    for _token in tokens:
        score_parts.append("CASE WHEN content ILIKE %s THEN 10 ELSE 0 END")
    score_params.extend(token_patterns)

    if tokens:
        token_clauses = " OR ".join("content ILIKE %s" for _token in tokens)
        search_clause = f"(content ILIKE %s OR ({token_clauses}))"
        search_params: list[Any] = [full_pattern, *token_patterns]
    else:
        search_clause = "content ILIKE %s"
        search_params = [full_pattern]

    clauses = [search_clause]
    filter_params: list[Any] = []
    if domain:
        clauses.append("domain = %s")
        filter_params.append(domain)
    if stage:
        clauses.append("stage = %s")
        filter_params.append(stage)
    params = [*score_params, *search_params, *filter_params, limit]
    sql = f"""
        SELECT chunk_id, asset_id, title, source_path, normalized_path, domain, stage, content,
               {' + '.join(score_parts)} AS score
        FROM hxy_knowledge_chunks
        WHERE {' AND '.join(clauses)}
        ORDER BY score DESC, updated_at DESC
        LIMIT %s
    """
    return sql, params


def normalize_review_question(question: str) -> str:
    stop_chars = "，。！？?；;：:、（）()[]【】\"'“”‘’"
    normalized = question or ""
    for char in stop_chars:
        normalized = normalized.replace(char, "")
    return "".join(normalized.split())


def build_existing_open_review_task_query(question: str, reason: str | None = None) -> tuple[str, list[Any]]:
    normalized = normalize_review_question(question)
    reason_clause = ""
    params: list[Any] = [normalized]
    if reason:
        reason_clause = " AND reason = %s"
        params.append(reason)
    sql = """
        SELECT task_id::text
        FROM hxy_knowledge_review_tasks
        WHERE status = 'open'
          AND COALESCE(payload_json->'correction_package'->>'normalized_question', '') = %s
          {reason_clause}
        ORDER BY
          CASE priority WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END,
          created_at DESC
        LIMIT 1
    """.format(reason_clause=reason_clause)
    return sql, params


def build_training_operating_issue_signal(
    *,
    store_id: str | None,
    days: int,
    retrain_count: int,
    top_mistakes: list[dict[str, Any]],
) -> dict[str, Any]:
    bounded_days = max(1, min(int(days or 7), 90))
    top_mistake = top_mistakes[0] if top_mistakes else {}
    mistake_text = str(top_mistake.get("mistake") or "").strip()
    should_create_issue = retrain_count >= 2 or bool(top_mistake and int(top_mistake.get("count") or 0) >= 2)
    if not should_create_issue:
        return {
            "should_create_issue": False,
            "title": "门店话术训练稳定",
            "priority": "low",
            "reason": f"近 {bounded_days} 天未出现需要升级为经营议题的复训风险。",
            "recommended_action": "继续保持每日训练，挑选高分话术沉淀为标准样本。",
        }

    priority = "high" if retrain_count >= 2 or int(top_mistake.get("count") or 0) >= 3 else "medium"
    reason_parts = [f"近 {bounded_days} 天有 {retrain_count} 次话术需要复训。"]
    if mistake_text:
        reason_parts.append(f"高频错误：{mistake_text}")
    return {
        "should_create_issue": True,
        "title": "门店话术复训风险",
        "priority": priority,
        "reason": " ".join(reason_parts),
        "recommended_action": "今天班前会先处理复训员工和高频错误，完成后再抽查一次同题话术。",
        "store_id": store_id or "all",
        "domain": "training",
        "owner": "店长/运营负责人",
    }


def build_training_briefing_tasks(
    low_score_employees: list[dict[str, Any]],
    top_mistakes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    correction_focus = (
        str(top_mistakes[0].get("mistake") or "").strip()
        if top_mistakes
        else "按顾客状态追问，再讲清清泡调补养区别，避开治疗承诺。"
    )
    tasks = []
    for employee in low_score_employees[:5]:
        tasks.append(
            {
                "employee_id": employee.get("employee_id") or "unknown",
                "employee_name": employee.get("employee_name") or "未命名员工",
                "training_focus": "清泡调补养门店推荐话术",
                "practice_question": "顾客问：清泡调补养有什么区别？请用 30 秒回答，先问状态，再推荐。",
                "correction_focus": correction_focus,
                "acceptance_standard": "现场复述通过，并连续 2 次达到 75 分以上。",
                "operating_metric": "调补养占比",
            }
        )
    if not tasks and top_mistakes:
        tasks.append(
            {
                "employee_id": "all",
                "employee_name": "全员",
                "training_focus": "高频错误纠偏",
                "practice_question": "顾客问：这个能不能治疗失眠？请用合规表达回答。",
                "correction_focus": correction_focus,
                "acceptance_standard": "班前会抽查 3 人，回答不出现治疗、治愈、保证有效。",
                "operating_metric": "投诉风险",
            }
        )
    return tasks


def _contains_any(text: str, terms: list[str]) -> bool:
    return any(term in text for term in terms)


def build_training_operating_impact_signals(
    *,
    days: int,
    retrain_count: int,
    low_score_employees: list[dict[str, Any]],
    top_mistakes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    bounded_days = max(1, min(int(days or 7), 90))
    low_score_count = len(low_score_employees or [])
    worst_score = min(
        [int(item.get("average_score") or 0) for item in low_score_employees or []],
        default=100,
    )
    mistake_text = " ".join(str(item.get("mistake") or "") for item in top_mistakes or [])
    has_training_risk = retrain_count > 0 or low_score_count > 0
    high_training_risk = retrain_count >= 2 or worst_score < 70

    signals: list[dict[str, Any]] = []
    if has_training_risk:
        training_signal = f"近 {bounded_days} 天有 {retrain_count} 次复训，{low_score_count} 名员工低于验收线。"
        risk_level = "high" if high_training_risk else "medium"
        signals.append(
            {
                "metric": "调补养占比",
                "risk_level": risk_level,
                "training_signal": training_signal,
                "reason": "员工讲不清清泡调补养区别时，顾客容易停留在清泡，升级项目占比会被压低。",
                "next_action": "班前会先练顾客状态追问，再用 30 秒讲清清泡、调泡、补泡、养泡的选择逻辑。",
            }
        )
        signals.append(
            {
                "metric": "客单价",
                "risk_level": risk_level,
                "training_signal": training_signal,
                "reason": "升级推荐不稳定会让员工只卖基础项目，客单价缺少可控提升动作。",
                "next_action": "抽查低分员工的升级推荐话术，要求先问状态、再给一档明确推荐、最后确认顾客感受。",
            }
        )

    if _contains_any(mistake_text, ["治疗", "治愈", "保证", "肯定有效", "失眠", "疾病"]):
        count = sum(int(item.get("count") or 0) for item in top_mistakes or [])
        signals.append(
            {
                "metric": "投诉风险",
                "risk_level": "high" if count >= 2 else "medium",
                "training_signal": f"近 {bounded_days} 天出现禁用或高风险表达 {count} 次。",
                "reason": "治疗、治愈、保证有效等表达会放大合规和客诉风险，必须优先纠偏。",
                "next_action": "今天抽查所有员工禁用表达，把回答统一改成放松、状态建议和到店感受描述。",
            }
        )

    if _contains_any(mistake_text, ["状态", "追问", "复访", "顾客", "随便", "需求"]) or has_training_risk:
        signals.append(
            {
                "metric": "复购率",
                "risk_level": "medium" if has_training_risk else "low",
                "training_signal": f"近 {bounded_days} 天训练暴露出顾客状态识别和推荐承接需要复盘。",
                "reason": "员工如果没有问清顾客状态，服务后就难以形成复访理由和下一次推荐。",
                "next_action": "复训每位员工的三问法：最近累不累、睡得怎么样、手脚冷热如何，并记录顾客下次建议。",
            }
        )

    if not signals:
        signals.append(
            {
                "metric": "训练通过率",
                "risk_level": "low",
                "training_signal": f"近 {bounded_days} 天未发现需要升级的训练风险。",
                "reason": "当前训练记录没有暴露明显经营风险，但仍需持续抽查真实服务现场。",
                "next_action": "挑选高分话术沉淀为门店标准样本，并每周复查一次。",
            }
        )
    return signals


class KnowledgeRepository:
    def __init__(self, database_url: str):
        if not database_url:
            raise ValueError("database_url is required")
        if psycopg is None:
            raise RuntimeError("psycopg is not installed")
        self.database_url = database_url

    def connect(self):
        return psycopg.connect(self.database_url, row_factory=dict_row)

    def clear_run(self, run_name: str) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM hxy_knowledge_chunks WHERE run_name = %s", (run_name,))
            conn.execute("DELETE FROM hxy_knowledge_assets WHERE run_name = %s", (run_name,))
            conn.execute("DELETE FROM hxy_knowledge_import_runs WHERE run_name = %s", (run_name,))

    def upsert_run(self, run_name: str, manifest_path: str, index_path: str, asset_count: int, chunk_count: int, status: str = "completed") -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO hxy_knowledge_import_runs (run_name, source_manifest_path, source_index_path, status, asset_count, chunk_count, finished_at)
                VALUES (%s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (run_name) DO UPDATE SET
                  source_manifest_path = EXCLUDED.source_manifest_path,
                  source_index_path = EXCLUDED.source_index_path,
                  status = EXCLUDED.status,
                  asset_count = EXCLUDED.asset_count,
                  chunk_count = EXCLUDED.chunk_count,
                  finished_at = NOW()
                """,
                (run_name, manifest_path, index_path, status, asset_count, chunk_count),
            )

    def upsert_assets(self, assets: list[dict[str, Any]]) -> None:
        with self.connect() as conn:
            for asset in assets:
                conn.execute(
                    """
                    INSERT INTO hxy_knowledge_assets (
                      asset_id, run_name, title, file_name, source_path, normalized_path, extension, mime_type,
                      file_size, sha256, domain, stage, status, warnings, quality_score, quality_grade,
                      quality_scores_json, metadata_json, updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s::jsonb, %s::jsonb, NOW())
                    ON CONFLICT (asset_id) DO UPDATE SET
                      run_name = EXCLUDED.run_name,
                      title = EXCLUDED.title,
                      file_name = EXCLUDED.file_name,
                      source_path = EXCLUDED.source_path,
                      normalized_path = EXCLUDED.normalized_path,
                      extension = EXCLUDED.extension,
                      mime_type = EXCLUDED.mime_type,
                      file_size = EXCLUDED.file_size,
                      sha256 = EXCLUDED.sha256,
                      domain = EXCLUDED.domain,
                      stage = EXCLUDED.stage,
                      status = EXCLUDED.status,
                      warnings = EXCLUDED.warnings,
                      quality_score = EXCLUDED.quality_score,
                      quality_grade = EXCLUDED.quality_grade,
                      quality_scores_json = EXCLUDED.quality_scores_json,
                      metadata_json = EXCLUDED.metadata_json,
                      updated_at = NOW()
                    """,
                    (
                        asset["asset_id"],
                        asset["run_name"],
                        asset["title"],
                        asset["file_name"],
                        asset["source_path"],
                        asset["normalized_path"],
                        asset["extension"],
                        asset["mime_type"],
                        asset["file_size"],
                        asset["sha256"],
                        asset["domain"],
                        asset["stage"],
                        asset["status"],
                        json.dumps(asset["warnings"], ensure_ascii=False),
                        asset.get("quality_score") or 0,
                        asset.get("quality_grade") or "unknown",
                        json.dumps(asset.get("quality_scores") or {}, ensure_ascii=False),
                        json.dumps(asset["metadata"], ensure_ascii=False),
                    ),
                )

    def upsert_chunks(self, chunks: list[dict[str, Any]]) -> None:
        with self.connect() as conn:
            for chunk in chunks:
                conn.execute(
                    """
                    INSERT INTO hxy_knowledge_chunks (
                      chunk_id, asset_id, run_name, chunk_index, title, source_path, normalized_path,
                      domain, stage, content, metadata_json, updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, NOW())
                    ON CONFLICT (chunk_id) DO UPDATE SET
                      asset_id = EXCLUDED.asset_id,
                      run_name = EXCLUDED.run_name,
                      chunk_index = EXCLUDED.chunk_index,
                      title = EXCLUDED.title,
                      source_path = EXCLUDED.source_path,
                      normalized_path = EXCLUDED.normalized_path,
                      domain = EXCLUDED.domain,
                      stage = EXCLUDED.stage,
                      content = EXCLUDED.content,
                      metadata_json = EXCLUDED.metadata_json,
                      updated_at = NOW()
                    """,
                    (
                        chunk["chunk_id"],
                        chunk["asset_id"],
                        chunk["run_name"],
                        chunk["chunk_index"],
                        chunk["title"],
                        chunk["source_path"],
                        chunk["normalized_path"],
                        chunk["domain"],
                        chunk["stage"],
                        chunk["content"],
                        json.dumps(chunk["metadata"], ensure_ascii=False),
                    ),
                )

    def upsert_image_understandings(self, records: list[dict[str, Any]]) -> None:
        if not records:
            return
        with self.connect() as conn:
            for record in records:
                conn.execute(
                    """
                    INSERT INTO hxy_knowledge_image_understandings (
                      asset_id, run_name, source_path, normalized_path, title, image_type,
                      visual_summary, business_summary, ocr_text, detected_entities, prices,
                      related_domains, confidence, qa_ready, needs_review, payload_json, updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s, %s, %s, %s::jsonb, NOW())
                    ON CONFLICT (asset_id, run_name) DO UPDATE SET
                      source_path = EXCLUDED.source_path,
                      normalized_path = EXCLUDED.normalized_path,
                      title = EXCLUDED.title,
                      image_type = EXCLUDED.image_type,
                      visual_summary = EXCLUDED.visual_summary,
                      business_summary = EXCLUDED.business_summary,
                      ocr_text = EXCLUDED.ocr_text,
                      detected_entities = EXCLUDED.detected_entities,
                      prices = EXCLUDED.prices,
                      related_domains = EXCLUDED.related_domains,
                      confidence = EXCLUDED.confidence,
                      qa_ready = EXCLUDED.qa_ready,
                      needs_review = EXCLUDED.needs_review,
                      payload_json = EXCLUDED.payload_json,
                      updated_at = NOW()
                    """,
                    (
                        record.get("asset_id") or None,
                        record.get("run_name") or "",
                        record.get("source_path") or "",
                        record.get("normalized_path") or "",
                        record.get("title") or "",
                        record.get("image_type") or "general_image",
                        record.get("visual_summary") or "",
                        record.get("business_summary") or "",
                        record.get("ocr_text") or "",
                        json.dumps(record.get("detected_entities") or [], ensure_ascii=False),
                        json.dumps(record.get("prices") or [], ensure_ascii=False),
                        json.dumps(record.get("related_domains") or [], ensure_ascii=False),
                        record.get("confidence") or 0,
                        bool(record.get("qa_ready")),
                        bool(record.get("needs_review", True)),
                        json.dumps(record.get("payload") or record, ensure_ascii=False),
                    ),
                )

    def summary(self) -> dict[str, Any]:
        with self.connect() as conn:
            asset_count = conn.execute("SELECT count(*) AS count FROM hxy_knowledge_assets").fetchone()["count"]
            chunk_count = conn.execute("SELECT count(*) AS count FROM hxy_knowledge_chunks").fetchone()["count"]
            domains = conn.execute("SELECT domain, count(*) AS count FROM hxy_knowledge_assets GROUP BY domain ORDER BY domain").fetchall()
            review_count = conn.execute("SELECT count(*) AS count FROM hxy_knowledge_assets WHERE status = 'needs_review'").fetchone()["count"]
        return {"asset_count": asset_count, "chunk_count": chunk_count, "domains": domains, "review_count": review_count}

    def assets(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT asset_id, title, file_name, source_path, domain, stage, status,
                       quality_score::float, quality_grade, quality_scores_json,
                       normalized_path, updated_at
                FROM hxy_knowledge_assets
                ORDER BY updated_at DESC
                LIMIT %s
                """,
                (limit,),
            ).fetchall()

    def search(
        self,
        query: str,
        domain: str | None = None,
        stage: str | None = None,
        limit: int = 20,
        domain_hint: str | None = None,
    ) -> list[dict[str, Any]]:
        sql, params = build_search_query(query, domain=domain, stage=stage, limit=limit, domain_hint=domain_hint)
        with self.connect() as conn:
            return conn.execute(sql, params).fetchall()

    def save_answer_run(self, payload: dict[str, Any]) -> str:
        with self.connect() as conn:
            row = conn.execute(
                """
                INSERT INTO hxy_knowledge_answer_runs (
                  question, normalized_query, intent, audience, answer, confidence,
                  needs_review, evidence_count, payload_json
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                RETURNING answer_id::text
                """,
                (
                    payload.get("question") or "",
                    payload.get("query") or "",
                    payload.get("intent") or "unknown",
                    payload.get("audience") or "general",
                    payload.get("answer") or "",
                    payload.get("confidence") or "low",
                    bool(payload.get("needs_review", True)),
                    len(payload.get("evidence") or payload.get("sources") or []),
                    json.dumps(payload, ensure_ascii=False),
                ),
            ).fetchone()
        return row["answer_id"]

    def save_feedback(self, payload: dict[str, Any]) -> str:
        with self.connect() as conn:
            row = conn.execute(
                """
                INSERT INTO hxy_knowledge_feedback (
                  answer_id, question, rating, note, payload_json
                )
                VALUES (%s, %s, %s, %s, %s::jsonb)
                RETURNING feedback_id::text
                """,
                (
                    payload.get("answer_id") or None,
                    payload.get("question") or "",
                    payload["rating"],
                    payload.get("note") or "",
                    json.dumps(payload, ensure_ascii=False),
                ),
            ).fetchone()
        return row["feedback_id"]

    def create_review_task(self, payload: dict[str, Any]) -> str:
        with self.connect() as conn:
            existing_sql, existing_params = build_existing_open_review_task_query(
                payload.get("question") or "",
                reason=payload.get("reason") or None,
            )
            existing = conn.execute(existing_sql, existing_params).fetchone()
            if existing:
                return existing["task_id"]
            row = conn.execute(
                """
                INSERT INTO hxy_knowledge_review_tasks (
                  answer_id, feedback_id, question, intent, reason, status, priority, payload_json
                )
                VALUES (%s, %s, %s, %s, %s, 'open', %s, %s::jsonb)
                RETURNING task_id::text
                """,
                (
                    payload.get("answer_id") or None,
                    payload.get("feedback_id") or None,
                    payload.get("question") or "",
                    payload.get("intent") or "unknown",
                    payload.get("reason") or "",
                    payload.get("priority") or "medium",
                    json.dumps(payload, ensure_ascii=False),
                ),
            ).fetchone()
        return row["task_id"]

    def review_tasks(self, status: str = "open", limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT task_id::text, answer_id::text, feedback_id::text, question, intent, reason,
                       status, priority, payload_json, created_at, resolved_at
                FROM hxy_knowledge_review_tasks
                WHERE status = %s
                ORDER BY
                  CASE priority WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END,
                  created_at DESC
                LIMIT %s
                """,
                (status, limit),
            ).fetchall()

    def resolve_review_task(self, task_id: str, status: str = "resolved") -> bool:
        with self.connect() as conn:
            row = conn.execute(
                """
                UPDATE hxy_knowledge_review_tasks
                SET status = %s, resolved_at = NOW()
                WHERE task_id = %s
                RETURNING task_id::text
                """,
                (status, task_id),
            ).fetchone()
        return row is not None

    def save_training_session(self, payload: dict[str, Any]) -> str:
        with self.connect() as conn:
            row = conn.execute(
                """
                INSERT INTO hxy_training_sessions (
                  employee_id, employee_name, store_id, store_name, training_item,
                  customer_question, employee_answer, scenario, role, score, level,
                  needs_retrain, dimensions_json, correction_points_json,
                  follow_up_questions_json, retraining_task_json, answer_card_draft_json,
                  review_task_id, capability_profile_json, adaptive_retrain_plan_json,
                  operating_metric_links_json, payload_json
                )
                VALUES (
                  %s, %s, %s, %s, %s,
                  %s, %s, %s, %s, %s, %s,
                  %s, %s::jsonb, %s::jsonb,
                  %s::jsonb, %s::jsonb, %s::jsonb,
                  %s, %s::jsonb, %s::jsonb,
                  %s::jsonb, %s::jsonb
                )
                RETURNING session_id::text
                """,
                (
                    payload.get("employee_id") or "",
                    payload.get("employee_name") or "",
                    payload.get("store_id") or "",
                    payload.get("store_name") or "",
                    payload.get("training_item") or "",
                    payload.get("customer_question") or "",
                    payload.get("employee_answer") or "",
                    payload.get("scenario") or "门店员工培训",
                    payload.get("role") or "门店员工",
                    int(payload.get("score") or 0),
                    payload.get("level") or "retrain",
                    bool(payload.get("needs_retrain")),
                    json.dumps(payload.get("dimensions") or [], ensure_ascii=False),
                    json.dumps(payload.get("correction_points") or [], ensure_ascii=False),
                    json.dumps(payload.get("follow_up_questions") or [], ensure_ascii=False),
                    json.dumps(payload.get("retraining_task") or {}, ensure_ascii=False),
                    json.dumps(payload.get("answer_card_draft"), ensure_ascii=False) if payload.get("answer_card_draft") is not None else None,
                    payload.get("review_task_id") or None,
                    json.dumps(payload.get("capability_profile") or {}, ensure_ascii=False),
                    json.dumps(payload.get("adaptive_retrain_plan") or {}, ensure_ascii=False),
                    json.dumps(payload.get("operating_metric_links") or [], ensure_ascii=False),
                    json.dumps(payload.get("payload") or payload, ensure_ascii=False),
                ),
            ).fetchone()
        return row["session_id"]

    def save_training_manager_acceptance(self, payload: dict[str, Any]) -> str:
        with self.connect() as conn:
            row = conn.execute(
                """
                INSERT INTO hxy_training_manager_acceptances (
                  session_id, manager_id, manager_name, accepted, score, note,
                  operating_metric_links_json, payload_json
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb)
                RETURNING acceptance_id::text
                """,
                (
                    payload.get("session_id") or "",
                    payload.get("manager_id") or "",
                    payload.get("manager_name") or "",
                    bool(payload.get("accepted")),
                    int(payload.get("score") or 0),
                    payload.get("note") or "",
                    json.dumps(payload.get("operating_metric_links") or [], ensure_ascii=False),
                    json.dumps(payload, ensure_ascii=False),
                ),
            ).fetchone()
        return row["acceptance_id"]

    def training_acceptance_evidence(self, session_id: str, pass_score: int = 75, required_pass_count: int = 2) -> dict[str, Any]:
        with self.connect() as conn:
            session = conn.execute(
                """
                SELECT session_id::text, employee_id, store_id, training_item
                FROM hxy_training_sessions
                WHERE session_id = %s
                """,
                (session_id,),
            ).fetchone()
            if not session:
                return {
                    "version": "hxy-training-acceptance-evidence.v1",
                    "session_id": session_id,
                    "pass_score": pass_score,
                    "required_pass_count": required_pass_count,
                    "consecutive_pass_count": 0,
                    "eligible": False,
                    "reason": "未找到训练记录，不能通过验收。",
                }
            rows = conn.execute(
                """
                SELECT score, needs_retrain
                FROM hxy_training_sessions
                WHERE employee_id = %s AND store_id = %s AND training_item = %s
                ORDER BY created_at DESC
                LIMIT 20
                """,
                (session["employee_id"], session["store_id"], session["training_item"]),
            ).fetchall()

        consecutive_pass_count = 0
        for row in rows:
            if int(row.get("score") or 0) >= pass_score and not row.get("needs_retrain"):
                consecutive_pass_count += 1
                continue
            break

        eligible = consecutive_pass_count >= required_pass_count
        reason = (
            f"同一训练项目已连续达标 {consecutive_pass_count} 次。"
            if eligible
            else f"同一训练项目最近只连续达标 {consecutive_pass_count} 次，还需要 {required_pass_count} 次。"
        )
        return {
            "version": "hxy-training-acceptance-evidence.v1",
            "session_id": session_id,
            "employee_id": session["employee_id"],
            "store_id": session["store_id"],
            "training_item": session["training_item"],
            "pass_score": pass_score,
            "required_pass_count": required_pass_count,
            "consecutive_pass_count": consecutive_pass_count,
            "eligible": eligible,
            "reason": reason,
        }

    def upsert_training_capability_level(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute(
                """
                INSERT INTO hxy_training_capability_levels (
                  employee_id, store_id, training_item, current_level, accepted_count,
                  last_acceptance_id, acceptance_evidence_json
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
                ON CONFLICT (employee_id, store_id, training_item)
                DO UPDATE SET
                  current_level = EXCLUDED.current_level,
                  accepted_count = EXCLUDED.accepted_count,
                  last_acceptance_id = EXCLUDED.last_acceptance_id,
                  acceptance_evidence_json = EXCLUDED.acceptance_evidence_json,
                  updated_at = NOW()
                RETURNING capability_id::text, employee_id, store_id, training_item,
                          current_level, accepted_count, last_acceptance_id
                """,
                (
                    payload.get("employee_id") or "",
                    payload.get("store_id") or "",
                    payload.get("training_item") or "",
                    payload.get("current_level") or "standard",
                    int(payload.get("accepted_count") or 0),
                    payload.get("last_acceptance_id") or "",
                    json.dumps(payload.get("acceptance_evidence") or {}, ensure_ascii=False),
                ),
            ).fetchone()
        return dict(row)

    def training_capability_levels(
        self,
        store_id: str | None = None,
        employee_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        filters: list[str] = []
        params: list[Any] = []
        if store_id:
            filters.append("store_id = %s")
            params.append(store_id)
        if employee_id:
            filters.append("employee_id = %s")
            params.append(employee_id)
        where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
        params.append(limit)
        with self.connect() as conn:
            return conn.execute(
                f"""
                SELECT capability_id::text, employee_id, store_id, training_item,
                       current_level, accepted_count, last_acceptance_id,
                       acceptance_evidence_json, updated_at, created_at
                FROM hxy_training_capability_levels
                {where_clause}
                ORDER BY updated_at DESC
                LIMIT %s
                """,
                tuple(params),
            ).fetchall()

    def training_sessions(self, store_id: str | None = None, employee_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        filters: list[str] = []
        params: list[Any] = []
        if store_id:
            filters.append("store_id = %s")
            params.append(store_id)
        if employee_id:
            filters.append("employee_id = %s")
            params.append(employee_id)
        where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
        params.append(limit)
        with self.connect() as conn:
            return conn.execute(
                f"""
                SELECT session_id::text, employee_id, employee_name, store_id, store_name,
                       training_item, customer_question, employee_answer, scenario, role,
                       score, level, needs_retrain, dimensions_json, correction_points_json,
                       follow_up_questions_json, retraining_task_json, answer_card_draft_json,
                       capability_profile_json, adaptive_retrain_plan_json,
                       operating_metric_links_json, review_task_id, created_at
                FROM hxy_training_sessions
                {where_clause}
                ORDER BY created_at DESC
                LIMIT %s
                """,
                tuple(params),
            ).fetchall()

    def training_manager_summary(self, store_id: str | None = None, days: int = 7) -> dict[str, Any]:
        filters = ["created_at >= NOW() - (%s::int * INTERVAL '1 day')"]
        params: list[Any] = [max(1, min(int(days or 7), 90))]
        if store_id:
            filters.append("store_id = %s")
            params.append(store_id)
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT employee_id, employee_name, store_id, store_name, score, level,
                       needs_retrain, correction_points_json, created_at
                FROM hxy_training_sessions
                WHERE {' AND '.join(filters)}
                ORDER BY created_at DESC
                """,
                tuple(params),
            ).fetchall()

        employee_stats: dict[str, dict[str, Any]] = {}
        mistake_counts: dict[str, int] = {}
        total_score = 0
        retrain_count = 0
        for row in rows:
            score = int(row.get("score") or 0)
            total_score += score
            if row.get("needs_retrain"):
                retrain_count += 1
            employee_id = row.get("employee_id") or "unknown"
            stat = employee_stats.setdefault(
                employee_id,
                {
                    "employee_id": employee_id,
                    "employee_name": row.get("employee_name") or "未命名员工",
                    "sessions": 0,
                    "score_total": 0,
                    "retrain_count": 0,
                },
            )
            stat["sessions"] += 1
            stat["score_total"] += score
            if row.get("needs_retrain"):
                stat["retrain_count"] += 1
            for point in row.get("correction_points_json") or []:
                mistake = str(point).strip()
                if mistake:
                    mistake_counts[mistake] = mistake_counts.get(mistake, 0) + 1

        low_score_employees = []
        for stat in employee_stats.values():
            average = round(stat["score_total"] / stat["sessions"]) if stat["sessions"] else 0
            if average < 75 or stat["retrain_count"]:
                low_score_employees.append(
                    {
                        "employee_id": stat["employee_id"],
                        "employee_name": stat["employee_name"],
                        "average_score": average,
                        "sessions": stat["sessions"],
                        "retrain_count": stat["retrain_count"],
                    }
                )
        low_score_employees.sort(key=lambda item: (item["average_score"], -item["retrain_count"]))
        top_mistakes = [
            {"mistake": mistake, "count": count}
            for mistake, count in sorted(mistake_counts.items(), key=lambda item: item[1], reverse=True)[:5]
        ]
        suggested_actions = []
        if retrain_count:
            suggested_actions.append("今天班前会先练清泡调补养区别、顾客状态追问和禁用表达。")
        if top_mistakes:
            suggested_actions.append(f"重点纠偏：{top_mistakes[0]['mistake']}")
        if not suggested_actions:
            suggested_actions.append("继续保持每日训练，挑选高分话术提交为答案卡候选。")

        return {
            "version": "hxy-training-manager-summary.v1",
            "store_id": store_id or "all",
            "days": params[0],
            "total_sessions": len(rows),
            "average_score": round(total_score / len(rows)) if rows else 0,
            "retrain_count": retrain_count,
            "active_employee_count": len(employee_stats),
            "low_score_employees": low_score_employees[:10],
            "top_mistakes": top_mistakes,
            "suggested_actions": suggested_actions,
            "briefing_tasks": build_training_briefing_tasks(low_score_employees, top_mistakes),
            "operating_impact_signals": build_training_operating_impact_signals(
                days=params[0],
                retrain_count=retrain_count,
                low_score_employees=low_score_employees,
                top_mistakes=top_mistakes,
            ),
            "operating_issue_signal": build_training_operating_issue_signal(
                store_id=store_id,
                days=params[0],
                retrain_count=retrain_count,
                top_mistakes=top_mistakes,
            ),
        }

    def save_store_daily_metrics(self, payload: dict[str, Any]) -> str:
        diagnosis = payload.get("diagnosis") or {}
        product_mix = payload.get("product_mix") if isinstance(payload.get("product_mix"), dict) else {}
        with self.connect() as conn:
            row = conn.execute(
                """
                INSERT INTO hxy_store_daily_metrics (
                  store_id, store_name, business_date, revenue, target_revenue, orders,
                  average_ticket, target_average_ticket, repeat_rate, target_repeat_rate,
                  product_mix_json, training_retrain_count, customer_complaints,
                  raw_metrics_json, diagnosis_json, updated_at
                )
                VALUES (
                  %s, %s, %s, %s, %s, %s,
                  %s, %s, %s, %s,
                  %s::jsonb, %s, %s,
                  %s::jsonb, %s::jsonb, NOW()
                )
                ON CONFLICT (store_id, business_date) DO UPDATE SET
                  store_name = EXCLUDED.store_name,
                  revenue = EXCLUDED.revenue,
                  target_revenue = EXCLUDED.target_revenue,
                  orders = EXCLUDED.orders,
                  average_ticket = EXCLUDED.average_ticket,
                  target_average_ticket = EXCLUDED.target_average_ticket,
                  repeat_rate = EXCLUDED.repeat_rate,
                  target_repeat_rate = EXCLUDED.target_repeat_rate,
                  product_mix_json = EXCLUDED.product_mix_json,
                  training_retrain_count = EXCLUDED.training_retrain_count,
                  customer_complaints = EXCLUDED.customer_complaints,
                  raw_metrics_json = EXCLUDED.raw_metrics_json,
                  diagnosis_json = EXCLUDED.diagnosis_json,
                  updated_at = NOW()
                RETURNING metrics_id::text
                """,
                (
                    payload.get("store_id") or "",
                    payload.get("store_name") or "",
                    payload.get("business_date"),
                    payload.get("revenue") or 0,
                    payload.get("target_revenue") or 0,
                    int(payload.get("orders") or 0),
                    payload.get("average_ticket") or 0,
                    payload.get("target_average_ticket") or 0,
                    payload.get("repeat_rate") or 0,
                    payload.get("target_repeat_rate") or 0,
                    json.dumps(product_mix, ensure_ascii=False),
                    int(payload.get("training_retrain_count") or 0),
                    int(payload.get("customer_complaints") or 0),
                    json.dumps(payload, ensure_ascii=False),
                    json.dumps(diagnosis, ensure_ascii=False),
                ),
            ).fetchone()
        return row["metrics_id"]

    def create_answer_card(self, payload: dict[str, Any]) -> str:
        with self.connect() as conn:
            row = conn.execute(
                """
                INSERT INTO hxy_knowledge_answer_cards (
                  question_pattern, intent, audience, answer, reasoning, evidence,
                  corrections, next_actions, status, source_answer_id, updated_at
                )
                VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s, %s, NOW())
                RETURNING card_id::text
                """,
                (
                    payload["question_pattern"],
                    payload.get("intent") or "unknown",
                    payload.get("audience") or "general",
                    payload["answer"],
                    json.dumps(payload.get("reasoning") or [], ensure_ascii=False),
                    json.dumps(payload.get("evidence") or [], ensure_ascii=False),
                    json.dumps(payload.get("corrections") or [], ensure_ascii=False),
                    json.dumps(payload.get("next_actions") or [], ensure_ascii=False),
                    payload.get("status") or "draft",
                    payload.get("source_answer_id") or None,
                ),
            ).fetchone()
        return row["card_id"]

    def list_answer_cards(self, status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        filters = []
        params: list[Any] = []
        if status:
            filters.append("status = %s")
            params.append(status)
        where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
        params.append(limit)
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT card_id::text, question_pattern, intent, audience, answer, reasoning,
                       evidence, corrections, next_actions, status, source_answer_id::text,
                       created_at, updated_at
                FROM hxy_knowledge_answer_cards
                {where_clause}
                ORDER BY updated_at DESC
                LIMIT %s
                """,
                tuple(params),
            ).fetchall()
        return list(rows)

    def find_answer_card(self, question: str, intent: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT card_id::text, question_pattern, intent, audience, answer, reasoning,
                       evidence, corrections, next_actions, status, source_answer_id::text,
                       created_at, updated_at
                FROM hxy_knowledge_answer_cards
                WHERE status = 'approved'
                  AND intent = %s
                  AND (
                    %s ILIKE ('%%' || question_pattern || '%%')
                    OR question_pattern ILIKE ('%%' || %s || '%%')
                  )
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (intent, question, question),
            ).fetchone()
        return row
