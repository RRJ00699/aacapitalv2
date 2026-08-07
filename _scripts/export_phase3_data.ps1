[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [string]$Destination = "C:\aacapital-exports\$(Get-Date -Format 'yyyy-MM-dd')"
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$DirectoryTargets = @("data", "ipo_backtest_export", "_output")
$FileTargets = @(
    "dip_defense.csv",
    "factor_report.csv",
    "forensic.csv",
    "ipo_factors.csv",
    "sector_map.csv",
    "ipo_master.xlsx"
)

Add-Type -AssemblyName System.IO.Compression.FileSystem
New-Item -ItemType Directory -Path $Destination -Force | Out-Null
$Destination = (Resolve-Path $Destination).Path

function Get-CsvDataRowCount([string]$Path) {
    if ([IO.Path]::GetExtension($Path) -ne ".csv") { return $null }
    $lineCount = 0
    $reader = [IO.File]::OpenText($Path)
    try { while ($null -ne $reader.ReadLine()) { $lineCount++ } }
    finally { $reader.Dispose() }
    return [Math]::Max(0, $lineCount - 1)
}

function Show-ExportHash([string]$Path) {
    $hash = Get-FileHash -Algorithm SHA256 -LiteralPath $Path
    Write-Host ("SHA256 {0}  {1}" -f $hash.Hash, $hash.Path)
}

$failed = $false
foreach ($relative in $DirectoryTargets) {
    $source = Join-Path $RepoRoot $relative
    if (-not (Test-Path -LiteralPath $source -PathType Container)) {
        Write-Error "Missing source directory: $source"
    }
    $sourceFiles = @(Get-ChildItem -LiteralPath $source -File -Recurse)
    $sourceBytes = [long](($sourceFiles | Measure-Object Length -Sum).Sum)
    $archive = Join-Path $Destination ($relative + ".zip")
    if (Test-Path -LiteralPath $archive) { Remove-Item -LiteralPath $archive -Force }
    [IO.Compression.ZipFile]::CreateFromDirectory($source, $archive, [IO.Compression.CompressionLevel]::Optimal, $false)

    $zip = [IO.Compression.ZipFile]::OpenRead($archive)
    try {
        $entries = @($zip.Entries | Where-Object { -not $_.FullName.EndsWith("/") })
        $exportBytes = [long](($entries | Measure-Object Length -Sum).Sum)
        $verified = ($entries.Count -eq $sourceFiles.Count -and $exportBytes -eq $sourceBytes)
    } finally { $zip.Dispose() }
    Write-Host ("{0}: files={1}, bytes={2}, verified={3}" -f $relative, $sourceFiles.Count, $sourceBytes, $verified)
    foreach ($csv in $sourceFiles | Where-Object Extension -eq ".csv") {
        Write-Host ("  CSV rows {0}: {1}" -f $csv.FullName.Substring($RepoRoot.Length + 1), (Get-CsvDataRowCount $csv.FullName))
    }
    if (-not $verified) { $failed = $true }
    Show-ExportHash $archive
}

foreach ($relative in $FileTargets) {
    $source = Join-Path $RepoRoot $relative
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
        Write-Error "Missing source file: $source"
    }
    $export = Join-Path $Destination $relative
    Copy-Item -LiteralPath $source -Destination $export -Force
    $sourceInfo = Get-Item -LiteralPath $source
    $exportInfo = Get-Item -LiteralPath $export
    $verified = ($sourceInfo.Length -eq $exportInfo.Length)
    $rows = Get-CsvDataRowCount $source
    $rowText = if ($null -eq $rows) { "N/A" } else { [string]$rows }
    Write-Host ("{0}: files=1, bytes={1}, rows={2}, verified={3}" -f $relative, $sourceInfo.Length, $rowText, $verified)
    if (-not $verified) { $failed = $true }
    Show-ExportHash $export
}

if ($failed) {
    Write-Error "Phase 3 export verification failed. No deletion is authorized."
    exit 1
}

Write-Host "Phase 3 export verified. Preserve this output and send it to the owner for explicit deletion approval."
exit 0
