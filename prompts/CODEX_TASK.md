# Current implementation task for Codex

Repository: https://github.com/Rameshdandu1/gold_bitcoin.

Read `AGENTS.md`, `DESIGN.md`, `README.md` and `docs/IMPLEMENTATION_PLAN.md` first. Inspect git status,
record current main and preserve unrelated changes. Do not restart earlier delivered milestones.

## Current task: Phase 6 contract corrections

Follow [CODEX_PHASE_6_CONTRACT_CORRECTIONS.md](CODEX_PHASE_6_CONTRACT_CORRECTIONS.md), using the
[independent workflow-acceptance review](../docs/audits/phase-6-workflow-acceptance-independent-review.md).
Reviewed main is `e9f419f5ef576ec957f9d59107ab3f7f06815b23` (merged PR #15); its 260-test baseline
passes, but six concrete requirements remain:

1. Candidate/initial-rules persistence must survive interruption and ordinary fresh-process resume.
2. Late pre-candidate trades must retain event/receipt identity and not create a false new stop.
3. Executed target-crossing history must survive recovery and govern the actual approved targets.
4. Dual readiness must use provider verdicts and its current gate, independently of an earlier
   individual arm's temporary market WAIT.
5. A terminal stop must not bypass source/quote/instrument coverage or imply a complete priced fill.
6. Completed provider working state and report/API projections must be bounded before materialization.

These complete existing Phase 6 requirements. Preserve the original corrected cases and exact
immutable/restart/holdout controls. Keep the six engines, four arms, stack and strategy thresholds.
No additional vendor, CoinGlass heatmap collector, options, order execution or channel integration
is included. Independent GPT/Claude analysis remains a review of the same canonical packet;
agreement cannot override deterministic gates or establish a statistical probability.

Implement the task in reviewable commits with tests and evidence; push a branch and open a PR.
Do not auto-merge, deploy, enable external flags or send real notifications during correction.

## Next operational and evidence stages

Prepare [CODEX_OPERATIONAL_VALIDATION.md](CODEX_OPERATIONAL_VALIDATION.md) offline while finishing
the software corrections: destination-host worksheet, bounded command pack, prerequisite/cost/
destination fields and prospective-experiment template. Reuse the existing Windows runbook.

After software acceptance and actual prerequisites/authorization, validate the intended Windows
host, Delta feeds, implemented CoinGlass endpoints, bounded GPT/Claude usage and one authorized
notification destination. The Gold reference adapter remains unwired; supplied credentials alone
do not implement it. Then freeze the common-opportunity paper experiment and collect genuine
elapsed evidence. Synthetic tests, destination readiness and empirical performance are separate.

Report exact files, commands/results, code/contract identities, unverified or blocked external
checks, PR link and the next concrete operator action. Missing external prerequisites must not leave
authorized offline preparation unfinished.

## Historical master brief (reference only; not the current task)

The original milestone narrative below is retained as product history. It does not authorize
restarting delivered phases or implementing its deferred features during the current corrective task.

You are the principal engineer for **dual-ai-market-intelligence**, a **Windows Server native** market intelligence platform for Delta Exchange India BTCUSD and supported Gold-token derivatives. Follow `AGENTS.md` exactly; read `DESIGN.md`, `README.md`, `docs/IMPLEMENTATION_PLAN.md`, and inspect the current code, git status and tests before changing anything.

Goal: deliver a robust, observable and testable research product with six independent opportunity detectors (Gold and BTC × 15–30m, 60m, 2–4h), independent GPT and Claude structured analysis on immutable same-timestamp snapshots, CoinGlass subscription integration, deterministic approval gate, clean UI, alerts and historical outcome measurement. **Do not add live orders or an execution integration.** No fictional stats or signals. Always make negative/stale/retry/recovery paths safe.

Work in vertical slices and commit to feature branches. Read docs for the exact current provider protocol; do not paste unverified or deprecated Delta channels. Use the official India public socket and REST; validate product availability before subscribing. For CoinGlass discover license limits, supported symbols/exchanges; never confuse estimated liquidation clusters with executable Delta orderbook depth. Tokenized-gold $10/$20/$30 are underlying USD price moves; BTC uses vol-normalized targets.

First milestone: harden market data integrity and persistence. Add Delta fixture-based contract tests, WS replay with packet-loss recovery and consistent event timestamps. Implement true rolling 500/5000 executed-trade windows, CVD and orderbook imbalance with correct buyer_role semantics, and verify closed-candle aggregation. Maintain raw instrument unit metadata.

Second milestone: create market-structure/sweep/retest and liquidity algorithms for each timeframe independently, with ATR-based feasibility, target barriers, episode IDs and TTL. Build event-time replay to show target-before-stop and real slippage/fees. Never label same-bar collisions automatic winners.

Third milestone: integrate GPT + Claude concurrently with strict Pydantic outputs, consistent canonical snapshot, response validation/refusal handling, no mutual contamination, selective trigger calling, cost ceilings and persisted reasons. Only validated agreement plus deterministic gate produces a CONFIRMED alert; one provider down means WAIT. Keep all raw rationale and disagreement visible; do not claim calibrated confidence until measured.

Fourth milestone: add a full responsive market dashboard, data health, candlesticks/order flow, six signal engines, coin glass liquidity layers, AI comparison, alert/outcome history, read-only options evaluation, Telegram. Add E2E tests and Windows-native service instructions.

For each milestone: propose acceptance tests, implement source, run tests/typecheck/build, show changed file paths and commit SHA, explicitly list mock/unverified integrations, and update README + DESIGN. No unrequested paid integration and no deployment claims without verifying Windows service run.
