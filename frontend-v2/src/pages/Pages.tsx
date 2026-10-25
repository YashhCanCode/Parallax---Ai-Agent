import { ArrowRight, RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";
import { CompanyMark } from "../components/brand";
import { Badge, Button, Card, Empty, cx } from "../components/ui";
import { MODES } from "../layout/TopBar";
import { type Prefs, relTime } from "../lib/prefs";
import type { IntegrationStatus, RecentItem } from "../types/api";

const tone = (s?: string) => (s === "online" || s === "configured" ? "good" : !s || /not|offline|error|disabled|missing|unauthorized/.test(s) ? "neutral" : "warning") as "good" | "neutral" | "warning";

export function DataSourcesPage({ status, onProbe, probing }: { status: IntegrationStatus | null; onProbe: () => void; probing: boolean }) {
  if (!status) return <Empty>Loading integration status…</Empty>;
  const rows = [
    { name: "Zetaris", role: "Federated SQL layer between FinSight and SEC EDGAR", state: status.zetaris.state,
      details: [status.zetaris.base_url, `${status.zetaris.registered_views} verified views`, ...(status.zetaris.lightning_databases != null ? [`${status.zetaris.lightning_databases} Lightning databases`] : []), ...status.zetaris.problems, status.zetaris.error ?? ""] },
    { name: "Meterless H-MEM", role: "Memory: facts, decisions, tripwires, append-only ledger", state: status.meterless_hmem.state,
      details: [status.meterless_hmem.url, status.meterless_hmem.engine_source ?? "", status.meterless_hmem.memories != null ? `${status.meterless_hmem.memories} memories` : "", status.meterless_hmem.error ?? ""] },
    { name: "NVIDIA Nemotron", role: "AI writer for summaries and Pre-Mortem voices, checked before display", state: status.nvidia?.state ?? "not_configured", details: [status.nvidia?.model ?? "", status.nvidia?.detail ?? ""] },
    { name: "Meterless Runtime", role: "Local model provider (Nightshift), tried first when online", state: status.meterless_runtime.state, details: [status.meterless_runtime.base_url, status.meterless_runtime.detail] },
    { name: "SEC EDGAR", role: "Source of record: company filings (XBRL) and the company directory", state: status.sec.user_agent_set ? "configured" : "not_configured", details: [status.sec.user_agent_set ? "Contact (User-Agent) set" : "Set SEC_USER_AGENT in .env"] },
    { name: "Gemini", role: "Optional fallback model provider", state: status.gemini.configured ? "configured" : "not_configured", details: [status.gemini.model] },
  ];
  return (
    <div className="space-y-4">
      <Card title="Data Sources" subtitle={`Default data mode: ${status.data_mode} · model order: ${status.llm_provider}`}
        actions={<Button variant="ghost" onClick={onProbe} disabled={probing}><RefreshCw size={15} className={probing ? "animate-spin" : ""} />{probing ? "Probing…" : "Probe live"}</Button>}>
        <p className="text-[13px] text-ink2">“Probe live” calls Zetaris, the Meterless Runtime and NVIDIA for real; otherwise configured services show “configured (not probed)”.</p>
      </Card>
      <div className="grid gap-3 md:grid-cols-2">
        {rows.map((r) => (
          <Card key={r.name} title={r.name} subtitle={r.role} actions={<Badge tone={tone(r.state)}>{r.state}</Badge>}>
            <ul className="space-y-0.5 text-[12.5px] text-ink2">{r.details.filter(Boolean).map((d) => <li key={d} className="break-all">{d}</li>)}</ul>
          </Card>
        ))}
      </div>
    </div>
  );
}

export function SettingsPage({ prefs, onChange }: { prefs: Prefs; onChange: (p: Prefs) => void }) {
  const [name, setName] = useState(prefs.name);
  useEffect(() => setName(prefs.name), [prefs.name]);
  return (
    <Card title="Settings" subtitle="Stored in this browser only.">
      <div className="grid max-w-lg gap-4">
        <label className="text-[13px] text-ink2">Your name (for the greeting and profile)
          <input value={name} maxLength={40} onChange={(e) => setName(e.target.value)} onBlur={() => onChange({ ...prefs, name: name.trim() })}
            className="mt-1 w-full rounded-xl border border-soft bg-[var(--chip)] px-3 py-2 text-sm text-ink" placeholder="e.g. Yashwanth" />
        </label>
        <label className="text-[13px] text-ink2">Default data source
          <select value={prefs.mode} onChange={(e) => onChange({ ...prefs, mode: e.target.value })} className="mt-1 w-full rounded-xl border border-soft bg-[var(--chip)] px-3 py-2 text-sm text-ink">
            <option value="">Use the server default</option>
            {MODES.map((m) => <option key={m.id} value={m.id}>{m.label}</option>)}
          </select>
        </label>
        <p className="text-[12px] text-muted">FinSight is an educational research tool. It does not give personalized financial advice.</p>
      </div>
    </Card>
  );
}

export function ReportsPage({ items, onOpen, title = "All investigations", hint = "Every investigation is saved with its evidence, findings, charts and integration trail.", filter }: {
  items: RecentItem[]; onOpen: (id: string) => void; title?: string; hint?: string; filter?: (r: RecentItem) => boolean;
}) {
  const list = filter ? items.filter(filter) : items;
  return (
    <Card title={title} subtitle={hint}>
      {list.length === 0 ? <Empty>No investigations yet.</Empty> : (
        <ul className="space-y-1.5">
          {list.map((r) => (
            <li key={r.id}>
              <button onClick={() => onOpen(r.id)} className="flex w-full items-center gap-3 rounded-[12px] bg-[rgba(255,255,255,0.035)] px-3 py-2 text-left hover:bg-[rgba(255,255,255,0.06)]">
                <CompanyMark ticker={r.ticker ?? "?"} size={32} radius={8} />
                <span className="min-w-0 flex-1"><span className="block truncate text-[13.5px] text-[var(--cream)]">{r.question}</span>
                  <span className="block text-[12px] text-muted">{r.ticker ?? "No company"} · {relTime(r.created_at)} · {r.data_mode}</span></span>
                <Badge tone={r.state === "COMPLETED" ? "good" : r.state === "FAILED" ? "critical" : "neutral"}>{r.state.replace(/_/g, " ").toLowerCase()}</Badge>
                <ArrowRight size={15} className="text-ink2" />
              </button>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

export function SubTabs<T extends string>({ tabs, value, onChange }: { tabs: [T, string][]; value: T; onChange: (t: T) => void }) {
  return (
    <div className="flex flex-wrap gap-1 rounded-[14px] border border-soft bg-panel p-1" role="tablist">
      {tabs.map(([id, label]) => (
        <button key={id} role="tab" aria-selected={value === id} onClick={() => onChange(id)}
          className={cx("rounded-[10px] px-3.5 py-1.5 text-[13.5px]", value === id ? "bg-[rgba(255,255,255,0.10)] font-medium text-[var(--cream)]" : "text-ink2 hover:text-ink")}>{label}</button>
      ))}
    </div>
  );
}
