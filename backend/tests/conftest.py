import os

# Isolate every test from the developer's database, memory sidecar and model providers.
os.environ["DATABASE_URL"] = "sqlite:///./test_finsight.db"
os.environ["HMEM_ENABLED"] = "false"
os.environ["LLM_PROVIDER"] = "none"
os.environ["FINSIGHT_DATA_MODE"] = "sample"
# Agent traces go to a throwaway folder, never the repository's logs/.
import tempfile as _tempfile
os.environ["PARALLAX_LOG_DIR"] = _tempfile.mkdtemp(prefix="parallax-trace-")
# A small offline copy of the SEC company directory (same format as company_tickers_exchange.json).
os.environ["FINSIGHT_COMPANY_DIRECTORY"] = os.path.join(os.path.dirname(__file__), "fixtures", "company_tickers_exchange.json")

import asyncio

import pytest

from app.config import Settings
from app.financial_data.companies import METRICS, find_company
from app.financial_data.providers import SampleProvider


def _load(ticker: str):
    provider = SampleProvider(Settings(), apply_amendment=False)
    return asyncio.run(provider.fetch(find_company(ticker), METRICS))


@pytest.fixture(scope="session")
def nwm():
    return _load("NWM")


@pytest.fixture(scope="session")
def csr():
    return _load("CSR")


def pytest_sessionfinish(session, exitstatus):
    try:
        os.remove("test_finsight.db")
    except FileNotFoundError:
        pass
