# FinSight AI

**Understand the facts. Investigate the risks. Explore the possibilities.**

FinSight AI is an agentic financial research workspace for beginner investors. Ask about a listed company, or paste a claim such as *"Was Tesla's 2024 revenue $97.7 billion?"*. FinSight then runs a full investigation:

- pulls SEC EDGAR XBRL facts, either through **Zetaris** or directly
- reconciles figures across filings, accounting concepts and sources
- explains each difference only when a documented cause reproduces it exactly
- checks a small set of risk indicators, listing evidence and counterevidence
- runs a transparent scenario calculator
- remembers what it learned in **Meterless H-MEM**, with an audit ledger

It is an educational tool. It does not rate securities, predict markets or give financial advice.

### What you can do in the app

| Tab | What it does |
|---|---|
| **Investigate a company** | Full evidence-backed investigation of one company or one claim, with charts, risk indicators, sources, memory and an integration trail. |
| **Check a post** | Paste a tweet, article or message. FinSight finds every financial claim (company + figure + amount + year), checks each one against filings, and explains any mix-up in plain words. Numbers it can't check are listed with the reason. |
| **Watchlist** | Follow companies. Each check fetches fresh data and asks Meterless H-MEM what is new, re-confirmed or **changed** since last time, plus any new filings. Click a memory id to see its ledger. In sample mode, "Publish fictional amended filing" demonstrates a detected change honestly. Set `WATCHLIST_CHECK_MINUTES` to check on a schedule. |
| **Blind board** | Compare 2–3 companies on their filings **with the names hidden**. Labels are shuffled on the server, and names, tickers and filing links aren't sent until you reveal. Revenue is shown as a size band. You choose which to look into, then reveal; if you recorded a first impression, FinSight shows whether the brand was shaping it. |
| **My decisions** | Your decision diary. From any investigation: run the **Pre-Mortem Room**, then **record your decision** in your own words with **tripwires** (e.g. "cash conversion falls below 0.8"). Each decision is written to Meterless H-MEM, and every watchlist check re-tests the tripwires with code. You get **"what you knew then vs now"**. |
| **Savings & fees** | Compare a savings account, a low-fee fund and a high-fee fund (all assumptions editable), or bad/middle/good years. Shows money lost to fees, including the growth those fees forgo, and inflation-adjusted values. |

**Pre-Mortem Room** (on every finished investigation): *"Imagine it's two years from now and a decision about this company went badly."* Nemotron writes a **Skeptic** and a **Defender**, both only from FinSight's findings, followed by questions only you can answer. Voices are rejected if they:
- cite unknown findings
- add numbers
- give a verdict or a prediction
- use size words like "doubled" that the evidence doesn't
- assert a cause the evidence says is unknown

The verified finding is shown under every point.

Every finding has an **"In plain words"** line, and financial terms are underlined: hover or tap one for a definition. Both come from deterministic templates and a hand-written glossary, not from a model, so they can't introduce a wrong number.

Open Agent Hackathon 2026. Primary track: **Track 1, Solving Fragmented Intelligence**. Also relevant to Track 2, *The Agent That Can Explain Why*.

---

## Quick start (sample mode, no credentials)

Requirements: Python 3.11+, Node 20+ (uv optional).

```bash
./scripts/dev.sh
```

Open http://127.0.0.1:5174. Search a company (one letter is enough), pick it, then ask your own question about it, or tap a suggested one. To try it offline, keep the data selector on **Sample (offline)** and pick a **sample case**. Sample mode uses two **fictional** companies, Northwind Motors and Contoso Retail. They are labeled `SAMPLE DATA` everywhere they appear, and each one exercises a reconciliation case reproducibly offline.

FinSight answers your question directly from the filings. AI-written answers must use only real numbers, agree with the direction of each change (rose or fell) and give no advice; otherwise FinSight shows an answer computed by code, or says plainly that it can't answer. The Home dashboard shows the latest finished investigation, your Watchlist (latest annual revenue and YoY change; FinSight has no market-price feed) and "Today's insights", which are real watchlist and decision events, never placeholders.

What `dev.sh` does:
1. Creates `.env` from `.env.example`.
2. Sets up `backend/.venv`.
3. Runs `npm run setup` in `services/hmem-sidecar`, which vendors the Meterless H-MEM engine.
4. Starts the backend (:8000), the H-MEM sidecar (:8765) and the frontend (`frontend-v2/`, :5174). The frontend proxies `/api` to the backend; set `VITE_BACKEND_URL` to point it elsewhere.

Or with Docker (tested: images build, and an investigation and a watchlist check run end to end with Postgres and H-MEM):

```bash
cp .env.example .env
docker compose up --build      # http://localhost:8080
```

## Live data

| Mode | Set in `.env` | What it needs |
|---|---|---|
| `sample` | `FINSIGHT_DATA_MODE=sample` | nothing |
| `sec_direct` | `FINSIGHT_DATA_MODE=sec_direct` | `SEC_USER_AGENT="your-app you@example.com"` (SEC requires a contact) |
| `zetaris` | `FINSIGHT_DATA_MODE=zetaris` | a Zetaris instance, `ZETARIS_*` settings, and the setup step below |

You can also switch modes per investigation in the UI. **Any SEC-listed company works** (about 10,400, from the SEC's official [company_tickers_exchange.json](https://www.sec.gov/files/company_tickers_exchange.json), cached for a day):
- In the UI, use the company search box (by ticker or name).
- In a question or a pasted post, write the ticker, for example `$PLTR` or `(NASDAQ: PLTR)`.

Nine companies (AAPL, MSFT, NVDA, TSLA, F, WMT, TGT, IBM, ORCL) are also recognised by name. In Zetaris mode, a company's SEC sources are **registered in Zetaris the first time it is looked up**, which takes about 10–40 seconds once. Its views are kept only if Zetaris's row counts match the SEC's. Set `ZETARIS_AUTO_REGISTER=false` to turn this off.

### Zetaris setup

```bash
backend/.venv/bin/python scripts/zetaris_setup.py --dry-run          # show the SQL; sends nothing
backend/.venv/bin/python scripts/zetaris_setup.py --apply            # create the sources, then verify them
backend/.venv/bin/python scripts/zetaris_setup.py --apply --tickers TSLA AAPL --skip-existing
```

To use the Zetaris SQL Editor instead, the same statements are in [`zetaris/sql/finsight_edgar_create.sql`](zetaris/sql/finsight_edgar_create.sql).

### Model provider (optional)

`LLM_PROVIDER=auto` tries the providers in this order:
1. **Meterless Runtime**, if online (`METERLESS_RUNTIME_TOKEN` or `METERLESS_TOKEN_FILE`)
2. **NVIDIA Nemotron**, if `NVIDIA_API_KEY` is set. Get a free key at build.nvidia.com. The default model is `nvidia/nemotron-3.5-lightning-30b-a3b`.
3. **Gemini**, if `GEMINI_API_KEY` is set
4. Otherwise no model: the summary is built deterministically from findings and labeled "No model used".

The model never does arithmetic and never supplies numbers. Its output is shown only after passing [`app/verification/model_output.py`](backend/app/verification/model_output.py), which checks four things:
- the output is valid JSON
- it cites only real finding ids
- every number in it already appears in the evidence
- it contains no buy/sell language

## Where the sponsors are used

Full details, including what is verified and what is not: [`docs/INTEGRATIONS.md`](docs/INTEGRATIONS.md).

**Zetaris: federated data access** ([`backend/app/integrations/zetaris/`](backend/app/integrations/zetaris))
- Uses the HTTP routes from Zetaris's official `getting-started` helpers: `POST /api/auth/login` and `POST /api/proxy/sql-editor/sqls/run-query`, with the `Authorization`, `X-Org-ID` and `X-Request-ID` headers.
- SEC EDGAR concepts are registered as `CREATE LIGHTNING REST TABLE` sources plus `CREATE SCHEMASTORE VIEW`s, following Zetaris's verified EDGAR recipe. FinSight queries those views with SQL.
- When cross-check is on, every Zetaris investigation also fetches the same facts from SEC directly and reports whether row counts and values agree. This is the check Zetaris's docs recommend.
- Every query is kept as a receipt: SQL, request id, rows and timing.

**Meterless: memory and model routing** ([`services/hmem-sidecar/`](services/hmem-sidecar), [`backend/app/integrations/meterless/`](backend/app/integrations/meterless))
- **H-MEM engine** (official reference, vendored by `npm run setup`). Each investigation:
  1. recalls earlier memories for the company (`MemoryRetrievalService`)
  2. writes the figures it found, with provenance (`MemoryStoreService`)
  3. re-confirms facts it already knew (feedback)
  4. records any changed figure as a `conflict_detected` / `conflict_resolved` entry in the append-only `TrustLedgerService`
- In the UI, click any memory id to see its ledger history.
- **Meterless Runtime provider**, implementing the published 0.90.0 contract:
  - URL normalization and bearer token, with `rt-local` rejected
  - `meterless-app` and `meterless-scope` headers
  - status decided by `/v1/models`: online, unauthorized or offline
  - port auto-detect and a 180 s timeout
- Model usage is shown exactly as the provider returns it. Costs are never estimated.

## Tests

```bash
cd backend && .venv/bin/pytest -q              # 100 tests: reconciliation, risk, scenarios, claims, answers, watchlist, Zetaris, Meterless, API
cd services/hmem-sidecar && npm test           # 4 tests against the real vendored H-MEM engine
cd frontend-v2 && npm test                     # 12 unit tests: names, times, money, feed, Key Insights, tripwire units
cd frontend-v2 && npm run test:e2e             # 14 browser tests of real user flows (first time: npx playwright install chromium)
cd frontend-v2 && npm run build                # typecheck + production build
```

The browser tests start their own private backend, H-MEM sidecar and frontend on ports 8767, 8011 and 5177, in sample mode with no AI model and a temporary database. They never read your `.env` keys, database or memory, and they need no internet. They cover asking a question, every investigation tab, claim checks, glossary pop-ups, the Home dashboard, Compare, Check a post, the savings simulator, watchlist change detection, the decision diary, the Pre-Mortem, Data Sources and the phone layout. A failed run leaves a screenshot and trace in `frontend-v2/test-results/`.

GitHub Actions (`.github/workflows/ci.yml`) runs all of the above, plus a Docker image build, on every push and pull request. No secrets are needed.

The brief's evaluation cases are covered in `backend/tests/test_reconciliation.py` and `test_risk_and_scenarios.py`:
1. quarterly vs annual
2. standalone vs consolidated
3. different units
4. stale vs newer source
5. profit up while cash flow falls
6. missing data and unresolved disagreement
7. scenario math, checked against closed-form formulas
8. an unsupported claim

## How an investigation works

`RECEIVED → PLANNING → RETRIEVING → NORMALIZING → RECONCILING → INVESTIGATING_RISKS → (SIMULATING) → VERIFYING → COMPLETED | NEEDS_MORE_EVIDENCE | FAILED`

Each step is recorded with real timestamps and events as it runs ([`backend/app/agents/workflow.py`](backend/app/agents/workflow.py)), and the UI polls that record. Inside the steps:

- **Reconciliation** ([`backend/app/reconciliation/engine.py`](backend/app/reconciliation/engine.py)):
  - The figure of record is the latest *financial-statement* filing (10-K/10-Q/20-F or an amendment) under a fixed concept priority.
  - Earlier filed values are kept.
  - Proxy statements (DEF 14A) and other documents are compared, but never treated as revisions.
- **Explaining an outside value:** FinSight tests these causes in order: exact match, reporting basis, revision or stale source, other concept, other document, partial period, unit scale, fiscal-year offset. If none reproduces the number, the finding is reported as **unresolved** (for a user claim, **contradicted**), and no cause is guessed.
- **Risk indicators** ([`backend/app/risk_analysis/indicators.py`](backend/app/risk_analysis/indicators.py)):
  - revenue trend
  - profit vs operating cash flow
  - debt trend and debt / operating cash flow
  - current ratio

  Each is computed over a window that uses one concept only, and each finding gives its formula, its inputs, its counterevidence and what it cannot tell you.
- **Scenarios** ([`backend/app/scenarios/calculator.py`](backend/app/scenarios/calculator.py)): monthly compounding with fees and inflation. Results are labeled hypothetical.

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | service health |
| GET | `/api/integrations/status?deep=true` | live status of Zetaris, H-MEM, Meterless Runtime and Gemini |
| GET | `/api/companies` | built-in live and sample companies, plus sample cases |
| GET | `/api/companies/search?q=` | search any SEC-listed company by ticker or name |
| POST | `/api/investigations` | start an investigation `{question, ticker?, data_mode?}` |
| GET | `/api/investigations/{id}` | state, steps, observations, findings, charts, receipts, memory |
| POST | `/api/scenarios/calculate` | deterministic scenarios (1–5) |
| GET | `/api/memory/{id}/audit` | H-MEM trust-ledger history for one memory |
| POST | `/api/claims/check` | check every claim in pasted text `{text, data_mode?}` |
| GET | `/api/glossary` | beginner glossary |
| GET / POST / DELETE | `/api/watchlist`, `/api/watchlist/{ticker}` | follow / list / unfollow companies |
| POST | `/api/watchlist/check` | re-check one or all followed companies and report changes |
| POST | `/api/investigations/{id}/premortem` | Pre-Mortem Room voices + questions |
| GET | `/api/tripwire-metrics?ticker=` | current values of tripwire metrics |
| GET / POST | `/api/decisions`, `/api/decisions/{id}`, `/api/decisions/{id}/check` | decision diary and tripwire checks |
| POST | `/api/board`, `/api/board/{id}/reveal` | Brand-Blind Board (blind view, then reveal) |
| GET / POST | `/api/sample/amendment` | publish the fictional Northwind amended filing (sample data only) |

## Repository layout

```
backend/app/        FastAPI app: agents/ (workflow, narrator, charts), financial_data/ (SEC client, providers,
                    normalization), integrations/ (zetaris, meterless, gemini), reconciliation/, risk_analysis/,
                    scenarios/, verification/, models/
services/hmem-sidecar/  Node HTTP wrapper around the Meterless H-MEM reference engine
frontend-v2/        the app: React + TypeScript + Vite + Tailwind + Apache ECharts (port 5174)
zetaris/            generated Lightning SQL and the verified-view manifest
sample_data/        fictional fixtures (labeled SAMPLE)
scripts/            dev.sh, zetaris_setup.py
docker/, docker-compose.yml
```

## Limitations

- **Zetaris is verified on a local instance** (Docker Compose bundle, 2026-10-24). The 9 built-in companies are registered (78 views), plus Palantir and Coca-Cola registered on demand. Every row count matches the SEC.
- **Coverage depends on the company's filings.** FinSight reads 6 figures under about 10 US-GAAP labels. Companies that use other labels, report under IFRS (most foreign filers), or are banks or insurers will show "insufficient evidence" for some figures rather than wrong numbers. Names in free text are only matched for the 9 built-in companies; others need the search box or a written ticker.
- **SEC-side gap:** for a few filers (seen for Coca-Cola), the SEC's per-concept endpoint returns an empty list while its companyfacts endpoint has the data. FinSight then reads that figure from companyfacts and doesn't register it in Zetaris, because a Zetaris table on the empty endpoint would be empty. The app labels those figures "Not via Zetaris".
- **The Meterless Runtime provider has not been run against a live runtime** (no Nightshift install on the build machine). It is tested against the published contract with mocks. **H-MEM is exercised for real**, against the vendored engine.
- **Gemini has not been called:** no key was available. NVIDIA Nemotron is the verified model provider.
- **Coverage is limited.** Only 9 live companies and 6 metrics are supported. XBRL facts are as filed. Some companies don't use the standard concepts; for example, Ford has no current assets/liabilities split. In that case FinSight reports *insufficient evidence* rather than zero.
- **Claim extraction** is rule-based. It handles company names, tickers, revenue/profit/cash-flow/debt figures, amounts with units and years. It doesn't read percentages, growth rates or forecasts, and it lists anything it skipped. A relative phrase like "last year" is checked against the latest fiscal year and flagged.
- **H-MEM conflict detection:** the reference engine's generic detector flags similar texts with different numbers, which would wrongly pair different fiscal years. So FinSight keys conflicts by company, metric and period, and records them through H-MEM's own ledger and `supersededBy` mechanism.
- **Licensing:** SEC data is filer-authored. FinSight queries it live and does not redistribute it.
