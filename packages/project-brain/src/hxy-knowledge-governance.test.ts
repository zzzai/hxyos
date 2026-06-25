import { describe, expect, test } from "vitest";
import {
  buildHxyKnowledgeGovernanceReport,
  classifyHxyClaimTheme,
  detectHxyClaimConflicts,
} from "./hxy-knowledge-governance.js";
import type { HxyKnowledgeClaim } from "./hxy-knowledge-extractor.js";

function claim(overrides: Partial<HxyKnowledgeClaim> & Pick<HxyKnowledgeClaim, "claim_id" | "claim_type" | "claim">): HxyKnowledgeClaim {
  return {
    stage: "preparation",
    status: "current_candidate",
    confidence: 0.75,
    evidence_ids: [`evidence-${overrides.claim_id}`],
    conflict_claim_ids: [],
    needs_validation: true,
    ...overrides,
  };
}

describe("hxy knowledge governance", () => {
  test("classifies strategic claim themes", () => {
    expect(classifyHxyClaimTheme("荷小悦定位社区泡脚按摩小店")).toBe("community_store_positioning");
    expect(classifyHxyClaimTheme("荷小悦是银发健康科技平台")).toBe("silver_health_platform_positioning");
    expect(classifyHxyClaimTheme("目标客群包含银发老人和社区家庭")).toBe("customer_segment");
    expect(classifyHxyClaimTheme("主推款60分钟泡脚+按摩+离店护理包，价格128元")).toBe("product_price_model");
    expect(classifyHxyClaimTheme("投资规模约50万元，目标回本周期8个月")).toBe("store_financial_model");
  });

  test("detects positioning conflicts between store model and platform narrative", () => {
    const conflicts = detectHxyClaimConflicts([
      claim({
        claim_id: "c1",
        claim_type: "brand_positioning",
        claim: "荷小悦定位社区泡脚按摩小店，强调社区小店和私域复购。",
      }),
      claim({
        claim_id: "c2",
        claim_type: "brand_positioning",
        claim: "荷小悦是银发健康科技平台，未来连接养老生态。",
      }),
    ]);

    expect(conflicts).toHaveLength(1);
    expect(conflicts[0]).toMatchObject({
      conflict_type: "positioning_stage_conflict",
      primary_claim_id: "c1",
      conflicting_claim_id: "c2",
    });
  });

  test("collapses repeated positioning conflicts into representative review items", () => {
    const conflicts = detectHxyClaimConflicts([
      claim({
        claim_id: "c1",
        claim_type: "brand_positioning",
        claim: "荷小悦定位社区泡脚按摩小店，强调社区小店和私域复购。",
      }),
      claim({
        claim_id: "c2",
        claim_type: "brand_positioning",
        claim: "荷小悦定位社区养生小店，强调社区信任。",
      }),
      claim({
        claim_id: "c3",
        claim_type: "brand_positioning",
        claim: "荷小悦是银发健康科技平台，未来连接养老生态。",
      }),
      claim({
        claim_id: "c4",
        claim_type: "brand_positioning",
        claim: "荷小悦未来成为银发基建平台。",
      }),
    ]);

    expect(conflicts).toHaveLength(1);
    expect(conflicts[0]).toMatchObject({
      conflict_type: "positioning_stage_conflict",
      primary_claim_id: "c1",
      conflicting_claim_id: "c3",
    });
  });

  test("builds governance report with recommended current candidates", () => {
    const report = buildHxyKnowledgeGovernanceReport([
      claim({
        claim_id: "c1",
        claim_type: "brand_positioning",
        claim: "荷小悦定位社区泡脚按摩小店，强调社区小店和私域复购。",
        confidence: 0.8,
      }),
      claim({
        claim_id: "c2",
        claim_type: "brand_positioning",
        claim: "荷小悦是银发健康科技平台，未来连接养老生态。",
        confidence: 0.7,
      }),
      claim({
        claim_id: "c3",
        claim_type: "financial_assumption",
        claim: "投资规模约50万元，目标回本周期8个月。",
        confidence: 0.72,
      }),
    ]);

    expect(report.theme_groups.community_store_positioning.claim_count).toBe(1);
    expect(report.theme_groups.silver_health_platform_positioning.claim_count).toBe(1);
    expect(report.recommended_current_candidates.map((item) => item.claim_id)).toContain("c1");
    expect(report.conflicts).toHaveLength(1);
    expect(report.summary.needs_human_review_count).toBeGreaterThan(0);
  });

  test("does not recommend competitor matrix or financing noise as current brand candidates", () => {
    const report = buildHxyKnowledgeGovernanceReport([
      claim({
        claim_id: "noise-community",
        claim_type: "brand_positioning",
        claim: "05 竞品差异化矩阵 荷小悦小店 vs 市场主流竞争对手 差异维度 旗舰大店模型（奈晚·谷小推等） 荷小悦小店模型 优劣势。",
        confidence: 0.95,
      }),
      claim({
        claim_id: "good-community",
        claim_type: "brand_positioning",
        claim: "荷小悦定位社区泡脚按摩小店，以社区小店、私域复购和真实有效为当前主定位。",
        confidence: 0.8,
      }),
      claim({
        claim_id: "noise-brand",
        claim_type: "brand_positioning",
        claim: "IPO 估值 500 亿，C 轮融资建设 AI 系统 V5.0。",
        confidence: 0.99,
      }),
      claim({
        claim_id: "good-brand",
        claim_type: "brand_asset",
        claim: "品牌名荷小悦，Slogan：草本真现煮，按出真功夫。",
        confidence: 0.78,
      }),
      claim({
        claim_id: "noise-product",
        claim_type: "financial_assumption",
        claim: "+-----------------+-----------------+ 属性维度 | 对应消费者需求 | 荷小悦产品回应 | 差异化竞争点 |",
        confidence: 0.9,
      }),
      claim({
        claim_id: "good-product",
        claim_type: "product_service",
        claim: "主推款60分钟现煮草本泡脚+按摩+离店护理包，价格128元。",
        confidence: 0.76,
      }),
    ]);

    const selected = new Set(report.recommended_current_candidates.map((candidate) => candidate.claim_id));
    expect(selected).toContain("good-community");
    expect(selected).toContain("good-brand");
    expect(selected).toContain("good-product");
    expect(selected).not.toContain("noise-community");
    expect(selected).not.toContain("noise-brand");
    expect(selected).not.toContain("noise-product");
  });

  test("requires theme-specific evidence before recommending current candidates", () => {
    const report = buildHxyKnowledgeGovernanceReport([
      claim({
        claim_id: "weak-ai",
        claim_type: "product_service",
        claim: "账、税务申报、供应商 Portal、全网流水、B 端企业客户。",
        confidence: 0.95,
      }),
      claim({
        claim_id: "good-ai",
        claim_type: "product_service",
        claim: "AI 诊断结果自动生成调理方案，包含到店服务、居家护理、泡脚包配方和饮食建议。",
        confidence: 0.74,
      }),
      claim({
        claim_id: "weak-finance",
        claim_type: "financial_assumption",
        claim: "平安集团可能收购，估值 50 亿。",
        confidence: 0.95,
      }),
      claim({
        claim_id: "good-finance",
        claim_type: "financial_assumption",
        claim: "单店投资50万元，月净利润6.4万元，目标回本周期8个月。",
        confidence: 0.7,
      }),
    ]);

    const selected = new Set(report.recommended_current_candidates.map((candidate) => candidate.claim_id));
    expect(selected).toContain("good-ai");
    expect(selected).toContain("good-finance");
    expect(selected).not.toContain("weak-ai");
    expect(selected).not.toContain("weak-finance");
  });

  test("prefers concrete current strategy claims over tables and org compensation artifacts", () => {
    const report = buildHxyKnowledgeGovernanceReport([
      claim({
        claim_id: "stage-table",
        claim_type: "brand_positioning",
        claim: "阶段目标拆解 阶段 时间 核心目标 关键指标 冷启动 开店前 2-3 月 社区介入，种植信任种子。",
        confidence: 0.95,
      }),
      claim({
        claim_id: "good-positioning",
        claim_type: "brand_positioning",
        claim: "荷小悦当前主定位是社区泡脚按摩小店，以真实有效、社区信任和私域复购为核心。",
        confidence: 0.78,
      }),
      claim({
        claim_id: "family-card",
        claim_type: "product_service",
        claim: "家庭健康卡绑定家人，LTV 预测后发送高价值套餐邀约。",
        confidence: 0.95,
      }),
      claim({
        claim_id: "good-price",
        claim_type: "product_service",
        claim: "招牌款60分钟现煮草本泡脚+手法按摩+护理包，价格128元。",
        confidence: 0.74,
      }),
      claim({
        claim_id: "cmo-pay",
        claim_type: "financial_assumption",
        claim: "荷小悦 CMO 薪酬方案，基本月薪 2 万/月，年度绩效 20-50 万。",
        confidence: 0.95,
      }),
      claim({
        claim_id: "fund-usage",
        claim_type: "financial_assumption",
        claim: "品牌影响力建设，AI数字化15%，产品研发10%，投资回报与风险控制，短期门店增长。",
        confidence: 0.98,
      }),
      claim({
        claim_id: "good-store-finance",
        claim_type: "financial_assumption",
        claim: "单店投资50万元，月营收18万元，月净利润6.4万元，回本周期6-8个月。",
        confidence: 0.7,
      }),
      claim({
        claim_id: "supplier-table",
        claim_type: "product_service",
        claim: "账、税务申报、全网流水、供应商 Portal、按时回款、对账、发货确认。",
        confidence: 0.99,
      }),
      claim({
        claim_id: "good-data-ai",
        claim_type: "product_service",
        claim: "AI 诊断结果自动生成调理方案，并沉淀健康档案、复购标签和服务推荐。",
        confidence: 0.74,
      }),
    ]);

    const selected = new Set(report.recommended_current_candidates.map((candidate) => candidate.claim_id));
    expect(selected).toContain("good-positioning");
    expect(selected).toContain("good-price");
    expect(selected).toContain("good-store-finance");
    expect(selected).toContain("good-data-ai");
    expect(selected).not.toContain("stage-table");
    expect(selected).not.toContain("family-card");
    expect(selected).not.toContain("cmo-pay");
    expect(selected).not.toContain("fund-usage");
    expect(selected).not.toContain("supplier-table");
  });

  test("prefers concise auditable decisions over long narrative fragments", () => {
    const report = buildHxyKnowledgeGovernanceReport([
      claim({
        claim_id: "long-flywheel-positioning",
        claim_type: "brand_positioning",
        claim:
          "荷小悦 HE XIAO YUE 泡脚养生国民品牌，以服务为媒，以信任为根，以健康为本。运营飞轮从一次体验，到社区口碑，再到家庭账户，拓新客带来首次体验，稳定服务建立基础信任，社区信任资产成为核心驱动力，健康管家提供专业价值，复购锁客提升消费频次，私域触达深化关系。",
        confidence: 0.95,
      }),
      claim({
        claim_id: "concise-positioning",
        claim_type: "brand_positioning",
        claim: "荷小悦当前主定位是社区泡脚按摩小店，以真实有效、社区信任和私域复购为核心。",
        confidence: 0.78,
      }),
      claim({
        claim_id: "menu-pain-fragment",
        claim_type: "pain_point",
        claim:
          "B ： 1 人 1 方 + 任选按摩 A ：草本泡脚包 + 套餐按摩 69 元 -40 分钟：草本泡脚 +A 按摩 79 元 -60 分钟：草本泡脚 +A+B+C 99 元 -70 分钟。",
        confidence: 0.96,
      }),
      claim({
        claim_id: "concise-menu",
        claim_type: "product_service",
        claim: "招牌款60分钟现煮草本泡脚+手法按摩+护理包，价格128元。",
        confidence: 0.74,
      }),
      claim({
        claim_id: "franchise-investment",
        claim_type: "financial_assumption",
        claim: "开放单店加盟模式，加盟门槛单店投资30-50万元，适合中小投资者，优先招募本地加盟商。",
        confidence: 0.95,
      }),
      claim({
        claim_id: "concise-store-model",
        claim_type: "financial_assumption",
        claim: "单店投资50万元，月营收18万元，月净利润6.4万元，回本周期6-8个月。",
        confidence: 0.7,
      }),
    ]);

    const selected = new Set(report.recommended_current_candidates.map((candidate) => candidate.claim_id));
    const selectedById = new Map(report.recommended_current_candidates.map((candidate) => [candidate.claim_id, candidate]));
    expect(selected).toContain("concise-positioning");
    expect(selected).toContain("concise-menu");
    expect(selected).toContain("concise-store-model");
    expect(selected).not.toContain("long-flywheel-positioning");
    expect(selected).not.toContain("menu-pain-fragment");
    expect(selectedById.get("concise-store-model")?.theme).toBe("store_financial_model");
    expect(selectedById.get("franchise-investment")?.theme).toBe("franchise_model");
  });

  test("does not treat future repositioning away from community store as current community positioning", () => {
    const report = buildHxyKnowledgeGovernanceReport([
      claim({
        claim_id: "future-repositioning",
        claim_type: "brand_positioning",
        claim:
          '荷小悦战略重新定位：基于行业研究，荷小悦不再定位为"社区小店"，而是重新定义为中国新一代智能化社区养生连锁第一品牌，核心差异化是AI驱动的社区健康数据网络。',
        confidence: 0.95,
      }),
      claim({
        claim_id: "current-community",
        claim_type: "brand_positioning",
        claim: "当前阶段先做社区泡脚按摩小店，强调家门口、真实有效、价格不心疼和私域复购。",
        confidence: 0.78,
      }),
    ]);

    const selected = new Set(report.recommended_current_candidates.map((candidate) => candidate.claim_id));
    expect(selected).toContain("current-community");
    expect(selected).not.toContain("future-repositioning");
  });

  test("rejects future strategy claims when no current community positioning exists", () => {
    const report = buildHxyKnowledgeGovernanceReport([
      claim({
        claim_id: "future-repositioning-only",
        claim_type: "brand_positioning",
        claim:
          '荷小悦战略重新定位：基于行业研究，荷小悦不再定位为"社区小店"，而是重新定义为中国新一代智能化社区养生连锁第一品牌，核心差异化是AI驱动的社区健康数据网络。',
        confidence: 0.95,
      }),
    ]);

    expect(report.recommended_current_candidates.map((candidate) => candidate.claim_id)).not.toContain(
      "future-repositioning-only",
    );
  });

  test("accepts concrete community positioning even when the wording does not say community store", () => {
    const report = buildHxyKnowledgeGovernanceReport([
      claim({
        claim_id: "massage-that-works",
        claim_type: "financial_assumption",
        claim: '荷小悦只要成为"社区里那个按摩真好使的地方"就够了。',
        confidence: 0.7,
      }),
    ]);

    const selected = report.recommended_current_candidates.find(
      (candidate) => candidate.theme === "community_store_positioning",
    );
    expect(selected?.claim_id).toBe("massage-that-works");
  });

  test("uses full business model claims for product and store model instead of fragments", () => {
    const report = buildHxyKnowledgeGovernanceReport([
      claim({
        claim_id: "rent-fragment",
        claim_type: "financial_assumption",
        claim: "租金成本控制在营收的 12% 以内。",
        confidence: 0.95,
      }),
      claim({
        claim_id: "full-store-model",
        claim_type: "financial_assumption",
        claim:
          "四、商业模型：店面面积约100㎡，核心服务泡脚+按摩，投资规模约50万元，目标回本周期8个月。套餐设计：入口款50分钟泡脚+按摩¥88，主推款60分钟泡脚+按摩+离店护理包¥128，加油款75分钟+下次优先预约¥168。",
        confidence: 0.7,
      }),
      claim({
        claim_id: "ui-flow-price",
        claim_type: "product_service",
        claim: "【操作流程】进入预约页面，订单确认显示服务项目60分钟中式足疗，服务价格¥128，可选加项薰衣草精油¥30。",
        confidence: 0.95,
      }),
      claim({
        claim_id: "menu-model",
        claim_type: "product_service",
        claim:
          "套餐设计：入口款50分钟泡脚+按摩¥88，主推款60分钟泡脚+按摩+离店护理包¥128，加油款75分钟+下次优先预约¥168。",
        confidence: 0.74,
      }),
    ]);

    const selectedByTheme = new Map(report.recommended_current_candidates.map((candidate) => [candidate.theme, candidate]));
    expect(selectedByTheme.get("store_financial_model")?.claim_id).toBe("full-store-model");
    expect(selectedByTheme.get("product_price_model")?.claim_id).toBe("menu-model");
  });

  test("classifies product-service pricing as product menu even when it contains store model signals", () => {
    const report = buildHxyKnowledgeGovernanceReport([
      claim({
        claim_id: "store-model",
        claim_type: "store_model",
        claim:
          "四、商业模型：店面面积约100㎡，核心服务泡脚+按摩，投资规模约50万元，目标回本周期8个月。套餐设计：入口款50分钟泡脚+按摩¥88，主推款60分钟泡脚+按摩+离店护理包¥128，加油款75分钟+下次优先预约¥168。",
        confidence: 0.74,
      }),
      claim({
        claim_id: "product-menu",
        claim_type: "product_service",
        claim:
          "四、商业模型：店面面积约100㎡，核心服务泡脚+按摩，投资规模约50万元，目标回本周期8个月。套餐设计：入口款50分钟泡脚+按摩¥88，主推款60分钟泡脚+按摩+离店护理包¥128，加油款75分钟+下次优先预约¥168。",
        confidence: 0.74,
      }),
    ]);

    const selectedByTheme = new Map(report.recommended_current_candidates.map((candidate) => [candidate.theme, candidate]));
    expect(selectedByTheme.get("store_financial_model")?.claim_id).toBe("store-model");
    expect(selectedByTheme.get("product_price_model")?.claim_id).toBe("product-menu");
  });

  test("prefers full multi-tier menu over a single SKU candidate", () => {
    const report = buildHxyKnowledgeGovernanceReport([
      claim({
        claim_id: "single-sku",
        claim_type: "product_service",
        claim:
          "80 MIN 高客单溢价款，15min草本药浴+65min全身精油推拿，¥158引流价，会员价¥238，含精油伴手礼。",
        confidence: 0.95,
      }),
      claim({
        claim_id: "three-tier-menu",
        claim_type: "product_service",
        claim:
          "套餐设计：入口款50分钟泡脚+按摩¥88，主推款60分钟泡脚+按摩+离店护理包¥128，加油款75分钟+下次优先预约¥168。",
        confidence: 0.74,
      }),
    ]);

    const selected = report.recommended_current_candidates.find((candidate) => candidate.theme === "product_price_model");
    expect(selected?.claim_id).toBe("three-tier-menu");
  });

  test("requires actual customer segment instead of acquisition tooling for customer candidates", () => {
    const report = buildHxyKnowledgeGovernanceReport([
      claim({
        claim_id: "acquisition-tooling",
        claim_type: "customer_segment",
        claim: "精准：利用 AI 竞对工具扫描商圈，精准定位高价值社区用户，实现低成本获客。",
        confidence: 0.95,
      }),
      claim({
        claim_id: "real-segment",
        claim_type: "customer_segment",
        claim: "一个核心人群：悦己型年轻养生客群，核心圈层是3公里社区复购人群。",
        confidence: 0.72,
      }),
    ]);

    const selected = report.recommended_current_candidates.find((candidate) => candidate.theme === "customer_segment");
    expect(selected?.claim_id).toBe("real-segment");
  });
});
