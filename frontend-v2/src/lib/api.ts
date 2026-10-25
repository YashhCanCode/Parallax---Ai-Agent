import type { RecentItem, Board, Decision, DecisionCheck, Premortem, TripwireMetric, TripwireSpec, CompanyHit, ClaimCheckResponse, GlossaryEntry, WatchItem, WatchReport, CompaniesResponse, IntegrationStatus, Investigation, ScenarioInput, ScenarioResponse } from "../types/api";

const BASE = import.meta.env.VITE_API_BASE ?? "";

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(BASE + path, {
    ...init,
    headers: { "content-type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!r.ok) {
    let detail = `${r.status} ${r.statusText}`;
    try {
      const body = await r.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body);
    } catch {
      /* keep status text */
    }
    throw new Error(detail);
  }
  return r.json() as Promise<T>;
}

export const api = {
  companies: () => req<CompaniesResponse>("/api/companies"),
  status: (deep = false) => req<IntegrationStatus>(`/api/integrations/status${deep ? "?deep=true" : ""}`),
  start: (question: string, ticker: string | null, data_mode: string) =>
    req<Investigation>("/api/investigations", { method: "POST", body: JSON.stringify({ question, ticker, data_mode }) }),
  get: (id: string) => req<Investigation>(`/api/investigations/${id}`),
  recent: () => req<RecentItem[]>("/api/investigations"),
  scenarios: (scenarios: ScenarioInput[]) =>
    req<ScenarioResponse>("/api/scenarios/calculate", { method: "POST", body: JSON.stringify({ scenarios }) }),
  searchCompanies: (q: string) =>
    req<{ results: CompanyHit[]; directory: { companies: number; source: string; error: string | null } }>(`/api/companies/search?q=${encodeURIComponent(q)}`),
  glossary: () => req<GlossaryEntry[]>("/api/glossary"),
  checkClaims: (text: string, data_mode: string) =>
    req<ClaimCheckResponse>("/api/claims/check", { method: "POST", body: JSON.stringify({ text, data_mode }) }),
  watchlist: () => req<WatchItem[]>("/api/watchlist"),
  follow: (ticker: string, data_mode: string) =>
    req<{ ticker: string; data_mode: string }>("/api/watchlist", { method: "POST", body: JSON.stringify({ ticker, data_mode }) }),
  unfollow: (ticker: string) => req<{ removed: string }>(`/api/watchlist/${ticker}`, { method: "DELETE" }),
  checkWatchlist: (ticker?: string) =>
    req<{ reports: WatchReport[] }>("/api/watchlist/check", { method: "POST", body: JSON.stringify({ ticker: ticker ?? null }) }),
  sampleAmendment: () => req<{ applied: boolean; description: string }>("/api/sample/amendment"),
  publishSampleAmendment: () => req<{ applied: boolean }>("/api/sample/amendment", { method: "POST" }),
  premortem: (invId: string) => req<Premortem>(`/api/investigations/${invId}/premortem`, { method: "POST" }),
  tripwireMetrics: (ticker: string, data_mode: string) =>
    req<{ ticker: string; company: string; mode_used: string; metrics: TripwireMetric[] }>(`/api/tripwire-metrics?ticker=${encodeURIComponent(ticker)}&data_mode=${data_mode}`),
  createDecision: (body: { ticker: string; data_mode: string; decision_type: string; note: string; tripwires: TripwireSpec[]; investigation_id?: string | null }) =>
    req<Decision>("/api/decisions", { method: "POST", body: JSON.stringify(body) }),
  decisions: (ticker = "") => req<Decision[]>(`/api/decisions${ticker ? `?ticker=${ticker}` : ""}`),
  checkDecision: (id: string) => req<{ decision: Decision; check: DecisionCheck }>(`/api/decisions/${id}/check`, { method: "POST" }),
  createBoard: (tickers: string[], data_mode: string, prior_pick: string | null) =>
    req<Board>("/api/board", { method: "POST", body: JSON.stringify({ tickers, data_mode, prior_pick }) }),
  revealBoard: (id: string, pick: string | null) => req<Board>(`/api/board/${id}/reveal`, { method: "POST", body: JSON.stringify({ pick }) }),
  audit: (memoryId: string) => req<{ memory: Record<string, unknown> | null; history: Record<string, unknown>[] }>(`/api/memory/${memoryId}/audit`),
};

export const TERMINAL = new Set(["COMPLETED", "NEEDS_MORE_EVIDENCE", "FAILED"]);
