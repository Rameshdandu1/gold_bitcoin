# Dual AI Market Intelligence — Gold + Bitcoin

## Current status: Phase 6 offline contract corrections implemented

The [independent workflow-acceptance review](docs/audits/phase-6-workflow-acceptance-independent-review.md)
of merged PR #15 at `e9f419f5ef576ec957f9d59107ab3f7f06815b23` confirms 260 passing tests, the
original later-book and stop/recovery corrections, and bounded irrelevant-quote loading. It also
reproduced six recovery, clock, target-history, dual-policy, outcome-coverage and
historical-state/output findings within the existing requirements. The corrective implementation
and its offline evidence are recorded in the
[contract-corrections verification](docs/audits/phase-6-contract-corrections-verification.md).

P6W-01 through P6W-06 now have regression coverage: candidate/rules creation is atomic, event and
receipt clocks plus per-target crossings are durable, provider verdicts are distinct from each
arm's market disposition, executed stops require continuous executable evidence, resolved provider
working state retires, and report/API projections page before model construction. Scientific
contracts are versioned; old derived checkpoints are retained but explicitly require a new isolated
experiment rather than silently mixing outcome semantics.

The original [closeout verification report](docs/audits/phase-6-closeout-verification.md) is retained
as historical implementation evidence. The later
[workflow acceptance verification](docs/audits/phase-6-workflow-acceptance-verification.md) retains
its executed results; the independent review qualifies its complete-acceptance claim. Tested
checkpoint/paper resume controls remain verified, while the candidate/initial-arm write boundary
is preserved by the corrected atomic write and fresh-process controls.

After the finite corrections, the sequence is controlled destination Windows/live integration
validation, then prospective paper observation. Derivatives/execution remain deferred.

## Phase 6 evidence-integrity workflow

Phase 6 adds availability/provenance fields, cadence evaluation, quote-side outcomes, protected
research and paper reads and a connected synthetic paper command. Closeout corrected the reviewed
clock-conflict, coverage, paper-holdout and terminal/progress failures. Shared predicates, derived-state
resume and 500-event input pages are implemented. Corrected workflows additionally page candidate
quote/source windows, retain lifecycle and target-crossing facts, retire completed paper/provider
working state, and stream latest-revision report exports in bounded pages. Research and paper state
remain isolated
from production review, budget and notification state. The included generator creates synthetic
verification streams; it does not establish strategy accuracy or profitability.

```powershell
.\.venv\Scripts\python.exe -m marketintel.research_fixtures --output data\phase5-fixtures
.\.venv\Scripts\python.exe -m marketintel.research validate-data --manifest data\phase5-fixtures\gold-manifest.json
.\.venv\Scripts\python.exe -m marketintel.research run-workflow --manifest data\phase5-fixtures\gold-manifest.json --config data\phase5-fixtures\gold-experiment.json --database data\gold-research.sqlite3 --production-database data\marketintel.sqlite3
.\.venv\Scripts\python.exe -m marketintel.research paper-workflow --database data\gold-research.sqlite3 --paper-database data\gold-paper.sqlite3 --production-database data\marketintel.sqlite3 --experiment-id phase5-gold-workflow-v1
.\.venv\Scripts\python.exe -m marketintel.research evaluate --database data\gold-research.sqlite3 --production-database data\marketintel.sqlite3 --experiment-id phase5-gold-workflow-v1
.\.venv\Scripts\python.exe -m marketintel.research report --database data\gold-research.sqlite3 --paper-database data\gold-paper.sqlite3 --production-database data\marketintel.sqlite3 --experiment-id phase5-gold-workflow-v1 --output data\gold-report
```

Repeat `run-workflow`, `paper-workflow`, `evaluate` and `report` with the generated BTC manifest/config and
`phase5-btc-workflow-v1`. Acceptance tests run all six real detectors; fixture provider completions
remain labelled `SYNTHETIC_FIXTURE`. `paper-workflow` is explicitly
`SIMULATED_PROSPECTIVE`: it durably records decisions before eligible fixture entry and derives
outcomes from later normalized quotes. It is not elapsed real-time prospective evidence. Missing
genuine assessments stay `UNAVAILABLE`. `run-workflow --maximum-events N` and
`paper-workflow --maximum-events N` persist scoped progress; invoking the same command again resumes
from the committed offset rather than claiming a 0/0 completion. Their normal paths use 500-event
batches. The external local-stream importer is separately bounded
and disabled:

```powershell
.\.venv\Scripts\python.exe -m marketintel.paper_worker --config config\paper-worker.example.json --once
```

`PAPER_COLLECTION_ENABLED=false`, live ingestion, paid AI and alerts remain off by default.
`TRADING_ENABLED=true` is rejected during settings validation.

**Research-only Windows Server application.** Independent Gold/BTC short (30m), hourly (60m), and session (240m) candidate detection using **Delta Exchange India** market data; separate GPT and Claude reviews, fresh deterministic consensus, authenticated operator views and durable Slack notification intents. `CoinGlass` integration is optional and entitlement-aware.

> **Not production ready, not an automatic trader and not evidence of profitable signals.** By default no live data ingestion or paid AI calls happen. Gold token XAUT/PAXG may not be listed at all times; the adapter discovers rather than assumes listings. Options/execution, pre-collection market history, macro news and calibrated probabilities are planned, not already built.

**Offline workflow status (2026-11-22):** The reviewed 260-test baseline and original
regression/resource cases are preserved. Contract-correction tests cover the exact transaction,
late-event, target-recovery, temporary-book, incomplete-stop and bounded-projection cases. A
600-opportunity report probe constructs no more than 200 selected records per page, while API limit
1 constructs one record; resolved provider objects are absent from complete checkpoints while the
indexed journal remains auditable. Live provider/model
entitlement, adequate licensed historical data, genuine historical AI assessments, Slack delivery,
prospective observation duration, destination Windows Server recovery, market-data soak and
empirical strategy performance remain unverified.

## What is already implemented in this starter
- Authenticated FastAPI read-only health, engine, candidate, revision, lifecycle, provider-attempt,
  queue, budget and feature-snapshot views. Only minimal `/healthz` is public.
- Delta India REST product discovery periodically validates live/operational BTC and available
  XAUT/PAXG linear futures/perpetuals, including vanilla notional, settlement, contract value,
  unit currencies and tick size. Existing collectors stay active when the verified symbols do not
  change.
- Public `trades` + incremental `ob_updates` ingestion uses typed UTC event envelopes, rolling
  executed-trade windows, sequence/CRC32 validation and fail-closed book resynchronization.
- Append-only SQLite raw-event/source-status journal with deterministic trade-to-candle replay and
  REST-vs-stream reconciliation helpers. SQLite capacity and retention still require a live soak.
- Six deterministic, independently configured engines (`GOLD_FAST`, `GOLD_HOURLY`,
  `GOLD_SESSION`, `BTC_FAST`, `BTC_HOURLY`, `BTC_SESSION`). They evaluate only closed,
  contiguous candles and combine confirmed market structure, liquidity sweeps or breakout/retests,
  executed-trade flow, validated order-book state, ATR, UTC-day candle-volume VWAP proxy, relative volume and
  volatility expansion. Outputs remain research `CANDIDATE` events, never trade confirmations.
- One byte-stable immutable analysis envelope per candidate revision, append-only review runs,
  fenced leased jobs, provider attempts, spend reservations, decisions and alert outbox rows.
- Independent concurrent typed GPT/Claude adapters with strict structured output, actual returned
  model metadata, bounded deadlines/retries and fail-closed validation. Calls are OFF by default.
- Fresh post-review revision/lifecycle/trade/book/spread/cost/risk gates. A decision and one
  revision-scoped Slack intent commit atomically; delivery is independently leased and revalidated.
- Optional entitlement-gated CoinGlass V4 BTC open-interest and last-closed funding context. The
  adapter verifies supported coins/pairs and never assumes Delta India coverage; paid liquidation
  endpoints are not called by the engines.
- A typed Gold reference-provider contract whose production adapter is deliberately unwired and
  reports `UNAVAILABLE`. Tests use fixtures explicitly labelled non-live; no licensed XAU/USD or
  macro integration is claimed.
- Accurate React provider/lifecycle/freshness views, single-operator HTTP Basic boundary, Slack
  adapter with fake-transport tests, and native Windows startup/check/backup scripts.

## Requirements
Windows Server 2022 or 2025; PowerShell 7 recommended; Python 3.12 or newer; Node 20+ (only for frontend build); outbound TLS access to provider APIs; Git. **GPU not needed**. Suggested initial VM: 6–8 vCPU, 16 GB RAM, SSD. Production raw market events may require much more storage.

## Setup on Windows Server (PowerShell)

```powershell
# In the downloaded project folder
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
# Set operator credentials. Keep live, AI and alerts disabled initially.
python -m pytest -q
python -m uvicorn marketintel.api:app --host 127.0.0.1 --port 8000
```

Authenticate to `http://127.0.0.1:8000/docs` or `/api/health`. In another PowerShell window, run the market worker **only after** choosing symbols and setting `LIVE_INGESTION_ENABLED=true` in `.env`:

```powershell
.\.venv\Scripts\Activate.ps1
python -m marketintel.worker
```

The worker polls REST closed candles and durably records validated public trade/order-book events.
Stored executed trades can be replayed deterministically into finalized candles; they do not
reconstruct events from before collection began. Missing/invalid Gold instruments produce
`UNAVAILABLE`/`PARTIAL`, not a substitute symbol or fake signal. With `AI_ENABLED=true`, a candidate
with a complete feature snapshot queues one immutable review; `python -m
marketintel.review_worker` processes it only when both providers, operator-entered rates, spend caps
and risk assumptions are configured. `python -m marketintel.notifications` sends only when
`ALERTS_ENABLED=true` and Slack is explicitly configured. No process contains an order path.

Build frontend:

```powershell
cd frontend
npm ci
npm run typecheck
npm run build
npm run dev
```

Open `http://127.0.0.1:5173` (Vite proxies `/api` to local FastAPI). No keys in frontend.

### Operator interface

The responsive dashboard has five views:

| View | Available evidence and interactions |
| --- | --- |
| Overview | Gold/BTC selection; 30-minute, 1-hour and 4-hour engine cards; recorded candidate price levels; lifecycle; searchable candidate journal |
| Liquidity sweeps | Recorded candidates whose trigger includes a sweep, with the attached closed-candle evidence |
| AI reviews | Independent GPT and Claude attempts, model names, rationales, counter-evidence, token usage and historical consensus |
| Research | Experiment selection, dataset and configuration provenance, saved reports and experiment-scoped paper transitions |
| System health | Feature configuration, source observations, service heartbeats, recorded spend and queue state |

All API requests are read-only. Observation times can be displayed in IST (default)
or UTC. Health, engine and candidate status poll 15 seconds after each request
completes; research evidence refreshes on request. Snapshot requests are cancelled
when selection changes, and mismatching candidate/snapshot identities are withheld.
Provider verdicts require matching candidate, revision, snapshot, evidence digest,
instrument, horizon and direction before they are displayed.

The price-level map displays stored entry, invalidation and target levels. It is not
a live price chart. Historical AI confirmation is shown separately from current
lifecycle, including expiry and invalidation. Technical reference levels are not
liquidation heatmap clusters. Missing data stays unavailable.

[Open the implementation and verification notes](docs/UI_IMPLEMENTATION.md).
An explicitly hypothetical, self-contained visual preview is provided at
`docs/ui-preview/preview.html`; download it and open it in a browser. It contains no
live account data, makes no API calls and is excluded from the production build.

For the optional browser smoke checks, install Playwright in a **test environment**,
start Vite, and run from the repository root:

```powershell
python -m pip install playwright
python -m playwright install chromium
# Set CHROMIUM_PATH to your installed Chromium executable if needed.
python frontend/tests/ui_smoke.py --base-url http://127.0.0.1:5173 --screenshots docs/ui-preview
```

The test runner intercepts API reads with labelled hypothetical fixtures and blocks
external requests. See the verification notes for which checks were executed and
which still require a browser-capable environment.

## Key environment settings
Copy `.env.example`. Do not commit `.env`. Important variables:
- `DELTA_REST_URL`, `DELTA_WS_URL`, `BTC_SYMBOL=BTCUSD`, `GOLD_SYMBOL=XAUTUSD` (discover/verify live; change to listed gold contract)
- `DELTA_BOOK_MAX_AGE_SECONDS=10` invalidates snapshots/updates whose exchange time is too old
- `DELTA_DISCOVERY_REFRESH_SECONDS=300` rechecks product availability without interrupting an
  unchanged healthy feed
- `LIVE_INGESTION_ENABLED=false`, `AI_ENABLED=false`, `ALERTS_ENABLED=false`,
  `TRADING_ENABLED=false`
- `OPENAI_API_KEY`, `OPENAI_MODEL`; `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`
- `COINGLASS_API_KEY`, `COINGLASS_ENABLED=false`, `COINGLASS_BASE_URL`, and the declared
  `COINGLASS_PLAN` used to block endpoints outside the configured subscription
- `OPERATOR_USERNAME`, `OPERATOR_PASSWORD`, exact `CORS_ALLOWED_ORIGINS_CSV`
- integer micro-USD provider rates/caps and explicit `RISK_FEE_BPS`, `RISK_SLIPPAGE_BPS`
- `SLACK_BOT_TOKEN`, `SLACK_CHANNEL_ID`; delivery stays off by default
- `DATABASE_PATH`, `DATA_MAX_AGE_SECONDS`

No `DELTA_API_KEY` is needed for public market data; do not give trading permissions to this MVP.

## Delta market-data integrity behavior

- Runtime discovery accepts only live, operational vanilla `futures`/`perpetual_futures` with
  verified underlying/contract/quote/settlement units. `GOLD_SYMBOL` is a preference; another
  verified XAUT/PAXG linear USD market may be selected, otherwise Gold is unavailable. Discovery
  refreshes periodically and replaces collectors only when the verified symbol set changes.
- Buyer role `r=t` is an aggressive buy and `r=m` is an aggressive sell. Unknown roles are stored
  and counted as unclassified rather than guessed. Quantities remain contracts until normalized
  with the discovered contract value.
- Raw events store exchange event time, local receive time and publish time separately. Duplicate
  deterministic IDs are ignored. The logical partition key is the UTC event day.
- An `ob_updates` gap, reorder, bad CRC32, stale/future time, empty side, crossed book, or exchange
  snapshot error invalidates that book. It is unusable until a fresh valid snapshot is received.
- Replay emits only closed, resolution-aligned candles. It never fills missing periods or uses an
  in-progress bucket. Phase 2 replay also requires each input candle's factual availability time,
  so a late REST observation or revision cannot be treated as known at the candle close.

## Phase 2 signal integrity behavior

- FAST engines use 1-minute triggers with closed 3/5-minute context; HOURLY engines use 5-minute
  breakout/retest logic with 15-minute/hour context; SESSION engines use 15-minute triggers with
  1/4-hour structure context. Resampling never forward-fills gaps.
- Confirmed pivots produce HH/HL/LH/LL and closed-candle BOS/CHOCH events without repainting.
  Candidate IDs include asset, verified symbol, engine, horizon, candle close, direction and rule
  version so retries cannot create duplicate signals.
- Order flow uses the exact most recent 500 and 5,000 executed trades available at the evaluation
  clock. Unknown aggressor roles are excluded from directional volume rather than guessed. Contract,
  base and quote quantities remain separately labelled.
- Sequence/checksum-validated books provide quote-notional depth imbalance and an explicit
  absorption proxy. A stale, crossed, missing or corrupt book forces book-dependent engines to
  `WAIT`.
- Gold evaluates geometric $10/$20/$30 underlying distances against ATR, reward/risk and nearby
  opposing levels. BTC tiers use the greater of configured percentage and ATR distances. These are
  feasibility filters, not probabilities or claims of expected profit.
- Missing or stale observations return `UNAVAILABLE`, `WAIT`, `WATCH` or `REJECTED`. Lifecycle
  transitions, invalidation and expiry are append-only and replayable. Active candidates are
  invalidated or expired when discovery, REST history or required feeds fail. Phase 2 defines no
  `CONFIRMED` state and cannot place an order.

## Phase 3 review and notification integrity

- Complete session/previous-day acquisition, first-break BOS/CHOCH identity, candle availability,
  event-based stop breach persistence and continuous discovery/reconciliation eligibility correct
  the independently reviewed Phase 2 defects.
- Both providers receive the same stored canonical bytes concurrently and never see each other's
  answer. Wrong identity, schema, model, refusal, truncation, timeout, provider error or budget
  failure cannot confirm.
- Agreement is followed by a new deterministic read of active revision, lifecycle, executed trade,
  target/stop ordering, validated book, spread, entry drift, costs and reward/risk. Approval of an
  older revision is never transferred.
- Slack is the one implemented channel. Confirmation and terminal lifecycle notifications use
  distinct stable identities and durable receipt states. Alerts remain off unless explicitly
  authorized; no real notification was sent during development verification.
- HTTP Basic is a single-operator control, not transport encryption. Keep the API on loopback and
  use a restricted HTTPS reverse proxy/VPN for remote access. See the Windows runbook.

Model agreement and passing software tests are not accuracy, probability, profitability, or trading
advice. Derivatives and execution remain deferred and are absent from this repository.

See the [initial codebase audit](docs/audits/initial-codebase-audit.md) for the measured baseline,
live discovery timestamp and remaining unverified operational work. Architecture and operating
references are in [DESIGN.md](DESIGN.md),
[ADR 0001](docs/adr/0001-delta-event-journal-and-book-integrity.md),
[ADR 0002](docs/adr/0002-deterministic-six-engine-signals.md),
[ADR 0003](docs/adr/0003-canonical-analysis-and-durable-review-jobs.md),
[ADR 0004](docs/adr/0004-single-operator-auth-and-slack-outbox.md), [the API guide](docs/API.md),
[the Phase 2 verification report](docs/audits/phase-2-verification.md),
[the independent Phase 2 review](docs/audits/phase-2-independent-review.md),
[the independent Phase 3 review](docs/audits/phase-3-independent-review.md),
[the independent Phase 4 review](docs/audits/phase-4-independent-review.md),
[the security policy](docs/SECURITY.md), and
[the Windows runbook](docs/WINDOWS_DEPLOYMENT.md); the ordered backlog is the
[implementation plan](docs/IMPLEMENTATION_PLAN.md). Contributors and coding agents should start
with [AGENTS.md](AGENTS.md), [CODEX_START_HERE.md](prompts/CODEX_START_HERE.md) and
[CODEX_TASK.md](prompts/CODEX_TASK.md). Phase instructions are in
[CODEX_PHASE_2.md](prompts/CODEX_PHASE_2.md), [CODEX_PHASE_3.md](prompts/CODEX_PHASE_3.md) and
[CODEX_PHASE_4.md](prompts/CODEX_PHASE_4.md), [CODEX_PHASE_5.md](prompts/CODEX_PHASE_5.md) and
[CODEX_PHASE_6.md](prompts/CODEX_PHASE_6.md).
Release history is recorded in [CHANGELOG.md](CHANGELOG.md).

## Run quality checks

```powershell
python -m pytest -q
python -m compileall -q src
python -m ruff check .
python -m ruff format --check .
cd frontend
npm run typecheck
npm run build
```

## GitHub repository
The project is maintained at **https://github.com/Rameshdandu1/gold_bitcoin**.

> **Visibility:** This existing repository is PUBLIC. Never commit credentials, private account exports, live position data, or local databases. `.env` and `data/` are excluded by `.gitignore`. For private development, change repository visibility from GitHub settings before adding sensitive proprietary algorithms or trading records.

Clone and start development:

```powershell
git clone https://github.com/Rameshdandu1/gold_bitcoin.git
cd gold_bitcoin
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
python -m pytest -q
```

For later updates use the supplied `scripts/push-gold-bitcoin.ps1` helper from an authenticated local machine. Do not change the remote to a different repository.
