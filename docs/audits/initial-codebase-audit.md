# Initial codebase audit — Delta market-data integrity

Audit date: 2026-11-21 (Asia/Kolkata)
Baseline commit: `b661e5b` on `main`
Task branch: `feature/delta-market-data-integrity`

This is an implementation audit, not a profitability or production-readiness assessment. Live
trading and order placement remain out of scope.

## Baseline validation

The first invocation of the requested commands could not start because this host had no usable
Python installation and the frontend dependencies were absent. Python 3.12.10 was then installed,
the repository-local `.venv` was created, declared Python dependencies were installed, and
`npm install` was run in `frontend/`.

| Command | Baseline result after dependency setup |
|---|---|
| `.venv\Scripts\python.exe -m pytest -q` | PASS — 25 tests |
| `.venv\Scripts\python.exe -m ruff check .` | FAIL — existing UTC alias, import order, line length and explicit `zip(strict=...)` findings |
| `.venv\Scripts\python.exe -m ruff format --check .` | FAIL — 14 files required formatting |
| `.venv\Scripts\python.exe -m compileall -q src` | PASS |
| `npm run typecheck` | PASS |
| `npm run build` | BLOCKED — esbuild was denied traversal above the managed workspace; TypeScript compilation itself completed |

The original CI referenced `frontend/package-lock.json` for npm caching but the lockfile was not
present. The install generated and now commits that lockfile.

## Baseline findings

### High severity

1. **Order-book integrity was not implemented.** The collector subscribed to the periodic
   top-15 `ob_l2` snapshot and accepted it without sequence or checksum verification. A gap,
   stale snapshot, crossed book, or malformed side could be exposed as the latest book.
2. **WebSocket events were memory-only.** Trades and book messages disappeared on restart and
   could not be replayed, audited, or reconciled. The worker could report `CONNECTED` after a
   trade even though no raw event was durably stored.
3. **Instrument discovery did not validate contract semantics.** A symbol was considered valid
   unless its state was literally `expired` or `delisted`; `live`, `trading_status`, contract type,
   tick size, contract value, underlying, quote, settlement, and contract-unit currency were not
   enforced.
4. **No streamed-candle replay or reconciliation existed.** REST candles were filtered by local
   time, but there was no independent trade aggregation, alignment validation, or deterministic
   replay proving the same closed candles after restart.

### Medium severity

1. Unknown buyer roles were discarded instead of being preserved as unclassified executed
   trades. Duplicate and out-of-order trade behavior was not tested.
2. REST requests had no bounded retry/cooldown behavior for 429 or transient 5xx responses.
3. The WebSocket reconnected with jitter, but no test demonstrated reconnect/resubscribe and no
   incremental book snapshot was restored after a detected integrity failure.
4. SQLite stored candidates/decisions but had no immutable raw-event or source-status history,
   retention enforcement, or measured high-frequency L2 capacity.
5. FastAPI is unauthenticated. It is safe only while bound to localhost as documented.
6. CoinGlass implements only a supported-coins request. Entitlements, pagination, quotas, caching,
   freshness, and downstream feature activation remain incomplete.
7. The frontend is a read-only overview, not the required order-flow/replay dashboard. It does not
   expose raw feed provenance, book validity, trade-window statistics, or reconciliation state.

### Low severity

1. The test setup emitted a pytest-asyncio loop-scope deprecation warning.
2. Several project files did not satisfy the repository's configured Ruff rules/formatter.

## Working and safety-positive behavior observed

- `TRADING_ENABLED=true` is rejected by settings validation; no order/execution route or exchange
  private-key integration exists.
- Live ingestion, AI calls, and CoinGlass are off by default.
- Candidate construction uses closed, contiguous candles and marks its provisional source quality
  `INCOMPLETE`, so the normal worker path cannot confirm the starter breakout candidate.
- GPT and Claude adapters receive the same serialized candidate independently; provider errors
  fail closed. These were fixture-tested only, not called live in this audit.
- Consensus checks matching snapshot/direction, warning-free dual approval, age, expiry, and target
  overlap. It remains a later-milestone component rather than evidence that M1 is complete.
- Candidate, assessment, decision, budget, ATR, detector, and conservative outcome helpers had 25
  passing baseline tests.
- The API has read-only routes only, and the React frontend contains no secrets or order actions.

## Mocked, unverified, and incomplete integrations

- Baseline Delta tests used minimal hand-written dictionaries; there was no recorded official
  product/trade/book contract fixture. This M1 slice adds official-document-derived fixtures.
- OpenAI, Anthropic, and CoinGlass network calls were not made. Models, entitlements, billing, and
  provider schema compatibility remain unverified.
- Windows Service installation, reboot recovery, backup/restore, NTP behavior, filesystem ACLs,
  reverse-proxy authentication, and production SQLite throughput were not exercised.
- No claims can be made about signal quality, hit rate, liquidity, slippage, or profitability.

## Time-bounded live Delta discovery evidence

A read-only call to `https://api.india.delta.exchange/v2/products` at
`2026-11-21T10:50:32.7438841Z` returned `success=true` and 1,639 product rows. At that instant:

- `BTCUSD` (product 27) was a live/operational perpetual, contract value `0.001 BTC`, tick size
  `0.5 USD`, quoted/settled in USD.
- `XAUTUSD` (product 131253) was a live/operational perpetual, contract value `0.001 XAUT`, tick
  size `0.01 USD`, quoted/settled in USD.
- `PAXGUSD` (product 123006) was a live/operational perpetual, contract value `0.001 PAXG`, tick
  size `0.01 USD`, quoted/settled in USD.

This is a transient discovery observation, not a committed live-market snapshot. Runtime code must
rediscover and validate availability every time; Gold must become `UNAVAILABLE` if neither linear
contract is eligible.

A separate 25-second, read-only public WebSocket smoke test began at approximately
`2026-11-21T11:01:17Z`. The implemented adapter received and validated:

- initial `ob_updates` snapshots for `BTCUSD` (sequence 10,353,060) and `XAUTUSD` (sequence
  9,006,073), followed by contiguous updates for both;
- one public `BTCUSD` executed-trade event; and
- final in-memory book health `valid` for both symbols, including matching CRC32 checksums.

The smoke test used no credentials and placed no orders. Its short duration did not validate a live
disconnect, rate limit, long-lived clock drift, an XAUT trade, sustained throughput, or candle
reconciliation; those paths are fixture-tested or remain soak work. Four of the 1,639 product rows
did not satisfy the strict common product schema and were ignored; neither selected instrument was
among them.

## M1 slice implemented by this branch

- Versioned Pydantic product/instrument/raw-event/trade contracts with `Decimal` contract units.
- Live/operational linear BTC and XAUT/PAXG discovery with preferred-symbol fallback.
- Official `trades` and `ob_updates` parsing, buyer-role semantics, bounded 5,000-trade state, and
  500/5,000-compatible statistics that preserve unclassified trades.
- Full incremental order-book snapshot/update assembly with CRC32, sequence continuity, deletion,
  crossed/missing-side/staleness checks, and invalid-until-snapshot behavior.
- Logical UTC-day-partitioned SQLite raw journal with database triggers preventing updates/deletes,
  duplicate event-ID suppression, and append-only source-status events.
- Deterministic event-time trade replay to finalized candles plus REST-vs-stream reconciliation.
- Worker persistence/status wiring, persisted 1m REST-vs-stream reconciliation health, and
  reconnect/resubscribe behavior after book invalidation.
- Periodic product rediscovery that keeps healthy collectors running for unchanged symbols and
  replaces them only when verified availability changes.

## M1 branch validation

| Command | Result |
|---|---|
| `.venv\Scripts\python.exe -m pytest -q` | PASS — 66 tests |
| `.venv\Scripts\python.exe -m ruff check .` | PASS |
| `.venv\Scripts\python.exe -m ruff format --check .` | PASS |
| `.venv\Scripts\python.exe -m compileall -q src tests` | PASS |
| `npm run typecheck` | PASS |
| `npm run build` | PASS — Vite production bundle, 28 modules |

The frontend build required running outside the managed filesystem sandbox because esbuild must
traverse Node runtime paths. No frontend source was changed by that elevated build.

## Remaining M1 work and operational limitations

- Measure sustained `ob_updates` throughput and storage growth before treating SQLite as suitable
  for continuous production collection; define and automate provider-license-compliant retention.
- Run a longer live soak to validate clock skew, reconnect cooldown, and candle reconciliation over
  actual outages. Fixture coverage does not prove 24/7 external availability.
- Accumulate enough live reconciliation coverage and make that health an explicit candidate
  eligibility input. Results are persisted as feed status, while candidate generation remains
  `INCOMPLETE`, which is safe but not feature-complete.
- Add backup/restore automation and off-host recovery validation.
- Add authenticated feed-health/replay API views and frontend presentation in a later milestone.
