# DESIGN.md — Dual AI Market Intelligence Architecture

**Status**: Design v0.2 / research MVP. **Scope**: deterministic analysis only in Phase 2;
AI confirmation, alerts and order execution are disabled. **Deployment**: native Windows Server
2022/2025 initially; Python worker/API run as Windows services after validation. Linux VM/docker
optional, not required for this starter.

**Independent review:** the merged v0.2 implementation has unresolved correctness and AI-boundary
findings documented in [the Phase 2 review](docs/audits/phase-2-independent-review.md). Architectural
requirements below are not proof that every invariant is already enforced. The next implementation
sequence is [CODEX_PHASE_3.md](prompts/CODEX_PHASE_3.md), beginning with the corrective 3A slice.

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
    H --> T[Telegram / Email Alert Workers]
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
3. Freeze canonical snapshot + hash. Persist the deterministic candidate revision and lifecycle
   transition. Phase 2 stops here: it does not invoke GPT, Claude, alerts or execution.
4. Phase 3 may give the same immutable snapshot to two independent AI calls. Strict parsing and
   fail-closed consensus remain future gates; no Phase 2 candidate is `CONFIRMED`.
5. Risk gate: positive entry/stop distances; reward/risk threshold; current price/timestamp freshness; legal/operational source entitlements; no disabled periods; duplicate suppression. `CONFIRMED` is merely an **alert**, NOT an instruction to buy options.
6. Record candidate revisions, state transitions, invalidation and expiry as append-only rows. Never
   overwrite history. Historical replay evaluates at each event-time candle close and requires the
   candle's explicit availability timestamp in addition to event/receive clocks for trades and books.

### Volatility and performance
ATR is a scale, not a directional prediction. Naive `ATR * sqrt(horizon / bar_minutes)` is a loose heuristic, not a forecast. Intraday sessions/news cause regime changes. Need walk-forward and purged time-based holdout, bootstrap CIs by day, fees/slippage, and target-before-stop labelling; ambiguous same-bar high/low = conservative loss or separate ambiguous bucket, not automatic win.

### Storage and messaging roadmap
- **M1 single-host store**: SQLite WAL contains immutable candidate/audit records plus an append-only
  raw public-event journal keyed by UTC-day logical partition. Database triggers block raw event
  updates/deletes. Deterministic replay rebuilds closed trade-derived candles and books. REST
  candles carry their response availability time in memory but are not yet stored as a raw source.
  Feature snapshots and candidate/lifecycle evidence are persisted. This is durable across
  process restart but is not yet throughput-qualified as a high-frequency production tick database.
- **Production target**: PostgreSQL + TimescaleDB (Windows native PostgreSQL or optional isolated Linux VM), durable raw events and candle tables; queue via PostgreSQL outbox or Redis in a supported Linux VM. Do NOT rely on discontinued native Windows Redis ports. Migrate only after measured feed throughput.
- Retention policies: raw order-book updates may grow quickly; sample or compress according to license and analytical requirements. Backups: nightly database + off-host restore test.

### Security
Windows service identity with least privileges; API listens on 127.0.0.1 behind authenticated HTTPS reverse proxy; no broad CORS; environment secrets not committed; audit access and rotation; `TRADING_ENABLED=false` permanently in this MVP. Record minimal safe diagnostics. Exchange data, retrieved news and LLM output are untrusted.

### Options follow-up (not implemented in MVP)
Discover active option products, strikes/expiries, full bid/ask, IV/Greeks; independently compute delta exposure, decay, expected value and worst-case spread/slippage. Validate premium economics before ranking CALL/PUT instruments. Distinguish underlying signal from options order.

### Operator-visible dashboard
Six-card grid, data freshness/status per market, source provenance, dual-provider verdicts, disagreements and spend, candidate lifecycle, historical performance (sample size), options page (after Phase 3), system health. Show `WAIT` by default. UI never invents live market data.

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
