# Phase 6 closeout verification

Date: 2026-11-22. Scope: offline evidence integrity and complete workflow acceptance only.

> **Later independent disposition, 2026-11-22:** This implementation report is retained as the
> original executed evidence. The [independent closeout review](phase-6-closeout-independent-review.md)
> at `81f86f79cb943c8cb837aae4f800135948f89f32` confirms P6-01 through P6-05 and tested resume controls,
> but reproduces P6C-01/02 contemporaneous decision/lifecycle failures and P6C-03 whole-workflow
> memory growth. The full shared-policy and bounded-memory acceptance claims below are therefore
> qualified; those two existing gates remain open. Follow
> [CODEX_PHASE_6_WORKFLOW_ACCEPTANCE.md](../../prompts/CODEX_PHASE_6_WORKFLOW_ACCEPTANCE.md).

## Frozen identities and evidence limits

- Starting code: `f66ac11f4d958a0075d7e22a5d841256e19b55df` (merged PR #10).
- Instruction/review revision: `6495ee72e1be835a7c75fe8eea12456c6fdbec7e`.
- Primary implementation commit: `1651888` (`feat: close phase 6 evidence integrity gaps`).
- Shared algorithm contract: `phase6-closeout-shared-v2`.
- Outcome revision: `phase6-closeout-outcome-v2`.
- Derived checkpoint schema: `phase6-closeout-derived-state-v1`.
- Paper processing contract: `phase6-closeout-paper-v1`.

All market/provider rows in the acceptance bundle were repository-generated `SYNTHETIC_FIXTURE`
evidence. External calls, live exchange/CoinGlass collection, paid model calls, real notifications,
orders and deployment were zero. Passing tests do not establish prediction accuracy, model lift or
profitability.

## Finding disposition

| Finding | Exact regression and correction | Disposition |
|---|---|---|
| P6-01 | A parsed/checksum-valid book with event 10:00:51, receipt 10:00:59.900, evaluation 10:01:00 and authorization 10:01:02 now suppresses with zero fake sends. Authorization uses the earliest event-time and receipt-time validity limit. The healthy delay and original stop/expiry/lease cases remain covered. | Closed offline |
| P6-02 | Public Gold workflows with provider or quote envelope availability delayed 120 seconds while the payload retains the original timestamp now return a typed validation error. Omitted-field fallback remains valid. Archived completions/decisions carry optional requested/returned model IDs; old unknowns stay `null`. | Closed offline |
| P6-03 | Bullish and bearish +0 anchor / +150 readiness-entry / +155 target cases with a 10-second gap return `INCOMPLETE`. An incomplete +0..30 pre-entry bar cannot establish coverage for a +30..40 target bar. | Closed offline |
| P6-04 | Paper evidence binds experiment, config, dataset hash, partition, run and processing policy. Before final access, a holdout-at-candidate experiment produces zero paper rows; authenticated API and export bytes expose none. After durable `FINAL_EVALUATION`, rerun produces 12 visible target outcomes. Legacy rows without provenance do not enter scoped projections. | Closed offline |
| P6-05 | Missing Claude and both-providers-late Gold public workflows persist all 12 arms and terminal unavailable/no-position outcomes without chronology errors or fabricated fills. Repeats are immutable/idempotent. A 100/5,333 run reports warmup partial with 5,233 remaining and resumes to the uninterrupted result. | Closed offline |

## Three prior acceptance gates

1. **Shared policy:** `application_policy.py` is used by production consensus and connected
   research for revision, lifecycle, expiry, evidence clock, source, stop, book geometry, spread and
   entry drift. Actual public detector workflows plus production consensus tests cover source loss
   and spread/drift rejection. The positive Gold/BTC workflows cover all six engines. Transport
   configuration and production persistence remain deliberate adapter differences.
2. **Complete derived resume:** `derived_workflow_checkpoints` stores manifest/config identities,
   input offset, next evaluation, bounded normalized feature/source state, provider completions and
   counters. A test stops after 100 warmup rows, again after the first provider row, then resumes in
   fresh Python processes. Its opportunities, engine matrix and final canonical state match an
   uninterrupted run. Changed experiment/source/config identity is refused by immutable checks.
3. **Bounded public workflow:** research state is capped at 5,000 trades/symbol and 2,000
   candles/series; normalized input and paper timelines process at most 500 rows per batch. The
   5,333-row Gold paper run measured maximum input batch 500, timeline 13, active candidates 3 and
   quotes/candidate 2. The 100-row prefix measured input batch 100. A larger simultaneous open-set
   legitimately raises the reported active-candidate count and must be capacity-tested with live
   workloads.

## Additive storage changes

Research database initialization adds `derived_workflow_checkpoints`. Paper initialization adds
`paper_workflow_runs` and nullable provenance columns on `paper_decision_evidence` for safe upgrade.
Existing evidence is not rewritten. Rows without sufficient experiment/partition provenance are
conservatively absent from experiment-scoped API/export projections. There is no destructive
down-migration; rollback requires stopping writers and restoring the matching pre-upgrade databases.

## Verification commands and results

Initial baseline before edits:

- `python -m pytest -q`: **237 passed**, one existing Starlette/httpx2 deprecation warning.
- Ruff lint/format, compilation, frontend typecheck and frontend production build: passed. The Vite
  build required the normal sandbox permission because esbuild traverses outside the workspace.

Final local verification:

- `python -m pytest -q`: **251 passed**, same single deprecation warning.
- `python -m ruff check .`: passed.
- `python -m ruff format --check .`: passed.
- `python -m compileall -q src tests`: passed.
- `git diff --check`: passed.
- `npm ci --no-audit --no-fund`, `npm run typecheck`, `npm run build`: passed; no dependency or
  application network integration was exercised.

The closeout regression file uses actual parser/assembler/store/worker paths, public commands,
advancing clocks, fake transports, authenticated API bytes and fresh-process subprocesses. No paid
transport is instantiated.

## Public Gold/BTC acceptance

For each asset, the following public commands were run in order: `validate-data`, `run-workflow`,
`paper-workflow`, `evaluate`, and `report --paper-database ...`. Both manifests validated **5,333**
observations. Each asset produced three opportunities (FAST, HOURLY, SESSION), 723 scheduled engine
evaluations, 12 decisions and 12 outcomes. Paper status was
`SIMULATED_PROSPECTIVE_COMPLETE`, with 5,333/5,333 input events, zero pending arms, maximum input
batch 500 and no external actions.

This constructed path produced target outcomes for every arm. That fact is only a positive software
fixture and is not an empirical result. `evaluate` correctly labelled both three-opportunity reports
`INSUFFICIENT_DATA` because there was one independent day block.

The report bundle includes the authoritative manifest/config, partition-selected opportunities,
paper summary/transitions and `SHA256SUMS`. Final hashes are recorded from the final acceptance run;
they must be regenerated if the fixture/config contract changes.

| Asset | Dataset hash | Config hash | `SHA256SUMS` file hash |
|---|---|---|---|
| Gold | `156251669880576df29d52bdacb08bc7cbc99738c2c81d9dab0f74cc8deb0b56` | `5e638461d6e03071da25a674b0ccb342f8894d7ba85798bc46d8c57039d1509d` | `88d6a4b3245070aaf654362f148c4d2689f76661a15a580aefe0d1b705f10e7b` |
| BTC | `fcd4e0c44d9edb9f620d0c4a7dc299b6af6359a226bd773e011f8a07e626f8a7` | `6d027c68e290b5a8e977ffead555c52fd466c0266b78ec14ba9aa4de5733c235` | `09d6b433a3c5ba9436240939f4b24b225e6f1f63c80f8f58706e59c6186bdeda` |

## Recovery and negative-state evidence

- Approved paper entry remains strictly after the durable decision and before expiry. Non-approved
  terminal evidence follows a separate no-entry rule and cannot receive an executed target/stop.
- Run identity includes experiment, canonical config, dataset hash, processing delay, effective
  entry latency and holdout state. A changed policy cannot silently reuse progress.
- Input completion, warmup partial, bounded partial, unresolved, holdout-protected and complete are
  distinct statuses. Equality of zero decisions and zero outcomes never means completion.
- Paper API and exports use the same experiment/holdout projection. Authentication does not open a
  holdout; only the durable final action does.
- Checkpoints advance after immutable batch output. A fault before advancement safely retries the
  same batch; identical writes are idempotent and conflicts fail.

## External prerequisites still pending

These are intentionally not software-closeout defects: destination Windows Server service/ACL/
reboot/restore evidence; current Delta instrument/unit and reconnect soak; CoinGlass entitlement and
pair coverage; licensed Gold reference data; configured/returned live GPT and Claude model access
under explicit spend limits; one authorized notification destination/receipt; and genuine elapsed
prospective evidence with adequate independent samples. Follow `docs/WINDOWS_DEPLOYMENT.md` for the
bounded validation sequence. `TRADING_ENABLED=true` remains refused and no execution endpoint exists.
