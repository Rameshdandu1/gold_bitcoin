# Security and operating policy

1. `.env` stays local and gitignored. Use distinct read-only API credentials, never exchange trading keys in this codebase. OpenAI, Anthropic, CoinGlass keys may be used **only** server side.
2. Bind FastAPI to `127.0.0.1`; don't expose port 8000 to internet. Put TLS-authenticated reverse proxy / VPN in front. Block everything else via Windows Defender Firewall. No permissive CORS in production.
3. Run worker and API as separate least-privileged Windows service accounts, with automatic recovery, service-specific log directories and filesystem ACLs for `.env`/database.
4. Rotate all API keys exposed accidentally. `git rm` does not erase secrets from history; use GitHub secret scanning plus credential revocation.
5. Treat all external text/AI responses as untrusted. Use Pydantic validated fields, no dynamic `eval`, no model-generated SQL or shell commands. No tools in analyst prompts.
6. Retain raw market data only within provider license. Encrypt backup disks; monitor byte growth and archive controls. Do not redistribute licensed CoinGlass data unless allowed.
7. Risk circuit breakers: stale/missing data => WAIT; bad checksum => invalid book; AI timeout/schema mismatch => WAIT; spending cap reached => WAIT; unsupported symbol => UNAVAILABLE.
8. Operator access log, budget alerts and backup restore drill before any external deployment. A trading execution service is out of scope; absence of execution is a feature, not a missing toggle.
