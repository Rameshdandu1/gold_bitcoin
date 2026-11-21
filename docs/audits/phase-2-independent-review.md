# Phase 2 independent review and Phase 3 entry gates

Review date: **2026-11-21**. Reviewed repository: `Rameshdandu1/gold_bitcoin`.

Reviewed code: [`10b3e9118448b55db80c94ae91cee7e227a64932`](https://github.com/Rameshdandu1/gold_bitcoin/commit/10b3e9118448b55db80c94ae91cee7e227a64932), the merged Phase 2 implementation from [PR #2](https://github.com/Rameshdandu1/gold_bitcoin/pull/2).
This is an independent review of that commit, not a claim that the findings below have been fixed.
All numerical market examples in this report are **hypothetical test fixtures**, not live prices or measured trading outcomes.

## Verdict

**The six-engine research foundation is implemented, but Phase 2 does not yet pass a clean correctness review.**
The existing suite passes. Additional fixture probes expose incorrect session context, missed price invalidation, repeated structural events, and gaps in the point-in-time and operator-display contracts.

Phase 3 should begin with a corrective slice, then implement the dual-provider review service. Keep paid AI calls and outbound alerts disabled until its acceptance gates pass. Model agreement cannot restore omitted observations or correct a stale candidate lifecycle.

The active quantitative worker deliberately stops before the AI branch (`worker.py:237–238`). Dormant AI-scaffold defects below are **future integration blockers**, not evidence that Phase 2 currently publishes live AI confirmations.

## Verification actually performed

| Check | Observed result |
|---|---|
| Main and PR state | PR #1 and PR #2 merged; main resolved to the reviewed SHA |
| GitHub Actions | [Run 44911653899](https://github.com/Rameshdandu1/gold_bitcoin/actions/runs/44911653899) succeeded; backend and frontend jobs inspected |
| CI backend log | 126 tests passed; Ruff lint/format and Python compilation passed on Windows/Python 3.12.10 |
| Independent local backend run | `python -m pytest -q`: **126 passed**; one host-installed AnyIO pytest-plugin deprecation warning |
| Independent local static checks | `ruff check .`, `ruff format --check .`, `compileall -q src tests` passed; 48 files already formatted |
| Independent local frontend | `npm ci --no-audit --no-fund`, `npm run typecheck`, `npm run build` passed |
| Additional review probes | Real detector/features, SQLite store, worker polling, and consensus functions exercised using fixtures and controlled clocks |

Local verification used Linux, Python 3.12.14, Node 24.22.3 and npm 11.19.1. The dependency install resolved OpenAI 2.54.0 and Anthropic 0.125.0; their asynchronous parse helper parameters were inspected. These observations do not establish account/model access or successful paid API calls.

No Delta live-market soak, paid CoinGlass call, GPT/Claude request, notification delivery, Windows service installation, server deployment, profitability test, or order placement was performed in this review. Source code was not changed to make the probes pass. The review probes are additional evidence, not additions to the reported 126-test suite.

## Phase 2 findings

Severity meanings: **P1** changes candidate validity or leaves a breached candidate active; **P2** breaks an advertised invariant, event identity, degraded-state behavior, or operator presentation.
Line references below refer to the reviewed commit.

### R1 — P1: short trigger history is labelled as full session history

Locations: `src/marketintel/quantitative.py:415–430`, `features.py:146–165,321–359,590–600`, `worker.py:110–116`.

`detect_signal` crops every candle series to `min_candles`, then uses that cropped series for UTC-session VWAP, session highs/lows, previous-day extremes, and resampled context. FAST retains 40 minutes; HOURLY retains five hours; SESSION retains 25 hours, which need not contain a complete previous day. The worker also fetches only `min_candles + 10` bars. Fixing the crop alone is insufficient.

This changes both the VWAP direction gate and the opposing-level target filter. There is no coverage flag distinguishing a complete session from a partial rolling window.

Two reproduced cases, using the existing `policy_bars`, `supportive_trades`, `supporting_book`, and `instrument` helpers in `tests/test_phase2_quantitative.py`:

| Hypothetical GOLD_HOURLY case | Full available UTC-session facts | Snapshot and candidate actually produced |
|---|---|---|
| Bullish: 120 contiguous 5m bars, midnight–10:00; earlier high-volume prices around 2,612; final close 2,608 | VWAP 2,611.210823; earlier high 2,615, only 7 above entry | VWAP 2,600.365314; retained high 2,607; targets 2,628 and 2,638 |
| Bearish mirror: earlier high-volume prices around 2,588; final close 2,592 | VWAP 2,588.789177; earlier low 2,585, only 7 below entry | VWAP 2,599.634686; retained low 2,593; targets 2,572 and 2,562 |

Under the implementation's own 90%-of-opposing-room policy, a known level seven dollars away permits at most 6.30 dollars of target distance. Discarding that level incorrectly permits the 20/30-dollar tiers. The full-session VWAP would also fail the stated direction gate in both cases.

**Required fix:** separate trigger lookback from session/context coverage. Fetch or accumulate sufficient history using verified provider limits. Persist coverage start/end/completeness. If coverage is insufficient, report the affected feature unavailable and apply the engine's documented required/optional policy. Do not silently rename a partial window a daily range. Add both counterexamples as regression tests.

### R2 — P1: price breaches can leave candidates active

Locations: `src/marketintel/worker.py:216–238`, especially line 221; `quantitative.py:799–804`.

The lifecycle sweep receives the latest **closed candle close**, although fresh executed trades and a fresh book are already available. A stop crossing between candle closes can be missed; checking only the latest traded price would also miss a crossing followed by recovery.

The review ran the real polling worker, detector, and SQLite store with fixture REST responses, parsed/journaled trades, a book checkpoint, and a controlled clock:

| Hypothetical case | Invalidation | Recorded post-observation breach | Latest trade | Price supplied to lifecycle | Observed result |
|---|---:|---:|---:|---:|---|
| BTC_FAST bullish | 69,000 | 68,999 | 68,999 | 70,251 | Candidate remains active |
| GOLD_HOURLY bearish, breach then recovery | 2,605 | 2,606 | 2,600 | 2,592 | Candidate remains active |

Both snapshots were `FRESH` with `book.available=true`. Passing the recorded breach directly to `terminal_transition` produced `INVALIDATED` in both cases. The BTC probe also generated a new candidate with entry 70,251 and invalidation 69,672.921429 while the latest trade and fresh bid were 68,999: the candidate was already beyond its own invalidation at admission.

**Required fix:** define a versioned trade/quote price policy, monitor every relevant post-observation event from a durable watermark, and enforce current eligibility before admitting a new candidate. Preserve terminal state after recovery. Gaps or unknown event ordering must produce an explicit unavailable/ambiguous result. Repeat the check before AI dispatch and before final publication.

### R3 — P2: one pivot break becomes several new BOS events

Locations: `src/marketintel/features.py:261–295`, `quantitative.py:313–335,655–666`.

The structure function compares the latest close with the last confirmed pivot and stamps the latest candle as the break time. It does not establish whether an earlier candle already broke that pivot. Candidate IDs include candle close, so ordinary duplicate-ID suppression does not catch this.

Two reproduced cases extend the existing GOLD_SESSION fixture with two 15m continuation bars:

- Bullish: the same 2,605 pivot from 23:00 is called a newly confirmed BOS at 01:00, 01:15, and 01:30. Three distinct candidate IDs are emitted.
- Bearish: the same 2,595 pivot similarly produces three newly timed BOS events and three distinct IDs.

**Required fix:** evaluate structure chronologically and preserve first-break identity/time. A consumed pivot cannot create another first-break event. If a continuation trigger is wanted, give it separate documented rearm rules. Test sustained closes beyond an old pivot and a later break of a genuinely new confirmed pivot.

### R4 — P2: the central detector ignores candle availability time

Locations: `src/marketintel/features.py:68–75,130–141`; `quantitative.py:403–420`.

`closed_candles` tests interval close time but ignores explicit `available_at_utc`. Resampling also drops availability metadata.

Two reproduced cases: set every candle in the valid GOLD_FAST fixture, then in the valid BTC_FAST fixture, to become available at **2026-11-19 00:40 UTC**. Evaluate at **2026-11-18 00:40 UTC**. Direct `detect_signal` still returns `CANDIDATE` in both cases.

**Scope:** `replay_engine` independently filters availability at `quantitative.py:837–843`; the live worker normally captures its decision clock after REST data arrives. These probes demonstrate a reusable-detector invariant gap, not leakage through the current replay wrapper.

**Required fix:** enforce both closed time and factual availability at the common boundary. Preserve maximum constituent availability on resampling. Unknown historical availability must not silently mean known-at-close. Test direct evaluation as well as the replay wrapper.

### R5 — P2: terminal lifecycle state is missing from the dashboard data path

Locations: `src/marketintel/storage.py:692–704`, `api.py:36–46`, `frontend/src/main.tsx:31,63–65`.

The list route returns the immutable candidate packet and consensus, without the current lifecycle. The dashboard uses the consensus status or `UNREVIEWED`; it does not consume the lifecycle endpoint.

For both the BTC and Gold probes, appending a real `INVALIDATED` transition left the list packet's creation-time `state=CANDIDATE`; its only top-level keys were `candidate` and `consensus`, so the UI showed `UNREVIEWED`. The separate lifecycle endpoint retained the correct event.

**Required fix:** preserve immutable creation data and add separate `current_lifecycle_state`, reason/time, and exact current review identity to the read model. Show `INVALIDATED`/`EXPIRED` prominently. Lifecycle state and AI review status are separate concepts.

### R6 — P2 operational gap: discovery failure does not create a continuing admission gate

Locations: `src/marketintel/worker.py:401–452`.

After successful discovery, a later discovery exception sweeps existing candidates and records `worker=ERROR`, but leaves polling/stream tasks active and discovery status at its previous value. A real `worker.main` scheduling probe with fake collectors observed the poller executing after the error, no collector cancellation before retry, and stale `product_discovery=PARTIAL`.

This proves task continuation and stale discovery status. It does **not** prove that the real detector emitted a candidate during an actual exchange outage. Continuing raw collection with cached verified metadata can be a legitimate design; silently leaving admission unaware of the error is the gap.

**Required fix:** specify a bounded metadata-cache/freshness policy, expose degraded discovery status and last successful verification separately, and make candidate admission consult that policy. Test a refresh failure after healthy startup and startup without any verified instrument. A one-time sweep is not a continuing gate.

## Contracts to harden before Phase 3

### C1 — Canonical evidence and in-memory immutability

`CandidateSignal` is frozen, but `targets`, `feature_evidence`, and `counter_evidence` are mutable lists (`models.py:406–429`). Assigning `candidate.targets[0] = 5000` changed `packet(candidate)` while leaving its snapshot ID unchanged. This establishes a missing immutability guarantee; it does not establish that current worker code performs such a mutation.

`features.py:615–640` hashes a custom payload that includes `last_close`; the persisted `FeatureSnapshot` at lines 641–664 omits that field and changes the layout. The ID is deterministic during construction, but its exact preimage cannot be recovered from the stored snapshot alone.

Persist one versioned canonical envelope, including the candidate revision and full feature evidence, together with its exact bytes and digest. Use deeply immutable values and one encoder. Preserve legacy IDs; do not silently rehash history. Reject attempts to reuse a canonical digest with different bytes.

### C2 — Revision-scoped reviews and storage

Current assessments are keyed by candidate/provider and saved with `INSERT OR IGNORE`; decisions are keyed only by candidate and replaced. The latest-candidate query joins decisions on candidate ID alone (`storage.py:96–108,630–674,692–704`).

Reproduced: save revision A plus its confirmation, then revision B. The list returns candidate **B** alongside **A's `CONFIRMED` decision**. Saving B's GPT assessment retains A's row. This is a dormant integration risk because the Phase 2 worker does not create AI decisions.

Use append-only review runs, provider attempts, decisions, and notification intents keyed to the exact revision and canonical input. A newer revision must not inherit an older approval; a late response must not revive an invalidated candidate.

### C3 — Dormant provider/consensus scaffold is not an M3 implementation

| Existing behavior | Phase 3 requirement |
|---|---|
| `ai.py:25–26` sends only the candidate summary | Both providers receive the same full canonical candidate-plus-feature packet, including numeric evidence and provenance |
| Parsed assessment discards SDK response metadata | Record server-owned provider identity, requested/returned model, request/response IDs, usage, finish/refusal status, and timing |
| Two budget reservations can hide SDK retries | Reserve every actual attempt atomically; explicitly control retry, token, and estimated-cost limits |
| Per-request timeout without shared deadline | Absolute review deadline bounded by candidate lifetime; independent bounded worker queue |
| Consensus checks historical summary only | Recheck authoritative lifecycle, revision, current feed/book, entry drift, stop/target history, and risk geometry before publication |
| Ordinary integer parsing plus filtering invalid indices | Strict unique indices, **1-based as in the current contract**, each within the frozen target array; reject the entire malformed assessment |
| Both UI provider cards inferred from consensus presence | Render each actual provider outcome and its revision, including missing/refused/timed-out states |

Additional reproduced dormant defects: a candidate observed ten seconds in the future can confirm; `now == expires_at` can confirm although Phase 2 expires at equality; `[true, "2", 2.0]` is coerced to `[1, 2, 2]`; `[1, 999]` can confirm by silently retaining index 1. All must be covered before connecting the six engines to AI.

## Remaining integration and operational limits

- REST/stream reconciliation `WAIT`/`INVALID` is recorded but not enforced at admission. The initial audit explicitly deferred this. Define required overlap/completeness and a hard gate; do not claim reconciliation health already protects confirmations.
- Unchanged source status does not advance `service_status.updated_at`. A transition timestamp is not a heartbeat or last verified observation. API response time likewise does not prove a current market feed.
- REST candle payloads and availability are not durably journaled yet. Store versioned raw responses/normalized observations and availability before claiming complete audit replay.
- CoinGlass paid entitlements, quota, response shapes, distribution permissions, and Delta India coverage remain unverified. Missing optional enrichment must be labelled; it must not be fabricated or silently declared required.
- Licensed XAU/USD, DXY, yields, and economic-calendar data remain unavailable. Token-market-only Gold research must remain explicitly identified. A missing required macro/calendar policy cannot be represented as a checked-and-clear result.
- Windows service recovery, SQLite throughput/retention, backup/restore, and an extended live-feed soak remain operational validation work.
- Test counts establish software checks. They establish no hit rate, probability, net expectancy, or benefit from dual-model agreement. Those require the Phase 4 comparisons and time-ordered evaluation.

## Next action

Implement [CODEX_PHASE_3.md](../../prompts/CODEX_PHASE_3.md) in order: **3A corrections, 3B evidence/storage contracts, 3C provider orchestration, 3D consensus/risk, 3E operator service and alerts**. Add targeted regressions for these findings before changing behavior. Record which gates are satisfied and which require operator credentials or a Windows host; do not mark untested live integrations complete.
