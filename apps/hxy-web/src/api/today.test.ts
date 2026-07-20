import { afterEach, describe, expect, it, vi } from "vitest";

import {
  productTodayClient,
  TodayRequestError,
  type TodayNextAction,
} from "./today";

const VALID_ITEM = {
  id: "brief-1",
  kind: "risk",
  severity: "high",
  statement: "水电位置仍待确认",
  why_it_matters: "影响施工进度",
  source_record_id: "record-1",
  evidence: [
    {
      source_record_id: "record-1",
      source_asset_id: null,
      quote: "水电位置待确认",
      locator: null,
    },
  ],
  captured_at: "2026-07-20T08:00:00Z",
  next_action: {
    type: "open_record",
    label: "查看记录",
    prompt: null,
  },
};


afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});


describe("productTodayClient", () => {
  it("represents a next action without an optional prompt", () => {
    const action: TodayNextAction = {
      type: "open_record",
      label: "查看记录",
      prompt: null,
    };

    expect(action.prompt).toBeNull();
  });

  it("loads no more than three briefing items with credentials", async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(JSON.stringify({ items: [] }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await productTodayClient.getToday(9);

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/today?limit=3",
      expect.objectContaining({ credentials: "include" }),
    );
  });

  it("uses the default limit for non-finite input", async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(JSON.stringify({ items: [] }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await productTodayClient.getToday(Number.NaN);

    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/today?limit=3");
  });

  it("preserves the response status on request failure", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn<typeof fetch>().mockResolvedValue(
        new Response(JSON.stringify({ detail: "Forbidden" }), {
          status: 403,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );

    await expect(productTodayClient.getToday()).rejects.toEqual(
      expect.objectContaining<Partial<TodayRequestError>>({
        name: "TodayRequestError",
        status: 403,
        detail: "Forbidden",
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

    await expect(productTodayClient.getToday()).rejects.toEqual(
      expect.objectContaining<Partial<TodayRequestError>>({
        name: "TodayRequestError",
        status: 200,
        detail: "Invalid Today response",
      }),
    );
  });

  it.each([
    ["an empty item", { items: [{}] }],
    ["a null item", { items: [null] }],
    [
      "a malformed next action",
      { items: [{ ...VALID_ITEM, next_action: {} }] },
    ],
    [
      "malformed evidence",
      { items: [{ ...VALID_ITEM, evidence: [{}] }] },
    ],
  ])("rejects %s in a success response", async (_name, payload) => {
    vi.stubGlobal(
      "fetch",
      vi.fn<typeof fetch>().mockResolvedValue(
        new Response(JSON.stringify(payload), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );

    await expect(productTodayClient.getToday()).rejects.toEqual(
      expect.objectContaining<Partial<TodayRequestError>>({
        detail: "Invalid Today response",
      }),
    );
  });
});
