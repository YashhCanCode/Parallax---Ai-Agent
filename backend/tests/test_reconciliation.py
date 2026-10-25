"""Evaluation cases from the project brief (section 10), run against labeled sample fixtures."""
from datetime import date

from app.models.schemas import FindingStatus
from app.reconciliation.claims import parse_question
from app.reconciliation.engine import (
    annual_series,
    concept_findings,
    explain_value,
    revision_findings,
    secondary_source_findings,
)


def _src(findings, name):
    return next(f for f in findings if name in f.title)


def test_annual_series_prefers_latest_filing_and_concept(nwm):
    s = annual_series(nwm.observations, "revenue")
    by_year = {r.period_end.year: r for r in s}
    assert by_year[2024].current.value == 52.4e9
    # FY2023 was revised by the FY2024 10-K: latest filing wins, original is kept.
    assert by_year[2023].current.value == 48.3e9
    assert by_year[2023].original.value == 48.9e9
    # FY2021 overlaps two concepts; the ASC 606 concept has priority.
    assert by_year[2021].current.concept.endswith("RevenueFromContractWithCustomerExcludingAssessedTax")
    # Quarterly / YTD facts are not mixed into the annual series.
    assert all(r.period_type == "annual" for r in s)


def test_case1_quarterly_vs_annual(nwm):
    f = _src(secondary_source_findings(nwm.observations, "revenue"), "Sample news article")
    assert "period mismatch" in f.title
    assert f.status == FindingStatus.supported


def test_case2_standalone_vs_consolidated(nwm):
    f = _src(secondary_source_findings(nwm.observations, "revenue"), "parent-only")
    assert "basis" in f.title


def test_case3_different_units(nwm):
    f = _src(secondary_source_findings(nwm.observations, "revenue"), "market-data site A")
    assert "unit normalized match" in f.title
    assert f.status == FindingStatus.supported


def test_case4_stale_vs_newer(nwm):
    f = _src(secondary_source_findings(nwm.observations, "revenue"), "market-data site B")
    assert "stale source" in f.title
    rev = revision_findings(nwm.observations, "revenue")
    assert any("revised" in r.title and r.calculation_details["difference"] == -0.6e9 for r in rev)


def test_case6_unresolved_disagreement(csr):
    f = _src(secondary_source_findings(csr.observations, "revenue"), "market-data site C")
    assert f.status == FindingStatus.unresolved
    assert "does not guess" in f.uncertainty_or_limitations


def test_concept_switch_detected(nwm):
    titles = [f.title for f in concept_findings(nwm.observations, "revenue")]
    assert any("switched reporting concept" in t for t in titles)
    assert any("different definitions" in t for t in titles)


def test_case8_unsupported_claim_is_contradicted(nwm):
    exp = explain_value(70e9, nwm.observations, "revenue", period_end_year=2024, is_user_claim=True)
    assert exp.status == FindingStatus.contradicted


def test_claim_in_wrong_units_is_explained(nwm):
    exp = explain_value(52_400, nwm.observations, "revenue", period_end_year=2024, is_user_claim=True)
    assert exp.kind == "unit_scale"


def test_claim_for_missing_year_is_insufficient(nwm):
    exp = explain_value(1e9, nwm.observations, "revenue", period_end_year=2015, is_user_claim=True)
    assert exp.status == FindingStatus.insufficient_evidence


def test_parse_question():
    p = parse_question("Was Northwind's 2024 revenue really $13.6 billion?")
    assert p.metric == "revenue" and p.fiscal_year == 2024 and p.claimed_value == 13.6e9
    p2 = parse_question("Is Tesla's debt a risk?")
    assert p2.metric == "long_term_debt" and p2.claimed_value is None and p2.wants_risk
    p3 = parse_question("Apple FY2023 net income 96,995 million")
    assert p3.metric == "net_income" and p3.fiscal_year == 2023 and p3.claimed_value == 96_995e6


def test_zero_denominator_is_undefined():
    from app.reconciliation.engine import rel_diff

    assert rel_diff(5, 0) is None


def test_instant_metric_has_no_start(nwm):
    s = annual_series(nwm.observations, "long_term_debt")
    assert s and all(r.period_start is None and r.period_type == "instant" for r in s)
    assert s[-1].period_end == date(2024, 12, 31)


def _mk(val, form, filed, accn, start="2025-01-01", end="2025-12-31", tag="NetIncomeLoss"):
    from app.financial_data.companies import METRIC_BY_KEY, Company
    from app.financial_data.normalize import normalize_facts
    from app.models.schemas import DataStatus

    return normalize_facts([{"start": start, "end": end, "val": val, "accn": accn, "form": form, "filed": filed}],
                           company=Company("TST", "Test Co", "0000000001"), metric=METRIC_BY_KEY["net_income"],
                           tag=tag, unit="USD", channel="test", status=DataStatus.sample)


def test_proxy_statement_is_not_a_revision():
    from app.reconciliation.engine import other_document_findings

    obs = _mk(3_794e6, "10-K", "2026-01-29", "A-1") + _mk(3_855e6, "DEF 14A", "2026-10-19", "A-2")
    s = annual_series(obs, "net_income")
    assert s[-1].current.form == "10-K" and not s[-1].revised
    assert revision_findings(obs, "net_income") == []
    docs = other_document_findings(obs, "net_income")
    assert len(docs) == 1 and "DEF 14A" in docs[0].title
    exp = explain_value(3_855e6, obs, "net_income", period_end_year=2025, is_user_claim=True)
    assert exp.kind == "other_document"


def test_claim_binds_to_metric_next_to_amount():
    p = parse_question("Is Tesla's profit backed by operating cash flow, and was its 2024 revenue $97.7 billion?")
    assert p.metric == "revenue" and p.claimed_value == 97.7e9 and p.fiscal_year == 2024


def test_amendment_counts_as_statement_revision():
    obs = _mk(100e6, "10-K", "2025-02-01", "A-1") + _mk(90e6, "10-K/A", "2025-06-01", "A-2")
    s = annual_series(obs, "net_income")
    assert s[-1].current.value == 90e6 and s[-1].revised
