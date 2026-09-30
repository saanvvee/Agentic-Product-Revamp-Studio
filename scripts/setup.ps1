# One-command setup on Windows (e.g. the GPU laptop that runs Ollama).
#
#   powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
#
# Needs, installed beforehand (the script checks and tells you what is missing):
#   Python 3.11   winget install Python.Python.3.11
#   Node 22       winget install OpenJS.NodeJS.LTS
#   Git           winget install Git.Git
#   Ollama        https://ollama.com/download  (GPU driver working: `ollama ps` shows GPU)
# Safe to re-run: every step skips work that is already done.

$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root

function Step($msg) { Write-Host "`n== $msg" -ForegroundColor Cyan }
function Fail($msg) { Write-Host "`nSETUP STOPPED: $msg" -ForegroundColor Red; exit 1 }
# Native programs (python, npm, ollama) do not throw in PowerShell; check their exit code.
function Run($what) {
    & $what[0] $what[1..($what.Length - 1)]
    if ($LASTEXITCODE -ne 0) { Fail "command failed ($LASTEXITCODE): $($what -join ' ')" }
}

Step "Checking prerequisites"
$missing = @()
& py -3.11 --version 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) { $missing += "Python 3.11   ->  winget install Python.Python.3.11" }
foreach ($p in @(
        @("node", "Node 22       ->  winget install OpenJS.NodeJS.LTS"),
        @("npm", "npm (comes with Node)"),
        @("git", "Git           ->  winget install Git.Git"),
        @("ollama", "Ollama        ->  https://ollama.com/download"))) {
    if (-not (Get-Command $p[0] -ErrorAction SilentlyContinue)) { $missing += $p[1] }
}
if ($missing.Count) {
    Write-Host "Missing:" -ForegroundColor Yellow
    $missing | ForEach-Object { Write-Host "  $_" }
    Fail "install the above, CLOSE AND REOPEN PowerShell (so PATH updates), then re-run this script."
}
Write-Host "Python $(py -3.11 --version), node $(node --version), $(git --version), ollama present."

Step "Python 3.11 virtual environment"
$py = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { Run @("py", "-3.11", "-m", "venv", ".venv") }
Run @($py, "-m", "pip", "install", "--upgrade", "pip", "--quiet")
Run @($py, "-m", "pip", "install", "-r", "requirements.txt", "--quiet")

Step "Audit binaries and browser worker"
Run @("powershell", "-ExecutionPolicy", "Bypass", "-File", "scripts\fetch_binaries.ps1")

Step ".env"
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env from .env.example. Add GITHUB_TOKEN (and optional keys) there."
} else { Write-Host ".env exists, left unchanged." }

Step "Ollama models (the exact tags from .env)"
& ollama list 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) { Fail "Ollama is installed but not running. Start the Ollama app, then re-run." }
$envText = Get-Content ".env" -Raw
function EnvVal($name, $default) {
    if ($envText -match "(?m)^$name=(.+)$") { return $Matches[1].Trim() } else { return $default }
}
$models = @(
    (EnvVal "REVAMP_OLLAMA_INSTRUCT" "qwen3:4b-instruct-2507-q4_K_M"),
    (EnvVal "REVAMP_OLLAMA_THINKING" "qwen3:4b-thinking-2507-q4_K_M"),
    (EnvVal "REVAMP_OLLAMA_VISION" "qwen3-vl:4b-instruct")
)
foreach ($m in $models | Select-Object -Unique) { Write-Host "ollama pull $m"; Run @("ollama", "pull", $m) }

Step "Evidence for the demo product and its private client constraints"
Run @($py, "-m", "revamp", "constraints", "umami")
Run @($py, "-m", "revamp", "audit", "umami")

Step "Readiness check (loads each model and confirms it sits on the GPU)"
& $py -m revamp doctor --gpu
if ($LASTEXITCODE -ne 0) { Fail "doctor found problems (FAIL lines above)." }

Write-Host "`nREADY. Start:  .venv\Scripts\python.exe -m revamp.dashboard   ->  http://localhost:8700" -ForegroundColor Green
