"""Normalize raw SEC XBRL `companyconcept` facts into Observation records.

The raw fact shape (from data.sec.gov/api/xbrl/companyconcept, and identical through the
Zetaris schemastore views, which flatten the same JSON) is:
  {start?, end, val, accn, fy, fp, form, filed, frame?}

Important: the payload's `fy`/`fp` describe the *filing*, not the period. A FY2024 10-K
carries FY2022 and FY2023 comparatives that are also tagged fy=2024. We therefore derive the
period's fiscal year from `end` and record the filing's fy/fp separately.
"""
from __future__ import annotations

import hashlib
from datetime import date, datetime, timezone
from typing import Any, Iterable

from app.financial_data.companies import Company, MetricDef
from app.models.schemas import DataStatus, Observation


def _d(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def classify_period(start: date | None, end: date) -> str:
    if start is None:
        return "instant"
    days = (end - start).days + 1
    if 350 <= days <= 380:
        return "annual"
    if 80 <= days <= 100:
        return "quarterly"
    if 100 < days < 350:
        return "ytd"
    return "other"


def filing_url(cik: str, accession: str | None) -> str | None:
    if not accession or not cik.isdigit():
        return None
    return f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}/"


def concept_api_url(cik: str, tag: str) -> str:
    return f"https://data.sec.gov/api/xbrl/companyconcept/CIK{cik}/us-gaap/{tag}.json"


def obs_id(*parts: Any) -> str:
    raw = "|".join(str(p) for p in parts)
    return "obs-" + hashlib.sha1(raw.encode()).hexdigest()[:12]


def normalize_facts(
    facts: Iterable[dict[str, Any]],
    *,
    company: Company,
    metric: MetricDef,
    tag: str,
    unit: str,
    channel: str,
    status: DataStatus,
    retrieved_at: datetime | None = None,
    source_name_prefix: str = "SEC EDGAR",
) -> list[Observation]:
    retrieved_at = retrieved_at or datetime.now(timezone.utc)
    out: list[Observation] = []
    seen: set[tuple] = set()
    for f in facts:
        try:
            end = _d(f.get("end") or f.get("period_end"))
            if end is None:
                continue
            start = _d(f.get("start") or f.get("period_start"))
            raw_val = f.get("val", f.get("value_usd", f.get("value")))
            if raw_val is None:
                continue
            value = float(raw_val)
        except (TypeError, ValueError):
            continue
        accn = f.get("accn") or f.get("accession_number")
        key = (tag, start, end, accn, value)
        if key in seen:  # the same fact can appear twice (e.g. with and without a frame)
            continue
        seen.add(key)
        period_type = classify_period(start, end)
        if metric.kind == "instant" and period_type != "instant":
            continue
        form = f.get("form") or f.get("form_type")
        filed = _d(f.get("filed") or f.get("filed_date"))
        notes = [
            f"period fiscal year derived from period end ({end.isoformat()}); "
            f"filing reported fy={f.get('fy', f.get('fiscal_year'))} fp={f.get('fp', f.get('fiscal_period'))}"
        ]
        if f.get("frame") or f.get("period_frame"):
            notes.append(f"SEC frame {f.get('frame') or f.get('period_frame')}")
        if f.get("note"):
            notes.append(str(f["note"]))
        out.append(
            Observation(
                id=obs_id(company.ticker, metric.key, tag, start, end, accn, value, channel),
                company=company.name,
                ticker=company.ticker,
                metric=metric.key,
                concept=f"us-gaap:{tag}" if not tag.startswith("sample:") else tag,
                value=value,
                currency_or_unit=unit,
                period_start=start,
                period_end=end,
                period_type=period_type,  # type: ignore[arg-type]
                fiscal_year=end.year,
                fiscal_period=f.get("fp") or f.get("fiscal_period"),
                form=form,
                reporting_basis=f.get("reporting_basis", "consolidated"),
                source_name=f.get("source_name") or f"{source_name_prefix} {form or ''} (accession {accn})".strip(),
                source_url=f.get("source_url") or filing_url(company.cik, accn),
                accession_number=accn,
                published_at=filed,
                retrieved_at=retrieved_at,
                data_status=status,
                retrieval_channel=channel,
                extraction_notes="; ".join(notes),
            )
        )
    return out
