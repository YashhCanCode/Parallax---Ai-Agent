// "Today's insights": real events Parallax observed, newest first. Never invented.
// Sources: watchlist reports (new filings, changed figures, tripwire hits) and the decision diary.
import type { Decision, WatchItem } from "../types/api";
import { shortName } from "./prefs";

export interface FeedItem { key: string; tone: "good" | "bad" | "info"; title: string; at: string; ticker: string; target: "watchlist" | "decisions" }

export function buildFeed(watch: WatchItem[], decisions: Decision[]): FeedItem[] {
  const out: FeedItem[] = [];
  for (const w of watch) {
    const r = w.last_report;
    if (!r || r.error) continue;
    const name = shortName(w.name);
    for (const f of r.new_filings ?? []) {
      out.push({ key: `${w.ticker}-f-${f.accession}`, tone: "good", ticker: w.ticker, target: "watchlist",
        title: `${name}: New ${f.form ?? "filing"} filing available`, at: r.checked_at });
    }
    for (const c of r.changes ?? []) {
      out.push({ key: `${w.ticker}-c-${c.key}`, tone: "bad", ticker: w.ticker, target: "watchlist",
        title: `${name}: ${c.label ?? "A figure"} was revised`, at: r.checked_at });
    }
    for (const d of r.decisions ?? []) {
      if (d.newly_hit.length) out.push({ key: `${w.ticker}-t-${d.id}`, tone: "bad", ticker: w.ticker, target: "decisions",
        title: `${name}: Tripwire hit (${d.newly_hit[0]})`, at: r.checked_at });
    }
    if (r.baseline && !(r.new_filings ?? []).length) {
      out.push({ key: `${w.ticker}-b`, tone: "info", ticker: w.ticker, target: "watchlist",
        title: `${name}: Tracking ${r.figures_tracked ?? 0} figures`, at: r.checked_at });
    }
  }
  for (const d of decisions) {
    out.push({ key: `dec-${d.id}`, tone: "info", ticker: d.ticker, target: "decisions",
      title: `${shortName(d.company)}: Decision recorded (${d.decision_label})`, at: d.created_at });
  }
  const seen = new Set<string>();
  return out.filter((x) => (seen.has(x.key) ? false : (seen.add(x.key), true)))
    .sort((a, b) => new Date(b.at).getTime() - new Date(a.at).getTime());
}
