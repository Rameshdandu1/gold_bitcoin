# Local operator HTTP API

The service is read-only and contains no order, account, leverage, or execution route. Bind it to
`127.0.0.1`. HTTP Basic authentication protects the dashboard, API, Swagger UI and OpenAPI. Only
`GET /healthz` is intentionally unauthenticated and returns non-sensitive process liveness. If
operator credentials are absent, protected routes return 503 rather than opening access. Use Basic
authentication only over a trusted loopback connection, VPN, or an HTTPS reverse proxy.

| Route | Response / purpose |
|---|---|
| `GET /healthz` | minimal unauthenticated process liveness |
| `GET /readyz` | authenticated configuration, migration, heartbeat, source, queue and budget gates; makes no provider call |
| `GET /api/health` | UTC response time, flags, source transitions/heartbeats, queue and spend state |
| `GET /api/engines` | six engine descriptors and last durable state |
| `GET /api/candidates?limit=50&offset=0` | bounded active revisions, current lifecycle, review run/attempt metadata and historical consensus |
| `GET /api/candidates/{id}/lifecycle?limit=100&offset=0` | append-only state events |
| `GET /api/candidates/{id}/revisions?limit=100&offset=0` | immutable revisions |
| `GET /api/candidates/{id}/assessments` | legacy Phase 2 records, never an authorization source |
| `GET /api/snapshots/{snapshot_id}` | exact quantitative feature snapshot or `null` |
| `GET /api/budget` | current UTC-day provider reservations and reported costs |
| `GET /api/queue` | review-job and alert-outbox counts plus stale lease counts |
| `GET /api/research/summary` | isolated experiment/paper counts and explicit evidence classification; no external call |
| `GET /api/research/experiments?limit=50&offset=0` | bounded experiment identities, canonical hashes, data mode and source coverage |
| `GET /api/research/experiments/{id}` | authoritative stored manifest/configuration, counts, engine matrix, reports and scoped action counters |
| `GET /api/research/experiments/{id}/engines` | six-engine evaluation/candidate counts for the selected experiment |
| `GET /api/research/experiments/{id}/opportunities?limit=50&offset=0` | bounded selected revision, four-arm decision and outcome records |
| `GET /api/research/paper/transitions?limit=100&offset=0` | append-only prospective paper decision/outcome transitions without raw provider payloads |
| `GET /docs`, `/openapi.json` | authenticated FastAPI schema and documentation |

Candidate responses keep `current_lifecycle_*` separate from historical consensus. Provider cards
use each attempt's `provider`, `status`, requested/returned model and completion time; consensus
presence is not evidence both providers are currently available. Prices are quote-price units for
the verified Delta instrument. Gold qualification remains tokenized XAUT/PAXG, not spot gold.

Allowed CORS origins are an exact operator list. No wildcard origin or client-supplied identity
header is trusted. Provider keys, Slack tokens and budget pricing are never returned.

## External integrations

Delta public REST/WS, OpenAI Responses structured parsing, Anthropic Messages structured parsing,
CoinGlass V4 and Slack Web API are behind environment configuration. AI, CoinGlass, live ingestion
and Slack delivery are disabled by default. Configuring credentials does not authorize tests to make
paid calls or send messages. Current model/account entitlement and actual Slack delivery require a
separate bounded operator-approved smoke test.

The research summary uses the same operator authentication as every non-liveness route. Action
counters carry an explicit experiment scope; an unmeasured counter is `null`, never a fabricated
zero. Dataset mode, hashes and counts come from the selected immutable experiment. Licensed raw
records and raw provider payloads are not returned.
`NOT_STARTED`, `EXPLORATORY` and insufficient-evidence labels are evidence states, not zero return
or a failed-strategy result. It returns counts and classifications, not secrets or dataset rows.
