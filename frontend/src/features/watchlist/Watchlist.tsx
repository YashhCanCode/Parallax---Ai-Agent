import { useCallback, useEffect, useState } from "react";
import { CompanyPicker } from "../../components/CompanyPicker";
import { MemoryId, useMemoryAudit } from "../../components/MemoryAudit";
import { Badge, Button, Card, DataStatusBadge, Empty } from "../../components/ui";
import { api } from "../../lib/api";
import { usd } from "../../lib/format";
import type { CompaniesResponse, CompanyHit, WatchItem, WatchReport } from "../../types/api";

function ReportView({ r, onAudit }: { r: WatchReport; onAudit: (id: string) => void }) {
  if (r.error) return <p className="text-sm text-critical">{r.error}</p>;
  const changes = r.changes ?? [];
  const newFigs = r.new_figures ?? [];
  const filings = r.new_filings ?? [];
  return (
    <div className="space-y-2 text-[13px]">
      <div className="flex flex-wrap items-center gap-1.5 text-xs text-muted">
        Checked {new Date(r.checked_at).toLocaleString()} · {r.mode_used} {(r.data_status ?? []).map((d) => <DataStatusBadge key={d} status={d} />)}
        {r.memory?.available ? <Badge tone="good">H-MEM memory used</Badge> : <Badge tone="warning" title={r.memory?.error}>Memory unavailable</Badge>}
      </div>
      {r.baseline ? (
        <p className="text-ink">
          <span className="font-semibold">Started watching.</span> FinSight now remembers {r.figures_tracked} figures
          {r.confirmed ? ` (${r.confirmed} already known from earlier investigations)` : ""}. Future checks will report what changes.
        </p>
      ) : changes.length === 0 && filings.length === 0 && newFigs.length === 0 ? (
        <p className="text-ink"><span aria-hidden>✓</span> No changes since the last check. {r.confirmed} remembered figures re-confirmed.</p>
      ) : (
        <p className="text-ink">
          <span className="font-semibold">{changes.length} changed figure(s), {newFigs.length} new figure(s), {filings.length} new filing(s)</span>
          {r.confirmed ? ` · ${r.confirmed} re-confirmed` : ""}.
        </p>
      )}
      {!r.memory?.available && r.memory?.error && <p className="text-xs text-muted">Change detection needs the H-MEM sidecar: {r.memory.error}</p>}
      {changes.length > 0 && (
        <ul className="space-y-1">
          {changes.map((c) => (
            <li key={c.key + c.memory_id} className="rounded-md border border-line bg-sunken px-2.5 py-1.5">
              <div className="flex flex-wrap items-baseline gap-x-2">
                <Badge tone="warning"><span aria-hidden>⚠</span>Changed</Badge>
                <span className="font-medium text-ink">{c.label}</span>
                <span className="num text-ink">{usd(c.old_value)} → {usd(c.value)}</span>
              </div>
              <div className="mt-0.5 text-xs text-ink2">
                New figure from {c.form} filed {c.filed}{c.source_url && <> · <a className="text-accent hover:underline" href={c.source_url} target="_blank" rel="noreferrer">filing ↗</a></>}
                {" "}· was <MemoryId id={c.old_memory_id} onOpen={onAudit} /> ({c.old_source}), now <MemoryId id={c.memory_id} onOpen={onAudit} /> · {c.resolution}
              </div>
            </li>
          ))}
        </ul>
      )}
      {!r.baseline && newFigs.length > 0 && (
        <ul className="space-y-0.5 text-xs text-ink2">
          {newFigs.map((f) => (
            <li key={f.key}><Badge tone="accent">New</Badge> {f.label}: <span className="num font-medium text-ink">{usd(f.value)}</span> ({f.form} filed {f.filed}) <MemoryId id={f.memory_id} onOpen={onAudit} /></li>
          ))}
        </ul>
      )}
      {(r.decisions ?? []).map((d) => (
        <div key={d.id} className={`rounded-md px-2.5 py-1.5 text-xs ${d.newly_hit.length ? "bg-[color-mix(in_srgb,var(--status-warning)_18%,transparent)] text-ink" : "bg-sunken text-ink2"}`}>
          <span className="font-medium text-ink">Your decision ({new Date(d.created_at).toLocaleDateString()}): {d.decision_label}</span>
          {d.newly_hit.length > 0 ? <> · <b>⚠ Tripwire hit:</b> {d.newly_hit.join("; ")}. You wrote: “{(d.note || d.decision_label).replace(/[.\s]+$/, "")}.”</>
            : <> · tripwires: {d.tripwires.map((t) => `${t.describe} (${t.state === "hit" ? "hit" : t.state === "ok" ? "not hit" : "no data"})`).join("; ")}</>}
        </div>
      ))}
      {filings.length > 0 && (
        <ul className="space-y-0.5 text-xs text-ink2">
          {filings.map((f) => (
            <li key={f.accession}><Badge>New filing</Badge> {f.form} filed {f.filed} · {f.accession}
              {!f.statement && <span className="text-muted"> (not a financial-statement filing)</span>}
              {f.url && <> · <a className="text-accent hover:underline" href={f.url} target="_blank" rel="noreferrer">open ↗</a></>}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function Watchlist({ mode, companies }: { mode: string; companies: CompaniesResponse | null }) {
  const [items, setItems] = useState<WatchItem[]>([]);
  const [ticker, setTicker] = useState("");
  const [picked, setPicked] = useState<CompanyHit | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [amend, setAmend] = useState<{ applied: boolean; description: string } | null>(null);
  const { open, view } = useMemoryAudit();

  const load = useCallback(async () => {
    try { setItems(await api.watchlist()); } catch (e) { setErr(String((e as Error).message)); }
  }, []);
  useEffect(() => { load(); api.sampleAmendment().then(setAmend).catch(() => undefined); }, [load]);

  const act = async (label: string, fn: () => Promise<unknown>) => {
    setBusy(label); setErr(null);
    try { await fn(); await load(); } catch (e) { setErr(String((e as Error).message)); } finally { setBusy(null); }
  };

  const pool = mode === "sample" ? companies?.sample ?? [] : companies?.live ?? [];
  const watched = new Set(items.map((i) => i.ticker));
  const hasNwm = watched.has("NWM");

  return (
    <div className="space-y-4">
      <Card title="Watchlist" subtitle="Follow companies. Each check fetches fresh data and compares it with what FinSight remembers in Meterless H-MEM, so you see exactly what changed.">
        <div className="flex flex-wrap items-center gap-2">
          {mode === "sample" ? (
            <select aria-label="Company to follow" value={ticker} onChange={(e) => setTicker(e.target.value)}
              className="rounded-lg border border-line bg-surface px-2 py-2 text-sm text-ink">
              <option value="">Choose a sample company</option>
              {pool.filter((c) => !watched.has(c.ticker)).map((c) => <option key={c.ticker} value={c.ticker}>{c.ticker} · {c.name}</option>)}
            </select>
          ) : (
            <div className="w-full max-w-md"><CompanyPicker mode={mode} value={picked} placeholder="Search any US-listed company to follow"
              onChange={(c) => { setPicked(c); setTicker(c?.ticker ?? ""); }} /></div>
          )}
          <Button disabled={!ticker || watched.has(ticker) || !!busy} onClick={() => act("follow", async () => { await api.follow(ticker, mode); await api.checkWatchlist(ticker); setTicker(""); setPicked(null); })}>
            {busy === "follow" ? "Following…" : "Follow"}
          </Button>
          <Button variant="ghost" disabled={!items.length || !!busy} onClick={() => act("all", () => api.checkWatchlist())}>
            {busy === "all" ? "Checking…" : "Check all for updates"}
          </Button>
        </div>
        {hasNwm && amend && (
          <div className="mt-3 rounded-lg border border-dashed border-line p-2.5 text-xs text-ink2">
            <Badge tone="warning">SAMPLE DATA</Badge>{" "}
            To see change detection without waiting for a real filing, publish a fictional amended filing for the fictional Northwind Motors.
            It only affects sample data. {amend.applied ? <span className="font-medium text-ink">Already published.</span> : (
              <button className="font-medium text-accent hover:underline" disabled={!!busy}
                onClick={() => act("amend", async () => { await api.publishSampleAmendment(); setAmend({ ...amend, applied: true }); })}>
                Publish fictional amended filing
              </button>
            )}
          </div>
        )}
        {err && <p className="mt-2 text-sm text-critical">{err}</p>}
      </Card>

      {items.length === 0 ? <Empty>Nothing followed yet. Follow a company to start tracking changes.</Empty> : (
        <div className="grid gap-4 lg:grid-cols-2">
          {items.map((w) => (
            <Card key={w.ticker} title={<span className="flex items-center gap-2">{w.name} <Badge>{w.ticker}</Badge></span>}
              subtitle={`Following since ${new Date(w.added_at).toLocaleDateString()} · ${w.data_mode}`}
              actions={
                <div className="flex gap-2">
                  <Button variant="ghost" className="px-2.5 py-1 text-xs" disabled={!!busy} onClick={() => act(w.ticker, () => api.checkWatchlist(w.ticker))}>
                    {busy === w.ticker ? "Checking…" : "Check now"}
                  </Button>
                  <Button variant="ghost" className="px-2.5 py-1 text-xs" disabled={!!busy} onClick={() => act("rm" + w.ticker, () => api.unfollow(w.ticker))}>Unfollow</Button>
                </div>
              }>
              {w.last_report ? <ReportView r={w.last_report} onAudit={open} /> : <p className="text-sm text-muted">Not checked yet.</p>}
            </Card>
          ))}
        </div>
      )}
      {view}
    </div>
  );
}
