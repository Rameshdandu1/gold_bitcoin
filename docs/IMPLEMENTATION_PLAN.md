# Implementation backlog (technical work order)

## Phase 0 — repository and safe defaults (starter)
- [x] README, DESIGN, AGENTS, prompts, Windows instructions, secrets hygiene
- [x] Basic data contracts, independent AI consensus, fail-closed defaults
- [x] Delta REST + WS and basic CoinGlass adapter
- [x] Simple six-card dashboard, CI and unit tests
- [x] GitHub repository created and CI run on GitHub (verified through merged PR #8).

## Phase 1 — trustworthy market data (before any live signals)
- [x] Resolve BTC and gold instruments by `/v2/products`, validate active contract state,
  quote/underlying/base units. Add fixtures for India API responses and symbols missing/delisted.
- [x] Persist **raw** trade + order-book snapshots and incremental changes in an append-only,
  logical UTC-day-partitioned schema. Store event time, receive time, publish time, channel,
  exchange and checksum.
- [x] Implement `ob_updates` snapshot, sequence continuity, checksum verification, resync and
  deterministic replay. Test dropped packet, duplicate, out-of-order, reconnect, crossed book,
  zero-size deletion and stale snapshot.
- [x] Reconcile REST 1m candles with streamed trade aggregation, identify finalized candles
  reliably across server clock/time sync and outages. The worker persists `WAIT`/`VALID`/`INVALID`
  reconciliation status; a longer live outage/clock-drift soak remains an operational acceptance
  item before M1 is declared production-ready.
- [x] Implement contract-size normalization: Delta contracts != USD, buyer role `r=t` -> aggressive
  buy, `r=m` -> aggressive sell; tests use documentation-derived fixtures.
- [x] Archive source API status/errors, bounded REST retry/cooldown and WebSocket backoff; no busy
  polling. Production rate/retention tuning remains operational work.

## Phase 2 — six purpose-built engines
- [x] Deterministic 1m/3m sweep/reclaim and follow-through for FAST, 5m/15m
  breakout+retest for HOURLY, higher-TF BOS/CHOCH and session levels for SESSION.
- [x] Features: ATR, UTC-day candle-volume VWAP proxy, relative volume, CVD rolling exact 500/5,000 trades,
  duration-window flow, quote-notional book imbalance, absorption proxy,
  stop-run/false-breakout rules and near-term opposing levels.
- [x] Add a fail-closed Gold reference-provider interface and optional BTC funding/OI CoinGlass
  context with supported coin/pair and declared-plan entitlement gates. A licensed live XAU/USD,
  DXY, yield and economic-calendar provider is **not configured or verified**, so Gold basis/macro
  fields remain unavailable rather than fabricated.
- [x] Independent per-engine configurable target, stop and invalidation thresholds. Distinguish
  `UNAVAILABLE`, `WAIT`, `WATCH`, `CANDIDATE`, `REJECTED`, `INVALIDATED` and `EXPIRED`; persist
  immutable revisions and append-only lifecycle events.

The existing Phase 2 automated suite exercises all six configurations independently, bullish/bearish inputs,
false breakouts, missing/stale/corrupt data, duplicate suppression, expiry/invalidation and
point-in-time replay with explicit candle availability plus trade/book event and receive clocks. It
does not establish live signal accuracy, profitability or
provider availability. CoinGlass subscription calls and a licensed Gold reference remain external
operator validation items.

**Independent review gate (2026-11-21):** the historical 126-test baseline did not close M2
correctness acceptance. [The review](audits/phase-2-independent-review.md) reproduced R1–R6 and
identified canonical/revision contracts that became the Phase 3 entry gate. Those findings are now
corrected and regression-tested; see [the Phase 3 verification report](audits/phase-3-verification.md).

## Phase 3 — dual-model and hardened service
- [x] Correct R1–R6: full session/previous-day acquisition, first-break structure identity, common
  candle availability, executed-event breach persistence, continuing discovery/reconciliation gates
  and accurate current lifecycle projection.
- [x] Canonical deeply immutable analysis bytes; revision-scoped envelopes, runs, leased jobs,
  provider attempts, decisions, migrations, persistent budgets and restore verification.
- [x] Independent concurrent OpenAI/Anthropic structured adapters with actual response metadata,
  bounded deadlines/retries and typed fail-closed provider outcomes. Missing verified pricing
  prevents paid dispatch.
- [x] Fresh post-review revision, lifecycle, time, trade, stop/target, source, book, spread, drift,
  fee/slippage and net reward/risk gates; decision and Slack intent commit atomically.
- [x] Authenticated bounded API/UI; Slack outbox worker, terminal event identities, durable delivery
  states; native Windows startup/check/backup instructions. Installation, live delivery and provider
  account/model access remain external verification items.

Implementation order and acceptance details are in [CODEX_PHASE_3.md](../prompts/CODEX_PHASE_3.md):

- [x] **3A:** fix session coverage, consumed structure events, candle availability, live price
  invalidation, discovery admission policy and lifecycle presentation; journal REST observations
  and define required reconciliation health.
- [x] **3B:** deeply immutable canonical evidence and exact bytes/digest; revision-scoped durable
  review jobs, attempts, decisions, budgets and migrations.
- [x] **3C:** independent concurrent GPT/Claude structured review, actual provider metadata,
  bounded deadlines/retries, strict validation, material-change idempotence and spend accounting.
- [x] **3D:** deterministic consensus plus current-price/source/lifecycle recheck; atomic decision
  and outbox commit against the active revision.
- [x] **3E:** accurate authenticated API/dashboard, one complete notification channel adapter,
  durable delivery state and Windows operation/recovery instructions.

AI and outbound alerts remain disabled by default. Fixture completion, paid-provider smoke tests,
Windows deployment and strategy-performance validation are separate evidence categories.

**Independent review history:** the original Phase 3 reproductions now have verified corrections.
The later [Phase 4 review](audits/phase-4-independent-review.md) distinguishes those improvements
from remaining dispatch, request-configuration and recovery defects. Implementation checkboxes
above describe delivered code, not completed operational or empirical acceptance.

## Phase 4 — historical evaluation and prospective paper research

15. Historical replay driven by factual availability and evaluation cadence, with separate exchange event time, purged chronological validation and no interpolation of future prices.
16. Label target-before-stop from each arm's eligible entry, model spread/slippage/fees, preserve partial-bar and missing-path ambiguity, and report per-session breakdowns.
17. Compare rules-only, rules plus GPT, rules plus Claude and rules plus dual agreement on common opportunities; publish sample size, coverage, net expectancy and statistical uncertainty. Calibration is N/A unless an out-of-sample probability estimator actually exists.
18. Paper-trade at least several weeks across regimes. Define release gate in measured terms; NEVER claim made-up hit rates.

Detailed implementation instructions: [CODEX_PHASE_4.md](../prompts/CODEX_PHASE_4.md).

- [ ] **4A acceptance:** fix environment-template parsing, complete-bucket reconciliation, request digest,
  revision scheduling, consistent risk/commit evidence, real input/spend limits, model/finish-status
  identity, dispatch recovery/destination, current alert eligibility and structure-state logic.
  Test finalization crashes/deadlines and non-ASCII auth input handling.
- [ ] **4B acceptance:** versioned dataset manifest and isolated as-observed replay, driven by factual
  availability/evaluation clocks with separate exchange event time, coverage and checkpoint parity.
- [ ] **4C acceptance:** eligible entry time, instrument/target identity, complete outcome path, conservative
  ambiguity, realistic quote-side fills and versioned contract/fee/slippage/funding assumptions.
- [ ] **4D acceptance:** rules/GPT/Claude/dual filter comparisons on common opportunities, arm-specific latency,
  preserved abstention denominators, shared opportunity folds, time-based label-information
  purging including delayed no-entry outcomes, untouched holdout and dependence-aware uncertainty.
  Retrospective LLM analysis remains explicitly exploratory.
- [ ] **4E acceptance:** durable prospective paper ledger, write-before-outcome decisions, restart/gap handling
  and separately declared hypothetical portfolio policy. Default off; no exchange orders.
- [ ] **4F acceptance:** authenticated research pages, reproducible CLI/exports, coverage/sample/uncertainty
  reporting, honest insufficient-evidence states and native Windows run instructions.

Software/fixture completion does not complete weeks of forward observation or demonstrate an edge.
Unavailable historical trades/books, licensed context and contemporaneous AI outputs stay
unavailable; no synthetic performance may be presented as empirical evidence.

**Independent Phase 4 gate (2026-11-21):** PR #6 delivered corrections and research components, with
206 passing tests. The [independent review](audits/phase-4-independent-review.md) identified the
integrated replay, outcome, paper chronology, dispatch and recovery gaps assigned to Phase 5. The
historical implementation report remains evidence of its executed checks, not closure of those later
findings. Real data, contemporary model assessments and forward observation remain separate.

## Phase 5 — research completion and operational validation

Detailed instructions: [CODEX_PHASE_5.md](../prompts/CODEX_PHASE_5.md).

- [x] **5A:** shared current-risk delivery policy, transaction-fenced dispatch authorization,
  zero-call terminal/configuration preflight and durable expired-result dispositions.
- [x] **5B:** canonical dataset/config identities, prefix-bound bounded replay, immutable journal and
  shared production-detector workflow for Gold/BTC across all six engines.
- [x] **5C:** public quote-path evaluation with readiness/latency once, pre-entry invalidation,
  expiry/path uncertainty and verified quote-side contract/cost calculations.
- [x] **5D:** unique opportunity/revision selection, past-only purged folds, frozen holdout policy,
  known-abstention operational comparisons and explicit final-holdout access.
- [x] **5E:** source-bound prospective paper event loop with write-before-entry/outcome chronology,
  legal arm states, restart idempotence, truncation and generation checks.
- [x] **5F:** authenticated experiment/engine/opportunity/paper views, authoritative checksummed
  exports, Gold/BTC public fixture workflows and native Windows instructions.

These checkboxes record Phase 5 implementation delivery and its original synthetic checks. They
do not close independent acceptance: the
[Phase 5 review](audits/phase-5-independent-review.md) reproduced P5-01–P5-07 at
`dfbb59ea91bfc034f4ab4ffa76c0dbda094f5a31`. Phase 6 below records the implemented dispositions
and preserves the remaining shared-policy, full-resume and operational gates without rewriting the
historical Phase 5 evidence.

Adequate licensed market history, genuine contemporary provider completions, extended prospective
observation, live integration soaks and destination-host recovery remain separate gates.

## Phase 6 — evidence integrity and complete workflow acceptance

Detailed instructions: [CODEX_PHASE_6.md](../prompts/CODEX_PHASE_6.md).

- [x] **6A:** advancing-clock alert authorization, cutoff-aligned evidence token, persisted
  freshness deadline and typed zero-call quarantine for incomplete legacy request policy.
- [x] **6B:** provider/quote availability and provenance retention, compatible evidence-mode
  validation, contiguous pre-entry/post-entry quote and OHLC coverage, versioned Phase 6 outcomes.
- [x] **6C reviewed counterexamples:** cadence evaluation during silence, availability-time provider
  decisions, source-state gates and a public connected paper command deriving later outcomes.
- [x] **6D:** atomic paper-event/cursor commits, consumed-prefix identity, duplicate-first recovery,
  replacement/truncation/conflict and interrupted-transaction regressions.
- [x] **6E:** central holdout projection for ordinary API/detail/summary/export inputs and durable
  explicit final opening with `HOLDOUT_PROTECTED`/`HOLDOUT_OPENED` operator state.
- [x] **6F offline verification:** public synthetic Gold/BTC research and connected paper commands,
  backend/frontend checks, evidence-mode displays and native Windows instructions.
- [x] **Phase 6 offline closeout:** shared revision/lifecycle/source/current-risk application policy,
  durable complete derived-workflow and connected-paper resume, scoped holdout-safe paper provenance,
  explicit unavailable/expired terminal arms and measured 500-event public-command batching.

The offline software gates are closed by the Phase 6 closeout regression/public-command bundle.
Destination Windows recovery, licensed live data, genuine contemporaneous provider outputs and
elapsed forward observation remain operational or empirical gates, not unfinished software slices.

## Phase 7 — derivatives/optional execution (separate approval; deferred)
19. Read-only Delta options chain/Greeks/contract expiry/bid ask; verify option premium expectancy not merely underlying direction.
20. Only after independent audit, create a separate execution system with separate keys and authorization, kill switch, position limits, approvals, idempotence, API order reconciliation and sandbox validations. Execution is not in this repo's current scope.

## Milestone acceptance criteria
- M1: connected market status is accurate; missing symbols/stream gaps show unavailable; replayable closed candles.
- M2: six engines emit deterministic, non-overlapping events with reasons/invalidation; no fake forecasts.
- M3: implemented with a passing fixture baseline; the reviewed dispatch/upgrade findings are
  corrected in 6A while complete shared-policy parity remains open. Live provider/model entitlement,
  paid-call behavior, Slack delivery,
  Windows installation and extended market soak remain separate operator acceptance gates.
- M4: measurable net-of-cost research outcomes on unseen data; dashboard reflects actual results, never estimated success percentages.
- M5 software acceptance remains open until the six-engine workflow, outcome evaluator, partitions,
  paper chronology/recovery and operator surfaces satisfy Phase 6 on immutable hypothetical
  evidence. M5 empirical readiness additionally requires real licensed and prospective evidence.
