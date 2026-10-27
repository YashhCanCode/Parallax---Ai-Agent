# Parallax

**Understand the facts. Investigate the risks. Explore the possibilities.**

Parallax is an AI research agent that answers questions about any US-listed company **from its official SEC filings**, and shows where every number came from. Ask *"Is Tesla's revenue still growing?"* or paste a post claiming *"Apple made $500 billion last year"*, and Parallax checks the filings, explains what it found in plain words, and shows every step it took.

Financial information is everywhere, but much of it is wrong: a quarterly figure quoted as the full year, a number that was later revised, or an AI answer with no source. Parallax treats every number as something to verify, not something to trust.

It is an educational tool. It does not rate securities, predict prices or give investment advice.

Open Agent Hackathon 2026. Primary track: **Track 1, Solving Fragmented Intelligence**. Also relevant to Track 2, *The Agent That Can Explain Why*.

---

## Try it in two minutes (sample mode, nothing connected)

Requirements: Python 3.11+ and Node 20+.

```bash
./scripts/dev.sh
```

Open **http://127.0.0.1:5174**, set the data selector at the top to **Sample (offline)**, then:

1. **Investigate** → click **Northwind Motors (SAMPLE, fictional)** → click *"Is Northwind Motors' free cash flow positive?"*
2. Try the sample case *"Was Northwind Motors' 2024 revenue really $13.6 billion?"*. Parallax shows the $13.6B is one quarter; the full year was $52.4B.
3. Open **Overview → Investigation progress** and **Sources** to see every step, query and memory behind the answer.

Sample mode needs no internet, keys, Zetaris or AI. It uses two **fictional** companies, Northwind Motors and Contoso Retail, labeled `SAMPLE DATA` everywhere. Without an AI model, every answer is computed by Parallax from the filings and labeled so.

`dev.sh` creates `.env` from `.env.example`, sets up `backend/.venv`, vendors the Meterless H-MEM engine, and starts the backend (:8000), the H-MEM memory service (:8765) and the app (:5174).

Or with Docker: `cp .env.example .env && docker compose up --build`, then open http://localhost:8080.

To force sample mode whatever else is configured, set `SAMPLE_MODE=true` in `.env`.

## Sample inputs and outputs

Recorded from a real run in sample mode (2026-10-27), with Nightshift switched off, so the answers below were written by Parallax's code from the facts. With Nightshift running, the same findings are explained by Nemotron and checked before they are shown.

**1. "Is Northwind Motors' free cash flow positive?"**
> **No:** Free cash flow was -$1.90B in FY2024, down from -$200.0M in FY2023; it was $2.20B in FY2021. (operating cash flow minus capital spending)
>
> Worth a closer look: Profit rose +22.2% while operating cash flow fell -30.8% in 2024 (3 years running); Long-term debt $19.50B, +62.5% since 2021; 7.2 years of operating cash flow; Current ratio 0.91 (was 1.13); Revenue for FY ending 2023-12-31 was revised in a later filing.

**2. "Was Northwind Motors' 2024 revenue really $13.6 billion?"**
> **Your claim is contradicted:** Claimed revenue of $13.6 billion. Matches the quarterly figure $13.60B for 2024-07-01 to 2024-09-30 (10-Q), not the full-year $52.40B.
>
> Plain language: "Your number isn't right as stated, but the mix-up is understandable: this number covers only part of the year (a quarter or year-to-date), not the full year."

**3. "Should I buy Northwind Motors stock?"**
> Parallax doesn't make investment decisions for you. The findings below show what the filings say, so you can judge for yourself.

The same three questions can be asked about any real company (for example *"Is Microsoft's free cash flow positive?"*) with the data selector on **Zetaris** or **SEC direct**.

## How the agent reached its answer (trace)

Every investigation records its full trail; the app shows it under **Overview → Investigation progress** and **Sources**, and `GET /api/investigations/{id}` returns it. From sample question 2 above:

```text
RECEIVED             Question received.
PLANNING             Interpreting the question and recalling memory.
RETRIEVING           Fetching evidence (sample).
NORMALIZING          Classifying periods, units and concepts.
RECONCILING          Comparing figures across filings, concepts and sources.
INVESTIGATING_RISKS  Checking a bounded set of risk indicators.
VERIFYING            Checking evidence links, writing memory, drafting the summary.
COMPLETED            Investigation finished.

Integration trail
  sample  sample_data/sample_companies.json   ok
  hmem    POST /recall                        ok   8 memories recalled
  hmem    POST /facts                         ok   13 facts written, with source
  hmem    POST /notes  (x3)                   ok

Claim check  claim-16e44909  contradicted (period_mismatch)
  formula: pct_difference = (claim - filed) / |filed|; match if |pct| <= 0.5%
  claimed 13,600,000,000 vs filed full year 52,400,000,000 (-74.0%)
```

In Zetaris mode the trail also lists each Zetaris SQL query with its request ID, row count and timing. When Nightshift writes the answer, each AI call is recorded under `model_calls` with the **model named in Nightshift's reply** (e.g. `nvidia/nemotron-3.5-lightning-30b-a3b`), its purpose, duration, token usage exactly as returned, and whether the answer passed the checks or why it was rejected. The app shows this as "Written by … via Meterless Nightshift" on the answer.

## What you can do

| Section | What it does |
|---|---|
| **Home** | The latest investigation's key figures and chart, recent investigations, your watchlist, a calendar and real events (new filings, revised figures, tripwire hits). |
| **Investigate** | Search a company (one letter is enough), pick it, and ask your own question, or tap a suggested one. The answer cites the filings; tabs show Financials (with a **Key figures** table), Risks, Sources, Stress-test and Notes & tripwires. |
| **Check a post** | Paste a post or article. Parallax finds each financial claim, checks it against the filings and explains any mix-up (wrong year, quarter vs year, units, an old figure). |
| **Savings & fees** | Compare a savings account, a low-fee fund and a high-fee fund, with money lost to fees and inflation shown. All assumptions are editable and labeled hypothetical. |
| **Compare** | Compare 2–3 companies on their filings **with the names hidden**, so a famous brand can't sway you. Choose which to look into, then reveal. |
| **Pre-Mortem** | *"Imagine this went badly. What most likely went wrong?"* A Skeptic and a Defender argue only from the verified findings, followed by questions only you can answer. |
| **Decision Diary** | Record your decision in your own words with **tripwires** (e.g. "free cash flow falls below $0"). Every watchlist check re-tests them with code. |
| **Watchlist** | Follow companies. Each check compares fresh filings with what Parallax remembers and shows exactly what changed. In sample mode, *Publish fictional amended filing* demonstrates a detected revision; *Reset the sample demo* lets you show it again. |
| **Data Sources** | Live status of Zetaris, Meterless H-MEM, Meterless Nightshift and SEC EDGAR. |

Financial terms are underlined throughout: hover or tap one for a plain-English definition.

## How answers stay trustworthy

1. **Filings first.** Figures come from SEC EDGAR XBRL filings, through Zetaris or directly. The figure of record is the latest financial-statement filing; earlier filed values are kept, so revisions are visible.
2. **Code does the maths.** A facts sheet is computed for every investigation: 11 filed figures (revenue, gross profit, operating income, net income, operating cash flow, capital spending, R&D, cash, long-term debt, buybacks, dividends) and 8 derived ones (gross, operating, net and free-cash-flow margins, free cash flow, R&D share of revenue, cash minus debt, buybacks plus dividends). A figure the company stopped reporting years ago is labeled "no current figure" rather than shown as current.
3. **The AI is checked, not trusted.** Before an AI answer is shown, Parallax checks that it cites real findings, uses only numbers from the evidence, agrees with the direction of every change (rose or fell), matches any yes/no the filings settle, and contains no advice. A rejected answer gets one retry told exactly what to fix; if that fails, Parallax writes the answer in code from the facts, or says plainly that it has no checked answer.
4. **No advice.** "Should I buy…?" always gets a fixed reply, followed by what the filings show.
5. **Nothing is hidden.** Results appear only after verification. Every step, SQL query, SEC request, AI call (with the model that handled it and its token usage) and memory read or write is shown in the app.

Investigation steps: `RECEIVED → PLANNING → RETRIEVING → NORMALIZING → RECONCILING → INVESTIGATING_RISKS → VERIFYING → COMPLETED`.

## Sponsor technology

Details of each integration, and what has been verified live: [`docs/INTEGRATIONS.md`](docs/INTEGRATIONS.md).

**Zetaris: the data layer** ([`backend/app/integrations/zetaris/`](backend/app/integrations/zetaris))
- SEC EDGAR XBRL concepts are registered in Zetaris as `CREATE LIGHTNING REST TABLE` sources with `CREATE SCHEMASTORE VIEW`s, and Parallax reads them with SQL through Zetaris's `run-query` API.
- Every view is kept only if Zetaris's row count matches the SEC's; 143 views across 13 companies are verified so far, and the count grows as new companies are looked up. A new company is registered on first lookup, and figures added later get their own views.
- Every query is recorded with its SQL, request ID, rows and timing, and shown in the Integration trail.

**Meterless: H-MEM memory engine** ([`services/hmem-sidecar/`](services/hmem-sidecar), [`backend/app/integrations/meterless/`](backend/app/integrations/meterless))
- The official H-MEM reference engine stores every figure Parallax finds, with provenance, and re-confirms it on later checks.
- A changed figure is recorded as a conflict in H-MEM's append-only trust ledger, which powers the Watchlist's revision detection, the Decision Diary and the audit trail (click any memory ID).
- **Test result** (`cd services/hmem-sidecar && npm test`, against the real engine, 2026-10-27):

  ```text
  ok 1 - health names the engine source
  ok 2 - new fact, re-confirmation, then a conflicting later filing
  ok 3 - a fact without a source is rejected
  ok 4 - recall is isolated per company
  # tests 4
  # pass 4
  # fail 0
  ```
- To see it working in the app: in sample mode, follow Northwind Motors on the **Watchlist**, click *Publish fictional amended filing*, then *Check now*. H-MEM records the conflict and the Watchlist shows exactly which figure changed.

**Meterless Nightshift: the AI provider, routing to NVIDIA Nemotron** ([`backend/app/integrations/meterless/runtime.py`](backend/app/integrations/meterless/runtime.py))
- Every AI call goes to Nightshift, found automatically on this Mac (port 8088, with the app's own token). Nightshift routes it to **NVIDIA Nemotron 3.5 Lightning 30B** (`nvidia/nemotron-3.5-lightning-30b-a3b`), with Nemotron's reasoning switched off for fast, structured answers.
- The model that handled each request, as named in Nightshift's reply, is shown on every answer ("Written by nvidia/nemotron-… via Meterless Nightshift"), in the Pre-Mortem and in the Integration trail.
- Setup: install Nightshift (free Mac M1+ edition: https://www.meterless.ai/mac.html) and add NVIDIA as a provider in the app. If Nightshift isn't running, answers are written in code.

**NVIDIA's contribution:** Nemotron writes the plain-English explanation of every investigation, the Pre-Mortem's Skeptic and Defender, and recognises which company a question is about ("JP Morgan" → JPM). Parallax's checks then decide whether its output is shown.

### What was unique about our use of the sponsor technologies

- **Zetaris as a verified data layer, not a pass-through.** Parallax registers SEC filings in Zetaris on demand and keeps a view only when Zetaris's row count matches the SEC's, so the data layer is checked before any figure is used.
- **H-MEM as the agent's memory of what the filings said.** Instead of chat history, H-MEM holds every filed figure with its source. Its append-only conflict ledger is what turns "the company revised its numbers" into a visible event, which powers revision detection, tripwires and the audit trail.
- **Nightshift and Nemotron under supervision.** Nemotron explains the findings, but never decides them: every number, direction (rose or fell) and yes/no it writes is checked against the facts, and a failed answer gets one targeted retry, then a code-written answer. The model that handled each request is shown on the answer.
- **Built for people checking numbers, not trading on them.** All three technologies serve one goal: showing where every number came from, and catching the common mix-ups (quarter vs year, revised figures, wrong units) in posts and AI answers.

## Configuration

`.env.example` lists every setting. The main ones:

| Setting | Purpose |
|---|---|
| `FINSIGHT_DATA_MODE` | `zetaris` (default), `sec_direct` or `sample`. The data selector in the app overrides it per investigation. If Zetaris isn't reachable, Parallax uses SEC directly and labels it. |
| `SAMPLE_MODE` | `true` forces sample mode (fictional data, nothing connected), whatever `FINSIGHT_DATA_MODE` says. |
| `SEC_USER_AGENT` | Required for live data: `"app-name you@example.com"` (the SEC asks for a contact). |
| `ZETARIS_*` | Your Zetaris instance and login. `ZETARIS_AUTO_REGISTER=false` turns off registration on first lookup. |
| `METERLESS_MODEL` | The model Nightshift should use; default `nvidia/nemotron-3.5-lightning-30b-a3b`. |
| `LLM_PROVIDER` | `auto` (use Nightshift when it is running) or `none` (answers always written in code). |

Some setting names keep the project's original `FINSIGHT_` prefix so existing setups keep working.

To register companies in Zetaris ahead of time:

```bash
backend/.venv/bin/python scripts/zetaris_setup.py --dry-run          # show the SQL; sends nothing
backend/.venv/bin/python scripts/zetaris_setup.py --apply            # create the sources, then verify them
```

## Tests

```bash
cd backend && .venv/bin/pytest -q              # 128 tests: reconciliation, risks, key figures, answers and checks, claims, company recognition, watchlist, Zetaris, Meterless, API
cd services/hmem-sidecar && npm test           # 4 tests against the real H-MEM engine
cd frontend-v2 && npm test                     # 14 unit tests
cd frontend-v2 && npm run test:e2e             # 16 browser tests of real user flows (first time: npx playwright install chromium)
cd frontend-v2 && npm run build                # type check + production build
```

The browser tests start their own private backend, memory service and app in sample mode, with no AI and a temporary database, so they never touch your `.env`, data or memory and need no internet. GitHub Actions ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) runs all of the above, plus a Docker build, on every push.

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | service health |
| GET | `/api/integrations/status?deep=true` | live status of Zetaris, H-MEM and Meterless Nightshift |
| GET | `/api/companies`, `/api/companies/search?q=` | built-in and sample companies; search any SEC-listed company |
| POST, GET | `/api/investigations`, `/api/investigations/{id}` | start an investigation `{question, ticker?, data_mode?}`; read its steps, findings, figures and trail |
| POST | `/api/investigations/{id}/premortem` | Pre-Mortem voices and questions |
| POST | `/api/claims/check` | check every claim in pasted text |
| POST | `/api/scenarios/calculate` | savings and fees scenarios |
| GET | `/api/glossary`, `/api/memory/{id}/audit` | plain-English glossary; H-MEM ledger history of one memory |
| GET, POST, DELETE | `/api/watchlist`, `/api/watchlist/{ticker}`, `/api/watchlist/check` | follow, list, unfollow and re-check companies |
| GET, POST | `/api/decisions`, `/api/decisions/{id}/check`, `/api/tripwire-metrics` | decision diary and tripwires |
| POST | `/api/board`, `/api/board/{id}/reveal` | brand-blind comparison |
| GET, POST, DELETE | `/api/sample/amendment` | publish or reset the fictional Northwind amended filing |

## Repository layout

```
backend/app/            FastAPI app
  agents/               investigation workflow, AI narrator, watchlist, charts
  analysis/             key figures (the facts sheet)
  financial_data/       SEC client, company directory, providers (Zetaris, SEC, sample)
  integrations/         Zetaris and Meterless (H-MEM client, Nightshift runtime)
  reconciliation/       figure of record, revisions, claim checks
  risk_analysis/        risk indicators
  verification/         checks on AI output (numbers, direction, yes/no, advice)
  decisions/            decision diary, tripwires, brand-blind board, pre-mortem
  explain/, scenarios/, models/, api/
backend/tests/          pytest suite
services/hmem-sidecar/  HTTP wrapper around the Meterless H-MEM reference engine
frontend-v2/            the app: React, TypeScript, Vite, Tailwind, Apache ECharts (+ e2e/ browser tests)
zetaris/                generated Lightning SQL and the verified-view manifest
sample_data/            fictional sample companies (labeled SAMPLE)
scripts/                dev.sh, zetaris_setup.py
docker/, docker-compose.yml, .github/workflows/
```
