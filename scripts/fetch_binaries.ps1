# Download the non-pip audit tools into tools/bin/ (gitignored).
# Run from the repo root:  powershell -ExecutionPolicy Bypass -File scripts/fetch_binaries.ps1
#
# Pinned versions. Re-check the release pages before bumping:
#   https://github.com/google/osv-scanner/releases
#   https://github.com/boyter/scc/releases
#   https://www.npmjs.com/package/axe-core
# Needs a network without TLS interception, or the interceptor's CA trusted by Windows.

$ErrorActionPreference = "Stop"
$OsvVersion = "2.6.0"
$SccVersion = "4.1.0"
$AxeVersion = "4.13.0"

$bin = Join-Path $PSScriptRoot "..\tools\bin"
New-Item -ItemType Directory -Force $bin | Out-Null

Write-Host "osv-scanner $OsvVersion"
Invoke-WebRequest -Uri "https://github.com/google/osv-scanner/releases/download/v$OsvVersion/osv-scanner_windows_amd64.exe" `
    -OutFile (Join-Path $bin "osv-scanner.exe")

Write-Host "scc $SccVersion"
$zip = Join-Path $env:TEMP "scc.zip"
Invoke-WebRequest -Uri "https://github.com/boyter/scc/releases/download/v$SccVersion/scc_Windows_x86_64.zip" -OutFile $zip
Expand-Archive -Force $zip -DestinationPath $bin
Remove-Item $zip

Write-Host "axe-core $AxeVersion"
Invoke-WebRequest -Uri "https://cdn.jsdelivr.net/npm/axe-core@$AxeVersion/axe.min.js" `
    -OutFile (Join-Path $bin "axe.min.js")

Write-Host "Playwright Chromium"
& (Join-Path $PSScriptRoot "..\.venv\Scripts\python.exe") -m playwright install chromium

Get-ChildItem $bin
