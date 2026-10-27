import asyncio
import dataclasses

from app.agents.claims_service import check_text
from app.config import Settings
from app.reconciliation.claim_extraction import extract_claims

POST = ("Northwind Motors had a huge 2024: revenue of $13.6 billion and net income of $4.4B. "
        "Its 2023 revenue was $48.9 billion, and margins grew 12%. Some company made $5 billion.")


def test_extracts_each_claim_with_its_metric_and_year():
    ex = extract_claims(POST)
    got = [(c.company.ticker, c.metric, c.value, c.fiscal_year) for c in ex.claims]
    assert got == [("NWM", "revenue", 13.6e9, 2024), ("NWM", "net_income", 4.4e9, 2024), ("NWM", "revenue", 48.9e9, 2023)]
    assert ex.claims[2].company_inferred is True
    reasons = " ".join(s["reason"] for s in ex.skipped)
    assert "Percentages" in reasons


def test_no_company_is_not_checked():
    ex = extract_claims("Revenue was $5 billion in 2024.")
    assert ex.claims == [] and "No supported company" in ex.skipped[0]["reason"]


def test_relative_year_is_flagged():
    ex = extract_claims("Northwind Motors revenue last year was $52.4 billion.")
    assert ex.claims[0].fiscal_year is None and "relative" in ex.claims[0].notes[0]


def test_check_text_in_sample_mode():
    s = dataclasses.replace(Settings(), sample_dir=Settings().sample_dir)
    out = asyncio.run(check_text(POST, "sample", s))
    statuses = [c["finding"]["status"] for c in out["claims"]]
    # 13.6B is a quarter (not the year); 4.4B matches; 48.9B is the pre-revision FY2023 figure.
    assert statuses == ["contradicted", "supported", "contradicted"]
    assert all(c["finding"]["plain_language"] for c in out["claims"])
    assert "part of the year" in out["claims"][0]["finding"]["plain_language"]
    assert out["companies"][0]["mode_used"] == "sample"
    cited = {o["id"] for o in out["observations"]}
    for c in out["claims"]:
        for e in c["finding"]["supporting_evidence"] + c["finding"]["counterevidence"]:
            assert e["observation_id"] in cited


def test_each_amount_goes_to_the_company_named_before_it():
    ex = extract_claims("Tesla's 2024 revenue was $97.7 billion and Apple's 2024 net income hit $93.7 billion. "
                        "It also had $50 billion of cash flow from operations in 2024.")
    got = [(c.company.ticker, c.metric, c.company_inferred) for c in ex.claims]
    assert got == [("TSLA", "revenue", False), ("AAPL", "net_income", False), ("AAPL", "operating_cash_flow", True)]


def test_each_amount_gets_the_year_from_its_own_clause():
    # Found testing frontend-v2: a second company's "$60 billion in 2024" was checked against Tesla's "2025".
    ex = extract_claims("Tesla's revenue was $94.8 billion in 2025 and Apple had revenue of $60 billion in 2024.")
    assert [(c.company.ticker, c.fiscal_year) for c in ex.claims] == [("TSLA", 2025), ("AAPL", 2024)]
    # A year named before another company's clause is not borrowed; with no year of its own the latest FY is used.
    ex = extract_claims("Tesla's 2025 revenue was $94.8 billion and Apple had revenue of $416 billion.")
    assert [(c.company.ticker, c.fiscal_year) for c in ex.claims] == [("TSLA", 2025), ("AAPL", None)]


def test_summary_answers_the_question_and_validates_the_answer():
    from app.agents.narrator import deterministic_answer
    from app.verification.model_output import validate_narrative

    ok = '{"answer": "Yes. Revenue was $5 billion.", "summary": "Revenue was $5 billion.", "key_points": [{"text": "Revenue $5 billion.", "finding_ids": ["f1"]}]}'
    out, why = validate_narrative(ok, {"f1"}, "revenue $5 billion")
    assert why is None and out.answer.startswith("Yes")
    # The answer goes through the same checks: an invented number or advice in it rejects the whole output.
    bad = ok.replace("Yes. Revenue was $5 billion.", "Revenue will reach $9 billion.")
    assert validate_narrative(bad, {"f1"}, "revenue $5 billion")[1].startswith("introduced numbers")
    advice = ok.replace("Yes. Revenue was $5 billion.", "You should buy it.")
    assert validate_narrative(advice, {"f1"}, "revenue $5 billion")[1] == "contained recommendation language"
    assert deterministic_answer("Should I buy Tesla?", []).startswith("Parallax doesn't make investment decisions")
    assert deterministic_answer("How is Tesla doing?", []) == ""
