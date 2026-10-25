"""Deterministic parsing of a user's question / financial claim.

Extracts: metric, fiscal year, an asserted value (with its unit word), and question intent.
No model is involved, so the numbers that get checked are exactly the numbers the user typed.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

METRIC_PATTERNS: list[tuple[str, str]] = [
    ("operating_cash_flow", r"operating cash ?flow|cash (?:flow )?from operations|\bocf\b"),
    ("net_income", r"net income|net profit|\bprofits?\b|\bearnings\b|net loss"),
    ("revenue", r"revenues?|\bsales\b|top[- ]line|turnover"),
    ("long_term_debt", r"long[- ]term debt|\bdebt\b|borrowings"),
    ("current_assets", r"current assets"),
    ("current_liabilities", r"current liabilities"),
]

_SCALE_WORDS = {
    "trillion": 1e12, "tn": 1e12, "t": 1e12,
    "billion": 1e9, "bn": 1e9, "b": 1e9, "bil": 1e9,
    "million": 1e6, "mn": 1e6, "m": 1e6, "mil": 1e6, "mm": 1e6,
    "thousand": 1e3, "k": 1e3,
}

_AMOUNT_RE = re.compile(
    r"(?P<cur>\$|usd\s?)?\s*(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)\s*"
    r"(?P<scale>trillion|billion|million|thousand|bn|tn|mn|mm|bil|mil|[tbmk])?\b",
    re.IGNORECASE,
)
_YEAR_RE = re.compile(r"\b(?:fy\s?|fiscal\s(?:year\s)?)?((?:19|20)\d{2})\b", re.IGNORECASE)


@dataclass
class ParsedQuestion:
    metric: Optional[str]
    fiscal_year: Optional[int]
    claimed_value: Optional[float]
    claimed_text: Optional[str]
    scale_word: Optional[str]
    wants_risk: bool
    wants_scenario: bool
    is_claim: bool


def parse_question(text: str) -> ParsedQuestion:
    lowered = text.lower()
    mentions: list[tuple[int, int, str]] = []  # (start, end, metric)
    for key, pattern in METRIC_PATTERNS:
        for m in re.finditer(pattern, lowered):
            if not any(s <= m.start() < e for s, e, _ in mentions):  # "operating cash flow" beats "cash flow"
                mentions.append((m.start(), m.end(), key))
    mentions.sort()
    metric = mentions[0][2] if mentions else None

    years = [int(m.group(1)) for m in _YEAR_RE.finditer(text)]
    fiscal_year = years[-1] if years else None

    claimed_value = claimed_text = scale_word = None
    for m in _AMOUNT_RE.finditer(text):
        num_txt = m.group("num")
        n = float(num_txt.replace(",", ""))
        scale = (m.group("scale") or "").lower()
        has_cur = bool(m.group("cur"))
        # Skip bare years and small bare numbers that are not amounts.
        if not scale and not has_cur and "," not in num_txt:
            if 1900 <= n <= 2100 or n < 1000:
                continue
        claimed_value = n * _SCALE_WORDS.get(scale, 1.0)
        claimed_text = m.group(0).strip()
        scale_word = scale or None
        # The claim is about the metric named closest before the amount (else the nearest after it).
        before = [k for s, e, k in mentions if e <= m.start()]
        after = [k for s, e, k in mentions if s >= m.end()]
        if before:
            metric = before[-1]
        elif after:
            metric = after[0]
        break

    wants_risk = bool(re.search(r"risk|warning|red flag|concern|safe|healthy|debt|cash ?flow|liquidity", lowered))
    wants_scenario = bool(re.search(r"invest|scenario|what if|return|retire|compound|contribut", lowered))
    return ParsedQuestion(
        metric=metric,
        fiscal_year=fiscal_year,
        claimed_value=claimed_value,
        claimed_text=claimed_text,
        scale_word=scale_word,
        wants_risk=wants_risk,
        wants_scenario=wants_scenario,
        is_claim=claimed_value is not None,
    )
