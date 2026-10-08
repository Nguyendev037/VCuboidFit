import { defineConfig, devices } from "@playwright/test";

// Cổng mặc định 3000; đặt PW_BASE_URL để chạy dev server ở cổng khác.
export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  reporter: "list",
  use: {
    baseURL: process.env.PW_BASE_URL ?? "http://127.0.0.1:3000",
    viewport: { width: 1440, height: 900 },
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } }],
});
