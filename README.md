# Dual AI Market Intelligence — Gold + Bitcoin

**Research-only Windows Server application.** Independent Gold/BTC short (30m), hourly (60m), and session (240m) candidate detection using **Delta Exchange India** market data; separate GPT and Claude reviews, fresh deterministic consensus, authenticated operator views and durable Slack notification intents. `CoinGlass` integration is optional and entitlement-aware.

> **Not production ready, not an automatic trader and not evidence of profitable signals.** By default no live data ingestion or paid AI calls happen. Gold token XAUT/PAXG may not be listed at all times; the adapter discovers rather than assumes listings. Options/execution, pre-collection market history, macro news and calibrated probabilities are planned, not already built.

**Review status (2026-11-21):** Phase 3 is merged and its 171-test baseline passes. The original
session-history, repeated-first-break and future-availability examples are corrected. The
[independent Phase 3 review](docs/audits/phase-3-independent-review.md) reproduced additional startup,
reconciliation, provider-identity, revision-scheduling, risk-race, budget and alert-delivery defects.
The next implementation is [CODEX_PHASE_4.md](prompts/CODEX_PHASE_4.md), beginning with mandatory
4A corrections before historical evaluation and prospective paper research. These findings and
instructions are not completed fixes. Live provider/model access, Slack delivery, Windows service
installation, market-data soak and strategy performance remain unverified.

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
npm install
npm run typecheck
npm run build
npm run dev
```

Open `http://127.0.0.1:5173` (Vite proxies `/api` to local FastAPI). No keys in frontend.

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
advice. Phase 4 must perform time-ordered historical evaluation and paper trading.

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
[the security policy](docs/SECURITY.md), and
[the Windows runbook](docs/WINDOWS_DEPLOYMENT.md); the ordered backlog is the
[implementation plan](docs/IMPLEMENTATION_PLAN.md). Contributors and coding agents should start
with [AGENTS.md](AGENTS.md), [CODEX_START_HERE.md](prompts/CODEX_START_HERE.md) and
[CODEX_TASK.md](prompts/CODEX_TASK.md). Phase instructions are in
[CODEX_PHASE_2.md](prompts/CODEX_PHASE_2.md), [CODEX_PHASE_3.md](prompts/CODEX_PHASE_3.md) and
[CODEX_PHASE_4.md](prompts/CODEX_PHASE_4.md). Release history is recorded in [CHANGELOG.md](CHANGELOG.md).

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
