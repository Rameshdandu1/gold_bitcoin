# Implementation backlog (technical work order)

## Phase 0 — repository and safe defaults (starter)
- [x] README, DESIGN, AGENTS, prompts, Windows instructions, secrets hygiene
- [x] Basic data contracts, independent AI consensus, fail-closed defaults
- [x] Delta REST + WS and basic CoinGlass adapter
- [x] Simple six-card dashboard, CI and unit tests
- [ ] GitHub repository created and CI run on GitHub (external operator action)

## Phase 1 — trustworthy market data (before any live signals)
1. Resolve BTC and gold instruments by `/v2/products`, validate active contract state, quote/underlying/base units. Add fixtures for India API responses and symbols missing/delisted.
2. Persist **raw** trade + order-book snapshots and incremental changes in an append-only, partitioned schema. Store event_time, receive_time, publish_time, channel, exchange and checksum.
3. Implement `ob_updates` snapshot, sequence continuity, checksum verification, resync and proper replay. Test dropped packet, duplicate, out-of-order, reconnect, crossed book, zero size deletion and stale snapshot.
4. Reconcile REST 1m candles with streamed trade aggregation, identify finalized candles reliably across server clock/time sync and outages.
5. Implement contract-size normalization: delta contracts != USD, buyer_role r=t -> aggressive buy, r=m -> aggressive sell; tests against documentation fixture.
6. Archive source API status/errors, backoff and cooldown; rate limits as configured, no busy polling.

## Phase 2 — six purpose-built engines
7. Deterministic 1m/3m sweep/reclaim and follow-through for FAST, 5m/15m breakout+retest for HOURLY, higher-TF BOS/CHOCH and session levels for SESSION.
8. Features: ATR, VWAP, relative volume, CVD rolling 500/5000 trades, trade-duration-normalized imbalance, absorption, stop-run/false breakout rules, near-term opposing levels.
9. Add macro/reference gold connector; XAUT/XAU basis and data quality filter. BTC funding/OI and CoinGlass exchange support/entitlements mapping.
10. Independent per-engine configurable target and invalidation thresholds. Distinguish `WAIT`, `WATCH`, `CANDIDATE`, `REJECT` and `EXPIRED`.

## Phase 3 — dual-model and hardened service
11. Guarded GPT and Claude structured responses with timeout, token ceilings, cached idempotence, retry caps, budget monitor, response/version audit.
12. Independent evaluations on immutable snapshots; no chain-of-thought request; compare explicit target-index overlap, invalidation agreement and hard risk checks. Emergency WAIT if either provider fails.
13. Auth, TLS reverse proxy, key rotation, Windows Services/Task Scheduler for restart, OS firewall, ingestion tracing and error alerts.
14. Slack/Telegram notifications with exact trigger/target/stop/source timestamp, dedup and expiry; never transmit secrets.

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
