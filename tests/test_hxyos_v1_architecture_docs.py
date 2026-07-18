from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(relative_path: str) -> str:
    path = ROOT / relative_path
    assert path.exists(), f"missing architecture document: {relative_path}"
    return path.read_text(encoding="utf-8")


def test_mixed_operating_model_is_staged_and_relationship_based() -> None:
    design = read("docs/plans/2026-07-18-hxyos-mixed-operating-model-design.md")

    for phrase in (
        "直营验证后再开放混合扩张",
        "StoreOperatingRelationship",
        "GovernanceProfile",
        "不以日期或门店数量自动开放",
        "direct_operated",
        "franchise_operated",
        "joint_venture_operated",
        "managed_operated",
        "直营首店只实现",
    ):
        assert phrase in design

    assert "一个 `operating_mode` 字段" in design
    assert "不能" in design


def test_core_contract_separates_catalog_datasets_facts_and_events() -> None:
    contract = read("docs/project-brain/contracts/hxyos-core-data-contract-v1.md")

    for concept in (
        "SourceAsset",
        "DataSource",
        "DataConnector",
        "DatasetSnapshot",
        "BusinessFact",
        "MetricDefinition",
        "AssetBinding",
        "OperatingEvent",
        "StoreOperatingRelationship",
        "GovernanceProfile",
        "System of Record",
    ):
        assert concept in contract

    assert "结构化经营数据不能伪装成文档" in contract
    assert "不能无差别进入 pgvector" in contract
    assert "禁止把任意 SQL、Python 或模型生成代码保存后直接执行" in contract
    assert "有效时间范围排他约束" in contract


def test_architecture_keeps_hxy_authority_and_external_commerce_boundary() -> None:
    adr = read("docs/project-brain/decisions/ADR-002-hxyos-v1-architecture.md")

    for phrase in (
        "统一数据目录",
        "直营验证后再开放加盟、联营、托管等混合模式",
        "HXYOS 是组织身份、正式知识、经营工作流、证据和治理状态的权威系统",
        "订单、会员、支付和团购平台初期继续由各业务系统保存权威原始记录",
        "不提前建设加盟招商和加盟商管理功能",
        "/root/hxy",
    ):
        assert phrase in adr

    assert "/root/htops" in adr
    assert "共享业务数据" in adr


def test_vertical_slice_plan_builds_catalog_before_operating_loop() -> None:
    plan = read(
        "docs/plans/2026-07-18-hxyos-store-issue-vertical-slice-implementation.md"
    )

    assert "020_hxy_data_catalog.sql" in plan
    assert "021_hxy_operating_loop.sql" in plan
    assert plan.index("020_hxy_data_catalog.sql") < plan.index("021_hxy_operating_loop.sql")
    assert "020_hxy_operating_loop.sql" not in plan
    assert "直营首店" in plan
    assert "加盟管理功能" in plan


def test_old_immediate_franchise_claims_are_explicitly_non_authoritative() -> None:
    design = read("docs/plans/2026-07-18-hxyos-mixed-operating-model-design.md")
    contract = read("docs/project-brain/contracts/hxyos-core-data-contract-v1.md")
    combined = design + "\n" + contract

    assert "立即开放单店加盟" in combined
    assert "历史参考" in combined
    assert "不能作为正式战略" in combined
