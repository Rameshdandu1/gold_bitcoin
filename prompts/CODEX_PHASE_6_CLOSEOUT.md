# CODEX TASK — Phase 6 closeout, then controlled operational validation

## Objective and fixed scope

Complete the existing Phase 6 requirements before beginning operational validation. Correct **P6-01 through P6-05** in the [independent Phase 6 review](../docs/audits/phase-6-independent-review.md), preserve the independently verified controls, and finish the three already-open software gates: full shared policy, durable derived-workflow resume and bounded total memory.

This is a closeout task for the current Gold/BTC analysis application. Do not add derivatives, execution, new indicators, a different database/stack or unrelated UI features. After closeout, the next stages are controlled Windows/live integration validation and prospective paper observation. They are distinct from more feature development.

## 1. First instructions

1. Inspect `git status`, branch, remotes and recent commits. Preserve unrelated work. Read `AGENTS.md`, `DESIGN.md`, `README.md`, `docs/IMPLEMENTATION_PLAN.md`, `docs/audits/phase-6-independent-review.md`, this file and relevant source/tests. `prompts/CODEX_PHASE_6.md` remains the governing acceptance specification; this task supplies exact remaining cases.
2. Fetch current main. The reviewed implementation is **`f66ac11f4d958a0075d7e22a5d841256e19b55df`**, merged PR #10. Compare any newer changes before treating a finding as open.
3. If the review/instructions have not merged, fetch them explicitly:

   ```bash
   git fetch origin refs/heads/docs/phase-6-closeout-and-validation:refs/remotes/origin/docs/phase-6-closeout-and-validation
   git show origin/docs/phase-6-closeout-and-validation:prompts/CODEX_PHASE_6_CLOSEOUT.md
   git show origin/docs/phase-6-closeout-and-validation:docs/audits/phase-6-independent-review.md
   ```

4. Create `feature/phase-6-closeout` from current main; use an isolated worktree if needed. Carry relevant instruction/review documents when absent from main. Do not reset another branch or merge unrelated changes.
5. Record starting code/instruction SHAs. Reproduce the **237-test** baseline, lint/format/compile and frontend checks. Reproduce the five remaining finding groups with maintainable tests before fixes. Use the exact anchored-gap and conflicting-payload examples: a different negative test that passes does not close them.
6. Make reviewable commits in the work-package order below. Continue until the authorized offline work is complete. Push and open PRs; do not auto-merge or deploy.

The initial deliverable is a short baseline/disposition matrix and failing regressions tied to the review. Do not spend that milestone on redesign or another generic architecture document.

## 2. Coding and evidence rules

- Preserve native Windows Server, Python/FastAPI, React/TypeScript and isolated SQLite research/paper storage. Keep the six Gold/BTC horizon engines and existing strategy thresholds.
- Live ingestion, AI, alerts and real paper collection remain off by default. `TRADING_ENABLED=true` remains rejected. No order/account/leverage/trading-key functionality.
- Use UTC-aware clocks, typed boundary contracts and `Decimal` for monetary decisions. Separate exchange time, receipt/availability, provider completion, database persistence and simulated readiness/fill time.
- Treat the outer accepted journal record as the factual receipt boundary. Inner payloads must not override identity, clocks or evidence classification. Validate conflicts rather than silently selecting whichever representation produces an earlier signal.
- Derive risk validity and authorization deadlines from shared predicates. A second handwritten approximation of freshness can disagree even when both use a fresh clock.
- Preserve immutable scientific identities. An identical retry keeps original evidence/timestamps; conflicting content fails. Add versioned contracts/migrations for changed persisted data, and retain prior results as historical evidence.
- Keep network I/O outside short database transactions. Inject advancing clocks and transports. Preserve leased ownership, uncertain remote-delivery recovery and destination binding; do not promise external exactly-once delivery.
- Use one shared application path for applicable admission, revision, lifecycle and market-risk logic. Separate output transport configuration from market eligibility so a simulator does not require real notification credentials.
- Keep explicit synthetic, retrospective, recorded and genuinely prospective provenance. Archive actual requested/returned model identity when present; do not invent it for old recordings. Unknown model evidence must remain unavailable or explicitly exploratory for model-specific studies.
- Preserve the denominator: unknown evidence is not a zero-P&L abstention; a known no-position decision is not an executed trade. Completion of processing is not proof of complete market evidence.
- Regression expectations must follow specified independent facts and hand calculations. Never compute the expected answer by calling the same production helper again. Do not weaken existing assertions to retain a test count.
- No secrets in source, logs, fixtures, exports or frontend. No paid requests, real messages or live deployment are needed to finish the offline closeout. Preserve already-established authorization for later bounded integration work; do not infer approval for orders or unrestricted spend.

## 3. Work package A — correct clock and coverage boundaries

### P6-01: authorization freshness

Unify the deadline calculation with the actual source/book validity policy. For the current book, include `last_event_time_utc + max_age_seconds`; retain receipt-age constraints if independently required. Take the earliest applicable expiry across candidate, lease and source validity. Use current time after acquiring the authorization transaction and preserve evidence/cutoff alignment.

Mandatory examples:

1. Book event 10:00:51, receipt 10:00:59.900, evaluation 10:01:00, max age 10 seconds, authorization 10:01:02: zero sends and no valid confirmation authorization. The event-time deadline has passed even though receipt age is small.
2. Healthy 600-millisecond processing delay: retain one authorized fake send with actual later authorization time. Retain the original stop-arrival, expiry and elapsed-lease suppressions.

Use the actual parser/assembler/current-risk/store/worker path. A hand-constructed fake eligibility object alone cannot prove policy agreement.

### P6-02: authoritative observation clocks

Normalize quote/provider clocks against the enclosing accepted observation. Reject conflicts or adopt a documented conservative rule that cannot make actionable evidence earlier than the authoritative receipt boundary. Apply the same contract on journal ingestion, projection, replay and paper reads; do not leave a permissive alternate path. Preserve event/completion clocks as distinct facts.

Mandatory examples:

1. Provider envelope availability +120 seconds with an explicit original payload availability: validation must reject it or all resulting readiness/entries must obey the later accepted boundary.
2. Quote envelope availability +120 seconds with an explicit original payload availability: the original +4-second fill must disappear or the record must be rejected.

Retain the passing omitted-field fallback and synthetic/prospective conflict controls. Include requested/returned model identity and provenance where supported; label unknown historical identity accurately. Bind changes into versioned experiment/evaluator configuration rather than rewriting old outputs.

### P6-03: complete pre-entry evidence

Track the last valid market observation through the first eligible entry quote. Readiness cannot replace a missing interval. Validate OHLC completeness before using any bar to advance coverage, including pre-entry bars. Preserve source continuity/sequence/age rules for sparse valid book updates and keep ambiguous ordering explicit.

Mandatory examples in both directions:

1. Neutral quote at +0, readiness and next quote at +150, target +155, maximum gap 10: `INCOMPLETE`, not a completed target. Include explicit quote availability fields.
2. `complete=False` neutral bar +0 to +30, readiness +30, complete target bar +30 to +40: cannot yield complete coverage/target. Keep the OHLC helper distinction explicit.

Retain continuous long/short arithmetic controls, missing-anchor/isolation controls, partial bars, expiry equality, known pre-entry stops and post-entry gaps.

**Package A gate:** the exact formerly failing cases are red before and green after the changes; the new healthy/recovery controls remain green; public workflows enforce the normalized contracts.

## 4. Work package B — protect derived data and terminal paper states

### P6-04: holdout policy through paper derivation

The normal research projection is now protected. Extend its policy across derived paper data rather than introducing a second definition of holdout access.

1. Bind derived paper records to experiment, frozen configuration, dataset/partition and originating opportunity/revision. Add a migration or conservative treatment for previously derived rows that lack sufficient provenance.
2. Before final access, block protected derivation/exposure or project it without outcome-bearing information. Apply the decision to paper transitions, outcomes, counts/filters and exports as well as UI/API detail. Authentication alone does not open a research holdout.
3. The explicit final access must be durably recorded before revealing protected results. After access, mark it opened and preserve the original identity. Existing protected rows must not become visible simply because an unrelated experiment was opened.

Mandatory examples:

- A valid experiment whose holdout starts at candidate time: normal opportunities remain hidden, and running the paper command cannot expose its 12 target transitions with zero access records.
- After the deliberate final action, the same eligible stored results become visible with their recorded opened state. Development records remain accessible normally; unauthenticated endpoints remain protected.

Test actual API/export bytes and separate paper databases. Cover a label that crosses the boundary as well as one observed inside holdout.

### P6-05: unavailable/expired decisions and truthful progress

1. Define explicit terminal unavailable/expired/no-position dispositions that can be recorded when their factual resolution occurs. They must not be forced through the same entry-eligible write rule as an approved candidate.
2. Keep approved prospective entry strictly after its durable decision and before permitted expiry. Do not backdate writes, extend expiry or fabricate missing model output to make a negative path pass.
3. Preserve all four arms and common-opportunity denominators. One unavailable provider produces an auditable unavailable/WAIT disposition as appropriate, not an application exception or invented execution.
4. Scope connected-run identity and progress to experiment/configuration, including effective processing/entry policy. Distinguish input completion, warmup/no decisions, bounded partial processing, pending arms and unresolved evidence. Zero decisions equalling zero outcomes is insufficient for full completion.
5. Ensure restart converges without duplicated entries or repeated terminal failures. Existing immutable evidence must not be overwritten by changed latency/configuration under the same identity.

Mandatory examples:

- Remove Claude's three completion rows from the Gold fixture and advance the clock beyond all expiries. The public research and paper commands must finish with explicit unavailable/no-position evidence for the affected arms, no fabricated fills and no chronology exception. Repeat the command and inspect the same durable result. Also test both providers arriving only after expiry.
- Run `paper-workflow --maximum-events 100` against the 5,333-event fixture. Report bounded warmup/partial progress with the expected remaining input, never full-workflow completion based on 0/0. Continue from saved progress to the same final result as uninterrupted execution.

**Package B gate:** protected outcomes cannot leak through paper; ordinary absent/late providers are handled as data states; public progress and denominators agree with durable records across repeat runs.

## 5. Work package C — finish the already-required shared service and resume

These are uncompleted 6C/6F requirements, not optional future work.

### One decision path

Extract a compact clock-injected application service used by the production/live-style worker, historical scheduler and connected paper path. Reuse actual candidate admission, material revision, lifecycle and applicable current market-risk rules. The service must consume only evidence available at its evaluation boundary and preserve canonical analysis and independent provider slots.

Demonstrate all six engines through the real entry points. Compare snapshots, accepted revisions, lifecycle, readiness, applicable risk gates and derived outcomes. Calling `detect_signal` in two wrappers is insufficient.

Two required parity cases: source loss during provider review prevents entry in both paths; a spread/drift change that fails production current-risk policy fails the corresponding simulated arm. Also include late candle availability, stop/target exhaustion, expiry and source aging during input silence. Document deliberate transport/persistence differences separately from market logic.

### Complete derived-state checkpoint

Persist input identity/offset, configuration/version, rolling feature/source state and references to pending candidates/providers/decisions/outcomes. Commit progress with derived state or use an equivalently proven recovery protocol. Validate consumed-prefix identity before resuming and reject changed source/configuration without partial silent reuse.

Two mandatory interruption cases: stop after a committed warmup batch; stop after a candidate/one-provider result but before its arm outcome. Restart in a fresh process and compare canonical scientific records/hashes with uninterrupted processing. Genuine wall-clock audit timestamps need not be falsely identical; simulated scientific clocks and results must be deterministic.

A full rerun from the beginning can remain an explicit recovery mode, but must not be reported as checkpoint resume. Include source replacement, configuration drift and output-boundary faults.

### Bounded whole-workflow processing

Stream normalized input and derived output in bounded indexed batches. Remove full-history observations/timeline materialization from the normal connected path. Avoid reloading all candidate quotes for every unrelated warmup event. Retire resolved in-memory state while retaining its immutable journal record. Stream prefix verification; avoid repeatedly joining the entire consumed file prefix per event.

Measure the public commands, including warmup, provider state, pending candidates and output projection. Two representative lengths with the same active working-window requirements must show memory bounded by the declared window/batch/open-state policy. A legitimate increase in simultaneously open positions must be accounted for explicitly. Do not cite only the 5,000-trade deque, a small visibility checkpoint or a command limit applied after reading the whole database.

**Package C gate:** six-engine application-service parity, fresh-process interrupted resume and measured whole-workflow resource bounds pass. The verification report may not list these three as unfinished while declaring software closeout complete.

## 6. Work package D — acceptance bundle and accurate status

Run the full backend/frontend checks and documented public Gold/BTC `validate-data`, `run-workflow`, `paper-workflow`, `evaluate` and `report` commands. Verify export checksums, stored result identities and agreement with API/UI projections. Use ordinary and protected partitions, valid continuous controls and negative/recovery streams.

Required baseline commands:

```bash
python -m pytest -q
python -m ruff check .
python -m ruff format --check .
python -m compileall -q src tests
```

From `frontend`:

```bash
npm ci --no-audit --no-fund
npm run typecheck
npm run build
```

Update README, DESIGN, implementation plan, configuration/examples, API/Windows documentation and release notes where behavior changes. Add `docs/audits/phase-6-closeout-verification.md` with:

- Starting/final code and instruction SHAs, migrations and evaluator/schema versions.
- P6-01–P6-05 red/green cases and preserved positive controls.
- Exact public command results, opportunity/arm/outcome/progress counts, hashes and reproducible fixture definitions.
- Shared-service parity matrix, crash boundaries, fresh-process resume proof and resource measurements.
- Holdout behavior across paper and research before/after opening, including existing derived rows.
- Zero external-action counts demonstrated by transport/service observations, not merely hard-coded summary fields.
- Actual Windows CI results and separate unverified destination/live/empirical gates.

Annotate historical reports with later status; retain their original executed evidence. Do not rewrite historical test results or claim actual model metadata that is absent. Tests must cover complete workflows and normal negative states, not merely raise the test count.

## 7. Next stage after software acceptance — controlled operational validation

Prepare the following runnable checks/runbook as part of closeout. Execute external steps only when the required credentials, bounded configuration and authorization are actually available. Finish all offline preparation even if external prerequisites are absent. Do not request plaintext secrets in chat.

| Operational step | Concrete checks | Evidence to retain |
|---|---|---|
| Windows destination | Start with external paths off; service identity, paths, ACLs, restart/reboot and backup/restore. | Host/version/config fingerprint, redacted health and recovery results; distinguish CI from the actual server. |
| Delta collection | Discover current BTC/gold instruments; validate units; collect bounded trades/book data; exercise reconnect/reconciliation. | Product IDs/spec versions, event/receipt clocks, source coverage/gaps and recovery records. |
| CoinGlass/context | Verify provided plan, supported endpoints/pairs and refresh age; missing Gold reference stays explicitly unavailable. | Entitlement/support responses and observed coverage; no assumptions of Delta-specific coverage. |
| GPT/Claude | Verify both configured accounts/models under explicit limits; preserve request/returned model metadata and independent same-input analysis. | Actual attempts/usage, canonical input digest, provider outcomes and cost accounting. |
| Notifications | Verify an authorized destination with a bounded test; stale/terminal signals suppress; uncertain delivery stays auditable. | Actual delivery receipt and local authorization/recovery records. |
| Prospective collection | Persist decisions before later market outcomes; record outages, exclusions, costs and arm denominators. | Genuine elapsed observations, clearly separate from synthetic/retrospective evidence. |

Two useful operational controls: restart a collector during a sequence gap and prove it waits for resynchronization; make one analyst unavailable and prove the application records WAIT/unavailable without presenting dual confirmation. Do not enable orders.

This stage is complete only when measured real-service/destination checks pass. A configured key or green unit test is not evidence that a provider call, restart or notification worked.

## 8. Prospective observation and reporting

Freeze experiment/selection/cost rules before evaluating forward results. Keep rules-only, GPT, Claude and dual arms on the common opportunity universe; preserve latency, abstentions, missing data and dependency-aware uncertainty. Report each asset/horizon separately.

Two comparisons to prepare: whether dual filtering improves net outcomes after its latency/model costs versus rules-only; whether FAST30 and SESSION240 behave differently across observed market regimes. Do not treat agreement between models as a calibrated probability or guaranteed edge.

Several weeks of elapsed observation may be needed, but duration alone is not an acceptance threshold. Define sufficient sample/coverage criteria and report insufficient evidence honestly. Historical, retrospective and synthetic data cannot substitute for genuine contemporaneous decisions.

## Definition of done and final response

The offline coding task is complete when work packages A–D pass, all five finding groups are closed, and the three previously open software gates have reproducible evidence. Operational and empirical stages remain separately labelled if their real prerequisites are unavailable.

Report changed behavior, verification commands/CI, PR links, remaining external prerequisites and the exact next operator action. Preserve the fixed feature scope. A newly discovered defect within these contracts should be corrected or explicitly left open under closeout; do not automatically create another feature phase or declare incomplete acceptance complete. Derivatives and any separately authorized execution system remain deferred.
