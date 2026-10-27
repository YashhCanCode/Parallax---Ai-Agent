"""The Parallax investigation workflow: an explicit, inspectable sequence of states.

Every StepRecord is written as the step actually runs (real timestamps, real outcomes), and the
investigation is persisted after each step so the UI shows true progress.
"""
from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

from app.agents.charts import build_charts
from app.analysis.key_figures import compute_key_figures
from app.agents.narrator import Narrator
from app.tracing import Tracer
from app.config import Settings
from app.db import save_investigation
from app.financial_data.companies import METRICS, Company, find_company, match_company_in_text
from app.financial_data.providers import FetchResult, SampleProvider, SecDirectProvider, ZetarisProvider
from app.integrations.meterless.hmem import HmemClient, HmemUnavailable
from app.integrations.zetaris.client import ZetarisError
from app.financial_data.sec_client import SecError
from app.models.schemas import (
    Classification,
    Finding,
    FindingStatus,
    Investigation,
    InvestigationRequest,
    MemoryItem,
    StepRecord,
    StepState,
    Summary,
)
from app.reconciliation.claims import parse_question
from app.reconciliation.claim_check import build_claim_finding
from app.explain.plain_language import apply_plain_language
from app.integrations.meterless.facts import build_memory_facts, sidecar_payload
from app.reconciliation.engine import (
    _fid,
    channel_cross_check,
    concept_findings,
    consistency_finding,
    fmt_usd,
    other_document_findings,
    revision_findings,
    secondary_source_findings,
)
from app.risk_analysis.indicators import run_risk_indicators
from app.scenarios.calculator import calculate, default_scenarios


def _now() -> datetime:
    return datetime.now(timezone.utc)


def new_investigation(req: InvestigationRequest, settings: Settings) -> Investigation:
    now = _now()
    inv = Investigation(
        id="inv-" + uuid.uuid4().hex[:12],
        question=req.question,
        ticker=req.ticker,
        data_mode=req.data_mode or settings.data_mode,
        state=StepState.RECEIVED,
        created_at=now,
        updated_at=now,
    )
    inv.steps.append(StepRecord(state=StepState.RECEIVED, started_at=now, finished_at=now, status="ok",
                                detail="Question received."))
    return inv


class Workflow:
    def __init__(self, inv: Investigation, settings: Settings):
        self.inv = inv
        self.s = settings
        self.hmem = HmemClient(settings.hmem_url) if settings.hmem_enabled else None
        self.narrator = Narrator(settings)
        self.company: Optional[Company] = None
        self.parsed = parse_question(inv.question)
        self.primary: Optional[FetchResult] = None
        self.trace = Tracer(inv.id, settings.log_dir, inv.trace)

    def _save(self) -> None:
        self.inv.updated_at = _now()
        save_investigation(self.inv)

    @asynccontextmanager
    async def step(self, state: StepState, detail: str = ""):
        rec = StepRecord(state=state, started_at=_now(), detail=detail)
        self.inv.state = state
        self.inv.steps.append(rec)
        self._save()
        try:
            yield rec
            if rec.status == "running":
                rec.status = "ok"
        except Exception as exc:
            rec.status = "error"
            rec.events.append(f"{exc.__class__.__name__}: {exc}")
            raise
        finally:
            rec.finished_at = _now()
            self._save()

    # ------------------------------------------------------------------------------------
    async def run(self) -> Investigation:
        try:
            await self._plan()
            if self.company is None:
                self.trace.emit("Orchestrator", "finish", self.inv.question, "Stopped: no company identified; asked the "
                                "user to pick one", status="needs_more_evidence")
                self.inv.state = StepState.NEEDS_MORE_EVIDENCE
                self.inv.limitations.append(
                    "Parallax could not identify the company. Pick it in the company search box, or write its "
                    "ticker in the question, for example $PLTR or (NASDAQ: PLTR). Any SEC-listed company works.")
                self._save()
                return self.inv
            await self._retrieve()
            await self._normalize()
            await self._reconcile()
            await self._risks()
            if self.parsed.wants_scenario:
                await self._simulate()
            await self._verify()
            needs_more = not self.inv.observations or any(
                f.category == "claim_check" and f.status == FindingStatus.insufficient_evidence for f in self.inv.findings)
            self.inv.state = StepState.NEEDS_MORE_EVIDENCE if needs_more else StepState.COMPLETED
            self.inv.steps.append(StepRecord(state=self.inv.state, started_at=_now(), finished_at=_now(), status="ok",
                                             detail="Investigation finished." if not needs_more else
                                             "Finished, but key evidence is missing (see limitations)."))
            s = self.inv.summary
            self.trace.emit("Orchestrator", "finish", f"{len(self.inv.findings)} findings",
                            f"Answer ({'written by ' + s.generated_by if s and s.generated_by != 'deterministic' else 'computed in code'}): "
                            f"{(s.answer if s else '') or '(summary only)'}",
                            status="completed" if not needs_more else "needs_more_evidence")
        except Exception as exc:  # noqa: BLE001 - surface any failure honestly
            self.inv.state = StepState.FAILED
            self.inv.error = f"{exc.__class__.__name__}: {exc}"
            self.trace.emit("Orchestrator", "finish", self.inv.question, self.inv.error, status="failed")
            self.inv.steps.append(StepRecord(state=StepState.FAILED, started_at=_now(), finished_at=_now(),
                                             status="error", detail=self.inv.error))
        if self.hmem:
            self.inv.receipts.extend(self.hmem.receipts)
            self.hmem.receipts.clear()
        self._save()
        return self.inv

    # ------------------------------------------------------------------------------------
    async def _plan(self) -> None:
        async with self.step(StepState.PLANNING, "Interpreting the question and recalling memory.") as rec:
            mode = self.inv.data_mode
            include_sample = mode == "sample"
            company = find_company(self.inv.ticker) or match_company_in_text(self.inv.question, include_sample=True)
            self.trace.emit("Planner", "read_question", self.inv.question,
                            f"Company {'from the chosen ticker' if self.inv.ticker and company else 'named in the question'}: "
                            f"{company.ticker if company else 'none found'}; claim: "
                            f"{self.parsed.claimed_text or 'none'}; focus: {self.parsed.metric or 'revenue'}",
                            target="Planner" if company else "CompanyInterpreter")
            if company and company.sample != include_sample:
                rec.events.append(
                    f"{company.ticker} is {'a sample' if company.sample else 'a live'} company; "
                    f"switching data mode to {'sample' if company.sample else 'sec_direct'}."
                )
                if company.sample:
                    self.inv.data_mode = "sample"
                elif mode == "sample":
                    self.inv.data_mode = "sec_direct"
                self.trace.emit("Planner", "choose_data_mode", f"{company.ticker} with mode {mode}",
                                f"Switched to {self.inv.data_mode}: sample and live companies never mix", status="adjusted")
            provider, detail = await self.narrator.select_provider()
            rec.events.append(f"Model provider: {provider or 'none'} ({detail}).")
            if company is None and provider:
                ticker, call = await self.narrator.interpret_company(self.inv.question, self.trace)
                if call:
                    self.inv.model_calls.append(call)
                company = find_company(ticker) if ticker else None
                rec.events.append(f"Model interpretation suggested {ticker or 'no company'} (checked against the SEC "
                                  f"directory and the question's own words).")
                if company and not company.sample and self.inv.data_mode == "sample":
                    self.inv.data_mode = "sec_direct"
                    rec.events.append(f"{company.ticker} is a live company; switching data mode to sec_direct.")
            self.company = company
            if company is None:
                rec.status = "warning"
                rec.detail = "No supported company found in the question."
                self.trace.emit("Planner", "resolve_company", self.inv.question, "No SEC-listed company found",
                                target="Orchestrator", status="needs_more_evidence")
                return
            self.inv.ticker, self.inv.company = company.ticker, company.name
            from app.financial_data.fetch import company_profile

            self.inv.profile = await company_profile(company, self.s)
            focus = self.parsed.metric or "revenue"
            self.inv.plan = {
                "company": company.name,
                "ticker": company.ticker,
                "data_mode": self.inv.data_mode,
                "focus_metric": focus,
                "fiscal_year": self.parsed.fiscal_year,
                "claim": {"value": self.parsed.claimed_value, "text": self.parsed.claimed_text} if self.parsed.is_claim else None,
                "metrics": [m.key for m in METRICS],
                "steps": ["retrieve", "normalize", "reconcile", "investigate risks"]
                         + (["simulate scenarios"] if self.parsed.wants_scenario else []) + ["verify"],
                "planner": "deterministic parser (numbers are taken verbatim from the question)",
            }
            rec.events.append(f"Company: {company.name} ({company.ticker}); focus metric: {focus}.")
            self.trace.emit("Planner", "plan", f"{company.ticker}, {self.inv.data_mode}",
                            f"Steps: {', '.join(self.inv.plan['steps'])}; focus {focus}"
                            + (f"; check the claim {self.parsed.claimed_text}" if self.parsed.is_claim else ""),
                            target="MemoryKeeper" if self.hmem else "Retriever")
            if self.hmem:
                try:
                    recall = await self.hmem.recall(company.ticker, f"{company.ticker} {company.name} {focus} risk cash flow debt revision")
                    for r in recall.get("memories", []):
                        m = r["memory"]
                        self.inv.memory_recalled.append(MemoryItem(
                            id=m["id"], content=m["content"], source=m["source"], relevance=round(r["relevance"], 3),
                            confidence=m.get("confidence"),
                            learned_at=datetime.fromtimestamp(m["provenance"]["learnedAt"] / 1000, timezone.utc).isoformat()))
                    rec.events.append(f"H-MEM recalled {len(self.inv.memory_recalled)} prior memories for {company.ticker}.")
                    self.trace.emit("MemoryKeeper", "recall", company.ticker,
                                    f"{len(self.inv.memory_recalled)} prior memories recalled from Meterless H-MEM",
                                    target="Retriever")
                except HmemUnavailable as exc:
                    self.trace.emit("MemoryKeeper", "recall", company.ticker, f"H-MEM unreachable: {exc}; continuing "
                                    "without memory", target="Retriever", status="failed")
                    rec.events.append(f"H-MEM unavailable: {exc}")
                    self.inv.limitations.append("Meterless H-MEM memory sidecar was not reachable; no prior memory was used or stored.")

    async def _retrieve(self) -> None:
        assert self.company
        async with self.step(StepState.RETRIEVING, f"Fetching evidence ({self.inv.data_mode}).") as rec:
            mode = self.inv.data_mode
            result: Optional[FetchResult] = None
            if mode == "zetaris":
                zp = ZetarisProvider(self.s)
                try:
                    result = await zp.fetch(self.company, METRICS)
                    rec.events += result.events
                    z = [r for r in result.receipts if r.channel == "zetaris"]
                    bad = sum(1 for r in z if not r.ok)
                    self.trace.emit("Retriever", "query_zetaris", f"{len(METRICS)} figures for {self.company.ticker}",
                                    f"{len(z)} SQL queries through Zetaris, {sum(r.rows or 0 for r in z)} rows, {bad} failed; "
                                    f"{len(result.observations)} observations",
                                    target="Normalizer" if result.observations else "Retriever",
                                    status="success" if result.observations and not bad else ("partial" if result.observations else "empty"),
                                    duration_ms=sum(r.duration_ms for r in z))
                except ZetarisError as exc:
                    self.trace.emit("Retriever", "query_zetaris", self.company.ticker, f"Zetaris unavailable: {exc}",
                                    target="Retriever", status="failed")
                    rec.status = "warning"
                    rec.events.append(f"Zetaris unavailable: {exc}")
                    self.inv.limitations.append(f"Zetaris could not be used ({exc}). Fell back to the direct SEC EDGAR API.")
                    result = None
                if result is not None and not result.observations:
                    rec.status = "warning"
                    self.inv.limitations.append("Zetaris returned no observations; fell back to the direct SEC EDGAR API.")
                    self.inv.receipts += result.receipts
                    self.inv.limitations += result.limitations
                    result = None
                if result is not None and self.s.zetaris_cross_check:
                    try:
                        check = await SecDirectProvider(self.s).fetch(self.company, METRICS)
                        self.inv.receipts += check.receipts
                        cc = channel_cross_check(result.raw_counts, check.raw_counts, result.observations, check.observations)
                        self.inv.findings.append(cc)
                        rec.events.append("Cross-checked Zetaris results against the direct SEC API.")
                        self.trace.emit("Retriever", "cross_check_sec", "Zetaris rows vs SEC EDGAR rows",
                                        f"{cc.status.value}: {cc.title}", target="Normalizer",
                                        status="success" if cc.status.value == "supported" else "mismatch")
                    except SecError as exc:
                        rec.events.append(f"Cross-check skipped: {exc}")
                if result is None:
                    mode = "sec_direct"
                    self.trace.emit("Retriever", "fallback_sec_direct", "Zetaris gave no usable data",
                                    "Falling back to SEC EDGAR directly (labelled in the answer)", target="Retriever",
                                    status="fallback", retry_count=1)
            if mode == "sec_direct":
                try:
                    result = await SecDirectProvider(self.s).fetch(self.company, METRICS)
                    rec.events += result.events
                    self.trace.emit("Retriever", "query_sec", f"{len(METRICS)} figures for {self.company.ticker}",
                                    f"{sum(1 for r in result.receipts if r.ok)} SEC EDGAR requests, "
                                    f"{len(result.observations)} observations", target="Normalizer",
                                    status="success" if result.observations else "empty")
                except SecError as exc:
                    self.trace.emit("Retriever", "query_sec", self.company.ticker, f"SEC unavailable: {exc}",
                                    target="Orchestrator", status="failed")
                    rec.status = "warning"
                    rec.events.append(str(exc))
                    self.inv.limitations.append(f"Live SEC data unavailable: {exc}")
                    result = FetchResult(channel="sec_direct")
            if mode == "sample":
                result = await SampleProvider(self.s).fetch(self.company, METRICS)
                rec.events += result.events
                self.trace.emit("Retriever", "load_sample", self.company.ticker,
                                f"{len(result.observations)} observations from the fictional sample filings",
                                target="Normalizer", status="success" if result.observations else "empty")
            assert result is not None
            self.primary = result
            self.inv.observations = result.observations
            self.inv.receipts += result.receipts
            self.inv.limitations += result.limitations
            if not result.observations:
                rec.status = "warning"

    async def _normalize(self) -> None:
        async with self.step(StepState.NORMALIZING, "Classifying periods, units and concepts.") as rec:
            obs = self.inv.observations
            counts: dict[str, int] = {}
            for o in obs:
                counts[o.period_type] = counts.get(o.period_type, 0) + 1
            rec.events.append("Observations by period type: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
            units = sorted({o.currency_or_unit for o in obs})
            rec.events.append(f"Units after normalization: {', '.join(units) or 'none'}.")
            self.trace.emit("Normalizer", "classify_periods", f"{len(obs)} observations",
                            ", ".join(f"{k}={v}" for k, v in sorted(counts.items())) + f"; units {', '.join(units) or 'none'}",
                            target="Reconciler")
            primary = [o for o in obs if o.form != "secondary" and o.published_at]
            if primary:
                latest = max(o.published_at for o in primary)
                age = (_now().date() - latest).days
                rec.events.append(f"Most recent filing in the data: {latest} ({age} days ago).")
                if age > 200:
                    self.inv.limitations.append(f"The newest filing in the data is {age} days old; newer results may exist.")
            self.inv.limitations.append(
                "SEC 'fy'/'fp' fields describe the filing, not the period; Parallax labels periods by their end date.")

    async def _reconcile(self) -> None:
        async with self.step(StepState.RECONCILING, "Comparing figures across filings, concepts and sources.") as rec:
            obs = self.inv.observations
            focus = self.parsed.metric or "revenue"
            metrics = [focus] + [m for m in ("revenue", "net_income", "operating_cash_flow") if m != focus]
            for m in metrics:
                f = consistency_finding(obs, m)
                if f:
                    self.inv.findings.append(f)
                self.inv.findings += revision_findings(obs, m, max_items=3 if m == focus else 1)
                self.inv.findings += concept_findings(obs, m)
                self.inv.findings += other_document_findings(obs, m)
                self.inv.findings += secondary_source_findings(obs, m)
            if self.parsed.is_claim and self.parsed.claimed_value is not None:
                self.inv.findings.append(self._claim_finding(focus))
            rec.events.append(f"{sum(1 for f in self.inv.findings if f.category in ('financial_truth', 'claim_check'))} "
                              f"financial-truth findings.")
            revisions = sum(1 for f in self.inv.findings if f.id.startswith("rev-"))
            claim = next((f for f in self.inv.findings if f.category == "claim_check"), None)
            self.trace.emit("Reconciler", "reconcile", f"{len(obs)} observations, metrics {', '.join(metrics)}",
                            f"{revisions} revised figures found"
                            + (f"; claim {claim.status.value}: {claim.claim}" if claim else ""),
                            target="RiskInvestigator",
                            status=("claim_" + claim.status.value) if claim else "success")

    def _claim_finding(self, metric_key: str) -> Finding:
        p = self.parsed
        return build_claim_finding(self.inv.observations, metric_key, p.claimed_value, p.claimed_text or "",
                                   p.fiscal_year)

    async def _risks(self) -> None:
        async with self.step(StepState.INVESTIGATING_RISKS, "Checking a bounded set of risk indicators.") as rec:
            risks = run_risk_indicators(self.inv.observations)
            self.inv.findings += risks
            rec.events.append(", ".join(f"{f.title} [{f.severity}]" for f in risks))
            flagged = [f.title for f in risks if f.severity != "info"]
            self.trace.emit("RiskInvestigator", "run_indicators", f"{len(risks)} indicators",
                            f"{len(flagged)} flagged" + (": " + "; ".join(flagged) if flagged else ""), target="Verifier")

    async def _simulate(self) -> None:
        async with self.step(StepState.SIMULATING, "Computing illustrative scenarios.") as rec:
            resp = calculate(default_scenarios())
            self.inv.charts["scenarios"] = resp.model_dump(mode="json")
            rec.events.append("Computed adverse / baseline / favorable presets; adjust them in the simulator.")

    async def _verify(self) -> None:
        async with self.step(StepState.VERIFYING, "Checking evidence links, writing memory, drafting the summary.") as rec:
            ids = {o.id for o in self.inv.observations}
            for f in self.inv.findings:
                missing = [e.observation_id for e in f.supporting_evidence + f.counterevidence if e.observation_id not in ids]
                if missing:
                    f.status = FindingStatus.unresolved
                    f.uncertainty_or_limitations += f" Verification: {len(missing)} cited observation(s) missing."
                if f.category in ("financial_truth", "risk") and f.status == FindingStatus.supported and not f.supporting_evidence:
                    f.status = FindingStatus.insufficient_evidence
            rec.events.append(f"Verified evidence links for {len(self.inv.findings)} findings.")
            unresolved = sum(1 for f in self.inv.findings if f.status in (FindingStatus.unresolved, FindingStatus.insufficient_evidence))
            self.trace.emit("Verifier", "check_evidence_links", f"{len(self.inv.findings)} findings",
                            f"{unresolved} downgraded (missing or no evidence); the rest cite real observations",
                            target="MemoryKeeper" if self.hmem else "Narrator",
                            status="success" if not unresolved else "partial")
            focus = self.parsed.metric or "revenue"
            claim = self.parsed
            self.inv.charts.update(build_charts(self.inv.observations, self.inv.findings, focus, claim.fiscal_year,
                                                claim.claimed_value, claim.claimed_text))
            key_figures = compute_key_figures(self.inv.observations)
            self.inv.charts["key_figures"] = [k.as_dict() for k in key_figures]
            rec.events.append(f"Computed {sum(1 for k in key_figures if k.points)} key figures (margins, free cash flow, "
                              f"changes) from the filings.")
            await self._write_memory(rec)
            apply_plain_language(self.inv.findings)
            if not self.inv.observations:
                # No filings were retrieved: there is nothing for a model to explain, so say why, plainly.
                reasons = [x for x in self.inv.limitations if "unavailable" in x.lower() or "could not" in x.lower()]
                self.inv.summary = Summary(
                    answer=f"Parallax couldn't retrieve any filings for {self.inv.company}, so it isn't answering. "
                           + (" ".join(reasons[:2]) if reasons else "Try again, or switch the data source to Sample."),
                    answer_by="computed", text="No filing data was retrieved, so no findings were produced.",
                    generated_by="deterministic", note="No evidence: the model was not asked.")
                self.trace.emit("Verifier", "require_evidence", "0 observations", "No filings retrieved: the model is "
                                "not asked; the answer says why", target="Orchestrator", status="blocked")
                return
            summary, call = await self.narrator.narrate(self.inv.question, self.inv.company or "", self.inv.findings,
                                                        key_figures, self.trace)
            self.inv.summary = summary
            if call:
                self.inv.model_calls.append(call)
                rec.events.append(f"Model summary {'accepted' if call.output_accepted else 'rejected: ' + str(call.rejection_reason or call.error)}.")

    async def _write_memory(self, rec: StepRecord) -> None:
        if not self.hmem or not self.company:
            return
        facts = build_memory_facts(self.company, self.inv.observations)
        try:
            res = await self.hmem.write_facts(self.company.ticker, sidecar_payload(facts))
            outcomes: dict[str, int] = {}
            for r in res.get("results", []):
                outcomes[r["outcome"]] = outcomes.get(r["outcome"], 0) + 1
                m = r.get("memory")
                if m:
                    self.inv.memory_written.append(MemoryItem(id=m["id"], content=m["content"], source=m["source"],
                                                              confidence=m.get("confidence")))
                for c in r.get("conflicts", []):
                    self.inv.memory_conflicts.append({"key": r["key"], **c})
            rec.events.append("H-MEM facts: " + ", ".join(f"{k}={v}" for k, v in sorted(outcomes.items())))
            n_conf = len(self.inv.memory_conflicts)
            self.trace.emit("MemoryKeeper", "write_facts", f"{len(facts)} facts with sources",
                            ", ".join(f"{k}={v}" for k, v in sorted(outcomes.items()))
                            + (f"; {n_conf} conflict(s) with earlier memory recorded in the trust ledger" if n_conf else ""),
                            target="Narrator", status="conflict_detected" if n_conf else "success")
            for c in self.inv.memory_conflicts:
                prev_val = next((t for t in c["previous"]["tags"] if t.startswith("value:")), "value:?")[6:]
                self.inv.findings.append(Finding(
                    id=_fid("mem", c["memoryA"], c["memoryB"]),
                    category="memory",
                    title=f"Changed since an earlier investigation: {c['key']}",
                    claim=f"Parallax's memory ({c['memoryA']}) recorded {fmt_usd(float(prev_val))} for {c['key']}; "
                          f"this run found a different value ({c['memoryB']}). Resolution: {c['resolution']}.",
                    classification=Classification.reported_fact,
                    uncertainty_or_limitations="Usually a later filing revised the figure; the earlier memory is kept in the H-MEM ledger.",
                    status=FindingStatus.supported,
                    severity="watch",
                ))
            notable = [f for f in self.inv.findings if f.category == "risk" and f.severity != "info"]
            for f in notable[:3]:
                await self.hmem.write_note(self.company.ticker, f"{self.company.ticker}: {f.title}",
                                           f"finsight:{self.inv.id}", [], [f"severity:{f.severity}", "risk"])
        except HmemUnavailable as exc:
            rec.events.append(f"H-MEM write skipped: {exc}")
            self.trace.emit("MemoryKeeper", "write_facts", f"{len(facts)} facts", f"H-MEM unreachable: {exc}; "
                            "nothing stored this run", target="Narrator", status="failed")
