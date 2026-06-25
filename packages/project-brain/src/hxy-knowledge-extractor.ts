import { createHash } from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";

export type HxyKnowledgeChunk = {
  chunkId?: string;
  sourceId: string;
  domain: string;
  title: string;
  relativePath: string;
  chunkIndex: number;
  text: string;
  keywords?: string[];
};

export type HxyKnowledgeIndex = {
  version: string;
  generatedAt: string;
  rootDir: string;
  rawDir: string;
  domains: string[];
  sources: Array<{
    sourceId: string;
    domain: string;
    title: string;
    relativePath: string;
    fileName: string;
    fileSize: number;
    updatedAt: string;
  }>;
  chunks: HxyKnowledgeChunk[];
  skippedFiles: unknown[];
};

export type HxyClaimType =
  | "brand_positioning"
  | "customer_segment"
  | "pain_point"
  | "product_service"
  | "store_model"
  | "financial_assumption"
  | "brand_asset"
  | "purchase_reason"
  | "super_symbol"
  | "risk"
  | "action_recipe"
  | "validation_metric";

export type HxyKnowledgeClaim = {
  claim_id: string;
  claim_type: HxyClaimType;
  claim: string;
  stage: "preparation";
  status: "current_candidate";
  confidence: number;
  evidence_ids: string[];
  conflict_claim_ids: string[];
  needs_validation: boolean;
};

export type HxyEntity = {
  entity_id: string;
  entity_type: string;
  name: string;
  claim_ids: string[];
};

export type HxyEvidence = {
  evidence_id: string;
  source_id: string;
  title: string;
  relative_path: string;
  chunk_index: number;
  snippet: string;
};

export type HxyRelation = {
  relation_id: string;
  relation_type: "supports";
  from_id: string;
  to_id: string;
};

export type HxyStructuredKnowledge = {
  version: "hxy-structured-knowledge.v1";
  generated_at: string;
  source_index_generated_at: string;
  assets: HxyKnowledgeIndex["sources"];
  claims: HxyKnowledgeClaim[];
  entities: HxyEntity[];
  evidence: HxyEvidence[];
  relations: HxyRelation[];
  summary: {
    asset_count: number;
    claim_count: number;
    entity_count: number;
    evidence_count: number;
    relation_count: number;
  };
};

function sha1(value: string): string {
  return createHash("sha1").update(value).digest("hex");
}

function normalizeWhitespace(value: string): string {
  return value.replace(/\s+/gu, " ").trim();
}

function firstMatchingSentence(text: string, patterns: RegExp[]): string {
  const sentences = normalizeWhitespace(text)
    .split(/(?<=[。！？；;])|\s{2,}/u)
    .map((sentence) => sentence.trim())
    .filter(Boolean);
  for (const pattern of patterns) {
    const matched = sentences.find((sentence) => pattern.test(sentence));
    if (matched) {
      return matched;
    }
  }
  return "";
}

function makeEvidenceId(chunk: HxyKnowledgeChunk): string {
  const sourceChunk = `${chunk.sourceId}:${chunk.chunkIndex}`;
  return `hxy_evidence_${sourceChunk}_${sha1(sourceChunk).slice(0, 12)}`;
}

function makeClaim(chunk: HxyKnowledgeChunk, claimType: HxyClaimType, claim: string, confidence = 0.72): HxyKnowledgeClaim {
  return {
    claim_id: `hxy_claim_${claimType}_${sha1(`${chunk.sourceId}:${chunk.chunkIndex}:${claimType}:${claim}`).slice(0, 16)}`,
    claim_type: claimType,
    claim,
    stage: "preparation",
    status: "current_candidate",
    confidence,
    evidence_ids: [makeEvidenceId(chunk)],
    conflict_claim_ids: [],
    needs_validation: ["financial_assumption", "store_model", "product_service"].includes(claimType),
  };
}

export function extractHxyClaimsFromChunk(chunk: HxyKnowledgeChunk): HxyKnowledgeClaim[] {
  const text = normalizeWhitespace(chunk.text);
  if (!text || chunk.domain !== "hxy") {
    return [];
  }
  if (!hasHxyProjectContext(text)) {
    return [];
  }
  const claims: HxyKnowledgeClaim[] = [];

  const positioning = firstMatchingSentence(text, [
    /定位.*(社区|泡脚|按摩|养生|健康|小店)/u,
    /(社区|泡脚|按摩|养生|健康).*定位/u,
    /荷小悦.*(社区|泡脚|按摩|养生|健康).*品牌/u,
  ]);
  if (positioning) {
    claims.push(makeClaim(chunk, "brand_positioning", positioning, 0.78));
  }

  const segment = firstMatchingSentence(text, [
    /(客群|用户|人群|目标).*?(女性|年轻|社区|家庭|银发|老人|悦己)/u,
    /(女性|年轻|社区|家庭|银发|老人|悦己).*?(客群|用户|人群)/u,
  ]);
  if (segment) {
    claims.push(makeClaim(chunk, "customer_segment", segment, 0.72));
  }

  const painPoint = firstMatchingSentence(text, [
    /(痛点|疲劳|酸痛|睡不好|亚健康|焦虑|孤独|信任|踩坑)/u,
  ]);
  if (painPoint) {
    claims.push(makeClaim(chunk, "pain_point", painPoint, 0.66));
  }

  const product = firstMatchingSentence(text, [
    /(泡脚|按摩|草本|护理包|精油|药包|套餐|SKU|SPU|服务项目)/u,
  ]);
  if (product) {
    claims.push(makeClaim(chunk, "product_service", product, 0.74));
  }

  const storeModel = firstMatchingSentence(text, [
    /(店面面积|面积|社区小店|小店模型|单店|加盟门槛|区域保护|技师)/u,
  ]);
  if (storeModel) {
    claims.push(makeClaim(chunk, "store_model", storeModel, 0.74));
  }

  const financial = firstMatchingSentence(text, [
    /(投资|回本|利润|营收|客单|现金流|毛利|净利|元|万元)/u,
  ]);
  if (financial) {
    claims.push(makeClaim(chunk, "financial_assumption", financial, 0.7));
  }

  const brandAsset = firstMatchingSentence(text, [
    /(Slogan|slogan|口号|IP|超级符号|品牌承诺|品牌名|草本真现煮|按出真功夫)/u,
  ]);
  if (brandAsset) {
    claims.push(makeClaim(chunk, "brand_asset", brandAsset, 0.76));
  }

  const purchaseReason = firstMatchingSentence(text, [
    /(购买理由|价格不心疼|真管用|有效|高质平价|极致性价比|功效)/u,
  ]);
  if (purchaseReason) {
    claims.push(makeClaim(chunk, "purchase_reason", purchaseReason, 0.7));
  }

  const risk = firstMatchingSentence(text, [
    /(风险|不足|问题|挑战|瓶颈|缺乏|不足|变形|难以|排斥)/u,
  ]);
  if (risk) {
    claims.push(makeClaim(chunk, "risk", risk, 0.64));
  }

  return dedupeClaims(claims);
}

function hasHxyProjectContext(text: string): boolean {
  const mentionsHxy = /荷小悦/u.test(text);
  if (!mentionsHxy) {
    return false;
  }
  if (isCompetitorResearchTable(text)) {
    return false;
  }
  const competitorOnlySignals = [
    "奈晚推拿",
    "长风拨筋",
    "谷小推",
    "郑远元",
    "LANN",
    "蘭泰式",
    "推小艾",
    "足康树",
    "小理家",
    "排名",
    "品牌名称",
  ].filter((term) => text.includes(term)).length;
  const hxyProjectSignals = [
    "荷小悦定位",
    "品牌名： 荷小悦",
    "荷小悦 泡脚",
    "草本真现煮",
    "按出真功夫",
    "社区小店",
    "小店模型",
    "项目概览",
    "商业计划书",
    "品牌策划",
    "AI交互小程序",
    "O2O",
  ].filter((term) => text.includes(term)).length;
  if (competitorOnlySignals >= 3 && hxyProjectSignals === 0) {
    return false;
  }
  return hxyProjectSignals > 0 || /荷小悦.*(定位|客群|产品|服务|投资|回本|品牌|口号|IP|加盟|门店)/u.test(text);
}

function isCompetitorResearchTable(text: string): boolean {
  const tableSignals = [
    "市场其他品牌调研",
    "指标体系表",
    "品牌数据填报页",
    "评分排名",
    "核心评估指标",
    "品牌名称",
  ].filter((term) => text.includes(term)).length;
  const hxySelfSignals = [
    "荷小悦-新小店模型",
    "品牌名： 荷小悦",
    "Slogon",
    "草本真现煮",
    "按出真功夫",
    "项目概览",
    "荷小悦 HE XIAO YUE",
  ].filter((term) => text.includes(term)).length;
  return tableSignals >= 2 && hxySelfSignals === 0;
}

function dedupeClaims(claims: HxyKnowledgeClaim[]): HxyKnowledgeClaim[] {
  const seen = new Set<string>();
  return claims.filter((claim) => {
    const key = `${claim.claim_type}:${claim.claim}`;
    if (seen.has(key)) {
      return false;
    }
    seen.add(key);
    return true;
  });
}

function entityTypeForClaim(claimType: HxyClaimType): string {
  const mapping: Record<HxyClaimType, string> = {
    brand_positioning: "BrandPositioning",
    customer_segment: "CustomerSegment",
    pain_point: "PainPoint",
    product_service: "ProductService",
    store_model: "StoreModel",
    financial_assumption: "FinancialAssumption",
    brand_asset: "BrandAsset",
    purchase_reason: "PurchaseReason",
    super_symbol: "SuperSymbol",
    risk: "Risk",
    action_recipe: "ActionRecipe",
    validation_metric: "ValidationMetric",
  };
  return mapping[claimType];
}

function entityNameForClaim(claim: HxyKnowledgeClaim): string {
  const prefix: Record<HxyClaimType, string> = {
    brand_positioning: "品牌定位",
    customer_segment: "客群",
    pain_point: "痛点",
    product_service: "产品服务",
    store_model: "门店模型",
    financial_assumption: "财务假设",
    brand_asset: "品牌资产",
    purchase_reason: "购买理由",
    super_symbol: "超级符号",
    risk: "风险",
    action_recipe: "行动方案",
    validation_metric: "验证指标",
  };
  return `${prefix[claim.claim_type]}：${claim.claim.slice(0, 40)}`;
}

export function buildHxyStructuredKnowledge(index: HxyKnowledgeIndex): HxyStructuredKnowledge {
  const evidenceById = new Map<string, HxyEvidence>();
  const claims: HxyKnowledgeClaim[] = [];
  const entities: HxyEntity[] = [];
  const relations: HxyRelation[] = [];

  for (const chunk of index.chunks) {
    const chunkClaims = extractHxyClaimsFromChunk(chunk);
    if (chunkClaims.length === 0) {
      continue;
    }
    const evidenceId = makeEvidenceId(chunk);
    if (!evidenceById.has(evidenceId)) {
      evidenceById.set(evidenceId, {
        evidence_id: evidenceId,
        source_id: chunk.sourceId,
        title: chunk.title,
        relative_path: chunk.relativePath,
        chunk_index: chunk.chunkIndex,
        snippet: normalizeWhitespace(chunk.text).slice(0, 360),
      });
    }
    for (const claim of chunkClaims) {
      claims.push(claim);
      const entityId = `hxy_entity_${entityTypeForClaim(claim.claim_type)}_${sha1(claim.claim).slice(0, 16)}`;
      entities.push({
        entity_id: entityId,
        entity_type: entityTypeForClaim(claim.claim_type),
        name: entityNameForClaim(claim),
        claim_ids: [claim.claim_id],
      });
      relations.push({
        relation_id: `hxy_relation_supports_${sha1(`${evidenceId}:${claim.claim_id}`).slice(0, 16)}`,
        relation_type: "supports",
        from_id: evidenceId,
        to_id: claim.claim_id,
      });
    }
  }

  const output: HxyStructuredKnowledge = {
    version: "hxy-structured-knowledge.v1",
    generated_at: new Date().toISOString(),
    source_index_generated_at: index.generatedAt,
    assets: index.sources,
    claims: dedupeClaimsById(claims),
    entities: dedupeEntities(entities),
    evidence: Array.from(evidenceById.values()),
    relations: dedupeRelations(relations),
    summary: {
      asset_count: index.sources.length,
      claim_count: 0,
      entity_count: 0,
      evidence_count: 0,
      relation_count: 0,
    },
  };
  output.summary.claim_count = output.claims.length;
  output.summary.entity_count = output.entities.length;
  output.summary.evidence_count = output.evidence.length;
  output.summary.relation_count = output.relations.length;
  return output;
}

function dedupeClaimsById(claims: HxyKnowledgeClaim[]): HxyKnowledgeClaim[] {
  const seen = new Set<string>();
  return claims.filter((claim) => {
    if (seen.has(claim.claim_id)) {
      return false;
    }
    seen.add(claim.claim_id);
    return true;
  });
}

function dedupeEntities(entities: HxyEntity[]): HxyEntity[] {
  const byId = new Map<string, HxyEntity>();
  for (const entity of entities) {
    const existing = byId.get(entity.entity_id);
    if (!existing) {
      byId.set(entity.entity_id, entity);
      continue;
    }
    existing.claim_ids = Array.from(new Set([...existing.claim_ids, ...entity.claim_ids]));
  }
  return Array.from(byId.values());
}

function dedupeRelations(relations: HxyRelation[]): HxyRelation[] {
  const seen = new Set<string>();
  return relations.filter((relation) => {
    if (seen.has(relation.relation_id)) {
      return false;
    }
    seen.add(relation.relation_id);
    return true;
  });
}

export async function readHxyKnowledgeIndex(indexPath: string): Promise<HxyKnowledgeIndex> {
  return JSON.parse(await fs.readFile(indexPath, "utf8")) as HxyKnowledgeIndex;
}

export async function writeHxyStructuredKnowledge(output: HxyStructuredKnowledge, outputDir: string): Promise<void> {
  await fs.mkdir(outputDir, { recursive: true });
  await Promise.all([
    fs.writeFile(path.join(outputDir, "structured-knowledge.json"), `${JSON.stringify(output, null, 2)}\n`, "utf8"),
    fs.writeFile(path.join(outputDir, "claims.json"), `${JSON.stringify(output.claims, null, 2)}\n`, "utf8"),
    fs.writeFile(path.join(outputDir, "entities.json"), `${JSON.stringify(output.entities, null, 2)}\n`, "utf8"),
    fs.writeFile(path.join(outputDir, "evidence.json"), `${JSON.stringify(output.evidence, null, 2)}\n`, "utf8"),
    fs.writeFile(path.join(outputDir, "relations.json"), `${JSON.stringify(output.relations, null, 2)}\n`, "utf8"),
  ]);
}
