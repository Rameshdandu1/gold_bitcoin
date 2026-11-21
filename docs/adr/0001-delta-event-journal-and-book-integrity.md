# ADR 0001: Append-only Delta event journal and fail-closed incremental book

- Status: Accepted for M1
- Date: 2026-11-21

## Context

The starter kept public trades and periodic L2 snapshots only in memory. It could not prove what
was received, replay a restart, detect an incremental packet gap, or reproduce closed candles.
Delta's documented compact public feed provides executed `trades` and `ob_updates` with an initial
snapshot, sequence number and CRC32 checksum.

## Decision

1. Normalize each accepted public message into a versioned envelope while preserving the verbatim
   JSON payload and separate exchange event, exchange publish and local receive times.
2. Use a deterministic payload hash as the event ID and persist with `INSERT OR IGNORE`.
3. Store events in SQLite WAL with a UTC-day logical partition key and indexes. Database triggers
   reject update/delete operations on raw events and source-status history.
4. Build books only from `ob_updates`. Require a fresh snapshot, `seq + 1`, documented top-10 CRC32,
   at least one bid and ask, and a non-crossed book. Any violation invalidates and clears the book;
   it cannot recover except through another valid snapshot.
5. Replay events by event time plus deterministic tie-breakers. Trade aggregation emits only fully
   closed, resolution-aligned candles and never interpolates missing intervals.

## Consequences

- Restart/replay and fixture-based packet-loss tests are possible without private credentials.
- Duplicate delivery is idempotent and late trades are deterministically ordered for replay.
- SQLite is acceptable for the narrow single-host M1 slice, not assumed sufficient for sustained
  high-frequency production L2 throughput. A measured soak, retention policy, backups and likely
  PostgreSQL/partition migration remain before production-scale collection.
- A book may be unavailable more often, which is intentional: unknown integrity fails closed and
  cannot make a candidate eligible.
