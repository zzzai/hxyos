import fs from "node:fs/promises";
import path from "node:path";
import type { HxyBrandPlanningDraft } from "./hxy-brand-planning-agent.js";
import type { PersonalKnowledgeSearchResult } from "./personal-knowledge.js";

export type HxyBrandMethodologyPrinciple = {
  key: "cultural_context" | "purchase_reason" | "super_symbol" | "shelf_thinking";
  label: string;
  application: string;
};

export type HxyBrandMasterPlan = {
  version: "hxy-brand-master-plan.v1";
  generated_at: string;
  source_draft_generated_at: string;
  executive_summary: string;
  methodology_principles: HxyBrandMethodologyPrinciple[];
  sections: Array<{
    key:
      | "positioning_strategy"
      | "purchase_reason_system"
      | "brand_asset_system"
      | "product_menu_strategy"
      | "terminal_execution"
      | "private_domain_growth"
      | "pilot_validation";
    title: string;
    content: string[];
  }>;
  validation_plan: HxyBrandPlanningDraft["validation_plan"];
  risks: string[];
  citations: Array<{
    sourceId: string;
    title: string;
    relativePath: string;
    chunkIndex: number;
    score: number;
    snippet: string;
  }>;
};

export function buildHxyBrandMasterPlan(params: {
  draft: HxyBrandPlanningDraft;
  theoryResults: PersonalKnowledgeSearchResult[];
}): HxyBrandMasterPlan {
  const draft = params.draft;
  return {
    version: "hxy-brand-master-plan.v1",
    generated_at: new Date().toISOString(),
    source_draft_generated_at: draft.generated_at,
    executive_summary: [
      draft.positioning.current,
      "当前全案只围绕样板店阶段收敛，不把远期平台叙事前置为顾客购买理由。",
    ].join(" "),
    methodology_principles: [
      {
        key: "cultural_context",
        label: "文化母体",
        application: "寄生在社区日常健康、邻里信任、下班疲劳修复和家庭照护这些真实生活场景里。",
      },
      {
        key: "purchase_reason",
        label: "购买理由",
        application: draft.purchase_reasons.join(" "),
      },
      {
        key: "super_symbol",
        label: "超级符号",
        application: "先用荷小悦、草本现煮、按出真功夫形成可看见、可听见、可复述的符号系统。",
      },
      {
        key: "shelf_thinking",
        label: "货架思维",
        application: "把门头、菜单、技师话术、私域消息都当成货架，让顾客一眼知道买什么、为什么买、下次怎么来。",
      },
    ],
    sections: [
      {
        key: "positioning_strategy",
        title: "定位策略",
        content: [
          `当前定位：${draft.positioning.current}`,
          `融资叙事：${draft.positioning.financing_narrative}`,
          `远期愿景：${draft.positioning.future_vision}`,
          "三层叙事必须分开，避免门店终端说空话。",
        ],
      },
      {
        key: "purchase_reason_system",
        title: "购买理由系统",
        content: draft.purchase_reasons,
      },
      {
        key: "brand_asset_system",
        title: "品牌资产系统",
        content: [
          `品牌名：${draft.brand_assets.name}`,
          `口号候选：${draft.brand_assets.slogan_candidates.join(" / ")}`,
          `核心表达：${draft.brand_assets.core_expression}`,
        ],
      },
      {
        key: "product_menu_strategy",
        title: "产品与菜单策略",
        content: [
          ...draft.product_price_candidates,
          "菜单需要形成基础款、招牌款、尊享款三层，而不是只堆项目名。",
        ],
      },
      {
        key: "terminal_execution",
        title: "终端执行",
        content: draft.terminal_actions.map((action) => `${action.surface}：${action.action}`),
      },
      {
        key: "private_domain_growth",
        title: "私域与复购",
        content: [
          "每次服务后沉淀健康档案、护理建议和下次触达理由。",
          "复购不是靠群发优惠，而是靠体感改善、熟人信任和连续护理建议。",
        ],
      },
      {
        key: "pilot_validation",
        title: "样板店验证",
        content: draft.validation_plan.map((item) => `${item.label}：${item.why}`),
      },
    ],
    validation_plan: draft.validation_plan,
    risks: draft.open_risks,
    citations: params.theoryResults.slice(0, 5).map((result) => ({
      sourceId: result.sourceId,
      title: result.title,
      relativePath: result.relativePath,
      chunkIndex: result.chunkIndex,
      score: result.score,
      snippet: result.text.slice(0, 180),
    })),
  };
}

export async function readHxyBrandPlanningDraft(draftPath: string): Promise<HxyBrandPlanningDraft> {
  return JSON.parse(await fs.readFile(draftPath, "utf8")) as HxyBrandPlanningDraft;
}

export async function writeHxyBrandMasterPlan(plan: HxyBrandMasterPlan, outputDir: string): Promise<void> {
  await fs.mkdir(outputDir, { recursive: true });
  await fs.writeFile(path.join(outputDir, "brand-master-plan.json"), `${JSON.stringify(plan, null, 2)}\n`, "utf8");
}
