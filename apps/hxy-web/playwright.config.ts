import { existsSync } from "node:fs";

import { defineConfig } from "@playwright/test";

type FileExists = (path: string) => boolean;

export function resolveChromiumLaunchOptions(
  candidates: readonly string[] = ["/usr/bin/chromium", "/snap/bin/chromium"],
  explicitPath = process.env.HXY_CHROMIUM_PATH,
  fileExists: FileExists = existsSync,
) {
  const executablePath =
    (explicitPath && fileExists(explicitPath) ? explicitPath : undefined) ??
    candidates.find(fileExists);
  return executablePath ? { executablePath } : {};
}

export default defineConfig({
  testDir: "./tests",
  outputDir: "./node_modules/.cache/playwright-test-results",
  reporter: "list",
  projects: [
    { name: "mobile-360", use: { viewport: { width: 360, height: 800 } } },
    { name: "mobile-390", use: { viewport: { width: 390, height: 844 } } },
    { name: "desktop-1280", use: { viewport: { width: 1280, height: 800 } } },
    { name: "desktop-1440", use: { viewport: { width: 1440, height: 900 } } },
  ],
  use: {
    baseURL: "http://127.0.0.1:4173",
    browserName: "chromium",
    headless: true,
    launchOptions: resolveChromiumLaunchOptions(),
  },
  webServer: {
    command: "npm run dev -- --host 127.0.0.1 --port 4173 --strictPort",
    url: "http://127.0.0.1:4173",
    reuseExistingServer: false,
  },
});
