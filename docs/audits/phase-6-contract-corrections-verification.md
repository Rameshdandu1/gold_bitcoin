# Phase 6 contract-corrections verification

All market prices, provider responses and outcomes used by this corrective work are hypothetical
synthetic software evidence. No live collection, paid provider call, real notification, order or
deployment is authorized by this report.

## Revisions and baseline

- Reviewed and starting code: `e9f419f5ef576ec957f9d59107ab3f7f06815b23`.
- Review/instruction revision: `5f0b1c7cac678ba255171f6c1e3da67d6033fcaa`.
- Corrective branch: `fix/phase-6-contract-corrections`.
- Windows-local CPython 3.12 worktree import: `.venv\Scripts\python.exe` with `PYTHONPATH` pinned to
  this checkout's `src`; 260 tests passed with one non-failing Starlette/httpx deprecation warning.
- Ruff lint/format, compilation, whitespace, clean frontend installation, TypeScript checking and
  the production frontend build passed at the baseline.

## Implementation plan

1. Make candidate plus initial `RULES_ONLY` persistence one recoverable store boundary and prove
   fresh-process convergence at the exact partial-write fault.
2. Persist historical trade occurrence and availability clocks plus per-target crossings, then feed
   the same facts into production, research, paper and restart paths.
3. Keep raw provider verdicts distinct from immutable individual-arm market dispositions; evaluate
   dual readiness from the verdicts and current facts. Require complete source, quote, instrument,
   ordering and executable-price evidence before a monetary outcome is complete.
4. Retire durable provider working state, page SQL before model construction, and stream report and
   export reads without changing revision or holdout semantics.
5. Re-run the exact red/green controls, full backend/frontend gates, Gold/BTC public workflows and
   checksum verification; record measured bounds and unperformed external gates here.

## Finding dispositions

| Finding | Corrected contract | Red / green evidence |
|---|---|---|
| P6W-01 | `save_candidate_with_initial_decision` exposes the candidate and deterministic `RULES_ONLY` arm in one SQLite transaction. Matching retries converge; conflicting payloads still fail. | On reviewed `e9f419f`, an aborting rules trigger left 1 candidate/0 rules. The corrected trigger rolls back both, a fresh public process reaches 3 candidates/12 decisions/3 opportunities/`COMPLETE`, and a repeat is idempotent. |
| P6W-02 | Trade `event_time_utc` must be on/after candidate observation; lifecycle occurrence retains event time while availability retains receipt time. | The late -0.1/+1 stop failed red and is ignored green. The +0.9/+1 stop remains terminal after recovery; bullish, bearish and benign controls pass. |
| P6W-03 | `research_target_crossings` stores immutable revision/target/source identity plus occurrence and receipt clocks. Provider, dual, outcome and paper entry receive visible crossed indices. | The 2700 Gold execution/recovery produced 12 incorrect target outcomes red and 12 no-entry dispositions green. A bearish target-1 crossing blocks target 1 while an uncrossed higher target remains independently evaluable. |
| P6W-04 | Individual decisions retain `raw_provider_verdict` and approved target indices separately from their immutable market disposition. Dual combines raw verdicts and runs a new market gate at its own readiness. | The exact +1.5 wide/+2 GPT/+2.5 healthy/+3 Claude case persisted dual `WAIT` red. Green preserves GPT `WAIT` but persists Claude and dual `APPROVED`; genuine provider `WAIT` remains blocked. |
| P6W-05 | A post-entry executed stop remains a terminal fact but complete P&L requires source, quote-gap and instrument continuity. The exit uses the next executable quote side, never the stop trade print. | The +4 entry/+100 stop/+150 quote case returned a complete priced stop red. Green returns `INCOMPLETE`, no exit price and no P&L for all original Gold arms. Bullish/bearish, source-loss and continuous quote-side controls pass. |
| P6W-06 | Provider observations are indexed durably and resolved provider objects retire after all dependent decisions persist. API/latest-revision/holdout filtering and report pages occur in SQLite before Pydantic construction; metrics/export are single-pass. | Reviewed page limit 1 constructed all 3 records and the two/eight-lifetime checkpoint retained 12/48 providers. Green API limit 1 constructs 1; a 600-opportunity report uses pages of at most 200. Standard Gold/BTC complete checkpoints retain 0 provider objects/2 serialized bytes while six durable provider rows remain per experiment. |

## Contract and migration handling

- Release: `0.6.2.0`; corrective code commit: `b8319ae`.
- Shared algorithm: `phase6-contract-corrections-shared-v4`.
- Derived checkpoint: `phase6-contract-corrections-derived-state-v3`.
- Outcome evaluator: `phase6-contract-corrections-outcome-v4`.
- Research databases add `research_target_crossings` and indexed
  `research_provider_completions`; existing immutable journal/outcome rows are retained.
- A v2 derived checkpoint is explicitly refused with a rebuild-under-new-experiment message. The
  old database is not deleted or overwritten. This prevents faulty outcomes from silently sharing
  a corrected scientific identity.

## Executed regression and resource evidence

The six focused probes were run against detached reviewed baseline `e9f419f`: **6 failed** for the
six documented reasons. The detached worktree was then removed. On the corrective branch:

- `tests/test_phase6_contract_corrections.py`: transaction/fresh-process, obsolete-checkpoint,
  late-trade, target/recovery, bearish target identity, temporary-book public workflow, provider
  WAIT, bullish/bearish stop coverage, source loss, public gap and 600-record paging cases pass.
- The exact earlier unchanged-book, GPT checkpoint, output-before-checkpoint, stop/recovery,
  benign recovery, 1,000/8,000 irrelevant-history, paper retirement and protected-holdout controls
  remain green. The combined workflow/closeout selection passed 23 tests.
- Complete public workflows report maximum active candidates 3, active provider completions 0,
  active provider JSON bytes 2 (`[]`), quote page/materialization 6 and source page 0. Paper reports
  maximum active candidates 3, retired candidates 3, maximum input batch 500 and quote page 6.
- The 600-opportunity projection test returns all exact records without truncation, constructs one
  API model for `limit=1`, and observes report pages `200,200,200` before the terminal empty page.
  This is a retained-object/model-materialization measurement, not an RSS claim.

## Verification gates

| Command | Result |
|---|---|
| `python -m pytest -q` | **272 passed**, one existing Starlette/httpx deprecation warning; CPython 3.12.10 |
| `python -m ruff check .` | Passed |
| `python -m ruff format --check .` | Passed; 103 files formatted |
| `python -m compileall -q src tests` | Passed |
| `git diff --check` | Passed |
| `npm ci --no-audit --no-fund` | Passed; 69 packages; npm reported the existing pending esbuild install-script approval warning |
| `npm run typecheck` | Passed with Node 24.18.0 / npm 11.16.0 |
| `npm run build` | Passed after granting the build read access blocked by the filesystem sandbox; Vite built 29 modules |
| Hosted Windows CI | **Passed** — PR #17 CI run 73 (`45017814906`), backend and frontend jobs, head `411b879` |

## Public Gold/BTC workflows and hashes

Both generated fixtures were explicitly `SYNTHETIC_FIXTURE`, with 5,333 validated observations.
For each asset, public `validate-data -> run-workflow -> paper-workflow -> evaluate -> report`
returned zero. Each workflow exercised FAST/HOURLY/SESSION, produced 3 opportunities and 12 arm
decisions, and the connected paper command recorded 12 decisions/12 outcomes before retirement.
The report classification remains `INSUFFICIENT_DATA` at each arm metric; synthetic net-P&L values
are not empirical performance.

| Asset | Dataset hash | Config hash | Verified report entries | `SHA256SUMS` file hash |
|---|---|---|---:|---|
| Gold | `2380d95bf81e7046484f8a049ce8b68aa35990e8d89aac71e0046752a5ae87ac` | `080f75ab09e7c25032051fe47cfe25f4440317c77cab3c7cda820c52752035c6` | 9 | `66cb32fbecede0dee0f413cdca10c2a9ca63e66d113e1644457c7ee4840a5658` |
| BTC | `900389b234b0f368a0654272f9a43b50dc7c2136809003a18137c800f9cde527` | `ba1bce1c8040e87b076e2baffef8fb40de68d5f28f029d9210cf606fd985d276` | 9 | `761f1a2b2a3aa19f2a357e53bedb9400125dd227f171f3d0778230c3f4f5778d` |

All report-listed hashes were recalculated successfully. These artifacts are local ignored
verification outputs, not committed market data.

## Offline operational preparation

- `docs/audits/operational-validation-template.md` separates local, hosted Windows, destination
  Windows, live endpoint, provider and notification evidence using `PASS/FAIL/BLOCKED/NOT_RUN`.
- `docs/OPERATIONAL_VALIDATION_COMMAND_PACK.md` uses existing bounded verification, backup,
  health and public research commands; it contains no enable-all or deployment action.
- `config/prospective-experiment.template.json` predeclares all six engines/four arms, source/config
  identities, missing-data/holdout/cost fields and evidence thresholds. It is valid JSON but
  intentionally `NOT_AUTHORIZED_NOT_STARTED`; monetary/request/sample limits remain null until an
  operator supplies and authorizes them.

## External validation

Destination Windows Server recovery, current Delta/CoinGlass/provider entitlement, authorized
notification delivery and elapsed prospective observation are `NOT_RUN`; the offline corrective
task has no credentials or authorization for those checks.

No live market collection, paid AI request, real Slack message, order, deployment or destination
host action occurred. Gold reference remains `BLOCKED` because the production adapter is unwired;
Liqwall, heatmaps, options and execution remain outside scope. Passing software checks do not claim
signal accuracy, probability, profitability or readiness to trade.
