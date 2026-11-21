# ADR 0004: single-operator authentication and Slack durable outbox

Status: accepted for Phase 3 development.

## Context

The native Windows research deployment has one operator and no identity provider. Dashboard/API
exposure still needs a concrete fail-closed boundary. A confirmation and its notification intent
must survive restart without reusing an older candidate revision or pretending external delivery is
exactly once.

## Decision

Use application HTTP Basic authentication with constant-time credential comparison. Credentials are
environment secrets; no credential is compiled into React. All routes except minimal `/healthz` are
protected, including docs and OpenAPI. The API binds to loopback. External use requires an HTTPS
reverse proxy or VPN with exact ingress and CORS restrictions. Forwarded identity headers are not
trusted.

Use Slack as the first complete channel. The atomic consensus transaction creates one revision-
scoped outbox intent per decision/event/destination. A separate leased worker revalidates lifecycle,
revision and expiry, uses bounded backoff, records the Slack timestamp receipt, and terminates on an
accepted-but-receipt-unknown outcome. Slack `client_msg_id` is derived from the stable delivery key,
but the application does not promise universal external exactly-once behavior. Terminal
invalidation/expiry intents have their own lifecycle-event identities. Alerts remain disabled by
default.

## Consequences

- Basic authentication is appropriate only behind encrypted trusted transport; it is not an
  internet-facing identity platform.
- Empty auth configuration makes protected routes unavailable rather than public.
- Slack is implemented and fake-transport tested; Telegram/email are not claimed.
- No real message, paid model call, service installation or deployment is part of development
  verification.
