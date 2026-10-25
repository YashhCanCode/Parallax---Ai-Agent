import { useState } from "react";
import { RichText } from "../../components/Glossary";
import { Badge, Button, Card } from "../../components/ui";
import { api } from "../../lib/api";
import type { Finding, Investigation, Premortem, VoicePoint } from "../../types/api";

function Voice({ title, icon, tone, points, findings, aiWritten }: {
  title: string; icon: string; tone: string; points: VoicePoint[]; findings: Map<string, Finding>; aiWritten: boolean;
}) {
  return (
    <section className="rounded-lg border border-line p-3" style={{ borderTop: `3px solid var(${tone})` }}>
      <h3 className="flex items-center gap-1.5 text-sm font-semibold text-ink"><span aria-hidden>{icon}</span>{title}</h3>
      <ol className="mt-2 space-y-2.5">
        {points.map((p, i) => (
          <li key={i} className="text-[13px] leading-relaxed text-ink">
            <RichText text={p.text} />
            {p.finding_ids.length > 0 && (
              <div className="mt-1 space-y-0.5 rounded-md bg-sunken px-2 py-1 text-[11.5px] text-ink2">
                <span className="font-medium text-muted">{aiWritten ? "Check against the verified finding:" : "From the finding:"}</span>
                {p.finding_ids.map((id) => {
                  const f = findings.get(id);
                  return <div key={id}>• {f ? f.title : id}</div>;
                })}
              </div>
            )}
          </li>
        ))}
      </ol>
    </section>
  );
}

export function PremortemRoom({ inv, onDecide }: { inv: Investigation; onDecide: () => void }) {
  const [pm, setPm] = useState<Premortem | null>(inv.premortem ?? null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [answered, setAnswered] = useState<Set<number>>(new Set());
  const findings = new Map(inv.findings.map((f) => [f.id, f]));
  const ai = !!pm && pm.generated_by !== "deterministic";

  const run = async () => {
    setBusy(true); setErr(null);
    try { setPm(await api.premortem(inv.id)); } catch (e) { setErr(String((e as Error).message)); } finally { setBusy(false); }
  };

  return (
    <Card id="premortem" title="Pre-Mortem Room"
      subtitle="Before deciding, imagine it went badly. Two voices argue from the evidence; neither wins, and FinSight never tells you what to do."
      actions={pm && <Badge tone={ai ? "accent" : "neutral"}>{ai ? `Voices by ${pm.generated_by}` : "Assembled without a model"}</Badge>}>
      {!pm ? (
        <div className="flex flex-wrap items-center gap-3">
          <Button onClick={run} disabled={busy}>{busy ? "Setting up the room…" : "Run the pre-mortem"}</Button>
          <p className="text-[13px] text-ink2">“Imagine it's {new Date().getFullYear() + 2} and a decision about {inv.company} went badly. What most likely went wrong?”</p>
        </div>
      ) : (
        <>
          <p className="mb-3 text-[13px] italic text-ink2">
            Imagine it is {pm.year} and a decision about {inv.company} went badly.
            {ai && " These arguments are AI-written from FinSight's findings; check each against the verified finding shown under it."}
          </p>
          <div className="grid gap-3 md:grid-cols-2">
            <Voice title="The Skeptic: how it could go wrong" icon="🔴" tone="--status-critical" points={pm.skeptic} findings={findings} aiWritten={ai} />
            <Voice title="The Defender: the case against that story" icon="🟢" tone="--status-good" points={pm.defender} findings={findings} aiWritten={ai} />
          </div>
          <h3 className="mt-4 text-sm font-semibold text-ink">Questions only you can answer</h3>
          <p className="text-xs text-muted">Nobody else knows your situation. Tick each one once you've thought it through.</p>
          <ul className="mt-2 space-y-1.5">
            {pm.questions.map((q, i) => (
              <li key={i}>
                <label className="flex cursor-pointer items-start gap-2 text-[13px]">
                  <input type="checkbox" className="mt-0.5" checked={answered.has(i)}
                    onChange={() => setAnswered((s) => { const n = new Set(s); if (n.has(i)) { n.delete(i); } else { n.add(i); } return n; })} />
                  <span><span className={answered.has(i) ? "text-muted line-through" : "font-medium text-ink"}>{q.question}</span>
                    <span className="block text-xs text-ink2">{q.why}</span></span>
                </label>
              </li>
            ))}
          </ul>
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <Button onClick={onDecide}>Record your decision →</Button>
            <span className="text-xs text-muted">{answered.size} of {pm.questions.length} thought through · {pm.note}</span>
          </div>
        </>
      )}
      {err && <p className="mt-2 text-sm text-critical">{err}</p>}
    </Card>
  );
}
