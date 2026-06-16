# ═══════════════════════════════════════════════════════════════
# AACapital — Daily Run Sequence
# Run after 4:30 PM IST (after market close)
# ═══════════════════════════════════════════════════════════════

Set-Location "C:\aacapital-v2"

# Load env
$envVars = Get-Content ".env.local" | Where-Object { $_ -match "=" -and $_ -notmatch "^#" }
foreach ($line in $envVars) {
    $parts = $line.Split("=", 2)
    $key = $parts[0].Trim()
    $val = $parts[1].Trim().Trim('"')
    [System.Environment]::SetEnvironmentVariable($key, $val, "Process")
}
Write-Host "✅ Env loaded" -ForegroundColor Green

# Step 1 — Kite token refresh
Write-Host "`n[1/6] Refreshing Kite token..." -ForegroundColor Cyan
python _scripts/kite-auth-auto.py --auto
if ($LASTEXITCODE -ne 0) {
    Write-Host "⚠ Auto auth failed — running manual mode" -ForegroundColor Yellow
    python _scripts/kite-auth-auto.py
}

# Reload env to pick up new token
$envVars = Get-Content ".env.local" | Where-Object { $_ -match "=" -and $_ -notmatch "^#" }
foreach ($line in $envVars) {
    $parts = $line.Split("=", 2)
    $key = $parts[0].Trim()
    $val = $parts[1].Trim().Trim('"')
    [System.Environment]::SetEnvironmentVariable($key, $val, "Process")
}

# Step 2 — Kite candle sync
Write-Host "`n[2/6] Syncing today's candles..." -ForegroundColor Cyan
python _scripts/kite-sync-candles.py --days 1

# Step 3 — Market regime + VIX
Write-Host "`n[3/6] Market regime + India VIX..." -ForegroundColor Cyan
python _scripts/engines/market_regime.py

# Step 4 — Multibagger screener
Write-Host "`n[4/6] Multibagger screener..." -ForegroundColor Cyan
npx tsx _scripts/engines/indicator_calculator.ts --mode latest
npx tsx _scripts/engines/multibagger_screener.ts
npx tsx _scripts/sync-signals-to-neon.ts

# Step 5 — Kite IPO sync
Write-Host "`n[5/6] Kite IPO sync..." -ForegroundColor Cyan
python _scripts/kite-sync-ipos.py

# Step 6 — Status check
Write-Host "`n[6/6] Neon status check..." -ForegroundColor Cyan
python check_neon.py

Write-Host "`n✅ Daily run complete!" -ForegroundColor Green
Write-Host "Dashboard: https://aacapital-v2.vercel.app" -ForegroundColor Blue
