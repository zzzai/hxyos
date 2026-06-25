import { createHash } from "node:crypto";
import pg from "pg";

const VECTOR_DIMS = 384;

function envDatabaseUrl(): string {
  const value = process.env.HXY_DATABASE_URL;
  if (!value) {
    throw new Error("HXY_DATABASE_URL is required");
  }
  return value;
}

function hashNumber(value: string): number {
  return createHash("sha1").update(value).digest().readUInt32BE(0);
}

function features(text: string): string[] {
  const compact = text.toLowerCase().replace(/\s+/gu, " ").trim();
  const parts = compact.split(/[\s,.;:!?，。；：！？、|/()[\]{}"'`<>《》「」]+/u).filter(Boolean);
  const chars = [...compact.replace(/\s+/gu, "")];
  const grams: string[] = [];
  for (const part of parts) {
    grams.push(`w:${part}`);
  }
  for (let index = 0; index < chars.length; index += 1) {
    grams.push(`c:${chars[index]}`);
    if (index + 1 < chars.length) grams.push(`b:${chars[index]}${chars[index + 1]}`);
    if (index + 2 < chars.length) grams.push(`t:${chars[index]}${chars[index + 1]}${chars[index + 2]}`);
  }
  return grams;
}

function lexicalEmbedding(text: string): number[] {
  const vector = Array.from({ length: VECTOR_DIMS }, () => 0);
  for (const feature of features(text)) {
    const hash = hashNumber(feature);
    const index = hash % VECTOR_DIMS;
    const sign = hash & 1 ? 1 : -1;
    vector[index] += sign;
  }
  const norm = Math.sqrt(vector.reduce((sum, value) => sum + value * value, 0));
  return norm > 0 ? vector.map((value) => Number((value / norm).toFixed(6))) : vector;
}

function vectorLiteral(values: number[]): string {
  return `[${values.join(",")}]`;
}

async function main() {
  const pool = new pg.Pool({ connectionString: envDatabaseUrl() });
  try {
    await pool.query("CREATE EXTENSION IF NOT EXISTS vector");
    await pool.query("CREATE EXTENSION IF NOT EXISTS pg_trgm");
    await pool.query(`
      CREATE TABLE IF NOT EXISTS hxy_memory_search_documents (
        memory_id TEXT PRIMARY KEY REFERENCES hxy_memory_items(memory_id) ON DELETE CASCADE,
        memory_type TEXT NOT NULL,
        status TEXT NOT NULL,
        project_stage TEXT,
        title TEXT NOT NULL,
        content TEXT NOT NULL,
        source_path TEXT,
        search_vector TSVECTOR GENERATED ALWAYS AS (
          to_tsvector('simple', coalesce(title, '') || ' ' || coalesce(content, ''))
        ) STORED,
        embedding vector(${VECTOR_DIMS}) NOT NULL,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
      )
    `);
    await pool.query(`
      CREATE INDEX IF NOT EXISTS idx_hxy_memory_search_documents_fts
        ON hxy_memory_search_documents USING GIN (search_vector)
    `);
    await pool.query(`
      CREATE INDEX IF NOT EXISTS idx_hxy_memory_search_documents_trgm
        ON hxy_memory_search_documents USING GIN (content gin_trgm_ops)
    `);
    await pool.query(`
      CREATE INDEX IF NOT EXISTS idx_hxy_memory_search_documents_embedding
        ON hxy_memory_search_documents USING hnsw (embedding vector_cosine_ops)
    `);

    const rows = await pool.query<{
      memory_id: string;
      memory_type: string;
      status: string;
      project_stage: string | null;
      title: string;
      body: string;
      source_path: string | null;
    }>(`
      SELECT memory_id, memory_type, status, project_stage, title, body, source_path
      FROM hxy_memory_items
      ORDER BY memory_id
    `);

    for (const row of rows.rows) {
      const content = `${row.title}\n${row.body}`;
      const embedding = vectorLiteral(lexicalEmbedding(`${row.memory_type}\n${row.project_stage ?? ""}\n${content}`));
      await pool.query(
        `
          INSERT INTO hxy_memory_search_documents (
            memory_id, memory_type, status, project_stage, title, content, source_path, embedding, updated_at
          ) VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8::vector, NOW()
          )
          ON CONFLICT (memory_id) DO UPDATE SET
            memory_type = EXCLUDED.memory_type,
            status = EXCLUDED.status,
            project_stage = EXCLUDED.project_stage,
            title = EXCLUDED.title,
            content = EXCLUDED.content,
            source_path = EXCLUDED.source_path,
            embedding = EXCLUDED.embedding,
            updated_at = NOW()
        `,
        [
          row.memory_id,
          row.memory_type,
          row.status,
          row.project_stage,
          row.title,
          content,
          row.source_path,
          embedding,
        ],
      );
    }

    const count = await pool.query("SELECT count(*)::int AS count FROM hxy_memory_search_documents");
    console.log(`[hxy-memory-search] documents=${count.rows[0].count} dims=${VECTOR_DIMS} backend=pgvector+fts`);
  } finally {
    await pool.end();
  }
}

main().catch((error: unknown) => {
  const message = error instanceof Error ? error.message : String(error);
  console.error(`[hxy-memory-search] failed: ${message}`);
  process.exitCode = 1;
});
