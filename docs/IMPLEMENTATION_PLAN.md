# Implementation backlog (technical work order)

## Phase 0 — repository and safe defaults (starter)
- [x] README, DESIGN, AGENTS, prompts, Windows instructions, secrets hygiene
- [x] Basic data contracts, independent AI consensus, fail-closed defaults
- [x] Delta REST + WS and basic CoinGlass adapter
- [x] Simple six-card dashboard, CI and unit tests
- [ ] GitHub repository created and CI run on GitHub (external operator action)

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

**Independent review gate (2026-11-21):** the passing 126-test baseline does not close M2
correctness acceptance. [The review](audits/phase-2-independent-review.md) reproduced R1–R6 and
identified canonical/revision contracts that must be hardened before AI promotion. Phase 3A below
owns that corrective work; completed implementation checkboxes above do not imply those findings
are fixed.

## Phase 3 — dual-model and hardened service

11. Guarded GPT and Claude structured responses with timeout, token ceilings, cached idempotence, retry caps, budget monitor, response/version audit.
12. Independent evaluations on immutable snapshots; no chain-of-thought request; compare explicit target-index overlap, invalidation agreement and hard risk checks. Emergency WAIT if either provider fails.
13. Auth, TLS reverse proxy, key rotation, Windows Services/Task Scheduler for restart, OS firewall, ingestion tracing and error alerts.
14. Slack/Telegram notifications with exact trigger/target/stop/source timestamp, dedup and expiry; never transmit secrets.

Implementation order and acceptance details are in [CODEX_PHASE_3.md](../prompts/CODEX_PHASE_3.md):

- [ ] **3A:** fix session coverage, consumed structure events, candle availability, live price
  invalidation, discovery admission policy and lifecycle presentation; journal REST observations
  and define required reconciliation health.
- [ ] **3B:** deeply immutable canonical evidence and exact bytes/digest; revision-scoped durable
  review jobs, attempts, decisions, budgets and migrations.
- [ ] **3C:** independent concurrent GPT/Claude structured review, actual provider metadata,
  bounded deadlines/retries, strict validation, material-change idempotence and spend accounting.
- [ ] **3D:** deterministic consensus plus current-price/source/lifecycle recheck; atomic decision
  and outbox commit against the active revision.
- [ ] **3E:** accurate authenticated API/dashboard, one complete notification channel adapter,
  durable delivery state and Windows operation/recovery instructions.

AI and outbound alerts remain disabled by default. Fixture completion, paid-provider smoke tests,
Windows deployment and strategy-performance validation are separate evidence categories.

## Phase 4 — historical evaluation
15. Historical market replay (event-time ordered), embargo/purged walk-forward test, no interpolation of future prices.
16. Label target-before-stop, model immediate spread/slippage/fees, ambiguous same-bar stop-target as loss/uncertain, per-session breakdown.
17. Compare rules-only vs GPT only vs Claude only vs agreement and rejection losses; publish sample size, calibration error, net expectancy and confidence intervals (statistical, not LLM).
18. Paper-trade at least several weeks across regimes. Define release gate in measured terms; NEVER claim made-up hit rates.

## Phase 5 — derivatives/optional execution (separate approval)
19. Read-only Delta options chain/Greeks/contract expiry/bid ask; verify option premium expectancy not merely underlying direction.
20. Only after independent audit, create a separate execution system with separate keys and authorization, kill switch, position limits, approvals, idempotence, API order reconciliation and sandbox validations. Execution is not in this repo's initial scope.

## Milestone acceptance criteria
- M1: connected market status is accurate; missing symbols/stream gaps show unavailable; replayable closed candles.
- M2: six engines emit deterministic, non-overlapping events with reasons/invalidation; no fake forecasts.
- M3: both AI providers independently return validated schema and failures fail closed.
- M4: measurable net-of-cost research outcomes on unseen data; dashboard reflects actual results, never estimated success percentages.
