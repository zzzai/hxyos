import path from "node:path";
import {
  buildHxyBrandMasterPlan,
  readHxyBrandPlanningDraft,
  writeHxyBrandMasterPlan,
} from "../packages/project-brain/src/hxy-brand-master-plan.js";
import { readPersonalKnowledgeIndex, searchPersonalKnowledgeChunks } from "../packages/project-brain/src/personal-knowledge.js";

type Args = {
  draftPath: string;
  brandIndexPath: string;
  outputDir: string;
};

function parseArgs(argv: string[]): Args {
  const rootDir = process.env.HXY_ROOT_DIR?.trim() || process.cwd();
  const args: Args = {
    draftPath: path.join(rootDir, "knowledge", "structured", "brand-planning-draft.json"),
    brandIndexPath: path.join(rootDir, "knowledge", "brand", "index.json"),
    outputDir: path.join(rootDir, "knowledge", "structured"),
  };
  for (let index = 0; index < argv.length; index += 1) {
    const current = argv[index];
    const next = argv[index + 1];
    switch (current) {
      case "--draft":
        if (!next) {
          throw new Error("--draft requires a value");
        }
        args.draftPath = path.resolve(next);
        index += 1;
        break;
      case "--brand-index":
        if (!next) {
          throw new Error("--brand-index requires a value");
        }
        args.brandIndexPath = path.resolve(next);
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
            "Usage: node --import tsx scripts/build-hxy-brand-master-plan.ts [options]",
            "",
            "Options:",
            "  --draft <path>        HXY brand planning draft JSON",
            "  --brand-index <path>  Brand theory knowledge index JSON",
            "  --output-dir <path>   Master plan output directory",
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
  const draft = await readHxyBrandPlanningDraft(args.draftPath);
  const brandIndex = await readPersonalKnowledgeIndex(args.brandIndexPath);
  const theoryResults = searchPersonalKnowledgeChunks(
    brandIndex.chunks,
    "华与华 文化母体 购买理由 超级符号 货架思维 终端 品牌战略",
    { domain: "brand", topK: 5 },
  );
  const plan = buildHxyBrandMasterPlan({ draft, theoryResults });
  await writeHxyBrandMasterPlan(plan, args.outputDir);
  console.log(
    [
      `[hxy-brand-master] wrote ${path.join(args.outputDir, "brand-master-plan.json")}`,
      `[hxy-brand-master] sections=${plan.sections.length} methodology=${plan.methodology_principles.length} citations=${plan.citations.length}`,
    ].join("\n"),
  );
}

void main().catch((error) => {
  const message = error instanceof Error ? error.stack ?? error.message : String(error);
  console.error(message);
  process.exitCode = 1;
});
