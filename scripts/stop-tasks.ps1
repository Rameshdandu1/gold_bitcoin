$ErrorActionPreference = "Stop"
$taskNames = @(
    'MarketIntel-API',
    'MarketIntel-MarketWorker',
    'MarketIntel-ReviewWorker',
    'MarketIntel-AlertWorker'
)
foreach ($taskName in $taskNames) {
    $task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    if ($null -ne $task -and $task.State -eq 'Running') {
        Stop-ScheduledTask -TaskName $taskName
    }
}
