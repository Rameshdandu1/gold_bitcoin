# Phase 4 verification — integration corrections and research infrastructure

Status: **IN PROGRESS**. This report separates software/fixture verification from empirical market
evidence. No fixture result is a performance claim.

## Recorded starting point

- Starting code: `d1978d30e48c0b8656d969da00ea70a7e4659562` (`main`, Phase 3 merge).
- Phase 4 instruction and independent-review revision:
  `6d12184c60b0a877d80500b0e3340f905687b2a7`.
- Implementation branch: `feature/phase-4-evaluation-and-paper-research`.
- Documentation carry commit: `e201f70` because PR #5 was open when implementation began.
- Starting checks: 171 Python tests passed; Ruff lint and format, Python compilation, frontend
  dependency installation, TypeScript typecheck and the production build passed. The first Vite
  build was denied by the managed Windows sandbox's parent-directory access policy; an authorized
  workspace-access rerun passed.

## Dependency-ordered implementation plan

1. **4A:** reproduce P3-01/P3-02/P3-03/P3-05 first, then correct P3-01 through P3-10 plus the
   finalization/deadline/authentication acceptance gaps. Preserve positive and fail-closed paths.
2. **4B:** add versioned manifests, isolated availability-driven replay and deterministic
   checkpoint/resume with explicit source coverage.
3. **4C:** add arm-specific eligible entry, instrument/target/path validation and versioned
   executable-side cost semantics while preserving ambiguous and incomplete outcomes.
4. **4D:** compare four arms on common opportunities with honest denominators, timing/cost and
   interval-aware chronological purging.
5. **4E:** add a separate prospective paper ledger with write-before-outcome and restart/gap safety.
6. **4F:** add authenticated research views, reproducible CLI/export commands and Windows guidance.

Live ingestion, AI dispatch, outbound alerts and paper collection remain disabled by default.
`TRADING_ENABLED=true` remains refused. Development verification will use only hypothetical
fixtures and fake/recorded transports.

## Baseline and final verification

Final results will be recorded after implementation.

## Review findings and regression evidence

Pending implementation.

## Dataset coverage and empirical limitations

No adequate real historical dataset or weeks of prospective paper observations were present at the
start of this phase. Until genuine as-observed evidence is collected, the empirical gate remains
`INSUFFICIENT_EVIDENCE`.

## External calls, messages and Windows checks

Pending final accounting. The expected development count is zero paid model calls and zero real
messages.
