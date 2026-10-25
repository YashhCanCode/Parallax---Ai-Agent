"""Watchlist: re-check followed companies and report what changed, using Meterless H-MEM memory.

- New filings: accession numbers not seen at the previous check (none reported on the first check).
- New / confirmed / changed figures: H-MEM's per-fact outcome when FinSight writes this run's figures
  (the same company + metric + period key with a different value is a change, kept in the ledger).
Nothing is reported that the data and memory did not actually produce.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from app.config import Settings
from app.db import WatchlistRow, save_watch_result
from app.financial_data.companies import find_company
from app.financial_data.fetch import fetch_company
from app.integrations.meterless.facts import build_memory_facts, sidecar_payload
from app.integrations.meterless.hmem import HmemClient, HmemUnavailable
from app.reconciliation.engine import is_statement_form


def _value_from_tags(tags: list[str]) -> Optional[float]:
    for t in tags:
        if t.startswith("value:"):
            try:
                return float(t[6:])
            except ValueError:
                return None
    return None


async def check_company(row: WatchlistRow, settings: Settings, hmem: Optional[HmemClient]) -> dict[str, Any]:
    company = find_company(row.ticker)
    checked_at = datetime.now(timezone.utc)
    if company is None:
        return {"ticker": row.ticker, "checked_at": checked_at.isoformat(), "error": "Unsupported company."}
    result, mode_used, notes = await fetch_company(company, row.data_mode, settings)
    obs = result.observations
    report: dict[str, Any] = {
        "ticker": company.ticker, "company": company.name, "checked_at": checked_at.isoformat(),
        "mode_used": mode_used, "data_status": sorted({o.data_status.value for o in obs}),
        "observations": len(obs), "notes": notes, "new_filings": [], "changes": [], "new_figures": [],
        "confirmed": 0, "figures_tracked": 0, "memory": {"available": False}, "baseline": row.accessions is None,
    }
    if not obs:
        report["error"] = "No data could be retrieved, so nothing was compared. " + " ".join(notes)
        return report

    filings: dict[str, dict[str, Any]] = {}
    for o in obs:
        if o.accession_number and o.form != "secondary":
            filings.setdefault(o.accession_number, {
                "accession": o.accession_number, "form": o.form,
                "filed": o.published_at.isoformat() if o.published_at else None, "url": o.source_url,
                "statement": is_statement_form(o)})
    if row.accessions is not None:
        seen = set(json.loads(row.accessions))
        report["new_filings"] = sorted((f for a, f in filings.items() if a not in seen),
                                       key=lambda f: f["filed"] or "", reverse=True)[:10]

    from app.reconciliation.engine import annual_series as _annual, rel_diff as _rd

    rev = _annual(obs, "revenue")[-6:]
    report["spark"] = {"metric": "revenue", "values": [r.current.value for r in rev],
                       "latest": rev[-1].current.value if rev else None, "period": rev[-1].label if rev else None,
                       "yoy": _rd(rev[-1].current.value, rev[-2].current.value) if len(rev) > 1 else None}

    facts = build_memory_facts(company, obs)
    report["figures_tracked"] = len(facts)
    by_key = {f["key"]: f for f in facts}
    if hmem is not None and facts:
        try:
            res = await hmem.write_facts(company.ticker, sidecar_payload(facts))
            report["memory"] = {"available": True}
            for r in res.get("results", []):
                f = by_key.get(r.get("key"), {})
                mem = r.get("memory") or {}
                base = {"key": r.get("key"), "label": f.get("label"), "value": f.get("value"), "form": f.get("form"),
                        "filed": f.get("filed"), "source_url": (f.get("refs") or [None])[0], "memory_id": mem.get("id"),
                        "observation_id": f.get("observation_id")}
                if r.get("outcome") == "confirmed":
                    report["confirmed"] += 1
                elif r.get("outcome") == "new":
                    report["new_figures"].append(base)
                elif r.get("outcome") == "conflict":
                    for c in r.get("conflicts", []):
                        prev = c.get("previous", {})
                        report["changes"].append({**base, "old_value": _value_from_tags(prev.get("tags", [])),
                                                  "old_memory_id": c.get("memoryA"), "old_source": prev.get("source"),
                                                  "resolution": c.get("resolution")})
                elif r.get("outcome") == "rejected":
                    report["notes"].append(f"Memory rejected {r.get('key')}: {r.get('reason')}")
        except HmemUnavailable as exc:
            report["memory"] = {"available": False, "error": str(exc)}
    elif hmem is None:
        report["memory"] = {"available": False, "error": "Meterless H-MEM is disabled (HMEM_ENABLED=false)."}

    # Re-evaluate the user's own tripwires for this company on the same fresh data (deterministic).
    from app.db import list_decisions, save_doc
    from app.decisions.diary import check_decision, dumps

    report["decisions"] = []
    for payload in list_decisions(company.ticker):
        d = json.loads(payload)
        if not d.get("tripwires"):
            continue
        chk = await check_decision(d, obs, hmem)
        save_doc("decision", d["id"], dumps(d), d["ticker"])
        report["decisions"].append({"id": d["id"], "decision_label": d["decision_label"], "note": d["note"],
                                    "created_at": d["created_at"], "newly_hit": chk["newly_hit"],
                                    "tripwires": [{"describe": t["describe"], "state": t["state"], "value_fmt": t["value_fmt"]}
                                                  for t in chk["tripwires"]]})

    save_watch_result(company.ticker, checked_at, json.dumps(sorted(filings)), json.dumps(report))
    return report


async def check_all(rows: list[WatchlistRow], settings: Settings, hmem: Optional[HmemClient]) -> list[dict[str, Any]]:
    return [await check_company(r, settings, hmem) for r in rows]
