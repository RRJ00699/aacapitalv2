$env:DATABASE_URL = "postgresql://neondb_owner:npg_CU4meJPwa8Gn@ep-small-river-apqw6vg6-pooler.c-7.us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
Set-Location "C:\aacapital-v2"

# Check if new Chittorgarh export exists
$csvPath = "data\chittorgarh\latest.csv"
$xlsxPath = "data\chittorgarh\latest.xlsx"

if (Test-Path $xlsxPath) {
    Write-Host "$(Get-Date) Starting Chittorgarh import (xlsx)..."
    python _scripts\ipo\import_chittorgarh.py --file $xlsxPath
    Rename-Item $xlsxPath "processed_$(Get-Date -Format 'yyyy-MM-dd').xlsx" -Force
} elseif (Test-Path $csvPath) {
    Write-Host "$(Get-Date) Starting Chittorgarh import (csv)..."
    python _scripts\ipo\import_chittorgarh.py --file $csvPath
    Rename-Item $csvPath "processed_$(Get-Date -Format 'yyyy-MM-dd').csv" -Force
} else {
    Write-Host "$(Get-Date) No new Chittorgarh export found â€” skipping import"
}

Write-Host "$(Get-Date) Running play selector..."
python _scripts\ipo\ipo_play_selector.py --recent 30

Write-Host "$(Get-Date) Running BRLM scores..."
python _scripts\ipo\compute_brlm_scores.py

Write-Host "$(Get-Date) IPO pipeline complete."
