import { useState } from "react";
import type { EvidenceRef, Finding, Observation } from "../types/api";
import { CLASS_LABEL, usd } from "../lib/format";
import { RichText } from "./Glossary";
import { Badge, SeverityPill, StatusPill } from "./ui";

function EvidenceRow({ ev, obs, counter }: { ev: EvidenceRef; obs?: Observation; counter?: boolean }) {
  if (!obs) return <li className="text-xs text-critical">Missing observation {ev.observation_id}</li>;
  const period = obs.period_type === "instant" ? `as of ${obs.period_end}` : `${obs.period_start ?? "?"} → ${obs.period_end}`;
  return (
    <li className="grid gap-x-3 gap-y-0.5 rounded-md bg-sunken px-2.5 py-1.5 text-xs sm:grid-cols-[auto_1fr_auto]">
      <span className="num font-semibold text-ink">{usd(obs.value)}</span>
      <span className="text-ink2">
        {counter && <span className="mr-1 font-medium text-ink">Counter:</span>}
        {ev.note && <span className="mr-1 text-ink">{ev.note} ·</span>}
        {period} · {obs.period_type} · {obs.concept.replace("us-gaap:", "")} · {obs.form ?? "n/a"}
        {obs.published_at && ` filed ${obs.published_at}`} · {obs.reporting_basis}
      </span>
      <span className="flex items-center gap-1.5">
        <Badge tone={obs.data_status === "sample" ? "warning" : obs.data_status === "live" ? "good" : "accent"}>{obs.data_status}</Badge>
        <Badge>{obs.retrieval_channel}</Badge>
        {obs.source_url && (
          <a className="text-accent underline-offset-2 hover:underline" href={obs.source_url} target="_blank" rel="noreferrer">
            source ↗
          </a>
        )}
      </span>
    </li>
  );
}

export function FindingCard({ f, obsById }: { f: Finding; obsById: Map<string, Observation> }) {
  const [open, setOpen] = useState(false);
  const hasDetail = f.supporting_evidence.length + f.counterevidence.length > 0 || f.calculation_details;
  return (
    <article className="rounded-lg border border-line bg-card p-3">
      <div className="flex flex-wrap items-center gap-1.5">
        <StatusPill status={f.status} />
        <Badge>{CLASS_LABEL[f.classification]}</Badge>
        <SeverityPill severity={f.severity} />
      </div>
      <h3 className="mt-2 text-sm font-semibold leading-snug text-ink">{f.title}</h3>
      {f.plain_language && (
        <p className="mt-1.5 rounded-md bg-[color-mix(in_srgb,var(--accent)_9%,transparent)] px-2.5 py-1.5 text-[13px] leading-relaxed text-ink">
          <span className="font-semibold">In plain words: </span><RichText text={f.plain_language} />
        </p>
      )}
      <p className="mt-1.5 text-[13px] leading-relaxed text-ink2"><RichText text={f.claim} /></p>
      {f.why_it_matters && <p className="mt-1.5 text-[12.5px] text-ink2"><span className="font-medium text-ink">Why it matters: </span>{f.why_it_matters}</p>}
      {f.uncertainty_or_limitations && (
        <p className="mt-1 text-[12.5px] text-muted"><span className="font-medium text-ink2">Limits: </span>{f.uncertainty_or_limitations}</p>
      )}
      {hasDetail && (
        <button className="mt-2 text-xs font-medium text-accent hover:underline" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
          {open ? "Hide evidence" : `Inspect evidence (${f.supporting_evidence.length + f.counterevidence.length})`}
        </button>
      )}
      {open && (
        <div className="mt-2 space-y-2">
          <ul className="space-y-1">
            {f.supporting_evidence.map((e, i) => <EvidenceRow key={"s" + i} ev={e} obs={obsById.get(e.observation_id)} />)}
            {f.counterevidence.map((e, i) => <EvidenceRow key={"c" + i} ev={e} obs={obsById.get(e.observation_id)} counter />)}
          </ul>
          {f.calculation_details && (
            <pre className="max-h-56 overflow-auto rounded-md bg-sunken p-2 text-[11px] leading-relaxed text-ink2">
              {JSON.stringify(f.calculation_details, null, 2)}
            </pre>
          )}
        </div>
      )}
    </article>
  );
}
