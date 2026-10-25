from app.verification.directions import contradicted_direction
from app.verification.model_output import _ADVICE_RE

TESLA = {"revenue": "down", "net_income": "down", "operating_cash_flow": "up"}
APPLE = {"revenue": "up", "net_income": "up", "operating_cash_flow": "down"}


def test_catches_the_wrong_direction_nemotron_wrote_for_tesla():
    # Found testing frontend-v2: revenue fell -2.9%, but the answer said it grew.
    why = contradicted_direction("Yes, Tesla's revenue grew to $94.83B in FY 2025.", TESLA)
    assert why and why.startswith("described revenue as rising")


def test_accepts_correct_and_mixed_statements():
    assert contradicted_direction("No, Tesla's revenue fell -2.9% to $94.83B in FY 2025.", TESLA) is None
    assert contradicted_direction("Net income rose +19.5% to $112.01B in 2025, but operating cash flow fell -5.7%.", APPLE) is None
    assert contradicted_direction("Profit and cash flow both rose.", APPLE) is None  # two metrics in one clause: not judged
    assert contradicted_direction("Revenue has risen since 2021.", TESLA) is None  # multi-year comparisons are skipped
    assert contradicted_direction("Revenue was $94.83B.", TESLA) is None


def test_operating_cash_flow_is_not_read_as_a_second_metric():
    assert contradicted_direction("Operating cash flow fell in 2025.", APPLE) is None
    assert contradicted_direction("Operating cash flow grew in 2025.", APPLE)


def test_advice_filter_catches_buying_and_recommendations():
    assert _ADVICE_RE.search("FinSight does not recommend buying Tesla stock.")
    assert _ADVICE_RE.search("Consider selling.")
    assert not _ADVICE_RE.search("FinSight doesn't make investment decisions for you.")


def test_yes_no_must_match_the_filings_and_negations_are_not_misread():
    from app.verification.directions import contradicted_yes_no

    assert contradicted_yes_no("Is Tesla's revenue still growing?", "Yes, revenue reached $94.83B.", TESLA)
    assert contradicted_yes_no("Is Tesla's revenue still growing?", "No, revenue fell -2.9%.", TESLA) is None
    assert contradicted_yes_no("Is Apple's revenue falling?", "No, it rose.", APPLE) is None
    # Found testing: "growth is not slowing down" is about a rate, with a negation; it must not be judged.
    assert contradicted_direction("NVIDIA's revenue growth is not slowing down.", {"revenue": "up"}) is None


def test_deterministic_answers_from_verified_findings():
    from app.agents.narrator import deterministic_answer
    from app.models.schemas import Classification, Finding, FindingStatus

    def f(id_, title, severity="info", **calc):
        return Finding(id=id_, category="risk", title=title, claim="c", classification=Classification.calculation,
                       supporting_evidence=[], calculation_details=calc, uncertainty_or_limitations="",
                       why_it_matters="", status=FindingStatus.supported, severity=severity)

    rev = f("risk-rev-2025", "Revenue trend: -2.9% in the latest fiscal year", growth={"FY2024": 0.01, "FY2025": -0.029})
    assert deterministic_answer("Is Tesla's revenue still growing?", [rev]).startswith("No: revenue fell")
    debt = f("risk-debt-x", "Long-term debt $6.58B, +539.8% since 2022", severity="watch")
    assert "Long-term debt $6.58B" in deterministic_answer("What are the warning signs?", [rev, debt])


def test_growth_slowing_question_is_answered_from_the_growth_rates():
    from app.agents.narrator import deterministic_answer
    from app.models.schemas import Classification, Finding, FindingStatus

    rev = Finding(id="risk-rev-2026", category="risk", title="Revenue trend: +65.5% in the latest fiscal year", claim="c",
                  classification=Classification.calculation, supporting_evidence=[], uncertainty_or_limitations="",
                  calculation_details={"growth": {"FY2025": 1.142, "FY2026": 0.655}}, why_it_matters="",
                  status=FindingStatus.supported, severity="info")
    assert deterministic_answer("Is NVIDIA's revenue growth slowing down?", [rev]) == \
        "Yes: revenue growth went from +114.2% to +65.5% in the latest fiscal year, so it slowed."
