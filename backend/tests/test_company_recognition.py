"""Which company a typed question is about. Found in testing: "jp morgan" was answered as Apple."""
import pytest

import app.financial_data.companies as companies
from app.agents.narrator import resolve_named_company
from app.financial_data.companies import match_company_in_text


@pytest.fixture(autouse=True)
def fresh_name_index():
    companies._name_index = None  # built from the test directory fixture
    yield
    companies._name_index = None


@pytest.mark.parametrize("question, ticker", [
    ("tell me about the finances and the growth of jp morgan 2025", "JPM"),  # everyday name, lowercase
    ("How is JPMorgan Chase doing?", "JPM"),
    ("Is Palantir Technologies profitable?", "PLTR"),  # exact SEC name
    ("What about Goldman Sachs revenue", "GS"),
    ("netflix growth", "NFLX"),
    ("Coca-Cola debt", "KO"),
    ("Is Apple's profit backed by cash?", "AAPL"),  # built-in companies still win
])
def test_companies_named_in_words_are_recognized(question, ticker):
    c = match_company_in_text(question)
    assert c is not None and c.ticker == ticker


@pytest.mark.parametrize("question", ["Tell me about growth and finances", "Compare revenue growth", "Show me the risks"])
def test_ordinary_words_are_not_mistaken_for_companies(question):
    assert match_company_in_text(question) is None


def test_the_model_cannot_swap_in_a_company_the_question_does_not_mention():
    q = "tell me about the finances and the growth of jp morgan 2025"
    assert resolve_named_company("AAPL", q) is None  # what happened before the fix
    assert resolve_named_company("Apple", q) is None
    assert resolve_named_company("JPMorgan Chase", q) == "JPM"
    assert resolve_named_company("Meta Platforms", "What is Meta's margin?") == "META"
    assert resolve_named_company("NFLX", "how is NFLX doing") == "NFLX"


def test_sample_mode_flag_forces_sample_data(monkeypatch):
    from app.config import Settings

    monkeypatch.setenv("FINSIGHT_DATA_MODE", "zetaris")
    monkeypatch.setenv("SAMPLE_MODE", "true")
    assert Settings().data_mode == "sample"
    monkeypatch.setenv("SAMPLE_MODE", "false")
    assert Settings().data_mode == "zetaris"
