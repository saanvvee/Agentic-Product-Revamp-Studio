# Walkthrough 00: the whole system in ten minutes

Read this first, then the walkthrough for the modules you own. Every member must be able to
explain any module in the viva, so read the other three walkthroughs too.

## The one idea

Specialist advice is easy to get from an LLM. **Integration** is the hard part: proposals that
contradict each other, a budget they all compete for, a client with reasons they are not told.
This project's contribution is the orchestration and arbitration that handles integration,
evaluated against a single LLM (A0) and against teams without arbitration (A1).

## Data flow (files in brackets)

1. **Evidence.** Tool runners measure the product: Lighthouse via PSI, axe-core, Playwright
   journeys, SEO checks, pricing snapshots, GitHub/Discourse complaints, scc, lizard,
   osv-scanner (`revamp/tools/`). Each measurement becomes a `Finding`
   (`revamp/contracts.py`), stored in SQLite (`revamp/kb.py`).
2. **Diagnosis.** The Chief Diagnostician chooses which audits to run over MCP
   (`revamp/mcp_server.py`, `revamp/agents/diagnostics.py`). Alternatively, `audit` runs
   every tool deterministically (`revamp/audit.py`).
3. **Engagement.** An ADK 2.9 graph workflow (`revamp/workflow/graph.py`) runs:
   brief → perspectives → propose → handoff → conflicts → allocate → red team → client →
   approve → finalize, with bounded back-edges.
4. **Output.** A `Plan` plus an HTML report (`revamp/report.py`). `eval` runs arms × seeds
   and computes metrics in code (`revamp/evaluation.py`).

## The ten agents, and what is not an agent

| Agent | Decides | Local tier (default) / hybrid |
|---|---|---|
| Engagement Lead | Focus areas (instruct); how to adapt after a client rejection (**thinking**) | instruct + thinking (Gemini in hybrid) |
| Chief Diagnostician | Which audits to run; when evidence is sufficient | instruct (multi-turn tool loop) |
| Voice of Customer | Which complaints are signal | instruct |
| Journey Auditor | Where journeys break, from screenshots | **vision** (Gemini in hybrid) |
| Design / Engineering / Product & Pricing | What to change, at what cost; Engineering's handoff review is **thinking** | instruct (review: thinking) |
| Conflict Detector | Which proposals contradict | **thinking** (Gemini in hybrid) |
| Red Team | Which plan items the evidence does not support | **thinking** (Gemini in hybrid) |
| Client | Accept or reject (decision in code, message by LLM) | instruct (Gemini in hybrid) |

**Not agents:**
- The audit tools, which measure.
- The Budget Allocator (an exact ILP) and the Dependency Sequencer (a topological sort). They
  decide, but they need no LLM.
- The human-approval guardrail, which is a workflow node.

Rule: a component is an agent only if it makes a judgment a model is needed for.

## Invariants (CLAUDE.md), and where each is enforced

| Invariant | Enforced in |
|---|---|
| Every LLM call is cached, and the seed is in the key | `revamp/llm/cache.py` (`CachedLlm`), `revamp/llm/registry.py` |
| Every proposal cites real findings | `workflow/nodes.py::drafts_to_proposals`, `kb.py::add_proposal` |
| Team cannot read client constraints | `kb.py` role checks; separate A2A process (`client_service.py`) |
| Every loop has a code cap | `workflow/arms.py` caps, checked in `workflow/nodes.py` |
| At most 3 LLM calls in flight | `llm/cache.py` semaphore |
| No answer-key leakage | `tools/voice.py` cutoff filter; `tools/code.py` advisory date filter |
| Evidence cost and LLM cost reported separately | `contracts.py::CostLedger`, `tools/common.py::evidence_timer` |

## Honest limitations (put these in the report)

- Local mode has three Ollama tiers (`revamp/llm/registry.py`, `LOCAL_TIER`): instruct `qwen3:4b-instruct-2507-q4_K_M`, thinking `qwen3:4b-thinking-2507-q4_K_M`, vision `qwen3-vl:4b-instruct`. Thinking is used only where judgment is the point (conflicts, red team, feasibility, inferring hidden constraints) because it is several times slower. Every request forces the GPU (`num_gpu=999`); `python -m revamp doctor --gpu` confirms each model sits in VRAM.
- The client's decision is rule-based on purpose (exact metric). The LLM only words the reply.
  So "information asymmetry" means inferring constraints from coarse reason codes, not from free
  conversation.
- `cross_team_overlaps` is a crude, LLM-free proxy for unresolved contradictions.
- Answer-key recall is keyword matching against hand-written themes, and it is descriptive.
  What a product shipped is not proof of what was optimal.
- The demo constraint file for umami was written by the same assistant that wrote the prompts,
  so it is circular. Replace it before evaluating.
