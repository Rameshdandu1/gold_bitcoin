# Windows Server Deployment — staged runbook

## 0. Scope and prerequisites
For a Windows Server 2022/2025 VPS or bare-metal host, start with **native Python + SQLite** only for MVP research and a small dataset; **no Linux VM** is mandatory. Install official Python 3.12+, Node 20+/22, Git. Use an unprivileged local service identity and a dedicated directory, e.g. `C:\MarketIntelligence`. This guide does NOT promise 24/7 production hardening.

## 1. Local setup
In PowerShell:

```powershell
Set-Location C:\MarketIntelligence
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
Copy-Item .env.example .env
notepad .env
.\scripts\verify.ps1
```

Edit only the `.env` copy. Do not use command-line flags or screenshots to paste secrets. Windows ACLs: deny non-service users read access to `.env` and `data`. Confirm NTP clock synchronization and timezone; app keeps UTC timestamps irrespective of host timezone.

## 2. Start API and collector manually first

```powershell
.\scripts\start-api.ps1
# second PowerShell terminal:
.\scripts\start-worker.ps1
```

Before enabling worker set `LIVE_INGESTION_ENABLED=true` and check configured symbols are supported by the current Delta India `/v2/products` result. Enable CoinGlass and AI separately after confirming entitlements and a bounded daily API budget. The prototype blocks confirmation on its own because flow-quality prerequisites are incomplete; an `INCOMPLETE` candidate is not a signal.

## 3. Frontend

```powershell
Set-Location C:\MarketIntelligence\frontend
npm install
npm run typecheck
npm run build
```

Vite dev server is **not** a public production web server. Serve compiled `frontend/dist` behind an authenticated HTTPS reverse proxy (IIS/ARR or another supported server) and proxy `/api` securely to `127.0.0.1:8000`. Lock CORS and add application login prior to publishing a URL. HTTPS certificates and access control are operator tasks.

## 4. Windows service management
For a durable server, configure each Python process as an independently managed Windows Service with an approved service wrapper (for example, a reviewed WinSW or NSSM release). Do not start a GUI desktop process and assume it survives logout. Set explicit working directory, auto restart/recovery, non-admin identity, log rotation, separate service accounts, and Windows Defender Firewall block rules. Confirm a full host reboot recovers both processes; do a dry-run before going live.

## 5. Storage and throughput
SQLite WAL is for small single-node research and audit only. Do not attempt to persist high-frequency raw L2 tick floods in SQLite at scale. If the raw event journal grows, migrate to PostgreSQL for Windows and separate compressed archived partitions (or a Linux VM for TimescaleDB if vendor support requires it). Record daily raw byte rates and retention, back up encrypted data off-host and test restore.

## 6. Readiness checklist
- [ ] Windows patching, anti-malware, NTP and least-privilege local accounts configured
- [ ] No exposed unauthenticated API or Vite dev service
- [ ] API keys masked and rotated; firewall outbound domains reviewed
- [ ] Delta product discovery confirms valid instruments, volumes and contract multipliers
- [ ] CoinGlass supported exchange/pair and plan permissions validated from API
- [ ] Live snapshots and tick streams survive reconnect, drops and stale-book conditions
- [ ] Source timestamps/closed-candle interpretation verified against exchange feed
- [ ] Local + GitHub CI passing; 30-day paper-trading policy decided
- [ ] No order execution API configured, enabled or shipped
