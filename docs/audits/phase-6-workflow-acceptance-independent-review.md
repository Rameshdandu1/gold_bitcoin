# Independent review of Phase 6 workflow acceptance

Review date: **2026-11-22 (Asia/Kolkata)**. All scenario times below are UTC. Every market price,
provider answer and outcome in this review is **hypothetical synthetic software evidence**.

## Verdict and scope

Reviewed merged main **`e9f419f5ef576ec957f9d59107ab3f7f06815b23`**, including
[PR #15](https://github.com/Rameshdandu1/gold_bitcoin/pull/15). Its implementation commit is
`5a7cbaa0c20209634a62a3cc50517724d0eef0bb`. PR head
`e87e5ca07a2de4b245ba93695dac6f6a986f2df9` and the reviewed merge have identical trees.

The exact earlier P6C-01 later-book failures and P6C-02 post-observation stop/recovery case are
corrected. P6C-03's irrelevant pre-candidate quote loading is also corrected, and paper retires
completed candidates. These improvements are preserved.

**Full offline acceptance is still open.** Six finding groups remain inside the existing
recovery, factual-clock, application-parity, outcome-coverage and bounded-processing requirements.
This review does not add indicators, provider integrations, execution or a new strategy phase.

The next coding task is [Phase 6 contract corrections](../../prompts/CODEX_PHASE_6_CONTRACT_CORRECTIONS.md).
The following stage is [controlled operational validation](../../prompts/CODEX_OPERATIONAL_VALIDATION.md),
then genuine prospective paper observation. Prepare operational material offline while correcting
the code; do not mistake preparation for completed external validation.

## Executed baseline and controls

| Check | Independently observed result |
|---|---|
| Python suite on reviewed source | **260 passed**, two non-failing dependency deprecation warnings |
| Ruff lint / format | Passed; 96 files already formatted |
| Python compilation / diff whitespace | Passed |
| Frontend TypeScript / production build | Passed using the existing installed dependency tree; frontend source and lockfile are unchanged |
| Clean offline frontend install | Could not finish because the npm cache lacked `yallist-3.1.1`; this is not recorded as a successful install |
| Hosted Windows CI | [Run 68](https://github.com/Rameshdandu1/gold_bitcoin/actions/runs/44996880111), both backend and frontend passed on PR head `e87e5ca` |
| Gold public validate/run/paper/evaluate/report | All returned zero; 5,333 observations, 3 opportunities, 12 arm decisions and 12 paper outcomes |
| BTC public validate/run/paper/evaluate/report | Same counts; all three BTC detectors exercised |
| Report checksums | Ten files per asset, including `SHA256SUMS`; all nine listed file hashes verified for each asset |
| Unchanged book at +2.5 and +21 seconds | Both complete with 3 opportunities/12 decisions and preserve canonical earlier decisions |
| Fresh-process resume after GPT, before +2.5 book/Claude | Equal decisions, lifecycle, opportunities and final checkpoint versus uninterrupted control |
| Original stop +0.9 event / +1 receipt, followed by recovery | Production invalidates all three Gold candidates; research records 12 `NO_ENTRY` outcomes, zero entries |
| Benign trade/recovery | Production remains eligible; research preserves 12 hypothetical target outcomes |
| Existing P6C-03 1,000/8,000 old-quote cases | Both targeted regressions pass; candidate-window quote load remains bounded in those cases |

Local verification used Linux CPython 3.12.14 with the reviewed worktree explicitly selected in
`PYTHONPATH`. The original stop checkpoint was also reloaded and matched in a separate CLI invocation
within one interpreter; that particular control is not described as a fresh-process test.
Hosted Windows CI and local checks do not establish destination Windows Server recovery.

All provider transports were synthetic/fake. The production dual comparison exercised real stores,
the review worker, current-risk logic and local outbox transactions, but never invoked a notification
dispatcher. No live market collection, paid model call, real message, order or deployment occurred.
The resulting statistics remain hypothetical and `INSUFFICIENT_DATA` for empirical comparisons.

## Finding index

| ID | Priority | Finding | Disposition relative to PR #15 |
|---|---|---|---|
| P6W-01 | P2 | Candidate commit without its rules arm strands resume | Existing recovery gap, newly reproduced at the required write boundary |
| P6W-02 | P2 | Late pre-candidate trade becomes a false new stop | Regression in the new research lifecycle path |
| P6W-03 | P1 | Executed target exhaustion disappears after recovery | Existing factual-input/parity gap remains open |
| P6W-04 | P2 | Earlier individual market WAIT incorrectly vetoes later dual approval | Mismatch in the changed dual-decision path |
| P6W-05 | P1 | Executed stop bypasses path coverage and creates a complete priced outcome | Regression in the new outcome path |
| P6W-06 | P2 | Completed provider state and output reads still grow with history | Remaining whole-workflow boundedness gaps |

P1 means incorrect scientific outcome/eligibility needs correction before accepting evidence;
P2 means an important recovery, policy or resource contract is incomplete. These priorities do not
claim an order-execution incident; the repository has no order path.

## P6W-01 — candidate/rules persistence is not recoverable as a pair

The [candidate write and early return](https://github.com/Rameshdandu1/gold_bitcoin/blob/e9f419f5ef576ec957f9d59107ab3f7f06815b23/src/marketintel/research_engine.py#L986)
commit the candidate before its `RULES_ONLY` arm. Retry sees an existing candidate and skips the arm
write. Finalization repairs missing provider/dual arms but assumes the rules arm exists.

Reproduce with a fresh generated Gold fixture. Inject a process failure immediately before the
first `ResearchStore.save_arm_decision` call for `RULES_ONLY`, after `save_candidate` has committed.
Do not modify persisted rows. Then invoke ordinary public `run-workflow` in a fresh process.

| Boundary | Candidates | Decisions | Opportunities | Checkpoint / result |
|---|---:|---:|---:|---|
| After injected failure | 1 | 0 | 0 | `RUNNING`, offset 5,000 |
| First ordinary resume | 3 | 11 | 2 | `INPUT_COMPLETE`, offset 5,333; exit 1, `KeyError: 'RULES_ONLY'` |
| Second ordinary resume | 3 | 11 | 2 | Same failure |

The valid restart cannot converge. The working GPT-boundary resume is a positive control, not proof
that every derived-write boundary is recoverable. Fix with an atomic candidate/initial-arm write or
deterministic recovery of the missing arm at its original factual clock. Preserve immutable conflict
rejection and document handling of already partial experiments.

## P6W-02 — event time is lost in late-trade invalidation

The [new terminal adapter](https://github.com/Rameshdandu1/gold_bitcoin/blob/e9f419f5ef576ec957f9d59107ab3f7f06815b23/src/marketintel/research_engine.py#L915)
compares candidate observation to receipt/availability, without the trade's event-time lower bound.
It also writes both lifecycle occurrence and availability as receipt time. The
[production trade query](https://github.com/Rameshdandu1/gold_bitcoin/blob/e9f419f5ef576ec957f9d59107ab3f7f06815b23/src/marketintel/storage.py#L863)
requires a post-observation exchange event and a receipt no later than the evaluation clock.

Use the standard Gold candidates at `2026-11-19T01:00:00Z`, preserve their identities and archived
provider bindings, parse/journal the trade with the real Delta parser, and regenerate file/manifest
hashes after adding it:

| Hypothetical case | Event time relative to candidate | Receipt | Stop price | Result |
|---|---:|---:|---:|---|
| Corrected old stop control | +0.9 s | +1 s | 2594.8 | Both paths invalidate |
| Late historical stop | -0.1 s | +1 s | 2594.8 | Production remains eligible; research invalidates all three candidates |

Both cases recover at event +1.4 / receipt +1.5 to 2599.2285714285713. In the late historical case,
research produces 12 `NO_ENTRY` outcomes while all three production candidates remain `CANDIDATE`
with passing current risk. Preserve event and availability separately and apply equivalent temporal
boundaries. A correction may not use future receipt information to rewrite an earlier decision.

## P6W-03 — executed target exhaustion is missing from research facts

Production [collects crossed target indices](https://github.com/Rameshdandu1/gold_bitcoin/blob/e9f419f5ef576ec957f9d59107ab3f7f06815b23/src/marketintel/review_worker.py#L51)
and [excludes those targets](https://github.com/Rameshdandu1/gold_bitcoin/blob/e9f419f5ef576ec957f9d59107ab3f7f06815b23/src/marketintel/consensus.py#L101).
Research's [current target arithmetic](https://github.com/Rameshdandu1/gold_bitcoin/blob/e9f419f5ef576ec957f9d59107ab3f7f06815b23/src/marketintel/research_engine.py#L605)
does not receive the same executed target-crossing history. Sharing the arithmetic alone does not
provide parity.

Add a hypothetical executed trade at event +0.9 / receipt +1, price **2700**, and recovery at
event +1.4 / receipt +1.5 to **2599.2285714285713**. Keep provider readiness +2/+3 and the original
entry/target quotes +4/+20. The real production lifecycle/current-risk path retains target 1 as
crossed and fails `FEASIBLE_TARGETS` for all three original candidates when target 1 is approved.
Public research instead returns **12 executable target-before-stop outcomes**.

The benign 2599.0/recovery case remains eligible in both paths. Preserve per-target historical facts,
their clocks and identities through checkpoint reload and paper processing. Target 1 crossing need
not invalidate every higher target; apply the production policy to the actual approved indices.

## P6W-04 — provider verdict and individual entry gate are conflated

The [dual constructor](https://github.com/Rameshdandu1/gold_bitcoin/blob/e9f419f5ef576ec957f9d59107ab3f7f06815b23/src/marketintel/research_engine.py#L637)
combines already market-gated individual arms. `_apply_market_gate` returns immediately for a
non-approved input, so a temporary earlier market failure is treated as a provider veto at the later
dual boundary. The [production worker](https://github.com/Rameshdandu1/gold_bitcoin/blob/e9f419f5ef576ec957f9d59107ab3f7f06815b23/src/marketintel/review_worker.py#L308)
checks current eligibility after both independent provider results arrive.

Exact hypothetical timeline, using matching thresholds, fees/slippage and target index 1:

| Time | Fact |
|---|---|
| +1.5 s | Valid book with bid 2600, ask 3000; temporary spread/drift failure |
| +2 s | GPT returns `CONFIRM`; GPT-only market arm correctly freezes `WAIT` |
| +2.5 s | Valid book restored to bid 2599.9, ask 2600.1 |
| +3 s | Claude returns `CONFIRM`; current market gates pass |

For GOLD_FAST, GOLD_HOURLY and GOLD_SESSION, public research persists GPT `WAIT`, Claude `APPROVED`
and dual `WAIT`. Its reason incorrectly says a provider returned WAIT. The production comparison
uses the same candidate IDs, real `ReviewWorker.run_once`, real Store, parsed CRC-validated books,
durable raw trades/source status and fake independent provider results. All three production
decisions are `CONFIRMED` at +3; both provider verdicts are `CONFIRM`.

Keep the immutable GPT-only +2 WAIT. Separately retain the provider verdict and evaluate dual from
both matching verdicts and facts at +3. Genuine provider WAIT/REJECT and terminal stop/source/revision
history must still block. This finding is research-policy drift, not a false live confirmation.

## P6W-05 — known invalidation is promoted to complete monetary evidence

The [post-entry executed-stop branch](https://github.com/Rameshdandu1/gold_bitcoin/blob/e9f419f5ef576ec957f9d59107ab3f7f06815b23/src/marketintel/research_evaluation.py#L328)
returns `STOP_BEFORE_TARGET`, `data_complete=True` and a trade-priced exit before checking source,
quote-gap and instrument continuity.

Public reproduction: retain original entry quotes at +4, move target quotes from +20 to +150, add a
parsed executed stop at event +99.9 / receipt +100, then recovery +100.4/+100.5. Keep the frozen
**60-second maximum quote gap**. Rehash valid file/manifest metadata and extend declared coverage.

The original three candidates' 12 arms all report complete stops, entry +4 and priced exit +100,
despite **96 seconds without quote coverage before the stop**. GOLD_FAST reports hypothetical net
P&L `-0.010249881`. The longer stream also creates two additional SESSION opportunities; the verified
claim concerns the original 12 arms, not the total experiment count.

Separate bullish/bearish evaluator controls show the same branch bypass with a source gap at +0.5,
stop +1 and next quote +2. Without the stop fact, that source path correctly returns `INCOMPLETE`.
The source-gap variant is evaluator evidence; the missing-quote variant was also exercised through
the public workflow.

A terminal candidate fact can remain certain while barrier ordering or executable exit economics
remain unknown. Preserve invalidation, but enforce coverage and quote-side pricing requirements;
do not count a complete empirical execution or attach definitive P&L to insufficient evidence.

## P6W-06 — completed provider state and output projections remain history-sized

The exact earlier irrelevant-quote cases pass. A separate finite test varies **completed candidate
history while holding maximum active candidates at three**. It uses two and eight separated,
explicitly synthetic daily episodes, the real production detectors and provider evidence bound to
their actual candidate/request/configuration identities, then fresh public research/paper runs.

| Measurement | Two episodes | Eight episodes |
|---|---:|---:|
| Input observations | 12,270 | 53,892 |
| Real-detector candidates | 6 | 24 |
| Maximum active candidates | 3 | 3 |
| Active candidates at completion | 0 | 0 |
| Paper decisions / outcomes | 24 / 24 | 96 / 96 |
| Paper candidates retired | 6 | 24 |
| Provider records retained in COMPLETE checkpoint | **12** | **48** |
| Serialized retained provider JSON bytes | **7,422** | **29,688** |
| Opportunity objects loaded by public report | **6** | **24** |
| Objects loaded by opportunity page with limit 1 | **6** | **24** |
| Objects returned by that page | 1 | 1 |

The provider-byte measurement is serialized JSON length, **not RSS or Python allocation peak**.
The projection probe records actual returned object counts without changing the underlying return
values. These cases demonstrate growth, not an out-of-memory failure.

Two mechanisms remain:

1. [Every provider completion](https://github.com/Rameshdandu1/gold_bitcoin/blob/e9f419f5ef576ec957f9d59107ab3f7f06815b23/src/marketintel/research_engine.py#L271)
   remains in a dictionary and [every checkpoint serializes it](https://github.com/Rameshdandu1/gold_bitcoin/blob/e9f419f5ef576ec957f9d59107ab3f7f06815b23/src/marketintel/research_engine.py#L392).
   Candidate retirement does not retire completed provider working state.
2. [Opportunity paging](https://github.com/Rameshdandu1/gold_bitcoin/blob/e9f419f5ef576ec957f9d59107ab3f7f06815b23/src/marketintel/research_storage.py#L427)
   calls the all-record projection before slicing, and [public reporting](https://github.com/Rameshdandu1/gold_bitcoin/blob/e9f419f5ef576ec957f9d59107ab3f7f06815b23/src/marketintel/research.py#L654)
   sorts and copies the full experiment.

Durable historical evidence should remain auditable. Only unresolved/provider working state belongs
in bounded checkpoints; history can be loaded by indexed identity when required. Page projected
output before materialization, preserving revision selection and holdout restrictions. The reviewed
quote lists remain bounded by a candidate time interval; no additional dense-window benchmark was
performed, and that is not presented as a separate reproduced failure.

## Next action and limits

Implement the six finite corrections and their specified positive/negative/restart controls. Preserve
the 260-test baseline and all five original P6 findings. Update scientific contract versions where
semantics change; migrate safely or refuse old corrected runs explicitly without deleting evidence.

After acceptance, validate the actual Windows destination, current Delta instruments/recovery,
provided CoinGlass entitlement, bounded GPT/Claude requests and one authorized notification
destination. Missing prerequisites remain explicit. Then freeze a prospective experiment and collect
genuine elapsed decisions/outcomes. Neither this review nor a passing corrected suite proves a
strategy edge or authorizes automated trading.
