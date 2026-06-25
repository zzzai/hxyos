import { createHash, randomUUID } from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";
import type { HxyMemoryStore } from "./store.js";
import type {
  HxyMemoryEvidenceLink,
  HxyMemoryItem,
  HxyMemoryStatus,
  HxyMemoryType,
} from "./types.js";

const MEMORY_VERSION = "hxy-memory.v1";

type ImportStore = Pick<
  HxyMemoryStore,
  "initialize" | "upsertMemoryItem" | "upsertEvidenceLinks" | "recordImportRun"
>;

export type HxyMemoryImportBuildResult = {
  items: HxyMemoryItem[];
  evidenceLinks: HxyMemoryEvidenceLink[];
  skippedFiles: string[];
};

export type HxyMemoryImportResult = HxyMemoryImportBuildResult & {
  importId: string;
};

function sha1(value: string): string {
  return createHash("sha1").update(value).digest("hex");
}

async function readJsonIfExists(filePath: string): Promise<unknown | undefined> {
  try {
    return JSON.parse(await fs.readFile(filePath, "utf8")) as unknown;
  } catch (error) {
    const code = typeof error === "object" && error ? (error as { code?: unknown }).code : undefined;
    if (code === "ENOENT") {
      return undefined;
    }
    throw error;
  }
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function asRecordArray(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value)
    ? value.filter((entry): entry is Record<string, unknown> => Boolean(entry) && typeof entry === "object" && !Array.isArray(entry))
    : [];
}

function asString(value: unknown): string | undefined {
  return typeof value === "string" && value.trim().length > 0 ? value.trim() : undefined;
}

function asNumber(value: unknown): number | undefined {
  const numeric = typeof value === "number" ? value : typeof value === "string" ? Number(value) : NaN;
  return Number.isFinite(numeric) ? numeric : undefined;
}

function normalizeStatus(value: unknown, fallback: HxyMemoryStatus): HxyMemoryStatus {
  switch (value) {
    case "draft":
    case "current_candidate":
    case "confirmed":
    case "validated":
    case "deprecated":
    case "conflicted":
    case "needs_review":
    case "open":
    case "closed":
      return value;
    default:
      return fallback;
  }
}

function stableObjectId(prefix: string, payload: Record<string, unknown>, preferredKeys: string[]): string {
  for (const key of preferredKeys) {
    const value = asString(payload[key]);
    if (value) {
      return value;
    }
  }
  return `${prefix}_${sha1(JSON.stringify(payload)).slice(0, 16)}`;
}

function buildMemoryItem(params: {
  memoryId: string;
  memoryType: HxyMemoryType;
  title: string;
  body: string;
  projectStage?: string;
  status: HxyMemoryStatus;
  confidence?: number;
  sourceKind: string;
  sourcePath: string;
  sourceObjectId?: string;
  payload: Record<string, unknown>;
  nowIso: string;
}): HxyMemoryItem {
  return {
    memoryId: params.memoryId,
    memoryType: params.memoryType,
    title: params.title,
    body: params.body,
    projectStage: params.projectStage,
    status: params.status,
    confidence: params.confidence,
    version: MEMORY_VERSION,
    sourceKind: params.sourceKind,
    sourcePath: params.sourcePath,
    sourceObjectId: params.sourceObjectId,
    payload: params.payload,
    createdAt: params.nowIso,
    updatedAt: params.nowIso,
  };
}

function pushEvidenceLinks(params: {
  links: HxyMemoryEvidenceLink[];
  memoryId: string;
  evidenceIds?: unknown;
  evidence?: unknown;
}): void {
  const evidenceRows = asRecordArray(params.evidence);
  const byId = new Map(evidenceRows.map((row) => [asString(row.evidence_id), row]));
  const ids = Array.isArray(params.evidenceIds)
    ? params.evidenceIds.filter((entry): entry is string => typeof entry === "string" && entry.trim().length > 0)
    : [];
  for (const evidenceId of ids) {
    const row = byId.get(evidenceId);
    params.links.push({
      memoryId: params.memoryId,
      evidenceId,
      sourcePath: asString(row?.relative_path),
      snippet: asString(row?.snippet),
      payload: row ?? {},
    });
  }
}

function importClaims(params: {
  claims: Record<string, unknown>[];
  nowIso: string;
  items: HxyMemoryItem[];
  links: HxyMemoryEvidenceLink[];
}): void {
  for (const claim of params.claims) {
    const claimId = stableObjectId("claim", claim, ["claim_id"]);
    const title = asString(claim.claim_type) ?? "HXY claim";
    const body = asString(claim.claim) ?? title;
    const memoryId = `hxy:claim:${claimId}`;
    params.items.push(
      buildMemoryItem({
        memoryId,
        memoryType: "claim",
        title,
        body,
        projectStage: asString(claim.stage),
        status: normalizeStatus(claim.status, "needs_review"),
        confidence: asNumber(claim.confidence),
        sourceKind: "claims",
        sourcePath: "knowledge/hxy/structured/claims.json",
        sourceObjectId: claimId,
        payload: claim,
        nowIso: params.nowIso,
      }),
    );
    pushEvidenceLinks({
      links: params.links,
      memoryId,
      evidenceIds: claim.evidence_ids,
    });
    if (claim.needs_validation === true) {
      const hypothesisId = `hxy:hypothesis:${claimId}`;
      params.items.push(
        buildMemoryItem({
          memoryId: hypothesisId,
          memoryType: "hypothesis",
          title: `验证假设：${title}`,
          body,
          projectStage: asString(claim.stage),
          status: normalizeStatus(claim.status, "current_candidate"),
          confidence: asNumber(claim.confidence),
          sourceKind: "claims",
          sourcePath: "knowledge/hxy/structured/claims.json",
          sourceObjectId: claimId,
          payload: {
            ...claim,
            derived_from_memory_id: memoryId,
            derivation: "claim.needs_validation",
          },
          nowIso: params.nowIso,
        }),
      );
      pushEvidenceLinks({
        links: params.links,
        memoryId: hypothesisId,
        evidenceIds: claim.evidence_ids,
      });
    }
  }
}

function importDecisions(params: {
  decisions: Record<string, unknown>[];
  nowIso: string;
  items: HxyMemoryItem[];
  links: HxyMemoryEvidenceLink[];
}): void {
  for (const decision of params.decisions) {
    const decisionId = stableObjectId("decision", decision, ["decision_id"]);
    const title = asString(decision.title) ?? asString(decision.decision_key) ?? "HXY decision";
    const body = asString(decision.decision) ?? title;
    const memoryId = `hxy:decision:${decisionId}`;
    params.items.push(
      buildMemoryItem({
        memoryId,
        memoryType: "decision",
        title,
        body,
        projectStage: asString(decision.project_stage),
        status: normalizeStatus(decision.status, "current_candidate"),
        confidence: asNumber(decision.confidence),
        sourceKind: "decision-log",
        sourcePath: "knowledge/hxy/structured/decision-log.json",
        sourceObjectId: decisionId,
        payload: decision,
        nowIso: params.nowIso,
      }),
    );
    pushEvidenceLinks({
      links: params.links,
      memoryId,
      evidenceIds: decision.evidence_ids,
      evidence: decision.evidence,
    });
  }
}

function importGovernance(params: {
  governance: Record<string, unknown>;
  nowIso: string;
  items: HxyMemoryItem[];
}): void {
  for (const review of asRecordArray(params.governance.review_queue)) {
    const reviewType = asString(review.review_type) ?? "review";
    const claimId = asString(review.claim_id) ?? sha1(JSON.stringify(review)).slice(0, 16);
    params.items.push(
      buildMemoryItem({
        memoryId: `hxy:review_task:${reviewType}:${claimId}`,
        memoryType: "review_task",
        title: `复核：${reviewType}`,
        body: asString(review.reason) ?? "HXY memory review task",
        status: "open",
        sourceKind: "governance-report",
        sourcePath: "knowledge/hxy/structured/governance-report.json",
        sourceObjectId: `${reviewType}:${claimId}`,
        payload: review,
        nowIso: params.nowIso,
      }),
    );
  }
  for (const conflict of asRecordArray(params.governance.conflicts)) {
    const conflictId = stableObjectId("conflict", conflict, ["conflict_id"]);
    params.items.push(
      buildMemoryItem({
        memoryId: `hxy:conflict:${conflictId}`,
        memoryType: "conflict",
        title: `冲突：${asString(conflict.severity) ?? "needs_review"}`,
        body: asString(conflict.reason) ?? asString(conflict.recommended_resolution) ?? "HXY memory conflict",
        status: "conflicted",
        sourceKind: "governance-report",
        sourcePath: "knowledge/hxy/structured/governance-report.json",
        sourceObjectId: conflictId,
        payload: conflict,
        nowIso: params.nowIso,
      }),
    );
  }
}

function importPilotValidation(params: {
  matrix: Record<string, unknown>;
  nowIso: string;
  items: HxyMemoryItem[];
}): void {
  for (const item of asRecordArray(params.matrix.items)) {
    const itemId = stableObjectId("validation", item, ["item_id", "id", "metric"]);
    params.items.push(
      buildMemoryItem({
        memoryId: `hxy:validation_task:${itemId}`,
        memoryType: "validation_task",
        title: asString(item.title) ?? asString(item.metric) ?? "样板验证项",
        body: asString(item.method) ?? asString(item.target) ?? "HXY pilot validation task",
        status: "open",
        sourceKind: "pilot-validation-matrix",
        sourcePath: "knowledge/hxy/structured/pilot-validation-matrix.json",
        sourceObjectId: itemId,
        payload: item,
        nowIso: params.nowIso,
      }),
    );
  }
}

function importOsiOpenReviewItems(params: {
  osi: Record<string, unknown>;
  nowIso: string;
  items: HxyMemoryItem[];
}): void {
  const governance = asRecord(params.osi.governance);
  for (const review of asRecordArray(governance.open_review_items)) {
    const conflictId = stableObjectId("osi_conflict", review, ["conflict_id"]);
    params.items.push(
      buildMemoryItem({
        memoryId: `hxy:conflict:${conflictId}`,
        memoryType: "conflict",
        title: `OSI 复核：${asString(review.severity) ?? "needs_review"}`,
        body: asString(review.reason) ?? asString(review.recommended_resolution) ?? "HXY OSI open review item",
        status: "conflicted",
        sourceKind: "osi-contract",
        sourcePath: "knowledge/hxy/structured/osi-contract.json",
        sourceObjectId: conflictId,
        payload: review,
        nowIso: params.nowIso,
      }),
    );
  }
}

export async function buildHxyMemoryImportItemsFromStructuredDir(params: {
  structuredDir: string;
  now?: () => Date;
}): Promise<HxyMemoryImportBuildResult> {
  const nowIso = (params.now ?? (() => new Date()))().toISOString();
  const items: HxyMemoryItem[] = [];
  const evidenceLinks: HxyMemoryEvidenceLink[] = [];
  const skippedFiles: string[] = [];

  const claims = await readJsonIfExists(path.join(params.structuredDir, "claims.json"));
  if (claims === undefined) {
    skippedFiles.push("claims.json");
  } else {
    importClaims({ claims: asRecordArray(claims), nowIso, items, links: evidenceLinks });
  }

  const decisionLog = asRecord(await readJsonIfExists(path.join(params.structuredDir, "decision-log.json")));
  if (Object.keys(decisionLog).length === 0) {
    skippedFiles.push("decision-log.json");
  } else {
    importDecisions({
      decisions: asRecordArray(decisionLog.decisions),
      nowIso,
      items,
      links: evidenceLinks,
    });
  }

  const governance = asRecord(await readJsonIfExists(path.join(params.structuredDir, "governance-report.json")));
  if (Object.keys(governance).length === 0) {
    skippedFiles.push("governance-report.json");
  } else {
    importGovernance({ governance, nowIso, items });
  }

  const matrix = asRecord(await readJsonIfExists(path.join(params.structuredDir, "pilot-validation-matrix.json")));
  if (Object.keys(matrix).length === 0) {
    skippedFiles.push("pilot-validation-matrix.json");
  } else {
    importPilotValidation({ matrix, nowIso, items });
  }

  const osi = asRecord(await readJsonIfExists(path.join(params.structuredDir, "osi-contract.json")));
  if (Object.keys(osi).length === 0) {
    skippedFiles.push("osi-contract.json");
  } else {
    importOsiOpenReviewItems({ osi, nowIso, items });
  }

  return { items, evidenceLinks, skippedFiles };
}

export async function importHxyMemoryFromStructuredDir(params: {
  store: ImportStore;
  structuredDir: string;
  importId?: string;
  now?: () => Date;
}): Promise<HxyMemoryImportResult> {
  const now = params.now ?? (() => new Date());
  const startedAt = now().toISOString();
  const importId = params.importId ?? `hxy-memory-import-${randomUUID()}`;
  await params.store.initialize();
  const built = await buildHxyMemoryImportItemsFromStructuredDir({
    structuredDir: params.structuredDir,
    now,
  });
  for (const item of built.items) {
    await params.store.upsertMemoryItem(item);
    const links = built.evidenceLinks.filter((link) => link.memoryId === item.memoryId);
    if (links.length > 0) {
      await params.store.upsertEvidenceLinks(item.memoryId, links);
    }
  }
  await params.store.recordImportRun({
    importId,
    sourceDir: params.structuredDir,
    startedAt,
    finishedAt: now().toISOString(),
    status: "completed",
    itemCount: built.items.length,
    payload: {
      skipped_files: built.skippedFiles,
      evidence_link_count: built.evidenceLinks.length,
    },
  });
  return { ...built, importId };
}
