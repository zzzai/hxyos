import fs from "node:fs/promises";
import path from "node:path";
import type { HxyKnowledgeClaim } from "./hxy-knowledge-extractor.js";

export type HxyClaimTheme =
  | "community_store_positioning"
  | "silver_health_platform_positioning"
  | "wellness_chain_positioning"
  | "brand_asset_expression"
  | "customer_segment"
  | "product_price_model"
  | "store_financial_model"
  | "franchise_model"
  | "data_ai_model"
  | "risk_or_constraint"
  | "other";

export type HxyClaimConflict = {
  conflict_id: string;
  conflict_type: "positioning_stage_conflict" | "financial_assumption_conflict" | "brand_expression_conflict";
  primary_claim_id: string;
  conflicting_claim_id: string;
  reason: string;
  recommended_resolution: string;
  needs_human_review: boolean;
};

export type HxyThemeGroup = {
  theme: HxyClaimTheme;
  claim_count: number;
  claim_ids: string[];
  representative_claims: string[];
};

export type HxyKnowledgeGovernanceReport = {
  version: "hxy-knowledge-governance.v1";
  generated_at: string;
  summary: {
    claim_count: number;
    theme_count: number;
    conflict_count: number;
    recommended_current_candidate_count: number;
    needs_human_review_count: number;
  };
  theme_groups: Record<string, HxyThemeGroup>;
  recommended_current_candidates: Array<{
    claim_id: string;
    claim_type: string;
    theme: HxyClaimTheme;
    claim: string;
    reason: string;
    confidence: number;
  }>;
  conflicts: HxyClaimConflict[];
  review_queue: Array<{
    review_type: "confirm_current" | "resolve_conflict" | "validate_assumption";
    claim_id?: string;
    conflict_id?: string;
    reason: string;
  }>;
};

export function classifyHxyClaimTheme(claim: string): HxyClaimTheme {
  const text = claim.toLowerCase();
  if (/客群|人群|用户|目标客群|目标用户|目标人群|老人|中老年|社区家庭|女性|年轻|悦己/u.test(claim)) {
    return "customer_segment";
  }
  if (/银发健康科技平台|银发基建|养老生态|健康科技平台|健康数字基础设施|社区健康基础设施|社区健康数字基础设施/u.test(claim)) {
    return "silver_health_platform_positioning";
  }
  if (/社区.*(泡脚|按摩|小店|私域|真好使)|泡脚按摩小店|社区小店/u.test(claim)) {
    return "community_store_positioning";
  }
  if (/养生连锁|国民品牌|健康生活方式|社区健康/u.test(claim)) {
    return "wellness_chain_positioning";
  }
  if (/slogan|口号|\bip\b|超级符号|品牌名|草本真现煮|按出真功夫|功效看得见/u.test(text)) {
    return "brand_asset_expression";
  }
  if (/加盟|区域保护|加盟商|督导|培训|开店/u.test(claim)) {
    return "franchise_model";
  }
  if (/投资|回本|利润|营收|毛利|净利|现金流|面积|房租|技师|单店/u.test(claim)) {
    return "store_financial_model";
  }
  if (isProductPriceText(claim)) {
    return "product_price_model";
  }
  if (/ai|数据|中台|小程序|iot|o2o|健康档案|标签/u.test(text)) {
    return "data_ai_model";
  }
  if (/风险|不足|问题|挑战|瓶颈|缺乏|排斥|合规/u.test(claim)) {
    return "risk_or_constraint";
  }
  return "other";
}

export function detectHxyClaimConflicts(claims: HxyKnowledgeClaim[]): HxyClaimConflict[] {
  const conflicts: HxyClaimConflict[] = [];
  const byTheme = groupClaimsByTheme(claims);
  const communityClaim = pickRepresentativeClaim(byTheme.community_store_positioning ?? [], "community_store_positioning");
  const platformClaim = pickRepresentativeClaim(
    byTheme.silver_health_platform_positioning ?? [],
    "silver_health_platform_positioning",
  );
  if (communityClaim && platformClaim) {
    conflicts.push({
      conflict_id: `hxy_conflict_positioning_${communityClaim.claim_id}_${platformClaim.claim_id}`,
      conflict_type: "positioning_stage_conflict",
      primary_claim_id: communityClaim.claim_id,
      conflicting_claim_id: platformClaim.claim_id,
      reason: "社区小店定位适合筹备期/样板店期，银发健康科技平台更像融资或远期生态叙事，二者不能同时作为当前主定位。",
      recommended_resolution: "建议当前主定位以社区泡脚按摩小店/社区健康服务入口为主，银发健康科技平台保留为远期愿景或融资叙事。",
      needs_human_review: true,
    });
  }

  const financialClaims = byTheme.store_financial_model ?? [];
  const hasFastPayback = financialClaims.filter((claim) => /8个月|8\s*个月|回本周期8/u.test(claim.claim));
  const hasLongerPayback = financialClaims.filter((claim) => /10.*14个月|14个月|10-14/u.test(claim.claim));
  for (const fast of hasFastPayback) {
    for (const longer of hasLongerPayback) {
      if (fast.claim_id === longer.claim_id) {
        continue;
      }
      conflicts.push({
        conflict_id: `hxy_conflict_finance_${fast.claim_id}_${longer.claim_id}`,
        conflict_type: "financial_assumption_conflict",
        primary_claim_id: fast.claim_id,
        conflicting_claim_id: longer.claim_id,
        reason: "回本周期存在 8 个月与 10-14 个月等不同假设，必须绑定具体店型、城市、房租和客流条件。",
        recommended_resolution: "保留为不同情景模型，不直接写成确定结论；样板店期用真实数据验证。",
        needs_human_review: true,
      });
    }
  }
  return dedupeConflicts(conflicts);
}

function pickRepresentativeClaim(claims: HxyKnowledgeClaim[], theme: HxyClaimTheme): HxyKnowledgeClaim | undefined {
  return claims.slice().sort((left, right) => scoreCandidate(right, theme) - scoreCandidate(left, theme))[0];
}

export function buildHxyKnowledgeGovernanceReport(claims: HxyKnowledgeClaim[]): HxyKnowledgeGovernanceReport {
  const byTheme = groupClaimsByTheme(claims);
  const themeGroups: Record<string, HxyThemeGroup> = {};
  for (const [theme, themeClaims] of Object.entries(byTheme)) {
    themeGroups[theme] = {
      theme: theme as HxyClaimTheme,
      claim_count: themeClaims.length,
      claim_ids: themeClaims.map((claim) => claim.claim_id),
      representative_claims: themeClaims
        .slice()
        .sort((left, right) => right.confidence - left.confidence || right.claim.length - left.claim.length)
        .slice(0, 5)
        .map((claim) => claim.claim),
    };
  }
  const conflicts = detectHxyClaimConflicts(claims);
  const recommendedCurrentCandidates = recommendCurrentCandidates(claims, byTheme);
  const reviewQueue = [
    ...recommendedCurrentCandidates.map((candidate) => ({
      review_type: "confirm_current" as const,
      claim_id: candidate.claim_id,
      reason: `确认 ${candidate.theme} 是否作为当前有效候选：${candidate.reason}`,
    })),
    ...conflicts.map((conflict) => ({
      review_type: "resolve_conflict" as const,
      conflict_id: conflict.conflict_id,
      reason: conflict.reason,
    })),
    ...claims
      .filter((claim) => claim.needs_validation)
      .slice(0, 50)
      .map((claim) => ({
        review_type: "validate_assumption" as const,
        claim_id: claim.claim_id,
        reason: "该 claim 涉及产品、店型或财务假设，需要样板店真实数据验证。",
      })),
  ];
  return {
    version: "hxy-knowledge-governance.v1",
    generated_at: new Date().toISOString(),
    summary: {
      claim_count: claims.length,
      theme_count: Object.keys(themeGroups).length,
      conflict_count: conflicts.length,
      recommended_current_candidate_count: recommendedCurrentCandidates.length,
      needs_human_review_count: reviewQueue.length,
    },
    theme_groups: themeGroups,
    recommended_current_candidates: recommendedCurrentCandidates,
    conflicts,
    review_queue: reviewQueue,
  };
}

function groupClaimsByTheme(claims: HxyKnowledgeClaim[]): Record<HxyClaimTheme, HxyKnowledgeClaim[]> {
  const grouped = {} as Record<HxyClaimTheme, HxyKnowledgeClaim[]>;
  for (const claim of claims) {
    const theme = classifyClaimThemeForGovernance(claim);
    grouped[theme] ??= [];
    grouped[theme].push(claim);
  }
  return grouped;
}

function classifyClaimThemeForGovernance(claim: HxyKnowledgeClaim): HxyClaimTheme {
  if (claim.claim_type === "product_service" && isProductPriceText(claim.claim)) {
    return "product_price_model";
  }
  if (
    (claim.claim_type === "store_model" || claim.claim_type === "financial_assumption") &&
    isStoreFinancialModelCandidate(claim.claim)
  ) {
    return "store_financial_model";
  }
  return classifyHxyClaimTheme(claim.claim);
}

function recommendCurrentCandidates(
  claims: HxyKnowledgeClaim[],
  byTheme: Record<HxyClaimTheme, HxyKnowledgeClaim[]>,
): HxyKnowledgeGovernanceReport["recommended_current_candidates"] {
  const priorityThemes: HxyClaimTheme[] = [
    "community_store_positioning",
    "brand_asset_expression",
    "product_price_model",
    "store_financial_model",
    "customer_segment",
    "franchise_model",
    "data_ai_model",
  ];
  const candidates: HxyKnowledgeGovernanceReport["recommended_current_candidates"] = [];
  for (const theme of priorityThemes) {
    const scoredClaims = (byTheme[theme] ?? [])
      .slice()
      .filter((claim) => isEligibleCurrentCandidate(claim, theme))
      .map((claim) => ({ claim, score: scoreCandidate(claim, theme) }))
      .sort((left, right) => right.score - left.score);
    const selected = scoredClaims[0];
    if (!selected || selected.score < minimumCandidateScore(theme)) {
      continue;
    }
    const claim = selected.claim;
    if (!claim) {
      continue;
    }
    candidates.push({
      claim_id: claim.claim_id,
      claim_type: claim.claim_type,
      theme,
      claim: claim.claim,
      confidence: claim.confidence,
      reason: currentCandidateReason(theme),
    });
  }
  return dedupeCandidates(candidates);
}

function minimumCandidateScore(theme: HxyClaimTheme): number {
  if (theme === "franchise_model") {
    return 85;
  }
  return 60;
}

function isEligibleCurrentCandidate(claim: HxyKnowledgeClaim, theme: HxyClaimTheme): boolean {
  const text = claim.claim;
  const noise =
    /市场其他品牌调研|指标体系表|品牌数据填报页|竞品差异化矩阵|旗舰大店|优劣势|属性维度|IPO|C轮|上市|投前|收购方|平安集团|腾讯|阶段目标拆解|核心KPI|对赌协议|候选人画像|CMO|薪酬方案|基本月薪|绩效奖金|供应商Portal|税务申报|对账|发货确认|运营飞轮/u;
  if (noise.test(text)) {
    return false;
  }
  switch (theme) {
    case "community_store_positioning":
      return (
        (claim.claim_type === "brand_positioning" || claim.claim_type === "financial_assumption") &&
        !/不再定位为?[“"']?社区小店|重新定义为|智能化社区养生连锁第一品牌|社区健康数据网络/u.test(text) &&
        /社区.*(小店|泡脚|按摩|养生|信任|真好使)|泡脚按摩小店|社区小店|私域复购/u.test(text)
      );
    case "brand_asset_expression":
      return /Slogon|Slogan|口号|品牌名|草本真现煮|按出真功夫|功效看得见|品牌调性|吉祥物|超级符号/u.test(text);
    case "product_price_model":
      return (
        claim.claim_type === "product_service" &&
        isProductPriceText(text) &&
        /泡脚|按摩|药浴|手法|护理包|套餐|草本/u.test(text)
      );
    case "store_financial_model":
      return isStoreFinancialModelCandidate(text);
    case "customer_segment":
      return isCustomerSegmentCandidate(text);
    case "data_ai_model":
      return (
        /AI(诊断|智能|体质|交互)|健康档案|数据中台|小程序|个性化方案|自动生成调理方案/u.test(text) &&
        !/供应商|税务|对账|发货|企业客户|企业账户/u.test(text)
      );
    case "franchise_model":
      return /加盟|区域保护|加盟商|督导|培训体系/u.test(text);
    default:
      return true;
  }
}

function isStoreFinancialModelCandidate(text: string): boolean {
  if (/加盟|加盟商|区域保护|薪酬|月薪|绩效|期权|候选人|CMO|VP|总监|资金用途|品牌影响力|产品研发|投资回报与风险控制/u.test(text)) {
    return false;
  }
  const signalCount = [
    /单店|门店/u,
    /投资|投入/u,
    /营收|收入/u,
    /利润|毛利|净利|月净利润|EBITDA/u,
    /回本/u,
    /房租|成本/u,
    /面积|㎡|平米|床位/u,
  ].filter((pattern) => pattern.test(text)).length;
  return signalCount >= 3;
}

function isProductPriceText(text: string): boolean {
  const hasMenuRole = /主推款|招牌款|基础款|尊享款|入口款|加油款|引流价|高端款/u.test(text);
  const hasPrice = /价格|¥|(\d+|\d+\.\d+)\s*元/u.test(text);
  const hasDuration = /(\d+|\d+\.\d+)\s*(分钟|min)/u.test(text);
  const hasService = /泡脚|按摩|药浴|手法|护理包|泡脚包|草本/u.test(text);
  return (hasMenuRole && (hasPrice || hasDuration || hasService)) || (hasPrice && hasDuration && hasService);
}

function isCustomerSegmentCandidate(text: string): boolean {
  if (/AI\s*竞对|竞对工具|扫描商圈|低成本获客|精准定位高价值社区用户/u.test(text)) {
    return false;
  }
  const signalCount = [
    /客群|人群|用户|目标客群|目标用户|目标人群/u,
    /悦己|年轻|女性|职场|老人|中老年|社区家庭|家庭|银发/u,
    /3公里|社区|复购|高频|养生/u,
  ].filter((pattern) => pattern.test(text)).length;
  return signalCount >= 2;
}

function scoreCandidate(claim: HxyKnowledgeClaim, theme: HxyClaimTheme): number {
  let score = claim.confidence * 100 + conciseDecisionScore(claim.claim);
  if (claim.claim_type === claimTypePreferredForTheme(theme)) {
    score += 18;
  }
  if (theme === "community_store_positioning" && /社区|泡脚|按摩|小店|私域/u.test(claim.claim)) {
    score += 30;
    if (/当前主定位|主定位|真实有效|社区信任|价格不心疼|复购/u.test(claim.claim)) {
      score += 22;
    }
  }
  if (theme === "brand_asset_expression" && /草本真现煮|按出真功夫|Slogan|口号|IP/u.test(claim.claim)) {
    score += 25;
  }
  if (theme === "product_price_model") {
    score += productMenuStructureScore(claim.claim);
  }
  if (theme === "store_financial_model" && /投资|回本|50万|8个月|面积/u.test(claim.claim)) {
    score += 20;
  }
  if (theme === "store_financial_model" && /单店|店面面积|月营收|月净利润|目标回本周期|套餐设计/u.test(claim.claim)) {
    score += 18;
  }
  if (theme === "customer_segment" && /悦己|年轻|女性|职场|社区家庭|3公里|复购/u.test(claim.claim)) {
    score += 20;
  }
  if (/市场其他品牌调研|指标体系表|品牌数据填报页|排名|竞品差异化矩阵|旗舰大店|优劣势|属性维度/u.test(claim.claim)) {
    score -= 120;
  }
  if (/IPO|C轮|融资|估值|上市|投前/u.test(claim.claim)) {
    score -= 90;
  }
  if (/运营飞轮|国民品牌|核心驱动力|生命周期价值|生态叙事/u.test(claim.claim)) {
    score -= 70;
  }
  return score;
}

function conciseDecisionScore(text: string): number {
  const length = text.replace(/\s+/g, "").length;
  if (length <= 80) {
    return 22;
  }
  if (length <= 160) {
    return 12;
  }
  if (length <= 260) {
    return 0;
  }
  return -Math.min(Math.ceil((length - 260) / 5), 80);
}

function productMenuStructureScore(text: string): number {
  const tierCount = [/入口款|基础款|引流价/u, /主推款|招牌款/u, /加油款|尊享款|高端款|溢价款/u].filter((pattern) =>
    pattern.test(text),
  ).length;
  const priceCount = new Set(Array.from(text.matchAll(/(?:¥\s*\d+|\d+\s*元)/gu)).map((match) => match[0])).size;
  return tierCount * 20 + Math.min(priceCount, 3) * 8;
}

function claimTypePreferredForTheme(theme: HxyClaimTheme): string {
  const preferred: Record<HxyClaimTheme, string> = {
    community_store_positioning: "brand_positioning",
    silver_health_platform_positioning: "brand_positioning",
    wellness_chain_positioning: "brand_positioning",
    brand_asset_expression: "brand_asset",
    customer_segment: "customer_segment",
    product_price_model: "product_service",
    store_financial_model: "financial_assumption",
    franchise_model: "store_model",
    data_ai_model: "validation_metric",
    risk_or_constraint: "risk",
    other: "",
  };
  return preferred[theme];
}

function currentCandidateReason(theme: HxyClaimTheme): string {
  const reasons: Record<HxyClaimTheme, string> = {
    community_store_positioning: "筹备期和样板店期需要先收敛到可落地的小店定位。",
    silver_health_platform_positioning: "更适合作为远期愿景，不建议直接作为当前主定位。",
    wellness_chain_positioning: "适合作为品牌大方向，需要与小店模型绑定。",
    brand_asset_expression: "品牌资产需要统一口号、IP 和终端表达。",
    customer_segment: "客群定义会影响产品、价格、选址和传播。",
    product_price_model: "产品价格模型直接影响单店利润和复购。",
    store_financial_model: "财务模型必须成为样板店验证主线。",
    franchise_model: "加盟模式决定复制质量和风险。",
    data_ai_model: "AI/Data 能力应服务经营验证，不宜先做平台叙事。",
    risk_or_constraint: "风险需要进入人工复核和行动闭环。",
    other: "需要人工判断是否保留。",
  };
  return reasons[theme];
}

function dedupeCandidates(
  candidates: HxyKnowledgeGovernanceReport["recommended_current_candidates"],
): HxyKnowledgeGovernanceReport["recommended_current_candidates"] {
  const seen = new Set<string>();
  return candidates.filter((candidate) => {
    if (seen.has(candidate.claim_id)) {
      return false;
    }
    seen.add(candidate.claim_id);
    return true;
  });
}

function dedupeConflicts(conflicts: HxyClaimConflict[]): HxyClaimConflict[] {
  const seen = new Set<string>();
  return conflicts.filter((conflict) => {
    const pair = [conflict.primary_claim_id, conflict.conflicting_claim_id].sort().join(":");
    const key = `${conflict.conflict_type}:${pair}`;
    if (seen.has(key)) {
      return false;
    }
    seen.add(key);
    return true;
  });
}

export async function readHxyClaims(claimsPath: string): Promise<HxyKnowledgeClaim[]> {
  return JSON.parse(await fs.readFile(claimsPath, "utf8")) as HxyKnowledgeClaim[];
}

export async function writeHxyKnowledgeGovernanceReport(
  report: HxyKnowledgeGovernanceReport,
  outputDir: string,
): Promise<void> {
  await fs.mkdir(outputDir, { recursive: true });
  await fs.writeFile(path.join(outputDir, "governance-report.json"), `${JSON.stringify(report, null, 2)}\n`, "utf8");
}
