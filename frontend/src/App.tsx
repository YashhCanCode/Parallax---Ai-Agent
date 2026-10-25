import { useEffect, useMemo, useRef, useState } from "react";
import { Badge, Button, Card, DataStatusBadge, Empty } from "./components/ui";
import { api, TERMINAL } from "./lib/api";
import { obsIndex, SourcesPanel, TruthPanel } from "./features/financial-truth/TruthPanel";
import { Limitations, MemoryPanel, ProgressPanel, SummaryPanel, TracePanel } from "./features/investigation/panels";
import { RiskPanel } from "./features/risk-analysis/RiskPanel";
import { ScenarioSimulator } from "./features/scenario-simulator/ScenarioSimulator";
import { ClaimChecker } from "./features/claim-checker/ClaimChecker";
import { Watchlist } from "./features/watchlist/Watchlist";
import { GlossaryProvider } from "./components/Glossary";
import { CompanyPicker } from "./components/CompanyPicker";
import { BlindBoard } from "./features/blind-board/BlindBoard";
import { DecisionDiary } from "./features/decisions/DecisionDiary";
import { DecisionForm } from "./features/decisions/DecisionForm";
import { PremortemRoom } from "./features/decisions/PremortemRoom";
import type { CompanyHit, CompaniesResponse, GlossaryEntry, IntegrationStatus, Investigation } from "./types/api";

const TABS = [
  { id: "investigate", label: "Investigate a company" },
  { id: "claims", label: "Check a post" },
  { id: "board", label: "Blind board" },
  { id: "watchlist", label: "Watchlist" },
  { id: "decisions", label: "My decisions" },
  { id: "simulator", label: "Savings & fees" },
] as const;
type Tab = (typeof TABS)[number]["id"];

const MODES = [
  { id: "sample", label: "Sample (offline, fictional)" },
  { id: "sec_direct", label: "Live: SEC EDGAR direct" },
  { id: "zetaris", label: "Live: SEC via Zetaris" },
];

function IntegrationStrip({ st, onProbe, probing }: { st: IntegrationStatus | null; onProbe: () => void; probing: boolean }) {
  if (!st) return null;
  const tone = (s?: string) => (s === "online" ? "good" : !s || s.includes("not") || ["offline", "error", "disabled"].includes(s) ? "neutral" : "warning") as "good" | "neutral" | "warning";
  return (
    <div className="flex flex-wrap items-center gap-1.5 text-xs">
      <Badge tone={tone(st.zetaris.state)} title={st.zetaris.problems.join("; ") || st.zetaris.error || ""}>Zetaris: {st.zetaris.state}{st.zetaris.registered_views ? ` · ${st.zetaris.registered_views} views` : ""}</Badge>
      <Badge tone={tone(st.meterless_hmem.state)} title={st.meterless_hmem.error ?? st.meterless_hmem.engine_source}>Meterless H-MEM: {st.meterless_hmem.state}</Badge>
      <Badge tone={tone(st.meterless_runtime.state)} title={st.meterless_runtime.detail}>Meterless Runtime: {st.meterless_runtime.state}</Badge>
      {st.nvidia && <Badge tone={tone(st.nvidia.state)} title={st.nvidia.detail ?? st.nvidia.model}>NVIDIA Nemotron: {st.nvidia.configured ? st.nvidia.state : "no key"}</Badge>}
      <Badge tone={st.gemini.configured ? "good" : "neutral"}>Gemini: {st.gemini.configured ? "configured" : "no key"}</Badge>
      <button onClick={onProbe} disabled={probing} className="text-accent hover:underline disabled:opacity-50">{probing ? "probing…" : "probe live"}</button>
    </div>
  );
}

export default function App() {
  const [companies, setCompanies] = useState<CompaniesResponse | null>(null);
  const [status, setStatus] = useState<IntegrationStatus | null>(null);
  const [probing, setProbing] = useState(false);
  const [question, setQuestion] = useState("Was Northwind Motors' 2024 revenue really $13.6 billion?");
  const [mode, setMode] = useState("sample");
  const [ticker, setTicker] = useState<string>("");
  const [picked, setPicked] = useState<CompanyHit | null>(null);
  const [inv, setInv] = useState<Investigation | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const timer = useRef<number | null>(null);
  const [tab, setTab] = useState<Tab>("investigate");
  const [glossary, setGlossary] = useState<GlossaryEntry[]>([]);
  const [followMsg, setFollowMsg] = useState<string | null>(null);

  const follow = async (t: string) => {
    try { await api.follow(t, mode); await api.checkWatchlist(t); setFollowMsg(`Following ${t}. See the Watchlist tab.`); }
    catch (e) { setFollowMsg(String((e as Error).message)); }
  };

  useEffect(() => {
    api.glossary().then(setGlossary).catch(() => undefined);
    api.companies().then(setCompanies).catch((e) => setErr(`Backend not reachable: ${e.message}`));
    api.status().then((s) => { setStatus(s); setMode(s.data_mode); }).catch(() => undefined);
  }, []);

  const probe = async () => { setProbing(true); try { setStatus(await api.status(true)); } finally { setProbing(false); } };

  const poll = (id: string) => {
    if (timer.current) window.clearTimeout(timer.current);
    const tick = async () => {
      try {
        const next = await api.get(id);
        setInv(next);
        if (!TERMINAL.has(next.state)) timer.current = window.setTimeout(tick, 600);
      } catch (e) { setErr(String((e as Error).message)); }
    };
    tick();
  };

  const investigateFromBoard = (t: string) => {
    setTab("investigate");
    setTicker(t);
    setPicked({ ticker: t, name: t, cik: "", exchange: "", builtin: false, zetaris_registered: false });
    const q = `How healthy are ${t}'s finances? Is its profit backed by operating cash flow?`;
    setQuestion(q);
    run(q, t);
  };

  const run = async (q = question, t = ticker) => {
    setErr(null);
    try {
      const started = await api.start(q, t || null, mode);
      setInv(started);
      poll(started.id);
    } catch (e) { setErr(String((e as Error).message)); }
  };

  const obsById = useMemo(() => obsIndex(inv?.observations ?? []), [inv?.observations]);
  const running = inv !== null && !TERMINAL.has(inv.state);
  const statuses = [...new Set(inv?.observations.map((o) => o.data_status) ?? [])];
  const pool = mode === "sample" ? companies?.sample ?? [] : companies?.live ?? [];

  return (
    <GlossaryProvider entries={glossary}>
    <div className="mx-auto max-w-7xl px-4 pb-16 sm:px-6">
      <header className="flex flex-wrap items-center justify-between gap-3 py-4">
        <div className="flex items-center gap-2.5">
          <div className="grid h-8 w-8 place-items-center rounded-lg bg-accent text-sm font-bold text-white" aria-hidden>F</div>
          <div>
            <h1 className="text-[17px] font-semibold leading-tight text-ink">FinSight AI</h1>
            <p className="text-xs text-ink2">Understand the facts. Investigate the risks. Explore the possibilities.</p>
          </div>
        </div>
        <IntegrationStrip st={status} onProbe={probe} probing={probing} />
      </header>

      <nav className="mb-4 flex flex-wrap items-center gap-1 border-b border-line" role="tablist" aria-label="Sections">
        {TABS.map((t) => (
          <button key={t.id} role="tab" aria-selected={tab === t.id} onClick={() => setTab(t.id)}
            className={`-mb-px border-b-2 px-3 py-2 text-sm ${tab === t.id ? "border-accent font-semibold text-ink" : "border-transparent text-ink2 hover:text-ink"}`}>
            {t.label}
          </button>
        ))}
        <label className="ml-auto flex items-center gap-1.5 pb-1 text-xs text-ink2">Data
          <select aria-label="Data mode" value={mode} onChange={(e) => { setMode(e.target.value); setTicker(""); setPicked(null); }}
            className="rounded-md border border-line bg-surface px-2 py-1 text-xs text-ink">
            {MODES.map((m) => <option key={m.id} value={m.id}>{m.label}</option>)}
          </select>
        </label>
      </nav>

      {tab === "claims" && <ClaimChecker key={mode} mode={mode} />}
      {tab === "watchlist" && <Watchlist mode={mode} companies={companies} />}
      {tab === "board" && <BlindBoard mode={mode} companies={companies} onInvestigate={investigateFromBoard} />}
      {tab === "decisions" && <DecisionDiary />}
      {tab === "simulator" && <ScenarioSimulator />}
      {tab === "investigate" && <>

      <Card>
        <form className="grid gap-2 md:grid-cols-[minmax(0,1fr)_minmax(0,22rem)_auto]" onSubmit={(e) => { e.preventDefault(); run(); }}>
          <label className="sr-only" htmlFor="q">Question or claim</label>
          <input id="q" value={question} onChange={(e) => setQuestion(e.target.value)} maxLength={600}
            placeholder="Ask about a company or paste a financial claim, e.g. “Was Tesla's 2024 revenue $97.7 billion?”"
            className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink placeholder:text-muted" />
          {mode === "sample" ? (
            <select aria-label="Company" value={ticker} onChange={(e) => setTicker(e.target.value)}
              className="rounded-lg border border-line bg-surface px-2 py-2 text-sm text-ink">
              <option value="">Company: detect from question</option>
              {pool.map((c) => <option key={c.ticker} value={c.ticker}>{c.ticker} · {c.name}</option>)}
            </select>
          ) : (
            <CompanyPicker mode={mode} value={picked} placeholder="Company: search any US-listed (or detect)"
              onChange={(c) => { setPicked(c); setTicker(c?.ticker ?? ""); }} />
          )}
          <Button type="submit" disabled={running || question.trim().length < 3}>{running ? "Investigating…" : "Investigate"}</Button>
        </form>
        {mode === "sample" && companies && (
          <div className="mt-2 flex flex-wrap gap-1.5">
            <span className="text-xs text-muted">Sample cases:</span>
            {companies.sample_cases.map((c) => (
              <button key={c.question} onClick={() => { setQuestion(c.question); setTicker(""); run(c.question, ""); }} disabled={running}
                className="rounded-md border border-line px-2 py-0.5 text-xs text-ink2 hover:bg-sunken">{c.question}</button>
            ))}
          </div>
        )}
        {mode === "sample" && <p className="mt-2 text-xs text-ink2"><Badge tone="warning">SAMPLE DATA</Badge> Northwind Motors and Contoso Retail are fictional companies with invented figures, built to show each reconciliation case reproducibly offline.</p>}
        {err && <p className="mt-2 text-sm text-critical">{err}</p>}
      </Card>

      {!inv ? (
        <div className="mt-4 grid gap-4 lg:grid-cols-[1fr_1fr]">
          <Empty>Run an investigation to see reconciled figures, risk indicators, evidence and sources.</Empty>
          <ScenarioSimulator />
        </div>
      ) : (
        <div className="mt-4 space-y-4">
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <span className="font-semibold text-ink">{inv.company ?? "No company identified"}</span>
            {inv.ticker && <Badge>{inv.ticker}</Badge>}
            <Badge>mode: {inv.data_mode}</Badge>
            {statuses.map((s) => <DataStatusBadge key={s} status={s} />)}
            <span className="text-xs text-muted">{inv.id}</span>
            {inv.ticker && TERMINAL.has(inv.state) && (
              <button onClick={() => follow(inv.ticker!)} className="ml-auto rounded-md border border-line px-2 py-1 text-xs text-ink hover:bg-sunken">
                + Follow {inv.ticker}
              </button>
            )}
            {followMsg && <span className="text-xs text-ink2">{followMsg}</span>}
          </div>
          <div className="grid gap-4 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
            <SummaryPanel inv={inv} />
            <ProgressPanel inv={inv} />
          </div>
          {inv.state === "FAILED" && <Card><p className="text-sm text-critical">Investigation failed: {inv.error}</p></Card>}
          {inv.observations.length > 0 && (
            <>
              <TruthPanel inv={inv} obsById={obsById} />
              <RiskPanel inv={inv} obsById={obsById} />
              {TERMINAL.has(inv.state) && inv.ticker && inv.findings.length > 0 && (
                <>
                  <PremortemRoom key={inv.id + "-pm"} inv={inv}
                    onDecide={() => document.getElementById("decide")?.scrollIntoView({ behavior: "smooth", block: "start" })} />
                  <DecisionForm key={inv.id + "-df"} ticker={inv.ticker} company={inv.company ?? inv.ticker} mode={inv.data_mode}
                    investigationId={inv.id} findings={inv.findings} />
                </>
              )}
            </>
          )}
          <div className="grid gap-4 lg:grid-cols-2">
            <ScenarioSimulator />
            <div className="space-y-4">
              <MemoryPanel inv={inv} />
              <TracePanel inv={inv} />
            </div>
          </div>
          {inv.observations.length > 0 && <SourcesPanel inv={inv} />}
          <Limitations inv={inv} />
        </div>
      )}
      </>}
    </div>
    </GlossaryProvider>
  );
}
