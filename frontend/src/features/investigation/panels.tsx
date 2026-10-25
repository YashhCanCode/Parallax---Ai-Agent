import { Badge, Card, Empty } from "../../components/ui";
import { MemoryId, useMemoryAudit } from "../../components/MemoryAudit";
import { duration } from "../../lib/format";
import type { Investigation } from "../../types/api";

const ORDER = ["RECEIVED", "PLANNING", "RETRIEVING", "NORMALIZING", "RECONCILING", "INVESTIGATING_RISKS", "SIMULATING", "VERIFYING"];

/** Progress shows only steps the backend actually recorded, with their real timings and events. */
export function ProgressPanel({ inv }: { inv: Investigation }) {
  const done = new Map(inv.steps.map((s) => [s.state, s]));
  const terminal = inv.steps.find((s) => ["COMPLETED", "NEEDS_MORE_EVIDENCE", "FAILED"].includes(s.state));
  const planned = (inv.plan?.steps as string[] | undefined)?.includes("simulate scenarios");
  const states = ORDER.filter((s) => s !== "SIMULATING" || planned || done.has(s));
  return (
    <Card title="Investigation progress" subtitle="Recorded by the backend as each step runs.">
      <ol className="space-y-1.5">
        {states.map((st) => {
          const s = done.get(st);
          const icon = !s ? "○" : s.status === "running" ? "◐" : s.status === "ok" ? "✓" : s.status === "warning" ? "!" : "✕";
          return (
            <li key={st} className={`text-[13px] ${s ? "text-ink" : "text-muted"}`}>
              <div className="flex items-center gap-2">
                <span aria-hidden className={`w-4 text-center ${s?.status === "running" ? "animate-pulse text-accent" : ""}`}>{icon}</span>
                <span className="font-medium">{st.replace("_", " ").toLowerCase().replace(/^\w/, (c) => c.toUpperCase())}</span>
                {s && <span className="num text-xs text-muted">{duration(s.started_at, s.finished_at)}</span>}
                {s?.status === "warning" && <Badge tone="warning">warning</Badge>}
                {s?.status === "error" && <Badge tone="critical">error</Badge>}
              </div>
              {s && s.events.length > 0 && (
                <ul className="ml-6 mt-0.5 list-disc pl-3 text-xs text-ink2">{s.events.map((e, i) => <li key={i}>{e}</li>)}</ul>
              )}
            </li>
          );
        })}
      </ol>
      {terminal && (
        <p className="mt-2 text-[13px] font-medium text-ink">
          {terminal.state === "COMPLETED" ? "✓ Completed" : terminal.state === "FAILED" ? "✕ Failed" : "! Needs more evidence"}: {terminal.detail}
        </p>
      )}
    </Card>
  );
}

export function SummaryPanel({ inv }: { inv: Investigation }) {
  const s = inv.summary;
  const byId = new Map(inv.findings.map((f) => [f.id, f]));
  return (
    <Card title="Executive summary" actions={s && <Badge tone={s.generated_by === "deterministic" ? "neutral" : "accent"}>{s.generated_by === "deterministic" ? "No model used" : `Written by ${s.generated_by}`}</Badge>}>
      {!s ? <Empty>The summary appears after verification.</Empty> : (
        <>
          <p className="text-[14px] leading-relaxed text-ink">{s.text}</p>
          {s.key_points.length > 0 && (
            <ul className="mt-2 space-y-1">
              {s.key_points.map((k, i) => (
                <li key={i} className="text-[13px] text-ink2">• {k.text}{" "}
                  {k.finding_ids.map((id) => <a key={id} href={`#${byId.get(id)?.category === "risk" ? "risks" : "truth"}`} className="text-xs text-accent hover:underline">[{id}]</a>)}
                </li>
              ))}
            </ul>
          )}
          {s.note && <p className="mt-2 text-xs text-muted">{s.note}</p>}
        </>
      )}
    </Card>
  );
}

export function MemoryPanel({ inv }: { inv: Investigation }) {
  const { open, view } = useMemoryAudit();
  const Row = ({ m }: { m: Investigation["memory_recalled"][number] }) => (
    <li className="flex items-start justify-between gap-2 rounded-md bg-sunken px-2 py-1.5 text-xs">
      <span className="text-ink2"><MemoryId id={m.id} onOpen={open} /> {m.content}
        <span className="text-muted"> · {m.source}</span></span>
      <span className="num shrink-0 text-muted">{m.relevance != null ? `rel ${m.relevance}` : ""}{m.confidence != null ? ` conf ${m.confidence.toFixed(2)}` : ""}</span>
    </li>
  );
  return (
    <Card title="Memory (Meterless H-MEM)" subtitle="Recalled before this run, and what this run wrote back. Click an id for its append-only trust-ledger history.">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-muted">Recalled ({inv.memory_recalled.length})</h3>
      {inv.memory_recalled.length ? <ul className="mt-1 space-y-1">{inv.memory_recalled.map((m) => <Row key={m.id} m={m} />)}</ul>
        : <p className="mt-1 text-xs text-muted">Nothing remembered yet for this company.</p>}
      <h3 className="mt-3 text-xs font-semibold uppercase tracking-wide text-muted">Written or re-confirmed ({inv.memory_written.length}) · conflicts {inv.memory_conflicts.length}</h3>
      {inv.memory_written.length ? <ul className="mt-1 max-h-48 space-y-1 overflow-auto">{inv.memory_written.map((m) => <Row key={m.id + m.content} m={m} />)}</ul>
        : <p className="mt-1 text-xs text-muted">No memory written (sidecar unavailable or no facts).</p>}
      {view}
    </Card>
  );
}

export function TracePanel({ inv }: { inv: Investigation }) {
  const byChannel = inv.receipts.reduce<Record<string, number>>((a, r) => ({ ...a, [r.channel]: (a[r.channel] ?? 0) + 1 }), {});
  return (
    <Card title="Integration trail" subtitle="Every external call this investigation made: data queries, memory calls and model calls.">
      <div className="mb-2 flex flex-wrap gap-1.5">{Object.entries(byChannel).map(([c, n]) => <Badge key={c}>{c}: {n}</Badge>)}</div>
      <h3 className="text-xs font-semibold uppercase tracking-wide text-muted">Model calls</h3>
      {inv.model_calls.length === 0 ? <p className="mt-1 text-xs text-muted">No model calls (no provider configured or reachable).</p> : (
        <ul className="mt-1 space-y-1 text-xs">
          {inv.model_calls.map((m, i) => (
            <li key={i} className="rounded-md bg-sunken px-2 py-1.5 text-ink2">
              <span className="font-medium text-ink">{m.provider}:{m.model}</span> · {m.purpose} · {m.duration_ms} ms ·{" "}
              {m.ok ? (m.output_accepted ? "accepted" : `rejected (${m.rejection_reason})`) : `failed (${m.error})`}
              {m.usage && (
                <span className="text-muted [overflow-wrap:anywhere]" title={JSON.stringify(m.usage)}>
                  {" "}· tokens as reported:{" "}
                  {["prompt_tokens", "completion_tokens", "total_tokens"].some((k) => k in m.usage!)
                    ? ["prompt_tokens", "completion_tokens", "total_tokens"].filter((k) => k in m.usage!)
                        .map((k) => `${k.replace("_tokens", "")} ${String(m.usage![k])}`).join(", ")
                    : JSON.stringify(m.usage)}
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
      <details className="mt-2">
        <summary className="cursor-pointer text-xs font-semibold uppercase tracking-wide text-muted">Data and memory receipts ({inv.receipts.length})</summary>
        <ul className="mt-1 max-h-64 space-y-1 overflow-auto text-[11px]">
          {inv.receipts.map((r, i) => (
            <li key={i} className="rounded bg-sunken px-2 py-1 text-ink2">
              <Badge tone={r.ok ? "good" : "critical"}>{r.channel}</Badge>{" "}
              <span className="break-all font-mono">{r.target.length > 160 ? r.target.slice(0, 160) + "…" : r.target}</span>
              <span className="text-muted"> · {r.duration_ms} ms{r.rows != null ? ` · ${r.rows} rows` : ""}{r.request_id ? ` · req ${r.request_id}` : ""}{r.error ? ` · ${r.error}` : ""}</span>
            </li>
          ))}
        </ul>
      </details>
    </Card>
  );
}

export function Limitations({ inv }: { inv: Investigation | null }) {
  return (
    <Card title="Limitations and disclaimer">
      {inv && inv.limitations.length > 0 && <ul className="mb-2 list-disc pl-4 text-[13px] text-ink2">{inv.limitations.map((l, i) => <li key={i}>{l}</li>)}</ul>}
      <p className="text-[13px] text-ink2">
        FinSight AI is an educational research tool. It shows what filings and sources say, how figures differ and why, and what hypothetical
        assumptions imply. It does not predict markets, rate securities or give personalized financial advice. XBRL facts are as filed and are
        not audited by FinSight; always read the underlying filing before relying on a number.
      </p>
    </Card>
  );
}
