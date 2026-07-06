import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_hxy_wiki_page_schema_requires_governance_fields():
    schema_path = ROOT / "knowledge" / "schema" / "hxy-wiki-page.schema.json"

    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    assert schema["title"] == "HXY Wiki Page"
    for field in [
        "id",
        "type",
        "title",
        "domain",
        "status",
        "sources",
        "confidence",
        "owner",
        "last_confirmed",
        "used_by",
        "risk_level",
    ]:
        assert field in schema["required"]


def test_compile_material_creates_reference_extract_not_approved():
    from apps.api.hxy_knowledge.knowledge_compiler import compile_material

    result = compile_material(
        {
            "asset_id": "asset-001",
            "title": "荷小悦定位讨论稿",
            "content": "荷小悦是社区轻养生品牌，主打泡脚和按摩。",
            "source_path": "knowledge/raw/inbox/positioning.md",
        }
    )

    assert result["status"] == "reference"
    assert result["memory_layer"] == "L1_structured_extract"
    assert result["sources"] == ["knowledge/raw/inbox/positioning.md"]
    assert result["official_use_allowed"] is False
    assert result["domain"] == "brand_positioning"


def test_extract_claims_marks_them_current_candidate_and_requires_review():
    from apps.api.hxy_knowledge.knowledge_compiler import extract_candidate_claims

    claims = extract_candidate_claims(
        {
            "extract_id": "extract-001",
            "content": "荷小悦不是传统足疗店。清泡调补养用于表达产品体系。",
            "sources": ["source.md"],
        }
    )

    assert len(claims) == 2
    assert all(claim["status"] == "current_candidate" for claim in claims)
    assert all(claim["requires_human_review"] is True for claim in claims)
    assert all(claim["official_use_allowed"] is False for claim in claims)


def test_extract_claims_distinguishes_compliance_boundary_from_overclaim():
    from apps.api.hxy_knowledge.knowledge_compiler import extract_candidate_claims

    claims = extract_candidate_claims(
        {
            "extract_id": "risk-extract-001",
            "content": (
                "我们这里是日常放松，不做治疗。"
                "草本泡脚不能替代医疗。"
                "员工不能承诺一次见效、包好、保证有效。"
                "禁止说治疗颈椎病。"
                "错误话术：草本泡脚可以治疗失眠。"
            ),
            "sources": ["risk.md"],
        }
    )
    by_text = {claim["claim"]: claim for claim in claims}

    assert by_text["我们这里是日常放松，不做治疗"]["risk_flags"] == []
    assert by_text["草本泡脚不能替代医疗"]["risk_flags"] == []
    assert by_text["员工不能承诺一次见效、包好、保证有效"]["risk_flags"] == ["forbidden_expression_reference"]
    assert by_text["禁止说治疗颈椎病"]["risk_flags"] == ["forbidden_expression_reference"]
    assert by_text["错误话术：草本泡脚可以治疗失眠"]["risk_flags"] == ["overclaim_risk"]


def test_extract_claims_does_not_mark_negative_effectiveness_as_overclaim():
    from apps.api.hxy_knowledge.knowledge_compiler import extract_candidate_claims

    claims = extract_candidate_claims(
        {
            "extract_id": "marketing-extract-001",
            "content": "广告有滞后效应，而且滞后之后还不一定有效应。",
            "sources": ["marketing.md"],
        }
    )

    assert claims[0]["risk_flags"] == []


def test_extract_claims_marks_checklists_as_forbidden_references_not_claims():
    from apps.api.hxy_knowledge.knowledge_compiler import extract_candidate_claims

    claims = extract_candidate_claims(
        {
            "extract_id": "risk-extract-002",
            "content": (
                "有没有一次见效、包好、保证有效。"
                "如果暗示疾病、疗效、诊断、改善、治疗，必须删除或改写。"
                "有没有把艾灸、热敷、拨筋说成治疗手段。"
                "我们这里不做脚气治疗。"
            ),
            "sources": ["risk.md"],
        }
    )
    by_text = {claim["claim"]: claim for claim in claims}

    assert by_text["有没有一次见效、包好、保证有效"]["risk_flags"] == ["forbidden_expression_reference"]
    assert by_text["如果暗示疾病、疗效、诊断、改善、治疗，必须删除或改写"]["risk_flags"] == [
        "forbidden_expression_reference"
    ]
    assert by_text["有没有把艾灸、热敷、拨筋说成治疗手段"]["risk_flags"] == ["forbidden_expression_reference"]
    assert by_text["我们这里不做脚气治疗"]["risk_flags"] == []


def test_extract_claims_splits_markdown_slides_and_filters_contact_noise():
    from apps.api.hxy_knowledge.knowledge_compiler import extract_candidate_claims

    claims = extract_candidate_claims(
        {
            "extract_id": "slide-extract-001",
            "content": (
                "[](Picture3.jpg)\n"
                "荷小悦 · 社区草本养生连锁品牌\n"
                "致力于成为中国社区的健康信任基础设施\n"
                "400-123-4567\n"
                "contact@hexiaoyue.com\n"
            ),
            "sources": ["bp.pdf.reference.txt"],
        }
    )

    texts = [claim["claim"] for claim in claims]
    assert "荷小悦 · 社区草本养生连锁品牌" in texts
    assert "致力于成为中国社区的健康信任基础设施" in texts
    assert all("Picture3.jpg" not in text for text in texts)
    assert all("contact@" not in text for text in texts)
    assert all("400-123-4567" not in text for text in texts)


def test_build_review_queue_prioritizes_high_value_claims_and_filters_pdf_noise():
    from apps.api.hxy_knowledge.knowledge_compiler import build_review_queue

    claims = [
        {
            "claim_id": "noise-page",
            "claim": "第 1 页 目录 1 2 3",
            "domain": "general",
            "sources": ["source.pdf"],
            "risk_flags": [],
        },
        {
            "claim_id": "store-model",
            "claim": "荷小悦社区小店建议控制面积、房间数量、人员配置和单店模型关键参数。",
            "domain": "general",
            "sources": ["source.pdf"],
            "risk_flags": [],
        },
        {
            "claim_id": "risk-medical",
            "claim": "员工不能承诺泡脚可以治疗失眠。",
            "domain": "risk_boundary",
            "sources": ["source.pdf"],
            "risk_flags": ["overclaim_risk"],
        },
    ]

    queue = build_review_queue(claims, limit=20)

    assert queue["version"] == "hxy-review-queue.v1"
    assert queue["total_claim_count"] == 3
    assert queue["noise_claim_count"] == 1
    assert [item["claim_id"] for item in queue["items"]] == ["risk-medical", "store-model"]
    assert queue["items"][0]["priority"] == "high"
    assert queue["items"][0]["recommended_reviewer"] == "运营/合规负责人"


def test_build_claim_triage_deduplicates_clusters_and_selects_representatives():
    from apps.api.hxy_knowledge.knowledge_compiler import build_claim_triage

    claims = [
        {
            "claim_id": "risk-1",
            "claim": "员工不能承诺泡脚可以治疗失眠。",
            "domain": "risk_boundary",
            "sources": ["risk-a.md"],
            "risk_flags": ["forbidden_expression_reference"],
        },
        {
            "claim_id": "risk-2",
            "claim": "员工不能承诺泡脚可以治疗失眠。",
            "domain": "risk_boundary",
            "sources": ["risk-b.md"],
            "risk_flags": ["forbidden_expression_reference"],
        },
        {
            "claim_id": "store-1",
            "claim": "荷小悦社区小店要围绕入口产品、房间数量、人员配置和单店模型关键参数做复核。",
            "domain": "store_model",
            "sources": ["store.md"],
            "risk_flags": [],
        },
        {
            "claim_id": "store-2",
            "claim": "荷小悦社区小店需要复核房间数量、人员配置和单店模型。",
            "domain": "store_model",
            "sources": ["store-2.md"],
            "risk_flags": [],
        },
        {
            "claim_id": "noise",
            "claim": "第 1 页 目录 1 2 3",
            "domain": "general",
            "sources": ["book.pdf"],
            "risk_flags": [],
        },
    ]

    triage = build_claim_triage(claims, limit=10)

    assert triage["version"] == "hxy-claim-triage.v1"
    assert triage["total_claim_count"] == 5
    assert triage["noise_claim_count"] == 1
    assert triage["duplicate_claim_count"] == 1
    assert triage["unique_reviewable_claim_count"] == 3
    assert triage["cluster_count"] == 2
    assert triage["selected_count"] == 2
    assert [item["claim_id"] for item in triage["items"]] == ["risk-1", "store-1"]
    risk_item = triage["items"][0]
    assert risk_item["duplicate_count"] == 1
    assert risk_item["cluster_member_count"] == 1
    assert risk_item["sources"] == ["risk-a.md", "risk-b.md"]
    store_item = triage["items"][1]
    assert store_item["cluster_member_count"] == 2
    assert store_item["cluster_id"].startswith("hxy-claim-cluster:")


def test_review_queue_prefers_hxy_claims_over_competitor_fragments():
    from apps.api.hxy_knowledge.knowledge_compiler import build_review_queue

    claims = [
        {
            "claim_id": "competitor-fragment",
            "claim": "二、加盟方式 单店加盟模式，优先西南区域，绑定医疗资源，投资40-70万元。",
            "domain": "franchise_finance",
            "sources": ["source.pdf"],
            "risk_flags": [],
        },
        {
            "claim_id": "page-break-fragment",
            "claim": "供应链体系：统一供应链配送泰式核心物料，建立古法手法培训体系。\f\f2，社区到底是什么",
            "domain": "employee_training",
            "sources": ["source.pdf"],
            "risk_flags": [],
        },
        {
            "claim_id": "hxy-store-model",
            "claim": "荷小悦社区小店要围绕入口产品、房间数量、人员配置和单店模型关键参数做复核。",
            "domain": "general",
            "sources": ["source.pdf"],
            "risk_flags": [],
        },
    ]

    queue = build_review_queue(claims, limit=20)

    assert queue["items"][0]["claim_id"] == "hxy-store-model"
    assert "page-break-fragment" not in [item["claim_id"] for item in queue["items"]]


def test_review_queue_uses_claim_triage_instead_of_raw_claim_flood():
    from apps.api.hxy_knowledge.knowledge_compiler import build_review_queue

    claims = []
    for index in range(30):
        claims.append(
            {
                "claim_id": f"store-{index}",
                "claim": f"荷小悦社区小店需要复核房间数量、人员配置和单店模型 {index}。",
                "domain": "store_model",
                "sources": [f"store-{index}.md"],
                "risk_flags": [],
            }
        )
    claims.append(
        {
            "claim_id": "risk",
            "claim": "员工不能承诺泡脚可以治疗失眠。",
            "domain": "risk_boundary",
            "sources": ["risk.md"],
            "risk_flags": ["forbidden_expression_reference"],
        }
    )

    queue = build_review_queue(claims, limit=20)

    assert queue["total_claim_count"] == 31
    assert queue["cluster_count"] == 2
    assert queue["reviewable_claim_count"] == 31
    assert len(queue["items"]) == 2
    assert [item["claim_id"] for item in queue["items"]] == ["risk", "store-0"]
    assert queue["items"][1]["cluster_member_count"] == 30


def test_claim_triage_deprioritizes_external_book_fragments_against_hxy_sources():
    from apps.api.hxy_knowledge.knowledge_compiler import build_review_queue

    claims = [
        {
            "claim_id": "external-therapy",
            "claim": "更好的心理治疗师需要长期训练。",
            "domain": "risk_boundary",
            "sources": ["knowledge/raw/inbox/荷小悦资料/09_知识库与参考资料/营销类书籍/动机与人格.pdf.reference.txt"],
            "risk_flags": ["overclaim_risk"],
        },
        {
            "claim_id": "hxy-risk",
            "claim": "员工不能承诺泡脚可以治疗失眠。",
            "domain": "risk_boundary",
            "sources": ["knowledge/raw/inbox/荷小悦资料/09_知识库与参考资料/09_风险与合规/荷小悦禁用表达库.md"],
            "risk_flags": ["forbidden_expression_reference"],
        },
        {
            "claim_id": "hxy-store",
            "claim": "荷小悦社区小店要围绕入口产品、房间数量、人员配置和单店模型关键参数做复核。",
            "domain": "store_model",
            "sources": ["knowledge/raw/inbox/荷小悦资料/03_门店模型/门店_荷小悦_小店模型_20260201.pdf.reference.txt"],
            "risk_flags": [],
        },
    ]

    queue = build_review_queue(claims, limit=3)

    assert [item["claim_id"] for item in queue["items"][:2]] == ["hxy-risk", "hxy-store"]
    assert queue["items"][0]["source_class"] == "risk_compliance"
    assert queue["items"][2]["source_class"] == "external_reference"
    assert queue["items"][2]["priority"] == "low"


def test_build_answer_card_drafts_only_uses_reviewable_claims():
    from apps.api.hxy_knowledge.knowledge_compiler import build_answer_card_drafts, build_review_queue

    claims = [
        {
            "claim_id": "brand-position",
            "claim": "荷小悦不是传统足疗店，而是社区轻养生门店。",
            "domain": "brand_positioning",
            "sources": ["brand.pdf"],
            "risk_flags": [],
        },
        {
            "claim_id": "noise",
            "claim": "PDF_TEXT_START 1 2 3",
            "domain": "general",
            "sources": ["brand.pdf"],
            "risk_flags": [],
        },
    ]
    queue = build_review_queue(claims, limit=20)

    drafts = build_answer_card_drafts(queue["items"], limit=10)

    assert drafts["version"] == "hxy-answer-card-drafts.v1"
    assert drafts["draft_count"] == 1
    draft = drafts["items"][0]
    assert draft["status"] == "draft"
    assert draft["official_use_allowed"] is False
    assert draft["requires_human_review"] is True
    assert draft["source_claim_ids"] == ["brand-position"]
    assert "当前为草稿" in draft["answer"]


def test_build_compliance_review_pack_prioritizes_human_review_without_approval():
    from apps.api.hxy_knowledge.knowledge_compiler import build_compliance_review_pack, build_review_queue

    claims = [
        {
            "claim_id": "safe-boundary",
            "claim": "员工不能承诺治疗、保证有效或一次见效，只能说日常放松和体验感受。",
            "domain": "risk_boundary",
            "sources": ["risk.md"],
            "risk_flags": ["forbidden_expression_reference"],
        },
        {
            "claim_id": "store-model",
            "claim": "荷小悦社区小店需要复核面积和人员配置。",
            "domain": "store_model",
            "sources": ["store.md"],
            "risk_flags": [],
        },
    ]
    queue = build_review_queue(claims, limit=20)

    pack = build_compliance_review_pack(queue["items"], limit=5)

    assert pack["version"] == "hxy-compliance-review-pack.v1"
    assert pack["status"] == "needs_human_review"
    assert pack["official_use_allowed"] is False
    assert pack["publish_allowed"] is False
    assert pack["count"] == 1
    item = pack["items"][0]
    assert item["claim_id"] == "safe-boundary"
    assert item["risk_level"] == "P0"
    assert item["required_decision"] == "approve_as_rule, needs_revision, or reject"
    assert item["review_question"] == "这条合规边界能否作为员工正式禁用表达或标准话术？"
    assert any("不能自动进入 approved answer card" in line for line in item["human_checklist"])


def test_compliance_review_pack_prioritizes_explicit_risk_flags_and_risk_sources():
    from apps.api.hxy_knowledge.knowledge_compiler import build_compliance_review_pack

    review_items = [
        {
            "claim_id": "generic-risk-boundary",
            "claim": "原则：记录品牌判断和禁用提醒。",
            "review_group": "risk_boundary",
            "risk_flags": [],
            "sources": ["knowledge/raw/inbox/marketing.md"],
        },
        {
            "claim_id": "explicit-risk",
            "claim": "不要把草本泡脚包装成治疗方案。",
            "review_group": "risk_boundary",
            "risk_flags": ["forbidden_expression_reference"],
            "sources": ["knowledge/raw/inbox/other.md"],
        },
        {
            "claim_id": "risk-source",
            "claim": "员工不能承诺一次见效。",
            "review_group": "employee_script",
            "risk_flags": [],
            "sources": ["knowledge/raw/inbox/荷小悦资料/09_知识库与参考资料/09_风险与合规/荷小悦禁用表达库.md"],
        },
    ]

    pack = build_compliance_review_pack(review_items, limit=3)

    assert [item["claim_id"] for item in pack["items"]] == [
        "explicit-risk",
        "risk-source",
        "generic-risk-boundary",
    ]


def test_compile_directory_builds_compliance_pack_from_full_reviewable_queue(tmp_path: Path):
    from apps.api.hxy_knowledge.knowledge_compiler import compile_directory

    raw_dir = tmp_path / "raw"
    wiki_dir = tmp_path / "wiki"
    raw_dir.mkdir(parents=True)
    for index in range(30):
        (raw_dir / f"brand-{index:02d}.md").write_text(
            f"荷小悦草本真现煮门店场景规则 {index}。荷小悦社区小店品牌表达要清楚具体 {index}。",
            encoding="utf-8",
        )
    (raw_dir / "risk.md").write_text(
        "员工不能承诺治疗、保证有效或一次见效，只能说日常放松和体验感受。",
        encoding="utf-8",
    )

    report = compile_directory(raw_dir, wiki_dir)

    assert 1 <= report["review_queue_count"] < 20
    assert report["compliance_review_count"] >= 1
    pack = json.loads((wiki_dir / "compliance-review-pack.json").read_text(encoding="utf-8"))
    assert pack["count"] >= 1
    assert any("治疗" in item["claim"] for item in pack["items"])


def test_compile_directory_writes_claim_triage_and_reports_reduction(tmp_path: Path):
    from apps.api.hxy_knowledge.knowledge_compiler import compile_directory

    raw_dir = tmp_path / "raw"
    wiki_dir = tmp_path / "wiki"
    raw_dir.mkdir(parents=True)
    for index in range(30):
        (raw_dir / f"store-{index:02d}.md").write_text(
            f"荷小悦社区小店需要复核房间数量、人员配置和单店模型 {index}。",
            encoding="utf-8",
        )
    (raw_dir / "risk.md").write_text(
        "员工不能承诺泡脚可以治疗失眠。",
        encoding="utf-8",
    )

    report = compile_directory(raw_dir, wiki_dir)

    assert (wiki_dir / "claim-triage.json").is_file()
    triage = json.loads((wiki_dir / "claim-triage.json").read_text(encoding="utf-8"))
    review_queue = json.loads((wiki_dir / "review-queue.json").read_text(encoding="utf-8"))
    assert report["claim_triage_cluster_count"] == 2
    assert report["claim_triage_selected_count"] == 2
    assert report["claim_triage_reduction_count"] >= 29
    assert triage["selected_count"] == 2
    assert review_queue["cluster_count"] == 2
    assert review_queue["items"][0]["claim_id"] != review_queue["items"][1]["claim_id"]


def test_build_knowledge_graph_links_claims_sources_domains_and_risks():
    from apps.api.hxy_knowledge.knowledge_compiler import build_knowledge_graph

    graph = build_knowledge_graph(
        extracts=[
            {
                "extract_id": "extract-001",
                "title": "定位讨论稿",
                "domain": "brand_positioning",
                "sources": ["source.md"],
            }
        ],
        claims=[
            {
                "claim_id": "claim-001",
                "claim": "荷小悦可以治疗失眠。",
                "domain": "risk_boundary",
                "sources": ["source.md"],
                "risk_flags": ["overclaim_risk"],
            }
        ],
    )

    assert graph["version"] == "hxy-knowledge-graph.v1"
    edge_types = {edge["type"] for edge in graph["edges"]}
    assert "belongs_to" in edge_types
    assert "supported_by" in edge_types
    assert "blocked_by" in edge_types


def test_compile_hxy_knowledge_cli_writes_wiki_graph_and_report(tmp_path: Path):
    raw_dir = tmp_path / "raw"
    wiki_dir = tmp_path / "wiki"
    report_path = tmp_path / "reports" / "compiler-latest.json"
    raw_dir.mkdir(parents=True)
    (raw_dir / "positioning.md").write_text(
        "# 荷小悦定位讨论\n\n荷小悦不是传统足疗店。清泡调补养用于表达产品体系。",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "compile-hxy-knowledge.py"),
            "--raw-dir",
            str(raw_dir),
            "--wiki-dir",
            str(wiki_dir),
            "--report",
            str(report_path),
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    assert (wiki_dir / "index.md").is_file()
    assert (wiki_dir / "graph.json").is_file()
    assert (wiki_dir / "review-queue.json").is_file()
    assert (wiki_dir / "answer-card-drafts.json").is_file()
    assert (wiki_dir / "compliance-review-pack.json").is_file()
    assert report_path.is_file()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["version"] == "hxy-knowledge-compiler-report.v1"
    assert report["extract_count"] == 1
    assert report["claim_count"] >= 2
    assert report["approved_count"] == 0
    assert report["review_queue_count"] >= 1
    assert "answer_card_draft_count" in report
    assert "compliance_review_count" in report


def test_compile_hxy_knowledge_cli_writes_harness_run_state_and_phases(tmp_path: Path):
    raw_dir = tmp_path / "raw"
    wiki_dir = tmp_path / "wiki"
    report_path = tmp_path / "reports" / "compiler-latest.json"
    runs_dir = tmp_path / "runs"
    run_id = "knowledge-run-test"
    raw_dir.mkdir(parents=True)
    (raw_dir / "positioning.md").write_text(
        "# 荷小悦定位讨论\n\n荷小悦不是传统足疗店。清泡调补养用于表达产品体系。",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "compile-hxy-knowledge.py"),
            "--raw-dir",
            str(raw_dir),
            "--wiki-dir",
            str(wiki_dir),
            "--report",
            str(report_path),
            "--run-id",
            run_id,
            "--runs-dir",
            str(runs_dir),
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    run_dir = runs_dir / run_id
    state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    assert state["version"] == "hxy-harness-state.v1"
    assert state["run_id"] == run_id
    assert state["goal"] == "compile_hxy_knowledge"
    assert state["status"] == "passed"
    assert state["gates"]["source_gate"] == "passed"
    assert state["gates"]["compile_gate"] == "passed"
    assert (run_dir / "phases" / "01_manifest.json").is_file()
    assert (run_dir / "phases" / "02_extracts.json").is_file()
    assert (run_dir / "phases" / "03_claims.json").is_file()
    assert (run_dir / "phases" / "04_graph.json").is_file()
    assert (run_dir / "phases" / "05_gates.json").is_file()
    assert (run_dir / "final-report.json").is_file()


def test_compile_hxy_knowledge_harness_blocks_empty_source_run(tmp_path: Path):
    raw_dir = tmp_path / "raw"
    wiki_dir = tmp_path / "wiki"
    report_path = tmp_path / "reports" / "compiler-latest.json"
    runs_dir = tmp_path / "runs"
    run_id = "empty-run"
    raw_dir.mkdir(parents=True)

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "compile-hxy-knowledge.py"),
            "--raw-dir",
            str(raw_dir),
            "--wiki-dir",
            str(wiki_dir),
            "--report",
            str(report_path),
            "--run-id",
            run_id,
            "--runs-dir",
            str(runs_dir),
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    state = json.loads((runs_dir / run_id / "state.json").read_text(encoding="utf-8"))
    assert state["status"] == "blocked"
    assert state["gates"]["source_gate"] == "failed"
    assert state["gates"]["compile_gate"] == "failed"
    assert "当前没有可编译资料" in " ".join(state["next_actions"])


def test_compiled_wiki_lint_flags_missing_sources_and_blocks_invalid_approved_pages():
    from apps.api.hxy_knowledge.enterprise_governance import lint_compiled_wiki_pages

    issues = lint_compiled_wiki_pages(
        [
            {
                "id": "wiki-reference-no-source",
                "type": "compiled_page",
                "title": "缺来源页面",
                "domain": "brand_positioning",
                "status": "reference",
                "sources": [],
            },
            {
                "id": "wiki-approved-no-owner",
                "type": "compiled_page",
                "title": "缺负责人已批准页面",
                "domain": "brand_positioning",
                "status": "approved",
                "sources": ["source.md"],
                "owner": "",
                "last_confirmed": "2026-06-28",
            },
        ]
    )

    issue_codes = {issue["code"] for issue in issues}
    assert "wiki_missing_sources" in issue_codes
    assert "wiki_approved_missing_owner" in issue_codes
    assert any(issue["blocks_release"] for issue in issues if issue["code"] == "wiki_approved_missing_owner")
