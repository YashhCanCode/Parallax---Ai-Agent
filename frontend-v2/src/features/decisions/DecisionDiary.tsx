import { useCallback, useEffect, useState } from "react";
import { MemoryId, useMemoryAudit } from "../../components/MemoryAudit";
import { Badge, Button, Card, Empty } from "../../components/ui";
import { api } from "../../lib/api";
import type { Decision, DecisionCheck } from "../../types/api";

function Hindsight({ d, check }: { d: Decision; check: DecisionCheck }) {
  const h = check.hindsight;
  const changed = h.rows.filter((r) => r.changed);
  return (
    <div className="mt-2 rounded-md border border-line p-2.5">
      <h4 className="text-xs font-semibold uppercase tracking-wide text-muted">What you knew then vs what's known now</h4>
      <p className="mt-0.5 text-xs text-ink2">
        Decided {new Date(d.created_at).toLocaleDateString()} with filings up to {h.latest_filing_then?.date ?? "?"} ({h.latest_filing_then?.form ?? ""}).
        Now: filings up to {h.latest_filing_now?.date ?? "?"} ({h.latest_filing_now?.form ?? ""}). {h.new_filings.length} new filing(s) since.
      </p>
      {changed.length === 0 ? <p className="mt-1 text-xs text-ink">Nothing you decided on has changed yet.</p> : (
        <table className="mt-1 w-full text-left text-xs">
          <thead className="text-muted"><tr><th className="py-0.5">Figure</th><th>When you decided</th><th>Now</th></tr></thead>
          <tbody>{changed.map((r) => (
            <tr key={r.metric} className="num border-t border-line text-ink"><td className="py-0.5">{r.label}</td><td>{r.then}</td><td className="font-semibold">{r.now}</td></tr>
          ))}</tbody>
        </table>
      )}
      <p className="mt-1 text-[11.5px] text-muted">Judge the decision by what you knew then, not by how things turned out.</p>
    </div>
  );
}

export function DecisionDiary({ ticker = "", compact = false, refreshKey }: { ticker?: string; compact?: boolean; refreshKey?: unknown } = {}) {
  const [items, setItems] = useState<Decision[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [latest, setLatest] = useState<Record<string, DecisionCheck>>({});
  const { open, view } = useMemoryAudit();
  const load = useCallback(() => api.decisions(ticker).then(setItems).catch((e) => setErr(String(e.message))), [ticker]);
  useEffect(() => { load(); }, [load, refreshKey]);

  const check = async (id: string) => {
    setBusy(id); setErr(null);
    try { const r = await api.checkDecision(id); setLatest((l) => ({ ...l, [id]: r.check })); await load(); }
    catch (e) { setErr(String((e as Error).message)); } finally { setBusy(null); }
  };

  return (
    <div className="space-y-4">
      {!compact && <Card title="Decision Diary" subtitle="Your own decisions and tripwires. Each is stored in Meterless H-MEM, so the record of what you knew, and when, can't be quietly rewritten.">
        <p className="text-[13px] text-ink2">Record one from any finished investigation (“Record your decision”). Watchlist checks re-test your tripwires automatically.</p>
        {err && <p className="mt-2 text-sm text-critical">{err}</p>}
      </Card>}
      {items.length === 0 ? <Empty>{ticker ? `No decisions recorded for ${ticker} yet.` : "No decisions yet."}</Empty> : items.map((d) => {
        const c = latest[d.id] ?? d.checks[d.checks.length - 1];
        const hits = d.tripwires_eval.filter((t) => t.state === "hit");
        return (
          <Card key={d.id} title={<span className="flex flex-wrap items-center gap-2">{d.company} <Badge>{d.ticker}</Badge><Badge tone="accent">{d.decision_label}</Badge>
            {hits.length > 0 && <Badge tone="warning"><span aria-hidden>⚠</span>{hits.length} tripwire{hits.length > 1 ? "s" : ""} hit</Badge>}</span>}
            subtitle={`Decided ${new Date(d.created_at).toLocaleString()} · ${d.data_mode}${d.checks.length ? ` · last checked ${new Date(d.checks[d.checks.length - 1].checked_at).toLocaleString()}` : ""}`}
            actions={<Button variant="ghost" className="px-2.5 py-1 text-xs" disabled={!!busy} onClick={() => check(d.id)}>{busy === d.id ? "Checking…" : "Check now"}</Button>}>
            {d.note && <p className="text-[13px] italic text-ink">“{d.note}”</p>}
            <ul className="mt-2 space-y-1 text-[13px]">
              {d.tripwires_eval.map((t, i) => (
                <li key={i} className="flex flex-wrap items-center gap-2">
                  <Badge tone={t.state === "hit" ? "warning" : t.state === "ok" ? "good" : "neutral"}>{t.state === "hit" ? "⚠ hit" : t.state === "ok" ? "✓ not hit" : "∅ no data"}</Badge>
                  <span className="text-ink">{t.describe}</span>
                  <span className="text-xs text-muted">now {t.value_fmt}{t.period ? ` (${t.period})` : ""}</span>
                </li>
              ))}
              {d.tripwires_eval.length === 0 && <li className="text-xs text-muted">No tripwires.</li>}
            </ul>
            {c && c.newly_hit.length > 0 && (
              <p className="mt-2 rounded-md bg-[color-mix(in_srgb,var(--status-warning)_18%,transparent)] px-2.5 py-1.5 text-[13px] text-ink">
                <span className="font-semibold">⚠ Tripwire hit:</span> {c.newly_hit.join("; ")}. You wrote: “{(d.note || d.decision_label).replace(/[.\s]+$/, "")}.” Time to revisit, on your terms.
                {c.hit_memory_ids.length > 0 && <> Logged in memory: {c.hit_memory_ids.map((id) => <MemoryId key={id} id={id} onOpen={open} />)}</>}
              </p>
            )}
            {c && <Hindsight d={d} check={c} />}
            <p className="mt-2 text-xs text-ink2">Memory record: <MemoryId id={d.memory_id} onOpen={open} />{!d.memory_id && "not in H-MEM (sidecar was unavailable)"}</p>
          </Card>
        );
      })}
      {view}
    </div>
  );
}
