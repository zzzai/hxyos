import { afterEach, describe, expect, it, vi } from "vitest";

import { productMaterialClient } from "./materials";
import {
  OrganizationRecordRequestError,
  productRecordClient,
} from "./records";


function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}


afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});


describe("productRecordClient", () => {
  it("lists records with credentials and a bounded limit", async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(
      jsonResponse({ records: [] }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await productRecordClient.listRecords(20);

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/organization-records?limit=20",
      expect.objectContaining({ credentials: "include" }),
    );
  });

  it("encodes a record id before requesting detail", async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(
      jsonResponse({ record: {} }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await productRecordClient.getRecord("record/id with space");

    expect(fetchMock.mock.calls[0][0]).toBe(
      "/api/v1/organization-records/record%2Fid%20with%20space",
    );
  });

  it("sends only the documented record capture fields", async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(
      jsonResponse({ record: {} }, 202),
    );
    vi.stubGlobal("fetch", fetchMock);

    await productRecordClient.createRecord({
      clientRecordId: "record-1",
      text: "装修群记录",
      sourceAssetIds: ["asset-1"],
    });

    const [path, init] = fetchMock.mock.calls[0];
    expect(path).toBe("/api/v1/organization-records");
    expect(init).toEqual(
      expect.objectContaining({ method: "POST", credentials: "include" }),
    );
    expect(new Headers(init?.headers).get("Content-Type")).toBe(
      "application/json",
    );
    expect(JSON.parse(String(init?.body))).toEqual({
      client_record_id: "record-1",
      text: "装修群记录",
      source_asset_ids: ["asset-1"],
    });
  });

  it("uploads a file and then captures it as one organization record", async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(
        jsonResponse({
          material: {
            id: "asset-1",
            file_name: "装修记录.txt",
            media_type: "text/plain",
            size_bytes: 12,
            status: "processing",
            receipt: { status: "已收到", message: "已收到" },
            original: { url: "/api/v1/materials/asset-1", can_preview: true },
            understanding: {
              summary: "",
              document_type: "unknown",
              source_origin: "unknown",
              authority_level: "fragment",
              knowledge_scale: "unknown",
              domain: "general",
              parse_status: "metadata_only",
              confidence: "low",
              warnings: [],
              official_use_allowed: false,
              use_boundary: "待处理",
            },
            created_at: "2026-07-20T08:00:00Z",
            updated_at: "2026-07-20T08:00:00Z",
          },
        }, 202),
      )
      .mockResolvedValueOnce(jsonResponse({ record: {} }, 202));
    vi.stubGlobal("fetch", fetchMock);

    const file = new File(["装修群记录"], "装修记录.txt", {
      type: "text/plain",
    });
    const material = await productMaterialClient.uploadMaterial(
      file,
      "",
      "upload-1",
    );
    await productRecordClient.createRecord({
      clientRecordId: "record-1",
      text: "",
      sourceAssetIds: [material.material.id],
    });

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/materials");
    expect(fetchMock.mock.calls[1][0]).toBe("/api/v1/organization-records");
    expect(JSON.parse(String(fetchMock.mock.calls[1][1]?.body))).toEqual({
      client_record_id: "record-1",
      text: "",
      source_asset_ids: ["asset-1"],
    });
  });

  it("preserves the response status on request failure", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn<typeof fetch>().mockResolvedValue(jsonResponse({}, 409)),
    );

    await expect(
      productRecordClient.createRecord({
        clientRecordId: "duplicate",
        text: "重复提交",
        sourceAssetIds: [],
      }),
    ).rejects.toEqual(
      expect.objectContaining<Partial<OrganizationRecordRequestError>>({
        name: "OrganizationRecordRequestError",
        status: 409,
      }),
    );
  });
});
