import { useCallback, useEffect, useState } from "react";
import type * as echarts from "echarts";
import type { CallbackDataParams } from "echarts/types/dist/shared";
import { axisStyle, baseOption, EChart } from "../../components/EChart";
import { RichText } from "../../components/Glossary";
import { Card } from "../../components/ui";
import { api } from "../../lib/api";
import { money, usd } from "../../lib/format";
import type { ScenarioResponse } from "../../types/api";

type Option = { name: string; annual_return_pct: number; annual_fee_pct: number };

const PRESETS: Record<string, { label: string; hint: string; options: Option[]; shared: { initial_amount: number; monthly_contribution: number; years: number; inflation_pct: number } }> = {
  compare: {
    label: "Compare where to save",
    hint: "The same money in three places. The rates below are example assumptions you can change, not quotes for any real product.",
    options: [
      { name: "Savings account", annual_return_pct: 3, annual_fee_pct: 0 },
      { name: "Low-fee index fund", annual_return_pct: 6, annual_fee_pct: 0.1 },
      { name: "High-fee managed fund", annual_return_pct: 6, annual_fee_pct: 1.5 },
    ],
    shared: { initial_amount: 5000, monthly_contribution: 200, years: 20, inflation_pct: 2.5 },
  },
  market: {
    label: "Bad / middle / good years",
    hint: "One investment under three different return assumptions, to show the range of outcomes.",
    options: [
      { name: "Adverse", annual_return_pct: 1, annual_fee_pct: 0.5 },
      { name: "Baseline", annual_return_pct: 5, annual_fee_pct: 0.5 },
      { name: "Favorable", annual_return_pct: 8, annual_fee_pct: 0.5 },
    ],
    shared: { initial_amount: 10000, monthly_contribution: 200, years: 10, inflation_pct: 2.5 },
  },
};
const COLORS = ["--series-1", "--series-2", "--series-3"];

export function ScenarioSimulator() {
  const [preset, setPreset] = useState<keyof typeof PRESETS>("compare");
  const [shared, setShared] = useState(PRESETS.compare.shared);
  const [opts, setOpts] = useState<Option[]>(PRESETS.compare.options);
  const [real, setReal] = useState(false);
  const [resp, setResp] = useState<ScenarioResponse | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const pick = (k: keyof typeof PRESETS) => { setPreset(k); setShared(PRESETS[k].shared); setOpts(PRESETS[k].options); };

  useEffect(() => {
    const payload = opts.map((o) => ({ ...o, initial_amount: shared.initial_amount, monthly_contribution: shared.monthly_contribution,
                                       years: shared.years, inflation_pct: shared.inflation_pct }));
    const h = setTimeout(() => {
      api.scenarios(payload).then((r) => { setResp(r); setErr(null); }).catch((e) => setErr(String(e.message ?? e)));
    }, 250);
    return () => clearTimeout(h);
  }, [opts, shared]);

  const build = useCallback((t: (n: string) => string): echarts.EChartsOption => ({
    ...baseOption(t),
    grid: { left: 8, right: 72, top: 36, bottom: 8, containLabel: true },
    tooltip: { ...baseOption(t).tooltip, trigger: "axis", valueFormatter: (v) => money(Number(v)) },
    xAxis: { type: "category", name: "Year", nameLocation: "end", nameTextStyle: { color: t("--text-muted"), fontSize: 11 },
             data: resp?.results[0]?.yearly.map((y) => String(y.year)) ?? [], ...axisStyle(t), splitLine: { show: false } },
    yAxis: { type: "value", ...axisStyle(t), axisLabel: { ...axisStyle(t).axisLabel, formatter: (v: number) => usd(v, 0) } },
    series: (resp?.results ?? []).map((r, i) => ({
      name: r.name, type: "line", symbol: "none", lineStyle: { width: 2, color: t(COLORS[i]) }, itemStyle: { color: t(COLORS[i]) },
      data: r.yearly.map((y) => (real ? y.real_balance : y.nominal_balance)),
      endLabel: { show: true, formatter: (x: CallbackDataParams) => usd(Number(x.value), 1), color: t("--text-secondary"), fontSize: 11 },
    })),
  }), [resp, real]);

  const num = (v: string) => (v === "" ? 0 : Number(v));
  const highestFee = resp ? [...resp.results].sort((a, b) => b.inputs.annual_fee_pct - a.inputs.annual_fee_pct)[0] : null;
  const sharedFields = [
    ["initial_amount", "Starting amount ($)", 100, 0, 1e9],
    ["monthly_contribution", "Added each month ($)", 25, 0, 1e7],
    ["years", "Years", 1, 1, 60],
    ["inflation_pct", "Inflation (%/yr)", 0.5, -5, 30],
  ] as const;

  return (
    <Card id="scenarios" title="Savings and fees simulator"
      subtitle="Hypothetical outcomes under assumptions you choose. These are not predictions, and real returns go up and down and can be negative.">
      <div className="mb-3 flex flex-wrap gap-1.5" role="tablist" aria-label="Simulator preset">
        {(Object.keys(PRESETS) as (keyof typeof PRESETS)[]).map((k) => (
          <button key={k} role="tab" aria-selected={preset === k} onClick={() => pick(k)}
            className={`rounded-md border px-2.5 py-1 text-xs ${preset === k ? "border-accent bg-[color-mix(in_srgb,var(--accent)_12%,transparent)] text-ink" : "border-line text-ink2"}`}>
            {PRESETS[k].label}
          </button>
        ))}
      </div>
      <p className="mb-2 text-xs text-ink2">{PRESETS[preset].hint}</p>
      <div className="grid gap-3 [grid-template-columns:repeat(auto-fit,minmax(9rem,1fr))]">
        {sharedFields.map(([k, label, step, min, max]) => (
          <label key={k} className="text-xs text-ink2">{label}
            <input type="number" min={min} max={max} step={step} value={shared[k]}
              onChange={(e) => setShared((s) => ({ ...s, [k]: Math.min(max, Math.max(min, num(e.target.value))) }))}
              className="num mt-1 w-full rounded-md border border-line bg-surface px-2 py-1.5 text-sm text-ink" />
          </label>
        ))}
      </div>
      {/* auto-fit keeps the option boxes readable whether the card is full width or half width */}
      <div className="mt-3 grid gap-3 [grid-template-columns:repeat(auto-fit,minmax(14rem,1fr))]">
        {opts.map((o, i) => (
          <fieldset key={o.name} className="rounded-lg border border-line p-2.5">
            <legend className="flex items-center gap-1.5 px-1 text-[13px] font-semibold text-ink">
              <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: `var(${COLORS[i]})` }} aria-hidden />{o.name}
            </legend>
            {([["annual_return_pct", "Assumed return", 0.5, -50, 50], ["annual_fee_pct", "Yearly fee", 0.1, 0, 10]] as const).map(([k, label, step, min, max]) => (
              <label key={k} className="mt-1 flex items-center justify-between gap-2 text-xs text-ink2">
                {label}
                <span className="flex items-center gap-1">
                  <input type="number" step={step} min={min} max={max} value={o[k]}
                    onChange={(e) => setOpts((all) => all.map((x, j) => j === i ? { ...x, [k]: Math.min(max, Math.max(min, num(e.target.value))) } : x))}
                    className="num w-20 rounded-md border border-line bg-surface px-1.5 py-1 text-right text-sm text-ink" />%
                </span>
              </label>
            ))}
          </fieldset>
        ))}
      </div>

      {highestFee && highestFee.fee_drag > 0 && (
        <p className="mt-3 rounded-lg bg-[color-mix(in_srgb,var(--status-warning)_16%,transparent)] px-3 py-2 text-[13px] text-ink">
          <span className="font-semibold">Fees add up:</span> a {highestFee.inputs.annual_fee_pct}% yearly fee on “{highestFee.name}” costs about{" "}
          <span className="num font-semibold">{money(highestFee.fee_drag)}</span> over {highestFee.inputs.years} years, compared with the same
          plan at no fee. That's {Math.round((highestFee.fee_drag / highestFee.final_without_fees) * 100)}% of what it would otherwise grow to,
          and it includes the growth the fees would have earned.
        </p>
      )}

      <div className="mt-3 flex items-center gap-2 text-xs text-ink2">
        <span>Show:</span>
        {[false, true].map((r) => (
          <button key={String(r)} onClick={() => setReal(r)} className={`rounded-md border px-2 py-1 ${real === r ? "border-accent text-ink" : "border-line"}`}>
            {r ? "After inflation (real)" : "Before inflation (nominal)"}
          </button>
        ))}
      </div>
      {err && <p className="mt-2 text-sm text-critical">Could not calculate: {err}</p>}
      {resp && (
        <>
          <EChart build={build} height={260} ariaLabel={`Hypothetical balances: ${resp.results.map((r) => `${r.name} ends at ${money(real ? r.final_real : r.final_nominal)}`).join("; ")}`} />
          <div className="overflow-x-auto">
            <table className="mt-2 w-full text-left text-xs">
              <thead className="text-muted"><tr><th className="py-1">Option</th><th>You put in</th><th>Final</th><th>After inflation</th><th>Fees paid</th><th>Lost to fees</th></tr></thead>
              <tbody>
                {resp.results.map((r) => (
                  <tr key={r.name} className="num border-t border-line text-ink">
                    <td className="py-1">{r.name}</td><td>{money(r.total_contributed)}</td><td>{money(r.final_nominal)}</td>
                    <td>{money(r.final_real)}</td><td>{money(r.total_fees)}</td><td>{money(r.fee_drag)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-2 text-xs text-ink2"><RichText text="Savings accounts and funds carry different risks: a fund's value can fall, sometimes for years, which a constant-return model does not show. Lost to fees includes compounding on the fees." /></p>
          <details className="mt-2 text-xs text-ink2">
            <summary className="cursor-pointer text-ink">Formula and assumptions</summary>
            <p className="mt-1">{resp.formula}</p>
            <ul className="mt-1 list-disc pl-4">{resp.assumptions.map((a) => <li key={a}>{a}</li>)}</ul>
          </details>
          <p className="mt-2 text-[12px] font-medium text-ink2">{resp.disclaimer}</p>
        </>
      )}
    </Card>
  );
}
