# Phase 6 verification — evidence integrity and workflow acceptance

> Historical implementation report. The later independent review found P6-01 through P6-05 and
> three open software gates. Their offline disposition is recorded without rewriting this evidence
> in [phase-6-closeout-verification.md](phase-6-closeout-verification.md).

Date: 2026-11-22  
Platform: native Windows development workstation, Python 3.13 virtual environment  
Starting code: `dfbb59ea91bfc034f4ab4ffa76c0dbda094f5a31`  
Instruction revision: `413711c122f5a625a0ff78688d451aebd848e234`  
Final implementation code: `dcf4cbd` (`feat: enforce phase 6 evidence integrity`)

This report records software behavior observed with deterministic synthetic inputs, archived fake
provider completions and fake notification transports. It is not live-market, model-quality,
profitability or deployment evidence. No paid provider request, real notification, order or
deployment was made.

## Scope and migration path

The branch started from current `main`, not directly from the independently reviewed Phase 5 SHA.
Operational stores apply additive migration `0006_phase6_evidence_integrity` after migrations 0003
through 0005. Research stores add version-scoped `research_outcome_revisions`; the old outcome table
remains readable. Paper stores add a non-null consumed-prefix digest to cursor bindings. Existing
Phase 5 rows are not rewritten.

External paths remain off in `.env.example`: live ingestion, AI, alerts, paper collection and
trading are false. `TRADING_ENABLED=true` remains rejected and no order endpoint exists.

## Independent finding dispositions

| Finding | Reproduction / failing assertion | Correction | Passing evidence |
|---|---|---|---|
| P5-01 | A worker clock advanced after the first risk read; the reviewed code could authorize using the old cutoff and time. | Refresh the clock for each risk attempt and inside the write transaction; bind token and trade snapshot to one cutoff; persist actual authorization and evidence-freshness deadlines. | `test_p5_01_alert_authorization_uses_advancing_clock_and_fresh_evidence`; invalid case: zero fake sends and no authorization. Existing positive/retry/lease tests also pass. |
| P5-02 | A quote or provider row available 120 seconds late retained its earlier economic/completion time; contradictory synthetic provider rows could be presented under a prospective manifest. | Preserve event, completion and availability clocks; fill at the later actionable time; retain provider/model/request/configuration provenance; reject incompatible evidence modes. | `test_p5_02_delayed_quote_availability_is_the_actionable_fill_time` and public `test_p5_02_public_workflow_honors_provider_availability_and_rejects_mode_conflict`. AI arms become no-entry at/after expiry; conflict exits 2. |
| P5-03 | A source gap at candidate +1 did not stop provider-approved arms at +2/+3, and dirty-only scheduling evaluated each engine once. | Evaluate every configured cadence during input silence; persist decisions only when evidence becomes available; apply source state at provider readiness; expose a public connected paper command that derives outcomes from later journal events. | Source-gap regression yields rules incomplete and GPT/Claude/dual `WAIT`; public Gold/BTC commands exercise all six engines. Complete production-worker/shared-service parity and full derived-state resume remain open below. |
| P5-04 | An isolated target quote/bar after a missing pre-entry interval produced a complete win. | Require a pre-entry anchor and continuous pre/post-entry quote coverage; require contiguous OHLC intervals; retain incomplete and source-gap outcomes. | `test_p5_04_sparse_pre_entry_quotes_and_ohlc_paths_are_incomplete` returns `PRE_ENTRY_QUOTE_COVERAGE_INCOMPLETE` and `OHLC_PATH_GAP`. Existing bullish/bearish and continuous controls pass. |
| P5-05 | A crash between event write and cursor write left a non-resumable duplicate; same-length file replacement was silently skipped. | Commit paper event and cursor in one SQLite transaction; compare immutable duplicates before new-write chronology; bind identity/generation/cursor to a SHA-256 of consumed bytes. | `test_p5_05_paper_duplicate_replay_file_replacement_and_transaction_rollback` injects decision and outcome failures: records and cursor both remain at the prior boundary. Same-size changed content raises `content changed`; append/bounded-cycle tests pass. |
| P5-06 | An authenticated ordinary read exposed unopened protected outcome/P&L while no final-access record existed. | Centralize the ordinary read projection; withhold protected and crossing records from detail/count/report inputs until the frozen final-access action; display protected/opened state. | `test_p5_06_api_hides_protected_outcomes_until_final_holdout_open` inspects authenticated API and actual JSON/JSONL/Markdown/HTML/CSV export bytes. Crossing/protected identities are absent before access and present in API after the durable final action; unauthenticated coverage remains in the API suite. |
| P5-07 | A migrated legacy queued job without a complete frozen policy called both providers. | Apply preflight regardless of request version and quarantine an incomplete legacy request as `LEGACY_REQUEST_CONFIGURATION_INCOMPLETE`; do not synthesize fields from current settings. | `test_p5_07_legacy_request_configuration_makes_zero_provider_calls`: GPT calls 0, Claude calls 0. Current-format success and saved-result recovery tests still pass. |

The maintained P5-01 through P5-07 regressions were introduced against the reviewed behavior before
their corresponding corrections. They use the actual worker/store/public command paths where the
finding was an integration defect, not only detached calculation helpers.

## Complete automated checks

| Command | Result |
|---|---|
| `.venv\Scripts\python.exe -m pytest -q` | **237 passed**, one non-failing Starlette TestClient/httpx2 deprecation warning, 161.60 seconds |
| `.venv\Scripts\python.exe -m ruff check .` | All checks passed |
| `.venv\Scripts\python.exe -m ruff format --check .` | 85 files already formatted |
| `.venv\Scripts\python.exe -m compileall -q src tests` | passed, no output |
| `git diff --check` | passed; Git emitted only Windows LF-to-CRLF checkout notices |
| `npm ci` | 69 packages installed; existing esbuild install-script approval notice |
| `npm run typecheck` | passed with UI package 0.6.0 |
| `npm run build` | passed; Vite transformed 29 modules and emitted a 238.46 kB JS bundle |

The first sandboxed Vite attempt could not read the directory above the workspace. Repeating the
same production build outside that restricted filesystem sandbox passed in 910 ms. This was an
execution-environment restriction, not a source-code correction.

## Public Gold and BTC acceptance

The exact sequence, repeated for `gold` and `btc`, was:

```powershell
.\.venv\Scripts\python.exe -m marketintel.research_fixtures --output data\phase6-verification\fixtures
.\.venv\Scripts\python.exe -m marketintel.research validate-data --manifest data\phase6-verification\fixtures\<asset>-manifest.json
.\.venv\Scripts\python.exe -m marketintel.research run-workflow --manifest data\phase6-verification\fixtures\<asset>-manifest.json --config data\phase6-verification\fixtures\<asset>-experiment.json --database data\phase6-verification\<asset>-research.sqlite3 --production-database data\phase6-verification\production.sqlite3
.\.venv\Scripts\python.exe -m marketintel.research paper-workflow --database data\phase6-verification\<asset>-research.sqlite3 --paper-database data\phase6-verification\<asset>-paper.sqlite3 --production-database data\phase6-verification\production.sqlite3 --experiment-id phase5-<asset>-workflow-v1 --maximum-events 10000 --processing-delay-ms 25 --entry-latency-ms 10
.\.venv\Scripts\python.exe -m marketintel.research evaluate --database data\phase6-verification\<asset>-research.sqlite3 --production-database data\phase6-verification\production.sqlite3 --experiment-id phase5-<asset>-workflow-v1
.\.venv\Scripts\python.exe -m marketintel.research report --database data\phase6-verification\<asset>-research.sqlite3 --production-database data\phase6-verification\production.sqlite3 --experiment-id phase5-<asset>-workflow-v1 --output data\phase6-verification\<asset>-report
```

Generated runtime databases/reports are gitignored. Their reproducible definitions are
`marketintel.research_fixtures` plus the checked-in public CLI implementation.

| Asset | Input | Dataset hash | Config hash | Result |
|---|---:|---|---|---|
| Gold | 5,333 events | `04d5aee7b4043128c4a603cbc2d8b08f20ca0a21d77ea9bab7a06d1b70636c53` | `2d50ea0118d37932e561833f4a03dce971e9a3674239f3744dda3a05620e7d04` | 3 opportunities, 12 decisions, 12 outcomes |
| BTC | 5,333 events | `00290a5cb4cd05c226fc684a2831955ea317b86f7fda8d95e7b4a61d123cf4a3` | `537f2c835826666f4da8e6eda18c97e372ccca33341d580189e31b8dcc84f333` | 3 opportunities, 12 decisions, 12 outcomes |

Each paper command reported `SIMULATED_PROSPECTIVE_COMPLETE`, 5,333 events consumed, effective
entry latency 26 ms, 12 `SIMULATED_PROSPECTIVE` decisions and zero explicit gaps for the positive
fixture. Decisions precede derived outcomes. This classification is intentionally different from
real prospective observation.

The exported Gold `summary.json` checksum was
`5168489695ab53e326513136045a42fd062e5d5b52e3ee1a09a865edfd78bac3`; BTC was
`73c8a17b8ad447781e220fea80c8035e5fd859c165d3e5911a6416bf90127edf`.
Each report includes `SHA256SUMS`, the exact manifest/config, selected immutable records, CSV,
Markdown, HTML and JSON summary. Both remain classified `INSUFFICIENT_DATA`.

## Six-engine matrix and negative paths

| Engine | Cadence evaluations | Candidates | Admission/lifecycle/readiness/outcome evidence |
|---|---:|---:|---|
| GOLD_FAST | 241 | 1 | public normalized stream, frozen rules/GPT/Claude/dual arms, later quote outcome |
| GOLD_HOURLY | 241 | 1 | same shared scheduler and paper path |
| GOLD_SESSION | 241 | 1 | same shared scheduler and paper path |
| BTC_FAST | 241 | 1 | public normalized stream, frozen rules/GPT/Claude/dual arms, later quote outcome |
| BTC_HOURLY | 241 | 1 | same shared scheduler and paper path |
| BTC_SESSION | 241 | 1 | same shared scheduler and paper path |

The positive public runs exercise entry and target paths for all four arms per engine. Regressions
also exercise: provider availability +120 seconds (AI arms cannot use future evidence), source loss
before provider readiness (three AI arms wait), source loss after entry (all 12 BTC paper outcomes
become incomplete), sparse pre-entry data, post-entry gaps, OHLC gaps, expiry/no-entry, conflicting
evidence modes and interrupted event persistence. Existing suites preserve stop, drift, spread,
stale evidence, recovery, bullish/bearish and duplicate cases.

The scheduler now runs at every frozen cadence rather than only on dirty symbols. State is bounded
per symbol to 5,000 trades, 2,000 candles and 10,000 source transitions; journal persistence batches
500 observations. Earlier checkpoint regressions retain only 128 visibility IDs for a 1,000-event
prefix with a serialized checkpoint below 10 kB. Paper import has a bounded per-cycle cursor and
the connected command has `--maximum-events`.

## Atomicity, clocks and immutable evidence

- The advancing alert regression starts at candidate observation +1 minute and advances to +5
  minutes before authorization. The stale risk state suppresses delivery; fake Slack calls remain 0.
- Decision fault injection throws after the event write but before cursor binding. Transaction
  rollback leaves decisions 0 and cursor 0.
- Outcome fault injection starts from one committed decision/cursor 1, then throws at the same
  boundary. It leaves decisions 1, outcomes 0 and cursor 1.
- A consumed one-line source replaced by different same-length content under the same declared
  identity fails its prefix digest. Fully successful duplicate replay remains idempotent.
- Phase 6 outcomes are appended under `phase6-outcome-v1`; Phase 5 results remain available through
  the compatibility read path rather than being overwritten.

## Holdout and operator projection

Before access, ordinary authenticated experiment counts, opportunity pages and report inputs omit
both protected and boundary-crossing records. The regression reads the generated JSON, JSONL, CSV,
Markdown and HTML bytes and finds only the development identity. `final-holdout` records the frozen
configuration identity and `FINAL_EVALUATION` purpose before protected API records can be returned.
The experiment page then displays `HOLDOUT_OPENED`; it cannot reset the access record to unseen.

## External action accounting and unverified gates

Actual development-session external actions were:

- paid GPT/Claude requests: **0** (research uses archived synthetic completion rows; the legacy
  regression's fake transports each record 0 calls);
- real notifications: **0** (only fake Slack transports were constructed);
- orders/account operations: **0** (unsupported by the application);
- deployments: **0**.

The following remain open and must not be inferred from this offline acceptance:

1. One application service shared end-to-end by the production worker and historical scheduler for
   every admission, material-revision, lifecycle, risk and output step. The reviewed source/silence
   counterexamples are fixed, but full production/live-style parity is not yet proven.
2. Durable checkpoint/resume of the complete derived workflow (warmup, pending candidates,
   provider state, decisions and outputs) with identical final hashes. Event/cursor atomicity and
   visibility replay checkpoints are proven separately; the public workflow currently restarts
   idempotently from its isolated journal rather than resuming every in-memory component.
3. A long whole-workflow bounded-memory soak. Declared deques/batches are bounded, but the public
   connected paper adapter still materializes the selected normalized observations and timeline.
4. Licensed historical/market-depth coverage, genuine contemporaneous GPT/Claude evidence,
   sufficient independent day blocks and weeks of forward paper observation.
5. Any live Delta/CoinGlass soak, current provider entitlement/model validation, or authorized Slack
   delivery smoke test.
6. Destination Windows Server installation, Task Scheduler/service identity, reboot/restore,
   filesystem ACLs, HTTPS proxy, backup recovery, log rotation and sustained ingestion. Local native
   Windows commands passed; Phase 6 CI status is recorded by the PR, not by this local report.

These open gates block claims of operational readiness, model lift, predictive accuracy or
profitability. Read-only derivatives research and any separately authorized execution system remain
deferred.
