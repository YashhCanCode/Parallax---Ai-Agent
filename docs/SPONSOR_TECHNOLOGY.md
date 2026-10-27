# Sponsor technology in Parallax

Parallax answers questions about US-listed companies from their SEC filings and shows where every number came from. Each sponsor technology does real work in the submitted build; the evidence for each is linked below.

## Zetaris: the data layer

SEC EDGAR filings are spread across thousands of separate XBRL concept endpoints, one per company per figure. Parallax registers them in Zetaris as `CREATE LIGHTNING REST TABLE` sources with `CREATE SCHEMASTORE VIEW`s, so the agent's Retriever asks one SQL access point for every figure it needs, through Zetaris's `run-query` API.

- A company is registered on its first lookup (`ZETARIS_AUTO_REGISTER`), and figures added later get their own views.
- A view is kept only when Zetaris's row count matches the SEC's own count. So far 143 views across 13 companies are verified, with 0 rejected (`zetaris/registered_views.json`).
- Every investigation cross-checks Zetaris's rows against SEC EDGAR directly. If Zetaris is unavailable or empty, the Retriever falls back to the SEC and the answer says so.
- Every query is logged with its SQL, request ID, rows and timing. Example 3 in the README: 18 Zetaris queries, 3,393 rows, cross-check passed (`logs/examples/example_3_trace.jsonl`).

Code: `backend/app/integrations/zetaris/`, `scripts/zetaris_setup.py`.

## Meterless: H-MEM, the engine we implemented

**What it does in Parallax.** The official H-MEM reference engine runs as a sidecar service (`services/hmem-sidecar/`). It is the agent's memory of what the filings said:

- **Facts with provenance:** every figure Parallax finds is stored with its source filing (accession number). A fact without a source is rejected.
- **Recall:** each investigation starts by recalling what Parallax already knows about the company.
- **Conflicts:** when a later filing changes a figure, H-MEM records a conflict in its append-only trust ledger, and the older memory is kept.

**The features it powers.** Watchlist revision detection (what changed since the last check), Decision Diary tripwires, the "changed since an earlier investigation" finding, and the audit trail behind every memory ID in the app. Example 6 in the README shows H-MEM detecting 2 conflicts after an amended filing: revenue $52.40B → $51.90B.

**Test result.** `cd services/hmem-sidecar && npm test` runs against the real engine, and passes 4 of 4 tests:

1. health names the engine source
2. new fact, re-confirmation, then a conflicting later filing
3. a fact without a source is rejected
4. recall is isolated per company

These tests also run in CI on every push.

## Meterless Nightshift: the AI provider

Nightshift is Parallax's primary and only AI provider. The backend finds the Nightshift runtime on the Mac (`127.0.0.1:8088/v1`) and reads the app's own runtime token automatically, so no key is stored in the project. Every model call (company interpretation, answer writing and the Pre-Mortem) goes through Nightshift's OpenAI-compatible API. The model named in Nightshift's reply is recorded on every call, with its token usage as returned, and shown on every answer: "Written by nvidia/nemotron-3.5-lightning-30b-a3b via Meterless Nightshift". If Nightshift is not running, Parallax still answers, writing each answer in code from the verified facts and labelling it.

Code: `backend/app/integrations/meterless/runtime.py`, `backend/app/agents/narrator.py`.

## NVIDIA: Nemotron through Nightshift

Nightshift routes Parallax's calls to **NVIDIA Nemotron 3.5 Lightning 30B** (`nvidia/nemotron-3.5-lightning-30b-a3b`). The NVIDIA key lives in Nightshift's Providers tab, not in the project. Nemotron has three jobs:

1. **Narrator:** explains each investigation's findings in plain English.
2. **Pre-Mortem:** writes the Skeptic and Defender voices, arguing only from verified findings.
3. **CompanyInterpreter:** names the company when a question has no ticker ("JP Morgan" → JPM).

Nemotron's reasoning is switched off (`chat_template_kwargs.enable_thinking=false`, passed through by Nightshift): about 1 second for a short reply instead of about 17. Every request records which model handled it.

## What was unique about our use

- **A verified data layer, not a pass-through.** Zetaris views are kept only when their row counts match the SEC's, and every run cross-checks them, so the data layer is checked before any figure is used.
- **Memory as evidence, not chat history.** H-MEM holds what each filing said, with its source. Its conflict ledger is what turns "the company revised its numbers" into a visible, auditable event.
- **Nemotron under supervision.** Nemotron explains, but a code Verifier decides what is shown. The Verifier checks citations, every number and its unit, the direction of each change, any yes/no the filings settle, and advice. It can send a draft back with the exact reason, override it, or replace it with a code-written answer. Example 5 in the README shows the Verifier rejecting a ratio Nemotron worked out itself, twice (`logs/examples/example_5_trace.jsonl`).
- **One goal.** All three technologies serve one purpose: showing where every number came from, and catching the common mix-ups (quarter vs year, revised figures, wrong units) in posts and AI answers.
