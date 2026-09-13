# Adaptive Multi-Modal Industrial Incident-Response Agent

Course project for **CSE3101 Agentic AI**, BML Munjal University, 2026-27.

## What this is

An agentic incident-response system for industrial equipment monitoring that
does **not** run a fixed pipeline. An orchestrator decides at runtime *how much*
evidence to gather, *from which modality*, and *in what order*, under an explicit
budget, then reflects on whether that evidence is sufficient before acting.

### The contribution is orchestration, not detection

The detectors are off-the-shelf pretrained models and we never train a novel one.

> The individual detection tasks in this project are well covered in the
> literature and we deliberately reuse published baselines. Our contribution is
> systems-level: a runtime-adaptive, budget-constrained orchestration policy over
> heterogeneous evidence sources, together with an evaluation methodology that
> measures orchestration quality rather than detection quality alone. We do not
> claim a new detection algorithm.

## The idea in one paragraph

A scenario harness emits synchronised `(audio, image, telemetry)` events for a
simulated facility. A triage agent classifies severity, which maps to a budget
through a static table. An orchestrator picks one of three structurally different
paths based on confidence and remaining budget: **fast** (act on one source),
**parallel fan-out** (query three detectors concurrently), or **sequential
escalation** (query one at a time until resolved or budget exhausted). Detectors
sit behind a single MCP server as tools. A critic decides whether the evidence is
sufficient and may loop back, capped at two iterations in code. A guardrail
blocks high-impact actions pending human approval. A dispatch service running as
a separate A2A process files the work order.

## Status

Phase 1. Pre-flight verification complete; see `PRD.md` for the full plan and
`notes/` for per-member design journals.

| Component | State |
|---|---|
| ADK 2.0 graph workflows | Verified (`google-adk` 2.9.0) |
| Local LLM tool calling | Verified (`qwen3:4b` via `ollama_chat`) |
| MCP concurrent tool calls | Verified overlapping over stdio |
| Cross-process A2A dispatch | Verified |
| Phoenix tracing | Verified |
| Detectors, harness, agents | In progress |

## Architecture: every external dependency is behind a seam

Each seam is a protocol we own, with at least two implementations. If a seam only
ever has one implementation, it is not a seam, and that is discovered at the
worst possible moment.

| Seam | Protocol | Implementations |
|---|---|---|
| LLM provider | `core/llm/base.py` | Ollama, Gemini, stub, plus a caching decorator |
| Detector | `detectors/base.py` | PaDiM, seeded mock |
| Event source | `harness/base.py` | synthetic generator, JSONL replay |
| Memory store | `memory/base.py` | SQLite, in-memory |
| Dispatch sink | `agents/dispatch/base.py` | A2A client, local stub |
| Tracing | `observability/base.py` | Phoenix, no-op |

Agents take their dependencies by constructor injection and never import a
concrete implementation. `core/config.py` decides which one is built, so the
whole system switches from local to hosted by changing one line.

## Setup

```bash
py -3.11 -m venv .venv
.venv/Scripts/activate          # Windows;  source .venv/bin/activate elsewhere
pip install -r requirements.txt

cp config/default.env .env      # then edit
```

Python **3.11** specifically — see `.python-version`.

For the local LLM path:

```bash
ollama serve
ollama pull qwen3:4b
```

Note `qwen3`, not Gemma 3: **Gemma 3 cannot make tool calls through Ollama at any
size**, and every local agent in this system needs structured tool calls.

## Tests

```bash
.venv/Scripts/python.exe -m pytest -q
```

Each seam has a test that runs against **both** implementations. That test is
what proves the seam is real rather than decorative.

## Data

No dataset files are in this repository. See **`DATA.md`** for sources, licences,
citations, and download instructions.

The datasets are used for non-commercial academic research. MVTec AD is
CC BY-NC-SA 4.0; `data/` and `datasets/` are gitignored from the first commit.

## Repository layout

```
core/           config, budget accounting, LLM provider seam
schemas/        frozen contracts: evidence report, incident record
detectors/      detector seam: PaDiM + mock
harness/        event source seam: synthetic generator + replay
memory/         memory store seam: SQLite + in-memory
agents/         triage, orchestrator, critic, memory, diagnostic, dispatch
guardrails/     action tiers, Tier-3 blocking, callbacks
workflows/      adaptive.py and static_baseline.py
mcp_server/     detectors exposed over MCP
observability/  tracing seam: Phoenix + no-op
eval/           ablations, custom trajectory metric, eval sets
tests/          dual-implementation seam tests
notes/          per-member design journals
```

## Documentation

- **`PRD.md`** — scope, architecture, risks, timeline. The source of truth.
- **`DATA.md`** — datasets, licences, citations.
- **`CLAUDE.md`** — working agreement and project invariants.
