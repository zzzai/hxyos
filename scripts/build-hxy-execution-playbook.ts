import path from "node:path";
import {
  buildHxyExecutionPlaybook,
  readHxyBrandMasterPlan,
  writeHxyExecutionPlaybook,
} from "../packages/project-brain/src/hxy-execution-playbook.js";

type Args = {
  masterPlanPath: string;
  outputDir: string;
};

function parseArgs(argv: string[]): Args {
  const rootDir = process.env.HXY_ROOT_DIR?.trim() || process.cwd();
  const args: Args = {
    masterPlanPath: path.join(rootDir, "knowledge", "structured", "brand-master-plan.json"),
    outputDir: path.join(rootDir, "knowledge", "structured"),
  };

  for (let index = 0; index < argv.length; index += 1) {
    const current = argv[index];
    const next = argv[index + 1];
    switch (current) {
      case "--master-plan":
        if (!next) {
          throw new Error("--master-plan requires a value");
        }
        args.masterPlanPath = path.resolve(next);
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
            "Usage: node --import tsx scripts/build-hxy-execution-playbook.ts [options]",
            "",
            "Options:",
            "  --master-plan <path>  HXY brand master plan JSON",
            "  --output-dir <path>   Execution playbook output directory",
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
  const plan = await readHxyBrandMasterPlan(args.masterPlanPath);
  const playbook = buildHxyExecutionPlaybook(plan);
  await writeHxyExecutionPlaybook(playbook, args.outputDir);
  console.log(
    [
      `[hxy-execution-playbook] wrote ${path.join(args.outputDir, "execution-playbook.json")}`,
      `[hxy-execution-playbook] surfaces=${playbook.surfaces.length} validation_metrics=${playbook.validation_metrics.length}`,
    ].join("\n"),
  );
}

void main().catch((error) => {
  const message = error instanceof Error ? error.stack ?? error.message : String(error);
  console.error(message);
  process.exitCode = 1;
});
