import { afterEach, describe, expect, it, vi } from "vitest";

import {
  productServiceClient,
  ServiceRequestError,
} from "./services";

const CONTEXT = {
  id: "66000000-0000-0000-0000-000000000001",
  status: "provisional",
  occurred_at: "2026-07-21T09:00:00Z",
  service_label: "足部舒缓服务",
  customer_display: "王女士 · 尾号 1234",
  feedback_count: 0,
  created_at: "2026-07-21T09:00:00Z",
};

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("productServiceClient", () => {
  it("loads recent service contexts with credentials", async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(JSON.stringify({ contexts: [CONTEXT] }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const response = await productServiceClient.listRecent(1);

    expect(response.contexts).toEqual([CONTEXT]);
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/service-contexts/recent?limit=1",
      expect.objectContaining({ credentials: "include" }),
    );
  });

  it.each([
    ["an empty context", { contexts: [{}] }],
    ["a null context", { contexts: [null] }],
    ["an invalid status", { contexts: [{ ...CONTEXT, status: "unknown" }] }],
    ["a malformed count", { contexts: [{ ...CONTEXT, feedback_count: -1 }] }],
  ])("rejects %s in a successful recent response", async (_name, payload) => {
    vi.stubGlobal(
      "fetch",
      vi.fn<typeof fetch>().mockResolvedValue(
        new Response(JSON.stringify(payload), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );

    await expect(productServiceClient.listRecent()).rejects.toEqual(
      expect.objectContaining<Partial<ServiceRequestError>>({
        name: "ServiceRequestError",
        detail: "Invalid service response",
      }),
    );
  });

  it("submits only feedback content and protected asset identifiers", async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(
        JSON.stringify({
          feedback: {
            id: "77000000-0000-0000-0000-000000000001",
            context_id: CONTEXT.id,
            status: "received",
            created_at: "2026-07-21T09:05:00Z",
          },
          context: { ...CONTEXT, feedback_count: 1 },
        }),
        { status: 201, headers: { "Content-Type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    await productServiceClient.addFeedback(CONTEXT.id, {
      clientFeedbackId: "78000000-0000-0000-0000-000000000001",
      text: "顾客反馈力度合适",
      sourceAssetIds: ["79000000-0000-0000-0000-000000000001"],
      durationMs: 42_000,
    });

    const request = fetchMock.mock.calls[0][1] as RequestInit;
    expect(JSON.parse(String(request.body))).toEqual({
      client_feedback_id: "78000000-0000-0000-0000-000000000001",
      text: "顾客反馈力度合适",
      source_asset_ids: ["79000000-0000-0000-0000-000000000001"],
      duration_ms: 42_000,
    });
    expect(String(request.body)).not.toMatch(/organization|store|assignment/);
  });

  it("rejects malformed feedback receipts", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn<typeof fetch>().mockResolvedValue(
        new Response(JSON.stringify({ feedback: {}, context: CONTEXT }), {
          status: 201,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );

    await expect(
      productServiceClient.addFeedback(CONTEXT.id, {
        clientFeedbackId: "78000000-0000-0000-0000-000000000001",
        text: "反馈",
        sourceAssetIds: [],
        durationMs: 1_000,
      }),
    ).rejects.toEqual(
      expect.objectContaining<Partial<ServiceRequestError>>({
        detail: "Invalid service response",
      }),
    );
  });
});
