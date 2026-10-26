// Unit tests only (src/**/*.test.ts). Browser flows in e2e/ run with Playwright: npm run test:e2e.
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: { include: ["src/**/*.test.ts"], environment: "node" },
});
