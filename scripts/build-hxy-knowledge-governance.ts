import path from "node:path";
import {
  buildHxyKnowledgeGovernanceReport,
  readHxyClaims,
  writeHxyKnowledgeGovernanceReport,
} from "../packages/project-brain/src/hxy-knowledge-governance.js";

type Args = {
  claimsPath: string;
  outputDir: string;
};

function parseArgs(argv: string[]): Args {
  const rootDir = process.env.HXY_ROOT_DIR?.trim() || process.cwd();
  const args: Args = {
    claimsPath: path.join(rootDir, "knowledge", "structured", "claims.json"),
    outputDir: path.join(rootDir, "knowledge", "structured"),
  };
  for (let index = 0; index < argv.length; index += 1) {
    const current = argv[index];
    const next = argv[index + 1];
    switch (current) {
      case "--claims":
        if (!next) {
          throw new Error("--claims requires a value");
        }
        args.claimsPath = path.resolve(next);
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
            "Usage: node --import tsx scripts/build-hxy-knowledge-governance.ts [options]",
            "",
            "Options:",
            "  --claims <path>      Structured HXY claims JSON",
            "  --output-dir <path>  Governance output directory",
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
  const claims = await readHxyClaims(args.claimsPath);
  const report = buildHxyKnowledgeGovernanceReport(claims);
  await writeHxyKnowledgeGovernanceReport(report, args.outputDir);
  console.log(
    [
      `[hxy-governance] wrote ${path.join(args.outputDir, "governance-report.json")}`,
      `[hxy-governance] claims=${report.summary.claim_count} themes=${report.summary.theme_count} conflicts=${report.summary.conflict_count} review_queue=${report.summary.needs_human_review_count}`,
    ].join("\n"),
  );
}

void main().catch((error) => {
  const message = error instanceof Error ? error.stack ?? error.message : String(error);
  console.error(message);
  process.exitCode = 1;
});
