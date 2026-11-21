# Codex Phase 5 — complete and validate the research workflow

Repository: **https://github.com/Rameshdandu1/gold_bitcoin**.

## Objective

Complete the missing observation-to-engine-to-outcome-to-report workflow, fix the independently reproduced Phase 4 defects, and make prospective paper evidence trustworthy. Preserve the native Windows architecture and the working Phase 3 corrections. This milestone replaces the earlier immediate move into derivatives; derivatives and execution remain deferred.

**A collection of passing helper tests is not completion.** The public commands, API/UI and paper worker must demonstrate the same versioned research workflow. No output may claim an empirical edge when only hypothetical fixtures exist.

## 0. First instructions

1. Read `AGENTS.md`, `DESIGN.md`, `README.md`, `docs/IMPLEMENTATION_PLAN.md`, `docs/audits/phase-4-independent-review.md`, this file, then the relevant source and tests. Read `prompts/CODEX_PHASE_4.md` for requirements that remain incomplete.
2. Inspect `git status`, remotes, current branch and recent commits. Preserve unrelated work. Fetch current main and compare it with the reviewed main commit **`3b07d21079729da41f53c80fa5c4604b1dea9499`**. PR #6 implemented Phase 4; PR #5 contained its instructions. Do not assume a finding remains unfixed if newer commits exist.
3. If the new documents are only on the documentation branch, fetch and read them explicitly:

   ```text
   git fetch origin main
   git fetch origin refs/heads/docs/phase-5-review-and-instructions:refs/remotes/origin/docs/phase-5-review-and-instructions
   git show origin/docs/phase-5-review-and-instructions:prompts/CODEX_PHASE_5.md
   git show origin/docs/phase-5-review-and-instructions:docs/audits/phase-4-independent-review.md
   ```

4. Create `feature/phase-5-research-completion` from updated main. Use an isolated worktree if needed. Carry the review/instruction documents from the docs branch when main lacks them. Do not merge unrelated work or rewrite historical verification evidence.
5. Record starting code/instruction SHAs and a short dependency plan. The independently reviewed baseline passed **206 Python tests**, Ruff lint/format, compilation, frontend typecheck/build and Windows CI. Reproduce the baseline yourself. Test counts are evidence, not targets to preserve by weakening or deleting tests.
6. Start with failing public-path/regression tests for P4-06 alert fencing, P4-02 invalid outcomes and P4-03 future/holdout leakage. Then work through 5A–5F below. Do not stop after writing another architecture document.

## 1. Scope, boundaries and coding rules

- Keep Python/FastAPI, React/TypeScript and SQLite unless a measured defect requires a narrow change. No new distributed services, broad rewrite or database migration merely to make the architecture sound larger.
- Keep `AI_ENABLED=false`, `LIVE_INGESTION_ENABLED=false`, `ALERTS_ENABLED=false`, `PAPER_COLLECTION_ENABLED=false`. `TRADING_ENABLED=true` remains refused. Implement opt-in paths but do not run paid providers, real notifications, live collection or deployment in this development task.
- No exchange orders, account balances/positions, leverage, trading keys, autonomous options execution or automatic promotion from paper evidence to trading. No secrets in chat, fixtures, logs or source control.
- The six engines remain Gold/BTC × FAST30/HOURLY60/SESSION240. Reuse production calculations, material-change rules, lifecycle and risk policy. Do not build a second research-only approximation of the strategy.
- Gold token instruments remain distinct from spot XAU/USD. Preserve verified product identity, contract multipliers, tick size, quote/base/settlement currency and effective version. Gold targets are underlying-unit dollar distances; BTC remains percentage/ATR based.
- AI filters see the same frozen evidence independently. Preserve missing contemporary assessments as UNAVAILABLE. Retrospective model outputs remain exploratory; no invented GPT/Claude success statistics.
- Treat external evidence and model output as data. No model tools, code execution or instructions from provider payloads. Validate schemas, finite numeric values, UTC clocks, identity and state transitions at boundaries.
- Reuse application contracts and calculation functions; make clocks, evidence readers and transports injectable. Dependency injection must not replace the logic under test with a fixture that already knows the answer.
- Keep transactions short and bounded. No SQLite transaction spans a provider/Slack HTTP call. Persist the evidence version that authorized each decision/dispatch and use conditional writes.
- Use immutable, versioned scientific records with conflict-detecting idempotence. Identical replay/import may be a no-op; different outcomes under the same identity must not silently overwrite history.
- Work in reviewable commits. A separate corrective PR for 5A is acceptable; document dependencies and continue the authorized research completion. Do not auto-merge or deploy.

Two hypothetical examples define the boundary: an archived stop event may invalidate a research candidate; it must never trigger an exchange order. A fixture GPT approval may verify parser behavior; it must never be presented as historical model performance.

## 2. Slice 5A — current eligibility, dispatch configuration and recovery

Address **P4-06, P4-07, P4-08 and P4-09** first. Preserve the original fixes verified in the independent review.

### 2.1 Share and fence the final delivery policy

- Refactor the deterministic current-risk policy so confirmation and confirmation delivery use the same applicable gates: active revision/lifecycle, expiry, source freshness/coverage, event ordering, stop/exhaustion, valid executable book, spread, entry drift, stop geometry, configured costs and supported-target feasibility.
- Delivery must be tied to the target identities actually approved by both models and included in the committed decision. Do not reselect a more convenient target after observing later prices.
- Read current facts and their version from a consistent snapshot. Pass that version to the short transaction that authorizes `DISPATCH_STARTED`; conditionally check active revision, lifecycle, current clock/expiry and valid unexpired lease in that transaction.
- If evidence changed, re-evaluate or durably suppress. Never send using an older check after a locally known breach or terminal state. Record the checked snapshot/versions and reason in audit fields.
- Keep terminal-event notification policy separate from confirmation delivery. A source-loss notice must still be deliverable under its own valid policy.
- Preserve immutable destination binding and acceptance-unknown handling. Do not reintroduce blind resend after a dispatch may have been accepted. Describe any remaining remote uncertainty honestly.

Examples: the 2,590/2,610 Gold book must fail spread/drift before sending; a 2,589 stop trade inserted between the read and dispatch-state write must invalidate that write. Also test the distinct 2,605/2,605.2 drift-only case and a terminal lifecycle inserted at the same boundary.

The guarantee is relative to locally persisted evidence at dispatch authorization. Do not claim knowledge of a later exchange event or universal exactly-once notification receipt.

### 2.2 Check before spending and execute frozen requests

- Before reserving budget or dispatching each attempt, check active proposal/revision, lifecycle, expiry, required sources, configured limits, run deadline and lease. Return a typed non-dispatch disposition for terminal/superseded/ineligible work. Preserve fresh post-response checks as well.
- Compare and execute the full queued request configuration: provider/model, output cap, prompt/schema versions, relevant parameters and risk/selection policy identity. Bind pricing/usage assumptions to their own recorded version. Either execute the frozen request or create a new run identity; never silently use changed current settings.
- Verify actual SDK request arguments, not only the stored configuration dictionary. Keep the passing request-visible digest, failed-finish, oversized-input and actual-consumption budget tests.
- Refresh the clock at meaningful authorization/commit boundaries, including after waiting for a database lock. An old `evaluated_at` argument must not allow a late result or an expired lease to finalize.

Examples: an INVALIDATED candidate queued earlier makes zero provider calls; a run queued with output cap 64 must not execute cap 650 under the same identity.

### 2.3 Make recovery reach a durable disposition

- Keep saved analyst results recoverable without repeating calls. Separate results availability from finalization state.
- Handle both recovery before the absolute deadline and recovery after it. After deadline/expiry, persist a terminal expired/WAIT disposition and finish the job without confirming. Do not leave RESULTS_READY eligible for infinite lease-expiry reclaims.
- On evidence-version conflict, implement a bounded retry/re-evaluation or terminal disposition. On lost lease, prevent the old owner from writing. Preserve provider billing uncertainty and do not treat an unknown dispatch as certainly free.
- Test the shipped **90-second deadline / 120-second lease** defaults, not only a shorter lease chosen to make recovery succeed. Verify another queued job can still make progress.

Examples: a 30-second lease can recover a saved result within a 90-second deadline without redispatch; recovery at seconds 121 and 242 under default timing must terminate the expired job and never publish a late confirmation.

**5A exit gate:** positive healthy confirmation/delivery works; all reproduced invalidity/configuration/recovery cases are covered through real workers and temporary stores, with fake external transports and zero actual paid calls/messages.

## 3. Slice 5B — integrate replay with production research decisions

Address **P4-01, P4-10 and P4-11**. A visibility timeline can remain a useful diagnostic; it is not the strategy replay itself.

### 3.1 One shared event-processing path

- Introduce or extract a small shared application service that accepts an injected clock, normalized observations, read-only evidence state and isolated output store. The live-style worker and historical scheduler must call the same detector/material-change/lifecycle/risk logic.
- Parse every replay event kind into an explicit validated contract. A free-form `payload: dict` plus a timestamp is not enough to establish valid trades, candles, books, product changes or provider completions.
- Preserve source event time, factual availability/receipt time and durable persistence order. The scheduler advances by actual availability and configured poll cadence; feature windows use event time. Define ties for arrivals, polling, lifecycle, completion and expiry.
- Reconstruct a book only from an available valid snapshot plus required ordered deltas. A gap invalidates it until resynchronization. Build closed candles and trade windows from actual observations, preserving the 500/5,000 executed-trade requirements and unit provenance.
- Coverage is per required source/symbol/interval, with recovery generations. One valid BTC source cannot establish Gold coverage or silently stand in for a missing required book. Do not synthesize trades or books from OHLC data.
- Generate all eligible opportunities and stage dispositions, including WAIT/UNAVAILABLE, from the shared engines. Apply a frozen material-revision and rearm policy. Persist links to exact feature/evidence IDs.
- Produce four arm decisions from quantitative eligibility plus matching archived/fake provider results. Archived results must match exact candidate revision, request digest, provider/configuration, target approval and factual completion time. Fixture provider outputs must stay labelled hypothetical.
- Store the frozen decision before the separate evaluator can read the subsequent outcome path. Avoid an API that hands the whole future dataset to features or analysts.

Examples: a candle arriving one second after close must be evaluated at the next eligible poll in both replay and the live-style fixture; a stop arriving during model analysis must invalidate that arm before entry while preserving the original analyst packet.

### 3.2 Bind evidence and resume identities

- Define a canonical dataset identity from a versioned manifest preimage, ordered file identities/checksums and relevant metadata, excluding its own digest. Recompute it during validation; never trust a self-asserted `content_hash`.
- Define a canonical experiment/config identity including dataset identity, code/algorithm versions, engines/rule/feature policy, arms, target/revision selection, entry/cost policy, schedule, folds/holdout/embargo, seed and tried-variant identity.
- Checkpoints bind both identities plus state-schema version, durable source cursors, sequence/generation state and committed output position. Validate prefix/state integrity before resume. Refuse a changed cadence, target, cost policy, source file or algorithm under the old checkpoint.
- Replay hashes must commit to relevant evidence/state/decisions, not only observation IDs. Document the hash preimage and test both identical reruns and material input changes.
- Replace opportunity/result/report overwrite behavior with immutable versioned records. Repeating identical writes is idempotent; conflicting data requires an explicit new revision/experiment or a typed integrity error. Reports identify the exact evaluation version they summarize.
- If archived opportunities are imported, validate their trusted provenance, parent identity, temporal/state/target consistency and supporting evidence. Keep this a distinct import mode; normal evaluation must derive outcomes itself.

Examples: updating a file checksum while leaving an old dataset identity must fail validation; resuming a 60-second experiment with a 30-second cadence must fail before producing mixed output. Replacing a completed 0.00695890 outcome with 0.19693990 under the same identity must be rejected.

### 3.3 Bound state, output and interruption recovery

- Retain the useful disk-backed input sort, but stream replay outputs into bounded transactional batches. Do not keep every prior observation ID in every point or return the full run as an ever-growing list.
- Keep only required rolling feature state, open opportunities/positions, source recovery state and durable references. Store event history once with indexed immutable offsets. A compact checkpoint must not contain the entire replay history.
- Commit output and the corresponding recovery cursor/state atomically or through a proven recoverable protocol. Persist checkpoints periodically and on bounded cancellation. Restart must neither lose already committed decisions nor duplicate them.
- Provide bounded progress reporting and useful cancellation/exit behavior. Measure memory and storage growth on a declared finite workload; distinguish input-sort, engine-state and output costs.
- Validate experiment/database identity before expensive replay. Keep production review/budget/outbox stores isolated. Reading a recorded production journal through a dedicated read-only source is acceptable; replay must never enqueue production jobs.

Examples: doubling 500 events to 1,000 must not reproduce the current 125,250-to-500,500 retained-reference growth; interruption after a committed batch must resume to the same final records/hash as an uninterrupted run.

**5B exit gate:** public replay generates versioned opportunities through real engines from local evidence, including one Gold and one BTC stream; all six engines have a live-style/replay parity matrix. Changed evidence changes the expected decisions or identity. Restart output is deterministic and memory is bounded by declared windows/batches rather than run length.

## 4. Slice 5C — trustworthy entry, path and economic outcomes

Address **P4-02** and the outcome contract omissions in P4-10. Wire the corrected evaluator into the public research path rather than leaving it called only by tests.

### 4.1 Declare clocks and eligibility once

- Separate candidate observation, analyst request start/completion, final current-risk readiness, diagnostic provider duration, configured post-decision entry latency, actual hypothetical fill and expiry.
- `ready_at_utc` must represent a defined factual instant. Do not add the already elapsed provider duration again. Apply `ExperimentConfig.entry_latency_ms` exactly once according to the frozen policy and record the effective entry threshold.
- A new entry requires effective readiness strictly before expiry and a valid observable fill before expiry. Expiry equality cannot open a position. Delay consumes the original horizon.
- Before entry, inspect the setup from observation through effective entry for stop breach, target exhaustion, terminal lifecycle, supersession and source gaps. A recovered price does not revive a stopped proposal. A new setup requires a new policy-valid opportunity.
- Preserve original target IDs/indices and approved target intersections. Resolve target selection before future-path access; do not choose the best target after the result.

Examples: a +10-second stop followed by recovery and +30-second approval is NO_ENTRY under the original proposal; a +30-second ready time with ten seconds of diagnostic provider duration stays +30 before any separately configured execution delay.

### 4.2 Validate the whole relevant path

- Validate approval/state, parent opportunity/revision/arm, instrument/product version, UTC and finite values, monotonic source ordering, interval boundaries and coverage before assigning a completed result.
- Apply declared gap/sequence/source validity throughout observation-to-entry and entry-to-outcome/expiry. Missing observations cannot prove that no earlier stop occurred. Decide which cases are INCOMPLETE versus AMBIGUOUS under a documented policy.
- OHLC bars crossing entry or expiry cannot localize a touch. Resolve using finer evidence or preserve uncertainty. A REJECTED/WAIT/UNAVAILABLE arm cannot acquire an executed outcome from a later bar.
- Define contiguous OHLC coverage and partial-bar handling; a `complete=True` flag on one bar does not establish the full candidate path. Wrong-symbol/version records cannot fill required coverage.
- Preserve supported event IDs, coverage intervals and the time each label becomes knowable. Enforce cross-field validation on ResearchOutcome, ArmRecord and OpportunityRecord; derive label-information bounds from actual decision/outcome evidence.

Examples: a 140-second gap cannot count as complete under a ten-second maximum; a +120-to-+240 bar cannot prove a hit before +180 expiry. Test mirrored bullish/bearish cases and complete valid paths.

### 4.3 Preserve defensible economics

- Longs enter ask and exit bid; shorts enter bid and exit ask. Apply tick rounding and configured slippage adversely. Do not infer limit-order queue priority from a touch.
- A stop gap uses the first observable adverse fill under the declared policy, not the nominal stop. Product validity and required coverage must remain meaningful throughout the position interval.
- Use verified contract units and quantity. Separate gross price distance, trading P&L, fees/spread/slippage/funding and net R. Validate all monetary fields as finite and consistent with the declared policy.
- Record funding/cost assumptions by effective interval/version. Missing required costs block net-performance claims. Keep API expense separate, with currency/unit basis, while allowing a clearly defined total research-economics view.
- OHLC-only touch studies must not masquerade as quote-executable P&L. Keep baseline/adverse-cost scenarios frozen before test inspection.

Examples: a Gold underlying quote move of 20 is scaled by verified contract multiplier and hypothetical quantity; a BTC short pays the bid/ask spread and adverse exit slippage even when direction was correct.

**5C exit gate:** public evaluation derives supported outcomes from evidence, including rejected arms, pre-entry invalidation, partial entry/expiry bars, post-entry gaps, expiry equality, costs and valid mirrored cases. No hand-entered P&L is required for the golden workflow.

## 5. Slice 5D — common-opportunity statistics and protected time partitions

Address **P4-03 and P4-04**. These policies must govern the actual CLI/report rows, not only produce a decorative list of fold IDs.

### 5.1 Freeze the unit of comparison

- Define opportunity identity, proposal revisions, permitted rearm and one actionable revision-selection policy per experiment. Group all arms/revisions of the same opportunity into the same temporal partition. Keep revision counts separate from independent opportunity/execution counts.
- Use one quantitative universe for RULES_ONLY, RULES_PLUS_GPT, RULES_PLUS_CLAUDE and RULES_PLUS_DUAL. Preserve discovered/eligible/reviewed/approved/executable/complete counts and all exclusions/abstentions.
- Define the primary estimand explicitly, including hypothetical quantity/risk normalization, opportunity versus day weighting and attributable model costs. A known no-position choice can have its declared zero trading P&L minus attributable cost; missing/unknown evidence must remain unavailable, not zero.
- Include avoided losses and missed winners in the operational comparison. A common-executions-only study may remain as a separate labelled diagnostic. Show both denominators and exclusions.
- Bind provider costs/latency to exact recorded attempts. Distinguish experiment-wide actual spend from arm-attributable counterfactual expense; do not charge the same bill four times.

Examples: two revisions of one 4.8 opportunity must not create 9.6 under a single-entry policy; in the ten-day fixture with accepted +4.8 and rejected rules-only -6.2 each day, the operational comparison must represent the -14 versus +48 totals rather than silently report only the common-trade zero difference.

### 5.2 Implement actual walk-forward validation

- Use past-only training/development and later validation/test segments. If an early segment has no eligible training history, omit/mark it according to policy; never train it from later observations.
- Purge using the union of all observation intervals needed to know every arm/revision outcome, including delayed completion, no-entry, exhausted, censored and rejected cases. Use timestamp-based embargo where declared. A sample-count gap alone is insufficient for irregular events.
- Freeze holdout boundaries and cost/rule/prompt/selection choices in ExperimentConfig before evaluation. Ordinary evaluate/report commands must honor that frozen policy and refuse conflicting CLI overrides under the same identity.
- Remove all development records whose label-information intervals enter holdout. Keep protected holdout outcomes out of development summaries, paired estimates, exports and tuning views until an explicit final evaluation action is recorded.
- A final holdout evaluation records the frozen selected configuration and access/evaluation event. Subsequent tuning creates a new experiment and must not reuse the same data as an untouched holdout.
- Keep partitions explicit in stored results and all public reports. Do not compute all-row metrics before applying the partition policy and then attach a folds field.

Examples: training day3/day4 to evaluate day1/day2 must fail the walk-forward invariant; a candidate observed at hour71 whose label becomes known at hour73 is excluded from development when holdout starts at hour72.

### 5.3 Report uncertainty without fabricated independence

- Report per asset, engine/horizon, direction, target, rule/model/configuration and declared session/regime when samples support it. Include coverage, ambiguity, time exits, missing evidence, counts and observation dates.
- Compute target/stop rates with explicit denominators, net R/expectancy, cost burden, latency and avoided/missed opportunity outcomes. Undefined or unavailable values stay null/N/A.
- Use paired dependence-aware blocks, preserving opportunity matching and the chosen weighting. A date boundary does not automatically make adjacent overlapping labels independent. Declare block length, overlap policy and resampling seed; too few usable blocks means insufficient uncertainty evidence.
- Handle zero-loss profit factor, no executions, identical pairs, unequal daily counts and degenerate intervals. An EXPLORATORY badge does not make an incorrectly scoped metric acceptable.
- Track tried variants and preserve final evaluation artifacts. No annualized return projections from short fixtures. Calibration/Brier scores remain N/A without an explicit out-of-sample probability model.
- Show portfolio equity/drawdown only under a separate frozen sizing/capital/concurrent-exposure policy. Event sums are not automatically a portfolio.

Examples: known rejections stay in the operational filter comparison while unavailable Claude outputs do not become zero-return trades; two overlapping four-hour signals must not be treated as independent ticks in uncertainty calculations.

**5D exit gate:** hand-checkable cohort totals, partition counts and paired estimates match the public report. Adversarial future/holdout fixtures cannot affect development outputs. Revisions do not inflate the selected counting unit.

## 6. Slice 5E — a genuinely prospective paper event loop

Address **P4-01 and P4-05**. Preserve the separate paper database and default-off switch.

- Implement a local-stream consumer that observes decisions and subsequent public market evidence through read-only source adapters. Reuse the shared eligibility and outcome policy. No exchange/account/order client is needed.
- Persist immutable candidate/revision, arm decision, exact target/configuration and effective readiness before eligible entry and future outcome processing. Store server persistence time separately from source event/availability times. Historical imports use a distinct historical mode and cannot be relabelled prospective.
- Enforce legal append-only transitions for no-entry, awaiting fill, open, target/stop/time close, ambiguous and data-censored results. A REJECTED decision cannot receive an executed win. A completed economic outcome predating decision persistence must fail prospectivity checks.
- Make decision/entry/outcome transitions conflict-detecting and idempotent under restart/concurrency. Do not permit two workers to overwrite each other's immutable results.
- Bind every cursor to source identity/generation, file/journal identity and committed state. Handle rotation, truncation, duplicate events and reordering. Checkpoint transitions and input progress together so a crash cannot skip or duplicate a paper entry.
- On downtime/gaps, attribute any valid backfill and distinguish evidence received later. Where order cannot be established, preserve incomplete/ambiguous outcome. Never silently mark unresolved positions profitable or cleanly expired.
- Keep four arm records linked to the same opportunity and predeclared target/revision policy. Preserve rejected opportunities as counterfactual study records; do not count them as open positions.
- Provide bounded `--once` and deterministic local dry-run paths. Document how operators would run authorized forward collection later. Do not start external collection in this task or claim that several weeks elapsed.

Examples: a January2 trade whose decision was first recorded January3 must be rejected as prospective; replacing source file A with file B must detect identity change instead of silently skipping B's first row using A's cursor.

**5E exit gate:** the same deterministic Gold/BTC local streams drive public paper commands from persisted decision through outcome, including restart and missing events. The records prove write-before-entry, not merely decision-row insertion before outcome-row insertion.

## 7. Slice 5F — usable reports, evidence gates and Windows operation

Address **P4-12** and reconcile every completion claim with tested behavior.

### 7.1 Public CLI and export workflow

Keep the existing command names where practical, with migration/help text for changed arguments. The intended operator path is:

```text
validate dataset -> replay shared engines -> evaluate derived outcomes
-> development/test report -> explicit final holdout evaluation when allowed
```

`evaluate` must operate on the experiment's derived/validated evidence, not require the user to invent an opportunities file. If archive import remains, expose its provenance and mode explicitly. Commands return meaningful machine-readable statuses and nonzero failures.

Export the authoritative stored manifest/configuration, code/algorithm identities, source coverage, selected opportunity/revision records, arm decisions, outcomes, partition membership/exclusions, summary metrics, uncertainty, cost basis and checksums. HTML/Markdown must explain incomplete and unavailable evidence. Do not copy arbitrary `--manifest`/`--config` files into an unrelated report. Preserve CSV formula sanitization, privacy and licensed-data restrictions.

Examples: a report for a BTC-only dataset shows Gold unavailable with the reason; a fixture export identifies SYNTHETIC_FIXTURE and carries the exact configuration that generated its outcomes.

### 7.2 Authenticated research views

- Add experiment list/detail and selected experiment state, source coverage/data mode, six-engine and four-arm filters, per-partition counts/metrics, target outcomes, latency/costs and paper transitions.
- Read actual stored provenance and measured counters. Do not hardcode `NO_DATASET_SELECTED` after an experiment is selected or display an unknown external-call count as a measured zero. Label the scope/time range of any counter.
- Keep loading/error/empty/unavailable/insufficient/exploratory states. Synthetic and retrospective data must remain visibly distinct from prospective evidence in pages and exports.
- Ensure API, UI and CLI agree on the same selected version/partition. Keep auth, bounded pagination and no frontend secrets. Do not expose raw licensed/private provider payloads unnecessarily.

Examples: selecting two experiments with different data modes updates attribution and counts; a failed report request displays an error rather than retaining a stale success card as current.

### 7.3 Separate software acceptance from empirical readiness

Use a machine-readable evidence matrix with independent states for software integration, dataset coverage, model provenance, forward observation and deployment verification. Do not collapse these into one ambiguous green badge.

- Software can be verified with complete hypothetical streams and negative controls.
- Empirical performance remains INSUFFICIENT_EVIDENCE until adequate real evidence actually exists.
- Prospective collection duration and sample count are measured fields, not a planned duration converted into completion.
- Windows CI is useful but is not destination server service/reboot/backup verification.

Provide native PowerShell instructions for installation, disabled startup, local fixture workflow, service/task configuration, bounded recovery, database backup/restore, logs and shutdown. Use `pathlib` and UTC storage with Asia/Kolkata display by default. Test what the available environment supports and explicitly mark destination-server steps unverified. No deployment in this task.

## 8. Acceptance tests and delivery contract

Use meaningful tests that assert expected behavior from external facts. The review's scripts are investigative evidence; create maintainable repository regressions with clear fixture builders. Do not write a test whose expected result simply calls the same helper again.

| Area | Minimum contrasting evidence |
|---|---|
| Delivery | Healthy send; wide spread/drift blocked; trade/lifecycle insert before dispatch authorization blocked; valid terminal notice |
| Provider lifecycle | Invalidated-before-start makes zero calls; frozen output/config identity; within-deadline recovery; default expired recovery terminalizes without redispatch |
| Shared replay | Gold/BTC positive and abstaining streams; all six engine parity; close+1-second arrival; source gap/resync; provider completion and expiry ordering |
| Identity | Valid canonical hashes; changed payload/config/checkpoint rejected or new identity; conflicting opportunity/outcome write rejected |
| Scaling/recovery | Bounded state/output growth; batch crash/cancellation; resumed/full result parity; no production side effects |
| Entry/outcomes | Pre-entry stop/target, recovered price, rejected arm, latency once, expiry equality, quote gaps, partial bars, missing earlier coverage, complete mirrored paths |
| Economics | Hand-calculated bid/ask/tick/multiplier/fees/slippage/funding; adverse scenarios; incomplete required cost |
| Validation | Past-only training; all arms/revisions grouped; label crossing holdout purged; CLI config honored; no holdout rows in development report |
| Comparisons | Unique-opportunity policy; avoided losses/missed winners; unavailable versus known abstention; API cost allocation; paired weighting and sparse blocks |
| Paper | Persist before entry; old outcome rejected as prospective; REJECTED cannot win; source generation/rotation; restart/concurrent idempotence |
| Operator surfaces | Auth, pagination, exact experiment provenance, consistent CLI/API/UI totals, complete safe exports, empty/error states |

Run and report the standard checks:

```powershell
python -m pytest -q
python -m ruff check .
python -m ruff format --check .
python -m compileall -q src tests
git diff --check
cd frontend
npm ci
npm run typecheck
npm run build
```

Run **two complete public-command golden workflows**, one Gold and one BTC. Include enough genuine-shaped hypothetical observations for the real engine prerequisites; do not patch the detector to return a predetermined candidate in this acceptance test. Verify expected events/entries/outcomes by hand, and compare the public output with independent expected values. Use fake request-visible analyst responses only in fixture mode.

Update README, DESIGN, implementation plan, API/Windows guides, relevant configuration examples, ADRs and release/version notes where appropriate. Preserve historical reports with an explicit later-review status rather than rewriting what was run.

Create `docs/audits/phase-5-verification.md` containing:

1. Starting/final code SHAs, instruction revision, baseline and final checks.
2. Each P4 finding: reproduced, corrected or remaining, with meaningful regression/public-workflow evidence.
3. The actual Gold/BTC CLI commands, artifact identities, expected/observed entries/outcomes and full workflow counts; six-engine parity matrix.
4. Recovery/dispatch race evidence and bounded-memory measurements with workload assumptions.
5. Partition/holdout policy, cohort accounting, comparison estimand and actual evidence limitations.
6. Paper decision-persistence versus entry/outcome chronology and source-resume evidence.
7. External calls/messages/orders/deployments actually performed. **Zero is expected for this development task.**
8. Windows checks executed versus destination-server steps unverified.
9. Real dataset/provider/forward-evidence status; no fabricated rates, probabilities or weeks of observation.

Push reviewable feature commits, open PR(s), and report the remaining acceptance gates. A newly discovered material defect must be fixed within this scope or stated explicitly; do not mark the affected slice complete because a narrow fixture passed.

## 9. Primary methodology references

- [scikit-learn TimeSeriesSplit](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html): past-to-future splitting and sample-count gaps; do not substitute it blindly for interval-aware purging.
- [SQLite isolation](https://www.sqlite.org/isolation.html): explicit snapshots and serialized writes; test the application's conditional transitions under concurrency.
- [Kong et al., Evaluating LLMs in Finance Requires Explicit Bias Consideration](https://proceedings.mlr.press/v306/kong26i.html): structural bias and cost controls in financial LLM evaluation; model agreement is not empirical validation.

Begin with the baseline and failing regressions, then deliver a functioning, auditable public workflow. Derivatives, paid observation and deployment remain separate later work.
