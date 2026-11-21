# Codex Phase 3 — corrections, independent AI review, and hardened service

Repository: **https://github.com/Rameshdandu1/gold_bitcoin**

This is an implementation task. Read the instructions, establish the baseline, then implement tested vertical slices. Do not stop after producing a plan. Do not enable paid services, send messages, deploy to the Windows host, or introduce trading during this development task.

## 0. First instructions: establish the correct foundation

1. Read `AGENTS.md`, `DESIGN.md`, `README.md`, `docs/IMPLEMENTATION_PLAN.md`, then `docs/audits/phase-2-independent-review.md`, this file, and the relevant code/tests. Follow existing repository rules; keep the application in this repository.
2. Inspect `git status`, branch, remotes, and recent commits before editing. Preserve unrelated work. Fetch current refs; do not reset or force-push shared history.
3. Phase 2 was reviewed at `10b3e9118448b55db80c94ae91cee7e227a64932` after PR #2 merged. Verify current state rather than assuming it remains unchanged. Reassess any finding already fixed on newer main; do not recreate obsolete defects.
4. Create `feature/phase-3-dual-ai-confirmation` from updated main. If this instruction/report exists only on `docs/phase-3-review-and-instructions`, read it with `git show origin/docs/phase-3-review-and-instructions:prompts/CODEX_PHASE_3.md` and read the report the same way. Copy those two documentation files into the feature branch if main lacks them; do not merge other pending feature branches automatically. Record the actual code and instruction SHAs.
5. Run the baseline tests/checks and record results. The independently reviewed baseline was 126 passing Python tests plus Ruff, compilation, TypeScript checking, and frontend build. Treat that as an observation, not a required test-count ceiling.
6. Write a short implementation plan and the proposed migrations/ADRs. Reproduce the review findings with targeted tests, then implement **3A first**. A provider adapter may be developed against fixtures in parallel, but no live confirmation path can be enabled before the correctness prerequisites pass.

## 1. Outcome and boundaries

Deliver an auditable dual-provider review pipeline for the six existing Gold/BTC engines, plus accurate operator views, authentication, Windows run instructions, and a durable alert outbox.

The quantitative engine owns entry, invalidation, targets, trigger, horizon, and evidence. GPT and Claude independently evaluate that fixed proposal. A deterministic gate decides whether the two valid approvals still apply to the current active candidate and market. `CONFIRMED` means the configured review checks passed; it does not mean an order, calibrated probability, guaranteed move, or measured profitable strategy.

Keep native Windows Server support, Python/FastAPI, React/TypeScript, and the existing single-host SQLite architecture. Use a durable SQLite job/outbox design with short transactions and explicit busy/lease behavior. Do not add Redis, Kafka, Docker, a new database, or paid infrastructure without a measured need and a documented approved architecture change.

Defaults remain `LIVE_INGESTION_ENABLED=false`, `AI_ENABLED=false`, `TRADING_ENABLED=false`. Add `ALERTS_ENABLED=false`. Continue rejecting `TRADING_ENABLED=true`. Public Delta market data requires no trading credentials. No order endpoints, leverage, options execution, account positions, or trading SDK permissions belong in this phase.

Two required end-to-end examples, using visibly hypothetical fixtures:

- Gold: a valid bullish proposal, both providers approve the same eligible target, and current deterministic checks pass -> one revision-scoped `CONFIRMED` decision and one notification intent.
- BTC: GPT approves but Claude times out, or the price invalidates the candidate while both are running -> `WAIT` or an authoritative terminal lifecycle state, with no confirmation alert.

## 2. Slice 3A — correct the Phase 2 findings

Use the independent review's R1–R6 and C1–C3 identifiers in tests and the delivery report. Do not weaken thresholds or rewrite fixtures solely to make failing behavior pass.

### 2.1 Session coverage and structural event identity

- Separate short trigger lookback from complete UTC-session, previous-day, and higher-timeframe history. Update both worker acquisition and feature construction; removing the `min_candles` crop alone is insufficient.
- Define required coverage, source/availability times, UTC boundaries, and gap treatment. Query or accumulate enough history using currently documented Delta limits. Partial history must yield a coverage warning/unavailable feature, never a falsely complete daily extreme or VWAP.
- Keep required/optional feature policy explicit per engine. If an engine's admission rule requires session VWAP or opposing levels, insufficient coverage blocks that rule. Do not substitute a rolling-window metric under the same label.
- Calculate structure chronologically. Persist/derive the first time a confirmed pivot breaks. Repeated closes beyond the same pivot are not new BOS/CHOCH events. Define separate identity and rearm conditions if continuation signals are intentionally supported.
- Bump rule/schema versions where changed semantics affect replay or candidate identity. Preserve old records as old-version evidence.

Regression examples: the bullish 2,608 Gold entry with a previously observed session high of 2,615 must not emit 20/30-dollar targets under the existing room policy; the bearish 2,592 entry with a known low of 2,585 must be treated symmetrically. Staying above one broken pivot for three bars must create one first-break event; breaking a newly confirmed pivot may create another.

### 2.2 Availability, raw observations, and discovery health

- At the shared detector/feature boundary, require each candle to be closed and actually available by the decision clock. Define handling of unknown availability; a historical row is not automatically known at its close.
- Resampled availability is the latest factual availability of its constituents. Missing buckets remain missing. Preserve event time, receive time, and response availability; reject impossible future timestamps under a documented clock-skew policy consistently across real books and test overrides.
- Journal REST candle response/normalized observations with source, request bounds, response availability, and version/digest. Preserve revisions instead of backdating a later revised candle. Do not claim history exists before collection without an attributed provider source.
- Define the REST/stream reconciliation prerequisite and required overlap/completeness. A required `INVALID`, missing, or stale check blocks admission/review. Warmup must not deadlock permanently, but unknown reconciliation cannot be represented as verified.
- Distinguish status-transition time, last successful verification, and heartbeat. Keep last error and degraded discovery state accurate. Define maximum age for cached verified instrument metadata; allow raw collection during an outage only if the documented policy permits it, and separately gate new candidates.

Regression examples: direct GOLD_FAST/BTC_FAST evaluation must reject candles available tomorrow; a successful discovery followed by a refresh outage must prevent admissions once the allowed metadata age is exceeded. Also test startup with no verified instrument and recovery after a fresh valid discovery.

### 2.3 Price invalidation and current lifecycle

- Define whether each rule uses executed trades, bid/ask, or a conservative combination. Record its price source and policy version. Closed candles remain appropriate for triggers; they are insufficient as the only live invalidation monitor.
- Process relevant post-observation price events from a durable watermark. Do not rely only on the most recent trade or a bounded tail that might omit an earlier breach. Catch up after restart; on an unfillable gap fail closed and preserve an explicit reason.
- A breach followed by recovery does not resurrect the candidate. Reject new admissions whose current market is already beyond invalidation or whose setup is exhausted under the configured price policy.
- Keep irreversible terminal transitions atomic. Handle expiry at `now >= expires_at_utc`. Distinguish ambiguous stop/target ordering from a successful outcome; this phase is not a performance-labelling shortcut.
- Return current lifecycle and terminal reason/time separately from the immutable creation packet. Use that read model in the dashboard.

Regression examples: BTC bullish stop 69,000 with a later trade at 68,999 must invalidate even if the closed candle is 70,251; Gold bearish stop 2,605 with a trade at 2,606 followed by 2,600 must remain invalidated. The API/UI must display the terminal state for both.

**3A exit gate:** the reproduced defects have meaningful regression coverage; legacy tests and replay still pass or are updated with a documented intentional rule-version change. No live AI or alert path has been enabled.

## 3. Slice 3B — canonical evidence and durable review contracts

### 3.1 One complete, immutable input

Introduce a versioned `AnalysisEnvelope` (name may follow existing conventions) containing:

- Exact candidate ID, candidate revision ID, feature snapshot ID, engine/rule/schema versions, asset, verified instrument/venue, horizon and direction.
- Frozen entry, invalidation, target array and explicit price/unit meaning. Use `Decimal` or canonical decimal strings for decision boundaries; reject non-finite values. Target indices remain **1-based, from 1 to N**, referring to this exact frozen array.
- Full relevant `FeatureSnapshot`: structure/levels, coverage, ATR/volume measures, 500/5,000 and duration flow windows, book quality/spread/depth, and external metrics with source, units, venue coverage, entitlement and freshness.
- Decision/observation times, source event/receive/availability times, expiry, warnings, and an explicit required-versus-optional context policy. Include all request-time gate evidence; no summary-only packet. New quote/lifecycle evidence read after the reviews belongs in a separate risk-check/decision record and must not mutate or rehash the approved request envelope.
- Prompt version, analysis schema version, risk-policy version, and the evaluation configuration needed to reproduce the request.

Use deeply immutable nested values. Serialize the shared analyst input once with a tested canonical encoder: stable field order, UTC representation, deterministic decimal representation, bounded arrays, no NaN/Infinity. Keep the digest outside its own hash preimage. Persist the exact canonical bytes and digest; both adapters consume those same bytes. Provider-specific API wrappers may differ, but market evidence and instructions must be equivalent, and neither model may see the other's response.

Do not silently reuse the old feature snapshot hash as a digest of a different layout. Preserve old schema records and introduce a migration/compatibility boundary. On duplicate digest/revision keys, compare bytes and reject conflicting content instead of silently ignoring it.

Examples: reordering object keys must not change the canonical digest; modifying a target, coverage flag, or source timestamp must change the relevant immutable revision/digest. No nested-list mutation may alter a packet after scheduling.

### 3.2 Append-only runs, attempts, decisions, and migrations

Add typed storage and additive, versioned migrations for:

| Record | Required identity and purpose |
|---|---|
| Analysis envelope | Exact canonical bytes, digest, schema and provenance |
| Review job/run | Candidate/revision/envelope digest plus prompt, schema, risk-policy, provider/model and parameter configuration |
| Provider attempt | Run, provider, attempt number, lease/dispatch identity, request/response metadata, outcome and usage |
| Consensus decision | Run/revision identity, both attempt references, explicit validation results and current risk-check evidence |
| Budget ledger | Atomic reservations, dispatch attempts, token/estimated-cost accounting and reconciliation |
| Notification outbox | Decision/event, destination identity, stable delivery key, attempt/receipt state |

Use a bounded durable job queue. Atomically claim jobs with lease owner, expiry and fencing/generation checks; a stale worker must not commit results after losing its lease. Recover abandoned jobs after restart without automatically replaying an uncertain paid request. Record dispatch-unknown outcomes explicitly and apply a documented bounded retry policy; provider billing cannot be made exactly-once by a local database.

Do not keep a database transaction open during HTTP calls. Protect concurrent reservations/claims and decision commits with SQLite-compatible transactions/uniqueness constraints. Make active revision selection explicit rather than relying on arbitrary hash ordering when timestamps tie. Preserve immutable history and provide a separate current projection.

Examples: two workers claiming one job result in one permitted claim/dispatch identity; approval of revision A must never appear as approval of revision B. Test migration of a database containing old candidate/provider/decision rows and reopening it without loss or duplicate migrations.

## 4. Slice 3C — independent GPT and Claude adapters

### 4.1 Structured, bounded output and trustworthy metadata

Extend the existing adapters rather than adding competing integration stacks. Inspect the installed SDK/API contract before changing calls. Use OpenAI Responses structured parsing and Claude Messages structured parsing where supported by the configured models. Model IDs remain environment/configuration values: `OPENAI_MODEL`, `ANTHROPIC_MODEL`. Do not invent a model ID, assume account access, or switch models silently.

Define a strict `AnalystAssessmentV2` with at least:

| Model-authored field | Validation |
|---|---|
| `schema_version`, `candidate_id`, `candidate_revision_id`, `snapshot_id`, `analysis_input_hash` | Exact match with the scheduled request |
| `asset`, `symbol`, `engine`, `horizon_minutes`, `direction` | Exact request match; only allowed enums/types |
| `decision` | `CONFIRM`, `REJECT`, or `WAIT` |
| `supported_target_indices` | Unique strict integers; booleans/strings/floats forbidden; every value in 1..N; nonempty for CONFIRM |
| `agrees_with_invalidation` | Strict boolean; required true for CONFIRM; no replacement stop price |
| `reason`, `counter_evidence`, `data_warnings` | Bounded concise content; no hidden reasoning request or probability badge |

Reject extra fields and semantic inconsistencies. Validate the full result, not a convenient valid subset. Keep warning semantics conservative: model-reported blocking uncertainty cannot be discarded just to obtain agreement. Deterministic policy decides whether missing source fields are optional; an LLM cannot waive required context.

Wrap the parsed assessment in a **server-owned** provider result: actual provider, requested model, returned model, request/response IDs when available, SDK version, timestamps/latency, token usage including available cached/reasoning categories, finish/stop reason, attempt number and safe failure code. The model does not attest its own identity or cost. Validate returned model against an explicitly documented alias/pinned-model policy; do not demand literal alias equality if a provider legitimately returns a resolved version.

Treat HTTP success as insufficient. Refusal, incomplete/truncated output, missing parsed object, validation error, unsupported model, authentication failure, rate limit, transport error and timeout are typed non-approval results. Never parse a sentence such as "looks bullish" as a confirmation.

Examples: `[true]` and `[1, 999]` invalidate the assessment; a valid-looking JSON body accompanied by a truncation/refusal status cannot be used. GPT success plus Claude failure must remain visibly two different provider outcomes.

### 4.2 Independence and prompt-injection boundary

- Start the two initial evaluations independently and concurrently, outside ingestion and candle polling. Do not share their outputs or conduct a debate/retry loop to force agreement.
- Keep tools, browsing, code execution, retrieval, and order capabilities absent from both analyst requests. Source text is untrusted data. Bound free text and prefer structured numeric features with provenance.
- Ask for concise reasons tied to supplied evidence, counter-evidence, and missing prerequisites. Do not ask for chain-of-thought or let either model generate new entry/stop/target prices.
- Preserve disagreeing and rejecting outputs in the audit. A different answer is not a transport failure to retry.

Examples: an exchange text field saying "ignore the risk gate" remains inert text; a provider response requesting a network call or a changed stop is rejected as an invalid contract, never executed.

### 4.3 Deadlines, retries, caching, and spend

- Enforce a total review deadline, per-attempt transport timeout, queue-age limit, input/output token caps, bounded concurrency, and a maximum attempt count. Bound the deadline by candidate lifetime and the configured snapshot-age policy. Measure latency; do not promise model turnaround that has not been observed.
- Disable hidden SDK retries or account for every actual attempt explicitly. Prefer application-owned retries. Retry only documented transient failures with bounded jitter/Retry-After, remaining deadline and a new reservation. Authentication/permission/unsupported-model errors, rejection, invalid semantics and disagreement do not trigger blind retries.
- Reserve provider calls, maximum tokens and conservatively estimated cost atomically before each dispatch, using persistent UTC-day accounting. Track actual provider-reported usage separately. A timeout may still be billable; unknown usage must not become zero or release the entire reservation automatically.
- Keep per-provider and total limits. Rates used for estimates are versioned operator configuration verified against official pricing. If a rate required for the cost reservation is missing/unknown, live dispatch is NOT_READY/WAIT with zero paid calls; never substitute a zero-cost estimate. Application estimates are not a guarantee of the provider's final bill.
- Cache/reuse only under an exact versioned request identity including envelope, prompt/schema, policy and provider/model parameters. Revalidate current eligibility even for a cache hit. Time-dependent data, changed revisions, or changed models cannot inherit approval. Do not repeatedly submit an unchanged REJECT/WAIT hoping for a different answer.
- Avoid a new review for timestamp-only refreshes with no material new evidence. Define how material-change detection creates a new revision/job while preserving provenance; do not defeat caching by changing a clock field every poll or copy old approval onto a changed hash.

Examples: with one remaining call reservation, two concurrent workers cannot both dispatch; if the retry delay exceeds the remaining candidate deadline, record WAIT without another paid request. A crashed request with unknown completion remains auditable and counted conservatively.

## 5. Slice 3D — consensus plus current deterministic eligibility

Keep candidate lifecycle, provider job state, and consensus status separate. `CandidateSignal.not_ai_confirmed=True` remains a statement about the creation packet; a separate decision records later review. A historical confirmation can coexist with a later terminal lifecycle event, but the current UI/alert eligibility must honor that terminal state.

### 5.1 Decision rules

Validate both server-owned results before combining opinions. Require one OpenAI result and one Anthropic result from the expected run, exact revision/envelope, allowed model configuration, completed status, deadline and strict schema.

| Condition | Current result |
|---|---|
| Either result absent, invalid, late, refused, truncated or unavailable | `WAIT`, with typed reasons |
| Valid results contain a rejection | `REJECTED`; preserve both outputs; never confirm |
| Both valid but either requests WAIT, direction differs, invalidation is not accepted, or target intersection is empty | `WAIT` |
| Both valid CONFIRM with matching direction/invalidation and shared targets | Eligible for deterministic risk recheck only |
| Candidate expired, invalidated, superseded, or required source/gate failed | No new confirmation; expose authoritative state and failed checks |
| Both approvals and all current deterministic checks pass atomically | Revision-scoped `CONFIRMED` decision plus outbox intent |

If one provider is unavailable while the other rejects, retain the rejection evidence while the incomplete-review status remains WAIT; document this precedence consistently. A valid non-approval must never be turned into approval.

### 5.2 Recheck immediately before committing

Require all of the following, with typed reason codes and recorded gate inputs:

- Candidate is still the active revision, unexpired (`now < expires_at_utc`), and not invalidated/superseded. Observation/availability times cannot be in the future; snapshot age remains acceptable.
- Required instrument/discovery/reconciliation state, executed-trade stream and sequence/checksum-valid book are current. A source warning from optional CoinGlass or XAU is distinct from a failed required feed.
- No disqualifying stop/target crossing has occurred since observation; current quote has not moved outside the configured entry tolerance. Define exhausted-target handling; do not advertise a target as an upcoming opportunity after it was already reached.
- Use fresh ask for a hypothetical long entry and fresh bid for a hypothetical short entry; use the documented opposing side and configured cost assumptions for exit feasibility. Recompute risk and eligible reward using consistent instrument units, tick rounding, spread, fees and slippage assumptions. If required cost assumptions are unknown, keep actionable confirmation unavailable rather than report fabricated net reward/risk.
- At least one target approved by both providers remains feasible after deterministic filtering. Preserve original target identities/indices; do not reindex the frozen array after filtering. Rejection of one target must not silently count as approval of another.
- Calendar/session/market-status restrictions are enforced only from verified data or an explicit token-market-only policy. Missing required event-calendar data is UNKNOWN, not "no events". No new paid macro dependency is assumed.

Read a current eligibility generation/event watermark and commit using an atomic conditional check against it. The same transaction records the decision and notification intent. If lifecycle/revision/quality changes during the commit race, fail/re-evaluate instead of publishing stale approval. Do not imply that this eliminates all market movement between an observation and a human reading an alert; retain timestamps and expiry.

Examples: both models approve Gold, but a recorded stop breach arrives before commit -> no confirmation; both approve BTC, but a fresh wider spread makes all shared targets fail the configured cost-adjusted rule -> WAIT. Add the positive case with unchanged valid inputs so a correct implementation can actually confirm.

## 6. Slice 3E — accurate API/UI, alerts, and Windows operation

### 6.1 Read models and operator view

- Extend existing API endpoints compatibly or version their schemas. Expose current lifecycle/reason/time, exact candidate revision, provider run/attempt states, actual model metadata, consensus/gate outcomes, freshness and spend. Paginate histories and bound payloads.
- Render six engine cards from actual backend data. GPT and Claude status comes from their own attempt records, never inferred from a non-null consensus. Separate configured, disabled, not-ready, running, unavailable, refused, and valid assessment states.
- Display market observation time, worker heartbeat, source verification age, review completion time and expiry separately. Default display timezone remains Asia/Kolkata, with UTC in storage/API.
- Keep entry/stop/target units and tokenized-gold qualification visible. Avoid calibrated-looking confidence percentages and performance cards without measured outcomes.
- Keep errors/loading/empty states and render provider text as escaped content. Do not expose secrets or unnecessarily redistribute licensed CoinGlass data through public endpoints.

Examples: GPT CONFIRM plus Claude TIMEOUT shows those exact cards and overall WAIT; an old confirmation followed by INVALIDATED shows that it is no longer active, while the historical review remains inspectable.

### 6.2 Durable notifications

- Implement an outbox and one operator-configured channel adapter first (Telegram or Slack, per project backlog); document the choice. Keep a provider interface for the other channel. A usable, tested first channel is required; a placeholder claiming both work is not.
- Decision and outbox intent commit together with a stable uniqueness key tied to decision/revision/event and destination. Notification workers use bounded attempts/backoff and durable receipts; they do not hold market-data locks.
- Revalidate active state/expiry before delivery. Suppress obsolete confirmation alerts; issue separately identified invalidation/expiry events where policy requires. An alert includes symbol/venue, direction, horizon, immutable target identities, entry/invalidation, source/review times, expiry and the research-only meaning of confirmation.
- Persist ambiguous delivery: a crash after remote acceptance but before local receipt can lead to uncertainty. Use destination idempotency when actually supported; do not promise exactly-once external delivery universally. Prevent repeated local intents and uncontrolled resend loops.
- Default alerts off. Fixtures and fake HTTP transports only in CI. Do not send test messages to real people during implementation. Live delivery requires the operator's explicit channel/destination authorization and locally configured secrets.

Examples: restart after decision commit schedules no second intent; an expired candidate is suppressed when the outbox worker resumes. Test a crash after provider acceptance and record the uncertain receipt honestly.

### 6.3 Authentication and Windows runbook

- Choose a concrete authentication approach suitable for a single-operator native Windows deployment and document the threat boundary. Protect dashboard/API/docs/OpenAPI before external exposure. Keep only a minimal non-sensitive liveness endpoint unauthenticated if needed.
- Bind the backend to loopback by default; document HTTPS reverse proxy, exact trusted proxy rules, restricted CORS and firewall access. Do not trust client-supplied identity headers unless a configured authenticated proxy is the sole permitted ingress.
- Secrets remain environment/secret-manager values, absent from URLs, logs, frontend bundles and committed fixtures. If browser sessions are used, handle secure HttpOnly cookies and CSRF appropriately; do not hardcode a long-lived admin token into the frontend build.
- Add readiness checks separate from liveness: configuration, database/migration health, worker heartbeat, required data, provider configuration, queue/backlog and budget state. Readiness must not make a paid AI call on every probe.
- Provide tested PowerShell startup/shutdown/check commands; document service/Task Scheduler installation, least-privilege identity, bounded restart backoff, log rotation, time synchronization, database backup/restore and migration rollback/recovery. Actual Windows service installation remains unverified until executed on a Windows host.
- Restore a copied fixture database in tests and verify revisions, active jobs, ledger and outbox integrity. Retention/backup must respect existing append-only constraints; do not casually delete audit rows or promise unmeasured tick-storage capacity.

Examples: an unauthenticated remote API/docs request fails while an authorized request succeeds; after worker restart the lease expires/reclaims safely and a committed notification intent is not duplicated.

## 7. Required verification matrix

Use deterministic clocks and fake provider transports. Add tests for observable business guarantees and races, not tests that merely restate helper implementation.

| Area | Minimum positive and negative coverage |
|---|---|
| Phase 2 corrections | R1–R6 counterexamples; complete/incomplete session history; first/new pivot; late availability; breach/recovery; discovery degraded state; lifecycle presentation |
| Canonical evidence | Byte-stable replay/restart; same exact packet to both adapters; changed evidence changes identity; nested mutation prevented; conflicting digest payload rejected |
| Review identity | A approval cannot attach to B; returned provider/model validation; one provider cannot occupy both slots; old worker lease cannot commit |
| Structured output | Valid approvals; wrong snapshot/revision/asset/direction; boolean/string/float/out-of-range/duplicate indices; extra fields; missing invalidation agreement; bounded text |
| Provider failures | Timeout, transport error, 401/403, 429 with Retry-After, 5xx, refusal, truncation, missing parsed object, unsupported model; all fail closed with typed diagnostics |
| Independence | Calls overlap without blocking ingestion; neither sees the other's output; reject/disagreement does not trigger answer-shopping |
| Time and price | Future observation/availability; expiry equality; deadline exceeded; price drift; stop breach and recovery; exhausted target; ambiguous event order; stale/gapped/corrupt book |
| Budgets and jobs | Concurrent claims/reservations, retry accounting, UTC-day boundary, token/cost caps, crash before/after dispatch, unknown usage, stale leases and restart recovery |
| Commit race | Candidate invalidated or superseded after request start and immediately before commit; no stale confirmation/outbox intent; valid unchanged path succeeds |
| Delivery | Intent uniqueness, restart, transient failure, expired-before-send, accepted-but-receipt-unknown, invalidation notification identity |
| Service/UI | Auth success/failure including docs, restricted CORS, escaped untrusted text, real per-provider statuses, accurate current lifecycle and freshness, no secrets in logs |
| Migration/Windows | Existing 0.2 database upgrade and repeat startup, restored backup integrity; Windows CI command path; installation/soak explicitly separate if not run |

Keep live smoke tests separately marked, disabled by default, and bounded by an explicit paid-call limit. Credentials alone are not permission to run an unbounded test. Record factual provider model/response metadata if an operator later authorizes a live smoke test. CI must complete without paid keys or an external market connection.

Run and report exact results:

```powershell
python -m pytest -q
python -m ruff check .
python -m ruff format --check .
python -m compileall -q src tests
git diff --check
cd frontend
npm ci
npm run typecheck
npm run build
```

Keep SDK/dependency changes narrow and reproducible; add a compatible lock/constraints mechanism if needed for the tested deployment path. Do not upgrade unrelated dependencies merely because newer versions exist.

## 8. Delivery and definition of done

Work in reviewable commits for 3A, 3B, 3C, 3D and 3E. If separate PRs are used, document their dependency order; keep the shared live path disabled until its required slices are integrated. Do not claim all of M3 is complete after adapter-only work.

Update `README.md`, `DESIGN.md`, `docs/IMPLEMENTATION_PLAN.md`, `docs/API.md`, `docs/SECURITY.md`, `docs/WINDOWS_DEPLOYMENT.md`, `.env.example`, `CHANGELOG.md`, versions where appropriate, and ADRs for canonical input, persistence and authentication decisions. Amend `AGENTS.md` only when an actual rule change is necessary; do not weaken it to bypass a failing gate.

Create `docs/audits/phase-3-verification.md` with:

1. Starting and final commit/branch, baseline and final check results.
2. Each review finding marked fixed/remaining with regression evidence and intentional rule-version changes.
3. A Gold and a BTC end-to-end fixture example, both labelled hypothetical; include approval and failure/terminal paths.
4. Canonical envelope/run/attempt/decision identity examples; migration and concurrent-worker results.
5. Paid-call counts actually made, models actually contacted, and explicitly unverified integrations. Zero paid calls is an acceptable development result; do not invent successes.
6. Auth/deployment approach, measured queue/latency observations if tested, Windows checks actually executed, and remaining live soak/credential requirements.
7. Known limits: CoinGlass entitlement/coverage, unavailable licensed Gold macro/reference data, no calibrated strategy performance, no execution.

Push the feature branch and create a PR targeting the verified foundation. Do not auto-merge or deploy. The PR must state the problem, changes, resulting behavior, tests, migrations, configuration, costs and remaining limits. Keep the full implementation in files and provide a substantive handoff, not only a list of filenames.

Phase 4 remains time-ordered historical evaluation and paper trading: compare rules-only, GPT-only, Claude-only and dual agreement net of costs with sample sizes and uncertainty. Agreement is a gate to study, not evidence of independent predictive errors or a guaranteed advantage.

## 9. Primary API references

Reviewed on 2026-11-21; recheck the installed SDK and current official docs when implementing:

- [OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs): structured parsing still requires handling refusals/incomplete responses and application business rules.
- [Claude Structured Outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs): the Python `messages.parse(..., output_format=...)` helper validates parsed output; refusal or token-limit termination requires explicit handling.
- [Delta Exchange documentation](https://docs.delta.exchange/): verify India endpoints, product metadata, channel/time semantics, and historical-candle limits before changing acquisition.
- [CoinGlass documentation](https://docs.coinglass.com/reference/getting-started-with-your-api): actual plan access, supported instruments, refresh intervals, usage and redistribution conditions must be verified separately with the operator's subscription.

**Start with the branch/baseline checks and the first failing R1/R2 regression. Implement 3A before connecting any live dual-AI confirmation path.**
