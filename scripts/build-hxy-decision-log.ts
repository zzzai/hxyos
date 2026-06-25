import path from "node:path";
import {
  buildHxyDecisionLog,
  readHxyDecisionLogInputs,
  writeHxyDecisionLog,
} from "../packages/project-brain/src/hxy-decision-log.js";

type Args = {
  structuredDir: string;
  outputDir: string;
};

function parseArgs(argv: string[]): Args {
  const rootDir = process.env.HXY_ROOT_DIR?.trim() || process.cwd();
  const args: Args = {
    structuredDir: path.join(rootDir, "knowledge", "structured"),
    outputDir: path.join(rootDir, "knowledge", "structured"),
  };
  for (let index = 0; index < argv.length; index += 1) {
    const current = argv[index];
    const next = argv[index + 1];
    switch (current) {
      case "--structured-dir":
        if (!next) {
          throw new Error("--structured-dir requires a value");
        }
        args.structuredDir = path.resolve(next);
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
            "Usage: node --import tsx scripts/build-hxy-decision-log.ts [options]",
            "",
            "Options:",
            "  --structured-dir <path>  HXY structured knowledge directory",
            "  --output-dir <path>      Output directory, default structured-dir",
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
  const inputs = await readHxyDecisionLogInputs(args.structuredDir);
  const log = buildHxyDecisionLog(inputs);
  await writeHxyDecisionLog(log, args.outputDir);
  console.log(
    [
      `[hxy-decision-log] wrote ${path.join(args.outputDir, "decision-log.json")}`,
      `[hxy-decision-log] decisions=${log.summary.decision_count} validation_required=${log.summary.validation_required_count}`,
    ].join("\n"),
  );
}

void main().catch((error) => {
  const message = error instanceof Error ? error.stack ?? error.message : String(error);
  console.error(message);
  process.exitCode = 1;
});
