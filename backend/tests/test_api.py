"""API tests in sample mode (offline). H-MEM is disabled here; the sidecar has its own tests."""
import os
import time

os.environ["DATABASE_URL"] = "sqlite:///./test_finsight.db"
os.environ["HMEM_ENABLED"] = "false"
os.environ["LLM_PROVIDER"] = "none"
os.environ["FINSIGHT_DATA_MODE"] = "sample"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


def test_health_and_companies():
    with TestClient(app) as c:
        assert c.get("/health").json()["status"] == "ok"
        body = c.get("/api/companies").json()
        assert {x["ticker"] for x in body["sample"]} == {"NWM", "CSR"}
        assert any(x["ticker"] == "TSLA" for x in body["live"])


def test_scenarios_endpoint_validates_and_calculates():
    with TestClient(app) as c:
        r = c.post("/api/scenarios/calculate", json={"scenarios": [
            {"name": "A", "initial_amount": 1000, "years": 2, "annual_return_pct": 0}]})
        assert r.status_code == 200 and r.json()["results"][0]["final_nominal"] == 1000
        assert c.post("/api/scenarios/calculate", json={"scenarios": []}).status_code == 422


def test_sample_investigation_end_to_end():
    with TestClient(app) as c:
        r = c.post("/api/investigations", json={"question": "Was Northwind Motors' 2024 revenue really $13.6 billion?"})
        assert r.status_code == 202
        inv_id = r.json()["id"]
        for _ in range(100):
            inv = c.get(f"/api/investigations/{inv_id}").json()
            if inv["state"] in ("COMPLETED", "NEEDS_MORE_EVIDENCE", "FAILED"):
                break
            time.sleep(0.05)
        assert inv["state"] == "COMPLETED", inv.get("error")
        states = [s["state"] for s in inv["steps"]]
        assert states[:6] == ["RECEIVED", "PLANNING", "RETRIEVING", "NORMALIZING", "RECONCILING", "INVESTIGATING_RISKS"]
        assert all(o["data_status"] == "sample" for o in inv["observations"])
        claim = next(f for f in inv["findings"] if f["category"] == "claim_check")
        assert claim["status"] == "contradicted" and "quarterly" in claim["claim"]
        assert inv["summary"]["generated_by"] == "deterministic"
        assert inv["charts"]["source_comparison"]["bars"]


def test_unknown_company_needs_more_evidence():
    with TestClient(app) as c:
        inv_id = c.post("/api/investigations", json={"question": "How is Acme Widgets doing?"}).json()["id"]
        for _ in range(100):
            inv = c.get(f"/api/investigations/{inv_id}").json()
            if inv["state"] not in ("RECEIVED", "PLANNING"):
                break
            time.sleep(0.05)
        assert inv["state"] == "NEEDS_MORE_EVIDENCE"


def test_glossary_and_claims_endpoints():
    with TestClient(app) as c:
        assert len(c.get("/api/glossary").json()) >= 20
        r = c.post("/api/claims/check", json={"text": "Northwind Motors 2024 revenue was $52.4 billion.", "data_mode": "sample"})
        assert r.status_code == 200
        body = r.json()
        assert body["claims"][0]["finding"]["status"] == "supported"
        assert c.post("/api/claims/check", json={"text": "x"}).status_code == 422


def test_watchlist_crud_and_check_without_memory():
    with TestClient(app) as c:
        c.delete("/api/watchlist/CSR")
        assert c.post("/api/watchlist", json={"ticker": "CSR"}).json()["data_mode"] == "sample"
        assert c.post("/api/watchlist", json={"ticker": "ZZZZ"}).status_code == 404
        assert any(w["ticker"] == "CSR" for w in c.get("/api/watchlist").json())
        rep = c.post("/api/watchlist/check", json={"ticker": "CSR"}).json()["reports"][0]
        assert rep["baseline"] is True and rep["memory"]["available"] is False
        assert c.get("/api/watchlist").json()[0]["last_report"]["ticker"] == "CSR"
        assert c.delete("/api/watchlist/CSR").status_code == 200


def test_status_reports_a_state_for_every_integration_even_when_disabled():
    with TestClient(app) as c:
        st = c.get("/api/integrations/status").json()
        assert st["meterless_hmem"]["state"] == "disabled"
        assert all(st[k]["state"] for k in ("zetaris", "meterless_hmem", "meterless_runtime"))


def test_listed_timestamps_carry_a_timezone():
    with TestClient(app) as c:
        c.post("/api/investigations", json={"question": "Was Northwind Motors' 2024 revenue really $13.6 billion?"})
        ts = c.get("/api/investigations").json()[0]["created_at"]
        assert ts.endswith("+00:00") or ts.endswith("Z"), ts
