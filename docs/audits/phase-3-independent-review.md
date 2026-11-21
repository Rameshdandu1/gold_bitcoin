# Independent Phase 3 review and Phase 4 prerequisites

Review date: **2026-11-21**. Repository: `Rameshdandu1/gold_bitcoin`.

Reviewed code: [`d1978d30e48c0b8656d969da00ea70a7e4659562`](https://github.com/Rameshdandu1/gold_bitcoin/commit/d1978d30e48c0b8656d969da00ea70a7e4659562), after [PR #4](https://github.com/Rameshdandu1/gold_bitcoin/pull/4) merged. PR #3 containing the previous review/instructions is also merged.

## Verdict

**Phase 3 contains substantial implementation, but does not pass an independent integration review.** The original session-history, repeated-first-break and future-availability counterexamples are fixed. New probes reproduce false confirmation under a database race, stale alert dispatch, request-identity omissions, budget enforcement gaps and paths that prevent normal operation.

The next milestone is **Phase 4: historical evaluation and prospective paper research**, beginning with a mandatory **4A corrective slice**. Do not enable paid reviews or external alerts on the assumption that the passing fixture suite establishes readiness. Do not produce strategy-performance claims from the current replay/label helpers.

This report records findings, not fixes. No application source was changed during this review. All prices, credentials, usage values and transport responses used in probes were **hypothetical fixtures**. There were **zero paid API calls, zero exchange requests and zero real notifications** in the review probes.

## Verification and improvements confirmed

| Check | Observed result |
|---|---|
| Phase 3 GitHub CI | [Run 44918538264](https://github.com/Rameshdandu1/gold_bitcoin/actions/runs/44918538264) succeeded; backend/frontend job steps inspected |
| Independent local tests | **171 passed** in Python 3.12; two dependency deprecation warnings, no failures |
| Ruff | Lint passed; 63 files already formatted |
| Compilation | `python -m compileall -q src tests` passed |
| Frontend | `npm ci --no-audit --no-fund`, typecheck and production build passed |
| Additional probes | Real worker, detector, storage, consensus and alert-worker logic exercised using controlled clocks and fake transports |

Local checks ran on Linux, not a deployed Windows Server. The repository CI uses Windows. Windows service installation/reboot recovery, live model/account access, Slack authorization/deduplication, paid CoinGlass coverage, long-duration market collection, throughput and profitability remain unverified.

The original Phase 2 probes now show:

- **Session history:** both Gold examples retain the earlier 2,615 high / 2,585 low and calculate the full-session VWAPs 2,611.210823 / 2,588.789177. Both return WATCH rather than the earlier invalid candidate.
- **First-break identity:** one bullish or bearish pivot break creates one candidate; subsequent continuation bars return WATCH with the first-break timestamp preserved.
- **Future availability:** direct GOLD_FAST and BTC_FAST calls with next-day candle availability return WAIT.
- **Lifecycle presentation:** current lifecycle is exposed separately from the creation packet and displayed by the frontend.
- Canonical envelopes, revision records, provider attempts, budget reservations, authenticated views and an outbox exist. Their presence does not establish all the cross-component guarantees claimed in the implementation report.

## Confirmed Phase 3 findings

P1 denotes a confirmation/delivery correctness failure, an unenforced spend control, or an ordinary operating path that cannot work as documented. P2 denotes an identity/recovery/classification or input-handling defect. Source lines refer to the reviewed commit.

### P3-01 — P1: the documented environment template fails settings validation

Locations: `.env.example:30–33`; `src/marketintel/config.py:15,41–44`.

The four optional integer provider-rate settings are written as empty assignments. Pydantic does not interpret those empty strings as `None` under the current configuration. In an isolated environment, loading `Settings(_env_file=Path('.env.example'))` produces four `int_parsing` errors, one for each rate. Consequently, copying this file to `.env` as instructed prevents the API and workers from initializing even with AI disabled.

**Fix and tests:** support an intentional blank/unset representation or omit/comment the optional numeric assignments. Preserve missing pricing as NOT_READY, never as zero cost. Test a fresh template with all external services disabled and a configured operator/model with pricing deliberately absent; the application should start while paid dispatch remains blocked.

### P3-02 — P1: reconciliation compares a partial first minute with a complete candle

Locations: `src/marketintel/worker.py:224–253,330–347`; trade aggregation in `replay.py`.

The rolling query starts at `decision_now - 65 minutes`, which is usually inside a minute. Aggregation still treats the first resulting bucket as a complete closed candle. The new admission gate then requires this mismatched comparison to be VALID.

A probe persisted one trade per second across a complete interval. Full-history aggregation and the reference candles reconciled. At **11:05:30**, the production rolling query began at **10:00:30** and cut the first minute in half:

```text
full_history_valid=True
worker_window_valid=False
matched=64, mismatched=1
first_reference_volume=60, first_stream_volume=30
```

This demonstrates a recurring query-boundary problem, not missing exchange data. The probe uses the exact production query/helpers; it is not a measured live Delta failure rate.

**Fix and tests:** align acquisition boundaries and reconcile only buckets with proven full collection coverage. Test nonzero seconds/microseconds and startup/reconnect gaps. Do not hide real missing intervals merely to obtain VALID.

### P3-03 — P1: both provider requests omit the digest required in their answers

Locations: `src/marketintel/ai.py:75–80,126–137`; `review.py:49–65`; `analysis.py:75–107,207–211`.

The assessment must echo `analysis_input_hash == analysis.digest`. The canonical envelope correctly excludes its own digest, but the transports send only the envelope bytes. Neither outgoing request supplies the digest separately.

Capturing actual OpenAI and Anthropic SDK request arguments with fake SDK clients produced:

```text
OpenAI: actual_input_digest_supplied=False, hash_required=True
Anthropic: actual_input_digest_supplied=False, hash_required=True
```

Existing fixture responses obtain the digest out of band. A real model should not be expected to compute SHA-256 from a long JSON packet without tools.

**Fix and tests:** send a server-generated request wrapper containing the canonical input and its digest outside the hash preimage, identically to both providers. Verify complete outgoing SDK requests. A fake analyst used for the contract test must construct its response from only what the real request contains.

### P3-04 — P1: repeated observations supersede the only queued review

Locations: `src/marketintel/worker.py:363–395`; `storage.py:856–883,1634–1685`.

Review creation is conditional on inserting a new candidate ID. Later same-candle observations nevertheless create/activate new revisions. A real poller/SQLite probe with two controlled detector emissions, thirty seconds apart, returned:

```text
same_candle_emissions=2
active_generation=2
queued_runs=1
active_revision_matches_only_run=False
```

The only queued review refers to an obsolete revision. This is neither material-change deduplication nor replacement scheduling. A review that takes longer than the next poll can be rendered unusable without a review for the active revision.

**Fix and tests:** distinguish a new observation from a materially changed proposal. Timestamp-only refreshes must not churn proposal identity. A material supersession must cancel/obsolete the old job and schedule the new exact revision under bounded policy. Check eligibility before paid dispatch. Test unchanged evidence across polls and a genuine changed target/stop/evidence revision separately.

### P3-05 — P1: current-risk facts and their commit token can refer to different database states

Locations: `src/marketintel/review_worker.py:50–93`; `storage.py:1193–1280`.

Risk evaluation reads trades and book first, then separately captures the token used for the atomic commit check. That token is not guaranteed to describe the observations actually evaluated. Its trade component also covers only the latest receive-time row, not every newly persisted event.

Two confirmed examples use Gold entry 2,600 and stop 2,590:

1. Insert a 2,589 breach between the trade read and token capture. The old risk facts say `stop_breached=False`; the new token includes the breach. `decide_v2` returns CONFIRMED, commit succeeds, and one outbox row is created. An immediate reread returns WAIT with `stop_breached=True`.
2. After risk evaluation, persist a breach whose receive timestamp is older than the latest stored trade. The token is unchanged, so the stale confirmation commits. This case concerns delayed persistence/import/recovery; normal stream ordering was not assumed.

**Fix and tests:** obtain facts and their versions from one consistent database snapshot. Use a monotonic persistence generation covering every relevant insert, including older timestamped rows, plus versions for book, lifecycle, revision and source health. Commit only against matching versions and current time/deadline. Do not keep database transactions open across provider or notification HTTP calls. Test both race windows and a healthy positive path.

### P3-06 — P1: an alert can be dispatched after a known breach and disconnect

Locations: `src/marketintel/storage.py:1436–1460`; `notifications.py:116–131`.

Delivery eligibility checks revision, lifecycle and expiry, but does not repeat the current-market checks. After a valid confirmation was committed, the probe recorded a 2,589 breach and `delta_websocket=DISCONNECTED`. Before the polling worker appended terminal lifecycle, a fresh call to current eligibility returned WAIT, while the alert worker called its fake transport and marked the confirmation SENT.

**Fix and tests:** before confirmation dispatch, re-evaluate current required source/price/book/risk eligibility consistently. Suppress obsolete intents with a durable reason. Test a stop breach awaiting lifecycle materialization and a required feed disconnect. Terminal notifications need their own rules so an outage does not suppress the notice explaining the invalidation. No real Slack dispatch was performed.

### P3-07 — P1: input limits and actual-consumption budget limits are not enforced

Locations: `src/marketintel/orchestration.py:57–64,135–146`; `storage.py:1525–1607`; provider dispatch in `ai.py`.

`ai_max_input_tokens` is used to estimate a reservation, without counting/bounding the request before dispatch. Subsequent admission sums original reserved cost while reported actual cost is stored separately.

The synthetic probe configured a **1,000-token** input cap and **5,000 micro-USD** daily cap, supplied a **63,096-byte** packet, and returned fake usage of **6,000 input + 16 output tokens** per call. Two calls recorded actual cost **12,032 micro-USD**, already above the cap. Another dual run still dispatched:

```text
reserved_calls=4
reserved_cost_microusd=4,256
reported_actual_cost_microusd=24,064
```

These are fixture ledger values, not an actual bill.

**Fix and tests:** bound the complete request, including instructions/schema/wrapper, before dispatch. Admission must account for known actual consumption plus outstanding/unknown reservations. Test an oversized request making zero calls and actual usage exceeding a reservation preventing further calls. Keep unknown usage conservatively reserved. Account for provider-specific usage categories and versioned rates without double-counting cached/reasoning tokens. No application estimate can guarantee a provider's final invoice.

### P3-08 — P2: outbox recovery and destination identity are incomplete

Locations: `src/marketintel/storage.py:1397–1434`; `notifications.py:125–169`.

Two reproduced cases:

- A fake receiver accepts a message, then the task is interrupted before its receipt is saved. The row remains CLAIMED. After lease expiry, a new worker sends again: two accepted fake calls, the same delivery key, final status SENT. Actual Slack deduplication is unverified; this proves automatic replay of an ambiguous dispatch, not two observed Slack messages.
- An intent stored for `slack:original-channel` is sent to the current setting `fixture-channel`. Delivery ignores the destination bound into the durable intent/key.

**Fix and tests:** persist dispatch-start separately from claim, recover uncertain dispatch into an explicit reconciliation state, and resolve the immutable destination of the intent. A changed configuration must not redirect pending messages silently. Test both interruption boundaries and destination mismatch; use idempotency only where the external contract actually supports it.

### P3-09 — P2: provider run identity and completion semantics are not fully enforced

Locations: `src/marketintel/storage.py:969–978`; `orchestration.py:200–202`; `ai.py:291–340`.

Two reproduced cases:

- A run queued with `queued-old-openai` / `queued-old-anthropic` executes using current settings `fixture-openai` / `fixture-anthropic` and stores SUCCEEDED results under the old run identity. The stored provider configuration is not checked at execution.
- An otherwise valid fake assessment with `finish_reason='failed'` becomes `ProviderResult.status='SUCCEEDED'`. The adapter does not require a provider-specific successful terminal status. This is a boundary-validation test, not evidence of such a live provider response.

**Fix and tests:** execute the frozen queued configuration or fail/requeue under a new identity. Bind model, prompt/schema, output parameters and policy versions. Require a valid successful terminal provider status, semantic validation and an unexpired run; failed/cancelled/incomplete replies cannot approve.

### P3-10 — P2: earlier bullish pivots permanently override later bearish structure

Location: `src/marketintel/features.py:270–278`.

`bias_before()` takes the set of every historical pivot kind. Once HH and HL have occurred, the bullish branch remains true even after a new sequence of confirmed lower highs and lower lows.

With hypothetical closes `100,101,110,105,95,100,115,105,98,104,108,100,90,95,103,95,85,90,99,90,80,85,90,101` and high/low equal to close +/-0.5:

- A downward continuation through 84.5 at minute 21 is labelled CHOCH after bearish structure is established.
- The subsequent upward break through the 99.5 lower high at minute 24 is labelled BOS.

**Fix and tests:** define chronological trend state from the relevant most recent confirmed swings/prior break state. Preserve the corrected first-break identities. Test continuation and reversal after a regime change and a mirrored sequence. The probe establishes incorrect evidence labels; it does not establish that candidate direction itself flips.

### Lower-priority input handling

`api.py:36–38` passes Unicode strings to `secrets.compare_digest`. A valid UTF-8 Basic username such as `operátor` produces HTTP 500 rather than an authentication failure. Compare encoded bytes or validate an explicit permitted character set. Test non-ASCII username and password paths. No authentication bypass was demonstrated.

## Source-evidenced recovery/deadline acceptance gaps

These were identified by reading control flow and are not included as additional reproduced race findings:

- `orchestration.py:282–288` marks a review COMPLETED before `review_worker.py:198–229` commits consensus. Add a crash test at that boundary and recover finalization from saved results without repeating provider calls. A durable RESULTS_READY/DECISION_PENDING stage or equivalent transactionally complete workflow is needed.
- Remaining deadline is checked before the provider call, but final completion and decision commit do not consistently carry/check the stored run deadline. Test response completion and delayed finalization at/after the deadline, lease fencing and expiry equality.
- Claims of bounded retries should be verified against Retry-After handling and remaining deadline, not only a short fixed sleep. A source status timestamp is not proof of current readiness.

## Existing Phase 4 scaffold limitations

These predate Phase 3 or belong to deliberately unfinished evaluation work. They are not demonstrated incorrect live performance reports.

### E1 — Replay is scheduled only at candle close

`quantitative.py:901–947` evaluates at `candle_close(row)` and excludes later-available candles. It never schedules evaluation when a normal delayed observation arrives between closes.

For both GOLD_FAST and BTC_FAST, delaying the final valid fixture candle until close +1 second gives a direct `CANDIDATE` at that receipt time, while the existing finite replay returns only WAIT for insufficient history. Keep the availability filter; fix the scheduler. Replaying as observed must follow availability/persistence and the actual evaluation schedule while retaining separate exchange event time.

### E2 — The old outcome helper does not establish valid entry, instrument or path coverage

`backtesting.py:17–59` is unchanged by Phase 3. Both bullish and bearish probes produce:

| Hypothetical input | Current result | Why it is unproven |
|---|---|---|
| Expiry 00:30; aligned 1h candle 00:00–01:00 contains a target | TARGET | Hit may occur after expiry |
| Only 00:29–00:30 is supplied; preceding 29 minutes missing | EXPIRED | Missing path may contain stop/target |
| Gold candidate evaluated using a BTC candle | TARGET | Instrument identity is unchecked |
| Candidate observed at 00:00:40; whole 00:00–00:01 bar contains target | TARGET | Hit may predate observation/entry |

Replace or harden this helper before using it in an evaluator. Validate instrument, actual entry eligibility/time, interval bounds, complete path coverage and ordering before assigning an outcome. Partial entry/expiry bars require finer observations or an explicit ambiguous/incomplete result. AI review latency must not receive a retroactive candle-close fill.

## Required next implementation

Follow [CODEX_PHASE_4.md](../../prompts/CODEX_PHASE_4.md): correct P3-01 through P3-10 and the recovery/deadline gates first; then implement a versioned dataset manifest, as-observed replay, conservative outcomes/costs, fair rules/GPT/Claude/dual comparisons, time-ordered validation, prospective paper records and honest reports.

Completion of the software and fixtures must be reported separately from collected real observations and measured out-of-sample results. Missing historical trades/books, CoinGlass history or actual model decisions must remain missing. No made-up data, backdated approvals, live orders, or claim of profitable double confirmation belongs in the next milestone.
