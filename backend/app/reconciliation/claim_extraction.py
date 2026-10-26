"""Extract every checkable financial claim from pasted text (a post, article or message).

Deterministic: a claim is (company, metric, amount, year) found in one sentence. The company can be
carried over from an earlier sentence (flagged as inferred). Anything ambiguous is reported as
'not checked' with a reason instead of being guessed. Percentages are listed but not checked.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from app.financial_data.companies import Company, company_mentions
from app.reconciliation.claims import _AMOUNT_RE, _SCALE_WORDS, _YEAR_RE, DERIVED, METRIC_PATTERNS

MAX_TEXT = 4000
MAX_CLAIMS = 15
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z$\"'(])|\n+")
_RELATIVE_YEAR = re.compile(r"\b(last|this|past|previous|current) (fiscal )?year\b", re.I)


@dataclass
class ExtractedClaim:
    sentence: str
    company: Optional[Company]
    company_inferred: bool
    metric: Optional[str]
    value: Optional[float]
    value_text: str
    fiscal_year: Optional[int]
    span: tuple[int, int]  # amount position within the sentence
    notes: list[str] = field(default_factory=list)

    @property
    def checkable(self) -> bool:
        return self.company is not None and self.metric is not None and self.value is not None


@dataclass
class Extraction:
    claims: list[ExtractedClaim]
    skipped: list[dict]  # {"sentence", "text", "reason"}
    truncated: bool


def _metric_mentions(sentence: str) -> list[tuple[int, int, str]]:
    lowered = sentence.lower()
    found: list[tuple[int, int, str]] = []
    for key, pattern in METRIC_PATTERNS:
        for m in re.finditer(pattern, lowered):
            if not any(s <= m.start() < e for s, e, _ in found):
                found.append((m.start(), m.end(), key))
    return sorted(found)


def _nearest(items: list[tuple[int, int, object]], start: int, end: int) -> Optional[object]:
    before = [x for x in items if x[1] <= start]
    after = [x for x in items if x[0] >= end]
    if before:
        return before[-1][2]
    if after:
        return after[0][2]
    return None


def _year_for(years: list[tuple[int, int, int]], named: list[tuple[int, int, object]], start: int, end: int) -> Optional[int]:
    """The year a figure refers to. "…$60 billion in 2024" wins outright (a year just after the amount); otherwise
    the nearest year before it, unless another company is named in between (that year belongs to the other
    company's clause, as in "Tesla … in 2025 and Coca-Cola had $60 billion"); otherwise the next year after it."""
    right_after = [y for y in years if 0 <= y[0] - end <= 16]
    if right_after:
        return right_after[0][2]
    before = [y for y in years if y[1] <= start]
    if before:
        y = before[-1]
        if not any(y[1] <= c[0] < start for c in named):
            return y[2]
    after = [y for y in years if y[0] >= end]
    return after[0][2] if after else None


def extract_claims(text: str) -> Extraction:
    truncated = len(text) > MAX_TEXT
    text = text[:MAX_TEXT]
    sentences = [s.strip() for s in _SENT_SPLIT.split(text) if s and s.strip()]
    claims: list[ExtractedClaim] = []
    skipped: list[dict] = []
    last_company: Optional[Company] = None
    for sentence in sentences:
        named = company_mentions(sentence)
        carried = last_company
        mentions = _metric_mentions(sentence)
        years = [(m.start(), m.end(), int(m.group(1))) for m in _YEAR_RE.finditer(sentence)]
        for m in _AMOUNT_RE.finditer(sentence):
            num_txt = m.group("num")
            n = float(num_txt.replace(",", ""))
            scale = (m.group("scale") or "").lower()
            has_cur = bool(m.group("cur"))
            tail = sentence[m.end(): m.end() + 9].lower()
            if tail.lstrip().startswith(("%", "percent")) or sentence[m.end() - 1: m.end()] == "%":
                skipped.append({"sentence": sentence, "text": m.group(0).strip() + "%",
                                "reason": "Percentages and growth rates are not checked yet."})
                continue
            if not scale and not has_cur and "," not in num_txt and (1900 <= n <= 2100 or n < 1000):
                continue  # a year or a small bare number, not an amount
            value_text = m.group(0).strip()
            # The company named nearest before the amount (else after it), else one carried from earlier text.
            hit = _nearest(named, m.start(), m.end())
            company, inferred = (hit, False) if isinstance(hit, Company) else (carried, carried is not None)
            metric = _nearest(mentions, m.start(), m.end())
            year_hit = _year_for(years, named, m.start(), m.end())
            notes: list[str] = []
            if inferred:
                notes.append(f"Company taken from an earlier sentence ({company.name}).")
            if year_hit is None and _RELATIVE_YEAR.search(sentence):
                notes.append(f"'{_RELATIVE_YEAR.search(sentence).group(0)}' is relative; checked against the latest fiscal year.")
            claim = ExtractedClaim(sentence=sentence, company=company, company_inferred=inferred,
                                   metric=metric if isinstance(metric, str) else None,
                                   value=n * _SCALE_WORDS.get(scale, 1.0), value_text=value_text,
                                   fiscal_year=year_hit if isinstance(year_hit, int) else None,
                                   span=(m.start(), m.end()), notes=notes)
            if company is None:
                skipped.append({"sentence": sentence, "text": value_text,
                                "reason": "No supported company is named, so this number can't be checked."})
                continue
            if metric == DERIVED:
                skipped.append({"sentence": sentence, "text": value_text,
                                "reason": "Ratios and computed figures (margins, free cash flow) aren't checked as claims "
                                          "yet; FinSight shows them under Key figures."})
                continue
            if claim.metric is None:
                skipped.append({"sentence": sentence, "text": value_text,
                                "reason": "It isn't clear which figure (revenue, profit, cash flow, debt) this number refers to."})
                continue
            if len(claims) >= MAX_CLAIMS:
                skipped.append({"sentence": sentence, "text": value_text,
                                "reason": f"Only the first {MAX_CLAIMS} claims are checked."})
                continue
            claims.append(claim)
        if named:
            last_company = named[-1][2]
    return Extraction(claims=claims, skipped=skipped, truncated=truncated)
