"""Key figures (the facts sheet), the answers built from them, and what the AI is given."""
import asyncio
import json

import pytest

from app.agents.narrator import Narrator, deterministic_answer, figures_named
from app.analysis.key_figures import compute_key_figures, facts_lines
from app.config import Settings
from app.decisions.metrics import compute_metrics
from app.financial_data.companies import METRICS, find_company
from app.financial_data.providers import SampleProvider
from app.reconciliation.claim_extraction import extract_claims
from app.reconciliation.claims import parse_question


def _obs(ticker):
    return asyncio.run(SampleProvider(Settings()).fetch(find_company(ticker), METRICS)).observations


@pytest.fixture(scope="module")
def nwm():
    return {k.key: k for k in compute_key_figures(_obs("NWM"))}


@pytest.fixture(scope="module")
def csr():
    return {k.key: k for k in compute_key_figures(_obs("CSR"))}


def test_filed_and_derived_figures_are_computed_from_the_filings(nwm):
    assert nwm["revenue"].sentence() == "Revenue was $52.40B in FY2024, up 8.5% from $48.30B in FY2023; it was $41.00B in FY2021."
    assert nwm["gross_margin"].latest.value == pytest.approx(8.59 / 52.4)
    assert nwm["gross_margin"].sentence().startswith("Gross margin was 16.4% in FY2024, down 0.6 points from 17.0% in FY2023")
    fcf = nwm["free_cash_flow"]
    assert [round(p.value / 1e9, 2) for p in fcf.points] == [2.2, 1.2, -0.2, -1.9]  # OCF minus capex, per year
    assert len(fcf.latest.evidence) == 2  # cites both filed observations it used (cash flow and capital spending)


def test_no_percentage_change_when_a_year_is_negative(nwm):
    # "-$0.2B to -$1.9B" as a percentage is nonsense, so only the two values are given.
    fcf = nwm["free_cash_flow"]
    assert fcf.change is None and fcf.direction == "down"
    assert fcf.sentence().startswith("Free cash flow was -$1.90B in FY2024, down from -$200.0M in FY2023")
    assert "%" not in fcf.sentence().split("(")[0]


def test_unreported_figures_say_so_instead_of_inventing(csr):
    assert csr["rnd"].points == []
    lines = {x["id"]: x["text"] for x in facts_lines(list(csr.values()))}
    assert lines["kf-rnd"] == "R&D spending: not reported in the filings Parallax read."
    assert "kf-rnd_share" not in lines  # derived figures with no data are simply left out


def test_plural_figures_read_naturally(nwm):
    assert nwm["buybacks"].sentence().startswith("Share buybacks were $100.0M in FY2024")
    assert "they were $300.0M in FY2021" in nwm["buybacks"].sentence()


def test_questions_name_the_right_figure():
    assert figures_named("Is free cash flow margin improving?") == ["fcf_margin"]
    assert figures_named("Is free cash flow positive?") == ["free_cash_flow"]
    assert figures_named("How much cash does it have compared with its debt?") == ["cash", "long_term_debt"]  # both lines
    assert figures_named("What is its cash minus debt?") == ["net_cash"]
    assert figures_named("Does it return cash to shareholders?") == ["shareholder_returns"]
    assert figures_named("What is the operating margin and gross profit?") == ["gross_profit", "operating_margin"]
    assert figures_named("Is profit backed by cash flow?") == ["operating_cash_flow", "net_income"]
    assert figures_named("Is Northwind Motors' profit backed by real cash?") == ["operating_cash_flow", "net_income"]


def test_coded_answers_for_common_questions(nwm, csr):
    kn, kc = list(nwm.values()), list(csr.values())
    assert deterministic_answer("Is Northwind Motors' free cash flow positive?", [], kn).startswith("No: Free cash flow was -$1.90B")
    assert deterministic_answer("Is the operating margin improving?", [], kn).startswith("Yes: Operating margin was 11.5%")
    assert deterministic_answer("Is the gross margin worsening?", [], kn).startswith("Yes: Gross margin was 16.4%")
    assert deterministic_answer("Is debt rising?", [], kn).startswith("Yes: Long-term debt was $19.50B")
    assert deterministic_answer("What is the gross margin?", [], kn).startswith("Gross margin was 16.4%")
    assert deterministic_answer("How much does Contoso spend on R&D?", [], kc) == "R&D spending: not reported in the filings Parallax read."
    assert deterministic_answer("Should I buy it?", [], kn).startswith("Parallax doesn't make investment decisions")


def test_derived_figures_are_never_checked_as_the_wrong_filed_figure():
    assert parse_question("Was the 2024 free cash flow really $2 billion?").metric is None  # not operating cash flow
    assert parse_question("Was the 2024 gross profit really $9 billion?").metric == "gross_profit"
    ex = extract_claims("Northwind Motors had free cash flow of $2 billion in 2024.")
    assert ex.claims == [] and "aren't checked as claims yet" in ex.skipped[0]["reason"]
    ex = extract_claims("Northwind Motors paid $750 million in dividends in 2024.")
    assert [(c.metric, c.fiscal_year) for c in ex.claims] == [("dividends", 2024)]


def test_tripwires_and_board_use_the_same_numbers(nwm):
    m = compute_metrics(_obs("NWM"))
    assert m["free_cash_flow"].value == nwm["free_cash_flow"].latest.value
    assert m["gross_margin"].value == nwm["gross_margin"].latest.value
    assert m["cash"].value == 3.6e9


def test_the_ai_gets_the_facts_and_a_specific_retry(nwm):
    """First answer invents a number; the retry is told exactly why, and the corrected answer is accepted."""
    from app.models.schemas import Classification, Finding, FindingStatus

    finding = Finding(id="risk-rev-2024", category="risk", title="Revenue trend: +8.5% in the latest fiscal year", claim="c",
                      classification=Classification.calculation, supporting_evidence=[], uncertainty_or_limitations="",
                      why_it_matters="", status=FindingStatus.supported, severity="info")
    sent = []
    replies = [
        {"answer": "Free cash flow was -$6.41B.", "summary": "s", "key_points": [{"text": "t", "finding_ids": ["kf-free_cash_flow"]}]},
        {"answer": "No: free cash flow was -$1.90B in FY2024.", "summary": "Free cash flow was -$1.90B in FY2024.",
         "key_points": [{"text": "Free cash flow was -$1.90B in FY2024.", "finding_ids": ["kf-free_cash_flow"]}]},
    ]
    n = Narrator(Settings())
    n.provider, n.detail = "fake", "test"

    async def complete(system, user, schema):
        sent.append(json.loads(user))
        return json.dumps(replies[len(sent) - 1]), {}, "fake-model", 1

    n._complete = complete  # type: ignore[method-assign]
    summary, call = asyncio.run(n.narrate("Is free cash flow positive?", "Northwind Motors", [finding], list(nwm.values())))
    assert any(f["id"] == "kf-free_cash_flow" and "-$1.90B" in f["text"] for f in sent[0]["facts"])
    assert "introduced numbers not present in the evidence: ['6.41']" in sent[1]["previous_answer_rejected_because"]
    assert "do not calculate" in sent[1]["previous_answer_rejected_because"]
    assert call.output_accepted and summary.answer.startswith("No: free cash flow was -$1.90B")
    assert summary.key_points[0]["finding_ids"] == ["kf-free_cash_flow"]  # facts can be cited like findings


def test_a_wrong_direction_on_a_new_figure_is_rejected(nwm):
    from app.analysis.key_figures import directions
    from app.verification.directions import contradicted_direction

    d = directions(list(nwm.values()))
    assert d["gross_margin"] == "down" and d["operating_margin"] == "up"
    assert contradicted_direction("Gross margin improved to 16.4% in FY2024.", d)
    assert contradicted_direction("Gross margin fell to 16.4% in FY2024.", d) is None
    assert contradicted_direction("Free cash flow rose to -$1.90B.", d)  # it fell


def _jpm_like():
    """Revenue to FY2025; long-term debt last tagged in FY2013 (as JPMorgan); negative operating cash flow."""
    from datetime import date, datetime, timezone

    from app.models.schemas import Observation

    def o(metric, end, v, start=True):
        return Observation(id=f"{metric}-{end}", company="Bank", ticker="JPM", metric=metric, concept="us-gaap:X",
                           value=v, currency_or_unit="USD", period_start=date(int(end[:4]), 1, 1) if start else None,
                           period_end=date.fromisoformat(end), period_type="annual" if start else "instant",
                           form="10-K", published_at=date(int(end[:4]) + 1, 2, 15), source_name="SEC",
                           retrieved_at=datetime.now(timezone.utc), retrieval_channel="sec_direct", data_status="live")
    return [o("revenue", "2024-12-31", 177.56e9), o("revenue", "2025-12-31", 182.45e9),
            o("net_income", "2024-12-31", 58.47e9), o("net_income", "2025-12-31", 57.05e9),
            o("operating_cash_flow", "2024-12-31", -42.01e9), o("operating_cash_flow", "2025-12-31", -147.78e9),
            o("long_term_debt", "2012-12-31", 249.02e9, start=False), o("long_term_debt", "2013-12-31", 267.89e9, start=False)]


def test_a_figure_last_reported_years_ago_is_not_shown_as_current():
    kfs = {k.key: k for k in compute_key_figures(_jpm_like())}
    debt = kfs["long_term_debt"]
    assert debt.stale and debt.direction is None
    assert debt.sentence().startswith("Long-term debt was last reported for FY2013 ($267.89B)")
    assert not kfs["revenue"].stale


def test_stale_debt_and_negative_cash_flow_risk_findings():
    from app.risk_analysis.indicators import debt_trend, profit_vs_cash

    d = debt_trend(_jpm_like())
    assert d.title == "Long-term debt: no current figure (last reported for FY2013)"
    assert d.status.value == "insufficient_evidence"
    p = profit_vs_cash(_jpm_like())
    assert p.title.startswith("Operating cash flow was negative in 2025 (-$147.78B, from -$42.01B)")
    assert "moved together" not in p.title and "%" not in p.title
    assert "financial companies" in p.uncertainty_or_limitations
