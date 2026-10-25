// End-to-end test of the sidecar against the real vendored H-MEM engine.
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { after, before, test } from "node:test";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const PORT = 18765 + Math.floor(Math.random() * 500);
const BASE = `http://127.0.0.1:${PORT}`;
const stateDir = fs.mkdtempSync(path.join(os.tmpdir(), "hmem-test-"));
let proc: ReturnType<typeof spawn>;

async function post(p: string, body: unknown) {
  const r = await fetch(BASE + p, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
  return { status: r.status, body: await r.json() };
}

before(async () => {
  proc = spawn(process.execPath, ["--import", "tsx", path.join(here, "..", "server.ts")], {
    env: { ...process.env, HMEM_PORT: String(PORT), HMEM_STATE_DIR: stateDir },
    stdio: "pipe",
  });
  for (let i = 0; i < 50; i++) {
    try {
      if ((await fetch(BASE + "/health")).ok) return;
    } catch {}
    await new Promise((r) => setTimeout(r, 100));
  }
  throw new Error("sidecar did not start");
});

after(() => {
  proc.kill();
  fs.rmSync(stateDir, { recursive: true, force: true });
});

const fact = (value: number, filed: string) => ({
  key: "TST:revenue:2024-12-31",
  content: "TST revenue for the fiscal year ending 2024-12-31",
  value,
  source: `sec:accn-${filed}`,
  refs: ["https://example.invalid/filing"],
  filed,
});

test("health names the engine source", async () => {
  const h = await (await fetch(BASE + "/health")).json();
  assert.equal(h.ok, true);
  assert.match(h.engine_source, /vendor\/hmem/);
});

test("new fact, re-confirmation, then a conflicting later filing", async () => {
  const first = await post("/facts", { ticker: "TST", facts: [fact(100, "2025-02-01")] });
  assert.equal(first.body.results[0].outcome, "new");
  const id = first.body.results[0].memory.id;

  const again = await post("/facts", { ticker: "TST", facts: [fact(100, "2025-02-01")] });
  assert.equal(again.body.results[0].outcome, "confirmed");
  assert.ok(again.body.results[0].memory.confidence > first.body.results[0].memory.confidence);

  const revised = await post("/facts", { ticker: "TST", facts: [fact(95, "2026-02-01")] });
  const r = revised.body.results[0];
  assert.equal(r.outcome, "conflict");
  assert.match(r.conflicts[0].resolution, /superseded/);

  const audit = await (await fetch(`${BASE}/memories/${id}/audit`)).json();
  const actions = audit.history.map((e: any) => e.action);
  assert.ok(actions.includes("create") && actions.includes("feedback") && actions.includes("conflict_detected") && actions.includes("conflict_resolved"));
  assert.equal(audit.memory.supersededBy, r.memory.id);
});

test("a fact without a source is rejected", async () => {
  const res = await post("/facts", { ticker: "TST", facts: [{ key: "k", content: "c", value: 1 }] });
  assert.equal(res.body.results[0].outcome, "rejected");
});

test("recall is isolated per company", async () => {
  await post("/notes", { ticker: "OTH", content: "OTH profit rose while cash flow fell", source: "finsight:inv-1" });
  const res = await post("/recall", { ticker: "TST", query: "TST revenue fiscal year" });
  assert.ok(res.body.memories.length > 0);
  assert.ok(res.body.memories.every((m: any) => m.memory.chatId === "TST"));
});
