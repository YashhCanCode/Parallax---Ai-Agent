import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { CompanyMark } from "./components/brand";
import { GlossaryProvider } from "./components/Glossary";
import { Button, Card, cx } from "./components/ui";
import { BlindBoard } from "./features/blind-board/BlindBoard";
import { ClaimChecker } from "./features/claim-checker/ClaimChecker";
import { DecisionDiary } from "./features/decisions/DecisionDiary";
import { DecisionForm } from "./features/decisions/DecisionForm";
import { PremortemRoom } from "./features/decisions/PremortemRoom";
import { obsIndex, SourcesPanel, TruthPanel } from "./features/financial-truth/TruthPanel";
import { CompanyPanel, FeatureCards, Greeting, RecentPanel, WatchlistPanel } from "./features/home/Home";
import { Limitations, MemoryPanel, ProgressPanel, SummaryPanel, TracePanel } from "./features/investigation/panels";
import { RiskPanel } from "./features/risk-analysis/RiskPanel";
import { ScenarioSimulator } from "./features/scenario-simulator/ScenarioSimulator";
import { Watchlist } from "./features/watchlist/Watchlist";
import { AskPanel, Calendar, TodaysInsights } from "./layout/RightRail";
import { Sidebar, type Page } from "./layout/Sidebar";
import { TopBar } from "./layout/TopBar";
import { api, TERMINAL } from "./lib/api";
import { buildFeed, type FeedItem } from "./lib/feed";
import { cleanName, loadPrefs, savePrefs, shortName, type Prefs } from "./lib/prefs";
import { AskComposer } from "./features/investigation/AskComposer";
import { KeyFiguresPanel } from "./features/financial-truth/KeyFigures";
import { DataSourcesPage, ReportsPage, SettingsPage, SubTabs } from "./pages/Pages";
import type { CompanyHit, CompaniesResponse, Decision, GlossaryEntry, IntegrationStatus, Investigation, RecentItem, WatchItem } from "./types/api";

type CompanyTab = "overview" | "financials" | "risks" | "sources" | "stress" | "notes";
type InvestigateTab = "company" | "claims" | "savings";

export default function App() {
  const [prefs, setPrefs] = useState<Prefs>(loadPrefs);
  const [page, setPage] = useState<Page>("home");
  const [itab, setItab] = useState<InvestigateTab>("company");
  const [ctab, setCtab] = useState<CompanyTab>("overview");
  const [mode, setMode] = useState(prefs.mode || "sample");
  const [status, setStatus] = useState<IntegrationStatus | null>(null);
  const [probing, setProbing] = useState(false);
  const [companies, setCompanies] = useState<CompaniesResponse | null>(null);
  const [glossary, setGlossary] = useState<GlossaryEntry[]>([]);
  const [recent, setRecent] = useState<RecentItem[]>([]);
  const [watch, setWatch] = useState<WatchItem[]>([]);
  const [decisions, setDecisions] = useState<Decision[]>([]);
  const [inv, setInv] = useState<Investigation | null>(null);
  const [homeInv, setHomeInv] = useState<Investigation | null>(null);
  const [question, setQuestion] = useState("");
  const [ticker, setTicker] = useState("");
  const [picked, setPicked] = useState<CompanyHit | null>(null);
  const [composing, setComposing] = useState(true); // the Ask box is open (no investigation shown on top of it)
  const [err, setErr] = useState<string | null>(null);
  const [followMsg, setFollowMsg] = useState<string | null>(null);
  const [refresh, setRefresh] = useState(0);
  const timer = useRef<number | null>(null);
  const searchRef = useRef<HTMLInputElement>(null);

  const loadActivity = useCallback(() => {
    api.recent().then(setRecent).catch(() => undefined);
    api.watchlist().then(setWatch).catch(() => undefined);
    api.decisions().then(setDecisions).catch(() => undefined);
  }, []);

  useEffect(() => {
    api.glossary().then(setGlossary).catch(() => undefined);
    api.companies().then(setCompanies).catch((e) => setErr(`Backend not reachable: ${e.message}`));
    // Quick status first, then a real probe in the background so the sidebar's dots show what is actually reachable.
    api.status().then((s) => { setStatus(s); if (!prefs.mode) setMode(s.data_mode); return api.status(true); })
      .then(setStatus).catch(() => undefined);
    loadActivity();
  }, [loadActivity]); // eslint-disable-line react-hooks/exhaustive-deps

  // Home shows the current investigation once finished, else the latest finished one with a company.
  useEffect(() => {
    if (inv && TERMINAL.has(inv.state) && inv.ticker && inv.observations.length) { setHomeInv(inv); return; }
    if (homeInv) return;
    const last = recent.find((r) => r.state === "COMPLETED" && r.ticker);
    if (last) api.get(last.id).then(setHomeInv).catch(() => undefined);
  }, [inv, recent]); // eslint-disable-line react-hooks/exhaustive-deps

  const probe = async () => { setProbing(true); try { setStatus(await api.status(true)); } finally { setProbing(false); } };
  const updatePrefs = (p: Prefs) => { const modeChanged = p.mode !== prefs.mode; setPrefs(p); savePrefs(p); if (p.mode && modeChanged) setMode(p.mode); };

  const poll = (id: string) => {
    if (timer.current) window.clearTimeout(timer.current);
    const tick = async () => {
      try {
        const next = await api.get(id);
        setInv(next);
        if (!TERMINAL.has(next.state)) timer.current = window.setTimeout(tick, 600);
        else loadActivity();
      } catch (e) { setErr(String((e as Error).message)); }
    };
    tick();
  };
  const goInvestigation = (tab: CompanyTab = "overview") => { setPage("investigate"); setItab("company"); setCtab(tab); };
  const run = async (q = question, t = ticker) => {
    setErr(null); setFollowMsg(null); setComposing(false); goInvestigation();
    try { const s = await api.start(q, t || null, mode); setInv(s); poll(s.id); } catch (e) { setErr(String((e as Error).message)); }
  };
  const open = (id: string, tab: CompanyTab = "overview") => { setComposing(false); goInvestigation(tab); setFollowMsg(null); poll(id); };
  /** Choosing a company opens "Ask about <company>"; nothing runs until the user asks. */
  const chooseCompany = (c: CompanyHit | null) => {
    setPicked(c); setTicker(c?.ticker ?? ""); setComposing(true); setErr(null); goInvestigation();
  };
  const askAbout = (q: string, t: string) => { setQuestion(q); setTicker(t); run(q, t); };
  const ask = (q: string) => { setQuestion(q); setTicker(""); setPicked(null); run(q, ""); };
  const follow = async (t: string) => {
    try { await api.follow(t, mode); await api.checkWatchlist(t); setFollowMsg(`Following ${t}.`); loadActivity(); }
    catch (e) { setFollowMsg(String((e as Error).message)); }
  };

  const feed = useMemo(() => buildFeed(watch, decisions), [watch, decisions]);
  const onFeed = (f: FeedItem) => setPage(f.target);
  const names = useMemo(() => {
    const m: Record<string, string> = {};
    for (const c of [...(companies?.live ?? []), ...(companies?.sample ?? [])]) m[c.ticker] = c.name;
    for (const w of watch) m[w.ticker] = w.name;
    if (homeInv?.ticker && homeInv.company) m[homeInv.ticker] = homeInv.company;
    if (inv?.ticker && inv.company) m[inv.ticker] = inv.company;
    return m;
  }, [companies, watch, homeInv, inv]);
  const activity = useMemo(() => [...recent.map((r) => r.created_at), ...decisions.map((d) => d.created_at)], [recent, decisions]);
  const obsById = useMemo(() => obsIndex(inv?.observations ?? []), [inv?.observations]);
  const running = !!inv && !TERMINAL.has(inv.state);
  const finished = !!inv && TERMINAL.has(inv.state);
  const hasData = !!inv && inv.observations.length > 0;
  // Findings, risks and key figures are shown only once the investigation is finished and verified;
  // while it runs, those tabs show the live progress instead of half-checked results.
  const verified = finished && hasData;

  const sampleChoices: CompanyHit[] = mode === "sample"
    ? (companies?.sample ?? []).map((c) => ({ ticker: c.ticker, name: c.name, cik: "", exchange: "", builtin: true, zetaris_registered: false }))
    : [];
  const startCard = (
    <>
      <AskComposer company={picked} mode={mode} running={running} onAsk={askAbout} onCompany={(c) => { setPicked(c); setTicker(c?.ticker ?? ""); }}
        autoFocus choices={sampleChoices} />
      {mode === "sample" && companies && !picked && (
        <div className="flex flex-wrap gap-1.5 px-1">
          <span className="text-xs text-muted">Or try a sample case (fictional companies):</span>
          {companies.sample_cases.map((c) => (
            <button key={c.question} disabled={running} onClick={() => { setPicked(null); setQuestion(c.question); setTicker(""); run(c.question, ""); }}
              className="rounded-lg border border-soft px-2 py-1 text-xs text-ink2 hover:bg-[var(--chip)]">{c.question}</button>
          ))}
        </div>
      )}
      {err && <p className="px-1 text-sm text-critical">{err}</p>}
    </>
  );
  const followUp = inv && finished && inv.ticker && (
    <AskComposer compact company={{ ticker: inv.ticker, name: inv.company ?? inv.ticker, cik: "", exchange: "", builtin: false, zetaris_registered: false }}
      mode={inv.data_mode} running={running} onAsk={askAbout} onCompany={() => chooseCompany(null)}
      title={`Ask another question about ${shortName(inv.company ?? inv.ticker)}`} />
  );

  const ctabs: [CompanyTab, string][] = [["overview", "Overview"], ["financials", "Financials"], ["risks", "Risks"], ["sources", "Sources"], ["stress", "Stress-test"], ["notes", "Notes & tripwires"]];
  const companyView = inv && (
    <>
      <section className="rounded-[18px] border border-soft bg-panel px-5 pt-4 backdrop-blur-sm">
        <div className="flex flex-wrap items-center gap-3">
          <CompanyMark ticker={inv.ticker ?? "?"} size={48} radius={12} />
          <div className="min-w-0 flex-1">
            <h2 className="text-[19px] font-medium text-[var(--cream)]">{inv.company ? cleanName(inv.company) : finished ? "No company identified" : picked?.name ? cleanName(picked.name) : "Identifying the company…"}</h2>
            <p className="text-[12.5px] text-ink2">{inv.ticker ?? picked?.ticker ?? ""}{inv.profile?.industry ? ` · ${inv.profile.industry}` : ""}
              {(finished || inv.company) && <> · {inv.data_mode === "sample" ? "Sample data (fictional)" : inv.data_mode === "zetaris" ? "Live via Zetaris" : "Live SEC EDGAR"}</>}</p>
          </div>
          {inv.ticker && finished && <button onClick={() => follow(inv.ticker!)} className="rounded-[10px] border border-[rgba(255,255,255,0.14)] px-3 py-1.5 text-[13px] text-[var(--cream)] hover:bg-[var(--chip)]">+ Add to watchlist</button>}
          {followMsg && <span className="text-xs text-ink2">{followMsg}</span>}
        </div>
        <nav className="scrollbar-none mt-3 flex gap-1 overflow-x-auto" role="tablist" aria-label="Company sections">
          {ctabs.map(([id, label]) => (
            <button key={id} role="tab" aria-selected={ctab === id} onClick={() => setCtab(id)}
              className={cx("-mb-px shrink-0 border-b-2 px-3 pb-2.5 text-[13.5px]", ctab === id ? "border-[var(--rose-pill)] font-medium text-[var(--cream)]" : "border-transparent text-ink2 hover:text-ink")}>{label}</button>
          ))}
        </nav>
      </section>
      {inv.state === "FAILED" && <Card><p className="text-sm text-critical">Investigation failed: {inv.error}</p></Card>}
      {ctab === "overview" && (
        <>
          <div className="grid gap-4 xl:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]"><SummaryPanel inv={inv} /><ProgressPanel inv={inv} /></div>
          {followUp}
          {hasData && finished && inv.ticker && <CompanyPanel inv={inv} onOpen={() => setCtab("financials")} onOpenTab={(t) => setCtab(t)} />}
          {finished && !hasData && <Limitations inv={inv} />}
        </>
      )}
      {ctab === "financials" && (verified ? <><KeyFiguresPanel inv={inv} /><TruthPanel inv={inv} obsById={obsById} /></> : <ProgressPanel inv={inv} />)}
      {ctab === "risks" && (verified ? <RiskPanel inv={inv} obsById={obsById} /> : <ProgressPanel inv={inv} />)}
      {ctab === "sources" && (<>{verified && <SourcesPanel inv={inv} />}<div className="grid gap-4 lg:grid-cols-2"><TracePanel inv={inv} /><MemoryPanel inv={inv} /></div><Limitations inv={inv} /></>)}
      {ctab === "stress" && (<>{finished && inv.ticker && inv.findings.length > 0 ? <PremortemRoom key={inv.id + "-pm"} inv={inv} onDecide={() => setCtab("notes")} /> : <ProgressPanel inv={inv} />}<ScenarioSimulator /></>)}
      {ctab === "notes" && inv.ticker && (
        <>
          {finished && inv.findings.length > 0 && <DecisionForm key={inv.id + "-df"} ticker={inv.ticker} company={inv.company ?? inv.ticker} mode={inv.data_mode}
            investigationId={inv.id} findings={inv.findings} onSaved={() => { setRefresh((r) => r + 1); loadActivity(); }} />}
          <DecisionDiary ticker={inv.ticker} compact refreshKey={refresh} />
        </>
      )}
    </>
  );

  return (
    <GlossaryProvider entries={glossary}>
      <div className="mx-auto max-w-[1707px] px-4 pb-6 pt-4 lg:pl-[33px] lg:pr-[34px] lg:pt-[31px]">
        <div className="lg:flex lg:gap-[40px]">
          <Sidebar page={page} onNavigate={setPage} status={status} />
          <div className="min-w-0 flex-1">
            <div className="lg:pt-[2px]">
              <TopBar mode={mode} onMode={(m) => { setMode(m); setTicker(""); setPicked(null); }} onPick={(c) => chooseCompany(c)} onAsk={ask}
                name={prefs.name} onProfile={() => setPage("settings")} feed={feed} onFeed={onFeed} searchRef={searchRef} />
            </div>
            {/* The calendar / insights rail belongs to Home only; every other page uses the full width. */}
            <div className={cx("mt-[21px]", page === "home" && "min-[1400px]:grid min-[1400px]:grid-cols-[minmax(0,1fr)_327px] min-[1400px]:gap-[20px]")}>
              <main className="min-w-0 space-y-[18px]">
                {page === "home" && (
                  <>
                    <div className="pt-[2px]"><Greeting name={prefs.name} /></div>
                    <div className="!mt-[17px]"><FeatureCards onNavigate={(p) => (p === "investigate" ? goInvestigation() : setPage(p))} /></div>
                    <div className="!mt-[20px]">
                      {homeInv ? <CompanyPanel inv={homeInv} onOpen={() => open(homeInv.id)} onOpenTab={(t) => open(homeInv.id, t)} /> : (
                        <Card title="No company yet" subtitle="Search a company above, or open Investigate and run a sample case.">
                          <Button onClick={() => chooseCompany(null)}>Ask about a company</Button>
                        </Card>
                      )}
                    </div>
                    <div className="grid grid-cols-1 gap-[15px] xl:grid-cols-[minmax(0,1.22fr)_minmax(0,1fr)]">
                      <RecentPanel items={recent} names={names} onOpen={(id) => open(id)} onSeeAll={() => setPage("reports")} />
                      <WatchlistPanel items={watch} onOpen={() => setPage("watchlist")} onSeeAll={() => setPage("watchlist")} />
                    </div>
                  </>
                )}
                {page === "investigate" && (
                  <>
                    <SubTabs tabs={[["company", "Company investigation"], ["claims", "Check a post"], ["savings", "Savings & fees"]]} value={itab} onChange={setItab} />
                    {itab === "company" && (composing || !inv ? startCard : (<>{companyView}
                      <button onClick={() => chooseCompany(null)} className="text-[13px] text-ink2 hover:text-[var(--cream)]">+ Ask about a different company</button></>))}
                    {itab === "claims" && <ClaimChecker key={mode} mode={mode} />}
                    {itab === "savings" && <ScenarioSimulator />}
                  </>
                )}
                {page === "compare" && <BlindBoard mode={mode} companies={companies} onInvestigate={(t) => chooseCompany({ ticker: t, name: names[t] ?? t, cik: "", exchange: "", builtin: false, zetaris_registered: false })} />}
                {page === "premortem" && (
                  <>
                    {inv && finished && inv.ticker && inv.findings.length > 0 && <PremortemRoom key={inv.id + "-pm2"} inv={inv} onDecide={() => goInvestigation("notes")} />}
                    <ReportsPage items={recent} onOpen={(id) => open(id, "stress")} title={inv && finished && inv.ticker ? "Or pick another investigation" : "Pre-Mortem Room"}
                      hint="Pick a finished investigation to stress-test: “imagine it went badly — what most likely went wrong?”"
                      filter={(r) => r.state === "COMPLETED" && !!r.ticker} />
                  </>
                )}
                {page === "decisions" && <DecisionDiary refreshKey={refresh} />}
                {page === "watchlist" && <Watchlist mode={mode} companies={companies} />}
                {page === "sources" && <DataSourcesPage status={status} onProbe={probe} probing={probing} />}
                {page === "settings" && <SettingsPage prefs={prefs} onChange={updatePrefs} />}
                {page === "reports" && <ReportsPage items={recent} onOpen={(id) => open(id)} />}
              </main>
              {page === "home" && <aside className="mt-[18px] space-y-[16px] min-[1400px]:mt-0" aria-label="Calendar and insights">
                <Calendar activity={activity} />
                <TodaysInsights feed={feed} onOpen={onFeed} onViewAll={() => setPage("watchlist")} />
                <div className="!mt-[18px]"><AskPanel onAsk={() => chooseCompany(homeInv?.ticker ? { ticker: homeInv.ticker, name: homeInv.company ?? homeInv.ticker, cik: "", exchange: "", builtin: false, zetaris_registered: false } : null)} /></div>
              </aside>}
            </div>
          </div>
        </div>
      </div>
    </GlossaryProvider>
  );
}
