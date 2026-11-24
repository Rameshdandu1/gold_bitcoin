# DESIGN.md — Dual AI Market Intelligence Architecture

**Status**: v0.6 implementation / Phase 6 offline contract corrections implemented; external validation follows. **Scope**: deterministic analysis plus opt-in dual-AI
review and Slack alerts; all external paths are disabled by default and order execution is absent. **Deployment**: native Windows Server
2022/2025 initially; Python worker/API run as Windows services after validation. Linux VM/docker
optional, not required for this starter.

## Phase 6 evidence architecture

The [independent Phase 6 review](docs/audits/phase-6-independent-review.md) defined the closeout
findings and acceptance gaps. Their offline disposition is recorded in the
[Phase 6 closeout verification](docs/audits/phase-6-closeout-verification.md). The later
[independent closeout review](docs/audits/phase-6-closeout-independent-review.md) verifies all five
exact corrections and tested resume paths. The later
[workflow acceptance verification](docs/audits/phase-6-workflow-acceptance-verification.md) records
the exact P6C-01/02/03 corrections and two-length resource evidence. The
[independent workflow-acceptance review](docs/audits/phase-6-workflow-acceptance-independent-review.md)
confirms those controls but reproduces P6W-01 through P6W-06 in the existing recovery/parity/resource
contracts. Their corrected evidence is recorded in the
[contract-corrections verification](docs/audits/phase-6-contract-corrections-verification.md).
Routine live operation follows the external validation gates.

The alert worker refreshes its clock at each risk attempt and again inside the short dispatch
authorization transaction. The eligibility token and evaluated trade set use the same receive-time
cutoff; the authorization records its actual time and the same book event-time freshness deadline
used by the current quality check. Legacy jobs without complete frozen request policy are
quarantined with a typed zero-call disposition.
Migration `0006_phase6_evidence_integrity` is additive.

The authenticated dashboard is itself a durable operator surface. A confirmed decision may be
committed without an external notification intent when `ALERTS_ENABLED=false`; Slack readiness is
evaluated independently and an outbox row is created only when alerts are explicitly enabled with
a configured destination. Provider connectivity smoke requests use the strict adapters and durable
UTC-day budget ledger.

Research stores provider completion and availability separately. Provider evidence uses the
authoritative envelope availability clock and rejects conflicting payload clocks. Modes,
request/configuration digests and available provider/model provenance are retained; missing genuine
provider identity remains unavailable rather than inferred. Synthetic/prospective mode conflicts
are rejected. Quote and OHLC evaluation require anchored, contiguous coverage through entry and
expiry, including complete pre-entry intervals.

The scheduler evaluates every frozen cadence even during input silence. Source transitions are
applied at their availability time to provider readiness and outcome eligibility. Production
consensus and connected research reuse clock-injected predicates for revision, lifecycle, expiry,
source, stop, spread, entry drift and current target economics. Individual arm decisions are
written once at their own readiness boundary. Raw provider verdicts and approved target indices are
retained separately from individual market dispositions, so dual consensus applies its own later
gate without rewriting either individual arm. Executed stop and per-target crossing facts retain
exchange occurrence and receipt clocks. A terminal stop remains durable but cannot create a
monetary outcome until quote/source/instrument coverage establishes an executable quote-side exit.

The connected `paper-workflow` command consumes the stored normalized journal in indexed 500-event
input batches, writes approved decisions before latency-adjusted eligible entry, and separately persists
terminal unavailable/no-position decisions at their factual resolution. Run identity binds the
experiment, configuration, dataset and processing/latency policy. Fixture runs are labelled
`SIMULATED_PROSPECTIVE`, never prospective elapsed observation. Paper rows retain partition
provenance; ordinary API, count and export paths hide protected/crossing outcomes until
`final-holdout` records the frozen access identity. Legacy rows lacking provenance are hidden from
scoped projections.

Research and paper query indexed candidate-time quote/source windows in pages. Eligibility is
checked before evidence is loaded, input and candidate pages have explicit peaks, and completed
paper candidate state is retired after durable outcome persistence. The 1,000/8,000 old-quote probes
keep the same maximum active set (three), quote page (six rows) and outcome set. The separate
two/eight-lifetime review found provider history retained in checkpoints and complete opportunity
materialization before report/API paging. The correction indexes provider history durably, retires
resolved working objects after dependent decisions persist, and performs opportunity selection,
holdout filtering and page limits in SQLite before Pydantic model construction. Report metrics are
single-pass and the selected-opportunity export is streamed in 200-record pages.

The local-stream worker commits each event and cursor atomically and binds progress to source
identity, generation and a consumed-prefix SHA-256.

## Phase 5 evidence foundation

The public `run-workflow` command validates the canonical dataset manifest, externally sorts input
by factual availability, and sends normalized trades, candles, book generations, instruments and
recorded provider completions through `SharedResearchEngine`. That service retains at most 5,000
trades per symbol and 2,000 candles per symbol/resolution and invokes the production
`detect_signal` function for all six engines. It never has a provider, notification, account or
order transport.

Candidates, four-arm decisions and their target/configuration identities are immutable records.
Candidate creation and its deterministic `RULES_ONLY` decision commit in one transaction;
identical retries repair an already matching candidate/initial-arm pair and conflicting payloads
still fail.
Phase 6 persists archived-provider decisions when their evidence becomes available, preserves
their clocks/provenance and revalidates source state before entry. Quote and OHLC evaluation now
require complete pre-entry and outcome paths. Ordinary aggregate, detail, API and export reads use
one holdout projection, with deliberate final access recorded before protected results become
visible.

`run-workflow` checkpoints manifest/config identities, the committed input offset, next evaluation
clock, bounded trades/candles/books, source history, provider slots and pending scientific state.
Fresh-process resumes skip the committed prefix and reject source/configuration drift. Output writes
are immutable and the tested candidate/rules, GPT and output checkpoint paths recover. The paper
bridge reports warmup, partial, unresolved and complete states. Corrected contract versions
explicitly refuse an old derived checkpoint rather than mixing old and new scientific identities;
the lifecycle, target-crossing and provider-index tables are additive and retain old evidence.

Manifest hashes commit to the canonical manifest preimage and ordered file identities. Experiment
hashes commit to dataset, algorithm, engine/feature, target/revision, cost, schedule, partition,
seed and variant policy. Checkpoints bind both hashes and validate the consumed input prefix while
retaining only the most recent 128 diagnostic event IDs. Conflicting writes fail instead of
overwriting scientific history.

The paper ledger binds candidate, revision, arm, target, configuration, source identity/generation,
decision persistence time and eligible-entry time. Prospective entries/outcomes must occur after
the decision write and be factually available before recording. Historical import remains a
distinct evidence mode. Phase 6 advances a source-bound cursor in the same transaction as each
idempotent event and detects replacement, reordering or truncation through a consumed-prefix hash.

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

**Independent review:** historical verification reports retain their original executed checks.
The [Phase 6 independent review](docs/audits/phase-6-independent-review.md) records current verified
fixes and remaining acceptance boundaries. Architectural requirements remain distinct from empirical
acceptance: live providers, licensed data, prospective duration and destination deployment are not
proven by fixtures. Passing fixtures are not evidence of live provider readiness or strategy performance.

## Operator read model (observability slice)

The authenticated market overview uses existing local trade, book, discovery, source-status,
engine and feature-snapshot records. Source states, timestamps and explicit stale/unavailable
labels are separate from configuration flags and historical review decisions. It performs no
provider calls and cannot approve signals. Independent overview/history polling prevents a
research API failure from hiding the market view. Full live readiness and delivery eligibility
remain separate backend policies.

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
   overwrite history. The required shared strategy replay must reproduce observation availability
   and evaluation cadence while features use event time. The current visibility-only timeline and
   older candle-close helper do not yet implement that complete workflow.

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
