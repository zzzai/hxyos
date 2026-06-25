import path from "node:path";
import { readHxyDeliverableInputs, writeHxyDeliverables } from "../packages/project-brain/src/hxy-deliverables.js";

type Args = {
  structuredDir: string;
  outputDir: string;
};

function parseArgs(argv: string[]): Args {
  const rootDir = process.env.HXY_ROOT_DIR?.trim() || process.cwd();
  const args: Args = {
    structuredDir: path.join(rootDir, "knowledge", "structured"),
    outputDir: path.join(rootDir, "projects", "hxy", "deliverables"),
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
            "Usage: node --import tsx scripts/build-hxy-deliverables.ts [options]",
            "",
            "Options:",
            "  --structured-dir <path>  HXY structured knowledge directory",
            "  --output-dir <path>      Markdown deliverables output directory",
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
  const inputs = await readHxyDeliverableInputs(args.structuredDir);
  await writeHxyDeliverables({ inputs, outputDir: args.outputDir });
  console.log(
    [
      `[hxy-deliverables] wrote ${path.join(args.outputDir, "hxy-brand-plan-v1.md")}`,
      `[hxy-deliverables] wrote ${path.join(args.outputDir, "hxy-pilot-execution-pack-v1.md")}`,
      `[hxy-deliverables] wrote ${path.join(args.outputDir, "hxy-terminal-material-pack-v1.md")}`,
      `[hxy-deliverables] wrote ${path.join(args.outputDir, "hxy-pilot-printable-cards-v1.md")}`,
    ].join("\n"),
  );
}

void main().catch((error) => {
  const message = error instanceof Error ? error.stack ?? error.message : String(error);
  console.error(message);
  process.exitCode = 1;
});
