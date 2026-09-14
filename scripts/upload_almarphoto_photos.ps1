# Import product photos from the almarphoto PHP app into Perfect Jewel ERP.
#
# Default source: C:\xampp\htdocs\almarphoto\uploads (1260+ camera JPEGs named with PJ codes).
# Matches each filename to a product and stores catalogue.ProductImage rows under MEDIA_ROOT.
# Re-runs are safe — already-imported (product, filename) pairs are skipped.
#
# Usage (from pj-erp, with venv activated or venv\Scripts\python.exe present):
#
#   powershell -File scripts\upload_almarphoto_photos.ps1
#   powershell -File scripts\upload_almarphoto_photos.ps1 -Apply
#   powershell -File scripts\upload_almarphoto_photos.ps1 -Apply -Limit 20
#   powershell -File scripts\upload_almarphoto_photos.ps1 -Apply -UploadToSpaces
#
# Pull from FTP first (set ALMARPHOTO_FTP_* env vars or pass -FtpHost / -FtpUser / -FtpPassword):
#
#   powershell -File scripts\upload_almarphoto_photos.ps1 -UseFtp -Apply `
#       -FtpHost ftp.example.com -FtpUser myuser -FtpPassword secret `
#       -FtpRemote /htdocs/almarphoto/uploads
#
# Env vars for FTP (optional):
#   ALMARPHOTO_FTP_HOST, ALMARPHOTO_FTP_USER, ALMARPHOTO_FTP_PASSWORD,
#   ALMARPHOTO_FTP_REMOTE_PATH (default /uploads)

param(
    [string]$Source = "C:\xampp\htdocs\almarphoto\uploads",
    [switch]$Apply,
    [switch]$UseFtp,
    [string]$FtpHost = $env:ALMARPHOTO_FTP_HOST,
    [string]$FtpUser = $env:ALMARPHOTO_FTP_USER,
    [string]$FtpPassword = $env:ALMARPHOTO_FTP_PASSWORD,
    [string]$FtpRemote = $(if ($env:ALMARPHOTO_FTP_REMOTE_PATH) { $env:ALMARPHOTO_FTP_REMOTE_PATH } else { "/uploads" }),
    [string]$FtpMirror = "",
    [switch]$UploadToSpaces,
    [int]$Limit = 0,
    [int]$Resize = 0,
    [int]$Quality = 88,
    [string]$Report = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path (Join-Path $Root "manage.py"))) { $Root = Get-Location }
Set-Location $Root

function Assert-Exit($step) {
    if ($LASTEXITCODE -ne 0) { throw "$step failed (exit $LASTEXITCODE)" }
}

$Py = Join-Path $Root "venv\Scripts\python.exe"
if (-not (Test-Path $Py)) { $Py = "python" }

$importSource = $Source
$tempMirror = $false

if ($UseFtp) {
    if (-not $FtpHost -or -not $FtpUser) {
        throw "UseFtp requires -FtpHost and -FtpUser (or ALMARPHOTO_FTP_HOST / ALMARPHOTO_FTP_USER)."
    }
    if (-not $FtpMirror) {
        $FtpMirror = Join-Path $env:TEMP "almarphoto_uploads_mirror"
        $tempMirror = $true
    }
    Write-Host "Syncing FTP $FtpHost`:$FtpRemote -> $FtpMirror"
    $ftpArgs = @(
        "scripts/ftp_download_folder.py",
        "--host", $FtpHost,
        "--user", $FtpUser,
        "--remote", $FtpRemote,
        "--dest", $FtpMirror
    )
    if ($FtpPassword) { $ftpArgs += @("--password", $FtpPassword) }
    if (-not $Apply) { $ftpArgs += "--dry-run" }
    & $Py @ftpArgs
    Assert-Exit "FTP sync"
    $importSource = $FtpMirror
}

if (-not (Test-Path $importSource)) {
    throw "Source folder not found: $importSource"
}

$fileCount = (Get-ChildItem $importSource -File -ErrorAction SilentlyContinue | Measure-Object).Count
Write-Host ""
Write-Host "Import source : $importSource ($fileCount file(s))"
Write-Host "Mode          : $(if ($Apply) { 'APPLY (writes to DB + media)' } else { 'DRY RUN (report only)' })"
Write-Host "Resize        : $(if ($Resize -gt 0) { "${Resize}px q$Quality" } else { 'keep originals' })"
Write-Host ""

$cmdArgs = @(
    "manage.py", "import_product_images", $importSource,
    "--resize", "$Resize",
    "--quality", "$Quality"
)
if (-not $Apply) { $cmdArgs += "--dry-run" }
if ($Limit -gt 0) { $cmdArgs += @("--limit", "$Limit") }
if ($Report) { $cmdArgs += @("--report", $Report) }

& $Py @cmdArgs
Assert-Exit "import_product_images"

if ($Apply -and $UploadToSpaces) {
    Write-Host ""
    Write-Host "Pushing local media to configured object storage (Spaces/R2/S3)..."
    & $Py manage.py upload_local_media --prefix product_images/
    Assert-Exit "upload_local_media"
}

if ($tempMirror -and $Apply) {
    Write-Host ""
    Write-Host "FTP mirror kept at $FtpMirror (temp). Delete manually when done."
}

Write-Host ""
Write-Host "Done."
