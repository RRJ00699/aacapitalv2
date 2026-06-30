<#
  run_ipo_pipeline.ps1  — AACapital IPO refresh chain (local, on-demand)

  Runs the full new-IPO pipeline in dependency order:
     1. fetch_nse_ipos.py            (catch new IPOs from NSE feeds)
     2. enrich_ipo_chittorgarh.py    (--auto --apply: fill issue_price/subscription/
                                       anchors/KPIs/BRLMs for the bare rows just caught)
     3. build_ipo_consolidated_v2.py (rebuild the one-stop wide table)

  Stops on the first hard failure so you never rebuild on half-fetched data.
  Run from the repo root:   .\_scripts\ipo\run_ipo_pipeline.ps1
  Dry-run (no DB writes):   .\_scripts\ipo\run_ipo_pipeline.ps1 -DryRun
#>
param(
    [switch]$DryRun  # preview: fetch --dry-run + enrich (no --apply); skips rebuild
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path "$PSScriptRoot\..\..").Path   # repo root from _scripts\ipo\
Set-Location $root

function Step($n, $label, $cmd) {
    Write-Host ""
    Write-Host "===== [$n] $label =====" -ForegroundColor Cyan
    Write-Host "  > $cmd" -ForegroundColor DarkGray
    Invoke-Expression $cmd
    if ($LASTEXITCODE -ne 0) {
        Write-Host "FAILED at step $n ($label) — stopping (exit $LASTEXITCODE)." -ForegroundColor Red
        exit $LASTEXITCODE
    }
    Write-Host "  ok" -ForegroundColor Green
}

$t0 = Get-Date
Write-Host "AACapital IPO pipeline  ($(if($DryRun){'DRY-RUN'}else{'LIVE'}))  $($t0.ToString('HH:mm:ss'))" -ForegroundColor Yellow

if ($DryRun) {
    Step 1 "Fetch NSE IPOs (dry-run)"        "python _scripts\ipo\fetch_nse_ipos.py --dry-run"
    Step 2 "Enrich from Chittorgarh (dry-run)" "python _scripts\ipo\enrich_ipo_chittorgarh.py --auto"
    Write-Host "`nDRY-RUN complete — no DB writes, consolidated not rebuilt." -ForegroundColor Yellow
}
else {
    Step 1 "Fetch NSE IPOs"                  "python _scripts\ipo\fetch_nse_ipos.py"
    Step 2 "Enrich new IPOs from Chittorgarh" "python _scripts\ipo\enrich_ipo_chittorgarh.py --auto --apply"
    Step 3 "Rebuild IPO consolidated"        "python _scripts\build_ipo_consolidated_v2.py"
    Write-Host "`nPipeline complete in $([int]((Get-Date)-$t0).TotalSeconds)s." -ForegroundColor Green
}
