import { Bell, ChevronDown, Database, Search } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { CompanyMark } from "../components/brand";
import { api } from "../lib/api";
import type { FeedItem } from "../lib/feed";
import { relTime } from "../lib/prefs";
import type { CompanyHit } from "../types/api";

export const MODES = [
  { id: "sample", label: "Sample (offline)" },
  { id: "sec_direct", label: "Live: SEC EDGAR" },
  { id: "zetaris", label: "Live: via Zetaris" },
];

/** Search a company (suggestions from the SEC directory) or press Enter to ask a free-text question. */
function CompanySearch({ onPick, onAsk, inputRef }: { onPick: (c: CompanyHit) => void; onAsk: (q: string) => void; inputRef: React.RefObject<HTMLInputElement> }) {
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<CompanyHit[]>([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const seq = useRef(0);
  useEffect(() => {
    if (q.trim().length < 1) { setHits([]); return; }
    const n = ++seq.current;
    const h = setTimeout(() => api.searchCompanies(q).then((r) => { if (n === seq.current) { setHits(r.results.slice(0, 7)); setOpen(true); setActive(-1); } }).catch(() => undefined), 180);
    return () => clearTimeout(h);
  }, [q]);
  const submit = () => {
    const t = q.trim();
    const looksLikeName = !t.includes("?") && t.split(/\s+/).length <= 3; // "tesla", "coca cola": pick, don't ask
    if (active >= 0 && hits[active]) { onPick(hits[active]); }
    else if (looksLikeName && hits[0]) { onPick(hits[0]); }
    else if (t.length >= 3) { onAsk(t); }
    setQ(""); setOpen(false);
  };
  return (
    <div className="relative min-w-0 flex-[1_1_100%] sm:flex-1">
      <form onSubmit={(e) => { e.preventDefault(); submit(); }}
        className="flex h-[46px] items-center gap-[12px] rounded-[14px] border border-[var(--chip-line)] bg-[var(--chip)] pl-[6px] pr-[14px]">
        <span className="grid h-[34px] w-[34px] place-items-center rounded-[10px] bg-[rgba(255,255,255,0.08)] text-[#d9dcda]"><Search size={18} strokeWidth={1.8} /></span>
        <label htmlFor="search" className="sr-only">Search a company or ask a question</label>
        <input id="search" ref={inputRef} value={q} onChange={(e) => setQ(e.target.value)} autoComplete="off"
          onKeyDown={(e) => {
            if (e.key === "ArrowDown") { e.preventDefault(); setActive((a) => Math.min(a + 1, hits.length - 1)); }
            else if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(a - 1, -1)); }
            else if (e.key === "Escape") setOpen(false);
          }}
          onBlur={() => setTimeout(() => setOpen(false), 150)} onFocus={() => hits.length && setOpen(true)}
          placeholder="Search a company or ask a question… (e.g. Apple, Is Tesla's revenue growing?)" maxLength={600}
          className="min-w-0 flex-1 bg-transparent text-[13.5px] text-[var(--cream)] placeholder:text-[#9aa5a8] focus:outline-none" />
      </form>
      {open && hits.length > 0 && (
        <ul role="listbox" className="absolute left-0 right-0 top-[52px] z-30 overflow-hidden rounded-[14px] border border-soft bg-[#142531] py-1 shadow-2xl">
          {hits.map((c, i) => (
            <li key={c.ticker} role="option" aria-selected={i === active} onMouseDown={(e) => { e.preventDefault(); onPick(c); setQ(""); setOpen(false); }}
              onMouseEnter={() => setActive(i)} className={`flex cursor-pointer items-center gap-3 px-3 py-2 text-[13px] ${i === active ? "bg-[rgba(255,255,255,0.06)]" : ""}`}>
              <CompanyMark ticker={c.ticker} size={26} radius={7} />
              <span className="w-14 font-semibold text-[var(--cream)]">{c.ticker}</span>
              <span className="truncate text-[var(--text-secondary)]">{c.name}</span>
              <span className="ml-auto text-[11px] text-[var(--text-muted)]">{c.exchange}</span>
            </li>
          ))}
          <li className="border-t border-soft px-3 py-1.5 text-[11px] text-[var(--text-muted)]">Pick a company, then ask your own question about it. Or press Enter to ask what you typed.</li>
        </ul>
      )}
    </div>
  );
}

export function TopBar({ mode, onMode, onPick, onAsk, name, onProfile, feed, onFeed, searchRef }: {
  mode: string; onMode: (m: string) => void; onPick: (c: CompanyHit) => void; onAsk: (q: string) => void;
  name: string; onProfile: () => void; feed: FeedItem[]; onFeed: (f: FeedItem) => void; searchRef: React.RefObject<HTMLInputElement>;
}) {
  const [bell, setBell] = useState(false);
  const recent = feed.filter((f) => Date.now() - new Date(f.at).getTime() < 86400_000);
  return (
    <header className="flex flex-wrap items-center gap-[13px]">
      <div className="flex min-w-[280px] flex-1 flex-wrap items-center gap-[13px] sm:flex-nowrap xl:max-w-[818px]">
        <CompanySearch onPick={onPick} onAsk={onAsk} inputRef={searchRef} />
        <label className="relative flex h-[46px] w-[185px] shrink-0 items-center gap-[10px] rounded-[14px] border border-[var(--chip-line)] bg-[var(--chip)] px-[14px] text-[13.5px] text-[#d9dcda]">
          <Database size={18} strokeWidth={1.7} aria-hidden />
          <select aria-label="Data source" value={mode} onChange={(e) => onMode(e.target.value)} className="min-w-0 flex-1 appearance-none bg-transparent pr-5 focus:outline-none">
            {MODES.map((m) => <option key={m.id} value={m.id}>{m.label}</option>)}
          </select>
          <ChevronDown size={16} className="pointer-events-none absolute right-[14px]" aria-hidden />
        </label>
      </div>
      <div className="ml-auto flex items-center gap-[26px]">
        <div className="relative">
          <button onClick={() => setBell((b) => !b)} aria-label={`Notifications (${recent.length} in the last day)`} aria-expanded={bell} className="relative grid h-10 w-10 place-items-center text-[#d9dcda]">
            <Bell size={22} strokeWidth={1.7} />
            {recent.length > 0 && <span className="absolute right-[7px] top-[6px] h-[9px] w-[9px] rounded-full bg-[#e07a63] ring-2 ring-[var(--page)]" aria-hidden />}
          </button>
          {bell && (
            <div className="absolute right-0 top-12 z-30 w-[320px] rounded-[16px] border border-soft bg-[#142531] p-2 shadow-2xl">
              <p className="px-2 py-1 text-[12px] font-medium text-[var(--text-secondary)]">Notifications</p>
              {feed.length === 0 ? <p className="px-2 py-3 text-[13px] text-[var(--text-muted)]">Nothing yet. Follow companies or record a decision.</p> :
                feed.slice(0, 6).map((f) => (
                  <button key={f.key} onClick={() => { setBell(false); onFeed(f); }} className="flex w-full items-start gap-2 rounded-[10px] px-2 py-2 text-left hover:bg-[rgba(255,255,255,0.05)]">
                    <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full" style={{ background: f.tone === "good" ? "var(--status-good)" : f.tone === "bad" ? "var(--status-critical)" : "var(--info)" }} />
                    <span className="min-w-0"><span className="block text-[13px] text-[var(--cream)]">{f.title}</span><span className="text-[11.5px] text-[var(--text-muted)]">{relTime(f.at)}</span></span>
                  </button>
                ))}
            </div>
          )}
        </div>
        <button onClick={onProfile} className="flex items-center gap-[10px]" aria-label="Profile and settings">
          <span className="grid h-[38px] w-[38px] place-items-center rounded-full bg-[#c9a3ad] text-[17px] text-[#3a2a31]">{(name.trim()[0] ?? "?").toUpperCase()}</span>
          <span className="hidden text-[14px] text-[var(--cream)] sm:inline">{name || "Set your name"}</span>
          <ChevronDown size={17} className="text-[#d9dcda]" />
        </button>
      </div>
    </header>
  );
}
