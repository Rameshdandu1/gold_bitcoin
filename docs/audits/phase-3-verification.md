# Phase 3 verification

Date: 2026-11-21. Branch: `feature/phase-3-dual-ai-confirmation`.

## Foundation and exact scope

- Verified starting main: `10b3e9118448b55db80c94ae91cee7e227a64932` (merged Phase 2).
- Instruction/review source: `origin/docs/phase-3-review-and-instructions` at `736e68b`.
- Final implementation commit before this report: `bb785f2`.
- Phase commits: `0648372` (3A), `a4512f1` (3B), `4f6a811` (3C), `a350270`
  (3D), `bb785f2` (3E). The documentation-gate commit is `346f435`.
- Baseline from updated main: 126 Python tests passed; Ruff lint/format, Python compilation,
  frontend TypeScript and production build passed. The build needed an out-of-sandbox rerun because
  the managed sandbox denied esbuild access to the Vite config; the application build itself passed.
- Final verification: 171 Python tests passed; Ruff lint and format, Python compilation,
  `git diff --check`, PowerShell parse, `npm ci`, frontend typecheck and production build passed.
  One FastAPI TestClient deprecation warning from the installed Starlette compatibility layer
  remains; it is not a test failure.

No paid provider call, real Slack notification, deployment, order, trading credential, or server
mutation was performed.

## Phase 2 independent findings

| Finding | Result | Regression evidence |
|---|---|---|
| R1 short history labelled full session | Fixed | complete/incomplete 120-bar bullish and bearish session fixtures; acquisition pages to complete UTC session/previous day |
| R2 breach followed by recovery stays active | Fixed | durable executed-trade breach at 68,999/2,606 remains terminal after price recovery |
| R3 repeated BOS/CHOCH for one pivot | Fixed | chronological first-break identity and new-pivot regression |
| R4 unavailable candle enters detector | Fixed | common closed-candle availability gate and resample max-constituent availability |
| R5 dashboard omits terminal lifecycle | Fixed | current lifecycle/reason/time read model and UI are separate from historical consensus |
| R6 discovery failure does not continue gating | Fixed | transition/heartbeat/last-success health, maximum-age cache and current reconciliation gate |

R1 and R2 were first added as failing regressions: both complete-session direction cases and the
breach/recovery worker case failed before implementation. They passed after 3A. The intentional
detector rule version changed from `m2-v1` to `m3a-v2`; old persisted evidence is not rehashed.

## Canonical evidence, jobs and budgets

The immutable envelope contains candidate, exact revision, full feature snapshot, verified
instrument, coverage/provenance, frozen entry/stop/targets, prompt/risk versions and evaluation
settings. A canonical encoder emits one byte sequence with sorted keys, canonical UTC/decimals and
no non-finite numbers. Both adapters receive those bytes. The digest is outside its own preimage.

Deterministic fixture identities (hypothetical, not live market data):

- Gold envelope digest `f71cc77310a5b83f1f1d583be79160f4d2630924f49389a707ce0b36cbbbe224`,
  revision `1c8274d35981c0f216be694748bc9d83cc28e4718ca2ceca46326e832f716a0d`.
- BTC envelope digest `38530eaf59752737dcc68ef79f31814d1cd60d375e393b4079938aeb19ebd4d3`,
  revision `c069154ace0e0e3d68bc4007e236a277b4baea87889ecf814741198b68f40792`.

Tests verify byte stability across restart/rebuild, material-change sensitivity, deep immutability,
conflicting digest rejection, revision A/B isolation, one winner from concurrent job claims, stale
lease fencing, UTC-day budget boundaries and atomic concurrent reservations. Migration
`0003_phase3_review_pipeline` upgrades a fixture 0.2 database, preserves old rows, records one
migration application and reopens without duplication. A SQLite backup/restore test preserves
revisions, an active queued job, budget ledger, outbox and migration history.

Provider dispatch is allowed only when both provider keys/model IDs, both verified pricing pairs and
a non-zero spend limit exist. Missing dual configuration or rates records two `NOT_READY` outcomes
and makes zero transport calls. A dispatched job is not automatically reclaimed as certainly
unbilled. Unknown usage stays conservatively reserved.

## Hypothetical vertical fixtures

These are software fixtures labelled `TEST_FIXTURE_NOT_LIVE`; they do not state signal quality.

### Gold approval and terminal path

The Gold fixture proposes bullish XAUTUSD at 2,600, invalidation 2,590 and frozen targets 2,610 and
2,620. Both fake independent providers approve original target identity T2. With unchanged active
revision/lifecycle, fresh 2,599.9/2,600.1 book, known fixture costs and feasible risk geometry, one
`CONFIRMED` decision and one revision-scoped Slack intent commit. A separate fixture executed-price
breach appends `INVALIDATED`; it suppresses an obsolete pending confirmation and creates a different
lifecycle-event delivery identity. Timeout, rejection, expiry equality, stop breach, wide spread,
crossed target, ambiguous ordering and revision supersession all fail closed.

### BTC approval and failure path

The BTC fixture proposes bullish BTCUSD at 70,000, invalidation 69,000 and frozen targets 71,000 and
72,000. Both fake providers approve T2. With a 69,999/70,001 book and unchanged fresh evidence, the
decision commits once. Provider timeout/refusal, incomplete dual configuration, exhausted budget,
stale source, later breach, invalidated candidate or changed revision cannot confirm and cannot
reuse the old approval.

## Provider, consensus and delivery results

- OpenAI and Anthropic transports start concurrently from the same canonical bytes. Tests cover
  valid output; wrong snapshot/revision/asset/direction; invalid boolean/string/float/duplicate
  target indices; extra fields; refusal; truncation; missing parsed output; returned-model mismatch;
  timeout; transport error; HTTP 401/403/429/5xx; unsupported model; bounded retry and no
  answer-shopping.
- Server-owned request/response/model/usage metadata and every failure/disagreement remain durable.
  One provider cannot fill both slots. Agreement never bypasses fresh source, price, lifecycle,
  spread, cost or risk gates.
- Consensus and notification intent use one conditional transaction over revision generation,
  lifecycle event, latest trade, source health and book checkpoint. A race invalidating or
  superseding the candidate creates neither stale decision nor outbox intent.
- Slack is the only completed channel. Fake transports verify stable intent uniqueness, restart,
  transient retry/backoff, expiry suppression, terminal-event identity, durable receipt and
  `RECEIPT_UNKNOWN` without uncontrolled resend. Slack credentials stay in the Authorization header;
  no real message was sent.

## Operator security and Windows result

HTTP Basic with constant-time comparison is the documented single-operator boundary. Empty
credentials fail closed. Dashboard, API, docs, OpenAPI and readiness require authentication; only
minimal liveness is public. CORS accepts exact configured origins. The backend binds to loopback and
remote access requires a restricted HTTPS reverse proxy/VPN. React renders provider/error text as
escaped values and contains no embedded provider or Slack secret.

Readiness separates liveness from migrations, auth, worker heartbeat, required source age, provider
and alert configuration, queue lease state and UTC-day spend. It makes no paid request. PowerShell
startup/check/stop/backup scripts all parsed successfully on this Windows development machine. The
Task Scheduler installation, reboot recovery, bounded restart behavior, log rotation and actual
restore drill on the destination server were not run and remain operational acceptance work. No
production queue latency, raw tick throughput or storage capacity was measured.

## External verification and known limits

Actual paid-call count: **0**. Actual OpenAI models contacted: **none**. Actual Anthropic models
contacted: **none**. Actual Slack messages: **0**. Configurable model IDs are intentionally blank by
default; account/model access was not invented.

During implementation, installed SDK parse signatures were inspected and current official OpenAI,
Anthropic and Delta documentation was reviewed. No live external endpoint was called in Phase 3.
The following remain unverified:

- OpenAI/Anthropic account entitlement, configured model support, billable usage and current pricing.
- Slack workspace/channel authorization and external receipt/idempotency behavior.
- CoinGlass subscription entitlement, Delta India pair coverage, refresh limits, license and
  redistribution terms.
- A licensed Gold spot/basis, DXY, yields, macro news and economic-calendar source.
- Extended Delta live-feed/reconnect/clock/storage soak and current availability of a qualified Gold
  contract.
- Native Windows Task Scheduler installation and destination-server backup/recovery.
- Calibrated accuracy, probability, profitability and any execution behavior. Phase 4 must evaluate
  rules-only, GPT-only, Claude-only and dual agreement in strict time order, net of costs, with
  sample sizes and uncertainty before paper trading.
