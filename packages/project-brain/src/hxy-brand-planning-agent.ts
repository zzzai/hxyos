import fs from "node:fs/promises";
import path from "node:path";
import type { HxyOsiContract, HxyOsiDomain, HxyOsiDomainKey } from "./hxy-osi-contract.js";

export type HxyBrandPlanningDraft = {
  version: "hxy-brand-planning-draft.v1";
  generated_at: string;
  source_osi_generated_at: string;
  positioning: {
    current: string;
    financing_narrative: string;
    future_vision: string;
  };
  brand_assets: {
    name: string;
    slogan_candidates: string[];
    core_expression: string;
  };
  purchase_reasons: string[];
  target_segments: string[];
  product_price_candidates: string[];
  terminal_actions: Array<{
    surface: "门头/门店" | "菜单/套餐" | "技师话术" | "私域/复购";
    action: string;
  }>;
  validation_plan: Array<{
    metric_key: string;
    label: string;
    source_domain: HxyOsiDomainKey;
    why: string;
  }>;
  boundaries: string[];
  open_risks: string[];
};

export function buildHxyBrandPlanningDraft(contract: HxyOsiContract): HxyBrandPlanningDraft {
  const brand = getDomain(contract, "brand_positioning");
  const customer = getDomain(contract, "customer_segment");
  const product = getDomain(contract, "product_price_model");
  const finance = getDomain(contract, "store_financial_model");
  const ai = getDomain(contract, "ai_health_solution");
  return {
    version: "hxy-brand-planning-draft.v1",
    generated_at: new Date().toISOString(),
    source_osi_generated_at: contract.generated_at,
    positioning: {
      current: "荷小悦是社区泡脚按摩小店，核心是家门口、真实有效、价格不心疼、能复购。",
      financing_narrative: "荷小悦是社区健康服务入口，先用泡脚按摩建立信任，再沉淀家庭健康关系。",
      future_vision: "荷小悦远期可以发展为银发健康科技平台或社区健康数字基础设施。",
    },
    brand_assets: {
      name: "荷小悦",
      slogan_candidates: ["草本真现煮，按出真功夫", "功效看得见，健康摸得着"],
      core_expression: firstClaimText(brand) || "真实有效、社区信任、按出真功夫。",
    },
    purchase_reasons: [
      "真实有效：现煮草本泡脚和手法按摩必须让顾客感到身体变化。",
      "价格不心疼：套餐价格要支撑高频社区复购。",
      "离家近可信：门店要成为社区里熟人推荐的健康服务点。",
      "服务可延伸：到店服务、居家护理包和健康档案形成连续关系。",
    ],
    target_segments: [
      firstClaimText(customer) || "悦己年轻人、社区家庭、银发人群仍需样板店验证。",
      "经营者画像需与消费者客群拆开：店长/合伙人是经营角色，不是消费客群。",
    ],
    product_price_candidates: [
      firstClaimText(product) || "招牌款 60 分钟现煮草本泡脚 + 手法按摩 + 护理包，价格候选 128 元。",
    ],
    terminal_actions: [
      { surface: "门头/门店", action: "突出荷小悦、草本现煮、按出真功夫，弱化平台化远期叙事。" },
      { surface: "菜单/套餐", action: "用基础款、招牌款、尊享款三层菜单承接不同频次和客单。" },
      { surface: "技师话术", action: "统一表达真实有效、按后体感、下次护理建议，不做医疗诊断。" },
      { surface: "私域/复购", action: "围绕健康档案、复购标签和居家护理建议做持续触达。" },
    ],
    validation_plan: [
      ...metricsForDomain(brand),
      ...metricsForDomain(customer),
      ...metricsForDomain(product),
      ...metricsForDomain(finance),
      ...metricsForDomain(ai),
    ],
    boundaries: uniqueStrings(contract.domains.flatMap((domain) => domain.answer_boundaries)),
    open_risks: contract.governance.open_review_items.map(
      (item) => `${item.reason} 处理建议：${item.recommended_resolution}`,
    ),
  };
}

function getDomain(contract: HxyOsiContract, domainKey: HxyOsiDomainKey): HxyOsiDomain {
  const domain = contract.domains.find((item) => item.domain === domainKey);
  if (!domain) {
    throw new Error(`Missing HXY OSI domain: ${domainKey}`);
  }
  return domain;
}

function firstClaimText(domain: HxyOsiDomain): string {
  return domain.current_claims[0]?.claim ?? "";
}

function metricsForDomain(domain: HxyOsiDomain): HxyBrandPlanningDraft["validation_plan"] {
  return domain.validation_metrics.map((metric) => ({
    metric_key: metric.key,
    label: metric.label,
    source_domain: domain.domain,
    why: metric.description,
  }));
}

function uniqueStrings(values: string[]): string[] {
  return Array.from(new Set(values));
}

export async function readHxyOsiContract(contractPath: string): Promise<HxyOsiContract> {
  return JSON.parse(await fs.readFile(contractPath, "utf8")) as HxyOsiContract;
}

export async function writeHxyBrandPlanningDraft(draft: HxyBrandPlanningDraft, outputDir: string): Promise<void> {
  await fs.mkdir(outputDir, { recursive: true });
  await fs.writeFile(path.join(outputDir, "brand-planning-draft.json"), `${JSON.stringify(draft, null, 2)}\n`, "utf8");
}
