# Phase 5 verification — research completion and operational validation

Date: 2026-11-21 (Asia/Kolkata development environment; evidence timestamps are UTC).

> **Later independent review:** this report preserves the implementation team's original checks
> and dispositions. The [independent Phase 5 review](phase-5-independent-review.md) of merged main
> `dfbb59ea91bfc034f4ab4ffa76c0dbda094f5a31` independently passed the 227-test baseline and verified
> substantial corrections, but reproduced seven remaining issues. Its findings qualify the
> completion claims below, especially full workflow parity, evidence availability/provenance,
> path coverage, paper recovery, holdout detail protection, alert clocks and legacy-job preflight.
> Follow [CODEX_PHASE_6.md](../../prompts/CODEX_PHASE_6.md) for the next acceptance work. No historical
> test output below has been rewritten. Implemented dispositions and remaining limits are recorded
> separately in [phase-6-verification.md](phase-6-verification.md).

## Revisions and baseline

- Starting code: `3b07d21079729da41f53c80fa5c4604b1dea9499` (`origin/main`).
- Instruction/review branch: `3f8af4e929ab9fe6968726134300a1f33f505871`.
- Implementation branch: `feature/phase-5-research-completion`.
- Final implementation code revision (before release documentation):
  `5adfe3a57f847ecdf51f258f9e6e644e213c5929`.
- Reproduced pre-change baseline: 206 Python tests passed; Ruff lint/format, compilation,
  `git diff --check`, frontend `npm ci`, TypeScript and Vite production build passed. The only Python
  warning was the existing Starlette `TestClient` deprecation.

Mandatory red regressions were run before their fixes. Five tests failed: P4-06 dispatched after a
locally persisted stop breach; three P4-02 cases incorrectly produced target wins; and P4-03 placed
future/label-crossing rows in training. These tests are retained as maintainable regressions.

## Findings disposition

| Finding | Disposition and evidence |
|---|---|
| P4-01 | Corrected. `run-workflow` now connects normalized observations to production `detect_signal`, immutable four-arm decisions, quote evaluation and stored reports. |
| P4-02 | Corrected for the public quote/bar evaluator. Pre-entry stop/target, latency once, expiry equality, quote gaps, instrument validity and partial entry/expiry bars fail closed. |
| P4-03 | Corrected. Folds use earlier training only, purge overlapping label intervals, and exclude protected/crossing holdout rows from development metrics. |
| P4-04 | Corrected. One revision per opportunity is selected for reports; known abstentions are zero-position/cost observations, while unavailable evidence remains excluded. |
| P4-05 | Corrected. Paper evidence binds candidate/revision/target/config/source and rejects backfilled decisions, future outcomes and executed wins on rejected arms. |
| P4-06 | Corrected relative to locally persisted evidence. Delivery uses the shared current-risk gates and inserts immutable dispatch authorization in the same short transaction that checks revision/lifecycle/evidence/expiry/lease. |
| P4-07 | Corrected. Terminal/ineligible work creates typed zero-call dispositions before budget reservation or transport dispatch. |
| P4-08 | Corrected. Queued models, output cap, prompt/schema/risk/cost/pricing configuration are frozen and digest-bound; changed runtime configuration is not silently substituted. |
| P4-09 | Corrected. Saved results remain recoverable before the deadline; expired `RESULTS_READY` work becomes durable `WAIT`/`REVIEW_DEADLINE_EXPIRED` and is not reclaimed or redispatched. |
| P4-10 | Corrected. Dataset/config/checkpoint identities are recomputed, output writes are conflict-detecting, and evaluation/report versions are explicit. |
| P4-11 | Corrected for working state. Replay retains at most 128 diagnostic IDs, engine state is capped at 5,000 trades and 2,000 candles per series, and input sort/journal growth remains intentionally linear on disk. |
| P4-12 | Corrected for software/operator usability. Authenticated list/detail/engine/opportunity/paper APIs, dashboard states, public commands and authoritative exports use the selected stored experiment. |

Remote Slack acceptance remains at-least-once/receipt-uncertain according to Slack's response
boundary. The dispatch guarantee is not a claim of knowledge about exchange events that have not
yet been persisted locally.

## Public hypothetical workflows

Commands executed with the repository virtual environment (paths abbreviated here only for
readability):

```powershell
python -m marketintel.research_fixtures --output .phase5-fixtures
python -m marketintel.research validate-data --manifest .phase5-fixtures\gold-manifest.json
python -m marketintel.research run-workflow --manifest .phase5-fixtures\gold-manifest.json --config .phase5-fixtures\gold-experiment.json --database .phase5-fixtures\gold.sqlite3 --production-database .phase5-fixtures\production.sqlite3
python -m marketintel.research evaluate --database .phase5-fixtures\gold.sqlite3 --production-database .phase5-fixtures\production.sqlite3 --experiment-id phase5-gold-workflow-v1
python -m marketintel.research validate-data --manifest .phase5-fixtures\btc-manifest.json
python -m marketintel.research run-workflow --manifest .phase5-fixtures\btc-manifest.json --config .phase5-fixtures\btc-experiment.json --database .phase5-fixtures\btc.sqlite3 --production-database .phase5-fixtures\production.sqlite3
python -m marketintel.research evaluate --database .phase5-fixtures\btc.sqlite3 --production-database .phase5-fixtures\production.sqlite3 --experiment-id phase5-btc-workflow-v1
```

The generated runtime directory was deleted after verification. It is reproducible and excluded
from Git; no generated database or bulk synthetic JSONL is committed.

Artifact identities from that run:

| Workflow | Dataset hash | Configuration hash | Records | Opportunities |
|---|---|---|---:|---:|
| Gold | `d9d874925f018877eba2f782a3a384268c82704d1402579ed6bcd47bb51feb47` | `2d50ea0118d37932e561833f4a03dce971e9a3674239f3744dda3a05620e7d04` | 5,333 | 3 |
| BTC | `e056dabe1cf1d5bd207f7a8c83f278764e60d947ad3cde71cfe5faa41d80b332` | `537f2c835826666f4da8e6eda18c97e372ccca33341d580189e31b8dcc84f333` | 5,333 | 3 |

All inputs declare `SYNTHETIC_FIXTURE`; GPT/Claude completions are fake recorded parser evidence with
zero attributed cost. They are not historical provider performance.

### Six-engine replay/live-style parity matrix

The fixture generator first applies each normalized stream to the production detector to bind
candidate identities. The public workflow independently reconstructs state and calls the same
production detector. Each expected candidate identity was reproduced once.

| Engine | Public state | Candidate count | Rules-only entry UTC | Exit UTC | Outcome |
|---|---|---:|---|---|---|
| GOLD_FAST | CANDIDATE | 1 | 01:00:04 | 01:00:20 | TARGET_BEFORE_STOP |
| GOLD_HOURLY | CANDIDATE | 1 | 01:00:04 | 01:00:20 | TARGET_BEFORE_STOP |
| GOLD_SESSION | CANDIDATE | 1 | 01:00:04 | 01:00:20 | TARGET_BEFORE_STOP |
| BTC_FAST | CANDIDATE | 1 | 01:00:04 | 01:00:20 | TARGET_BEFORE_STOP |
| BTC_HOURLY | CANDIDATE | 1 | 01:00:04 | 01:00:20 | TARGET_BEFORE_STOP |
| BTC_SESSION | CANDIDATE | 1 | 01:00:04 | 01:00:20 | TARGET_BEFORE_STOP |

Times above are on 2026-11-19 UTC. Hand-checked rules-only economics (one hypothetical contract,
contract multiplier 0.001, one basis-point fee per side, one basis-point adverse slippage):

| Engine | Entry | Exit | Gross P&L | Fee cost | Net P&L |
|---|---:|---:|---:|---:|---:|
| GOLD_FAST | 2604.27 | 2613.74 | 0.009470 | 0.000521801 | 0.008948199 |
| GOLD_HOURLY | 2608.27 | 2627.74 | 0.019470 | 0.000523601 | 0.018946399 |
| GOLD_SESSION | 2607.27 | 2626.74 | 0.019470 | 0.000523401 | 0.018946599 |
| BTC_FAST | 70258.5 | 71189.5 | 0.9310 | 0.01414480 | 0.91685520 |
| BTC_HOURLY | 70608.5 | 72137.0 | 1.5285 | 0.01427455 | 1.51422545 |
| BTC_SESSION | 70607.5 | 71553.0 | 0.9455 | 0.01421605 | 0.93128395 |

The formula checked independently in acceptance tests is `(entry + exit) × 0.001 × 0.0001` for
fees, followed by `net = gross - fee`. These fixture results are software checks, not an edge.

## Recovery, scaling, partitions and paper chronology

- Each Gold/BTC public workflow was run twice against the same isolated database. Repeated journal,
  evaluation, decision and outcome writes were identical no-ops; conflicting identity tests fail.
- A 1,000-event replay retained 128 IDs and produced a checkpoint below 10 KB. The 5,333-record
  engine workflows measured maximum state of 5,000 trades per symbol and 100 candles in any series,
  below the declared 2,000-candle cap. The SQLite sort spool and immutable journal are O(n) disk.
- Trade and terminal-lifecycle insertion immediately before dispatch authorization both suppressed
  the confirmation. Wide-spread/drift and drift-only books were also suppressed.
- Default 90-second deadline/120-second lease recovery at second 121 terminated saved results and
  preserved the two provider records without reclaim or redispatch.
- Development reports select one actionable revision per opportunity. Label intervals crossing a
  frozen holdout are absent from metrics and folds. `final-holdout` requires the explicit
  `FINAL_EVALUATION` acknowledgement and records immutable access/configuration identity.
- A ten-day hand fixture preserved known GPT abstentions: rules-only operational P&L was -62.0,
  GPT abstention P&L was 0, and the paired mean difference was +6.2. Unavailable output was not
  converted to zero.
- The paper worker wrote the decision at 10:00:10, then accepted the 10:00:11 entry/10:00:30 outcome
  only in a later cycle. Restart was idempotent; source replacement and truncation were rejected.

## Checks and evidence limits

Final local checks:

- `python -m pytest -q`: **227 passed**, one existing Starlette deprecation warning.
- `python -m ruff check .`: passed.
- `python -m ruff format --check .`: 82 files formatted.
- `python -m compileall -q src tests`: passed.
- `git diff --check`: passed.
- `npm ci`: 69 packages installed; npm reported the existing esbuild allow-scripts notice.
- `npm run typecheck`: passed.
- `npm run build`: Vite 6.4.6, 29 modules; production build passed.

Native Windows commands, local paths, disabled startup, bounded paper execution, backup/restore and
shutdown instructions were updated. The available Windows development machine ran the commands
above. Task Scheduler installation, service reboot recovery, destination-host ACL/TLS/log rotation,
backup restore and long-running soak remain unverified.

External actions performed during development:

- Paid OpenAI/Anthropic calls: **0**.
- CoinGlass/Delta live calls: **0**.
- Real Slack notifications: **0**.
- Exchange orders/account/leverage operations: **0**.
- Deployments: **0**.

No adequate real historical dataset, genuine contemporary model history, licensed XAU reference,
prospective duration or empirical sample exists. Accuracy, probability, profitability, calibration,
annualized return and production readiness therefore remain **INSUFFICIENT_EVIDENCE**.
