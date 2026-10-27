#!/usr/bin/env python3
"""Run one example question through POST /run, print the agent trace and the answer, optionally save the output.

    python3 scripts/run_example.py input_examples/example_1.json
    python3 scripts/run_example.py input_examples/example_1.json --save output_examples/example_1_output.json

The same call with curl:

    curl -X POST http://127.0.0.1:8000/run -H "Content-Type: application/json" -d @input_examples/example_1.json

Needs only the Python standard library. Start the app first (./scripts/dev.sh). PARALLAX_API changes the
backend address (default http://127.0.0.1:8000).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

API = os.environ.get("PARALLAX_API", "http://127.0.0.1:8000").rstrip("/")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input", help="a JSON file: {question, ticker?, data_mode?}")
    ap.add_argument("--save", help="write the output JSON here")
    args = ap.parse_args()
    with open(args.input) as fh:
        body = json.load(fh)
    print(f"POST {API}/run: {body['question']}")
    req = urllib.request.Request(API + "/run", method="POST", data=json.dumps(body).encode(),
                                 headers={"content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=330) as r:
            out = json.loads(r.read())
    except urllib.error.HTTPError as exc:
        print(f"HTTP {exc.code}: {exc.read().decode()[:500]}", file=sys.stderr)
        return 1
    except urllib.error.URLError as exc:
        print(f"Cannot reach the backend at {API}: {exc}. Start it with ./scripts/dev.sh", file=sys.stderr)
        return 2
    print(f"trace_id {out['trace_id']}")
    for e in out["trace"]:
        arrow = f" -> {e['target_agent']}" if e["target_agent"] else ""
        retry = f" (retry {e['retry_count']})" if e["retry_count"] else ""
        model = f" [{e['model']}]" if e.get("model") else ""
        print(f"  {e['agent_name']}.{e['action']}{arrow} [{e['status']}]{retry}{model}: {e['output_summary']}")
    print(f"\n{out['state']}  answer ({out['written_by']}): {out['answer']}")
    if args.save:
        with open(args.save, "w") as fh:
            json.dump(out, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        print(f"saved {args.save}")
    return 0 if out["state"] != "FAILED" else 1


if __name__ == "__main__":
    sys.exit(main())
