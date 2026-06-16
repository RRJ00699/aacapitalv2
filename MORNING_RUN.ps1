# ═══════════════════════════════════════════════════════════════
# AACapital — Morning Run (6:30 AM IST before market open)
# ═══════════════════════════════════════════════════════════════

Set-Location "C:\aacapital-v2"

$envVars = Get-Content ".env.local" | Where-Object { $_ -match "=" -and $_ -notmatch "^#" }
foreach ($line in $envVars) {
    $parts = $line.Split("=", 2)
    $key = $parts[0].Trim(); $val = $parts[1].Trim().Trim('"')
    [System.Environment]::SetEnvironmentVariable($key, $val, "Process")
}

Write-Host "AACapital Morning Run" -ForegroundColor Blue
Write-Host (Get-Date -Format "dddd, dd MMM yyyy HH:mm") -ForegroundColor Gray

# Refresh Kite token first
Write-Host "`n[1/3] Kite token refresh..." -ForegroundColor Cyan
python _scripts/kite-auth-auto.py --auto

# Reload token
$envVars = Get-Content ".env.local" | Where-Object { $_ -match "=" -and $_ -notmatch "^#" }
foreach ($line in $envVars) {
    $parts = $line.Split("=", 2)
    $key = $parts[0].Trim(); $val = $parts[1].Trim().Trim('"')
    [System.Environment]::SetEnvironmentVariable($key, $val, "Process")
}

# Check what's listing today
Write-Host "`n[2/3] IPO listing check..." -ForegroundColor Cyan
python _scripts/kite-sync-ipos.py --listing --dry-run

# Neon status
Write-Host "`n[3/3] System status..." -ForegroundColor Cyan
python check_neon.py

Write-Host "`n✅ Morning check complete" -ForegroundColor Green
