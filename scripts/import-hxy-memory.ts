import path from "node:path";
import { Pool } from "pg";
import { importHxyMemoryFromStructuredDir } from "../packages/memory-service/src/importer.js";
import { HxyMemoryStore } from "../packages/memory-service/src/store.js";

type Args = {
  rootDir: string;
  structuredDir: string;
};

function parseArgs(argv: string[]): Args {
  const rootDir = process.env.HXY_ROOT_DIR || process.cwd();
  const args: Args = {
    rootDir,
    structuredDir: path.join(rootDir, "knowledge", "structured"),
  };
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    const next = argv[index + 1];
    switch (arg) {
      case "--root":
        if (!next) {
          throw new Error("--root requires a value");
        }
        args.rootDir = path.resolve(next);
        args.structuredDir = path.join(args.rootDir, "knowledge", "structured");
        index += 1;
        break;
      case "--structured-dir":
        if (!next) {
          throw new Error("--structured-dir requires a value");
        }
        args.structuredDir = path.resolve(next);
        index += 1;
        break;
      case "--help":
      case "-h":
        console.log(
          [
            "Usage: node --import tsx scripts/import-hxy-memory.ts [options]",
            "",
            "Options:",
            "  --root <path>            Project root. Defaults to HXY_ROOT_DIR or cwd.",
            "  --structured-dir <path>  HXY structured knowledge directory.",
            "",
            "Environment:",
            "  HXY_DATABASE_URL is required.",
          ].join("\n"),
        );
        process.exit(0);
      default:
        throw new Error(`Unknown argument: ${arg}`);
    }
  }
  return args;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const connectionString = process.env.HXY_DATABASE_URL;
  if (!connectionString) {
    throw new Error("HXY_DATABASE_URL is required");
  }
  const pool = new Pool({ connectionString });
  try {
    const store = new HxyMemoryStore(pool);
    const result = await importHxyMemoryFromStructuredDir({
      store,
      structuredDir: args.structuredDir,
    });
    console.log(
      [
        `[hxy-memory] import_id=${result.importId}`,
        `[hxy-memory] structured_dir=${args.structuredDir}`,
        `[hxy-memory] items=${result.items.length} evidence_links=${result.evidenceLinks.length} skipped=${result.skippedFiles.length}`,
      ].join("\n"),
    );
  } finally {
    await pool.end();
  }
}

main().catch((error: unknown) => {
  const message = error instanceof Error ? error.message : String(error);
  console.error(`[hxy-memory] failed: ${message}`);
  process.exitCode = 1;
});
