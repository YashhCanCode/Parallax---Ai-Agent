// Parallax memory sidecar: exposes the Meterless H-MEM reference engine over HTTP so the
// Python backend can use it. Every route maps to a named H-MEM service:
//
//   POST /facts            MemoryStoreService.add + TrustLedgerService (conflict_detected /
//                          conflict_resolved) + MemoryRetrievalService.feedback (re-observed)
//   POST /notes            MemoryStoreService.add
//   POST /recall           MemoryRetrievalService.query (hybrid ranking, reinjection, trace)
//   GET  /memories/:id/audit  TrustLedgerService.history (append-only)
//   GET  /health, /stats   engine source, record counts, ledger action counts
//
// Memories are namespaced per company through H-MEM's chatId field, so recall for one
// ticker never returns another company's memories.
//
// Conflict rule: the reference ConflictDetectionService flags any two very similar texts
// with different numbers, which would wrongly flag "revenue FY2023 = X" against "revenue
// FY2024 = Y". Parallax instead keys each financial fact by company + metric + period
// (tag `fact:<key>`). A different value for the same key is a real conflict; it is logged to
// the H-MEM trust ledger and the older-filed record is marked supersededBy (kept, penalized
// in ranking, never deleted), exactly as AGENTS.md section 10 prescribes.

import fs from "node:fs";
import http from "node:http";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const PORT = Number(process.env.HMEM_PORT ?? 8765);
const HOST = process.env.HMEM_HOST ?? "127.0.0.1";
const STATE_DIR = process.env.HMEM_STATE_DIR ?? path.join(here, ".hmem-state");

const CANDIDATES = [
  { label: "vendor/hmem (degit of meterless/meterless engines/hmem/reference)", entry: path.join(here, "vendor", "hmem", "src", "index.ts") },
];

async function loadEngine(): Promise<{ HMEM: any; source: string }> {
  for (const c of CANDIDATES) {
    if (fs.existsSync(c.entry)) {
      const mod = await import(pathToFileURL(c.entry).href);
      return { HMEM: mod.HMEM, source: c.label };
    }
  }
  console.error("H-MEM engine not found. Run `npm run setup` in services/hmem-sidecar first.");
  process.exit(1);
}

type Json = Record<string, any>;

function publicRecord(r: any): Json {
  const { embedding, ...rest } = r;
  return rest;
}

async function readBody(req: http.IncomingMessage): Promise<Json> {
  const chunks: Buffer[] = [];
  let size = 0;
  for await (const chunk of req) {
    size += (chunk as Buffer).length;
    if (size > 2_000_000) throw new Error("body too large");
    chunks.push(chunk as Buffer);
  }
  if (!chunks.length) return {};
  return JSON.parse(Buffer.concat(chunks).toString("utf-8"));
}

function send(res: http.ServerResponse, status: number, body: unknown): void {
  const data = JSON.stringify(body);
  res.writeHead(status, { "content-type": "application/json", "content-length": Buffer.byteLength(data) });
  res.end(data);
}

const ACTOR = "finsight-agent";

async function main(): Promise<void> {
  const { HMEM, source } = await loadEngine();
  const hmem = new HMEM({ persistDir: STATE_DIR, actor: ACTOR });
  console.log(`H-MEM sidecar | engine source: ${source} | state: ${STATE_DIR}`);

  const findFact = (key: string) =>
    hmem.store.all().filter((m: any) => m.tags.includes(`fact:${key}`) && !m.supersededBy);

  const server = http.createServer(async (req, res) => {
    try {
      const url = new URL(req.url ?? "/", `http://${HOST}`);
      if (req.method === "GET" && url.pathname === "/health") {
        return send(res, 200, { ok: true, engine: "meterless-hmem-reference", engine_source: source, memories: hmem.store.all().length });
      }
      if (req.method === "GET" && url.pathname === "/stats") {
        return send(res, 200, { memories: hmem.store.all().length, ledger: hmem.ledger.stats() });
      }
      const audit = url.pathname.match(/^\/memories\/([\w-]+)\/audit$/);
      if (req.method === "GET" && audit) {
        const rec = hmem.store.get(audit[1]);
        return send(res, rec ? 200 : 404, { memory: rec ? publicRecord(rec) : null, history: hmem.ledger.history(audit[1]) });
      }
      if (req.method !== "POST") return send(res, 404, { error: "not found" });
      const body = await readBody(req);

      if (url.pathname === "/facts") {
        const ticker = String(body.ticker ?? "").toUpperCase();
        if (!ticker || !Array.isArray(body.facts)) return send(res, 400, { error: "ticker and facts[] required" });
        const results: Json[] = [];
        for (const f of body.facts) {
          if (!f.key || !f.content || typeof f.value !== "number" || !f.source) {
            results.push({ key: f.key, outcome: "rejected", reason: "key, content, numeric value and source are required" });
            continue;
          }
          const existing = findFact(f.key);
          const same = existing.find((m: any) => m.tags.includes(`value:${f.value}`));
          if (same) {
            // Re-observed from an independent retrieval: confidence feedback, logged in the ledger.
            hmem.feedback(same.id, "helpful");
            results.push({ key: f.key, outcome: "confirmed", memory: publicRecord(hmem.store.get(same.id)) });
            continue;
          }
          const record = hmem.add({
            content: f.content,
            type: "factual",
            layer: "working",
            tags: [`fact:${f.key}`, `value:${f.value}`, `ticker:${ticker}`, ...(f.tags ?? [])],
            confidence: typeof f.confidence === "number" ? f.confidence : 0.8,
            source: f.source,
            provenance: { origin: "document", learnedAt: hmem.clock(), label: f.source, refs: f.refs ?? [] },
            chatId: ticker,
          });
          const conflicts: Json[] = [];
          for (const old of existing) {
            const oldFiled = String(old.tags.find((t: string) => t.startsWith("filed:")) ?? "filed:").slice(6);
            const newFiled = String(f.filed ?? "");
            const details = { with: record.id, reason: "same fact key, different value", key: f.key, oldValue: old.tags.find((t: string) => t.startsWith("value:")), newValue: f.value };
            hmem.ledger.log(old.id, "conflict_detected", ACTOR, { details });
            hmem.ledger.log(record.id, "conflict_detected", ACTOR, { details: { ...details, with: old.id } });
            let resolution = "queued";
            if (newFiled && oldFiled && newFiled > oldFiled) {
              // Later filing supersedes the earlier one; the old record is kept and penalized.
              hmem.store.update(old.id, { supersededBy: record.id });
              hmem.ledger.log(old.id, "conflict_resolved", ACTOR, { details: { winner: record.id, rule: "later filing date supersedes" } });
              resolution = `superseded ${old.id} (later filing)`;
            }
            conflicts.push({ memoryA: old.id, memoryB: record.id, previous: publicRecord(old), resolution });
          }
          if (f.filed) hmem.store.update(record.id, { tags: [...record.tags, `filed:${f.filed}`] });
          results.push({ key: f.key, outcome: conflicts.length ? "conflict" : "new", memory: publicRecord(hmem.store.get(record.id)), conflicts });
        }
        return send(res, 200, { results });
      }

      if (url.pathname === "/notes") {
        const ticker = String(body.ticker ?? "").toUpperCase();
        if (!ticker || !body.content || !body.source) return send(res, 400, { error: "ticker, content and source required" });
        const record = hmem.add({
          content: body.content,
          type: "general",
          layer: "working",
          tags: [`ticker:${ticker}`, ...(body.tags ?? [])],
          confidence: typeof body.confidence === "number" ? body.confidence : 0.7,
          source: body.source,
          provenance: { origin: "plan_completion", learnedAt: hmem.clock(), label: body.source, refs: body.refs ?? [] },
          chatId: ticker,
        });
        return send(res, 200, { memory: publicRecord(record) });
      }

      if (url.pathname === "/recall") {
        const ticker = String(body.ticker ?? "").toUpperCase();
        if (!ticker || !body.query) return send(res, 400, { error: "ticker and query required" });
        const result = hmem.query(String(body.query), { topN: body.topN ?? 8, threshold: body.threshold ?? 0.1, chatId: ticker });
        return send(res, 200, {
          memories: result.memories
            .filter((r: any) => r.memory.chatId === ticker)
            .map((r: any) => ({ relevance: r.relevance, memory: publicRecord(r.memory) })),
          context: result.context,
          trace: result.trace,
        });
      }
      return send(res, 404, { error: "not found" });
    } catch (err) {
      return send(res, 500, { error: String((err as Error).message ?? err) });
    }
  });
  server.listen(PORT, HOST, () => console.log(`listening on http://${HOST}:${PORT}`));
}

main();
