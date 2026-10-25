"""Zetaris view registry: the manifest of verified views, and on-demand registration of a company.

On-demand registration uses exactly the statements scripts/zetaris_setup.py uses (Zetaris's EDGAR
recipe pattern). A newly created view is only recorded as verified when the rows Zetaris returns
match the SEC's row count for that concept, the same rule the setup script applies.
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from app.config import REPO_ROOT, Settings
from app.financial_data.companies import METRICS, Company
from app.financial_data.sec_client import SecClient
from app.integrations.zetaris.client import ZetarisClient, ZetarisError
from app.integrations.zetaris.sql import ViewSpec, container_sql, database_sql, rest_table_sql, view_sql
from app.models.schemas import QueryReceipt

MANIFEST = REPO_ROOT / "zetaris" / "registered_views.json"
_FIELDS = ("ticker", "metric", "tag", "view", "zetaris_rows", "sec_rows")
_locks: dict[str, asyncio.Lock] = {}
_file_lock = asyncio.Lock()


def load_manifest(path: Path = MANIFEST) -> dict[str, Any]:
    return json.loads(path.read_text()) if path.exists() else {"views": []}


def merge_manifest(previous: dict[str, Any], *, db: str, container: str, base_url: str,
                   probed: Iterable[tuple[str, str]], verified: list[dict[str, Any]],
                   rejected: list[dict[str, Any]], no_data: list[dict[str, Any]],
                   api_empty: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Replace entries for the (ticker, tag) pairs probed now; keep everything else."""
    now = datetime.now(timezone.utc).isoformat()
    same = previous.get("lightning_db") == db and previous.get("container") == container
    probed = set(probed)

    def keep(key: str) -> list[dict[str, Any]]:
        return [v for v in previous.get(key, []) if same and (v["ticker"], v["tag"]) not in probed]

    order = lambda v: (v["ticker"], v["metric"], v["tag"])  # noqa: E731
    return {
        "created_at": previous.get("created_at", now) if same else now,
        "updated_at": now,
        "zetaris_base_url": base_url,
        "lightning_db": db,
        "container": container,
        "views": sorted(keep("views") + [{**{k: v[k] for k in _FIELDS}, "verified_at": now} for v in verified], key=order),
        "rejected": keep("rejected") + rejected,
        "no_data": sorted(keep("no_data") + [{**v, "checked_at": now} for v in no_data], key=order),
        # SEC's companyconcept endpoint returns no rows although companyfacts has data: not registered in
        # Zetaris (its REST table would be empty); FinSight reads these from SEC companyfacts directly.
        "concept_api_empty": sorted(keep("concept_api_empty") + [{**v, "checked_at": now} for v in (api_empty or [])],
                                    key=order),
    }


async def save_merged(settings: Settings, **kwargs: Any) -> dict[str, Any]:  # noqa: D401
    async with _file_lock:
        merged = merge_manifest(load_manifest(), db=settings.zetaris_lightning_db,
                                container=settings.zetaris_container, base_url=settings.zetaris_base_url, **kwargs)
        MANIFEST.parent.mkdir(parents=True, exist_ok=True)
        MANIFEST.write_text(json.dumps(merged, indent=2) + "\n")
        return merged


@dataclass
class Registration:
    pending: dict[str, int] = field(default_factory=dict)  # tag -> SEC row count, created but not yet verified
    no_data: list[dict[str, Any]] = field(default_factory=list)
    api_empty: list[dict[str, Any]] = field(default_factory=list)
    receipts: list[QueryReceipt] = field(default_factory=list)
    events: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


async def _run(z: ZetarisClient, sql: str, reg: Registration, tolerate_exists: bool = True) -> bool:
    started = datetime.now(timezone.utc)
    try:
        q = await z.run_query(sql, limit=1)
        reg.receipts.append(QueryReceipt(channel="zetaris", target=sql, started_at=started, duration_ms=q.duration_ms,
                                         ok=True, request_id=q.request_id))
        return True
    except ZetarisError as exc:
        exists = tolerate_exists and "exist" in str(exc).lower()
        reg.receipts.append(QueryReceipt(channel="zetaris", target=sql, started_at=started, duration_ms=0, ok=exists,
                                         error="already exists" if exists else str(exc)[:300]))
        if not exists:
            reg.errors.append(str(exc)[:300])
        return exists


async def register_company(company: Company, settings: Settings, z: ZetarisClient) -> Registration:
    """Create Zetaris REST tables + views for every concept the company reports (probed via SEC first)."""
    reg = Registration()
    ua = settings.sec_user_agent
    if not ua or "@" not in ua:
        reg.errors.append("SEC_USER_AGENT must be set ('app_name contact@email') to register SEC sources in Zetaris.")
        return reg
    lock = _locks.setdefault(company.ticker, asyncio.Lock())
    async with lock:
        sec = SecClient(ua, settings.cache_dir)
        specs = [ViewSpec(company, m, t) for m in METRICS for t in m.tags]
        counts: dict[str, int] = {}
        for sp in specs:
            r = await sec.concept_rows(company.cik, sp.tag)
            entry = {"ticker": company.ticker, "metric": sp.metric.key, "tag": sp.tag}
            if r.get("fallback") == "companyfacts":
                counts[sp.tag] = 0
                reg.api_empty.append({**entry, "companyfacts_rows": len(r["rows"])})
            else:
                counts[sp.tag] = len(r["rows"])
                if not r["rows"]:
                    reg.no_data.append(entry)
        present = [sp for sp in specs if counts[sp.tag] > 0]
        if reg.api_empty:
            reg.events.append(f"SEC's companyconcept endpoint returns no rows for {len(reg.api_empty)} concept(s) that "
                              f"companyfacts has; those are read from SEC directly, not registered in Zetaris.")
        if not present:
            reg.events.append(f"{company.name} reports none of FinSight's concepts; nothing to register in Zetaris.")
            return reg
        db, container = settings.zetaris_lightning_db, settings.zetaris_container
        await _run(z, database_sql(db), reg)
        await _run(z, container_sql(container), reg)
        for sp in present:
            if await _run(z, rest_table_sql(sp, db, ua), reg) and await _run(z, view_sql(sp, db, container), reg):
                reg.pending[sp.tag] = counts[sp.tag]
        reg.events.append(f"Registered {company.ticker} in Zetaris on demand: {len(reg.pending)} of {len(present)} "
                          f"concepts created ({len(reg.no_data)} not reported by the company"
                          + (f", {len(reg.api_empty)} unavailable from SEC's per-concept endpoint" if reg.api_empty else "")
                          + ").")
    return reg
