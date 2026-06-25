import { spawn } from "node:child_process";
import fs from "node:fs/promises";
import path from "node:path";
import {
  buildHxyKnowledgeFactory,
  writeHxyKnowledgeFactoryOutputs,
} from "../packages/project-brain/src/hxy-knowledge-factory.js";
import type { HxyKnowledgeTaxonomyOverride } from "../packages/project-brain/src/hxy-knowledge-taxonomy.js";
import { readSourceTextWithMarkitdownFallback } from "../packages/project-brain/src/markitdown-converter.js";

type Args = {
  rootDir: string;
  rawDir: string;
  outputDir: string;
  chunkSize: number;
  overlap: number;
  overridesPath: string;
};

function parseArgs(argv: string[]): Args {
  const rootDir = process.env.HXY_ROOT_DIR?.trim() || process.cwd();
  const args: Args = {
    rootDir,
    rawDir: path.join(rootDir, "knowledge", "raw"),
    outputDir: path.join(rootDir, "knowledge"),
    chunkSize: 1200,
    overlap: 160,
    overridesPath: path.join(rootDir, "knowledge", "taxonomy-overrides.json"),
  };
  for (let index = 0; index < argv.length; index += 1) {
    const current = argv[index];
    const next = argv[index + 1];
    switch (current) {
      case "--root-dir":
        if (!next) {
          throw new Error("--root-dir requires a value");
        }
        args.rootDir = path.resolve(next);
        index += 1;
        break;
      case "--raw-dir":
        if (!next) {
          throw new Error("--raw-dir requires a value");
        }
        args.rawDir = path.resolve(next);
        index += 1;
        break;
      case "--output-dir":
        if (!next) {
          throw new Error("--output-dir requires a value");
        }
        args.outputDir = path.resolve(next);
        index += 1;
        break;
      case "--chunk-size":
        if (!next) {
          throw new Error("--chunk-size requires a value");
        }
        args.chunkSize = Number.parseInt(next, 10);
        index += 1;
        break;
      case "--overlap":
        if (!next) {
          throw new Error("--overlap requires a value");
        }
        args.overlap = Number.parseInt(next, 10);
        index += 1;
        break;
      case "--overrides":
        if (!next) {
          throw new Error("--overrides requires a value");
        }
        args.overridesPath = path.resolve(next);
        index += 1;
        break;
      case "--help":
      case "-h":
        console.log(
          [
            "Usage: node --import tsx scripts/build-hxy-knowledge-factory.ts [options]",
            "",
            "Options:",
            "  --root-dir <path>     Repo root, default cwd",
            "  --raw-dir <path>      HXY raw knowledge directory",
            "  --output-dir <path>   HXY knowledge output directory",
            "  --chunk-size <chars>  Chunk size, default 1200",
            "  --overlap <chars>     Chunk overlap, default 160",
            "  --overrides <path>    Taxonomy override JSON path",
          ].join("\n"),
        );
        process.exit(0);
      default:
        throw new Error(`Unknown argument: ${current}`);
    }
  }
  return args;
}

async function readTaxonomyOverrides(overridesPath: string): Promise<HxyKnowledgeTaxonomyOverride[]> {
  try {
    const raw = await fs.readFile(overridesPath, "utf8");
    const parsed = JSON.parse(raw) as unknown;
    if (!parsed || typeof parsed !== "object") {
      return [];
    }
    const overrides = (parsed as { overrides?: unknown }).overrides;
    return Array.isArray(overrides) ? (overrides as HxyKnowledgeTaxonomyOverride[]) : [];
  } catch (error) {
    const code = (error as { code?: string }).code;
    if (code === "ENOENT") {
      return [];
    }
    throw error;
  }
}

async function commandExists(command: string): Promise<boolean> {
  return await new Promise((resolve) => {
    const child = spawn("bash", ["-lc", `command -v ${command}`], {
      stdio: "ignore",
    });
    child.on("close", (code) => resolve(code === 0));
    child.on("error", () => resolve(false));
  });
}

async function runTextCommand(command: string, args: string[]): Promise<string> {
  return await new Promise((resolve, reject) => {
    const child = spawn(command, args, {
      stdio: ["ignore", "pipe", "pipe"],
    });
    const chunks: Buffer[] = [];
    const errorChunks: Buffer[] = [];
    child.stdout.on("data", (chunk: Buffer) => chunks.push(chunk));
    child.stderr.on("data", (chunk: Buffer) => errorChunks.push(chunk));
    child.on("error", reject);
    child.on("close", (code) => {
      if (code !== 0) {
        reject(
          new Error(
            Buffer.concat(errorChunks).toString("utf8").trim() ||
              `${command} exited with code ${code}`,
          ),
        );
        return;
      }
      resolve(Buffer.concat(chunks).toString("utf8"));
    });
  });
}

async function runZipText(filePath: string, memberPattern: string): Promise<string> {
  return await new Promise((resolve, reject) => {
    const child = spawn("bash", ["-lc", `unzip -p "$1" '${memberPattern}' 2>/dev/null`, "bash", filePath], {
      stdio: ["ignore", "pipe", "pipe"],
    });
    const chunks: Buffer[] = [];
    const errorChunks: Buffer[] = [];
    child.stdout.on("data", (chunk: Buffer) => chunks.push(chunk));
    child.stderr.on("data", (chunk: Buffer) => errorChunks.push(chunk));
    child.on("error", reject);
    child.on("close", (code) => {
      const text = Buffer.concat(chunks).toString("utf8");
      if (code !== 0 && !text.trim()) {
        reject(
          new Error(
            Buffer.concat(errorChunks).toString("utf8").trim() ||
              `unzip exited with code ${code}`,
          ),
        );
        return;
      }
      resolve(text);
    });
  });
}

function stripXmlText(value: string): string {
  return value
    .replace(/<a:t[^>]*>/gu, " ")
    .replace(/<w:tab\/>/gu, " ")
    .replace(/<w:br\/>/gu, "\n")
    .replace(/<[^>]+>/gu, " ")
    .replace(/&lt;/gu, "<")
    .replace(/&gt;/gu, ">")
    .replace(/&amp;/gu, "&")
    .replace(/&quot;/gu, '"')
    .replace(/&apos;/gu, "'")
    .replace(/\s+/gu, " ")
    .trim();
}

async function readSourceText(filePath: string): Promise<string> {
  const ext = path.extname(filePath).toLowerCase();
  if (ext === ".pdf") {
    if (!(await commandExists("pdftotext"))) {
      throw new Error("pdftotext is required to index PDF files");
    }
    return await runTextCommand("pdftotext", ["-layout", "-enc", "UTF-8", filePath, "-"]);
  }
  if (ext === ".epub" || ext === ".docx") {
    if (!(await commandExists("pandoc"))) {
      throw new Error("pandoc is required to index EPUB/DOCX files");
    }
    return await runTextCommand("pandoc", [filePath, "-t", "plain"]);
  }
  if (ext === ".pptx") {
    if (!(await commandExists("unzip"))) {
      throw new Error("unzip is required to index PPTX files");
    }
    return stripXmlText(await runZipText(filePath, "ppt/slides/slide*.xml"));
  }
  if ((ext === ".html" || ext === ".htm") && (await commandExists("pandoc"))) {
    return await runTextCommand("pandoc", [filePath, "-t", "plain"]);
  }
  return await fs.readFile(filePath, "utf8");
}

async function readSourceTextWithPreferredParser(filePath: string) {
  return await readSourceTextWithMarkitdownFallback(filePath, readSourceText);
}

async function main(): Promise<void> {
  const args = parseArgs(process.argv.slice(2));
  const taxonomyOverrides = await readTaxonomyOverrides(args.overridesPath);
  const output = await buildHxyKnowledgeFactory({
    rootDir: args.rootDir,
    rawDir: args.rawDir,
    outputDir: args.outputDir,
    readSourceText: readSourceTextWithPreferredParser,
    taxonomyOverrides,
    chunkSize: args.chunkSize,
    overlap: args.overlap,
  });
  await writeHxyKnowledgeFactoryOutputs(output, { outputDir: args.outputDir });
  console.log(
    [
      `[hxy-knowledge-factory] wrote ${args.outputDir}`,
      `[hxy-knowledge-factory] assets=${output.manifest.assets.length} indexed=${output.doctor.summary.indexed_asset_count} skipped=${output.doctor.summary.skipped_asset_count} failed=${output.doctor.summary.failed_asset_count} low_confidence=${output.doctor.summary.low_confidence_asset_count}`,
      `[hxy-knowledge-factory] chunks=${output.index.chunks.length} normalized=${output.normalizedFiles.length}`,
    ].join("\n"),
  );
}

void main().catch((error) => {
  const message = error instanceof Error ? error.stack ?? error.message : String(error);
  console.error(message);
  process.exitCode = 1;
});
