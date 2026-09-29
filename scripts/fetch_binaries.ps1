# Download the non-pip audit tools into tools/bin/ (gitignored).
# Run from the repo root:  powershell -ExecutionPolicy Bypass -File scripts/fetch_binaries.ps1
#
# Pinned versions. Re-check the release pages before bumping:
#   https://github.com/google/osv-scanner/releases
#   https://github.com/boyter/scc/releases
# Needs a network without TLS interception, or the interceptor's CA trusted by Windows.

$ErrorActionPreference = "Stop"
$OsvVersion = "2.6.0"
$SccVersion = "4.1.0"

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

Write-Host "browser worker: Playwright + axe-core (versions pinned in browser_worker/package.json)"
Push-Location (Join-Path $PSScriptRoot "..\browser_worker")
npm install --no-audit --no-fund
npx playwright install chromium
Pop-Location

Get-ChildItem $bin
