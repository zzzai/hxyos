import { afterEach, describe, expect, it, vi } from "vitest";

import { productTodayClient, TodayRequestError } from "./today";


afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});


describe("productTodayClient", () => {
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

  it("preserves the response status on request failure", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn<typeof fetch>().mockResolvedValue(new Response(null, { status: 403 })),
    );

    await expect(productTodayClient.getToday()).rejects.toEqual(
      expect.objectContaining<Partial<TodayRequestError>>({
        name: "TodayRequestError",
        status: 403,
      }),
    );
  });
});
