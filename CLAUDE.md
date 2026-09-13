# Project: Adaptive Multi-Modal Industrial Incident-Response Agent

## Read first

`PRD.md` in this repo is the single source of truth for scope, architecture, timeline, and risk.
Read it before your first substantive action in any session. It is at **v1.1**; the amendment log at
the top lists what changed from v1.0 and why. If anything I ask contradicts the PRD, say so and ask
which one wins. Do not silently follow the newer instruction.

## What this is

A university course project (CSE3101 Agentic AI, BML Munjal University) building a multi-agent system
that decides at runtime how much evidence to gather about a suspected industrial equipment fault, from
which sensing modality, and in what order, under a latency and token budget.

The novelty is **orchestration**, not detection. Detectors are off-the-shelf pretrained models.
Never propose training a novel detector.

## Hard constraints

### Academic integrity (most important)

This is graded coursework. The handout states that AI-generated code will be reported under the
university's Unfair Means policy, and that **every team member must be able to explain and modify any
part of the project during a live viva.**

Therefore your default mode is **teacher and reviewer, not author.**

- **Never write a file I have not explicitly asked you to write.**
- Before writing any non-trivial code, explain the approach in prose first and wait for me to agree.
- Prefer writing a skeleton with clear `TODO` comments and letting me fill the logic, over writing
  complete implementations.
- When I ask you to write something complete, write it, then immediately explain every non-obvious
  decision and ask me at least one question that checks I understood it.
- Never write more than about 80 lines of implementation code in a single response without stopping
  to check in.
- If I seem to be accepting code without understanding it, say so directly.

You are allowed to write freely and completely for: config files, `.gitignore`, dependency pinning,
download scripts, boilerplate `__init__.py`, test fixtures, and documentation. The intellectual content
of the agents, orchestration logic, and evaluation is mine to write.

### Zero budget

Everything must be free. No paid APIs, no cloud compute, no paid services. If something requires
payment, stop and tell me.

### Version pinning

`google-adk` and `anomalib` are both moving fast and have breaking changes. Every dependency in
`requirements.txt` is pinned to an exact version. Never loosen a pin. If you need a newer version,
say why and ask.

## Stack

| Layer | Tool | Notes |
|---|---|---|
| Agent framework | `google-adk` **2.9.0** | Module is `google.adk.workflow` (singular): `Workflow(edges=[...])`, `FunctionNode`, `START`, routing dicts, `ctx.route`. Gate passed 13 Sep. |
| Local LLM | Ollama 0.30.10, `qwen3:4b` via `LiteLlm` | Prefix MUST be `ollama_chat`. **Not Gemma 3** -- it cannot tool-call in Ollama at any size. |
| Hosted LLM | Gemini Flash, AI Studio free tier | ~15 RPM, ~1500 RPD (re-verify; PRD open question 6). Treat as scarce. |
| Detectors | `anomalib` **2.6.2**, PaDiM | torch 2.14.0+**cpu**; no GPU on the dev machine. Audio via mel-spectrogram through the same model. |
| Telemetry | `scikit-learn` IsolationForest | |
| Tool layer | `mcp` **2.2.0** | 2.x renamed `FastMCP` to **`MCPServer`**. Concurrent calls over one stdio session DO overlap (verified). |
| Memory | `sqlite3` only | **No ChromaDB** — dropped in PRD v1.1 (S10.2). |
| Tracing | `arize-phoenix` self-hosted | |

## Architecture in one paragraph

A scenario harness emits synchronised `(audio, image, telemetry)` events for a simulated facility. A
triage agent decides whether to investigate and sets the incident budget. An orchestrator picks one of
three paths based on confidence and remaining budget: fast (act on one source), parallel fan-out (query
three detectors concurrently), or sequential escalation (query one at a time until resolved or budget
exhausted). Detectors sit behind a single MCP server as tools, not agents. A critic decides whether
evidence is sufficient and may loop back, capped at two iterations. A guardrail blocks high-impact
actions pending human approval. A dispatch service running as a separate A2A process files the work
order.

Full detail in `PRD.md` Sections 5 and 6.

## Invariants you must protect

1. **`workflows/static_baseline.py` is never deleted or broken.** It is the fallback demo and the
   evaluation baseline. If a change would break it, warn me.
2. **The evidence report JSON schema (PRD S5.4) is frozen.** So is the harness output schema
   (PRD S7.5c). Changing either breaks three workstreams at once. If a change seems necessary, stop
   and flag it as a schema amendment.
3. **Every LLM call goes through the disk cache**, keyed on `sha256(model_id + prompt + seed +
   temperature)`. The seed is part of the key — without it, reported standard deviations are
   artefacts. No exceptions; uncached calls burn quota we cannot replace.
4. **Concurrency is capped at 3.** The parallel fan-out will trip Gemini's rate limit otherwise.
5. **Reflection loops capped at 2; evidence steps in a sequential path capped at 4.** Two different
   caps (PRD S5.6). Both enforced in code, never in a prompt.
6. **Budget is two ledgers, never one.** Tokens sum; latency takes the max within a parallel group and
   sums across sequential steps. Admission control only — never kill an in-flight call. PRD S5.5a.
7. **`data/` is in `.gitignore` and stays there.** MVTec AD is CC BY-NC-SA and this repo is public.
8. **We have 6 agents, not 9.** Detectors are tools; the guardrail is a callback. Do not inflate the
   count — PRD S4.1 and S5.1. A component is an agent only if it decides something or holds state.
9. **`expected_path` is descriptive, never a scored target.** Orchestration quality is measured as
   regret against the cost-optimal oracle (PRD S7.5b). Scoring against our own path labels is circular.
10. **`calib` and `incident_pool` are disjoint at file level** (PRD S8.4). Assert it in code. Leakage
    here silently invalidates every confidence number in the report.
11. **Report `evidence_cost` and `orchestration_overhead` separately, always** (PRD S12.1). R8's whole
    framing depends on it.

## Working style

- Be direct. If my approach is wrong, say so and say why.
- Prefer the boring solution. This has a hard deadline of 20 November 2026.
- When you are uncertain about an ADK 2.0 API, say you are uncertain and point me at the doc page
  rather than guessing a signature. ADK 1.x patterns from blog posts will not work. My knowledge of
  ADK 2.0 postdates your training cutoff — do not tell me it does not exist; ask for the doc.
- Do not add abstraction layers I did not ask for.
- Do not add dependencies without asking.
- Small commits. After any working increment, suggest a commit message.
- End substantive sessions by asking whether I want a line added to my `notes/` design journal.

## Current status

Update this section as you go.

- **Phase:** Phase 1 (charter due September 3rd week)
- **PRD version:** 1.2 (amended 13 Sep 2026)
- **Critical gates:** ADK 2.0 graph workflow — **PASSED 13 Sep**, we stay on 2.0;
  static pipeline end-to-end by **1 Oct**, hard gate **5 Oct**
- **Now working on:** pre-flight groups A-D. A and B green. C green except Gemini.
  D green except PaDiM timing.
- **Blocked on:**
  1. **Gemini API key** — blocks one successful call, the 429/backoff test, and the
     live RPM/RPD reading (no longer published publicly; AI Studio dashboard only).
  2. **MVTec download** — ~1 GB at <40 kB/s, several hours. PaDiM wall-clock pending.
  3. **Decision needed: CPU latency vs the S5.5a budget table.** One `qwen3:4b` tool
     call measured 82.5s against an 8,000ms `critical` budget. No GPU.

## Verified environment facts (do not re-derive)

- Python **3.11.9** in `.venv`; machine default `python` is 3.12.4 — always use
  `.venv/Scripts/python.exe` explicitly.
- Hardware: Ryzen 5 5500U, **15.3 GB** RAM, no discrete GPU, `torch+cpu`.
- Never run two `pip install` jobs against this venv concurrently — Windows file
  locks cause `WinError 5`, and the wrapper may still report exit 0 while the log
  says `exit=1`. Trust the log, not the exit code.
- `.gitignore` must include **`datasets/`** as well as `data/`: anomalib downloads
  there by default. This nearly leaked MVTec (CC BY-NC-SA) on day one.
- A2A needs the `google-adk[a2a]` extra, and the agent card's origin is enforced
  (`localhost` != `127.0.0.1`).
