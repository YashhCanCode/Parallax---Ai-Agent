import { FindingCard } from "../../components/FindingCard";
import { Card, SeverityPill, StatusPill } from "../../components/ui";
import type { Investigation, Observation } from "../../types/api";
import { DebtChart, ProfitCashChart } from "../financial-truth/charts";

export function RiskPanel({ inv, obsById }: { inv: Investigation; obsById: Map<string, Observation> }) {
  const risks = inv.findings.filter((f) => f.category === "risk");
  const dash = inv.charts.risk_dashboard ?? [];
  return (
    <Card id="risks" title="Risk investigation"
      subtitle="A bounded set of indicators. Each separates reported facts, the calculation and the interpretation. This is not a buy/sell rating.">
      <ul className="mb-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
        {dash.map((d) => (
          <li key={d.id} className="rounded-lg border border-line bg-sunken p-2.5">
            <div className="flex flex-wrap gap-1"><SeverityPill severity={d.severity} /><StatusPill status={d.status} /></div>
            <p className="mt-1.5 text-[12.5px] leading-snug text-ink">{d.title}</p>
          </li>
        ))}
      </ul>
      <div className="grid gap-4 lg:grid-cols-2">
        <div>
          <h3 className="mb-1 text-[13px] font-semibold text-ink">Net income vs operating cash flow (USD, fiscal years)</h3>
          <ProfitCashChart charts={inv.charts} />
        </div>
        <div>
          <h3 className="mb-1 text-[13px] font-semibold text-ink">Long-term debt at fiscal year-end (USD)</h3>
          <DebtChart charts={inv.charts} />
          <p className="mt-1 text-[11.5px] text-muted">Debt is charted separately from cash flow so neither scale distorts the other.</p>
        </div>
      </div>
      <div className="mt-4 grid gap-3 md:grid-cols-2">
        {risks.map((f) => <FindingCard key={f.id} f={f} obsById={obsById} />)}
      </div>
    </Card>
  );
}
