# Phase 4 verification — integration corrections and research infrastructure

Status: **SOFTWARE/FIXTURE COMPLETE; EMPIRICAL EVIDENCE INSUFFICIENT**. Passing software tests and
synthetic outcomes are not accuracy, probability, edge or profitability claims.

## Recorded revisions

- Starting code: `d1978d30e48c0b8656d969da00ea70a7e4659562` (`main`, reviewed Phase 3).
- Instructions/review: `6d12184c60b0a877d80500b0e3340f905687b2a7`.
- Documentation carry: `e201f70`; PR #5 was open when implementation began.
- 4A correction commit: `409e4cb`.
- Implementation branch: `feature/phase-4-evaluation-and-paper-research`.

## Baseline and final checks

The reproduced baseline was 171 passing Python tests, Ruff check/format, compilation, frontend
dependency installation/typecheck/build and `git diff --check`. The first Vite build was denied by
the Windows sandbox parent traversal policy; a scoped authorized rerun passed.

Final verification on 2026-11-21:

- `python -m pytest -q`: **206 passed**, with one pre-existing TestClient deprecation warning.
- `python -m ruff check .`, `python -m ruff format --check .`,
  `python -m compileall -q src tests` and `git diff --check`: **passed**.
- `npm ci`, `npm run typecheck` and `npm run build`: **passed**. The build used the same scoped
  esbuild sandbox allowance on this workstation.
- Fixture CLI: `validate-data` accepted 2 records; replay wrote 4 points with rolling hash
  `1a212bf0522768717c6359b33b42f59e2fae37d4d92bac360866fdb525355ee1`. The example paper
  worker returned `DISABLED` and recorded zero rows.

## 4A findings corrected

- **P3-01:** blank optional rates load as `None`; risk decimals reject non-finite/negative values.
- **P3-02:** reconciliation aligns to closed minutes and requires interval-start source coverage.
- **P3-03:** exact canonical request wrapper/digest reaches both providers and token admission covers
  wrapper, prompt and schema.
- **P3-04:** material proposal identity excludes poll-only observations; atomic admission deduplicates
  unchanged work and supersedes/queues changed revisions.
- **P3-05:** trade/book reads and eligibility identity share one SQLite snapshot; persisted trade
  generation and full book payload invalidate stale commits, including older-timestamp inserts.
- **P3-06:** confirmation alerts recheck source/trade/book/price state; terminal alerts bypass it.
- **P3-07:** complete bounds reject oversized requests pre-dispatch; reservations plus actual settled
  spend enforce limits.
- **P3-08:** configured destination matching and durable `DISPATCH_STARTED` prevent blind resend
  after acceptance-unknown cancellation; known pre-acceptance transient failure can retry.
- **P3-09:** queued/current model IDs and successful provider finish reasons must match.
- **P3-10:** latest chronological confirmed high/low state determines continuation/reversal.
- Finalization persists `RESULTS_READY`, rehydrates without provider redispatch, and atomically
  commits decision/outbox/job completion with lease/deadline/expiry fencing. UTF-8 byte comparison
  safely handles non-ASCII Basic credentials.

No finding was closed by weakening a successful or fail-closed path. Real-provider Retry-After and
provider-side cancellation timing remain external acceptance, not fixture proof.

## 4B–4F implemented evidence

- Manifests/configs cover data mode, provenance/license, hashes/counts, instrument validity/units,
  source coverage/gaps, code/rule/feature versions and costs.
- Availability-clock replay has deterministic ties/checkpoints. A bounded-batch temporary SQLite
  spool externally orders large evidence files and emits progress without retaining all records in
  memory. Corrections wait for arrival, gaps are unavailable, and restart/full hashes match.
- Research state is isolated from production; an equal database path is rejected.
- Outcomes use each arm's ready time, original target, active product, expiry and executable path.
  Bid/ask, adverse slippage/tick rounding, multiplier, quantity, fees and funding are explicit.
  Bullish BTC, bearish Gold, expiry equality, wrong product, missing path and bar ambiguity are tested.
- Four arm identities share an opportunity contract. Missing genuine AI remains unavailable in the
  denominator. Actual latency/cost persists. Folds group revisions/arms and purge overlapping label
  intervals plus embargo. Small samples and zero-loss profit factor are insufficient/undefined.
- Paper state writes immutable per-arm decisions before terminal outcomes and preserves cursors/gaps.
  Collection is disabled by config and environment.
- The authenticated API/dashboard shows `NOT_STARTED`/`EXPLORATORY`. CLI commands validate, replay,
  evaluate and report with JSON/exit codes, atomic checkpoints, pathlib, safe CSV and checksums.

## Dataset and empirical limits

Only `tests/fixtures/research` was created: two synthetic BTC records across three declared minutes.
It verifies software only. There is no adequate real Gold/BTC dataset, macro/context history,
genuine historical model assessment, untouched empirical holdout, regime sample, weeks of forward
paper observation or meaningful cohort. No empirical arm metric is reported; the gate remains
`INSUFFICIENT_EVIDENCE`.

## External and Windows accounting

- Paid OpenAI: **0**; Anthropic: **0**; CoinGlass: **0**; Phase 4 Delta live calls: **0**.
- Slack/other real messages: **0**. Orders, exchange credentials, leverage and deployment: **none**.
- Locally verified on Windows: Python checks, fixture CLI/checkpoint, disabled paper invocation,
  frontend install/typecheck/build and PowerShell-compatible paths.
- Not verified: destination Windows Server tasks/reboot/recovery, capacity/restore, long collection,
  provider entitlement/pricing, Slack acceptance or live market soak.

## Next evidence milestone

Independently review Phase 4. Then acquire/licence as-observed data, freeze a manifest/holdout,
collect genuine assessments prospectively with explicit gaps for several weeks across regimes, and
run the documented Windows/operator smoke tests under separate authorization. Execution remains out
of scope.
