import { createHash } from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";
import {
  classifyHxyKnowledgeAsset,
  type HxyKnowledgeTaxonomyOverride,
} from "./hxy-knowledge-taxonomy.js";

export type PersonalKnowledgeSourceText = string;

export type PersonalKnowledgeSource = {
  sourceId: string;
  domain: string;
  title: string;
  relativePath: string;
  fileName: string;
  fileSize: number;
  updatedAt: string;
  parser?: string;
  parserWarnings?: string[];
  contentSha1?: string;
  assetId?: string;
  knowledgeDomain?: string;
  secondaryKnowledgeDomains?: string[];
  projectStage?: string;
  classificationConfidence?: number;
  classificationReasons?: string[];
};

export type PersonalKnowledgeChunk = {
  chunkId: string;
  sourceId: string;
  domain: string;
  title: string;
  relativePath: string;
  chunkIndex: number;
  text: string;
  keywords: string[];
  metadata?: Record<string, unknown>;
};

export type PersonalKnowledgeIndex = {
  version: "personal-knowledge-index.v1";
  generatedAt: string;
  rootDir: string;
  rawDir: string;
  domains: string[];
  sources: PersonalKnowledgeSource[];
  chunks: PersonalKnowledgeChunk[];
  skippedFiles: Array<{
    fileName: string;
    relativePath: string;
    reason: string;
  }>;
};

export type PersonalKnowledgeSearchResult = {
  chunkId: string;
  sourceId: string;
  domain: string;
  title: string;
  relativePath: string;
  chunkIndex: number;
  text: string;
  keywords: string[];
  score: number;
};

const SUPPORTED_EXTENSIONS = new Set([".md", ".txt", ".json", ".csv", ".html", ".htm", ".pdf", ".docx", ".pptx"]);
const IMAGE_EXTENSIONS = new Set([".gif", ".jpeg", ".jpg", ".png", ".svg", ".webp"]);

function sha1(value: string): string {
  return createHash("sha1").update(value).digest("hex");
}

function normalizeWhitespace(value: string): string {
  return value.replace(/\s+/gu, " ").trim();
}

export function normalizePersonalKnowledgeTitle(fileName: string): string {
  return path.basename(fileName, path.extname(fileName)).replace(/[-_]+/gu, " ").trim() || fileName;
}

export function isSupportedPersonalKnowledgeSource(fileName: string): boolean {
  return SUPPORTED_EXTENSIONS.has(path.extname(fileName).toLowerCase());
}

function tokenize(value: string): string[] {
  return Array.from(
    new Set(
      normalizeWhitespace(value.toLowerCase())
        .split(/[\s,.;:!?，。；：！？、|/()[\]{}"'`<>《》「」]+/u)
        .map((part) => part.trim())
        .filter(Boolean),
    ),
  );
}

export function chunkPersonalKnowledgeText(params: {
  domain: string;
  sourceId: string;
  title: string;
  relativePath: string;
  text: string;
  chunkSize?: number;
  overlap?: number;
  metadata?: Record<string, unknown>;
}): PersonalKnowledgeChunk[] {
  const compact = normalizeWhitespace(params.text);
  if (!compact) {
    return [];
  }
  const chunkSize = Math.max(200, params.chunkSize ?? 1200);
  const overlap = Math.max(0, Math.min(params.overlap ?? 160, Math.floor(chunkSize / 2)));
  const chunks: PersonalKnowledgeChunk[] = [];
  let start = 0;
  while (start < compact.length) {
    const text = compact.slice(start, start + chunkSize).trim();
    if (text) {
      const chunkIndex = chunks.length;
      chunks.push({
        chunkId: `${params.sourceId}:chunk:${chunkIndex}`,
        sourceId: params.sourceId,
        domain: params.domain,
        title: params.title,
        relativePath: params.relativePath,
        chunkIndex,
        text,
        keywords: tokenize(`${params.title} ${text}`).slice(0, 24),
        metadata: params.metadata,
      });
    }
    if (start + chunkSize >= compact.length) {
      break;
    }
    start += chunkSize - overlap;
  }
  return chunks;
}

async function collectFiles(rawDir: string): Promise<string[]> {
  const files: string[] = [];
  async function visit(directory: string): Promise<void> {
    const entries = await fs.readdir(directory, { withFileTypes: true });
    for (const entry of entries.sort((left, right) => left.name.localeCompare(right.name, "zh-Hans-CN"))) {
      const absolutePath = path.join(directory, entry.name);
      if (entry.isDirectory()) {
        await visit(absolutePath);
      } else if (entry.isFile() || entry.isSymbolicLink()) {
        files.push(absolutePath);
      }
    }
  }
  await visit(rawDir);
  return files;
}

export async function buildPersonalKnowledgeIndex(params: {
  rootDir: string;
  rawDir: string;
  domain: string;
  readSourceText?: (filePath: string) => Promise<PersonalKnowledgeSourceText>;
  hxyTaxonomyOverrides?: HxyKnowledgeTaxonomyOverride[];
  now?: () => Date;
  chunkSize?: number;
  overlap?: number;
}): Promise<PersonalKnowledgeIndex> {
  const now = params.now ?? (() => new Date());
  const files = await collectFiles(params.rawDir);
  const sources: PersonalKnowledgeSource[] = [];
  const chunks: PersonalKnowledgeChunk[] = [];
  const skippedFiles: PersonalKnowledgeIndex["skippedFiles"] = [];
  const readSourceText = params.readSourceText ?? ((filePath: string) => fs.readFile(filePath, "utf8"));

  for (const absolutePath of files) {
    const fileName = path.basename(absolutePath);
    const relativePath = path.relative(params.rootDir, absolutePath).replace(/\\/gu, "/");
    if (!isSupportedPersonalKnowledgeSource(fileName)) {
      const extension = path.extname(fileName).toLowerCase();
      skippedFiles.push({
        fileName,
        relativePath,
        reason: IMAGE_EXTENSIONS.has(extension) ? "markitdown_required" : "unsupported_file_type",
      });
      continue;
    }
    let text = "";
    try {
      text = await readSourceText(absolutePath);
    } catch {
      skippedFiles.push({ fileName, relativePath, reason: "text_extraction_failed" });
      continue;
    }
    const stats = await fs.stat(absolutePath);
    const title = normalizePersonalKnowledgeTitle(fileName);
    const classification = classifyHxyKnowledgeAsset({
      relativePath,
      fileName,
      title,
      overrides: params.hxyTaxonomyOverrides,
    });
    const sourceId = `${params.domain}:${sha1(relativePath).slice(0, 16)}`;
    const assetId = `${params.domain}:asset:${sha1(relativePath).slice(0, 16)}`;
    const source: PersonalKnowledgeSource = {
      sourceId,
      domain: params.domain,
      title,
      relativePath,
      fileName,
      fileSize: stats.size,
      updatedAt: stats.mtime.toISOString(),
      parser: "text",
      contentSha1: sha1(text),
      assetId,
      knowledgeDomain: classification.domain,
      secondaryKnowledgeDomains: classification.secondaryDomains,
      projectStage: classification.stage,
      classificationConfidence: classification.confidence,
      classificationReasons: classification.reasons,
    };
    const sourceChunks = chunkPersonalKnowledgeText({
      domain: params.domain,
      sourceId,
      title,
      relativePath,
      text,
      chunkSize: params.chunkSize,
      overlap: params.overlap,
      metadata: {
        assetId,
        knowledgeDomain: classification.domain,
        secondaryKnowledgeDomains: classification.secondaryDomains,
        projectStage: classification.stage,
        classificationConfidence: classification.confidence,
        classificationReasons: classification.reasons,
      },
    });
    sources.push(source);
    chunks.push(...sourceChunks);
  }

  return {
    version: "personal-knowledge-index.v1",
    generatedAt: now().toISOString(),
    rootDir: params.rootDir,
    rawDir: params.rawDir,
    domains: [params.domain],
    sources,
    chunks,
    skippedFiles,
  };
}

export async function readPersonalKnowledgeIndex(indexPath: string): Promise<PersonalKnowledgeIndex> {
  return JSON.parse(await fs.readFile(indexPath, "utf8")) as PersonalKnowledgeIndex;
}

export function searchPersonalKnowledgeChunks(
  chunks: PersonalKnowledgeChunk[],
  query: string,
  options: { domain?: string; topK?: number } = {},
): PersonalKnowledgeSearchResult[] {
  const queryTokens = tokenize(query);
  const topK = options.topK ?? 10;
  return chunks
    .filter((chunk) => !options.domain || chunk.domain === options.domain)
    .map((chunk) => {
      const haystack = `${chunk.title} ${chunk.text}`.toLowerCase();
      const keywordHits = chunk.keywords.filter((keyword) => queryTokens.includes(keyword)).length;
      const textHits = queryTokens.filter((token) => haystack.includes(token)).length;
      return {
        chunkId: chunk.chunkId,
        sourceId: chunk.sourceId,
        domain: chunk.domain,
        title: chunk.title,
        relativePath: chunk.relativePath,
        chunkIndex: chunk.chunkIndex,
        text: chunk.text,
        keywords: chunk.keywords,
        score: keywordHits * 4 + textHits,
      };
    })
    .filter((item) => item.score > 0)
    .sort((left, right) => right.score - left.score)
    .slice(0, topK);
}
