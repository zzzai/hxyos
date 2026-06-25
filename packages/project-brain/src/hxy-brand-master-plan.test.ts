import { describe, expect, test } from "vitest";
import { buildHxyBrandMasterPlan } from "./hxy-brand-master-plan.js";
import type { HxyBrandPlanningDraft } from "./hxy-brand-planning-agent.js";
import type { PersonalKnowledgeSearchResult } from "./personal-knowledge.js";

function draft(): HxyBrandPlanningDraft {
  return {
    version: "hxy-brand-planning-draft.v1",
    generated_at: "2026-05-14T00:00:00.000Z",
    source_osi_generated_at: "2026-05-14T00:00:00.000Z",
    positioning: {
      current: "荷小悦是社区泡脚按摩小店，核心是家门口、真实有效、价格不心疼、能复购。",
      financing_narrative: "荷小悦是社区健康服务入口，先用泡脚按摩建立信任，再沉淀家庭健康关系。",
      future_vision: "荷小悦远期可以发展为银发健康科技平台或社区健康数字基础设施。",
    },
    brand_assets: {
      name: "荷小悦",
      slogan_candidates: ["草本真现煮，按出真功夫", "功效看得见，健康摸得着"],
      core_expression: "真实有效、社区信任、按出真功夫。",
    },
    purchase_reasons: [
      "真实有效：现煮草本泡脚和手法按摩必须让顾客感到身体变化。",
      "价格不心疼：套餐价格要支撑高频社区复购。",
    ],
    target_segments: ["悦己年轻人、社区家庭、银发人群仍需样板店验证。"],
    product_price_candidates: ["招牌款60分钟现煮草本泡脚+手法按摩+护理包，价格128元。"],
    terminal_actions: [
      { surface: "门头/门店", action: "突出荷小悦、草本现煮、按出真功夫，弱化平台化远期叙事。" },
      { surface: "菜单/套餐", action: "用基础款、招牌款、尊享款三层菜单承接不同频次和客单。" },
      { surface: "技师话术", action: "统一表达真实有效、按后体感、下次护理建议，不做医疗诊断。" },
      { surface: "私域/复购", action: "围绕健康档案、复购标签和居家护理建议做持续触达。" },
    ],
    validation_plan: [
      { metric_key: "brand_asset_consistency", label: "品牌资产一致率", source_domain: "brand_positioning", why: "统一表达。" },
      { metric_key: "payback_months", label: "回本周期", source_domain: "store_financial_model", why: "验证单店模型。" },
    ],
    boundaries: ["当前主定位、融资叙事、远期平台愿景必须分开表达。"],
    open_risks: ["社区小店定位与银发健康科技平台不能同时作为当前主定位。"],
  };
}

function theoryResult(overrides: Partial<PersonalKnowledgeSearchResult>): PersonalKnowledgeSearchResult {
  return {
    chunkId: "chunk-1",
    sourceId: "source-1",
    domain: "brand",
    title: "华与华方法论",
    relativePath: "knowledge/brand/raw/book.epub",
    chunkIndex: 1,
    text: "文化母体、购买理由、超级符号、货架思维共同形成品牌方法。",
    keywords: ["文化母体", "购买理由", "超级符号", "货架思维"],
    score: 10,
    ...overrides,
  };
}

describe("hxy brand master plan", () => {
  test("builds a master plan with methodology, strategy, terminal actions and validation", () => {
    const plan = buildHxyBrandMasterPlan({
      draft: draft(),
      theoryResults: [
        theoryResult({ title: "超级符号原理", text: "文化母体和购买理由需要通过超级符号放大。" }),
        theoryResult({ title: "华与华使用说明书", text: "购买理由要成为终端可执行的货架语言。" }),
      ],
    });

    expect(plan.version).toBe("hxy-brand-master-plan.v1");
    expect(plan.executive_summary).toContain("社区泡脚按摩小店");
    expect(plan.methodology_principles.map((item) => item.key)).toEqual([
      "cultural_context",
      "purchase_reason",
      "super_symbol",
      "shelf_thinking",
    ]);
    expect(plan.sections.map((section) => section.key)).toContain("terminal_execution");
    expect(plan.validation_plan.map((item) => item.metric_key)).toEqual(["brand_asset_consistency", "payback_months"]);
  });

  test("keeps citations and risks visible", () => {
    const plan = buildHxyBrandMasterPlan({
      draft: draft(),
      theoryResults: [theoryResult({ sourceId: "book-a", title: "超级符号原理" })],
    });

    expect(plan.citations).toHaveLength(1);
    expect(plan.citations[0]).toMatchObject({ sourceId: "book-a", title: "超级符号原理" });
    expect(plan.risks[0]).toContain("社区小店定位与银发健康科技平台不能同时作为当前主定位");
  });
});
