import math

import pytest
from pydantic import ValidationError

from app.models.schemas import FindingStatus, ScenarioInput
from app.risk_analysis.indicators import debt_trend, liquidity, profit_vs_cash, run_risk_indicators
from app.scenarios.calculator import calculate, simulate


def test_case5_profit_up_cash_down(nwm):
    f = profit_vs_cash(nwm.observations)
    assert "Profit rose" in f.title and "operating cash flow fell" in f.title
    assert f.severity == "elevated"  # three years running
    assert f.calculation_details["cash_conversion"]["2024"] == pytest.approx(2.7 / 4.4)
    assert f.counterevidence, "positive OCF must be listed as counterevidence"


def test_healthy_company_not_flagged(csr):
    f = profit_vs_cash(csr.observations)
    assert "moved together" in f.title and f.severity == "info"


def test_case6_missing_debt_is_insufficient_not_zero(csr):
    f = debt_trend(csr.observations)
    assert f.status == FindingStatus.insufficient_evidence
    assert "not evidence of zero debt" in f.uncertainty_or_limitations


def test_liquidity_ratio(nwm):
    f = liquidity(nwm.observations)
    assert f.calculation_details["current_ratio"] == pytest.approx(21 / 23)
    assert f.severity == "watch"  # below 1 and falling


def test_every_risk_finding_cites_evidence_or_is_insufficient(nwm, csr):
    for obs in (nwm.observations, csr.observations):
        for f in run_risk_indicators(obs):
            assert f.supporting_evidence or f.status == FindingStatus.insufficient_evidence


# --- Case 7: scenario calculations under different assumptions -------------------------

def test_zero_return_no_fees_equals_contributions():
    r = simulate(ScenarioInput(initial_amount=1000, monthly_contribution=100, years=5, annual_return_pct=0))
    assert r.final_nominal == pytest.approx(1000 + 100 * 60)
    assert r.nominal_gain == pytest.approx(0)


def test_lump_sum_matches_closed_form():
    r = simulate(ScenarioInput(initial_amount=10_000, years=10, annual_return_pct=7))
    assert r.final_nominal == pytest.approx(10_000 * 1.07 ** 10, abs=0.005)


def test_contributions_match_annuity_formula():
    rm = 1.06 ** (1 / 12) - 1
    expected = 200 * (((1 + rm) ** 120 - 1) / rm)
    r = simulate(ScenarioInput(initial_amount=0, monthly_contribution=200, years=10, annual_return_pct=6))
    assert r.final_nominal == pytest.approx(expected, abs=0.005)


def test_fees_and_inflation_reduce_outcome():
    base = dict(initial_amount=10_000, monthly_contribution=100, years=20, annual_return_pct=6)
    no_fee = simulate(ScenarioInput(**base))
    fee = simulate(ScenarioInput(**base, annual_fee_pct=1))
    infl = simulate(ScenarioInput(**base, inflation_pct=3))
    assert fee.final_nominal < no_fee.final_nominal and fee.total_fees > 0
    assert infl.final_real == pytest.approx(infl.final_nominal / 1.03 ** 20)


def test_negative_returns_allowed_and_labeled():
    resp = calculate([ScenarioInput(initial_amount=1000, years=3, annual_return_pct=-10)])
    r = resp.results[0]
    assert r.final_nominal == pytest.approx(1000 * 0.9 ** 3)
    assert "not a prediction" in r.label
    assert "not financial advice" in resp.disclaimer


def test_scenario_input_bounds():
    with pytest.raises(ValidationError):
        ScenarioInput(initial_amount=-1, years=5, annual_return_pct=5)
    with pytest.raises(ValidationError):
        ScenarioInput(initial_amount=1, years=0, annual_return_pct=5)
    assert math.isfinite(simulate(ScenarioInput(initial_amount=1e9, years=60, annual_return_pct=50)).final_nominal)


def test_fee_drag_is_growth_lost_to_fees():
    base = dict(initial_amount=5000, monthly_contribution=200, years=20, annual_return_pct=6)
    no_fee = simulate(ScenarioInput(**base))
    high = simulate(ScenarioInput(**base, annual_fee_pct=1.5))
    assert no_fee.fee_drag == pytest.approx(0, abs=0.01)
    assert high.final_without_fees == pytest.approx(no_fee.final_nominal, abs=0.01)
    assert high.fee_drag == pytest.approx(no_fee.final_nominal - high.final_nominal, abs=0.02)
    assert high.fee_drag > high.total_fees  # includes forgone growth on the fees
