# One-command setup on Windows (e.g. the GPU laptop that runs Ollama).
#
#   powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
#
# Needs, installed beforehand: Python 3.11 (py launcher), Node 22, Git, Ollama (with the
# GPU driver working: `ollama ps` shows "100% GPU" when a model is loaded).
# Safe to re-run: every step skips work that is already done.

$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root

function Step($msg) { Write-Host "`n== $msg" -ForegroundColor Cyan }

Step "Python 3.11 virtual environment"
if (-not (Test-Path ".venv\Scripts\python.exe")) { py -3.11 -m venv .venv }
.venv\Scripts\python.exe -m pip install --upgrade pip --quiet
.venv\Scripts\python.exe -m pip install -r requirements.txt --quiet

Step "Audit binaries and browser worker"
powershell -ExecutionPolicy Bypass -File scripts\fetch_binaries.ps1

Step ".env"
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env from .env.example. Add GITHUB_TOKEN (and optional keys) there."
} else { Write-Host ".env exists, left unchanged." }

Step "Ollama models (the exact tags from .env)"
$envText = Get-Content ".env" -Raw
function EnvVal($name, $default) {
    if ($envText -match "(?m)^$name=(.+)$") { return $Matches[1].Trim() } else { return $default }
}
$models = @(
    (EnvVal "REVAMP_OLLAMA_INSTRUCT" "qwen3:4b-instruct-2507-q4_K_M"),
    (EnvVal "REVAMP_OLLAMA_THINKING" "qwen3:4b-thinking-2507-q4_K_M"),
    (EnvVal "REVAMP_OLLAMA_VISION" "qwen3-vl:4b-instruct")
)
foreach ($m in $models | Select-Object -Unique) { Write-Host "ollama pull $m"; ollama pull $m }

Step "Evidence for the demo product and its private client constraints"
.venv\Scripts\python.exe -m revamp constraints umami
.venv\Scripts\python.exe -m revamp audit umami

Step "Readiness check (loads each model and confirms it sits on the GPU)"
.venv\Scripts\python.exe -m revamp doctor --gpu

Write-Host "`nNext:  .venv\Scripts\python.exe -m revamp.dashboard   ->  http://localhost:8700" -ForegroundColor Green
