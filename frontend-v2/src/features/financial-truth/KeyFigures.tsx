import { ArrowDown, ArrowUp, Minus } from "lucide-react";
import { RichText } from "../../components/Glossary";
import { Card, Empty } from "../../components/ui";
import type { Investigation, KeyFigure } from "../../types/api";

/** The facts sheet: every figure Parallax computed from the filings, with the filing behind it.
 *  Direction arrows are neutral on purpose: a rise is not automatically good (debt) or bad (spending). */
export function KeyFiguresPanel({ inv }: { inv: Investigation }) {
  const rows = (inv.charts.key_figures ?? []).filter((k) => k.latest);
  const missing = (inv.charts.key_figures ?? []).filter((k) => !k.latest && k.formula === "as filed");
  return (
    <Card title="Key figures" subtitle="Computed in code from the filings: the latest fiscal year, the year before, and how each figure is worked out. These are the same numbers Parallax's answers use.">
      {rows.length === 0 ? <Empty>No key figures yet.</Empty> : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] text-left text-[13px]">
            <thead className="text-[12px] text-muted">
              <tr><th className="py-1.5 font-normal">Figure</th><th className="font-normal">Latest</th><th className="font-normal">Year before</th>
                <th className="font-normal">Change</th><th className="font-normal">From</th></tr>
            </thead>
            <tbody>
              {rows.map((k) => <Row key={k.key} k={k} />)}
            </tbody>
          </table>
        </div>
      )}
      {missing.length > 0 && (
        <p className="mt-3 text-[12px] text-muted">Not reported in the filings Parallax read: {missing.map((k) => k.label).join(", ")}.</p>
      )}
    </Card>
  );
}

function Row({ k }: { k: KeyFigure }) {
  const Icon = k.direction === "up" ? ArrowUp : k.direction === "down" ? ArrowDown : Minus;
  return (
    <tr className="border-t border-soft align-top">
      <td className="py-2 pr-3 text-ink"><RichText text={k.label} /></td>
      <td className="num py-2 pr-3 text-[var(--cream)]">{k.latest?.display}<span className="ml-1 text-[11px] text-muted">{k.latest?.fy}</span></td>
      <td className="num py-2 pr-3 text-ink2">{k.prior ? <>{k.prior.display}<span className="ml-1 text-[11px] text-muted">{k.prior.fy}</span></> : "—"}</td>
      <td className="num py-2 pr-3 text-ink2">
        {k.stale ? <span className="text-[12px] text-[var(--status-warning)]">last reported {k.latest?.fy}; no current figure</span> : k.direction ? <span className="inline-flex items-center gap-1"><Icon size={12} aria-hidden />{k.change_display ?? (k.direction === "up" ? "higher" : "lower")}</span> : k.prior ? "unchanged" : "—"}
      </td>
      <td className="py-2 text-[12px] text-muted">{k.formula === "as filed" ? `${k.latest?.form ?? "filing"} filed ${k.latest?.filed ?? "?"}` : k.formula}</td>
    </tr>
  );
}
