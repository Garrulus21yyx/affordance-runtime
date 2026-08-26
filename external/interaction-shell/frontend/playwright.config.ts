import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  expect: { timeout: 8_000 },
  use: { baseURL: "http://127.0.0.1:3100", trace: "retain-on-failure" },
  webServer: [
    {
      command: "INTERACTION_SHELL_DEMO=true ../backend/.venv/bin/uvicorn interaction_shell.api:app --host 127.0.0.1 --port 8100",
      url: "http://127.0.0.1:8100/health",
      reuseExistingServer: false,
      timeout: 30_000,
    },
    {
      command: "SHELL_BACKEND_URL=http://127.0.0.1:8100 npm run dev -- --hostname 127.0.0.1 --port 3100",
      url: "http://127.0.0.1:3100",
      reuseExistingServer: false,
      timeout: 60_000,
    },
  ],
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
