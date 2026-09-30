#!/usr/bin/env bash
# One-command setup on Linux or macOS (e.g. the GPU machine that runs Ollama).
#
#   bash scripts/setup.sh
#
# Needs, installed beforehand: python3.11, Node 22 (npm), git, Ollama with a working GPU
# driver (`ollama ps` shows "100% GPU" when a model is loaded). Safe to re-run.
set -euo pipefail
cd "$(dirname "$0")/.."

OSV_VERSION=2.6.0
SCC_VERSION=4.1.0
step() { printf '\n== %s\n' "$1"; }

step "Python 3.11 virtual environment"
[ -x .venv/bin/python ] || python3.11 -m venv .venv
.venv/bin/python -m pip install --upgrade pip --quiet
.venv/bin/python -m pip install -r requirements.txt --quiet

step "Audit binaries (tools/bin) and browser worker"
mkdir -p tools/bin
case "$(uname -s)-$(uname -m)" in
  Linux-x86_64)  OSV=osv-scanner_linux_amd64;  SCC=scc_Linux_x86_64.tar.gz ;;
  Linux-aarch64) OSV=osv-scanner_linux_arm64;  SCC=scc_Linux_arm64.tar.gz ;;
  Darwin-arm64)  OSV=osv-scanner_darwin_arm64; SCC=scc_Darwin_arm64.tar.gz ;;
  Darwin-x86_64) OSV=osv-scanner_darwin_amd64; SCC=scc_Darwin_x86_64.tar.gz ;;
  *) echo "unsupported platform $(uname -s)-$(uname -m)"; exit 1 ;;
esac
[ -x tools/bin/osv-scanner ] || { curl -fsSL -o tools/bin/osv-scanner \
  "https://github.com/google/osv-scanner/releases/download/v$OSV_VERSION/$OSV"; chmod +x tools/bin/osv-scanner; }
[ -x tools/bin/scc ] || curl -fsSL "https://github.com/boyter/scc/releases/download/v$SCC_VERSION/$SCC" \
  | tar -xz -C tools/bin scc
(cd browser_worker && npm install --no-audit --no-fund && npx playwright install chromium)

step ".env"
if [ ! -f .env ]; then cp .env.example .env; echo "Created .env. Add GITHUB_TOKEN (and optional keys)."; fi
val() { grep -E "^$1=" .env | tail -1 | cut -d= -f2- | tr -d '[:space:]'; }
INSTRUCT=$(val REVAMP_OLLAMA_INSTRUCT); THINKING=$(val REVAMP_OLLAMA_THINKING); VISION=$(val REVAMP_OLLAMA_VISION)

step "Ollama models"
for m in "${INSTRUCT:-qwen3:4b-instruct-2507-q4_K_M}" "${THINKING:-qwen3:4b-thinking-2507-q4_K_M}" \
         "${VISION:-qwen3-vl:4b-instruct}"; do
  echo "ollama pull $m"; ollama pull "$m"
done

step "Evidence for the demo product and its private client constraints"
.venv/bin/python -m revamp constraints umami
.venv/bin/python -m revamp audit umami

step "Readiness check (loads each model and confirms it sits on the GPU)"
.venv/bin/python -m revamp doctor --gpu

printf '\nNext:  .venv/bin/python -m revamp.dashboard   ->  http://localhost:8700\n'
