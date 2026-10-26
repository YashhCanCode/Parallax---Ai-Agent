import asyncio
import dataclasses
import json

import httpx
import respx

from app.config import Settings
from app.financial_data.companies import METRICS, company_mentions, find_company
from app.financial_data.directory import DIRECTORY
from app.financial_data.providers import ZetarisProvider
from app.integrations.zetaris.registry import merge_manifest

ZBASE = "http://zetaris.test:3000"


def test_any_sec_listed_ticker_is_a_company():
    c = find_company("pltr")
    assert c and c.name == "Palantir Technologies Inc." and c.cik == "0001321655" and not c.builtin
    assert find_company("BRK-B").table_prefix == "brk_b"
    assert find_company("AAPL").builtin and find_company("AAPL").name == "Apple Inc."  # built-in wins
    assert find_company("NOPE") is None


def test_directory_search_ranks_ticker_then_name_and_prefers_major_exchanges():
    tickers = [e.ticker for e in DIRECTORY.search("PLT")]
    assert tickers[:2] == ["PLTR", "PLTX"]
    assert [e.ticker for e in DIRECTORY.search("alphabet")] == ["GOOG", "GOOGL"]
    assert DIRECTORY.search("") == []


def test_one_letter_search_matches_word_starts_only():
    from fastapi.testclient import TestClient

    from app.main import app

    res = TestClient(app).get("/api/companies/search", params={"q": "n"}).json()["results"]
    tickers = [r["ticker"] for r in res]
    assert "NVDA" in tickers and "AAPL" not in tickers  # "Apple Inc." contains an "n" but no word starts with it
    for e in DIRECTORY.search("N"):
        assert e.ticker.startswith("N") or any(w.startswith("N") for w in e.name.upper().replace(",", " ").split())


def test_explicit_tickers_in_text_but_not_common_words():
    hits = [(c.ticker) for _, _, c in company_mentions("$PLTR revenue (USD) beat Apple, and (GOOGL) too.")]
    assert hits == ["PLTR", "AAPL", "GOOGL"]


def test_merge_manifest_replaces_only_probed_pairs():
    prev = {"lightning_db": "DB", "container": "c", "views": [
        {"ticker": "AAPL", "metric": "revenue", "tag": "Revenues", "view": "aapl_revenues", "zetaris_rows": 1, "sec_rows": 1}],
        "no_data": [], "rejected": []}
    new = {"ticker": "PLTR", "metric": "revenue", "tag": "Revenues", "view": "pltr_revenues", "zetaris_rows": 2, "sec_rows": 2}
    out = merge_manifest(prev, db="DB", container="c", base_url="x", probed=[("PLTR", "Revenues")],
                         verified=[new], rejected=[], no_data=[])
    assert {v["ticker"] for v in out["views"]} == {"AAPL", "PLTR"}


@respx.mock
def test_on_demand_registration_verifies_and_rejects_by_row_count(tmp_path):
    s = dataclasses.replace(Settings(), zetaris_base_url=ZBASE, zetaris_org_id="1", zetaris_api_key="k",
                            sec_user_agent="finsight-test test@example.com", cache_dir=tmp_path)
    facts = {"Revenues": [{"start": "2024-01-01", "end": "2024-12-31", "val": 2.87e9, "accn": "A-1", "form": "10-K", "filed": "2025-02-18"},
                          {"start": "2023-01-01", "end": "2023-12-31", "val": 2.23e9, "accn": "A-1", "form": "10-K", "filed": "2025-02-18"}],
             "NetIncomeLoss": [{"start": "2024-01-01", "end": "2024-12-31", "val": 4.6e8, "accn": "A-1", "form": "10-K", "filed": "2025-02-18"}]}

    def sec(request):
        tag = request.url.path.rsplit("/", 1)[-1].removesuffix(".json")
        if tag in facts:
            return httpx.Response(200, json={"units": {"USD": facts[tag]}})
        return httpx.Response(404)

    respx.get(url__regex=r"https://data\.sec\.gov/api/xbrl/companyconcept/CIK0001321655/us-gaap/.*").mock(side_effect=sec)
    sent = []

    def zetaris(request):
        sql = json.loads(request.content)["sql"]
        sent.append(sql)
        if sql.startswith("SELECT") and "pltr_revenues" in sql:
            rows = [{"period_start": f["start"], "period_end": f["end"], "value_usd": str(f["val"]), "accession_number": f["accn"],
                     "form_type": f["form"], "filed_date": f["filed"]} for f in facts["Revenues"]]
            return httpx.Response(200, json={"data": rows, "headers": []})
        if sql.startswith("SELECT") and "pltr_net_income" in sql:
            return httpx.Response(200, json={"data": [], "headers": []})  # count mismatch: 0 vs SEC 1
        return httpx.Response(200, json={"data": [], "headers": []})

    respx.post(f"{ZBASE}/api/proxy/sql-editor/sqls/run-query").mock(side_effect=zetaris)
    p = ZetarisProvider(s, manifest={"container": "finsight", "views": []}, auto_register=True)
    res = asyncio.run(p.fetch(find_company("PLTR"), METRICS))

    creates = [q for q in sent if q.startswith("CREATE LIGHTNING REST TABLE")]
    assert {c.split()[4] for c in creates} == {"pltr_revenues_facts", "pltr_net_income_facts"}
    assert all("CIK0001321655" in c for c in creates)
    assert {o.metric for o in res.observations} == {"revenue"} and len(res.observations) == 2
    assert all(o.retrieval_channel == "zetaris" for o in res.observations)
    assert any("returned 0 rows but SEC has 1" in l for l in res.limitations)
    assert any("Registered PLTR in Zetaris on demand" in e for e in res.events)
    assert any("Verified 1 new Zetaris view" in e for e in res.events)


@respx.mock
def test_empty_companyconcept_falls_back_to_companyfacts_and_is_labeled(tmp_path):
    from app.financial_data.companies import METRIC_BY_KEY
    from app.financial_data.providers import SecDirectProvider

    s = dataclasses.replace(Settings(), sec_user_agent="finsight-test test@example.com", cache_dir=tmp_path)
    row = {"start": "2025-01-01", "end": "2025-12-31", "val": 4.794e10, "accn": "A-9", "form": "10-K", "filed": "2026-02-20"}
    respx.get("https://data.sec.gov/api/xbrl/companyconcept/CIK0001321655/us-gaap/Revenues.json").mock(
        return_value=httpx.Response(200, json={"tag": "Revenues", "units": {"USD": {}}}))  # SEC-side empty object
    respx.get(url__regex=r".*/companyconcept/CIK0001321655/us-gaap/(?!Revenues\.json).*").mock(return_value=httpx.Response(404))
    respx.get("https://data.sec.gov/api/xbrl/companyfacts/CIK0001321655.json").mock(
        return_value=httpx.Response(200, json={"facts": {"us-gaap": {"Revenues": {"units": {"USD": [row]}}}}}))
    res = asyncio.run(SecDirectProvider(s).fetch(find_company("PLTR"), [METRIC_BY_KEY["revenue"]]))
    assert len(res.observations) == 1 and res.observations[0].value == 4.794e10
    assert "companyfacts" in res.observations[0].extraction_notes
    assert any(r.error and "used SEC companyfacts" in r.error for r in res.receipts)


@respx.mock
def test_registration_skips_concepts_whose_companyconcept_is_empty(tmp_path):
    from app.integrations.zetaris.client import ZetarisClient
    from app.integrations.zetaris.registry import register_company

    s = dataclasses.replace(Settings(), zetaris_base_url=ZBASE, zetaris_org_id="1", zetaris_api_key="k",
                            sec_user_agent="finsight-test test@example.com", cache_dir=tmp_path)
    row = {"start": "2025-01-01", "end": "2025-12-31", "val": 1.0e9, "accn": "A-9", "form": "10-K", "filed": "2026-02-20"}
    respx.get("https://data.sec.gov/api/xbrl/companyconcept/CIK0001321655/us-gaap/NetIncomeLoss.json").mock(
        return_value=httpx.Response(200, json={"units": {"USD": {}}}))
    respx.get(url__regex=r".*/companyconcept/CIK0001321655/us-gaap/(?!NetIncomeLoss\.json).*").mock(return_value=httpx.Response(404))
    respx.get("https://data.sec.gov/api/xbrl/companyfacts/CIK0001321655.json").mock(
        return_value=httpx.Response(200, json={"facts": {"us-gaap": {"NetIncomeLoss": {"units": {"USD": [row]}}}}}))
    sent = []
    respx.post(f"{ZBASE}/api/proxy/sql-editor/sqls/run-query").mock(
        side_effect=lambda r: sent.append(json.loads(r.content)["sql"]) or httpx.Response(200, json={"data": []}))
    reg = asyncio.run(register_company(find_company("PLTR"), s, ZetarisClient(s)))
    assert [v["tag"] for v in reg.api_empty] == ["NetIncomeLoss"]
    assert "NetIncomeLoss" not in {v["tag"] for v in reg.no_data}
    assert not any("CREATE LIGHTNING REST TABLE" in q for q in sent)  # nothing registered for an empty endpoint


def _pltr_known_manifest() -> dict:
    # PLTR registered before gross profit existed in FinSight: a revenue view, and the rest probed as no-data.
    from app.financial_data.companies import METRIC_BY_KEY
    old = ("revenue", "net_income", "operating_cash_flow", "long_term_debt", "current_assets", "current_liabilities")
    return {"container": "finsight",
            "views": [{"ticker": "PLTR", "metric": "revenue", "tag": "Revenues", "view": "pltr_revenues"}],
            "no_data": [{"ticker": "PLTR", "metric": k, "tag": t} for k in old for t in METRIC_BY_KEY[k].tags if t != "Revenues"]}


@respx.mock
def test_known_company_registers_only_figures_added_later(tmp_path):
    from app.financial_data.companies import METRIC_BY_KEY

    s = dataclasses.replace(Settings(), zetaris_base_url=ZBASE, zetaris_org_id="1", zetaris_api_key="k",
                            sec_user_agent="finsight-test test@example.com", cache_dir=tmp_path)
    gp = [{"start": "2024-01-01", "end": "2024-12-31", "val": 2.3e9, "accn": "A-1", "form": "10-K", "filed": "2025-02-18"}]
    respx.get(url__regex=r".*/companyconcept/CIK0001321655/us-gaap/GrossProfit\.json").mock(
        return_value=httpx.Response(200, json={"units": {"USD": gp}}))
    respx.get(url__regex=r".*/companyconcept/CIK0001321655/us-gaap/(?!GrossProfit\.json).*").mock(return_value=httpx.Response(404))
    sent = []

    def zetaris(request):
        sql = json.loads(request.content)["sql"]
        sent.append(sql)
        if sql.startswith("SELECT") and "gross" in sql:
            return httpx.Response(200, json={"data": [{"period_start": "2024-01-01", "period_end": "2024-12-31", "value_usd": "2300000000",
                                                       "accession_number": "A-1", "form_type": "10-K", "filed_date": "2025-02-18"}], "headers": []})
        return httpx.Response(200, json={"data": [], "headers": []})

    respx.post(f"{ZBASE}/api/proxy/sql-editor/sqls/run-query").mock(side_effect=zetaris)
    p = ZetarisProvider(s, manifest=_pltr_known_manifest(), auto_register=True)
    res = asyncio.run(p.fetch(find_company("PLTR"), [METRIC_BY_KEY["revenue"], METRIC_BY_KEY["gross_profit"]]))
    creates = [q for q in sent if q.startswith("CREATE LIGHTNING REST TABLE")]
    assert len(creates) == 1 and "GrossProfit" in creates[0]  # the existing revenue view is not recreated
    assert [o.value for o in res.observations if o.metric == "gross_profit"] == [2.3e9]
    assert all(o.retrieval_channel == "zetaris" for o in res.observations)


@respx.mock
def test_figure_without_a_zetaris_view_comes_from_sec_and_is_labeled(tmp_path):
    from app.financial_data.companies import METRIC_BY_KEY

    s = dataclasses.replace(Settings(), zetaris_base_url=ZBASE, zetaris_org_id="1", zetaris_api_key="k",
                            sec_user_agent="finsight-test test@example.com", cache_dir=tmp_path)
    gp = [{"start": "2024-01-01", "end": "2024-12-31", "val": 2.3e9, "accn": "A-1", "form": "10-K", "filed": "2025-02-18"}]
    respx.get(url__regex=r".*/companyconcept/CIK0001321655/us-gaap/GrossProfit\.json").mock(
        return_value=httpx.Response(200, json={"units": {"USD": gp}}))
    respx.get(url__regex=r".*/companyconcept/CIK0001321655/us-gaap/(?!GrossProfit\.json).*").mock(return_value=httpx.Response(404))
    respx.post(f"{ZBASE}/api/proxy/sql-editor/sqls/run-query").mock(return_value=httpx.Response(200, json={"data": [], "headers": []}))
    p = ZetarisProvider(s, manifest=_pltr_known_manifest(), auto_register=False)
    res = asyncio.run(p.fetch(find_company("PLTR"), [METRIC_BY_KEY["gross_profit"]]))
    assert [(o.value, o.retrieval_channel) for o in res.observations] == [(2.3e9, "sec_direct")]
    assert any(l.startswith("Not via Zetaris: gross profit for PLTR") for l in res.limitations)
