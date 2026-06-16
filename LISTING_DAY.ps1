# ═══════════════════════════════════════════════════════════════
# AACapital — Listing Day Script
# Run when an IPO is listing — refreshes live OI + VWAP signals
# ═══════════════════════════════════════════════════════════════

Set-Location "C:\aacapital-v2"

$envVars = Get-Content ".env.local" | Where-Object { $_ -match "=" -and $_ -notmatch "^#" }
foreach ($line in $envVars) {
    $parts = $line.Split("=", 2)
    $key = $parts[0].Trim(); $val = $parts[1].Trim().Trim('"')
    [System.Environment]::SetEnvironmentVariable($key, $val, "Process")
}

Write-Host "AACapital — Listing Day Mode" -ForegroundColor Magenta
Write-Host "Refreshing every 5 minutes..." -ForegroundColor Gray

while ($true) {
    $time = Get-Date -Format "HH:mm:ss"
    Write-Host "`n[$time] Fetching listing signals..." -ForegroundColor Cyan
    python _scripts/kite-sync-ipos.py --listing
    Write-Host "Dashboard: https://aacapital-v2.vercel.app/dashboard/listing" -ForegroundColor Blue
    Write-Host "Next refresh in 5 minutes. Ctrl+C to stop."
    Start-Sleep -Seconds 300
}
