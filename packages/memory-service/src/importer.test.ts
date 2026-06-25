import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { describe, expect, it, vi } from "vitest";
import {
  buildHxyMemoryImportItemsFromStructuredDir,
  importHxyMemoryFromStructuredDir,
} from "./importer.js";

async function writeJson(filePath: string, value: unknown): Promise<void> {
  await fs.mkdir(path.dirname(filePath), { recursive: true });
  await fs.writeFile(filePath, `${JSON.stringify(value, null, 2)}\n`, "utf8");
}

describe("HXY memory importer", () => {
  it("builds memory items from HXY structured assets", async () => {
    const rootDir = await fs.mkdtemp(path.join(os.tmpdir(), "hxy-memory-import-"));
    const structuredDir = path.join(rootDir, "knowledge", "hxy", "structured");
    await writeJson(path.join(structuredDir, "claims.json"), [
      {
        claim_id: "claim-store-model",
        claim_type: "financial_assumption",
        claim: "样板店回本周期需要用真实房租和技师人数验证。",
        stage: "pilot_store",
        status: "current_candidate",
        confidence: 0.62,
        evidence_ids: ["ev-1"],
        needs_validation: true,
      },
    ]);
    await writeJson(path.join(structuredDir, "decision-log.json"), {
      version: "hxy-decision-log.v1",
      decisions: [
        {
          decision_id: "decision-current-positioning",
          decision_key: "current_positioning",
          title: "当前定位",
          decision: "当前先讲社区泡脚按摩小店。",
          rationale: "筹备期和样板店期要先收敛。",
          project_stage: "preparation",
          status: "current_candidate",
          confidence: 0.7,
          evidence_ids: ["ev-2"],
          evidence: [{ evidence_id: "ev-2", relative_path: "raw/a.pdf", snippet: "社区小店定位" }],
        },
      ],
    });
    await writeJson(path.join(structuredDir, "governance-report.json"), {
      version: "hxy-knowledge-governance.v1",
      review_queue: [
        {
          review_type: "confirm_current",
          claim_id: "claim-store-model",
          reason: "确认该财务假设是否进入当前候选。",
        },
      ],
      conflicts: [
        {
          conflict_id: "conflict-positioning",
          severity: "high",
          reason: "社区小店定位和银发健康科技平台不能同时作为当前主定位。",
          recommended_resolution: "当前主定位先用社区小店，平台作为远期愿景。",
        },
      ],
    });
    await writeJson(path.join(structuredDir, "pilot-validation-matrix.json"), {
      version: "hxy-pilot-validation-matrix.v1",
      items: [
        {
          item_id: "validate-payback",
          title: "验证回本周期",
          metric: "payback_months",
          target: "8个月以内",
          method: "采集真实投资、房租、人工和现金流。",
        },
      ],
    });
    await writeJson(path.join(structuredDir, "osi-contract.json"), {
      version: "hxy-osi-contract.v1",
      governance: {
        open_review_items: [
          {
            conflict_id: "osi-conflict-positioning",
            severity: "high",
            reason: "远期愿景不能替代当前门店口径。",
            recommended_resolution: "分层表达。",
          },
        ],
      },
    });

    const result = await buildHxyMemoryImportItemsFromStructuredDir({
      structuredDir,
      now: () => new Date("2026-05-31T01:00:00.000Z"),
    });

    expect(result.items).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          memoryId: "hxy:claim:claim-store-model",
          memoryType: "claim",
          status: "current_candidate",
        }),
        expect.objectContaining({
          memoryId: "hxy:hypothesis:claim-store-model",
          memoryType: "hypothesis",
          status: "current_candidate",
        }),
        expect.objectContaining({
          memoryId: "hxy:decision:decision-current-positioning",
          memoryType: "decision",
          title: "当前定位",
        }),
        expect.objectContaining({
          memoryId: "hxy:review_task:confirm_current:claim-store-model",
          memoryType: "review_task",
          status: "open",
        }),
        expect.objectContaining({
          memoryId: "hxy:conflict:conflict-positioning",
          memoryType: "conflict",
          status: "conflicted",
        }),
        expect.objectContaining({
          memoryId: "hxy:validation_task:validate-payback",
          memoryType: "validation_task",
          status: "open",
        }),
        expect.objectContaining({
          memoryId: "hxy:conflict:osi-conflict-positioning",
          memoryType: "conflict",
          sourceKind: "osi-contract",
        }),
      ]),
    );
    expect(result.evidenceLinks).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          memoryId: "hxy:decision:decision-current-positioning",
          evidenceId: "ev-2",
          sourcePath: "raw/a.pdf",
        }),
      ]),
    );

    await fs.rm(rootDir, { recursive: true, force: true });
  });

  it("imports built memory items idempotently into the store", async () => {
    const rootDir = await fs.mkdtemp(path.join(os.tmpdir(), "hxy-memory-store-import-"));
    const structuredDir = path.join(rootDir, "knowledge", "hxy", "structured");
    await writeJson(path.join(structuredDir, "decision-log.json"), {
      decisions: [
        {
          decision_id: "decision-current-positioning",
          title: "当前定位",
          decision: "当前先讲社区泡脚按摩小店。",
          project_stage: "preparation",
          status: "current_candidate",
        },
      ],
    });

    const store = {
      initialize: vi.fn().mockResolvedValue(undefined),
      upsertMemoryItem: vi.fn().mockResolvedValue(undefined),
      upsertEvidenceLinks: vi.fn().mockResolvedValue(undefined),
      recordImportRun: vi.fn().mockResolvedValue(undefined),
    };

    await importHxyMemoryFromStructuredDir({
      store,
      structuredDir,
      importId: "import-1",
      now: () => new Date("2026-05-31T01:00:00.000Z"),
    });
    await importHxyMemoryFromStructuredDir({
      store,
      structuredDir,
      importId: "import-2",
      now: () => new Date("2026-05-31T01:00:00.000Z"),
    });

    expect(store.upsertMemoryItem).toHaveBeenCalledTimes(2);
    expect(store.upsertMemoryItem).toHaveBeenNthCalledWith(
      1,
      expect.objectContaining({ memoryId: "hxy:decision:decision-current-positioning" }),
    );
    expect(store.upsertMemoryItem).toHaveBeenNthCalledWith(
      2,
      expect.objectContaining({ memoryId: "hxy:decision:decision-current-positioning" }),
    );
    expect(store.recordImportRun).toHaveBeenLastCalledWith(
      expect.objectContaining({
        importId: "import-2",
        status: "completed",
        itemCount: 1,
      }),
    );

    await fs.rm(rootDir, { recursive: true, force: true });
  });
});
