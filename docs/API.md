# Local HTTP API (read-only MVP)

All endpoints are intentionally read-only; **no order, trading account or credential endpoints exist**. Bind to localhost. Until authentication + HTTPS proxy is added, never expose this API directly to the internet.

| Route | Response / purpose |
|---|---|
| `GET /api/health` | ingestion/AI flags, UTC time, worker quality statuses, trading always disabled |
| `GET /api/engines` | six horizon configurations and last stored decision state |
| `GET /api/candidates?limit=50` | immutable candidate packet and latest consensus, max 200 rows |
| `GET /api/candidates/{candidate_id}/assessments` | separately persisted GPT/Claude parsed assessments (if called) |
| `GET /docs` | generated FastAPI OpenAPI docs |

**No auth in starter**: localhost-only is a safety requirement, not an access-control substitute. All client UI values must be labelled unreviewed/unavailable when observations are missing. Future endpoints need stable response schemas, pagination, authenticated sessions and rate limits.

## Provider configuration
Delta public REST: `https://api.india.delta.exchange` / public WS: `wss://public-socket.india.delta.exchange`. CoinGlass V4: `https://open-api-v4.coinglass.com` header `CG-API-KEY`. OpenAI Responses structured parse and Anthropic Messages parse are used behind typed adapters, disabled by default.

## Candidate outcomes and lifecycle
`UNAVAILABLE → WATCH → CANDIDATE → WAIT/CONFIRMED/REJECTED → TARGET/STOP/AMBIGUOUS/EXPIRED` is the target design. The starter stores provisional `CANDIDATE` and some `WAIT` statuses, not a complete lifecycle machine. Outcome backtest helper labels outcomes but does not yet persist them or validate slippage.
