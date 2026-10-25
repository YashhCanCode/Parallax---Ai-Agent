import { createContext, Fragment, useContext, useId, useMemo, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import type { GlossaryEntry } from "../types/api";

const Ctx = createContext<GlossaryEntry[]>([]);

export function GlossaryProvider({ entries, children }: { entries: GlossaryEntry[]; children: ReactNode }) {
  return <Ctx.Provider value={entries}>{children}</Ctx.Provider>;
}

function escape(s: string) {
  return s.replace(/[.*+?^${}()|[\]\\/]/g, "\\$&");
}

/** A dotted-underlined term with a definition that opens on hover, focus or tap.
 *  The card is portalled to <body> with fixed positioning, so clipped or truncated rows can't cut it off,
 *  and the trigger is a span (not a button) so it can sit inside clickable rows. */
function Term({ text, entry }: { text: string; entry: GlossaryEntry }) {
  const [pos, setPos] = useState<{ x: number; y: number; up: boolean } | null>(null);
  const ref = useRef<HTMLSpanElement>(null);
  const id = useId();
  const show = () => {
    const r = ref.current?.getBoundingClientRect();
    if (!r) return;
    // The page is zoomed (see --ui-zoom); the card is positioned in zoomed units, rects come in screen pixels.
    const z = parseFloat(getComputedStyle(document.body).zoom || "1") || 1;
    const b = { left: r.left / z, top: r.top / z, bottom: r.bottom / z };
    const vw = window.innerWidth / z, vh = window.innerHeight / z;
    const w = 256;
    const x = Math.max(8, Math.min(b.left, vw - w - 8));
    const up = b.bottom + 160 > vh;
    setPos({ x, y: up ? b.top - 6 : b.bottom + 6, up });
  };
  const hide = () => setPos(null);
  return (
    <>
      <span ref={ref} role="button" tabIndex={0} aria-describedby={pos ? id : undefined}
        className="cursor-help underline decoration-dotted decoration-[color:var(--text-muted)] underline-offset-2 focus:outline-none focus-visible:ring-1 focus-visible:ring-[var(--accent)]"
        onMouseEnter={show} onMouseLeave={hide} onFocus={show} onBlur={hide}
        onClick={(e) => { e.stopPropagation(); e.preventDefault(); pos ? hide() : show(); }}
        onKeyDown={(e) => { if (e.key === "Escape") hide(); if (e.key === "Enter" || e.key === " ") { e.preventDefault(); e.stopPropagation(); pos ? hide() : show(); } }}>
        {text}
      </span>
      {pos && createPortal(
        <span id={id} role="tooltip" style={{ left: pos.x, top: pos.y, transform: pos.up ? "translateY(-100%)" : undefined }}
          className="pointer-events-none fixed z-[100] block w-64 whitespace-normal rounded-[12px] border border-soft bg-[#142531] p-3 text-left text-[12px] font-normal leading-relaxed text-[var(--text-secondary)] shadow-2xl">
          <span className="mb-0.5 block text-[12.5px] font-semibold text-[var(--cream)]">{entry.term}</span>
          {entry.definition}
        </span>, document.body)}
    </>
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
