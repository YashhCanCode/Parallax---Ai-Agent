"""Build the financial facts Parallax stores in Meterless H-MEM.

Each fact is keyed by company + metric + exact period, so H-MEM can tell "the same figure seen
again" (confirmed) from "a different value for the same period" (conflict). Keys:
  duration metrics: TICKER:metric:START..END      instant metrics: TICKER:metric:END
"""
from __future__ import annotations

from typing import Any

from app.financial_data.companies import METRIC_BY_KEY, Company
from app.models.schemas import Observation
from app.reconciliation.engine import PeriodResolution, annual_series, resolve_periods

ANNUAL_METRICS = ("revenue", "net_income", "operating_cash_flow", "long_term_debt")
QUARTERLY_METRICS = ("revenue", "net_income", "operating_cash_flow")


def fact_key(ticker: str, metric: str, r: PeriodResolution) -> str:
    if r.period_start is None:
        return f"{ticker}:{metric}:{r.period_end.isoformat()}"
    return f"{ticker}:{metric}:{r.period_start.isoformat()}..{r.period_end.isoformat()}"


def _fact(company: Company, metric: str, r: PeriodResolution, kind: str) -> dict[str, Any]:
    o = r.current
    label = METRIC_BY_KEY[metric].label
    if kind == "quarter":
        period = f"quarter {r.period_start} to {r.period_end}"
    elif r.period_start is None:
        period = f"as of {r.period_end}"
    else:
        period = f"fiscal year ending {r.period_end}"
    return {
        "key": fact_key(company.ticker, metric, r),
        "label": f"{label}, {period}",
        "content": f"{company.name} {label.lower()} for the {period}, as filed ({o.concept})",
        "value": o.value,
        "source": f"{o.retrieval_channel}:{o.accession_number or o.source_name}",
        "refs": [u for u in [o.source_url] if u],
        "filed": o.published_at.isoformat() if o.published_at else None,
        "confidence": 0.5 if o.data_status.value == "sample" else 0.8,
        "tags": [f"metric:{metric}", f"status:{o.data_status.value}", f"period:{kind}"],
        "observation_id": o.id,
        "form": o.form,
    }


def build_memory_facts(company: Company, observations: list[Observation], years: int = 3,
                       quarters: int = 2) -> list[dict[str, Any]]:
    facts = []
    for m in ANNUAL_METRICS:
        for r in annual_series(observations, m)[-years:]:
            facts.append(_fact(company, m, r, "annual"))
    for m in QUARTERLY_METRICS:
        for r in resolve_periods(observations, METRIC_BY_KEY[m], ("quarterly",))[-quarters:]:
            facts.append(_fact(company, m, r, "quarter"))
    return facts


def sidecar_payload(facts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    keep = ("key", "content", "value", "source", "refs", "filed", "confidence", "tags")
    return [{k: f[k] for k in keep} for f in facts]
