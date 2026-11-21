# Push an existing, initialized working tree to the designated GitHub repository.
# Requires GitHub authentication on your Windows host. Does not commit credentials.
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)
if (!(Test-Path .git)) { throw 'Clone gold_bitcoin first; do not create a second repository.' }
$expected = 'https://github.com/Rameshdandu1/gold_bitcoin.git'
$remote = (& git remote get-url origin).Trim()
if ($remote -ne $expected -and $remote -ne 'git@github.com:Rameshdandu1/gold_bitcoin.git') {
    throw "Unexpected origin $remote. Refusing to push to the wrong repository."
}
& git status --short
& git diff --check
if ($LASTEXITCODE -ne 0) { throw 'Whitespace check failed.' }
Write-Host 'Review changes, commit, then push with: git push origin main'
