# Controlled operational validation — 2026-11-24

This records a bounded local Windows workstation run. It is not destination Windows Server
acceptance, a deployment, a performance evaluation, or evidence of profitable signals.

## Identity and boundaries

| Item | Evidence | Status |
|---|---|---|
| Starting code | `399c70bbdd012e539a06d3e423fd30d8de498ab7`; branch `ops/controlled-live-validation` | PASS |
| Runtime | Windows 10 build 19045; Python 3.12.10; Node 24.18.0; npm 11.16.0; PowerShell 7.6.9 | PASS (local only) |
| Paid authorization | Combined OpenAI + Anthropic cap $5 per UTC day; one smoke request per provider | PASS |
| Trading | `TRADING_ENABLED=false`; no order/private-account calls | PASS |
| Notifications | `ALERTS_ENABLED=false`; no destination or messages | NOT_RUN |

Secrets remained in ignored `.env` and were checked only for boolean presence. A unique operator
credential was generated locally and was not printed or committed. Keys previously pasted into
chat should be rotated separately.

## Delta India public data

Public `/v2/products` discovery returned these live/operational vanilla contracts:

| Asset | Symbol / product | Contract value | Tick | Quote / settle | Result |
|---|---|---:|---:|---|---|
| BTC | BTCUSD / 27 | 0.001 BTC | 0.5 USD | USD / USD | PASS |
| Gold preferred | XAUTUSD / 131253 | 0.001 XAUT | 0.01 USD | USD / USD | PASS |
| Gold alternative | PAXGUSD / 123006 | 0.001 PAXG | 0.01 USD | USD / USD | PASS |

Four invalid catalog rows were ignored. The public worker used BTCUSD and XAUTUSD. At
`2026-11-24T05:27:04Z`, journal counts were BTC 7,288 trades / 4,888 book events and XAUT 7,244
trades / 6,457 book events. REST 1m/5m/15m candle responses validated for both symbols. Both book
checkpoints were valid and fresh at that sample. No Delta credential or private endpoint was used.

At the final `2026-11-24T05:50:09Z` check, counts had advanced to BTC 9,012 trades / 6,821 book
events and XAUT 9,495 trades / 8,946 book events, confirming collection was still active.

All six engines reached `WATCH`: `GOLD_FAST`, `GOLD_HOURLY`, `GOLD_SESSION`, `BTC_FAST`,
`BTC_HOURLY`, and `BTC_SESSION`. Their details reported no qualifying deterministic trigger or
insufficient persistent flow. No candidate or probability was fabricated.

The feed produced repeated fail-closed resynchronizations. The measured reason included an
order-book event older than the configured ten-second event-time limit (`stale_event`); a later
resource-contention interval produced a typed `DeltaDataIntegrityError`. Each occurrence invalidated
books and required a new snapshot. Continuous REST/stream candle reconciliation stayed `WAIT`, so
`/readyz` now correctly reports `required_market_sources=false` and HTTP 503 while `/healthz`, the
authenticated dashboard and collection remain available. Extended reconnect/clock/storage soak is
still required.

## Providers and budget

Official structured-output documentation and pricing were checked on 2026-11-24. The selected
cost-sensitive IDs were `gpt-6-luna` and `claude-haiku-5-5`, each documented at $0.10 per million
input tokens and $0.50 per million output tokens. Local rates are stored as 100,000 / 500,000
micro-USD per million tokens; the durable combined cap is 5,000,000 micro-USD.

| Provider | Account/model check | One paid structured smoke | Usage / cost | Status |
|---|---|---|---|---|
| OpenAI | model list returned HTTP 504; generation returned exact `gpt-6-luna` | strict schema valid | 1,842 input, 491 output; 430 micro-USD | PASS for generation |
| Anthropic | `claude-haiku-5-5` present in a 15-model list | SDK strict parse raised `ValidationError`; no retry | usage unknown; conservative reservation retained | FAIL |

Both calls used canonical digest
`9f6b2d9feb1bdf1e0e70490d6f868475ad38b71769108f349ed4c03e7cbad2f0` and a payload labelled
`SYNTHETIC_PROVIDER_CONNECTIVITY_SMOKE_NOT_MARKET_SIGNAL`. The ledger recorded two reserved calls,
430 micro-USD reported actual spend, one usage-unknown result and 1,495 micro-USD admission cost.
The Anthropic adapter was corrected offline to use `output_config.format` and preserve metadata
across semantic parse failures. It was not called again. `AI_ENABLED=false` remains required;
ongoing dual review and the review worker were not started.

Official references:

- OpenAI structured outputs: https://developers.openai.com/api/docs/guides/structured-outputs
- OpenAI models/pricing: https://developers.openai.com/api/docs/models and https://developers.openai.com/api/docs/pricing
- Anthropic structured outputs: https://platform.claude.com/docs/en/build-with-claude/structured-outputs
- Anthropic models/pricing: https://platform.claude.com/docs/en/models/overview and https://platform.claude.com/docs/en/about-claude/pricing

## Costs, dashboard and optional integrations

Delta India publishes a 0.05% futures taker fee, 0.02% maker fee and 18% GST on trading fees. The
single cross-asset setting uses a conservative 5.9 bps per side (5 bps × 1.18 GST) plus 5 bps
slippage per side. This is a research assumption, not an execution configuration. Gold's published
fee is lower, so the shared value does not understate the listed standard BTC rate.

The dashboard/API is running on `127.0.0.1:8000`; `/`, `/healthz`, authenticated `/api/health` and
`/api/engines` returned 200. Operator authentication is configured locally. Slack is no longer an
AI-readiness dependency: a confirmed decision can persist to the authenticated dashboard without
an alert outbox row. Alerts remain disabled.

CoinGlass is `BLOCKED`: no API key, plan entitlement or endpoint permission was available. No
CoinGlass call was made. Gold reference/basis/macro context remains unavailable.

## Verification

- Full Python suite: `278 passed`, one upstream Starlette/httpx warning, 687.98 seconds.
- Focused AI/dashboard smoke tests: `30 passed`.
- Delta/market-worker tests: `43 passed`.
- Dashboard readiness tests: `10 passed`.
- Final combined provider/dashboard/Delta/worker regression selection: `74 passed`.
- Repository-wide Ruff lint/format, Python compilation and `git diff --check`: PASS.
- Frontend `npm ci`: 69 packages, zero reported vulnerabilities; typecheck: PASS; production build:
  PASS (29 modules, 238.46 kB JavaScript / 73.75 kB gzip). The first build attempt was blocked by
  the filesystem sandbox; the identical approved build command then passed.

## Remaining gates

- Obtain a clean interval long enough for candle reconciliation and complete the extended soak.
- Run a separately authorized Anthropic recheck only after the UTC-day/provider ceiling resets or
  is explicitly changed. Do not enable ongoing AI until both providers pass.
- Verify CoinGlass key, subscription and endpoint/symbol permissions before enabling it.
- Slack is optional; a real message still requires destination-specific authorization.
- Destination Windows Server ACLs, Task Scheduler, reboot, backup/restore and HTTPS/VPN checks were
  not run on this Windows 10 workstation.
