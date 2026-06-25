import type { Pool } from "pg";
import type {
  HxyMemoryEvidenceLink,
  HxyMemoryImportRun,
  HxyMemoryItem,
  HxyMemoryItemFilter,
  HxyMemoryStatus,
  HxyMemoryTransition,
} from "./types.js";

type Queryable = Pick<Pool, "query">;

function normalizeTimestampField(value: unknown): string | undefined {
  if (typeof value === "string" && value.trim().length > 0) {
    return value;
  }
  if (value instanceof Date && Number.isFinite(value.getTime())) {
    return value.toISOString();
  }
  return undefined;
}

function parseObjectRecord(value: unknown): Record<string, unknown> {
  if (!value) {
    return {};
  }
  if (typeof value === "string") {
    try {
      const parsed = JSON.parse(value) as unknown;
      return parsed && typeof parsed === "object" && !Array.isArray(parsed)
        ? (parsed as Record<string, unknown>)
        : {};
    } catch {
      return {};
    }
  }
  return typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function normalizeNumber(value: unknown): number | undefined {
  const numeric = typeof value === "number" ? value : typeof value === "string" ? Number(value) : NaN;
  return Number.isFinite(numeric) ? numeric : undefined;
}

function mapMemoryItemRow(row: Record<string, unknown>): HxyMemoryItem {
  return {
    memoryId: String(row.memory_id),
    memoryType: String(row.memory_type) as HxyMemoryItem["memoryType"],
    title: String(row.title ?? ""),
    body: String(row.body ?? ""),
    projectStage: typeof row.project_stage === "string" ? row.project_stage : undefined,
    status: String(row.status) as HxyMemoryStatus,
    confidence: normalizeNumber(row.confidence),
    version: String(row.version ?? ""),
    sourceKind: String(row.source_kind ?? ""),
    sourcePath: typeof row.source_path === "string" ? row.source_path : undefined,
    sourceObjectId: typeof row.source_object_id === "string" ? row.source_object_id : undefined,
    payload: parseObjectRecord(row.payload_json),
    createdAt: normalizeTimestampField(row.created_at) ?? String(row.created_at ?? ""),
    updatedAt: normalizeTimestampField(row.updated_at) ?? String(row.updated_at ?? ""),
    reviewAt: normalizeTimestampField(row.review_at),
  };
}

export class HxyMemoryStore {
  private initialized = false;

  constructor(private readonly queryable: Queryable) {}

  async initialize(): Promise<void> {
    if (this.initialized) {
      return;
    }
    await this.queryable.query(`
      CREATE TABLE IF NOT EXISTS hxy_memory_items (
        memory_id TEXT PRIMARY KEY,
        memory_type TEXT NOT NULL,
        title TEXT NOT NULL,
        body TEXT NOT NULL,
        project_stage TEXT,
        status TEXT NOT NULL,
        confidence DOUBLE PRECISION,
        version TEXT NOT NULL,
        source_kind TEXT NOT NULL,
        source_path TEXT,
        source_object_id TEXT,
        payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at TIMESTAMPTZ NOT NULL,
        updated_at TIMESTAMPTZ NOT NULL,
        review_at TIMESTAMPTZ
      );

      CREATE INDEX IF NOT EXISTS idx_hxy_memory_items_type_status
        ON hxy_memory_items (memory_type, status, updated_at DESC);

      CREATE INDEX IF NOT EXISTS idx_hxy_memory_items_stage
        ON hxy_memory_items (project_stage, updated_at DESC);

      CREATE TABLE IF NOT EXISTS hxy_memory_evidence_links (
        memory_id TEXT NOT NULL,
        evidence_id TEXT NOT NULL,
        source_path TEXT,
        snippet TEXT,
        payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
        PRIMARY KEY (memory_id, evidence_id)
      );

      CREATE INDEX IF NOT EXISTS idx_hxy_memory_evidence_links_evidence_id
        ON hxy_memory_evidence_links (evidence_id);

      CREATE TABLE IF NOT EXISTS hxy_memory_transitions (
        transition_id BIGSERIAL PRIMARY KEY,
        memory_id TEXT NOT NULL,
        from_status TEXT,
        to_status TEXT NOT NULL,
        reason TEXT,
        actor TEXT,
        payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at TIMESTAMPTZ NOT NULL
      );

      CREATE INDEX IF NOT EXISTS idx_hxy_memory_transitions_memory_id
        ON hxy_memory_transitions (memory_id, created_at DESC);

      CREATE TABLE IF NOT EXISTS hxy_memory_import_runs (
        import_id TEXT PRIMARY KEY,
        source_dir TEXT NOT NULL,
        started_at TIMESTAMPTZ NOT NULL,
        finished_at TIMESTAMPTZ,
        status TEXT NOT NULL,
        item_count INTEGER NOT NULL DEFAULT 0,
        payload_json JSONB NOT NULL DEFAULT '{}'::jsonb
      );
    `);
    this.initialized = true;
  }

  async upsertMemoryItem(item: HxyMemoryItem): Promise<void> {
    await this.initialize();
    await this.queryable.query(
      `
        INSERT INTO hxy_memory_items (
          memory_id, memory_type, title, body, project_stage, status, confidence,
          version, source_kind, source_path, source_object_id, payload_json,
          created_at, updated_at, review_at
        ) VALUES (
          $1, $2, $3, $4, $5, $6, $7,
          $8, $9, $10, $11, $12::jsonb,
          $13, $14, $15
        )
        ON CONFLICT (memory_id) DO UPDATE SET
          memory_type = EXCLUDED.memory_type,
          title = EXCLUDED.title,
          body = EXCLUDED.body,
          project_stage = EXCLUDED.project_stage,
          status = EXCLUDED.status,
          confidence = EXCLUDED.confidence,
          version = EXCLUDED.version,
          source_kind = EXCLUDED.source_kind,
          source_path = EXCLUDED.source_path,
          source_object_id = EXCLUDED.source_object_id,
          payload_json = EXCLUDED.payload_json,
          updated_at = EXCLUDED.updated_at,
          review_at = EXCLUDED.review_at
      `,
      [
        item.memoryId,
        item.memoryType,
        item.title,
        item.body,
        item.projectStage ?? null,
        item.status,
        item.confidence ?? null,
        item.version,
        item.sourceKind,
        item.sourcePath ?? null,
        item.sourceObjectId ?? null,
        JSON.stringify(item.payload ?? {}),
        item.createdAt,
        item.updatedAt,
        item.reviewAt ?? null,
      ],
    );
  }

  async upsertEvidenceLinks(memoryId: string, links: HxyMemoryEvidenceLink[]): Promise<void> {
    await this.initialize();
    await this.queryable.query("DELETE FROM hxy_memory_evidence_links WHERE memory_id = $1", [memoryId]);
    for (const link of links) {
      await this.queryable.query(
        `
          INSERT INTO hxy_memory_evidence_links (
            memory_id, evidence_id, source_path, snippet, payload_json
          ) VALUES (
            $1, $2, $3, $4, $5::jsonb
          )
          ON CONFLICT (memory_id, evidence_id) DO UPDATE SET
            source_path = EXCLUDED.source_path,
            snippet = EXCLUDED.snippet,
            payload_json = EXCLUDED.payload_json
        `,
        [
          memoryId,
          link.evidenceId,
          link.sourcePath ?? null,
          link.snippet ?? null,
          JSON.stringify(link.payload ?? {}),
        ],
      );
    }
  }

  async getMemoryItem(memoryId: string): Promise<HxyMemoryItem | null> {
    await this.initialize();
    const result = await this.queryable.query(
      `
        SELECT *
        FROM hxy_memory_items
        WHERE memory_id = $1
        LIMIT 1
      `,
      [memoryId],
    );
    const row = result.rows[0] as Record<string, unknown> | undefined;
    return row ? mapMemoryItemRow(row) : null;
  }

  async listMemoryItems(filter: HxyMemoryItemFilter = {}): Promise<HxyMemoryItem[]> {
    await this.initialize();
    const clauses: string[] = [];
    const values: unknown[] = [];
    if (filter.memoryType) {
      values.push(filter.memoryType);
      clauses.push(`memory_type = $${values.length}`);
    }
    if (filter.status) {
      values.push(filter.status);
      clauses.push(`status = $${values.length}`);
    }
    if (filter.projectStage) {
      values.push(filter.projectStage);
      clauses.push(`project_stage = $${values.length}`);
    }
    const limit = Math.max(1, Math.min(500, Math.trunc(filter.limit ?? 100)));
    values.push(limit);
    const whereSql = clauses.length > 0 ? `WHERE ${clauses.join(" AND ")}` : "";
    const result = await this.queryable.query(
      `
        SELECT *
        FROM hxy_memory_items
        ${whereSql}
        ORDER BY updated_at DESC, memory_id ASC
        LIMIT $${values.length}
      `,
      values,
    );
    return result.rows.map((row: Record<string, unknown>) => mapMemoryItemRow(row));
  }

  async transitionMemoryStatus(params: {
    memoryId: string;
    toStatus: HxyMemoryStatus;
    reason?: string;
    actor?: string;
    payload?: Record<string, unknown>;
    createdAt: string;
  }): Promise<void> {
    await this.initialize();
    const current = await this.queryable.query(
      "SELECT status FROM hxy_memory_items WHERE memory_id = $1 LIMIT 1",
      [params.memoryId],
    );
    const fromStatus =
      typeof current.rows[0]?.status === "string"
        ? (current.rows[0].status as HxyMemoryStatus)
        : undefined;
    await this.queryable.query(
      `
        UPDATE hxy_memory_items
        SET status = $1, updated_at = $2
        WHERE memory_id = $3
      `,
      [params.toStatus, params.createdAt, params.memoryId],
    );
    await this.queryable.query(
      `
        INSERT INTO hxy_memory_transitions (
          memory_id, from_status, to_status, reason, actor, payload_json, created_at
        ) VALUES (
          $1, $2, $3, $4, $5, $6::jsonb, $7
        )
      `,
      [
        params.memoryId,
        fromStatus ?? null,
        params.toStatus,
        params.reason ?? null,
        params.actor ?? null,
        JSON.stringify(params.payload ?? {}),
        params.createdAt,
      ],
    );
  }

  async recordImportRun(run: HxyMemoryImportRun): Promise<void> {
    await this.initialize();
    await this.queryable.query(
      `
        INSERT INTO hxy_memory_import_runs (
          import_id, source_dir, started_at, finished_at, status, item_count, payload_json
        ) VALUES (
          $1, $2, $3, $4, $5, $6, $7::jsonb
        )
        ON CONFLICT (import_id) DO UPDATE SET
          source_dir = EXCLUDED.source_dir,
          started_at = EXCLUDED.started_at,
          finished_at = EXCLUDED.finished_at,
          status = EXCLUDED.status,
          item_count = EXCLUDED.item_count,
          payload_json = EXCLUDED.payload_json
      `,
      [
        run.importId,
        run.sourceDir,
        run.startedAt,
        run.finishedAt ?? null,
        run.status,
        run.itemCount,
        JSON.stringify(run.payload ?? {}),
      ],
    );
  }
}
