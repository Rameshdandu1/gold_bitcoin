# Independent Phase 4 review and next implementation gate

Review date: **2026-11-21**. Repository: `Rameshdandu1/gold_bitcoin`.

Reviewed main: [`3b07d21079729da41f53c80fa5c4604b1dea9499`](https://github.com/Rameshdandu1/gold_bitcoin/commit/3b07d21079729da41f53c80fa5c4604b1dea9499), following merged [PR #6](https://github.com/Rameshdandu1/gold_bitcoin/pull/6). Implementation head: `7185d22f04ca1363582682598aeae44cf24310fd`. Previous review/instructions PR #5 is merged.

## Verdict

**Phase 4 contains useful corrections and research components, but its SOFTWARE/FIXTURE COMPLETE acceptance claim is not supported by the public workflows.** The 206-test baseline passes. The original Phase 3 reproductions improve substantially. However, replay does not run the six engines, evaluation imports precomputed outcomes, the paper worker only imports decisions, and independent probes reproduce invalid outcomes, time-validation leakage, misleading comparisons and stale alert dispatch.

The next milestone is **Phase 5: research completion, correctness and operational validation**, specified in [CODEX_PHASE_5.md](../../prompts/CODEX_PHASE_5.md). The earlier roadmap's derivatives/optional-execution work is deferred. Neither the current review nor Phase 5 authorizes orders, trading credentials, paid calls, real notifications or deployment.

This is a review and instruction change, not an application fix. All market values, credentials, usage and external responses in the probes were **hypothetical local fixtures**. There were **zero paid API calls, zero live exchange/CoinGlass calls, zero real notifications and zero orders** in this review. Source locations below refer to the reviewed commit.

## Verification

| Check | Independently observed result |
|---|---|
| Phase 4 CI | [Run 44924680442](https://github.com/Rameshdandu1/gold_bitcoin/actions/runs/44924680442) succeeded; backend and frontend steps inspected |
| Python | **206 passed** in 6.47 seconds; two dependency deprecation warnings |
| Ruff | Lint passed; 75 files already formatted |
| Compilation | `python -m compileall -q src tests` passed |
| Frontend | `npm ci --no-audit --no-fund`, typecheck and production build passed |
| Additional review | Real CLI, evaluator, worker, storage, consensus and SDK request construction exercised with temporary databases and fake transports |

Local verification ran on Linux. CI uses Windows. Destination Windows Server installation/reboot recovery, actual provider/model entitlement, real Slack acceptance, long collection, licensed coverage and empirical performance remain unverified.

## Original corrections confirmed

| Prior finding | Observed improvement |
|---|---|
| P3-01 startup | `.env.example` loads with a cleared environment; external flags are off and blank rates are `None`. |
| P3-02 reconciliation | Complete nonaligned polling and genuinely incomplete collection tests pass. The rolling start is aligned and interval coverage is checked. |
| P3-03 request identity | Both actual SDK request constructions include the same canonical payload and digest. Responses derived only from request-visible fields validate. |
| P3-04 repeated observation | Two same-candle/time-only emissions retain one active revision and one matching queued run. |
| P3-05 commit race | A concurrent trade insertion changes the version and blocks the stale commit; an older-timestamp insertion also changes the version. Both produce zero outbox rows. |
| P3-06 known invalidity before checks | A breach/disconnect already present when the alert checks begin suppresses delivery. |
| P3-07 request/spend bounds | A conservative 7,227-token input against a 1,000-token cap makes zero calls; settled actual consumption above the cap blocks the next reservation. |
| P3-08 recovery/destination | Acceptance-unknown cancellation remains `DISPATCH_STARTED` and is not blindly resent; a changed destination is suppressed. |
| P3-09 model/status | Queued model-name mismatch makes zero calls; failed terminal status returns `INVALID_FINISH_STATUS`. |
| P3-10 structure | The earlier sequence now labels the downward continuation at 84.5/minute 21 as BOS and the upward reversal at 99.5/minute 24 as CHOCH. |
| Saved-result recovery | With a 30-second lease and 90-second deadline, recovery finalizes WAIT without redispatch. That fixture has no current feed evidence, so WAIT is correct. |

These are specific confirmed corrections. They do not prove every broader guarantee. In particular, the original read/commit race is fixed while the distinct alert read/dispatch race below remains.

## Findings and incomplete workflows

P1 denotes a material operational or research-validity blocker. P2 denotes an identity, accounting, recovery, scaling or incomplete-delivery issue. P4-01 and P4-12 explicitly identify incomplete public workflows; other findings include executed counterexamples.

### P4-01 — P1: the research commands do not form an engine-to-outcome pipeline

Locations: `research_replay.py:156–231`; `research.py:80–179`; `paper_worker.py:29–56`.

Replay appends observation IDs to a visible list, computes coverage status and hashes that list. It does not parse market payloads into production feature state, reconstruct books, call the six detectors, apply candidate/lifecycle rules, produce arm decisions or evaluate outcomes. The `evaluate` command requires an external `--opportunities` file containing already-calculated `OpportunityRecord` outcomes. Neither outcome helper is invoked by a public research command. The paper worker reads only a recorded-decision JSONL file; it does not observe market events or advance positions/outcomes.

The documented two-record fixture command returns:

```text
complete=True
experiments=1 replay_points=4 opportunities=0 reports=0
detector/feature/outcome-evaluator calls=[]
```

Zero candidates from two records alone would be expected and is not the finding. The missing function calls and source control flow establish that no dataset can currently take this command through the required strategy evaluation. Changing every replay observation payload to a different price produces identical replay points and rolling hashes because only visibility IDs are processed.

**Required completion:** build a public path from validated observations through the existing six engines, proposal/revision policy, recorded/fake analyst evidence, current-risk checks, outcome evaluator and persisted report. The paper worker must consume the corresponding live-style local event stream. Keep an explicitly labelled import mode if useful; importing caller-calculated P&L is not the normal strategy evaluator.

### P4-02 — P1: entry, path and OHLC semantics can produce unsupported wins

Locations: `research_evaluation.py:135–172,186–268,277–320`; `research_models.py:285–298`.

The new quote evaluator drops all pre-readiness quotes and checks `maximum_quote_gap_seconds` only before entry. The bar evaluator checks rough overlap and touches without enforcing approval, fully eligible boundaries or complete earlier coverage.

Both bullish and bearish fixtures reproduce:

| Input | Actual result |
|---|---|
| Known stop breach at +10 seconds, recovery/dual entry at +30, target at +60 | `TARGET_BEFORE_STOP`, `data_complete=True` |
| Entry at +30, next quote at +170, configured maximum gap 10 seconds | Complete target despite a 140-second gap |
| Readiness +30, target-containing bar spans +0 to +60 | Complete target; hit may precede entry |
| Expiry +180, target-containing bar spans +120 to +240 | Complete target; hit may follow expiry |
| REJECTED decision followed by target-containing bar | Complete target for a rejected arm |
| Only +170 to +180 bar supplied after readiness +30 | Complete target despite missing intervening history |

There are two additional timing inconsistencies. `provider_latency_ms` is added to the already factual `ready_at_utc`, while `ExperimentConfig.entry_latency_ms` is not wired into evaluation. A +30 readiness with a ten-second recorded provider duration misses an executable +30 entry and +35 target because evaluation starts at +40. At readiness exactly equal to expiry, both directions can open and immediately TIME_EXIT; the live eligibility convention rejects already-expired admission.

**Required correction:** validate pre-entry invalidation/exhaustion, decision state, instrument/source validity, entry delay exactly once, full observable path and boundary coverage. Preserve incomplete/ambiguous cases; never resurrect a known stopped proposal. Treat OHLC touch classification separately from executable fills. Test positive complete paths as well as these failures.

### P4-03 — P1: future training data and holdout leakage remain

Locations: `research_evaluation.py:324–370`; `research.py:149–178,183–196`; `research_models.py:161–173`.

The fold helper sorts opportunities, but uses both earlier and later groups for training. With four successive days and two folds, its first result is:

```text
train=(day3, day4) test=(day1, day2)
```

This is not the promised past-to-future walk-forward study. A symmetric purged study would need separate labeling and does not replace operational walk-forward validation.

Holdout membership uses only earliest opportunity observation. An opportunity observed at hour 71 with outcome information through hour 73 remains in development when holdout begins at hour 72.

The public evaluator separately aggregates all rows before constructing folds. Even when `--holdout-start` is supplied, its headline metrics and paired comparisons include holdout outcomes. In a four-opportunity fixture with two development and two holdout rows:

```text
development only: complete_executions=2 net_pnl=0.01391780
CLI with holdout: complete_executions=4 net_pnl=0.20781760
```

The frozen config's holdout and embargo settings are not loaded by the evaluate command; separate CLI defaults govern them. The report command recomputes aggregate metrics from all stored opportunities again.

**Required correction:** derive chronological splits and their policy from the immutable experiment, exclude future training rows and purge every outcome-information interval crossing the protected boundary. Compute/report metrics by the intended partition. Make final holdout evaluation an explicit, versioned action, not an accidental side effect of an ordinary report.

### P4-04 — P2: revision counting and paired comparisons misstate the intended study

Locations: `research_evaluation.py:374–423,426–483`.

Two revisions of one opportunity are counted as two opportunities and two completed executions. The fixture's single 4.8 outcome becomes 9.6, with denominator 2. No frozen revision-selection or rearm policy prevents double counting.

The paired estimator also drops known rejections because it requires numeric completed P&L on both arms. A ten-day fixture, using actual quote-evaluator results, contains each day:

- one accepted opportunity returning +4.8 in both arms;
- one rules-only stop returning -6.2 that the dual arm rejects.

Actual computed totals are rules-only **-14.0** and dual **+48.0** across 20 common opportunities. Yet the paired calculation uses only the ten common executions and returns mean difference **0.0**, interval **[0.0, 0.0]**. This can be a separately labelled common-executions diagnostic; it does not measure the filter's operational benefit or missed opportunities.

**Required correction:** predeclare the opportunity/revision counting unit and estimand. Include known no-position choices under their declared payoff/cost policy; leave unavailable evidence unknown. Retain separate conditional-execution and complete-cohort analyses. Preserve paired time blocks and explain whether weighting is per opportunity or per day.

### P4-05 — P1: the paper ledger does not enforce prospective chronology or decision-state consistency

Locations: `research_storage.py:207–267`; `paper_worker.py:29–56`.

The ledger checks insertion order but not whether the economic entry/outcome occurred after the decision was persisted. A real helper-generated trade enters at **2026-01-02 10:00:11 UTC** and exits at **10:00:30**. Its decision is inserted on **2026-01-03 10:00:00**, then its historical outcome one second later. Both writes are accepted and the summary labels it prospective paper observation.

A second probe records a REJECTED decision, then attaches a `TARGET_BEFORE_STOP` executed outcome. It is also accepted: the outcome write does not validate the stored decision payload, target/configuration or economic timestamps.

The worker's cursor is the line number under a global `recorded_decisions` source key. After reading one row from file A, changing to a new one-row file B skips that row and reports zero records without a gap or source-change error.

**Required correction:** freeze candidate/arm/configuration and persist the decision before eligible entry/future outcome access. Separate historical imports from prospective events. Enforce state/time/identity invariants and a legal append-only paper transition model. Bind cursors to source identity and generation; detect rotation/truncation. Implement the market-event/outcome consumer identified in P4-01.

### P4-06 — P1: final alert delivery omits quote gates and is not fenced against checked evidence

Locations: `notifications.py:127–178`; `storage.py:1845–1859`; current consensus policy in `consensus.py:224–244`.

The worker now checks a fresh price/source snapshot, but only a subset of current eligibility. With a previously valid hypothetical Gold confirmation at entry 2,600 / stop 2,590:

| Updated valid, fresh book | Current consensus | Actual fake alert |
|---|---|---|
| Bid 2,590 / ask 2,610 | WAIT: SPREAD and ENTRY_DRIFT | One send; SENT |
| Bid 2,605 / ask 2,605.2 | WAIT: ENTRY_DRIFT | One send; SENT |

Separately, `mark_outbox_dispatch_started` compares claimed status, owner and generation but not the risk token, active revision, lifecycle or expiry. Inserting a 2,589 stop trade between eligibility read and the dispatch transition still sends. Persisting both that breach and terminal INVALIDATED before the transition also still sends. A fresh reread returns WAIT in both cases.

**Required correction:** reuse the full deterministic current-risk policy for the originally approved target identities. Fence the short dispatch-intent transaction against the exact checked evidence, revision, lifecycle, current time and lease. On change, re-evaluate or suppress. Release the transaction before HTTP. This guarantees behavior relative to locally persisted evidence at dispatch authorization, not knowledge of future exchange events or external exactly-once delivery.

### P4-07 — P2: an already terminal proposal still consumes both analyst calls

Locations: `review_worker.py:197–253`; `orchestration.py:226–305`.

A candidate is queued, then an authoritative INVALIDATED lifecycle event is persisted before the real review worker starts. Request-only fake providers are still invoked twice. The final decision is correctly WAIT.

```text
predispatch_terminal=INVALIDATED transport_calls=2 decision=WAIT
```

**Required correction:** preflight active revision, lifecycle, expiry, required sources and configuration before reservations/dispatch. Record a typed non-dispatch disposition. Preserve post-response checks because conditions can change during inference. This finding is wasted dispatch, not false confirmation or an observed real provider charge.

### P4-08 — P2: recorded request configuration is only partly enforced

Locations: `worker.py:405–413`; `orchestration.py:226–232`; `ai.py:283–288`.

Model-name drift is fixed, but the mismatch check ignores other recorded request parameters. A run queued with `max_output_tokens=64` executes both providers with current settings at **650** and records both outcomes as SUCCEEDED under the same run identity.

**Required correction:** execute the exact frozen configuration or reject/requeue under a new identity. Compare actual request parameters, prompt/schema and relevant policy versions, not only model names. Keep the corrected model-name test.

### P4-09 — P2: default recovery repeatedly reclaims expired results

Locations: `config.py:35,38`; `storage.py:1215–1226,1618–1621`; `review_worker.py:267–280`.

The default deadline is **90 seconds** and the lease **120 seconds**. After both results are saved and a process stops before finalization, recovery only reclaims RESULTS_READY after lease expiry. Finalization is then past its deadline and is rejected without a terminal job disposition.

```text
at121=RESULTS_READY at242=RESULTS_READY lease_generation=3
decision=None original_transport_calls=2 redispatch_calls=0
```

**Required correction:** persist a terminal expired/WAIT disposition and complete the job without late confirmation or redispatch. Preserve the passing within-deadline recovery. Test shipped defaults, changed evidence, lost leases and queue progress; do not extend deadlines merely to allow stale confirmations.

### P4-10 — P2: research identity and mutable records weaken reproducibility

Locations: `research_replay.py:44–60,168–177,199–206`; `research_models.py:92–111,213–227,341–420`; `research_storage.py:94–130`.

Executed counterexamples:

- A manifest with correct per-file checksum/count but an all-zero self-asserted `content_hash` is accepted. There is no recomputation of the dataset identity.
- The replay helper accepts a checkpoint under the same experiment ID after cadence changes from 60 to 30 seconds and target index from 1 to 2. The checkpoint does not bind the config. The existing database's immutable experiment check is a useful later guard; it does not fix this helper/portable-checkpoint contract.
- Changing price payloads while keeping observation IDs/times unchanged produces the same replay points/hash. Visibility hashes alone do not commit to evidence or engine decisions.
- `INSERT OR REPLACE` changes an opportunity's result under the same experiment/opportunity/revision identity. One fixture changes net P&L from **0.00695890** to **0.19693990** without a new revision or experiment.

Source inspection also shows that imported outcomes and label intervals lack cross-field linkage to their parent opportunity, economic timestamps, approved target and recorded evidence. These omissions are distinct from the executed examples above.

**Required correction:** derive and validate canonical dataset/config identities, bind checkpoints to both plus algorithm/state versions, and validate restored state. Store immutable opportunities/outcomes and versioned reports; allow identical idempotent writes, reject conflicts. Validate source/provenance before accepting an archived outcome and compute label-knowledge bounds from facts.

### P4-11 — P2: replay still retains growing history at every point

Locations: `research_replay.py:175,181,191–215,223–230`; `research.py:103–116`.

The disk spool bounds input sorting, but replay keeps every visible ID, copies the whole list into every returned point and retains all points until the command finishes. At one new event/evaluation per second:

```text
500 events/points:  125250 retained ID references
1000 events/points: 500500 retained ID references
```

Doubling this fixture roughly quadruples retained history. This is a direct structural count, not a measured production throughput claim. The command also writes points/checkpoint only after the entire replay call returns.

**Required correction:** stream outputs to bounded transactional batches, retain only necessary feature/window state and durable references, and checkpoint committed offsets/state incrementally. Measure bounded-memory growth and interruption recovery on a finite declared workload; do not describe disk sorting alone as a bounded replay.

### P4-12 — P2: reports and research UI are summary scaffolds

Locations: `api.py:210–224`; `frontend/src/main.tsx:89–98`; `research.py:183–243`; `research_storage.py:133–160`.

Source inspection establishes that the research route/UI only expose counts and empty/exploratory summaries. There is no experiment detail, six-engine/arm outcome comparison or paper event view. `data_mode` is hardcoded to `NO_DATASET_SELECTED`. Exported summaries lack required opportunity/outcome evidence tables and per-partition results; manifest/config copies are optional arbitrary input paths rather than the experiment's authoritative stored records.

**Required completion:** expose actual experiment selection and immutable provenance, partition-aware arm/engine metrics, coverage and uncertainty, paper transitions, meaningful unavailable states and reproducible complete exports. Keep synthetic results visibly hypothetical. This is an incomplete workflow finding, not a claim of an observed real-data dashboard leak.

## Required implementation evidence

The next PR must demonstrate the public workflow, not only isolated helpers:

1. Validated local market events generate production-engine opportunities and versioned arm decisions.
2. The evaluator derives outcomes from subsequent evidence and preserves incomplete cases.
3. Chronological development/test/holdout boundaries govern actual report rows and comparisons.
4. The same local stream drives prospective paper state with decisions persisted before entry.
5. CLI, API/UI and exports agree on counts, selected revisions, costs, partitions and provenance.
6. Recovery, dispatch fencing, immutable configuration and bounded replay remain verified under negative and positive cases.

At least two complete hypothetical end-to-end streams, one Gold and one BTC, must pass through the public commands. Cover all six engines with a deterministic parity matrix. Real datasets, actual model outputs and weeks of observation remain separate evidence gates. Do not replace absent real evidence with fixtures or equate financial-model agreement with measured accuracy.

## Methodology references

- [scikit-learn TimeSeriesSplit](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html): describes past-to-future validation and a sample-count gap; irregular label intervals require additional handling.
- [SQLite isolation](https://www.sqlite.org/isolation.html): describes explicit read snapshots, serialized writes and WAL snapshot behavior; an application must still connect the checked version to its conditional state transition.
- [Kong et al., Evaluating LLMs in Finance Requires Explicit Bias Consideration](https://proceedings.mlr.press/v306/kong26i.html): identifies look-ahead, survivorship, narrative, objective and cost concerns in financial LLM evaluation. This reference does not validate this application's performance.

Proceed with [CODEX_PHASE_5.md](../../prompts/CODEX_PHASE_5.md). Preserve the working corrections and complete the missing research path before derivatives or any future execution design.
