"""Supported companies and metric definitions.

Live companies mirror the official Zetaris EDGAR recipe
(github.com/zetaris/getting-started, open_data/rest_apis/sql/rate_limited/01_edgar_company_facts_create.sql)
plus Microsoft and NVIDIA. CIKs were checked against the live SEC API.
Sample companies are fictional and exist only in sample_data/.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Company:
    ticker: str
    name: str
    cik: str  # 10-digit, zero padded
    sample: bool = False
    exchange: str = ""
    builtin: bool = True  # False for companies looked up in the SEC directory

    @property
    def table_prefix(self) -> str:
        """Identifier-safe prefix for Zetaris table names (unchanged for the built-in companies)."""
        import re

        p = re.sub(r"[^a-z0-9]", "_", self.ticker.lower())
        return p if p[:1].isalpha() else f"t_{p}"


LIVE_COMPANIES: list[Company] = [
    Company("AAPL", "Apple Inc.", "0000320193"),
    Company("MSFT", "Microsoft Corporation", "0000789019"),
    Company("NVDA", "NVIDIA Corporation", "0001045810"),
    Company("TSLA", "Tesla, Inc.", "0001318605"),
    Company("F", "Ford Motor Company", "0000037996"),
    Company("WMT", "Walmart Inc.", "0000104169"),
    Company("TGT", "Target Corporation", "0000027419"),
    Company("IBM", "International Business Machines Corp", "0000051143"),
    Company("ORCL", "Oracle Corporation", "0001341439"),
]

SAMPLE_COMPANIES: list[Company] = [
    Company("NWM", "Northwind Motors (SAMPLE, fictional)", "SAMPLE-NWM", sample=True),
    Company("CSR", "Contoso Retail (SAMPLE, fictional)", "SAMPLE-CSR", sample=True),
]


@dataclass(frozen=True)
class MetricDef:
    key: str
    label: str
    tags: tuple[str, ...]  # US-GAAP tags in priority order
    kind: str  # "duration" (flow over a period) or "instant" (balance at a date)
    unit: str = "USD"


METRICS: list[MetricDef] = [
    MetricDef(
        "revenue",
        "Revenue",
        ("RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet"),
        "duration",
    ),
    MetricDef("net_income", "Net income", ("NetIncomeLoss",), "duration"),
    MetricDef(
        "operating_cash_flow",
        "Operating cash flow",
        ("NetCashProvidedByUsedInOperatingActivities", "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"),
        "duration",
    ),
    MetricDef("long_term_debt", "Long-term debt", ("LongTermDebtNoncurrent", "LongTermDebt"), "instant"),
    MetricDef("current_assets", "Current assets", ("AssetsCurrent",), "instant"),
    MetricDef("current_liabilities", "Current liabilities", ("LiabilitiesCurrent",), "instant"),
    # Added for wider questions (margins, free cash flow, cash, shareholder returns). All US-GAAP, USD.
    MetricDef("gross_profit", "Gross profit", ("GrossProfit",), "duration"),
    MetricDef("operating_income", "Operating income", ("OperatingIncomeLoss",), "duration"),
    MetricDef("rnd", "R&D spending",
              ("ResearchAndDevelopmentExpense", "ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost"), "duration"),
    MetricDef("capex", "Capital spending",
              ("PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"), "duration"),
    MetricDef("cash", "Cash and equivalents",
              ("CashAndCashEquivalentsAtCarryingValue", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"),
              "instant"),
    MetricDef("buybacks", "Share buybacks", ("PaymentsForRepurchaseOfCommonStock",), "duration"),
    MetricDef("dividends", "Dividends paid", ("PaymentsOfDividends", "PaymentsOfDividendsCommonStock"), "duration"),
]

METRIC_BY_KEY = {m.key: m for m in METRICS}


def all_companies() -> list[Company]:
    return LIVE_COMPANIES + SAMPLE_COMPANIES


def find_company(ticker: str | None, use_directory: bool = True) -> Company | None:
    """Built-in companies first, then any company in the SEC's official ticker directory."""
    if not ticker:
        return None
    t = ticker.upper().strip()
    for c in all_companies():
        if c.ticker == t:
            return c
    if not use_directory:
        return None
    from app.financial_data.directory import DIRECTORY

    e = DIRECTORY.get(t)
    return Company(e.ticker, e.name, e.cik, exchange=e.exchange, builtin=False) if e else None


# Uppercase tokens that look like tickers in finance text but almost never mean one.
_NOT_TICKERS = {"USD", "CEO", "CFO", "COO", "CTO", "GAAP", "EPS", "SEC", "IPO", "AI", "ETF", "FY", "YTD", "TTM",
                "EBITDA", "ROI", "ROE", "IRS", "GDP", "EV", "US", "USA", "UK", "EU", "Q1", "Q2", "Q3", "Q4", "LLC",
                "INC", "NYSE", "NASDAQ", "OTC", "API", "IT", "PE", "YOY", "QOQ", "CAGR"}
_EXPLICIT_TICKER = re.compile(
    r"\$([A-Z][A-Z.\-]{0,6})\b|\(([A-Z][A-Z.\-]{0,6})\)|\b(?:NYSE|NASDAQ|Nasdaq|ticker)[:\s]+([A-Z][A-Z.\-]{0,6})\b")


_ALIASES = {
    "AAPL": ["apple"],
    "MSFT": ["microsoft"],
    "NVDA": ["nvidia"],
    "TSLA": ["tesla"],
    "F": ["ford"],
    "WMT": ["walmart", "wal-mart"],
    "TGT": ["target corp", "target corporation"],
    "IBM": ["ibm", "international business machines"],
    "ORCL": ["oracle"],
    "NWM": ["northwind"],
    "CSR": ["contoso"],
}


def company_mentions(text: str, include_sample: bool = True) -> list[tuple[int, int, Company]]:
    """Every supported company named in the text, with its position (names, then tickers as whole words;
    a one-letter ticker such as F only when written as "$F" or "(F)")."""
    import re

    lowered = text.lower()
    pool = all_companies() if include_sample else LIVE_COMPANIES
    found: list[tuple[int, int, Company]] = []
    for c in pool:
        for alias in _ALIASES.get(c.ticker, []):
            for m in re.finditer(rf"\b{re.escape(alias)}\b", lowered):
                found.append((m.start(), m.end(), c))
        pattern = rf"(\${c.ticker}\b|\({c.ticker}\))" if len(c.ticker) == 1 else rf"\b{c.ticker}\b"
        for m in re.finditer(pattern, text):
            found.append((m.start(), m.end(), c))
    # Any SEC-listed ticker written explicitly: $PLTR, (PLTR), NYSE: PLTR.
    taken = {(a, b) for a, b, _ in found}
    for m in _EXPLICIT_TICKER.finditer(text):
        t = next(g for g in m.groups() if g)
        if t in _NOT_TICKERS or any(a <= m.start() < b for a, b in taken):
            continue
        c = find_company(t)
        if c is not None and (include_sample or not c.sample):
            found.append((m.start(), m.end(), c))
    found.sort(key=lambda x: x[0])
    return found


def match_company_in_text(text: str, include_sample: bool = True) -> Company | None:
    """The first supported company named in the text, or None."""
    hits = company_mentions(text, include_sample)
    return hits[0][2] if hits else None
