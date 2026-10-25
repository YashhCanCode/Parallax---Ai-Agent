import asyncio

import pytest

from app.decisions.diary import DecisionRequest, Tripwire, check_decision, evaluate, new_decision, then_vs_now
from app.decisions.metrics import compute_metrics, fmt_metric


def test_metrics_from_sample_filings(nwm, csr):
    m = compute_metrics(nwm.observations)
    assert m["revenue"].value == 52.4e9 and m["revenue"].period == "FY ending 2024-12-31"
    assert m["revenue_growth"].value == pytest.approx(52.4 / 48.3 - 1)
    assert m["cash_conversion"].value == pytest.approx(2.7 / 4.4)
    assert m["debt_to_ocf"].value == pytest.approx(19.5 / 2.7)
    assert m["current_ratio"].value == pytest.approx(21 / 23)
    assert m["net_margin"].value == pytest.approx(4.4 / 52.4)
    assert m["recent_revisions"].value == 1  # FY2023 revenue revised
    assert m["revenue_decline_streak"].value == 0
    assert all(m[k].evidence for k in ("revenue", "cash_conversion", "debt_to_ocf"))
    c = compute_metrics(csr.observations)
    assert c["long_term_debt"].value is None and c["debt_to_ocf"].value is None and c["long_term_debt"].note


def test_tripwire_states_and_formatting(nwm):
    m = compute_metrics(nwm.observations)
    res = evaluate([Tripwire(metric="cash_conversion", op="<", threshold=0.8),
                    Tripwire(metric="long_term_debt", op=">", threshold=25e9),
                    Tripwire(metric="current_ratio", op="<", threshold=0.5)], m)
    assert [r["state"] for r in res] == ["hit", "ok", "ok"]
    assert res[0]["describe"] == "Cash conversion below 0.80x" and res[0]["evidence"]
    assert fmt_metric("revenue_growth", 0.085) == "+8.5%"
    with pytest.raises(ValueError):
        Tripwire(metric="recent_revisions", op=">", threshold=1)  # informational metric, not a tripwire


def test_unknown_when_data_missing(csr):
    res = evaluate([Tripwire(metric="debt_to_ocf", op=">", threshold=4)], compute_metrics(csr.observations))
    assert res[0]["state"] == "unknown" and res[0]["note"]


def test_decision_snapshot_then_check_reports_new_hit_once(nwm):
    from app.config import Settings
    from app.financial_data.companies import METRICS, find_company
    from app.financial_data.providers import SampleProvider

    req = DecisionRequest(ticker="NWM", decision_type="wait", note="Waiting for cash to recover",
                          tripwires=[Tripwire(metric="revenue", op="<", threshold=52e9)])
    d = new_decision(req, "Northwind Motors (SAMPLE, fictional)", "sample", nwm.observations)
    assert d["tripwires_eval"][0]["state"] == "ok" and d["snapshot"]["metrics"]["revenue"]["fmt"] == "$52.40B"
    amended = asyncio.run(SampleProvider(Settings(), apply_amendment=True).fetch(find_company("NWM"), METRICS)).observations
    c1 = asyncio.run(check_decision(d, amended, None))
    assert c1["newly_hit"] == ["Revenue (latest year) below $52.00B"]
    rows = {r["metric"]: r for r in c1["hindsight"]["rows"]}
    assert rows["revenue"]["then"] == "$52.40B" and rows["revenue"]["now"] == "$51.90B" and rows["revenue"]["changed"]
    assert "SAMPLE-NWM-2025-10KA" in c1["hindsight"]["new_filings"]
    c2 = asyncio.run(check_decision(d, amended, None))
    assert c2["newly_hit"] == []  # reported once, not on every check
    assert then_vs_now(d["snapshot"], nwm.observations)["new_filings"] == []
