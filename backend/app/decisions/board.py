"""Brand-Blind Board: compare 2-3 companies on filed evidence with their names hidden.

Labels (A, B, C) are shuffled server-side. Until the user reveals, the response carries no names,
tickers, filing links or exact dates: revenue is shown as a size band and periods as fiscal years.
Row comparisons are neutral sentences ("A turns $1.40 of every $1 of profit into cash; C turns $0.61"),
never "better/worse". FinSight does not pick for the user.
"""
from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from app.decisions.metrics import SPEC_BY_KEY, MetricValue, compute_metrics, fmt_metric
from app.models.schemas import Observation

LABELS = ["A", "B", "C"]
ROWS = ["revenue", "revenue_growth", "net_margin", "cash_conversion", "debt_to_ocf", "current_ratio",
        "revenue_decline_streak", "recent_revisions"]


def size_band(v: Optional[float]) -> str:
    if v is None:
        return "n/a"
    for limit, label in ((1e9, "Under $1B"), (1e10, "$1B to $10B"), (1e11, "$10B to $100B")):
        if v < limit:
            return label
    return "Over $100B"


def _fy(period: Optional[str]) -> Optional[str]:
    return f"FY{period[-10:-6]}" if period and len(period) >= 10 and period[-10:-6].isdigit() else period


def _sentence(key: str, vals: dict[str, Optional[float]]) -> str:
    have = {k: v for k, v in vals.items() if v is not None}
    missing = [k for k, v in vals.items() if v is None]
    tail = f" No figure for {', '.join(missing)}." if missing else ""
    if len(have) < 2:
        return ("Not enough companies have this figure to compare." + tail).strip()
    hi = max(have, key=lambda k: have[k])
    lo = min(have, key=lambda k: have[k])
    f = lambda k: fmt_metric(key, have[k])  # noqa: E731
    if hi == lo or have[hi] == have[lo]:
        return f"All compared companies show {f(hi)}." + tail
    if key == "cash_conversion":
        return f"{hi} turns ${have[hi]:.2f} of every $1 of profit into operating cash; {lo} turns ${have[lo]:.2f}." + tail
    if key == "debt_to_ocf":
        return (f"{lo} would need {have[lo]:.1f} years of operating cash flow to repay its long-term debt; "
                f"{hi} would need {have[hi]:.1f}.") + tail
    if key == "current_ratio":
        return f"For each $1 due within a year, {hi} holds ${have[hi]:.2f} in short-term assets; {lo} holds ${have[lo]:.2f}." + tail
    if key == "revenue_decline_streak":
        return (f"{hi}'s revenue has fallen {int(have[hi])} year(s) in a row; {lo}'s {int(have[lo])}." if have[hi] else
                "None of the compared companies' revenue fell last year.") + tail
    if key == "recent_revisions":
        return (f"{hi} had {int(have[hi])} recent figure(s) revised by a later filing; {lo} had {int(have[lo])}.") + tail
    if key == "revenue":
        return f"Largest by revenue: {hi}; smallest: {lo}. Size alone says nothing about quality." + tail
    return f"Highest {SPEC_BY_KEY[key].label.lower()}: {hi} ({f(hi)}); lowest: {lo} ({f(lo)})." + tail


def build(entries: list[dict[str, Any]], data_mode: str, prior_pick: Optional[str]) -> dict[str, Any]:
    """entries: [{"company": Company, "observations": [...], "mode_used": str}] -> stored board document."""
    labels = LABELS[: len(entries)]
    order = list(range(len(entries)))
    secrets.SystemRandom().shuffle(order)
    companies: dict[str, dict[str, Any]] = {}
    metrics: dict[str, dict[str, MetricValue]] = {}
    for label, idx in zip(labels, order):
        e = entries[idx]
        obs: list[Observation] = e["observations"]
        m = compute_metrics(obs)
        metrics[label] = m
        by_id = {o.id: o for o in obs}
        companies[label] = {
            "ticker": e["company"].ticker, "name": e["company"].name, "mode_used": e["mode_used"],
            "data_status": sorted({o.data_status.value for o in obs}),
            "evidence": {k: [{"value": by_id[i].value, "form": by_id[i].form,
                              "filed": by_id[i].published_at.isoformat() if by_id[i].published_at else None,
                              "url": by_id[i].source_url, "period_end": by_id[i].period_end.isoformat()}
                             for i in m[k].evidence if i in by_id][:4] for k in ROWS},
            "periods": {k: m[k].period for k in ROWS},
        }
    rows = []
    for key in ROWS:
        spec = SPEC_BY_KEY[key]
        vals = {lab: metrics[lab][key].value for lab in labels}
        have = {k: v for k, v in vals.items() if v is not None}
        cells = {lab: {"fmt": size_band(vals[lab]) if key == "revenue" else fmt_metric(key, vals[lab]),
                       "value": None if key == "revenue" else vals[lab],
                       "period": _fy(metrics[lab][key].period),
                       "note": metrics[lab][key].note if vals[lab] is None else ""} for lab in labels}
        rows.append({"metric": key, "label": spec.label, "description": spec.description, "cells": cells,
                     "highest": max(have, key=lambda k: have[k]) if len(have) > 1 else None,
                     "lowest": min(have, key=lambda k: have[k]) if len(have) > 1 else None,
                     "sentence": _sentence(key, vals)})
    return {"id": "brd-" + uuid.uuid4().hex[:10], "created_at": datetime.now(timezone.utc).isoformat(),
            "data_mode": data_mode, "labels": labels, "rows": rows, "companies": companies,
            "prior_pick": prior_pick, "pick": None, "revealed_at": None}


def public_view(board: dict[str, Any]) -> dict[str, Any]:
    """What the browser may see. Names, tickers and evidence links only after reveal."""
    view = {k: board[k] for k in ("id", "created_at", "data_mode", "labels", "rows", "pick", "revealed_at")}
    view["has_prior_pick"] = bool(board.get("prior_pick"))
    if board.get("revealed_at"):
        view["companies"] = board["companies"]
        view["reflection"] = reflection(board)
    return view


def reflection(board: dict[str, Any]) -> dict[str, Any]:
    pick = board.get("pick")
    picked = board["companies"].get(pick, {}) if pick else {}
    prior = board.get("prior_pick")
    name = (picked.get("name") or "").rstrip(".")  # "Walmart Inc." must not end the sentence as "Inc.."
    if not pick:
        text = "You revealed without choosing. Try choosing on evidence first next time."
    elif not prior:
        text = f"On the evidence alone you chose {pick}, which is {name}."
    elif prior == picked.get("ticker"):
        text = (f"Your first impression ({picked.get('name')}) matched the company you chose on evidence ({pick}). "
                "Your view held up without the name attached.")
    else:
        first = next((c["name"] for c in board["companies"].values() if c["ticker"] == prior), prior)
        text = (f"Before seeing the board you expected {first} to look strongest. On the evidence alone you chose {pick}, "
                f"which is {name}. The name may have been shaping your first impression.")
    return {"pick": pick, "picked_ticker": picked.get("ticker"), "prior_pick": prior, "text": text}
