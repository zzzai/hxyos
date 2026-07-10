import { existsSync } from "node:fs";

import { defineConfig } from "@playwright/test";

const chromiumExecutablePath = ["/usr/bin/chromium", "/snap/bin/chromium"].find(
  existsSync,
);

if (!chromiumExecutablePath) {
  throw new Error("System Chromium was not found");
}

export default defineConfig({
  testDir: "./tests",
  outputDir: "./node_modules/.cache/playwright-test-results",
  reporter: "list",
  use: {
    baseURL: "http://127.0.0.1:4173",
    browserName: "chromium",
    headless: true,
    launchOptions: {
      executablePath: chromiumExecutablePath,
    },
  },
  webServer: {
    command: "npm run dev -- --host 127.0.0.1 --port 4173 --strictPort",
    url: "http://127.0.0.1:4173",
    reuseExistingServer: false,
  },
});
