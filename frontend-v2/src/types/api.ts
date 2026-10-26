export type DataStatus = "live" | "cached" | "sample" | "unavailable";
export type FindingStatus = "supported" | "contradicted" | "unresolved" | "insufficient_evidence";
export type Classification = "reported_fact" | "calculation" | "interpretation" | "hypothetical";
export type Severity = "info" | "watch" | "elevated";

export interface Observation {
  id: string;
  company: string;
  ticker: string;
  metric: string;
  concept: string;
  value: number;
  currency_or_unit: string;
  period_start: string | null;
  period_end: string;
  period_type: string;
  form: string | null;
  reporting_basis: string;
  source_name: string;
  source_url: string | null;
  accession_number: string | null;
  published_at: string | null;
  retrieved_at: string;
  data_status: DataStatus;
  retrieval_channel: string;
  extraction_notes: string;
}

export interface EvidenceRef { observation_id: string; note: string }

export interface Finding {
  id: string;
  category: "financial_truth" | "risk" | "claim_check" | "memory" | "integration";
  title: string;
  claim: string;
  classification: Classification;
  supporting_evidence: EvidenceRef[];
  counterevidence: EvidenceRef[];
  calculation_details: Record<string, unknown> | null;
  uncertainty_or_limitations: string;
  why_it_matters: string;
  plain_language: string;
  status: FindingStatus;
  severity: Severity;
}

export interface StepRecord {
  state: string;
  started_at: string;
  finished_at: string | null;
  status: "running" | "ok" | "warning" | "error" | "skipped";
  detail: string;
  events: string[];
}

export interface QueryReceipt {
  channel: string;
  target: string;
  started_at: string;
  duration_ms: number;
  ok: boolean;
  rows: number | null;
  request_id: string | null;
  error: string | null;
}

export interface ModelCall {
  provider: string;
  model: string;
  purpose: string;
  started_at: string;
  duration_ms: number;
  ok: boolean;
  usage: Record<string, unknown> | null;
  error: string | null;
  output_accepted: boolean;
  rejection_reason: string | null;
}

export interface MemoryItem {
  id: string;
  content: string;
  source: string;
  relevance: number | null;
  confidence: number | null;
  learned_at: string | null;
}

export interface TrendPoint {
  period_end: string;
  period_start?: string | null;
  label: string;
  value: number;
  original_value: number;
  revised: boolean;
  observation_id: string;
  concept: string;
  form: string | null;
  filed: string | null;
  source_url: string | null;
}

export interface ComparisonBar {
  label: string;
  kind: "filing" | "secondary" | "quarterly" | "ytd" | "claim";
  value: number;
  concept: string;
  observation_id: string | null;
  published_at: string | null;
  is_current: boolean;
  basis: string;
}

export interface ScenarioInput {
  name: string;
  initial_amount: number;
  monthly_contribution: number;
  years: number;
  annual_return_pct: number;
  annual_fee_pct: number;
  inflation_pct: number;
}

export interface ScenarioResult {
  name: string;
  inputs: ScenarioInput;
  final_nominal: number;
  final_real: number;
  total_contributed: number;
  total_fees: number;
  nominal_gain: number;
  final_without_fees: number;
  fee_drag: number;
  yearly: { year: number; contributions_total: number; nominal_balance: number; real_balance: number; fees_paid_total: number }[];
  label: string;
}

export interface ScenarioResponse { results: ScenarioResult[]; formula: string; assumptions: string[]; disclaimer: string }

export interface KeyFigurePoint { fy: string; period_end: string; value: number; display: string; form: string | null; filed: string | null; evidence: string[] }
export interface KeyFigure {
  key: string; label: string; unit: "usd" | "pct" | "ratio";
  latest: KeyFigurePoint | null; prior: KeyFigurePoint | null;
  change: number | null; change_display: string | null; direction: "up" | "down" | null;
  history: KeyFigurePoint[]; formula: string; sentence: string; note: string;
}

export interface Charts {
  key_figures?: KeyFigure[];
  meta?: { unit: string; data_status: string[]; channels: string[] };
  trends?: Record<string, { label: string; unit: string; points: TrendPoint[] }>;
  quarterly?: Record<string, { label: string; unit: string; points: TrendPoint[] }>;
  source_comparison?: { metric: string; metric_label: string; unit: string; period: string; period_end: string; bars: ComparisonBar[] };
  timeline?: { date: string; form: string | null; source_name: string; accession: string | null; url: string | null; metrics: string[]; kind: string }[];
  risk_dashboard?: { id: string; title: string; severity: Severity; status: FindingStatus; classification: Classification }[];
  scenarios?: ScenarioResponse;
}

export interface Investigation {
  id: string;
  question: string;
  ticker: string | null;
  company: string | null;
  data_mode: string;
  state: string;
  created_at: string;
  updated_at: string;
  steps: StepRecord[];
  plan: Record<string, unknown> | null;
  observations: Observation[];
  findings: Finding[];
  charts: Charts;
  summary: { answer?: string; answer_by?: string; text: string; key_points: { text: string; finding_ids: string[] }[]; generated_by: string; note: string } | null;
  receipts: QueryReceipt[];
  model_calls: ModelCall[];
  memory_recalled: MemoryItem[];
  memory_written: MemoryItem[];
  memory_conflicts: Record<string, unknown>[];
  limitations: string[];
  premortem?: Premortem | null;
  profile?: { industry?: string | null; sic?: string; exchange?: string | null; fiscal_year_end?: string; filer_category?: string; source?: string } | null;
  error: string | null;
}

export interface CompaniesResponse {
  live: { ticker: string; name: string; cik: string; zetaris_registered: boolean }[];
  sample: { ticker: string; name: string }[];
  sample_cases: { ticker: string; question: string }[];
}

export interface IntegrationStatus {
  data_mode: string;
  zetaris: { configured: boolean; problems: string[]; base_url: string; registered_views: number; state: string; error?: string; lightning_databases?: number };
  meterless_hmem: { state: string; engine_source?: string; memories?: number; error?: string; url: string };
  meterless_runtime: { state: string; base_url: string; models: string[]; detail: string; token_set: boolean };
  nvidia?: { configured: boolean; model: string; state: string; detail?: string };
  gemini: { configured: boolean; model: string };
  llm_provider: string;
  sec: { user_agent_set: boolean };
}

export interface GlossaryEntry { term: string; aliases: string[]; definition: string }

export interface ClaimResult {
  sentence: string;
  span: [number, number];
  ticker: string;
  company: string;
  company_inferred: boolean;
  metric: string;
  value: number;
  value_text: string;
  fiscal_year: number | null;
  notes: string[];
  finding: Finding;
}

export interface ClaimCheckResponse {
  claims: ClaimResult[];
  not_checked: { sentence: string; text: string; reason: string }[];
  truncated: boolean;
  companies: { ticker: string; name: string; mode_used: string; data_status: string[]; observations: number; queries: number }[];
  counts: Record<string, number>;
  observations: Observation[];
  notes: string[];
}

export interface WatchFigure {
  key: string;
  label: string | null;
  value: number | null;
  form: string | null;
  filed: string | null;
  source_url: string | null;
  memory_id: string | null;
  observation_id: string | null;
}

export interface WatchChange extends WatchFigure {
  old_value: number | null;
  old_memory_id: string | null;
  old_source: string | null;
  resolution: string | null;
}

export interface WatchReport {
  ticker: string;
  company?: string;
  checked_at: string;
  mode_used?: string;
  data_status?: string[];
  observations?: number;
  notes?: string[];
  baseline?: boolean;
  new_filings?: { accession: string; form: string | null; filed: string | null; url: string | null; statement: boolean }[];
  changes?: WatchChange[];
  new_figures?: WatchFigure[];
  confirmed?: number;
  figures_tracked?: number;
  memory?: { available: boolean; error?: string };
  spark?: { metric: string; values: number[]; latest: number | null; period: string | null; yoy: number | null };
  decisions?: { id: string; decision_label: string; note: string; created_at: string; newly_hit: string[];
    tripwires: { describe: string; state: string; value_fmt: string }[] }[];
  error?: string;
}

export interface WatchItem {
  ticker: string;
  name: string;
  data_mode: string;
  added_at: string;
  last_checked_at: string | null;
  last_report: WatchReport | null;
}

export interface CompanyHit {
  ticker: string;
  name: string;
  cik: string;
  exchange: string;
  builtin: boolean;
  zetaris_registered: boolean;
}

export interface VoicePoint { text: string; finding_ids: string[] }
export interface Premortem {
  year: number;
  skeptic: VoicePoint[];
  defender: VoicePoint[];
  questions: { question: string; why: string; finding_ids: string[] }[];
  generated_by: string;
  note: string;
  created_at?: string;
}

export interface TripwireMetric { key: string; label: string; unit: "usd" | "pct" | "ratio" | "years" | "count"; description: string; value: number | null; fmt: string; period: string | null; note: string }
export interface TripwireSpec { metric: string; op: "<" | ">"; threshold: number }
export interface TripwireEval extends TripwireSpec { describe: string; value: number | null; value_fmt: string; period: string | null; state: "hit" | "ok" | "unknown"; note: string; evidence: string[] }
export interface HindsightRow { metric: string; label: string; then: string; now: string; changed: boolean; then_period: string | null; now_period: string | null }
export interface DecisionCheck {
  checked_at: string;
  tripwires: TripwireEval[];
  newly_hit: string[];
  hit_memory_ids: string[];
  hindsight: { rows: HindsightRow[]; new_filings: string[]; latest_filing_then: { date: string; form: string } | null; latest_filing_now: { date: string; form: string } | null };
}
export interface Decision {
  id: string;
  ticker: string;
  company: string;
  data_mode: string;
  created_at: string;
  decision_type: string;
  decision_label: string;
  note: string;
  tripwires: TripwireSpec[];
  tripwires_eval: TripwireEval[];
  already_hit_at_creation: string[];
  investigation_id: string | null;
  snapshot: { metrics: Record<string, { value: number | null; fmt: string; period: string | null }>; latest_filing: { date: string; form: string; url: string | null } | null };
  memory_id: string | null;
  checks: DecisionCheck[];
}

export interface BoardCell { fmt: string; value: number | null; period: string | null; note: string }
export interface BoardRow { metric: string; label: string; description: string; cells: Record<string, BoardCell>; highest: string | null; lowest: string | null; sentence: string }
export interface Board {
  id: string;
  created_at: string;
  data_mode: string;
  labels: string[];
  rows: BoardRow[];
  pick: string | null;
  revealed_at: string | null;
  has_prior_pick: boolean;
  companies?: Record<string, { ticker: string; name: string; mode_used: string; data_status: string[];
    evidence: Record<string, { value: number; form: string | null; filed: string | null; url: string | null; period_end: string }[]> }>;
  reflection?: { pick: string | null; picked_ticker: string | null; prior_pick: string | null; text: string };
}

export interface RecentItem { id: string; ticker: string | null; state: string; created_at: string; question: string; data_mode: string }
