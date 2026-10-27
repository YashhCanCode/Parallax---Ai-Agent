"""Validation gate for model-written text. Model output is rendered only if it passes.

Checks:
1. Valid JSON matching the expected schema.
2. Every cited finding id exists.
3. Number grounding: every number in the text appears in the evidence the model was given, and a number written
   as a percentage or a multiple ("5.4%", "5.4 times") must appear in the evidence as that kind of figure too, so a
   ratio the model worked out cannot pass by matching an unrelated percentage.
4. No recommendation language (buy/sell/price targets).
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional

from pydantic import BaseModel, ValidationError

_NUM_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")
_ADVICE_RE = re.compile(
    r"\b(buy|buying|sell|selling|strong buy|hold rating|undervalued|overvalued|price target|you should invest|"
    r"guaranteed|recommends?|recommended|recommending|recommendation)\b", re.I
)


_NUM_WORDS = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
              "eleven": 11, "twelve": 12, "twice": 2, "double": 2, "triple": 3}
_NUM_WORD_RE = re.compile(r"\b(" + "|".join(_NUM_WORDS) + r")\b", re.I)


def grounded(n: str, allowed: set[str]) -> bool:
    """1.0 and 1, or 2.50 and 2.5, are the same number."""
    return n in allowed or ("." in n and n.rstrip("0").rstrip(".") in allowed)


def ungrounded_number_words(text: str, evidence_text: str) -> list[str]:
    """Spelled-out numbers ("four consecutive years") must match a digit or the same word in the evidence."""
    allowed = _numbers(evidence_text)
    ev = evidence_text.lower()
    bad = []
    for m in _NUM_WORD_RE.finditer(text):
        w = m.group(1).lower()
        if str(_NUM_WORDS[w]) not in allowed and not re.search(rf"\b{w}\b", ev):
            bad.append(w)
    return bad


class KeyPoint(BaseModel):
    text: str
    finding_ids: list[str]


class NarrativeOutput(BaseModel):
    answer: str = ""
    summary: str
    key_points: list[KeyPoint]


# What a number is, from the characters around it: "22.2%" is a percentage, "5.4x" or "5.4 times" a multiple.
_KIND_RE = re.compile(r"\d[\d,]*(?:\.\d+)?(\s*(?:%|percent\b|per cent\b|points?\b|pp\b)|\s*(?:x\b|×|times\b))?", re.I)


def _kinds(text: str) -> dict[str, set[str]]:
    """Each number in the text, with the kinds it appears as: "percent", "multiple" or "plain"."""
    out: dict[str, set[str]] = {}
    for m in _KIND_RE.finditer(text):
        n = m.group(0)
        suffix = (m.group(1) or "").strip().lower()
        num = _NUM_RE.match(n).group(0).replace(",", "").rstrip(".")
        kind = "plain" if not suffix else ("multiple" if suffix in ("x", "×", "times") else "percent")
        for key in {num, num.rstrip("0").rstrip(".") if "." in num else num}:
            out.setdefault(key, set()).add(kind)
    return out


def mismatched_kinds(text: str, evidence_text: str) -> list[str]:
    """Numbers written as a percentage or multiple that the evidence only has as a different kind of figure."""
    ev = _kinds(evidence_text)
    bad = []
    for n, kinds in _kinds(text).items():
        have = ev.get(n, set())
        for k in kinds - {"plain"}:
            if have and k not in have and "plain" not in have:
                bad.append(f"{n} as a {'multiple' if k == 'multiple' else 'percentage'}")
    return sorted(set(bad))


def _numbers(text: str) -> set[str]:
    out = set()
    for m in _NUM_RE.findall(text):
        n = m.replace(",", "").rstrip(".")
        if not n:
            continue
        out.add(n)
        if "." in n:
            out.add(n.rstrip("0").rstrip("."))
    return out


def validate_narrative(raw: str, finding_ids: set[str], evidence_text: str,
                       directions: Optional[dict[str, str]] = None, question: str = "") -> tuple[Optional[NarrativeOutput], Optional[str]]:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.S)
    if not cleaned.startswith("{") and "{" in cleaned and "}" in cleaned:
        # Some models add a sentence before or after the JSON object; keep only the object itself.
        cleaned = cleaned[cleaned.index("{"): cleaned.rindex("}") + 1]
    try:
        data: Any = json.loads(cleaned)
        out = NarrativeOutput.model_validate(data)
    except (json.JSONDecodeError, ValidationError) as exc:
        return None, f"output was not valid JSON for the required schema ({exc.__class__.__name__})"
    if not out.summary.strip() or len(out.summary) > 2000:
        return None, "summary empty or too long"
    if len(out.answer) > 700:
        return None, "answer too long"
    for kp in out.key_points:
        unknown = [i for i in kp.finding_ids if i not in finding_ids]
        if unknown:
            return None, f"cited unknown finding ids: {unknown[:3]}"
        if not kp.finding_ids:
            return None, "a key point cited no finding"
    allowed = _numbers(evidence_text)
    full_text = out.answer + " " + out.summary + " " + " ".join(k.text for k in out.key_points)
    ungrounded = sorted(n for n in _numbers(full_text) if not grounded(n, allowed))
    if ungrounded:
        return None, f"introduced numbers not present in the evidence: {ungrounded[:5]}"
    mismatched = mismatched_kinds(full_text, evidence_text)
    if mismatched:
        return None, (f"numbers not in the evidence in that form (worked out by the model?): {mismatched[:4]}")
    words = ungrounded_number_words(full_text, evidence_text)
    if words:
        return None, f"used number words not supported by the evidence: {words[:4]}"
    if _ADVICE_RE.search(full_text):
        return None, "contained recommendation language"
    if directions:
        from app.verification.directions import contradicted_direction, contradicted_yes_no
        wrong = contradicted_direction(full_text, directions) or contradicted_yes_no(question, out.answer, directions)
        if wrong:
            return None, wrong
    return out, None
