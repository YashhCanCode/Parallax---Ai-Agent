import re

from app.explain.glossary import GLOSSARY
from app.explain.plain_language import apply_plain_language, explain
from app.reconciliation.engine import (
    concept_findings,
    consistency_finding,
    fmt_usd,
    revision_findings,
    secondary_source_findings,
)
from app.risk_analysis.indicators import run_risk_indicators


def _all(obs):
    out = [consistency_finding(obs, "revenue")]
    out += revision_findings(obs, "revenue") + concept_findings(obs, "revenue") + secondary_source_findings(obs, "revenue")
    out += run_risk_indicators(obs)
    return [f for f in out if f]


def test_every_finding_gets_plain_language(nwm, csr):
    for obs in (nwm.observations, csr.observations):
        fs = _all(obs)
        apply_plain_language(fs)
        assert fs and all(f.plain_language for f in fs), [f.id for f in fs if not f.plain_language]


def test_plain_language_numbers_come_from_the_finding(nwm):
    for f in _all(nwm.observations):
        text = explain(f)
        allowed = f.title + " " + f.claim + " " + repr(f.calculation_details)
        d = f.calculation_details or {}
        for v in list((d.get("inputs") or {}).values()) + [d.get("debt_to_ocf"), d.get("current_ratio")]:
            if isinstance(v, (int, float)):
                allowed += f" {fmt_usd(v)} {v:.1f} {v:.2f}"
        for g in [d.get("debt_growth_over_window"), *(d.get("growth") or {}).values()]:
            if isinstance(g, (int, float)):
                allowed += f" {abs(g) * 100:.1f}%"
        for num in re.findall(r"\d[\d,]*\.?\d*", text):
            assert num.rstrip(".") in allowed, (f.id, num, text)


def test_specific_explanations(nwm):
    fs = {f.title: explain(f) for f in _all(nwm.observations)}
    assert any("less real cash" in t for k, t in fs.items() if k.startswith("Profit rose"))
    assert any("part of the year" in t for k, t in fs.items() if "news article" in k)
    assert any("before the company updated" in t for k, t in fs.items() if "site B" in k)
    assert any("first reported $48.90B" in t for t in fs.values())


def test_glossary_entries_are_complete():
    terms = [g["term"] for g in GLOSSARY]
    assert len(terms) == len(set(terms)) >= 20
    assert all(g["definition"] and isinstance(g["aliases"], list) for g in GLOSSARY)
