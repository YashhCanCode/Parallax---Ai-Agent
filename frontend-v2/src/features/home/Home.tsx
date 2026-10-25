import type * as echarts from "echarts";
import { ArrowDown, ArrowLeftRight, ArrowRight, ArrowUp, BarChart3, ChevronDown, ChevronRight, Clock3, Coins, Droplet, FileText, Lightbulb, NotebookText, ReceiptText, Search, Shield, Star } from "lucide-react";
import { useCallback, useState, type ReactNode } from "react";
import { CompanyMark, Sparkline } from "../../components/brand";
import { axisStyle, baseOption, EChart } from "../../components/EChart";
import { usd } from "../../lib/format";
import { RichText } from "../../components/Glossary";
import { cleanName, greeting, relTime, shortName } from "../../lib/prefs";
import type { Investigation, RecentItem, TrendPoint, WatchItem } from "../../types/api";
import type { Page } from "../../layout/Sidebar";

const panel = "rounded-[18px] border border-soft bg-panel backdrop-blur-sm";
const pct = (x: number) => `${Math.abs(x * 100).toFixed(1)}%`;
const fy = (p?: TrendPoint) => (p ? `FY${p.period_end.slice(0, 4)}` : "");

export function Greeting({ name }: { name: string }) {
  return (
    <div>
      <h1 className="text-[32px] font-semibold leading-[1.15] tracking-[-0.015em] text-[var(--cream)]">
        {greeting()}{name ? `, ${name}` : ""} <span aria-hidden>👋</span>
      </h1>
      <p className="mt-[8px] text-[15px] text-[#c9cfcd]">Understand the facts. Investigate the risks. Explore the possibilities.</p>
    </div>
  );
}

const CARDS: { page: Page; title: string; body: string; bg: string; dark?: boolean; Icon: typeof Search }[] = [
  { page: "investigate", title: "Investigate", body: "Ask questions about any company with evidence-backed answers.", bg: "var(--card-1)", Icon: Search },
  { page: "compare", title: "Compare", body: "Brand-blind comparison focused on the evidence.", bg: "var(--card-2)", Icon: ArrowLeftRight },
  { page: "premortem", title: "Pre-Mortem", body: "Explore what could go wrong and what could go right.", bg: "var(--card-3)", Icon: Shield },
  { page: "decisions", title: "Decision Diary", body: "Record your reasoning and set tripwires.", bg: "var(--card-4)", dark: true, Icon: NotebookText },
];

export function FeatureCards({ onNavigate }: { onNavigate: (p: Page) => void }) {
  return (
    <div className="grid gap-[15px] sm:grid-cols-2 xl:grid-cols-[1.09fr_1.03fr_1fr_1fr]">
      {CARDS.map(({ page, title, body, bg, dark, Icon }) => (
        <button key={page} onClick={() => onNavigate(page)} style={{ background: bg }}
          className="group relative flex h-[165px] flex-col rounded-[16px] p-[17px] text-left shadow-[0_8px_24px_rgba(0,0,0,0.18)] transition hover:brightness-[1.04]">
          <span className="grid h-[44px] w-[44px] place-items-center rounded-[10px] bg-[rgba(255,255,255,0.88)] text-[#2b2a33]"><Icon size={22} strokeWidth={1.8} /></span>
          <span className={`mt-[14px] text-[19px] font-semibold leading-tight ${dark ? "text-[#2b2226]" : "text-[var(--cream)]"}`}>{title}</span>
          <span className={`mt-[6px] pr-[40px] text-[13px] leading-[1.38] ${dark ? "text-[#4b3f44]" : "text-[#f1e7e3]/90"}`}>{body}</span>
          <span className="absolute bottom-[16px] right-[16px] grid h-[36px] w-[36px] place-items-center rounded-full bg-[rgba(255,255,255,0.9)] text-[#2b2a33] transition group-hover:translate-x-0.5"><ArrowRight size={18} /></span>
        </button>
      ))}
    </div>
  );
}

function Kpi({ label, value, delta, up, Icon }: { label: string; value: string; delta: string | null; up: boolean; Icon: typeof BarChart3 }) {
  return (
    <div className="relative h-[84px] rounded-[14px] border border-soft bg-panelx px-[15px] pt-[12px]">
      <div className="text-[12.5px] text-[#d2d6d4]"><RichText text={label} /></div>
      <div className="num mt-[3px] text-[21px] font-semibold tracking-[-0.01em] text-[var(--cream)]">{value}</div>
      {delta && <div className="mt-[2px] flex items-center gap-[3px] text-[12px]" style={{ color: up ? "var(--status-good)" : "var(--status-critical)" }}>
        {up ? <ArrowUp size={12} /> : <ArrowDown size={12} />}{delta} <span className="text-[#c9cfcd]">YoY</span></div>}
      <span className="absolute right-[13px] top-[16px] grid h-[38px] w-[38px] place-items-center rounded-[10px] bg-[rgba(255,255,255,0.08)] text-[#d9dcda]"><Icon size={19} strokeWidth={1.7} /></span>
    </div>
  );
}

const SERIES: [string, string, string][] = [["revenue", "Revenue", "--series-1"], ["net_income", "Net Income", "--series-2"], ["operating_cash_flow", "Operating Cash Flow", "--series-3"]];

function GroupedChart({ inv, period }: { inv: Investigation; period: "annual" | "quarterly" }) {
  const src = period === "quarterly" ? inv.charts.quarterly : inv.charts.trends;
  const ends = [...new Set(SERIES.flatMap(([k]) => (src?.[k]?.points ?? []).map((p) => p.period_end)))].sort().slice(-5);
  const label = (e: string) => {
    if (period === "annual") return e.slice(0, 4);
    const p = SERIES.map(([k]) => src?.[k]?.points.find((x) => x.period_end === e)).find(Boolean);
    const m = (d?: string | null) => (d ? new Date(d + "T00:00:00").toLocaleDateString(undefined, { month: "short" }) : "");
    return `${m(p?.period_start)}–${m(e)} ${e.slice(2, 4)}`;
  };
  const build = useCallback((t: (n: string) => string): echarts.EChartsOption => ({
    ...baseOption(t),
    grid: { left: 6, right: 8, top: 34, bottom: 4, containLabel: true },
    legend: { top: 0, left: "center", icon: "circle", itemWidth: 8, itemHeight: 8, itemGap: 16, textStyle: { color: t("--text-secondary"), fontSize: 11 } },
    tooltip: { ...baseOption(t).tooltip, trigger: "axis", axisPointer: { type: "shadow", shadowStyle: { color: "rgba(255,255,255,0.04)" } },
      formatter: (ps: unknown) => {
        const arr = ps as { seriesName: string; marker: string; data: { p?: TrendPoint } | null }[];
        const rows = arr.filter((x) => x.data?.p).map((x) => `${x.marker}${x.seriesName}: <b>${usd(x.data!.p!.value)}</b> <span style="opacity:.7;font-size:11px">${x.data!.p!.form ?? ""} filed ${x.data!.p!.filed ?? "?"}</span>`);
        return rows.join("<br/>") || "No data";
      } },
    xAxis: { type: "category", data: ends.map(label), ...axisStyle(t), axisLine: { lineStyle: { color: t("--grid") } }, splitLine: { show: false } },
    yAxis: { type: "value", ...axisStyle(t), axisLabel: { ...axisStyle(t).axisLabel, formatter: (v: number) => usd(v, 0) } },
    series: SERIES.map(([k, name, color]) => ({
      name, type: "bar", barWidth: 15, barGap: "35%",
      itemStyle: { color: t(color), borderRadius: [3, 3, 0, 0] },
      data: ends.map((e) => { const p = src?.[k]?.points.find((x) => x.period_end === e); return p ? { value: p.value, p } : null; }),
    })),
  }), [src, period, ends.join()]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!ends.length) return <p className="py-16 text-center text-[13px] text-[var(--text-muted)]">No {period} figures in this investigation{period === "quarterly" ? " (quarterly figures come from 10-Q filings)" : ""}.</p>;
  return <EChart build={build} height={172} ariaLabel={`Revenue, net income and operating cash flow, ${period}, ${ends.map(label).join(", ")}`} />;
}

type Insight = { key: string; title: string; sub: string; dir: "up" | "down" | "neutral" };

/** Four deterministic insights from the filed trend data, each citing its filing. */
export function insightsFrom(inv: Investigation): Insight[] {
  const t = inv.charts.trends ?? {};
  const last2 = (k: string) => { const p = t[k]?.points ?? []; return [p[p.length - 2], p[p.length - 1]] as const; };
  const out: Insight[] = [];
  const add = (k: string, noun: string, kind: "filing" | "compare" | "range") => {
    const [a, b] = last2(k);
    if (!b) return;
    if (!a || !a.value) { out.push({ key: k, title: `${noun} was ${usd(b.value, 1)} in ${fy(b)}`, sub: `Supported by ${b.form ?? "filing"} (${b.filed ?? "?"})`, dir: "neutral" }); return; }
    const g = (b.value - a.value) / Math.abs(a.value);
    const dir = g >= 0 ? "up" : "down";
    const verb = g >= 0 ? "grew" : "fell";
    const title = k === "revenue" ? `${noun} ${verb} ${pct(g)} in ${fy(b)}` : `${noun} ${g >= 0 ? "up" : "down"} ${pct(g)}`;
    const sub = kind === "filing" ? `${b.form ?? "Filing"} filed ${b.filed ?? "?"}`
      : kind === "compare" ? `Compared to ${fy(a)}` : `From ${usd(a.value, 1)} to ${usd(b.value, 1)}`;
    out.push({ key: k, title, sub, dir: k === "long_term_debt" ? "neutral" : dir });
  };
  add("revenue", "Revenue", "filing");
  add("net_income", "Net income", "filing");
  add("operating_cash_flow", "Operating cash flow", "compare");
  add("long_term_debt", "Long-term debt", "range");
  return out;
}

export function CompanyPanel({ inv, onOpen, onOpenTab }: { inv: Investigation; onOpen: () => void; onOpenTab: (tab: "financials" | "risks") => void }) {
  const [period, setPeriod] = useState<"annual" | "quarterly">("annual");
  const t = inv.charts.trends ?? {};
  const kpi = (k: string) => {
    const p = t[k]?.points ?? []; const b = p[p.length - 1], a = p[p.length - 2];
    return { b, g: a && b && a.value ? (b.value - a.value) / Math.abs(a.value) : null };
  };
  const rev = kpi("revenue"), ni = kpi("net_income"), ocf = kpi("operating_cash_flow"), debt = kpi("long_term_debt");
  const ticker = inv.ticker ?? "?";
  return (
    <section className={`${panel} px-[19px] pb-[12px] pt-[14px]`}>
      <div className="flex flex-wrap items-center gap-[14px]">
        <CompanyMark ticker={ticker} size={52} radius={12} />
        <div className="min-w-0">
          <h2 className="text-[19px] font-medium text-[var(--cream)]">{cleanName(inv.company ?? ticker)}</h2>
          <p className="text-[12.5px] text-[#c9cfcd]">{ticker}{inv.data_mode === "sample" && <span className="ml-2 rounded-md bg-[rgba(224,184,96,0.18)] px-1.5 py-[1px] text-[11px] text-[#e7cf98]">Sample data, fictional</span>}</p>
        </div>
        <div className="ml-auto flex items-center gap-[12px]">
          <label className="relative flex h-[34px] items-center rounded-[10px] border border-[rgba(255,255,255,0.14)] bg-[rgba(255,255,255,0.04)] pl-[14px] pr-[34px] text-[13px] text-[#e3e6e4]">
            <select aria-label="Period" value={period} onChange={(e) => setPeriod(e.target.value as "annual" | "quarterly")} className="appearance-none bg-transparent focus:outline-none">
              <option value="annual">Annual</option><option value="quarterly">Quarterly</option>
            </select>
            <ChevronDown size={15} className="pointer-events-none absolute right-[11px]" />
          </label>
          <button onClick={onOpen} className="flex h-[34px] items-center gap-[8px] rounded-[10px] bg-[var(--rose-pill)] px-[15px] text-[13px] font-medium text-[var(--ink-dark)] hover:brightness-105">
            View Full Analysis <ArrowRight size={15} />
          </button>
        </div>
      </div>
      <div className="mt-[12px] grid gap-[14px] sm:grid-cols-2 xl:grid-cols-4">
        <Kpi label={`Revenue (${fy(rev.b) || "n/a"})`} value={rev.b ? usd(rev.b.value, 1) : "n/a"} delta={rev.g != null ? pct(rev.g) : null} up={(rev.g ?? 0) >= 0} Icon={BarChart3} />
        <Kpi label="Net Income" value={ni.b ? usd(ni.b.value, 1) : "n/a"} delta={ni.g != null ? pct(ni.g) : null} up={(ni.g ?? 0) >= 0} Icon={ReceiptText} />
        <Kpi label="Operating Cash Flow" value={ocf.b ? usd(ocf.b.value, 1) : "n/a"} delta={ocf.g != null ? pct(ocf.g) : null} up={(ocf.g ?? 0) >= 0} Icon={Coins} />
        <Kpi label="Long-term Debt" value={debt.b ? usd(debt.b.value, 1) : "n/a"} delta={debt.g != null ? pct(debt.g) : null} up={(debt.g ?? 0) >= 0} Icon={FileText} />
      </div>
      <div className="mt-[14px] grid grid-cols-1 gap-[14px] xl:grid-cols-[minmax(0,1.68fr)_minmax(0,1fr)]">
        <div className="min-w-0 rounded-[14px] border border-soft bg-panelx px-[14px] pb-[4px] pt-[12px]">
          <h3 className="text-[14px] font-medium text-[var(--cream)]">Revenue, Net Income and Operating Cash Flow</h3>
          <GroupedChart inv={inv} period={period} />
        </div>
        <KeyInsights inv={inv} onOpenTab={onOpenTab} />
      </div>
    </section>
  );
}

function KeyInsights({ inv, onOpenTab }: { inv: Investigation; onOpenTab: (tab: "financials" | "risks") => void }) {
  const items = insightsFrom(inv);
  return (
    <div className="rounded-[14px] border border-soft bg-panelx px-[14px] pb-[6px] pt-[12px]">
      <div className="mb-[4px] flex items-center justify-between">
        <h3 className="flex items-center gap-[8px] text-[15px] font-medium text-[var(--cream)]"><Lightbulb size={18} strokeWidth={1.7} /> Key insights</h3>
        <button onClick={() => onOpenTab("risks")} className="flex items-center gap-1 text-[12.5px] text-[#d9dcda] hover:text-[var(--cream)]">View all <ArrowRight size={14} /></button>
      </div>
      <ul>
        {items.map((it) => (
          <li key={it.key}>
            <button onClick={() => onOpenTab("financials")} className="flex w-full items-center gap-[12px] rounded-[10px] py-[5px] text-left hover:bg-[rgba(255,255,255,0.03)]">
              <span className="grid h-[28px] w-[28px] shrink-0 place-items-center rounded-full"
                style={{ background: it.dir === "up" ? "rgba(108,192,139,0.22)" : it.dir === "down" ? "rgba(224,124,104,0.30)" : "rgba(155,168,171,0.22)",
                  color: it.dir === "up" ? "#8fd3a6" : it.dir === "down" ? "#f2a593" : "#c3ccd0" }}>
                {it.dir === "up" ? <ArrowUp size={15} /> : it.dir === "down" ? <ArrowDown size={15} /> : <Droplet size={14} />}
              </span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[12.5px] text-[var(--cream)]" title={it.title}><RichText text={it.title} /></span>
                <span className="block truncate text-[11.5px] text-[#9aa5a8]"><RichText text={it.sub} /></span>
              </span>
              <ChevronRight size={17} className="shrink-0 text-[#c9cfcd]" />
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

function ListPanel({ title, Icon, onSeeAll, children, note }: { title: string; Icon: typeof Star; onSeeAll: () => void; children: ReactNode; note?: string }) {
  return (
    <section className={`${panel} px-[15px] pb-[9px] pt-[12px]`}>
      <div className="mb-[8px] flex items-center justify-between px-[2px]">
        <h3 className="flex items-center gap-[10px] text-[15px] font-medium text-[var(--cream)]"><Icon size={18} strokeWidth={1.7} /> {title}
          {note && <span className="text-[11px] font-normal text-[var(--text-muted)]">{note}</span>}</h3>
        <button onClick={onSeeAll} className="flex items-center gap-1 text-[12.5px] text-[#d9dcda] hover:text-[var(--cream)]">See all <ArrowRight size={14} /></button>
      </div>
      {children}
    </section>
  );
}

export function RecentPanel({ items, names, onOpen, onSeeAll }: { items: RecentItem[]; names: Record<string, string>; onOpen: (id: string) => void; onSeeAll: () => void }) {
  return (
    <ListPanel title="Recent investigations" Icon={Clock3} onSeeAll={onSeeAll}>
      {items.length === 0 ? <p className="px-2 py-6 text-[13px] text-[var(--text-muted)]">No investigations yet. Search a company to start.</p> : (
        <ul className="space-y-[6px]">
          {items.slice(0, 3).map((r) => (
            <li key={r.id}>
              <button onClick={() => onOpen(r.id)} className="flex h-[42px] w-full items-center gap-[12px] rounded-[10px] bg-[rgba(255,255,255,0.035)] px-[12px] text-left hover:bg-[rgba(255,255,255,0.06)]">
                <CompanyMark ticker={r.ticker ?? "?"} size={32} radius={8} />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[13.5px] text-[var(--cream)]">{r.ticker ? `${shortName(names[r.ticker] ?? r.ticker)} (${r.ticker})` : "No company identified"}</span>
                  <span className="block truncate text-[12px] text-[#9aa5a8]">{r.question}</span>
                </span>
                <span className="shrink-0 text-[12px] text-[#c9cfcd]">{relTime(r.created_at)}</span>
                <ChevronRight size={17} className="shrink-0 text-[#c9cfcd]" />
              </button>
            </li>
          ))}
        </ul>
      )}
    </ListPanel>
  );
}

export function WatchlistPanel({ items, onOpen, onSeeAll }: { items: WatchItem[]; onOpen: (ticker: string) => void; onSeeAll: () => void }) {
  return (
    <ListPanel title="Watchlist" Icon={Star} onSeeAll={onSeeAll} note="revenue · YoY">
      {items.length === 0 ? <p className="px-2 py-6 text-[13px] text-[var(--text-muted)]">Follow a company to track its filings here.</p> : (
        <ul>
          {items.slice(0, 4).map((w) => {
            const sp = w.last_report?.spark;
            const up = (sp?.yoy ?? 0) >= 0;
            return (
              <li key={w.ticker}>
                <button onClick={() => onOpen(w.ticker)} title="Latest annual revenue and change versus the year before"
                  className="flex h-[36px] w-full items-center gap-[10px] rounded-[8px] px-[6px] text-left hover:bg-[rgba(255,255,255,0.04)]">
                  <CompanyMark ticker={w.ticker} size={26} radius={7} />
                  <span className="min-w-0 flex-1 truncate text-[13px] text-[var(--cream)]" title={`${cleanName(w.name)} (${w.ticker})`}>{shortName(w.name)}</span>
                  <span className="num w-[62px] text-right text-[13px] text-[var(--cream)]">{sp?.latest != null ? usd(sp.latest, 1) : "—"}</span>
                  <Sparkline values={sp?.values ?? []} color={up ? "var(--status-good)" : "var(--status-critical)"} />
                  <span className="num w-[44px] text-right text-[12px]" style={{ color: sp?.yoy == null ? "var(--text-muted)" : up ? "var(--status-good)" : "var(--status-critical)" }}>
                    {sp?.yoy == null ? "n/a" : `${up ? "+" : "-"}${pct(sp.yoy)}`}</span>
                  <ChevronRight size={16} className="shrink-0 text-[#c9cfcd]" />
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </ListPanel>
  );
}
