# Agentic Product Revamp Studio

CSE3101 Agentic AI, BML Munjal University. Aakarsh Goyal, Saksham Garg, Tanishka Dhaka,
Saanvee Sharma.

A multi-agent consultancy that audits a real open-source SaaS product with measured evidence,
has specialist teams propose costed changes, arbitrates their conflicts under a fixed
engineering budget, sequences the survivors by dependency, and negotiates with a Client agent
that holds constraints the team cannot see. The output is a sequenced revamp plan in which every
item traces back to a tool measurement.

Plain-language summary of the work so far: [docs/PROGRESS.md](docs/PROGRESS.md).
Scope, decisions and build order: [PLAN.md](PLAN.md). Module walkthroughs for the viva:
[docs/walkthrough/](docs/walkthrough/).

## How it works

```
 audit (tools, no LLM) ──► Knowledge base (SQLite, namespaced)
                                  │
 Engagement Lead ─► Voice of Customer + Journey Auditor ─► Design / Engineering / Product&Pricing
                                                                  │ proposals cite finding ids
 Engineering handoff review ──reject──► back to the proposing team (≤ 2 rounds)
                                  │
 Conflict Detector ─► Budget Allocator (exact ILP) ─► Dependency Sequencer ─► Red Team (≤ 2)
                                  │
 Client (separate A2A process, private constraints) ──reject──► Engagement Lead adapts (≤ 3)
                                  │ accept
 Human approval of high-impact items ─► final plan + HTML report
```

Ten LLM agents and two deterministic solvers. The audits are MCP tools, not agents.

## Setup

```powershell
py -3.11 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
powershell -ExecutionPolicy Bypass -File scripts\fetch_binaries.ps1   # osv-scanner, scc, browser worker + Chromium
copy .env.example .env    # then fill in keys if needed (defaults to local Ollama)
ollama pull qwen3:4b-instruct-2507-q4_K_M
ollama pull qwen3:4b-thinking-2507-q4_K_M
ollama pull qwen3-vl:4b-instruct
```

Everything runs locally by default via Ollama, in three tiers: **instruct** for most agents,
**thinking** for the arbitration judgments (Conflict Detector, Red Team, feasibility review,
inferring the client's hidden constraints), and **vision** for the Journey Auditor's
screenshots. Gemini is an optional alternative (`REVAMP_MODEL_MODE=hybrid|gemini`).

### Plug and play on a GPU machine

```powershell
git clone https://github.com/goyalaakarsh/ai-prj.git; cd ai-prj
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1     # Linux/macOS: bash scripts/setup.sh
```

This creates the venv, installs everything, downloads the audit binaries and Chromium, creates
`.env`, pulls the three models, audits the demo product, and runs
`python -m revamp doctor --gpu`. That last step loads each model and fails loudly if a model is
not in VRAM. Every model call forces the GPU (`REVAMP_OLLAMA_NUM_GPU=999`). The only manual
step is adding `GITHUB_TOKEN` to `.env`.

Ollama on another machine: run `OLLAMA_HOST=0.0.0.0 ollama serve` there and set
`OLLAMA_API_BASE=http://<its-ip>:11434` here.
public APIs. The campus network's TLS inspection blocks PyPI; install from another network.

## Use

```powershell
.venv\Scripts\python.exe -m revamp audit umami            # evidence, no LLM -> its own report
.venv\Scripts\python.exe -m revamp audit umami --agentic  # the Chief Diagnostician over MCP
.venv\Scripts\python.exe -m revamp constraints umami      # load the client's private constraints
.venv\Scripts\python.exe -m revamp run umami --arm A2     # one engagement -> runs\reports\<id>.html
.venv\Scripts\python.exe -m revamp run umami --hitl       # pause for human approval
.venv\Scripts\python.exe -m revamp report <run id>       # rebuild any past report, no tools, no model
.venv\Scripts\python.exe -m revamp report <run id> --open  # ... and open it in the browser
.venv\Scripts\python.exe -m revamp findings umami --full  # every finding, not just the counts
.venv\Scripts\python.exe -m revamp eval umami --arms A0,A1,A2 --seeds 0,1,2
```

An audit is a run, so it has a run record, a trace, events and a report of its own at
`runs/reports/audit-<product>-<stamp>.html`: one row per step with the input it was given, the
findings it measured and their provenance, the cumulative coverage, and the evidence/orchestration
cost split. Reports are plain HTML with no dependencies, so they open from disk. Every run started
from the CLI **or** from Mission Control leaves that file behind.

## Watch it run

```powershell
.venv\Scripts\python.exe -m revamp.dashboard            # Mission Control -> http://localhost:8700
```

Mission Control shows the workflow graph live: the active node, the agents working inside it,
back-edges as they are taken, and every agent's prompt and answer. It also shows tool calls,
proposals, the budget ledger and plan waves, the conflict register, the client negotiation, and
the cost split. It can launch runs and audits, take the human-approval decision in the browser,
and replay any past run without a model.
[Walkthrough 05](docs/walkthrough/05-observability-dashboard.md) explains it.

Traces (OpenTelemetry, one trace per run) go to either backend:
- **Langfuse:** set `LANGFUSE_BASE_URL`, `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY`. Langfuse
  Cloud Hobby is free with no card. `deploy/langfuse` self-hosts it on a machine with RAM to
  spare.
- **Phoenix:** `docker run -p 6006:6006 arizephoenix/phoenix` (not a pip dependency: it conflicts with litellm and google-adk) and
  `PHOENIX_COLLECTOR_ENDPOINT=http://localhost:6006`.

Optional pieces:
- Client as a separate process: `python -m revamp.client_service --port 8765`, plus
  `REVAMP_CLIENT_URL=http://localhost:8765`.
- One model family for every agent: `--mode local` or `--mode gemini`.

## Tests

```powershell
.venv\Scripts\python.exe -m pytest -q
```

The suite runs offline. Agents are replaced by scripted models, so the tests check the
orchestration (routing, loop caps, provenance, veto, arms, human approval, A2A) independently
of model quality.

## Evaluation arms

| Arm | What changes | What it isolates |
|---|---|---|
| A0 | One LLM, same evidence | Multi-agent at all |
| A1 | Teams in parallel, no arbitration | The arbitration layer |
| A2 | Full system | Reference |
| A3 | No Conflict Detector | Conflict detection |
| A4 | Unlimited budget | Budget scarcity |
| A5 | No handoff rejection | Handoff rejection |
| A6 | Client constraints visible to teams | Information asymmetry |

## Repository hygiene

Audited products' source (`workspace/`), tool output and screenshots (`runs/`), the LLM cache
(`cache/`) and secrets (`.env`) are gitignored. The product configs and the private-constraint
files in `products/` are committed on purpose: their commit timestamps prove the constraints
were written before any evaluation run.
