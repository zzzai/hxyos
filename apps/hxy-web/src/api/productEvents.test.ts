import { afterEach, describe, expect, it, vi } from "vitest";

import { productEventClient } from "./productEvents";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("productEventClient", () => {
  it("sends only the fixed privacy-safe event contract", async () => {
    const fetch = vi.fn().mockResolvedValue({ ok: true });
    vi.stubGlobal("fetch", fetch);

    const tracked = await productEventClient.track({
      clientEventId: "10000000-0000-0000-0000-000000000001",
      eventName: "briefing_feedback",
      subjectId: "10000000-0000-0000-0000-000000000002",
      useful: true,
    });

    expect(fetch).toHaveBeenCalledWith(
      "/api/v1/product-events",
      expect.objectContaining({
        method: "POST",
        credentials: "include",
        body: JSON.stringify({
          client_event_id: "10000000-0000-0000-0000-000000000001",
          event_name: "briefing_feedback",
          subject_id: "10000000-0000-0000-0000-000000000002",
          useful: true,
        }),
      }),
    );
    expect(tracked).toBe(true);
  });

  it("never blocks the operating action when telemetry is unavailable", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));

    await expect(
      productEventClient.track({
        clientEventId: "10000000-0000-0000-0000-000000000001",
        eventName: "briefing_feedback",
        subjectId: "10000000-0000-0000-0000-000000000002",
        useful: false,
      }),
    ).resolves.toBe(false);
  });

  it("reports an HTTP rejection without throwing", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false }));

    await expect(
      productEventClient.track({
        clientEventId: "10000000-0000-0000-0000-000000000001",
        eventName: "briefing_feedback",
        subjectId: "10000000-0000-0000-0000-000000000002",
        useful: true,
      }),
    ).resolves.toBe(false);
  });
});
