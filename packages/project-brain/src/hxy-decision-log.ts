import fs from "node:fs/promises";
import path from "node:path";
import type { HxyEvidence, HxyKnowledgeClaim } from "./hxy-knowledge-extractor.js";
import type { HxyClaimTheme, HxyKnowledgeGovernanceReport } from "./hxy-knowledge-governance.js";

export type HxyDecisionKey =
  | "current_positioning"
  | "brand_asset"
  | "product_menu"
  | "store_model"
  | "customer_segment"
  | "franchise_model"
  | "data_ai_model"
  | "other";

export type HxyDecisionLogItem = {
  decision_id: string;
  decision_key: HxyDecisionKey;
  title: string;
  decision: string;
  rationale: string;
  project_stage: HxyKnowledgeClaim["stage"];
  status: HxyKnowledgeClaim["status"];
  confidence: number;
  claim_id: string;
  evidence_ids: string[];
  evidence: Array<Pick<HxyEvidence, "evidence_id" | "title" | "relative_path" | "chunk_index" | "snippet">>;
  validation_required: boolean;
  validation_plan: string[];
};

export type HxyDecisionLog = {
  version: "hxy-decision-log.v1";
  generated_at: string;
  source_governance_generated_at: string;
  decisions: HxyDecisionLogItem[];
  summary: {
    decision_count: number;
    validation_required_count: number;
  };
};

const THEME_TO_DECISION: Partial<Record<HxyClaimTheme, { key: HxyDecisionKey; title: string }>> = {
  community_store_positioning: { key: "current_positioning", title: "当前定位" },
  brand_asset_expression: { key: "brand_asset", title: "品牌资产" },
  product_price_model: { key: "product_menu", title: "产品与菜单" },
  store_financial_model: { key: "store_model", title: "单店模型" },
  customer_segment: { key: "customer_segment", title: "目标客群" },
  franchise_model: { key: "franchise_model", title: "加盟模型" },
  data_ai_model: { key: "data_ai_model", title: "数据与 AI 模型" },
};

export function buildHxyDecisionLog(params: {
  claims: HxyKnowledgeClaim[];
  evidence: HxyEvidence[];
  governance: HxyKnowledgeGovernanceReport;
  now?: () => Date;
}): HxyDecisionLog {
  const now = params.now ?? (() => new Date());
  const claimById = new Map(params.claims.map((claim) => [claim.claim_id, claim]));
  const evidenceById = new Map(params.evidence.map((evidence) => [evidence.evidence_id, evidence]));
  const validationByClaimId = new Map<string, string[]>();
  for (const item of params.governance.review_queue) {
    if (item.review_type !== "validate_assumption" || !item.claim_id) {
      continue;
    }
    const list = validationByClaimId.get(item.claim_id) ?? [];
    list.push(item.reason);
    validationByClaimId.set(item.claim_id, list);
  }
  const decisions: HxyDecisionLogItem[] = [];
  for (const candidate of params.governance.recommended_current_candidates) {
    const claim = claimById.get(candidate.claim_id);
    if (!claim) {
      continue;
    }
    const decisionMeta = THEME_TO_DECISION[candidate.theme] ?? { key: "other" as const, title: "其他决策" };
    const evidence = claim.evidence_ids
      .map((evidenceId) => evidenceById.get(evidenceId))
      .filter((item): item is HxyEvidence => Boolean(item))
      .map((item) => ({
        evidence_id: item.evidence_id,
        title: item.title,
        relative_path: item.relative_path,
        chunk_index: item.chunk_index,
        snippet: item.snippet,
      }));
    const validationPlan = validationByClaimId.get(claim.claim_id) ?? [];
    decisions.push({
      decision_id: `hxy_decision_${decisionMeta.key}_${claim.claim_id}`,
      decision_key: decisionMeta.key,
      title: decisionMeta.title,
      decision: compactDecisionText(decisionMeta.key, claim.claim),
      rationale: candidate.reason,
      project_stage: claim.stage,
      status: claim.status,
      confidence: candidate.confidence,
      claim_id: claim.claim_id,
      evidence_ids: claim.evidence_ids,
      evidence,
      validation_required: claim.needs_validation || validationPlan.length > 0,
      validation_plan: validationPlan.length > 0 ? validationPlan : defaultValidationPlan(decisionMeta.key),
    });
  }
  return {
    version: "hxy-decision-log.v1",
    generated_at: now().toISOString(),
    source_governance_generated_at: params.governance.generated_at,
    decisions,
    summary: {
      decision_count: decisions.length,
      validation_required_count: decisions.filter((decision) => decision.validation_required).length,
    },
  };
}

function compactDecisionText(key: HxyDecisionKey, text: string): string {
  const normalized = normalizeDecisionText(text);
  if (key === "brand_asset") {
    const brandName = firstMatch(normalized, /品牌名[：:]\s*([^\s；;,，。]+)/u);
    const slogan = firstMatch(normalized, /Slog(?:a|o)n[：:]\s*([^。；;]+)/iu);
    const category = firstMatch(normalized, /品牌名[：:]\s*[^\s；;,，。]+\s+([^；;,，。]*?(?:泡脚\.按摩|泡脚·按摩|泡脚按摩))/u);
    const parts = [
      brandName ? `品牌名：${brandName}` : undefined,
      category ? `品类表达：${category}` : undefined,
      slogan ? `Slogan：${slogan}` : undefined,
    ].filter(Boolean);
    if (parts.length > 0) {
      return `${parts.join("；")}。`;
    }
  }
  if (key === "product_menu") {
    const entry = firstMatch(normalized, /(入口款\s*\d+\s*分钟[^¥。；;]*¥\s*\d+)/u);
    const main = firstMatch(normalized, /(主推款\s*\d+\s*分钟[^¥。；;]*¥\s*\d+)/u);
    const upsell = firstMatch(normalized, /(加油款\s*\d+\s*分钟[^¥。；;]*¥\s*\d+)/u);
    const items = [entry, main, upsell]
      .filter((item): item is string => Boolean(item))
      .map((item) => item.replace(/\s+/g, ""));
    if (items.length > 0) {
      return `产品菜单：${items.join("；")}。`;
    }
  }
  if (key === "current_positioning") {
    const community = firstMatch(normalized, /成为[“"']?(社区里那个按摩真好使的地方)[”"']?/u);
    if (community) {
      return `当前定位：成为${community}。`;
    }
    const direct = firstMatch(normalized, /(社区泡脚按摩小店[^。；;]*)/u);
    if (direct) {
      return `当前定位：${direct}。`;
    }
  }
  if (key === "store_model") {
    const area = firstMatch(normalized, /(?:店面面积|面积)\s*约?\s*(\d+\s*㎡)/u);
    const coreService = firstMatch(
      normalized,
      /核心服务\s*([^。；;，,]*?泡脚\s*\+\s*按摩(?:（[^）]*）)?)(?=\s*(?:装修|投资|目标|套餐|。|；|;|，|,|$))/u,
    );
    const investment = firstMatch(normalized, /投资规模\s*约?\s*(\d+\s*万元)/u);
    const payback = firstMatch(normalized, /目标回本周期\s*(\d+\s*个月)/u);
    const parts = [
      area ? `约${area.replace(/\s+/g, "")}` : undefined,
      coreService ? `核心服务：${coreService.replace(/（[^）]*）/gu, "").replace(/\s+/g, "")}` : undefined,
      investment ? `投资约${investment.replace(/\s+/g, "")}` : undefined,
      payback ? `目标回本周期${payback.replace(/\s+/g, "")}` : undefined,
    ].filter(Boolean);
    if (parts.length > 0) {
      return `单店模型：${parts.join("；")}。`;
    }
  }
  if (key === "customer_segment") {
    const segment = firstMatch(normalized, /(?:一个核心人群|核心人群|目标客群)[：:]?\s*([^。；;？?]+)/u);
    if (segment) {
      return `目标客群：${segment.replace(/\s*荷小悦到底在解决什么问题$/, "")}。`;
    }
  }
  if (key === "franchise_model") {
    const scope = /开放单店加盟模式/u.test(normalized) ? "开放单店加盟" : undefined;
    const region = firstMatch(normalized, /聚焦([^，,。；;]+)/u);
    const threshold = firstMatch(normalized, /(?:加盟门槛|门槛)[：:]?\s*(单店投资\s*\d+\s*-\s*\d+\s*万元)/u);
    const parts = [
      scope && region ? `${scope}，聚焦${region}` : scope,
      threshold ? `门槛：${threshold.replace(/\s+/g, "")}` : undefined,
    ].filter(Boolean);
    if (parts.length > 0) {
      return `加盟模型：${parts.join("；")}。`;
    }
  }
  if (key === "data_ai_model" && /AI诊断结果|自动生成调理方案/u.test(normalized)) {
    return "数据与AI模型：基于AI诊断结果自动生成到店服务、居家护理和饮食建议。";
  }
  return normalized;
}

function normalizeDecisionText(text: string): string {
  return text.replace(/\s+/g, " ").replace(/​/g, "").trim();
}

function firstMatch(text: string, pattern: RegExp): string | undefined {
  return pattern.exec(text)?.[1]?.trim();
}

function defaultValidationPlan(key: HxyDecisionKey): string[] {
  if (key === "store_model") {
    return ["用样板店真实营收、成本、客流、复购和回本周期验证单店模型。"];
  }
  if (key === "product_menu") {
    return ["用套餐选择率、复购率、客单价和顾客反馈验证产品菜单。"];
  }
  if (key === "current_positioning") {
    return ["用到店转化、顾客复述、私域咨询和复购反馈验证定位是否被理解。"];
  }
  return ["补充人工确认和样板店反馈。"];
}

export function renderHxyDecisionLogMarkdown(log: HxyDecisionLog): string {
  const lines = [
    "# HXY 决策日志",
    "",
    `生成时间：${log.generated_at}`,
    `决策数：${log.summary.decision_count}`,
    `需验证：${log.summary.validation_required_count}`,
    "",
  ];
  for (const decision of log.decisions) {
    lines.push(`## ${decision.title}`);
    lines.push("");
    lines.push(`- 决策：${decision.decision}`);
    lines.push(`- 理由：${decision.rationale}`);
    lines.push(`- 阶段：${decision.project_stage}`);
    lines.push(`- 状态：${decision.status}`);
    lines.push(`- 置信度：${decision.confidence}`);
    lines.push(`- Claim：${decision.claim_id}`);
    if (decision.validation_required) {
      lines.push("- 待验证：是");
      for (const item of decision.validation_plan) {
        lines.push(`  - ${item}`);
      }
    }
    if (decision.evidence.length > 0) {
      lines.push("- 证据：");
      for (const evidence of decision.evidence) {
        lines.push(`  - ${evidence.title} ${evidence.relative_path}#chunk-${evidence.chunk_index}`);
        lines.push(`    ${evidence.snippet}`);
      }
    }
    lines.push("");
  }
  return `${lines.join("\n").trim()}\n`;
}

export async function readHxyDecisionLogInputs(structuredDir: string): Promise<{
  claims: HxyKnowledgeClaim[];
  evidence: HxyEvidence[];
  governance: HxyKnowledgeGovernanceReport;
}> {
  const [claimsRaw, evidenceRaw, governanceRaw] = await Promise.all([
    fs.readFile(path.join(structuredDir, "claims.json"), "utf8"),
    fs.readFile(path.join(structuredDir, "evidence.json"), "utf8"),
    fs.readFile(path.join(structuredDir, "governance-report.json"), "utf8"),
  ]);
  return {
    claims: JSON.parse(claimsRaw) as HxyKnowledgeClaim[],
    evidence: JSON.parse(evidenceRaw) as HxyEvidence[],
    governance: JSON.parse(governanceRaw) as HxyKnowledgeGovernanceReport,
  };
}

export async function writeHxyDecisionLog(log: HxyDecisionLog, outputDir: string): Promise<void> {
  await fs.mkdir(outputDir, { recursive: true });
  await Promise.all([
    fs.writeFile(path.join(outputDir, "decision-log.json"), `${JSON.stringify(log, null, 2)}\n`, "utf8"),
    fs.writeFile(path.join(outputDir, "decision-log.md"), renderHxyDecisionLogMarkdown(log), "utf8"),
  ]);
}
