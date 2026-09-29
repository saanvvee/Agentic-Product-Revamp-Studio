# Project: Agentic Product Revamp Studio

## Read first

`PLAN.md` is the source of truth for scope, decisions (Section 2), architecture, and build order. The
Phase-1 synopsis is the original brief; where `PLAN.md` Section 1 contradicts it, `PLAN.md` wins.
The previous project (industrial incident response) is archived on branch
`obsolete/incident-response`. Do not touch it and do not reuse its invariants.

## What this is

CSE3101 Agentic AI course project (BML Munjal University). Team: Aakarsh Goyal, Saksham Garg,
Tanishka Dhaka, Saanvee Sharma. A multi-agent consultancy that audits a real open-source SaaS
product with measured evidence, has specialist teams propose costed changes, arbitrates conflicts
under a fixed engineering budget, sequences by dependency, and negotiates with a Client agent that
holds private constraints. Output: a sequenced, budget-constrained revamp plan with an evidence
chain for every item.

The novelty is **orchestration and arbitration**, not the audits. Audits are off-the-shelf tools.

## Working mode

Claude builds the code (owner's decision, 29 Sep 2026). Every member must still be able to explain
and modify any part in the viva, so:

- Code is plain and boring. No clever abstractions, no frameworks we did not ask for.
- Each module ends with a short walkthrough in `docs/walkthrough/` and viva questions.
- Explain non-obvious decisions in the final message of each step.
- Small commits, one per working increment.

## Hard constraints

- **Zero budget.** Nothing that needs payment or a credit card. Never enable billing on any Google
  Cloud / AI Studio project. If something needs payment, stop and say so.
- **Pin every dependency exactly** in `requirements.txt`. Never loosen a pin. Ask before adding one.
- **Secrets** live in `.env` only (gitignored). `.env.example` lists the names.
- Gemini free-tier prompts may be used for training: send it **public data only**.

## Stack (verified in this venv)

| Layer | Tool | Notes |
|---|---|---|
| Python | 3.11.9 in `.venv` | Always call `.venv/Scripts/python.exe`; machine default is 3.12 |
| Agent framework | `google-adk` 2.9.0 | `google.adk.workflow`: `Workflow(edges=[...])`, `ctx.route`, `ctx.run_node`, `RequestInput`. ADK 1.x blog patterns do not apply |
| Local LLM | Ollama 0.30.10, `qwen3:4b` via `LiteLlm` | Prefix MUST be `ollama_chat` (wrong prefix fails silently). Gemma 3 cannot tool-call. ~80 s per tool round trip on CPU |
| Hosted LLM | Gemini Flash, AI Studio free tier | Limits only on the AI Studio dashboard. Scarce |
| Tool layer | `mcp` 2.2.0 | Server class is `MCPServer` (not `FastMCP`) |
| A2A | `a2a-sdk` 1.1.2, `to_a2a` / `RemoteA2aAgent` | Experimental. `localhost` != `127.0.0.1` for the card origin |
| KB | `sqlite3` | No ChromaDB (PLAN D4) |
| Solver | `scipy.optimize.milp` | PLAN D5 |
| Tracing | `arize-phoenix` self-hosted | `phoenix.otel.register(auto_instrument=True)` |
| Audits | PSI API, Lighthouse CLI 13.5 (npx), axe via Playwright, osv-scanner, scc, lizard, GitHub API, Discourse JSON | See `notes/research-2026-09-29.md` |

## Invariants

1. **Every LLM call goes through the disk cache**, keyed on
   `sha256(model_id + request + seed + temperature)`.
2. **Every `Finding` cites a tool run; every `Proposal` cites at least one existing `finding_id`.**
   The provenance validator is code, not a prompt.
3. **`client_private` is unreadable by team roles**, enforced in the KB layer and tested. ADK state
   has no access control, so never put Client constraints in session state.
4. **Every back-edge has a counter in code:** Client rejection loop <= 3, Red Team loop <= 2. ADK
   does not bound cycles.
5. **LLM concurrency <= 3**, enforced by a semaphore. `Workflow.max_concurrency` does not cover
   `ctx.run_node` children.
6. **Contracts in `revamp/contracts.py` are frozen** once B1 lands. A change is a logged amendment in
   `PLAN.md`.
7. **Voice of Customer only sees items dated before the product's `cutoff`**, enforced in the tool
   layer. Otherwise the answer key leaks into the input.
8. **Answer-key overlap is descriptive, never the only score.**
9. **Report evidence cost (tool runs) and orchestration cost (LLM) separately.**
10. **Be polite to live sites:** PSI for performance; axe/Playwright on a short page list; crawls
    throttled to ~1 request/s and obey robots.txt.
11. `workspace/`, `cache/`, `runs/`, `.env` are gitignored and stay that way.

## Working style

- Be direct. If an approach is wrong, say so and why.
- Uncertain about an ADK 2.9 API: read the installed source under `.venv/Lib/site-packages/google/adk/`
  before writing the call. Do not guess signatures.
- Windows: never run two `pip install` against this venv at once (`WinError 5`).

## Current status (30 Sep 2026)

- **Built:** B0-B13 plus observability (`revamp/observe.py`, `revamp/tracing.py`) and the
  Mission Control dashboard (`python -m revamp.dashboard`). 51 offline tests pass.
- **Verified live (30 Sep):** all 7 MCP audit tools through a real MCP stdio client (umami:
  123 findings); deterministic audit; Phoenix receiving OTLP spans; dashboard streaming a real
  local-model run.
- **Owner still to do:**
  1. `.env`: GOOGLE_API_KEY (AI Studio, no billing), GITHUB_TOKEN, optional PSI_API_KEY.
     Langfuse: Cloud Hobby keys (free), or self-host `deploy/langfuse` on a machine with RAM.
  2. Replace `products/constraints/umami.yaml` (demo, circular), write constraints for the
     other products and answer-key themes, by a member who has not read the prompts.
- **Verified facts (do not re-derive):**
  - LiteLLM + Ollama qwen3 needs `reasoning_effort="none"` (think=false), else >600 s per call.
  - osv-scanner 2.6 `--recursive` walks the drive root on Windows; pass `-L <lockfile>`.
  - ADK: a node must not set `ctx.route` before yielding `RequestInput`, or resume fast-forwards.
  - ADK: two routed edges between the same node pair = "Duplicate edge"; use `DEFAULT_ROUTE`.
  - Discourse robots.txt disallows `/search`; use `/top.json`.
  - Campus network: only PyPI is TLS-intercepted. httpx, gh, git, npm work. Install Python
    packages from GitHub source (`--no-build-isolation`); browser tooling comes from npm
    (`browser_worker/`).
  - MCP stdio children get a minimal environment and inherit the JSON-RPC stdin: pass
    `env=os.environ` and use `stdin=DEVNULL` for subprocesses, or Lighthouse finds no Chrome.
  - Self-hosted Langfuse (ClickHouse + Postgres + Redis + MinIO) does not fit next to Ollama
    on this 15 GB laptop.
