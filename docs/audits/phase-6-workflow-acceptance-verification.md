# Phase 6 workflow acceptance verification

Verification date: 2026-11-22 (Asia/Kolkata). Application and fixture clocks are UTC. All prices,
provider rows and outcomes in this report are synthetic software evidence, not observed performance.

**Later independent disposition:** The
[independent workflow-acceptance review](phase-6-workflow-acceptance-independent-review.md) at merged
`e9f419f5ef576ec957f9d59107ab3f7f06815b23` preserves this report's executed cases and confirms the
original corrections. It also reproduces P6W-01 through P6W-06 in recovery, event/target facts, dual
gating, outcome coverage and whole-workflow state/output bounds. This report remains historical
implementation evidence; its complete-acceptance statements are qualified by that later review.

## Scope and identities

- Starting code: `81f86f79cb943c8cb837aae4f800135948f89f32`.
- Instruction/review branch: `a596fcee2c824c9e3d372df27d628359ecf404e5`.
- Implementation code commit: `5a7cbaa0c20209634a62a3cc50517724d0eef0bb`.
- Branch: `fix/phase-6-workflow-acceptance`.
- Release version: `0.6.1.0` (corrective patch; no strategy expansion).
- No live collection, paid model request, real notification, order, deployment or destination-host
  operation was performed.

The corrected scientific contract versions are:

| Contract | Version |
|---|---|
| Shared algorithm | `phase6-workflow-acceptance-shared-v3` |
| Derived checkpoint | `phase6-workflow-acceptance-derived-state-v2` |
| Outcome evaluation | `phase6-workflow-acceptance-outcome-v3` |
| Paper processing | `phase6-workflow-acceptance-paper-v2` |

`research_lifecycle_events` and its availability index are additive SQLite objects. Existing
scientific rows are not rewritten. A v1 derived checkpoint is explicitly refused with a rebuild
message; corrected work must use the new algorithm/configuration identity and a fresh isolated
experiment/database. The immutable experiment check prevents silently mixing a v3 run into a v2
experiment ID. Prior reports remain historical artifacts.

## Finding dispositions

### P6C-01 — contemporaneous immutable decisions: fixed

The exact Gold fixture was amended with an unchanged generation/sequence-2 book at +21 seconds and
+2.5 seconds. Before the correction both public commands failed with `Arm decision identity is
immutable`; the first left 12 decisions and no opportunities, and the second left the three rules
plus three GPT decisions and no opportunities. Both variants now finish with three opportunities,
12 immutable decisions/outcomes and a `COMPLETE` checkpoint.

Individual provider arms are created only if absent, using facts visible at their own readiness.
The dual arm combines the two persisted individual decisions and reruns revision, lifecycle,
freshness, book, spread, drift and target-economics checks at the later readiness. Final outcome
derivation reloads stored decisions rather than rebuilding them from the last book. A deliberate
different-payload retry still raises `Arm decision identity is immutable`.

The factual ordering is availability time, persistence sequence and immutable observation ID.
Provider payload availability must match its envelope. After entry, equal-time
executed-stop/quote ordering without a stronger fact is classified `AMBIGUOUS`, not guessed.

Recovery evidence:

- A fresh process resumed after all GPT results were durable but before the +2.5-second book and
  Claude results. Its decisions, lifecycle events, outcomes and final checkpoint state matched an
  uninterrupted run.
- A fault injected after opportunity/output persistence but before the `COMPLETE` checkpoint left
  `INPUT_COMPLETE`; retry converged to the same immutable opportunities without duplicates or
  changed scientific timestamps.
- Existing changed-manifest/configuration refusal and warmup/provider resume tests remain in the
  complete suite.

### P6C-02 — application/lifecycle parity: fixed for the finite offline matrix

The exact Gold public stream added an executed trade at exchange +0.900/receipt +1.000 seconds at
2594.8, followed by recovery at exchange +1.400/receipt +1.500 seconds at
2599.2285714285713. All three Gold candidates now retain an immutable
`EXECUTED_STOP_BREACH` lifecycle event. The rules arm reports
`EXECUTED_STOP_BREACH_BEFORE_ENTRY`; provider arms are blocked by lifecycle/stop policy, and none
of the 12 arms invents a later target fill. A benign 2599.0 update plus recovery preserves the 12
healthy target fixture outcomes.

The production lifecycle transition and research lifecycle adapter share
`executed_stop_breached`. Production consensus and research share current target feasibility,
including configured fee/slippage and minimum net reward/risk. Research supplies persisted current
revision, source, trade/book age and terminal facts instead of constant lifecycle/revision values.
Clock evaluation persists expiry without waiting for another input row.

A bearish post-entry breach at 106 followed by a quote recovery is classified
`STOP_BEFORE_TARGET/EXECUTED_STOP_BREACH_AFTER_ENTRY`, with the original entry retained. This is
distinct from the no-position pre-entry case. Source loss and wide spread/drift continue to block
the connected research/provider arms and production consensus in the established regressions.

Finite parity evidence by case:

| Case | Evidence and result |
|---|---|
| Healthy candidates/providers | Public Gold/BTC workflow uses all six detectors; one accepted revision per engine, three opportunities and 12 arms per asset. |
| Long stop then recovery | Exact public Gold path invalidates FAST/HOURLY/SESSION; no later entry/win. |
| Short stop then recovery | Shared production stop predicate plus quote evaluator preserves a post-entry bearish stop through recovery. |
| Source loss during review | Existing public connected-research and production-consensus regression remains WAIT/fail-closed. |
| Spread/entry drift | Existing public connected-research and production-consensus regression remains WAIT with the same failed gate. |
| Target/cost/net reward-risk | Production consensus and research use the same target-feasibility helper; target exhaustion remains fail-closed. |
| Expiry/source aging in silence | Cadence expiry is durable; book/trade age is evaluated at provider readiness. |
| Late candle/book | The two unchanged-book counterexamples prove later evidence cannot alter earlier decisions. |
| Revision and retry | Current revision is read from durable candidate history; conflicting same-identity decisions still fail. |

The production worker keeps its production `Store` and alert transport checks; research/paper use
isolated stores and never require Slack credentials. That persistence/transport difference is
intentional and does not change the shared market/lifecycle predicates.

### P6C-03 — bounded complete processing: fixed for measured histories

The normal path queries indexed quote/source evidence by experiment, symbol and candidate interval
in 500-row pages. It checks persisted/unresolved arms before evidence loading. Candidate projection
uses 200-row pages, the active set is bounded by concurrent candidates, and all three fixture
candidates are retired after terminal paper outcomes. No fixed truncation cap discards required
candidate-window evidence.

Fresh-process measurements used `scripts/phase6-workflow-memory-probe.py` on
`Windows-10-10.0.19045-SP0`, CPython 3.12.10. `tracemalloc` measures Python allocations only, not
total RSS or destination Windows Server capacity.

| Public command | 1,000 older quotes | 8,000 older quotes |
|---|---:|---:|
| Complete `run-workflow` peak bytes | 13,250,269 | 14,313,785 |
| Complete `run-workflow` seconds | 15.790155 | 18.320000 |
| Paper first 100 events peak bytes | 381,870 | 381,767 |
| Complete paper peak bytes | 2,892,217 | 3,068,828 |
| Complete paper seconds | 1.232573 | 2.890972 |
| Maximum quote rows materialized before opportunity filtering | 6 | 6 |
| Maximum quotes retained per candidate | 2 | 2 |
| Maximum active candidates / retired at completion | 3 / 3 | 3 / 3 |

Both warmup calls loaded zero quote rows, retained zero active candidates and reported
`SIMULATED_PROSPECTIVE_WARMUP_PARTIAL`.
Both complete calls recorded 12 decisions and 12 outcomes. The three canonical opportunity records
were identical across lengths. The measured allocation delta is overhead from reading the larger
input journal, not growth in active candidate/quote state; the structural CI assertions remain the
portable acceptance threshold.

## Public workflow evidence

Both generated manifests validated 5,333 records with valid checksums/sequence metadata.

| Asset | Dataset hash | Config hash | Engines/evaluations | Research | Paper |
|---|---|---|---:|---:|---:|
| Gold | `10ea736afd7e9d042bae1ee9a4736796aa8c179edc4a778409d4ca966490ef7f` | `ffc551dd91d1457670f4f882abc87c5ba6cfe44b6d2ccf2de2eb862eefbf1d3e` | 3 × 241 | 3 opportunities / 12 arms | 12 decisions / 12 outcomes |
| BTC | `0c8657e033a6b6d4d679523a24b6b5688418861efc3087fac0a96509d0bd0742` | `0535b0d3516e404e1c0bf2eba3508d454d01161f9325228edcda4876a0e1c6c7` | 3 × 241 | 3 opportunities / 12 arms | 12 decisions / 12 outcomes |

`validate-data`, `run-workflow`, `paper-workflow`, `evaluate` and `report` all returned zero for
both assets. Each report produced ten files and every `SHA256SUMS` entry verified. The constructed
target outcomes and nonzero hypothetical P&L are fixture behavior; paired day blocks correctly
remain `INSUFFICIENT_DATA` and do not establish accuracy, probability, lift or profitability.

## Automated checks and external gates

The reviewed baseline reproduced as 251 passing tests. The final local suite passed 260 tests with
one non-failing Starlette/httpx deprecation warning. The corrective suite adds exact public
counterexamples, conflict/recovery controls, bearish/benign lifecycle controls and both history
lengths. Ruff lint, Ruff format check, compilation and `git diff --check` passed. `npm ci`, frontend
TypeScript and the Vite production build passed. GitHub Actions Windows CI
[run 44993204955](https://github.com/Rameshdandu1/gold_bitcoin/actions/runs/44993204955) passed both
the backend and frontend jobs on pull-request head `bccc999395a70520268b78d537bd460e32300a27`.
Destination Windows Server validation is still pending.

External action observations during this work: zero paid provider calls, zero live collection,
zero real notifications and zero orders. This was verified by using only generated manifests,
archived synthetic provider rows, isolated SQLite paths and public commands with no external
transport configured; it is not inferred solely from hard-coded counters.

Destination Windows Server service identity/ACLs, reboot/restore, clock health and long-running
capacity remain pending. Delta current instrument discovery/units and gap recovery, licensed Gold
or reference coverage, CoinGlass entitlement, configured GPT/Claude account/model usage, and one
authorized notification receipt remain pending external prerequisites. Follow
`docs/WINDOWS_DEPLOYMENT.md`; after those gates, freeze the prospective paper experiment before
collecting elapsed evidence.
