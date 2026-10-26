import { ArrowRight, Sparkles, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { CompanyMark } from "../../components/brand";
import { CompanyPicker } from "../../components/CompanyPicker";
import type { CompanyHit } from "../../types/api";
import { cleanName, shortName } from "../../lib/prefs";

/** Questions FinSight can answer from filings. Templates only; the company name is filled in, never a number. */
/** "Tesla" -> "Tesla's", "Northwind Motors" -> "Northwind Motors'". */
export const possessive = (n: string) => (n.endsWith("s") ? `${n}'` : `${n}'s`);

export function suggestedQuestions(name: string): string[] {
  const n = shortName(name);
  const ns = possessive(n);
  return [
    `Is ${ns} profit backed by real cash?`,
    `Is ${ns} revenue growing or shrinking?`,
    `Is ${ns} free cash flow positive?`,
    `What is ${ns} gross margin, and is it improving?`,
    `How much debt does ${n} have compared with its cash flow?`,
    `What are the warning signs in ${ns} filings?`,
  ];
}

export const healthCheckQuestion = (name: string) =>
  `How healthy are ${possessive(cleanName(name))} finances? Is its profit backed by operating cash flow?`;

/** Ask a question about one company. Picking a company never runs anything by itself: the user asks. */
export function AskComposer({ company, mode, running, onAsk, onCompany, autoFocus, compact, title, choices = [] }: {
  company: CompanyHit | null;
  mode: string;
  running: boolean;
  onAsk: (question: string, ticker: string) => void;
  onCompany: (c: CompanyHit | null) => void;
  autoFocus?: boolean;
  compact?: boolean;
  title?: string;
  /** One-click companies shown above the search (the fictional sample companies in sample mode). */
  choices?: CompanyHit[];
}) {
  const [q, setQ] = useState("");
  const ref = useRef<HTMLTextAreaElement>(null);
  useEffect(() => { if (autoFocus && company) ref.current?.focus(); }, [autoFocus, company?.ticker]); // eslint-disable-line react-hooks/exhaustive-deps
  const name = company ? shortName(company.name) : "";
  const submit = (text = q) => { if (company && text.trim().length >= 3) { onAsk(text.trim(), company.ticker); setQ(""); } };

  return (
    <section className={`rounded-[18px] border border-soft bg-panel backdrop-blur-sm ${compact ? "p-[16px]" : "p-[20px]"}`} aria-label="Ask about a company">
      <h2 className="flex items-center gap-2 text-[15px] font-medium text-[var(--cream)]">
        <Sparkles size={16} strokeWidth={1.8} className="text-[var(--accent)]" />{title ?? (company ? `Ask about ${name}` : "Ask about a company")}
      </h2>
      {!compact && <p className="mt-1 text-[12.5px] text-ink2">FinSight answers from official filings only, cites every number, and never tells you what to buy or sell.</p>}

      <div className="mt-3">
        {company ? (
          !compact && (
            <div className="flex items-center gap-3 rounded-[12px] bg-[rgba(255,255,255,0.04)] px-3 py-2">
              <CompanyMark ticker={company.ticker} size={32} radius={8} />
              <span className="min-w-0 flex-1 truncate text-[13.5px] text-[var(--cream)]">{cleanName(company.name)} <span className="text-ink2">({company.ticker})</span></span>
              <button onClick={() => onCompany(null)} className="flex items-center gap-1 text-[12px] text-ink2 hover:text-[var(--cream)]" aria-label="Choose a different company"><X size={14} /> change</button>
            </div>
          )
        ) : (
          <div><span className="mb-1 block text-[12.5px] text-ink2">1. Choose a company</span>
            {choices.length > 0 && (
              <div className="mb-2 flex flex-wrap gap-1.5">
                {choices.map((c) => (
                  <button key={c.ticker} onClick={() => onCompany(c)} className="flex items-center gap-2 rounded-[10px] border border-soft px-2.5 py-1.5 text-[12.5px] text-[var(--cream)] hover:bg-[rgba(255,255,255,0.05)]">
                    <CompanyMark ticker={c.ticker} size={22} radius={6} />{c.name}
                  </button>
                ))}
              </div>
            )}
            <CompanyPicker mode={mode} value={null} placeholder={choices.length ? "…or search a real company (type a letter)" : "Type a letter, e.g. A for Apple"} onChange={(c) => onCompany(c)} /></div>
        )}
      </div>

      <form className="mt-3" onSubmit={(e) => { e.preventDefault(); submit(); }}>
        {!company && <span className="mb-1 block text-[12.5px] text-ink2">2. Ask your question</span>}
        <div className="flex items-end gap-2 rounded-[14px] border border-[var(--chip-line)] bg-[var(--chip)] p-2 focus-within:border-[var(--accent)]">
          <label className="sr-only" htmlFor="ask-q">Your question</label>
          <textarea id="ask-q" ref={ref} value={q} onChange={(e) => setQ(e.target.value)} maxLength={600} rows={compact ? 1 : 2} disabled={!company}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(); } }}
            placeholder={company ? `e.g. Is ${possessive(name)} revenue growing? Was its 2024 net income really $X billion?` : "Choose a company first"}
            className="min-h-[40px] flex-1 resize-none bg-transparent px-2 py-1.5 text-[14px] text-[var(--cream)] placeholder:text-[#8f9a9e] focus:outline-none disabled:opacity-60" />
          <button type="submit" disabled={!company || running || q.trim().length < 3}
            className="flex h-[38px] shrink-0 items-center gap-2 rounded-full bg-[var(--rose-pill)] px-4 text-[13.5px] font-medium text-[var(--ink-dark)] disabled:opacity-50">
            {running ? "Working…" : "Ask"} <ArrowRight size={15} />
          </button>
        </div>
      </form>

      {company && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          <span className="w-full text-[11.5px] text-muted sm:w-auto sm:py-1">Try:</span>
          {suggestedQuestions(company.name).slice(0, compact ? 3 : 6).map((s) => (
            <button key={s} disabled={running} onClick={() => submit(s)}
              className="rounded-full border border-soft px-3 py-1 text-[12px] text-ink2 hover:bg-[rgba(255,255,255,0.05)] hover:text-[var(--cream)] disabled:opacity-50">{s}</button>
          ))}
          {!compact && (
            <button disabled={running} onClick={() => submit(healthCheckQuestion(company.name))}
              className="rounded-full border border-[var(--accent)]/50 px-3 py-1 text-[12px] text-[var(--accent)] hover:bg-[rgba(220,183,193,0.08)] disabled:opacity-50">Quick health check</button>
          )}
        </div>
      )}
    </section>
  );
}
