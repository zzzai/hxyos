import path from "node:path";
import {
  buildHxyBrandPlanningDraft,
  readHxyOsiContract,
  writeHxyBrandPlanningDraft,
} from "../packages/project-brain/src/hxy-brand-planning-agent.js";

type Args = {
  osiContractPath: string;
  outputDir: string;
};

function parseArgs(argv: string[]): Args {
  const rootDir = process.env.HXY_ROOT_DIR?.trim() || process.cwd();
  const args: Args = {
    osiContractPath: path.join(rootDir, "knowledge", "structured", "osi-contract.json"),
    outputDir: path.join(rootDir, "knowledge", "structured"),
  };
  for (let index = 0; index < argv.length; index += 1) {
    const current = argv[index];
    const next = argv[index + 1];
    switch (current) {
      case "--osi-contract":
        if (!next) {
          throw new Error("--osi-contract requires a value");
        }
        args.osiContractPath = path.resolve(next);
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
            "Usage: node --import tsx scripts/build-hxy-brand-planning-draft.ts [options]",
            "",
            "Options:",
            "  --osi-contract <path>  HXY OSI contract JSON",
            "  --output-dir <path>    Brand planning draft output directory",
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
  const contract = await readHxyOsiContract(args.osiContractPath);
  const draft = buildHxyBrandPlanningDraft(contract);
  await writeHxyBrandPlanningDraft(draft, args.outputDir);
  console.log(
    [
      `[hxy-brand] wrote ${path.join(args.outputDir, "brand-planning-draft.json")}`,
      `[hxy-brand] terminal_actions=${draft.terminal_actions.length} validation_items=${draft.validation_plan.length} open_risks=${draft.open_risks.length}`,
    ].join("\n"),
  );
}

void main().catch((error) => {
  const message = error instanceof Error ? error.stack ?? error.message : String(error);
  console.error(message);
  process.exitCode = 1;
});
