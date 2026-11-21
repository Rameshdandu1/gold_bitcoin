# Master implementation prompt for GPT / Codex (copy or point the agent to this file)

You are the principal engineer for **dual-ai-market-intelligence**, a **Windows Server native** market intelligence platform for Delta Exchange India BTCUSD and supported Gold-token derivatives. Follow `AGENTS.md` exactly; read `DESIGN.md`, `README.md`, `docs/IMPLEMENTATION_PLAN.md`, and inspect the current code, git status and tests before changing anything.

Goal: deliver a robust, observable and testable research product with six independent opportunity detectors (Gold and BTC × 15–30m, 60m, 2–4h), independent GPT and Claude structured analysis on immutable same-timestamp snapshots, CoinGlass subscription integration, deterministic approval gate, clean UI, alerts and historical outcome measurement. **Do not add live orders or an execution integration.** No fictional stats or signals. Always make negative/stale/retry/recovery paths safe.

Work in vertical slices and commit to feature branches. Read docs for the exact current provider protocol; do not paste unverified or deprecated Delta channels. Use the official India public socket and REST; validate product availability before subscribing. For CoinGlass discover license limits, supported symbols/exchanges; never confuse estimated liquidation clusters with executable Delta orderbook depth. Tokenized-gold $10/$20/$30 are underlying USD price moves; BTC uses vol-normalized targets.

First milestone: harden market data integrity and persistence. Add Delta fixture-based contract tests, WS replay with packet-loss recovery and consistent event timestamps. Implement true rolling 500/5000 executed-trade windows, CVD and orderbook imbalance with correct buyer_role semantics, and verify closed-candle aggregation. Maintain raw instrument unit metadata.

Second milestone: create market-structure/sweep/retest and liquidity algorithms for each timeframe independently, with ATR-based feasibility, target barriers, episode IDs and TTL. Build event-time replay to show target-before-stop and real slippage/fees. Never label same-bar collisions automatic winners.

Third milestone: integrate GPT + Claude concurrently with strict Pydantic outputs, consistent canonical snapshot, response validation/refusal handling, no mutual contamination, selective trigger calling, cost ceilings and persisted reasons. Only validated agreement plus deterministic gate produces a CONFIRMED alert; one provider down means WAIT. Keep all raw rationale and disagreement visible; do not claim calibrated confidence until measured.

Fourth milestone: add a full responsive market dashboard, data health, candlesticks/order flow, six signal engines, coin glass liquidity layers, AI comparison, alert/outcome history, read-only options evaluation, Telegram. Add E2E tests and Windows-native service instructions.

For each milestone: propose acceptance tests, implement source, run tests/typecheck/build, show changed file paths and commit SHA, explicitly list mock/unverified integrations, and update README + DESIGN. No unrequested paid integration and no deployment claims without verifying Windows service run.
