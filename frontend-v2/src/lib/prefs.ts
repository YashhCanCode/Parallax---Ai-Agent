// Per-browser conveniences (display name, default data mode). Wrapped so the app works without storage.
export interface Prefs { name: string; mode: string }
const KEY = "finsight.v2.prefs";
const DEFAULTS: Prefs = { name: "", mode: "" };

export function loadPrefs(): Prefs {
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? { ...DEFAULTS, ...JSON.parse(raw) } : DEFAULTS;
  } catch {
    return DEFAULTS;
  }
}

export function savePrefs(p: Prefs): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(p));
  } catch {
    /* storage unavailable: this visit only */
  }
}

export function greeting(d = new Date()): string {
  const h = d.getHours();
  return h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
}

export function relTime(iso: string): string {
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) { const h = Math.floor(s / 3600); return `${h} hour${h > 1 ? "s" : ""} ago`; }
  const d = Math.floor(s / 86400);
  return `${d} day${d > 1 ? "s" : ""} ago`;
}

export const cleanName = (n: string) => n.replace(/ \(SAMPLE, fictional\)$/, "");

/** Short display name: "Apple Inc." -> "Apple", "NVIDIA Corporation" -> "NVIDIA" (as in the reference). */
export const shortName = (n: string) => cleanName(n)
  .replace(/,?\s+(Inc\.?|Incorporated|Corporation|Corp\.?|Co\.?|Company|Ltd\.?|Limited|PLC|plc|Holdings?|Group|N\.V\.|S\.A\.)$/i, "")
  .replace(/,?\s+(Inc\.?|Corp\.?)$/i, "").trim();
