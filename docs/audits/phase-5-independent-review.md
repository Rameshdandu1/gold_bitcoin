# Independent Phase 5 review

Review date: 2026-11-21. Application timestamps below are UTC. All numerical examples are hypothetical software fixtures.

## Verdict and scope

**Phase 5 delivered a working public research workflow and substantial corrections, but its software acceptance is still incomplete.** Seven reproducible findings remain. Phase 6 should close those findings and demonstrate the complete decision/paper workflow before derivatives or execution work starts.

- Repository: [Rameshdandu1/gold_bitcoin](https://github.com/Rameshdandu1/gold_bitcoin).
- Reviewed main: [`dfbb59ea91bfc034f4ab4ffa76c0dbda094f5a31`](https://github.com/Rameshdandu1/gold_bitcoin/commit/dfbb59ea91bfc034f4ab4ffa76c0dbda094f5a31).
- Implementation: [merged PR #8](https://github.com/Rameshdandu1/gold_bitcoin/pull/8), head `959cf50fe8263165a3ae7fa5e25e320a7037e362`.
- Previous reviewed code: `3b07d21079729da41f53c80fa5c4604b1dea9499`.
- Previous requirements: [CODEX_PHASE_5.md](../../prompts/CODEX_PHASE_5.md) and [Phase 4 independent review](phase-4-independent-review.md).
- Next implementation task: [CODEX_PHASE_6.md](../../prompts/CODEX_PHASE_6.md).

This review changed documentation only. Reproductions used isolated temporary databases, synthetic streams, advancing fake clocks and fake provider/notification transports. No paid requests, live market collection, real notifications, orders or deployment were performed. Finding priority refers to application/research correctness, not a security exploit rating or evidence of actual financial loss.

## Verification and genuine improvements

The independent baseline passed **227 Python tests**, Ruff lint, Ruff format for 82 files, Python compilation, frontend dependency installation, TypeScript checks and Vite production build. Two dependency deprecation warnings did not fail the run. The merged PR's [GitHub Actions run 44932503079](https://github.com/Rameshdandu1/gold_bitcoin/actions/runs/44932503079) also passed both jobs, including Windows backend validation. This does not prove installation or recovery on the destination Windows Server.

Public `research_fixtures`, `run-workflow` and `evaluate` commands were exercised for Gold and BTC. Each generated stream contained **5,333 observations** and produced **three opportunities**, collectively covering all six production detector configurations. Gold report export was also exercised. These are constructed positive cases, not six independent market observations or an accuracy estimate.

The following original counterexamples now behave correctly:

| Area | Independently verified result |
|---|---|
| Current alert quote policy | Wide spread and excessive entry drift suppress delivery; zero fake sends. |
| Original dispatch races | A stop within the evaluated time cutoff, or a terminal lifecycle transition before authorization, suppresses delivery. |
| New-format provider preflight | Terminal candidates produce zero calls; queued output cap 64 versus runtime 650 produces zero calls. |
| Saved provider results | Results recover without redispatch; default 90-second deadline/120-second lease yields a durable deadline-expired WAIT rather than repeated reclaim. |
| Quote outcomes | Known pre-readiness stop, post-entry gap, expiry equality and duplicate application of diagnostic provider latency now behave correctly. |
| Bar outcomes | Partial entry/expiry bars and rejected arms no longer produce completed executions. |
| Partitions and comparisons | Training uses earlier intervals; labels crossing holdout are excluded from ordinary development metrics; known abstentions remain in paired comparisons. |
| Paper legality | Backfilled decisions, unavailable future outcomes and executed wins on rejected arms are rejected. |
| Public usability | Real detector-backed opportunities, authenticated research views and stored report exports are present. |

The old raw-helper duplicate-count example is not repeated as a current public-path defect: the public evaluator now selects one revision per opportunity before aggregation. Similarly, the new provider configuration checks and original alert token checks work for the cases they cover. The findings below describe their remaining boundaries.

## P5-01 — P1: alert authorization uses a stale clock

**Code:** [notifications.py](../../src/marketintel/notifications.py), lines 105–106, 155–156 and 185–189; [storage.py](../../src/marketintel/storage.py), eligibility token/fact reads around 1623–1683 and dispatch authorization around 1981–2055.

`AlertWorker.run_once` captures time once and reuses it for both risk attempts and the authorization transaction. The evidence token includes newly persisted trades, while risk facts filter out events received after that original timestamp. A changed token causes a retry, but the retry can accept the new token without evaluating the newly arrived trade. Time-dependent expiry, lease and freshness checks also use the old clock.

Reproduced with the actual worker, evaluator and SQLite store, without supplying `run_once(now=...)`:

1. Worker starts at **10:01:00**. A stop trade arrives and is persisted at **10:01:00.600** before authorization. The first token check rejects; the second authorizes. Result: **SENT, one fake transport call**, authorization recorded at 10:01:00. A fresh reread returns `WAIT/STOP_BREACH`.
2. Worker starts at **10:29:59**, candidate expires at **10:30:00**, and processing advances to **10:30:01** before authorization. Result: **SENT, one fake call** despite expiry. A separate 31-second pause likewise authorizes after a 30-second lease and book freshness have elapsed.

**Required:** refresh time for every risk attempt, align the evaluated event cutoff with its evidence token, and validate time-dependent authorization limits after obtaining the short write transaction. Record actual authorization time. Network delivery remains outside the database transaction; external exactly-once delivery is not claimed.

## P5-02 — P1: research loses evidence availability and provider provenance

**Code:** [research_engine.py](../../src/marketintel/research_engine.py), lines 232–240, 332–374 and 523–585; [research_storage.py](../../src/marketintel/research_storage.py), lines 523–536 and experiment metadata projection; [research_models.py](../../src/marketintel/research_models.py), executable quote/arm contracts.

The journal is sorted by availability, but downstream decisions and fills discard that clock. Provider state retains completion time without the envelope's availability time. Quote projection defaults its only timestamp to exchange time. After consuming the entire journal, the workflow constructs decisions and outcomes using those earlier timestamps.

Two public CLI counterexamples start with the generated Gold fixture, change only the named evidence availability, recompute file/manifest hashes and use a new isolated database:

1. Entry/target quote availability is delayed by **120 seconds**. First quote is available at **01:02:04**, but all three dual arms remain complete target wins with entry **01:00:04** and exit **01:00:20**.
2. Provider completion availability is delayed by **120 seconds**. GPT/Claude become available at **01:02:02/03**, but all three dual arms still report readiness **01:00:03**, entry **01:00:04** and exit **01:00:20**.

A related provenance control also fails: changing the manifest's asserted mode to `RECORDED_PROSPECTIVE_MODEL`, with a valid recomputed manifest hash, while retaining six completion rows explicitly labelled `SYNTHETIC_FIXTURE`, is accepted by the public command. Experiment metadata displays the prospective mode; all three dual arms are executable, and their projected arm records lose the fixture provenance. This does not prove actual prospective evidence; it demonstrates contradictory evidence being accepted and mislabeled.

**Required:** preserve event, completion, receipt/availability and persistence clocks through every derived record; bind arm readiness to factual availability and current-risk readiness. Define conservative fill eligibility for delayed quotes. Validate evidence-mode compatibility and preserve provider/model/request provenance in arm records, reports and APIs. A valid hash proves bytes, not the truth or compatibility of the claimed evidence category.

## P5-03 — P1: detector reuse does not establish full workflow parity

**Code:** [research_engine.py](../../src/marketintel/research_engine.py), `SharedResearchEngine.evaluate`, `_decisions` and `run_shared_workflow`; compare [worker.py](../../src/marketintel/worker.py) and [consensus.py](../../src/marketintel/consensus.py).

The new workflow calls the production `detect_signal`, which is a real improvement. It does not call the same complete candidate admission, lifecycle and current-risk decision path. Archived confirmations are converted directly into approved arm decisions. Source transitions affect subsequent detector evaluations but do not revalidate an existing candidate when an analyst result becomes usable.

Two observations establish the remaining gap:

1. Add `SOURCE_TRANSITION=UNAVAILABLE` at **candidate time +1 second**, with no recovery, to the otherwise valid generated Gold stream. GPT/Claude complete at +2/+3; all three dual arms still become `EXECUTABLE` and complete target wins at +20.
2. The public fixture's final evaluation window extends four hours, but each Gold/BTC engine is evaluated only once because subsequent quote/provider events do not mark it dirty. The `dirty_symbols` loop does not schedule time-driven lifecycle/freshness evaluation. That is insufficient evidence of parity for expiry or source aging without new trades/candles.

The second observation is a structural acceptance gap, not an additional measured false expiry outcome. Full production worker parity was not demonstrated by calling the shared detector alone.

**Required:** use a shared, clock-injected decision service for applicable admission, material revision, lifecycle and current market-risk rules. Re-evaluate an arm at actual readiness and before hypothetical entry. Schedule required expiry/freshness transitions even during input silence. Keep simulation-specific output/notification configuration separate from shared market-risk gates. Demonstrate all six engines through both actual entry points, including abstaining paths.

## P5-04 — P1: missing pre-entry or OHLC path can still become a complete win

**Code:** [research_evaluation.py](../../src/marketintel/research_evaluation.py), quote matching/pre-entry logic at 148–188 and bar path logic at 367–440.

Known pre-entry breaches and post-entry quote gaps are now handled. The remaining issue is proving that the path before entry was observed at all. The bar evaluator likewise checks individual bars without establishing complete interval coverage.

Reproduced in both bullish and bearish directions:

1. Candidate at +0, neutral quote at +0, no further evidence until readiness/entry at **+150**, target at **+155**, maximum permitted quote gap **10 seconds**: `TARGET_BEFORE_STOP`, `data_complete=True`. Removing the initial quote entirely gives the same answer.
2. Readiness at **+30**; the only OHLC bar covers **+170 to +180** and reaches the target: complete target outcome despite the missing 140 seconds before that bar.

**Required:** establish coverage from candidate observation through effective entry and through the outcome, including a valid starting anchor and every intervening gap. Distinguish a valid book carried forward under a proven continuous source from a bare sparse quote list. For OHLC, prove contiguous intervals; do not let one bar's `complete=True` establish the entire path. The public connected workflow currently uses quotes; the bar result remains a helper defect that must be closed before that evidence mode is accepted.

## P5-05 — P1: paper crash recovery and file identity remain incomplete

**Code:** [paper_worker.py](../../src/marketintel/paper_worker.py), lines 39–57 and 68–102; [research_storage.py](../../src/marketintel/research_storage.py), `PaperLedger.record_decision` at 715–778 and `bind_cursor`.

Decision persistence and input cursor advancement occur in separate transactions. Duplicate decision ingestion performs the new-write chronology checks before discovering the existing identical record. Source binding checks a caller-supplied label, generation and line count; it does not verify that the consumed file prefix is unchanged.

Two finite worker reproductions:

1. Simulate a crash after the decision commits but before cursor advancement. Durable state is **one decision, cursor 0**. Restart one second later rejects the identical record with `Prospective decision must be persisted before eligible entry`, so progress cannot resume normally.
2. Consume a one-line file, replace it with a different one-line decision while retaining the same path, source label and generation, then run again. The worker returns `RECORDED` with **zero new records**, cursor 1, and silently omits the replacement event. The existing test changes the declared label; it does not cover actual replacement with an unchanged label/count.

**Required:** make transition and cursor progress atomic, or provide equally rigorous recoverable idempotence that consults the immutable original decision before applying new-write timing rules. Bind source progress to stable journal/file identity plus a verified prefix or equivalent digest. Preserve the original timestamp on retries and reject conflicting bytes. A supported rotation protocol must never silently skip input.

The public paper worker still imports caller-supplied decision/outcome JSON. Its chronology checks are useful, but that interface alone is not a demonstrated market-observation-to-paper-outcome service. Phase 6 must supply the connected path or explicitly leave that acceptance gate open.

## P5-06 — P1: normal authenticated reads expose unopened holdout outcomes

**Code:** [api.py](../../src/marketintel/api.py), lines 257–264; [research_storage.py](../../src/marketintel/research_storage.py), `opportunity_page` at 301–312 and separate holdout-access recording.

Ordinary CLI aggregate evaluation now filters protected and crossing rows. The opportunity detail read path retrieves complete outcome JSON without applying the same protection.

Reproduction uses a valid manifest/configuration, holdout at **10:01**, a protected candidate at **10:02**, and a hypothetical target result calculated by the real quote evaluator:

1. Unauthenticated GET returns **401**, confirming that authentication is enforced.
2. Authenticated GET `/api/research/experiments/{id}/opportunities` returns **200**, including `TARGET_BEFORE_STOP`, **+4.8 hypothetical net P&L**, entry 10:02:10 and exit 10:02:20. Holdout access records remain **zero** before and after the read.

This is a scientific blinding failure for the authenticated operator, not an authentication bypass. An explicit final-evaluation command does not protect the holdout if an ordinary detail endpoint reveals its outcomes first.

**Required:** centralize partition/access policy across aggregate reports, details, UI and exports. Withhold protected/crossing outcome-bearing data before the recorded final-evaluation action. After opening, label it as opened, retain the frozen configuration/access identity and avoid implying it remains unseen.

## P5-07 — P2: upgraded legacy jobs bypass new dispatch preflight

**Code:** [orchestration.py](../../src/marketintel/orchestration.py), queued-configuration handling around 82–90 and conditional preflight at 354–357, 419 and 427; [storage.py](../../src/marketintel/storage.py), migration 0005.

Strict preflight is conditional on `request_config_version=phase5-v1`. Older queued configurations remain executable after migration.

The probe created a database using the actual Phase 4 `Store` from commit `3b07d21` and its production admission/configuration path, invalidated the queued candidate, then reopened it with Phase 5 and ran the actual review worker with fake providers. Migration 0005 applied; the worker still made **two provider calls**, both succeeded, and final consensus was `WAIT`.

For comparison, the equivalent new-format terminal job correctly makes **zero calls**. A new-format queued cap of 64 versus runtime cap 650 also correctly makes zero calls. The defect is the supported upgrade path, not the corrected current-format behavior.

**Required:** terminal/deadline/lease/revision/source preflight must apply independently of request format. Quarantine legacy pending jobs whose complete request identity cannot be proven, or migrate them with an explicit audited policy. Do not invent missing frozen fields from current settings. No real charge or false confirmation was observed in this reproduction.

## Reproduction and acceptance notes

The independent probes were temporary investigative scripts, not application changes. Implement maintainable repository regressions from the cases above. To reproduce the public arrival/source/provenance cases:

1. Generate the documented Gold fixture with `python -m marketintel.research_fixtures --output <temporary-directory>`.
2. Change only the indicated observation clock, source-transition row or asserted evidence mode. Recompute the evidence file SHA-256/count and canonical manifest hash; preserve contradictory row provenance in the mixed-mode case.
3. Run the documented `run-workflow` command against a fresh isolated database, then inspect stored four-arm outcomes and authenticated projections. No live service or key is required.

The baseline commands were `python -m pytest -q`, `python -m ruff check .`, `python -m ruff format --check .`, `python -m compileall -q src tests`, frontend `npm ci --no-audit --no-fund`, `npm run typecheck` and `npm run build`.

Retained trade/candle limits and compact visibility checkpoints are useful evidence. They do not, by themselves, prove bounded total workflow memory, interrupted full-workflow resume, or parity with a live-style worker. Those acceptance checks must include warmup, provider state, pending candidates, derived outputs and actual paper transitions.

**Next gate:** complete the scoped Phase 6 corrections and public integration tests. Then record separate readiness for licensed historical coverage, contemporary provider evidence, weeks of forward observation, Windows destination recovery and authorized external soaks. Software fixtures cannot establish whether dual-model confirmation improves net results, whether a $10–$30 gold move is predictable, or whether any engine has an empirical edge.
