"""Check every claim found in a pasted text against filings."""
from __future__ import annotations

from typing import Any

from app.config import Settings
from app.explain.plain_language import apply_plain_language
from app.financial_data.fetch import fetch_company
from app.models.schemas import Observation
from app.reconciliation.claim_check import build_claim_finding
from app.reconciliation.claim_extraction import extract_claims


async def check_text(text: str, data_mode: str, settings: Settings) -> dict[str, Any]:
    extraction = extract_claims(text)
    by_ticker: dict[str, Any] = {}
    companies: list[dict[str, Any]] = []
    notes: list[str] = []
    for c in extraction.claims:
        t = c.company.ticker  # type: ignore[union-attr]
        if t in by_ticker:
            continue
        result, mode_used, fetch_notes = await fetch_company(c.company, data_mode, settings)  # type: ignore[arg-type]
        by_ticker[t] = result
        statuses = sorted({o.data_status.value for o in result.observations})
        companies.append({"ticker": t, "name": c.company.name, "mode_used": mode_used,  # type: ignore[union-attr]
                          "data_status": statuses, "observations": len(result.observations),
                          "queries": len(result.receipts)})
        notes += fetch_notes

    results: list[dict[str, Any]] = []
    cited: dict[str, Observation] = {}
    for i, c in enumerate(extraction.claims):
        obs = by_ticker[c.company.ticker].observations  # type: ignore[union-attr]
        finding = build_claim_finding(obs, c.metric, c.value, c.value_text, c.fiscal_year,  # type: ignore[arg-type]
                                      extra_limit=" ".join(c.notes), id_salt=f"{i}:{c.sentence}")
        apply_plain_language([finding])
        by_id = {o.id: o for o in obs}
        for e in finding.supporting_evidence + finding.counterevidence:
            if e.observation_id in by_id:
                cited[e.observation_id] = by_id[e.observation_id]
        results.append({
            "sentence": c.sentence,
            "span": list(c.span),
            "ticker": c.company.ticker,  # type: ignore[union-attr]
            "company": c.company.name,  # type: ignore[union-attr]
            "company_inferred": c.company_inferred,
            "metric": c.metric,
            "value": c.value,
            "value_text": c.value_text,
            "fiscal_year": c.fiscal_year,
            "notes": c.notes,
            "finding": finding.model_dump(mode="json"),
        })
    counts: dict[str, int] = {}
    for r in results:
        counts[r["finding"]["status"]] = counts.get(r["finding"]["status"], 0) + 1
    return {
        "claims": results,
        "not_checked": extraction.skipped,
        "truncated": extraction.truncated,
        "companies": companies,
        "counts": counts,
        "observations": [o.model_dump(mode="json") for o in cited.values()],
        "notes": sorted(set(notes)),
    }
