"""Agent trace: one JSON line per decision, so a run can be followed from the logs alone.

Each investigation writes `logs/runs/<trace_id>.jsonl` (PARALLAX_LOG_DIR changes the folder) and prints the
same events to stdout. Events record what really happened: which role acted, what it decided, which role it
handed to, how many retries it took and whether the step succeeded, was rejected or fell back.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger("parallax.trace")

# The roles inside the Parallax agent. Two of them call NVIDIA Nemotron through Meterless Nightshift;
# the rest are code, so their decisions are repeatable.
ROLES = {
    "Planner": "reads the question, finds the company, plans the steps (code)",
    "CompanyInterpreter": "names the company when the question has no ticker (Nemotron via Nightshift)",
    "MemoryKeeper": "recalls and stores figures in Meterless H-MEM; reports conflicts",
    "Retriever": "queries SEC filings through Zetaris, falls back to SEC EDGAR directly (code)",
    "Normalizer": "classifies periods, units and concepts (code)",
    "Reconciler": "picks the figure of record, finds revisions, checks claims (code)",
    "RiskInvestigator": "runs a bounded set of risk indicators (code)",
    "Narrator": "explains the findings in plain words (Nemotron via Nightshift)",
    "Verifier": "checks every AI output: citations, numbers, direction, yes/no, advice; can reject or override",
    "Orchestrator": "runs the steps and returns the result",
}


def _summary(value: Any, limit: int = 300) -> str:
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    return text if len(text) <= limit else text[: limit - 1] + "…"


class Tracer:
    def __init__(self, trace_id: str, log_dir: Optional[Path], events: Optional[list[dict[str, Any]]] = None):
        self.trace_id = trace_id
        # Pass an investigation's own list to add to it (it is saved with the investigation).
        self.events: list[dict[str, Any]] = events if events is not None else []
        self.path: Optional[Path] = None
        if log_dir is not None:
            try:
                (log_dir / "runs").mkdir(parents=True, exist_ok=True)
                self.path = log_dir / "runs" / f"{trace_id}.jsonl"
            except OSError as exc:  # a read-only disk must not stop an investigation
                log.warning("trace file disabled: %s", exc)

    def emit(self, agent: str, action: str, input_summary: Any, output_summary: Any, *, target: str = "",
             status: str = "success", retry_count: int = 0, **extra: Any) -> dict[str, Any]:
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "trace_id": self.trace_id,
            "agent_name": agent,
            "action": action,
            "input_summary": _summary(input_summary),
            "output_summary": _summary(output_summary),
            "target_agent": target,
            "retry_count": retry_count,
            "status": status,
            **{k: v for k, v in extra.items() if v is not None},
        }
        self.events.append(event)
        line = json.dumps(event, ensure_ascii=False)
        if self.path is not None:
            try:
                with self.path.open("a", encoding="utf-8") as fh:
                    fh.write(line + "\n")
            except OSError as exc:
                log.warning("could not write trace: %s", exc)
        arrow = f" -> {target}" if target else ""
        log.info("[%s] %s.%s%s [%s] %s", self.trace_id, agent, action, arrow, status, event["output_summary"])
        return event
