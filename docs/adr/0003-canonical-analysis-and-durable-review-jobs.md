# ADR 0003: canonical analysis envelopes and durable review jobs

Status: accepted for Phase 3 development.

## Context

The Phase 2 candidate model had a stable top-level identity but mutable nested evidence and no
recoverable preimage for the snapshot hash. Provider assessments and consensus were keyed only by
candidate ID, so an assessment for revision A could be displayed with revision B. Provider calls
also need bounded retry and spend behavior across process restarts without holding a SQLite
transaction open during HTTP requests.

## Decision

Each review uses one `AnalysisEnvelope` containing the exact candidate revision, full feature
snapshot, verified instrument, frozen price geometry, coverage/provenance, context policy, prompt
version, risk-policy version, and evaluation configuration. Decision prices use canonical decimal
strings. UTC datetimes use one canonical representation. A deterministic encoder sorts object keys,
rejects non-finite numbers, serializes the envelope once, and stores the exact bytes plus a SHA-256
digest kept outside the hash preimage. Both provider adapters receive those same bytes.

Candidate revision identity is separate from the Phase 2 candidate ID and snapshot ID. The current
revision is an explicit projection with a monotonically increasing generation; timestamp ties do
not silently select a revision by hash order. Legacy candidate/snapshot IDs remain valid historical
evidence and are not rehashed in place.

Additive migration `0003_phase3_review_pipeline` creates append-only analysis envelopes, revision-
scoped review runs, leased jobs, provider attempts, consensus decisions, a persistent budget ledger,
and notification outbox. Jobs use short `BEGIN IMMEDIATE` claim transactions, lease owner/expiry,
and fencing generations. A job marked dispatched is not automatically reclaimed as if no paid call
occurred; uncertain dispatch must be recorded explicitly. HTTP calls occur outside database
transactions.

Budget reservations use integer micro-USD estimates and UTC-day accounting. Every provider attempt
requires its own reservation. Missing pricing configuration prevents dispatch; a timeout or unknown
usage remains conservatively reserved until reconciled.

## Consequences

- An approval for one revision cannot attach to another revision.
- Duplicate envelope digests compare exact bytes and reject conflicting content.
- SQLite remains sufficient for the single-host deployment, with bounded worker concurrency.
- Local storage cannot guarantee exactly-once provider billing or external notification delivery;
  dispatch-unknown and receipt-unknown are explicit audit states.
- Legacy assessment/decision tables remain readable for historical compatibility but are not used
  to authorize a Phase 3 confirmation.
