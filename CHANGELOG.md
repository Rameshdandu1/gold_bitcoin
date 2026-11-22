# Changelog

All notable changes to this project are documented in this file.

The project uses four-part release versions for shipped milestones.

## [0.6.0.0] - 2026-11-22

### Added

- Preserve provider completion/availability, quote availability and evidence-mode provenance through
  arm decisions, outcomes, authenticated views and exports; reject incompatible manifest/provider modes.
- Add cadence-driven source-risk scheduling and a public connected bounded paper workflow that
  derives simulated outcomes from later normalized observations for all six Gold/BTC engines.
- Add additive Phase 6 dispatch evidence migration, versioned research outcomes, consumed-prefix
  paper progress and central holdout-aware read projections.
- Add one shared clock-injected production/research application policy, durable derived-workflow
  checkpoints and bounded 500-event public research/paper processing.

### Fixed

- Refresh alert risk/authorization clocks, align trade snapshot cutoffs with evidence tokens and
  recheck freshness/lease/expiry inside the dispatch transaction.
- Quarantine legacy jobs lacking complete frozen request policy before any provider call.
- Reject missing pre-entry anchors, quote gaps and non-contiguous OHLC paths; use factual
  availability for readiness/fills and propagate source outages as abstentions/incomplete outcomes.
- Commit paper events and progress atomically, recover identical late retries, and detect same-size
  consumed-file replacement before success.
- Withhold protected and boundary-crossing holdout outcomes from ordinary authenticated reads until
  the explicit final-evaluation access record exists.
- Close P6-01 through P6-05: align book authorization with event-time freshness, reject conflicting
  availability clocks, enforce complete pre-entry coverage, protect paper-derived holdout data and
  persist unavailable/expired arms with truthful resumable progress.

### Evidence and safety

- Verification uses zero-network `SYNTHETIC_FIXTURE` streams, archived fake provider rows and fake
  notification transports. Connected paper results are `SIMULATED_PROSPECTIVE`, not elapsed forward
  observation or empirical performance.
- Shared-policy parity, complete derived-workflow checkpoint/resume and bounded public processing
  are verified offline. Licensed data, genuine provider access, destination Windows recovery and
  external soaks remain unverified.
- Live ingestion, AI, alerts and paper collection stay disabled by default. Orders remain absent and
  `TRADING_ENABLED=true` remains refused.

## [0.5.0.0] - 2026-11-21

### Added

- Add a shared bounded research processor that invokes all six production detectors from
  availability-ordered observations, freezes four-arm decisions, and derives quote-side outcomes
  from an immutable isolated journal.
- Add canonical manifest/configuration identities, prefix-validated bounded checkpoints,
  conflict-detecting research records, protected holdout access, operational abstention accounting,
  and authoritative checksummed exports.
- Add source-bound prospective paper decisions/outcomes with write-before-entry chronology,
  restart/truncation/generation checks, plus authenticated experiment, engine, opportunity and paper
  transition views.
- Add deterministic Gold/BTC synthetic workflow generation and end-to-end acceptance through the
  real FAST, HOURLY and SESSION detectors for each asset.

### Fixed

- Recheck the complete current-risk policy at notification delivery and transaction-fence dispatch
  against revision, lifecycle, locally persisted market evidence, expiry and a valid lease.
- Prevent terminal or configuration-drifted reviews from spending provider budget; freeze complete
  request configuration and terminalize expired saved-result recovery without redispatch.
- Prevent pre-entry stop recovery, quote gaps, partial boundary bars, future training rows and
  holdout-crossing labels from producing unsupported outcomes or validation results.

### Evidence and safety

- Software acceptance uses generated `SYNTHETIC_FIXTURE` observations only. It establishes no
  accuracy, probability, profitability, licensed-data coverage or elapsed prospective duration.
- Live ingestion, paid AI, alerts and paper collection remain disabled by default;
  `TRADING_ENABLED=true` remains refused. No paid request, real notification, order or deployment
  was performed.

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
