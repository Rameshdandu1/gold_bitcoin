# Independent Phase 6 review and closeout gate

Review date: 2026-11-22 (Asia/Kolkata). Application timestamps in this report are UTC. All prices, P&L and elapsed-time examples are hypothetical verification fixtures.

> **Later review:** The [independent closeout review](phase-6-closeout-independent-review.md) of
> merged PR #12/#13 confirms the five exact P6-01 through P6-05 corrections. It retains three
> reproducible issues within shared application parity and whole-workflow memory acceptance.
> This report preserves the original `f66ac11` findings and executed results; the current task is
> [CODEX_PHASE_6_WORKFLOW_ACCEPTANCE.md](../../prompts/CODEX_PHASE_6_WORKFLOW_ACCEPTANCE.md).

## Verdict

**Phase 6 improves the application and passes its automated baseline, but remains incomplete against its existing acceptance criteria.** Five finding groups require correction, and the implementation report already acknowledges three unfinished software gates. The next coding task is **Phase 6 closeout**, followed by controlled Windows/live integration validation and prospective paper observation. This is not authorization to start derivatives or execution.

- Reviewed main: [`f66ac11f4d958a0075d7e22a5d841256e19b55df`](https://github.com/Rameshdandu1/gold_bitcoin/commit/f66ac11f4d958a0075d7e22a5d841256e19b55df).
- Implementation: [merged PR #10](https://github.com/Rameshdandu1/gold_bitcoin/pull/10), head `020c94365513c53dcfd71f3514c59ca253bcd14b`.
- Prior reviewed code: `dfbb59ea91bfc034f4ab4ffa76c0dbda094f5a31`.
- Governing requirements: [CODEX_PHASE_6.md](../../prompts/CODEX_PHASE_6.md).
- Next task: [CODEX_PHASE_6_CLOSEOUT.md](../../prompts/CODEX_PHASE_6_CLOSEOUT.md).

This review changed documentation only. Tests used isolated SQLite databases, synthetic observations, fake provider/notification transports and injected clocks. There were zero paid provider requests, live market requests, real notifications, orders or deployments. A priority below concerns software/research correctness; it is not a claim of observed financial loss.

## Baseline and positive evidence

Independent local verification passed **237 Python tests**, Ruff lint, Ruff formatting for 86 files, compilation, frontend dependency installation, TypeScript checks and the Vite production build. Two Python dependency deprecation warnings were non-failing. The implementation's [GitHub Actions run 44939257365](https://github.com/Rameshdandu1/gold_bitcoin/actions/runs/44939257365) passed the Windows backend and frontend jobs. Destination Windows Server installation/recovery was not tested.

The documented public commands were executed for Gold and BTC: fixture generation, `run-workflow`, and connected `paper-workflow`; Gold `evaluate`/`report` and export checksums were also checked. Each asset had **5,333 observations, three opportunities and 12 complete target outcomes**, with 241 cadence evaluations per engine. These are deliberately constructed positive streams, not a measured market win rate. Paper outputs correctly identify themselves as `SIMULATED_PROSPECTIVE`.

Independent long/short arithmetic controls also matched. Under quantity 4, multiplier 0.01, tick 0.1, one basis point per side for fees/slippage and two basis points of configured funding cost:

| Hypothetical control | Entry | Exit | Gross P&L | Configured cost | Net P&L |
|---|---:|---:|---:|---:|---:|
| Bullish | 100.3 | 104.9 | 0.184 | 0.0016232 | 0.1823768 |
| Bearish | 99.9 | 95.1 | 0.192 | 0.0015792 | 0.1904208 |

These verify arithmetic under the supplied policy; they do not verify a live venue's actual fee/funding schedule or executable liquidity.

## Disposition of the previous findings

| Previous finding | Independently verified progress | Remaining boundary |
|---|---|---|
| P5-01 alert clock | Normally arriving stop, stop between clock capture/read, expiry and elapsed lease now suppress with zero fake sends. Healthy delayed authorization records the later time. | P6-01: book freshness deadline uses a different clock from the actual quality predicate. |
| P5-02 availability/provenance | Envelope-only provider delay moves readiness correctly; explicit synthetic/prospective mode conflict is rejected. | P6-02: a supplied payload timestamp overrides the authoritative envelope. Actual model identity is still absent from archived research contracts. |
| P5-03 full workflow | Cadence evaluation and source-loss examples are corrected; connected synthetic paper outcomes are present. | Full shared production policy, complete checkpoint/resume and whole-workflow memory acceptance remain unfinished. |
| P5-04 coverage | Missing quote anchor and isolated late OHLC bar now return incomplete; positive economics work. | P6-03: the exact anchored 150-second gap still wins; an incomplete pre-entry bar can prove false completeness. |
| P5-05 paper durability | The maintained tests verify duplicate-first chronology, consumed-prefix replacement checks and transactional rollback for decision/outcome plus cursor. | Do not confuse these local-import controls with complete derived-workflow resume. P6-05 covers connected paper terminal/completion handling. |
| P5-06 holdout | Ordinary opportunity/API/report projections hide protected records; deliberate final access opens them durably. | P6-04: the paper bridge derives and exposes those outcomes before final access. |
| P5-07 legacy jobs | A real Phase 4 database upgrade now makes zero calls and records `LEGACY_REQUEST_CONFIGURATION_INCOMPLETE`. | The demonstrated legacy defect is closed. Preserve this control. |

Current-format healthy review still produces two successful fake assessments, a `CONFIRMED` decision and one durable outbox intent. Terminal/configuration-drift controls make zero calls. Saved-result recovery within deadline and deadline-expired terminalization remain correct without redispatch. No notification was sent by that provider control.

## P6-01 — P1: book authorization expires later than the actual book

**Sources:** [review_worker.py](../../src/marketintel/review_worker.py), lines 117–129; [delta.py](../../src/marketintel/delta.py), lines 489–491; [notifications.py](../../src/marketintel/notifications.py), lines 195–200; [storage.py](../../src/marketintel/storage.py), lines 2018–2055.

The new authorization fence uses fresh time, but its book freshness deadline is calculated from `last_received_at_utc`. The real `OrderBookAssembler.quality` predicate calculates freshness from `last_event_time_utc`. Those are different when a packet arrives late.

Reproduction with an actual parsed, checksum-valid book:

- Book event: **10:00:51**; local receipt: **10:00:59.900**.
- Initial evaluation: **10:01:00**; maximum book age: **10 seconds**. The book is initially valid.
- Actual event-time freshness limit: **10:01:01**. Stored authorization deadline: **10:01:09.900**.
- Authorization at **10:01:02** succeeds: `SENT`, one fake transport call. A fresh real risk evaluation at the same time returns `WAIT/REQUIRED_SOURCES` because the book is 11 seconds old.

For comparison, a healthy 600-millisecond delay authorizes correctly at the later time, while the prior expiry/lease/stop cases correctly suppress. The original clock fix should be retained.

**Correction:** derive authorization deadlines from the exact shared validity predicates. Include the book's event-time expiry and any independently required receipt-time expiry. Test a delay that crosses only event-time freshness. The network send remains outside the short authorization transaction.

## P6-02 — P1: payload timestamps bypass journal availability

**Sources:** [research_engine.py](../../src/marketintel/research_engine.py), lines 241–246 and 362–401; [research_storage.py](../../src/marketintel/research_storage.py), lines 570–578.

Phase 6 copies envelope availability into completion/quote payloads only when the payload does not already supply it. An explicitly earlier payload timestamp survives. A valid current schema therefore permits conflicting clocks, and downstream readiness/fills use the earlier one.

Two public Gold workflow cases pass `validate-data` and `run-workflow` after recomputing legitimate file/manifest hashes:

1. Provider envelopes become available at **01:02:02/03**, but payload availability remains **01:00:02/03**. All three dual arms regain readiness **01:00:03**, entry **01:00:04** and complete target exit **01:00:20**.
2. Quote envelope availability begins at **01:02:04**, but payload availability remains **01:00:04**. All three dual arms again report the original complete target wins before receipt of the required quote records.

The original missing-payload-field case now works: a 120-second provider delay moves dual readiness to 01:02:03 and produces `NO_ENTRY`. Explicit mode conflicts are also rejected. Those improvements do not close the conflicting-field path.

**Correction:** use one authoritative normalization rule. Reject contradictory envelope/payload clocks or conservatively reconcile them so actionable readiness/fill is never earlier than the accepted journal boundary. Apply the rule once at ingestion and preserve it across every projection. Treat a checksum as proof of bytes, not proof of factual availability.

**Documentation qualification:** archived contracts now preserve provider labels and request/configuration digests, but `ProviderCompletion` and `ArmDecision` still lack requested/returned model identity. The implementation report's phrase “provider/model/request/configuration provenance” overstates the model portion. Preserve unknowns and add actual model evidence before claiming model-specific prospective comparisons.

## P6-03 — P1 coverage: the final pre-entry gap is still ignored

**Sources:** [research_evaluation.py](../../src/marketintel/research_evaluation.py), lines 190–207 and 249–260; bar handling at 495 and 522–542. The public quote workflow calls the evaluator at [research_engine.py](../../src/marketintel/research_engine.py), lines 642–652.

The coverage loop stops at readiness. The later entry check subtracts `max(ready, coverage_previous_at)`, allowing readiness to erase the missing interval since the last real observation.

Two independently reproduced coverage cases, both bullish and bearish:

1. Candidate/neutral quote at +0, no quotes until readiness/entry **+150**, target **+155**, maximum gap **10 seconds**: still `TARGET_BEFORE_STOP`, `data_complete=True`. Explicit availability fields do not change the result. This is the original anchored-gap counterexample, not a new speculative case.
2. Neutral OHLC bar +0 to +30 has **`complete=False`**; readiness is +30; the next complete bar +30 to +40 reaches target. The bar helper still reports a complete target because it advances coverage/handles pre-entry bars before validating completeness.

The second is a **P2 helper defect within this finding group**; the connected workflow currently uses quotes. Missing initial anchors and isolated late bars now fail closed.

**Correction:** require coverage all the way from the last valid pre-entry observation to the first eligible entry quote. Readiness is a decision clock, not market evidence. Incomplete bars must never establish coverage, even when their timestamps are contiguous or they occur before entry. Preserve valid continuous positive controls and conservative ambiguity.

## P6-04 — P1: paper replay bypasses protected holdout reads

**Sources:** [research.py](../../src/marketintel/research.py), lines 192–198 and 228–279; [api.py](../../src/marketintel/api.py), lines 266–270; [research_storage.py](../../src/marketintel/research_storage.py), paper transition projection at 1190–1199.

The normal research projection is corrected. The connected paper command reads unfiltered candidates/decisions, derives their outcomes into another database, and exposes paper transitions without the experiment's protected-partition policy.

A valid Gold fixture freezes holdout at candidate time; provider request/configuration digests and file/manifest hashes are regenerated consistently:

1. Before final access, ordinary authenticated opportunities return `[]` and ordinary exports omit protected identities. Yet `paper-workflow` creates **12 protected target outcomes**, and authenticated paper transitions reveal all **12 `TARGET_BEFORE_STOP` identities/times**. Holdout-access records remain **zero**.
2. The deliberate `final-holdout` command subsequently works: three opportunities become visible and one access event records `HOLDOUT_OPENED`.

Authentication itself works: unauthenticated ordinary reads return 401. This is scientific blinding failure through a derived-data path, not an authentication bypass. The exposed paper response contains outcome codes/times, not P&L fields in this reproduction.

**Correction:** preserve experiment/configuration/partition provenance into paper-derived records and enforce the same visibility policy, or block protected derivation/exposure until deliberate final access. Account for existing derived rows and outcome-bearing counts, filters, events and exports. Frontend masking alone is insufficient.

## P6-05 — P1 terminal handling, P2 completion reporting in connected paper

**Sources:** [research.py](../../src/marketintel/research.py), lines 183–205, 281–306; [research_engine.py](../../src/marketintel/research_engine.py), unavailable-provider readiness; [research_storage.py](../../src/marketintel/research_storage.py), lines 839–844.

Missing/too-late assessments are represented with readiness at expiry. The paper command schedules their decision persistence at readiness plus processing delay, then the ledger rejects every new simulated/prospective decision at or after expiry. Expected unavailable-provider input therefore aborts the command.

Two public command reproductions use the generated Gold fixture and preserve its original market coverage window:

1. Remove the three Claude completions and append a clock-only expiry observation after the longest horizon. Research completes, but `paper-workflow` exits **2** with `Prospective decision must be persisted before eligible entry`. Six rules/GPT decisions/outcomes exist; unavailable arms cannot complete. Rerunning gives the same error.
2. Deliver both providers after all candidate expiries. Research completes, but paper again exits **2**, after recording only the three rules-only decisions/outcomes.

These are normal negative paths that should be auditable unavailable/no-position dispositions, not application errors. Do not fix them by backdating writes or allowing an expired approved entry.

A separate bounded-progress counterexample uses the unmodified fixture: `--maximum-events 100` consumes only warmup, records **zero decisions and zero outcomes**, yet reports **`SIMULATED_PROSPECTIVE_COMPLETE`** because zero equals zero. The ledger itself still says `NOT_STARTED`. Completion must reflect expected input/horizon and required terminal dispositions, not equality of two global row counts.

**Correction:** represent terminal unavailable/expired/no-position events separately from entry-eligible approved decisions; preserve factual timing and the denominator. Distinguish not-started, partial, fully processed and unresolved evidence states. Scope progress/counts to the selected experiment/configuration. Genuine incomplete paths must remain incomplete even if processing has finished.

## Three existing software gates remain open

The [Phase 6 implementation report](phase-6-verification.md) explicitly records these as unverified. They were already required by 6C/6F and should be completed under the same phase:

1. **Full shared policy:** production and research still lack one complete admission/material-revision/lifecycle/current-risk application path. Detector reuse and a source-state check do not establish parity. For example, source loss and spread/entry-drift changes must be handled by the same applicable policy.
2. **Durable derived-workflow resume:** visibility checkpoints and atomic local import are not a checkpoint of feature state, pending candidates/providers, decisions and outcomes. For example, interruption during warmup and interruption while a review is pending must converge to uninterrupted canonical results.
3. **Bounded whole-workflow memory:** the connected paper command materializes the entire observations list/timeline; the local importer reads the complete file and recomputes prefix hashes. For example, `--maximum-events` is applied after the full observation read, and bounding a trade deque does not bound accumulated candidates/derived rows. Measure the actual public path.

There is no need to add new indicators, trading features or a new stack to close these gates.

## Next work and evidence limits

Follow [CODEX_PHASE_6_CLOSEOUT.md](../../prompts/CODEX_PHASE_6_CLOSEOUT.md). It freezes the next task to P6-01–P6-05 plus the three existing gates and defines the subsequent operational-validation entry criteria.

The independent probes were temporary investigative scripts; future implementation must add maintainable regressions with the exact specified clocks and outcomes. Public cases begin with `marketintel.research_fixtures`, alter only the indicated evidence/configuration, recompute hashes/digests where required, and use fresh isolated databases. Code changes must preserve the passing controls as well as close the failing variants.

Baseline commands: `python -m pytest -q`, `python -m ruff check .`, `python -m ruff format --check .`, `python -m compileall -q src tests`, frontend `npm ci --no-audit --no-fund`, `npm run typecheck`, and `npm run build`.

After software closeout, verify real Delta/CoinGlass/model access, permitted notifications and destination Windows operation using explicitly authorized bounded tests. Prospective observation and strategy comparison then require real elapsed time and adequate independent evidence. Current synthetic results do not establish prediction accuracy, model lift or profitability.
