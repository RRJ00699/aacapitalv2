# _scripts/ipo/setup_ipo_scheduler.ps1
# =====================================================
# Sets up Windows Task Scheduler for the IPO pipeline
# Run ONCE as Administrator from the project root.
#
# Tasks created:
#   1. AACapital-IPO-Import  — Runs 8:30 PM Mon-Fri
#      After you export Chittorgarh Pro CSV → runs import + scoring
#   2. AACapital-IPO-Morning — Runs 8:45 AM on listing days
#      Reminder to start listing_day_monitor.py manually
#
# Usage:
#   cd C:\aacapital-v2
#   powershell -ExecutionPolicy Bypass -File _scripts\ipo\setup_ipo_scheduler.ps1

$ProjectRoot = (Get-Location).Path
$PythonPath  = (Get-Command python).Source
$EnvFile     = "$ProjectRoot\.env.local"

# Read DATABASE_URL from .env.local
$DbUrl = ""
if (Test-Path $EnvFile) {
    Get-Content $EnvFile | ForEach-Object {
        if ($_ -match "^DATABASE_URL=(.+)") { $DbUrl = $matches[1] }
    }
}

if (-not $DbUrl) {
    Write-Host "ERROR: DATABASE_URL not found in .env.local" -ForegroundColor Red
    exit 1
}

Write-Host "Setting up AACapital IPO Task Scheduler..." -ForegroundColor Cyan
Write-Host "Project: $ProjectRoot"
Write-Host "Python:  $PythonPath"

# ── Task 1: Daily IPO scoring (8:30 PM Mon-Fri) ───────────────────────────────
# After you download and drop Chittorgarh CSV to data/chittorgarh/latest.csv,
# this task auto-imports it and re-runs the play selector.

$Action1 = New-ScheduledTaskAction `
    -Execute $PythonPath `
    -Argument "_scripts\ipo\run_ipo_pipeline.ps1" `
    -WorkingDirectory $ProjectRoot

# Actually use a PS script that sets env and runs both scripts
$PipelineScript = @"
`$env:DATABASE_URL = "$DbUrl"
Set-Location "$ProjectRoot"

# Check if new Chittorgarh export exists
`$csvPath = "data\chittorgarh\latest.csv"
`$xlsxPath = "data\chittorgarh\latest.xlsx"

if (Test-Path `$xlsxPath) {
    Write-Host "`$(Get-Date) Starting Chittorgarh import (xlsx)..."
    python _scripts\ipo\import_chittorgarh.py --file `$xlsxPath
    Rename-Item `$xlsxPath "processed_`$(Get-Date -Format 'yyyy-MM-dd').xlsx" -Force
} elseif (Test-Path `$csvPath) {
    Write-Host "`$(Get-Date) Starting Chittorgarh import (csv)..."
    python _scripts\ipo\import_chittorgarh.py --file `$csvPath
    Rename-Item `$csvPath "processed_`$(Get-Date -Format 'yyyy-MM-dd').csv" -Force
} else {
    Write-Host "`$(Get-Date) No new Chittorgarh export found — skipping import"
}

Write-Host "`$(Get-Date) Running play selector..."
python _scripts\ipo\ipo_play_selector.py --recent 30

Write-Host "`$(Get-Date) Running BRLM scores..."
python _scripts\ipo\compute_brlm_scores.py

Write-Host "`$(Get-Date) IPO pipeline complete."
"@

# Save the pipeline script
$PipelinePath = "$ProjectRoot\_scripts\ipo\run_ipo_pipeline.ps1"
$PipelineScript | Out-File -FilePath $PipelinePath -Encoding UTF8
Write-Host "Created pipeline script: $PipelinePath" -ForegroundColor Green

# Create scheduled task — runs 8:30 PM every weekday
$Trigger1  = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At "20:30"
$Action1   = New-ScheduledTaskAction -Execute "PowerShell.exe" `
             -Argument "-ExecutionPolicy Bypass -NonInteractive -File `"$PipelinePath`"" `
             -WorkingDirectory $ProjectRoot
$Settings1 = New-ScheduledTaskSettingsSet -RunOnlyIfNetworkAvailable -StartWhenAvailable

Register-ScheduledTask -TaskName "AACapital-IPO-Daily" `
    -Trigger $Trigger1 -Action $Action1 -Settings $Settings1 `
    -RunLevel Highest -Force | Out-Null

Write-Host "Task 1 created: AACapital-IPO-Daily (8:30 PM Mon-Fri)" -ForegroundColor Green

# ── Task 2: Listing day reminder (8:45 AM) ───────────────────────────────────
# Runs every morning and checks if any IPO is listing today.
# If yes — opens a notification to run listing_day_monitor.py

$ReminderScript = @"
`$env:DATABASE_URL = "$DbUrl"
Set-Location "$ProjectRoot"

# Check for listing day IPOs
`$today = (Get-Date).ToString("yyyy-MM-dd")
`$result = python - << 'PY'
import os, psycopg2
conn = psycopg2.connect(os.environ['DATABASE_URL'])
cur = conn.cursor()
cur.execute("SELECT company_name, symbol FROM ipo_intelligence WHERE listing_date = CURRENT_DATE AND symbol IS NOT NULL")
rows = cur.fetchall()
for r in rows:
    print(f"{r[0]}|{r[1]}")
conn.close()
PY

if (`$result) {
    foreach (`$line in `$result -split "`n") {
        if (`$line.Trim()) {
            `$parts = `$line.Split("|")
            `$company = `$parts[0]; `$symbol = `$parts[1]
            Write-Host "IPO LISTING TODAY: `$company (`$symbol)"
            
            # Show Windows notification
            Add-Type -AssemblyName System.Windows.Forms
            [System.Windows.Forms.MessageBox]::Show(
                "IPO LISTING TODAY: `$company (`$symbol)`n`nRun:`npython _scripts\ipo\listing_day_monitor.py --symbol `$symbol",
                "AACapital — IPO Listing Alert",
                [System.Windows.Forms.MessageBoxButtons]::OK,
                [System.Windows.Forms.MessageBoxIcon]::Information
            ) | Out-Null
        }
    }
}
"@

$ReminderPath = "$ProjectRoot\_scripts\ipo\listing_day_reminder.ps1"
$ReminderScript | Out-File -FilePath $ReminderPath -Encoding UTF8

$Trigger2  = New-ScheduledTaskTrigger -Daily -At "08:45"
$Action2   = New-ScheduledTaskAction -Execute "PowerShell.exe" `
             -Argument "-ExecutionPolicy Bypass -NonInteractive -WindowStyle Hidden -File `"$ReminderPath`"" `
             -WorkingDirectory $ProjectRoot
$Settings2 = New-ScheduledTaskSettingsSet -RunOnlyIfNetworkAvailable

Register-ScheduledTask -TaskName "AACapital-IPO-ListingReminder" `
    -Trigger $Trigger2 -Action $Action2 -Settings $Settings2 `
    -RunLevel Highest -Force | Out-Null

Write-Host "Task 2 created: AACapital-IPO-ListingReminder (8:45 AM daily)" -ForegroundColor Green

# ── Create data folders ───────────────────────────────────────────────────────
New-Item -ItemType Directory -Force -Path "$ProjectRoot\data\chittorgarh" | Out-Null

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  AACapital IPO Scheduler Setup Complete" -ForegroundColor Cyan
Write-Host "============================================"
Write-Host ""
Write-Host "DAILY WORKFLOW:" -ForegroundColor Yellow
Write-Host "  1. Open Chittorgarh Pro → Export CSV"
Write-Host "  2. Save to: data\chittorgarh\latest.csv"
Write-Host "  3. At 8:30 PM → Task auto-imports + scores all IPOs"
Write-Host "  4. At 8:45 AM → Reminder if any IPO is listing today"
Write-Host ""
Write-Host "LISTING DAY (manual):" -ForegroundColor Yellow
Write-Host "  python _scripts\ipo\listing_day_monitor.py --symbol NSDL"
Write-Host ""
Write-Host "To verify tasks:"
Write-Host "  Get-ScheduledTask -TaskName 'AACapital*'"
