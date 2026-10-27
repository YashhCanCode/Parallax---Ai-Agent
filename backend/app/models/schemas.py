"""Pydantic schemas for observations, findings, investigations and scenarios."""
from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator


class DataStatus(str, Enum):
    live = "live"
    cached = "cached"
    sample = "sample"
    unavailable = "unavailable"


class Observation(BaseModel):
    """One normalized financial fact, with full provenance."""

    id: str
    company: str
    ticker: str
    metric: str  # canonical metric key, e.g. "revenue"
    concept: str  # source definition, e.g. US-GAAP tag
    value: float
    currency_or_unit: str
    period_start: Optional[date] = None  # None for instant (balance-sheet) values
    period_end: date
    period_type: Literal["annual", "quarterly", "ytd", "instant", "other"]
    fiscal_year: Optional[int] = None
    fiscal_period: Optional[str] = None
    form: Optional[str] = None
    reporting_basis: str = "consolidated"
    source_name: str
    source_url: Optional[str] = None
    accession_number: Optional[str] = None
    published_at: Optional[date] = None
    retrieved_at: datetime
    data_status: DataStatus
    retrieval_channel: str  # "zetaris", "sec_direct", "sample"
    extraction_notes: str = ""


class Classification(str, Enum):
    reported_fact = "reported_fact"
    calculation = "calculation"
    interpretation = "interpretation"
    hypothetical = "hypothetical"


class FindingStatus(str, Enum):
    supported = "supported"
    contradicted = "contradicted"
    unresolved = "unresolved"
    insufficient_evidence = "insufficient_evidence"


class EvidenceRef(BaseModel):
    observation_id: str
    note: str = ""


class Finding(BaseModel):
    id: str
    category: Literal["financial_truth", "risk", "claim_check", "memory", "integration"]
    title: str
    claim: str
    classification: Classification
    supporting_evidence: list[EvidenceRef] = Field(default_factory=list)
    counterevidence: list[EvidenceRef] = Field(default_factory=list)
    calculation_details: Optional[dict[str, Any]] = None
    uncertainty_or_limitations: str = ""
    why_it_matters: str = ""
    # Beginner-friendly explanation, generated from templates filled only with this finding's own numbers.
    plain_language: str = ""
    status: FindingStatus
    severity: Literal["info", "watch", "elevated"] = "info"


class StepState(str, Enum):
    RECEIVED = "RECEIVED"
    PLANNING = "PLANNING"
    RETRIEVING = "RETRIEVING"
    NORMALIZING = "NORMALIZING"
    RECONCILING = "RECONCILING"
    INVESTIGATING_RISKS = "INVESTIGATING_RISKS"
    SIMULATING = "SIMULATING"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    NEEDS_MORE_EVIDENCE = "NEEDS_MORE_EVIDENCE"
    FAILED = "FAILED"


class StepRecord(BaseModel):
    state: StepState
    started_at: datetime
    finished_at: Optional[datetime] = None
    status: Literal["running", "ok", "warning", "error", "skipped"] = "running"
    detail: str = ""
    events: list[str] = Field(default_factory=list)


class QueryReceipt(BaseModel):
    """A record of one real external call made while gathering evidence."""

    channel: str  # "zetaris" | "sec_direct" | "sample" | "hmem" | "llm"
    target: str  # SQL text, URL, or endpoint
    started_at: datetime
    duration_ms: int
    ok: bool
    rows: Optional[int] = None
    request_id: Optional[str] = None
    error: Optional[str] = None


class ModelCall(BaseModel):
    provider: str
    model: str
    purpose: str
    started_at: datetime
    duration_ms: int
    ok: bool
    # Usage exactly as returned by the provider; never estimated.
    usage: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    output_accepted: bool = False
    rejection_reason: Optional[str] = None


class ScenarioInput(BaseModel):
    name: str = Field(default="Baseline", max_length=40)
    initial_amount: float = Field(ge=0, le=1e12)
    monthly_contribution: float = Field(default=0, ge=0, le=1e9)
    years: int = Field(ge=1, le=60)
    annual_return_pct: float = Field(ge=-50, le=50)
    annual_fee_pct: float = Field(default=0, ge=0, le=10)
    inflation_pct: float = Field(default=0, ge=-5, le=30)


class ScenarioYear(BaseModel):
    year: int
    contributions_total: float
    nominal_balance: float
    real_balance: float
    fees_paid_total: float


class ScenarioResult(BaseModel):
    name: str
    inputs: ScenarioInput
    final_nominal: float
    final_real: float
    total_contributed: float
    total_fees: float
    nominal_gain: float
    # What the same plan would reach with no fees, and the difference (fees paid plus the growth they forgo).
    final_without_fees: float
    fee_drag: float
    yearly: list[ScenarioYear]
    label: str = "Hypothetical illustration, not a prediction or guarantee."


class ScenarioRequest(BaseModel):
    scenarios: list[ScenarioInput] = Field(min_length=1, max_length=5)


class ScenarioResponse(BaseModel):
    results: list[ScenarioResult]
    formula: str
    assumptions: list[str]
    disclaimer: str


class InvestigationRequest(BaseModel):
    question: str = Field(min_length=3, max_length=600)
    ticker: Optional[str] = Field(default=None, max_length=10)
    data_mode: Optional[Literal["sample", "sec_direct", "zetaris"]] = None

    @field_validator("ticker")
    @classmethod
    def upper(cls, v: Optional[str]) -> Optional[str]:
        return v.upper().strip() if v else v


class MemoryItem(BaseModel):
    id: str
    content: str
    source: str
    relevance: Optional[float] = None
    confidence: Optional[float] = None
    learned_at: Optional[str] = None


class Summary(BaseModel):
    answer: str = ""  # direct answer to the user's question (validated like the rest), or "" when there is none
    answer_by: str = ""  # "model" or "computed" (assembled by code from verified findings)
    text: str
    key_points: list[dict[str, Any]] = Field(default_factory=list)
    generated_by: str  # "deterministic" or "<provider>:<model>"
    note: str = ""


class Investigation(BaseModel):
    id: str
    question: str
    ticker: Optional[str] = None
    company: Optional[str] = None
    data_mode: str
    state: StepState
    created_at: datetime
    updated_at: datetime
    steps: list[StepRecord] = Field(default_factory=list)
    plan: Optional[dict[str, Any]] = None
    observations: list[Observation] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    charts: dict[str, Any] = Field(default_factory=dict)
    summary: Optional[Summary] = None
    receipts: list[QueryReceipt] = Field(default_factory=list)
    model_calls: list[ModelCall] = Field(default_factory=list)
    memory_recalled: list[MemoryItem] = Field(default_factory=list)
    memory_written: list[MemoryItem] = Field(default_factory=list)
    memory_conflicts: list[dict[str, Any]] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    premortem: Optional[dict[str, Any]] = None
    # Company profile from the SEC submissions record (industry, exchange) or the sample fixture.
    profile: Optional[dict[str, Any]] = None
    # Agent trace: one entry per decision (also written to logs/runs/<id>.jsonl).
    trace: list[dict[str, Any]] = Field(default_factory=list)
    error: Optional[str] = None
