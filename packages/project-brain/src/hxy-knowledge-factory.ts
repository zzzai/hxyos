import fs from "node:fs/promises";
import path from "node:path";
import {
  classifyHxyKnowledgeAsset,
  HXY_KNOWLEDGE_DOMAINS,
  HXY_PROJECT_STAGES,
  type HxyKnowledgeTaxonomyOverride,
  type HxyKnowledgeDomainKey,
  type HxyProjectStageKey,
} from "./hxy-knowledge-taxonomy.js";
import {
  buildPersonalKnowledgeIndex,
  chunkPersonalKnowledgeText,
  normalizePersonalKnowledgeTitle,
  isSupportedPersonalKnowledgeSource,
  type PersonalKnowledgeIndex,
  type PersonalKnowledgeSource,
  type PersonalKnowledgeSourceText,
} from "./personal-knowledge.js";

export type HxyKnowledgeAssetStatus =
  | "staged"
  | "normalized"
  | "indexed"
  | "structured"
  | "skipped"
  | "failed"
  | "needs_review";

export type HxyKnowledgeManifestAsset = {
  assetId: string;
  sourceId?: string;
  fileName: string;
  relativePath: string;
  normalizedPath?: string;
  sha1?: string;
  fileSize: number;
  updatedAt: string;
  contentType: string;
  parser?: string;
  parserWarnings?: string[];
  knowledgeDomain: HxyKnowledgeDomainKey | "external";
  secondaryKnowledgeDomains: string[];
  projectStage: HxyProjectStageKey | "evergreen";
  classificationConfidence: number;
  classificationReasons: string[];
  status: HxyKnowledgeAssetStatus;
  chunkCount: number;
  warnings: string[];
};

export type HxyKnowledgeManifest = {
  version: "hxy-knowledge-manifest.v1";
  generatedAt: string;
  rawDir: string;
  normalizedDir: string;
  assets: HxyKnowledgeManifestAsset[];
};

export type HxyKnowledgeDoctorReport = {
  version: "hxy-knowledge-doctor.v1";
  generatedAt: string;
  summary: {
    total_asset_count: number;
    indexed_asset_count: number;
    skipped_asset_count: number;
    failed_asset_count: number;
    low_confidence_asset_count: number;
    duplicate_asset_count: number;
  };
  coverage: Record<string, Record<string, number>>;
  issues: Array<{
    fileName: string;
    relativePath: string;
    status: HxyKnowledgeAssetStatus;
    warnings: string[];
  }>;
  impacts: string[];
};

export type HxyKnowledgeFactoryOutput = {
  taxonomy: {
    version: "hxy-knowledge-taxonomy.v1";
    domains: typeof HXY_KNOWLEDGE_DOMAINS;
    stages: typeof HXY_PROJECT_STAGES;
  };
  manifest: HxyKnowledgeManifest;
  index: PersonalKnowledgeIndex;
  doctor: HxyKnowledgeDoctorReport;
  normalizedFiles: Array<{
    relativePath: string;
    text: string;
  }>;
};

type HxyVisionSidecar = {
  asset_type?: string;
  knowledge_domain?: HxyKnowledgeDomainKey;
  project_stage?: HxyProjectStageKey;
  observations?: string[];
  brand_elements?: string[];
  price_signals?: string[];
  service_signals?: string[];
  evidence_text?: string[];
  confidence?: number;
};

async function collectFiles(rawDir: string): Promise<string[]> {
  const files: string[] = [];
  async function visit(directory: string): Promise<void> {
    const entries = await fs.readdir(directory, { withFileTypes: true });
    for (const entry of entries.sort((left, right) => left.name.localeCompare(right.name, "zh-Hans-CN"))) {
      const absolutePath = path.join(directory, entry.name);
      if (entry.isDirectory()) {
        await visit(absolutePath);
        continue;
      }
      if (entry.isFile() || entry.isSymbolicLink()) {
        files.push(absolutePath);
      }
    }
  }
  await visit(rawDir);
  return files;
}

function extensionToContentType(fileName: string): string {
  const extension = path.extname(fileName).toLowerCase().replace(/^\./u, "");
  return extension || "unknown";
}

function sanitizePathSegment(value: string): string {
  return value
    .replace(/[\\/:*?"<>|]+/gu, "-")
    .replace(/\s+/gu, "-")
    .replace(/-+/gu, "-")
    .replace(/^-|-$/gu, "")
    .slice(0, 120);
}

function normalizedRelativePath(params: {
  title: string;
  assetId: string;
  knowledgeDomain: string;
  projectStage: string;
}): string {
  return path
    .join(
      "knowledge",
      "hxy",
      "normalized",
      params.knowledgeDomain,
      params.projectStage,
      `${sanitizePathSegment(params.title) || params.assetId.slice(0, 10)}.md`,
    )
    .replace(/\\/gu, "/");
}

function renderNormalizedMarkdown(source: PersonalKnowledgeSource, chunks: PersonalKnowledgeIndex["chunks"]): string {
  return [
    `# ${source.title}`,
    "",
    `- source_id: ${source.sourceId}`,
    `- asset_id: ${source.assetId ?? ""}`,
    `- relative_path: ${source.relativePath}`,
    `- knowledge_domain: ${source.knowledgeDomain ?? "external"}`,
    `- project_stage: ${source.projectStage ?? "evergreen"}`,
    "",
    ...chunks.map((chunk) => [`## Chunk ${chunk.chunkIndex + 1}`, "", chunk.text, ""].join("\n")),
  ].join("\n");
}

function renderVisionSidecarMarkdown(params: {
  title: string;
  relativePath: string;
  sidecar: HxyVisionSidecar;
}): string {
  const section = (label: string, values?: string[]): string[] =>
    values && values.length > 0 ? [`## ${label}`, "", ...values.map((value) => `- ${value}`), ""] : [];
  return [
    `# ${params.title}`,
    "",
    `- source_type: image_vision_sidecar`,
    `- relative_path: ${params.relativePath}`,
    `- asset_type: ${params.sidecar.asset_type ?? "image"}`,
    `- knowledge_domain: ${params.sidecar.knowledge_domain ?? "external"}`,
    `- project_stage: ${params.sidecar.project_stage ?? "evergreen"}`,
    "",
    ...section("Observations", params.sidecar.observations),
    ...section("Brand Elements", params.sidecar.brand_elements),
    ...section("Price Signals", params.sidecar.price_signals),
    ...section("Service Signals", params.sidecar.service_signals),
    ...section("Evidence Text", params.sidecar.evidence_text),
  ].join("\n");
}

async function readVisionSidecar(imagePath: string): Promise<HxyVisionSidecar | undefined> {
  const sidecarPath = `${imagePath}.vision.json`;
  try {
    const raw = await fs.readFile(sidecarPath, "utf8");
    const parsed = JSON.parse(raw) as unknown;
    return parsed && typeof parsed === "object" ? (parsed as HxyVisionSidecar) : undefined;
  } catch {
    return undefined;
  }
}

function buildVisionSource(params: {
  rootDir: string;
  relativePath: string;
  fileName: string;
  stats: { size: number; mtime: Date };
  sidecar: HxyVisionSidecar;
  classification: ReturnType<typeof classifyHxyKnowledgeAsset>;
  chunkSize?: number;
  overlap?: number;
}): {
  source: PersonalKnowledgeSource;
  chunks: PersonalKnowledgeIndex["chunks"];
  normalizedPath: string;
  normalizedText: string;
} {
  const title = normalizePersonalKnowledgeTitle(params.fileName);
  const contentDomain = params.sidecar.knowledge_domain ?? params.classification.domain;
  const projectStage = params.sidecar.project_stage ?? params.classification.stage;
  const text = renderVisionSidecarMarkdown({ title, relativePath: params.relativePath, sidecar: params.sidecar });
  const assetId = `vision:${params.relativePath}`;
  const sourceId = `hxy:${params.relativePath}:vision`;
  const confidence = params.sidecar.confidence ?? params.classification.confidence;
  const source: PersonalKnowledgeSource = {
    sourceId,
    domain: "hxy",
    title,
    relativePath: params.relativePath,
    fileName: params.fileName,
    fileSize: params.stats.size,
    updatedAt: params.stats.mtime.toISOString(),
    assetId,
    knowledgeDomain: contentDomain,
    secondaryKnowledgeDomains: params.classification.secondaryDomains,
    projectStage,
    classificationConfidence: confidence,
    classificationReasons: ["vision_sidecar", ...params.classification.reasons],
  };
  const chunks = chunkPersonalKnowledgeText({
    domain: "hxy",
    sourceId,
    title,
    relativePath: params.relativePath,
    text,
    chunkSize: params.chunkSize,
    overlap: params.overlap,
    metadata: {
      assetId,
      knowledgeDomain: contentDomain,
      secondaryKnowledgeDomains: params.classification.secondaryDomains,
      projectStage,
      classificationConfidence: confidence,
      classificationReasons: source.classificationReasons,
    },
  });
  return {
    source,
    chunks,
    normalizedPath: normalizedRelativePath({
      title,
      assetId,
      knowledgeDomain: contentDomain,
      projectStage,
    }),
    normalizedText: text,
  };
}

function emptyCoverage(): Record<string, Record<string, number>> {
  const coverage: Record<string, Record<string, number>> = {};
  for (const domain of HXY_KNOWLEDGE_DOMAINS) {
    coverage[domain.key] = {};
    for (const stage of HXY_PROJECT_STAGES) {
      coverage[domain.key][stage.key] = 0;
    }
  }
  return coverage;
}

export function buildHxyKnowledgeDoctorReport(
  manifest: HxyKnowledgeManifest,
  now: () => Date = () => new Date(),
): HxyKnowledgeDoctorReport {
  const coverage = emptyCoverage();
  const issues: HxyKnowledgeDoctorReport["issues"] = [];
  let duplicateCount = 0;
  for (const asset of manifest.assets) {
    coverage[asset.knowledgeDomain] ??= {};
    coverage[asset.knowledgeDomain][asset.projectStage] ??= 0;
    if (asset.status === "indexed" || asset.status === "normalized" || asset.status === "structured") {
      coverage[asset.knowledgeDomain][asset.projectStage] += 1;
    }
    if (asset.warnings.length > 0 || asset.status === "skipped" || asset.status === "failed" || asset.status === "needs_review") {
      issues.push({
        fileName: asset.fileName,
        relativePath: asset.relativePath,
        status: asset.status,
        warnings: asset.warnings,
      });
    }
    if (asset.warnings.includes("duplicate_content")) {
      duplicateCount += 1;
    }
  }
  const impacts = HXY_KNOWLEDGE_DOMAINS.filter((domain) => {
    const total = Object.values(coverage[domain.key] ?? {}).reduce((sum, count) => sum + count, 0);
    return total === 0;
  }).map((domain) => `${domain.key} knowledge is missing; related HXY answers should avoid firm conclusions.`);
  return {
    version: "hxy-knowledge-doctor.v1",
    generatedAt: now().toISOString(),
    summary: {
      total_asset_count: manifest.assets.length,
      indexed_asset_count: manifest.assets.filter((asset) => asset.status === "indexed").length,
      skipped_asset_count: manifest.assets.filter((asset) => asset.status === "skipped").length,
      failed_asset_count: manifest.assets.filter((asset) => asset.status === "failed").length,
      low_confidence_asset_count: manifest.assets.filter((asset) => asset.classificationConfidence < 0.5).length,
      duplicate_asset_count: duplicateCount,
    },
    coverage,
    issues,
    impacts,
  };
}

export async function buildHxyKnowledgeFactory(params: {
  rootDir: string;
  rawDir: string;
  outputDir: string;
  readSourceText?: (filePath: string) => Promise<PersonalKnowledgeSourceText>;
  taxonomyOverrides?: HxyKnowledgeTaxonomyOverride[];
  now?: () => Date;
  chunkSize?: number;
  overlap?: number;
}): Promise<HxyKnowledgeFactoryOutput> {
  const now = params.now ?? (() => new Date());
  const index = await buildPersonalKnowledgeIndex({
    rootDir: params.rootDir,
    rawDir: params.rawDir,
    domain: "hxy",
    readSourceText: params.readSourceText,
    hxyTaxonomyOverrides: params.taxonomyOverrides,
    now,
    chunkSize: params.chunkSize,
    overlap: params.overlap,
  });
  const files = await collectFiles(params.rawDir);
  const sourceByRelativePath = new Map(index.sources.map((source) => [source.relativePath, source]));
  const skippedReasonByRawRelativePath = new Map<string, string>();
  for (const item of index.skippedFiles) {
    skippedReasonByRawRelativePath.set(item.fileName, item.reason);
    skippedReasonByRawRelativePath.set(item.relativePath, item.reason);
    const rawRelativePath = path.relative(params.rawDir, path.join(params.rootDir, item.relativePath)).replace(/\\/gu, "/");
    skippedReasonByRawRelativePath.set(rawRelativePath, item.reason);
  }
  const chunksBySource = new Map<string, PersonalKnowledgeIndex["chunks"]>();
  for (const chunk of index.chunks) {
    const list = chunksBySource.get(chunk.sourceId) ?? [];
    list.push(chunk);
    chunksBySource.set(chunk.sourceId, list);
  }
  const seenSha1 = new Set<string>();
  const normalizedFiles: HxyKnowledgeFactoryOutput["normalizedFiles"] = [];
  const assets: HxyKnowledgeManifestAsset[] = [];
  for (const absolutePath of files) {
    const stats = await fs.stat(absolutePath);
    const fileName = path.basename(absolutePath);
    const relativePath = path.relative(params.rootDir, absolutePath).replace(/\\/gu, "/");
    const rawRelativePath = path.relative(params.rawDir, absolutePath).replace(/\\/gu, "/");
    const source = sourceByRelativePath.get(relativePath);
    if (!isSupportedPersonalKnowledgeSource(fileName) || !source) {
      const classification = classifyHxyKnowledgeAsset({
        relativePath,
        fileName,
        title: path.basename(fileName, path.extname(fileName)),
        overrides: params.taxonomyOverrides,
      });
      const sidecar = await readVisionSidecar(absolutePath);
      if (sidecar) {
        const vision = buildVisionSource({
          rootDir: params.rootDir,
          relativePath,
          fileName,
          stats,
          sidecar,
          classification,
          chunkSize: params.chunkSize,
          overlap: params.overlap,
        });
        index.sources.push(vision.source);
        index.chunks.push(...vision.chunks);
        normalizedFiles.push({ relativePath: vision.normalizedPath, text: vision.normalizedText });
        assets.push({
          assetId: vision.source.assetId ?? vision.source.sourceId,
          sourceId: vision.source.sourceId,
          fileName,
          relativePath,
          normalizedPath: vision.normalizedPath,
          fileSize: stats.size,
          updatedAt: stats.mtime.toISOString(),
          contentType: extensionToContentType(fileName),
          parser: vision.source.parser,
          parserWarnings: vision.source.parserWarnings,
          knowledgeDomain: (vision.source.knowledgeDomain ?? classification.domain) as HxyKnowledgeManifestAsset["knowledgeDomain"],
          secondaryKnowledgeDomains: vision.source.secondaryKnowledgeDomains ?? [],
          projectStage: (vision.source.projectStage ?? classification.stage) as HxyKnowledgeManifestAsset["projectStage"],
          classificationConfidence: vision.source.classificationConfidence ?? classification.confidence,
          classificationReasons: vision.source.classificationReasons ?? classification.reasons,
          status: "indexed",
          chunkCount: vision.chunks.length,
          warnings: ["vision_sidecar_indexed"],
        });
        continue;
      }
      if (fileName.endsWith(".vision.json")) {
        continue;
      }
      assets.push({
        assetId: `skipped:${relativePath}`,
        fileName,
        relativePath,
        fileSize: stats.size,
        updatedAt: stats.mtime.toISOString(),
        contentType: extensionToContentType(fileName),
        knowledgeDomain: classification.domain,
        secondaryKnowledgeDomains: classification.secondaryDomains,
        projectStage: classification.stage,
        classificationConfidence: classification.confidence,
        classificationReasons: classification.reasons,
        status: "skipped",
        chunkCount: 0,
        warnings: [
          skippedReasonByRawRelativePath.get(rawRelativePath) ??
            (isSupportedPersonalKnowledgeSource(fileName) ? "text_extraction_failed" : "unsupported_file_type"),
        ],
      });
      continue;
    }
    const sourceChunks = chunksBySource.get(source.sourceId) ?? [];
    const warnings: string[] = [];
    if (source.contentSha1 && seenSha1.has(source.contentSha1)) {
      warnings.push("duplicate_content");
    }
    if (source.contentSha1) {
      seenSha1.add(source.contentSha1);
    }
    if ((source.classificationConfidence ?? 0) < 0.5) {
      warnings.push("low_classification_confidence");
    }
    const normalizedPath = normalizedRelativePath({
      title: source.title,
      assetId: source.assetId ?? source.sourceId,
      knowledgeDomain: source.knowledgeDomain ?? "external",
      projectStage: source.projectStage ?? "evergreen",
    });
    const normalizedText = renderNormalizedMarkdown(source, sourceChunks);
    normalizedFiles.push({ relativePath: normalizedPath, text: normalizedText });
    assets.push({
      assetId: source.assetId ?? source.sourceId,
      sourceId: source.sourceId,
      fileName,
      relativePath,
      normalizedPath,
      sha1: source.contentSha1,
      fileSize: stats.size,
      updatedAt: stats.mtime.toISOString(),
      contentType: extensionToContentType(fileName),
      parser: source.parser,
      parserWarnings: source.parserWarnings,
      knowledgeDomain: (source.knowledgeDomain ?? "external") as HxyKnowledgeManifestAsset["knowledgeDomain"],
      secondaryKnowledgeDomains: source.secondaryKnowledgeDomains ?? [],
      projectStage: (source.projectStage ?? "evergreen") as HxyKnowledgeManifestAsset["projectStage"],
      classificationConfidence: source.classificationConfidence ?? 0.2,
      classificationReasons: source.classificationReasons ?? [],
      status: warnings.includes("low_classification_confidence") ? "needs_review" : "indexed",
      chunkCount: sourceChunks.length,
      warnings,
    });
  }
  const manifest: HxyKnowledgeManifest = {
    version: "hxy-knowledge-manifest.v1",
    generatedAt: now().toISOString(),
    rawDir: path.relative(params.rootDir, params.rawDir).replace(/\\/gu, "/"),
    normalizedDir: "knowledge/hxy/normalized",
    assets,
  };
  return {
    taxonomy: {
      version: "hxy-knowledge-taxonomy.v1",
      domains: HXY_KNOWLEDGE_DOMAINS,
      stages: HXY_PROJECT_STAGES,
    },
    manifest,
    index,
    doctor: buildHxyKnowledgeDoctorReport(manifest, now),
    normalizedFiles,
  };
}

async function writeJson(filePath: string, payload: unknown): Promise<void> {
  await fs.mkdir(path.dirname(filePath), { recursive: true });
  await fs.writeFile(filePath, `${JSON.stringify(payload, null, 2)}\n`, "utf8");
}

export async function writeHxyKnowledgeFactoryOutputs(
  output: HxyKnowledgeFactoryOutput,
  params: {
    outputDir: string;
  },
): Promise<void> {
  await writeJson(path.join(params.outputDir, "taxonomy.json"), output.taxonomy);
  await writeJson(path.join(params.outputDir, "manifest.json"), output.manifest);
  await writeJson(path.join(params.outputDir, "index.json"), output.index);
  await writeJson(path.join(params.outputDir, "reports", "knowledge-doctor.json"), output.doctor);
  const rootDir = path.resolve(params.outputDir, "..", "..");
  for (const file of output.normalizedFiles) {
    const absolutePath = path.join(rootDir, file.relativePath);
    await fs.mkdir(path.dirname(absolutePath), { recursive: true });
    await fs.writeFile(absolutePath, file.text, "utf8");
  }
}
