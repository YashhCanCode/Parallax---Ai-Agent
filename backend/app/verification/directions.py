"""Direction check for model-written text: a figure described as rising must have risen in the filings, and vice versa.

The number-grounding check only proves a number exists in the evidence. It cannot see "revenue grew to $94.8B"
when revenue actually fell. This module derives each metric's latest year-over-year direction from the
deterministic risk findings and rejects text whose wording contradicts it.
"""
from __future__ import annotations

import re
from typing import Optional

from app.models.schemas import Finding

_METRICS: list[tuple[str, re.Pattern[str]]] = [
    # Order matters: "operating cash flow" must win over a bare "cash flow".
    ("operating_cash_flow", re.compile(r"\b(operating cash flow|cash flow from operations|ocf|cash flow)\b", re.I)),
    ("net_income", re.compile(r"\b(net income|profits?|earnings|net profit)\b", re.I)),
    ("revenue", re.compile(r"\b(revenues?|sales|top line)\b", re.I)),
    ("long_term_debt", re.compile(r"\b(long-term debt|debt)\b", re.I)),
]
_UP = re.compile(r"\b(grew|grow|grows|growing|rose|risen|rising|increased?|increases|increasing|climbed|higher|expanded|up)\b", re.I)
_DOWN = re.compile(r"\b(fell|fall|falls|falling|fallen|declined?|declines|declining|decreased?|decreases|decreasing|"
                   r"dropped|drops?|shrank|shrinking|lower|down)\b", re.I)
# "since 2022" (multi-year), "not"/"n't" (negation flips meaning), "growth slowing" (a rate, not a level).
_SKIP = re.compile(r"\bsince\b|\bover the (last|past)\b|\bfrom (fy)?\d{4}\b|\bnot\b|n't\b|\bno longer\b|"
                   r"\bgrowth\b|\bslow|\bpace\b|\brate\b|\bdirection\b", re.I)
_CLAUSE = re.compile(r"[.;]|,\s*(?:but|while|whereas|and|yet)?\s*|\s+(?:but|while|whereas)\s+", re.I)


def _last(d: object) -> Optional[float]:
    if isinstance(d, dict):
        vals = [v for v in d.values() if isinstance(v, (int, float))]
        return vals[-1] if vals else None
    return d if isinstance(d, (int, float)) else None


def latest_directions(findings: list[Finding]) -> dict[str, str]:
    """{"revenue": "down", ...} from the risk findings' calculation details (latest fiscal year vs the year before)."""
    out: dict[str, str] = {}

    def put(metric: str, g: Optional[float]) -> None:
        if g is not None and g != 0:
            out[metric] = "up" if g > 0 else "down"

    for f in findings:
        d = f.calculation_details or {}
        if f.id.startswith("risk-rev"):
            put("revenue", _last(d.get("growth")))
        elif f.id.startswith("risk-cash"):
            put("net_income", _last(d.get("net_income_growth")))
            put("operating_cash_flow", _last(d.get("ocf_growth")))
        # Debt is left out on purpose: its finding measures change since the start of a window ("+539.8% since
        # 2022"), so a correct "debt rose since 2022" could disagree with the latest year's direction.
    return out


def contradicted_direction(text: str, directions: dict[str, str]) -> Optional[str]:
    """The first clause that names one metric with a direction word opposite to the filings, else None."""
    for clause in _CLAUSE.split(text or ""):
        if not clause or not clause.strip() or _SKIP.search(clause):
            continue  # multi-year comparisons, negations and growth-rate talk can't be judged by direction alone
        named = []
        rest = clause
        for key, pat in _METRICS:
            if pat.search(rest):
                named.append(key)
                rest = pat.sub(" ", rest)  # so "cash flow" inside "operating cash flow" isn't counted twice
        if len(named) != 1 or named[0] not in directions:
            continue  # zero or several metrics in one clause: too ambiguous to judge
        up, down = bool(_UP.search(clause)), bool(_DOWN.search(clause))
        if up == down:
            continue
        said = "up" if up else "down"
        if said != directions[named[0]]:
            return (f"described {named[0].replace('_', ' ')} as {'rising' if said == 'up' else 'falling'}, "
                    f"but the filings show it {'rose' if directions[named[0]] == 'up' else 'fell'}: \"{clause.strip()[:90]}\"")
    return None


_YES = re.compile(r"^\s*yes\b", re.I)
_NO = re.compile(r"^\s*no\b", re.I)


def contradicted_yes_no(question: str, answer: str, directions: dict[str, str]) -> Optional[str]:
    """ "Is revenue still growing?" answered "Yes" when revenue fell (or "No" when it rose)."""
    q = question or ""
    if _SKIP.search(q) and not re.search(r"\bstill\b", q, re.I):
        return None
    named = [k for k, pat in _METRICS if pat.search(q)]
    if len(named) < 1 or named[0] not in directions:
        return None
    up, down = bool(_UP.search(q)), bool(_DOWN.search(q))
    if up == down:
        return None
    asked = "up" if up else "down"
    says_yes, says_no = bool(_YES.search(answer or "")), bool(_NO.search(answer or ""))
    if not (says_yes or says_no):
        return None
    truth = directions[named[0]] == asked
    if says_yes != truth:
        return (f"answered {'yes' if says_yes else 'no'} to whether {named[0].replace('_', ' ')} "
                f"{'rose' if asked == 'up' else 'fell'}, but the filings show it {'rose' if directions[named[0]] == 'up' else 'fell'}")
    return None
