# ADR 0005: Availability clocks, conservative labels and isolated paper state

Status: accepted for Phase 4 software/fixture verification.

## Decision

Every historical record has exchange and availability time. Replay reveals it only at availability
time, with deterministic persistence/event ordering and a rolling checkpoint hash. Manifests pin
evidence bytes, coverage, gaps, instruments, code/rule versions and provenance.

Every arm enters at its own actual ready time. Instrument/product, one-based target, expiry and path
identity are validated. Executable quotes use adverse bid/ask, slippage and tick rounding with
contract units, both-side fees and applicable funding. Unordered same-bar paths remain ambiguous;
absent paths remain incomplete.

Research and prospective paper records use SQLite files separate from production market/review/
outbox state. Paper decisions are immutable and persisted before outcomes. Replay cannot call paid
providers, enqueue notifications or place orders. Missing genuine AI assessments are unavailable.

## Consequences

Fixtures verify determinism, arithmetic and fail-closed behavior but not market performance.
Chronological studies keep revisions/arms together, purge overlapping label intervals and preserve
an untouched holdout. Real paper evidence starts only after explicit collection and may contain
declared gaps.
