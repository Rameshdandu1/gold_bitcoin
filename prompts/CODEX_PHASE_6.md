# CODEX TASK — Phase 6: evidence integrity and complete workflow acceptance

## Objective

Close **P5-01 through P5-07** in the [independent Phase 5 review](../docs/audits/phase-5-independent-review.md), preserve verified corrections, and demonstrate one trustworthy Gold/BTC observation-to-decision-to-paper-outcome workflow through the public interfaces. This phase continues the existing Windows research application. It does not add derivatives or execution.

The reviewed implementation now produces real detector-backed fixture opportunities. Its remaining problems are concrete: stale authorization clocks, lost evidence availability/provenance, incomplete shared risk/lifecycle logic, incomplete path coverage, paper crash/file-identity handling, unprotected holdout detail reads and legacy job preflight. Fix those contracts before expanding features.

## 1. First instructions — inspect, reproduce, then implement

1. Read `AGENTS.md`, `DESIGN.md`, `README.md`, `docs/IMPLEMENTATION_PLAN.md`, `docs/audits/phase-5-independent-review.md`, this task and the relevant code/tests. Read `prompts/CODEX_PHASE_5.md` for continuing integration requirements. Historical verification reports record what was tested; later independent findings qualify their acceptance claims.
2. Inspect the working tree, remotes, branch and recent commits. Preserve unrelated changes. Fetch main and compare with reviewed commit **`dfbb59ea91bfc034f4ab4ffa76c0dbda094f5a31`**. PR #8 implemented Phase 5. If newer fixes exist, reproduce the finding before changing them.
3. If these instructions are not yet on main, fetch the docs branch explicitly:

   ```bash
   git fetch origin refs/heads/docs/phase-6-review-and-instructions:refs/remotes/origin/docs/phase-6-review-and-instructions
   git show origin/docs/phase-6-review-and-instructions:prompts/CODEX_PHASE_6.md
   git show origin/docs/phase-6-review-and-instructions:docs/audits/phase-5-independent-review.md
   ```

4. Create `feature/phase-6-evidence-integrity` from current main, using an isolated worktree when needed. Carry only the relevant review/instruction documentation if main lacks it. Do not merge unrelated work, reset another contributor's changes or rewrite earlier verification reports.
5. Record starting code and instruction SHAs. Reproduce the **227-test** baseline, Ruff, compilation and frontend checks. Test counts are observations, not targets: never delete or weaken a meaningful regression to keep a count or green build.
6. Reproduce the seven findings using maintainable repository fixtures and real public/store/worker paths. Use the review's counterexamples rather than depending on temporary reviewer scripts. Confirm a failing assertion for each changed core contract before the fix.
7. Record a short dependency plan and implement the slices below in order. Separate corrective PRs are acceptable; continue through the authorized scope. Push reviewable commits and open PRs without auto-merging or deploying.

**First deliverable:** a concise reproduced-baseline/finding matrix and the initial corrective commit. Do not spend the first milestone redesigning the UI, replacing the stack, choosing new models or tuning strategy thresholds.

## 2. Boundaries and coding rules

- Preserve native Windows Server support, Python/FastAPI, React/TypeScript and isolated SQLite research/paper stores. No new infrastructure dependency is justified by these fixes alone.
- Preserve all six engines: Gold/BTC × FAST30, HOURLY60 and SESSION240. Gold targets remain underlying-unit dollar distances; BTC remains percentage/ATR based. Hypothetical economics must use the correct versioned product multiplier and currency.
- Keep live ingestion, paid AI, alerts and paper collection disabled by default. Keep `TRADING_ENABLED=true` rejected. No order, account, position, leverage or trading-key functionality.
- Do not run paid APIs, real notifications or deploy as part of these corrections. Use existing local recordings and explicit fixtures. Document externally blocked acceptance instead of fabricating successful evidence.
- Continue independent GPT and Claude assessment of the same immutable canonical facts. Dual agreement is an analyst filter, not measured accuracy, a calibrated probability or permission to skip risk rules.
- Use typed contracts, timezone-aware UTC clocks and `Decimal` for monetary boundaries. Distinguish exchange event, provider completion, receipt/availability, persistence, evaluation, authorization and hypothetical fill times.
- Inject a callable clock into time-sensitive services. Tests must be able to advance it between claim, read, retry, lock acquisition and authorization. A single fixed `now` parameter is not sufficient to prove a running worker remains current.
- Keep database write transactions short and free of network I/O. Use bounded retries and typed terminal dispositions. Do not promise remote exactly-once delivery.
- Immutable identity includes scientific policy and provenance. Identical retry is a no-op preserving original timestamps; conflicting bytes under one identity fail explicitly. Never repair an old result by silently overwriting it.
- Add explicit migrations for persisted contract changes. Validate upgrades with actual old-format state, not only fresh databases. Preserve prior outcomes/audits and version corrected evaluation results.
- Prefer a small shared policy/application service over a parallel implementation. Separate market-risk policy from simulation transport/output configuration so research does not need a real Slack destination to evaluate otherwise valid market evidence.
- Add tests for observable behavior. Expected output must come from specified external facts or hand calculations, not a second invocation of the same production helper. Keep secrets, licensed raw data and generated runtime databases out of git.
- Report precisely what is completed, blocked and unverified. A passing positive fixture cannot close a failure/recovery acceptance gate it never exercised.

## 3. Slice 6A — fresh authorization and safe upgrades

Addresses **P5-01 and P5-07**. Preserve the working spread/drift gate, transaction token fence, current-format frozen request checks and saved-result recovery.

### Alert clock and evidence fence

1. Give the alert worker and authorization boundary an advancing, injectable clock. Capture fresh time for each evidence evaluation; distinguish claim time from authorization time.
2. Ensure the evidence token and evaluated facts describe the same relevant persisted evidence. An event newer than the evaluation cutoff must cause a retry/suppression, not appear only in the token while being omitted from risk facts. Specify deterministic event/receipt cutoff rules.
3. After acquiring the authorization transaction, check current lease ownership/generation, actual lease time, candidate expiry and time-dependent source freshness. If evidence or time has invalidated the evaluated snapshot, fail closed or reread with a fresh clock under a bounded retry policy.
4. Persist the actual authorization timestamp and evidence identity. Keep the network send outside the transaction. Preserve `DISPATCH_STARTED`/unknown-delivery recovery behavior and destination immutability.

Two mandatory advancing-clock cases:

- Worker starts 10:01:00; a normally timestamped stop arrives at 10:01:00.600 before authorization. Both initial and retry paths must produce zero transport calls after that stop becomes locally available.
- Worker starts 10:29:59, expiry is 10:30:00, authorization is attempted at 10:30:01. Suppress. Also test a pause beyond a 30-second lease without a competing worker or any data mutation.

Include lock-delay/source-aging and evidence-arrival-between-clock-capture-and-read cases. Do not claim these local tests cover exchange events the application has never received.

### Legacy review admission

1. Apply terminal lifecycle, active revision, lease, deadline and required-source checks to every dispatchable job, regardless of request configuration version. Recheck before each paid attempt/retry.
2. Define a migration/disposition for queued legacy requests missing complete frozen policy. Quarantine/terminalize with a typed audited reason unless all required historical fields can genuinely be reconstructed. Do not fill missing policy from current runtime defaults under the old run identity.
3. Reuse valid saved results without redispatch when permitted; retain the existing durable expired-results disposition and budget accounting.

Two upgrade examples: a real Phase 4 database with an invalidated pending candidate must make zero calls after migration; an otherwise active legacy request lacking a frozen output/prompt policy must be explicitly migrated or retired, never silently executed under today's configuration.

**6A gate:** fresh and legacy databases pass positive, advancing-clock, concurrency and recovery tests using real workers/stores and fake transports. No external calls are required.

## 4. Slice 6B — preserve availability, provenance and complete paths

Addresses **P5-02 and P5-04**. Migrate research contracts and version the evaluator as needed; do not rewrite existing results in place.

### Availability and archived assessment identity

1. Preserve exchange/event time and local receipt/availability for every quote and provider completion. Keep durable observation IDs, persistence order and evidence-mode provenance in derived records.
2. Define provider readiness as no earlier than the matching result's factual availability and applicable current-risk decision. Dual readiness cannot precede either required result. Apply configured post-decision entry latency exactly once; provider duration remains diagnostic.
3. Never backdate a fill to an unavailable quote. Document a conservative executable-quote policy including maximum event age, source continuity, validated book state and arrival time. Late historical quotes may support only conclusions justified by the declared data mode; they do not authorize an earlier simulated decision/fill.
4. Validate candidate/revision, target, request/configuration digest, actual provider/model identity, prompt/schema/policy version and evidence classification to the extent required by the declared study. Unknown contemporary model evidence remains unavailable or explicitly exploratory.
5. Enforce compatibility between manifest mode and row-level provenance. Retain provenance in arms, reports, API/UI and exports. Reject conflicting fixture/prospective labels or segregate/downgrade the affected arm explicitly; never upgrade evidence because the manifest label says so.
6. Distinguish simulated market time from actual database write time. Historical replay may record a simulated readiness timestamp, but it must not present that as a genuine contemporaneous persistence proof.

Two mandatory timing examples: delaying every entry quote by 120 seconds must eliminate the fixture's original +4-second fill; delaying both model results by 120 seconds must eliminate its original +3-second dual readiness and +4-second entry.

Two mandatory provenance examples: prospective-labelled data with explicitly synthetic completions must not yield prospective AI-arm evidence; recorded market data with retrospective LLM analysis must retain the retrospective classification through export.

### Coverage and outcome semantics

1. Establish source coverage from candidate observation through effective entry, then through the outcome/expiry. Require a valid starting anchor and reject undeclared/unobserved gaps that could hide terminal invalidation.
2. Support sparse book changes only if source sequence/heartbeat evidence proves a continuous valid book and the declared age policy allows carrying it forward. A list containing two quotes is not proof of continuous source coverage.
3. For OHLC evidence, validate contiguous intervals and interval boundaries. Preserve ambiguity when entry/expiry cuts a bar or target/stop ordering cannot be determined. Do not infer intervening prices.
4. Preserve corrections already made for known pre-entry breaches, post-entry gaps, expiry equality, rejected arms and instrument validity. Unknown evidence is `INCOMPLETE`/`AMBIGUOUS`, not a completed win or a known zero-position result.
5. Keep long ask-entry/bid-exit and short bid-entry/ask-exit economics, adverse tick/slippage treatment and versioned quantity/multiplier/fee/funding policy. Retain hand-calculated positive examples in both directions.

Two mandatory missing-path examples: a 150-second unobserved pre-entry interval under a 10-second gap policy cannot produce a complete target; readiness +30 with only a +170-to-180 OHLC bar cannot produce a complete target. Exercise both directions and absence of any initial anchor.

**6B gate:** public `validate-data`/`run-workflow` reject or correctly classify delayed, contradictory and incomplete evidence; all derived/API/export records retain the accepted clocks and provenance. Valid continuous controls still execute according to their frozen policy.

## 5. Slice 6C — complete shared decision and paper workflow

Addresses **P5-03** and continuing Phase 5 integration requirements. Calling `detect_signal` from two locations is insufficient parity.

### Shared service

1. Extract or extend a compact application service used by the live-style worker and historical scheduler. Reuse production admission, material-change/revision, lifecycle and applicable current market-risk logic. Keep adapters, clock, evidence reader and output store injectable.
2. Supply the shared policy with the same validated evidence: discovered versioned instrument, closed candles, required reconciliation/source coverage, trades, book state, frozen target and costs. Missing required evidence must produce a reasoned abstention.
3. Apply current-risk validation when a provider result becomes available and when an arm becomes eligible for hypothetical entry. Analyst approvals do not preserve a candidate through a new stop, stale source, unavailable book, excessive drift/spread or exhausted target.
4. Schedule expiry, freshness and pending-arm transitions even when no new trade/candle arrives. Provider/quote/source events must affect pending opportunities at their correct availability time.
5. Persist frozen arm decisions and lifecycle transitions before observing the outcomes assigned to those decisions. A historical simulator may see future data only through its clock-ordered scheduler. Keep genuinely prospective writes distinguishable.
6. Define durable full-workflow progress, not only visibility-replay checkpoints. Resume after a committed batch to the same canonical candidates, decisions, outcomes and hashes as uninterrupted execution. Validate dataset/configuration/prefix identity before resuming.
7. Bound total memory by declared working windows and open state. Stream warmup and derived writes in batches; retire/archive resolved provider/candidate state; paginate output reads. Measure the whole workflow, not only the 5,000-trade/2,000-candle deques.

Two required parity examples: a candle arriving one second after close becomes eligible at the same evaluation point in both modes; a required source becoming unavailable at candidate +1 prevents a +3 dual-ready arm from entering at +4 without recovery.

### Connected paper path

1. Provide a bounded public paper command/service consuming normalized market and archived/fake-provider events through the shared service. Decide/persist first, then ingest later quotes/outcomes. Continue to support explicit historical import as a separate mode if useful.
2. Do not make the normal paper demonstration depend on an operator submitting the correct finished `ResearchOutcome` JSON. Derive it from later observed evidence using the shared evaluator and frozen policy.
3. Keep production review/budget/outbox stores isolated. A read-only adapter to a recorded production journal is acceptable; paper/replay must not enqueue paid reviews or real alerts.
4. Ensure realistic processing delay is represented. Persistence must precede eligible paper entry; do not require exact equality between independently sampled microsecond timestamps or backdate writes to manufacture it. Define effective readiness/entry scheduling around the real persisted decision boundary.

Two connected-paper examples: a decision is durably written, then a later quote opens and a still-later quote resolves the hypothetical position; missing source evidence after entry creates an unresolved/incomplete transition with its reason rather than an invented target result.

**6C gate:** Gold and BTC streams pass through actual public research and paper entry points, with positive and abstaining cases for all six engines. Compare canonical snapshots/decisions/lifecycle/outcomes between modes, not merely detector return values. Demonstrate input silence, late arrival, stop during analysis, source gap/recovery and interrupted resume. Use fake archived assessments and zero external calls.

## 6. Slice 6D — atomic paper recovery and verified source progress

Addresses **P5-05**, integrated with 6C.

1. Commit an input event's paper transition and cursor/progress update in one SQLite transaction where possible. If a different design is necessary, document and test the recovery protocol with the same guarantees.
2. On retry of an identical persisted decision, compare the immutable original record before applying checks intended for a new decision. Preserve original write time and eligibility. A conflict must still fail, even when its identity matches.
3. Bind progress to the physical/logical stream identity and generation plus a consumed-prefix digest or equivalent stable immutable journal offset. Validate path/file replacement, same-length replacement, truncation, reordering and append behavior. A free-form source label and line count alone are insufficient.
4. Define rotation and generation rollover explicitly. Either reject unexpected replacement before consuming it or safely start a new declared generation with auditable linkage. Never silently skip the beginning of a replacement file.
5. Make malformed input, partial trailing records and bounded-cycle exits recoverable without duplicate entries, skipped decisions or cursor advancement beyond a failed record.

Two mandatory recovery examples: crash after decision persistence and before progress commit, then restart at a later clock with exactly one decision and correct progress; replace a consumed one-line file with different one-line content under the same label/path and detect the conflict before returning success.

Also test a crash around outcome/progress persistence and a legitimate append across bounded cycles. Ordinary rerunning after a fully successful cycle does not substitute for interruption testing.

**6D gate:** fault injection at each durable boundary produces the same final immutable ledger and cursor as uninterrupted execution, or an explicit recoverable source-conflict state. No chronology rule is disabled to make recovery pass.

## 7. Slice 6E — protect holdout across all ordinary reads

Addresses **P5-06**. Preserve the corrected chronological folds, crossing-label exclusion, one-revision aggregation and known-abstention denominators.

1. Centralize research partition/access policy in a shared read/projection layer. Apply it to experiment details, opportunity pages, filters, exports, HTML/JSON/CSV reports and UI/API responses.
2. Before final access, withhold protected/crossing outcome-bearing fields and outcome-derived selectors/counts that reveal the result. Expose only explicitly permitted coverage/status metadata. Document what remains visible and why.
3. Require the existing deliberate final-evaluation action, or an equivalent explicit authenticated operation, to record the frozen config/dataset/partition identity and access event before returning protected results. This is a scientific workflow gate for the operator, not a replacement for normal authentication.
4. After access, clearly display `HOLDOUT_OPENED` or an equivalent state. Idempotent reads can reuse the same opened result; they must never reset it to unseen or silently use changed policy under its old identity.
5. Keep development results available normally. Do not hide everything or weaken useful operator troubleshooting merely to avoid implementing partition-aware projections.

Two mandatory examples: authenticated ordinary opportunity GET cannot reveal a protected target result or its P&L before access; authorized final access reveals the same stored result with a durable opened-state record, while unauthenticated reads still return 401.

Include a candidate observed before holdout whose label interval crosses its boundary, and verify JSON/CSV/HTML exports plus UI drill-downs. Editing the frontend alone does not protect an API response.

**6E gate:** one policy covers every outcome-bearing read path; tests inspect actual response/export bytes and access records before and after opening. Existing development metrics remain unchanged for unaffected records.

## 8. Slice 6F — public acceptance, documentation and readiness

Do this after the correctness slices. The goal is a reproducible acceptance bundle with honest limits.

### Required verification matrix

| Area | Required external behavior |
|---|---|
| Alert timing | Healthy send; normally timestamped mid-run stop; token retry; expiry/lease/freshness during delay; zero sends for invalid cases. |
| Legacy upgrade | Actual prior-schema pending jobs; terminal zero calls; missing frozen policy disposition; saved-result recovery preserved. |
| Availability | +120 quote/provider delays change earliest readiness/fill; no future evidence; completion at/after expiry fails closed. |
| Provenance | Explicit synthetic/retrospective evidence cannot be shown as prospective; identities retained through exports. |
| Coverage/economics | Both directions; no start anchor; pre/post-entry gaps; missing/partial OHLC; hand-calculated continuous controls. |
| Shared policy | Six engines × live-style/replay entry points; source loss, stop, drift, expiry and silence produce matching decisions. |
| Paper | Decision before actual entry; derived outcomes from later events; crash boundaries; conflicts; append/rotation/truncation. |
| Holdout | Ordinary detail/export/UI reads withheld; final opening recorded; crossing labels protected; development results preserved. |
| Scaling/resume | Full workflow interrupted between batches; same final hashes; warmup/pending/output memory bounded under longer input. |
| Defaults | No orders; external switches off; isolated stores; fake transports count calls explicitly. |

Keep fixture generation and public workflow commands reproducible on native Windows. Write generated text with an explicit encoding/newline policy when byte hashes must match across platforms. Do not relabel differently hashed input bytes as identical evidence.

Run the repository's full checks after the scoped changes:

```bash
python -m pytest -q
python -m ruff check .
python -m ruff format --check .
python -m compileall -q src tests
```

From `frontend`:

```bash
npm ci --no-audit --no-fund
npm run typecheck
npm run build
```

Run the documented Gold/BTC public `validate-data`, `run-workflow`, `evaluate` and `report` sequence, plus the connected bounded paper command. Validate exported checksums and agreement between API, stored records and reports. Preserve truthful insufficient-data classifications; do not quote fixture hit rates as estimated market performance.

### Documentation and release evidence

Update README, DESIGN, implementation plan, configuration examples, API/Windows guides and version/release notes where behavior changes. Add `docs/audits/phase-6-verification.md` containing:

- Starting and final code SHAs, instruction SHA and migration path.
- P5-01–P5-07 disposition table with reproduction, failing assertion, fix and passing command/test.
- Actual command outputs/counts, dataset/configuration hashes and locations of reproducible fixture definitions.
- Advancing-clock times, interrupted transaction boundaries, immutable record counts and source-prefix checks.
- Six-engine parity matrix covering admission/lifecycle/risk/readiness/outcomes, with any deliberate simulation differences explained.
- Export/holdout behavior and data-mode provenance examples.
- Memory/input scale and resume evidence for the complete path, including warmup and outputs.
- Explicit counts for actual provider requests, notifications and orders; do not rely on a hard-coded summary value as proof.
- Exact unverified operational and empirical gates.

Record native Windows CI separately from destination-server installation. A Windows runner can validate commands and migrations; it cannot prove the user's server's Task Scheduler/service setup, reboot recovery, ACLs, HTTPS, backups or sustained market ingestion. Provide a bounded operator runbook and leave unavailable external checks open.

Two readiness examples: a zero-network synthetic soak proves deterministic processing and recovery only; real licensed observations plus genuine contemporaneous provider outputs are necessary before evaluating whether the dual arm improves results over rules-only. Neither example authorizes execution.

### Definition of done

Phase 6 software acceptance requires all seven findings corrected or narrowly justified as already fixed with reproducible evidence, the shared/paper public workflow gates passed, migrations and Windows CI green, and updated operator/documentation projections agreeing with immutable records. Do not mark a slice complete if only its helper tests pass.

Conclude with changed behavior, tests/CI, PR links, blocked external items and remaining limitations. If the data or destination is unavailable, finish the authorized offline work and say precisely what remains. Do not invent weeks of observation, claim predictive accuracy, or automatically enable external integrations.

After this phase, the next decision is controlled data collection and prospective validation against preregistered criteria. Read-only derivatives research and any separate execution system remain deferred until their prerequisites and authorization are independently established.
