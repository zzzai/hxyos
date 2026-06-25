import path from "node:path";
import {
  buildHxyPilotValidationMatrix,
  calculateHxyStoreModel,
  readHxyStoreModelInput,
  writeHxyStoreModelOutputs,
} from "../packages/project-brain/src/hxy-store-model-calculator.js";

type Args = {
  inputPath: string;
  outputDir: string;
};

function parseArgs(argv: string[]): Args {
  const rootDir = process.env.HXY_ROOT_DIR?.trim() || process.cwd();
  const args: Args = {
    inputPath: path.join(rootDir, "projects", "hxy", "samples", "store-model-input.sample.json"),
    outputDir: path.join(rootDir, "knowledge", "structured"),
  };

  for (let index = 0; index < argv.length; index += 1) {
    const current = argv[index];
    const next = argv[index + 1];
    switch (current) {
      case "--input":
        if (!next) {
          throw new Error("--input requires a value");
        }
        args.inputPath = path.resolve(next);
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
            "Usage: node --import tsx scripts/build-hxy-store-model.ts [options]",
            "",
            "Options:",
            "  --input <path>      HXY sample store model input JSON",
            "  --output-dir <path> Store model output directory",
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
  const input = await readHxyStoreModelInput(args.inputPath);
  const model = calculateHxyStoreModel(input);
  const matrix = buildHxyPilotValidationMatrix(model);
  await writeHxyStoreModelOutputs({ model, matrix, outputDir: args.outputDir });
  console.log(
    [
      `[hxy-store-model] wrote ${path.join(args.outputDir, "store-model.json")}`,
      `[hxy-store-model] wrote ${path.join(args.outputDir, "pilot-validation-matrix.json")}`,
      `[hxy-store-model] monthly_revenue=${model.monthly_revenue} monthly_net_cashflow=${model.monthly_net_cashflow} payback_months=${model.payback_months ?? "n/a"}`,
    ].join("\n"),
  );
}

void main().catch((error) => {
  const message = error instanceof Error ? error.stack ?? error.message : String(error);
  console.error(message);
  process.exitCode = 1;
});
