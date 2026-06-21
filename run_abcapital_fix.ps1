# run_abcapital_fix.ps1
# Run from C:\aacapital-v2
# Loads .env.local and fixes ABCAPITAL

Write-Host "Loading .env.local..." -ForegroundColor Cyan
Get-Content .env.local | ForEach-Object {
    if ($_ -match '^([^#=]+)=(.*)$') {
        $name = $matches[1].Trim().Trim('"')
        $value = $matches[2].Trim().Trim('"')
        if ($name -and $value) {
            [System.Environment]::SetEnvironmentVariable($name, $value, "Process")
        }
    }
}

Write-Host "Kite token: $($env:KITE_ACCESS_TOKEN.Substring(0,8))..." -ForegroundColor Green
Write-Host "DB: $($env:DATABASE_URL.Substring(0,30))..." -ForegroundColor Green

Write-Host "`nStep 1: Fix ABCAPITAL data..." -ForegroundColor Yellow
python _scripts\fix_abcapital_data.py

Write-Host "`nStep 2: Sync candles with valid token..." -ForegroundColor Yellow
python _scripts\kite-sync-candles.py --symbol ABCAPITAL --days 90

Write-Host "`nStep 3: Regenerate signals..." -ForegroundColor Yellow
python _scripts\generate_signals.py --symbols ABCAPITAL

Write-Host "`nStep 4: Check result..." -ForegroundColor Yellow
python _scripts\check_abcapital.py

Write-Host "`nAlso run shareholding for 100 more stocks..." -ForegroundColor Yellow
python _scripts\score_management_commentary.py --symbols ABCAPITAL BAJFINANCE NTPC PAYTM SWIGGY

Write-Host "`nDone!" -ForegroundColor Green
