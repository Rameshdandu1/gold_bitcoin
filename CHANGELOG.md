# Changelog

All notable changes to this project are documented in this file.

The project uses four-part release versions for shipped milestones.

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
