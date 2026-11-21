# Changelog

All notable changes to this project are documented in this file.

The project uses four-part release versions for shipped milestones.

## [0.4.0.0] - 2026-11-21

### Added

- Versioned dataset manifests, source gaps, availability-clock replay and deterministic checkpoint
  resume in an isolated experiment database.
- Arm-specific entry timing, executable quote-side fills, versioned instrument/cost inputs,
  ambiguous/incomplete outcomes, common cohorts and interval-purged folds.
- Immutable write-before-outcome paper state, a bounded default-off worker, authenticated research
  views and checksummed spreadsheet-safe exports.

### Fixed

- Close review findings P3-01 through P3-10 and finalization/deadline/non-ASCII authentication gaps
  while preserving successful and fail-closed paths.

### Evidence and safety

- The committed two-record dataset is a synthetic software fixture. No adequate empirical dataset,
  weeks of paper observation, accuracy or profitability claim exists.
- No paid provider request, real notification, exchange account, order route or deployment was used.

## [0.3.0.0] - 2026-11-21

### Added

- Add canonical immutable analysis envelopes, exact revision identities, additive Phase 3 storage,
  fenced review jobs, provider attempts, UTC budget reservations and atomic notification outbox.
- Add independent concurrent OpenAI Responses and Anthropic Messages structured adapters with
  strict schemas, server-owned metadata and typed failure outcomes.
- Add fresh deterministic consensus gates for lifecycle/revision, executed price, stop/target order,
  source/book quality, spread, drift, costs and reward/risk.
- Add authenticated operator APIs/dashboard, Slack durable delivery, terminal lifecycle alerts,
  readiness/queue/spend views and native Windows backup/recovery scripts.

### Fixed

- Correct incomplete session/previous-day history, repeated BOS/CHOCH identity, late candle
  availability, stop breach/recovery handling, discovery admission and stale lifecycle display.
- Prevent older-revision approval, stale worker leases, duplicated provider slots and obsolete alert
  delivery from authorizing a current confirmation.

### Safety

- Keep live ingestion, AI, CoinGlass and outbound alerts disabled by default. Missing credentials,
  model IDs, pricing, cost assumptions, destination or fresh market facts fail closed.
- No paid provider call, real notification, trading credential, order endpoint or deployment was
  used for this release's development verification. Agreement is not an accuracy/profitability
  claim.

## [0.2.0.0] - 2026-11-21

### Added

- Add six independent Gold/BTC deterministic engines across fast, hourly and session horizons with
  confirmed structure, liquidity, order-flow, order-book and volatility features.
- Add independent Gold $10/$20/$30 and BTC percentage/ATR target, stop, invalidation and expiry
  policies, producing research candidates only.
- Add immutable feature snapshots, candidate revisions, append-only lifecycle events and read-only
  API routes for their audit history.
- Add entitlement-gated CoinGlass BTC OI/funding enrichment and an explicitly unavailable Gold
  reference-provider boundary.

### Changed

- Require exact 500/5,000 trade windows and point-in-time candle availability for historical
  replay; reject future event/receive times and late REST observations.
- Materialize validated order-book checkpoints while keeping the immutable raw event journal as the
  authoritative replay source.
- Make active candidates fail safe during stale/corrupt data, missing instruments, REST failures,
  discovery outages and disabled ingestion.

### Fixed

- Prevent context-bar repeat triggers, post-clock order-book reads, concurrent terminal lifecycle
  transitions and non-positive target prices.
- Validate CoinGlass supported-pair response shape and record actual provider receive timestamps.

### Safety

- GPT, Claude, alerts and all order execution remain disabled in the Phase 2 production path. No
  live accuracy, profitability or provider-availability claim is made.

## [0.1.0.0] - 2026-11-21

### Added

- Discover currently available BTC and tokenized-Gold contracts on Delta Exchange India with
  verified state, notional, settlement, contract size, tick size, and currency units.
- Ingest public trades and incremental order books with typed timestamps, bounded trade windows,
  sequence continuity, CRC32 verification, freshness checks, and fail-closed resynchronization.
- Persist immutable raw market events and source-status transitions in SQLite for deterministic
  trade-candle and order-book replay.
- Reconcile finalized one-minute REST candles with streamed trade aggregation and expose durable
  `WAIT`, `VALID`, `INVALID`, `STALE`, `DISCONNECTED`, and `UNAVAILABLE` health transitions.
- Periodically rediscover product availability without interrupting healthy unchanged collectors.
- Cover positive, malformed, stale, missing, duplicate, out-of-order, outage, reconnect, rate-limit,
  replay, and lifecycle paths with automated tests and documentation-derived fixtures.

### Changed

- Generate and commit the frontend dependency lockfile so CI caching and repeatable installs work.
- Bring existing Python files into compliance with the configured Ruff lint and formatting gates.
- Document the measured baseline, time-bounded live public-feed smoke test, architecture decision,
  and remaining operational soak, retention, backup, and production-readiness gates.

### Fixed

- Prevent stale or crossed order books, inverse/base-settled products, stale/future trades, and open
  candle buckets from entering trusted calculations.
- Preserve WebSocket backoff across invalid snapshots, avoid collector gaps during unchanged product
  refreshes, and keep database writes from blocking the async receive loop.
