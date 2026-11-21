# Security and operating policy

1. `.env` stays local and gitignored. This repository must never receive exchange trading keys,
   account credentials, live positions, or execution permissions. OpenAI, Anthropic, CoinGlass and
   Slack secrets are server-side environment values only.
2. HTTP Basic is the concrete single-operator authentication boundary. Empty credentials fail
   closed. It does not encrypt traffic: bind FastAPI to `127.0.0.1` and require an operator-managed
   HTTPS reverse proxy or VPN before remote access. Restrict proxy ingress and Windows Firewall;
   never trust forwarded identity headers from arbitrary clients.
3. CORS uses exact configured origins. Swagger, OpenAPI, the dashboard and every operational API
   route are protected. Only minimal `/healthz` liveness is public. Browser credentials are not
   embedded into the frontend bundle.
4. Provider responses, exchange payloads and market/reference text are untrusted. Strict Pydantic
   schemas, fixed prompts, no analyst tools/browsing, no dynamic SQL/eval and server-owned metadata
   form the trust boundary. Neither analyst sees the other's result.
5. Missing pricing, fees/slippage, model IDs, secrets, destination, data freshness, validated book,
   revision identity, or spend capacity forces `NOT_READY`/`WAIT` with no discretionary fallback.
6. Durable leases are fenced. A dispatched request is not automatically reclaimed as unpaid;
   unknown provider usage and unknown Slack receipts remain explicit. External exactly-once delivery
   is not promised.
7. Run API, market, review and alert workers under a least-privilege Windows identity. Restrict ACLs
   on `.env`, SQLite and backups; rotate accidentally exposed credentials immediately. Keep logs free
   of payload secrets and Authorization headers.
8. Encrypt and retain market/audit data only within source licenses. Do not publicly redistribute
   licensed CoinGlass data. Verify backups with SQLite integrity and foreign-key checks and test a
   restore before deployment.
9. There is no trading execution service. Model agreement is not a probability, profitability
   estimate, or authorization to trade.
