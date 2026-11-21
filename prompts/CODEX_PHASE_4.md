# Codex Phase 4 — integration corrections, historical evaluation and paper research

Repository: **https://github.com/Rameshdandu1/gold_bitcoin**.

Implement this task in dependency order. The objective is to determine whether the six quantitative engines and independent AI filters add measurable value under realistic timing and costs. The first slice fixes independently reproduced Phase 3 defects. Do not turn passing fixtures or plausible model explanations into claims of a trading edge.

## 0. First instructions

1. Read `AGENTS.md`, `DESIGN.md`, `README.md`, `docs/IMPLEMENTATION_PLAN.md`, `docs/audits/phase-3-independent-review.md`, this file, then relevant source/tests. Preserve the existing repository and native Windows architecture.
2. Inspect `git status`, remotes, branch and recent commits. Fetch current main. Phase 3 was reviewed at `d1978d30e48c0b8656d969da00ea70a7e4659562` after PR #4 merged; verify actual current state. Do not overwrite unrelated work or assume an old finding remains unfixed.
3. If these instructions are only on the documentation branch, fetch it explicitly:

   ```text
   git fetch origin refs/heads/docs/phase-4-review-and-instructions:refs/remotes/origin/docs/phase-4-review-and-instructions
   git show origin/docs/phase-4-review-and-instructions:prompts/CODEX_PHASE_4.md
   git show origin/docs/phase-4-review-and-instructions:docs/audits/phase-3-independent-review.md
   ```

4. Create `feature/phase-4-evaluation-and-paper-research` from updated main. Copy the two instruction/review files from the documentation branch if main lacks them. Do not merge unrelated feature branches. Record code/instruction SHAs and a short implementation plan.
5. Establish the baseline. The reviewed commit passed **171 Python tests**, Ruff lint/format, compilation, TypeScript checks and frontend build. Run the checks yourself; the number is evidence, not a target to preserve by deleting failing tests.
6. Start with failing tests for P3-01, P3-02, P3-03 and P3-05. Implement the full **4A** correction set before promoting any real confirmation or performance report. Then deliver the replay, labels, comparison and paper-research slices. Do not stop at a design document.

## 1. Boundaries and delivery sequence

Keep this application research-only. No orders, trading keys, leverage, account-position access, automated options execution, or live money. Delta tokenized Gold remains distinct from licensed XAU/USD. Gold target distances are USD per verified underlying unit; BTC targets remain percentage/ATR based.

Keep `LIVE_INGESTION_ENABLED=false`, `AI_ENABLED=false`, `ALERTS_ENABLED=false`, `TRADING_ENABLED=false`. Add an explicit paper-worker switch defaulting off. Implement opt-in capabilities, but do not enable paid requests, real notifications, live collection or deployment during this development task. Do not ask for secrets in chat or commit them.

Use the existing Python/FastAPI, React/TypeScript and SQLite stack. Isolate experiment/paper state from production candidate/review/outbox data. A historical replay must never enqueue a production paid review or notification. Reuse corrected contracts and calculation code rather than creating a second subtly different strategy implementation.

| Slice | Deliverable | Required evidence |
|---|---|---|
| **4A** | Phase 3 integration corrections | Reproductions fail before fixes and pass after, including positive paths |
| **4B** | Dataset manifest and as-observed replay | Deterministic replay using factual availability, coverage and source versions |
| **4C** | Entry/outcome/cost engine | Valid instrument, timing, ordering and coverage; conservative ambiguous cases |
| **4D** | Arm comparison and chronological validation | Fair denominators, actual latency/cost, purged label overlap, untouched test periods |
| **4E** | Prospective paper ledger | Immutable decisions before outcomes, restart-safe observation and no external execution |
| **4F** | Authenticated reports, CLI and operating guide | Reproducible reports, insufficient-data states, evidence-based acceptance gates |

Two end-to-end examples, explicitly hypothetical: a Gold target reached after an eligible ask-side entry and before its stop can receive a completed research outcome; a BTC target touched while Claude is still evaluating cannot be backdated into a dual-review win.

## 2. Slice 4A — mandatory integration corrections

Use the independent review's finding IDs in regression tests and the verification report. Fix underlying contracts, not just the sample values. Do not weaken fail-closed checks to make more candidates appear.

### 2.1 Bootstrapping and reconciliation: P3-01 / P3-02

- Make the documented `.env.example` bootstrap usable. Empty optional numeric rates must mean deliberately missing, or be omitted/commented. Preserve non-ready pricing and zero paid dispatch when rates are absent. Validate price/cost settings as finite, permitted values with actionable redacted errors.
- Exercise actual settings loading from a copied template under an isolated environment. Test all external flags off and a configured operator/model with missing rates. Do not require a live API key to start the read-only application or display a not-ready state.
- Reconcile complete, closed, interval-aligned buckets only. Align the rolling acquisition start and track collector coverage, including reconnect/startup gaps. Do not label a half-observed minute as a complete trade candle.
- Keep per-symbol reconciliation age/state accurate and apply the documented prerequisite. A truly mismatched candle still blocks admission.

Examples: a poll at 11:05:30 must not compare only 30 seconds of streamed volume with a 60-second REST candle; a collector that really missed the first half-minute must remain incomplete rather than being repaired with invented trades.

### 2.2 Provider request identity and run lifecycle: P3-03 / P3-04 / P3-09

- Supply the required analysis digest explicitly to both real SDK requests. Keep it outside its own hash preimage. One valid design is a server-generated wrapper with `analysis_input_hash` and the exact canonical analysis payload. Test outgoing request contents and schema for both providers, including wrapper identity and unchanged input bytes.
- Build a contract fixture that derives the response only from the request-visible fields. It must not obtain `analysis.digest` from a hidden fixture closure. Invalid echo remains a rejection, not a reason to weaken the check.
- Separate new observations from material proposal revisions. Define a versioned material-change policy using explicit features/geometry/coverage changes. Time-only refreshes must not activate a new proposal every poll. Do not transfer approval onto genuinely changed evidence.
- Material supersession must atomically obsolete/cancel old pending work and queue the appropriate new exact revision, subject to limits. Preflight must check revision, terminal lifecycle, expiry, required data and configuration before spending. Test repeated same-candle observations and changed stop/target/evidence separately.
- Bind execution to the queued provider configuration, including requested models, prompt/schema, relevant parameters and policy versions. Execute the frozen configuration or fail/requeue with a new identity; changing environment variables must not silently change the meaning of an old run.
- Require provider-specific successful terminal status in addition to parsed JSON, model identity and semantic validation. Handle failed/cancelled/incomplete/refused output explicitly. Use current official SDK contracts; no guessed model names or silent model fallback.
- Introduce a durable results-ready/decision-pending stage, or an equivalent recoverable transaction boundary. Do not mark a job fully completed before its decision/outbox finalization is durable. A restart after saving two valid results must finalize without paying for both calls again.
- Carry the stored absolute run deadline through response completion and commit. Reject late results, expiry equality and stale lease ownership. Persist unknown dispatch states; do not reclaim a possibly billed request as certainly uncalled. Honor applicable Retry-After and the remaining deadline.

Examples: switching configured models after enqueue must not execute under the old model-run identity; a crash after both responses are saved must resume finalization without duplicate provider dispatch.

### 2.3 Consistent risk evidence and spend: P3-05 / P3-07

- Read all risk facts and the version identifying those facts from one consistent database snapshot. Use a monotonic generation covering every relevant persisted trade, including a later insertion with an older event/receive timestamp, plus book/source/revision/lifecycle versions.
- Compute from that snapshot and conditionally commit only if its versions still hold. Check current time, run deadline, candidate expiry and lease/fencing state in the commit path. Retry/re-evaluate safely on changes; do not let a stale worker finalize a newer owner's job.
- Keep transactions short; no transaction spans a provider or Slack HTTP request. Define the scope of versions per affected market to avoid unrelated symbols indefinitely starving each other. Record the final risk evidence and generation separately from the frozen analyst input.
- Before dispatch, bound the **entire** model request, including canonical input, digest wrapper, instructions and schema overhead. Use a supported token counter or a documented conservative upper bound; never merely multiply a configured limit by a rate while sending unlimited input. Oversized requests make zero paid calls or create a new explicitly versioned reduced packet; no silent evidence truncation.
- Budget admission must count settled actual consumption plus unresolved/unknown reservations. A known actual cost above its estimate must reduce remaining headroom and block subsequent calls. Reconcile provider-specific usage categories and rates without double-counting. Unknown usage remains reserved; configurable daily limits and concurrent reservations remain atomic.
- Version the pricing configuration and store the actual usage basis. Mark provider billing uncertainty honestly; a software budget cannot guarantee the provider invoice when rates/usage are unknown.

Examples: a stop breach inserted between risk read and commit must prevent confirmation even when its receive timestamp is older than the latest row; reported usage above a reservation must prevent the next request when the daily limit is exhausted.

### 2.4 Delivery integrity: P3-06 / P3-08

- Recheck confirmation eligibility immediately before dispatch using consistent current market/source/lifecycle evidence, not only a cached lifecycle row. Suppress stale intents with a durable reason. A known breach must not wait for another worker to materialize INVALIDATED before it blocks sending.
- Keep terminal-notification rules separate: source loss should not suppress the notice explaining source-loss invalidation.
- Persist a dispatch-start transition before external delivery. Recover claimed-but-undispatched work separately from dispatch-started/acceptance-unknown work. The latter requires reconciliation or an explicitly supported idempotent retry policy, not automatic lease-expiry resend.
- Use the immutable destination bound to each intent. If current credentials cannot serve it or configuration has changed, block with a destination reason. Do not substitute the current default channel while retaining the old destination's delivery key.
- Test fake acceptance followed by cancellation/crash, and transient errors that definitively occurred before acceptance. Do not assert universal exactly-once Slack delivery. No real messages during development.

Examples: a recorded stop breach or disconnected required feed suppresses a pending confirmation; an intent for channel A cannot silently be sent to channel B after an environment change.

### 2.5 Structure and API input handling: P3-10 and lower-priority note

- Replace the union-of-all-historical-pivot-kinds bias with a documented chronological trend-state rule based on relevant latest confirmed structure/prior breaks. Preserve the already-correct first-break identities and no-look-ahead pivot confirmation. Increment rule versions when semantics change.
- Test established bearish continuation and bearish-to-bullish reversal after an earlier bullish period, then mirror the sequence. Do not claim a direction flip from a test that only validates BOS/CHOCH labels.
- Handle non-ASCII Basic credentials consistently, using byte comparisons or an explicit input policy; invalid credentials must not produce an internal server error. Keep authentication, exact CORS and loopback/HTTPS boundaries intact.

**4A exit gate:** all reproduced findings have meaningful negative and positive regression tests; fresh-template startup works; actual request construction is contract-tested; finalization/dispatch crash boundaries are tested. Keep paid providers and notifications off. Reassess any unresolved findings explicitly before proceeding with empirical claims.

## 3. Slice 4B — versioned data and as-observed replay

### 3.1 Dataset manifest and evidence quality

Create typed, versioned `DatasetManifest` and `ExperimentConfig` contracts (names may follow project conventions). Persist at least:

- Dataset/experiment ID and content hashes; code commit, rule/schema/feature versions; creation time and source license/provenance.
- Venue, actual symbol/product ID and **time-valid** instrument contract multiplier, tick size, quote/base/settlement currencies, listing/availability intervals. Do not apply today's contract spec retrospectively without evidence.
- Coverage by source and interval: raw trades, snapshots/deltas, candle observations/revisions, instrument discovery, reconciliation, external metrics and provider results. Track gaps, sequence/checksum health, stale periods, duplicates and exclusions.
- Exchange event time, receive/availability time, persistence sequence and raw observation/revision identity. Preserve immutable evidence and distinguish originally observed history from later downloads/corrections.
- Experiment evaluation schedule, horizon/expiry, target identity policy, feature prerequisites, cost/fill policy, model/prompt/config identities, folds, seeds, trial count and report schema.

The current journal is an input, not proof of months of usable history. Importers must validate file/source schema, monotonic identities, finite prices/units, UTC-aware times and coverage. No forward-filled fake ticks/books/OI or fabricated availability times. Use a separate dataset/experiment store or a consistent read-only backup; importing/replaying must not mutate the live journal, active candidates, budgets or outbox.

Explicit data modes:

| Mode | Permitted claim |
|---|---|
| Synthetic fixture | Software behavior only; visibly hypothetical |
| Later-downloaded OHLC history | Limited candle-only study with documented availability/fill assumptions; no claim of historical live 5,000-trade/book features |
| Recorded as-observed market data | Replay of supported features during actually covered intervals |
| Recorded prospective model results | Analysis of exact decisions/latency/config recorded before outcomes became available |
| Retrospective new LLM calls | Exploratory analysis with possible model-training hindsight; separate from prospective evidence |

Examples: 1m candles cannot reconstruct individual 5,000-trade flow; current CoinGlass funding/OI cannot be filled backward into a missing historical snapshot. If a required input is unavailable, mark the experiment/engine ineligible and report the count/reason.

### 3.2 Replay clocks and parity

- Implement an injected clock and bounded event reader. The operational replay schedule follows **factual availability/persistence and the configured evaluation cadence**, while feature windows use exchange event time. A candle that closes at 10:00 and arrives at 10:00:01 is not available at 10:00, but must be considered at the next scheduled eligible evaluation.
- Include observation arrivals, scheduled polls, source transitions, instrument changes, reconnect/resync, revisions, provider completions and expiries as explicit events. Define deterministic tie-breaking. Do not use wall-clock `now()` inside replay logic.
- Never expose observations later than the simulated availability clock to features/analysts. Keep outcome-path access in a separate evaluator after the decision has been frozen. Later corrections must not rewrite earlier decisions.
- Restore books from an actually available valid snapshot plus ordered deltas. Gaps invalidate until resynchronization. Preserve trade aggressor classification, contract normalization and exact count/duration windows.
- Reuse production detector/material-change/lifecycle/risk rules. Replay jobs/decisions use isolated experiment namespaces and fake/recorded review providers; default replay does not contact external APIs.
- Support checkpoints/resume and deterministic output hashes. A checkpoint must include state and input offsets/versions needed to reproduce the same output, not just the last candle timestamp.

Examples: the GOLD_FAST and BTC_FAST close+1-second availability probes must match an equivalent live-style schedule; inserting a late corrected candle must not alter a decision that predates its arrival.

**4B exit gate:** two complete hypothetical streams produce identical replay outputs across runs and checkpoint restarts; deliberately missing source coverage produces explicit unavailable results; no network, paid call, production review or notification is triggered.

## 4. Slice 4C — entry, outcome and cost semantics

Replace or harden `backtesting.evaluate_target_before_stop`; its current partial-bar, symbol and coverage behavior is unsuitable for performance measurement. Introduce a versioned result contract that records a reason and supporting event IDs, not only a five-value enum.

### 4.1 Earliest eligible entry and immutable targets

- Distinguish signal candle close, observation availability, candidate creation, provider completion, final eligibility, hypothetical entry and expiry. Every research arm has its own actual decision-ready time. Never fill a delayed AI approval at the earlier candle close.
- Use the first eligible observable executable quote at/after readiness plus the configured latency/fill policy. A long enters on ask and exits on bid; a short enters on bid and exits on ask, with adverse slippage where configured. A trade-only or OHLC-only study must disclose its weaker fill assumptions.
- Freeze candidate/revision, target IDs/indices, entry policy, invalidation and target distances before reading the outcome path. Target indices remain 1-based within the exact packet; filtering must not renumber targets or relabel a 20-dollar tier as the original 10-dollar tier.
- If stop/target was already crossed before entry, the proposed entry is stale/exhausted under the policy. Do not book a retroactive win. Entry delay consumes the existing horizon; it does not reset expiry unless a different policy was predeclared and separately identified.
- Evaluate separate target policies as separate experiments. Do not count every target from one candidate as an independent full-size trade and sum them into a portfolio. Partial-exit strategies require their own explicit position/cost model and are optional later work.

Examples: a Gold target hit 20 seconds before both models finish is not a dual-review win; a BTC short must account for entering at bid and buying back at ask, rather than using mid-price for both legs.

### 4.2 Outcomes, path coverage and ambiguity

- Validate instrument/venue, monotonic event identity, interval alignment, UTC timestamps, finite geometry, entry/expiry bounds and required path coverage **before** returning a target/stop outcome.
- Prefer ordered trade/quote evidence where available. If one OHLC candle can contain both stop and target, the order is unknown unless finer evidence resolves it. At entry/expiry boundaries, a partially overlapping candle cannot prove a hit occurred inside the eligible interval.
- Record at least: no entry and reason; target before stop; stop before target; time exit/expired with complete coverage; ambiguous ordering; incomplete/censored coverage. Keep their denominators explicit.
- Treat ambiguous cases conservatively in the primary result or show an explicit bounded sensitivity range. Never drop ambiguous/loss-prone rows silently or count them as wins. Incomplete data is a data-quality outcome, not automatically a time exit.
- A gap through a stop is filled using the first observable adverse executable price under the declared policy, not magically at the nominal stop. A target touch alone does not guarantee a limit fill without a declared fill model. Avoid invented queue priority.
- Calculate favorable/adverse excursion and time to outcome only over supported observations after eligible entry. Unknown intervals remain marked unknown.

Examples: an aligned 00:00–01:00 candle cannot prove a target hit before a 00:30 expiry; a lone 00:29 candle cannot establish that the preceding 29 minutes were stop-free. Also reject BTC candles supplied to a Gold candidate.

### 4.3 Economics and units

- Use verified contract multipliers, tick rounding and explicit hypothetical quantity. Report gross price distance separately from monetary P&L. A $20 move in a token quote is not automatically $20 per exchange contract.
- Model entry/exit spread, both-side fees, adverse slippage and funding where the instrument/time interval requires it. Costs must be sourced/configured/versioned; unknown required rates block net-performance claims. Do not fetch paid data or invent fee schedules.
- Define net reward/risk and R-multiple denominators consistently using actual hypothetical entry/stop risk under the cost policy. Record gross and net results, costs and assumptions separately.
- Support baseline and adverse-cost scenarios frozen before test evaluation. Do not optimize costs downward to turn a loss into a gain.

Examples: a gross target hit can still have negative net expectancy when small wins and larger losses are combined with costs; a stop gap must reduce realized R beyond the nominal planned loss when the observed executable price is worse.

**4C exit gate:** bullish/bearish, Gold/BTC, entry latency, partial expiry, wrong symbol, missing path, gaps, same-bar ambiguity, tick/contract units and cost sensitivity have hand-checkable fixture outputs. The old helper cannot silently drive research reports with its previous semantics.

## 5. Slice 4D — fair comparisons and time-ordered validation

### 5.1 Four research arms and common opportunity records

Use one frozen quantitative candidate universe. The arms are filters on those proposals, not four separately invented sets of trades:

| Arm | Selection |
|---|---|
| `RULES_ONLY` | Quantitative and deterministic eligibility rules |
| `RULES_PLUS_GPT` | Same rules plus a valid GPT approval |
| `RULES_PLUS_CLAUDE` | Same rules plus a valid Claude approval |
| `RULES_PLUS_DUAL` | Same rules plus valid matching approvals and the dual consensus policy |

Preserve every opportunity, including REJECT, WAIT, timeout, not-ready, budget block, stale-before-review, superseded revision and incomplete outcome. Report the denominator at each stage: discovered, quantitatively eligible, reviewed, approved, executable, fully labelled. Never compare a dual subset against an unrelated baseline sample.

Provide two clearly distinguished analyses:

- **Deployable timing:** each arm enters only after its own required results and current-risk checks, using its actual recorded latency. This is the primary operational comparison.
- **Controlled selection study:** optionally compare filters on a matched candidate set at a documented common decision clock to isolate selection effects. Label this separately and report exclusions; do not present it as the arm's achievable early entry.

Record retained winners, rejected losses, missed winners, retained losses, abstention coverage, decision latency and model expense. A high conditional win rate on a tiny accepted fraction is not sufficient evidence of improvement.

Examples: dual agreement may avoid a losing candidate while missing a fast winner before both models respond; a GPT-only arm may have lower selectivity but earlier executable entry. Measure both rather than assume consensus is better.

### 5.2 Model evidence and hindsight controls

- Use recorded provider outputs only when their exact candidate revision, canonical request, provider/model configuration and factual completion time match the experiment.
- If real contemporaneous assessments are absent, mark that arm unavailable. Fixtures can test the evaluator; they cannot supply empirical AI performance.
- Retrospective calls to today's LLMs can contain training-time knowledge of historical outcomes even when the supplied packet is timestamp-filtered. Label them exploratory and keep them separate from prospective evidence. A prompt saying "ignore future information" is not proof of temporal independence.
- No model receives future outcome labels, another model's answer, or post-decision macro/news data. Disable tools/browsing in analyst requests. Archive prompt/model versions and distinguish model changes across periods.
- Report experiment-wide actual API spend separately from counterfactual per-arm attributable costs. If a study calls both providers once, do not claim that each of four comparison arms incurred the entire same bill, or that a rules-only system would pay for AI.
- New paid retrospective/prospective calls are a separate opt-in operator action, with an explicit call/cost cap and existing credentials configured locally. This development task makes zero paid calls.

Examples: a backfilled GPT response produced after the outcome cannot be presented as a decision recorded before it; an archived Claude result from a different model/prompt revision cannot be substituted because its direction matches.

### 5.3 Walk-forward splits, purging and trial tracking

- Use chronological train/development, validation and untouched test periods. Freeze rule thresholds, cost policies, prompts and selection criteria before opening each test segment. Do not randomly shuffle market events.
- Assign all arms and revisions of one opportunity to the same fold. Treat overlapping outcome-information intervals as dependent. Purge training opportunities whose label-information intervals overlap a validation/test interval, and apply a documented time-based gap/embargo where appropriate.
- Use the union of the observation intervals needed to determine each opportunity's arm outcomes, through the time each label becomes known. Include actual entry-to-outcome/expiry intervals, delayed provider completions, and no-entry, exhausted, rejected or censored cases where later observations determine the classification. Do not purge only filled entry-to-exit intervals; a 4-hour label or delayed no-entry result must not cross a boundary unnoticed.
- Irregular candidate events require timestamp/interval-aware splitting. A library's sample-count `gap` is not automatically a market-time embargo or a complete overlapping-label purge.
- Record every tried threshold/prompt/model variant and the selection process. Do not select the best test-period configuration and then call the same result out-of-sample. Preserve a final holdout; new tuning creates a new experiment and may require new future data.
- For the initial milestone, keep the existing six rules fixed and evaluate them before adding more indicators or a new ML model. If insufficient dates/events exist, produce an insufficient-data report and working infrastructure rather than a fabricated walk-forward result.

Examples: a pre-boundary candidate with rules ready before the boundary and dual review ready after it must stay in one fold and be purged when its label uses test-period observations; a proposal classified NO_ENTRY only after a post-boundary target crossing or timeout also needs purging despite having no filled entry. A prompt chosen after inspecting test losses must not retain the same untouched-test label.

### 5.4 Metrics and uncertainty

Report per asset, engine/horizon, direction, original target identity/distance, rule/model version and eligible regime/session where sample size supports it. Include:

- Counts and coverage for all states, including ambiguity and missing data; elapsed dates and unique trading days.
- Target-before-stop rate with explicit denominator, stop/time-exit rates, no-entry rate and time-to-target.
- Mean/median gross and net R, net expectancy, fee/spread/slippage/funding burden, and cost sensitivity.
- Profit factor with a defined zero-loss/undefined case; favorable/adverse excursion; latency, API calls and attributable cost per reviewed/accepted opportunity.
- Differences between the four arms on matched opportunities, including what was rejected or missed.
- Confidence intervals computed with a documented dependence-aware approach, such as paired day/time-block resampling. Preserve pairing across arms. Do not bootstrap overlapping ticks as if independent or claim reliable intervals from too few blocks.

Event-level R is not a portfolio equity curve. Show drawdown/equity only under a separately declared hypothetical sizing, capital, overlap and concurrent-exposure policy. Otherwise report event-level outcomes without inventing portfolio returns. No annualization of a few hours of data into a revenue projection.

Calibration metrics apply only if an explicit out-of-sample probability estimator exists. This phase's CONFIRM/WAIT/REJECT labels are not probabilities; show calibration/Brier fields as N/A rather than assigning model confidence scores.

Examples: two nearby signals derived from the same move must not count as independent statistical evidence; a profit factor with no observed losses is undefined/insufficient, not a proof of unlimited profitability.

**4D exit gate:** the same input/config reproduces the same splits/counts/metrics, future data cannot change earlier decisions, invalid study modes are labelled, and negative-control fixtures expose leakage/selection mistakes. Report actual data limitations instead of a target success percentage.

## 6. Slice 4E — prospective paper research

Implement a separate durable paper ledger, with no exchange-order client or trading credential. A paper worker observes research decisions and public market events; its positions/fills are explicitly hypothetical.

- Persist the proposal, configuration, decision-ready time, eligible entry/fill policy and selected target **before** observing future outcomes. Append position/outcome events; never rewrite entry after seeing the result.
- Maintain independent arm records linked to the same opportunity. Freeze one declared target/exit policy per paper experiment. Preserve rejected/abstained opportunities for later counterfactual analysis without presenting them as actual paper positions.
- Define legal states for no-entry, open, target/stop/time close, ambiguous and data-censored outcomes. Candidate invalidation/expiry is evidence; it does not automatically imply a particular executed paper price or complete path.
- Resume from durable cursors. Missing events during downtime must lead to backfill from an attributed source or an explicit coverage gap. Do not mark every unresolved position profitable or cleanly expired after restart.
- Store planned versus observed hypothetical fill, spread/cost assumptions, MFE/MAE, timeout/staleness, and source event IDs. Never access real balances or positions.
- Separate event studies from a hypothetical portfolio policy. If portfolio mode is added, define capital, sizing, maximum concurrent exposure, conflict handling across engines and what happens when the same asset has opposing signals. Predeclare the policy; do not retrospectively select the better engine.
- Default paper collection off. Provide bounded dry-run commands and an operator runbook for several weeks of forward observation across available regimes. A planned duration is not evidence of sufficient samples. Do not claim weeks of observation were completed during one coding session or start an unattended external run without authorization.

Examples: a restart after a paper entry must not duplicate it; a stop and target touched during an unobserved gap produces an incomplete/ambiguous result rather than an invented sequence.

**4E exit gate:** synthetic prospective streams verify write-before-outcome behavior, separate arms, resume/idempotence and gap handling. Real forward evidence remains collecting/not-started until it actually exists.

## 7. Slice 4F — CLI, authenticated research pages and acceptance report

### 7.1 Reproducible operator commands

Provide documented CLI entry points equivalent to the following intended interface; these commands are requirements to implement, not claims that they already exist:

```text
python -m marketintel.research validate-data --manifest <manifest.json>
python -m marketintel.research replay --manifest <manifest.json> --config <experiment.json>
python -m marketintel.research evaluate --experiment-id <id>
python -m marketintel.research report --experiment-id <id> --output <directory>
python -m marketintel.paper_worker --config <paper-experiment.json>
```

Return machine-readable results and useful exit codes. Add cancellation/checkpoint support for long runs, bounded memory/chunked reads and progress reporting. Paths must work on Windows with `pathlib`; no Linux-only command assumptions. Keep datasets and generated reports out of public source control unless they are explicitly small hypothetical fixtures.

### 7.2 Research UI and exports

Add an authenticated research view with experiment identity/status, dataset coverage, six-engine filters, four-arm comparison, target outcomes, costs, uncertainty and paper ledger. Include empty/loading/error states. Keep current operational signals distinct from historical/fixture results.

Useful displays: outcome counts/coverage, comparison tables, chronological test windows, net-R distributions and a paper equity curve only when a valid portfolio model exists. Every chart should identify data mode, sample size, date range, cost policy and model/rule version. Show `INSUFFICIENT_DATA`, `UNAVAILABLE`, `EXPLORATORY` and `NOT_STARTED` honestly; zero rows is not a 0% or 100% hit rate.

Export a manifest/config copy, opportunity/outcome tables, summary JSON and a readable HTML/Markdown report with checksums and source references. Sanitize CSV text cells that could be interpreted as spreadsheet formulas. Exclude secrets, account identifiers, unnecessary licensed raw metrics and provider-private payloads from exports.

Examples: a fixture experiment carries a hypothetical badge on every results page/export; a BTC-only dataset shows Gold unavailable instead of filling Gold cards with sample statistics.

### 7.3 Release decision

Define a machine-readable gate result such as `SOFTWARE_VERIFIED`, `INSUFFICIENT_EVIDENCE`, `EXPERIMENTAL_ONLY`, or `ELIGIBLE_FOR_FURTHER_PAPER_RESEARCH`. Predeclare minimum coverage, elapsed dates, sample/uncertainty requirements, acceptable data gaps, latency/cost limits and adverse-cost checks. Document the rationale; no universal sample count guarantees a valid edge.

Keep software completion separate from empirical validation. All fixture tests may pass while the correct empirical result remains INSUFFICIENT_EVIDENCE. Do not introduce an automated transition to real trading or label any result production-approved.

## 8. Verification matrix and delivery

Add meaningful deterministic tests for:

| Area | Required contrasting cases |
|---|---|
| Startup / reconciliation | Blank template starts safely; missing rates block calls; nonaligned polling on complete data passes; genuine partial coverage fails |
| Request / revisions | Both actual requests include the digest; request-only responder works; unchanged observations preserve proposal; changed evidence queues correct replacement |
| Budgets / model identity | Oversized input makes zero calls; actual overspend blocks further admission; queued/current model mismatch fails/requeues; failed finish status cannot approve |
| Risk races | Stop insert before token read and older-timestamp insert after read both block stale commit; consistent healthy snapshot can confirm |
| Recovery / delivery | Crash after saved model results resumes finalization; dispatch-unknown is not blindly resent; destination drift blocks; stale market suppresses confirmation |
| Structure / auth | Bull-to-bear continuation and reversal labels; mirrored sequence; first-break identity preserved; non-ASCII credentials do not cause HTTP 500 |
| Replay | Close+1-second availability parity for Gold/BTC; future/corrected observations excluded until available; checkpoint restart deterministic; no production side effects |
| Labels | Wrong symbol, partial entry/expiry, missing intervals, ambiguous stop/target, gap fills, stale pre-entry setup, valid bullish/bearish paths |
| Costs / comparisons | Contract/tick arithmetic hand-checks; adverse costs reduce results; exact cohort counts; per-arm latency and API-cost attribution; no selection-denominator loss |
| Temporal validation | Shared opportunity/arm/revision folds; overlap purge across 30/60/240-minute and delayed no-entry label intervals; timestamp gaps; training-only fitting; unchanged holdout; repeatable hashes |
| Metrics / UI | Empty/small/ambiguous samples; undefined metrics; dependent samples; paired comparisons; hypothetical labels; authenticated pages and safe exports |
| Paper / Windows | Write-before-outcome; restart and gaps; separate experiment database; native PowerShell commands; destination-server operations explicitly marked if untested |

Do not test paid providers or send messages in CI. Recheck installed SDK contracts and official docs only when integration changes require it. Preserve privacy and existing API/auth controls. Keep dependency changes narrow and reproducible; add a statistical library only when a defined calculation warrants it.

Run and report:

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

Update `README.md`, `DESIGN.md`, `docs/IMPLEMENTATION_PLAN.md`, `docs/API.md`, `docs/WINDOWS_DEPLOYMENT.md`, `.env.example`, release notes/version where appropriate, and ADRs for replay clocks, labels/costs, experiment isolation and paper state. Keep the source-storage description accurate: Phase 3 journals normalized REST candle observations; older documentation may still say it does not. Do not call normalized observations a full raw HTTP archive unless those bytes are actually stored.

Create `docs/audits/phase-4-verification.md` recording:

1. Starting/final commits, instruction revision, baseline and final checks.
2. Each independent-review finding fixed/remaining with regression evidence; distinguish reproduced defects from source-evidenced follow-ups.
3. Two hand-checkable hypothetical end-to-end examples, one Gold and one BTC, with timestamps, selected target, fill/cost assumptions and outcomes.
4. Dataset provenance/coverage and experiment artifacts actually created. If no adequate real dataset exists, state that and report software/fixture verification only.
5. Four-arm results only where matching genuine assessments/data exist; explicit unavailable arms, latency and cost basis, holdout dates and tried variants.
6. Actual paid-call/message counts and Windows checks executed. Zero calls/messages is expected for this task. Do not invent a live model or deployment success.
7. Paper observation start/end and sample count actually collected. Infrastructure completion does not complete weeks of forward research.
8. Remaining data licenses, provider entitlements, operational soak, uncertainty and empirical release gates.

Use reviewable commits for 4A–4F. A separate corrective PR is acceptable if it makes review safer; document dependencies and continue the authorized implementation. Push feature branch(es), open PR(s), and provide a substantive handoff. Do not auto-merge, deploy, weaken tests, or create an order path.

## 9. Methodology references

These support the research cautions, not claims about this application's performance. Reviewed on 2026-11-21:

- [scikit-learn TimeSeriesSplit](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html): chronological splitting and the meaning of its sample-count gap; irregular events still require explicit interval logic.
- [Bailey et al., The Probability of Backtest Overfitting](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf): repeated strategy selection can overfit historical results; preserve trial history and untouched evaluation.
- [Kong et al., Evaluating LLMs in Finance Requires Explicit Bias Consideration](https://proceedings.mlr.press/v306/kong26i.html): financial LLM evaluation requires explicit bias and cost controls; retrospective outputs are not automatically valid deployment evidence.

**Begin with the baseline and failing 4A regressions. Deliver reproducible evaluation, a durable paper ledger and explicit evidence status.**
