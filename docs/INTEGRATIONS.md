# Sponsor integrations: what is used, where, and how it was verified

Sources checked on 2026-10-23:
- Hackathon event page: https://hackathon.genai.works/event/open-agent-hackathon-2026
  - Judging puts 10 of 100 points on sponsor tech.
  - The Wildcard track requires both Zetaris and Meterless.
  - The demo video must show how both are integrated.
- Zetaris: https://github.com/zetaris/getting-started (updated 2026-10-22). Files used: `scripts/zetaris_api.py`, `query_zetaris.py`, `check_zetaris.py`, `scripts/HOWTO.md`, `open_data/rest_apis/sql/rate_limited/01_edgar_company_facts_*.sql`, `docs/guides/zetaris-lightning-sql-companion.md`.
- Meterless: https://github.com/meterless/meterless. Files used: `docs/agent-ready/add-meterless-provider.md` (Runtime 0.90.0 contract), `engines/hmem/` (spec and reference engine), `templates/agentathon-starter/`, `docs/community/hackathon-guide.md`.

## Zetaris

**Role:** the federated SQL layer between Parallax and SEC EDGAR. Each company × concept is a Lightning REST table that Zetaris fetches live, flattened by a schemastore view. Parallax never parses Zetaris-only formats. It reads the view rows and normalizes them the same way it normalizes the direct SEC API, so the two channels can be compared row for row.

| Piece | File | Source of truth |
|---|---|---|
| Auth | `backend/app/integrations/zetaris/client.py` `_login` | `POST /api/auth/login {username,password}` → `idToken`/`token`/`accessToken`, or `ZETARIS_API_KEY` (official `zetaris_api.py`) |
| Query | `client.py` `run_query` | `POST /api/proxy/sql-editor/sqls/run-query {sql, limit, engineId?}` with `Authorization: Bearer`, `X-Org-ID`, `X-Request-ID` (official `query_zetaris.py`) |
| Health | `client.py` `list_databases` | `GET /api/proxy/lightning-database/databases` (official `check_zetaris.py`) |
| Response parsing | `client.py` `parse_query_response` | `{data:[...], headers:[...]}`, with object or array rows (official `examples/pudl-chart/render.py`) |
| Source registration | `backend/app/integrations/zetaris/sql.py`, `scripts/zetaris_setup.py` | `CREATE LIGHTNING DATABASE`, `CREATE SCHEMASTORE CONTAINER`, `CREATE LIGHTNING REST TABLE … REQUEST(endpoint, method, response_type, http_encoding) HEADER(user-agent) BODY()`, `CREATE SCHEMASTORE VIEW … LATERAL VIEW explode(units.USD)` (official EDGAR recipe) |
| Verification | `scripts/zetaris_setup.py --verify`; `reconciliation/engine.py` `channel_cross_check` | The recipe's advice: compare each view's `COUNT(*)` with the live SEC endpoint before trusting it |
| Runtime use | `backend/app/financial_data/providers.py` `ZetarisProvider` | Reads only the views listed in `zetaris/registered_views.json`, which is written by a successful verify |

**Two changes from the recipe, both deliberate:**
1. Balance-sheet (instant) concepts have no `start` field, so their views select `CAST(NULL AS STRING) AS period_start`.
2. Concepts a company doesn't report (SEC returns 404) are never registered. The setup script probes SEC first.

**Failure behavior:**
- If Zetaris is unreachable or not configured, the investigation records the failed receipt and says so in *Limitations*.
- It then falls back to the direct SEC API. The fallback is labeled; it never passes itself off as a Zetaris result.

**Verification status: working against a live local Zetaris instance** (Docker Compose bundle, 2026-10-24).
- **Sign-in:** both methods work against `localhost:3000`, the API key and `POST /api/auth/login` with a username and password.
- **Query route:** `GET /api/proxy/lightning-database/databases` and `POST /api/proxy/sql-editor/sqls/run-query` work, including on the sample `NY_TAXI` data.
- **Registration:** `scripts/zetaris_setup.py --apply` created the `FINSIGHT_SEC` Lightning database, the `finsight` container, and **78 REST tables plus views for all 9 companies**. **All 78 row counts match the direct SEC API**; `--verify` re-checked them all. The 12 company/concept pairs the SEC has no data for (mostly Ford) are listed under `no_data` in `zetaris/registered_views.json`, so the app can say "the company doesn't report this" instead of "not registered".
- **On-demand registration:** Palantir and Coca-Cola were later registered on first lookup, and the 7 figures added later (gross profit, operating income, R&D, capital spending, cash, buybacks, dividends) got their own views for Apple, Microsoft, NVIDIA, Tesla and Walmart. The manifest now holds **143 verified views across 13 companies, 0 rejected** (2026-10-27).
- **Live investigations** in `zetaris` mode, each cross-checked against the SEC with **0 value mismatches**:
  - Tesla: 1,133 facts through 9 queries
  - Apple: 1,272 facts through 10 queries
  - Ford: 617 facts through 5 queries
- Two behaviours of the real instance that the docs don't mention, both now handled and covered by tests:
  - Database descriptions may only contain letters, digits, spaces and `_ . - ,`. Parallax's first description had a colon and was rejected.
  - Every value in query results comes back as text (`"1"`, not `1`). Parallax converts these.
- 10 unit tests in `backend/tests/test_zetaris.py`, plus 8 in `backend/tests/test_any_company.py` covering the directory, on-demand registration and the SEC-gap fallback.

**On-demand registration for any SEC-listed company** (`backend/app/integrations/zetaris/registry.py`). The first time a company is looked up in `zetaris` mode, Parallax:
1. Probes the SEC for the concepts it reports.
2. Creates the same `CREATE LIGHTNING REST TABLE` and `CREATE SCHEMASTORE VIEW` statements as the setup script.
3. Queries the new views, and keeps each one **only if Zetaris returns the same number of rows as the SEC**. Mismatches are recorded under `rejected`, and their data isn't used.

Every CREATE is logged in the investigation's Integration trail. Verified live:
- Palantir: 6 views created and verified in 13 s, 317 facts, 0 mismatches
- Coca-Cola: 3 views

**SEC-side gap found while testing:** for Coca-Cola, `companyconcept` (the endpoint the Zetaris recipe reads) returns `"USD": {}` for 5 concepts, while `companyfacts` has the full history. Parallax records those pairs under `concept_api_empty` instead of registering empty Zetaris tables. It reads those figures from `companyfacts` directly and shows "Not via Zetaris" for them.

Of the 8 companies spot-checked, only Coca-Cola had this. The others' concept counts matched `companyfacts` exactly.

To register companies ahead of time (any SEC ticker):

```bash
backend/.venv/bin/python scripts/zetaris_setup.py --apply --tickers AAPL MSFT --skip-existing
```

## Meterless

### H-MEM (memory engine) — exercised for real

**Role:** Parallax's long-term memory across investigations, with provenance and an audit trail.

`services/hmem-sidecar/server.ts` loads the official H-MEM reference engine. `npm run setup` vendors it from `meterless/meterless/engines/hmem/reference` via degit, exactly as the official agentathon starter does. The sidecar exposes the engine over HTTP for the Python backend.

| Parallax action | H-MEM service | When |
|---|---|---|
| Recall prior memories for a company (namespaced via `chatId` = ticker) | `MemoryRetrievalService.query` (hybrid ranking, trace) | PLANNING |
| Store each reconciled annual figure, with `source` + `provenance.refs` (filing URL) | `MemoryStoreService.add` (rejects records with no source) | VERIFYING |
| Same figure seen again | `MemoryRetrievalService.feedback("helpful")` (+0.05 confidence, logged) | VERIFYING |
| Same company/metric/period with a different value | `TrustLedgerService.log("conflict_detected")`, `store.update({supersededBy})` + `conflict_resolved` when the new value comes from a later filing | VERIFYING |
| Note notable risk findings | `MemoryStoreService.add` | VERIFYING |
| "Ledger for mem-N" in the UI | `TrustLedgerService.history` | on click |
| **Decision Diary**: the user's decision and tripwires, stored with timestamped provenance. The append-only ledger proves what was decided and when | `MemoryStoreService.add`, `TrustLedgerService` | My decisions; "Record your decision" |
| **Tripwire hit**: logged as its own memory, linked to the decision | `MemoryStoreService.add` | every watchlist or decision check |
| **Blind-board pick**: which company the user chose on evidence, before seeing names | `MemoryStoreService.add` | Blind board reveal |
| **Watchlist check**: write this run's figures (latest 3 years + latest 2 quarters per metric) and report each fact's outcome as new / confirmed / changed | same services as above | Watchlist tab, `POST /api/watchlist/check`, or every `WATCHLIST_CHECK_MINUTES` |

**Why conflicts are keyed by fact:** the reference `ConflictDetectionService` flags any two very similar texts with different numbers. That would wrongly flag "revenue FY2023 = X" against "revenue FY2024 = Y". So Parallax keys each fact by company, metric and period, and records real conflicts through the same ledger actions and `supersededBy` semantics defined in the H-MEM spec (AGENTS.md §10).

**Verification status:**
- 4 sidecar tests run against the real engine (`services/hmem-sidecar/test/sidecar.test.ts`).
- `backend/tests/test_watchlist.py` starts the real sidecar and checks the full flow: baseline, then re-confirmation, then detecting the fictional amendment. That last step catches revenue 52.4B → 51.9B and net income 4.4B → 4.1B, with `conflict_detected` and `conflict_resolved` in the ledger.
- Manual end-to-end runs on live Tesla and Apple data exercised recall and re-confirmation. A conflict also appeared when a corrected value replaced one stored by an earlier (buggy) run, which exercised the ledger path end to end.

### Meterless Nightshift (Runtime) — the AI provider, routing to NVIDIA Nemotron; verified live (2026-10-26)

**Role:** Parallax's only AI provider:
- question interpretation, used only when no supported company is found deterministically
- the direct answer and plain-language summary
- the Pre-Mortem voices

When it is offline, Parallax writes answers in code from verified findings and key figures.

`backend/app/integrations/meterless/runtime.py` implements the published contract for Runtime 0.90.0:

| Contract rule | Implementation |
|---|---|
| Default `http://127.0.0.1:8088/v1`; normalize any pasted URL to `<host>/v1`, never `/v1/v1` | `normalize_base_url` |
| `Authorization: Bearer <token>`; token from `<stateDir>/proxy-token`; `rt-local` rejected | `resolve_token`, `METERLESS_TOKEN_FILE`; with no setting, the Mac app's `runtime-token` is found automatically |
| `meterless-app` on every request, `meterless-scope: user` on chat | `_headers` (app id `parallax-ai`) |
| Model ids are routing modes (`meterless/auto` …) or provider models, read from `/v1/models` | `METERLESS_MODEL` (default `nvidia/nemotron-3.5-lightning-30b-a3b`), `status().models` |
| `/v1/models` decides status: 401/403 unauthorized, 200 with meterless ids online, else offline | `status` |
| Auto-detect ports 8088, 8090, 8787, 11434 on 127.0.0.1 / localhost / [::1] | `auto_detect` |
| 180 s chat timeout | `CHAT_TIMEOUT_S` |

What Parallax records per call (`ModelCall`):
- provider and model id, exactly as returned
- duration
- the `usage` object, exactly as returned
- whether the output passed verification

Parallax does not compute or claim costs.

**Verification status: working live** against Nightshift on a Mac M1+ (2026-10-26), with NVIDIA added as a provider in the Nightshift app.
- **Connection:** found on port 8088 and authenticated with the app's `runtime-token`, no configuration needed. `/v1/models` lists Nightshift's routing modes, its on-device models and the NVIDIA Nemotron models.
- **Model:** Parallax requests `nvidia/nemotron-3.5-lightning-30b-a3b` through Nightshift, with `chat_template_kwargs.enable_thinking=false`, which Nightshift passes through: about 1 s for a short reply instead of about 17 s with reasoning on. If a model rejects the switch, the call is retried once without it.
- **Live investigations** (Zetaris data, Nemotron via Nightshift): 5 of 7 answers were model-written and passed every check, at about 5 s per call. The other 2 used a number not in the evidence and were replaced by answers computed in code, as designed. Every answer names the model from Nightshift's reply.
- **On-device models:** Nightshift's routing modes (`meterless/auto`, `fast`, `deep`, `local`) chose 1–4B on-device models with a 4,096-token context. They failed or took 1–2 minutes on Parallax's evidence, so the default is Nemotron.
- **Tests:** contract, token discovery, the Nemotron switch and its retry, and the full answer path, all against mocks (`backend/tests/test_meterless_and_llm.py`).
