import path from "node:path";
import {
  buildHxyStructuredKnowledge,
  readHxyKnowledgeIndex,
  writeHxyStructuredKnowledge,
} from "../packages/project-brain/src/hxy-knowledge-extractor.js";

type Args = {
  indexPath: string;
  outputDir: string;
};

function parseArgs(argv: string[]): Args {
  const rootDir = process.env.HXY_ROOT_DIR?.trim() || process.cwd();
  const args: Args = {
    indexPath: path.join(rootDir, "knowledge", "index.json"),
    outputDir: path.join(rootDir, "knowledge", "structured"),
  };
  for (let index = 0; index < argv.length; index += 1) {
    const current = argv[index];
    const next = argv[index + 1];
    switch (current) {
      case "--index":
        if (!next) {
          throw new Error("--index requires a value");
        }
        args.indexPath = path.resolve(next);
        index += 1;
        break;
      case "--output-dir":
        if (!next) {
          throw new Error("--output-dir requires a value");
        }
        args.outputDir = path.resolve(next);
        index += 1;
        break;
      case "--help":
      case "-h":
        console.log(
          [
            "Usage: node --import tsx scripts/build-hxy-structured-knowledge.ts [options]",
            "",
            "Options:",
            "  --index <path>       HXY personal knowledge index JSON",
            "  --output-dir <path>  Structured output directory",
          ].join("\n"),
        );
        process.exit(0);
      default:
        throw new Error(`Unknown argument: ${current}`);
    }
  }
  return args;
}

async function main(): Promise<void> {
  const args = parseArgs(process.argv.slice(2));
  const index = await readHxyKnowledgeIndex(args.indexPath);
  const output = buildHxyStructuredKnowledge(index);
  await writeHxyStructuredKnowledge(output, args.outputDir);
  console.log(
    [
      `[hxy-knowledge] wrote ${args.outputDir}`,
      `[hxy-knowledge] assets=${output.summary.asset_count} claims=${output.summary.claim_count} entities=${output.summary.entity_count} evidence=${output.summary.evidence_count} relations=${output.summary.relation_count}`,
    ].join("\n"),
  );
}

void main().catch((error) => {
  const message = error instanceof Error ? error.stack ?? error.message : String(error);
  console.error(message);
  process.exitCode = 1;
});
