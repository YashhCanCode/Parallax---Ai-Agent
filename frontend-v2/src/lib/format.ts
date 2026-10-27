export function usd(v: number | null | undefined, digits = 2): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "n/a";
  const a = Math.abs(v);
  const s = v < 0 ? "-" : "";
  if (a >= 1e12) return `${s}$${(a / 1e12).toFixed(digits)}T`;
  if (a >= 1e9) return `${s}$${(a / 1e9).toFixed(digits)}B`;
  if (a >= 1e6) return `${s}$${(a / 1e6).toFixed(1)}M`;
  if (a >= 1e3) return `${s}$${(a / 1e3).toFixed(1)}K`;
  return `${s}$${a.toFixed(0)}`;
}

export function money(v: number): string {
  return v.toLocaleString(undefined, { style: "currency", currency: "USD", maximumFractionDigits: 0 });
}

export function duration(start: string, end: string | null): string {
  if (!end) return "…";
  const ms = new Date(end).getTime() - new Date(start).getTime();
  return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`;
}

export const CLASS_LABEL: Record<string, string> = {
  reported_fact: "Reported fact",
  calculation: "Calculation",
  interpretation: "Interpretation",
  hypothetical: "Hypothetical",
};

/** "meterless:nvidia/nemotron-3.5-lightning-30b-a3b" -> "nvidia/nemotron-3.5-lightning-30b-a3b via Meterless Nightshift".
 *  The model id is the one Nightshift reported in its reply, so it names the model that actually handled the request. */
export function modelLabel(generatedBy: string): string {
  const i = generatedBy.indexOf(":");
  const provider = i < 0 ? generatedBy : generatedBy.slice(0, i);
  const model = i < 0 ? generatedBy : generatedBy.slice(i + 1);
  return provider === "meterless" ? `${model} via Meterless Nightshift` : `${model} (${provider})`;
}
