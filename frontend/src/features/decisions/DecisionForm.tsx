import { useEffect, useState } from "react";
import { MemoryId, useMemoryAudit } from "../../components/MemoryAudit";
import { Badge, Button, Card } from "../../components/ui";
import { api } from "../../lib/api";
import type { Decision, Finding, TripwireMetric, TripwireSpec } from "../../types/api";

const TYPES: [string, string][] = [
  ["wait", "I'll wait"], ["research", "I'll research more"], ["comfortable", "I'm comfortable with this"],
  ["pass", "Not for me"], ["other", "Other"],
];

/** Converts between what the user types (in $B, %, x, years) and raw values. */
export const unitOf = (m?: TripwireMetric) => (m?.unit === "usd" ? "$B" : m?.unit === "pct" ? "%" : m?.unit === "years" ? "years" : "x");
export const toRaw = (m: TripwireMetric | undefined, v: number) => (m?.unit === "usd" ? v * 1e9 : m?.unit === "pct" ? v / 100 : v);
const fromRaw = (m: TripwireMetric, v: number) => (m.unit === "usd" ? v / 1e9 : m.unit === "pct" ? v * 100 : v);
const round = (v: number) => Math.round(v * 100) / 100;

/** Starting suggestions from the findings: the user edits or removes them. Deterministic. */
function suggest(metrics: TripwireMetric[], findings: Finding[]): { metric: string; op: "<" | ">"; input: number }[] {
  const by = new Map(metrics.map((m) => [m.key, m]));
  const out: { metric: string; op: "<" | ">"; input: number }[] = [];
  const has = (k: string) => findings.some((f) => f.id.startsWith(k));
  const cc = by.get("cash_conversion");
  if (cc?.value != null && has("risk-cash")) out.push({ metric: "cash_conversion", op: "<", input: round(Math.min(cc.value * 0.9, 0.8)) });
  const d = by.get("long_term_debt");
  if (d?.value != null && has("risk-debt")) out.push({ metric: "long_term_debt", op: ">", input: round(fromRaw(d, d.value * 1.2)) });
  const g = by.get("revenue_growth");
  if (g?.value != null) out.push({ metric: "revenue_growth", op: "<", input: 0 });
  return out.slice(0, 3);
}

export function DecisionForm({ ticker, company, mode, investigationId, findings, onSaved }: {
  ticker: string; company: string; mode: string; investigationId?: string; findings: Finding[]; onSaved?: (d: Decision) => void;
}) {
  const [metrics, setMetrics] = useState<TripwireMetric[]>([]);
  const [type, setType] = useState("wait");
  const [note, setNote] = useState("");
  const [rows, setRows] = useState<{ metric: string; op: "<" | ">"; input: number }[]>([]);
  const [saved, setSaved] = useState<Decision | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const { open, view } = useMemoryAudit();

  useEffect(() => {
    api.tripwireMetrics(ticker, mode).then((r) => { setMetrics(r.metrics); setRows(suggest(r.metrics, findings)); })
      .catch((e) => setErr(String((e as Error).message)));
  }, [ticker, mode, findings]);

  const by = new Map(metrics.map((m) => [m.key, m]));
  const save = async () => {
    setBusy(true); setErr(null);
    try {
      const tripwires: TripwireSpec[] = rows.map((r) => ({ metric: r.metric, op: r.op, threshold: toRaw(by.get(r.metric), r.input) }));
      const d = await api.createDecision({ ticker, data_mode: mode, decision_type: type, note, tripwires, investigation_id: investigationId ?? null });
      setSaved(d); onSaved?.(d);
    } catch (e) { setErr(String((e as Error).message)); } finally { setBusy(false); }
  };

  if (saved) {
    return (
      <Card id="decide" title="Decision recorded" subtitle="Written to Meterless H-MEM. Its append-only ledger proves what you knew, and when.">
        <p className="text-sm text-ink"><span className="font-semibold">{saved.decision_label}</span>{saved.note && <> — “{saved.note}”</>}</p>
        <ul className="mt-2 space-y-1 text-[13px]">
          {saved.tripwires_eval.map((t, i) => (
            <li key={i} className="flex flex-wrap items-center gap-2">
              <Badge tone={t.state === "hit" ? "warning" : t.state === "ok" ? "good" : "neutral"}>{t.state === "hit" ? "⚠ already true" : t.state === "ok" ? "✓ armed" : "∅ no data"}</Badge>
              <span className="text-ink">{t.describe}</span><span className="text-xs text-muted">now {t.value_fmt}{t.period ? ` (${t.period})` : ""}</span>
            </li>
          ))}
          {saved.tripwires_eval.length === 0 && <li className="text-xs text-muted">No tripwires set.</li>}
        </ul>
        <p className="mt-2 text-xs text-ink2">
          Every watchlist check re-tests these tripwires with code, not AI. Memory record: <MemoryId id={saved.memory_id} onOpen={open} />
          {!saved.memory_id && " (memory sidecar unavailable; saved in FinSight only)"} · Find it under the <b>My decisions</b> tab.
        </p>
        {view}
      </Card>
    );
  }

  return (
    <Card id="decide" title={`Record your decision about ${company}`}
      subtitle="Your words, your call. Add tripwires: evidence that would change your mind. FinSight watches them for you and holds you to them.">
      <fieldset className="flex flex-wrap gap-2" aria-label="Your decision">
        {TYPES.map(([k, label]) => (
          <label key={k} className={`cursor-pointer rounded-lg border px-3 py-1.5 text-sm ${type === k ? "border-accent bg-[color-mix(in_srgb,var(--accent)_12%,transparent)] text-ink" : "border-line text-ink2"}`}>
            <input type="radio" name="dtype" value={k} checked={type === k} onChange={() => setType(k)} className="sr-only" />{label}
          </label>
        ))}
      </fieldset>
      <label className="mt-3 block text-xs text-ink2">Why, in your own words (this is what future-you will read)
        <textarea value={note} onChange={(e) => setNote(e.target.value)} maxLength={1000} rows={2}
          placeholder="e.g. Profit looks good but cash isn't following. I'll wait for two more quarters."
          className="mt-1 w-full rounded-lg border border-line bg-surface p-2 text-sm text-ink placeholder:text-muted" />
      </label>
      <h3 className="mt-3 text-sm font-semibold text-ink">Tripwires: “I'd rethink this if…”</h3>
      <ul className="mt-1 space-y-1.5">
        {rows.map((r, i) => {
          const m = by.get(r.metric);
          return (
            <li key={i} className="flex flex-wrap items-center gap-2 text-sm">
              <select aria-label="Metric" value={r.metric} onChange={(e) => {
                // Start the threshold from the newly chosen metric's current value, in its own units.
                const nm = by.get(e.target.value);
                const start = nm?.value != null ? round(fromRaw(nm, nm.value)) : 0;
                setRows((rs) => rs.map((x, j) => j === i ? { ...x, metric: e.target.value, input: start } : x));
              }}
                className="rounded-md border border-line bg-surface px-2 py-1 text-ink">
                {metrics.map((mm) => <option key={mm.key} value={mm.key}>{mm.label}</option>)}
              </select>
              <select aria-label="Direction" value={r.op} onChange={(e) => setRows((rs) => rs.map((x, j) => j === i ? { ...x, op: e.target.value as "<" | ">" } : x))}
                className="rounded-md border border-line bg-surface px-2 py-1 text-ink">
                <option value="<">falls below</option><option value=">">rises above</option>
              </select>
              <input type="number" step="any" aria-label="Threshold" value={r.input}
                onChange={(e) => setRows((rs) => rs.map((x, j) => j === i ? { ...x, input: Number(e.target.value) } : x))}
                className="num w-24 rounded-md border border-line bg-surface px-2 py-1 text-right text-ink" />
              <span className="text-xs text-ink2">{unitOf(m)}</span>
              <span className="text-xs text-muted">now: {m?.fmt ?? "…"}{m?.period ? ` (${m.period})` : ""}</span>
              <button className="text-xs text-accent hover:underline" onClick={() => setRows((rs) => rs.filter((_, j) => j !== i))}>remove</button>
            </li>
          );
        })}
      </ul>
      {rows.length < 6 && metrics.length > 0 && (
        <button className="mt-1 text-xs font-medium text-accent hover:underline"
          onClick={() => setRows((rs) => [...rs, { metric: metrics[0].key, op: "<", input: 0 }])}>+ add a tripwire</button>
      )}
      <p className="mt-1 text-[11.5px] text-muted">Suggestions come from this investigation's warning signs. Change or remove any of them; they're yours.</p>
      <div className="mt-3 flex items-center gap-3">
        <Button onClick={save} disabled={busy || metrics.length === 0}>{busy ? "Saving…" : "Save to my decision diary"}</Button>
        <span className="text-xs text-muted">FinSight records your decision; it never makes one.</span>
      </div>
      {err && <p className="mt-2 text-sm text-critical">{err}</p>}
    </Card>
  );
}
