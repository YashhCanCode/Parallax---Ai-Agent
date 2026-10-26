// Deletes this run's temporary database and memory folder (see playwright.config.ts).
import fs from "node:fs";

export default function teardown() {
  const dir = process.env.FINSIGHT_E2E_STATE;
  if (dir && dir.includes("finsight-e2e-")) fs.rmSync(dir, { recursive: true, force: true });
}
