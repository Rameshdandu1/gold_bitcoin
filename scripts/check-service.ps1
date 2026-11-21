$ErrorActionPreference = "Stop"
$user = $env:OPERATOR_USERNAME
$password = $env:OPERATOR_PASSWORD
if (!$user -or !$password) { throw 'OPERATOR_USERNAME and OPERATOR_PASSWORD are required' }
$credential = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes("${user}:${password}"))
$headers = @{ Authorization = "Basic $credential" }
$live = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/healthz'
$ready = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/readyz' -Headers $headers
[PSCustomObject]@{ Liveness = $live.status; Ready = $ready.ready; Checks = $ready.checks }
