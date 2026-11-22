# CODEX TASK — close the six reviewed contracts, then prepare operational validation

## Goal and first instructions

Review and correct **P6W-01 through P6W-06** in the
[independent workflow-acceptance review](../docs/audits/phase-6-workflow-acceptance-independent-review.md).
The reviewed baseline is **`e9f419f5ef576ec957f9d59107ab3f7f06815b23`**, merged PR #15.
The original later-book, stop/recovery and irrelevant-quote corrections work; preserve them.

1. Inspect `git status`, branch, recent history and remote. Preserve unrelated work. Fetch main and
   record the actual starting SHA; compare any newer changes before assuming a finding remains open.
2. Read `AGENTS.md`, `DESIGN.md`, `README.md`, `docs/IMPLEMENTATION_PLAN.md`, the independent review,
   this task, the relevant source/tests and `docs/WINDOWS_DEPLOYMENT.md`.
3. If this documentation is not on main, fetch its branch and read the exact files before coding:

   ```bash
   git fetch origin refs/heads/docs/phase-6-acceptance-review:refs/remotes/origin/docs/phase-6-acceptance-review
   git show origin/docs/phase-6-acceptance-review:prompts/CODEX_PHASE_6_CONTRACT_CORRECTIONS.md
   git show origin/docs/phase-6-acceptance-review:docs/audits/phase-6-workflow-acceptance-independent-review.md
   ```

4. Create `fix/phase-6-contract-corrections` from current main, with an isolated worktree if needed.
   Carry the review/task documentation if absent. Do not force-push, reset another branch or merge
   unrelated work. Use a suitable unused branch suffix if necessary.
5. Reproduce the **260-test baseline**, static checks and applicable frontend checks. Ensure imports
   resolve to the intended worktree, especially when reusing an editable installation.
6. Write a short implementation plan for the transaction, event-fact, provider-verdict and paging
   boundaries. Add meaningful failing tests before each correction. Implement packages A-D below;
   do not stop at a plan or merely rerun the old positive fixtures.
7. Complete authorized offline code, tests, documentation and operational preparation; push the task
   branch and open a reviewable PR. Do not auto-merge, deploy, enable external flags or send messages.

## Coding and evidence rules

- Preserve native Windows, Python/FastAPI, React/TypeScript, the six engines, four comparison arms,
  strategy thresholds, current database separation and source/provenance contracts.
- No orders, trading/account credentials, leverage controls, strategy expansion, stack migration,
  new Liqwall integration, additional CoinGlass endpoints, options or notification channels here.
  The recent provider comparison is planning context, not authorization for feature expansion.
- Keep live ingestion, paid AI, alerts and prospective collection disabled by default;
  `TRADING_ENABLED=true` remains rejected. Use fake providers and synthetic data for this task.
- Separate exchange occurrence, factual availability, model completion, arm decision time, actual
  persistence, eligible entry and outcome observation. Use UTC-aware clocks and Decimal boundaries.
- Provider verdict, individual-arm market disposition, candidate lifecycle and execution-outcome
  completeness are distinct facts. Do not encode one as another to simplify a branch.
- Preserve immutable IDs/payloads, valid identical retries and conflict rejection. Never make a test
  pass by suppressing a conflict, overwriting history, omitting an arm or weakening production gates.
- Share applicable decision rules with equivalent factual inputs. Compare actual stores/workers and
  public commands; two preconstructed agreeing eligibility objects do not establish application parity.
- Keep network work outside transactions. Preserve dispatch/receipt uncertainty, budget fencing,
  current revision, expiry, source freshness and target indices.
- Version changed scientific/checkpoint contracts. Give old experiments a documented safe migration
  or explicit refusal/rebuild route. Do not silently reuse faulty outcomes under the same identity.
- Page before materialization, keep only necessary active state and retain historical evidence
  durably. Do not use an arbitrary truncation cap or erase evidence to produce a memory bound.
- No secrets, account exports, licensed raw datasets or local databases in commits/logs. Label every
  constructed price, trade, provider answer and result hypothetical/synthetic.

## Package A — recover candidate and initial rules decisions (P6W-01)

Reproduce the failure after `save_candidate` commits and before the first `RULES_ONLY` write.
Ordinary fresh-process resume currently reaches 3 candidates, 11 decisions, 2 opportunities and
`KeyError: 'RULES_ONLY'`; a second resume repeats it.

Make candidate plus initial rules decision atomic, or recover a missing rules decision from its
original deterministic boundary. An existing candidate is not sufficient evidence that every
dependent scientific record exists. Preserve the factual timestamp and original payload.

Acceptance:

1. Fault at this exact boundary; restart in a fresh process through public `run-workflow`; compare
   with uninterrupted output. Require 3 candidates, 12 arms, 3 opportunities, equal lifecycle/outcomes
   and `COMPLETE`. Repeat completion to prove idempotence.
2. Preserve fresh-process resume after GPT and before the +2.5 book/Claude, and the existing
   output-before-checkpoint fault control. A deliberately conflicting payload still fails.

Explain how an already partial database is recognized and repaired or refused without deleting it.

## Package B — preserve equivalent historical market facts (P6W-02 and P6W-03)

### B1. Late historical trade versus a new stop

Use the standard Gold candidate time `2026-11-19T01:00:00Z`. Parse trades with the real parser and
preserve the original candidate/provider bindings. These are hypothetical prices:

| Case | Stop event | Receipt | Stop price | Recovery event/receipt and price |
|---|---:|---:|---:|---|
| New stop | +0.9 s | +1 s | 2594.8 | +1.4/+1.5 s, 2599.2285714285713 |
| Historical stop delivered late | -0.1 s | +1 s | 2594.8 | Same recovery |

Production correctly distinguishes them. Research currently invalidates both and writes occurrence
as receipt time. Preserve both clocks and apply equivalent event/receipt bounds; never reveal a
late fact before receipt or apply a pre-candidate execution as a new candidate stop.

Require actual production lifecycle/current-risk and public research/paper comparisons for bullish
and bearish variants. New post-observation stops remain terminal after recovery and restart;
pre-observation late trades do not create that terminal fact. Retain benign update/recovery controls.

### B2. Executed target crossings persist through recovery

Add an executed Gold trade at event +0.9 / receipt +1, price 2700, then the original recovery
+1.4/+1.5. Keep provider readiness +2/+3 and executable quotes +4/+20. Current research incorrectly
credits the original 12 target outcomes although production rejects approved target 1 as exhausted.

Persist/reconstruct per-target executed crossing facts with event time, receipt cutoff, revision and
source identity. Apply them to provider readiness and pre-entry eligibility, with the same policy as
production. A current-price helper must not forget an earlier crossing.

Acceptance examples:

1. Target 1 crosses and price recovers: target 1 cannot be reused for a later entry; a higher target
   remains governed by its own crossing history, approved indices and current economics.
2. All approved targets cross, versus no target crossing: the first has no feasible entry and the
   healthy control keeps its original outcomes. Include bearish directions and restart after the
   crossing but before provider completion/entry.

Do not retrospectively change a provider answer or a rules decision made before the crossing.
Record the later eligibility/no-entry fact separately and preserve all arm denominators.

## Package C — independent arm gates and honest outcomes (P6W-04 and P6W-05)

### C1. Separate provider verdict from the individual market gate

Reproduce the exact temporary-book case:

- +1.5: bid 2600 / ask 3000; +2: GPT returns CONFIRM.
- +2.5: book restored to bid 2599.9 / ask 2600.1; +3: Claude returns CONFIRM.
- Use the same configured spread/drift, cost/RR and target-index policy in both applications.

The GPT-only arm's +2 WAIT is correct and immutable. The dual arm at +3 must use the two matching
provider verdicts and its own current market/lifecycle gate. It must agree with the real production
review-worker path, which confirms the three Gold cases. Never describe a failed entry gate as a
provider WAIT.

Acceptance examples:

1. Temporary spread failure recovers before dual readiness: GPT-only remains WAIT; Claude/dual are
   eligible when the actual later gates pass. Persist the corrected arm through paper and reports.
2. Actual provider WAIT/REJECT, continuing wide spread at +3, or a terminal executed stop before
   recovery: dual remains blocked for the correct recorded reason.

Retain exact unchanged-book +2.5/+21 controls, independent same-packet provider inputs, current
revision/expiry checks and immutable identical retry semantics.

### C2. A known stop does not prove a complete executable outcome

The new executed-stop branch must not return a complete monetary outcome before checking factual
source continuity, quote coverage, instrument validity and barrier ordering.

Acceptance examples:

1. Public Gold fixture: original entry +4, executed stop event +99.9 / receipt +100, next quote +150,
   maximum quote gap 60 seconds. Keep invalidation, but do not produce a complete priced execution
   across the 96-second pre-stop quote gap. The extended fixture can create additional opportunities;
   assert the three original identities instead of hard-coding the total output count.
2. Source loss at +0.5, stop +1 and next quote +2: preserve terminal history while representing
   incomplete/ambiguous outcome evidence. Retain a continuous valid quote-side stop control.

Cover both directions and prospective/paper propagation. A print from another trade is not proof of
our executable exit price. Do not fabricate a replacement quote, select a favorable ordering or
erase the stop fact. Version any corrected evaluator/result semantics.

## Package D — complete the existing bounded-state/output contract (P6W-06)

Preserve the passing 1,000/8,000 irrelevant-quote cases and completed paper-candidate retirement.
Add separated synthetic real-detector lifetimes, holding maximum active candidates at three.
The independent two/eight-episode probe produced 6/24 candidates and zero active at completion,
but retained 12/48 provider completions in COMPLETE checkpoints. Public report and a page requested
with limit 1 loaded all 6/24 opportunity objects before returning results.

1. Retire resolved provider working state after its evidence and decisions are durable. Keep only
   necessary unresolved/pending state in the checkpoint; load historical evidence by indexed
   identity where needed. Preserve conflict detection, later dual readiness, late-provider policy
   and fresh-process recovery. Do not drop unresolved providers or delete the immutable journal.
2. Make opportunity/API pages and report/export projections genuinely bounded before Python model
   construction. Preserve current revision selection, stable ordering, protected/crossing holdout
   behavior and explicit final opening. Use streaming/batched aggregates or isolated disk-backed
   work when necessary; do not replace correct statistics with approximate silent truncation.
3. Instrument actual provider counts/checkpoint size and rows materialized before output slicing.
   Repeat the two/eight-lifetime comparison and the old-quote comparison. Assert working-state/page
   limits structurally, not an arbitrary exact byte total. Check matching canonical outcomes.
4. Restart with unresolved providers as well as after retirement. Exercise report/API/export before
   and after final-holdout access, including legacy unscoped rows. All protected reads remain safe.

The measured serialized provider bytes are not RSS. Report any command-allocation/RSS measurement
with its host/runtime and method, separately from retained-object counts. Dense within-horizon
quotes were not a newly reproduced finding; do not add an unrelated performance rewrite.

## Required verification and deliverables

Run the existing gates:

```bash
python -m pytest -q
python -m ruff check .
python -m ruff format --check .
python -m compileall -q src tests
git diff --check
```

From `frontend` run `npm ci --no-audit --no-fund`, `npm run typecheck`, `npm run build` when the
environment permits; report installation limitations honestly. Run Gold and BTC public fixture
generation, `validate-data`, `run-workflow`, `paper-workflow`, `evaluate` and `report`, verify all
export hashes, and retain holdout tests. Avoid broad repetition after the concrete risks are resolved.

Deliver:

- Narrow code/test commits closing all six IDs; no unrelated strategy or UI expansion.
- `docs/audits/phase-6-contract-corrections-verification.md`: exact SHAs/versions, red/green cases,
  preserved controls, public counts/hashes, fresh-process and partial-write behavior, actual
  materialization bounds, and unverified external gates.
- README, DESIGN, plan and release-note status consistent with the evidence. Annotate historical
  reviews/reports with later disposition without replacing their original executed results.
- Offline operational preparation from [CODEX_OPERATIONAL_VALIDATION.md](CODEX_OPERATIONAL_VALIDATION.md):
  a concrete prerequisite/evidence worksheet, bounded command pack and prospective experiment
  template. Reuse the existing Windows deployment architecture and scripts.
- A reviewable PR and a concise report of exact tests, remaining limitations and next operator action.

## Stopping rule

This task is complete when P6W-01 through P6W-06 and their listed controls pass, prior required
regressions remain green, and the evidence documents agree. Do not add another feature milestone.
If a listed case still fails, name it and leave it open. Missing Windows access, keys or a licensed
feed does not block finishing the offline corrective PR and operational preparation; it blocks only
the specific unperformed external validation.
