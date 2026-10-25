import { useMemo, useState } from "react";
import { FindingCard } from "../../components/FindingCard";
import { Card } from "../../components/ui";
import { usd } from "../../lib/format";
import type { Investigation, Observation } from "../../types/api";
import { RevenueChart, SourceComparisonChart } from "./charts";

export function TruthPanel({ inv, obsById }: { inv: Investigation; obsById: Map<string, Observation> }) {
  const findings = inv.findings.filter((f) => f.category === "financial_truth" || f.category === "claim_check" || f.category === "integration");
  const claim = findings.filter((f) => f.category === "claim_check");
  const rest = findings.filter((f) => f.category !== "claim_check");
  const sc = inv.charts.source_comparison;
  const [table, setTable] = useState(false);
  const [showAll, setShowAll] = useState(false);
  const ordered = [...claim, ...rest.filter((f) => f.severity !== "info"), ...rest.filter((f) => f.severity === "info")];
  const visible = showAll ? ordered : ordered.filter((f) => f.category === "claim_check" || f.severity !== "info").slice(0, 8);
  const hidden = ordered.length - visible.length;
  return (
    <Card id="truth" title="Financial truth" subtitle="Figures compared across filings, definitions and sources. Each finding links to the exact facts behind it.">
      <div className="grid gap-4 lg:grid-cols-2">
        <div>
          <div className="mb-1 flex items-baseline justify-between gap-2">
            <h3 className="text-[13px] font-semibold text-ink">{sc?.metric_label ?? "Metric"}: every figure for {sc?.period ?? "the period"}</h3>
            <button className="text-xs text-accent hover:underline" onClick={() => setTable((x) => !x)}>{table ? "Chart" : "Table"}</button>
          </div>
          {table ? <ComparisonTable inv={inv} /> : <SourceComparisonChart charts={inv.charts} />}
          <p className="mt-1 text-[11.5px] text-muted">USD, nominal, as reported. Secondary sources are normalized to USD before comparison.</p>
        </div>
        <div>
          <h3 className="mb-1 text-[13px] font-semibold text-ink">Annual revenue (fiscal years, latest filing of record)</h3>
          <RevenueChart charts={inv.charts} />
          <p className="mt-1 text-[11.5px] text-muted">Hover a point to see its concept, filing and any earlier filed value.</p>
        </div>
      </div>
      <div className="mt-4 grid gap-3 md:grid-cols-2">
        {visible.map((f) => <FindingCard key={f.id} f={f} obsById={obsById} />)}
      </div>
      {(hidden > 0 || showAll) && (
        <button className="mt-3 text-sm font-medium text-accent hover:underline" onClick={() => setShowAll((x) => !x)}>
          {showAll ? "Show fewer findings" : `Show ${hidden} more finding(s), including context`}
        </button>
      )}
    </Card>
  );
}

function ComparisonTable({ inv }: { inv: Investigation }) {
  const bars = inv.charts.source_comparison?.bars ?? [];
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-xs">
        <thead className="text-muted"><tr><th className="py-1 pr-2">Source</th><th className="pr-2">Value</th><th className="pr-2">Concept</th><th>Basis</th></tr></thead>
        <tbody>
          {bars.map((b, i) => (
            <tr key={i} className="border-t border-line">
              <td className="py-1 pr-2 text-ink">{b.label}{b.is_current && " (of record)"}</td>
              <td className="num pr-2 text-ink">{usd(b.value)}</td>
              <td className="pr-2 text-ink2">{b.concept.replace("us-gaap:", "")}</td>
              <td className="text-ink2">{b.basis}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function SourcesPanel({ inv }: { inv: Investigation }) {
  const items = useMemo(() => [...(inv.charts.timeline ?? [])].reverse(), [inv.charts.timeline]);
  const statuses = [...new Set(inv.observations.map((o) => o.data_status))];
  const retrieved = inv.observations[0]?.retrieved_at;
  return (
    <Card id="sources" title="Sources and timeline" subtitle={`${inv.observations.length} observations · status: ${statuses.join(", ") || "none"}${retrieved ? ` · retrieved ${new Date(retrieved).toLocaleString()}` : ""}`}>
      {items.length === 0 ? <p className="text-sm text-muted">No sources.</p> : (
        <ol className="relative ml-2 border-l border-line">
          {items.map((s, i) => (
            <li key={i} className="mb-2 ml-4">
              <span className="absolute -left-[5px] mt-1.5 h-2.5 w-2.5 rounded-full border-2 border-card" style={{ background: s.kind === "secondary" ? "var(--series-3)" : "var(--series-1)" }} />
              <div className="flex flex-wrap items-baseline gap-x-2 text-[13px]">
                <span className="num font-medium text-ink">{s.date}</span>
                <span className="text-ink">{s.form ?? s.source_name}</span>
                {s.accession && <span className="text-xs text-muted">{s.accession}</span>}
                {s.url && <a className="text-xs text-accent hover:underline" href={s.url} target="_blank" rel="noreferrer">open ↗</a>}
              </div>
              <div className="text-xs text-ink2">{s.kind === "secondary" ? s.source_name + " · " : ""}{s.metrics.join(", ")}</div>
            </li>
          ))}
        </ol>
      )}
    </Card>
  );
}

export function obsIndex(obs: Observation[]): Map<string, Observation> {
  return new Map(obs.map((o) => [o.id, o]));
}

export { usd };
