import { describe, expect, it, vi } from "vitest";
import { HxyMemoryStore } from "./store.js";

describe("HxyMemoryStore", () => {
  it("initializes durable HXY memory tables", async () => {
    const query = vi.fn().mockResolvedValue({ rows: [] });
    const store = new HxyMemoryStore({ query } as never);

    await store.initialize();

    const initSql = String(query.mock.calls[0]?.[0] ?? "");
    expect(initSql).toContain("CREATE TABLE IF NOT EXISTS hxy_memory_items");
    expect(initSql).toContain("CREATE TABLE IF NOT EXISTS hxy_memory_evidence_links");
    expect(initSql).toContain("CREATE TABLE IF NOT EXISTS hxy_memory_transitions");
    expect(initSql).toContain("CREATE TABLE IF NOT EXISTS hxy_memory_import_runs");
    expect(initSql).toContain("payload_json JSONB NOT NULL DEFAULT '{}'::jsonb");
  });

  it("upserts and lists memory items with JSON payloads", async () => {
    const query = vi
      .fn()
      .mockResolvedValueOnce({ rows: [] })
      .mockResolvedValueOnce({ rows: [] })
      .mockResolvedValueOnce({
        rows: [
          {
            memory_id: "hxy:decision:current-positioning",
            memory_type: "decision",
            title: "当前定位",
            body: "当前定位收敛为社区泡脚按摩小店。",
            project_stage: "preparation",
            status: "current_candidate",
            confidence: 0.7,
            version: "hxy-memory.v1",
            source_kind: "decision-log",
            source_path: "knowledge/hxy/structured/decision-log.json",
            source_object_id: "hxy_decision_current_positioning",
            payload_json: { decision_key: "current_positioning" },
            created_at: new Date("2026-05-31T01:00:00.000Z"),
            updated_at: new Date("2026-05-31T01:00:00.000Z"),
            review_at: null,
          },
        ],
      });
    const store = new HxyMemoryStore({ query } as never);

    await store.upsertMemoryItem({
      memoryId: "hxy:decision:current-positioning",
      memoryType: "decision",
      title: "当前定位",
      body: "当前定位收敛为社区泡脚按摩小店。",
      projectStage: "preparation",
      status: "current_candidate",
      confidence: 0.7,
      version: "hxy-memory.v1",
      sourceKind: "decision-log",
      sourcePath: "knowledge/hxy/structured/decision-log.json",
      sourceObjectId: "hxy_decision_current_positioning",
      payload: { decision_key: "current_positioning" },
      createdAt: "2026-05-31T01:00:00.000Z",
      updatedAt: "2026-05-31T01:00:00.000Z",
    });

    await expect(
      store.listMemoryItems({ memoryType: "decision", status: "current_candidate", limit: 10 }),
    ).resolves.toEqual([
      expect.objectContaining({
        memoryId: "hxy:decision:current-positioning",
        memoryType: "decision",
        title: "当前定位",
        status: "current_candidate",
        payload: { decision_key: "current_positioning" },
        updatedAt: "2026-05-31T01:00:00.000Z",
      }),
    ]);
    expect(query).toHaveBeenLastCalledWith(
      expect.stringContaining("WHERE memory_type = $1 AND status = $2"),
      ["decision", "current_candidate", 10],
    );
  });

  it("updates item status and appends transition history", async () => {
    const query = vi
      .fn()
      .mockResolvedValueOnce({ rows: [] })
      .mockResolvedValueOnce({ rows: [{ status: "current_candidate" }] })
      .mockResolvedValueOnce({ rows: [] })
      .mockResolvedValueOnce({ rows: [] });
    const store = new HxyMemoryStore({ query } as never);

    await store.transitionMemoryStatus({
      memoryId: "hxy:decision:current-positioning",
      toStatus: "confirmed",
      reason: "人工确认当前定位",
      actor: "founder",
      payload: { source: "manual_review" },
      createdAt: "2026-05-31T02:00:00.000Z",
    });

    expect(query).toHaveBeenNthCalledWith(
      3,
      expect.stringContaining("UPDATE hxy_memory_items"),
      ["confirmed", "2026-05-31T02:00:00.000Z", "hxy:decision:current-positioning"],
    );
    expect(query).toHaveBeenNthCalledWith(
      4,
      expect.stringContaining("INSERT INTO hxy_memory_transitions"),
      [
        "hxy:decision:current-positioning",
        "current_candidate",
        "confirmed",
        "人工确认当前定位",
        "founder",
        JSON.stringify({ source: "manual_review" }),
        "2026-05-31T02:00:00.000Z",
      ],
    );
  });

  it("records import run metadata", async () => {
    const query = vi.fn().mockResolvedValue({ rows: [] });
    const store = new HxyMemoryStore({ query } as never);

    await store.recordImportRun({
      importId: "import-1",
      sourceDir: "knowledge/hxy/structured",
      startedAt: "2026-05-31T01:00:00.000Z",
      finishedAt: "2026-05-31T01:00:01.000Z",
      status: "completed",
      itemCount: 42,
      payload: { files: ["decision-log.json"] },
    });

    expect(query).toHaveBeenLastCalledWith(
      expect.stringContaining("INSERT INTO hxy_memory_import_runs"),
      [
        "import-1",
        "knowledge/hxy/structured",
        "2026-05-31T01:00:00.000Z",
        "2026-05-31T01:00:01.000Z",
        "completed",
        42,
        JSON.stringify({ files: ["decision-log.json"] }),
      ],
    );
  });
});
