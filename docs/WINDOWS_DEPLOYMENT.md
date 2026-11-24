# Native Windows operation and recovery

This is a staged single-host research runbook for Windows Server 2022/2025. It does not claim that a
Windows service installation, external provider, live feed soak, Slack delivery or deployment was
performed during Phase 3 development.

Use the prepared [bounded command pack](OPERATIONAL_VALIDATION_COMMAND_PACK.md) and
[PASS/FAIL/BLOCKED/NOT_RUN worksheet](audits/operational-validation-template.md) for destination
acceptance. They are offline preparation, not evidence that any destination or external check ran.

## 1. Install and verify

Use Python 3.12+, Node 20+/22 and Git under an unprivileged local identity. Keep the checkout, `.env`,
SQLite and backups in ACL-restricted directories. Confirm Windows Time is synchronized.

```powershell
Set-Location C:\MarketIntelligence
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
Copy-Item .env.example .env
notepad .env
.\scripts\verify.ps1
```

Set unique `OPERATOR_USERNAME`/`OPERATOR_PASSWORD`. Leave ingestion, AI and alerts false initially.
AI additionally requires two explicit model IDs/keys, verified non-zero pricing and spend caps,
and fee/slippage assumptions. Slack is optional for dashboard-only operation and remains a separate
alert readiness gate. Credentials alone are not permission for a paid smoke test. The project
contains no exchange key or order setting.

After explicit request/cost authorization, the bounded smoke command reserves the daily ledger
before making at most one call per provider:

```powershell
.\.venv\Scripts\python.exe -m marketintel.provider_smoke --authorize-paid-smoke --output data\operational\provider-smoke.json
```

## 2. Manual staged startup

Run each foreground command in a separate PowerShell window. They exit without external work when
their feature flag is false.

```powershell
.\scripts\start-api.ps1
.\scripts\start-worker.ps1
.\scripts\start-review-worker.ps1
.\scripts\start-alert-worker.ps1
```

The API binds to `127.0.0.1:8000`. Check it without putting credentials in a URL:

```powershell
$env:OPERATOR_USERNAME = 'local-operator'
$env:OPERATOR_PASSWORD = Read-Host 'Operator password'
.\scripts\check-service.ps1
```

`/healthz` proves only that the API process runs. `/readyz` separately reports migrations, auth,
market-worker heartbeat, current discovery/WebSocket/book/reconciliation health, provider/alert
configuration, queue leases and UTC-day budget.
It never calls a paid provider.

## 3. HTTPS and browser access

Do not expose port 8000. Put IIS/ARR or another reviewed reverse proxy on the same host, terminate
HTTPS there and proxy only to `127.0.0.1:8000`. Permit only the expected host/origin and do not pass
or trust arbitrary identity headers. Restrict inbound firewall rules to the operator VPN/network.
Compiled `frontend/dist` is served by the authenticated backend. Basic authentication is acceptable
only through this encrypted boundary.

## 4. Task Scheduler installation pattern

Task Scheduler is the selected built-in supervisor; installation remains an operator action. Create
four “At startup” tasks under the least-privilege service identity with working directory
`C:\MarketIntelligence` and actions:

```text
powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File C:\MarketIntelligence\scripts\start-api.ps1
powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File C:\MarketIntelligence\scripts\start-worker.ps1
powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File C:\MarketIntelligence\scripts\start-review-worker.ps1
powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File C:\MarketIntelligence\scripts\start-alert-worker.ps1
```

Name them `MarketIntel-API`, `MarketIntel-MarketWorker`, `MarketIntel-ReviewWorker` and
`MarketIntel-AlertWorker`. Configure restart every 1 minute, at most 5 times, stop after 72 hours
only if an approved maintenance policy restarts it, and “do not start a new instance” on overlap.
Redirect task history/operational logs into an ACL-restricted, size-bounded log directory and create
an Event Log alert for repeated failure. Do not run as Administrator.

```powershell
Start-ScheduledTask -TaskName MarketIntel-API
Get-ScheduledTask -TaskName 'MarketIntel-*' | Get-ScheduledTaskInfo
.\scripts\stop-tasks.ps1
```

After installation, reboot the host and verify bounded recovery, worker heartbeats, lease reclaim and
no duplicate outbox intents. This reboot/soak is not replaced by unit tests.

## 5. Backup, restore and migration recovery

The online backup uses SQLite's backup API and runs integrity checks. Use a local encrypted target,
then copy to an approved encrypted off-host location under retention policy.

```powershell
.\scripts\backup-db.ps1 -Destination C:\MarketIntelBackup\marketintel-20261121.sqlite3
.\.venv\Scripts\python.exe -m marketintel.maintenance verify C:\MarketIntelBackup\marketintel-20261121.sqlite3
```

Restore only while all four tasks are stopped. Preserve the failed database for forensics; do not
delete append-only audit rows. Verify the backup before replacing the configured database path:

```powershell
.\scripts\stop-tasks.ps1
.\.venv\Scripts\python.exe -m marketintel.maintenance verify C:\MarketIntelBackup\marketintel-20261121.sqlite3
Copy-Item data\marketintel.sqlite3 data\marketintel.failed.sqlite3 -ErrorAction SilentlyContinue
Copy-Item C:\MarketIntelBackup\marketintel-20261121.sqlite3 data\marketintel.sqlite3
Start-ScheduledTask -TaskName MarketIntel-API
.\scripts\check-service.ps1
```

Migrations are additive and idempotent. There is no destructive down-migration. A rollback means
stopping writers, restoring the pre-migration backup and running the previous signed application
version. A `DISPATCHED` review job or `RECEIPT_UNKNOWN` alert requires operator reconciliation; do
not blindly reset it to queued.

## 6. Offline research and bounded paper recording

Use the repository virtual environment and Windows paths. Research and paper files must not equal
`DATABASE_PATH`:

```powershell
.\.venv\Scripts\python.exe -m marketintel.research_fixtures --output data\phase5-fixtures
.\.venv\Scripts\python.exe -m marketintel.research validate-data --manifest data\phase5-fixtures\gold-manifest.json
.\.venv\Scripts\python.exe -m marketintel.research run-workflow --manifest data\phase5-fixtures\gold-manifest.json --config data\phase5-fixtures\gold-experiment.json --database data\gold-research.sqlite3 --production-database data\marketintel.sqlite3
.\.venv\Scripts\python.exe -m marketintel.research paper-workflow --database data\gold-research.sqlite3 --paper-database data\gold-paper.sqlite3 --production-database data\marketintel.sqlite3 --experiment-id phase5-gold-workflow-v1
.\.venv\Scripts\python.exe -m marketintel.research evaluate --database data\gold-research.sqlite3 --production-database data\marketintel.sqlite3 --experiment-id phase5-gold-workflow-v1
.\.venv\Scripts\python.exe -m marketintel.research report --database data\gold-research.sqlite3 --paper-database data\gold-paper.sqlite3 --production-database data\marketintel.sqlite3 --experiment-id phase5-gold-workflow-v1 --output data\gold-report
.\.venv\Scripts\python.exe -m marketintel.paper_worker --config config\paper-worker.example.json --once
```

For a fresh-process Python-allocation probe, generate a fixture with a declared historical prefix
and wrap the same public command. This is an offline capacity regression, not total service RSS:

```powershell
.\.venv\Scripts\python.exe -m marketintel.research_fixtures --output data\phase6-memory --historical-quotes 8000
.\.venv\Scripts\python.exe scripts\phase6-workflow-memory-probe.py -- run-workflow --manifest data\phase6-memory\gold-manifest.json --config data\phase6-memory\gold-experiment.json --database data\phase6-memory\gold-research.sqlite3 --production-database data\marketintel.sqlite3
.\.venv\Scripts\python.exe scripts\phase6-workflow-memory-probe.py -- paper-workflow --database data\phase6-memory\gold-research.sqlite3 --paper-database data\phase6-memory\gold-paper.sqlite3 --production-database data\marketintel.sqlite3 --experiment-id phase5-gold-workflow-v1
```

Repeat the workflow with the BTC manifest/config and `phase5-btc-workflow-v1`. The connected paper
command persists frozen arms before latency-adjusted eligible entry and derives outcomes from later
quotes/source events. Fixture decisions are `SIMULATED_PROSPECTIVE`, not elapsed prospective
evidence. Every generated file is labelled `SYNTHETIC_FIXTURE`; delete it before configuring licensed/private evidence. The
example paper config and `PAPER_COLLECTION_ENABLED` are disabled. An approved local paper stream
must declare a stable `source_identity` and increment `source_generation` on rotation; replacement,
reordering or truncation before the committed cursor is refused using a consumed-prefix SHA-256.
Each imported event and cursor advance commit atomically. The worker is bounded by `--once` and
cannot send orders.

To rehearse restart recovery, stop after a bounded committed prefix and invoke the same command
again. Do not change the manifest, configuration, processing delay or entry latency under the same
run identity:

```powershell
.\.venv\Scripts\python.exe -m marketintel.research run-workflow --manifest data\phase5-fixtures\gold-manifest.json --config data\phase5-fixtures\gold-experiment.json --database data\gold-resume.sqlite3 --production-database data\marketintel.sqlite3 --maximum-events 500
.\.venv\Scripts\python.exe -m marketintel.research run-workflow --manifest data\phase5-fixtures\gold-manifest.json --config data\phase5-fixtures\gold-experiment.json --database data\gold-resume.sqlite3 --production-database data\marketintel.sqlite3
.\.venv\Scripts\python.exe -m marketintel.research paper-workflow --database data\gold-resume.sqlite3 --paper-database data\gold-paper-resume.sqlite3 --production-database data\marketintel.sqlite3 --experiment-id phase5-gold-workflow-v1 --maximum-events 100
.\.venv\Scripts\python.exe -m marketintel.research paper-workflow --database data\gold-resume.sqlite3 --paper-database data\gold-paper-resume.sqlite3 --production-database data\marketintel.sqlite3 --experiment-id phase5-gold-workflow-v1
```

`DERIVED_WORKFLOW_PARTIAL` and `SIMULATED_PROSPECTIVE_WARMUP_PARTIAL` are expected after the first
bounded calls. Completion requires `input_complete=true`, no pending terminal arms and the frozen
input count. Back up research and paper databases together; never copy only a checkpoint table.

Back up production, research and paper SQLite files with their manifests, configurations, source
generation records, checkpoints and report `SHA256SUMS`. A safe restore stops all writers, verifies
each database, restores the matching artifact set, then reruns the bounded command. Do not copy a
cursor without its exact source identity/generation. Destination-server Task Scheduler install,
reboot/restore, log rotation and long paper/live soaks were not run in Phase 6. Native Windows
checks validate code paths, not the destination host.

### Controlled live-validation checklist (not executed by offline closeout)

1. Start with all external flags false; record host/version/config fingerprints and verify ACLs,
   UTC synchronization, service restart, reboot and matching-database backup/restore.
2. With bounded authorization, discover current Delta BTC and Gold instruments, record product/unit
   versions, collect a short trade/book sample, interrupt during a sequence gap and prove snapshot
   resynchronization before eligibility returns.
3. Verify CoinGlass entitlement/pair support and Gold-reference availability; retain unavailable
   states rather than substituting data.
4. Under explicit provider budgets, verify configured and returned GPT/Claude model identities with
   the same canonical input. One-provider failure must remain WAIT/unavailable.
5. Send one explicitly authorized test notification only after stale/terminal suppression checks;
   retain the remote receipt or `RECEIPT_UNKNOWN` state.
6. Freeze prospective selection/cost rules before collection. Synthetic/retrospective outcomes do
   not count as elapsed prospective evidence.

## 7. Operational acceptance still required

- Verify Delta symbols/units and perform an extended reconnect, gap, clock-drift and storage-rate
  soak; SQLite capacity is intentionally not claimed.
- Verify OpenAI/Anthropic account/model access and official current pricing in one bounded,
  explicitly authorized smoke test.
- Verify CoinGlass plan, instruments, license and redistribution rights separately.
- Authorize a private Slack channel and one real message only in a separate operator-approved test.
- Execute Task Scheduler installation, reboot recovery, log rotation and backup restore on the
  intended Windows host.
- Keep execution absent. Passing checks or dual-model agreement does not establish profitability.
