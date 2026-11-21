# Local HTTP API (read-only MVP)

All endpoints are intentionally read-only; **no order, trading account or credential endpoints exist**. Bind to localhost. Until authentication + HTTPS proxy is added, never expose this API directly to the internet.

| Route | Response / purpose |
|---|---|
| `GET /api/health` | ingestion/AI flags, UTC time, worker quality statuses, trading always disabled |
| `GET /api/engines` | six horizon configurations and last stored decision state |
| `GET /api/candidates?limit=50` | immutable candidate packet and latest consensus, max 200 rows |
| `GET /api/candidates/{candidate_id}/assessments` | separately persisted GPT/Claude parsed assessments (if called) |
| `GET /api/candidates/{candidate_id}/lifecycle` | append-only Phase 2 state, invalidation and expiry events |
| `GET /api/candidates/{candidate_id}/revisions` | immutable, duplicate-safe candidate revisions |
| `GET /api/snapshots/{snapshot_id}` | exact content-addressed quantitative feature snapshot, or `null` |
| `GET /docs` | generated FastAPI OpenAPI docs |

**No auth in starter**: localhost-only is a safety requirement, not an access-control substitute. All client UI values must be labelled unreviewed/unavailable when observations are missing. Future endpoints need stable response schemas, pagination, authenticated sessions and rate limits.

## Provider configuration
Delta public REST: `https://api.india.delta.exchange` / public WS: `wss://public-socket.india.delta.exchange`. CoinGlass V4: `https://open-api-v4.coinglass.com` header `CG-API-KEY`. OpenAI Responses structured parse and Anthropic Messages parse are used behind typed adapters, disabled by default.

## Candidate outcomes and lifecycle
Phase 2 detector states are `UNAVAILABLE`, `WAIT`, `WATCH`, `CANDIDATE`, `REJECTED`,
`INVALIDATED` and `EXPIRED`. Legal transitions are validated and appended; candidate revisions are
immutable and duplicate-safe. There is intentionally no Phase 2 `CONFIRMED` state. Phase 3 may add
independent AI assessments and deterministic consensus, while target/stop research labelling and
net-of-cost validation remain Phase 4 work.

Engine state is read from durable service status. When a snapshot exists, the API reports its
verified market symbol rather than substituting the configured symbol preference. Candidate and
snapshot payloads are research evidence and are never order instructions.
