# Bounded operational-validation command pack

These commands prepare and inspect the existing Windows architecture. They do not install tasks,
enable external integrations, spend money, send notifications, or deploy. Run from the repository
root in PowerShell with all external flags false.

## Offline entry gate

```powershell
git status --short --branch
git rev-parse HEAD
Get-Content VERSION
py -3.12 --version
node --version
npm --version
pwsh --version
.\scripts\verify.ps1
.\.venv\Scripts\python.exe -m marketintel.research_fixtures --output data\validation-fixtures
```

For each of `gold`/`phase5-gold-workflow-v1` and `btc`/`phase5-btc-workflow-v1`, execute the
bounded local workflow below. Replace `<asset>` and `<experiment>` literally; do not enable live
flags.

```powershell
.\.venv\Scripts\python.exe -m marketintel.research validate-data --manifest data\validation-fixtures\<asset>-manifest.json
.\.venv\Scripts\python.exe -m marketintel.research run-workflow --manifest data\validation-fixtures\<asset>-manifest.json --config data\validation-fixtures\<asset>-experiment.json --database data\<asset>-research.sqlite3 --production-database data\marketintel.sqlite3 --maximum-events 500
.\.venv\Scripts\python.exe -m marketintel.research run-workflow --manifest data\validation-fixtures\<asset>-manifest.json --config data\validation-fixtures\<asset>-experiment.json --database data\<asset>-research.sqlite3 --production-database data\marketintel.sqlite3
.\.venv\Scripts\python.exe -m marketintel.research paper-workflow --database data\<asset>-research.sqlite3 --paper-database data\<asset>-paper.sqlite3 --production-database data\marketintel.sqlite3 --experiment-id <experiment> --maximum-events 100
.\.venv\Scripts\python.exe -m marketintel.research paper-workflow --database data\<asset>-research.sqlite3 --paper-database data\<asset>-paper.sqlite3 --production-database data\marketintel.sqlite3 --experiment-id <experiment>
.\.venv\Scripts\python.exe -m marketintel.research evaluate --database data\<asset>-research.sqlite3 --production-database data\marketintel.sqlite3 --experiment-id <experiment>
.\.venv\Scripts\python.exe -m marketintel.research report --database data\<asset>-research.sqlite3 --paper-database data\<asset>-paper.sqlite3 --production-database data\marketintel.sqlite3 --experiment-id <experiment> --output data\<asset>-report
Get-FileHash data\<asset>-report\* -Algorithm SHA256
```

`--maximum-events` bounds the interruption rehearsal; the second invocation must converge without
changing the manifest/configuration. Treat fixture outputs as synthetic software evidence only.

## Destination-host evidence commands

Run only after host access is authorized. Capture output in the worksheet; these commands are
read-only except the explicitly operator-approved backup command.

```powershell
Get-ComputerInfo | Select-Object WindowsProductName,WindowsVersion,OsBuildNumber,CsName,CsTotalPhysicalMemory
Get-TimeZone
w32tm /query /status
Get-ScheduledTask | Where-Object TaskName -Like 'MarketIntel*' | Get-ScheduledTaskInfo
Get-NetTCPConnection -State Listen | Where-Object LocalPort -Eq 8000
Get-Acl <APP_PATH>
Get-Acl <DATA_PATH>
Invoke-WebRequest http://127.0.0.1:8000/healthz -UseBasicParsing
.\scripts\check-service.ps1
```

Use `scripts\backup-db.ps1` only with explicit source/destination paths and after recording the
matching manifest, config, source-generation, checkpoint and report identities. Stop all writers
before a restore. Never restore over the only copy of a failed database.

## External validation stop gate

There is deliberately no generic “enable everything” command. Before each Delta, CoinGlass,
provider, or Slack check, fill the worksheet duration/request/token/cost/message ceiling and the
specific authorization. A missing credential, entitlement, licensed gold source, destination host,
or notification approval is `BLOCKED` for that row, not permission to substitute data.

## Explicitly authorized provider smoke

Only after recording official model IDs/rates, a non-zero combined cap and one-call provider /
two-call total ceilings, run:

```powershell
.\.venv\Scripts\python.exe -m marketintel.provider_smoke --authorize-paid-smoke --output data\operational\provider-smoke.json
```

The command uses one synthetic payload labelled as not a market signal, sends its identical digest
independently, reserves budget before dispatch, and records safe references plus usage. A failure or
usage-unknown result keeps dual confirmation disabled; do not retry without new authorization.
