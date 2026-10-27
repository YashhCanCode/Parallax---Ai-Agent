#!/usr/bin/env python3
"""Run one example question against a running Parallax backend, print the agent trace, save the output.

    python3 scripts/run_example.py input_examples/example_1.json
    python3 scripts/run_example.py input_examples/example_1.json --save output_examples/example_1_output.json

Needs only the Python standard library. Start the app first (./scripts/dev.sh). PARALLAX_API changes the
backend address (default http://127.0.0.1:8000).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

API = os.environ.get("PARALLAX_API", "http://127.0.0.1:8000").rstrip("/")
DONE = {"COMPLETED", "NEEDS_MORE_EVIDENCE", "FAILED"}


def call(method: str, path: str, body: dict | None = None) -> dict:
    req = urllib.request.Request(API + path, method=method, data=json.dumps(body).encode() if body else None,
                                 headers={"content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def abridge(inv: dict) -> dict:
    """The parts a reader needs: the answer, who wrote it, the evidence, the calls made and the full trace."""
    s = inv.get("summary") or {}
    channels: dict[str, dict] = {}
    for r in inv.get("receipts", []):
        c = channels.setdefault(r["channel"], {"requests": 0, "failed": 0, "rows": 0})
        c["requests"] += 1
        c["failed"] += 0 if r["ok"] else 1
        c["rows"] += r.get("rows") or 0
    return {
        "trace_id": inv["id"],
        "question": inv["question"],
        "company": inv.get("company"),
        "ticker": inv.get("ticker"),
        "data_mode": inv["data_mode"],
        "state": inv["state"],
        "answer": s.get("answer"),
        "answer_by": s.get("answer_by"),
        "written_by": s.get("generated_by"),
        "summary": s.get("text"),
        "key_points": s.get("key_points", []),
        "findings": [{"id": f["id"], "category": f["category"], "status": f["status"], "severity": f["severity"],
                      "title": f["title"]} for f in inv.get("findings", [])],
        "key_figures": [{"label": k["label"], "latest": k["latest"]["display"], "fiscal_year": k["latest"]["fy"],
                         "change": k.get("change_display"), "stale": k.get("stale")}
                        for k in (inv.get("charts") or {}).get("key_figures", []) if k.get("latest")],
        "model_calls": [{k: m.get(k) for k in ("provider", "model", "purpose", "duration_ms", "output_accepted",
                                                "rejection_reason", "usage")} for m in inv.get("model_calls", [])],
        "data_requests": channels,
        "memory": {"recalled": len(inv.get("memory_recalled", [])), "written": len(inv.get("memory_written", [])),
                   "conflicts": len(inv.get("memory_conflicts", []))},
        "limitations": inv.get("limitations", []),
        "trace": inv.get("trace", []),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input", help="a JSON file: {question, ticker?, data_mode?}")
    ap.add_argument("--save", help="write the abridged output JSON here")
    args = ap.parse_args()
    body = json.load(open(args.input))
    try:
        inv_id = call("POST", "/api/investigations", body)["id"]
    except urllib.error.URLError as exc:
        print(f"Cannot reach the backend at {API}: {exc}. Start it with ./scripts/dev.sh", file=sys.stderr)
        return 2
    print(f"trace_id {inv_id}: {body['question']}")
    seen = 0
    for _ in range(600):
        inv = call("GET", f"/api/investigations/{inv_id}")
        for e in inv.get("trace", [])[seen:]:
            arrow = f" -> {e['target_agent']}" if e["target_agent"] else ""
            retry = f" (retry {e['retry_count']})" if e["retry_count"] else ""
            print(f"  {e['agent_name']}.{e['action']}{arrow} [{e['status']}]{retry}: {e['output_summary']}")
        seen = len(inv.get("trace", []))
        if inv["state"] in DONE:
            break
        time.sleep(0.5)
    out = abridge(inv)
    print(f"\n{out['state']}  answer ({out['written_by']}): {out['answer']}")
    if args.save:
        with open(args.save, "w") as fh:
            json.dump(out, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        print(f"saved {args.save}")
    return 0 if out["state"] != "FAILED" else 1


if __name__ == "__main__":
    sys.exit(main())
