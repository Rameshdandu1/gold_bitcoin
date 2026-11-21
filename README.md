# Dual AI Market Intelligence — Gold + Bitcoin

**Research-only Windows Server starter.** Independent Gold/BTC short (30m), hourly (60m), and session (240m) candidate detection using **Delta Exchange India** market data; separate GPT and Claude reviews and a fail-closed consensus engine. `CoinGlass` integration is optional and entitlement-aware.

> **Not production ready, not an automatic trader and not evidence of profitable signals.** By default no live data ingestion or paid AI calls happen. Gold token XAUT/PAXG may not be listed at all times; the adapter discovers rather than assumes listings. Options/execution, pre-collection market history, macro news and calibrated probabilities are planned, not already built.

## What is already implemented in this starter
- FastAPI read-only `/api/health`, `/api/engines`, `/api/candidates` endpoints; authenticated production deployment remains operator work.
- Delta India REST product discovery periodically validates live/operational BTC and available
  XAUT/PAXG linear futures/perpetuals, including vanilla notional, settlement, contract value,
  unit currencies and tick size. Existing collectors stay active when the verified symbols do not
  change.
- Public `trades` + incremental `ob_updates` ingestion uses typed UTC event envelopes, rolling
  executed-trade windows, sequence/CRC32 validation and fail-closed book resynchronization.
- Append-only SQLite raw-event/source-status journal with deterministic trade-to-candle replay and
  REST-vs-stream reconciliation helpers. SQLite capacity and retention still require a live soak.
- Unit-tested ATR + closed-candle breakout candidate detectors across six asset × horizon configurations. **These provisional candidates are marked INCOMPLETE and cannot produce a confirmed alert until verified order-flow/quality gates are implemented.**
- Independent typed GPT/Claude adapters, frozen snapshot ID, strict two-provider consensus and fail-closed validation; calls are OFF by default.
- SQLite audit store with duplicate-safe candidate and consensus records, health/data staleness states.
- Optional CoinGlass V4 supported-coins probe; no assumption that subscription includes all endpoints.
- Minimal responsive React dashboard; Windows PowerShell scripts, lint/test CI.

## Requirements
Windows Server 2022 or 2025; PowerShell 7 recommended; Python 3.12 or newer; Node 20+ (only for frontend build); outbound TLS access to provider APIs; Git. **GPU not needed**. Suggested initial VM: 6–8 vCPU, 16 GB RAM, SSD. Production raw market events may require much more storage.

## Setup on Windows Server (PowerShell)

```powershell
# In the downloaded project folder
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
# Edit .env: symbols are discovered; only enable live when you are ready.
python -m pytest -q
python -m uvicorn marketintel.api:app --host 127.0.0.1 --port 8000
```

Check `http://127.0.0.1:8000/docs` and `/api/health`. In another PowerShell window, run the market worker **only after** choosing symbols and setting `LIVE_INGESTION_ENABLED=true` in `.env`:

```powershell
.\.venv\Scripts\Activate.ps1
python -m marketintel.worker
```

The worker polls REST closed candles and durably records validated public trade/order-book events.
Stored executed trades can be replayed deterministically into finalized candles; they do not
reconstruct events from before collection began. Missing/invalid Gold instruments produce
`UNAVAILABLE`/`PARTIAL`, not a substitute symbol or fake signal. The worker's AI evaluation requires
`AI_ENABLED=true`, valid keys and model IDs, but M1 candidates remain `INCOMPLETE` until persisted
candle-reconciliation health has adequate live coverage and is wired into the eligibility gate.

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
- `LIVE_INGESTION_ENABLED=false`, `AI_ENABLED=false`, `TRADING_ENABLED=false`
- `OPENAI_API_KEY`, `OPENAI_MODEL`; `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`
- `COINGLASS_API_KEY`, `COINGLASS_ENABLED=false`, `COINGLASS_BASE_URL`
- `DATABASE_PATH`, `DATA_MAX_AGE_SECONDS`, `MAX_AI_CALLS_PER_DAY`

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
  in-progress bucket.

See `docs/audits/initial-codebase-audit.md` for the measured baseline, live discovery timestamp and
remaining unverified operational work.

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
