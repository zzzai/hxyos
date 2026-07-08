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


def test_build_core_decision_topics_prioritizes_hxy_0_to_1_operating_questions():
    from apps.api.hxy_knowledge.knowledge_compiler import build_core_decision_topics

    claims = [
        {
            "claim_id": "brand-positioning",
            "claim": "荷小悦核爆点定位要围绕社区高疲劳人群、草本泡脚按摩和轻恢复表达。",
            "domain": "brand_positioning",
            "sources": ["knowledge/raw/inbox/荷小悦资料/00_项目总览.md"],
            "risk_flags": [],
        },
        {
            "claim_id": "customer-evidence",
            "claim": "首店开业前需要补齐用户原话、复述测试、付费理由和替代方案。",
            "domain": "brand_positioning",
            "sources": ["knowledge/raw/inbox/荷小悦资料/00_项目总览.md"],
            "risk_flags": [],
        },
        {
            "claim_id": "external-fragment",
            "claim": "某外部书籍认为企业需要高效管理组织。",
            "domain": "management",
            "sources": ["knowledge/raw/inbox/营销类书籍/book.reference.txt"],
            "risk_flags": [],
        },
    ]

    topics = build_core_decision_topics(claims, limit=8)

    assert topics["version"] == "hxy-core-decision-topics.v1"
    assert topics["raw_claims_hidden"] is True
    assert topics["official_use_allowed"] is False
    assert topics["requires_human_review"] is True
    assert topics["core_topic_count"] >= 2
    serialized = json.dumps(topics, ensure_ascii=False)
    assert "品牌战略与核爆点定位" in serialized
    assert "顾客证据与首店验证" in serialized
    assert "这个判断现在能不能作为首店开业和对外口径的依据？" in serialized
    assert "某外部书籍认为企业需要高效管理组织" not in serialized
    assert "claim_id" not in topics["items"][0]
    assert "sample_claims" not in topics["items"][0]


def test_build_topic_draft_assets_turns_core_topics_into_review_assets():
    from apps.api.hxy_knowledge.knowledge_compiler import build_topic_draft_assets

    topics = {
        "version": "hxy-core-decision-topics.v1",
        "items": [
            {
                "version": "hxy-core-decision-topic.v1",
                "topic_id": "hxy-core-topic:brand_positioning",
                "topic_key": "brand_positioning",
                "title": "品牌战略与核爆点定位",
                "decision_question": "这个判断现在能不能作为首店开业和对外口径的依据？",
                "why_it_matters": "定位没定清楚，前台话术、门头、内容和员工训练都会漂。",
                "next_action": "补齐用户原话、复述测试、付费理由和替代方案。",
                "review_owner": "创始人",
                "priority": "P0",
                "evidence_count": 4,
                "source_samples": ["brand.md"],
                "source_classes": ["hxy_project"],
                "official_use_allowed": False,
                "requires_human_review": True,
            }
        ],
    }

    result = build_topic_draft_assets(topics)

    assert result["version"] == "hxy-topic-draft-assets.v1"
    assert result["status"] == "ready"
    assert result["count"] == 1
    asset = result["items"][0]
    assert asset["asset_type"] == "positioning_card"
    assert asset["status"] == "needs_review"
    assert asset["official_use_allowed"] is False
    assert asset["requires_human_review"] is True
    assert asset["authority_rule"] == "draft_assets_are_not_approved_knowledge"
    assert "用户原话" in " ".join(asset["draft"]["evidence_gaps"])


def test_build_topic_draft_assets_keeps_risk_boundary_p0_and_unapproved():
    from apps.api.hxy_knowledge.knowledge_compiler import build_topic_draft_assets

    topics = {
        "version": "hxy-core-decision-topics.v1",
        "items": [
            {
                "topic_id": "hxy-core-topic:risk_boundary",
                "topic_key": "risk_boundary",
                "title": "合规与功效表达边界",
                "decision_question": "哪些表达必须禁用？",
                "why_it_matters": "医疗化、疗效保证和夸大宣传是最高风险。",
                "next_action": "生成禁用表达、替代表达和发布前预检规则。",
                "review_owner": "运营/合规负责人",
                "priority": "P1",
                "evidence_count": 1,
                "source_samples": ["risk.md"],
                "source_classes": ["risk_compliance"],
            }
        ],
    }

    asset = build_topic_draft_assets(topics)["items"][0]

    assert asset["asset_type"] == "risk_card"
    assert asset["priority"] == "P0"
    assert asset["status"] == "needs_review"
    assert asset["official_use_allowed"] is False
    assert "禁用" in " ".join(asset["draft"]["next_actions"])


def test_build_topic_draft_assets_prefers_evidence_task_for_low_evidence_non_risk_topic():
    from apps.api.hxy_knowledge.knowledge_compiler import build_topic_draft_assets

    topics = {
        "version": "hxy-core-decision-topics.v1",
        "items": [
            {
                "topic_id": "hxy-core-topic:product_system",
                "topic_key": "product_system",
                "title": "产品服务体系与清泡调补养",
                "decision_question": "员工能不能讲清？",
                "why_it_matters": "产品说不清，菜单、价格、推荐路径和复购都会乱。",
                "next_action": "先确认主服务、组合服务、禁用功效和员工推荐标准话术。",
                "review_owner": "产品/运营负责人",
                "priority": "P0",
                "evidence_count": 1,
                "source_samples": ["product.md"],
                "source_classes": ["hxy_project"],
            }
        ],
    }

    asset = build_topic_draft_assets(topics)["items"][0]

    assert asset["asset_type"] == "evidence_task"
    assert asset["status"] == "needs_review"
    assert "补证据" in asset["draft"]["recommended_use"]


def test_build_topic_review_packets_turns_draft_assets_into_human_tasks():
    from apps.api.hxy_knowledge.knowledge_compiler import build_topic_review_packets

    draft_assets = {
        "version": "hxy-topic-draft-assets.v1",
        "items": [
            {
                "version": "hxy-topic-draft-asset.v1",
                "asset_id": "hxy-topic-draft:brand_positioning",
                "topic_key": "brand_positioning",
                "asset_type": "positioning_card",
                "title": "品牌战略与核爆点定位",
                "status": "needs_review",
                "priority": "P0",
                "review_owner": "创始人",
                "decision_question": "这个判断现在能不能作为首店开业和对外口径的依据？",
                "draft": {
                    "evidence_gaps": ["补齐目标用户原话"],
                    "next_actions": ["完成访谈"],
                },
                "source_samples": ["brand.md"],
            }
        ],
    }

    packets = build_topic_review_packets(draft_assets)

    assert packets["version"] == "hxy-topic-review-packets.v1"
    assert packets["status"] == "ready"
    assert packets["count"] == 1
    packet = packets["items"][0]
    assert packet["version"] == "hxy-topic-review-packet.v1"
    assert packet["packet_id"] == "hxy-topic-review-packet:brand_positioning"
    assert packet["status"] == "open"
    assert packet["promotion_target"] == "approved_positioning_card"
    assert packet["decision_options"] == [
        "needs_more_evidence",
        "revise_draft",
        "ready_for_manual_approval",
        "reject",
    ]
    assert "真实顾客原话" in " ".join(packet["review_questions"])
    assert "不能自动发布" in packet["blocked_actions"]
    assert packet["official_use_allowed"] is False
    assert packet["requires_human_review"] is True


def test_build_topic_review_packets_keeps_risk_cards_blocked_and_p0():
    from apps.api.hxy_knowledge.knowledge_compiler import build_topic_review_packets

    draft_assets = {
        "version": "hxy-topic-draft-assets.v1",
        "items": [
            {
                "asset_id": "hxy-topic-draft:risk_boundary",
                "topic_key": "risk_boundary",
                "asset_type": "risk_card",
                "title": "合规与功效表达边界",
                "priority": "P1",
                "review_owner": "运营/合规负责人",
                "decision_question": "哪些表达必须禁用？",
                "draft": {
                    "evidence_gaps": ["确认禁用表达来源"],
                    "next_actions": ["整理禁用表达"],
                },
                "source_samples": ["risk.md"],
            }
        ],
    }

    packet = build_topic_review_packets(draft_assets)["items"][0]

    assert packet["priority"] == "P0"
    assert packet["promotion_target"] == "approved_risk_boundary_card"
    assert "禁用表达" in " ".join(packet["review_questions"])
    assert "不能写入 approved answer cards" in packet["blocked_actions"]
    assert packet["official_use_allowed"] is False


def test_build_topic_review_decision_stub_and_sample_keep_decisions_pending():
    from apps.api.hxy_knowledge.knowledge_compiler import (
        build_topic_review_decisions_sample,
        build_topic_review_decisions_stub,
    )

    packets = {
        "version": "hxy-topic-review-packets.v1",
        "items": [
            {
                "version": "hxy-topic-review-packet.v1",
                "packet_id": "hxy-topic-review-packet:brand_positioning",
                "asset_id": "hxy-topic-draft:brand_positioning",
                "topic_key": "brand_positioning",
                "asset_type": "positioning_card",
                "title": "品牌战略与核爆点定位",
                "priority": "P0",
                "review_owner": "创始人",
                "decision_options": [
                    "needs_more_evidence",
                    "revise_draft",
                    "ready_for_manual_approval",
                    "reject",
                ],
                "promotion_target": "approved_positioning_card",
            }
        ],
    }

    stub = build_topic_review_decisions_stub(packets)
    sample = build_topic_review_decisions_sample(stub)

    assert stub["version"] == "hxy-topic-review-decisions-stub.v1"
    assert stub["target_filename"] == "topic-review-decisions.json"
    assert stub["decision_count"] == 1
    assert stub["official_use_allowed"] is False
    assert stub["publish_allowed"] is False
    assert stub["write_to_database"] is False
    assert stub["requires_human_review"] is True
    assert stub["authority_rule"] == "topic_review_decisions_do_not_publish_official_knowledge"
    assert stub["items"][0]["decision"] == "pending"
    assert stub["items"][0]["status"] == "pending_decision"
    assert "ready_for_manual_approval" in stub["items"][0]["allowed_decisions"]

    assert sample["version"] == "hxy-topic-review-decisions-sample.v1"
    assert sample["target_filename"] == "topic-review-decisions.json"
    assert sample["initialized_from_stub"] is True
    assert sample["official_use_allowed"] is False
    assert sample["publish_allowed"] is False
    assert sample["write_to_database"] is False
    assert sample["items"][0]["decision"] == "pending"
    assert sample["items"][0]["reviewer"] == ""
    assert sample["items"][0]["rationale"] == ""
    assert "approved_cards" not in json.dumps(sample, ensure_ascii=False)


def test_validate_topic_review_decisions_allows_ready_state_without_publishing():
    from apps.api.hxy_knowledge.knowledge_compiler import validate_topic_review_decisions

    packets = {
        "version": "hxy-topic-review-packets.v1",
        "items": [
            {
                "packet_id": "hxy-topic-review-packet:brand_positioning",
                "title": "品牌战略与核爆点定位",
                "decision_options": [
                    "needs_more_evidence",
                    "revise_draft",
                    "ready_for_manual_approval",
                    "reject",
                ],
                "promotion_target": "approved_positioning_card",
            }
        ],
    }
    decisions = {
        "version": "hxy-topic-review-decisions.v1",
        "official_use_allowed": False,
        "publish_allowed": False,
        "write_to_database": False,
        "items": [
            {
                "packet_id": "hxy-topic-review-packet:brand_positioning",
                "decision": "ready_for_manual_approval",
                "reviewer": "创始人",
                "rationale": "已有顾客原话和员工复述记录，可以进入下一步人工批准前检查。",
            }
        ],
    }

    validation = validate_topic_review_decisions(packets, decisions)

    assert validation["version"] == "hxy-topic-review-decisions-validation.v1"
    assert validation["valid"] is True
    assert validation["manual_decision_count"] == 1
    assert validation["ready_for_manual_approval_count"] == 1
    assert validation["approved_count"] == 0
    assert validation["official_use_allowed"] is False
    assert validation["publish_allowed"] is False
    assert validation["write_to_database"] is False
    assert validation["authority_rule"] == "ready_for_manual_approval_is_not_approved_knowledge"
    assert validation["items"][0]["decision"] == "ready_for_manual_approval"
    assert validation["items"][0]["status"] == "valid_manual_decision"


def test_validate_topic_review_decisions_rejects_invalid_decision_and_publish_flags():
    from apps.api.hxy_knowledge.knowledge_compiler import validate_topic_review_decisions

    packets = {
        "version": "hxy-topic-review-packets.v1",
        "items": [
            {
                "packet_id": "hxy-topic-review-packet:risk_boundary",
                "title": "合规与功效表达边界",
                "decision_options": ["needs_more_evidence", "revise_draft", "ready_for_manual_approval", "reject"],
                "promotion_target": "approved_risk_boundary_card",
            }
        ],
    }
    decisions = {
        "version": "hxy-topic-review-decisions.v1",
        "official_use_allowed": True,
        "publish_allowed": True,
        "write_to_database": True,
        "items": [
            {
                "packet_id": "hxy-topic-review-packet:risk_boundary",
                "decision": "approve",
                "reviewer": "",
                "rationale": "",
            }
        ],
    }

    validation = validate_topic_review_decisions(packets, decisions)

    assert validation["valid"] is False
    assert validation["invalid_decision_count"] == 1
    assert validation["publish_block_count"] == 3
    assert validation["items"][0]["status"] == "invalid"
    assert "approve" in json.dumps(validation["errors"], ensure_ascii=False)
    assert "不能发布" in json.dumps(validation["errors"], ensure_ascii=False)


def test_compile_directory_writes_core_decision_topics_before_claim_review_queue(tmp_path: Path):
    from apps.api.hxy_knowledge.knowledge_compiler import compile_directory

    raw_dir = tmp_path / "raw"
    wiki_dir = tmp_path / "wiki"
    raw_dir.mkdir(parents=True)
    (raw_dir / "brand.md").write_text(
        "荷小悦核爆点定位要围绕社区高疲劳人群、草本泡脚按摩和轻恢复表达。"
        "首店开业前需要补齐用户原话、复述测试、付费理由和替代方案。"
        "员工不能承诺泡脚可以治疗失眠。",
        encoding="utf-8",
    )

    report = compile_directory(raw_dir, wiki_dir)

    assert (wiki_dir / "core-decision-topics.json").is_file()
    assert (wiki_dir / "topic-draft-assets.json").is_file()
    assert (wiki_dir / "topic-review-packets.json").is_file()
    assert (wiki_dir / "topic-review-decisions.stub.json").is_file()
    assert (wiki_dir / "topic-review-decisions.sample.json").is_file()
    core_topics = json.loads((wiki_dir / "core-decision-topics.json").read_text(encoding="utf-8"))
    draft_assets = json.loads((wiki_dir / "topic-draft-assets.json").read_text(encoding="utf-8"))
    review_packets = json.loads((wiki_dir / "topic-review-packets.json").read_text(encoding="utf-8"))
    decision_stub = json.loads((wiki_dir / "topic-review-decisions.stub.json").read_text(encoding="utf-8"))
    decision_sample = json.loads((wiki_dir / "topic-review-decisions.sample.json").read_text(encoding="utf-8"))
    assert report["core_decision_topic_count"] >= 2
    assert report["topic_draft_asset_count"] == draft_assets["count"]
    assert report["topic_review_packet_count"] == review_packets["count"]
    assert report["topic_review_decision_stub_count"] == decision_stub["decision_count"]
    assert report["human_review_object"] == "core_decision_topics"
    assert report["artifacts"]["topic_draft_assets"]["items"]
    assert report["artifacts"]["topic_review_packets"]["items"]
    assert core_topics["version"] == "hxy-core-decision-topics.v1"
    assert draft_assets["version"] == "hxy-topic-draft-assets.v1"
    assert review_packets["version"] == "hxy-topic-review-packets.v1"
    assert decision_stub["version"] == "hxy-topic-review-decisions-stub.v1"
    assert decision_sample["version"] == "hxy-topic-review-decisions-sample.v1"
    assert {item["decision"] for item in decision_sample["items"]} == {"pending"}
    assert review_packets["official_use_allowed"] is False
    assert draft_assets["official_use_allowed"] is False
    assert decision_sample["official_use_allowed"] is False
    assert decision_sample["publish_allowed"] is False
    assert core_topics["raw_claims_hidden"] is True
    assert "claim_triage_is_machine_intermediate" in core_topics["authority_rule"]


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
