# CODEX TASK — controlled Windows/live validation, then prospective observation

## Entry gate and scope

This is the next operational stage already described in `docs/IMPLEMENTATION_PLAN.md` and
`docs/WINDOWS_DEPLOYMENT.md`. It follows verified software acceptance; it does not add indicators,
strategy rules, a new data vendor, options or order execution.

The review at `e9f419f5ef576ec957f9d59107ab3f7f06815b23` leaves P6W-01 through P6W-06 open. Complete
[the corrective task](CODEX_PHASE_6_CONTRACT_CORRECTIONS.md) first. Its offline preparation work may
include the documents/templates below. Do not claim external checks ran simply because templates
or fixture tests exist.

## First instructions

1. Inspect git status and current SHA. Read AGENTS, DESIGN, README, implementation plan, the latest
   independent review and correction evidence, then the Windows runbook and relevant source/tests.
2. Record whether each software entry gate actually passes on the chosen deployment commit.
3. Create an operations task branch and finish all authorized offline preparation before requesting
   a missing operator prerequisite. Preserve existing authorizations; do not repeatedly ask for
   permission already supplied. Never request or print plaintext credentials in chat.
4. Inventory the destination host, approved data/account access, model names, explicit monetary and
   request limits, intended duration and notification destination. Existence of a credential is not
   by itself authorization to spend money or send a message.
5. Use `PASS`, `FAIL`, `BLOCKED` and `NOT_RUN` in an evidence worksheet. Keep local Linux checks,
   hosted Windows CI, Windows workstation checks and destination Windows Server observations distinct.

## A. Offline deliverables

Prepare a reviewable command pack and `docs/audits/operational-validation-template.md` containing:

- Exact code/config/contract versions; host/OS/runtime versions; task names, working directories,
  service identity, restricted paths/ACLs, loopback/HTTPS boundary and clock-health evidence fields.
- Expected health/readiness/authentication checks and actual timestamps/results, initially NOT_RUN.
- Bounded validation durations, request/attempt ceilings, token/cost limits, stop conditions and
  required artifacts. Do not insert arbitrary live budgets as if the user authorized them.
- Backup/restore and interrupted-run checks for the matching production, research and paper stores,
  manifests/configurations, source generations, checkpoints and report checksums.
- A provider/endpoint matrix separating implemented features from optional/future ones. Current
  CoinGlass OI/funding support does not mean a heatmap collector has been implemented. Liqwall remains
  a separately considered future input unless the user explicitly adds that integration to scope.
- A predeclared prospective-experiment template for the four arms and six engines, cost/latency
  assumptions, missing-data policy, holdout policy and evidence sufficiency criteria.

Reuse existing start/check/stop/backup scripts and the selected Task Scheduler design. If a bounded
validation command or structured evidence output is missing, implement the smallest required tool
with fake-transport tests and documented behavior before presenting it as runnable. Do not claim
that a proposed command already exists. Preparing task definitions does not install or start them.

## B. Destination Windows acceptance

With actual access and authorization, verify the intended Windows Server:

- Python/Node/PowerShell versions and exact deployment SHA; least-privilege identity and ACLs;
  UTC synchronization; exact frontend origin; loopback API plus restricted authenticated HTTPS access.
- Existing MarketIntel API, market worker, review worker and alert worker tasks, with bounded restart
  policy and no overlapping instances. External flags begin false; trading remains refused.
- Foreground startup, supervised restart/reboot and worker recovery. Record real host observations;
  hosted CI cannot substitute for this evidence.
- Online backup integrity, stopped-writer restore of a matching artifact set and recovery checks.
  Preserve failed databases; do not overwrite live state or reboot a host without authorization.

Two required recovery examples: terminate a worker after a committed prefix and verify idempotent
resume; restore a matching backup set and verify that source generations/checkpoints still match.
Uncertain provider dispatch or remote receipt requires reconciliation, never blind requeue.

## C. Bounded external integration checks

Run only the specific authorized checks with available prerequisites. Do not run indefinitely.

| Integration | Record and verify |
|---|---|
| Delta public feed | Actual listed BTC/gold product IDs, units, contract/tick values; event/receive clocks; closed candles; source age; sequence/checksum, reconnect and reconciliation |
| Gold reference | Record supplied source/license/instrument details. The production adapter remains unwired: retain reference/basis/macro UNAVAILABLE and validation BLOCKED until an implemented adapter and authorization exist; adding it requires separate scope |
| CoinGlass | Provided plan and permitted implemented endpoints, actual supported symbols/exchanges, response timestamps, refresh age, typed failures and redacted usage evidence |
| GPT + Claude | Identical canonical input digest, independent analysis, actual requested/returned models, request identifiers, validated responses, measured latency/usage/cost within supplied ceilings |
| Alerts | Existing channel only; one specifically authorized destination/test after stale/terminal suppression checks; actual receipt or explicit uncertain-receipt state |

Check current official documentation when changing protocol or model settings. Do not infer access
from website charts or assume Delta gold is spot XAU/USD. A missing gold product remains unavailable.
Never add account/trading permissions to make a public feed check work.

Two failure controls: interrupt a book sequence and require a new valid snapshot before eligibility
returns; make one model unavailable and verify no dual confirmation. Also preserve request-rate and
budget refusal, stale/expired suppression and duplicate-intent controls. Real notification sending
requires the specific existing or newly provided user authorization and destination.

## D. Freeze and begin prospective paper observation

Only after the required operational checks pass, freeze the experiment before outcomes arrive:

- Common candidate/revision selection and four arms: rules-only, GPT, Claude, dual.
- Separate BTC/Gold and FAST/HOURLY/SESSION denominators, decisions, rejections, WAIT/unavailable,
  latency, fees/slippage/funding assumptions, outages and evidence gaps.
- Required source identity/generation and supported collection bridge. The existing local-stream
  importer needs an actual approved producer; a complete fixture file is not elapsed observation.
- Training/development/final holdout boundaries, cost assumptions and sample/coverage/uncertainty
  criteria declared before examining the protected outcomes.

Two comparisons: dual filtering versus rules-only after attributable costs, and FAST versus SESSION
behavior on the actually observed data. Include abstentions and incomplete records; do not report
only winning/filled cases. Elapsed weeks without adequate independent observations remain insufficient.

Preserve `SYNTHETIC_FIXTURE`, retrospective/exploratory and genuine prospective evidence separately.
Do not claim an accuracy percentage, probability, profitable edge or readiness to execute orders
from software checks or model agreement.

## Completion report

Provide the code/config SHA, worksheet, commands and real observations; actual requests/costs and
redacted receipt IDs; failed/blocked/not-run checks with exact prerequisites; recovery results; and
the frozen prospective configuration if that stage started. Missing server access or credentials
does not justify leaving the offline preparation unfinished. Do not auto-merge or deploy; stop after
the authorized bounded work and report the next concrete operator action.
