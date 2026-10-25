import { useState } from "react";
import { CompanyPicker } from "../../components/CompanyPicker";
import { RichText } from "../../components/Glossary";
import { Badge, Button, Card, Empty } from "../../components/ui";
import { api } from "../../lib/api";
import { usd } from "../../lib/format";
import type { Board, CompaniesResponse, CompanyHit } from "../../types/api";

export function BlindBoard({ mode, companies, onInvestigate }: {
  mode: string; companies: CompaniesResponse | null; onInvestigate: (ticker: string) => void;
}) {
  const [picked, setPicked] = useState<(CompanyHit | null)[]>([null, null, null]);
  const [sampleSel, setSampleSel] = useState<string[]>(["NWM", "CSR"]);
  const [prior, setPrior] = useState("");
  const [board, setBoard] = useState<Board | null>(null);
  const [choice, setChoice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const tickers = mode === "sample" ? sampleSel : (picked.filter(Boolean) as CompanyHit[]).map((c) => c.ticker);
  const names: Record<string, string> = mode === "sample"
    ? Object.fromEntries((companies?.sample ?? []).map((c) => [c.ticker, c.name]))
    : Object.fromEntries((picked.filter(Boolean) as CompanyHit[]).map((c) => [c.ticker, c.name]));
  const uniq = [...new Set(tickers)];

  const build = async () => {
    setBusy(true); setErr(null); setChoice(null);
    try { setBoard(await api.createBoard(uniq, mode, prior || null)); } catch (e) { setErr(String((e as Error).message)); } finally { setBusy(false); }
  };
  const reveal = async () => {
    if (!board) return;
    setBusy(true);
    try { setBoard(await api.revealBoard(board.id, choice)); } catch (e) { setErr(String((e as Error).message)); } finally { setBusy(false); }
  };
  const reset = () => { setBoard(null); setChoice(null); setPrior(""); };
  const revealed = !!board?.revealed_at;

  return (
    <div className="space-y-4">
      <Card title="Brand-Blind Board" subtitle="Compare companies on their filings with the names hidden, so a famous brand can't do your thinking for you. You choose which to look into; then reveal.">
        {!board ? (
          <>
            <div className="grid gap-2 md:grid-cols-3">
              {mode === "sample" ? (companies?.sample ?? []).map((c) => (
                <label key={c.ticker} className="flex items-center gap-2 rounded-lg border border-line px-3 py-2 text-sm text-ink">
                  <input type="checkbox" checked={sampleSel.includes(c.ticker)}
                    onChange={() => setSampleSel((s) => s.includes(c.ticker) ? s.filter((x) => x !== c.ticker) : [...s, c.ticker])} />{c.name}
                </label>
              )) : [0, 1, 2].map((i) => (
                <CompanyPicker key={i} mode={mode} value={picked[i]} placeholder={i < 2 ? `Company ${i + 1}` : "Company 3 (optional)"}
                  onChange={(c) => setPicked((p) => p.map((x, j) => (j === i ? c : x)))} />
              ))}
            </div>
            {uniq.length >= 2 && (
              <label className="mt-3 flex flex-wrap items-center gap-2 text-[13px] text-ink2">
                Optional, before you look: which do you expect to look strongest?
                <select value={prior} onChange={(e) => setPrior(e.target.value)} className="rounded-md border border-line bg-surface px-2 py-1 text-sm text-ink">
                  <option value="">Skip</option>
                  {uniq.map((t) => <option key={t} value={t}>{names[t] ?? t}</option>)}
                </select>
              </label>
            )}
            <div className="mt-3 flex items-center gap-3">
              <Button onClick={build} disabled={busy || uniq.length < 2}>{busy ? "Fetching filings…" : "Build the blind board"}</Button>
              <span className="text-xs text-muted">2 or 3 companies · data: {mode}{mode === "zetaris" ? " (first lookups may register in Zetaris)" : ""}</span>
            </div>
          </>
        ) : (
          <div className="flex flex-wrap items-center gap-2 text-xs text-ink2">
            <Badge>{board.labels.length} companies, names hidden</Badge>
            {board.has_prior_pick && <Badge tone="accent">first impression recorded</Badge>}
            <button className="ml-auto text-accent hover:underline" onClick={reset}>New board</button>
          </div>
        )}
        {err && <p className="mt-2 text-sm text-critical">{err}</p>}
      </Card>

      {busy && !board && <Empty>Fetching each company's filings… live data can take a few seconds per company.</Empty>}

      {board && (
        <Card title={revealed ? "Revealed" : "Which would you look into first, on the evidence alone?"}
          subtitle="Revenue is shown as a size band and periods as fiscal years, so obvious details don't give the names away. Highest and lowest are marked; neither means better.">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[560px] text-left text-[13px]">
              <thead>
                <tr className="text-ink">
                  <th className="w-[34%] py-2 font-medium text-muted">Evidence</th>
                  {board.labels.map((l) => (
                    <th key={l} className="py-2">
                      <div className="text-base font-semibold">Company {l}</div>
                      {revealed && board.companies && <div className="text-xs font-normal text-ink2">{board.companies[l].name} <Badge>{board.companies[l].ticker}</Badge></div>}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {board.rows.map((r) => (
                  <tr key={r.metric} className="border-t border-line align-top">
                    <td className="py-2 pr-2">
                      <div className="font-medium text-ink"><RichText text={r.label} /></div>
                      <div className="text-[11.5px] text-muted">{r.sentence}</div>
                    </td>
                    {board.labels.map((l) => {
                      const c = r.cells[l];
                      const mark = r.highest === l ? "▲ highest" : r.lowest === l ? "▼ lowest" : "";
                      const ev = revealed ? board.companies?.[l].evidence[r.metric] ?? [] : [];
                      return (
                        <td key={l} className="py-2 pr-2">
                          <div className={`num ${choice === l ? "font-semibold text-ink" : "text-ink"}`}>{c.fmt}</div>
                          <div className="text-[11px] text-muted">{c.period ?? ""}{mark && ` · ${mark}`}{c.note && ` · ${c.note}`}</div>
                          {ev.length > 0 && (
                            <div className="mt-0.5 text-[11px]">
                              {ev.slice(0, 2).map((e, i) => e.url
                                ? <a key={i} className="mr-1.5 text-accent hover:underline" href={e.url} target="_blank" rel="noreferrer">{e.form} {e.filed} ({usd(e.value)}) ↗</a>
                                : <span key={i} className="mr-1.5 text-muted">{e.form} {e.filed}</span>)}
                            </div>
                          )}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!revealed ? (
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <span className="text-[13px] text-ink">I'd look into first:</span>
              {board.labels.map((l) => (
                <button key={l} onClick={() => setChoice(l)} aria-pressed={choice === l}
                  className={`rounded-lg border px-3 py-1.5 text-sm ${choice === l ? "border-accent bg-[color-mix(in_srgb,var(--accent)_14%,transparent)] font-semibold text-ink" : "border-line text-ink2"}`}>
                  Company {l}
                </button>
              ))}
              <Button className="ml-auto" onClick={reveal} disabled={busy}>{choice ? "Reveal the names" : "Reveal without choosing"}</Button>
            </div>
          ) : board.reflection && (
            <div className="mt-3 rounded-lg bg-[color-mix(in_srgb,var(--accent)_10%,transparent)] p-3 text-[13px] text-ink">
              <p>{board.reflection.text}</p>
              <p className="mt-1 text-xs text-ink2">Choosing what to research isn't a decision to invest. FinSight doesn't pick for you.</p>
              <div className="mt-2 flex flex-wrap gap-2">
                {board.companies && Object.values(board.companies).map((c) => (
                  <Button key={c.ticker} variant="ghost" className="px-2.5 py-1 text-xs" onClick={() => onInvestigate(c.ticker)}>Investigate {c.ticker} →</Button>
                ))}
              </div>
            </div>
          )}
        </Card>
      )}
    </div>
  );
}
