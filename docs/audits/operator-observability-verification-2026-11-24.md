# Operator observability and live-data reliability verification

Date: 2026-11-24 (Asia/Kolkata)  
Implementation branch: `feature/live-market-intelligence-completion`  
PR #19 tested head: `9949856969ed36915251ca448bb28a556ce33ee7`  
PR #19 merge commit: `24412fefd696efde095d1fcbde61d39226d2c1d4`

## Safety and scope

- The existing local `.env`, provider keys, operator credentials, databases, and collection history
  were not copied, printed, overwritten, or committed.
- No paid OpenAI or Anthropic request was made. The prior stored Anthropic invalid-assessment result
  was inspected only through persisted metadata and was not retried.
- No Slack message or other external notification was sent.
- `TRADING_ENABLED=true` remains refused; this change adds no account, order, leverage, or execution
  functionality.
- CoinGlass remains disabled until key, entitlement, and endpoint support can be verified separately.

## PR #19 integration

The feature branch was reviewed, updated with current `main`, and its README conflict was resolved
without discarding either the controlled-live-validation material or the operator-observability
material. Focused integration checks reported 67 passing tests. TypeScript checks and the production
frontend build passed. The final tested head was merged as PR #19; this follow-up branch starts from
the resulting merge commit.

## Reproduced live findings before correction

Read-only inspection of the existing live database showed verified `BTCUSD` and `XAUTUSD`
discovery, current trades, valid order books, and fully classified 500/5,000-trade windows for both
assets. Both markets were nevertheless `DEGRADED` because candle reconciliation remained invalid.
All six engines were `WATCH`, with the following factual detector reasons:

- FAST: no confirmed sweep/reclaim or breakout follow-through;
- HOURLY: no closed breakout/retest or rejection trigger;
- SESSION: no newly confirmed higher-timeframe BOS/CHOCH.

Those are legitimate no-trigger dispositions, not service failures. No detector threshold or
validation gate was bypassed.

The last 5,000 persisted events per stream had these event-to-receipt latency measurements before
the correction:

| Stream | p50 seconds | p95 seconds | p99 seconds | maximum seconds | over 10 seconds |
| --- | ---: | ---: | ---: | ---: | ---: |
| BTC book | 1.217 | 7.899 | 9.493 | 60.662 | 18 |
| BTC trades | 2.627 | 9.418 | 10.583 | 13.377 | 121 |
| XAUT book | 1.895 | 8.213 | 9.778 | 13.149 | 26 |
| XAUT trades | 3.114 | 9.301 | 10.717 | 13.228 | 120 |

Two application defects explained the reliability symptoms:

1. The WebSocket receive loop awaited a new SQLite transaction per frame and a checkpoint write per
   book update. Frames could wait in the client socket before normalization stamped receipt time,
   producing stale-event reconnects under local disk latency.
2. Reconciliation required the entire rolling 65-minute interval to be continuously connected. A
   reconnect therefore forced `WAIT` for up to 65 minutes even after later fully covered candles
   were available.

## Corrections

- The validated stream now feeds a bounded, ordered persistence queue. A consumer writes raw events
  in transactional batches and materializes book checkpoints only after those events are durable.
  Queue exhaustion invalidates the stream and restarts fail-closed; frames are not dropped.
- Source-status ordering is monotonic even when Windows returns the same wall-clock timestamp.
- Candle reconciliation selects the continuously connected suffix ending at the latest closed
  minute, rounds a reconnect forward to the next complete minute, and compares only that factual
  suffix with REST. Missing stream candles, missing REST candles, value mismatches, source loss, and
  stale books still invalidate eligibility.
- Migration `0007_operator_observability` adds the bounded REST-candle lookup index used by the
  authenticated chart endpoint.
- Authenticated operator APIs now provide factual candles/daily values and a read-only secret-safe
  configuration projection.
- The frontend now provides Market Overview, Order Flow, AI Consensus, Settings, and System Health
  pages. Charts use only closed persisted candles at 1m/5m/15m/1h; incomplete daily fields and
  missing calculation evidence remain explicitly unavailable.
- Provider views expose stored requested/returned models, status, failure code, latency, structured
  assessment, counter-evidence, and data warnings. Slack remains optional for dashboard-only review.

## Structured-provider investigation

The merged adapters use the current structured-response shapes: OpenAI Responses parsing with a
Pydantic format and Anthropic Messages `output_config.format` with a JSON schema, followed by local
Pydantic validation. The previously stored Claude attempt failed strict assessment validation; it
is preserved as evidence. Connectivity is not claimed from configuration or software tests, and no
new paid request was authorized or made in this work.

## Automated verification

Commands were run from this implementation worktree. The restricted desktop sandbox cannot use the
default Windows user temp directory for SQLite sort files, so the full test run set `TEMP` and `TMP`
to a worktree-local temporary directory. A previously failing public-workflow test passed under that
boundary, confirming the initial 27 identical `unable to open database file` errors were an
environment limitation rather than product failures.

| Check | Result |
| --- | --- |
| `python -m pytest -q -p no:cacheprovider` | 288 passed; one existing Starlette/httpx deprecation warning; 856.16s |
| Focused market worker/operator tests | 18 passed |
| `python -m ruff check .` | passed |
| `python -m ruff format --check .` | 108 files already formatted |
| `python -m compileall -q src tests` | passed |
| `git diff --check` | passed |
| `npm run typecheck` | passed |
| `npm run test:browser` | 2 passed in 7.4s using recorded API fixtures |
| `npm run build` | passed; 33 modules; JS 263.71 kB (79.17 kB gzip); CSS 12.61 kB |

The browser scenarios cover chart/timeframe navigation, daily statistics, order-flow values, AI
failure/latency evidence, secret-safe settings, health/readiness views, and an explicit candle-
unavailable state. They use local recorded fixtures and do not establish live-provider availability.

## Live restart and browser verification

Live post-restart observations are recorded below after the tested migration and services are
started. This section must not be interpreted as a long-duration soak or empirical signal result.

The tested worker was started against the preserved local `.env` and 1.3 GB database. The API was
started from the same implementation while serving the rebuilt frontend. The new migration and
index were confirmed in that database before operator reads were performed.

Delta public product discovery and every requested candle page returned HTTP 200. Discovery
verified `BTCUSD` and `XAUTUSD`. Authenticated candle reads returned up to 240 bars for 1m and 5m,
152 bars for 15m, and 38 bars for 1h for each asset at the observation time; both UTC daily-stat
states were `AVAILABLE`.

After a restart, reconciliation correctly reported `WAIT` until the first complete clock-aligned
minute was available. It then converged for both assets to `VALID` with
`matched=1; missing_stream=0; missing_rest=0; mismatched=0`. Both 500- and 5,000-trade windows were
complete and classified. The final authenticated readiness read returned HTTP 200 with every gate
passing; both market summaries were `HEALTHY` with fresh valid books.

The final six engine dispositions were fresh and factual:

- `GOLD_FAST`: `WATCH` — trigger opposed the latest 5m structure break;
- `GOLD_HOURLY`: `WATCH` — no closed breakout/retest or rejection trigger;
- `GOLD_SESSION`: `WATCH` — no newly confirmed higher-timeframe BOS/CHOCH;
- `BTC_FAST`: `WATCH` — no confirmed sweep/reclaim or breakout follow-through;
- `BTC_HOURLY`: `WATCH` — no closed breakout/retest or rejection trigger;
- `BTC_SESSION`: `WATCH` — no newly confirmed higher-timeframe BOS/CHOCH.

These statuses are detector outcomes, not predictions or accuracy claims. During the first short
run, Delta delivered one XAUT book event 13.086 seconds old. The collector correctly disconnected,
invalidated books, reconnected, and held reconciliation at `WAIT` until a fully covered new minute
closed. This was not bypassed. Browser QA also exposed a separate monitoring race: an XAUT frame
could arrive while a BTC health record was being persisted and then be compared with the older BTC
clock. Commit `5745219` captures the clock immediately before each synchronous symbol-quality read.
Its concurrent regression passed; after restart there were zero
`received_after_evaluation_clock` health records.

The post-fix sample after the final restart contained 2,666 events:

| Stream | events | p50 seconds | p95 seconds | p99 seconds | maximum seconds | over 10 seconds |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| BTC book | 524 | 1.175 | 2.630 | 3.580 | 4.189 | 0 |
| BTC trades | 461 | 1.504 | 3.298 | 4.241 | 4.458 | 0 |
| XAUT book | 854 | 1.171 | 2.748 | 3.646 | 4.404 | 0 |
| XAUT trades | 827 | 1.486 | 3.166 | 3.798 | 4.428 | 0 |

This is a short operational sample, not a sustained-latency guarantee. The live browser verified
the candlestick chart and daily statistics, complete 500/5,000 order-flow calculations, the AI
disabled/budget state, secret-safe settings, Slack-optional state, all readiness gates, and explicit
`WAIT`/`WATCH` details. No live candidate existed during the observation, so provider review cards
correctly showed no recorded attempt rather than inventing evidence. OpenAI, Anthropic, CoinGlass,
Slack, private Delta APIs, and trading endpoints were not called.

## Remaining limitations

- A longer Windows live-collection soak is still required to characterize reconnect frequency and
  tail event latency under sustained operation.
- A future Anthropic paid smoke retry requires separate authorization. OpenAI and Anthropic model
  availability are not inferred from configured IDs.
- CoinGlass entitlement/API support and external notifications remain unverified and disabled.
- Existing historical proposals and model reviews are not current trade authorization.
- No signal accuracy, probability, profitability, or prospective-paper performance is claimed.
