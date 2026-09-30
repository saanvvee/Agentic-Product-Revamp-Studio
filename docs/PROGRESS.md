# Agentic Product Revamp Studio: Work Done So Far

*Status as of 30 September 2026*

CSE3101 Agentic AI, BML Munjal University
Team: Aakarsh Goyal, Saksham Garg, Tanishka Dhaka, Saanvee Sharma

---

## Contents

1. [The project in one paragraph](#1-the-project-in-one-paragraph)
2. [Why this problem is interesting](#2-why-this-problem-is-interesting)
3. [How a run works, step by step](#3-how-a-run-works-step-by-step)
4. [The agents, and what is not an agent](#4-the-agents-and-what-is-not-an-agent)
5. [The main building blocks](#5-the-main-building-blocks)
6. [Rules the system always follows](#6-rules-the-system-always-follows)
7. [How we will evaluate it](#7-how-we-will-evaluate-it)
8. [What is built, and what has been checked](#8-what-is-built-and-what-has-been-checked)
9. [What is still to do](#9-what-is-still-to-do)
10. [Key decisions and why we made them](#10-key-decisions-and-why-we-made-them)
11. [Things we learned the hard way](#11-things-we-learned-the-hard-way)
12. [How to run it](#12-how-to-run-it)
13. [Where to read more](#13-where-to-read-more)
14. [Glossary](#14-glossary)

---

## 1. The project in one paragraph

We built a team of AI agents that works like a small consultancy. It takes a real open-source
software product (our demo is **Umami**, a web analytics tool) and measures it with real tools:
page speed, accessibility, SEO, code quality, security advisories and user complaints. Specialist
teams (Design, Engineering, Product & Pricing) then propose changes, each with a cost in
engineering days. Their proposals often clash and always cost more than the budget allows, so an
arbitration layer resolves the clashes, picks the best set that fits the budget, and puts the
work in a sensible order. Finally a **Client** agent, which holds constraints the team is never
allowed to see, accepts or rejects the plan. The result is a sequenced, costed revamp plan in
which **every item traces back to a real measurement**.

## 2. Why this problem is interesting

Asking an LLM "how should I improve this product?" is easy, and the answer usually sounds good.
The hard part is **integration**:

- Two teams propose changes that contradict each other.
- Everything together costs three times the budget.
- Some changes depend on others being done first.
- The client has reasons for saying no that they never fully explain.

Our contribution is the **orchestration and arbitration** that handles these problems, not the
audits themselves. The audits use standard, off-the-shelf tools. We then test whether all this
machinery actually helps, by comparing it against a single LLM given the same evidence, and
against teams that work without arbitration.

## 3. How a run works, step by step

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

In plain words:

1. **Gather evidence.** Audit tools measure the product. Each result is saved as a **Finding**
   (for example, "the pricing page has a Largest Contentful Paint of 4.1 s") in a local SQLite
   database. No LLM is involved in this step.
2. **Set the focus.** The Engagement Lead reads the evidence and decides what the engagement
   should concentrate on.
3. **Listen to users.** Voice of Customer reads real GitHub issues and forum posts and separates
   genuine, repeated complaints (signal) from one-off noise. The Journey Auditor walks through
   the product page by page, takes screenshots, and reports where the experience breaks.
4. **Propose.** The three teams each propose changes. Every proposal must cite at least one real
   Finding and give a cost in engineering days.
5. **Handoff review.** Engineering checks the other teams' proposals. If an estimate looks
   unrealistic, the proposal goes back to its team for revision (at most 2 times).
6. **Arbitrate.**
   - The **Conflict Detector** finds proposals that contradict each other.
   - The **Budget Allocator** picks the most valuable set of proposals that fits the budget,
     respects dependencies and avoids conflicts. This is an exact mathematical optimisation,
     not a guess.
   - The **Dependency Sequencer** orders the chosen items into waves.
   - The **Red Team** challenges items that the evidence does not really support. Blocked items
     are removed and the plan is re-solved (at most 2 times).
7. **Negotiate with the Client.** The Client checks the plan against its private constraints.
   If it rejects, it gives only short reason codes. The Engagement Lead has to work out what
   went wrong and adapt the plan (at most 3 rounds).
8. **Human approval.** If the plan contains high-risk or very expensive items, the run pauses
   and asks a human to approve them.
9. **Report.** The final plan is written to an HTML report with the full evidence chain.

## 4. The agents, and what is not an agent

Our rule: **something is an agent only if it makes a judgment that needs a model.** Measuring,
optimising and sorting do not need one.

**The ten LLM agents**

| Agent | What it decides | Model |
|---|---|---|
| Engagement Lead | What to focus on; how to adapt after a Client rejection | Gemini |
| Chief Diagnostician | Which audits to run, and when there is enough evidence | qwen3 (local) |
| Voice of Customer | Which user complaints are real signal | qwen3 |
| Journey Auditor | Where user journeys break, from screenshots | Gemini (vision) |
| Design team | UI/UX changes and their cost | qwen3 |
| Engineering team | Technical changes, cost and dependencies | qwen3 |
| Product & Pricing team | Pricing and packaging changes | Gemini |
| Conflict Detector | Which proposals contradict each other | Gemini |
| Red Team | Which plan items the evidence does not support | Gemini |
| Client | Accept or reject (the decision is code; the LLM only writes the message) | Gemini |

**Not agents**

- **The audit tools** (Lighthouse, axe, osv-scanner and others). They measure; they do not
  decide.
- **The Budget Allocator.** It is an exact integer linear program (ILP).
- **The Dependency Sequencer.** It is a topological sort.
- **Human approval.** It is a pause point in the workflow.

The original synopsis had around 22 agents. We cut this to 10 because the local model takes
about 80–110 seconds per call on our laptops, and 22 agents would make a single run take hours.

## 5. The main building blocks

All code is in the `revamp/` package.

| Block | What it does | Main files |
|---|---|---|
| **Contracts** | The shared data shapes: `Finding`, `Proposal`, `Conflict`, `Plan`, `ClientVerdict`, `RunRecord`. Frozen, so everyone codes against the same thing | `contracts.py` |
| **Knowledge base** | One SQLite file with three namespaces (`shared`, `client_private`, `priors`). Who may read or write what is checked in code on every call | `kb.py` |
| **Audit tools** | Plain Python functions that measure the product and return Findings | `tools/` |
| **MCP server** | Exposes the audit tools to the Chief Diagnostician through the Model Context Protocol | `mcp_server.py` |
| **LLM layer** | Picks the model for each agent, caches every call on disk, and limits calls in flight to 3 | `llm/` |
| **Agents** | The ten agent definitions and their structured output schemas | `agents/` |
| **Workflow** | The Google ADK 2.9 graph that connects everything, with capped loops | `workflow/` |
| **Arbitration** | Budget optimiser, dependency sorter, client-constraint checker | `arbitration/` |
| **Client service** | The Client running as a separate process, reached over A2A | `client_service.py` |
| **Evaluation** | Runs the experiment arms and computes metrics in code | `evaluation.py` |
| **Report** | Static HTML report for each run | `report.py` |
| **Observability** | Live event stream, OpenTelemetry tracing, Mission Control dashboard | `observe.py`, `tracing.py`, `dashboard/` |

**Products.** Each product is described by a YAML file in `products/`, so the code works for any
of them without changes. We have configs for **Umami** (demo), **Mautic**, **Plane** and
**Invoice Ninja**. Each file lists the product's repository, public pages, forum, budget, and the
release we audit.

### The audit tools

| Tool | Measures |
|---|---|
| PageSpeed Insights API / Lighthouse | Page speed and Core Web Vitals |
| axe-core (in a real browser) | Accessibility against WCAG 2.2 AA |
| Playwright journeys | Screenshots and errors along user flows |
| SEO checks | Page HTML, robots.txt, sitemap |
| Pricing snapshot | The product's pricing page and its competitors' |
| GitHub issues / Discourse forum | Real user complaints |
| scc | Code size |
| lizard | Code complexity |
| osv-scanner | Known security advisories in dependencies |

None of them calls an LLM, and nothing from the audited product's code is installed or run.

### The budget optimiser, in brief

Choosing which proposals to fund is a classic "knapsack" problem with extra rules. We solve it
exactly with `scipy.optimize.milp`:

```
maximise   Σ value_i · x_i            (x_i = 1 if proposal i is chosen)
subject to Σ cost_i · x_i ≤ budget
           x_i ≤ x_j                   (i needs j, so i cannot be chosen without j)
           x_a + x_b ≤ 1               (a and b conflict, so pick at most one)
           x_i = 0                     (blocked by the Client, Red Team or a human)
```

A simple greedy approach ("pick the best value per day first") fails exactly the cases we care
about, for example when a cheap enabling change unlocks a valuable one. We have unit tests that
show this.

## 6. Rules the system always follows

These are enforced **in code**, not by asking the model nicely.

1. **Every LLM call is cached on disk**, keyed on the model, the request, the seed and the
   temperature. Re-running an experiment costs nothing and gives the same answer.
2. **Every Finding cites a tool run, and every Proposal cites at least one real Finding.**
   Proposals citing made-up Finding ids are cleaned or dropped, and we count how often this
   happens (our hallucination metric).
3. **The team can never read the Client's private constraints.** The knowledge base checks the
   caller's role on every read. ADK's shared session state has no access control, so we never
   put secrets there.
4. **Every loop has a hard cap:** handoff revision ≤ 2, Red Team ≤ 2, Client rejection ≤ 3.
   ADK does not stop cycles on its own.
5. **At most 3 LLM calls run at once**, enforced with a semaphore.
6. **The contracts are frozen.** Any change is logged as an amendment in `PLAN.md`.
7. **No peeking at the future.** Voice of Customer only sees posts from before the audited
   release's cutoff date, and security advisories published later are excluded. Otherwise the
   system would "predict" things it had already read about. (For Umami, this filter reduces
   the advisories from 152 to 3.)
8. **Evidence cost and LLM cost are reported separately**, so it is clear what the measurement
   costs and what the reasoning costs.
9. **We are polite to live websites:** at most one request per second per host, robots.txt
   respected, and page speed measured on Google's servers through the PSI API.

## 7. How we will evaluate it

### The answer key

Several products we chose later shipped a big, documented redesign. Umami, for example, moved
from v2 to a fully redesigned v3 in November 2025. We audit the **old** release and then compare
our plan with what the real team actually shipped. This is a useful check, but what shipped is
not necessarily what was best, so we report this overlap as descriptive only and never as the
sole score.

### The experiment arms

Each arm switches off one mechanism, so any difference in results is caused by that mechanism.

| Arm | What changes | What it tests |
|---|---|---|
| A0 | One LLM, same evidence | Is multi-agent worth it at all? |
| A1 | Teams in parallel, no arbitration | Is the arbitration layer worth it? |
| A2 | Full system | The reference |
| A3 | No Conflict Detector | Conflict detection |
| A4 | Unlimited budget | Budget pressure |
| A5 | No handoff rejection | Engineering review |
| A6 | Team can see the Client's constraints | Hidden information |

### The metrics

All are computed in code from the knowledge base:

- Hidden-constraint violations in the final plan
- Days over budget
- Dependency-order violations
- Contradictions left between teams
- Share of invented citations (hallucination rate)
- Client rounds, and whether the Client accepted
- Answer-key recall (descriptive only)
- Time and tokens, split into evidence cost and orchestration cost

### Guarding against fooling ourselves

- The Client's constraints must be written **before** any run, by a member who has not read the
  agent prompts, and committed to git so the timestamp proves it.
- The answer-key themes must be written blind to the system's outputs.
- User complaints and security data stop at the cutoff date.

## 8. What is built, and what has been checked

### Build steps

All thirteen planned build steps are done, plus observability.

| Step | What | Status |
|---|---|---|
| B0 | Project skeleton, exact dependency pins, settings | Done |
| B1 | Data contracts | Done |
| B2 | LLM layer: model registry, disk cache, concurrency limit | Done |
| B3 | Knowledge base with role-based access | Done |
| B4 | Audit tool runners | Done (PSI needs an API key to run live) |
| B5 | MCP tool server | Done |
| B6 | Product configs for 4 products | Done (local Docker replay not built) |
| B7 | Budget optimiser, dependency sorter, constraint checker | Done |
| B8 | The ten agents | Done |
| B9 | ADK workflow graph with capped loops, all 7 arms | Done |
| B10 | Client over A2A, human approval step | Done |
| B11 | Evaluation runner and metrics | Done |
| B12 | HTML report per run | Done |
| B13 | Module walkthroughs with viva questions | Done |
| Extra | Mission Control live dashboard and OpenTelemetry tracing | Done |

### What has been checked

- **51 automated tests pass** (last run 30 Sep 2026, about 19 seconds). They run offline: agents
  are replaced by scripted fake models, so the tests check the orchestration itself (routing,
  loop caps, provenance, veto, all arms, human approval, the real A2A connection) independently
  of how good the model is.
- **All 7 MCP audit tools work end to end** through a real MCP client against the live Umami
  project, producing 123 findings.
- **The deterministic audit** (every tool, no LLM) runs end to end.
- **Tracing reaches Arize Phoenix** (spans received).
- **The dashboard streams a real run** that uses the local model.

### Timeline

| Date | What happened |
|---|---|
| 13–14 Sep | Previous project idea (industrial incident response) built and explored |
| 29 Sep | Pivot to Revamp Studio. Old work archived on branch `obsolete/incident-response`. Research, plan, decisions D1–D8, then build steps B0–B13 |
| 30 Sep | Browser worker, all tools verified live, Mission Control dashboard, tracing, docs |

## 9. What is still to do

**Owner setup**

1. Fill in `.env`: `GOOGLE_API_KEY` (AI Studio, no billing), `GITHUB_TOKEN`, and optionally
   `PSI_API_KEY`. For Langfuse, use the free Cloud Hobby keys.

**Evaluation inputs (must be written by a member who has not read the prompts)**

2. Replace the demo constraint file `products/constraints/umami.yaml`. The current one was
   written by the same assistant that wrote the prompts, so it is circular.
3. Write constraint files for Mautic, Plane and Invoice Ninja.
4. Fill in the answer-key `themes` in each product YAML, blind to any outputs.

**Then**

5. Run the evaluation arms (A0–A6 over the products and seeds), likely overnight or on Gemini.
6. Write up the results, including the honest limitations below.

**Optional**

- Local Docker replay of old releases (a second audit target).
- Tier-2 agents (Growth, Quality & Risk, Retro and others), only if time remains.

### Honest limitations to state in the report

- The local model is slow (about 90–110 s per call on CPU). A full local run takes tens of
  minutes.
- The Client's decision is rule-based on purpose, so that the veto and the metric are exact. The
  team learns about hidden constraints only from short reason codes, not from a free
  conversation.
- "Contradictions between teams" is measured by a crude proxy (different teams touching the same
  area).
- Answer-key recall is keyword matching against hand-written themes.

## 10. Key decisions and why we made them

| Decision | Why |
|---|---|
| **10 agents, not 22** | 22 agents on a CPU model would take hours per run. Audits became tools, since measuring is not judging |
| **Products: Umami, Mautic, Plane, Invoice Ninja** | Open source, public, and each later shipped a documented redesign we can use as an answer key. Cal.com, named in the synopsis, went closed-source in April 2026 |
| **Audit live sites first** | Lighthouse on Wayback Machine copies measures archive.org, not the product |
| **SQLite, no vector database** | Namespaces, provenance and access checks are relational. We had no measured need for vector search |
| **Exact ILP for the budget** | Greedy selection fails on dependencies and conflicts, which are exactly the cases we care about |
| **Client decision in code** | The veto is exact, and the evaluation metric uses the same check, so behaviour and measurement cannot drift apart |
| **Client as a separate process (A2A)** | A process boundary is stronger proof of information hiding than a rule inside one program. A same-process fallback exists because ADK's A2A support is experimental |
| **Hybrid models** | The local qwen3 model is free but slow and cannot see images. Gemini's free tier is scarce, so it goes to the agents that need vision or heavy reasoning |
| **Zero budget** | Nothing that needs payment or a credit card. Gemini only ever receives public data |
| **Own dashboard as well as Langfuse** | Trace tools show spans. They do not know what a budget ledger, a veto or a handoff rejection is |

## 11. Things we learned the hard way

These cost us time and are good viva material.

- **The local model hung for over 10 minutes per call** until we turned off its "thinking" mode
  (`reasoning_effort="none"` through LiteLLM).
- **The model prefix matters.** With LiteLLM and Ollama it must be `ollama_chat`. A wrong prefix
  fails silently.
- **osv-scanner's `--recursive` flag scans the whole drive on Windows.** We pass each lockfile
  explicitly instead.
- **ADK resume bug.** If a node sets its route before pausing for human input, ADK skips past the
  node on resume. We found the cause by reading ADK's source code.
- **ADK rejects two labelled edges between the same pair of nodes** ("Duplicate edge").
- **Discourse forbids `/search` in robots.txt**, so we read `/top.json` instead.
- **The campus network intercepts PyPI traffic**, so Python packages are installed from GitHub
  source and browser tooling comes from npm.
- **MCP child processes get a minimal environment**, so Lighthouse could not find Chrome until
  we passed the environment through explicitly.
- **Self-hosted Langfuse needs 4–6 GB of RAM** and does not fit next to Ollama on a 15 GB
  laptop. We use Phoenix locally or Langfuse Cloud instead.

## 12. How to run it

**One-time setup (Windows PowerShell):**

```powershell
py -3.11 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
powershell -ExecutionPolicy Bypass -File scripts\fetch_binaries.ps1
copy .env.example .env      # then add your keys
ollama pull qwen3:4b
```

**Everyday commands:**

```powershell
.venv\Scripts\python.exe -m revamp audit umami            # measure the product, no LLM
.venv\Scripts\python.exe -m revamp constraints umami      # load the Client's private constraints
.venv\Scripts\python.exe -m revamp run umami --arm A2     # one full engagement
.venv\Scripts\python.exe -m revamp run umami --hitl       # pause for human approval
.venv\Scripts\python.exe -m revamp eval umami --arms A0,A1,A2 --seeds 0,1,2
.venv\Scripts\python.exe -m revamp.dashboard              # Mission Control at http://localhost:8700
.venv\Scripts\python.exe -m pytest -q                     # run the test suite
```

Reports are written to `runs/reports/<run id>.html`.

**Mission Control** shows the workflow graph live: which step is running, which agents are
working, which loops were taken, and every agent's prompt and answer. It can also start runs,
take the human-approval decision in the browser, and replay any past run without a model, which
is our fallback for a live demo on a slow laptop.

## 13. Where to read more

| Document | What is in it |
|---|---|
| [README.md](../README.md) | Short project overview and commands |
| [PLAN.md](../PLAN.md) | Full scope, decisions, architecture and build order |
| [Walkthrough 00](walkthrough/00-overview.md) | The whole system in ten minutes |
| [Walkthrough 01](walkthrough/01-aakarsh-kb-tools-diagnostics.md) | Knowledge base, tools, diagnostics (Aakarsh) |
| [Walkthrough 02](walkthrough/02-saksham-orchestration-arbitration.md) | Workflow and arbitration (Saksham) |
| [Walkthrough 03](walkthrough/03-tanishka-perspective-teams.md) | User perspective and proposal teams (Tanishka) |
| [Walkthrough 04](walkthrough/04-saanvee-client-guardrails-eval.md) | Client, guardrails, evaluation (Saanvee) |
| [Walkthrough 05](walkthrough/05-observability-dashboard.md) | Tracing and Mission Control (everyone) |
| [Research notes](../notes/research-2026-09-29.md) | Sources behind the tool and product choices |

Each walkthrough ends with viva questions.

## 14. Glossary

| Term | Meaning |
|---|---|
| **Finding** | One measured fact about the product, linked to the tool run that produced it |
| **Proposal** | A suggested change with a cost, a value, and the Findings that justify it |
| **Plan** | The chosen proposals, in execution order, within budget |
| **Provenance** | The chain from a plan item back to the measurements behind it |
| **Arbitration** | Resolving conflicts, choosing under budget, and ordering the work |
| **Arm** | One version of the system in the experiment, with one mechanism switched off |
| **Answer key** | What the real product team shipped in their later redesign |
| **Cutoff** | The date of the audited release. Data after it is hidden from the system |
| **ADK** | Google's Agent Development Kit, the framework our workflow runs on |
| **MCP** | Model Context Protocol, a standard way to give an agent tools |
| **A2A** | Agent-to-Agent protocol, used to run the Client as a separate service |
| **ILP** | Integer linear program, the exact optimisation behind the budget choice |
| **HITL** | Human in the loop, the approval pause for high-impact items |
| **qwen3 / Gemini** | Our two model families: local and free, or hosted and free-tier |
