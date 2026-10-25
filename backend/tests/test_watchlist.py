"""Watchlist change detection against the REAL Meterless H-MEM sidecar (skipped if it isn't set up)."""
import asyncio
import os
import shutil
import socket
import subprocess
import tempfile
import time
from pathlib import Path

import httpx
import pytest

from app.agents.watchlist import check_company
from app.config import Settings
from app.db import add_watch, remove_watch, set_state, watchlist_rows
from app.integrations.meterless.hmem import HmemClient

SIDECAR = Path(__file__).resolve().parents[2] / "services" / "hmem-sidecar"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def hmem_url():
    if not (SIDECAR / "vendor" / "hmem" / "src" / "index.ts").exists() or not shutil.which("node"):
        pytest.skip("H-MEM sidecar not set up (run npm run setup in services/hmem-sidecar)")
    port, state = _free_port(), tempfile.mkdtemp(prefix="hmem-pytest-")
    env = {**os.environ, "HMEM_PORT": str(port), "HMEM_STATE_DIR": state}
    proc = subprocess.Popen(["node", "--import", "tsx", "server.ts"], cwd=SIDECAR, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            if httpx.get(url + "/health", timeout=0.5).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.1)
    else:
        proc.kill()
        pytest.fail("sidecar did not start")
    yield url
    proc.kill()
    shutil.rmtree(state, ignore_errors=True)


def _row(ticker):
    return next(r for r in watchlist_rows() if r.ticker == ticker)


def test_baseline_then_amendment_is_detected(hmem_url):
    set_state("sample_amendment_applied", "false")
    remove_watch("NWM")
    add_watch("NWM", "sample")
    s, hmem = Settings(), HmemClient(hmem_url)

    first = asyncio.run(check_company(_row("NWM"), s, hmem))
    assert first["baseline"] is True and first["memory"]["available"] is True
    assert first["new_filings"] == [] and first["changes"] == []
    assert len(first["new_figures"]) == first["figures_tracked"] > 0

    again = asyncio.run(check_company(_row("NWM"), s, hmem))
    assert again["baseline"] is False and again["changes"] == [] and again["new_filings"] == []
    assert again["confirmed"] == again["figures_tracked"]

    set_state("sample_amendment_applied", "true")
    after = asyncio.run(check_company(_row("NWM"), s, hmem))
    accs = {f["accession"] for f in after["new_filings"]}
    assert accs == {"SAMPLE-NWM-2025-10KA", "SAMPLE-NWM-2025-10Q1"}
    changed = {c["key"]: (c["old_value"], c["value"]) for c in after["changes"]}
    assert changed["NWM:revenue:2024-01-01..2024-12-31"] == (52.4e9, 51.9e9)
    assert changed["NWM:net_income:2024-01-01..2024-12-31"] == (4.4e9, 4.1e9)
    assert all("superseded" in c["resolution"] for c in after["changes"])
    assert any(f["key"] == "NWM:revenue:2025-01-01..2025-03-31" for f in after["new_figures"])

    audit = asyncio.run(hmem.audit(after["changes"][0]["old_memory_id"]))
    actions = [e["action"] for e in audit["history"]]
    assert "conflict_detected" in actions and "conflict_resolved" in actions
    set_state("sample_amendment_applied", "false")
    remove_watch("NWM")


def test_memory_unavailable_is_reported_not_hidden():
    remove_watch("CSR")
    add_watch("CSR", "sample")
    rep = asyncio.run(check_company(_row("CSR"), Settings(), HmemClient("http://127.0.0.1:9", timeout_s=0.5)))
    assert rep["memory"]["available"] is False and "unreachable" in rep["memory"]["error"]
    assert rep["changes"] == [] and rep["figures_tracked"] > 0
    remove_watch("CSR")


def test_watchlist_check_fires_user_tripwire_and_logs_it_in_hmem(hmem_url):
    from app.db import save_doc
    from app.decisions.diary import DecisionRequest, Tripwire, dumps, new_decision, remember_decision
    from app.financial_data.companies import METRICS, find_company
    from app.financial_data.providers import SampleProvider

    set_state("sample_amendment_applied", "false")
    remove_watch("NWM")
    add_watch("NWM", "sample")
    hmem = HmemClient(hmem_url)
    obs = asyncio.run(SampleProvider(Settings(), apply_amendment=False).fetch(find_company("NWM"), METRICS)).observations
    d = new_decision(DecisionRequest(ticker="NWM", decision_type="wait", note="test",
                                     tripwires=[Tripwire(metric="net_income", op="<", threshold=4.2e9)]),
                     "Northwind", "sample", obs)
    d["memory_id"] = asyncio.run(remember_decision(hmem, d))
    assert d["memory_id"]
    save_doc("decision", d["id"], dumps(d), "NWM")
    asyncio.run(check_company(_row("NWM"), Settings(), hmem))  # baseline, no hit
    set_state("sample_amendment_applied", "true")
    rep = asyncio.run(check_company(_row("NWM"), Settings(), hmem))
    mine = next(x for x in rep["decisions"] if x["id"] == d["id"])
    assert mine["newly_hit"] == ["Net income (latest year) below $4.20B"]
    hist = asyncio.run(hmem.audit(d["memory_id"]))
    assert hist["memory"]["content"].startswith("Decision on NWM") and hist["history"][0]["action"] == "create"
    recall = asyncio.run(hmem.recall("NWM", "tripwire hit decision net income"))
    assert any("Tripwire hit" in m["memory"]["content"] for m in recall["memories"])
    set_state("sample_amendment_applied", "false")
    remove_watch("NWM")
