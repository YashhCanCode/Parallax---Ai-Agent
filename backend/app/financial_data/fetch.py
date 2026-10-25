"""Fetch one company's observations in a requested data mode, with the same honest fallbacks
the investigation workflow uses (Zetaris -> direct SEC, labeled; sample companies only in sample mode)."""
from __future__ import annotations

from typing import Optional

from app.config import Settings
from app.financial_data.companies import METRICS, Company
from app.financial_data.providers import FetchResult, SampleProvider, SecDirectProvider, ZetarisProvider
from app.financial_data.sec_client import SecError
from app.integrations.zetaris.client import ZetarisError


def resolve_mode(company: Company, requested: str) -> str:
    if company.sample:
        return "sample"
    return "sec_direct" if requested == "sample" else requested


async def fetch_company(company: Company, requested_mode: str, settings: Settings,
                        sample_amendment: Optional[bool] = None) -> tuple[FetchResult, str, list[str]]:
    mode = resolve_mode(company, requested_mode)
    notes: list[str] = []
    if mode != requested_mode:
        notes.append(f"{company.ticker} used {mode} mode ({'sample company' if company.sample else 'live company'}).")
    if mode == "zetaris":
        try:
            r = await ZetarisProvider(settings).fetch(company, METRICS)
            if r.observations:
                return r, "zetaris", notes + r.limitations
            notes.append("Zetaris returned no observations; used the direct SEC API instead.")
            notes += r.limitations
        except ZetarisError as exc:
            notes.append(f"Zetaris unavailable ({exc}); used the direct SEC API instead.")
        mode = "sec_direct"
    if mode == "sec_direct":
        try:
            r = await SecDirectProvider(settings).fetch(company, METRICS)
            return r, "sec_direct", notes + r.limitations
        except SecError as exc:
            notes.append(f"Live SEC data unavailable: {exc}")
            return FetchResult(channel="sec_direct"), "sec_direct", notes
    r = await SampleProvider(settings, apply_amendment=sample_amendment).fetch(company, METRICS)
    return r, "sample", notes + r.limitations


async def company_profile(company: Company, settings: Settings) -> Optional[dict]:
    """Industry and exchange from the SEC submissions record (live) or the sample fixture. Never raises."""
    import json

    if company.sample:
        try:
            data = json.loads((settings.sample_dir / "sample_companies.json").read_text())
            prof = data["companies"].get(company.ticker, {}).get("profile")
            return {**prof, "source": "sample fixture"} if prof else None
        except (OSError, ValueError, KeyError):
            return None
    try:
        from app.financial_data.sec_client import SecClient

        r = await SecClient(settings.sec_user_agent, settings.cache_dir).submissions(company.cik)
    except (SecError, ValueError):
        return None
    if r["status"] == "missing":
        return None
    p = r["payload"]
    return {"industry": (p.get("sicDescription") or "").title() or None, "sic": p.get("sic"),
            "exchange": (p.get("exchanges") or [None])[0], "fiscal_year_end": p.get("fiscalYearEnd"),
            "filer_category": p.get("category"), "source": "SEC submissions"}
