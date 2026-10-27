// End-to-end tests: a real browser drives the app against its own private backend.
// Offline and reproducible: sample data only, no AI model, no keys, and a fresh temporary
// database and H-MEM memory each run. Your real .env values, database and memory are never used.
import { defineConfig, devices } from "@playwright/test";
import os from "node:os";
import path from "node:path";

const PORTS = { hmem: 8767, backend: 8011, web: 5177 };
// Set once in the main process; worker processes inherit it, so every part of a run shares one folder.
process.env.FINSIGHT_E2E_STATE ??= path.join(os.tmpdir(), `finsight-e2e-${Date.now()}`);
const STATE = process.env.FINSIGHT_E2E_STATE;

const backendEnv: Record<string, string> = {
  ...(process.env as Record<string, string>),
  DATABASE_URL: `sqlite:///${path.join(STATE, "e2e.db")}`,
  HMEM_URL: `http://127.0.0.1:${PORTS.hmem}`,
  FINSIGHT_DATA_MODE: "sample",
  FINSIGHT_CACHE_DIR: path.join(STATE, "cache"),
  PARALLAX_LOG_DIR: path.join(STATE, "logs"),
  LLM_PROVIDER: "none",
  // Explicit empty values win over the repo's .env (it is loaded with override=False).
  METERLESS_RUNTIME_TOKEN: "",
  ZETARIS_ORG_ID: "", ZETARIS_API_KEY: "", ZETARIS_USERNAME: "", ZETARIS_PASSWORD: "",
  SEC_USER_AGENT: "", ZETARIS_USER_AGENT: "",
  WATCHLIST_CHECK_MINUTES: "0",
};

export default defineConfig({
  testDir: "./e2e",
  globalTeardown: "./e2e/teardown.ts",
  fullyParallel: false,
  workers: 1, // the tests share one backend, so they run in order
  retries: process.env.CI ? 1 : 0,
  timeout: 60_000,
  expect: { timeout: 15_000 },
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: `http://127.0.0.1:${PORTS.web}`,
    viewport: { width: 1536, height: 1024 },
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"], viewport: { width: 1536, height: 1024 } } }],
  webServer: [
    {
      command: `npm start --prefix ../services/hmem-sidecar`,
      url: `http://127.0.0.1:${PORTS.hmem}/health`,
      env: { ...(process.env as Record<string, string>), HMEM_PORT: String(PORTS.hmem), HMEM_STATE_DIR: path.join(STATE, "hmem") },
      reuseExistingServer: false,
      timeout: 60_000,
    },
    {
      command: `../backend/.venv/bin/uvicorn app.main:app --app-dir ../backend --host 127.0.0.1 --port ${PORTS.backend}`,
      url: `http://127.0.0.1:${PORTS.backend}/health`,
      env: backendEnv,
      reuseExistingServer: false,
      timeout: 90_000,
    },
    {
      command: `npx vite --host 127.0.0.1 --port ${PORTS.web} --strictPort`,
      url: `http://127.0.0.1:${PORTS.web}`,
      env: { ...(process.env as Record<string, string>), VITE_BACKEND_URL: `http://127.0.0.1:${PORTS.backend}` },
      reuseExistingServer: false,
      timeout: 60_000,
    },
  ],
});
