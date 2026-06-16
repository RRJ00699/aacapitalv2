# AACapital — IPO Scraper Deployment
# Copies all IPO pipeline scripts into the correct project locations
# Run from project root: C:\aacapital-v2>
# Command: powershell -File DEPLOY_IPO_SCRAPERS.ps1

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "  AACapital — IPO Scraper Deployment"      -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

# ── Verify we are in the right directory ──────────────────────────────────────
$here = Get-Location
if (-not (Test-Path "$here\package.json") -and -not (Test-Path "$here\.env.local")) {
    Write-Host "ERROR: Run this script from C:\aacapital-v2 (project root)" -ForegroundColor Red
    Write-Host "  cd C:\aacapital-v2" -ForegroundColor Yellow
    exit 1
}
Write-Host "✓ Project root: $here" -ForegroundColor Green

# ── Create directories ────────────────────────────────────────────────────────
$dirs = @("_scripts", "_scripts\logs", "_scripts\engines")
foreach ($d in $dirs) {
    if (-not (Test-Path $d)) {
        New-Item -ItemType Directory -Path $d -Force | Out-Null
        Write-Host "  Created: $d" -ForegroundColor DarkGray
    }
}
Write-Host "✓ Directories ready" -ForegroundColor Green

# ── Detect where downloaded files are ─────────────────────────────────────────
# Scripts are downloaded from Claude — check common locations
$downloadLocations = @(
    "$env:USERPROFILE\Downloads",
    "$env:USERPROFILE\Desktop",
    ".\downloads",
    "."
)

$scriptNames = @(
    "scraper_chittorgarh.py",
    "scraper_gmp.py",
    "scraper_anchors.py",
    "calculator_returns.py",
    "run_ipo_pipeline.py",
    "check_coverage.sql"
)

Write-Host ""
Write-Host "Looking for downloaded scripts..." -ForegroundColor Yellow

$foundScripts = @{}
foreach ($name in $scriptNames) {
    foreach ($loc in $downloadLocations) {
        $full = Join-Path $loc $name
        if (Test-Path $full) {
            $foundScripts[$name] = $full
            break
        }
    }
}

if ($foundScripts.Count -eq 0) {
    Write-Host ""
    Write-Host "SCRIPTS NOT FOUND IN DOWNLOADS." -ForegroundColor Yellow
    Write-Host "Creating script files directly in _scripts\..." -ForegroundColor Cyan
    Write-Host "(Paste content from Claude into the files that open)" -ForegroundColor DarkGray
    Write-Host ""
    
    foreach ($name in $scriptNames) {
        if ($name.EndsWith(".sql")) {
            $dest = "_scripts\$name"
        } else {
            $dest = "_scripts\$name"
        }
        if (-not (Test-Path $dest)) {
            New-Item -ItemType File -Path $dest -Force | Out-Null
            Write-Host "  Created empty: $dest" -ForegroundColor DarkGray
        }
    }
    Write-Host ""
    Write-Host "→ Open each .py file in VS Code and paste the script content from Claude." -ForegroundColor Yellow
} else {
    # Copy found scripts
    Write-Host ""
    foreach ($name in $scriptNames) {
        if ($foundScripts.ContainsKey($name)) {
            $src  = $foundScripts[$name]
            $dest = "_scripts\$name"
            Copy-Item -Path $src -Destination $dest -Force
            Write-Host "  ✓ Copied: $name" -ForegroundColor Green
        } else {
            Write-Host "  ✗ Not found: $name  (download from Claude and run script again)" -ForegroundColor Red
        }
    }
}

# ── Load environment ───────────────────────────────────────────────────────────
Write-Host ""
Write-Host "Loading environment from .env.local..." -ForegroundColor Yellow

if (Test-Path ".env.local") {
    $envVars = Get-Content ".env.local" | Where-Object { $_ -match "=" -and $_ -notmatch "^#" }
    foreach ($l in $envVars) {
        $parts = $l.Split("=", 2)
        if ($parts.Count -eq 2) {
            [System.Environment]::SetEnvironmentVariable($parts[0].Trim(), $parts[1].Trim().Trim('"'), "Process")
        }
    }
    Write-Host "✓ Environment loaded" -ForegroundColor Green
} else {
    Write-Host "  ⚠ .env.local not found — set DATABASE_URL manually" -ForegroundColor Yellow
}

# ── Verify DATABASE_URL ────────────────────────────────────────────────────────
$dbUrl = [System.Environment]::GetEnvironmentVariable("DATABASE_URL", "Process")
if (-not $dbUrl) {
    Write-Host ""
    Write-Host "  ⚠ DATABASE_URL not set." -ForegroundColor Yellow
    Write-Host "  Set it manually before running scripts:" -ForegroundColor Yellow
    Write-Host '  $env:DATABASE_URL = "postgresql://..."' -ForegroundColor Cyan
} else {
    Write-Host "✓ DATABASE_URL set (...$($dbUrl.Substring([Math]::Max(0,$dbUrl.Length-25))))" -ForegroundColor Green
}

# ── Verify IPO Excel ──────────────────────────────────────────────────────────
$xlsxFiles = @(
    "aacapital_ipo_master_304.xlsx",
    "_data\aacapital_ipo_master_304.xlsx",
    "data\aacapital_ipo_master_304.xlsx"
)
$xlsxFound = $false
foreach ($xf in $xlsxFiles) {
    if (Test-Path $xf) {
        [System.Environment]::SetEnvironmentVariable("IPO_EXCEL", (Resolve-Path $xf).Path, "Process")
        Write-Host "✓ IPO Excel: $xf" -ForegroundColor Green
        $xlsxFound = $true
        break
    }
}
if (-not $xlsxFound) {
    Write-Host "  ⚠ aacapital_ipo_master_304.xlsx not found." -ForegroundColor Yellow
    Write-Host "  Copy it to C:\aacapital-v2\ and rerun, or set:" -ForegroundColor Yellow
    Write-Host '  $env:IPO_EXCEL = "C:\path\to\aacapital_ipo_master_304.xlsx"' -ForegroundColor Cyan
}

# ── Install Python dependencies ───────────────────────────────────────────────
Write-Host ""
Write-Host "Installing Python dependencies..." -ForegroundColor Yellow
$pipPackages = "requests beautifulsoup4 lxml psycopg2-binary pandas openpyxl"
try {
    python -m pip install $pipPackages.Split(" ") --quiet
    Write-Host "✓ Python packages installed" -ForegroundColor Green
} catch {
    Write-Host "  ⚠ pip install failed. Run manually:" -ForegroundColor Yellow
    Write-Host "  pip install $pipPackages" -ForegroundColor Cyan
}

# ── Summary and next steps ────────────────────────────────────────────────────
Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "  DEPLOYMENT COMPLETE — NEXT STEPS"         -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Run in this order:" -ForegroundColor White
Write-Host ""
Write-Host "  STEP 1 — Returns from Kite candles (fastest, ~5 min):" -ForegroundColor Green
Write-Host "    python _scripts\calculator_returns.py" -ForegroundColor Cyan
Write-Host ""
Write-Host "  STEP 2 — Chittorgarh master scraper (~90 min, run overnight):" -ForegroundColor Yellow
Write-Host "    python _scripts\scraper_chittorgarh.py" -ForegroundColor Cyan
Write-Host ""
Write-Host "  STEP 3 — GMP history (~45 min):" -ForegroundColor Yellow
Write-Host "    python _scripts\scraper_gmp.py" -ForegroundColor Cyan
Write-Host ""
Write-Host "  STEP 4 — Anchor investors (~30 min):" -ForegroundColor Yellow
Write-Host "    python _scripts\scraper_anchors.py" -ForegroundColor Cyan
Write-Host ""
Write-Host "  OR run all steps automatically:" -ForegroundColor White
Write-Host "    python _scripts\run_ipo_pipeline.py" -ForegroundColor Cyan
Write-Host ""
Write-Host "  After scraping, check coverage in Neon console:" -ForegroundColor White
Write-Host "    → Paste contents of _scripts\check_coverage.sql" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Logs saved to: _scripts\logs\" -ForegroundColor DarkGray
Write-Host ""
