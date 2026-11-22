# CODEX TASK — finish Phase 6 workflow acceptance, then operational validation

## Outcome and finite scope

Correct **P6C-01, P6C-02 and P6C-03** from the
[independent closeout review](../docs/audits/phase-6-closeout-independent-review.md).
These are unfinished parts of the existing shared-service and whole-workflow-memory requirements.
The exact P6-01 through P6-05 regressions now pass; preserve them. The checkpoint/resume mechanism
also passes its tested fixture paths and should be extended, not replaced without a concrete need.

The deliverable is a reviewable implementation PR with reproducible evidence closing these three
items. Once the finite acceptance matrix passes, the next stage is controlled Windows/live
integration validation and then prospective paper observation. Keep derivatives, orders, new
indicators, stack changes and unrelated UI work out of this task.

## 1. First actions

1. Inspect `git status`, branch, remotes and recent commits. Preserve unrelated changes. Read
   `AGENTS.md`, `DESIGN.md`, `README.md`, `docs/IMPLEMENTATION_PLAN.md`, the independent closeout
   review, this task and the relevant source/tests. Read the existing package C requirements in
   `prompts/CODEX_PHASE_6_CLOSEOUT.md`; this task supplies the concrete failing cases.
2. Fetch current main and record the starting SHA. The reviewed baseline is
   **`81f86f79cb943c8cb837aae4f800135948f89f32`**, containing merged PR #12 and PR #13. Compare newer
   implementation changes before treating findings as still open.
3. If these instructions have not merged, fetch their documentation branch explicitly:

   ```bash
   git fetch origin refs/heads/docs/closeout-review-and-next-steps:refs/remotes/origin/docs/closeout-review-and-next-steps
   git show origin/docs/closeout-review-and-next-steps:prompts/CODEX_PHASE_6_WORKFLOW_ACCEPTANCE.md
   git show origin/docs/closeout-review-and-next-steps:docs/audits/phase-6-closeout-independent-review.md
   ```

4. Create `fix/phase-6-workflow-acceptance` from current main, using an isolated worktree if needed.
   Carry the relevant instruction/review documentation if absent. Do not reset another branch,
   force-push main or merge unrelated work.
5. Reproduce the **251-test** baseline, lint/format/compile and frontend checks. Add meaningful
   failing regressions for the exact public counterexamples before changing production behavior.
   Record a short implementation plan identifying ownership of clock, lifecycle and bounded state.
6. Implement packages A–C below in reviewable commits. Finish all authorized offline work, push and
   open a PR. Do not auto-merge, deploy or enable external operations.

## 2. Coding rules

- Keep Python/FastAPI, React/TypeScript, native Windows and isolated SQLite research/paper stores.
  Preserve all six Gold/BTC horizon engines, their strategy thresholds and four comparison arms.
- Keep live ingestion, paid AI, alerts and real paper collection disabled by default.
  `TRADING_ENABLED=true` remains rejected; no order/account/leverage/trading-key endpoints.
- Use UTC-aware injected clocks and typed evidence contracts. Preserve exchange time, accepted
  receipt/availability, provider completion, decision persistence, entry eligibility and outcome
  observation as separate facts. Use `Decimal` at monetary boundaries.
- Persist contemporaneous decisions immutably. Identical retries preserve original bytes and
  timestamps. Conflicting writes must still fail; never suppress the immutable-store error or
  overwrite history to make P6C-01 disappear.
- Reuse canonical candidate/admission/material-revision/lifecycle and applicable market-risk
  logic. Transport configuration is a separate concern; research must not require Slack credentials
  merely to evaluate market eligibility.
- A shared function only provides parity when callers supply equivalent factual inputs. Do not
  hardcode current revision, active lifecycle or unambiguous ordering when the journal establishes
  otherwise. A recovered price cannot erase a terminal executed stop.
- Both actual model providers retain independent analysis of the same canonical input. Preserve
  frozen archived request/configuration binding and actual model metadata when present; unknowns
  remain null/unavailable or explicitly exploratory. Do not invent contemporary model evidence.
- Version changed experiment/evaluator/checkpoint contracts. Add compatible migrations or an
  explicit safe refusal/rebuild path for old checkpoints; do not silently mix corrected results
  into an old scientific identity or destroy prior records.
- Bound normalized input, source/feature state, pending candidates/providers, quote evaluation and
  output projection. No hidden full-history `fetchall()` or filtering after full materialization on
  the normal path. Do not replace correct history with a silent truncation cap.
- Keep network work outside short transactions; preserve job leases, budget accounting,
  authorization freshness, uncertain delivery recovery and destination binding.
- Use independent expectations and hand calculations. Do not derive expected answers from the
  same helper being tested, skip a failing integration test or weaken historical assertions.
- No plaintext secrets in chat, commits, logs, fixtures or exports. No paid request, real message,
  live collection or destination deployment is needed for this corrective task.

## 3. Package A — contemporaneous arm decisions and later evidence

### Exact red cases: P6C-01

Generate a fresh standard Gold fixture for each variant. Add one valid same-price `BOOK_SNAPSHOT`
with bid **2599.9**, ask **2600.1**, sequence/generation 2 and matching envelope/feature times. Use
unique IDs, valid ordering and regenerated file/count/manifest hashes.

1. Snapshot at **candidate +21 seconds**, after target quotes at +20. Current public workflow
   exits 2 with `Arm decision identity is immutable`, 12 decisions and zero completed opportunities.
2. Snapshot at **+2.5 seconds**, between GPT +2 and Claude +3. Current public workflow exits 2 with
   six saved decisions and zero completed opportunities.

Unmodified Gold/BTC streams must continue to produce three opportunities and 12 decisions/outcomes
per asset. Both amended streams must complete without rewriting earlier decisions. Run through the
public CLI with fresh databases; a helper-only test is insufficient.

### Required behavior

1. Resolve each arm once at its factual readiness boundary from evidence available at that time.
   Persist the supporting snapshot/version or sufficient immutable references to reproduce it.
2. Reuse saved decisions during later provider/source events and final outcome derivation. Do not
   reconstruct historical decisions from `state.books` at the end of the input.
3. Evaluate the dual arm at the later provider readiness against current applicable facts. For
   example, GPT approved at +2 is preserved, but a source failure at +2.5 must still prevent a dual
   approval at +3. Likewise, an unchanged book at +2.5 must not retroactively change GPT at +2.
4. Track subsequent risk/lifecycle events separately. If a new versioned decision is required by
   policy, give it an explicit identity and preserve the original; never mutate a prior arm.
5. Define deterministic same-time ordering and ambiguity behavior using factual receipt sequence.
   Late availability must not reveal a candle, trade or model result before receipt.
6. Retain genuine conflict detection. Add a deliberate conflicting rewrite regression proving that
   the store still rejects it after the workflow is repaired.

### Recovery acceptance

- Interrupt after GPT has been durably recorded but before the +2.5 book and Claude; resume in a
  fresh Python process. Compare canonical decisions, lifecycle, outcomes and final checkpoint with
  uninterrupted processing of the exact same stream.
- Inject a failure after a derived output write and before progress advancement. Retry must converge
  without duplicate records, changed scientific timestamps or partial success claims.

Keep the existing 100-row warmup and one-provider resume tests. Changed source/configuration
identity must still be refused before silently reusing an incompatible checkpoint.

## 4. Package B — actual shared admission/lifecycle/current-risk facts

### Exact red case: P6C-02

Use the three original Gold candidates observed at **2026-11-19 01:00:00 UTC**. Preserve their IDs and
provider request bindings. Parse/journal these trades with the actual trade parser, and put the
same normalized observations into the research fixture:

| Hypothetical event | Exchange time | Receipt time | Price |
|---|---|---|---:|
| Executed stop breach | 01:00:00.900 | 01:00:01.000 | 2594.8 |
| Price recovery | 01:00:01.400 | 01:00:01.500 | 2599.2285714285713 |

The three stops are 2595.8, 2596.8 and 2598.2285714285713. Original GPT/Claude readiness remains
+2/+3 and first executable entry/target quotes remain +4/+20. The actual production lifecycle sweep
marks all three candidates `INVALIDATED`, while current public research reports 12 target wins.

Correct research/paper outcomes must retain the terminal breach and cannot invent later fills.
Keep arm denominators and distinguish an unfilled terminal/no-position case from an already-entered
position that later stops. Add the corresponding bearish stop/recovery case; also retain a benign
trade/recovery control that never crosses invalidation and remains eligible.

### Required implementation

1. Share the compact clock-injected application service actually invoked by the production worker,
   research scheduler and connected paper processing. Reuse candidate admission/material revisions,
   lifecycle and applicable current-risk decisions; avoid another independent simulation policy.
2. Carry event-driven terminal history forward. Preserve executed-trade watermarks, receipt cutoffs,
   target exhaustion, expiry and source-loss semantics through recovery and restart.
3. Supply real revision/lifecycle/order/source facts to the shared predicates. Check applicable
   target feasibility, configured costs and net reward/risk consistently. Preserve justified
   differences in output transports and persistence, and document them explicitly.
4. Keep original strategy thresholds and scientific identities unless a version change is required
   to represent corrected semantics. Do not make the parity test pass by loosening production gates.
5. Make current source age advance during input silence; a last-known available flag is not proof
   of freshness at a later provider/entry boundary.

### Finite parity matrix

Exercise all six engines through real application entry points with matching normalized evidence.
Use fake transports and the real stores. Compare canonical snapshots, accepted revisions,
lifecycle/terminal reasons, provider readiness, applicable risk gates and outcomes. Avoid proving
parity by constructing two already-agreeing eligibility objects or calling only `detect_signal`.

| Required case | Expected agreement |
|---|---|
| Healthy candidate and independent provider results | Same accepted revision and eligible market policy |
| Long and short executed stop followed by recovery | Terminal breach survives; no post-invalidation entry |
| Source loss during provider review | Later arm/entry remains unavailable or WAIT |
| Spread or entry drift becomes unacceptable | Corresponding simulated arm is blocked by the same policy |
| Target already exhausted or net reward/risk insufficient | No supposedly feasible entry bypasses production rules |
| Expiry/source aging during silence | Clock-driven terminal/suppression occurs without waiting for another input row |
| Late candle and ordinary book update | No future evidence affects an earlier decision |
| Unchanged versus material proposal revision | Same admission/deduplication policy; terminal or superseded revisions stay ineligible |

This matrix completes the existing package C contract. It is not permission to expand the strategy
or introduce live trading.

## 5. Package C — bound complete research/paper working state

### Exact red measurement: P6C-03

Use the standard Gold fixture plus **1,000** and **8,000** unbound executable quotes strictly before
candidate observation. Give them one-second spacing ending at -1 second, bid 2599.9 and ask 2600.1;
regenerate valid evidence/manifest hashes. Keep the same three candidate lifetimes, provider rows
and outcome quotes. The review measured:

| Public path | 1,000 older quotes | 8,000 older quotes |
|---|---:|---:|
| Complete research Python allocation peak | 14,460,816 bytes | 44,692,151 bytes |
| Paper limited to first 100 input events | 3,387,871 bytes | 24,256,542 bytes |
| Complete paper allocation peak | 5,669,300 bytes | 36,581,091 bytes |
| Complete paper quotes loaded per candidate | 1,002 | 8,002 |

The 100-row runs report zero visible quotes while materializing all of them before the horizon
filter. Input batch size 500 and a 5,000-trade deque are insufficient evidence of total bounds.

### Required implementation and evidence

1. Query quotes by experiment/symbol, factual availability and candidate interval using suitable
   indexes and bounded pages. Carry the necessary predecessor/coverage anchor and incremental
   outcome state; do not reload the complete symbol history for every candidate/horizon.
2. Check whether an arm is persisted, unresolved and relevant to the current horizon before loading
   its evidence. Avoid quote loading for unrelated warmup events and already terminal arms.
3. Page candidates, decisions and report/export rows. Retain only a declared active set in memory;
   move resolved provider/candidate/outcome state to immutable storage. A completed candidate must
   not remain in an ever-growing in-memory dictionary merely because the experiment continues.
4. Retain sufficient source/sequence history for the active window. Do not silently keep the first
   10,000 rows, drop a current gap or truncate required pre-entry evidence to satisfy a memory cap.
5. Instrument rows actually materialized before filtering, active versus historical candidates,
   quote/source batch peaks, provider/pending state and output batches. Report command-level
   allocations or RSS in a reproducible benchmark with host/runtime information.
6. Rerun both public lengths and both warmup/complete paper paths in fresh processes. Same active
   window/open-set requirements must have memory governed by the declared bound, not history length.
   Preserve identical canonical outcomes. Separately show that a legitimate increase in concurrent
   candidates is bounded/configured and reported honestly.
7. Use stable structural/count assertions for CI. Exact byte counts from this review are evidence,
   not portable pass thresholds. Set a justified tolerance for measured overhead and retain raw
   measurements; do not increase the allowance until an unbounded path passes.

## 6. Preserve established corrections and acceptance evidence

Retain exact tests for all five original finding groups and their controls:

- Event-time book freshness crossing with zero sends; healthy delayed authorization, stop arrival,
  expiry/lease fences, destination immutability and uncertain remote delivery recovery.
- Explicit conflicting provider/quote payload clocks; omitted-field fallback; incompatible modes;
  optional actual model IDs and honest null unknowns; request/configuration identity failures.
- Anchored quote gap and incomplete pre-entry bar in both directions; continuous hand-calculated
  economics, pre-entry invalidation, post-entry coverage and expiry boundary behavior.
- Holdout before/after deliberate opening across ordinary and paper APIs, counts and exports;
  conservative handling of legacy unscoped rows; protected/crossing labels remain protected.
- Missing Claude and both providers after expiry; all four arms and no fabricated entries; repeat
  idempotency; truthful warmup/partial/unresolved/complete progress and fresh-process resume.

Run:

```bash
python -m pytest -q
python -m ruff check .
python -m ruff format --check .
python -m compileall -q src tests
git diff --check
```

From `frontend`:

```bash
npm ci --no-audit --no-fund
npm run typecheck
npm run build
```

Execute the documented public Gold and BTC sequence: fixture generation, `validate-data`,
`run-workflow`, `paper-workflow`, `evaluate`, and `report --paper-database ...`. Verify checksums and
API/export agreement for ordinary and protected partitions. All synthetic results remain labelled;
do not describe 12 constructed target outcomes as empirical success.

Add `docs/audits/phase-6-workflow-acceptance-verification.md` containing:

- Exact starting/final code and instruction SHAs, contract versions and additive migration/recovery
  policy, including treatment of existing faulty research outputs/checkpoints.
- P6C-01/02/03 red/green results, exact source mutations and preserved healthy/negative controls.
- The finite six-engine parity matrix and explicit adapter differences.
- Fresh-process resume and output-before-progress fault evidence, canonical record comparisons and
  unchanged-source/configuration checks.
- Both representative lengths' whole-command measurements and structural bounds, including all
  pre-filter loads and resolved-state retirement.
- Public command counts, evidence modes, hashes and actual Windows CI results. Distinguish Linux
  local measurements, hosted Windows CI and the still-unverified destination Windows Server.
- External-action observations: no paid transports, live collection, real notifications or orders.
  Do not rely solely on hard-coded zero counters as proof.

Update README, DESIGN, implementation plan and release notes to match measured results. Preserve
older executed reports and append later disposition; do not rewrite historical numbers.

## 7. Next stage after the software gate passes

Use `docs/WINDOWS_DEPLOYMENT.md`. Prepare the concrete commands/configuration and evidence template
offline. Run only external steps covered by actual authorization, available credentials and explicit
spend/destination limits. Do not repeatedly ask for permission already granted, and do not request
plaintext keys in chat. Record absent prerequisites as blocked rather than inventing success.

| Stage | Required measured evidence |
|---|---|
| Destination Windows | Service identity/ACLs, paths and clock health, authenticated endpoints, startup/reboot, bounded recovery and matching production/research/paper backup-restore |
| Delta and reference data | Current discovered BTC/gold instruments and units; bounded collection, receipt clocks, gaps/reconnect/reconciliation; missing token gold or licensed reference explicitly unavailable |
| CoinGlass | Actual subscribed entitlement and supported exchange/pair/endpoint coverage, refresh age and unavailable/error behavior |
| GPT and Claude | Configured/returned models, identical canonical input, actual bounded request/usage evidence and independent failure behavior |
| Notifications | One specifically authorized destination/test, real receipt or uncertain-receipt state; stale/terminal cases suppress |

Two operational controls: interrupt collection during a sequence gap and verify resynchronization
before eligibility returns; make one provider unavailable and verify no dual confirmation. These
are measured integration checks, not justification for changing the strategy.

After operational acceptance, freeze a prospective experiment before collecting elapsed results.
Keep rules-only/GPT/Claude/dual on common opportunity denominators, account for latency, costs,
outages and abstentions, and report Gold/BTC and each horizon separately. Compare dual filtering
against rules-only after costs, and FAST versus SESSION behavior across observed regimes. Define
sample/coverage/uncertainty criteria; elapsed weeks alone do not establish an edge.

## Definition of done and stopping rule

This corrective task is done when the three review items and finite parity/recovery/resource matrix
pass, all earlier exact regressions remain green, and the evidence/status documents agree. Push a
reviewable PR and report verification plus the precise next operator action. Do not automatically
add another feature phase. If a listed contract still fails, state the exact failing case and keep
it open; do not mark software acceptance complete based only on a green baseline test count.
