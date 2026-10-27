"""Decision Diary with tripwires.

A user records their own decision about a company in their own words, plus tripwires: simple rules
on filed metrics that would change their mind ("cash conversion < 0.8"). Parallax:
- snapshots what was known at decision time (metric values + latest filing),
- writes the decision to Meterless H-MEM, whose append-only ledger proves what was known and when,
- re-evaluates tripwires with deterministic code on every check (and on every watchlist check),
- logs each newly hit tripwire to H-MEM too.
Parallax never makes or suggests the decision.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator

from app.decisions.metrics import SPEC_BY_KEY, compute_metrics, fmt_metric, latest_filing
from app.integrations.meterless.hmem import HmemClient, HmemUnavailable
from app.models.schemas import Observation

DECISION_TYPES = {
    "wait": "I'll wait",
    "research": "I'll research more",
    "comfortable": "I'm comfortable with this",
    "pass": "Not for me",
    "other": "Other",
}


class Tripwire(BaseModel):
    metric: str
    op: Literal["<", ">"]
    threshold: float

    @field_validator("metric")
    @classmethod
    def known(cls, v: str) -> str:
        if v not in SPEC_BY_KEY or not SPEC_BY_KEY[v].tripwire:
            raise ValueError(f"unknown tripwire metric {v}")
        return v

    def describe(self) -> str:
        return f"{SPEC_BY_KEY[self.metric].label} {'below' if self.op == '<' else 'above'} {fmt_metric(self.metric, self.threshold)}"


class DecisionRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=10)
    data_mode: str = Field(default="", pattern="^(|sample|sec_direct|zetaris)$")
    decision_type: Literal["wait", "research", "comfortable", "pass", "other"]
    note: str = Field(default="", max_length=1000)
    tripwires: list[Tripwire] = Field(default_factory=list, max_length=6)
    investigation_id: Optional[str] = Field(default=None, max_length=40)


def evaluate(tripwires: list[Tripwire], metrics: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for t in tripwires:
        m = metrics.get(t.metric)
        value = m.value if m else None
        if value is None:
            state = "unknown"
        else:
            state = "hit" if (value < t.threshold if t.op == "<" else value > t.threshold) else "ok"
        out.append({"metric": t.metric, "op": t.op, "threshold": t.threshold, "describe": t.describe(),
                    "value": value, "value_fmt": fmt_metric(t.metric, value), "period": m.period if m else None,
                    "evidence": m.evidence if m else [], "formula": m.formula if m else "",
                    "note": (m.note if m and value is None else ""), "state": state})
    return out


def snapshot(obs: list[Observation]) -> dict[str, Any]:
    metrics = compute_metrics(obs)
    return {
        "metrics": {k: {"value": v.value, "fmt": fmt_metric(k, v.value), "period": v.period} for k, v in metrics.items()},
        "latest_filing": latest_filing(obs),
        "accessions": sorted({o.accession_number for o in obs if o.accession_number and o.form != "secondary"}),
    }


def then_vs_now(then: dict[str, Any], obs: list[Observation]) -> dict[str, Any]:
    now = snapshot(obs)
    rows = []
    for k, spec in SPEC_BY_KEY.items():
        a, b = then["metrics"].get(k, {}), now["metrics"].get(k, {})
        changed = a.get("value") != b.get("value")
        rows.append({"metric": k, "label": spec.label, "then": a.get("fmt", "n/a"), "now": b.get("fmt", "n/a"),
                     "then_period": a.get("period"), "now_period": b.get("period"), "changed": changed})
    new_filings = sorted(set(now["accessions"]) - set(then.get("accessions", [])))
    return {"rows": rows, "new_filings": new_filings, "latest_filing_then": then.get("latest_filing"),
            "latest_filing_now": now["latest_filing"]}


async def remember_decision(hmem: Optional[HmemClient], decision: dict[str, Any]) -> Optional[str]:
    if hmem is None:
        return None
    trip = "; ".join(t["describe"] for t in decision["tripwires_eval"]) or "no tripwires"
    content = (f"Decision on {decision['ticker']} ({decision['created_at'][:10]}): {DECISION_TYPES[decision['decision_type']]}. "
               f"Note: {decision['note'] or '(none)'}. Tripwires: {trip}.")
    try:
        res = await hmem.write_note(decision["ticker"], content, f"finsight:decision:{decision['id']}", [],
                                    ["decision", f"decision:{decision['id']}"])
        return res.get("memory", {}).get("id")
    except HmemUnavailable:
        return None


async def remember_hits(hmem: Optional[HmemClient], decision: dict[str, Any], hits: list[dict[str, Any]]) -> list[str]:
    ids = []
    if hmem is None:
        return ids
    for h in hits:
        content = (f"Tripwire hit for decision {decision['id']} on {decision['ticker']}: {h['describe']}; "
                   f"now {h['value_fmt']} ({h['period']}).")
        try:
            res = await hmem.write_note(decision["ticker"], content, f"finsight:decision:{decision['id']}", [],
                                        ["tripwire-hit", f"decision:{decision['id']}"])
            if res.get("memory", {}).get("id"):
                ids.append(res["memory"]["id"])
        except HmemUnavailable:
            break
    return ids


def new_decision(req: DecisionRequest, company_name: str, mode_used: str, obs: list[Observation]) -> dict[str, Any]:
    metrics = compute_metrics(obs)
    tev = evaluate(req.tripwires, metrics)
    return {
        "id": "dec-" + uuid.uuid4().hex[:10],
        "ticker": req.ticker.upper(),
        "company": company_name,
        "data_mode": mode_used,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "decision_type": req.decision_type,
        "decision_label": DECISION_TYPES[req.decision_type],
        "note": req.note.strip(),
        "tripwires": [t.model_dump() for t in req.tripwires],
        "tripwires_eval": tev,
        "already_hit_at_creation": [t["describe"] for t in tev if t["state"] == "hit"],
        "investigation_id": req.investigation_id,
        "snapshot": snapshot(obs),
        "memory_id": None,
        "checks": [],
    }


async def check_decision(decision: dict[str, Any], obs: list[Observation], hmem: Optional[HmemClient]) -> dict[str, Any]:
    tripwires = [Tripwire(**t) for t in decision["tripwires"]]
    tev = evaluate(tripwires, compute_metrics(obs))
    previously_hit = {t["describe"] for c in decision.get("checks", []) for t in c["tripwires"] if t["state"] == "hit"}
    previously_hit |= set(decision.get("already_hit_at_creation", []))
    newly_hit = [t for t in tev if t["state"] == "hit" and t["describe"] not in previously_hit]
    memory_ids = await remember_hits(hmem, decision, newly_hit)
    check = {"checked_at": datetime.now(timezone.utc).isoformat(), "tripwires": tev,
             "newly_hit": [t["describe"] for t in newly_hit], "hit_memory_ids": memory_ids,
             "hindsight": then_vs_now(decision["snapshot"], obs)}
    decision["checks"] = (decision.get("checks", []) + [check])[-20:]
    decision["tripwires_eval"] = tev
    return check


def dumps(decision: dict[str, Any]) -> str:
    return json.dumps(decision, default=str)
