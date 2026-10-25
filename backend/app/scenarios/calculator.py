"""Deterministic hypothetical investment scenarios.

Monthly simulation:
  r_m   = (1 + R)^(1/12) - 1          R = hypothetical annual return
  fee_m = F / 12                       F = annual fee rate, charged monthly on the balance
  B_t   = (B_{t-1} * (1 + r_m)) * (1 - fee_m) + C      C = monthly contribution, end of month
  real  = nominal / (1 + I)^(t/12)     I = annual inflation
"""
from __future__ import annotations

from app.models.schemas import ScenarioInput, ScenarioResponse, ScenarioResult, ScenarioYear

FORMULA = (
    "Each month: balance = (balance x (1 + r_m)) x (1 - F/12) + contribution, where "
    "r_m = (1 + R)^(1/12) - 1. Real value = nominal / (1 + I)^(years). R = hypothetical annual return, "
    "F = annual fee, I = annual inflation."
)

DISCLAIMER = (
    "Hypothetical illustration only. Returns are assumptions you chose, not forecasts, and real returns vary "
    "year to year and can be negative. Taxes are not modelled. This is not financial advice."
)


def _final_nominal(inp: ScenarioInput, fee_pct: float) -> float:
    r_m = (1 + inp.annual_return_pct / 100) ** (1 / 12) - 1
    fee_m = (fee_pct / 100) / 12
    balance = inp.initial_amount
    for _ in range(inp.years * 12):
        balance = balance * (1 + r_m) * (1 - fee_m) + inp.monthly_contribution
    return balance


def simulate(inp: ScenarioInput) -> ScenarioResult:
    r_m = (1 + inp.annual_return_pct / 100) ** (1 / 12) - 1
    fee_m = (inp.annual_fee_pct / 100) / 12
    infl = inp.inflation_pct / 100
    balance = inp.initial_amount
    contributed = inp.initial_amount
    fees = 0.0
    yearly: list[ScenarioYear] = [
        ScenarioYear(year=0, contributions_total=contributed, nominal_balance=balance, real_balance=balance, fees_paid_total=0)
    ]
    for month in range(1, inp.years * 12 + 1):
        grown = balance * (1 + r_m)
        fee = grown * fee_m
        fees += fee
        balance = grown - fee + inp.monthly_contribution
        contributed += inp.monthly_contribution
        if month % 12 == 0:
            y = month // 12
            real = balance / ((1 + infl) ** y)
            yearly.append(ScenarioYear(year=y, contributions_total=round(contributed, 2), nominal_balance=round(balance, 2),
                                       real_balance=round(real, 2), fees_paid_total=round(fees, 2)))
    final_real = balance / ((1 + infl) ** inp.years)
    without_fees = _final_nominal(inp, 0.0)
    return ScenarioResult(
        name=inp.name,
        inputs=inp,
        final_nominal=round(balance, 2),
        final_real=round(final_real, 2),
        total_contributed=round(contributed, 2),
        total_fees=round(fees, 2),
        nominal_gain=round(balance - contributed, 2),
        final_without_fees=round(without_fees, 2),
        fee_drag=round(without_fees - balance, 2),
        yearly=yearly,
    )


def calculate(scenarios: list[ScenarioInput]) -> ScenarioResponse:
    return ScenarioResponse(
        results=[simulate(s) for s in scenarios],
        formula=FORMULA,
        assumptions=[
            "Returns compound monthly at a constant hypothetical rate.",
            "Fees are charged monthly as a percentage of the balance.",
            "Contributions are added at the end of each month.",
            "Inflation adjustment divides by cumulative inflation; taxes are ignored.",
            "'Lost to fees' compares each option with the same plan at zero fees, so it includes growth the fees forgo.",
            "A constant return hides ups and downs: fund values can fall, which this model does not show.",
        ],
        disclaimer=DISCLAIMER,
    )


def default_scenarios(initial: float = 10_000, monthly: float = 200, years: int = 10) -> list[ScenarioInput]:
    """Adverse / baseline / favorable presets. The rates are illustrative assumptions, not forecasts."""
    return [
        ScenarioInput(name="Adverse", initial_amount=initial, monthly_contribution=monthly, years=years,
                      annual_return_pct=1.0, annual_fee_pct=1.0, inflation_pct=3.0),
        ScenarioInput(name="Baseline", initial_amount=initial, monthly_contribution=monthly, years=years,
                      annual_return_pct=5.0, annual_fee_pct=0.5, inflation_pct=2.5),
        ScenarioInput(name="Favorable", initial_amount=initial, monthly_contribution=monthly, years=years,
                      annual_return_pct=8.0, annual_fee_pct=0.2, inflation_pct=2.0),
    ]

