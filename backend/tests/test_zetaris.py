"""Zetaris client/provider tests against a mocked HTTP server that follows the response shapes in
Zetaris's official helpers (github.com/zetaris/getting-started). These prove request
construction and parsing; they do not replace a run against a real Zetaris instance."""
import asyncio
import dataclasses
import json

import httpx
import pytest
import respx

from app.config import Settings
from app.financial_data.companies import METRIC_BY_KEY, find_company
from app.financial_data.providers import ZetarisProvider
from app.integrations.zetaris.client import ZetarisClient, ZetarisError, ZetarisNotConfigured, parse_query_response
from app.integrations.zetaris.sql import ViewSpec, rest_table_sql, select_sql, view_sql
from app.reconciliation.engine import channel_cross_check

BASE = "http://zetaris.test:3000"


def settings(**kw):
    base = dict(zetaris_base_url=BASE, zetaris_org_id="7", zetaris_username="u", zetaris_password="p", zetaris_api_key="")
    base.update(kw)
    return dataclasses.replace(Settings(), **base)


def test_parse_object_and_array_rows():
    rows, cols = parse_query_response({"data": [{"PERIOD_END": "2024-12-31", "value_usd": 1}]})
    assert rows == [{"period_end": "2024-12-31", "value_usd": 1}]
    rows, cols = parse_query_response({"headers": [{"name": "A"}, "b"], "data": [[1, 2]]})
    assert rows == [{"a": 1, "b": 2}] and cols == ["a", "b"]
    with pytest.raises(ZetarisError):
        parse_query_response({"rows": []})
    with pytest.raises(ZetarisError):
        parse_query_response({"headers": ["a"], "data": [[1, 2]]})


def test_not_configured():
    c = ZetarisClient(settings(zetaris_org_id="", zetaris_username="", zetaris_password=""))
    assert len(c.configuration_problems()) == 2
    with pytest.raises(ZetarisNotConfigured):
        asyncio.run(c.run_query("SELECT 1"))


@respx.mock
def test_login_then_query_sends_documented_headers():
    login = respx.post(f"{BASE}/api/auth/login").mock(return_value=httpx.Response(200, json={"idToken": "tok.abc"}))
    run = respx.post(f"{BASE}/api/proxy/sql-editor/sqls/run-query").mock(
        return_value=httpx.Response(200, json={"headers": [{"name": "n"}], "data": [[1]]}))
    q = asyncio.run(ZetarisClient(settings()).run_query("SELECT 1"))
    assert q.rows == [{"n": 1}]
    assert json.loads(login.calls[0].request.content) == {"username": "u", "password": "p"}
    req = run.calls[0].request
    assert req.headers["authorization"] == "Bearer tok.abc"
    assert req.headers["x-org-id"] == "7"
    assert len(req.headers["x-request-id"]) == 36
    assert json.loads(req.content) == {"sql": "SELECT 1", "limit": 1000}


@respx.mock
def test_api_key_skips_login_and_html_error_is_explained():
    respx.post(f"{BASE}/api/proxy/sql-editor/sqls/run-query").mock(
        return_value=httpx.Response(404, text="<html></html>", headers={"content-type": "text/html"}))
    with pytest.raises(ZetarisError, match="UI origin"):
        asyncio.run(ZetarisClient(settings(zetaris_api_key="key")).run_query("SELECT 1"))


def test_sql_rendering_matches_recipe_shape():
    tsla = find_company("TSLA")
    rev = ViewSpec(tsla, METRIC_BY_KEY["revenue"], "Revenues")
    assert "CREATE LIGHTNING REST TABLE tsla_revenues_facts FROM FINSIGHT_SEC REQUEST(" in rest_table_sql(rev, "FINSIGHT_SEC", "app a@b.c")
    assert "companyconcept/CIK0001318605/us-gaap/Revenues.json" in rest_table_sql(rev, "FINSIGHT_SEC", "app a@b.c")
    v = view_sql(rev, "FINSIGHT_SEC", "finsight")
    assert "fact.`start` AS period_start" in v and "LATERAL VIEW explode(units.USD) AS fact" in v
    debt = ViewSpec(tsla, METRIC_BY_KEY["long_term_debt"], "LongTermDebt")
    assert "CAST(NULL AS STRING) AS period_start" in view_sql(debt, "FINSIGHT_SEC", "finsight")
    assert select_sql(rev, "finsight").endswith("FROM finsight.tsla_revenues")
    with pytest.raises(ValueError):
        rest_table_sql(rev, "FINSIGHT_SEC", 'bad"agent')


@respx.mock
def test_provider_normalizes_rows_and_cross_check_agrees():
    respx.post(f"{BASE}/api/auth/login").mock(return_value=httpx.Response(200, json={"token": "t"}))
    row = {"cik": 1318605, "entity_name": "Tesla, Inc.", "concept": "Revenues", "period_start": "2024-01-01",
           "period_end": "2024-12-31", "value_usd": 97690000000, "accession_number": "0001628280-25-003063",
           "fiscal_year": 2024, "fiscal_period": "FY", "period_frame": None, "form_type": "10-K", "filed_date": "2025-01-30"}
    respx.post(f"{BASE}/api/proxy/sql-editor/sqls/run-query").mock(return_value=httpx.Response(200, json={"data": [row]}))
    manifest = {"container": "finsight", "views": [{"ticker": "TSLA", "metric": "revenue", "tag": "Revenues"}]}
    p = ZetarisProvider(settings(), manifest=manifest)
    tsla = find_company("TSLA")
    res = asyncio.run(p.fetch(tsla, [METRIC_BY_KEY["revenue"]]))
    assert len(res.observations) == 1
    o = res.observations[0]
    assert o.retrieval_channel == "zetaris" and o.value == 97.69e9 and o.period_type == "annual"
    assert "Zetaris view finsight.tsla_revenues" in o.extraction_notes
    assert res.receipts[0].channel == "zetaris" and res.receipts[0].rows == 1
    f = channel_cross_check(res.raw_counts, {("revenue", "Revenues"): 1}, res.observations, res.observations)
    assert f.status.value == "supported"


def test_database_description_uses_only_characters_zetaris_accepts():
    # Live Zetaris rejects descriptions outside letters, digits, spaces and _ . - , (found against a real instance).
    import re

    from app.integrations.zetaris.sql import database_sql

    desc = re.search(r'DESCRIBE BY "([^"]*)"', database_sql("FINSIGHT_SEC")).group(1)
    assert re.fullmatch(r"[A-Za-z0-9 _.,-]+", desc)


def test_text_valued_rows_are_converted():
    # Live Zetaris returns every value as text, e.g. {"one": "1"}.
    from app.financial_data.companies import METRIC_BY_KEY, find_company
    from app.financial_data.normalize import normalize_facts
    from app.models.schemas import DataStatus

    rows = [{"period_start": None, "period_end": "2024-12-31", "value_usd": "5535000000",
             "accession_number": "0001628280-25-003063", "form_type": "10-K", "filed_date": "2025-01-30"}]
    obs = normalize_facts(rows, company=find_company("TSLA"), metric=METRIC_BY_KEY["long_term_debt"], tag="LongTermDebt",
                          unit="USD", channel="zetaris", status=DataStatus.live)
    assert obs[0].value == 5.535e9 and obs[0].period_type == "instant"


def test_cross_check_treats_unreported_concept_as_agreement():
    # SEC returns 0 rows for a concept the company doesn't report; no Zetaris table exists for it.
    f = channel_cross_check({("revenue", "Revenues"): 1}, {("revenue", "Revenues"): 1, ("current_assets", "AssetsCurrent"): 0}, [], [])
    assert f.calculation_details["rows"] and "0 had different row counts" in f.claim


def test_unreported_metric_gets_an_accurate_limitation():
    manifest = {"container": "finsight", "views": [],
                "no_data": [{"ticker": "F", "tag": "AssetsCurrent"}]}
    res = asyncio.run(ZetarisProvider(settings(zetaris_api_key="k"), manifest=manifest)
                      .fetch(find_company("F"), [METRIC_BY_KEY["current_assets"]]))
    assert "reports none of the tags" in res.limitations[0] and "run scripts" not in res.limitations[0]


def test_every_metric_tag_has_a_zetaris_table_name():
    # A tag without a name crashes on-demand registration (found when adding gross profit and friends).
    from app.financial_data.companies import METRICS
    from app.integrations.zetaris.sql import TAG_SLUGS

    tags = [t for m in METRICS for t in m.tags]
    assert [t for t in tags if t not in TAG_SLUGS] == []
    assert len(set(TAG_SLUGS[t] for t in tags)) == len(tags)  # names are unique
