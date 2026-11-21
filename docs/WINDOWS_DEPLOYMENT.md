# Native Windows operation and recovery

This is a staged single-host research runbook for Windows Server 2022/2025. It does not claim that a
Windows service installation, external provider, live feed soak, Slack delivery or deployment was
performed during Phase 3 development.

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
fee/slippage assumptions and Slack destination/token. Credentials alone are not permission for a
paid smoke test. The project contains no exchange key or order setting.

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
market-worker heartbeat/source age, provider/alert configuration, queue leases and UTC-day budget.
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
.\.venv\Scripts\python.exe -m marketintel.research validate-data --manifest tests\fixtures\research\manifest.json
.\.venv\Scripts\python.exe -m marketintel.research replay --manifest tests\fixtures\research\manifest.json --config tests\fixtures\research\experiment.json --database data\research.sqlite3 --production-database data\marketintel.sqlite3 --checkpoint data\research-checkpoint.json
.\.venv\Scripts\python.exe -m marketintel.paper_worker --config config\paper-worker.example.json --once
```

The example paper config and `PAPER_COLLECTION_ENABLED` are disabled. Enable collection only for an
approved local recorded-decision source; the worker is bounded by `--once` and cannot send orders.
Back up both research SQLite files, manifests, configs, checkpoints and report `SHA256SUMS` together.
Verify checkpoint restart hash parity, retain explicit source gaps and never edit a recorded paper
decision. Destination-server task installation, reboot/restore and long paper soak were not run.

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
