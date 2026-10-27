"""The structured result of one investigation: the answer, who wrote it, the evidence, the calls made and the trace.

Returned by POST /run and saved by scripts/run_example.py into output_examples/.
"""
from __future__ import annotations

from typing import Any

from app.models.schemas import Investigation


def report(inv: Investigation) -> dict[str, Any]:
    d = inv.model_dump(mode="json")
    s = d.get("summary") or {}
    channels: dict[str, dict[str, int]] = {}
    for r in d.get("receipts", []):
        c = channels.setdefault(r["channel"], {"requests": 0, "failed": 0, "rows": 0})
        c["requests"] += 1
        c["failed"] += 0 if r["ok"] else 1
        c["rows"] += r.get("rows") or 0
    return {
        "trace_id": d["id"],
        "question": d["question"],
        "company": d.get("company"),
        "ticker": d.get("ticker"),
        "data_mode": d["data_mode"],
        "state": d["state"],
        "answer": s.get("answer"),
        "answer_by": s.get("answer_by"),
        "written_by": s.get("generated_by"),
        "summary": s.get("text"),
        "key_points": s.get("key_points", []),
        "findings": [{"id": f["id"], "category": f["category"], "status": f["status"], "severity": f["severity"],
                      "title": f["title"]} for f in d.get("findings", [])],
        "key_figures": [{"label": k["label"], "latest": k["latest"]["display"], "fiscal_year": k["latest"]["fy"],
                         "change": k.get("change_display"), "stale": k.get("stale")}
                        for k in (d.get("charts") or {}).get("key_figures", []) if k.get("latest")],
        "model_calls": [{k: m.get(k) for k in ("provider", "model", "purpose", "duration_ms", "output_accepted",
                                                "rejection_reason", "usage")} for m in d.get("model_calls", [])],
        "data_requests": channels,
        "memory": {"recalled": len(d.get("memory_recalled", [])), "written": len(d.get("memory_written", [])),
                   "conflicts": len(d.get("memory_conflicts", []))},
        "limitations": d.get("limitations", []),
        "error": d.get("error"),
        "trace": d.get("trace", []),
    }
