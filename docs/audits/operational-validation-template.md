# Controlled operational-validation worksheet

This worksheet is prepared offline for the stage after Phase 6 software acceptance. Every external
row starts `NOT_RUN`. Use only `PASS`, `FAIL`, `BLOCKED`, or `NOT_RUN`; attach evidence rather than
inferring success from configuration. Never paste secrets into this file.

## Frozen identity

| Field | Required value | Status / evidence |
|---|---|---|
| Deployment commit | Exact reviewed Git SHA | NOT_RUN — record before install |
| Application release | `VERSION` plus dirty-tree check | NOT_RUN |
| Research algorithm | `phase6-contract-corrections-shared-v4` | NOT_RUN |
| Derived checkpoint | `phase6-contract-corrections-derived-state-v3` | NOT_RUN |
| Outcome evaluator | `phase6-contract-corrections-outcome-v4` | NOT_RUN |
| Manifest/config | Canonical IDs and SHA-256 | NOT_RUN |
| Host | Name, Windows edition/build, CPU/RAM/disk | NOT_RUN — destination access required |
| Runtime | Python, Node, npm, PowerShell versions | NOT_RUN |
| Clock | UTC source, offset, last sync, drift | NOT_RUN |

## Host and service boundary

| Check | Expected boundary | Status / evidence |
|---|---|---|
| Service identity | Dedicated least-privilege user; no interactive admin need | NOT_RUN |
| Working/data/log paths | Absolute paths owned only by operator/service identity | NOT_RUN |
| Task Scheduler | API, market, review, alert tasks; no overlapping instances; bounded restart | NOT_RUN |
| API listener | `127.0.0.1`; remote access only through authenticated HTTPS/VPN proxy | NOT_RUN |
| Authentication | Operator auth enabled; non-ASCII credential control checked | NOT_RUN |
| External defaults | live ingestion, AI, alerts, paper collection all false | NOT_RUN |
| Trading refusal | `TRADING_ENABLED=true` rejected; no order routes or credentials | NOT_RUN |
| Health/readiness | timestamped `/healthz` and authenticated `/api/health` results | NOT_RUN |
| Restart/reboot | foreground start, supervised restart, reboot recovery | NOT_RUN |

Record task names, executable arguments, working directories, service identity, restart policy,
ACL output, loopback binding, HTTPS origin, clock commands, timestamps, logs, and redacted artifact
paths here before marking a row `PASS`.

## Bounded authorization envelope

No live ceiling is authorized by this template. The operator must fill every blank and approve the
specific run before external flags are changed.

| Boundary | Authorized value | Actual result |
|---|---|---|
| Start/end or maximum duration | `<REQUIRED>` | NOT_RUN |
| Delta sample/event ceiling | `<REQUIRED>` | NOT_RUN |
| GPT requests/attempts/tokens/cost | `<REQUIRED>` | NOT_RUN |
| Claude requests/attempts/tokens/cost | `<REQUIRED>` | NOT_RUN |
| CoinGlass requests and permitted endpoints | `<REQUIRED>` | NOT_RUN |
| Alert destination and maximum messages | `<REQUIRED>` | NOT_RUN |
| Stop conditions | stale clock/source, budget/rate refusal, uncertain receipt, operator stop | NOT_RUN |

Required artifacts: redacted configuration hash, exact commands, UTC start/stop, request IDs,
requested/returned model IDs, token/usage/cost records, source/product identities, reconnect and
reconciliation logs, notification receipt or `RECEIPT_UNKNOWN`, database integrity output, and
checksummed reports. Stop immediately on any ceiling breach or identity mismatch.

## Backup, restore, and interrupted-run evidence

| Check | Required evidence | Status |
|---|---|---|
| Online backup | production, research, paper stores plus manifests/config/source generations | NOT_RUN |
| Integrity | SQLite integrity and report `SHA256SUMS` verified | NOT_RUN |
| Prefix recovery | terminate after a committed prefix; fresh process resumes idempotently | NOT_RUN |
| Provider uncertainty | reconcile persisted result/dispatch state; no blind redispatch | NOT_RUN |
| Stopped-writer restore | restore one matching artifact set; preserve failed database separately | NOT_RUN |
| Restored identities | generations, checkpoints, cursors, manifests and configs match | NOT_RUN |

## Integration matrix

| Integration | Implemented scope | Live prerequisite | Status |
|---|---|---|---|
| Delta India public | product discovery, BTC/available tokenized-gold trades/books/candles, CRC/recovery | destination network and bounded collection authorization | NOT_RUN |
| Gold reference | typed unavailable contract only; production adapter is not wired | separately licensed source and new implementation scope | BLOCKED |
| CoinGlass | optional BTC OI and last-closed funding only | supplied plan/key and endpoint entitlement | NOT_RUN |
| GPT | frozen structured review transport | account/model, official rates, explicit request/cost ceilings | NOT_RUN |
| Claude | frozen structured review transport | account/model, official rates, explicit request/cost ceilings | NOT_RUN |
| Slack | existing single-channel adapter | authorized destination and one-message authorization | NOT_RUN |
| Liqwall/heatmaps/options/orders | not implemented and outside this task | separate approved scope | BLOCKED |

Required negative controls: interrupt a book sequence and require a new snapshot; make one model
unavailable and require no dual confirmation; preserve budget/rate refusal, stale/expired alert
suppression, and duplicate-intent fencing.

## Prospective observation entry gate

Do not start elapsed observation until all required host/data/provider checks pass and the template
at `config/prospective-experiment.template.json` is copied to a new immutable configuration with
real approved ceilings and source identities. Decisions must be persisted before eligible entry and
future outcomes. Report six-engine/four-arm denominators, abstentions, incomplete paths, outages,
latency and attributable cost. Synthetic fixtures and retrospective provider answers never count as
prospective evidence.
