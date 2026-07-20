import { afterEach, describe, expect, it, vi } from "vitest";

import {
  productTodayClient,
  TodayRequestError,
  type TodayNextAction,
} from "./today";


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
});
