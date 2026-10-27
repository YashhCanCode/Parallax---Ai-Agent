"""The agent trace: every run writes one JSON line per decision, and the Verifier's loop with Nemotron shows."""
import asyncio
import dataclasses
import json

import httpx
import respx

from app.agents.workflow import Workflow, new_investigation
from app.config import Settings
from app.models.schemas import InvestigationRequest

REQUIRED = {"timestamp", "trace_id", "agent_name", "action", "input_summary", "output_summary", "target_agent",
            "retry_count", "status"}


def test_sample_run_writes_a_full_trace_to_logs_and_the_investigation(tmp_path):
    s = dataclasses.replace(Settings(), log_dir=tmp_path)
    inv = new_investigation(InvestigationRequest(
        question="Was Northwind Motors' 2024 revenue really $13.6 billion?", ticker="NWM", data_mode="sample"), s)
    inv = asyncio.run(Workflow(inv, s).run())

    lines = [json.loads(x) for x in (tmp_path / "runs" / f"{inv.id}.jsonl").read_text().splitlines()]
    assert lines == inv.trace and len(lines) >= 8
    assert all(REQUIRED <= set(e) and e["trace_id"] == inv.id for e in lines)
    steps = [(e["agent_name"], e["action"]) for e in lines]
    for expected in [("Planner", "plan"), ("Retriever", "load_sample"), ("Normalizer", "classify_periods"),
                     ("Reconciler", "reconcile"), ("RiskInvestigator", "run_indicators"),
                     ("Verifier", "check_evidence_links"), ("Orchestrator", "finish")]:
        assert expected in steps
    reconcile = next(e for e in lines if e["action"] == "reconcile")
    assert reconcile["status"] == "claim_contradicted" and "52.40B" in reconcile["output_summary"]
    # No model in tests: the Narrator says the answer is written in code, and the run completes.
    assert any(e["agent_name"] == "Narrator" and e["status"] == "fallback" for e in lines)
    assert lines[-1]["status"] == "completed"


def _answer(summary):
    return json.dumps({"answer": "", "summary": summary, "key_points": [{"text": "Cash lagged.", "finding_ids": ["f1"]}]})


@respx.mock
def test_verifier_sends_a_bad_draft_back_and_accepts_the_retry(tmp_path):
    from app.agents.narrator import Narrator
    from app.models.schemas import Classification, Finding, FindingStatus
    from app.tracing import Tracer

    token = tmp_path / "token"
    token.write_text("rt-test-token")
    f = Finding(id="f1", category="risk", title="Profit rose +22.2% while operating cash flow fell -30.8% in 2024",
                claim="x", classification=Classification.interpretation, status=FindingStatus.supported, severity="elevated")
    respx.get("http://127.0.0.1:8088/v1/models").mock(return_value=httpx.Response(200, json={"data": [{"id": "meterless/auto"}]}))
    reply = lambda text: httpx.Response(200, json={"model": "nvidia/nemotron-test", "choices": [{"message": {"content": text}}]})  # noqa: E731
    respx.post("http://127.0.0.1:8088/v1/chat/completions").mock(side_effect=[
        reply(_answer("Profit rose 99.9% in 2024.")),  # invented number: must be rejected
        reply(_answer("Profit rose 22.2% while cash flow fell 30.8% in 2024.")),
    ])
    n = Narrator(dataclasses.replace(Settings(), llm_provider="auto", meterless_token_file=str(token)))
    asyncio.run(n.select_provider())
    t = Tracer("t-retry", tmp_path)
    summary, call = asyncio.run(n.narrate("Is profit backed by cash?", "Co", [f], trace=t))

    flow = [(e["agent_name"], e["action"], e["status"], e["retry_count"], e["target_agent"]) for e in t.events]
    assert flow == [
        ("Narrator", "draft_answer", "success", 0, "Verifier"),
        ("Verifier", "validate_answer", "needs_revision", 0, "Narrator"),
        ("Narrator", "draft_answer", "success", 1, "Verifier"),
        ("Verifier", "validate_answer", "success", 1, "Orchestrator"),
    ]
    assert "99.9" in t.events[1]["output_summary"] and t.events[0]["model"] == "nvidia/nemotron-test"
    assert call.output_accepted and summary.generated_by == "meterless:nvidia/nemotron-test"


def test_trace_endpoint_returns_the_events():
    import time

    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        inv_id = c.post("/api/investigations", json={"question": "Is Northwind Motors' free cash flow positive?",
                                                     "ticker": "NWM", "data_mode": "sample"}).json()["id"]
        for _ in range(100):
            body = c.get(f"/api/investigations/{inv_id}/trace").json()
            if body["state"] in ("COMPLETED", "NEEDS_MORE_EVIDENCE", "FAILED"):
                break
            time.sleep(0.1)
        assert body["trace_id"] == inv_id and body["state"] == "COMPLETED"
        assert body["events"][-1]["agent_name"] == "Orchestrator"
        assert c.get("/api/investigations/nope/trace").status_code == 404


def test_with_no_filings_the_model_is_not_asked_and_the_answer_says_why(tmp_path, monkeypatch):
    from app.financial_data import providers
    from app.financial_data.providers import FetchResult

    async def nothing(self, company, metrics):
        return FetchResult(channel="sample", limitations=["Live SEC data unavailable: test outage"])

    monkeypatch.setattr(providers.SampleProvider, "fetch", nothing)
    s = dataclasses.replace(Settings(), log_dir=tmp_path)
    inv = new_investigation(InvestigationRequest(question="Is revenue growing?", ticker="NWM", data_mode="sample"), s)
    inv = asyncio.run(Workflow(inv, s).run())
    assert inv.state.value == "NEEDS_MORE_EVIDENCE"
    assert inv.summary.answer.startswith("Parallax couldn't retrieve any filings") and "test outage" in inv.summary.answer
    assert any(e["action"] == "require_evidence" and e["status"] == "blocked" for e in inv.trace)
