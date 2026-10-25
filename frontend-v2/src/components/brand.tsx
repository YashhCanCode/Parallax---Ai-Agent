// Company marks, sparklines and the illustration used by the v2 dashboard.

/** Initials mark on a light tile (FinSight has no logo files, so it never fakes a logo). */
export function CompanyMark({ ticker, size = 40, radius = 10 }: { ticker: string; size?: number; radius?: number }) {
  const t = (ticker || "?").slice(0, 4);
  return (
    <span aria-hidden className="grid shrink-0 place-items-center font-bold text-[var(--ink-dark)]"
      style={{ width: size, height: size, borderRadius: radius, background: "var(--cream)", fontSize: size * (t.length > 3 ? 0.27 : 0.34), letterSpacing: "-0.02em" }}>
      {t}
    </span>
  );
}

export function Sparkline({ values, color, width = 52, height = 20 }: { values: number[]; color: string; width?: number; height?: number }) {
  if (values.length < 2) return <span style={{ width, height }} />;
  const min = Math.min(...values), max = Math.max(...values), span = max - min || 1;
  const d = values.map((v, i) => `${i ? "L" : "M"}${((i / (values.length - 1)) * (width - 2) + 1).toFixed(1)},${(height - 2 - ((v - min) / span) * (height - 4)).toFixed(1)}`).join(" ");
  return <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} aria-hidden><path d={d} fill="none" stroke={color} strokeWidth={1.6} strokeLinejoin="round" strokeLinecap="round" /></svg>;
}

/** Illustration for the cream action panel: a person reviewing a chart and a note card. Drawn for FinSight. */
export function QuestionIllustration({ className = "" }: { className?: string }) {
  const ink = "#2b2a33";
  return (
    <svg viewBox="0 0 220 200" className={className} aria-hidden fill="none" strokeLinecap="round" strokeLinejoin="round">
      <path d="M150 170c-8-40 6-72 34-80 26 10 32 48 26 84z" fill="#c9b4bc" opacity=".55" />
      <rect x="44" y="22" width="104" height="64" rx="8" fill="#fbf6f1" stroke={ink} strokeWidth="1.6" transform="rotate(-6 96 54)" />
      <path d="M70 44c4-6 10-6 13 0" stroke={ink} strokeWidth="1.6" />
      <rect x="104" y="48" width="8" height="18" rx="2" fill="#a8838f" />
      <rect x="116" y="38" width="8" height="28" rx="2" fill="#a8838f" />
      <rect x="128" y="28" width="8" height="38" rx="2" fill="#8b6e7b" />
      <rect x="30" y="96" width="62" height="40" rx="8" fill="#fbf6f1" stroke={ink} strokeWidth="1.6" />
      <path d="M40 110h40M40 120h30" stroke={ink} strokeWidth="1.6" />
      <path d="M58 136l-6 10 14-10" stroke={ink} strokeWidth="1.6" fill="#fbf6f1" />
      <circle cx="166" cy="74" r="18" fill="#f3e4dc" stroke={ink} strokeWidth="1.6" />
      <path d="M150 66c2-14 26-18 34-4-6-2-12 0-16 6-6-4-12-4-18-2z" fill={ink} />
      <path d="M140 196c0-34 10-62 28-70 22 4 34 30 36 70" fill="#4a5c6a" stroke={ink} strokeWidth="1.6" />
      <path d="M152 140c-14 6-26 2-36-8" stroke={ink} strokeWidth="1.6" />
      <circle cx="114" cy="130" r="4" fill="#f3e4dc" stroke={ink} strokeWidth="1.4" />
    </svg>
  );
}

/** Abstract mark for the FinSight logo (segmented ring), drawn for FinSight. */
export function LogoMark({ size = 28 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden>
      <circle cx="16" cy="16" r="12" fill="none" stroke="#f7efe7" strokeWidth="5" strokeDasharray="22 6" transform="rotate(-30 16 16)" />
      <circle cx="16" cy="16" r="12" fill="none" stroke="#a8838f" strokeWidth="5" strokeDasharray="14 61" transform="rotate(150 16 16)" />
    </svg>
  );
}
