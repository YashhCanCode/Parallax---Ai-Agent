import { useMemo, useState } from "react";
import { FindingCard } from "../../components/FindingCard";
import { Badge, Button, Card, DataStatusBadge, Empty, StatusPill } from "../../components/ui";
import { api } from "../../lib/api";
import { obsIndex } from "../financial-truth/TruthPanel";
import type { ClaimCheckResponse, ClaimResult } from "../../types/api";

const EXAMPLES = {
  sample: "Northwind Motors had a huge 2024: revenue of $13.6 billion and net income of $4.4B. Its 2023 revenue was $48.9 billion, and margins grew 12%.",
  live: "Tesla's 2024 revenue was $97.7 billion and Apple's 2024 net income hit $93.7 billion. Microsoft made $500 billion in revenue in 2025.",
};

function Sentence({ c }: { c: ClaimResult }) {
  const [a, b] = c.span;
  return (
    <blockquote className="border-l-2 border-line pl-2.5 text-[13px] italic text-ink2">
      “{c.sentence.slice(0, a)}<mark className="rounded bg-[color-mix(in_srgb,var(--status-warning)_35%,transparent)] px-0.5 not-italic text-ink">{c.sentence.slice(a, b)}</mark>{c.sentence.slice(b)}”
    </blockquote>
  );
}

export function ClaimChecker({ mode }: { mode: string }) {
  const [text, setText] = useState(mode === "sample" ? EXAMPLES.sample : EXAMPLES.live);
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState<ClaimCheckResponse | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const obsById = useMemo(() => obsIndex(res?.observations ?? []), [res]);

  const run = async () => {
    setBusy(true); setErr(null);
    try { setRes(await api.checkClaims(text, mode)); } catch (e) { setErr(String((e as Error).message)); } finally { setBusy(false); }
  };

  return (
    <div className="space-y-4">
      <Card title="Check a post or article" subtitle="Paste text with financial numbers. Parallax finds each claim and checks it against official filings. Opinions aren't judged, only numbers. Any SEC-listed company works if its ticker is written like $PLTR or (NASDAQ: PLTR).">
        <label htmlFor="claimtext" className="sr-only">Text to check</label>
        <textarea id="claimtext" value={text} onChange={(e) => setText(e.target.value)} rows={5} maxLength={8000}
          className="w-full rounded-lg border border-line bg-surface p-3 text-sm leading-relaxed text-ink placeholder:text-muted"
          placeholder="Paste a tweet, news paragraph or message…" />
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <Button onClick={run} disabled={busy || text.trim().length < 3}>{busy ? "Checking…" : "Check claims"}</Button>
          <span className="text-xs text-muted">Examples:</span>
          <button className="rounded-md border border-line px-2 py-0.5 text-xs text-ink2 hover:bg-sunken" onClick={() => setText(EXAMPLES.sample)}>Sample post (fictional company)</button>
          <button className="rounded-md border border-line px-2 py-0.5 text-xs text-ink2 hover:bg-sunken" onClick={() => setText(EXAMPLES.live)}>Live post (real companies)</button>
          <span className="ml-auto text-xs text-muted">Data mode: {mode}</span>
        </div>
        {err && <p className="mt-2 text-sm text-critical">{err}</p>}
      </Card>

      {busy && !res && <Empty>Fetching filings and checking each number… (live data can take a few seconds per company)</Empty>}

      {res && (
        <>
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <span className="font-semibold text-ink">{res.claims.length} claim(s) checked</span>
            {Object.entries(res.counts).map(([s, n]) => <span key={s} className="flex items-center gap-1"><StatusPill status={s} /><span className="text-xs text-muted">×{n}</span></span>)}
            {res.companies.map((c) => (
              <span key={c.ticker} className="flex items-center gap-1"><Badge>{c.ticker} · {c.mode_used}</Badge>{c.data_status.map((d) => <DataStatusBadge key={d} status={d} />)}</span>
            ))}
          </div>
          {res.claims.length === 0 && <Empty>No checkable claims found. A claim needs a supported company, a figure (revenue, profit, cash flow or debt) and an amount.</Empty>}
          <div className="grid gap-3 lg:grid-cols-2">
            {res.claims.map((c, i) => (
              <div key={i} className="space-y-1.5">
                <Sentence c={c} />
                {c.notes.length > 0 && <p className="text-xs text-muted">{c.notes.join(" ")}</p>}
                <FindingCard f={c.finding} obsById={obsById} />
              </div>
            ))}
          </div>
          {res.not_checked.length > 0 && (
            <Card title={`Not checked (${res.not_checked.length})`} subtitle="Numbers Parallax found but could not check, with the reason.">
              <ul className="space-y-1 text-[13px] text-ink2">
                {res.not_checked.map((n, i) => <li key={i}><span className="font-medium text-ink">{n.text}</span> — {n.reason} <span className="text-muted">(“{n.sentence.slice(0, 90)}{n.sentence.length > 90 ? "…" : ""}”)</span></li>)}
              </ul>
            </Card>
          )}
          {(res.notes.length > 0 || res.truncated) && (
            <ul className="list-disc pl-5 text-xs text-muted">
              {res.truncated && <li>Only the first 4,000 characters were checked.</li>}
              {res.notes.map((n) => <li key={n}>{n}</li>)}
            </ul>
          )}
        </>
      )}
    </div>
  );
}
