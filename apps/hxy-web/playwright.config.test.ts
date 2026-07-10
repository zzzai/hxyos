import { describe, expect, it } from "vitest";

import { resolveChromiumLaunchOptions } from "./playwright.config";

describe("Playwright Chromium resolution", () => {
  it("falls back to Playwright-managed Chromium when no system executable exists", () => {
    expect(resolveChromiumLaunchOptions([], undefined, () => false)).toEqual({});
  });

  it("honors an explicit Chromium path before system candidates", () => {
    expect(
      resolveChromiumLaunchOptions(
        ["/system/chromium"],
        "/custom/chromium",
        () => true,
      ),
    ).toEqual({ executablePath: "/custom/chromium" });
  });
});
