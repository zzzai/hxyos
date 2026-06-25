import path from "node:path";
import {
  buildHxyOsiContract,
  readHxyKnowledgeGovernanceReport,
  writeHxyOsiContract,
} from "../packages/project-brain/src/hxy-osi-contract.js";

type Args = {
  governanceReportPath: string;
  outputDir: string;
};

function parseArgs(argv: string[]): Args {
  const rootDir = process.env.HXY_ROOT_DIR?.trim() || process.cwd();
  const args: Args = {
    governanceReportPath: path.join(rootDir, "knowledge", "structured", "governance-report.json"),
    outputDir: path.join(rootDir, "knowledge", "structured"),
  };
  for (let index = 0; index < argv.length; index += 1) {
    const current = argv[index];
    const next = argv[index + 1];
    switch (current) {
      case "--governance-report":
        if (!next) {
          throw new Error("--governance-report requires a value");
        }
        args.governanceReportPath = path.resolve(next);
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
            "Usage: node --import tsx scripts/build-hxy-osi-contract.ts [options]",
            "",
            "Options:",
            "  --governance-report <path>  HXY governance report JSON",
            "  --output-dir <path>         OSI contract output directory",
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
  const report = await readHxyKnowledgeGovernanceReport(args.governanceReportPath);
  const contract = buildHxyOsiContract(report);
  await writeHxyOsiContract(contract, args.outputDir);
  console.log(
    [
      `[hxy-osi] wrote ${path.join(args.outputDir, "osi-contract.json")}`,
      `[hxy-osi] domains=${contract.domains.length} open_review_items=${contract.governance.open_review_items.length}`,
    ].join("\n"),
  );
}

void main().catch((error) => {
  const message = error instanceof Error ? error.stack ?? error.message : String(error);
  console.error(message);
  process.exitCode = 1;
});
