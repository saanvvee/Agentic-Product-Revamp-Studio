# Agentic Product Revamp Studio — Implementation Plan

**Status:** DRAFT v0.1, 29 Sep 2026. Not yet agreed by the team.
**Source of truth for scope:** the synopsis (Phase-1 submission). This plan turns it into modules, phases
and todos, and flags where the research contradicts the synopsis. Once the team signs off on Section 2,
this becomes `PRD.md` v1.0.
**Hard deadline:** 20 Nov 2026 (semester end). That leaves **7.5 weeks**, not 8.
**Previous project:** archived on branch `obsolete/incident-response`. Environment facts verified there
(ADK 2.9, Ollama, MCP 2.2, Phoenix) are reused below.

---

## 1. What the research changed (read this first)

Three research passes ran on 29 Sep: the tool/API survey, candidate products, and ADK 2.9 capabilities.
Evidence URLs are in `notes/research-2026-09-29.md`.

| # | Finding | Impact on the synopsis |
|---|---|---|
| F1 | **Cal.com went closed-source on 15 Apr 2026.** The public repo is now the `calcom/cal.diy` fork. | The synopsis names Cal.com as the first data source. **Replace it.** |
| F2 | Lighthouse on Wayback-archived pages measures archive.org, not the product (rewritten URLs, broken JS, archive latency). | "Historical replay via Wayback CDX" does not work for performance. **Replace it with a local self-hosted replay of the pre-redesign release** (F3). Keep Wayback for text/SEO diffs only. |
| F3 | Several candidates **shipped a documented redesign later**: Umami v2 to v3 (Oct/Nov 2025), Mautic 5 to 6 "Orion" (Mar 2025), Plane Navigation 2.0 (Dec 2025), OpenProject Primer migration, Invoice Ninja Flutter to React (2024). | This gives an **answer key**. Audit the *old* release, then compare the plan against what the team really shipped. It is the strongest evaluation idea available to us. |
| F4 | Gemini free-tier limits are **no longer published** (AI Studio dashboard only). **Free-tier prompts may be used for training and read by human reviewers.** | Send Gemini only public data (fine, since everything we audit is public). Read the real RPM/RPD from the dashboard before planning quota. |
| F5 | ADK 2.9 state is **one shared dict with no access control.** | The Client's private namespace **must be enforced in our own KB/MCP layer**, as the synopsis already says (Aakarsh). This is a good viva point. |
| F6 | ADK graph cycles are **not bounded automatically**. | Every rejection/back-edge loop needs an explicit counter in code. |
| F7 | `Workflow.max_concurrency` does **not** throttle nodes started with `ctx.run_node()`. | Dynamic fan-out needs our own `asyncio.Semaphore` or `max_parallel_workers`. |
| F8 | ADK A2A is marked **EXPERIMENTAL**. `localhost` and `127.0.0.1` are different origins. | Keep a same-process fallback for the Client agent. |
| F9 | `qwen3:4b-instruct` on local Ollama: all agents wired locally by default. | Previous ~82.5 s CPU metric was measured on an older device; current setup runs local model calls directly. |
| F10 | npm audit, pip-audit and radon don't fit JS/TS/PHP/Ruby repos without a full install. | Use **osv-scanner** (reads lockfiles from a bare clone) and **lizard** (multi-language complexity) instead. |

---

## 2. Decisions the team must make (blocking Phase 1)

Decided 29 Sep 2026 (Aakarsh).

- **D1 — Agent count: compressed.** 10 LLM agents + 2 deterministic solvers (Section 4). Auditors are
  MCP tools. Tier-2 agents only if time remains.
- **D2 — Products:** Umami, Mautic, Plane, Invoice Ninja; Umami is the demo product. **Build first,
  evaluate later**: code is product-agnostic, driven by `products/<name>.yaml`.
- **D3 — Audit target: both, live first.** Live public pages are the primary target (PSI API runs
  Lighthouse on Google's servers, so no load from us; axe/Playwright on a small page list; SEO crawl
  throttled). Local Docker of an old release is an optional second target for answer-key replay.
  Every `Finding` records `target` = `live` | `local:<version>`.
- **D4 — SQLite only.** Namespaces, provenance links and access checks are relational. Chroma adds
  vector search we have no measured need for, plus a dependency to explain.
- **D5 — Budget solver:** exact 0/1 ILP via `scipy.optimize.milp` (scipy already present, pinned).
  Precedence `x_i <= x_j`, conflict pairs `x_i + x_j <= 1`, capacity `sum(cost) <= budget`.
- **D6 — Disclosure:** out of scope for this plan (owner's call).
- **D7 — No phase dates.** Build the whole system in dependency order (Section 5), fast.
- **D8 — New `CLAUDE.md`:** written 29 Sep.
- **Authorship mode:** Claude builds all code; each module ends with a walkthrough so every member
  can explain and modify it in the viva.

---

## 2a. Contract amendments

| # | Date | Change | Why |
|---|---|---|---|
| 1 | 29 Sep 2026 | `Team` gains `"single_llm"` | Baseline A0's plan items need a proposal author that is not a team |

## 3. Architecture (modules and contracts)

Each module has one owner and a frozen interface. Members code against the contracts in parallel.
**The contracts in M1 are frozen at the end of Phase 1.** Changing one later is a schema amendment,
logged in the PRD.

```
            +------------------ Engagement Lead (scope, budget, loop control) ------------------+
            |                                                                                    |
  Product ->| Diagnostics  --> Findings (KB) --> Proposal teams --> Arbitration --> Plan --> Client (A2A)
  (Docker)  | (MCP tools)        ^   ^            (costed, cite      conflict,       ^         |
            | User perspective --+   |             finding ids)      knapsack,       |         |
            | (Playwright+vision)    |                               sequencing      +-reject--+
            |                  Provenance validator (code)                     (bounded, max 3)
            +---------------------- Retro writes priors to KB (Tier 2) ---------------------------+
```

| Module | What it is | Owner | Depends on |
|---|---|---|---|
| **M0 Infra** | pinned `requirements.txt`, `.env.example`, pre-commit hook for secrets, LLM disk cache, Phoenix setup | Aakarsh + all | none |
| **M1 Contracts** | pydantic models: `Finding`, `Proposal`, `Conflict`, `Plan`, `ClientVerdict`, `RunRecord` | all, frozen week 1 | none |
| **M2 Knowledge base** | SQLite, namespaced (`shared`, `client_private`, `priors`), provenance table, access enforced by the caller role in code | Aakarsh | M1 |
| **M3 MCP tool server** | one `MCPServer` wrapping runners: `lighthouse`, `axe_scan`, `screenshot_flow`, `osv_scan`, `scc`, `lizard`, `github_issues`, `discourse_topics`, `seo_crawl` | Aakarsh | M1 |
| **M4 Product harness** | Docker Compose per product and release (old and new), health check, seeded demo data, teardown | Tanishka + Aakarsh | none |
| **M5 Diagnostics layer** | Chief Diagnostician picks which audits to run and when evidence is enough; writes `Finding`s | Aakarsh | M2, M3 |
| **M6 User perspective** | Voice of Customer (complaint signal vs noise), Journey Auditor (Playwright flows + screenshot vision) | Tanishka | M3, M4 |
| **M7 Proposal teams** | Design, Engineering, Product & Pricing (Tier 1); Growth, Quality & Risk (Tier 2). Each emits costed `Proposal`s that cite finding ids | Tanishka | M2, M5, M6 |
| **M8 Arbitration** | Conflict Detector (LLM), Budget Allocator (solver), Dependency Sequencer (toposort), Red Team (LLM) | Saksham | M7 |
| **M9 Orchestration** | ADK 2.9 graph: routed back-edges with counters, fan-out with semaphore(3), HITL pause | Saksham | M5–M8 |
| **M10 Client + guardrails** | Client agent as a separate A2A process; private constraints in `client_private`; veto logic; HITL on high-impact items | Saanvee | M2, M9 |
| **M11 Evaluation** | arms A0–A6, metrics, answer-key scoring, results tables | Saanvee (lead) + all | everything |
| **M12 Dashboard** | trace viewer, conflict register, budget ledger, plan view | all (Phase 6) | M11 |

### Invariants (proposed, to be copied into the new CLAUDE.md)

1. **Every LLM call goes through the disk cache**, keyed on `sha256(model_id + prompt + seed + temperature)`.
2. **Every `Finding` cites a tool run.** Every `Proposal` cites at least one existing `finding_id`. The
   provenance validator is code, not a prompt.
3. **The Client namespace is unreadable by team agents**, enforced in the KB layer and tested.
4. **Every back-edge has a counter in code:** client rejection loop ≤ 3, red-team loop ≤ 2.
5. **Concurrency cap of 3** on LLM calls (Gemini RPM), enforced by semaphore.
6. **Contracts (M1) are frozen after Phase 1.** Changes are logged amendments.
7. **No credentials, no `.env`, no product data dumps are committed.** Audited product source is
   cloned into `workspace/` and gitignored.
8. **Answer-key overlap is descriptive, never the only score** (what shipped ≠ what was optimal).

---

## 4. Agent roster, tiered

**Tier 1: 10 LLM agents and 2 solvers (MVP; these must work).**

| Layer | Component | LLM | Decides |
|---|---|---|---|
| Engagement | Engagement Lead | Gemini | scope, budget, when to stop |
| Engagement | **Client** (A2A) | Gemini | accept or reject against private constraints |
| Diagnostics | Chief Diagnostician | qwen3 | which audits, sufficiency |
| User | Voice of Customer | qwen3 | which complaints are signal |
| User | Journey Auditor | Gemini (vision) | where flows break, from screenshots |
| Proposal | Design team | qwen3 | UI/UX changes, cost |
| Proposal | Engineering team | qwen3 | technical changes, cost, dependencies |
| Proposal | Product & Pricing team | Gemini | pricing and packaging changes |
| Arbitration | Conflict Detector | Gemini | which proposals contradict |
| Arbitration | Red Team | Gemini | which plan items are unsupported or risky |
| Arbitration | Budget Allocator | **none (solver)** | subset under the capacity budget |
| Arbitration | Dependency Sequencer | **none (toposort)** | execution order |

The synopsis's separate Performance/A11y/SEO/Codebase/Security auditors become **MCP tools that the
Chief Diagnostician calls**. Their output is measurement, not decision.

**Tier 2 (stretch, add in this order):** Growth team, Quality & Risk team, Escalation (tiebreak on
conflicting vetoes), Retro/Calibration (priors to KB), JTBD Analyst, Onboarding Critic, Delivery
Manager, Principal, Comparative UX.

---

## 5. Build order (dependency-ordered, no dates)

Each step ends runnable and tested. Tick when merged to `main`.

- [x] **B0 Infra:** `requirements.txt` pins, `pyproject.toml`, `.env.example`, `.gitignore`, package skeleton `revamp/`, settings loader
- [x] **B1 Contracts (M1):** pydantic models for `Finding`, `Proposal`, `Conflict`, `Plan`, `ClientVerdict`, `RunRecord`
- [x] **B2 LLM layer (M0):** model registry (qwen3 via `ollama_chat`, Gemini), disk cache as a `BaseLlm` wrapper (`CachedLlm`), semaphore(3), Phoenix tracing
- [x] **B3 Knowledge base (M2):** SQLite, namespaces, role-based access, provenance links, tests (team role cannot read `client_private`)
- [~] **B4 Tool runners:** (PSI needs a key; axe/journeys need Playwright, blocked by campus TLS; rest verified live) PSI, Lighthouse local, axe, Playwright screenshots, osv-scanner, scc, lizard, GitHub issues, Discourse, SEO crawl. Each returns `Finding`s; each has a recorded-fixture test
- [x] **B5 MCP server (M3):** `MCPServer` exposing runners and KB reads, caller role enforced
- [x] **B6 Product configs:** `products/{umami,mautic,plane,invoiceninja}.yaml` (URLs, repo, forum, release cut-off, budget). Local-replay Docker setup NOT built: set `local_base_url` by hand if you run one
- [x] **B7 Arbitration solvers (M8):** budget ILP (`scipy.optimize.milp`), dependency toposort, provenance validator. Pure functions, unit-tested
- [x] **B8 Agents:** Chief Diagnostician, Voice of Customer, Journey Auditor, Design, Engineering, Product & Pricing, Conflict Detector, Red Team, Engagement Lead, Client
- [x] **B9 Orchestration (M9):** ADK `Workflow` graph with bounded back-edges; baselines A0 and A1 as separate entry points
- [x] **B10 Client over A2A + HITL (M10):** separate process, private constraints, veto; `RequestInput` approval for high-impact items; in-process fallback
- [x] **B11 Evaluation (M11):** arm runner A0–A6, metrics in code, answer-key scorer, results tables
- [x] **B12 Dashboard (M12):** static HTML report per run (conflict register, budget ledger, plan, trace link)
- [x] **B13 Walkthroughs:** `docs/walkthrough/<module>.md` per module, with viva questions
- [x] **B14 Audit as a run:** `RunRecord` for both audit arms (`audit-det`, `audit-agentic`), per-step events with the step's input and its finding ids, `audit_finished` so the dashboard stops waiting, an HTML report per audit that rebuilds from `runs/events` + KB, audit-specific graph/KPIs in Mission Control, and the tool wall time booked to the parent's evidence ledger (invariant 9 for MCP tools). `revamp/contracts.py` untouched.

---

## 6. Evaluation design (draft)

**Arms.**

| Arm | What it is | What it isolates |
|---|---|---|
| A0 | Single LLM, same evidence, asked for a plan | Value of multi-agent at all |
| A1 | Specialist teams in parallel, no arbitration | Value of the arbitration layer |
| A2 | Full system | Reference |
| A3 | A2 without the Conflict Detector | Conflict detection |
| A4 | A2 with unlimited budget | Budget scarcity |
| A5 | A2 without handoff rejection | Handoff rejection |
| A6 | A2 with Client constraints visible to the team | Information asymmetry |

**Metrics.** All except the last two are computed in code, not judged by an LLM.

- Unresolved contradictions left in the final plan
- Budget overrun: total cost against capacity
- Dependency-order violations
- Hidden-constraint violations, and rounds until the Client accepts
- Provenance coverage: % of plan items with a valid evidence chain
- Tokens and wall-clock, reported separately for **evidence** (tool runs) and **orchestration** (LLM)
- Answer-key recall: fraction of themes the product really shipped that the plan covers
  (theme list written by hand **before** any run, by one member, and blind to the outputs)
- Optional: rubric scoring by an LLM judge. It must be a different model from the planner, and it is
  a secondary metric only.

**Circularity traps (these must be in the report).**

- We author the Client's hidden constraints, so A6 can be gamed. Write the constraints before building
  the team agents, have them written by someone who didn't write the prompts, and freeze them in git
  with a timestamp.
- The answer key is what shipped, not what was optimal. Report it as descriptive overlap only.
- Voice of Customer must only see issues and posts dated **before** the old release's cut-off, or the
  answer key leaks into the input.

**Seeds.** A2 at 3 seeds; other arms at 1 seed unless quota allows more.

---

## 7. Descope ladder (apply in order the moment a gate slips)

1. Drop Tier-2 agents entirely.
2. Evaluation set drops to 3 products (Umami, Mautic, Plane).
3. Client runs in-process instead of over A2A (keep the namespace enforcement).
4. Journey Auditor drops vision and uses the axe and Playwright DOM only.
5. Ablations cut to A0, A1, A2, A6.
6. Evaluation set drops to Umami only, at 3 seeds.

---

## 8. Top risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| CPU LLM latency makes the evaluation arms take days | High | Tier-1 roster; Gemini for heavy reasoning; cache; run evaluation overnight from 3 Nov |
| Gemini free quota lower than assumed | Medium | Read the dashboard in Phase 0; cache; concurrency 3; qwen3 fallback per agent |
| Docker harness for PHP/Rails products eats a week | Medium | Umami first (trivial); Mautic/Plane in Phase 2 with a timebox of 2 days each |
| qwen3:4b fails structured output | Medium | Validate in code; retry once; route that agent to Gemini |
| Lighthouse variance swamps before/after deltas | Medium | Median of 5, simulated throttling, never run two at once |
| Answer-key leakage through post-release issues | Medium | Date filter in the tool layer, tested |
| A2A experimental breakage | Low–Medium | In-process fallback (descope step 3) |
| Integrity: code not understood by its owner | — | Owners write the logic; swap-owner walkthroughs weekly |

---

## 9. Open questions

1. Is the synopsis already submitted, or can Section 1's corrections still go into it?
2. Does the handout specify ADK, or was that our choice? (It affects how firmly we stay on 2.9.)
3. What does "engineering budget" mean in units: engineer-days? Who sets it per product?
4. Should pricing analysis cover Mautic, which has no SaaS pricing page (competitors only)?
