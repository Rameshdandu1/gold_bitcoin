# DESIGN.md — Dual AI Market Intelligence Architecture

**Status**: Design v0.5 / research-completion MVP. **Scope**: deterministic analysis plus opt-in dual-AI
review and Slack alerts; all external paths are disabled by default and order execution is absent. **Deployment**: native Windows Server
2022/2025 initially; Python worker/API run as Windows services after validation. Linux VM/docker
optional, not required for this starter.

## Phase 5 evidence architecture

The public `run-workflow` command validates the canonical dataset manifest, externally sorts input
by factual availability, and sends normalized trades, candles, book generations, instruments and
recorded provider completions through `SharedResearchEngine`. That service retains at most 5,000
trades per symbol and 2,000 candles per symbol/resolution and invokes the production
`detect_signal` function for all six engines. It never has a provider, notification, account or
order transport.

Candidates, four-arm decisions and their exact target/configuration identities are immutable
records. Decisions are stored before the evaluator reads the journal-backed future quote path.
Executable outcomes reuse bid/ask, tick, multiplier, fee, slippage, funding and gap policies.
Ordinary evaluation selects one revision per opportunity and excludes label intervals that enter
the frozen holdout. Protected holdout access is a separate recorded command.

Manifest hashes commit to the canonical manifest preimage and ordered file identities. Experiment
hashes commit to dataset, algorithm, engine/feature, target/revision, cost, schedule, partition,
seed and variant policy. Checkpoints bind both hashes and validate the consumed input prefix while
retaining only the most recent 128 diagnostic event IDs. Conflicting writes fail instead of
overwriting scientific history.

The paper ledger binds candidate, revision, arm, target, configuration, source identity/generation,
decision persistence time and eligible-entry time. Prospective entries/outcomes must occur after
the decision write and be factually available before recording. Historical import remains a
distinct evidence mode. The worker advances a source-bound cursor after each idempotent event and
detects replacement or truncation.

## Phase 4 foundation

Historical observations carry exchange time and factual `available_at_utc`; replay orders by
availability time, persistence sequence, event-kind priority and immutable event ID. Dataset
manifests pin file hashes/counts, instruments, source coverage/gaps, code/rule versions, provenance
and data mode. A rolling hash and atomic checkpoint make resume deterministic without revealing
corrections before their recorded arrival.

`research.sqlite3` stores experiment inputs, replay points, common-opportunity arm records and
reports. `paper.sqlite3` stores prospective decisions before outcomes, cursors and gaps. Both reject
the production database path and never use production review/outbox tables.

Every arm enters at its actual decision-ready time. Long entries use ask and exits bid; shorts use
bid and exits ask. Tick rounding/slippage are adverse, fees cover both sides, instrument contract
units are versioned, and required funding fails closed. Outcomes preserve `NO_ENTRY`, target, stop,
time exit, `AMBIGUOUS` and `INCOMPLETE`. Folds keep all opportunity revisions/arms together and
purge overlapping label-information intervals with a time embargo.

**Independent review:** the original Phase 2 counterexamples and the subsequent
[Phase 3 review](docs/audits/phase-3-independent-review.md) findings have regression coverage and
Phase 4 corrections. Architectural requirements remain distinct from empirical acceptance: live
providers, licensed data, prospective duration and deployment are not proven by fixtures. Follow
[CODEX_PHASE_5.md](prompts/CODEX_PHASE_5.md). Passing fixtures are
not evidence of live provider readiness or strategy performance.

## Business purpose
Monitor Delta Exchange India gold-linked instruments (XAUT/PAXG *only if discovered as currently listed*) and BTCUSD; determine credible upcoming moves over three independent horizons: short (15–30m), medium (60m), long (120–240m). Proposed gold gross-underlying targets: $10/$20/$30; BTC targets are asset-relative percentages/ATR selected from calibrated results. Stop risk, commissions and options premiums can make an underlying move untradable.

## System boundaries and sequence

```mermaid
flowchart TD
    D[Delta Public WS + REST] --> N[Normalizer, Time and Symbol Validation]
    C[CoinGlass V4 REST (optional)] --> N
    M[Optional XAU/USD + Macro Feed] --> N
    N --> Q[Durable Raw Event Storage & Quality Monitor]
    Q --> F[Closed-candle Features, Structure, ATR, Volume & Liquidity]
    F --> E[6 Independent Horizon Engines]
    E --> S[Canonical Immutable Snapshot + Candidate]
    S --> G[GPT Analyst]
    S --> A[Claude Analyst]
    G --> V[Schema / Freshness Validation]
    A --> V
    V --> K[Deterministic Consensus + Risk Gate]
    K --> H[Audit Database and Results]
    H --> U[Authenticated Dashboard]
    H --> T[Durable Slack Alert Worker]
```

### Adapters
- `DeltaREST`: `/v2/products` validates live/operational linear instruments, contract value, unit
  currencies and tick size; `/v2/history/candles` supplies historical candles. Requests use bounded
  retries for 429/5xx. REST candles are **not** historical raw trades.
- `DeltaWS`: `wss://public-socket.india.delta.exchange`, documented compact `trades` and
  `ob_updates`. The M1 collector preserves event/receive/publish times, deduplicates trades, stores a
  bounded 5,000-trade working set, and durably journals every accepted event. Incremental books
  require snapshot, contiguous sequence, CRC32, non-crossed sides and freshness; failure forces
  reconnect/resubscribe and keeps the book invalid until a new snapshot.
- `CoinGlass V4`: `https://open-api-v4.coinglass.com`, `CG-API-KEY`. Feature gating by actual subscription and supported exchanges/pairs. Start with supported-coins discovery and OI/funding; liquidation map endpoints are Professional entitlement, not assumed. Cache/rate limit; commercial use requires an eligible license.
- `ReferenceGold`: optional XAU/USD, DXY, yields, economic calendar with provider attribution and time stamp. If missing, report unknown rather than silently treating XAUT as spot gold.

### Core domain models
`MarketEvent`, `Candle`, `Instrument`, `FeatureSnapshot`, `Candidate`, `AnalystAssessment`, `ConsensusDecision`, `Alert`, `Outcome` are versioned. Use UTC timestamp in payload, decimal handling of prices, explicit unit/currency, exchange and source. Snapshot hash is immutable and sent to both AI models.

### Six engines, independent policy
| Engine | Base candles |  Context | Forecast | Trigger family | Raw targets |
|---|---|---|---|---|---|
| GOLD_FAST | 1m | 5m | 30m | Sweep/reclaim, breakout pressure | $10/$20/$30 |
| GOLD_HOURLY | 5m | 15m/1h | 60m | Breakout/retest, structure | $10/$20/$30 |
| GOLD_SESSION | 15m | 1h/4h | 240m | Session range/major BOS | $10/$20/$30 |
| BTC_FAST | 1m | 5m | 30m | Aggression/vol expansion | 0.25/0.5/0.75% initial candidate values |
| BTC_HOURLY | 5m | 15m/1h | 60m | Retest/OI/flow | 0.25/0.5/0.75% |
| BTC_SESSION | 15m | 1h/4h | 240m | Larger structure/macro | 0.25/0.5/0.75% |

Target tiers and ATR projection filters are **provisional heuristics**, not learned success odds.
Phase 2 implements all six engine policies using confirmed pivots and HH/HL/LH/LL, BOS/CHOCH,
sweep/reclaim, breakout/retest, false-breakout rejection, executed-trade flow over exact 500/5,000
windows, validated depth imbalance/absorption, ATR, UTC-day candle-volume VWAP proxy, relative volume and volatility
expansion. Gold $10/$20/$30 and BTC percentage/ATR tiers are emitted only when geometric room and
reward/risk permit them. No result is a learned forecast, probability, AI confirmation or order.

### Trade signal pipeline
1. Produce a candidate only on a newly **closed** candle, after enough contiguous historical bars.
   Stable ID from `asset|symbol|engine|horizon|candle_close|direction|rule_version`.
2. Calculate ATR(14), range/structure levels and volatility budget. Evidence includes source freshness and numerical features. Candidate targets/stop computed by code, never AI.
3. Freeze one canonical analysis envelope as exact bytes plus digest. Persist the candidate revision,
   lifecycle transition, envelope and a bounded leased review job. Phase 2 evidence remains intact.
4. Phase 3 independently and concurrently gives those same bytes to GPT and Claude. Strict parsed
   identities, actual model metadata, persistent budgets and bounded failures feed consensus.
5. After agreement, re-read revision/lifecycle, executed price, target/stop events, discovery,
   reconciliation, book, spread, entry drift, cost and calendar/session policy. Atomically commit the
   decision and revision-scoped outbox intent. `CONFIRMED` is merely an **alert**, NOT an order.
6. Record candidate revisions, state transitions, invalidation and expiry as append-only rows. Never
   overwrite history. Historical replay evaluates at each event-time candle close and requires the
   candle's explicit availability timestamp in addition to event/receive clocks for trades and books.

### Volatility and performance
ATR is a scale, not a directional prediction. Naive `ATR * sqrt(horizon / bar_minutes)` is a loose heuristic, not a forecast. Intraday sessions/news cause regime changes. Need walk-forward and purged time-based holdout, bootstrap CIs by day, fees/slippage, and target-before-stop labelling; ambiguous same-bar high/low = conservative loss or separate ambiguous bucket, not automatic win.

### Storage and messaging roadmap
- **M1 single-host store**: SQLite WAL contains immutable candidate/audit records plus an append-only
  raw public-event journal keyed by UTC-day logical partition. Database triggers block raw event
  updates/deletes. Deterministic replay rebuilds closed trade-derived candles and books. REST
  candles carry their response availability time; Phase 3 also journals normalized REST candle
  observations with request bounds, response availability and a digest. This is not a full raw
  HTTP-response archive. Feature snapshots and candidate/lifecycle evidence are persisted. This is
  durable across process restart but is not yet throughput-qualified as a high-frequency production
  tick database.
- **Production target**: PostgreSQL + TimescaleDB (Windows native PostgreSQL or optional isolated Linux VM), durable raw events and candle tables; queue via PostgreSQL outbox or Redis in a supported Linux VM. Do NOT rely on discontinued native Windows Redis ports. Migrate only after measured feed throughput.
- **Phase 3 single-host path**: additive SQLite migration adds immutable envelopes, review runs,
  fenced job leases, provider attempts, UTC budget ledger, decisions and alert outbox. SQLite backup
  API plus integrity verification is supported; dispatched/receipt-unknown states require operator
  reconciliation rather than blind retry.
- Retention policies: raw order-book updates may grow quickly; sample or compress according to license and analytical requirements. Backups: nightly database + off-host restore test.

### Security
Windows service identity with least privileges; API listens on 127.0.0.1 and all routes except
minimal liveness require constant-time HTTP Basic credentials. Remote access requires a restricted
HTTPS reverse proxy/VPN. CORS is exact; environment secrets are not committed; `TRADING_ENABLED`
cannot be enabled. Exchange data, retrieved reference data and LLM output are untrusted.

### Options follow-up (not implemented in MVP)
Discover active option products, strikes/expiries, full bid/ask, IV/Greeks; independently compute delta exposure, decay, expected value and worst-case spread/slippage. Validate premium economics before ranking CALL/PUT instruments. Distinguish underlying signal from options order.

### Operator-visible dashboard
Six-card grid, market observation and source/worker freshness, exact provider attempts/models,
disagreements and spend, current candidate lifecycle and historical decision. Show `WAIT` by
default. Do not display unmeasured performance or calibrated-looking confidence. UI never invents
live market data.

### Operational SLOs (targets not claims)
- WS reconnect with exponential jitter and observability; stale trades/book invalidated.
- Data freshness configurable per feed; alert decision must be based on matching snapshot and unexpired candidate.
- Recovery after Windows service restart without duplicate alerts.
- CI static checks + unit tests, nightly replay tests before live rollout.

### References (review quarterly)
- Delta India: https://docs.delta.exchange/
- CoinGlass V4: https://docs.coinglass.com/reference/getting-started-with-your-api
- CoinGlass permissions: https://docs.coinglass.com/reference/plans-and-permissions
- OpenAI structured output: https://developers.openai.com/api/docs/guides/structured-outputs
- Anthropic structured output: https://platform.claude.com/docs/en/build-with-claude/structured-outputs
