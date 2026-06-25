import { describe, expect, test } from "vitest";
import {
  buildHxyDecisionLog,
  renderHxyDecisionLogMarkdown,
} from "./hxy-decision-log.js";
import type { HxyKnowledgeClaim, HxyEvidence } from "./hxy-knowledge-extractor.js";
import type { HxyKnowledgeGovernanceReport } from "./hxy-knowledge-governance.js";

function claim(overrides: Partial<HxyKnowledgeClaim> & Pick<HxyKnowledgeClaim, "claim_id" | "claim_type" | "claim">): HxyKnowledgeClaim {
  return {
    stage: "preparation",
    status: "current_candidate",
    confidence: 0.78,
    evidence_ids: [`evidence-${overrides.claim_id}`],
    conflict_claim_ids: [],
    needs_validation: false,
    ...overrides,
  };
}

function evidence(id: string, snippet: string): HxyEvidence {
  return {
    evidence_id: id,
    source_id: `source-${id}`,
    title: `资料 ${id}`,
    relative_path: `knowledge/hxy/raw/${id}.md`,
    chunk_index: 0,
    snippet,
  };
}

describe("hxy decision log", () => {
  test("builds traceable decisions from governance candidates and evidence", () => {
    const claims = [
      claim({
        claim_id: "positioning",
        claim_type: "brand_positioning",
        claim: "荷小悦当前主定位是社区泡脚按摩小店，以真实有效、社区信任和私域复购为核心。",
      }),
      claim({
        claim_id: "finance",
        claim_type: "financial_assumption",
        claim: "单店投资50万元，月营收18万元，月净利润6.4万元，回本周期6-8个月。",
        needs_validation: true,
      }),
    ];
    const governance: HxyKnowledgeGovernanceReport = {
      version: "hxy-knowledge-governance.v1",
      generated_at: "2026-05-18T00:00:00.000Z",
      summary: {
        claim_count: claims.length,
        theme_count: 2,
        conflict_count: 0,
        recommended_current_candidate_count: 2,
        needs_human_review_count: 1,
      },
      theme_groups: {},
      recommended_current_candidates: [
        {
          claim_id: "positioning",
          claim_type: "brand_positioning",
          theme: "community_store_positioning",
          claim: claims[0].claim,
          reason: "当前样板店阶段应收敛为社区小店定位。",
          confidence: 0.78,
        },
        {
          claim_id: "finance",
          claim_type: "financial_assumption",
          theme: "store_financial_model",
          claim: claims[1].claim,
          reason: "单店模型需要作为样板店验证假设。",
          confidence: 0.7,
        },
      ],
      conflicts: [],
      review_queue: [
        {
          review_type: "validate_assumption",
          claim_id: "finance",
          reason: "该 claim 涉及财务假设，需要样板店真实数据验证。",
        },
      ],
    };

    const log = buildHxyDecisionLog({
      claims,
      evidence: [
        evidence("evidence-positioning", "荷小悦定位社区泡脚按摩小店，强调社区信任和复购。"),
        evidence("evidence-finance", "单店投资50万元，月净利润6.4万元，回本周期6-8个月。"),
      ],
      governance,
      now: () => new Date("2026-05-18T00:00:00.000Z"),
    });

    expect(log.version).toBe("hxy-decision-log.v1");
    expect(log.decisions).toHaveLength(2);
    expect(log.decisions[0]).toMatchObject({
      decision_key: "current_positioning",
      status: "current_candidate",
      project_stage: "preparation",
      decision: "当前定位：社区泡脚按摩小店，以真实有效、社区信任和私域复购为核心。",
    });
    expect(log.decisions[0]?.evidence[0]?.snippet).toContain("社区泡脚按摩小店");
    expect(log.decisions[1]?.validation_required).toBe(true);
    expect(log.decisions[1]?.validation_plan[0]).toContain("样板店真实数据验证");

    const markdown = renderHxyDecisionLogMarkdown(log);
    expect(markdown).toContain("# HXY 决策日志");
    expect(markdown).toContain("当前定位");
    expect(markdown).toContain("单店模型");
    expect(markdown).toContain("knowledge/hxy/raw/evidence-finance.md");
  });

  test("renders compact decisions instead of dumping long source fragments", () => {
    const claims = [
      claim({
        claim_id: "brand",
        claim_type: "brand_asset",
        claim: "荷小悦-新小店模型 品牌名：荷小悦 泡脚.按摩 Slogon: 草本真现煮，按出真功夫。",
      }),
      claim({
        claim_id: "menu",
        claim_type: "product_service",
        claim:
          "四、商业模型 店型核心参数 参数 设计值 店面面积 约 100 ㎡ 核心服务 泡脚 + 按摩。套餐设计 套餐 内容 价格 战略角色 入口款 50 分钟泡脚+按摩 ¥88 降低决策门槛，完成首次体验 主推款 60 分钟泡脚+按摩+离店护理包 ¥128 核心利润款，嵌入零售转化 加油款 75 分钟+下次优先预约 ¥168 卖确定性，提升粘性与客单价。",
        needs_validation: true,
      }),
    ];
    const governance: HxyKnowledgeGovernanceReport = {
      version: "hxy-knowledge-governance.v1",
      generated_at: "2026-05-18T00:00:00.000Z",
      summary: {
        claim_count: claims.length,
        theme_count: 2,
        conflict_count: 0,
        recommended_current_candidate_count: 2,
        needs_human_review_count: 0,
      },
      theme_groups: {},
      recommended_current_candidates: [
        {
          claim_id: "brand",
          claim_type: "brand_asset",
          theme: "brand_asset_expression",
          claim: claims[0].claim,
          reason: "品牌资产需要统一口号、IP 和终端表达。",
          confidence: 0.76,
        },
        {
          claim_id: "menu",
          claim_type: "product_service",
          theme: "product_price_model",
          claim: claims[1].claim,
          reason: "产品价格模型直接影响单店利润和复购。",
          confidence: 0.74,
        },
      ],
      conflicts: [],
      review_queue: [],
    };

    const log = buildHxyDecisionLog({
      claims,
      evidence: [evidence("evidence-brand", claims[0].claim), evidence("evidence-menu", claims[1].claim)],
      governance,
      now: () => new Date("2026-05-18T00:00:00.000Z"),
    });

    expect(log.decisions[0]?.decision).toBe("品牌名：荷小悦；品类表达：泡脚.按摩；Slogan：草本真现煮，按出真功夫。");
    expect(log.decisions[1]?.decision).toBe(
      "产品菜单：入口款50分钟泡脚+按摩¥88；主推款60分钟泡脚+按摩+离店护理包¥128；加油款75分钟+下次优先预约¥168。",
    );
    expect(log.decisions[1]?.decision).not.toContain("四、商业模型");
  });

  test("compacts positioning, customer segment, store model, franchise, and data AI decisions", () => {
    const claims = [
      claim({
        claim_id: "positioning",
        claim_type: "financial_assumption",
        claim: '荷小悦不是要赢郑远元，不是要赢奈晚推拿，荷 小悦只要成为"社区里那个按摩真好使的地方"就够了。',
      }),
      claim({
        claim_id: "store",
        claim_type: "store_model",
        claim:
          "四、商业模型 店型核心参数 参数 设计值 店面面积 约 100 ㎡ 核心服务 泡脚 + 按摩（极简双项） 装修风格 新中式极简（干净、安静、暖光） 投资规模 约 50 万元 目标回本周期 8 个月 套餐设计 套餐 内容 价格 战略角色 入口款 50 分钟泡脚+按摩 ¥88 主推款 60 分钟泡脚+按摩+离店护理包 ¥128。",
        needs_validation: true,
      }),
      claim({
        claim_id: "segment",
        claim_type: "customer_segment",
        claim: "一个核心人群：悦己型年轻养生客群 荷小悦到底在解决什么问题？",
      }),
      claim({
        claim_id: "franchise",
        claim_type: "store_model",
        claim: "二、加盟方式 开放单店加盟模式，聚焦华南社区，门槛较低：加盟门槛单店投资30-50万元，适合中小投资者。",
        needs_validation: true,
      }),
      claim({
        claim_id: "ai",
        claim_type: "product_service",
        claim:
          "基于AI诊断结果，自动生成调理方案：到店服务：推拿+艾灸+拔罐组合，居家护理：泡脚包配方、穴位按摩视频、作息建议，饮食建议：根据体质推荐食谱。",
        needs_validation: true,
      }),
    ];
    const themes = [
      "community_store_positioning",
      "store_financial_model",
      "customer_segment",
      "franchise_model",
      "data_ai_model",
    ] as const;
    const governance: HxyKnowledgeGovernanceReport = {
      version: "hxy-knowledge-governance.v1",
      generated_at: "2026-05-18T00:00:00.000Z",
      summary: {
        claim_count: claims.length,
        theme_count: 5,
        conflict_count: 0,
        recommended_current_candidate_count: 5,
        needs_human_review_count: 0,
      },
      theme_groups: {},
      recommended_current_candidates: claims.map((item, index) => ({
        claim_id: item.claim_id,
        claim_type: item.claim_type,
        theme: themes[index],
        claim: item.claim,
        reason: "测试理由",
        confidence: item.confidence,
      })),
      conflicts: [],
      review_queue: [],
    };

    const log = buildHxyDecisionLog({
      claims,
      evidence: claims.map((item) => evidence(`evidence-${item.claim_id}`, item.claim)),
      governance,
      now: () => new Date("2026-05-18T00:00:00.000Z"),
    });

    expect(log.decisions.map((item) => item.decision)).toEqual([
      '当前定位：成为社区里那个按摩真好使的地方。',
      "单店模型：约100㎡；核心服务：泡脚+按摩；投资约50万元；目标回本周期8个月。",
      "目标客群：悦己型年轻养生客群。",
      "加盟模型：开放单店加盟，聚焦华南社区；门槛：单店投资30-50万元。",
      "数据与AI模型：基于AI诊断结果自动生成到店服务、居家护理和饮食建议。",
    ]);
  });
});
