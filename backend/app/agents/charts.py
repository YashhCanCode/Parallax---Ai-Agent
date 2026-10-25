"""Chart-ready data derived only from observations and findings (no invented points)."""
from __future__ import annotations

from typing import Any, Optional

from app.financial_data.companies import METRIC_BY_KEY
from app.models.schemas import Finding, Observation
from app.reconciliation.engine import annual_series, is_primary


def trend_series(obs: list[Observation]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in ("revenue", "net_income", "operating_cash_flow", "long_term_debt"):
        s = annual_series(obs, key)[-8:]
        out[key] = {
            "label": METRIC_BY_KEY[key].label,
            "unit": "USD",
            "points": [
                {
                    "period_end": r.period_end.isoformat(),
                    "period_start": r.period_start.isoformat() if r.period_start else None,
                    "label": r.label,
                    "value": r.current.value,
                    "original_value": r.original.value,
                    "revised": r.revised,
                    "observation_id": r.current.id,
                    "concept": r.current.concept,
                    "form": r.current.form,
                    "filed": r.current.published_at.isoformat() if r.current.published_at else None,
                    "source_url": r.current.source_url,
                }
                for r in s
            ],
        }
    return out


def quarterly_series(obs: list[Observation]) -> dict[str, Any]:
    """Latest 8 standalone quarters (from 10-Q filings) for flow metrics. Fiscal Q4 is usually not filed as a
    standalone quarter, so gaps are expected and left visible rather than derived."""
    from app.reconciliation.engine import resolve_periods

    out: dict[str, Any] = {}
    for key in ("revenue", "net_income", "operating_cash_flow"):
        s = resolve_periods(obs, METRIC_BY_KEY[key], ("quarterly",))[-8:]
        out[key] = {"label": METRIC_BY_KEY[key].label, "unit": "USD", "points": [
            {"period_end": r.period_end.isoformat(), "period_start": r.period_start.isoformat() if r.period_start else None,
             "label": r.label, "value": r.current.value, "original_value": r.original.value, "revised": r.revised,
             "observation_id": r.current.id, "concept": r.current.concept, "form": r.current.form,
             "filed": r.current.published_at.isoformat() if r.current.published_at else None,
             "source_url": r.current.source_url} for r in s]}
    return out


def source_comparison(obs: list[Observation], metric: str, year: Optional[int],
                      claim_value: Optional[float], claim_text: Optional[str]) -> dict[str, Any]:
    series = annual_series(obs, metric)
    if not series:
        return {"metric": metric, "bars": [], "period": None}
    ref = next((r for r in series if year and r.period_end.year == year), series[-1])
    bars: list[dict[str, Any]] = []
    for concept, items in ref.by_concept.items():
        for o in items:
            bars.append({
                "label": f"{o.form or 'filing'} filed {o.published_at}",
                "kind": "filing",
                "value": o.value,
                "concept": concept,
                "observation_id": o.id,
                "published_at": o.published_at.isoformat() if o.published_at else None,
                "is_current": o.id == ref.current.id,
                "basis": o.reporting_basis,
            })
    for o in obs:
        if o.metric == metric and not is_primary(o) and o.period_end == ref.period_end:
            bars.append({"label": o.source_name, "kind": "secondary", "value": o.value, "concept": o.concept,
                         "observation_id": o.id, "published_at": o.published_at.isoformat() if o.published_at else None,
                         "is_current": False, "basis": o.reporting_basis})
    # Quarterly / YTD figures within the same fiscal year, so period mix-ups are visible.
    for o in obs:
        if (o.metric == metric and is_primary(o) and o.period_type in ("quarterly", "ytd") and ref.period_start
                and ref.period_start < o.period_end <= ref.period_end):
            bars.append({"label": f"{o.period_type} {o.period_start}..{o.period_end}", "kind": o.period_type,
                         "value": o.value, "concept": o.concept, "observation_id": o.id,
                         "published_at": o.published_at.isoformat() if o.published_at else None,
                         "is_current": False, "basis": o.reporting_basis})
    if claim_value is not None:
        bars.append({"label": f"Your claim ({claim_text})", "kind": "claim", "value": claim_value, "concept": "user claim",
                     "observation_id": None, "published_at": None, "is_current": False, "basis": "n/a"})
    return {"metric": metric, "metric_label": METRIC_BY_KEY[metric].label, "unit": "USD",
            "period": ref.label, "period_end": ref.period_end.isoformat(), "bars": bars}


def timeline(obs: list[Observation]) -> list[dict[str, Any]]:
    seen: dict[str, dict[str, Any]] = {}
    for o in obs:
        if o.published_at is None:
            continue
        key = o.accession_number or f"{o.source_name}|{o.published_at}"
        item = seen.setdefault(key, {
            "date": o.published_at.isoformat(), "form": o.form, "source_name": o.source_name,
            "accession": o.accession_number, "url": o.source_url, "metrics": set(), "kind":
            "secondary" if not is_primary(o) else "filing",
        })
        item["metrics"].add(o.metric)
    items = sorted(seen.values(), key=lambda x: x["date"])[-24:]
    for i in items:
        i["metrics"] = sorted(i["metrics"])
    return items


def risk_dashboard(findings: list[Finding]) -> list[dict[str, Any]]:
    return [{"id": f.id, "title": f.title, "severity": f.severity, "status": f.status.value,
             "classification": f.classification.value} for f in findings if f.category == "risk"]


def build_charts(obs: list[Observation], findings: list[Finding], focus_metric: str, focus_year: Optional[int],
                 claim_value: Optional[float], claim_text: Optional[str]) -> dict[str, Any]:
    statuses = sorted({o.data_status.value for o in obs})
    channels = sorted({o.retrieval_channel for o in obs})
    return {
        "meta": {"unit": "USD (nominal, as reported)", "data_status": statuses, "channels": channels},
        "trends": trend_series(obs),
        "quarterly": quarterly_series(obs),
        "source_comparison": source_comparison(obs, focus_metric, focus_year, claim_value, claim_text),
        "timeline": timeline(obs),
        "risk_dashboard": risk_dashboard(findings),
    }
