import fs from "node:fs/promises";
import path from "node:path";
import type {
  HxyClaimConflict,
  HxyClaimTheme,
  HxyKnowledgeGovernanceReport,
} from "./hxy-knowledge-governance.js";

export type HxyOsiDomainKey =
  | "brand_positioning"
  | "customer_segment"
  | "product_price_model"
  | "store_financial_model"
  | "ai_health_solution";

export type HxyOsiField = {
  key: string;
  label: string;
  description: string;
};

export type HxyOsiValidationMetric = {
  key: string;
  label: string;
  description: string;
};

export type HxyOsiAgentUsage = {
  agent_key: string;
  purpose: string;
};

export type HxyOsiClaimRef = {
  claim_id: string;
  claim_type: string;
  theme: HxyClaimTheme;
  claim: string;
  confidence: number;
};

export type HxyOsiDomain = {
  domain: HxyOsiDomainKey;
  label: string;
  purpose: string;
  base_fields: HxyOsiField[];
  current_claims: HxyOsiClaimRef[];
  answer_boundaries: string[];
  validation_metrics: HxyOsiValidationMetric[];
  agent_usages: HxyOsiAgentUsage[];
};

export type HxyOsiContract = {
  version: "hxy-osi-contract.v1";
  generated_at: string;
  stage: "preparation";
  source_governance_generated_at: string;
  domains: HxyOsiDomain[];
  governance: {
    open_review_items: Array<{
      source: "knowledge_governance";
      conflict_id: string;
      severity: "high" | "medium";
      reason: string;
      recommended_resolution: string;
    }>;
  };
};

export function buildHxyOsiContract(report: HxyKnowledgeGovernanceReport): HxyOsiContract {
  const candidates = report.recommended_current_candidates.map((candidate) => ({
    claim_id: candidate.claim_id,
    claim_type: candidate.claim_type,
    theme: candidate.theme,
    claim: candidate.claim,
    confidence: candidate.confidence,
  }));
  return {
    version: "hxy-osi-contract.v1",
    generated_at: new Date().toISOString(),
    stage: "preparation",
    source_governance_generated_at: report.generated_at,
    domains: [
      buildBrandPositioningDomain(candidates),
      buildCustomerSegmentDomain(candidates),
      buildProductPriceDomain(candidates),
      buildStoreFinancialDomain(candidates),
      buildAiHealthSolutionDomain(candidates),
    ],
    governance: {
      open_review_items: report.conflicts.map(toOpenReviewItem),
    },
  };
}

function buildBrandPositioningDomain(candidates: HxyOsiClaimRef[]): HxyOsiDomain {
  return {
    domain: "brand_positioning",
    label: "品牌定位 OSI",
    purpose: "把当前主定位、品牌资产和远期平台叙事拆开，避免策划输出混用。",
    base_fields: [
      { key: "current_positioning", label: "当前主定位", description: "面向顾客、门店和招商的当前阶段定位。" },
      { key: "brand_promise", label: "品牌承诺", description: "顾客能直接感知和复述的承诺。" },
      { key: "brand_asset", label: "品牌资产", description: "名称、口号、IP、符号和终端表达。" },
      { key: "future_vision", label: "远期愿景", description: "融资或规模化阶段可使用的平台叙事。" },
    ],
    current_claims: pickClaims(candidates, ["community_store_positioning", "brand_asset_expression"]),
    answer_boundaries: [
      "当前主定位、融资叙事、远期平台愿景必须分开表达。",
      "未人工确认前，不把银发健康科技平台作为当前主定位。",
      "品牌策划输出必须说明适用阶段。",
    ],
    validation_metrics: [
      { key: "unaided_positioning_recall", label: "无提示定位复述率", description: "顾客或加盟商能否复述当前主定位。" },
      { key: "brand_asset_consistency", label: "品牌资产一致率", description: "门头、物料、话术是否使用统一表达。" },
    ],
    agent_usages: [
      { agent_key: "brand_planning_agent_v1", purpose: "生成定位、购买理由、口号、终端动作。" },
      { agent_key: "terminal_expression_agent_v1", purpose: "把定位翻译为门头、菜单、物料和话术。" },
    ],
  };
}

function buildCustomerSegmentDomain(candidates: HxyOsiClaimRef[]): HxyOsiDomain {
  return {
    domain: "customer_segment",
    label: "客群 OSI",
    purpose: "拆分消费者客群、经营者画像和阶段性验证人群。",
    base_fields: [
      { key: "consumer_segment", label: "消费者客群", description: "实际购买和复购的用户人群。" },
      { key: "operator_profile", label: "经营者画像", description: "店长、合伙人、主理人等经营角色。" },
      { key: "pain_point", label: "痛点", description: "疲劳、酸痛、情绪、信任和健康管理需求。" },
      { key: "usage_scene", label: "场景", description: "社区、家庭、悦己、银发等消费场景。" },
    ],
    current_claims: pickClaims(candidates, ["customer_segment"]),
    answer_boundaries: [
      "消费者客群和店长/合伙人画像必须分开。",
      "悦己年轻人、社区家庭、银发人群目前是并列候选，不能直接合成单一结论。",
    ],
    validation_metrics: [
      { key: "first_visit_conversion_rate", label: "首访转化率", description: "不同客群首次到店转化。" },
      { key: "repeat_visit_rate", label: "复购率", description: "不同客群 30/60/90 天复购。" },
      { key: "segment_ltv", label: "客群 LTV", description: "不同客群的生命周期价值。" },
    ],
    agent_usages: [
      { agent_key: "customer_research_agent_v1", purpose: "生成用户洞察和调研问题。" },
      { agent_key: "campaign_strategy_agent_v1", purpose: "按客群生成营销动作。" },
    ],
  };
}

function buildProductPriceDomain(candidates: HxyOsiClaimRef[]): HxyOsiDomain {
  return {
    domain: "product_price_model",
    label: "产品价格 OSI",
    purpose: "沉淀项目、套餐、价格、时长和适用场景，供菜单和单店模型复用。",
    base_fields: [
      { key: "product_name", label: "产品名", description: "项目或套餐名称。" },
      { key: "duration_minutes", label: "服务时长", description: "服务交付时长。" },
      { key: "price_amount", label: "价格", description: "标价或建议成交价。" },
      { key: "included_items", label: "包含内容", description: "泡脚、按摩、护理包、草本茶等。" },
      { key: "target_segment", label: "目标客群", description: "产品适配的人群和场景。" },
    ],
    current_claims: pickClaims(candidates, ["product_price_model"]),
    answer_boundaries: [
      "价格版本并存时必须标注候选版本，不输出唯一价格表。",
      "套餐必须绑定时长、价格、服务内容和毛利假设。",
    ],
    validation_metrics: [
      { key: "take_rate_by_package", label: "套餐选择率", description: "各套餐成交占比。" },
      { key: "gross_margin_by_package", label: "套餐毛利率", description: "价格扣除人工、耗材和平台费用后的毛利。" },
      { key: "revisit_rate_by_package", label: "套餐复购率", description: "不同套餐带来的复购差异。" },
    ],
    agent_usages: [
      { agent_key: "menu_design_agent_v1", purpose: "输出菜单、套餐和价格结构。" },
      { agent_key: "store_model_calculator_v1", purpose: "把套餐价格带入单店模型测算。" },
    ],
  };
}

function buildStoreFinancialDomain(candidates: HxyOsiClaimRef[]): HxyOsiDomain {
  return {
    domain: "store_financial_model",
    label: "单店财务 OSI",
    purpose: "把投资、营收、成本、利润和回本周期变成可验证假设。",
    base_fields: [
      { key: "initial_investment", label: "初始投资", description: "装修、设备、开办和周转资金。" },
      { key: "monthly_revenue", label: "月营收", description: "服务、产品和会员相关收入。" },
      { key: "monthly_cost", label: "月成本", description: "房租、人工、耗材、水电、平台和总部费用。" },
      { key: "monthly_profit", label: "月利润", description: "扣除运营成本后的利润。" },
      { key: "payback_months", label: "回本周期", description: "初始投资除以月净现金流。" },
    ],
    current_claims: pickClaims(candidates, ["store_financial_model"]),
    answer_boundaries: [
      "未有样板店真实数据前，只能称为假设模型。",
      "回本周期必须绑定城市、面积、房租、人工、客流和套餐结构。",
    ],
    validation_metrics: [
      { key: "initial_investment", label: "初始投资", description: "样板店真实投入。" },
      { key: "monthly_net_cashflow", label: "月净现金流", description: "每月实际到账减经营支出。" },
      { key: "payback_months", label: "回本周期", description: "真实累计净现金流覆盖初始投资的月份。" },
    ],
    agent_usages: [
      { agent_key: "store_model_calculator_v1", purpose: "测算不同店型和价格结构的回本周期。" },
      { agent_key: "pilot_store_validation_agent_v1", purpose: "跟踪样板店假设验证。" },
    ],
  };
}

function buildAiHealthSolutionDomain(candidates: HxyOsiClaimRef[]): HxyOsiDomain {
  return {
    domain: "ai_health_solution",
    label: "AI 健康方案 OSI",
    purpose: "把 AI 能力限定在健康档案、服务推荐、复购标签和调理方案，不先做空泛平台叙事。",
    base_fields: [
      { key: "health_profile", label: "健康档案", description: "体质、偏好、服务历史和禁忌。" },
      { key: "diagnosis_input", label: "诊断输入", description: "问诊、舌诊/面诊、服务反馈等输入。" },
      { key: "recommendation", label: "推荐方案", description: "到店服务、居家护理、泡脚包和饮食建议。" },
      { key: "followup_tag", label: "复购标签", description: "用于提醒、召回和复购推荐的标签。" },
    ],
    current_claims: pickClaims(candidates, ["data_ai_model"]),
    answer_boundaries: [
      "AI 不能输出医疗诊断结论。",
      "AI 建议必须绑定可执行服务、居家护理或复购动作。",
      "没有用户授权和数据闭环前，不宣称健康科技平台能力已成立。",
    ],
    validation_metrics: [
      { key: "recommendation_acceptance_rate", label: "推荐采纳率", description: "用户接受 AI 推荐服务的比例。" },
      { key: "followup_conversion_rate", label: "跟进转化率", description: "AI 标签推动复购或到店的转化。" },
      { key: "profile_completion_rate", label: "健康档案完整率", description: "有效字段覆盖率。" },
    ],
    agent_usages: [
      { agent_key: "health_plan_agent_v1", purpose: "根据档案和服务历史生成调理建议。" },
      { agent_key: "retention_action_agent_v1", purpose: "把健康标签转成复购动作。" },
    ],
  };
}

function pickClaims(candidates: HxyOsiClaimRef[], themes: HxyClaimTheme[]): HxyOsiClaimRef[] {
  return candidates.filter((candidate) => themes.includes(candidate.theme));
}

function toOpenReviewItem(conflict: HxyClaimConflict): HxyOsiContract["governance"]["open_review_items"][number] {
  return {
    source: "knowledge_governance",
    conflict_id: conflict.conflict_id,
    severity: conflict.conflict_type === "positioning_stage_conflict" ? "high" : "medium",
    reason: conflict.reason,
    recommended_resolution: conflict.recommended_resolution,
  };
}

export async function readHxyKnowledgeGovernanceReport(reportPath: string): Promise<HxyKnowledgeGovernanceReport> {
  return JSON.parse(await fs.readFile(reportPath, "utf8")) as HxyKnowledgeGovernanceReport;
}

export async function writeHxyOsiContract(contract: HxyOsiContract, outputDir: string): Promise<void> {
  await fs.mkdir(outputDir, { recursive: true });
  await fs.writeFile(path.join(outputDir, "osi-contract.json"), `${JSON.stringify(contract, null, 2)}\n`, "utf8");
}
