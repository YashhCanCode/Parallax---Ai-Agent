import { useCallback } from "react";
import type * as echarts from "echarts";
import type { CallbackDataParams } from "echarts/types/dist/shared";
import { axisStyle, baseOption, EChart } from "../../components/EChart";
import { usd } from "../../lib/format";
import type { Charts, TrendPoint } from "../../types/api";

type T = (n: string) => string;

const yAxisUsd = (t: T) => ({ type: "value" as const, ...axisStyle(t), axisLabel: { ...axisStyle(t).axisLabel, formatter: (v: number) => usd(v, 0) } });

function trendTooltip(params: unknown): string {
  const ps = (Array.isArray(params) ? params : [params]) as { seriesName: string; marker: string; data: { p: TrendPoint } }[];
  const head = ps[0]?.data?.p;
  const rows = ps.map((x) => {
    const p = x.data.p;
    const rev = p.revised ? ` <span style="opacity:.7">(first filed ${usd(p.original_value)})</span>` : "";
    return `${x.marker}${x.seriesName}: <b>${usd(p.value)}</b>${rev}<br/><span style="opacity:.7;font-size:11px">${p.concept.replace("us-gaap:", "")} · ${p.form ?? ""} filed ${p.filed ?? "?"}</span>`;
  });
  return `<div style="font-weight:600;margin-bottom:4px">${head?.label ?? ""}</div>${rows.join("<br/>")}`;
}

const fyLabel = (periodEnd: string) => `FY${periodEnd.slice(0, 4)}`;

function lineSeries(name: string, pts: TrendPoint[], color: string, surface: string, axis: string[]): echarts.SeriesOption {
  const byEnd = new Map(pts.map((p) => [p.period_end, p]));
  return {
    name, type: "line", connectNulls: false,
    data: axis.map((end) => { const p = byEnd.get(end); return p ? { value: p.value, p } : null; }),
    lineStyle: { width: 2, color }, itemStyle: { color, borderColor: surface, borderWidth: 2 },
    symbol: "circle", symbolSize: 8, emphasis: { scale: 1.4 },
    endLabel: { show: true, formatter: (x: CallbackDataParams) => usd((x.data as { p: TrendPoint }).p.value, 1), color: "inherit", fontSize: 11 },
  };
}

/** Revenue: single series, so no legend box; the title names it. */
export function RevenueChart({ charts }: { charts: Charts }) {
  const pts = charts.trends?.revenue?.points ?? [];
  const build = useCallback((t: T): echarts.EChartsOption => ({
    ...baseOption(t),
    legend: { show: false },
    grid: { left: 8, right: 56, top: 16, bottom: 8, containLabel: true },
    tooltip: { ...baseOption(t).tooltip, trigger: "axis", axisPointer: { type: "line", lineStyle: { color: t("--border") } }, formatter: trendTooltip },
    xAxis: { type: "category", data: pts.map((p) => fyLabel(p.period_end)), ...axisStyle(t), splitLine: { show: false } },
    yAxis: yAxisUsd(t),
    series: [lineSeries("Revenue", pts, t("--series-1"), t("--surface-1"), pts.map((p) => p.period_end))],
  }), [pts]);
  if (!pts.length) return <p className="text-sm text-muted">No annual revenue in the data.</p>;
  return <EChart build={build} height={230} ariaLabel={`Annual revenue by fiscal year: ${pts.map((p) => `${p.period_end} ${usd(p.value)}`).join(", ")}`} />;
}

/** Profit vs operating cash flow on ONE shared USD axis (same unit, comparable scale). */
export function ProfitCashChart({ charts }: { charts: Charts }) {
  const ni = charts.trends?.net_income?.points ?? [];
  const ocf = charts.trends?.operating_cash_flow?.points ?? [];
  const build = useCallback((t: T): echarts.EChartsOption => {
    const axis = [...new Set([...ni, ...ocf].map((p) => p.period_end))].sort();
    return {
      ...baseOption(t),
      grid: { left: 8, right: 56, top: 36, bottom: 8, containLabel: true },
      tooltip: { ...baseOption(t).tooltip, trigger: "axis", axisPointer: { type: "line", lineStyle: { color: t("--border") } },
                 formatter: (ps: unknown) => trendTooltip((ps as { data: unknown }[]).filter((x) => x.data)) },
      xAxis: { type: "category", data: axis.map(fyLabel), ...axisStyle(t), splitLine: { show: false } },
      yAxis: yAxisUsd(t),
      series: [lineSeries("Net income", ni, t("--series-2"), t("--surface-1"), axis), lineSeries("Operating cash flow", ocf, t("--series-3"), t("--surface-1"), axis)],
    };
  }, [ni, ocf]);
  if (!ni.length && !ocf.length) return <p className="text-sm text-muted">No profit or cash-flow data.</p>;
  return <EChart build={build} height={250} ariaLabel={`Net income and operating cash flow by fiscal year. Net income: ${ni.map((p) => `${p.period_end} ${usd(p.value)}`).join(", ")}. Operating cash flow: ${ocf.map((p) => `${p.period_end} ${usd(p.value)}`).join(", ")}.`} />;
}

export function DebtChart({ charts }: { charts: Charts }) {
  const pts = charts.trends?.long_term_debt?.points ?? [];
  const build = useCallback((t: T): echarts.EChartsOption => ({
    ...baseOption(t),
    legend: { show: false },
    grid: { left: 8, right: 16, top: 16, bottom: 8, containLabel: true },
    tooltip: { ...baseOption(t).tooltip, trigger: "item", formatter: (x: unknown) => trendTooltip([x]) },
    xAxis: { type: "category", data: pts.map((p) => fyLabel(p.period_end)), ...axisStyle(t), splitLine: { show: false } },
    yAxis: yAxisUsd(t),
    series: [{ type: "bar", name: "Long-term debt", barMaxWidth: 28, data: pts.map((p) => ({ value: p.value, p })),
               itemStyle: { color: t("--series-1"), borderRadius: [4, 4, 0, 0] } }],
  }), [pts]);
  if (!pts.length) return <p className="text-sm text-muted">No long-term debt facts were found. Missing data is not the same as zero debt.</p>;
  return <EChart build={build} height={200} ariaLabel={`Long-term debt at fiscal year-end: ${pts.map((p) => `${p.period_end} ${usd(p.value)}`).join(", ")}`} />;
}

const KIND_LABEL: Record<string, string> = {
  filing: "Filing (earlier or other concept)", current: "Filing of record", secondary: "Secondary source",
  partial: "Partial year (quarter or year-to-date)", claim: "Your claim",
};

/** Horizontal bars: every figure found for one period, so differences are visible side by side. */
export function SourceComparisonChart({ charts }: { charts: Charts }) {
  const sc = charts.source_comparison;
  const bars = sc?.bars ?? [];
  const build = useCallback((t: T): echarts.EChartsOption => {
    const color = (k: string) => k === "current" ? t("--series-1") : k === "claim" ? t("--series-2") : k === "secondary" ? t("--series-3") : t("--series-neutral");
    const kinds = bars.map((b) => (b.kind === "filing" && b.is_current ? "current" : b.kind === "quarterly" || b.kind === "ytd" ? "partial" : b.kind));
    const present = [...new Set(kinds)];
    return {
      ...baseOption(t),
      grid: { left: 8, right: 64, top: 40, bottom: 8, containLabel: true },
      legend: { ...baseOption(t).legend, data: present.map((k) => ({ name: KIND_LABEL[k], itemStyle: { color: color(k) } })) },
      tooltip: { ...baseOption(t).tooltip, trigger: "item", formatter: (x: unknown) => {
        const d = (x as { data: { b: (typeof bars)[number] } }).data.b;
        return `<b>${d.label}</b><br/>${usd(d.value)}<br/><span style="opacity:.7;font-size:11px">${d.concept} · basis: ${d.basis}${d.published_at ? ` · published ${d.published_at}` : ""}</span>`;
      } },
      xAxis: { type: "value", ...axisStyle(t), axisLabel: { ...axisStyle(t).axisLabel, formatter: (v: number) => usd(v, 0) } },
      yAxis: { type: "category", inverse: true, data: bars.map((b) => b.label), ...axisStyle(t), splitLine: { show: false },
               axisLabel: { ...axisStyle(t).axisLabel, width: 170, overflow: "truncate" } },
      series: present.map((k) => ({
        name: KIND_LABEL[k], type: "bar", stack: "one", barMaxWidth: 18,
        data: bars.map((b, i) => (kinds[i] === k ? { value: b.value, b } : null)),
        itemStyle: { color: color(k), borderRadius: [0, 4, 4, 0] },
        label: { show: kinds.includes(k), position: "right", color: t("--text-secondary"), fontSize: 11, formatter: (x: CallbackDataParams) => usd(Number(x.value), 1) },
      })),
    };
  }, [bars]);
  if (!bars.length) return <p className="text-sm text-muted">No figures to compare for this period.</p>;
  return <EChart build={build} height={Math.max(160, 44 + bars.length * 34)} ariaLabel={`${sc?.metric_label} for ${sc?.period}: ${bars.map((b) => `${b.label} ${usd(b.value)}`).join("; ")}`} />;
}
