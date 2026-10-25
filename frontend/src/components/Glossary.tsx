import { createContext, Fragment, useContext, useId, useMemo, useState, type ReactNode } from "react";
import type { GlossaryEntry } from "../types/api";

const Ctx = createContext<GlossaryEntry[]>([]);

export function GlossaryProvider({ entries, children }: { entries: GlossaryEntry[]; children: ReactNode }) {
  return <Ctx.Provider value={entries}>{children}</Ctx.Provider>;
}

function escape(s: string) {
  return s.replace(/[.*+?^${}()|[\]\\/]/g, "\\$&");
}

/** A dotted-underlined term with a definition that opens on hover, focus or tap. */
function Term({ text, entry }: { text: string; entry: GlossaryEntry }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  return (
    <span className="relative inline-block">
      <button type="button" aria-describedby={open ? id : undefined}
        className="cursor-help underline decoration-dotted decoration-[color:var(--text-muted)] underline-offset-2"
        onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)}
        onFocus={() => setOpen(true)} onBlur={() => setOpen(false)} onClick={() => setOpen(true)}
        onKeyDown={(e) => { if (e.key === "Escape") setOpen(false); }}>
        {text}
      </button>
      {open && (
        <span id={id} role="tooltip"
          className="absolute left-0 top-full z-20 mt-1 w-64 rounded-lg border border-line bg-card p-2.5 text-left text-xs font-normal leading-relaxed text-ink2 shadow-lg">
          <span className="block font-semibold text-ink">{entry.term}</span>
          {entry.definition}
        </span>
      )}
    </span>
  );
}

/** Renders text with each glossary term (first occurrence) explained in place. */
export function RichText({ text }: { text: string }) {
  const entries = useContext(Ctx);
  const { re, lookup } = useMemo(() => {
    const lookup = new Map<string, GlossaryEntry>();
    for (const e of entries) for (const w of [e.term, ...e.aliases]) lookup.set(w.toLowerCase(), e);
    const words = [...lookup.keys()].sort((a, b) => b.length - a.length).map(escape);
    return { re: words.length ? new RegExp(`(?<![\\w-])(${words.join("|")})(?![\\w-])`, "gi") : null, lookup };
  }, [entries]);
  if (!re || !text) return <>{text}</>;
  const parts: ReactNode[] = [];
  const used = new Set<string>();
  let last = 0;
  for (const m of text.matchAll(re)) {
    const entry = lookup.get(m[0].toLowerCase());
    if (!entry || used.has(entry.term) || m.index === undefined) continue;
    used.add(entry.term);
    parts.push(text.slice(last, m.index), <Term key={m.index} text={m[0]} entry={entry} />);
    last = m.index + m[0].length;
  }
  parts.push(text.slice(last));
  return <>{parts.map((p, i) => <Fragment key={i}>{p}</Fragment>)}</>;
}
