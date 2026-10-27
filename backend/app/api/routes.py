from __future__ import annotations

import asyncio
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException

from pydantic import BaseModel, Field

from app.agents.claims_service import check_text
from app.decisions.diary import DecisionRequest
from app.agents.watchlist import check_all
from app.agents.workflow import Workflow, new_investigation
from app.db import add_watch, get_state, remove_watch, set_state, utc, watchlist_rows
from app.explain.glossary import GLOSSARY
from app.financial_data.companies import find_company
from app.config import get_settings
from app.db import list_investigations, load_investigation, save_investigation, save_scenario_run
from app.financial_data.companies import LIVE_COMPANIES, SAMPLE_COMPANIES
from app.financial_data.providers import load_zetaris_manifest
from app.integrations.meterless.hmem import HmemClient, HmemUnavailable
from app.integrations.meterless.runtime import MeterlessRuntime, resolve_token
from app.integrations.zetaris.client import ZetarisClient, ZetarisError
from app.models.schemas import Investigation, InvestigationRequest, ScenarioRequest, ScenarioResponse
from app.scenarios.calculator import calculate

router = APIRouter()
_tasks: set[asyncio.Task] = set()
INVESTIGATION_TIMEOUT_S = 300


async def _run(inv: Investigation) -> None:
    wf = Workflow(inv, get_settings())
    try:
        await asyncio.wait_for(wf.run(), timeout=INVESTIGATION_TIMEOUT_S)
    except asyncio.TimeoutError:
        from app.models.schemas import StepState

        inv.state = StepState.FAILED
        inv.error = f"Investigation exceeded {INVESTIGATION_TIMEOUT_S}s and was stopped."
        save_investigation(inv)


@router.post("/api/investigations", response_model=Investigation, status_code=202)
async def start_investigation(req: InvestigationRequest) -> Investigation:
    inv = new_investigation(req, get_settings())
    save_investigation(inv)
    task = asyncio.create_task(_run(inv))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return inv


@router.get("/api/investigations")
async def recent_investigations() -> list[dict[str, Any]]:
    return list_investigations()


@router.get("/api/investigations/{inv_id}", response_model=Investigation)
async def get_investigation(inv_id: str) -> Investigation:
    inv = load_investigation(inv_id)
    if inv is None:
        raise HTTPException(404, "investigation not found")
    return inv


@router.post("/api/scenarios/calculate", response_model=ScenarioResponse)
async def scenarios(req: ScenarioRequest) -> ScenarioResponse:
    resp = calculate(req.scenarios)
    save_scenario_run("scn-" + uuid.uuid4().hex[:12], req.model_dump_json())
    return resp


@router.get("/api/companies")
async def companies() -> dict[str, Any]:
    manifest = load_zetaris_manifest()
    registered = {v["ticker"] for v in manifest.get("views", [])}
    return {
        "live": [{"ticker": c.ticker, "name": c.name, "cik": c.cik, "zetaris_registered": c.ticker in registered}
                 for c in LIVE_COMPANIES],
        "sample": [{"ticker": c.ticker, "name": c.name} for c in SAMPLE_COMPANIES],
        "sample_cases": [
            {"ticker": "NWM", "question": "Was Northwind Motors' 2024 revenue really $13.6 billion?"},
            {"ticker": "NWM", "question": "Is Northwind Motors' profit backed by cash flow?"},
            {"ticker": "CSR", "question": "Does Contoso Retail's revenue match across sources?"},
            {"ticker": "NWM", "question": "If I invest $10,000 for 10 years, what scenarios should I consider?"},
        ],
    }


@router.get("/api/companies/search")
async def search_companies(q: str = "", limit: int = 15) -> dict[str, Any]:
    """Search built-in and SEC-listed companies by ticker or name."""
    from app.financial_data.directory import DIRECTORY

    q = q.strip()[:60]
    limit = max(1, min(limit, 30))
    manifest = load_zetaris_manifest()
    registered = {v["ticker"] for v in manifest.get("views", [])}
    out: list[dict[str, Any]] = []
    if q:
        ql = q.lower()
        for c in LIVE_COMPANIES:
            # Short queries match the start of the ticker or of a word in the name ("n" -> NVIDIA, not "Inc.").
            if c.ticker.lower().startswith(ql) or re.search(rf"\b{re.escape(ql)}", c.name.lower()) \
                    or (len(ql) >= 3 and ql in c.name.lower()):
                out.append({"ticker": c.ticker, "name": c.name, "cik": c.cik, "exchange": "", "builtin": True})
        for e in await asyncio.to_thread(DIRECTORY.search, q, limit):
            if all(x["ticker"] != e.ticker for x in out):
                out.append({"ticker": e.ticker, "name": e.name, "cik": e.cik, "exchange": e.exchange, "builtin": False})
    for x in out:
        x["zetaris_registered"] = x["ticker"] in registered
    return {"results": out[:limit], "directory": {"companies": len(DIRECTORY), "source": DIRECTORY.source,
                                                  "error": DIRECTORY.error}}


@router.get("/api/memory/{memory_id}/audit")
async def memory_audit(memory_id: str) -> dict[str, Any]:
    s = get_settings()
    try:
        return await HmemClient(s.hmem_url).audit(memory_id)
    except HmemUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc


@router.get("/api/integrations/status")
async def integrations_status(deep: bool = False) -> dict[str, Any]:
    """Live status of each integration. `deep=true` also calls Zetaris (lists Lightning databases)."""
    s = get_settings()
    out: dict[str, Any] = {"data_mode": s.data_mode}

    z = ZetarisClient(s)
    problems = z.configuration_problems()
    manifest = load_zetaris_manifest()
    zetaris: dict[str, Any] = {
        "configured": not problems,
        "problems": problems,
        "base_url": s.zetaris_base_url,
        "registered_views": len(manifest.get("views", [])),
        "manifest_created_at": manifest.get("created_at"),
    }
    if deep and not problems:
        try:
            dbs, req_id, ms = await z.list_databases()
            zetaris.update(state="online", lightning_databases=len(dbs), request_id=req_id, duration_ms=ms)
        except ZetarisError as exc:
            zetaris.update(state="error", error=str(exc))
    else:
        zetaris["state"] = "not_configured" if problems else "configured (not probed)"
    out["zetaris"] = zetaris

    hmem: dict[str, Any] = {"url": s.hmem_url, "enabled": s.hmem_enabled, "state": "disabled"}
    if s.hmem_enabled:
        try:
            hmem.update(await HmemClient(s.hmem_url, timeout_s=2).health(), state="online")
        except HmemUnavailable as exc:
            hmem.update(state="offline", error=str(exc))
    out["meterless_hmem"] = hmem

    rt = MeterlessRuntime(s.meterless_base_url, resolve_token(s.meterless_token, s.meterless_token_file),
                          s.meterless_model)
    st = await (rt.auto_detect() if deep else rt.status())
    out["meterless_runtime"] = {"state": st.state, "base_url": st.base_url, "models": st.models[:10],
                                "detail": st.detail, "token_set": bool(rt.token)}
    out["llm_provider"] = s.llm_provider
    out["sec"] = {"user_agent_set": bool(s.sec_user_agent and "@" in s.sec_user_agent)}
    return out


# ---------------------------------------------------------------------------------------
# Glossary, pasted-text claim checks, watchlist
# ---------------------------------------------------------------------------------------

@router.get("/api/glossary")
async def glossary() -> list[dict[str, Any]]:
    return GLOSSARY


class ClaimTextRequest(BaseModel):
    text: str = Field(min_length=3, max_length=8000)
    data_mode: str = Field(default="", pattern="^(|sample|sec_direct|zetaris)$")


@router.post("/api/claims/check")
async def claims_check(req: ClaimTextRequest) -> dict[str, Any]:
    s = get_settings()
    try:
        return await asyncio.wait_for(check_text(req.text, req.data_mode or s.data_mode, s), timeout=180)
    except asyncio.TimeoutError as exc:
        raise HTTPException(504, "Checking took too long; try fewer companies at once.") from exc


class WatchRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=10)
    data_mode: str = Field(default="", pattern="^(|sample|sec_direct|zetaris)$")


class WatchCheckRequest(BaseModel):
    ticker: str | None = None


def _hmem_or_none() -> HmemClient | None:
    s = get_settings()
    return HmemClient(s.hmem_url) if s.hmem_enabled else None


@router.get("/api/watchlist")
async def watchlist() -> list[dict[str, Any]]:
    import json

    out = []
    for r in watchlist_rows():
        c = find_company(r.ticker)
        out.append({"ticker": r.ticker, "name": c.name if c else r.ticker, "data_mode": r.data_mode,
                    "added_at": utc(r.added_at), "last_checked_at": utc(r.last_checked_at),
                    "last_report": json.loads(r.last_report) if r.last_report else None})
    return out


@router.post("/api/watchlist", status_code=201)
async def follow(req: WatchRequest) -> dict[str, Any]:
    c = find_company(req.ticker)
    if c is None:
        raise HTTPException(404, f"{req.ticker} is not a supported company.")
    mode = "sample" if c.sample else (req.data_mode or get_settings().data_mode)
    if mode == "sample" and not c.sample:
        mode = "sec_direct"
    add_watch(c.ticker, mode)
    return {"ticker": c.ticker, "data_mode": mode}


@router.delete("/api/watchlist/{ticker}")
async def unfollow(ticker: str) -> dict[str, Any]:
    if not remove_watch(ticker.upper()):
        raise HTTPException(404, "not on the watchlist")
    return {"removed": ticker.upper()}


@router.post("/api/watchlist/check")
async def watch_check(req: WatchCheckRequest) -> dict[str, Any]:
    rows = [r for r in watchlist_rows() if not req.ticker or r.ticker == req.ticker.upper()]
    if not rows:
        raise HTTPException(404, "Nothing to check: the watchlist is empty.")
    try:
        reports = await asyncio.wait_for(check_all(rows, get_settings(), _hmem_or_none()), timeout=300)
    except asyncio.TimeoutError as exc:
        raise HTTPException(504, "Watchlist check timed out.") from exc
    return {"reports": reports}


@router.get("/api/sample/amendment")
async def sample_amendment_state() -> dict[str, Any]:
    return {"applied": get_state("sample_amendment_applied") == "true",
            "description": "Fictional Northwind Motors 10-K/A and Q1 2025 10-Q (SAMPLE data only)."}


@router.post("/api/sample/amendment")
async def publish_sample_amendment() -> dict[str, Any]:
    """Make the fictional amended filing visible in sample mode. It affects only the fictional NWM company."""
    set_state("sample_amendment_applied", "true")
    return {"applied": True}


@router.delete("/api/sample/amendment")
async def reset_sample_amendment() -> dict[str, Any]:
    """Reset the sample demo so the amendment can be shown again (fictional companies only).

    Hides the fictional amended filing, unfollows NWM, and starts a new memory round for the sample companies
    (see memory_subject). H-MEM is append-only: earlier rounds stay in its ledger; real companies are untouched."""
    set_state("sample_amendment_applied", "false")
    remove_watch("NWM")
    n = int(get_state("sample_demo_round") or 0) + 1
    set_state("sample_demo_round", str(n))
    return {"applied": False, "round": n}


# ---------------------------------------------------------------------------------------
# Decision Diary (tripwires)
# ---------------------------------------------------------------------------------------

async def _company_obs(ticker: str, data_mode: str):
    from app.financial_data.fetch import fetch_company

    c = find_company(ticker)
    if c is None:
        raise HTTPException(404, f"{ticker} is not an SEC-listed or sample company.")
    result, mode_used, notes = await fetch_company(c, data_mode or get_settings().data_mode, get_settings())
    if not result.observations:
        raise HTTPException(502, "No data could be retrieved for this company. " + " ".join(notes))
    return c, result.observations, mode_used, notes


@router.get("/api/tripwire-metrics")
async def tripwire_metrics(ticker: str, data_mode: str = "") -> dict[str, Any]:
    from app.decisions.metrics import SPECS, compute_metrics, fmt_metric

    c, obs, mode_used, notes = await _company_obs(ticker, data_mode)
    m = compute_metrics(obs)
    return {"ticker": c.ticker, "company": c.name, "mode_used": mode_used, "notes": notes,
            "metrics": [{"key": s.key, "label": s.label, "unit": s.unit, "description": s.description,
                         "value": m[s.key].value, "fmt": fmt_metric(s.key, m[s.key].value), "period": m[s.key].period,
                         "note": m[s.key].note} for s in SPECS if s.tripwire]}


@router.post("/api/decisions", status_code=201)
async def create_decision(req: DecisionRequest) -> dict[str, Any]:
    from app.db import save_doc
    from app.decisions.diary import dumps, new_decision, remember_decision

    c, obs, mode_used, _ = await _company_obs(req.ticker, req.data_mode)
    d = new_decision(req, c.name, mode_used, obs)
    d["memory_id"] = await remember_decision(_hmem_or_none(), d)
    save_doc("decision", d["id"], dumps(d), d["ticker"])
    return d


@router.get("/api/decisions")
async def decisions(ticker: str = "") -> list[dict[str, Any]]:
    import json as _json

    from app.db import list_decisions

    return [_json.loads(p) for p in list_decisions(ticker.upper() or None)]


@router.post("/api/decisions/{decision_id}/check")
async def check_decision_now(decision_id: str) -> dict[str, Any]:
    import json as _json

    from app.db import load_doc, save_doc
    from app.decisions.diary import check_decision, dumps

    p = load_doc("decision", decision_id)
    if p is None:
        raise HTTPException(404, "decision not found")
    d = _json.loads(p)
    _, obs, _, _ = await _company_obs(d["ticker"], d["data_mode"])
    check = await check_decision(d, obs, _hmem_or_none())
    save_doc("decision", d["id"], dumps(d), d["ticker"])
    return {"decision": d, "check": check}


@router.post("/api/investigations/{inv_id}/premortem")
async def premortem(inv_id: str) -> dict[str, Any]:
    from app.agents.narrator import Narrator, run_premortem

    inv = load_investigation(inv_id)
    if inv is None:
        raise HTTPException(404, "investigation not found")
    if inv.state.value not in ("COMPLETED", "NEEDS_MORE_EVIDENCE") or not inv.findings:
        raise HTTPException(409, "Run the pre-mortem after an investigation has finished with findings.")
    n = Narrator(get_settings())
    await n.select_provider()
    result, call = await run_premortem(n, inv.company or inv.ticker or "", inv.findings)
    result["created_at"] = datetime.now(timezone.utc).isoformat()
    inv.premortem = result
    if call:
        inv.model_calls.append(call)
    save_investigation(inv)
    return result


# ---------------------------------------------------------------------------------------
# Brand-Blind Board
# ---------------------------------------------------------------------------------------

class BoardRequest(BaseModel):
    tickers: list[str] = Field(min_length=2, max_length=3)
    data_mode: str = Field(default="", pattern="^(|sample|sec_direct|zetaris)$")
    prior_pick: str | None = Field(default=None, max_length=10)


class RevealRequest(BaseModel):
    pick: str | None = Field(default=None, pattern="^[ABC]$")


@router.post("/api/board", status_code=201)
async def create_board(req: BoardRequest) -> dict[str, Any]:
    import json as _json

    from app.db import save_doc
    from app.decisions.board import build, public_view
    from app.financial_data.fetch import fetch_company

    tickers = list(dict.fromkeys(t.upper().strip() for t in req.tickers))
    if len(tickers) < 2:
        raise HTTPException(422, "Choose two or three different companies.")
    mode = req.data_mode or get_settings().data_mode
    entries = []
    for t in tickers:
        c = find_company(t)
        if c is None:
            raise HTTPException(404, f"{t} is not an SEC-listed or sample company.")
        result, mode_used, _ = await fetch_company(c, mode, get_settings())
        if not result.observations:
            raise HTTPException(502, f"No data could be retrieved for {t}.")
        entries.append({"company": c, "observations": result.observations, "mode_used": mode_used})
    prior = req.prior_pick.upper() if req.prior_pick and req.prior_pick.upper() in tickers else None
    board = build(entries, mode, prior)
    save_doc("board", board["id"], _json.dumps(board))
    return public_view(board)


@router.post("/api/board/{board_id}/reveal")
async def reveal_board(board_id: str, req: RevealRequest) -> dict[str, Any]:
    import json as _json

    from app.db import load_doc, save_doc
    from app.decisions.board import public_view, reflection

    p = load_doc("board", board_id)
    if p is None:
        raise HTTPException(404, "board not found")
    board = _json.loads(p)
    if board.get("revealed_at"):
        return public_view(board)
    if req.pick and req.pick not in board["labels"]:
        raise HTTPException(422, "pick must be one of the board's labels")
    board["pick"], board["revealed_at"] = req.pick, datetime.now(timezone.utc).isoformat()
    save_doc("board", board["id"], _json.dumps(board))
    hmem = _hmem_or_none()
    if hmem and req.pick:
        picked = board["companies"][req.pick]
        others = ", ".join(c["ticker"] for lab, c in board["companies"].items() if lab != req.pick)
        try:
            await hmem.write_note(picked["ticker"], f"Brand-blind board {board['id']}: chose {req.pick} ({picked['ticker']}) "
                                  f"on evidence over {others}. {reflection(board)['text']}",
                                  f"finsight:board:{board['id']}", [], ["blind-board"])
        except HmemUnavailable:
            pass
    return public_view(board)
