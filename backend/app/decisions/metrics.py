"""Deterministic company metrics used by tripwires and the Brand-Blind Board.

Every value is computed from filed observations (latest filing of record, one concept per series)
and carries its formula, inputs and the observation ids behind it. Nothing here calls a model.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from app.models.schemas import Observation
from app.reconciliation.engine import PeriodResolution, annual_series, consistent_window, fmt_usd, rel_diff


@dataclass
class MetricValue:
    key: str
    value: Optional[float]
    period: Optional[str]  # e.g. "FY ending 2025-12-31"
    evidence: list[str] = field(default_factory=list)  # observation ids
    formula: str = ""
    inputs: dict[str, Any] = field(default_factory=dict)
    note: str = ""

    @property
    def available(self) -> bool:
        return self.value is not None


@dataclass(frozen=True)
class MetricSpec:
    key: str
    label: str
    unit: str  # "usd" | "pct" | "ratio" | "years" | "count"
    description: str
    higher_is: str  # "more" | "less" | "neutral": wording only, never a verdict
    tripwire: bool = True


SPECS: list[MetricSpec] = [
    MetricSpec("revenue", "Revenue (latest year)", "usd", "Sales in the latest fiscal year.", "more"),
    MetricSpec("revenue_growth", "Revenue growth", "pct", "Change in revenue versus the year before.", "more"),
    MetricSpec("revenue_decline_streak", "Years of falling revenue", "years",
               "How many years in a row revenue has fallen (0 if it rose last year).", "less"),
    MetricSpec("net_income", "Net income (latest year)", "usd", "Profit after all costs in the latest fiscal year.", "more"),
    MetricSpec("net_margin", "Net margin", "pct", "Net income as a share of revenue.", "more"),
    MetricSpec("operating_cash_flow", "Operating cash flow", "usd", "Cash the everyday business brought in.", "more"),
    MetricSpec("cash_conversion", "Cash conversion", "ratio",
               "Operating cash flow divided by net income. Below 1 means profit isn't fully arriving as cash.", "more"),
    MetricSpec("long_term_debt", "Long-term debt", "usd", "Borrowing due after more than a year, at the latest year-end.", "less"),
    MetricSpec("debt_to_ocf", "Debt / operating cash flow", "ratio",
               "Years of operating cash flow needed to repay long-term debt.", "less"),
    MetricSpec("current_ratio", "Current ratio", "ratio", "Short-term assets for each $1 owed within a year.", "more"),
    MetricSpec("gross_margin", "Gross margin", "pct", "Gross profit as a share of revenue.", "more"),
    MetricSpec("operating_margin", "Operating margin", "pct", "Operating income as a share of revenue.", "more"),
    MetricSpec("free_cash_flow", "Free cash flow", "usd", "Operating cash flow minus capital spending.", "more"),
    MetricSpec("cash", "Cash and equivalents", "usd", "Cash and cash equivalents at the latest year-end.", "more"),
    MetricSpec("recent_revisions", "Recent revised figures", "count",
               "Annual revenue, profit or cash-flow figures from the last 3 years that a later filing changed.", "neutral",
               tripwire=False),
]
SPEC_BY_KEY = {s.key: s for s in SPECS}


def _latest(series: list[PeriodResolution]) -> Optional[PeriodResolution]:
    return series[-1] if series else None


def _by_year(series: list[PeriodResolution]) -> dict[int, PeriodResolution]:
    return {r.period_end.year: r for r in series}


def compute_metrics(obs: list[Observation]) -> dict[str, MetricValue]:
    rev = consistent_window(annual_series(obs, "revenue"), 6)
    ni = consistent_window(annual_series(obs, "net_income"), 6)
    ocf = consistent_window(annual_series(obs, "operating_cash_flow"), 6)
    debt = consistent_window(annual_series(obs, "long_term_debt"), 4)
    ca, cl = _by_year(annual_series(obs, "current_assets")), _by_year(annual_series(obs, "current_liabilities"))
    out: dict[str, MetricValue] = {}

    def simple(key: str, series: list[PeriodResolution]) -> None:
        r = _latest(series)
        out[key] = MetricValue(key, r.current.value if r else None, r.label if r else None,
                               [r.current.id] if r else [], "as filed", {key: r.current.value} if r else {},
                               "" if r else "not reported")

    simple("revenue", rev)
    simple("net_income", ni)
    simple("operating_cash_flow", ocf)
    simple("long_term_debt", debt)

    if len(rev) >= 2:
        a, b = rev[-2], rev[-1]
        out["revenue_growth"] = MetricValue("revenue_growth", rel_diff(b.current.value, a.current.value), b.label,
                                            [a.current.id, b.current.id], "(revenue_t - revenue_t-1) / |revenue_t-1|",
                                            {a.label: a.current.value, b.label: b.current.value})
        streak = 0
        for x, y in zip(reversed(rev[:-1]), reversed(rev)):
            if y.current.value < x.current.value:
                streak += 1
            else:
                break
        out["revenue_decline_streak"] = MetricValue("revenue_decline_streak", float(streak), b.label,
                                                    [r.current.id for r in rev[-(streak + 1):]],
                                                    "consecutive years with revenue below the year before",
                                                    {r.label: r.current.value for r in rev})
    else:
        for k in ("revenue_growth", "revenue_decline_streak"):
            out[k] = MetricValue(k, None, None, note="needs two years of revenue")

    def pair(key: str, num: dict[int, PeriodResolution], den: dict[int, PeriodResolution], formula: str,
             guard: Callable[[float], bool], why: str) -> None:
        years = sorted(set(num) & set(den))
        if not years:
            out[key] = MetricValue(key, None, None, note="needs both figures for the same year")
            return
        y = years[-1]
        n, d = num[y], den[y]
        if not guard(d.current.value):
            out[key] = MetricValue(key, None, n.label, [n.current.id, d.current.id], formula,
                                   {"numerator": n.current.value, "denominator": d.current.value}, why)
            return
        out[key] = MetricValue(key, n.current.value / d.current.value, n.label, [n.current.id, d.current.id], formula,
                               {"numerator": n.current.value, "denominator": d.current.value})

    pair("net_margin", _by_year(ni), _by_year(rev), "net_income / revenue", lambda d: d > 0, "revenue not positive")
    pair("cash_conversion", _by_year(ocf), _by_year(ni), "operating_cash_flow / net_income", lambda d: d > 0,
         "undefined when net income is zero or negative")
    pair("debt_to_ocf", _by_year(debt), _by_year(ocf), "long_term_debt / operating_cash_flow", lambda d: d > 0,
         "undefined when operating cash flow is zero or negative")
    pair("current_ratio", ca, cl, "current_assets / current_liabilities", lambda d: d > 0, "no current liabilities")

    revised = []
    for m in ("revenue", "net_income", "operating_cash_flow"):
        for r in annual_series(obs, m)[-3:]:
            if r.revised:
                revised.append(r.current.id)
    out["recent_revisions"] = MetricValue("recent_revisions", float(len(revised)), "last 3 fiscal years", revised,
                                          "count of annual periods whose figure differs between filings")
    # A figure the company stopped reporting years ago (JPMorgan's long-term debt ends in FY2013) is not current.
    rev_years = [r.period_end.year for r in rev[-1:]] + [r.period_end.year for r in ni[-1:]]
    current = max(rev_years) if rev_years else None
    if current is not None and debt and debt[-1].period_end.year < current - 1:
        stale = f"last reported for FY{debt[-1].period_end.year}; no current figure"
        for k in ("long_term_debt", "debt_to_ocf"):
            if k in out:
                out[k] = MetricValue(k, None, None, note=stale)
    # From the key-figures facts sheet, so tripwires, the board and answers all use the same numbers.
    from app.analysis.key_figures import compute_key_figures
    kfs = {k.key: k for k in compute_key_figures(obs)}
    for key in ("gross_margin", "operating_margin", "free_cash_flow", "cash"):
        k, p = kfs.get(key), (kfs[key].latest if key in kfs else None)
        out[key] = MetricValue(key, p.value if p else None, f"FY ending {p.period_end.isoformat()}" if p else None,
                               p.evidence if p else [], k.formula if k else "", {}, "" if p else "not reported")
    return out


def fmt_metric(key: str, value: Optional[float]) -> str:
    if value is None:
        return "n/a"
    unit = SPEC_BY_KEY[key].unit
    if unit == "usd":
        return fmt_usd(value)
    if unit == "pct":
        return f"{value * 100:+.1f}%" if key.endswith("growth") else f"{value * 100:.1f}%"
    if unit == "ratio":
        return f"{value:.2f}x"
    if unit == "years":
        return f"{int(value)} yr"
    return f"{int(value)}"


def latest_filing(obs: list[Observation]) -> Optional[dict[str, Any]]:
    filed = [o for o in obs if o.published_at and o.form != "secondary"]
    if not filed:
        return None
    o = max(filed, key=lambda x: (x.published_at, x.accession_number or ""))
    return {"date": o.published_at.isoformat(), "form": o.form, "accession": o.accession_number, "url": o.source_url}
