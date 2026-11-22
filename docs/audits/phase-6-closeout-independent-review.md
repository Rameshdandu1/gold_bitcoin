# Independent review of the Phase 6 closeout

Review date: 2026-11-22 (Asia/Kolkata). All application clocks below are UTC. Prices, P&L,
provider results and market paths are explicitly hypothetical software fixtures.

## Verdict

**The five original findings P6-01 through P6-05 are corrected in their exact retests. The
claim that every offline acceptance gate is complete is premature.** Three reproducible issues
remain within two previously required gates: contemporaneous shared application policy and
bounded whole-workflow memory. Derived checkpoint/resume works in the tested uninterrupted and
interrupted fixture paths; that progress is preserved.

The next coding task is the finite [Phase 6 workflow acceptance correction](../../prompts/CODEX_PHASE_6_WORKFLOW_ACCEPTANCE.md).
After it passes, proceed to controlled Windows/live integration validation, then prospective
paper observation. These findings do not justify derivatives, execution, new indicators or another
architecture redesign.

- Reviewed main: [`81f86f79cb943c8cb837aae4f800135948f89f32`](https://github.com/Rameshdandu1/gold_bitcoin/commit/81f86f79cb943c8cb837aae4f800135948f89f32).
- Implementation: [merged PR #12](https://github.com/Rameshdandu1/gold_bitcoin/pull/12), primary
  implementation commit `1651888`, merged as `92634a32e81f730f922ad95528db5c688db184e5`.
- Status documentation: [merged PR #13](https://github.com/Rameshdandu1/gold_bitcoin/pull/13).
- Previous independently reviewed implementation: `f66ac11f4d958a0075d7e22a5d841256e19b55df`.
- Existing requirements: [Phase 6 closeout, package C](../../prompts/CODEX_PHASE_6_CLOSEOUT.md#5-work-package-c--finish-the-already-required-shared-service-and-resume).

This review changes documentation only. Verification used local synthetic files, isolated SQLite
databases, injected clocks and fake transports. No live collection, paid provider request, real
notification, order or deployment was performed. Reported priorities concern reproducible software
and research correctness; they do not describe observed trading losses.

## Baseline and positive public workflows

Independent local verification passed:

| Check | Result |
|---|---|
| Python suite | **251 passed**; two non-failing dependency deprecation warnings |
| Ruff lint | Passed |
| Ruff formatting | Passed; 91 files already formatted |
| Compile `src` and `tests` | Passed |
| Frontend `npm ci`, TypeScript and production build | Passed |
| PR #12 CI | [Run 44964368372](https://github.com/Rameshdandu1/gold_bitcoin/actions/runs/44964368372), both Windows jobs succeeded |
| PR #13 CI | [Run 44977598422](https://github.com/Rameshdandu1/gold_bitcoin/actions/runs/44977598422), succeeded |

The public `validate-data`, `run-workflow`, `paper-workflow`, `evaluate` and `report` commands were
executed independently for both assets. Every report's nine checksummed files verified.

| Synthetic asset | Input observations | Opportunities | Paper decisions | Paper outcomes | Pending arms |
|---|---:|---:|---:|---:|---:|
| Gold | 5,333 | 3 | 12 | 12 | 0 |
| BTC | 5,333 | 3 | 12 | 12 | 0 |

Both paper runs correctly report `SIMULATED_PROSPECTIVE_COMPLETE`. All three horizons are represented
per asset, with 241 scheduled evaluations per engine. The constructed outcomes hit targets; the
paired day-block comparisons correctly report `INSUFFICIENT_DATA`. This establishes positive
software behavior, not an observed win rate, dual-model lift or profitability.

## Exact disposition of P6-01 through P6-05

| Finding | Independently observed correction | Preserved control |
|---|---|---|
| **P6-01: book freshness deadline** | Event 10:00:51, receipt 10:00:59.900, evaluation 10:01:00 and authorization 10:01:02 now produce deadline 10:01:01, `SUPPRESSED`, zero fake sends and no authorization. | Healthy +600 ms still sends once; stop arrival, expiry, elapsed lease, uncertain delivery and immutable destination controls remain intact. |
| **P6-02: payload availability override** | Provider and quote envelopes delayed 120 seconds with earlier explicit payload clocks fail `run-workflow` with typed conflicts. | Omitted provider availability uses the outer receipt: dual ready 01:02:03 and three `NO_ENTRY` outcomes. Incompatible evidence modes still fail. |
| **P6-03: incomplete pre-entry coverage** | Both directions of the +0 anchor / +150 ready-entry / +155 target case return `INCOMPLETE/ENTRY_QUOTE_GAP_EXCEEDED`. The incomplete +0..30 pre-entry bar returns `INCOMPLETE/PARTIAL_BAR_IN_PATH`. | Continuous long and short hand calculations still match; OHLC is a helper check, while the public connected path uses quotes. |
| **P6-04: paper holdout bridge** | Holdout at candidate time permits processing all 5,333 inputs but creates zero protected paper rows before final access. Authenticated API/detail/export bytes expose none; access count remains zero. | Deliberate final access records one event, then reveals three opportunities and 12 target transitions. A valid legacy unscoped target remains hidden. |
| **P6-05: absent/late providers and progress** | Missing Claude yields 12 terminal arm records: six targets and six incomplete/unavailable outcomes. Both providers +5 hours late yield three targets and nine incomplete/unavailable outcomes. No unavailable arm gets an entry. | Repeats preserve identical transitions. A 100-row BTC prefix reports warmup partial and 5,233 remaining; a fresh-process resume matches uninterrupted paper transitions. |

Semantic payload rejection occurs in `run-workflow`; `validate-data` still accepts the enclosing
well-formed, correctly hashed file in the conflict cases. Do not claim the validator itself rejects
those payloads.

Optional requested/returned model IDs now survive into individual-provider arm decisions. Supplied
hypothetical GPT IDs were retained verbatim; omitted Claude IDs remained null. Incorrect request or
configuration digests produced unavailable arms. This verifies retention and binding of archived
metadata, not current remote account access or authenticity of a real model response.

The real review worker with two fake transports still receives identical canonical input bytes,
produces a healthy confirmation and one durable outbox intent. Terminal/configuration-drift and
actual Phase 4 upgrade cases make zero calls. Saved-result recovery and expired-deadline
terminalization do not redispatch. These controls remain distinct from the research defects below.

Independent arithmetic controls used quantity 4, multiplier 0.01, tick 0.1, fees/slippage of one
basis point per side, and two basis points of configured funding:

| Hypothetical direction | Entry | Exit | Gross P&L | Configured cost | Net P&L |
|---|---:|---:|---:|---:|---:|
| Bullish | 100.3 | 104.9 | 0.184 | 0.0016232 | 0.1823768 |
| Bearish | 99.9 | 95.1 | 0.192 | 0.0015792 | 0.1904208 |

## P6C-01 — P1: later book observations recompute immutable earlier decisions

**Sources at reviewed SHA:**
[book updates](https://github.com/Rameshdandu1/gold_bitcoin/blob/81f86f79cb943c8cb837aae4f800135948f89f32/src/marketintel/research_engine.py#L218-L236),
[provider-event recomputation](https://github.com/Rameshdandu1/gold_bitcoin/blob/81f86f79cb943c8cb837aae4f800135948f89f32/src/marketintel/research_engine.py#L714-L748),
[finalization](https://github.com/Rameshdandu1/gold_bitcoin/blob/81f86f79cb943c8cb837aae4f800135948f89f32/src/marketintel/research_engine.py#L842-L859),
[point-in-time predicate](https://github.com/Rameshdandu1/gold_bitcoin/blob/81f86f79cb943c8cb837aae4f800135948f89f32/src/marketintel/application_policy.py#L67-L71),
[immutable decision check](https://github.com/Rameshdandu1/gold_bitcoin/blob/81f86f79cb943c8cb837aae4f800135948f89f32/src/marketintel/research_storage.py#L574-L603).

Generate the ordinary Gold fixture. Add exactly one valid `BOOK_SNAPSHOT` with unchanged bid
**2599.9** and ask **2600.1**, sequence/generation 2, `snapshot=true`, a unique observation ID and
matching envelope/feature times. Recompute the evidence count, file SHA-256 and canonical manifest
hash. Leave pre-candidate trigger inputs and provider request identities untouched. Use a fresh
research database for each variant.

| Case | `validate-data` | `run-workflow` | Durable result |
|---|---:|---|---|
| Unmodified 5,333-row control | 0 | 0 | Three opportunities, 12 decisions, checkpoint `COMPLETE` |
| Same-price snapshot at candidate +21 seconds, after the +20 target quotes | 0 | **2: `Arm decision identity is immutable`** | 12 saved decisions, zero completed opportunities, checkpoint `INPUT_COMPLETE` |
| Same-price snapshot at +2.5 seconds, between GPT +2 and Claude +3 | 0 | **2: `Arm decision identity is immutable`** | Three rules and three GPT decisions, zero completed opportunities, checkpoint `RUNNING` |

The shared predicate correctly refuses evidence from after an earlier decision's readiness time.
The workflow incorrectly combines that historical readiness with the newest book. It then tries to
write the changed answer under the already frozen arm identity. The immutable-store check is
protecting the record; weakening it would hide the defect.

**Correction:** resolve each arm against its contemporaneous evidence boundary and persist that
decision. Finalization consumes persisted decisions. Later books, trades and source changes may
cause current lifecycle/risk transitions or a separately identified decision, never a rewrite of
the original. A later dual decision needs its own current eligibility check at the slower
provider's readiness; preserving the earlier GPT decision must not bypass that check.

## P6C-02 — P1: research ignores a production-terminal executed stop breach

**Sources at reviewed SHA:**
[production lifecycle sweep](https://github.com/Rameshdandu1/gold_bitcoin/blob/81f86f79cb943c8cb837aae4f800135948f89f32/src/marketintel/worker.py#L50-L104),
[research gate inputs](https://github.com/Rameshdandu1/gold_bitcoin/blob/81f86f79cb943c8cb837aae4f800135948f89f32/src/marketintel/research_engine.py#L539-L595),
[research outcome inputs](https://github.com/Rameshdandu1/gold_bitcoin/blob/81f86f79cb943c8cb837aae4f800135948f89f32/src/marketintel/research_engine.py#L868-L878).

Use the same three production detector candidates from the Gold fixture. Persist them in a real
production `Store`. Parse and journal these two hypothetical executed trades, and add the exact
corresponding normalized observations to a fresh research manifest:

| Fact | Exchange time | Receipt/availability | Price |
|---|---|---|---:|
| Stop breach | 01:00:00.900 | 01:00:01.000 | 2594.8 |
| Recovery | 01:00:01.400 | 01:00:01.500 | 2599.2285714285713 |

Candidates originate at **2026-11-19 01:00:00**. GPT/Claude remain +2/+3, and the executable entry
and target quotes remain +4/+20. Run the actual production `_sweep_quant_candidates` at +3 with
fresh sources and the recovered latest price. This is a real worker function against the real
store, not the whole live ingestion loop.

| Identical candidate ID in both paths | Invalidation | Production sweep |
|---|---:|---|
| `f2865d736e71adedf991cadb` | 2595.8 | `INVALIDATED` |
| `8763566f1e7e4fa7d10f65a3` | 2596.8 | `INVALIDATED` |
| `2af95b87481f16eca51f7978` | 2598.2285714285713 | `INVALIDATED` |

Production retains the known executed stop breach even after recovery. Public research validates
and completes successfully on the same candidate IDs, but **all 12 arms report
`EXECUTABLE/TARGET_BEFORE_STOP`**. It uses the current book for stop status and supplies constant
`revision_current=True`, lifecycle `CANDIDATE` and unambiguous ordering. The outcome evaluator never
receives the executed-trade invalidation history.

**Correction:** share the actual event-driven admission/revision/lifecycle and applicable current
risk facts. A known post-observation breach must remain terminal through recovery and provider
completion. Preserve the original decision, then persist the terminal event; an unfilled arm cannot
become a winning execution after invalidation. Apply correct ordering separately when entry already
occurred before a terminal event.

The extraction of `application_policy.py` is useful but narrower than full application parity.
Production still owns target feasibility/net reward-risk checks outside it, and the research
adapter supplies assumptions instead of equivalent facts for several shared predicates. These are
coverage limits of the existing acceptance claim, not separately reproduced additional findings.
The remaining parity matrix should verify these contracts rather than add new strategy rules.

## P6C-03 — P2: public processing still materializes full quote history

**Sources at reviewed SHA:**
[full observation list](https://github.com/Rameshdandu1/gold_bitcoin/blob/81f86f79cb943c8cb837aae4f800135948f89f32/src/marketintel/research_storage.py#L445-L467),
[quote projection](https://github.com/Rameshdandu1/gold_bitcoin/blob/81f86f79cb943c8cb837aae4f800135948f89f32/src/marketintel/research_storage.py#L682-L700),
[paper loading/filtering order](https://github.com/Rameshdandu1/gold_bitcoin/blob/81f86f79cb943c8cb837aae4f800135948f89f32/src/marketintel/research.py#L218-L269),
[research output accumulation](https://github.com/Rameshdandu1/gold_bitcoin/blob/81f86f79cb943c8cb837aae4f800135948f89f32/src/marketintel/research_engine.py#L842-L917).

The new 500-event input page is real. It does not bound the complete workflow: `quotes()` first
loads every quote observation for the symbol into a list, builds another quote list, then the paper
command filters by the current horizon. This occurs before checking whether that candidate has a
persisted unresolved arm. Candidate/decision collections also contain the full experiment rather
than only its current open working set.

The resource probe adds **1,000** or **8,000** valid unbound market quotes before candidate time to
the standard Gold fixture. Quotes have one-second spacing ending at -1 second, bid 2599.9 and ask
2600.1. Both cases have the same latest history, three candidate lifetimes, six provider results,
two outcome quotes per candidate and 12 target outcomes. Evidence hashes/counts are regenerated.
The added history cannot legitimately increase the simultaneously open candidate set.

Each public command runs in a fresh Python process. `tracemalloc` measures its Python allocation
peak; these are not total process RSS or Windows capacity estimates.

| Public command | 1,000 older quotes / 6,333 input rows | 8,000 older quotes / 13,333 input rows |
|---|---:|---:|
| Complete `run-workflow` peak bytes | 14,460,816 | 44,692,151 |
| `paper-workflow --maximum-events 100` peak bytes | 3,387,871 | 24,256,542 |
| Complete `paper-workflow` peak bytes | 5,669,300 | 36,581,091 |
| Complete paper elapsed time with allocation tracing | 5.037 seconds | 58.214 seconds |
| Quotes loaded per candidate by the complete paper path | 1,002 | 8,002 |

Both bounded 100-row paper calls report `maximum_quotes_per_candidate=0`, despite constructing the
full quote history before filtering it. Both complete calls report a maximum input batch of 500,
timeline batch of 13 and candidate count of three. Those counters cannot substantiate bounded total
memory. The measured growth is not caused by more simultaneous active positions.

**Correction:** query/stream only required point-in-time candidate intervals and predecessor
anchors in indexed batches; check unresolved eligibility before loading evidence. Persist bounded
rolling outcome/lifecycle state, retire resolved memory, page candidate/output projections, and
report allocations before filtering. A fixed row cap that silently discards required evidence is
not an acceptable correction. Use count/window assertions for stable regression tests and retain
machine-specific allocation measurements as acceptance evidence.

## Acceptance gate disposition

| Existing gate | Independent result |
|---|---|
| Exact P6-01 through P6-05 corrections | Pass in the finite retest matrix above |
| Shared predicates/source-loss/spread-drift examples | Implemented; existing tests pass |
| Full contemporaneous application/lifecycle parity | **Open: P6C-01 and P6C-02** |
| Derived checkpoint and fresh-process resume | Pass for warmup/provider fixture cases in the suite; independent BTC paper resume also passes |
| Whole-workflow memory bound | **Open: P6C-03** |
| Destination Windows and real service validation | Not performed; operational stage remains pending |
| Empirical edge and elapsed prospective evidence | Not established; evidence stage remains pending |

Resume success is qualified by the tested streams; P6C-01 must also recover deterministically after
ordinary intervening book observations. There is no reason to discard the new checkpoint mechanism
or reopen corrected findings without a failing regression.

## Next work and stopping rule

Follow [CODEX_PHASE_6_WORKFLOW_ACCEPTANCE.md](../../prompts/CODEX_PHASE_6_WORKFLOW_ACCEPTANCE.md).
Make three focused corrections, retain the five exact regressions, and rerun the specified
application parity, recovery and two-length resource matrix. Correct the status documentation as
part of this review; preserve original reports as historical executed evidence.

Once that finite software gate passes, stop feature work and move to the prepared
[Windows/live validation runbook](../WINDOWS_DEPLOYMENT.md). Actual machine recovery, licensed feed
coverage, CoinGlass entitlement, provider model access and a specifically authorized notification
need measured operational evidence. Prospective observation follows on frozen rules and common
opportunity denominators. Model agreement is not a calibrated probability or proof of an edge.
