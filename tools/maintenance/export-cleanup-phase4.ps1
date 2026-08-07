param(
    [string]$RepositoryRoot = (Get-Location).Path,
    [string]$ExportRoot = "C:\aacapital-exports\cleanup-phase4\$(Get-Date -Format 'yyyy-MM-dd')"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$relativePaths = @(
    "DAILY_RUN.ps1"
    "DEPLOY_IPO_SCRAPERS.ps1"
    "LISTING_DAY.ps1"
    "MORNING_RUN.ps1"
    "RUN_IPO_PIPELINE.ps1"
    "RUN_STEP1.bat"
    "RUN_STEP2.bat"
    "RUN_STEP3.bat"
    "RUN_STEP4.bat"
    "SETUP.bat"
    "run_abcapital_fix.ps1"
)

$RepositoryRoot = (Resolve-Path -LiteralPath $RepositoryRoot).Path
$payloadRoot = Join-Path $ExportRoot "files"
$manifestPath = Join-Path $ExportRoot "manifest-sha256.tsv"
$zipPath = Join-Path $ExportRoot "cleanup-phase4-root-launchers.zip"

if (Test-Path -LiteralPath $ExportRoot) {
    throw "Export destination already exists; refusing to overwrite: $ExportRoot"
}
New-Item -ItemType Directory -Path $payloadRoot -Force | Out-Null

$sourceFiles = foreach ($relativePath in $relativePaths) {
    $source = Join-Path $RepositoryRoot $relativePath
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
        throw "Required source file is missing: $relativePath"
    }

    $destination = Join-Path $payloadRoot $relativePath
    $destinationParent = Split-Path -Parent $destination
    New-Item -ItemType Directory -Path $destinationParent -Force | Out-Null
    Copy-Item -LiteralPath $source -Destination $destination

    $item = Get-Item -LiteralPath $source
    [PSCustomObject]@{
        RelativePath = $relativePath.Replace('\', '/')
        Bytes = $item.Length
        SHA256 = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant()
    }
}

$sourceCount = @($sourceFiles).Count
$sourceBytes = ($sourceFiles | Measure-Object -Property Bytes -Sum).Sum
$manifestLines = @("relative_path`tsha256")
$manifestLines += $sourceFiles | ForEach-Object { "$($_.RelativePath)`t$($_.SHA256)" }
[System.IO.File]::WriteAllLines($manifestPath, $manifestLines, [System.Text.UTF8Encoding]::new($false))

Compress-Archive -Path (Join-Path $payloadRoot "*") -DestinationPath $zipPath -CompressionLevel Optimal

Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip = [System.IO.Compression.ZipFile]::OpenRead($zipPath)
try {
    $entries = @($zip.Entries | Where-Object { -not [string]::IsNullOrEmpty($_.Name) })
    $zipCount = $entries.Count
    $zipBytes = ($entries | Measure-Object -Property Length -Sum).Sum
} finally {
    $zip.Dispose()
}

Write-Host "Source file count: $sourceCount"
Write-Host "Source byte count: $sourceBytes"
Write-Host "ZIP entry count: $zipCount"
Write-Host "ZIP uncompressed byte count: $zipBytes"

if ($zipCount -ne $sourceCount) {
    throw "ZIP entry count mismatch: expected $sourceCount, found $zipCount"
}
if ($zipBytes -ne $sourceBytes) {
    throw "ZIP uncompressed byte count mismatch: expected $sourceBytes, found $zipBytes"
}

$zipSha256 = (Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash.ToLowerInvariant()
Write-Host "ZIP SHA256: $zipSha256"
Write-Host "Manifest: $manifestPath"
Write-Host "Archive verified successfully: $zipPath"
