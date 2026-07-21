import { afterEach, describe, expect, it, vi } from "vitest";

import { productMaterialClient } from "./materials";
import {
  OrganizationRecordInputError,
  OrganizationRecordRequestError,
  productRecordClient,
  type RecordEvidence,
} from "./records";

const RECORD_ID = "12000000-0000-4000-8000-000000000001";
const ASSET_ID = "13000000-0000-4000-8000-000000000001";
const UPLOAD_ID = "14000000-0000-4000-8000-000000000001";

const VALID_RECORD = {
  id: RECORD_ID,
  source_types: ["text"],
  preview: "装修群记录",
  submitted_by: "周店长",
  store_id: null,
  captured_at: "2026-07-20T08:00:00Z",
  occurred_at: null,
  processing_status: "received",
  original: { text: "装修群记录", assets: [] },
  interpretation: null,
};

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
  it("represents nullable evidence fields returned by the API", () => {
    const value: RecordEvidence = {
      source_record_id: "record-1",
      source_asset_id: null,
      quote: "原文依据",
      locator: null,
    };

    expect(value.source_asset_id).toBeNull();
    expect(value.locator).toBeNull();
  });

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

  it("uses the default list limit for non-finite input", async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(
      jsonResponse({ records: [] }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await productRecordClient.listRecords(Number.NaN);

    expect(fetchMock.mock.calls[0][0]).toBe(
      "/api/v1/organization-records?limit=50",
    );
  });

  it("encodes a record id before requesting detail", async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(
      jsonResponse({ record: VALID_RECORD }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await productRecordClient.getRecord("record/id with space");

    expect(fetchMock.mock.calls[0][0]).toBe(
      "/api/v1/organization-records/record%2Fid%20with%20space",
    );
  });

  it("sends only the documented record capture fields", async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(
      jsonResponse({ record: VALID_RECORD }, 202),
    );
    vi.stubGlobal("fetch", fetchMock);

    await productRecordClient.createRecord({
      clientRecordId: RECORD_ID,
      text: "装修群记录",
      sourceAssetIds: [ASSET_ID],
      purpose: "closing_review",
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
      client_record_id: RECORD_ID,
      text: "装修群记录",
      source_asset_ids: [ASSET_ID],
      purpose: "closing_review",
    });
  });

  it("rejects an invalid capture before making a request", async () => {
    const fetchMock = vi.fn<typeof fetch>();
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      productRecordClient.createRecord({
        clientRecordId: "not-a-uuid",
        text: " ",
        sourceAssetIds: [],
      }),
    ).rejects.toBeInstanceOf(OrganizationRecordInputError);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("uploads a file and then captures it as one organization record", async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(
        jsonResponse({
          material: {
            id: ASSET_ID,
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
      .mockResolvedValueOnce(jsonResponse({ record: VALID_RECORD }, 202));
    vi.stubGlobal("fetch", fetchMock);

    const file = new File(["装修群记录"], "装修记录.txt", {
      type: "text/plain",
    });
    const material = await productMaterialClient.uploadMaterial(
      file,
      "",
      UPLOAD_ID,
    );
    await productRecordClient.createRecord({
      clientRecordId: RECORD_ID,
      text: "",
      sourceAssetIds: [material.material.id],
    });

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/materials");
    expect(fetchMock.mock.calls[1][0]).toBe("/api/v1/organization-records");
    expect(JSON.parse(String(fetchMock.mock.calls[1][1]?.body))).toEqual({
      client_record_id: RECORD_ID,
      text: "",
      source_asset_ids: [ASSET_ID],
      purpose: "general",
    });
  });

  it("preserves the response status on request failure", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn<typeof fetch>().mockResolvedValue(
        jsonResponse({ detail: "Idempotency key conflict" }, 409),
      ),
    );

    await expect(
      productRecordClient.createRecord({
        clientRecordId: RECORD_ID,
        text: "重复提交",
        sourceAssetIds: [],
      }),
    ).rejects.toEqual(
      expect.objectContaining<Partial<OrganizationRecordRequestError>>({
        name: "OrganizationRecordRequestError",
        status: 409,
        detail: "Idempotency key conflict",
      }),
    );
  });

  it("normalizes a malformed success response to the client error type", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn<typeof fetch>().mockResolvedValue(
        new Response("not-json", {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );

    await expect(productRecordClient.listRecords()).rejects.toEqual(
      expect.objectContaining<Partial<OrganizationRecordRequestError>>({
        name: "OrganizationRecordRequestError",
        status: 200,
        detail: "Invalid organization record response",
      }),
    );
  });

  it.each([
    ["an empty record", { record: {} }],
    ["a null list item", { records: [null] }],
    [
      "a malformed nested asset",
      {
        record: {
          ...VALID_RECORD,
          original: { text: "装修群记录", assets: [{}] },
        },
      },
    ],
    [
      "a malformed interpretation",
      {
        record: {
          ...VALID_RECORD,
          interpretation: { summary: "缺少其余结构" },
        },
      },
    ],
  ])("rejects %s in a success response", async (_name, payload) => {
    vi.stubGlobal(
      "fetch",
      vi.fn<typeof fetch>().mockResolvedValue(jsonResponse(payload)),
    );

    const request = "records" in payload
      ? productRecordClient.listRecords()
      : productRecordClient.getRecord(RECORD_ID);

    await expect(request).rejects.toEqual(
      expect.objectContaining<Partial<OrganizationRecordRequestError>>({
        detail: "Invalid organization record response",
      }),
    );
  });

  it("normalizes FastAPI array-form validation errors", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn<typeof fetch>().mockResolvedValue(
        jsonResponse(
          {
            detail: [
              {
                type: "string_too_long",
                loc: ["body", "text"],
                msg: "String should have at most 20000 characters",
                input: "private input must not leak",
              },
            ],
          },
          422,
        ),
      ),
    );

    await expect(
      productRecordClient.createRecord({
        clientRecordId: RECORD_ID,
        text: "提交内容",
        sourceAssetIds: [],
      }),
    ).rejects.toEqual(
      expect.objectContaining<Partial<OrganizationRecordRequestError>>({
        detail: "text: String should have at most 20000 characters",
      }),
    );
  });
});
