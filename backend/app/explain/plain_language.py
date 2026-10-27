"""Beginner-friendly 'in plain words' text for each finding.

Templates are deterministic. The only numbers they insert come from the finding's own
calculation_details, formatted with the same formatter the findings use, so a plain-language
line can never contain a figure that is not in the evidence. No model is involved.
"""
from __future__ import annotations

from typing import Any, Optional

from app.models.schemas import Finding, FindingStatus
from app.reconciliation.engine import fmt_usd


def finding_kind(f: Finding) -> str:
    return f.id.rsplit("-", 1)[0]


def _pct(x: Optional[float]) -> str:
    return "an undefined amount" if x is None else f"{abs(x) * 100:.1f}%"


def _num(d: dict[str, Any], *keys: str) -> Optional[float]:
    for k in keys:
        v = d.get(k)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return float(v)
    return None


EXPLANATION_TEXT = {
    "match": "This agrees with the company's official filing.",
    "unit_normalized_match": "This agrees with the official filing once the source's units (for example 'in millions') are converted.",
    "basis": "This source counts only part of the company (for example the parent without its subsidiaries), so a different number is expected. It isn't an error, but it answers a different question.",
    "stale_source": "This source was published before the company updated the figure, so it still shows the old number.",
    "revision": "This matches an older version of the figure that the company later changed.",
    "period_mismatch": "This number covers only part of the year (a quarter or year-to-date), not the full year.",
    "unit_scale": "The number matches if it is read in different units, for example millions instead of dollars.",
    "alternate_concept": "This matches the figure under a different accounting definition, which is why it differs.",
    "other_document": "This matches a figure from a non-financial-statement document, not the official annual or quarterly report.",
    "fiscal_year_offset": "This matches a different year's figure; the year may have been mixed up.",
    "unexplained": "Parallax couldn't find any reason this differs from the official filing. Be careful with this number until you can check where it came from.",
    "no_data": "There isn't enough official data to check this.",
}


def _claim_or_source(f: Finding) -> str:
    d = f.calculation_details or {}
    kind = str(d.get("explanation_kind", ""))
    base = EXPLANATION_TEXT.get(kind, "")
    if finding_kind(f) == "claim":
        if f.status == FindingStatus.supported and kind == "match":
            return "Your number matches the company's official filing."
        if f.status == FindingStatus.contradicted and kind == "unexplained":
            ref = _num(d, "reference_value")
            return ("Your number doesn't match the official filing"
                    + (f", which reports {fmt_usd(ref)}" if ref is not None else "")
                    + ", and no common mix-up (wrong year, quarter instead of year, units, old figure) explains it.")
        if f.status == FindingStatus.contradicted:
            return "Your number isn't right as stated, but the mix-up is understandable: " + base[0].lower() + base[1:]
        return base or "Parallax could not check this number."
    return base


def explain(f: Finding) -> str:
    k = finding_kind(f)
    d = f.calculation_details or {}
    inputs = d.get("inputs") if isinstance(d.get("inputs"), dict) else {}

    if k in ("claim", "src"):
        return _claim_or_source(f)
    if k == "latest":
        if f.status == FindingStatus.supported:
            return "This is the official figure for the company's most recent full year, and every filing that mentions it gives the same number."
        return "Filings give more than one value for the latest year, so check which filing a source used."
    if k == "rev":
        o, n = _num(inputs, "original"), _num(inputs, "latest")
        if o is not None and n is not None:
            return (f"The company first reported {fmt_usd(o)}, then changed it to {fmt_usd(n)} in a later report. "
                    f"A website showing {fmt_usd(o)} may simply be using the older number. The filings don't say why it changed.")
        return "The company changed this number in a later report."
    if k == "concept":
        agree = f.severity == "info"
        return ("The same year's number appears under two accounting labels. "
                + ("They agree, so it doesn't matter which one a website uses." if agree else
                   "They give different numbers, so two websites can both be 'right' and still disagree."))
    if k == "switch":
        return ("The company changed which accounting label it uses for this number. A tool that only reads the old "
                "label would wrongly look as if the data stopped.")
    if k == "doc":
        return ("A different kind of document (such as a proxy statement, written for shareholder votes) shows a slightly "
                "different number. Parallax treats the official annual or quarterly report as the reliable figure.")
    if k == "xcheck":
        return ("Parallax compared the data it received through Zetaris with the SEC's own records"
                + (" and they matched exactly, so nothing was lost or changed." if f.status == FindingStatus.supported
                   else ". They differed, so treat these figures with care until the difference is understood."))
    if k == "mem":
        return "This number changed since Parallax last looked at this company, usually because a newer filing updated it."
    if k == "risk-rev":
        growth = d.get("growth") if isinstance(d.get("growth"), dict) else {}
        vals = [v for v in growth.values() if isinstance(v, (int, float))]
        if vals:
            g = vals[-1]
            direction = "grew" if g >= 0 else "shrank"
            return (f"Sales {direction} by {_pct(g)} in the latest year. One year on its own says little; "
                    "look at whether the trend holds over several years.")
        return "There isn't enough history to show a sales trend."
    if k == "risk-cash":
        ni_g, ocf_g = _num(d, "net_income_growth"), _num(d, "ocf_growth")
        if f.severity in ("watch", "elevated"):
            return ("The company reports rising profit, but less real cash is coming in. That can be harmless (for example "
                    "customers paying later) or an early warning sign. It is worth asking why before relying on the profit figure.")
        if ni_g is not None and ocf_g is not None:
            return ("Profit and the cash the business brings in moved in the same direction last year, so there's no "
                    "profit-versus-cash warning here.")
        return "Parallax couldn't compare profit with cash."
    if k == "risk-cash-missing":
        return "There isn't enough data to compare profit with the cash the business brings in."
    if k == "risk-debt":
        cov = _num(d, "debt_to_ocf")
        g = _num(d, "debt_growth_over_window")
        vals = [v for v in inputs.values() if isinstance(v, (int, float))]
        last = vals[-1] if vals else None
        parts = []
        if last is not None:
            parts.append(f"The company owes {fmt_usd(last)} in long-term debt.")
        if g is not None:
            parts.append(f"That is {'up' if g >= 0 else 'down'} {_pct(g)} over the period shown.")
        if cov is not None:
            parts.append(f"At last year's pace, repaying it would take about {cov:.1f} years of the cash the business brings in.")
        parts.append("Some businesses, such as carmakers with lending arms, carry large debt by design.")
        return " ".join(parts)
    if k == "risk-debt-missing":
        return "No debt figures were found. That doesn't mean the company has no debt; it may report it differently."
    if k == "risk-liq":
        r = _num(d, "current_ratio")
        if r is None:
            return "The current ratio couldn't be calculated."
        return (f"For every $1 the company must pay within a year, it holds about ${r:.2f} in cash and other short-term assets. "
                + ("Below $1 isn't automatically bad; large retailers often run this way." if r < 1 else
                   "Above $1 means short-term bills are covered by short-term assets."))
    if k == "risk-liq-missing":
        return "The company's balance sheet doesn't split short-term and long-term items, so this ratio can't be calculated."
    return ""


def apply_plain_language(findings: list[Finding]) -> None:
    for f in findings:
        if not f.plain_language:
            f.plain_language = explain(f)
