"""Bounded, deterministic risk indicators with evidence and counterevidence.

Indicators: revenue trend, profit vs operating-cash-flow divergence, cash conversion,
long-term debt trend and debt coverage, and the current ratio. Each finding separates the
reported facts (cited observations), the calculation (formula + inputs) and the
interpretation (what it may mean and what it cannot establish). No buy/sell judgement.
"""
from __future__ import annotations

from typing import Optional

from app.models.schemas import Classification, EvidenceRef, Finding, FindingStatus, Observation
from app.reconciliation.engine import PeriodResolution, _fid, annual_series, consistent_window, fmt_usd, rel_diff


def _growth(series: list[PeriodResolution]) -> list[tuple[PeriodResolution, PeriodResolution, Optional[float]]]:
    return [(a, b, rel_diff(b.current.value, a.current.value)) for a, b in zip(series, series[1:])]


def _pct(x: Optional[float]) -> str:
    return "undefined" if x is None else f"{x * 100:+.1f}%"


def _by_year(series: list[PeriodResolution]) -> dict[int, PeriodResolution]:
    return {r.period_end.year: r for r in series}


def revenue_trend(obs: list[Observation]) -> Optional[Finding]:
    s = consistent_window(annual_series(obs, "revenue"), 4)
    if len(s) < 2:
        return None
    g = _growth(s)
    latest = g[-1][2]
    declines = [x for _, _, x in g if x is not None and x < 0]
    return Finding(
        id=_fid("risk-rev", s[-1].period_end),
        category="risk",
        title=f"Revenue trend: {_pct(latest)} in the latest fiscal year",
        claim="Year-over-year revenue change: " + "; ".join(
            f"{b.period_end.year} {_pct(x)}" for _, b, x in g),
        classification=Classification.calculation,
        supporting_evidence=[EvidenceRef(observation_id=r.current.id, note=r.label) for r in s],
        calculation_details={
            "formula": "growth_t = (revenue_t - revenue_{t-1}) / |revenue_{t-1}|",
            "inputs": {r.label: r.current.value for r in s},
            "growth": {b.label: x for _, b, x in g},
        },
        uncertainty_or_limitations="Growth figures ignore acquisitions, divestitures, currency effects and inflation.",
        why_it_matters="Sustained declines can pressure profits and debt service; one weak year alone says little.",
        status=FindingStatus.supported,
        severity="watch" if len(declines) >= 2 or (latest is not None and latest < -0.1) else "info",
    )


def profit_vs_cash(obs: list[Observation]) -> Optional[Finding]:
    ni = _by_year(consistent_window(annual_series(obs, "net_income"), 6))
    ocf = _by_year(consistent_window(annual_series(obs, "operating_cash_flow"), 6))
    years = sorted(set(ni) & set(ocf))[-4:]
    if len(years) < 2:
        missing = "net income" if not ni else "operating cash flow" if not ocf else "overlapping years"
        return Finding(
            id=_fid("risk-cash-missing", len(ni), len(ocf)),
            category="risk",
            title="Profit vs operating cash flow: not enough data",
            claim=f"Cannot compare profit with operating cash flow: missing {missing}.",
            classification=Classification.calculation,
            uncertainty_or_limitations="The company may report these under concepts Parallax does not map.",
            status=FindingStatus.insufficient_evidence,
        )
    conv = {y: (ocf[y].current.value / ni[y].current.value) if ni[y].current.value > 0 else None for y in years}
    y0, y1 = years[-2], years[-1]
    ni_g = rel_diff(ni[y1].current.value, ni[y0].current.value)
    ocf_g = rel_diff(ocf[y1].current.value, ocf[y0].current.value)
    diverging = ni_g is not None and ocf_g is not None and ni_g > 0 and ocf_g < 0
    run = 0
    for a, b in zip(years, years[1:]):
        g1 = rel_diff(ni[b].current.value, ni[a].current.value)
        g2 = rel_diff(ocf[b].current.value, ocf[a].current.value)
        run = run + 1 if (g1 is not None and g2 is not None and g1 > 0 and g2 < 0) else 0
    counter: list[EvidenceRef] = []
    counter_notes: list[str] = []
    if ocf[y1].current.value > 0:
        counter.append(EvidenceRef(observation_id=ocf[y1].current.id, note="operating cash flow still positive"))
        counter_notes.append("operating cash flow is still positive")
    c1 = conv.get(y1)
    if c1 is not None and c1 >= 1:
        counter_notes.append(f"cash conversion is {c1:.2f}x (cash still exceeds profit)")
    evidence = []
    for y in years:
        evidence += [EvidenceRef(observation_id=ni[y].current.id, note=f"net income {y}"),
                     EvidenceRef(observation_id=ocf[y].current.id, note=f"operating cash flow {y}")]
    negative = ocf[y0].current.value <= 0 or ocf[y1].current.value <= 0
    if negative:
        # A percentage change to or from a negative cash flow means nothing ("-251.8%"), so state the values.
        diverging = False
        title = (f"Operating cash flow was {'negative' if ocf[y1].current.value <= 0 else 'positive'} in {y1} "
                 f"({fmt_usd(ocf[y1].current.value)}, from {fmt_usd(ocf[y0].current.value)}) while net income was "
                 f"{fmt_usd(ni[y1].current.value)}")
        counter_notes.append("for banks, insurers and other financial companies, operating cash flow swings with "
                             "lending, deposits and trading, so it says little about profit quality")
    elif diverging:
        title = (f"Profit rose {_pct(ni_g)} while operating cash flow fell {_pct(ocf_g)} in {y1}"
                 + (f" ({run} years running)" if run > 1 else ""))
    else:
        title = f"Profit and operating cash flow moved together in {y1} (net income {_pct(ni_g)}, cash flow {_pct(ocf_g)})"
    return Finding(
        id=_fid("risk-cash", y1, diverging),
        category="risk",
        title=title,
        claim=(
            f"Net income {fmt_usd(ni[y0].current.value)} -> {fmt_usd(ni[y1].current.value)}; operating cash flow "
            f"{fmt_usd(ocf[y0].current.value)} -> {fmt_usd(ocf[y1].current.value)}. Cash conversion (OCF / net income): "
            + ", ".join(f"{y} {conv[y]:.2f}x" if conv[y] is not None else f"{y} n/a (net income <= 0)" for y in years)
            + "."
        ),
        classification=Classification.interpretation if diverging else Classification.calculation,
        supporting_evidence=evidence,
        counterevidence=counter,
        calculation_details={
            "formula": "cash_conversion = operating_cash_flow / net_income (undefined when net income <= 0)",
            "inputs": {str(y): {"net_income": ni[y].current.value, "operating_cash_flow": ocf[y].current.value} for y in years},
            "cash_conversion": {str(y): conv[y] for y in years},
            "net_income_growth": ni_g,
            "ocf_growth": None if negative else ocf_g,
        },
        uncertainty_or_limitations=(
            "A gap between profit and cash can come from growing receivables or inventory, timing of payments, "
            "non-cash gains, or aggressive revenue recognition. These numbers cannot tell which. "
            + (("Counterevidence: " + "; ".join(counter_notes) + ".") if counter_notes else "")
        ),
        why_it_matters=(
            "Profits that do not turn into cash over several years are a classic reason to read the cash-flow "
            "statement and working-capital notes closely."
        ),
        status=FindingStatus.supported,
        severity="elevated" if diverging and run > 1 else "watch" if (diverging or negative) else "info",
    )


def latest_filed_year(obs: list[Observation]) -> Optional[int]:
    """The company's latest fiscal year, from its annual revenue or net income."""
    years = [r.period_end.year for k in ("revenue", "net_income") for r in annual_series(obs, k)[-1:]]
    return max(years) if years else None


def debt_trend(obs: list[Observation]) -> Optional[Finding]:
    debt = annual_series(obs, "long_term_debt")
    if not debt:
        return Finding(
            id=_fid("risk-debt-missing", "none"),
            category="risk",
            title="Long-term debt: no reported figures found",
            claim="No long-term debt facts were found under LongTermDebtNoncurrent or LongTermDebt.",
            classification=Classification.reported_fact,
            uncertainty_or_limitations=(
                "Missing data is not evidence of zero debt. The company may report debt under other concepts "
                "or in notes that Parallax does not read."
            ),
            status=FindingStatus.insufficient_evidence,
        )
    s = consistent_window(debt, 4)
    ocf = _by_year(annual_series(obs, "operating_cash_flow"))
    last = s[-1]
    current = latest_filed_year(obs)
    if current is not None and last.period_end.year < current - 1:
        # e.g. JPMorgan: the standard long-term-debt line stops in FY2013; a 2013 figure says nothing about today.
        return Finding(
            id=_fid("risk-debt-stale", last.period_end),
            category="risk",
            title=f"Long-term debt: no current figure (last reported for FY{last.period_end.year})",
            claim=(f"The latest filings (FY{current}) don't report long-term debt under LongTermDebtNoncurrent or "
                   f"LongTermDebt; the last value found is {fmt_usd(last.current.value)} for FY{last.period_end.year}, "
                   f"too old to judge debt today."),
            classification=Classification.reported_fact,
            supporting_evidence=[EvidenceRef(observation_id=last.current.id, note=last.label)],
            uncertainty_or_limitations=("Banks and other financial companies often report borrowings under other "
                                        "concepts, which Parallax doesn't map. Missing data is not evidence of no debt."),
            status=FindingStatus.insufficient_evidence,
        )
    g = rel_diff(last.current.value, s[0].current.value) if len(s) > 1 else None
    coverage = None
    o = ocf.get(last.period_end.year)
    if o and o.current.value > 0:
        coverage = last.current.value / o.current.value
    evidence = [EvidenceRef(observation_id=r.current.id, note=r.label) for r in s]
    if o:
        evidence.append(EvidenceRef(observation_id=o.current.id, note="operating cash flow, same year"))
    return Finding(
        id=_fid("risk-debt", last.period_end),
        category="risk",
        title=(f"Long-term debt {fmt_usd(last.current.value)}"
               + (f", {_pct(g)} since {s[0].period_end.year}" if g is not None else "")
               + (f"; {coverage:.1f} years of operating cash flow" if coverage is not None else "")),
        claim=f"Long-term debt ({s[-1].current.concept}) by year-end: " + "; ".join(
            f"{r.period_end.isoformat()} {fmt_usd(r.current.value)}" for r in s) + ".",
        classification=Classification.calculation,
        supporting_evidence=evidence,
        calculation_details={
            "formula": "debt_to_ocf = long_term_debt / operating_cash_flow (same fiscal year; undefined if OCF <= 0)",
            "inputs": {r.label: r.current.value for r in s},
            "debt_growth_over_window": g,
            "debt_to_ocf": coverage,
        },
        uncertainty_or_limitations=(
            "Excludes current portion of debt, leases and off-balance-sheet obligations. Captive finance arms "
            "(common at automakers) carry large debt by design."
        ),
        why_it_matters="Rising debt relative to cash generation reduces flexibility if conditions worsen.",
        status=FindingStatus.supported,
        severity="watch" if (g is not None and g > 0.3) or (coverage is not None and coverage > 4) else "info",
    )


def liquidity(obs: list[Observation]) -> Optional[Finding]:
    ca = _by_year(annual_series(obs, "current_assets"))
    cl = _by_year(annual_series(obs, "current_liabilities"))
    years = sorted(set(ca) & set(cl))
    if not years:
        return Finding(
            id=_fid("risk-liq-missing", len(ca), len(cl)),
            category="risk",
            title="Current ratio: not available",
            claim="Current assets and current liabilities were not both reported for the same year-end.",
            classification=Classification.calculation,
            uncertainty_or_limitations=(
                "Some companies (for example those with finance subsidiaries) present an unclassified balance sheet "
                "with no current/non-current split."
            ),
            status=FindingStatus.insufficient_evidence,
        )
    y = years[-1]
    ratio = ca[y].current.value / cl[y].current.value if cl[y].current.value else None
    prev = years[-2] if len(years) > 1 else None
    prev_ratio = (ca[prev].current.value / cl[prev].current.value) if prev and cl[prev].current.value else None
    return Finding(
        id=_fid("risk-liq", y),
        category="risk",
        title=f"Current ratio {ratio:.2f}" + (f" (was {prev_ratio:.2f})" if prev_ratio else "") if ratio else "Current ratio undefined",
        claim=f"Current assets {fmt_usd(ca[y].current.value)} / current liabilities {fmt_usd(cl[y].current.value)} "
              f"at {ca[y].period_end.isoformat()}.",
        classification=Classification.calculation,
        supporting_evidence=[EvidenceRef(observation_id=ca[y].current.id, note="current assets"),
                             EvidenceRef(observation_id=cl[y].current.id, note="current liabilities")],
        calculation_details={"formula": "current_ratio = current_assets / current_liabilities",
                             "inputs": {"current_assets": ca[y].current.value, "current_liabilities": cl[y].current.value},
                             "current_ratio": ratio, "previous_ratio": prev_ratio},
        uncertainty_or_limitations=(
            "A ratio below 1.0 is normal for some business models (large retailers collect cash before paying "
            "suppliers). Compare with the company's own history and peers rather than a fixed threshold."
        ),
        why_it_matters="Shows whether short-term obligations are covered by short-term assets.",
        status=FindingStatus.supported,
        severity="watch" if ratio is not None and ratio < 1 and prev_ratio is not None and ratio < prev_ratio else "info",
    )


def run_risk_indicators(obs: list[Observation]) -> list[Finding]:
    out = []
    for fn in (revenue_trend, profit_vs_cash, debt_trend, liquidity):
        f = fn(obs)
        if f is not None:
            out.append(f)
    return out
