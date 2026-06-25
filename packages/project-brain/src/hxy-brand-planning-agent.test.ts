import { describe, expect, test } from "vitest";
import { buildHxyBrandPlanningDraft } from "./hxy-brand-planning-agent.js";
import type { HxyOsiContract } from "./hxy-osi-contract.js";

function osiContract(): HxyOsiContract {
  return {
    version: "hxy-osi-contract.v1",
    generated_at: "2026-05-14T00:00:00.000Z",
    stage: "preparation",
    source_governance_generated_at: "2026-05-14T00:00:00.000Z",
    domains: [
      {
        domain: "brand_positioning",
        label: "品牌定位 OSI",
        purpose: "拆开当前定位和远期愿景。",
        base_fields: [],
        current_claims: [
          {
            claim_id: "positioning-1",
            claim_type: "brand_positioning",
            theme: "community_store_positioning",
            claim: "荷小悦当前主定位是社区泡脚按摩小店，以真实有效、社区信任和私域复购为核心。",
            confidence: 0.8,
          },
          {
            claim_id: "asset-1",
            claim_type: "brand_asset",
            theme: "brand_asset_expression",
            claim: "品牌名荷小悦，Slogan：草本真现煮，按出真功夫。",
            confidence: 0.78,
          },
        ],
        answer_boundaries: ["当前主定位、融资叙事、远期平台愿景必须分开表达。"],
        validation_metrics: [{ key: "brand_asset_consistency", label: "品牌资产一致率", description: "统一表达。" }],
        agent_usages: [],
      },
      {
        domain: "customer_segment",
        label: "客群 OSI",
        purpose: "拆分消费者和经营者。",
        base_fields: [],
        current_claims: [
          {
            claim_id: "customer-1",
            claim_type: "customer_segment",
            theme: "customer_segment",
            claim: "客群：悦己年轻人、社区家庭和银发人群需要拆分验证。",
            confidence: 0.72,
          },
        ],
        answer_boundaries: ["消费者客群和店长/合伙人画像必须分开。"],
        validation_metrics: [{ key: "repeat_visit_rate", label: "复购率", description: "30/60/90 天复购。" }],
        agent_usages: [],
      },
      {
        domain: "product_price_model",
        label: "产品价格 OSI",
        purpose: "沉淀套餐价格。",
        base_fields: [],
        current_claims: [
          {
            claim_id: "price-1",
            claim_type: "product_service",
            theme: "product_price_model",
            claim: "招牌款60分钟现煮草本泡脚+手法按摩+护理包，价格128元。",
            confidence: 0.76,
          },
        ],
        answer_boundaries: ["价格版本并存时必须标注候选版本，不输出唯一价格表。"],
        validation_metrics: [{ key: "take_rate_by_package", label: "套餐选择率", description: "各套餐成交占比。" }],
        agent_usages: [],
      },
      {
        domain: "store_financial_model",
        label: "单店财务 OSI",
        purpose: "验证单店模型。",
        base_fields: [],
        current_claims: [
          {
            claim_id: "finance-1",
            claim_type: "financial_assumption",
            theme: "store_financial_model",
            claim: "单店投资50万元，月营收18万元，月净利润6.4万元，回本周期6-8个月。",
            confidence: 0.72,
          },
        ],
        answer_boundaries: ["未有样板店真实数据前，只能称为假设模型。"],
        validation_metrics: [{ key: "payback_months", label: "回本周期", description: "真实累计净现金流覆盖投资。" }],
        agent_usages: [],
      },
      {
        domain: "ai_health_solution",
        label: "AI 健康方案 OSI",
        purpose: "限定 AI 健康方案。",
        base_fields: [],
        current_claims: [
          {
            claim_id: "ai-1",
            claim_type: "product_service",
            theme: "data_ai_model",
            claim: "AI诊断结果自动生成调理方案，并沉淀健康档案、复购标签和服务推荐。",
            confidence: 0.74,
          },
        ],
        answer_boundaries: ["AI 不能输出医疗诊断结论。"],
        validation_metrics: [{ key: "recommendation_acceptance_rate", label: "推荐采纳率", description: "用户接受推荐比例。" }],
        agent_usages: [],
      },
    ],
    governance: {
      open_review_items: [
        {
          source: "knowledge_governance",
          conflict_id: "conflict-positioning",
          severity: "high",
          reason: "社区小店定位与银发健康科技平台不能同时作为当前主定位。",
          recommended_resolution: "当前用社区小店，平台作为远期愿景。",
        },
      ],
    },
  };
}

describe("hxy brand planning agent", () => {
  test("builds a planning draft from OSI domains", () => {
    const draft = buildHxyBrandPlanningDraft(osiContract());
    expect(draft.version).toBe("hxy-brand-planning-draft.v1");
    expect(draft.positioning.current).toContain("社区泡脚按摩小店");
    expect(draft.positioning.financing_narrative).toContain("社区健康服务入口");
    expect(draft.positioning.future_vision).toContain("银发健康科技平台");
    expect(draft.boundaries).toContain("当前主定位、融资叙事、远期平台愿景必须分开表达。");
  });

  test("turns OSI claims into purchase reasons and terminal actions", () => {
    const draft = buildHxyBrandPlanningDraft(osiContract());
    expect(draft.purchase_reasons).toContain("真实有效：现煮草本泡脚和手法按摩必须让顾客感到身体变化。");
    expect(draft.purchase_reasons).toContain("价格不心疼：套餐价格要支撑高频社区复购。");
    expect(draft.terminal_actions.map((action) => action.surface)).toEqual(["门头/门店", "菜单/套餐", "技师话术", "私域/复购"]);
  });

  test("keeps validation assumptions explicit", () => {
    const draft = buildHxyBrandPlanningDraft(osiContract());
    expect(draft.validation_plan.map((item) => item.metric_key)).toEqual([
      "brand_asset_consistency",
      "repeat_visit_rate",
      "take_rate_by_package",
      "payback_months",
      "recommendation_acceptance_rate",
    ]);
    expect(draft.open_risks[0]).toContain("社区小店定位与银发健康科技平台不能同时作为当前主定位");
  });
});
