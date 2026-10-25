import { useEffect, useId, useRef, useState } from "react";
import { api } from "../lib/api";
import type { CompanyHit } from "../types/api";
import { Badge } from "./ui";

/** Search any SEC-listed company by ticker or name. Keyboard: arrows to move, Enter to pick, Esc to close. */
export function CompanyPicker({ value, onChange, mode, placeholder = "Search any US-listed company (ticker or name)" }: {
  value: CompanyHit | null;
  onChange: (c: CompanyHit | null) => void;
  mode: string;
  placeholder?: string;
}) {
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<CompanyHit[]>([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [note, setNote] = useState<string | null>(null);
  const listId = useId();
  const seq = useRef(0);

  useEffect(() => {
    if (!q.trim()) { setHits([]); return; }
    const n = ++seq.current;
    const h = setTimeout(() => {
      api.searchCompanies(q).then((r) => {
        if (n !== seq.current) return;
        setHits(r.results); setActive(0); setOpen(true);
        setNote(r.directory.error ?? `${r.directory.companies.toLocaleString()} SEC-listed companies (${r.directory.source})`);
      }).catch((e) => setNote(String((e as Error).message)));
    }, 200);
    return () => clearTimeout(h);
  }, [q]);

  if (value) {
    return (
      <div className="flex min-w-0 items-center gap-2 rounded-lg border border-line bg-surface px-2 py-1.5 text-sm text-ink">
        <Badge>{value.ticker}</Badge>
        <span className="truncate">{value.name}</span>
        {mode === "zetaris" && (value.zetaris_registered
          ? <Badge tone="good">in Zetaris</Badge>
          : <Badge tone="warning" title="The first lookup registers this company's SEC data in Zetaris and verifies it (about 20-40 seconds).">registers on first use</Badge>)}
        <button type="button" className="ml-auto text-xs text-accent hover:underline" onClick={() => { onChange(null); setQ(""); }}>change</button>
      </div>
    );
  }

  const pick = (c: CompanyHit) => { onChange(c); setOpen(false); setQ(""); };
  return (
    <div className="relative min-w-0">
      <input role="combobox" aria-expanded={open} aria-controls={listId} aria-autocomplete="list" aria-label="Company"
        value={q} placeholder={placeholder} onChange={(e) => setQ(e.target.value)} onFocus={() => hits.length && setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") { e.preventDefault(); setActive((a) => Math.min(a + 1, hits.length - 1)); }
          else if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)); }
          else if (e.key === "Enter" && open && hits[active]) { e.preventDefault(); pick(hits[active]); }
          else if (e.key === "Escape") setOpen(false);
        }}
        className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink placeholder:text-muted" />
      {open && (
        <ul id={listId} role="listbox" className="absolute left-0 right-0 top-full z-20 mt-1 max-h-72 overflow-auto rounded-lg border border-line bg-card py-1 shadow-lg">
          {hits.length === 0 && <li className="px-3 py-2 text-xs text-muted">No SEC-listed company matches “{q}”.</li>}
          {hits.map((c, i) => (
            <li key={c.ticker} role="option" aria-selected={i === active} onMouseDown={(e) => { e.preventDefault(); pick(c); }}
              onMouseEnter={() => setActive(i)}
              className={`flex cursor-pointer items-center gap-2 px-3 py-1.5 text-sm ${i === active ? "bg-sunken" : ""}`}>
              <span className="w-16 shrink-0 font-semibold text-ink">{c.ticker}</span>
              <span className="truncate text-ink2">{c.name}</span>
              <span className="ml-auto flex shrink-0 gap-1">
                {c.exchange && <span className="text-[11px] text-muted">{c.exchange}</span>}
                {c.zetaris_registered && <Badge tone="good">Zetaris</Badge>}
              </span>
            </li>
          ))}
          {note && <li className="border-t border-line px-3 pt-1.5 text-[11px] text-muted">{note}</li>}
        </ul>
      )}
    </div>
  );
}
