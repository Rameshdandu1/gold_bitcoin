# CODEX_START_HERE.md — First instructions and master execution brief

> Repository: https://github.com/Rameshdandu1/gold_bitcoin  
> Project: Dual AI Market Intelligence (Delta Exchange India + CoinGlass + GPT + Claude)  
> Platform: Native Windows Server 2022/2025, PowerShell 7, Python 3.12+, React/TypeScript.  
> Status: Research-only application; Phase 6 contract corrections pending, **not live-trading ready**.

## COPY/PASTE THIS AS THE FIRST MESSAGE IN CODEX

Work in https://github.com/Rameshdandu1/gold_bitcoin. Inspect the current repository and preserve
unrelated changes. Read `AGENTS.md`, `DESIGN.md`, `README.md`, `docs/IMPLEMENTATION_PLAN.md`, then
`prompts/CODEX_TASK.md` and the current review/task documents.

The current task is **`prompts/CODEX_PHASE_6_CONTRACT_CORRECTIONS.md`**, with evidence in
`docs/audits/phase-6-workflow-acceptance-independent-review.md`. Reviewed baseline:
`e9f419f5ef576ec957f9d59107ab3f7f06815b23`, merged PR #15, 260 passing Python tests. Fetch current
main and compare newer changes before treating any finding as open. If these documents have not
merged, fetch `docs/phase-6-acceptance-review` and read the exact files from that branch.

Create `fix/phase-6-contract-corrections` (or a suitable unused suffix), reproduce the six listed
failures with meaningful tests, and implement the finite packages. Preserve the working original
later-book, stop/recovery, quote-window and checkpoint controls. Update evidence/status documentation
and open a reviewable PR; do not auto-merge or deploy.

Prepare the existing next stage from `prompts/CODEX_OPERATIONAL_VALIDATION.md` offline. Keep live
ingestion, AI, alerts and real paper collection disabled by default; trading remains refused. No
new strategies, data vendors, options, order paths or notification channels belong to this task.
Do not restart the delivered Phase 1 work described in the historical roadmap below.

Report actual code changes, commands/results, exact SHAs, remaining unverified integrations and the
next operator prerequisite. Missing server access or paid credentials does not block the offline
corrective PR and operational preparation. Never fabricate external success or ask for secrets in chat.

---

## Historical product roadmap reference

These original requirements describe the longer-term product. The current implementation plan and
task above govern immediate scope; roadmap items are not proof of an implemented integration.

### A. Assets and horizons

Develop **six independent research engines**:

| Engine | Underlying market | Evaluation clocks | Prediction horizon | Initial target approach |
|---|---|---|---|---|
| GOLD_FAST | Delta India active tokenized-gold contract, if listed | 1m + 3m; 5m context | 15–30m | USD +10/+20/+30 per underlying token |
| GOLD_HOURLY | Same discovered Gold instrument | 5m; 15m + 1h context | 60m | USD +10/+20/+30 |
| GOLD_SESSION | Same discovered Gold instrument | 15m; 1h + 4h context | 120–240m | USD +10/+20/+30 |
| BTC_FAST | Delta India discovered BTC market | 1m + 3m; 5m context | 15–30m | Percentage/ATR normalized |
| BTC_HOURLY | Same discovered BTC market | 5m; 15m + 1h context | 60m | Percentage/ATR normalized |
| BTC_SESSION | Same discovered BTC market | 15m; 1h + 4h context | 120–240m | Percentage/ATR normalized |

Do not assume `XAUTUSD`, `PAXGUSD` or a specific option contract is currently listed. Discover exchange products and verify active status, contract size, price tick, quote asset and denomination. Do **not** silently equate tokenized Gold with global spot XAU/USD. BTC must not reuse fixed $10–$30 Gold targets. Long and short candidates are both supported. When a source or instrument is unavailable, show `UNAVAILABLE` or `WAIT`, not artificial live data.

### B. Data ingestion and data quality — highest priority

Build adapters with explicit, versioned Pydantic contracts and fixture tests for:

- Delta public REST product discovery, historical closed candles, REST snapshots, ticker/index/mark data where supported.
- Delta public WebSocket trade and order-book channels; only documented channel names and actual payload field types.
- Delta book snapshot + incremental update assembly with sequence continuity/checksum when provided. A gap, impossible state, stale update or checksum mismatch marks the book **invalid until resynchronized**.
- Rolling 500 trades and rolling 5,000 **executed trades** per asset, with timestamps, transaction counts, total buy/sell **contract quantity**, normalized notional only if contract specs permit, and window elapsed duration.
- Buyer-role handling per verified Delta message schema: buyer taker (`r=t`) implies aggressor buy; buyer maker (`r=m`) implies aggressor sell; missing/unknown markers must remain unclassified.
- Resilient reconnection with jitter, bounded memory, backpressure, subscriptions rebuilt after reconnect, heartbeats, rate limiting and idempotent persistence.
- Event time vs receive/ingest time stored separately in UTC with timezone-aware objects; only finalized candles can trigger a signal.
- Durable append-only raw event persistence for deterministic replay; backups and retention rules; never depend solely on bounded in-memory WS buffers.
- Do not treat exchange trade volume as market-wide Gold/BTC volume or detect named traders/whales from anonymous trades.

**Required negative tests:** malformed data, delisted Gold pair, wrong contract size, duplicate/out-of-order trade, dropped order-book update, checksum failure, reconnect, stale snapshot, invalid candle clock, missing bid/ask, rate limit, partial service outage.

### C. CoinGlass subscription integration

Integrate CoinGlass as a separate, entitlement-aware, read-only connector. Do not guess plan features. Confirm actual subscription permitted endpoints and supported coins/exchanges before feature activation; store entitlement and data provenance per dataset.

- BTC: eligible OI, funding, CVD, cross-exchange liquidation data, liquidation heatmap and order-book heatmap **only when entitled and supported**.
- Gold: only use CoinGlass data if the specific token/market is supported and verified. Otherwise rely on Delta and optional external XAU/USD/macro sources.
- CoinGlass liquidation maps are **estimates of potential liquidation concentrations**, not confirmed executable orders, guarantees of price movement, or Delta India-specific liquidity.
- Implement bounded rate limits, cache TTL, explicit failures, pagination where required, field mapping, retry policies, timestamp freshness and API quota/usage monitoring.
- Never synthesize missing heatmap levels or market-wide metrics.

### D. Deterministic quantitative engines

Implement a shared feature library plus independent horizon policies for each asset. Candidate engines—not the LLMs—compute:

1. Closed-candle ATR, volatility regime, session range, VWAP and relative volume with exchange-appropriate units.
2. HH/HL/LH/LL, swing points, BOS/CHOCH, range breakouts, retests, liquidity sweeps, failed breakouts, session highs/lows.
3. Trade aggressor delta, cumulative volume delta, rolling 500/5,000 trade imbalance, normalized big-trade participation, book imbalance, absorption evidence with limitations.
4. Opposing structure/liquidity barriers, volatility-feasibility filters and target/stop selection.
5. Candidate ID, immutable snapshot ID/hash, schema/rule versions, source-quality report, evidence, entry range, invalidation, target tiers, generation time and expiry.
6. Candidate states `UNAVAILABLE`, `WAIT`, `WATCH`, `CANDIDATE`, `REJECTED`, `CONFIRMED`, `INVALIDATED`, `EXPIRED`, with legal transitions and idempotent event IDs.

No LLM-generated stops, targets, market data, or made-up probability percentages. The initial basic breakout detector remains `INCOMPLETE` until required order flow, context and risk quality are validated.

### E. Independent GPT + Claude analysis

Once deterministic candidates and verified snapshots are reliable, call both models **independently and concurrently**, each using the same immutable, canonical input:

- Include snapshot ID, asset, venue, instrument, target horizon, timestamps, price reference, numerical features, candidate entry/stop/targets, source health, macro context if available.
- Use strict JSON/Pydantic response contracts: `snapshot_id`, `direction`, `decision`, `supported_target_indices`, `reason`, `counter_evidence`, `data_warnings`, `model_id`, `response_timestamp`. Never ask for hidden reasoning or chain of thought.
- Initial GPT response must not be shown to Claude and vice versa; there is no negotiation to manufacture agreement.
- Enforce allowed enums, matching snapshot, direction consistency, age limits, selected target intersection, bounded tokens, per-provider timeout/retry/cost budgets and durable audit trail.
- One provider timeout, malformed response, stale snapshot, API refusal, contradictory target or missing evidence = `WAIT` / `REJECTED`; never silently substitute a single-model approval.
- Model agreement does **not** represent an empirical win probability. Count historical outcomes by model independently and together.

### F. Deterministic consensus and risk

Only issue a `CONFIRMED` research alert when all are true:

- A valid quant candidate exists for the intended asset and horizon, from fresh, valid feeds.
- GPT and Claude independently approve the **same snapshot** and direction with at least one overlapping target.
- Market price still lies within a configured non-stale entry range; candidate has not expired, been invalidated or duplicated.
- Entry/stop/target geometry is valid; spread, slippage, expected costs, volatility feasibility and minimum reward/risk pass conservative, documented thresholds.
- No blocked economic-event window, critical service outage, feed integrity issue, missing entitlement or blocked symbol state.
- Risk policy controls the final decision. It must be possible to inspect why any candidate was rejected.

There must be **no exchange order endpoints** or trading permissions in this MVP. Alerts never claim actual profit or suggest that a CALL/PUT option is profitable without instrument-premium analysis.

### G. Outcome research and backtesting

Build deterministic event-time replay and walk-forward testing with separate scores for 15–30m, 60m and 120–240m, for each asset.

- Label target-before-stop within horizon; handle ambiguous same-bar stop/target conservatively or mark uncertain.
- Include spreads, fees, slippage, delays, symbol changes, market sessions and Gold-token basis.
- Compare rules-only vs GPT-only vs Claude-only vs dual consensus **on the same dataset**, with out-of-sample cohorts and statistical uncertainty.
- Report sample size, alert frequency, risk/reward realized, net expectancy, hit rate and calibration **only from actual observed outcomes**.
- No data leakage or use of future candles; no retrospective tailoring of signals.

### H. Dashboard and alerts

Build a usable React/TypeScript UI with:

- Six market/horizon status cards, actual live vs demo labels, source timestamp and health.
- Asset chart with closed candles, candidate entry/invalidation/target levels and relevant structure.
- Order-flow view (recent trades, 500/5,000 delta, book quality) and CoinGlass layers only where legitimately available.
- Separate GPT and Claude decisions and counterarguments; consensus reason; WAIT/REJECT explanation.
- Signal lifecycle, historical outcomes and system/API usage with budget controls.
- Read-only options analysis as a later milestone: bid/ask, Greeks, expiries, fees and premium economics; don't equate underlying success with options profitability.
- Telegram alerts with deduplication and expiration only after actual consensus gates, never from sample/demo events.

Add error/loading/empty states and authenticated access before exposing the UI beyond localhost.

### I. Windows Server deployment and operational rules

Windows Server 2022/2025 is the primary supported platform. Do **not** assume Docker Desktop or native Windows Redis works on Windows Server. Begin with native Python + FastAPI + database + PowerShell, using Windows Service/Task Scheduler as appropriate; document any optional Linux VM separately.

- Python 3.12+, Node.js LTS for frontend, PowerShell 7, Windows-compatible process supervision.
- Initially bind API to `127.0.0.1`; configure authenticated HTTPS reverse proxy and least-privilege Windows service identities before internet exposure.
- Retention, daily off-host backups, recovery steps, watchdogs, log redaction, health/readiness routes, secrets rotation and deployment smoke tests.
- No GPU requirement for hosted GPT/Claude APIs.
- Never print or commit credentials. Use `.env.example` placeholders and secrets via environment/secret vault; `.env`, private files and `data/` must stay ignored.
- The repository may be public. Treat every commit as publicly readable. Do not upload exchange account records or paid/licensed data snapshots without permission.

### J. Engineering and coding standards

Follow `AGENTS.md` plus:

- Python: typed functions, Pydantic v2 at boundaries, UTC-aware datetime, `Decimal` at monetary boundaries, small services, clear dependencies, no unlogged catch-all errors, asyncio cancellation/timeouts done correctly.
- TypeScript: strict mode, typed API contracts, resilient React components, no secrets client-side; frontend never generates or upgrades trading signals.
- Version all feed schemas and stored events; make migrations explicit and reversible when feasible.
- Prefer clear deterministic logic to model speculation. Keep adapters pure; avoid heavy changes to unrelated features.
- Never commit while unit tests knowingly fail without clearly documenting that failure.
- Each new feature needs positive tests, negative tests, integration fixtures, operational logs and updated docs.
- Do not claim external API tests passed when they were not run. Verify actual provider API documentation and plan permissions.
- Track architecture changes with short ADRs under `docs/adr/`.
- For each milestone, update `README.md`, `DESIGN.md`, `docs/IMPLEMENTATION_PLAN.md`, `.env.example`, tests and GitHub CI when relevant.

## DEVELOPMENT ORDER AND HARD GATES

### Milestone M1 — market data reliability (start NOW)
Implement product discovery, schemas, trades/order-book ingest, sequence recovery, raw persistence, closed candles, feed quality and deterministic replay. **No paid model calls required.** Gate: corrupt/stale/unknown feed never produces a candidate eligible for AI.

### Milestone M2 — quantitative engine completeness
Implement exact six engine rules, rolling volume/order-flow measures, session/structure, volatility feasibility, candidates and outcome replay. Gate: deterministic replay and no look-ahead tests pass, all candidate states auditable.

### Milestone M3 — double-model confirmation
Independent OpenAI + Anthropic structured reviews, same snapshot, fail-closed consensus, cost budget, risk gate. Gate: positive and failure scenario suites pass; no single-model confirmation possible.

### Milestone M4 — UI + alerts + Windows operations
Functional six-engine dashboard, source freshness, alerts, secret-safe services, auth, backup/recovery and Windows setup docs. Gate: frontend typecheck/build, critical E2E checks and deployment smoke verification.

### Milestone M5 — data-driven performance
Walk-forward replay, paper-trading reports, P&L costs, LLM-vs-rules comparison and calibration. Gate: objective sample size/outcome reports; zero claims of guaranteed performance.

### Beyond MVP — options and execution
Read-only options evaluation may be added **after** the core signal research works. Automated orders require separate authorization and independent security/risk design; do not implement them on this task.

## Historical first PR — delivered foundation, not the current task

Name: **feat: establish reliable Delta public market-data foundation**

Deliver in one or more small commits:
1. Baseline audit document `docs/audits/initial-codebase-audit.md` listing what is real, placeholder, incomplete and blocked.
2. Delta REST/WebSocket schema fixtures, instrument metadata validation, unavailable Gold contract behavior.
3. Event-time/ingest-time UTC normalization, closed-candle guard and trade buyer-role contract tests.
4. Raw append-only event persistence and replay covering a minimal end-to-end slice.
5. Order-book sequence/checksum failure handling or an explicit fail-closed downgrade if the documented feed capability isn't supported by the current adapter.
6. Tests for reconnect, stale feeds, duplicate event IDs, missing book sequence, wrong units and no-look-ahead.
7. README/DESIGN/plan + `.env.example` updated for actual verified code.

**Acceptance:** `pytest`, `ruff`, frontend typecheck/build (when relevant) pass; no fabricated feed snapshots; deterministic replay reproduces the same candles; invalid/stale book blocks affected features; Gold contract absence never creates fake Gold signals; all findings and limitations are documented. Only then proceed to Phase 2.

## FINAL RESPONSE FORMAT FOR EVERY CODEX SESSION

1. **Summary:** what was actually implemented.
2. **Changed files:** exact paths and why.
3. **Validation:** commands, passing/failing/skipped tests; clearly separate mocks from live provider checks.
4. **Risks and gaps:** unverified APIs, data quality, billing, operational concerns.
5. **Git:** branch name, commit SHA, PR URL (only if actually created).
6. **Next step:** one concrete slice from the implementation plan.

**Start with the current contract-correction task above. Finish authorized offline work before
reporting the precise prerequisites for subsequent external validation. Do not expose secrets.**
