import { describe, expect, test } from "vitest";
import { buildHxyOsiContract, type HxyOsiDomainKey } from "./hxy-osi-contract.js";
import type { HxyKnowledgeGovernanceReport } from "./hxy-knowledge-governance.js";

function governanceReport(): HxyKnowledgeGovernanceReport {
  return {
    version: "hxy-knowledge-governance.v1",
    generated_at: "2026-05-14T00:00:00.000Z",
    summary: {
      claim_count: 6,
      theme_count: 6,
      conflict_count: 1,
      recommended_current_candidate_count: 6,
      needs_human_review_count: 7,
    },
    theme_groups: {},
    recommended_current_candidates: [
      {
        claim_id: "positioning-1",
        claim_type: "brand_positioning",
        theme: "community_store_positioning",
        claim: "荷小悦当前主定位是社区泡脚按摩小店，以真实有效、社区信任和私域复购为核心。",
        confidence: 0.8,
        reason: "筹备期和样板店期需要先收敛到可落地的小店定位。",
      },
      {
        claim_id: "asset-1",
        claim_type: "brand_asset",
        theme: "brand_asset_expression",
        claim: "品牌名荷小悦，Slogan：草本真现煮，按出真功夫。",
        confidence: 0.78,
        reason: "品牌资产需要统一口号、IP 和终端表达。",
      },
      {
        claim_id: "price-1",
        claim_type: "product_service",
        theme: "product_price_model",
        claim: "招牌款60分钟现煮草本泡脚+手法按摩+护理包，价格128元。",
        confidence: 0.76,
        reason: "产品价格模型直接影响单店利润和复购。",
      },
      {
        claim_id: "finance-1",
        claim_type: "financial_assumption",
        theme: "store_financial_model",
        claim: "单店投资50万元，月营收18万元，月净利润6.4万元，回本周期6-8个月。",
        confidence: 0.72,
        reason: "财务模型必须成为样板店验证主线。",
      },
      {
        claim_id: "customer-1",
        claim_type: "customer_segment",
        theme: "customer_segment",
        claim: "客群：悦己年轻人、社区家庭和银发人群需要拆分验证。",
        confidence: 0.72,
        reason: "客群定义会影响产品、价格、选址和传播。",
      },
      {
        claim_id: "ai-1",
        claim_type: "product_service",
        theme: "data_ai_model",
        claim: "AI诊断结果自动生成调理方案，并沉淀健康档案、复购标签和服务推荐。",
        confidence: 0.74,
        reason: "AI/Data 能力应服务经营验证，不宜先做平台叙事。",
      },
    ],
    conflicts: [
      {
        conflict_id: "conflict-positioning",
        conflict_type: "positioning_stage_conflict",
        primary_claim_id: "positioning-1",
        conflicting_claim_id: "platform-1",
        reason: "社区小店定位与银发健康科技平台不能同时作为当前主定位。",
        recommended_resolution: "当前用社区小店，平台作为远期愿景。",
        needs_human_review: true,
      },
    ],
    review_queue: [],
  };
}

describe("hxy osi contract", () => {
  test("builds five core OSI domains from governance report", () => {
    const contract = buildHxyOsiContract(governanceReport());
    expect(contract.version).toBe("hxy-osi-contract.v1");
    expect(contract.stage).toBe("preparation");
    expect(contract.domains.map((domain) => domain.domain)).toEqual([
      "brand_positioning",
      "customer_segment",
      "product_price_model",
      "store_financial_model",
      "ai_health_solution",
    ] satisfies HxyOsiDomainKey[]);
  });

  test("binds current candidate claims to matching domains", () => {
    const contract = buildHxyOsiContract(governanceReport());
    const byDomain = Object.fromEntries(contract.domains.map((domain) => [domain.domain, domain]));

    expect(byDomain.brand_positioning.current_claims.map((claim) => claim.claim_id)).toContain("positioning-1");
    expect(byDomain.brand_positioning.current_claims.map((claim) => claim.claim_id)).toContain("asset-1");
    expect(byDomain.product_price_model.current_claims.map((claim) => claim.claim_id)).toEqual(["price-1"]);
    expect(byDomain.store_financial_model.current_claims.map((claim) => claim.claim_id)).toEqual(["finance-1"]);
    expect(byDomain.ai_health_solution.current_claims.map((claim) => claim.claim_id)).toEqual(["ai-1"]);
  });

  test("carries answer boundaries and validation metrics for downstream agents", () => {
    const contract = buildHxyOsiContract(governanceReport());
    const brand = contract.domains.find((domain) => domain.domain === "brand_positioning");
    const finance = contract.domains.find((domain) => domain.domain === "store_financial_model");
    const ai = contract.domains.find((domain) => domain.domain === "ai_health_solution");

    expect(brand?.answer_boundaries).toContain("当前主定位、融资叙事、远期平台愿景必须分开表达。");
    expect(finance?.validation_metrics.map((metric) => metric.key)).toContain("payback_months");
    expect(ai?.agent_usages.map((usage) => usage.agent_key)).toContain("health_plan_agent_v1");
  });

  test("surfaces governance conflicts as human review items", () => {
    const contract = buildHxyOsiContract(governanceReport());
    expect(contract.governance.open_review_items).toHaveLength(1);
    expect(contract.governance.open_review_items[0]).toMatchObject({
      source: "knowledge_governance",
      conflict_id: "conflict-positioning",
      severity: "high",
    });
  });
});
