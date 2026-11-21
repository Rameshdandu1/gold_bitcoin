$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
if (!(Test-Path '.venv\Scripts\python.exe')) { throw 'Run Python venv setup from README first' }
& .\.venv\Scripts\python.exe -m uvicorn marketintel.api:app --host 127.0.0.1 --port 8000
