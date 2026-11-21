# ADR 0002 — Deterministic six-engine signal boundary

- Status: accepted for Phase 2
- Date: 2026-11-21

## Context

The application needs separate Gold and BTC policies for 15–30 minute, one-hour and 2–4 hour
horizons. A candidate must be reproducible from persisted observations without claiming live
accuracy or allowing incomplete data, paid enrichment, language models or future observations to
silently influence the result.

## Decision

Implement six named, immutable configurations: `GOLD_FAST`, `GOLD_HOURLY`, `GOLD_SESSION`,
`BTC_FAST`, `BTC_HOURLY` and `BTC_SESSION`. Each engine has its own primary/context resolutions,
trigger family, freshness limit, flow/book thresholds, target geometry, stop multiplier and expiry.

Every evaluation uses an explicit decision clock and only candles closed and available by that clock. Resampled
context must consist of complete buckets; gaps are never forward-filled. Confirmed pivots generate
HH/HL/LH/LL and BOS/CHOCH without revising earlier pivot decisions. Executed-trade features use the
exact available tail of 500 and 5,000 records and exclude unknown aggressor roles from directional
volume. Book-dependent policies require the Phase 1 sequence/checksum/freshness-validated book.

The feature snapshot is immutable and content-addressed. The stable candidate identity includes the
engine and rule version. Candidate revisions and lifecycle events are append-only; invalidation and
expiry are deterministic and required-source loss closes active candidates fail-safe. Gold target distances are $10/$20/$30; BTC tiers combine configured
percentages and ATR distances. Both are filtered by volatility budget, nearby opposing levels and
minimum reward/risk. They are not probabilities.

CoinGlass is optional, allow-listed and gated by the declared plan. The core detector remains
available when CoinGlass is absent and records that no derivatives claim was used. Gold reference
data is represented by a provider protocol whose production default is unavailable. No synthetic
XAU, DXY, yield or calendar observation is permitted.

Phase 2 terminates after deterministic state/candidate persistence. It cannot call GPT, Claude,
send alerts, create a `CONFIRMED` state or place an order.

## Consequences

- Historical replay can reproduce detector outputs without look-ahead and can suppress duplicate
  candidate identities.
- Missing, stale, corrupt or insufficient observations result in explicit non-candidate states.
- Live accuracy, target hit rate, slippage, fees and profitability remain unmeasured until Phase 4.
- Paid CoinGlass responses and a licensed Gold macro/reference feed remain operational integrations
  that cannot be verified in an offline automated suite.
