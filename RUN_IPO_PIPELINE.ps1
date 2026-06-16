# AACapital — Run IPO Data Pipeline
# Loads env, then runs all 4 scripts in correct order
# Run from: C:\aacapital-v2>
# Command:  powershell -File RUN_IPO_PIPELINE.ps1
# Or single step: powershell -File RUN_IPO_PIPELINE.ps1 -Step 1

param(
    [int]$Step = 0   # 0 = all, 1-4 = specific step
)

$ErrorActionPreference = "Continue"

# ── Load environment ──────────────────────────────────────────────────────────
if (Test-Path ".env.local") {
    $envVars = Get-Content ".env.local" | Where-Object { $_ -match "=" -and $_ -notmatch "^#" }
    foreach ($l in $envVars) {
        $p = $l.Split("=", 2)
        if ($p.Count -eq 2) {
            [System.Environment]::SetEnvironmentVariable($p[0].Trim(), $p[1].Trim().Trim('"'), "Process")
        }
    }
    Write-Host "✓ Environment loaded" -ForegroundColor Green
}

# ── Set IPO Excel path ────────────────────────────────────────────────────────
foreach ($xf in @("aacapital_ipo_master_304.xlsx", "_data\aacapital_ipo_master_304.xlsx")) {
    if (Test-Path $xf) {
        [System.Environment]::SetEnvironmentVariable("IPO_EXCEL", (Resolve-Path $xf).Path, "Process")
        Write-Host "✓ IPO Excel: $xf" -ForegroundColor Green
        break
    }
}

$db = [System.Environment]::GetEnvironmentVariable("DATABASE_URL", "Process")
if (-not $db) {
    Write-Host "ERROR: DATABASE_URL not set" -ForegroundColor Red
    exit 1
}

# ── Step definitions ──────────────────────────────────────────────────────────
$steps = @(
    @{ Num=1; Script="_scripts\calculator_returns.py";    Name="Returns Calculator (Kite candles)";   Color="Green"  },
    @{ Num=2; Script="_scripts\scraper_chittorgarh.py";   Name="Chittorgarh Master Scraper";          Color="Yellow" },
    @{ Num=3; Script="_scripts\scraper_gmp.py";           Name="GMP History Scraper";                 Color="Yellow" },
    @{ Num=4; Script="_scripts\scraper_anchors.py";       Name="Anchor Investor Scraper";             Color="Yellow" }
)

# ── Run ───────────────────────────────────────────────────────────────────────
$results = @{}
$start   = Get-Date

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "  AACapital — IPO Data Pipeline"           -ForegroundColor Cyan
Write-Host "  Started: $(Get-Date -Format 'HH:mm:ss')" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan

foreach ($s in $steps) {
    if ($Step -ne 0 -and $Step -ne $s.Num) { continue }

    Write-Host ""
    Write-Host "── STEP $($s.Num): $($s.Name) ──" -ForegroundColor $s.Color

    if (-not (Test-Path $s.Script)) {
        Write-Host "  ✗ Script not found: $($s.Script)" -ForegroundColor Red
        Write-Host "    Run DEPLOY_IPO_SCRAPERS.ps1 first" -ForegroundColor Yellow
        $results[$s.Num] = "MISSING"
        continue
    }

    $t = Get-Date
    try {
        python $s.Script
        $elapsed = [Math]::Round(((Get-Date) - $t).TotalMinutes, 1)
        Write-Host "  ✓ Completed in $elapsed min" -ForegroundColor Green
        $results[$s.Num] = "OK"
    } catch {
        $elapsed = [Math]::Round(((Get-Date) - $t).TotalMinutes, 1)
        Write-Host "  ✗ Failed after $elapsed min: $_" -ForegroundColor Red
        $results[$s.Num] = "FAILED"
    }
}

# ── Summary ───────────────────────────────────────────────────────────────────
$totalMin = [Math]::Round(((Get-Date) - $start).TotalMinutes, 1)
Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "  Pipeline Summary — $totalMin min total" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
foreach ($s in $steps) {
    if ($results.ContainsKey($s.Num)) {
        $status = $results[$s.Num]
        $color  = if ($status -eq "OK") { "Green" } elseif ($status -eq "MISSING") { "Yellow" } else { "Red" }
        Write-Host "  Step $($s.Num): $status — $($s.Name)" -ForegroundColor $color
    }
}
Write-Host ""
Write-Host "  Logs: _scripts\logs\" -ForegroundColor DarkGray
Write-Host "  Next: paste _scripts\check_coverage.sql into Neon console" -ForegroundColor Cyan
Write-Host ""
