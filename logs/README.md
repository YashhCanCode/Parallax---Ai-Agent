# Agent traces

Every investigation writes one JSON line per agent decision to `logs/runs/<trace_id>.jsonl` (ignored by git) and prints the same events to stdout. `GET /api/investigations/{id}/trace` returns them too.

Each line has `timestamp`, `trace_id`, `agent_name`, `action`, `input_summary`, `output_summary`, `target_agent`, `retry_count` and `status`, plus `model` and `duration_ms` for model calls.

`examples/` holds the traces of the six runs in `output_examples/`:

| File | What to look for |
|---|---|
| `example_1_trace.jsonl` | Reconciler: claim contradicted (a quarter quoted as the full year) |
| `example_2_trace.jsonl` | Verifier `block_advice`: an investment question gets the fixed reply |
| `example_3_trace.jsonl` | Retriever: 18 Zetaris SQL queries, then the SEC cross-check |
| `example_4_trace.jsonl` | No ticker: the company found from its name; a bank's negative cash flow flagged |
| `example_5_trace.jsonl` | Verifier rejects Nemotron's self-calculated ratio twice (`needs_revision`, `rejected`), then `fallback_to_code` |
| `example_6_trace.jsonl` | MemoryKeeper `conflict_detected`: H-MEM catches the revised figures |
