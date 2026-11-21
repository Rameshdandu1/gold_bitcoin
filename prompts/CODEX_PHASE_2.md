# CODEX_PHASE_2.md — Next Codex instructions: six independent signal engines

Repository: https://github.com/Rameshdandu1/gold_bitcoin  
Owner: Rameshdandu1  
Prior work: PR #1, `feature/delta-market-data-integrity`  
Next milestone: Phase 2 / M2 — Deterministic Gold and Bitcoin opportunity detection.

## Copy/paste into Codex

You are the principal engineer for the Gold + Bitcoin Dual-AI Market Intelligence application in `Rameshdandu1/gold_bitcoin`.

**FIRST, VERIFY CURRENT GIT AND M1 STATUS; DO NOT ASSUME M1 IS MERGED.**
1. Read `AGENTS.md`, `DESIGN.md`, `README.md`, `docs/IMPLEMENTATION_PLAN.md` and this file. Preserve all existing data and working changes.
2. Inspect the latest commit, branch, open pull requests, CI and the M1 modules/tests. As of the preparation of this instruction, PR #1 (`feature/delta-market-data-integrity`) is OPEN, mergeable, with 66 locally reported passing backend tests and a successful GitHub CI workflow. Verify its **current** status again.
3. Review PR #1 for correctness; specifically inspect the remaining gaps stated in its description: malformed REST envelopes/4xx, corrupt or unknown WS frames and 429, rare collector restart/no-symbol paths, long-duration soak/reconnect/replay not validated. Fix blocking correctness problems on the M1 branch before expanding M2. Record non-blocking operational gaps in the backlog. Never label a short public API smoke test as a production reliability guarantee.
4. Do **not merge PR #1 automatically**. If it remains open and its reviewed foundation is adequate for M2 work, create a feature branch `feature/six-quantitative-engines` from the HEAD of `feature/delta-market-data-integrity` and prepare a **stacked** pull request based on the M1 branch. If PR #1 is already merged, branch from updated `main` and target `main` instead. Never develop dependent features from the old `main` starter by mistake.
5. Run current Python backend tests and Ruff, then the frontend typecheck/build if touched. Report baseline before changes. Propose concise interfaces, fixtures, acceptance tests and work slices. Then implement, not just design.

**IMPLEMENT PHASE 2, TASKS 7–10: SIX INDEPENDENT DETERMINISTIC DETECTION ENGINES.** No live orders, no trading keys and no live GPT/Claude approval calls. `AI_ENABLED=false`, `TRADING_ENABLED=false`; unvalidated candidates must remain `INCOMPLETE`/`WATCH`/`WAIT` rather than `CONFIRMED`.

### 1. Domain and data contracts
- Reuse the verified M1 normalized Delta India trades, candles, instrument metadata, books and replay. Do not introduce a second divergent market-data client.
- All market snapshots are UTC, versioned, immutable, source-attributed and only refer to closed candles. Track event time, receive time, quality/freshness and source units.
- Raw exchange trade quantity is **contracts**; compute base-asset/notional equivalents only using verified instrument contract specs. Unknown aggressor roles are excluded from signed delta.
- Create typed models for `FeatureSnapshot`, `LiquidityLevel`, `OrderFlowFeatures`, `VolatilityBudget`, `StructureEvent`, `CandidateSignal`, `CandidateLifecycleEvent`. Extend existing models compatibly rather than fork types.
- Stable deterministic candidate ID = asset + instrument + engine + horizon + candle-close UTC + direction + rule-version; prevent duplicate processing on restart, replay or reconnect.

### 2. Gold engines — three separate horizon policies
**GOLD_FAST (15–30m):**
- 1m primary candles; 3m/5m derived context.
- Detect explicit liquidity sweep/reclaim and breakout-with-follow-through; evaluate relative volume, near-term swing highs/lows, aggressive delta, order-book integrity, ATR feasibility.
- Candidate target tiers: +/$- 10, 20, 30 *USD per token unit* from a defensible entry, only when sufficient room exists; invalid levels must be filtered.
- Separate upside/downside candidates; do not label a single sweep as automatically bullish/bearish.

**GOLD_HOURLY (60m):**
- 5m entry/trigger; 15m/1h closed-candle context.
- Detect breakout + retest, failure/rejection, structure direction and VWAP alignment; require persistence of volume pressure, not one spike.
- Compute conservative entry, stop/invalidation, opposing liquidity and $10/$20/$30 feasibility.

**GOLD_SESSION (120–240m):**
- 15m trigger with 1h/4h context.
- Detect higher-timeframe BOS/CHOCH, session highs/lows, previous-day extremes, trend continuation and reversal; include session logic with explicit UTC session boundaries.
- Stop and $10/$20/$30 target tiers must pass horizon-adjusted range and opposing-level checks.

Do **not** treat Delta XAUT/PAXG as identical to XAU/USD. If XAU reference prices are not licensed/available, report missing reference and prevent any basis-dependent claim, while allowing only explicitly approved token-market-only features.

### 3. Bitcoin engines — same horizons, independent parameterization
**BTC_FAST (15–30m):** short-window trade aggression, 1m/3m sweep-reclaim, 5m structure, volume/range expansion and book integrity.  
**BTC_HOURLY (60m):** 5m/15m structure, breakout/retest, VWAP, CVD, funding/OI only if available and fresh.  
**BTC_SESSION (120–240m):** 15m/1h/4h structure, session levels, sustained order flow, derivatives positioning and macro if verified.

Do not reuse Gold $10/$20/$30 targets for BTC; use ATR- and percentage-scaled target tiers as **configurable, provisional heuristics**, not empirical probabilities. Allow each engine to output a different direction. Show `WAIT` for insufficient movement budget.

### 4. Shared quantitative feature layer
Implement and test:
- OHLCV candle aggregation/resampling from *closed* base candles only, correctly handling missing intervals and no forward-fill of fake candles.
- ATR(14), session VWAP (reset boundaries documented), relative volume/volume regime, range compression/expansion, volatility budget.
- Swings, HH/HL/LH/LL, BOS/CHOCH with **non-repainting** confirmation rules, prior day/session highs/lows, gap-handling.
- Liquidity sweep/reclaim, false breakout, breakout/retest, absorption proxy with caveats. Trade-book liquidity is not the same as CoinGlass estimated liquidation heatmaps.
- Exact rolling **500 and 5,000 executed-trade** windows; signed aggressor CVD, unclassified quantities kept separate, per-window clock duration and trade-rate normalized flow. Also keep 5m/15m time-window flow so high/low activity periods are comparable.
- Top-of-book and bounded-depth imbalance only from a sequence-validated fresh book. Missing/stale/corrupted books invalidate book-dependent signals.
- Market regime `TRENDING|RANGING|VOLATILE|UNKNOWN` derived from explicit documented metrics rather than model guesses.
- Stop/target geometric validation, conservative spread/slippage assumptions, ATR-based feasibility, room-to-next-opposing-level and expiry.

### 5. CoinGlass and Gold reference enrichment (behind gates)
- Extend the existing CoinGlass adapter using current official V4 docs and the **actual subscription entitlements**; confirm supported exchanges, assets, timestamps, and rate limits. Start with discovery, funding and open interest; add liquidation map/heatmap only when authorized. Missing license/key yields `UNAVAILABLE`, never synthetic data.
- CoinGlass-derived BTC liquidation clusters are *estimated* and cross-venue, not executable Delta India depth. Do not force the detector to depend on CoinGlass when entitlement is absent, except for explicitly required features.
- Build pluggable interface for external XAU/USD reference, DXY and US Treasury yields with provider, timestamp, units, token-gold basis; do not hardcode a fake source or require paid feeds without approval. Implement fixture-driven contract tests first, live only when authorized.

### 6. Signal state and presentation contract
States: `UNAVAILABLE`, `WAIT`, `WATCH`, `CANDIDATE`, `REJECTED`, `INVALIDATED`, `EXPIRED`; `CONFIRMED` must remain blocked until M3 passes both GPT/Claude plus risk gates. Define legal transitions and idempotent event emission.
Each candidate must contain:
`candidate_id`, `snapshot_id`, `schema_version`, `asset`, `venue`, `symbol`, `engine`, `horizon_minutes`, `direction`, `rule_version`, `trigger`, `feature_evidence`, `counter_evidence`, `source_quality`, `entry`, `invalidation`, `targets`, `expires_at_utc` and a concise machine-checkable explanation.
Persist revisions and invalidations instead of overwriting past decisions. M2 dashboard/API, if touched, must show source timestamps and explicitly `NOT AI CONFIRMED`.

### 7. Deterministic replay and test requirements
Write **fixture-based** tests using M1 raw event journal and recorder/replayer for:
1. Gold bullish sweep/reclaim and bearish sweep/rejection.
2. BTC upside breakout + confirmed retest and downside failed breakout.
3. Each engine's clock and expiry, including 30m vs 60m vs 240m independent decisions.
4. The same trade stream yields identical rolling 500/5,000 delta on replay; unknown aggressors excluded, contract sizes normalized correctly.
5. Repeated events/restarts do not duplicate candidate IDs or alerts.
6. A missing candle, out-of-order update, stale/corrupt order book or wrong/absent Gold symbol fails closed.
7. No look-ahead: future candles never change a candidate that existed at its original decision time; no repainting pivots.
8. Volatility insufficient for $30 Gold target => reject $30 even if a $10 candidate is plausible.
9. Same-bar stop-and-target hits are conservatively marked ambiguous/not-won; no future event leaks into signal generation.
10. CoinGlass missing subscription/unsupported pair does not create false data or call premium endpoints.
11. Signals never trigger paid AI, telegram `CONFIRMED` or trading endpoints in M2.

Use property-based/fuzz testing for state transitions and price arithmetic if feasible. Test normal, adverse and pathological market sequences. Keep sample/demo data visibly marked and only in tests/fixtures.

### 8. Delivery process and definition of done
- Work in reviewable vertical slices: (A) feature contracts + replay windows; (B) structure/sweep algorithms; (C) six horizon policies; (D) optional CoinGlass/reference enrichment; (E) persistence/state/API; (F) tests and docs.
- Update tests, `AGENTS.md` only if rules need amendment, `DESIGN.md`, `README.md`, `docs/IMPLEMENTATION_PLAN.md`, `.env.example`, `CHANGELOG.md` and ADR(s) where architectural changes occur.
- Run `python -m pytest -q`, `python -m ruff check .`, `python -m ruff format --check .`, `python -m compileall -q src`; for frontend changes `npm run typecheck`, `npm run build`. Run `git diff --check` and check for secrets.
- Make tests deterministic and independent from paid providers. Separate fixture, optional live smoke, and production validations in your report.
- Create a PR, do not auto-merge. Report branch/base, commit SHA, PR link, six-engine output examples explicitly marked **hypothetical**, exact test counts, remaining assumptions, external API coverage and blocked requirements.
- **Never claim a 70–90% prediction probability, detected 'whale', guaranteed $30 move, or successful options return without empirical evidence.**
- No live order placement, no key permission escalation, no user credentials in GitHub and no Windows Server deployment claims without actual validation.

**Begin now by validating PR #1 and establishing the Phase 2 feature branch from the correct foundation; then implement the first tested vertical slice, not only a plan.**
