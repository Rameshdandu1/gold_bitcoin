$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)
if (!(Test-Path '.venv\Scripts\python.exe')) { throw 'Install Python dependencies first' }
& .\.venv\Scripts\python.exe -m ruff check --fix .
& .\.venv\Scripts\python.exe -m ruff format .
& .\.venv\Scripts\python.exe -m pytest -q
