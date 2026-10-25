"""Turn one asserted value (from a question or pasted text) into a checked Finding."""
from __future__ import annotations

from typing import Optional

from app.financial_data.companies import METRIC_BY_KEY
from app.models.schemas import Classification, EvidenceRef, Finding, FindingStatus, Observation
from app.reconciliation.engine import _fid, explain_value, fmt_usd

# A match to a different period, an earlier (revised) value, another concept, another document or
# another year means the claim does not hold as stated, even though the difference is explained.
_EXPLAINED_BUT_WRONG = ("period_mismatch", "revision", "stale_source", "alternate_concept", "fiscal_year_offset",
                        "other_document")


def build_claim_finding(observations: list[Observation], metric_key: str, value: float, value_text: str,
                        fiscal_year: Optional[int], extra_limit: str = "", id_salt: str = "") -> Finding:
    exp = explain_value(value, observations, metric_key, period_end_year=fiscal_year, is_user_claim=True)
    metric = METRIC_BY_KEY[metric_key]
    support: list[EvidenceRef] = []
    counter: list[EvidenceRef] = []
    if exp.matched:
        (support if exp.status == FindingStatus.supported else counter).append(
            EvidenceRef(observation_id=exp.matched.id, note=exp.kind))
    if exp.reference and (not exp.matched or exp.reference.current.id != exp.matched.id):
        counter.append(EvidenceRef(observation_id=exp.reference.current.id, note="current filed figure"))
    status = exp.status
    verdict = {"supported": "Supported", "contradicted": "Not supported by filings",
               "insufficient_evidence": "Insufficient evidence", "unresolved": "Unresolved"}[exp.status.value]
    if exp.kind == "unit_scale":
        verdict = "Supported if read in different units"
    elif exp.kind in _EXPLAINED_BUT_WRONG:
        status = FindingStatus.contradicted
        verdict = "Not accurate as stated (difference explained)"
    limits = "The claim was parsed as written; if a different period or definition was meant, the result may differ."
    if fiscal_year is None:
        limits += " No year was given, so the latest fiscal year was used."
    if extra_limit:
        limits += " " + extra_limit
    return Finding(
        id=_fid("claim", value, fiscal_year, metric_key, id_salt),
        category="claim_check",
        title=f"{verdict}: {metric.label.lower()} of {value_text}" + (f" for {fiscal_year}" if fiscal_year else ""),
        claim=f"Claimed {metric.label.lower()} of {value_text} ({fmt_usd(value)}). {exp.text}",
        classification=Classification.calculation,
        supporting_evidence=support,
        counterevidence=counter,
        calculation_details={"formula": "pct_difference = (claim - filed) / |filed|; match if |pct| <= 0.5%",
                             "explanation_kind": exp.kind, **exp.details},
        uncertainty_or_limitations=limits,
        why_it_matters="Checks the number against primary filings before you rely on it.",
        status=status,
        severity="watch" if status in (FindingStatus.contradicted, FindingStatus.unresolved) else "info",
    )
