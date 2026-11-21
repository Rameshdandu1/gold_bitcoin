# Phase 2 verification — six deterministic engines

Date: 2026-11-21

## Phase 1 review

Pull request #1 remained open and was not merged. Its GitHub Actions run completed successfully, and
the Phase 2 branch was created from the Phase 1 feature head so the market-data work remains in its
history. Local verification passed all 66 tests present at that head, Ruff lint/format, Python
compilation, frontend type checking and the production frontend build.

The Phase 1 collector was also extended with negative coverage for immediate non-429 REST 4xx
failure, malformed success envelopes, corrupt WebSocket JSON, unknown WebSocket frames and the
documented 429 cooldown. These checks do not replace a long-running live-feed soak.

## Phase 2 verified implementation

- Six named engine configurations with independent clocks, thresholds, target/stop and expiry rules.
- Closed/contiguous candle validation, complete-bucket resampling and no forward filling.
- Confirmed HH/HL/LH/LL pivots, BOS/CHOCH, sweep/reclaim, breakout/retest and false-breakout rules.
- Exact 500/5,000 executed-trade windows, classified buy/sell flow, CVD and labelled contract/base/
  quote quantities; unknown aggressors do not become directional evidence.
- Sequence-validated book depth imbalance and absorption proxy, plus ATR, UTC-day candle-volume VWAP proxy,
  relative volume, range expansion, regime and near-term opposing levels.
- Gold $10/$20/$30 and BTC percentage/ATR target feasibility with deterministic invalidation and
  expiry.
- Entitlement-gated optional CoinGlass BTC OI/last-closed funding context, and a fail-closed Gold
  reference provider contract.
- Immutable candidate revisions, append-only lifecycle events and point-in-time historical replay
  with explicit candle availability, trade/book event and receive clocks, and duplicate suppression.
- Fail-safe lifecycle sweeps during missing instruments, REST failures, discovery outages and
  disabled ingestion, plus atomic single-winner terminal transitions.
- A hard Phase 2 boundary that does not invoke GPT, Claude, alerts or order execution.

## Automated results

The completed local Phase 2 run passed 126 tests. The suite includes all six engines in bullish,
bearish and historical-replay cases, plus false breakouts, stale/missing/corrupt inputs, duplicate
signals, invalid lifecycle transitions and no-look-ahead behavior. Ruff lint/format, Python bytecode
compilation, frontend type checking and the frontend production build also passed.

## Unverified external behavior and limitations

- No paid CoinGlass request was made. Actual plan permissions, quota, response shape, exchange
  coverage and commercial license must be validated with the operator's subscription.
- No licensed XAU/USD, DXY, Treasury-yield or economic-calendar provider is configured. Gold
  engines explicitly mark token-market-only evidence and make no spot-basis or macro claim.
- No claim is made for hit rate, forecast accuracy, profitability, option economics, fees or
  slippage. Those require purged walk-forward research and paper trading.
- No automatic trading or real order path exists or was exercised. AI confirmation remains disabled
  in Phase 2.
- SQLite raw-event throughput, retention, backup/restore and Windows service restart behavior still
  require a measured operational soak.
- Delta REST candle responses are used with a recorded in-memory availability time, but their raw
  payloads are not yet journaled. Durable replay before collection began remains impossible.
