// Small shadcn/ui-style primitives (hand-written; no generator needed).
import type { ButtonHTMLAttributes, ReactNode } from "react";

export function cx(...c: (string | false | null | undefined)[]): string {
  return c.filter(Boolean).join(" ");
}

export function Card({ title, subtitle, actions, children, className, id }: {
  title?: ReactNode; subtitle?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string; id?: string;
}) {
  return (
    <section id={id} className={cx("rounded-[18px] border border-soft bg-panel p-4 backdrop-blur-sm sm:p-5", className)}>
      {(title || actions) && (
        <header className="mb-3 flex flex-wrap items-start justify-between gap-2">
          <div>
            {title && <h2 className="text-[15px] font-semibold text-ink">{title}</h2>}
            {subtitle && <p className="mt-0.5 text-[13px] text-ink2">{subtitle}</p>}
          </div>
          {actions}
        </header>
      )}
      {children}
    </section>
  );
}

const TONES = {
  neutral: "border-line bg-sunken text-ink2",
  accent: "border-transparent bg-[color-mix(in_srgb,var(--accent)_14%,transparent)] text-ink",
  good: "border-transparent bg-[color-mix(in_srgb,var(--status-good)_16%,transparent)] text-ink",
  warning: "border-transparent bg-[color-mix(in_srgb,var(--status-warning)_22%,transparent)] text-ink",
  serious: "border-transparent bg-[color-mix(in_srgb,var(--status-serious)_20%,transparent)] text-ink",
  critical: "border-transparent bg-[color-mix(in_srgb,var(--status-critical)_16%,transparent)] text-ink",
} as const;

export type Tone = keyof typeof TONES;

export function Badge({ tone = "neutral", children, title }: { tone?: Tone; children: ReactNode; title?: string }) {
  return (
    <span title={title} className={cx("inline-flex items-center gap-1 whitespace-nowrap rounded-md border px-1.5 py-0.5 text-[11.5px] font-medium", TONES[tone])}>
      {children}
    </span>
  );
}

export function Button({ variant = "primary", className, ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "ghost" }) {
  return (
    <button
      {...props}
      className={cx(
        "inline-flex items-center justify-center gap-1.5 rounded-xl px-3.5 py-2 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-50",
        variant === "primary" ? "bg-[var(--rose-pill)] text-[var(--ink-dark)] hover:brightness-105" : "border border-soft bg-[var(--chip)] text-ink hover:bg-sunken",
        className,
      )}
    />
  );
}

/** Status pairs an icon and a label with the colour, never colour alone. */
export function StatusPill({ status }: { status: string }) {
  const map: Record<string, { tone: Tone; icon: string; label: string }> = {
    supported: { tone: "good", icon: "✓", label: "Supported" },
    contradicted: { tone: "critical", icon: "✕", label: "Contradicted" },
    unresolved: { tone: "warning", icon: "?", label: "Unresolved" },
    insufficient_evidence: { tone: "neutral", icon: "∅", label: "Insufficient evidence" },
  };
  const m = map[status] ?? { tone: "neutral" as Tone, icon: "•", label: status };
  return <Badge tone={m.tone}><span aria-hidden>{m.icon}</span>{m.label}</Badge>;
}

export function SeverityPill({ severity }: { severity: string }) {
  if (severity === "elevated") return <Badge tone="serious"><span aria-hidden>▲</span>Closer look</Badge>;
  if (severity === "watch") return <Badge tone="warning"><span aria-hidden>●</span>Worth noting</Badge>;
  return <Badge><span aria-hidden>○</span>Context</Badge>;
}

export function DataStatusBadge({ status }: { status: string }) {
  const tone: Tone = status === "live" ? "good" : status === "sample" ? "warning" : status === "cached" ? "accent" : "neutral";
  const label = status === "sample" ? "SAMPLE DATA (fictional)" : status === "live" ? "LIVE" : status.toUpperCase();
  return <Badge tone={tone}>{label}</Badge>;
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="rounded-lg border border-dashed border-line px-3 py-6 text-center text-sm text-muted">{children}</p>;
}
