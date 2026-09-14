# PRD: Adaptive Multi-Modal Industrial Incident-Response Agent

**Course:** CSE3101 Agentic AI (BML Munjal University, 2026-27, 7th Semester)
**Faculty:** Dr. Soharab Hossain Shaikh, Mr. Pranshu Tiwari
**Document version:** 1.7
**Date:** 13 September 2026 (v1.0), amended 13-14 September 2026 (v1.1-v1.7)
**Semester window:** 27 July 2026 to 20 November 2026
**Status:** Ready for Phase-1 submission

### Amendment log

| Version | Change | Rationale |
|---|---|---|
| 1.1 | Agent count restated as 6, not 9 (S5.1) | S4.1 applied strictly; analysts are tools, not agents |
| 1.1 | Expected-path ground truth replaced by cost-optimal oracle + regret (S7.5, S12.1) | Fiat path labels made path accuracy circular and trivially gamed by an if/else |
| 1.1 | Harness scope cut to 3 machines / 1 MIMII type / 2 MVTec categories (S7.3, S7.5) | Hidden critical path; halves the largest work item |
| 1.1 | "Deceptive" ambiguity level given a constructive definition (S7.5) | Was unbuildable as written |
| 1.1 | Budget accounting fully specified; ms and tokens accounted separately (S5.5a) | Core mechanism was one sentence |
| 1.1 | Calibration split specified, leakage prohibited (S8.4) | R7 mitigation was unexecutable |
| 1.1 | Cache key includes seed; variance reported on A2 only (S7.8, S12.4) | Prompt-hash-only key forced std dev to exactly zero |
| 1.1 | Ablations cut to A0/A1/A2/A3 planned, A4/A5 stretch (S12.2) | Quota arithmetic; A3 retained to defend the memory agent in viva |
| 1.1 | ChromaDB dropped; SQLite only (S10.2) | One dependency served one bullet |
| 1.1 | Post-incident reviewer agent cut (S5.1) | Was descope tier 1 and fed no metric |
| 1.1 | Orchestrator overhead measured separately from evidence cost (S12.1) | R8 rescue depends on it |
| 1.1 | R1 re-rated High/High with 1.x-equivalent design written out (S6.3, S18.1) | Framework capability is an architecture gate, not a checkbox |
| 1.1 | R8 impact raised to Medium; R16 promoted; R19 team availability added (S18) | See risk re-ranking |
| 1.1 | MCP concurrency added to pre-flight; stdio multiplexing unverified (S9.2, S15) | Parallel path may serialise at the transport layer |
| 1.1 | Repo and MCP server renamed (S9.1, S14.4) | Stale names from another project |
| 1.1 | Dispatch work-order templates specified as a deliverable (S7.6a) | Agent 10 referenced templates that did not exist |
| 1.1 | `demo/dashboard.py` removed from the tree (S14.4) | In no milestone, no deliverable, no descope tier |
| 1.1 | Syllabus-vocabulary argument for ADK 2.0 withdrawn (S6.1) | "Template-based workflows" is 1.x vocabulary; handout covers both generations |
| **1.2** | **Architecture gate PASSED** -- `google-adk==2.9.0`, graph workflow with conditional route ran (S6.2) | Pre-flight item 3. We stay on 2.0; the S6.3 1.x branch is not taken |
| 1.2 | Real ADK 2.0 API surface recorded; module is `google.adk.workflow` singular (S6.2) | v1.0 named constructs that do not exist. Read from the installed package |
| 1.2 | **Gemma 3 rejected; `qwen3:4b` selected** (S14.1, S14.2a) | Gemma 3 does not support tool calls in Ollama at any size. Resolves open question 3 |
| 1.2 | `ollama_chat` vs `ollama` trap verified empirically (S14.2) | Wrong prefix: no tool call, empty text, no exception. Viva demo material |
| 1.2 | **CPU latency measurements contradict the budget table** (S5.5a) | One local call is 82.5s against an 8,000ms budget. Flagged as a live open item for M2 |
| 1.2 | **R20 CLOSED** -- stdio multiplexes concurrent tool calls (S9.2, S18.1) | Measured 4.02s sequential vs 2.02s concurrent. Parallel fan-out is real |
| 1.2 | R17 near miss recorded: `datasets/` added to `.gitignore` (S18.2) | anomalib downloads to `./datasets/`, which the v1.0 spec did not cover |
| 1.2 | `mcp` 2.x renames `FastMCP` to `MCPServer` (S9.1, S14.1) | v1 vocabulary in the PRD and in every tutorial |
| 1.2 | A2A verified cross-process; three gotchas recorded (S9.4) | Needs the `[a2a]` extra; agent-card origin is enforced; layer is EXPERIMENTAL |
| 1.2 | Phoenix verified capturing ADK traces (S13) | `traces=1`, span `invocation [traced_gate]` |
| 1.2 | Gemini free-tier RPM/RPD **no longer public**; must be read from the AI Studio dashboard (S7.8) | Blocks the S7.8 arithmetic until the key exists |
| 1.2 | **Domain cost vs system overhead split** (S5.5b) | Budgeting LLM latency was a category error. The budget models plant evidence acquisition; LLM latency is substrate overhead, measured and reported but never budgeted. Also completes the R8 guard |
| 1.2 | **R22 added: eval wall-clock is now the critical path**, not the harness (S7.5, S18.1) | ~4 min of local LLM time per incident x 150 incidents = ~10 h per ablation run on CPU. Fix is free Colab T4 for eval runs |
| 1.2 | R23 added: pin model tags, stamp execution environment into results (S14.3) | Consequence of running dev on CPU and eval on GPU |
| **1.3** | Oracle reframed as **"the cost-optimal plan under a reference decision rule"** (S7.5b) | It was never a lower bound on the system, only on evidence acquisition under a fixed fusion rule. Naming that kills the circularity |
| 1.3 | Reference rule is **sum of log-odds**, not mean-of-confidence (S7.5b) | Mean is non-monotone: adding a normal-looking source can flip a correct anomalous verdict, contradicting the project premise that more evidence helps. `max(confidence)` documented as the R7 fallback |
| 1.3 | **`oracle_cost_tokens` deleted** from the frozen schema (S7.5b, S7.5c, `schemas/incident.py`) | Per S5.5b tokens are measured, never budgeted. The field was a phantom carried in from pre-5.5b text; one ledger, in milliseconds |
| 1.3 | Dual baseline: omniscient oracle **and** achievable A1; the gap named **"the cost of uncertainty"** (S7.5b) | Regret against an omniscient oracle is unachievable for any online policy, so reporting it alone would make an irreducible property look like failure |
| 1.3 | Regret **stratified by ambiguity level** (S7.5b) | Near-zero regret on `clear` is a correctness check; large regret on `deceptive` demonstrates irreducibility |
| 1.3 | Oracle **frozen into the fixture** with `reference_rule_version`; never recomputed at eval time (S7.5b) | Changing the fusion rule would otherwise silently rewrite every historical results table. Same class as R23 |
| 1.3 | **B8 CLOSED**: deceptive constructed in calibrated score space (S7.5a) | The conflict is defined where it is measurable -- detector output -- not in physics, where no cross-modal law exists for synthetic composites |
| 1.3 | **Unresolvable incidents allocated at 7% by exact count** (S7.5a) | Measured: the first generator gave a 0.0% no-oracle rate, leaving escalation precision with no hard cases; a probability draw then swung 0-10% by seed. Now 8.0%/7.3% for every seed, asserted in tests |
| 1.3 | Score bands declared FIXED, with a mandated M1 divergence check (S7.5a) | The mock-to-real swap is one config line but not distribution-preserving; `scripts/compare_score_distributions.py` must run at M1 and be reported either way |
| 1.3 | `allow_empty=False` on the oracle (S7.5b, `harness/reference_rule.py`) | The empty set is not a plan, it is the absence of one. An oracle that may decline to investigate is not comparable to a system that must decide what to investigate, and asymmetric cost means acting on zero evidence is wrong even when it is right |
| **1.4** | **`is_unresolvable` added to the incident record**, distinct from `ambiguity_level` (schema 1.2, S7.5a) | Collapsing them confounded two behaviours: escalating on an unresolvable incident is correct, escalating on a merely deceptive one may be a failure. Escalation precision would have rewarded giving up on hard cases |
| 1.4 | Schema validator asserts construction intent matches the reference rule outcome | Keeping both fields is only worthwhile if a divergence fails loudly rather than shifting escalation numbers quietly |
| 1.4 | **M1 divergence-check failure branch decided in advance** (S7.5a) | "Report it either way" was not a plan; the action now depends on when the failure is found, and the limitation paragraph is pre-drafted |
| 1.4 | Declared cost documented as a **model parameter**, not a measurement (S5.5a) | Measured PaDiM latency differs between dev CPU and eval GPU; without the distinction a reader would see cost fall and think the budget moved |
| 1.4 | **Pre-commit hook** blocking dataset bytes and secrets (`scripts/pre-commit`, R17) | R17 nearly fired twice from unpredicted paths, caught only by manual audit. Habits degrade under deadline pressure; this converts discipline into a guarantee |
| 1.4 | PaDiM measured: 33.9 s fit, **161 ms/image**, AUROC 0.930 (S8.2) | Validates `DECLARED_COST_MS[VISION]` of 200 ms, set before measurement. Closes R12 |
| **1.5** | **Budget table recalibrated to 900/600/250 ms** (S5.5a, `core/config.py`) | The v1.1 placeholders made the budget INERT -- all five sources cost 1,050 ms against a 1,500 ms floor, so admission control was dead code and the project's central claim was untestable |
| 1.5 | Five terminal reasons, adding **`no_affordable_source`** and `steps_exhausted` (S5.5a) | Stranded budget is not exhaustion: one wants a bigger budget, the other a cheaper source. Conflating them corrupts the decision log |
| 1.5 | A rejected admission **consumes an evidence step** (S5.5a) | Planning is not free; termination then falls out of the existing bound instead of needing a new counter |
| 1.5 | Parallel admission all-or-nothing, with **availability logged apart from choice** (S5.5a) | "Prefers sequential under pressure" is orchestrator behaviour OR admission mechanism, and logging only the choice makes them unrecoverable |
| 1.5 | **Fast path uses the same budget, no exception** (S5.5a) | Its cheapness must be emergent, or cross-path cost comparisons measure different things. v1.4 was silent on the path that handles most incidents |
| 1.5 | `scripts/check_setup.py` verifies `core.hooksPath` is set | README instructions get skimmed, and the hook is per-clone config git does not distribute -- two of three clones could silently lack it |
| 1.5 | `low` declared a **cheap-investigation** tier, not a no-investigation tier (S5.5a) | It affords telemetry, vision, and the pair at exactly 250 ms. The two policies give very different results tables and the name implies the first |
| 1.5 | Budget tiers **frozen as `budget-v1`** before any eval run (S5.5a) | Tuning tiers to make admission fire is necessary; tuning them after seeing results is circular. A version string makes the difference auditable |
| 1.5 | Duplicate source requests **counted** though they cost nothing (`core/budget.py`) | A free no-op is invisible: a critic re-requesting sources constantly would look like normal operation. Non-zero is a critic bug, not a budget event |
| 1.5 | **Severity-distribution degeneracy check** added (`eval/severity_health.py`, S12.1) | With binding tiers, triage is load-bearing on the headline result. A 95%-`standard` classifier would make the tier system decorative while every mechanism test still passed |
| **1.6** | **`INCIDENT_SPACING_HOURS` 1 -> 6**, harness 1.1 (S7.5, `harness/synthetic.py`) | At 1 hour, 150 incidents spanned 6 days and the memory-recency rule fired on **86.7%** of incidents -- a constant, not a condition. A3 would have measured nothing. At 6 hours the span is 37 days and the S10.3 rules fire at 26.0% and 2.0% |
| 1.6 | **Verdict-to-tier mapping specified with arithmetic first** (S11.1a) | Confidence alone put Tier 3 at 20.0%; the memory gate as originally worded filtered it only to 18.7%. Adopted rule (>=2 confirmed faults in 3 days) gives 2.0% |
| 1.6 | **Demo split hand-CONSTRUCTED**, 12 incidents (S7.7, `harness/demo_builder.py`) | The sampled 8-incident split could never trigger Scenario D. Test must be representative, demo must be complete, and sampling achieves only the first |
| 1.6 | `eval/split_guard.py` refuses to aggregate over constructed incidents | Non-representative by design; it would poison any results table it reached |
| 1.6 | **Recurring-pattern lesson promoted to report S12.1** (S20.1) | Three occurrences of one failure -- thresholds in unmeasured units -- is a methodological finding, not three anecdotes |
| **1.7** | **Scenario F named** in S3.2: correlated sensor failure | Found while building the demo split, not designed. It is the honest limit of the whole method -- cross-modal corroboration fails when the modalities fail together -- and saying it ourselves is far better than an examiner saying it |
| 1.7 | S20.1 extended to **four occurrences** plus the base-rate corollary | The memory-recency rule at 86.7% is the most consequential instance: A3 would have produced a confident null result. Also records the two DIRECTIONS of the failure (inert vs degenerate) and that a count threshold must be checked against the base rate, not only the window |
| 1.7 | **Memory rules measured and frozen as `memrules-v1`** (S10.3, `memory/base.py`) | 26.0% / 2.0% / 2.0%, mutually disjoint (union exactly 45). A3 ablates three separable mechanisms |
| 1.7 | `lower_threshold` window set to **2 days, not 3**, deliberately | At 3 days the Tier 3 incidents become a strict subset of it and A3 cannot attribute effects separately |
| 1.7 | Memory store takes a mandatory `as_of` and bounds queries strictly below it | Replaying an eval set would otherwise let an incident see its own future and inflate every memory effect |
| 1.7 | **`memory/clock.py`: `as_of` may only be derived from the incident record**, asserted per incident | The bound is only as good as its input. Wall-clock would satisfy it and be useless, placing every past incident inside every window -- silently, without raising, producing better numbers |
| 1.7 | `CONFIRMED_FAULT_WINDOW` documented as an **experimental-design choice** (S10.3) | "Why 2 days and not 3" has a real answer about attribution in A3, which is a better exchange than a parameter defence |
| 1.7 | **S20.2 added**: what dual implementations actually bought | The SQLite/in-memory idempotency divergence is the concrete payoff, and worth more than an abstract modularity claim. Cost stated alongside the catch |
| 1.7 | **`before_tool_callback` VERIFIED to block, not observe** (S11.2a) | The highest-stakes unverified assertion in the PRD: a guardrail that logs without blocking is a false safety claim. Tested by side-effect absence, not callback firing. Also records that the agent receives the block as a tool response and stops, rather than retrying around it |

---

## 0. TL;DR

We are building an agentic incident-response system for industrial equipment monitoring. The system does not run a fixed pipeline. An orchestrator decides at runtime **how much evidence to gather, from which modality, and in what order**, under an explicit latency and token budget, then reflects on whether the evidence is sufficient before acting.

The computer-vision and audio components are commodity. We use pretrained, off-the-shelf detectors and never train a novel model. **All project novelty is architectural: runtime-adaptive, evidence-driven, budget-aware orchestration across three modalities.**

**Feasibility verdict:** High. ~85% confidence of full delivery, ~98% confidence of a passing deliverable, given the descope ladder in Section 18.

**Total cost:** Zero. Verified.

---

## 1. Problem Statement

### 1.1 The real-world gap

Industrial facilities monitor equipment using either acoustic or visual anomaly detection, usually independently and usually with fixed thresholds. Single-modality evidence is frequently ambiguous. An unusual sound may be a door slamming or a bearing beginning to fail. A visual artifact may be a lighting change or a genuine defect. A static rule-based system cannot resolve that ambiguity, so it must either raise a false alarm or miss a real fault.

### 1.2 What is actually missing

The missing capability is not better detection. Detection is a solved benchmark problem. The missing capability is **an autonomous decision process that knows when it does not know enough, and can decide what additional evidence is worth the cost of gathering.**

### 1.3 Reframed project question

> Given an ambiguous industrial sensor event, how should an autonomous system decide *how much* evidence to gather, *from whom*, and *in what order*, subject to a latency and cost budget, before committing to an action?

This framing moves the contribution from detection accuracy (where we would be reproducing known results) to orchestration quality (where we can produce genuinely new measurements). It also directly addresses the faculty feedback that the project must be more multi-agent and more orchestration-oriented.

### 1.4 Honest novelty statement for the report

> The individual detection tasks in this project are well-covered in the literature and we deliberately reuse published baselines. Our contribution is systems-level: a runtime-adaptive, budget-constrained orchestration policy over heterogeneous evidence sources, together with an evaluation methodology that measures orchestration quality rather than detection quality alone. We do not claim a new detection algorithm.

Write this verbatim in the report. Overclaiming is the fastest way to lose marks in a viva.

---

## 2. Goals, Non-Goals, and Success Criteria

### 2.1 Goals

| ID | Goal |
|----|------|
| G1 | Build a multi-agent system with **6 agents that each make genuine autonomous decisions**, plus a tool layer (3 detector tools over MCP, 1 guardrail callback). Count honestly per S4.1; do not pad the roster. |
| G2 | Demonstrate three structurally different workflow paths chosen at runtime by evidence, not by configuration |
| G3 | Implement transient vs persistent memory with measurable effect on decisions |
| G4 | Implement reflection: the system can decide its own evidence is insufficient and gather more |
| G5 | Enforce guardrails via callbacks, including human-in-the-loop for high-impact actions |
| G6 | Expose detectors over MCP and the dispatch service over A2A |
| G7 | Produce an evaluation with ablations comparing adaptive vs static orchestration |
| G8 | Run the high-volume agents (triage, memory, dispatch) on a local LLM for privacy-preserving operation |
| G9 | Full observability: every run traced, inspectable, and replayable |

### 2.2 Non-goals

We explicitly do not:

- Train any novel detection model
- Claim state-of-the-art detection accuracy
- Build a production-grade deployment
- Handle real-time streaming at industrial throughput
- Use real factory data or partner with an industrial site
- Build a polished consumer UI beyond a demo dashboard

Stating non-goals in the report protects you. It prevents an examiner assuming you tried and failed at something you never attempted.

### 2.3 Success criteria mapped to the course rubric

| Rubric criterion | How we satisfy it | Evidence artifact |
|---|---|---|
| C1 Problem Definition | Section 1 of this PRD | Project charter |
| C2 Objectives and Outcomes | Section 2 | Project charter |
| C3 Methodology | Sections 5 to 12 | PRD + architecture diagram |
| C4 Feasibility and Resource Planning | Sections 7, 14, 18 | This document |
| C5 Individual Understanding | Section 17 rotation plan | Per-member design notes |
| C6 Progress vs Plan | Section 16 milestones | Burn-down against this PRD |
| C7 Technical Understanding | Custom trajectory metric, guardrail callbacks | Code + viva |
| C8 Problem Solving | Section 18 risk register with realised mitigations | Progress report |
| C9 Documentation | This PRD, DATA.md, ARCHITECTURE.md, EVAL.md | Repo |
| C10 / C15 Individual Contribution | Rotation matrix, per-member commit history | Contribution matrix |
| C11 Final Product | Running system + demo | Live demo |
| C12 Technical Depth | ADK 2.0 graph workflows, MCP, A2A, custom eval metric | Report Section on methods |
| C13 Innovation / Application | Budget-aware adaptive orchestration | Report novelty section |
| C14 Presentation | Final PPT + traces | Deck |

### 2.4 Definition of done

The project is done when a single command replays a held-out incident set end-to-end, produces a results table with all five ablations, and the trace viewer shows three visibly different execution graphs for three different incident types.

---

## 3. Users and Scenarios

### 3.1 Primary user

A plant maintenance supervisor who receives alerts and must decide whether to dispatch a technician, schedule inspection, or dismiss.

### 3.2 Core scenarios

**Scenario A: Unambiguous fault (fast path)**
A pump emits a clearly anomalous acoustic signature at high confidence. The system should not waste time and tokens corroborating. It should act in one hop.

**Scenario B: Ambiguous single-modality signal (parallel fan-out)**
A fan produces a borderline acoustic reading. The orchestrator concludes it cannot decide, fires the audio, vision, and telemetry detector tools concurrently, and joins the results.

**Scenario C: Weak signals across all modalities (escalation loop)**
Nothing is decisive. The orchestrator gathers one evidence source at a time, checking after each whether it has crossed the confidence threshold, until it either resolves or exhausts its budget and escalates to a human.

**Scenario D: High-impact recommended action (guardrail)**
The system concludes the correct action is to halt a production line. The guardrail agent blocks the tool call and requires human confirmation before dispatch.

**Scenario E: Repeat offender (memory)**
A zone that produced four false alarms last month generates another borderline reading. The memory agent surfaces that history and the orchestrator lowers its escalation priority.

**Scenario F: correlated sensor failure (the honest limit of this approach)**
Every modality reads normal on a machine that is genuinely faulty -- or every
modality reads anomalous on one that is fine. No subset of evidence resolves the
incident, because cross-modal corroboration only works when the modalities fail
*independently*. The correct behaviour is to decline: "I cannot determine this,
escalate to a human."

**This scenario is the limit of the whole method and we state it ourselves.** The
premise of multi-modal corroboration is that independent sensors are unlikely to
be wrong together; when that assumption fails, more evidence cannot help and a
confident answer is wrong even when it happens to be right. Constructed
deliberately at ~7% of incidents (S7.5a) and it is the ground truth for escalation
precision (S12.1).

It was found rather than designed: while building the demo split we discovered that
an intended Scenario E false alarm had all three sources reading anomalous on a
normal incident, making it unresolvable rather than merely wrong. Separating the
two cases is what made both measurable.

Scenarios A, B, C, and E are your demo script. Scenario D is your safety story.
Scenario F is your limitations slide. Rehearse all six.

---

## 4. Architectural Principles

These are non-negotiable design rules. Violating them is how the project drifts back into being a CV pipeline with agent branding.

1. **A component is an agent only if it decides something or holds state.** Everything else is a tool. Count honestly in the report.
2. **The orchestrator never sees raw sensor data.** It sees structured evidence reports with confidence values and costs. This keeps the orchestration logic modality-agnostic and testable.
3. **Every evidence-gathering call has a declared cost.** Latency in milliseconds and tokens. The orchestrator spends from a budget.
4. **Detectors are behind MCP, not imported.** This forces a clean contract and hits a syllabus topic.
5. **The static pipeline is never deleted.** It is the fallback demo and the evaluation baseline. It lives in the repo permanently.
6. **Every decision is logged with its reason.** No unexplainable branch.
7. **Determinism where possible.** Fixed seeds, cached LLM responses, replayable runs. Non-determinism in the evaluation is a grading liability.

---

## 5. System Architecture

### 5.1 Agent roster

Section 4.1 says a component is an agent only if it decides something or holds state. We apply that
strictly and report **6 agents**, not 9. Inflating the count is the first thing an examiner will probe,
and Section 4.1 is the stick we handed them. A confident 6 beats a defensive 9.

**Agents (decide or hold state):**

| # | Agent | LLM? | Decides what | Holds state |
|---|---|---|---|---|
| 1 | Triage agent | Local | Investigate, drop, or escalate immediately | No |
| 2 | Orchestrator / planner | Gemini Flash | Which path, which evidence, in what order, what budget | Yes (plan, budget ledger) |
| 3 | Memory agent | Local | Which history is relevant to this machine and symptom | Yes (persistent) |
| 4 | Diagnostic RAG agent | Gemini Flash | Which manual sections to retrieve, what root cause fits | No |
| 5 | Critic / reflection agent | Gemini Flash | Is the evidence sufficient, or gather more | Yes (iteration count) |
| 6 | Dispatch agent (remote, A2A) | Local | Which work-order template, what priority | Yes (ticket log) |

**Not agents, and described as such in the report:**

| Component | What it actually is | Why not an agent |
|---|---|---|
| Audio analyst | MCP tool wrapping PaDiM on mel-spectrograms | Deterministic scorer; decides nothing, holds nothing |
| Vision analyst | MCP tool wrapping PaDiM | Same |
| Telemetry analyst | MCP tool wrapping IsolationForest | Same |
| Safety guardrail | `before_tool_callback` + rule engine | Pure policy function over a tool call |

**Cut in v1.1:** the post-incident reviewer (formerly agent 11). It was descope tier 1, fed no metric in
Section 12, and its write-back duty is absorbed by the dispatch agent committing the incident row.

**Report wording:** "The system comprises six agents by our stated definition, plus three deterministic
detector tools exposed over MCP and one rule-based guardrail callback. We deliberately do not count
tools or callbacks as agents."

An earlier draft of this PRD listed 11 components and claimed 9 agents. That claim is withdrawn.

#### 5.1a Why the fan-out is over tools, not agents (report rationale)

**This is the first thing an examiner will probe**, because "you removed agents from a multi-agent
project" looks like a retreat. It is not. Write this argument into the report verbatim; it is a
strength, not a concession.

**The argument.** Wrapping a deterministic detector in an LLM adds cost and non-determinism for zero
decision value. PaDiM returns a distance; IsolationForest returns a score. Neither has a judgement to
make. An LLM wrapper around either would:

| Cost of wrapping | Consequence |
|---|---|
| Tokens and latency per call | Pure overhead, charged against the very budget the project is about conserving |
| Non-determinism in a scoring path | Corrupts calibration (S8.4) and makes the oracle (S7.5b) non-reproducible |
| A hallucination surface on a number | An LLM can restate 0.83 as "roughly 0.9", and the guard bands are defined to two decimals |
| One more thing to explain in the viva | For a component that decides nothing |

An agent that only reformats a float into a sentence is **decoration**, and S4.1 exists precisely to
stop us shipping decoration with an agent label on it.

**Where the multi-agent character actually lives.** In the decision chain, which is unbroken and fully
agentic:

```
triage ──▶ orchestrator ──▶ critic ──▶ guardrail ──▶ dispatch (remote, over A2A)
  │             │             │           │              │
severity    which path,    is this     block or      which work
class       which         enough       allow or      order, what
            sources,      evidence?    escalate      priority
            what budget
```

Every link in that chain makes a judgement that cannot be reduced to a threshold, and two of them hold
state across the incident. The detectors hang off the orchestrator as instruments it chooses to read.

**The one-line viva answer:** "The agents are the things that decide. The detectors are the instruments
they decide to consult. We fan out over instruments, not over opinions — putting a language model in
front of a distance metric would cost tokens and add non-determinism to buy nothing."

**Corollary worth stating in the report:** this is also *why* our token costs are defensible. A system
that wraps every sensor in an LLM would show larger orchestration overhead and would make the S12.1
cost attribution meaningless.

### 5.2 LLM assignment strategy

This is driven entirely by free-tier quota (see Section 7.4).

- **Local via Ollama:** triage, memory, dispatch. High call volume, low reasoning complexity, mostly structured output.
- **Gemini Flash:** orchestrator, critic, diagnostic RAG. Low call volume, high reasoning complexity.
- **No LLM at all:** the three detector tools and the guardrail. Scoring a spectrogram does not need a
  language model, and pretending it does would be the single easiest thing for an examiner to dismantle.

Per incident that means roughly 2 to 4 Gemini calls and 2 to 4 local calls. This is lower than the v1.0
estimate precisely because the analysts stopped being LLM agents, which also relieves R2 and R6.

### 5.3 Architecture layers

```
Layer 0  Scenario harness        Emits synchronised multi-modal events
Layer 1  Ingestion               Triage agent
Layer 2  Orchestration           Planner, critic, budget accounting
Layer 3  Evidence                3 detector tools + 2 lookup tools behind one MCP server
Layer 4  Safety                  Guardrail callbacks, HITL pause/resume
Layer 5  Action                  Dispatch service over A2A
Layer 6  Observability           Phoenix traces, structured decision log
```

### 5.4 Evidence report contract

Every analyst agent returns exactly this structure. Fixing this early is the single highest-leverage decision in the project because it decouples all the workstreams.

```json
{
  "source": "audio | vision | telemetry | memory | manual",
  "machine_id": "zone_a_pump_01",
  "verdict": "normal | anomalous | inconclusive",
  "confidence": 0.0,
  "score_raw": 0.0,
  "evidence_summary": "one sentence, natural language",
  "supporting_detail": {},
  "cost_ms": 0,
  "cost_tokens": 0,
  "timestamp": "ISO8601"
}
```

Freeze this schema in week 1 and version it. Every team member codes against it independently.

### 5.5 Orchestrator decision policy

The orchestrator is an LLM agent, but it operates inside a hard-coded budget envelope so that its decisions are bounded and auditable.

**Inputs:** triggering evidence report, machine history summary, remaining budget (ms and tokens), list of available evidence sources with their declared costs.

**Output:**
```json
{
  "path": "fast | parallel | sequential",
  "sources_to_query": ["vision", "telemetry"],
  "reason": "audio confidence 0.58 is within the ambiguous band; vision is cheap and historically discriminative for this machine type",
  "budget_allocated_ms": 4000,
  "max_reflection_loops": 2
}
```

**Guard bands (tunable, declare them in the report):**
- confidence >= 0.85 or <= 0.15 → fast path
- 0.15 < confidence < 0.85 and budget is ample → parallel fan-out
- ambiguous band and budget is tight → sequential escalation loop

The orchestrator may deviate from the guard bands when memory provides a reason. Log every deviation. Deviations are your most interesting result.

### 5.5a Budget accounting (specification)

v1.0 asserted that the orchestrator "spends from a budget" and never said how. This is the core
mechanism of the project, so it is specified here in full. All of it is enforced in code, never in a
prompt.

**Two ledgers, not one.** Latency and tokens do not compose the same way, and a single budget number
cannot represent both. Parallel fan-out spends three token costs but elapses one latency.

| Ledger | Composition rule | Why |
|---|---|---|
| `tokens_spent` | **Sum** over every call made, always | Every token is billed whether or not calls overlapped |
| `latency_ms_spent` | **Max** over calls in a parallel group, **sum** across sequential steps | Wall-clock is what the supervisor waits for |

**Starting budget.** Set per incident by the triage agent, not the orchestrator: an agent must not set
its own spending limit.

**The triage agent emits a severity class, never a budget number.** The class is mapped to a budget by a
static table in config. This split matters and is deliberate:

| Concern | Owner | Why |
|---|---|---|
| "How serious is this?" | Triage LLM | A genuine classification judgement over noisy multi-modal input. This is why triage is an agent. |
| "What may a `critical` incident spend?" | `config/budgets.yaml` | Spending policy. Must be deterministic, auditable, diffable, and identical across every ablation run. |

| Severity class | `budget_ms` | `budget_tokens` |
|---|---|---|
| `critical` | 8,000 | 6,000 |
| `standard` | 4,000 | 3,000 |
| `low` | 1,500 | 1,000 |

**The table lives in config, never in a prompt.** A prompt-supplied budget is unauditable (it can drift
per call), untestable (no assertion can pin it), and silently variable across ablations — which would
make cost comparisons between A1 and A2 meaningless. Triage's output schema is therefore
`{"severity": "critical|standard|low", "reason": "..."}`, validated against that enum before the budget
lookup; an out-of-enum value is a hard failure, not a default.

**These figures are the domain cost model, not wall-clock time.** See S5.5b, which is the load-bearing
distinction: the orchestrator budgets against modelled industrial evidence-acquisition cost, not
against LLM inference latency. Calibrate these numbers at M2 from measured detector inference times,
then freeze before M7 and report both the initial and final values.

### 5.5b Domain cost vs system overhead (resolves the CPU-latency contradiction)

v1.1 implied a single latency ledger covering everything, and measurement on the dev hardware exposed
that as a category error: one `qwen3:4b` tool call took **82.5 s** against an 8,000 ms `critical`
budget -- roughly 10x the entire incident budget, for one call.

The mistake was not the budget figure. It was budgeting the wrong quantity.

**What the budget actually models.** The cost of acquiring evidence in a plant: repositioning a camera,
opening a microphone capture window, running a detector inference pass. The LLM is the reasoning
substrate deciding *about* those costs. It is scaffolding, not the modelled process. A plant supervisor
waits on the sensor, not on our choice of local model.

Two quantities, tracked separately and never summed:

| | **Domain cost** | **System overhead** |
|---|---|---|
| What it is | Modelled industrial evidence-acquisition cost | Wall-clock cost of running our agents |
| Contains | Detector inference (measured PaDiM / IsolationForest) + declared sensor acquisition cost | LLM latency, tokens, orchestrator call count |
| Budgeted? | **Yes** -- this is what S5.5a's ledgers debit | **No, never** |
| Reported? | Yes, as the efficiency result | Yes, separately, as the cost of the architecture |
| Hardware-dependent? | Only via detector inference, which is stable | Heavily -- CPU vs GPU is a 10x swing |

PaDiM inference is genuinely in the 50-200 ms range, so an 8,000 ms budget remains a meaningful
constraint that the orchestrator can actually exhaust. The guard bands stay interpretable.

**This also completes the R8 guard** (S12.1), which already required orchestration overhead to be
measured apart from evidence cost. One mechanism resolves both: `evidence_cost` is domain cost,
`orchestration_overhead` is system overhead. Two problems, one split.

**Report sentence, verbatim:**

> The orchestrator reasons over a domain cost model parameterised from measured detector latencies. LLM
> inference latency is system overhead and is reported separately rather than budgeted, since it
> represents the reasoning substrate rather than the modelled industrial process.

This is standard practice for simulation-based systems work and it survives a viva. **Hiding an 82.5 s
call inside a claimed 8 s budget would not**, and an examiner who asked "how long did that incident
actually take?" would find it immediately.

**Measured on the dev machine, 13 September 2026** (Ryzen 5 5500U, 15.3 GB RAM, no discrete GPU,
`torch 2.14.0+cpu`) -- these are system-overhead numbers, recorded so the report can state the
substrate honestly:

| Measurement | Wall clock |
|---|---|
| `gemma3:4b`, 3-token reply, cold load | 24.3 s |
| `qwen3:4b`, one full ADK tool-call round trip | 82.5 s |

**Viva answer:** "The LLM decides how serious the incident is. Code decides what that seriousness is
allowed to cost. We never let a language model pick its own spending limit."

**Declared vs measured cost.** Each evidence source publishes a static `declared_cost` used by the
orchestrator *for planning*, and every call returns its measured `cost_ms`. The orchestrator plans
against declared; the ledger debits measured. Publishing the drift between the two is a free result and
a good viva answer.

**Declared cost is a MODEL PARAMETER, not a measurement, and the results table must say so.** The two
diverge by environment: PaDiM inference measured **161 ms on the dev CPU** and will be substantially
faster on the Colab T4 used for eval runs (R22). The declared 200 ms does not change when the hardware
does.

The R23 environment stamp must therefore distinguish three quantities explicitly, or a reader will see
a measured cost fall and conclude the budget moved:

| Quantity | Changes with hardware? | Where it appears |
|---|---|---|
| `declared_cost_ms` | **No.** Fixed parameter of the simulated plant | Config; the orchestrator planning input |
| measured `cost_ms` | **Yes** | Every evidence report; the debited ledger |
| `budget_ms` | **No.** Derived from severity via the static table | `decisions.jsonl` |

Label EVAL.md columns as *declared (model)* and *measured (observed, ENV)*. The budget is defined over
the model, so guard bands and the oracle stay stable across environments even when observed latency does
not -- which is what makes cross-environment results comparable at all.

**Admission control, not interruption.** A call is admitted only if the declared cost fits the
remaining budget; an in-flight call is never killed. For a parallel group, admission tests the summed
token cost and the max latency cost of the whole group. Consequence: **the budget can be overspent by
at most one group's declared-vs-measured drift, and never more.** State that bound in the report.

**Overspend behaviour.** On exhaustion the orchestrator may not query further sources. It must decide
on the evidence held, or escalate to a human. Running out of budget is a legitimate, logged outcome,
not an error.

**Recorded per incident** in `decisions.jsonl`: starting budget, every debit with its source, the
remaining balance at each decision, and the terminal reason.

##### The four cases v1.4 left unspecified, now decided

v1.4 described escalation and parallel admission and was silent on everything
else. Implemented in `core/budget.py`, each decision documented at its point of
enforcement and covered by a test.

**Decision 1 -- admission rejection with budget remaining is NOT exhaustion.**
There are **five** terminal reasons, not three:

| Reason | Meaning |
|---|---|
| `resolved` | The critic accepted the evidence. Wins over every exhaustion reason |
| `budget_exhausted` | Spend reached the limit; nothing was affordable at any price |
| `no_affordable_source` | **Budget REMAINS, but every ungathered source costs more than what is left** |
| `steps_exhausted` | Hit `max_evidence_steps`, independently of cost |
| `escalated` | Handed to a human |

`no_affordable_source` is distinct because the remedy differs: exhaustion wants a
bigger budget, a stranded balance wants a cheaper source. Conflating them would
corrupt the one artifact whose entire purpose is explaining why the system
stopped.

**Decision 2 -- a rejected admission consumes an evidence step.** Planning is not
free, and this makes the termination guarantee fall out of the existing
`max_evidence_steps` bound rather than needing a second counter: a system that
keeps proposing unaffordable groups terminates on `steps_exhausted` instead of
spinning. One exception, and it is deliberate: re-requesting an
already-gathered source (forbidden by S11.3) does **not** consume a step, because
that is a critic logic error rather than a budget event, and charging a step
would hide the bug behind a plausible-looking termination.

**Decision 3 -- parallel admission is all-or-nothing, and availability is logged
separately from choice.** A group that does not fit is rejected whole; the caller
may re-plan something smaller at the cost of another step.

The instrumentation matters more than the rule. "The orchestrator prefers
sequential under budget pressure" reads as an adaptive finding but could be pure
admission-control artifact, and if only the *choice* is logged the two are
unrecoverable. So `assess_paths()` records, at **every** path decision and without
consuming a step, whether each path was available. Two rates are then reportable:

| Reported rate | What it is |
|---|---|
| Parallel **chosen when available** | Orchestrator **behaviour** |
| Parallel **unavailable by admission** | **Mechanism** |

A large second number is itself a finding worth a paragraph: under budget
pressure the design structurally forces sequential investigation.

**Decision 4 -- the fast path draws from the same budget, with no exception.**
Its cheapness must be an *emergent property* of querying one source, never a
special case in the accounting. Otherwise cross-path cost comparisons are not
measuring the same thing, and the fast path -- which will handle most incidents --
would sit outside the cost model entirely. A fast-path request consumes a step
and debits measured cost exactly like any other.

##### The budget table was inert, and measurement found it

The v1.1 figures (8,000 / 4,000 / 1,500 ms) were placeholders written before any
cost existed. Once PaDiM was measured, arithmetic showed they made the budget
**unable to bind at all**: querying *every* source costs 1,050 ms, so even the
tightest tier had 1.4x headroom over the absolute worst case.

Admission control could never reject anything, `budget_exhausted` could never
fire, `no_affordable_source` was unreachable, and **"budget-aware orchestration"
-- the project's central claim -- was untestable.** An examiner asking to see one
incident where the budget changed the decision would have had nothing to show.

Recalibrated so each tier forbids something different:

| Tier | `budget_ms` | Parallel trio (350) | Sequential trio (600) | All five (1,050) |
|---|---|---|---|---|
| `critical` | 900 | fits | fits | **rejected** |
| `standard` | 600 | fits | fits exactly | rejected |
| `low` | 250 | **rejected** | rejected | rejected |

`low` is therefore the tier where admission control forces sequential
investigation and the parallel path becomes structurally unavailable -- which is
precisely the mechanism decision 3 instruments. `standard` binds exactly at the
sequential trio, making exhaustion reachable on a fourth source. `critical` is
generous but still refuses the exhaustive sweep, so **no tier permits everything**,
asserted per-severity in `tests/test_budget.py`.

**`low` is a cheap-investigation tier, not a no-investigation tier.** Decided
deliberately, because the two produce very different results tables and the
tier name implies the first. At 250 ms it affords telemetry (50), vision (200),
and the pair at exactly 250, rejecting only audio (350) and manual (400). A
low-severity incident therefore gathers two of three sensors and reaches a real
verdict; it does **not** terminate with zero evidence. A no-investigation tier
would need a budget below 50 ms and a different name.

##### How to state the recalibration honestly in the report

Tuning tiers until admission control fires is necessary, and it is one step away
from tuning parameters until the results look good. The distinction must be made
explicitly, so use this wording:

> Budget tiers were calibrated against measured detector latencies so that each
> severity class admits a distinct subset of evidence-gathering plans. Tiers
> chosen such that no plan is ever rejected would render admission control inert;
> tiers chosen post-hoc to produce a favourable result would be circular. We fix
> tiers before running any evaluation and report them as a design parameter.

**Frozen as `budget-v1` on 14 September 2026, before any evaluation run.**
`BUDGET_TABLE_VERSION` is stamped into every results table beside
`reference_rule_version`. Any later change is a documented amendment with a
version bump -- the same discipline as the fusion rule. **If the tiers move after
results exist, the finding is worthless.**

##### The methodological point worth putting in the report

The cost model became falsifiable only once PaDiM produced a real latency. The
placeholder figures were **unfalsifiable by construction**: no measurement existed
that could have contradicted them, so every branch passed its tests while the
mechanism could never fire. What caught it was not a test but arithmetic against
a measured number.

That is a general lesson about this class of system and worth saying out loud: a
threshold expressed in units nobody has measured yet cannot be wrong, and
therefore cannot be right either.

##### Triage is now load-bearing on the headline result

A consequence of tiers that bind: **the severity distribution largely determines
how often admission control fires at all.** If triage labels most incidents
`standard`, admission rarely binds; if it favours `low`, the parallel path is
structurally unavailable for most of the set and mass early termination follows.

So triage classification is an input to the headline result, not a routing
convenience. Two requirements follow:

1. **Log the severity distribution beside every results table**
   (`eval/severity_health.py`). A results table without it cannot be interpreted,
   because the same orchestrator produces very different aggregate costs on
   differently-classified sets.
2. **Sanity-check for degeneracy at M2.** A triage agent labelling 95% of incidents
   `standard` would make the tier system decorative again -- subtler than the inert
   table, because every mechanism would still work and simply never be exercised.
   Flagged when any tier falls below 10% or exceeds 75% of the set.

Deliberately a **report**, not a gate. Forcing a target distribution would mean
tuning triage to produce a convenient spread, which is the same circularity the
frozen tiers avoid.

### 5.6 Three paths, specified

**Fast path**
One evidence source already scored. Skip corroboration. Straight to critic, then guardrail, then dispatch. Target latency under 2 seconds. Target 1 Gemini call.

**Parallel fan-out**
Three detector tools run concurrently. Results joined. Highest latency reduction, highest token cost. Target latency under 5 seconds.

**Sequential escalation loop**
Query one source, evaluate, decide whether to continue. Lowest token cost, highest latency. Ends in
resolution, budget exhaustion, or human escalation.

**Two distinct caps, not to be confused.** v1.0 used "iterations" for both and invited exactly that
confusion:

| Cap | Value | What it bounds | Enforced by |
|---|---|---|---|
| `max_evidence_steps` | 4 | Evidence sources queried inside one sequential path | Loop counter + the source-exhaustion rule (S11.3) |
| `max_reflection_loops` | 2 | Times the critic may send the orchestrator back for more | Separate counter on the critic node |

Four is also the natural ceiling for the first cap, since there are only four queryable sources
(audio, vision, telemetry, manual) and S11.3 forbids re-querying one already gathered.

The comparison between parallel and sequential is a genuine cost/latency tradeoff the planner makes. Measuring that tradeoff is a headline result.

---

## 6. Workflow Implementation

### 6.1 Framework decision: ADK Python 2.0

**Use ADK Python 2.0, not 1.x.** ADK Python 2.0 reached general availability on 19 May 2026. It introduces a Workflow Runtime, a graph-based execution engine supporting routing, fan-out/fan-in, loops, retry, state management, dynamic nodes, human-in-the-loop, and nested workflows, plus a Task API for structured agent-to-agent delegation.

**Withdrawn in v1.1: the syllabus-vocabulary argument.** v1.0 argued that because the syllabus lists
"graph workflows, dynamic workflows, collaborative workflows", the course was written against 2.0. That
inference does not hold. The handout's full topic line is "Graph workflows, dynamic workflows,
collaborative workflows, **and template-based workflows**" — and template-based workflows are 1.x
vocabulary. The handout covers both generations and mandates neither.

The real case for 2.0 is simply that it is current, GA since 19 May 2026, and that its Workflow Runtime
expresses our three paths directly. That case stands on its own and does not need the syllabus prop.

**Critical warnings:**
- 2.0 has breaking changes to the agent API, event model, and session schema versus 1.x.
- Most blog tutorials you will find online are 1.x. Use only the official docs at `google.github.io/adk-docs/2.0/`.
- Pin the exact version in `requirements.txt` on day one and never float it.

### 6.2 Which workflow construct for which path

**Verified API surface (13 Sep 2026, `google-adk==2.9.0`).** Read from the installed package, not from
memory or blog posts. Note the module is `google.adk.workflow`, **singular**:

| Need | Construct | Verified |
|---|---|---|
| Graph container | `Workflow(name=..., edges=[...], max_concurrency=3)` | yes |
| A node | `FunctionNode(func=..., name=...)`; also `Node`, `JoinNode`, `BaseNode` | yes |
| Entry point | `START` sentinel in an edge chain | yes |
| Conditional route | routing dict in a chain: `(node, {"fast": a, "parallel": b})` | yes |
| Emitting a route | `ctx.route = "fast"` inside the node; `DEFAULT_ROUTE` is the fallback arm | yes |
| Parallel fan-out | tuple as a routing value: `{"parallel": (a, b, c)}` triggers all | declared, not yet run |
| Concurrency cap | `max_concurrency` is a first-class `Workflow` field, so **S4 invariant 4 is framework-enforced** | yes |
| Human approval | built-in HITL pause/resume | **NOT yet verified -- M4** |
| Dispatch | remote A2A agent (`to_a2a()` + `RemoteA2aAgent`) | yes, cross-process |

`ctx.route` is what the graph routes on; a node's **return value is ignored for routing**. The
orchestrator's plan object (S5.5) therefore cannot travel by return value: only `path` becomes
`ctx.route`, and the rest of the plan must be written to session state for downstream nodes to read.

| Path | Construct |
|---|---|
| Overall incident flow | Dynamic workflow (Python control flow, `async`/`await`) |
| Parallel fan-out | Routing-map tuple fan-out, joined |
| Sequential escalation | `while` loop inside the dynamic workflow with budget check |
| Human approval | Built-in HITL pause/resume (unverified; see S18.1 R1) |
| Dispatch | Remote A2A agent as a workflow node |

Dynamic workflows in ADK 2.0 track each node execution and automatically skip successful sub-nodes when resuming, which makes complex logic durable and resumable by default. That is free crash resilience for your demo.

### 6.3 Fallback: the ADK 1.x-equivalent design (R1)

v1.0 gave this one line. R1 is now rated High/High (S18.1), and a one-line fallback for the
highest-variance risk in the project is not a plan. The 1.x design is therefore written out here, so
that if pre-flight item 3 fails we execute rather than redesign.

**Gate:** pre-flight item 3 (hello-world graph workflow, two nodes, one conditional route) is an
**architecture gate, to be resolved in the first 48 hours**, not a checklist tick. If it is not green by
15 September, we take this fallback and do not revisit the decision.

**Mapping, 2.0 construct to 1.x equivalent:**

| 2.0 construct | 1.x equivalent | Cost of the swap |
|---|---|---|
| Dynamic workflow (overall flow) | `CustomAgent` implementing `_run_async_impl`, plain Python `async` control flow | None of substance; more boilerplate |
| Graph routing / conditional edges | `if`/`elif` inside `_run_async_impl`, dispatching to sub-agents | Routing logic is in Python, not declarative. Arguably *easier* to explain in a viva. |
| Fan-out with join node | `ParallelAgent` over the three analyst tool calls | None; `ParallelAgent` is mature |
| Sequential escalation loop | `LoopAgent` with `max_iterations=4`, or a `while` in the custom agent | None |
| Built-in HITL pause/resume | Manual: guardrail callback raises, state persisted to SQLite, separate `resume` entry point reads it back | **This is the real loss.** Costs roughly a day and the resumability is ours to maintain. |
| Automatic node-skip on resume | Not available; re-run the incident from the start | Loses "free crash resilience". Acceptable — our incidents take seconds. |
| Task API for A2A delegation | `to_a2a()` / explicit A2A client calls | Minor |

**What we lose:** declarative graph structure, built-in HITL suspend/resume, and automatic resumption.
Everything the *rubric* rewards — three distinct runtime paths, budget-bounded orchestration, reflection,
guardrails, MCP, A2A, custom evaluation — is fully reachable in 1.x.

**What it costs:** roughly half a grade band on C12 Technical Depth, and about two extra days of work
for the manual HITL path. Nothing else in this PRD changes: the evidence contract, the harness, the
oracle, the budget ledger, and the whole of S12 are framework-independent by design.

**Deliberate insulation.** All orchestration logic lives behind our own thin interface
(`workflows/`), and no ADK type appears in `detectors/`, `eval/`, or the harness. That is why this
fallback costs days rather than weeks, and it is the main reason the S4 architectural principles are
worth obeying.

Do not burn a week fighting the framework. Decide by 15 September and move.

## 7. Data Plan

### 7.1 Datasets: verified sources and licences

| Dataset | Modality | Direct link | Licence | Notes |
|---|---|---|---|---|
| MIMII (public 1.0) | Audio | https://zenodo.org/records/3384388 | **CC BY-SA 4.0** | Open download, no gate. NOT NonCommercial. |
| MVTec AD | Vision | https://www.mvtec.com/company/research/datasets/mvtec-ad | CC BY-NC-SA 4.0 | Registration form required |
| MVTec AD mirror | Vision | https://huggingface.co/datasets/Voxel51/mvtec-ad | CC BY-NC-SA 4.0 | Use if the official URL fails |
| AI4I 2020 | Telemetry | https://archive.ics.uci.edu/dataset/601 | CC BY 4.0 | `fetch_ucirepo(id=601)` |

**Correction worth noting:** the original MIMII release is Attribution-ShareAlike, not NonCommercial. The MIMII DG and MIMII DUE variants are CC BY-NC-SA. Use the original.

### 7.2 Dataset facts you will need in the report

**MIMII:** four machine types (valves, pumps, fans, slide rails), four product models each in the public 1.0 release (IDs 00, 02, 04, 06). Every clip is 10 seconds at 16 kHz, 16-bit, recorded with an eight-channel microphone array. Available at three SNR levels: -6, 0, and +6 dB, with real factory noise mixed in. Roughly 14,719 normal and 3,300 abnormal files per SNR condition.

**MVTec AD:** 5,354 high-resolution colour images across 15 categories (5 texture, 10 object), with 3,629 training images (all defect-free) and 1,725 test images.

**AI4I 2020:** 10,000 rows, 14 columns, synthetic but modelled on a real milling machine. Features include air temperature, process temperature, rotational speed, torque, and tool wear. Five labelled failure modes: TWF, HDF, PWF, OSF, RNF. Failure rate is 3.39%, which is severely imbalanced and must be handled.

### 7.3 Download scope: do not pull everything

**Scope cut in v1.1.** The harness is the hidden critical path (S7.5), so we cut its input surface
roughly in half. Three machines, one MIMII machine type, two MVTec categories still exercise every
path and every ambiguity level. More data buys no additional orchestration result.

| Dataset | What to take (v1.1) | Approx size | v1.0 said |
|---|---|---|---|
| MIMII | One SNR level (+6 dB), **one machine type (fan)**, all four model IDs | ~2.5 GB | two types, ~5 GB |
| MVTec AD | **Two categories only** (`metal_nut`, `screw`) | ~1 GB | four categories, ~2 GB |
| AI4I 2020 | Everything | 500 KB | unchanged |

Taking all of MIMII across all three SNR levels would be tens of GB and gains you nothing.

The four MIMII model IDs (00, 02, 04, 06) are what give us three distinct machines from one machine
type, which is the point: model ID becomes machine identity, so per-machine history in the memory
store is real rather than invented.

### 7.4 Licence compliance and repo hygiene

The handout mandates a public GitHub repository. MVTec AD is NonCommercial-ShareAlike. Handle this correctly:

- Add `data/` to `.gitignore` on the very first commit, before any data exists
- Commit `scripts/download_data.sh` instead of data
- Create `DATA.md` listing every dataset, its licence, its URL, and its full citation
- Never commit `.wav`, `.png` from MVTec, or derived spectrograms
- Add a licence note in the README stating the datasets are used for non-commercial academic research

### 7.5 The scenario harness

**Budget one full week. This is the most underestimated *build* item in the project.**

**Revised in v1.2:** v1.0 and v1.1 called this "the hidden critical path". After measuring local
inference (S5.5b), **eval wall-clock (R22) is the critical path** -- roughly 10 hours per ablation run
on CPU, which does not fit the November schedule without moving inference to a free Colab GPU. The
harness remains the largest single build item and still needs its full week; it is no longer the thing
most likely to sink the timeline.

MIMII, MVTec AD, and AI4I have no shared machine identity. There is no real facility where the same pump has audio, images, and telemetry. Without a synthesis layer, "at least two distinct workflow paths taken depending on evidence confidence" is unmeasurable, because you have no ground truth for what the correct path was.

**What the harness does:**

1. Defines a simulated facility with **3 machines across 2 zones** (v1.1; was 6 across 3)
2. Maps each machine to one MIMII model ID, one MVTec category, and one AI4I product type
3. Emits synchronised events: `(audio_clip_path, image_path, telemetry_row, timestamp, machine_id)`
4. Attaches ground truth: `is_anomalous` plus an **ambiguity level**
5. Attaches a **cost-optimal oracle plan** so orchestration quality is measurable as regret (S7.5b)

#### 7.5a Ambiguity construction

`is_anomalous` is the facility-level truth for the incident. Each modality is then sampled to agree or
disagree with it deliberately.

| Level | Construction | Share of set |
|---|---|---|
| Clear-anomalous | All three modalities drawn from their anomalous pools | 20% |
| Clear-normal | All three drawn from normal pools | 20% |
| Borderline | Anomalous in exactly one modality, normal in the other two | 30% |
| Deceptive | See below | 30% |

**"Deceptive" now has a constructive definition, and B8 is CLOSED.**

The original critique (B8) held that this level was **unbuildable**: our machines
are synthetic composites of three unrelated datasets, there is no physical law
linking a fan's audio to a metal nut's image, so no rule could say when two
modalities "conflict".

**Constructing directly in calibrated score space dissolves that problem.** We do
not search real clips for a cross-modal conflict that does not exist. We sample
confidences with a specified statistical relationship, then attach real files
whose class (normal or anomalous) matches the sampled sign. The conflict is
defined where it is actually measurable -- in the detector's own output -- rather
than in physics, where it is not. B8 is therefore closed rather than deferred.

Implemented in `harness/synthetic.py`. Bands, in calibrated confidence:

| Band | Range | Role |
|---|---|---|
| `STRONG_ANOMALOUS` | 0.88-0.98 | Above the 0.85 guard band; decisive alone |
| `WEAK_ANOMALOUS` | 0.55-0.75 | Inside the band, leaning anomalous |
| `UNINFORMATIVE` | 0.40-0.60 | Straddles 0.5; contributes ~nothing to fused log-odds |
| `WEAK_NORMAL` | 0.25-0.45 | Inside the band, leaning normal |
| `STRONG_NORMAL` | 0.02-0.12 | Below the 0.15 guard band; decisive alone |

A **deceptive** incident has exactly two sources in the weak bands **disagreeing
in sign** -- one agreeing with ground truth (a hit), one contradicting it (a miss)
-- with the third uninformative. Under the reference rule the pair nearly cancels,
so no single source resolves the incident.

##### Unresolvable incidents: a tuned target, not an accident

A **7% share of all incidents is constructed so that EVERY source contradicts
ground truth**, making `oracle_exists` false. These are where escalation
precision and recall (S12.1) get their teeth: the correct behaviour is "I cannot
determine this, escalate", and a system that answers confidently is wrong even
when it guesses right.

**This was found by measurement, and both attempts failed first:**

1. The initial generator produced a no-oracle rate of **exactly 0.0%**, because
   every construction guaranteed at least one source agreeing with the truth. Our
   most novel metric would have had no hard cases at all, and we would only have
   discovered that after building the eval.
2. The fix, drawn per-incident as `rng.random() < share`, gave realised rates from
   **0.0% to 10.0% across seeds** -- one seed produced a test split with *no*
   unresolvable incidents, leaving escalation precision undefined for that run.

**Allocated as an exact count, never sampled as a probability.** Realised rate is
now 8.0% (dev) and 7.3% (test), identical for every seed, and asserted in
`tests/test_harness_seam.py` so a future generator change cannot drift it back
toward zero. Target band is 5-10%: near zero and the metric measures nothing,
much larger and the ambiguity construction or the calibration is wrong.

These incidents are also physically meaningful rather than contrived: a genuine
early-stage fault that no installed sensor can yet detect is exactly the case
where an honest system must decline to answer.

##### Score distributions are FIXED parameters, not fitted (decision, with a cost)

The bands above are fixed constants chosen before any real detector existed. That
keeps the generator reproducible, hand-checkable, and unblocked by dataset
downloads.

**The honest cost: mock and real detectors will differ in distribution, so the
mock-to-real swap is one line of config but is NOT distribution-preserving.** The
guard bands, the ambiguity construction, and the oracle all live in confidence
space, so an unexamined gap there would quietly invalidate every result built on
mock data. If real PaDiM confidences cluster at 0.99 and 0.01, the "weak
anomalous" band describes nothing that ever happens and the deceptive level stops
being deceptive.

**M1 therefore carries a mandated check**, not an optional one:
`scripts/compare_score_distributions.py` compares real calibrated scores against
these bands, reports per-band occupancy and saturation, and fails if any band
holds under 5% of real scores or if over 25% of scores are saturated. Record the
result in EVAL.md **whether it passes or fails** -- a passed check is evidence.

##### The decision branch if that check fails, decided NOW

"Report it either way" is honest but it is not a plan, and deciding this in
October under time pressure is how a bad choice gets made. The branch is
therefore fixed in advance, keyed on **when** the failure is found:

| Condition | Action | Why |
|---|---|---|
| Fails **before the M2 gate (1 Oct)** | **Refit the bands, bump `HARNESS_VERSION`, regenerate every fixture.** Re-run nothing else | No result depends on the old bands yet; cheapest possible moment |
| Fails **after M2, before M7 eval runs** | **Refit, bump, regenerate, and re-run the static baseline only** | A1 is cheap to re-run and adaptive results do not exist yet |
| Fails **during or after M7** | **Keep the bands. Write the limitation paragraph. Do NOT refit** | Refitting mid-eval invalidates every completed run and cannot finish before 20 Nov. A stated limitation costs a fraction of a grade band; an unfinishable re-run costs the deliverable |
| Fails **for one modality only** | Refit that modality alone; bands are per-source constants | Localised failure, localised fix |

The limitation paragraph, if needed, is already drafted: *Our synthetic score
bands were fixed before detector calibration. At M1 we measured the divergence
between them and real calibrated detector output and found [X]. We did not refit,
because doing so would have invalidated completed evaluation runs inside the
project window. Results should therefore be read as measuring orchestration
behaviour over a score distribution that is realistic in structure but not fitted
in detail.*

That paragraph is worth more than a silent refit: it tells an examiner we measured
the thing and chose knowingly.

#### 7.5b Cost-optimal oracle and regret (replaces "expected path")

v1.0 attached an `expected_path` label to each incident and measured "path selection accuracy" against
it. **That was circular.** The label was assigned by us, by fiat, from the ambiguity level; an
orchestrator that is a three-line `if/else` over the same rule scores 100%, and the metric therefore
measured policy-adherence to our own table rather than decision quality. An examiner would find that,
and it is a bad thing to be found.

**Replacement: the cost-optimal plan under a reference decision rule.**

That phrase is deliberate and belongs in the report verbatim. The oracle was never a lower bound on the
*system*; it is a lower bound on **evidence acquisition given a fixed fusion rule**. Naming that
honestly is what kills the circularity, because the thing being compared is no longer our own path
label.

For each incident, after the detectors are calibrated but before any agent runs, the harness computes
the oracle offline by brute force:

1. Score all four sources (audio, vision, telemetry, manual) once; cache the scores in the record.
2. Enumerate every subset of sources (2^4 = 16, trivially cheap).
3. Mark each subset **sufficient** if the **reference decision rule** (below) applied to that subset
   alone yields the correct `is_anomalous` verdict.
4. Among sufficient subsets, the **oracle set** is the one of minimum `cost_ms`, tie-broken by fewer
   sources, then by lexical order for determinism.
5. Record `oracle_sources`, `oracle_cost_ms`, `oracle_exists`, and `reference_rule_version`.

##### The reference decision rule: sum of log-odds

```
logit(p) = log(p / (1 - p))            with p clamped to [0.01, 0.99]
fused    = sum of logit(p_i) over the queried subset
verdict  = anomalous if fused > 0, else normal
```

This is the Bayes-optimal fusion of calibrated probabilities under conditional independence, and it is
three lines of code.

**Why not mean-of-confidence, which an earlier draft proposed.** The mean lets *weak, uninformative*
evidence overturn a strong signal. Measured on our own implementation:

| Subset | Sum of log-odds | Verdict | Mean | Verdict |
|---|---|---|---|---|
| 0.95 | +2.944 | anomalous | 0.950 | anomalous |
| 0.95, 0.10 | +0.747 | anomalous | 0.525 | anomalous |
| 0.95, 0.10, 0.15 | **-0.987** | normal | **0.400** | normal |
| 0.95, 0.45 | +2.744 | anomalous | 0.700 | anomalous |
| 0.95, 0.45, 0.45 | **+2.543** | anomalous | **0.617** | anomalous |

Read the last row carefully, because it is the whole argument. Two near-uninformative readings at 0.45
consume **77% of the mean's margin** above its 0.5 boundary, while moving the log-odds sum by **1.5%**
of its margin. Under the mean, a third such reading flips the verdict; under log-odds, nothing has
meaningfully happened, which is correct -- a source reporting 0.45 has told us almost nothing.

**Precision about the claim, because the imprecise version is wrong.** Neither rule is monotone, and
log-odds also flips on row 3 (+0.747 to -0.987). That flip is *correct*: two independent sources both
reading normal genuinely should outweigh one anomalous reading. The defensible property is not "never
flips" but **proportionality** -- the fused value moves in proportion to how much the added evidence
actually says, so noise cannot drag a strong signal across the boundary while genuine counter-evidence
still can. An earlier draft of this PRD claimed log-odds was monotone and the mean was not; that claim
is withdrawn as overstated, and the table above is what we defend instead.

**Two caveats, written down now rather than discovered later:**

- **The rule depends on calibration holding, which is R7 and still open.** If the M1 calibration check
  fails, the documented fallback is `max(confidence)` against the guard band. Decide at M1 with the
  calibration numbers in hand, not now. Either way, **record which rule was used** in every incident
  record via `reference_rule_version`.
- **Clamp confidences to [0.01, 0.99] before taking logits.** A single saturated detector reporting
  0.0 or 1.0 has infinite log-odds and would dominate every subset it appears in.

**The critic may sometimes beat the oracle. Report that, do not suppress it.** The oracle is optimal
under a *fixed* rule; an LLM critic reasoning over evidence summaries is not bound by that rule and can
occasionally do better. Those cases are evidence the LLM is contributing something a fixed rule does
not, which is the most interesting negative-space result available to us.

##### One ledger, in milliseconds

There is no `oracle_cost_tokens`. Per S5.5b, tokens are **measured but never budgeted**, so the oracle
optimises a single quantity and the two-ledger ordering ambiguity never arises.

Check this against the least obvious sources. **Memory:** the lookup is a SQLite query, roughly 50 ms,
and that is its domain cost; the LLM reasoning over what it returns is system overhead. **Manual /
RAG:** retrieval is domain cost; generation is overhead. Consistent throughout.

##### Metric: regret against two baselines

```
cost_regret   = actual_cost_ms   - oracle_cost_ms     (>= 0 when the system is correct)
source_regret = |actual_sources| - |oracle_sources|
```

**A single baseline would be misleading**, because the oracle knows `is_anomalous` and the system does
not. On a deceptive incident where one source happens to be right by luck, the oracle is that one
source; a system that queries all three, confirms carefully and gets the right answer is charged large
regret **for behaving correctly under uncertainty**. Bounded regret against an omniscient oracle is
unachievable in principle for any online policy, so reporting it alone would make an irreducible
property look like a failure.

Report both, as is standard in the bandit literature:

| Baseline | Achievable? | What it measures |
|---|---|---|
| Omniscient oracle | **No** | The floor. What perfect foresight would cost |
| A1, static always-query-all | **Yes** | What we actually claim to beat |

**The oracle-to-A1 gap is the cost of uncertainty**, and it is a result rather than a caveat: it is what
perfect foresight would save over exhaustive evidence gathering, and no online policy can capture it.
It quantifies the room between knowing nothing and knowing everything, and A2 sits somewhere inside it.
State it in exactly those terms in the report.

##### Stratify regret by ambiguity level

Same computation, three numbers instead of one, and it answers the obvious hostile question before it
is asked:

| Stratum | Expected | What a violation means |
|---|---|---|
| `clear_*` | Near-zero regret | **A correctness check on the orchestrator.** Non-trivial regret here means it is over-gathering on easy cases, which is a finding |
| `borderline` | Moderate | The interesting middle where adaptivity should pay |
| `deceptive` | Large, for everyone | **The demonstration that the gap is irreducible**, not that our system failed |

##### The oracle is frozen into the fixture, never recomputed

`oracle_sources`, `oracle_cost_ms`, and `reference_rule_version` are computed **once, at harness
generation time**, and stored in the incident record.

**Never recompute the oracle at eval time.** Changing the fusion rule in November would otherwise
silently rewrite every historical results table, and nobody would notice — the same class of failure as
R23, with the same fix: a version string travelling with the data.

**Why this is better viva material.** "We measure how much more evidence the system bought than it
needed to, against a per-incident optimum computed by exhaustive search under a stated fusion rule, and
we report it against both an unachievable floor and an achievable baseline" is a defensible sentence.
"We measure whether it followed our table" is not.

`expected_path` is retained in the record as a **descriptive** field for stratifying results by intended
difficulty. It is no longer a scored target. Say that explicitly in EVAL.md.

#### 7.5c Harness output schema (freeze alongside the evidence contract)

R3's real mitigation is not "allocate a week" — that is an estimate, not a mitigation. It is to freeze
this schema in week 1 so detector work and orchestration work proceed against synthetic harness output
while the real harness is still being built.

```json
{
  "incident_id": "inc_0042",
  "machine_id": "zone_a_fan_02",
  "timestamp": "ISO8601",
  "audio_clip_path": "data/mimii/fan/id_02/abnormal/00000012.wav",
  "image_path": "data/mvtec/metal_nut/test/bent/003.png",
  "telemetry_row": {},
  "is_anomalous": true,
  "ambiguity_level": "clear_anomalous | clear_normal | borderline | deceptive",
  "expected_path": "fast | parallel | sequential",
  "cached_scores": {
    "audio":     {"score_raw": 0.0, "confidence": 0.0},
    "vision":    {"score_raw": 0.0, "confidence": 0.0},
    "telemetry": {"score_raw": 0.0, "confidence": 0.0},
    "manual":    {"score_raw": 0.0, "confidence": 0.0}
  },
  "oracle_exists": true,
  "oracle_sources": ["audio", "telemetry"],
  "oracle_cost_ms": 1400,
  "reference_rule_version": "logodds-v1",
  "split": "dev | test | demo",
  "seed": 0,
  "harness_version": "1.0"
}
```

`harness_version` is mandatory. Regenerating the harness after results exist, without a version bump,
is how a results table silently stops matching its data.

**Ambiguity is manufactured deliberately, and we declare the simulation honestly in the report.** Write:
"Because no public dataset provides time-aligned multi-modal recordings of the same industrial asset, we
construct a synthetic facility that composes three real public datasets into synchronised incident
events. Detector inputs are real; the cross-modal alignment is synthetic. Ambiguity levels are
constructed in calibrated detector-score space. This is a limitation we state explicitly."

An examiner who spots a hidden simulation will punish you. An examiner who reads that you declared it will credit you for rigour.

### 7.6 Maintenance manual corpus for the RAG agent

There is no public corpus of industrial maintenance manuals matching these machines. Options in order of preference:

1. Write 15 to 20 short synthetic fault-cause documents yourself, one per failure mode (TWF, HDF, PWF, OSF, and MIMII anomaly types such as contamination, leakage, rotating unbalance, rail damage). About 200 words each. Two hours of work, fully controllable.
2. Use public equipment maintenance guides from manufacturer websites where licensing permits.

Option 1 is correct for a course project. Say so.

### 7.6a Work-order templates

v1.0 had the dispatch agent choose "which work-order template" while defining no templates anywhere.
Write these alongside the manual corpus; they are the dispatch agent's actual decision space.

| Template | Trigger | Action tier (S11.1) |
|---|---|---|
| `WO-INSPECT` | Anomalous, low confidence or single weak source | 1 |
| `WO-TECH-ROUTINE` | Anomalous, corroborated, no safety implication | 2 |
| `WO-TECH-URGENT` | Anomalous, corroborated, repeat offender or fast-degrading | 2 |
| `WO-HALT-LINE` | Anomalous, high confidence, safety-critical failure mode | **3, blocked pending human approval** |
| `WO-DISMISS` | Normal, or confirmed false-alarm pattern from memory | 0 |

Five templates, one per action tier plus a split at tier 2. `WO-HALT-LINE` is the Scenario D demo.

### 7.7 Eval set sizing

| Split | Incidents | Purpose |
|---|---|---|
| Dev | 50 | Prompt iteration, fast loop |
| Test | 150 | Reported results, frozen |
| Demo | 12 | **Hand-CONSTRUCTED**, not sampled. See below |

150 is deliberate. It is enough for a credible table and small enough to survive Section 7.8.

**The demo split is constructed, not sampled, and that is what a demo split is
for.** The two splits have different jobs and sampling can only do one of them:

| Split | Job | Achievable by sampling? |
|---|---|---|
| `test` | **Representative** -- it produces the reported numbers | Yes, and it must be |
| `demo` | **Complete** -- it must exercise every path, including rare ones | **No** |

Measured: the sampled 8-incident demo split could **never** trigger Scenario D,
because the Tier 3 precondition needs two prior confirmed faults on one machine and
8 incidents round-robined across 3 machines cannot accumulate them. A demo that
cannot show the safety story is a demo of the common case, not of this system.

`harness/demo_builder.py` therefore specifies 12 incidents by hand, each with a
documented purpose, including two deliberately planted precondition chains: three
confirmed faults on one machine for the Tier 3 block, and four false alarms on
another for the memory downgrade. Written to
**`incidents.demo_constructed.jsonl`** -- a distinct filename so it cannot be
mistaken for a sampled split.

**Guard:** `eval/split_guard.assert_reportable()` raises if any results computation
is handed a constructed incident, including a single one smuggled into a real
split. Being non-representative by design, it would poison any aggregate it
reached. Same class of protection as the token-ledger regression test.

### 7.8 The real constraint: LLM quota, not compute

Compute is a non-issue. Quota is the binding constraint.

**Status of these numbers, 13 September 2026: unverified and partly wrong.**

Google no longer publishes free-tier RPM/RPD on its public rate-limit page; the page now says limits
"can be viewed in Google AI Studio" and links to a per-account dashboard. **The figures below are
therefore assumptions, not facts, until someone reads the dashboard with our key.** That is open
question 6 and it gates the whole of this section's arithmetic.

The claim that "Pro models were removed from the free tier in April 2026" is **wrong**: the pricing page
currently lists Gemini 2.5 Pro with a limited free tier. This does not change our architecture (we plan
around Flash regardless) but it is a factual error that an examiner could check, so it is corrected here.

Also note the free-tier Flash lineup has grown well beyond a single "Gemini Flash": 2.5 Flash, 2.5
Flash-Lite, 3 Flash Preview, 3.1/3.5/3.6/3.7/3.8 Flash and Flash-Lite variants all carry free tiers.
**Pin one exact model id** in `requirements`-adjacent config, with the same discipline as a dependency
pin, and record it in the report. "We used Gemini Flash" is not a reproducible statement.

Working assumption until measured: roughly 15 requests per minute and about 1,500 requests per day. Parallel requests and token-heavy prompts are the two patterns that hit these limits fastest, usually before developers expect them to.

**Arithmetic:** 4 Gemini-backed agents x 150 incidents = 600 calls for one eval run. Five ablation configurations = 3,000 calls. That exceeds two full days of quota, and your parallel fan-out will trip 429s on the RPM limit immediately.

**Mandatory mitigations:**

| Mitigation | Effect |
|---|---|
| Local Ollama for the 6 high-volume agents | Removes ~60% of calls |
| Response cache keyed on (prompt hash **+ seed + model id**), on disk, committed as a fixture | Re-running an ablation costs near zero |
| Exponential backoff with jitter on 429 | Survives RPM limits |
| Semaphore capping concurrency at 3 | Prevents fan-out from tripping RPM |
| Eval set at 150, not 500 | Keeps a full run inside one day |
| Run ablations overnight, one per night | Spreads across the RPD ceiling |

The cache is not optional. Without it you cannot iterate.

**Cache key, specified (v1.1).** The key is `sha256(model_id + prompt_text + seed + temperature)`.

v1.0 said "keyed on prompt hash" alone, which silently contradicted S12.4's requirement to run three
seeds and report mean plus standard deviation: with a prompt-only key, runs 2 and 3 are cache hits
returning run 1's bytes, and **the reported standard deviation would be exactly zero** — a number that
looks like a result and is actually an artefact of the cache. That is a viva trap of our own making.

Including the seed makes variance real and triples the quota cost of any varied configuration, which is
why S12.4 now measures variance on A2 only.

**This constraint is also a deliverable.** CO2 requires privacy-preserving local LLMs. Write in the report that quota economics drove a hybrid local/hosted architecture, and measure the quality delta between all-Gemini and hybrid. That is a legitimate experiment.

---

## 8. Detector Specification

### 8.1 The simplification that saves a week

**Do not build a separate audio model.** Convert MIMII clips to mel-spectrogram images and run the same Anomalib model used for vision. Anomaly patterns are frequently visible in mel-spectrograms, making image-based models a reasonable choice for acoustic anomaly detection. This collapses two detector codebases into one.

### 8.2 Model choice

**MEASURED on our own hardware, 14 September 2026** -- PRD v1.0 quoted "9.2 seconds" from a published
benchmark with unstated hardware, which is fine as rationale and dangerous as a pass criterion:

| Measurement | Value |
|---|---|
| PaDiM fit, `metal_nut`, 220 train images | **33.9 s** |
| Test over 115 images | 18.5 s |
| **Per-image inference** | **161 ms** |
| image AUROC | **0.930** |
| image F1 | 0.938 |
| pixel AUROC | 0.946 |
| Hardware | AMD Ryzen 5 5500U, 15.3 GB RAM, **no GPU**, `torch 2.14.0+cpu` |

Two things follow. First, 33.9 s is 3.7x the published 9.2 s, entirely explained by CPU-only execution --
quote our own number in the report, with the hardware, and cite the benchmark only as rationale for
choosing PaDiM over PatchCore. Second, and more important: **161 ms per image validates the domain cost
model.** `DECLARED_COST_MS[VISION]` was set to 200 ms before any measurement existed, and the measured
value sits inside it. The S5.5b budget of 8,000 ms for a `critical` incident is therefore a real
constraint over real detector latencies, not a round number.

AUROC 0.930 also closes R12 (detector accuracy too low for meaningful orchestration): comfortably strong
enough that orchestration differences, not detector noise, will drive the results.

| Detector | Model | Rationale |
|---|---|---|
| Vision | Anomalib PaDiM | Trains in ~34 s on our CPU (9.2 s published, on a GPU) versus PatchCore's 282.8 s, with a pixel AUROC drop of only 0.003 |
| Audio | Anomalib PaDiM on mel-spectrograms | Same pipeline, same code |
| Telemetry | scikit-learn IsolationForest | Trivial on 10k rows |

If PaDiM underperforms, switch to PatchCore. PatchCore requires no backpropagation, using a pretrained backbone plus nearest-neighbour search over a memory bank.

### 8.3 Spectrogram parameters

Use published settings as your starting point: 64 mel bands, frame size 1024, hop 512, then upscale patches to 224x224 and standardise with ImageNet statistics to match the pretrained backbone's domain.

### 8.4 Confidence calibration

Raw anomaly scores from PaDiM are unbounded distances, not probabilities. **The orchestrator's entire decision policy depends on calibrated confidence.** Fit a simple calibration (min-max over the validation set, or Platt scaling) so that confidence is in [0, 1] and roughly means what it says. Document the calibration method. An uncalibrated confidence makes your guard bands meaningless and an examiner will ask.

**The split, specified (v1.1).** v1.0 said "over the validation set" without saying what that set was,
which made R7's mitigation unexecutable and risked leakage into the reported results.

| Split | Drawn from | Used for | Size |
|---|---|---|---|
| `detector_train` | MVTec `train/` (defect-free only); MIMII normal; AI4I non-failure rows | Fitting PaDiM / IsolationForest | Per anomalib defaults |
| `calib` | Held-out normal **and** anomalous files, disjoint from `detector_train` | Fitting the score to confidence mapping, and establishing the percentile bands S7.5a needs | ~200 files per modality |
| `incident_pool` | Everything remaining | Harness draws dev/test/demo incidents from here | Remainder |

**Hard rule: `calib` and `incident_pool` are disjoint at the file level, not the category level.** A
clip used to fit the calibration may never appear in a scored incident. Enforce this with an assertion
in the harness build, not a comment — leakage here would invalidate every confidence number in the
report, and it is invisible unless you test for it.

Calibration is fitted **once**, committed as a small JSON of parameters, and never refitted after M2
without a `harness_version` bump.

---

## 9. Tool Layer: MCP

### 9.1 Design

One MCP server, `incident_detectors`, exposing:

(v1.0 called this `behooked_detectors`, a name carried in from an unrelated project. Renamed.)

| Tool | Input | Output |
|---|---|---|
| `score_audio` | clip path, machine_id | Evidence report |
| `score_image` | image path, machine_id | Evidence report |
| `score_telemetry` | row, machine_id | Evidence report |
| `lookup_history` | machine_id, symptom | List of prior incidents |
| `search_manuals` | query | Retrieved passages |

Build the server with the `mcp` Python package. Building an MCP server in Python requires the model-context-protocol library, while ADK provides the client side.

### 9.2 Connecting from ADK

ADK's `McpToolset` is the primary mechanism. On initialisation it establishes and manages the connection, queries the server via `list_tools`, and converts discovered MCP tool schemas into ADK-compatible `BaseTool` instances.

Use `StdioConnectionParams` for local development (it supports timeouts, unlike bare `StdioServerParameters`), and `StreamableHTTPConnectionParams` or `SseConnectionParams` if you later containerise.

**Unverified and load-bearing: concurrency over stdio.** S5.6's parallel fan-out issues three tool calls
at once, through one MCP server. Stdio is a single pipe. Whether `McpToolset` multiplexes concurrent
calls over one stdio session, or serialises them, is **not something we have verified**, and if it
serialises then our "parallel" path is parallel only on paper — R10 fires for a reason we did not
anticipate, and the headline latency result evaporates.

Pre-flight item 9 therefore tests **two concurrent tool calls**, not merely two tools. If stdio
serialises, switch that toolset to `StreamableHTTPConnectionParams` (the server then runs as a local
HTTP process) before building the parallel path, not after.

### 9.4 A2A wiring gotchas (verified 13 September 2026)

Dispatch over A2A works cross-process: `to_a2a()` served the agent card, a second agent called it via
`RemoteA2aAgent`, and the work order came back over JSONRPC. Three things cost time:

1. **A2A is an optional extra.** `from google.adk.a2a.utils.agent_to_a2a import to_a2a` raises
   `ModuleNotFoundError: No module named 'a2a'` until you install `google-adk[a2a]` (pulls
   `a2a-sdk==1.1.2`). The import exists in the base package; the dependency does not.
2. **Agent-card origin is strictly enforced.** The card advertises `http://localhost:8001`; fetching it
   from `http://127.0.0.1:8001` fails with *"Agent card RPC URL must have the same origin as the
   location the card was fetched from"*. Same machine, same port, different hostname string is enough
   to break it. **Pick one spelling and use it everywhere**, including in config and tests.
3. **ADK's A2A layer self-declares `[EXPERIMENTAL]` and subject to breaking changes.** The A2A protocol
   itself is not experimental; ADK's implementation of it is. This supports keeping dispatch behind our
   own thin interface and keeps R13's "cheapest thing to cut" rating honest.

A response may arrive as more than one event (a streaming chunk plus a final). Understand the event
shape before M6 rather than deduplicating by accident.

### 9.3 Why this is worth doing

It is a named syllabus topic, it forces a clean contract between the ML work and the agent work so two team members can work in parallel, and it makes the detectors swappable for ablations.

---

## 10. Memory Design

The syllabus distinguishes transient versus persistent state. Implement both visibly.

### 10.1 Transient (session state)

Lives for one incident. Held in ADK session state.

Contents: current evidence reports, budget remaining, reflection iteration count, orchestrator plan, path taken.

### 10.2 Persistent (across incidents)

**SQLite only (v1.1).** ChromaDB is dropped. It existed to serve one bullet — surfacing semantically
similar past incidents to the diagnostic agent — while all three of the *measurable* memory effects in
S10.3 are structured queries. One dependency, one embedding model, and one more thing to explain in the
viva, for one bullet, is a bad trade on a ten-week schedule.

| Table | Contents |
|---|---|
| `machines` | machine_id, zone, type, install_date |
| `incidents` | incident_id, machine_id, timestamp, verdict, action, was_false_alarm, evidence_summary |
| `incident_tags` | incident_id, symptom_tag |

Similarity retrieval becomes a `symptom_tag` match plus recency ordering over `incidents`. With 3
machines and a 150-incident test set, exact tag matching is not meaningfully worse than embedding
similarity, and it is fully explainable in a viva. If M6 finishes early, Chroma can return as an
enhancement — but it is not on the critical path and not a Phase-3 requirement.

### 10.3 Memory's measurable effect

The memory agent must change decisions, not just add colour. Concretely:

- A machine with >= 3 false alarms in 30 days gets its escalation priority downgraded
- A machine with a confirmed fault in the last 7 days gets its confidence threshold lowered
- Semantically similar past incidents are surfaced to the diagnostic agent

**The no-memory ablation must show a measurable difference.** If it does not, the memory agent is decoration and you should say so honestly rather than pretend.

---

## 11. Safety and Guardrails

### 11.1 Action tiers

| Tier | Example action | Control |
|---|---|---|
| 0 Informational | Log, notify dashboard | Auto |
| 1 Low impact | Schedule routine inspection | Auto |
| 2 Medium impact | Dispatch technician, raise priority ticket | Auto with audit log |
| 3 High impact | Halt line, shut down machine, emergency callout | **Blocked, requires human approval** |

#### 11.1a Verdict-to-tier mapping, with the arithmetic done first

v1.5 listed tiers and example actions but never said **what maps a verdict to a
tier** -- the same class of gap as "who sets the budget". Left unspecified, Tier 3
risked being inert exactly as the budget table was: every branch tested, mechanism
never exercised, and "show me the system blocking an action" answered with silence.

**Measured before writing any guardrail code** (test split, n=150, harness 1.1):

| Candidate rule | Tier 3 rate | Verdict |
|---|---|---|
| Anomalous AND fused log-odds > 5 | **20.0%** | Far too high. One incident in five halting a production line is not a safety control |
| ...AND any prior anomaly within 7 days | **18.7%** | **The memory gate did nothing.** The 7-day window was wider than the dataset's 6-day span |
| ...AND **>= 2 confirmed faults within 3 days** | **2.0%** (3 incidents) | **ADOPTED** |
| ...AND >= 3 confirmed faults within 7 days | 2.7% (4) | Also viable |

**The adopted rule:**

```
Tier 3 (blocked, requires human approval) iff
    verdict is anomalous
AND fused log-odds > 5.0
AND the machine has >= 2 confirmed faults in the preceding 3 days
```

Three properties worth stating in the report. It is **rare** (2.0%), as a safety
control must be. It **depends on memory**, which gives the memory agent a fourth
measurable effect beyond S10.3's three and strengthens ablation A3. And it is
**auditable**: three conditions, all computable from stored state, none from a
prompt.

**Reporting caution.** Three incidents is a thin denominator. Report the guardrail's
block rate and false-block rate as **raw counts alongside any percentage** -- "3 of
3 Tier 3 actions blocked" is honest, "100% block rate" over n=3 invites a
reasonable objection.

Tiers 0-2 map from verdict and confidence alone: normal or dismissed is Tier 0,
anomalous below the decisive band is Tier 1 (inspection), anomalous above it is
Tier 2 (dispatch). Only Tier 3 consults memory.

### 11.2 Implementation

Use `before_tool_callback` to intercept tool calls. If the requested action is Tier 3, block execution and trigger the HITL pause. ADK 2.0's workflow runtime has built-in human-in-the-loop pause and resume, so the workflow suspends cleanly and resumes on approval.

#### 11.2a VERIFIED: the callback blocks, it does not merely observe

This was the **highest-stakes unverified assertion left in the PRD**. Every other
threshold that turned out degenerate cost us a metric; a guardrail that logs a
block without blocking is **a safety claim that is false**, and it is the one an
examiner is most likely to test live by asking us to trigger it.

**Verified the hard way, 14 September 2026** -- not "did the callback fire" but
"did the tool's side effect fail to happen". A callback returning a value the
framework ignored would pass a fire-check and fail this one. The probe tool wrote
to a module-level ledger AND appended to a file; both were checked afterwards.

```
callback fired      : 1 time(s) -> ['halt_production_line']
SIDE EFFECT (memory): []
SIDE EFFECT (file)  : '<no file>'
VERDICT: BLOCKED (side effect absent)
```

**Mechanism, read from `flows/llm_flows/_tool_caller.py`:** a `before_tool_callback`
returning a non-`None` dict becomes the `function_response`, and the tool itself is
invoked only `if function_response is None`. Blocking is therefore structural, not
advisory -- `tool_runner()` is never reached.

**What the agent receives, which matters as much.** The block arrives as an ordinary
tool RESPONSE, not as an error:

```
CALL: halt_production_line
RESP: {"status": "BLOCKED_PENDING_HUMAN_APPROVAL", "tier": 3, ...}
TEXT: The production line halt for zone_a_fan_00 is pending human approval.
      Please authorize the halt to proceed.
```

The agent treated it as a **terminal state and stopped**, rather than retrying,
rephrasing, or routing around it. That is the behaviour a safety story needs: a
deterministic outcome, not a negotiation. Had ADK surfaced an error the model could
see and react to, the agent might have argued with the guardrail -- a worse failure
than a broken callback, because it would look like the system working.

**Fallback if this ever changes** (ADK's A2A layer is already self-declared
EXPERIMENTAL): wrap the dispatch client itself, so the guard lives BELOW the
framework rather than inside it. Less elegant, equally sound. Recorded here so the
decision does not have to be made under pressure.

### 11.3 Additional guardrails

- **Input guardrail:** reject malformed or out-of-range sensor payloads before they reach any LLM
- **Output guardrail:** validate the decision agent's output against a JSON schema; a hallucinated action type is rejected and retried once
- **Budget guardrail:** hard cap of 2 reflection loops and a token ceiling per incident, enforced in code and not by prompt
- **Loop guardrail:** the critic cannot re-request an evidence source already gathered

Prompt-based guardrails are weak. Code-based guardrails are strong. Use code and say why in the report.

---

## 12. Evaluation Plan

This is where the grade is won. Most teams will demo and stop. Do not be most teams.

### 12.1 Metric families

**Detection quality (component-level, not the headline)**
- AUROC per modality
- Precision, recall, F1 at the operating threshold
- Per-ambiguity-level breakdown

**Orchestration quality (the headline)**
- **Cost regret vs the oracle (S7.5b):** how much more evidence cost did the system spend than the
  per-incident optimum? Mean regret, plus fraction of incidents at zero regret. **This replaces "path
  selection accuracy", which v1.0 defined circularly against our own labels.**
- **Source regret:** signed difference in number of sources queried; under-gathering weighted harder.
- **Trajectory correctness:** custom metric in S12.3 (set F1 + Kendall's tau + asymmetric partial credit).
- **Escalation precision and recall:** when the system said "I cannot decide," was it right to say so?
  Ground truth here is `oracle_exists == false`. This is our most novel metric.
- **Overconfidence rate:** fraction of wrong decisions made at confidence > 0.85
- **Path distribution:** how often each path fired, stratified by `ambiguity_level`. Descriptive, not
  scored — it is the evidence that branching is real.

**Cost attribution (new in v1.1, and R8 depends on it)**

Total cost per incident must be split into two lines, always reported separately:

| Line | Contains |
|---|---|
| `evidence_cost` | The detector/tool calls the system chose to make |
| `orchestration_overhead` | The orchestrator, critic and triage LLM calls the system spent to make those choices |

R8's rescue is "adaptivity buys efficiency, not accuracy". That rescue **fails silently** if we only
report the total, because the adaptive system pays an orchestration overhead the static baseline (A1)
does not pay at all. It is entirely possible for A2 to win on `evidence_cost` and still lose on total —
in which case the honest headline is "adaptivity reduces evidence cost by X% but costs Y% in
orchestration overhead, netting Z". We must be able to say which, so we measure both from M2 onward.

**Cost**
- Wall-clock latency per incident, per path
- Tokens per incident, split local vs hosted
- Latency and tokens per *correct* decision (the efficiency frontier)

**Safety**
- Tier-3 block rate (should be 100%)
- False block rate on Tier 0 to 2 actions

### 12.2 Ablation matrix

| # | Configuration | Question answered | Status (v1.1) |
|---|---|---|---|
| A0 | Single modality (audio only), fixed threshold | Naive baseline | **Planned** |
| A1 | Static pipeline: always query all three, fixed order | Does adaptivity beat brute force? | **Planned** |
| A2 | Full adaptive system | The proposal | **Planned** |
| A3 | Adaptive, memory agent disabled | Does memory earn its place? | **Planned** |
| A4 | Adaptive, critic/reflection disabled | Does reflection earn its place? | Stretch |
| A5 | Adaptive, all-Gemini (no local models) | Cost of the privacy-preserving choice | Stretch |

**Four planned, two stretch.** v1.0 scheduled six as baseline while S18.3 already listed A3/A4/A5 as
descope tier 5 — the plan contradicted its own descope ladder.

A3 is **planned, not stretch**, deliberately: the memory agent is one of the six agents, S10.3 commits
to it changing decisions, and without A3 we cannot answer "does memory earn its place?" in the viva.
An unfalsifiable component is worse than an absent one. A4 and A5 are genuinely nice-to-have.

With seed-in-key caching (S7.8), re-running an unchanged configuration is nearly free; a *new*
configuration still costs full quota.

**Expected and defensible result:** A2 will probably not beat A1 on raw accuracy, because A1 always has maximum evidence. A2 should beat A1 substantially on **tokens and latency per correct decision**. That is the correct story and you should predict it in the PRD rather than be surprised by it. Adaptivity buys efficiency, not accuracy.

### 12.3 ADK's built-in eval and its limitation

ADK provides `tool_trajectory_avg_score`, which compares actual tools and arguments against expected tools, scoring 1 per match and 0 per mismatch, then averaging. It also provides `response_match_score` using ROUGE-1 by default, plus rubric-based LLM-judged criteria.

**Known limitation you must plan around:** ADK's tool trajectory evaluation currently supports only exact matching, requiring identical call order and exactly matching arguments, which suits it poorly where slight variations are common.

Your system has multiple valid paths by design, so exact match will systematically under-report. **Write a custom trajectory metric:**

- Set-based F1 over consulted agents (order-insensitive)
- Order correlation (Kendall's tau) as a separate score
- Partial credit for a superset trajectory (gathered more than needed) versus a subset (gathered too little), weighted differently because under-gathering is the worse error

Document why you built it. This is a genuine technical contribution and excellent viva material.

### 12.4 Statistical honesty

LLM outputs are stochastic. A single-run table with three decimal places is not credible and an
examiner may say so.

**Variance is measured on A2 only (v1.1).** Three seeds x 150 incidents on A2; every other
configuration runs once at seed 0.

Why: S7.8's cache key now includes the seed, so three seeds genuinely cost three times the quota. Three
seeds across all six configurations is 18 runs, which does not fit the free tier, and v1.0 asked for it
anyway. A2 is the configuration whose numbers we actually defend, and it is the one with the most
stochastic components, so that is where the error bars belong.

**Reporting rule:** A2 reported as mean +/- std over 3 seeds. A0/A1/A3 reported as single-run point
estimates, **labelled as such in the table caption**, with A1 additionally noted as near-deterministic
(it makes no orchestration decisions, so its only stochasticity is in the critic's phrasing). Never
print a +/- next to a number that had one run.

---

## 13. Observability

Self-hosted Phoenix, no account required:

```bash
pip install arize-phoenix openinference-instrumentation-google-adk arize-phoenix-otel
phoenix serve
```

Phoenix automatically collects traces from Google ADK via OpenInference instrumentation, capturing every agent run, tool call, model request, and response with full context and metadata, and can be self-hosted so data stays on your own infrastructure.

**Deliverables from this:**
- Side-by-side trace screenshots showing three visibly different execution graphs
- A latency waterfall showing parallel fan-out actually running concurrently
- A structured `decisions.jsonl` log: one line per orchestrator decision with inputs, output, and reason

The three-different-graphs screenshot is your single strongest slide. It proves dynamic branching in one image.

---

## 14. Technology Stack and Environment

### 14.1 Stack

| Layer | Choice | Version discipline |
|---|---|---|
| Language | Python 3.11 | Pin |
| Agent framework | `google-adk` 2.9.0 | Verified 13 Sep 2026. Module is `google.adk.workflow` (singular) |
| Local LLM host | Ollama 0.30.10 | **Qwen3 4B** (`qwen3:4b`). NOT Gemma 3 -- see S14.2a |
| Hosted LLM | Gemini Flash (AI Studio free tier) | **Pin an exact model id**; the free-tier lineup now spans 2.5 to 3.8 Flash |
| Model connector | `litellm` via ADK's `LiteLlm` | |
| Detectors | `anomalib` 2.6.2 | torch 2.14.0+cpu on the dev machine |
| Telemetry | `scikit-learn` | |
| MCP server | `mcp` 2.2.0 | 2.x renamed `FastMCP` to **`MCPServer`** |
| Memory | `sqlite3` only (no `chromadb`, v1.1 S10.2) | |
| Tracing | `arize-phoenix` | |
| Dataset fetch | `ucimlrepo` | |
| Env | `uv` or `venv` | |

### 14.2 Ollama wiring gotcha

ADK integrates with Ollama through LiteLLM:

```python
from google.adk.models.lite_llm import LiteLlm
model = LiteLlm(model="ollama_chat/gemma3:latest")
```

**Set the provider to `ollama_chat`, not `ollama`.** This is an explicit warning in the ADK docs and it is the most common wiring failure. Tool calling breaks silently with the wrong prefix.

**Verified empirically, 13 September 2026.** Same agent, same model, same tool; only the prefix differs:

| Prefix | Tool invoked | Final text | Exception raised |
|---|---|---|---|
| `ollama_chat/qwen3:4b` | **yes**, `args=['zone_a_fan_02']` | model reasoned, then called the tool | none |
| `ollama/qwen3:4b` | **no** | `''` (empty) | **none** |

The wrong prefix produces no tool call, no output, and no error. Keep this two-line diff as a viva
demonstration: it is a concrete, reproducible failure mode we found ourselves.

### 14.2a Local model choice: Qwen3, not Gemma 3 (resolves open question 3)

v1.0 offered "Gemma 3 4B or Qwen3 4B" and R6 said to prefer Gemma 3. **Gemma 3 is not viable at any
size.** Ollama refuses tool calls outright:

```
litellm.BadRequestError: Ollama_chatException -
{"error":"registry.ollama.ai/library/gemma3:4b does not support tools"}
```

Triage, memory, and dispatch all require structured tool calls, so the choice is settled by constraint
rather than preference: **`qwen3:4b`**. Verified working end to end through ADK's `LiteLlm`.

### 14.3 Hardware

| Task | Requirement |
|---|---|
| Detector training | Colab free tier or any laptop |
| Ollama with a 4B model, **development** | 8 GB RAM minimum, 16 GB comfortable. CPU is acceptable for dev because the disk cache absorbs repeats |
| Ollama with a 4B model, **evaluation runs** | **Free Colab T4.** CPU-only inference at ~82.5 s per call makes a 150-incident ablation ~10 h (R22). On a T4 it is 1-2 s per call. This is not optional for M7 |
| Everything else | Any laptop |

**Measured dev machine (13 Sep 2026):** AMD Ryzen 5 5500U, 6C/12T, **15.3 GB** RAM (below the PRD's
"16 GB comfortable" line), integrated Radeon with 0.5 GB VRAM, so `torch` installs as `2.14.0+cpu` and
there is no GPU offload for Ollama. Everything runs; evaluation is the only thing that does not run
*fast enough*.

**Environment discipline (R23):** dev on local CPU, eval on Colab GPU means two execution environments.
Pin the exact model tag (`qwen3:4b`, never `qwen3:latest`) and stamp the execution environment into
every results table and every `decisions.jsonl` line. "The numbers changed and we do not know why" is a
bad week in November.

If no team member has 16 GB RAM, use Gemma 3 1B, or run Ollama on Colab and expose it, or fall back to Gemini Flash for everything and accept the quota squeeze. Check this on day one.

### 14.4 Repository structure

```
ai-prj/   (GitHub: incident-response-agent)
├── README.md
├── DATA.md                     licences, citations, download instructions
├── ARCHITECTURE.md             diagram + agent roster + contracts
├── EVAL.md                     metrics, ablations, results
├── CONTRIBUTING.md             rotation plan, who owns what this phase
├── requirements.txt            pinned
├── .gitignore                  data/, .env, *.ckpt, cache/
├── scripts/
│   ├── download_data.sh
│   ├── build_harness.py
│   └── train_detectors.py
├── detectors/
│   ├── audio.py                spectrogram + PaDiM
│   ├── vision.py               PaDiM
│   ├── telemetry.py            IsolationForest
│   └── calibration.py
├── mcp_server/
│   └── server.py
├── agents/
│   ├── triage.py
│   ├── orchestrator.py
│   ├── analysts.py             thin MCP tool wrappers; not agents (S5.1)
│   ├── memory.py
│   ├── diagnostic.py
│   ├── critic.py
│   └── dispatch_a2a/           separate A2A service
├── workflows/
│   ├── adaptive.py             the dynamic workflow
│   └── static_baseline.py      NEVER DELETE
├── guardrails/
│   └── callbacks.py
├── memory/
│   └── store.py                SQLite only; no ChromaDB (S10.2)
├── eval/
│   ├── evalsets/*.test.json
│   ├── custom_trajectory.py
│   └── run_ablations.py
└── cache/                      gitignored, but keep a committed fixture subset
```

---

## 15. Pre-Flight Checklist

**Complete every item before writing a single line of agent code.** Each takes minutes. Skipping them costs days.

- [ ] Confirm at least one team machine has 16 GB RAM for Ollama
- [ ] `pip install google-adk` and run a hello-world agent
- [ ] **[ARCHITECTURE GATE, by 15 Sep]** Build a hello-world **graph workflow** in ADK 2.0 with two nodes and a conditional route. If this fails, execute S6.3 and stop revisiting it.
- [ ] `ollama run gemma3` and confirm it responds
- [ ] Wire ADK to Ollama with `LiteLlm(model="ollama_chat/gemma3:latest")` and confirm a **tool call** works, not just chat
- [ ] Get a Gemini API key from AI Studio and make one successful call
- [ ] Deliberately trigger a 429 and confirm your backoff handles it
- [ ] `pip install anomalib`, train PaDiM on one MVTec category, confirm it finishes in under a minute
- [ ] Convert one MIMII clip to a mel-spectrogram and view it
- [ ] Submit the MVTec registration form (do this today; approval may take time)
- [ ] Download MIMII +6 dB fan subset and confirm the files play
- [ ] `fetch_ucirepo(id=601)` returns a dataframe
- [ ] Build a two-tool MCP server and connect it from ADK via `McpToolset`
- [ ] Issue **two concurrent tool calls over one stdio MCP session** and confirm they overlap rather than serialise (R20). Measure wall-clock, do not assume.
- [ ] Expose a trivial agent over A2A with `to_a2a()` and call it from another agent
- [ ] `phoenix serve` and confirm one ADK trace appears
- [ ] Create the GitHub repo, public, with `.gitignore` containing `data/` in the first commit
- [ ] Agree and freeze the evidence report JSON schema (Section 5.4)
- [ ] Agree and freeze the **harness output schema** (Section 7.5c), so detector and orchestration work can proceed against synthetic harness output (R3)
- [ ] Confirm the live Gemini free-tier RPM/RPD figures against the current rate-limit page and update S7.8 if they have moved

If any item fails, you have found a risk before it becomes a crisis. That is the point.

---

## 16. Timeline and Milestones

Today is 13 September 2026. Semester ends 20 November 2026. That is roughly 10 weeks.

| Window | Milestone | Exit criterion |
|---|---|---|
| **13 to 20 Sep** | **M0: Phase-1 submission** | Charter, timeline, responsibility matrix submitted. Pre-flight 100% green. Repo created. **Both** schemas frozen (evidence S5.4, harness S7.5c). **ADK architecture gate resolved by 15 Sep.** |
| 21 Sep to 28 Sep | M1: Detectors + harness | All three detectors scoring, calibrated. Harness emits 200 labelled synchronised events. |
| 29 Sep to **5 Oct** | **M2: Static pipeline (CRITICAL GATE)** | `static_baseline.py` runs end-to-end on 50 incidents and produces a results table. **If this slips, descope immediately.** |
| 6 Oct to 13 Oct | M3: MCP + adaptive skeleton | Detectors behind MCP. Orchestrator picks between fast and parallel paths. |
| 14 Oct to 20 Oct | M4: Memory + critic + guardrails | Three paths live. Reflection loop bounded. Tier-3 blocking works. |
| **21 to 26 Oct** | **M5: Phase-2 demo** | Working prototype, progress report, revised timeline, three-path trace screenshots. |
| 27 Oct to 3 Nov | M6: A2A + RAG + HITL | Dispatch service running as separate A2A process. Diagnostic RAG agent live. Human approval flow demoed. |
| 4 Nov to 11 Nov | M7: Evaluation | A0/A1/A2/A3 run; A2 at 3 seeds, others single-seed (S12.4). Custom trajectory metric and oracle regret implemented. Results table final. |
| 12 Nov to 17 Nov | M8: Report + deck | Report written, deck built, EVAL.md complete. |
| 18 to 20 Nov | **M9: Phase-3** | Final demo, viva, submission. |

### 16.0 Slack (added v1.1, mitigates R19)

v1.0 ran every window back to back with zero slack across ten weeks, three people, a 20%-weighted quiz
in week 4, and other courses. One member losing a week ate an entire milestone. That is not a schedule,
it is a best case.

| Slack | When | Rule |
|---|---|---|
| **Buffer A** | 29 Sep to 5 Oct | M2 targets **1 October**, not 5 October. The remaining four days are buffer. The 5 October gate is unmoved. |
| **Buffer B** | 12 to 13 Nov | Between M7 and M8. Reserved for eval re-runs after a late bug, the most likely late failure. |
| **Standing rule** | Any milestone | A milestone more than three days late triggers **one tier** of the S18.3 descope ladder, automatically and without a team meeting. Pre-agreeing this is the point: it removes the argument from the moment when nobody has time to have it. |

Buffers are not work. If a buffer is unused, it stays unused or absorbs documentation, never new scope.

### 16.1 The one date that matters

**5 October.** If the static pipeline is not running end-to-end by then, stop adding features and execute the descope ladder in Section 18.3. A working boring system beats a broken ambitious one at every grade band.

---

## 17. Team and Contribution Plan

The handout requires that roles rotate across phases, that no student limits themselves to a single area, and that every student can explain and modify any part during the viva.

### 17.1 Vertical slices, rotated

Do not split by layer (one person does ML, one does agents, one does docs). That violates the rotation requirement and creates viva-day panic. Split by **vertical slice** and rotate.

| Slice | Contains |
|---|---|
| S1 Evidence | Detectors, calibration, MCP server, harness |
| S2 Orchestration | Planner, critic, workflow graph, budget logic |
| S3 Periphery | Memory, guardrails, A2A dispatch, observability, eval |

| Phase | Member A | Member B | Member C |
|---|---|---|---|
| Phase 1 to M2 | S1 | S2 | S3 |
| M3 to Phase 2 | S2 | S3 | S1 |
| Phase 2 to Phase 3 | S3 | S1 | S2 |

### 17.2 Viva insurance

Every member keeps a personal `notes/<name>.md` in the repo. After each work session, write three lines: what you changed, why, and what you would change next. This costs two minutes a day and is the difference between confident and stumbling answers in the viva.

At M5 and M8, hold an internal cross-examination: each member is questioned by the other two on a slice they do not currently own.

---

## 18. Risk Register

### 18.1 Technical risks

| # | Risk | Likelihood | Impact | Mitigation | Fallback |
|---|---|---|---|---|---|
| R1 | ADK 2.0 capability does not match the docs, or its API fights us | **High** | **High** | **Architecture gate, not a checkbox:** hello-world graph workflow with a conditional route, resolved by 15 September. Pin the exact version. Official 2.0 docs only. Keep all ADK types out of `detectors/`, `eval/`, harness. | Execute the fully-written 1.x design in S6.3. Costs ~half a grade band on C12 plus ~2 days for manual HITL. **Decision is final once taken.** |
| R2 | Gemini free-tier 429s block eval | **High** | High | Local models for 6 agents; disk cache; concurrency semaphore at 3; backoff with jitter | Reduce test set to 80; run ablations across 4 nights; if desperate, use a second team member's API key |
| R3 | Harness takes longer than planned | **High** | High | Allocate a full week; spec it in Phase-1 charter | Cut to 3 machines and 2 ambiguity levels; 100 incidents |
| R4 | MVTec registration not approved in time | Low | Medium | Submit today | Use the Voxel51 Hugging Face mirror |
| R5 | Official MVTec download URL broken | Medium | Low | Anomalib's data module auto-downloads | Manual download from the MVTec page, or the HF/Kaggle mirror |
| R6 | Ollama tool calling unreliable with small models | Medium | High | Use `ollama_chat` prefix; test tool calling in pre-flight; prefer Gemma 3 4B over 1B | Move analyst agents to Gemini Flash and cut test set to 80 to stay in quota |
| R7 | Confidence scores uncalibrated, guard bands meaningless | Medium | **High** | Explicit calibration step in M1 with a validation split | Use percentile-rank confidence instead of calibrated probability; document it |
| R8 | Adaptive system does not beat static baseline on accuracy | **High** | **Medium** | Expect it, and frame the contribution as efficiency. **But the rescue is conditional:** it only works if the efficiency win is real, so split `evidence_cost` from `orchestration_overhead` (S12.1) from M2 onward. The fast path still pays a Gemini orchestrator call that A1 never pays. | If A2 loses on evidence cost *and* total cost, report that honestly and pivot the headline to cost regret vs the oracle (S7.5b), which remains a genuine result regardless of the A1 comparison. |
| R9 | Reflection loop runs away, burns quota | Medium | Medium | Hard cap of 2 iterations enforced in code | Cap at 1 |
| R10 | Parallel fan-out trips RPM before finishing | **High** | **Low (v1.1)** | Semaphore at 3 concurrent. Largely defused *at this level*: the three detectors are no longer LLM agents (S5.1), so fan-out itself makes no Gemini calls. **The exposure did not vanish, it moved to the eval loop — see R21.** | Make "parallel" logical-only (sequential execution, joined results), and disclose it |
| R11 | No team machine can run Ollama | Low | High | Verify in pre-flight today | Gemma 3 1B, or Colab-hosted Ollama, or all-Gemini with reduced eval |
| R12 | Detector accuracy too low for meaningful orchestration | Low | Medium | PaDiM on MVTec is a strong published baseline | Switch to PatchCore; or restrict to easier MVTec categories |
| R13 | A2A service adds integration pain late in the project | Medium | Low | Build it in M6 as an isolated optional layer | Drop it. It is the cheapest thing to cut. |
| R19 | **Team availability: illness, the week-4 quiz, other courses** | **High** | **High** | S16 had zero slack — every window ran back to back, so one lost week ate a whole milestone. v1.1 adds explicit slack (S16) and keeps the descope ladder pre-agreed so cutting needs no meeting. Any member can run any slice because of the rotation matrix. | Execute S18.3 one tier per lost week. Tier 7 is still a complete passing project. |
| R20 | ~~MCP stdio serialises concurrent tool calls~~ | -- | -- | **CLOSED 13 Sep 2026, did not materialise.** Two concurrent tool calls over one stdio session overlapped: sequential 4.02s vs concurrent 2.02s, same server pid, overlapping start timestamps. Stdio multiplexes. | n/a -- no transport change needed |
| R22 | **Eval wall-clock: local inference makes a full ablation run take ~10 hours** | **High** | **High** | **This, not the harness, is now the critical path.** Arithmetic: 3 local agents (triage, memory, dispatch) x ~82.5 s measured = ~4 min of LLM time per incident; x 150 incidents = **~10 h per run**; x 4 ablations + 3 seeds on A2 = **does not fit in November**. Mitigations, all free: (1) **run Ollama on a Colab free T4 for eval runs** -- inference drops to 1-2 s, which is the real fix; (2) `/no_think` on Qwen3 everywhere, do this regardless; (3) `qwen3:1.7b` for triage and dispatch, which emit fixed-enum structured output, keeping 4B only where reasoning matters; (4) dev stays local on CPU with the disk cache absorbing repeats. | Move the three local agents to Gemini Flash. Fastest to implement but reintroduces the quota problem and weakens the CO2 privacy-preserving story, so it is a fallback, not a plan |
| R23 | **Results not reproducible across execution environments** | Medium | Medium | Consequence of R22's fix: if eval runs on Colab GPU and dev runs on local CPU, different quantisations give different outputs. **Pin the exact model tag** (`qwen3:4b`, not `qwen3:latest`) and **record the execution environment in every results table and in `decisions.jsonl`**. | Re-run the affected configuration in a single environment before the report is written |
| R21 | **`eval/run_ablations.py` trips RPM by processing incidents concurrently** | **High** | **High** | The RPM exposure R10 used to name did not disappear when the detectors stopped being agents — it **moved up a level**. Fan-out is now free of Gemini calls, but each incident still costs 2-4 Gemini calls (orchestrator, critic, diagnostic RAG), and the eval loop runs 150 of them. Concurrency 3 at 3 calls each is ~9 in flight, which trips a 15 RPM ceiling almost immediately. **Hard cap the incident loop at 2 concurrent incidents**, enforced by one semaphore owned by the runner, plus backoff with jitter. The cap is a constant in `eval/run_ablations.py`, not a CLI flag that can be raised at 2am on 10 November. | Drop the incident loop to fully sequential and run overnight; at ~4s per incident, 150 incidents is under an hour even serially, so this fallback costs wall-clock only, never results |

### 18.1a The one non-recoverable risk: R16, UFM

Every other risk in this register costs a grade band. **This one is disciplinary and cannot be
recovered from**, so it is called out separately rather than buried in a project-management table.

The handout is explicit: "Cases of AI-generated code or plagiarism will be taken seriously and reported
according to the university's policy on Unfair Means (UFM)", and "each student should be able to explain
and modify any part of the project" during the demo and viva.

**Standing rules, non-negotiable:**

1. Every team member writes their own implementation code. AI assistance is for review, explanation,
   design critique, and boilerplate (config, `.gitignore`, dependency pinning, download scripts) only.
2. `notes/<name>.md` is updated after every session: what changed, why, what next. This is the
   contemporaneous record of our own reasoning and it is the cheapest possible insurance.
3. Commits are small and incremental. Three giant drops look exactly like what they look like.
4. Internal cross-examination at M5 and M8 (S17.2): each member is questioned by the other two on a
   slice they do not currently own.
5. If any member cannot explain a file, that file is rewritten by that member before it ships.

The design journals plus an incremental commit history are also what make the *defence* credible if the
question is ever raised.

### 18.2 Project-management risks

| # | Risk | Mitigation |
|---|---|---|
| R14 | Team builds the exciting part first and has no fallback demo | The 5 October gate. Non-negotiable. |
| R15 | Uneven contribution; one member cannot answer viva questions | Rotation matrix + internal cross-examination at M5 and M8 |
| R16 | AI-generated code flagged under UFM | Write your own code. Keep `notes/` design journals showing your reasoning. Commit incrementally, not in giant drops. Be able to modify any file live. |
| R17 | Datasets accidentally committed to the public repo | `.gitignore` in the first commit, before data exists. **Near miss, 13 Sep 2026: the v1.0 spec listed only `data/`, but anomalib downloads to `./datasets/` by default.** MVTec (CC BY-NC-SA) would have been staged on the first `git add -A`. `datasets/`, `*.wav`, `*.ckpt`, `*.pt`, `*.pth` are now all ignored. Verify with `git status --short` before every commit, and never trust a path spec written before the tools were run. |
| R18 | Scope creep during M3 to M4 | This PRD is the scope. Changes require a written amendment. |

### 18.3 Descope ladder

If you fall behind, cut **in this exact order**. Each tier still passes.

**Renumbered in v1.1.** v1.0's tier 1 (post-incident reviewer) is already spent — that agent was cut
outright in S5.1 — and v1.0's tier 5 cut A3, which S12.2 now lists as planned. The ladder is re-cut so
that each tier is a real, available, ordered decision.

| Tier | Cut | Still delivers |
|---|---|---|
| 0 | Nothing | Full v1.1 scope, A+ candidate |
| 1 | Ablations A4 and A5 (already stretch in S12.2) | 6 agents, four ablations, everything else intact |
| 2 | A2A dispatch service (make dispatch a local agent) | Loses one syllabus topic, keeps everything else |
| 3 | Diagnostic RAG agent (and the manual corpus) | Loses the Agentic RAG topic; 5 agents |
| 4 | Sequential escalation path (keep fast + parallel) | Still satisfies "at least two distinct workflow paths" |
| 5 | Ablation A3; cut the test set from 150 to 80 | Still proves adaptive vs static (A0/A1/A2). Memory becomes undefended in viva — accept only under real pressure. |
| 6 | Telemetry modality (back to audio + vision) | Original two-modality scope; oracle subsets drop from 16 to 8 |
| 7 | Memory agent | Minimal viable: triage, orchestrator, critic, guardrail, dispatch, 2 detector tools, 2 paths |

**Tier 7 is still a complete, demonstrable, passing agentic project.** That is your floor, and the floor
is high. This is why the feasibility verdict is confident.

**Trigger, per S16.0:** any milestone more than three days late spends exactly one tier, automatically.

---

## 19. Deliverables by Phase

### Phase 1 (September 3rd week, 10%)

- [ ] One-page project charter / synopsis
- [ ] Project timeline (Section 16)
- [ ] Team responsibility matrix (Section 17)
- [ ] Public GitHub repo created with README, DATA.md, `.gitignore`
- [ ] This PRD attached as the methodology annex
- [ ] Architecture diagram

### Phase 2 (October 3rd/4th week, 30%)

- [ ] Updated charter if revised
- [ ] Revised timeline showing progress vs plan
- [ ] Working prototype demo: three paths executing live
- [ ] 1 to 2 page progress report
- [ ] Phoenix trace screenshots showing three distinct execution graphs
- [ ] Preliminary results on the dev set

### Phase 3 (last week, 40%)

- [ ] Final functional agentic application
- [ ] Public GitHub repository (mandatory)
- [ ] Final project report in the provided template
- [ ] Final presentation deck
- [ ] Live demonstration (5 scenarios from Section 3)
- [ ] Group and self contribution matrix
- [ ] Viva readiness: every member can modify any component

### Quiz (September 4th week, 20%)

Independent of the project. Revise agent fundamentals, ReAct, CoT, ToT, self-consistency, agentic design patterns, CrewAI and ADK core concepts, MCP and A2A basics.

---

## 20. Report Outline

1. Introduction and problem statement
2. Related work: industrial anomaly detection, multi-agent orchestration, evidence-based reasoning
3. **Limitations of existing approaches** (fixed pipelines, single modality, no budget awareness)
4. System design: agent roster, evidence contract, orchestration policy
5. Workflow implementation: ADK 2.0 graph and dynamic workflows
6. Tool layer: MCP design and rationale
7. Memory: transient vs persistent
8. Safety: guardrails, action tiers, HITL
9. Datasets and the synthetic facility harness (**declare the simulation here**)
10. Evaluation methodology, including the custom trajectory metric and why ADK's built-in one was insufficient
11. Results: detection, orchestration, cost, ablations
12. Discussion: adaptivity buys efficiency, not accuracy
    12.1 **Thresholds in unmeasured units: a recurring methodological failure**
13. Limitations and threats to validity
14. Future work
15. Individual contributions

---

## 20.2 Report: what dual implementations actually bought

**Put the concrete case in the report, not an abstract claim about modularity.**
Every seam in this system has at least two implementations and a contract test
that runs against both (PRD S14.4). The argument for that discipline is usually
hand-waved; here it has a specific payoff worth one paragraph:

> The memory store has two implementations, SQLite and in-memory, and a contract
> test that runs every query against both. On first run they disagreed:
> `SqliteStore` used `INSERT OR REPLACE` and was idempotent, while `InMemoryStore`
> appended to a list and counted a re-recorded incident three times. Because
> ablation A3 disables memory and attributes the difference to the memory agent,
> **an undetected divergence between the two stores would have meant A3 measured
> the storage backend rather than the mechanism under study.** A seam with one
> implementation cannot surface that class of defect, because there is nothing to
> disagree with.

**State the cost and the catch; let the reader judge.** The discipline is cheap --
a second implementation of a narrow protocol, plus one parametrised test file per
seam -- and it caught one silent divergence that would have corrupted a headline
ablation. It surfaced no defect in the LLM or event-source seams, but those are
load-bearing for other reasons anyway (the one-line local-to-API switch, and
replay reproducibility), and which seam would diverge was not knowable in advance.
Report the cost and the catch as facts rather than computing a hit rate, which
would imply the other seams were speculative when they were not.

## 20.1 Report section 12.1: thresholds in unmeasured units

**Write this as a first-class discussion section, not a footnote in methods.** It is
an honest account of a real mistake we caught ourselves, three times, and it reads
as engineering maturity rather than as an admission.

### The pattern

The same failure occurred three times during development, in three unrelated
subsystems. In each case a threshold was expressed in units that nothing had yet
measured, every code path was implemented and tested, and the mechanism **could
not fire**:

| Subsystem | The threshold | What measurement revealed |
|---|---|---|
| Budget tiers (S5.5a) | 8,000 / 4,000 / 1,500 ms | Querying *every* source costs 1,050 ms. Even the tightest tier had 1.4x headroom, so admission control could never reject anything and `budget_exhausted` could never fire |
| Memory recency (S10.3) | "confirmed fault in the last 7 days" | 150 incidents spanned 6 days across 3 machines, so the condition was true for **86.7%** of incidents. Not a condition -- a constant. Ablation A3 would have measured nothing |
| Tier 3 gate (S11.1a) | "prior fault within 7 days" | Filtered 20.0% down to 18.7%, i.e. barely. The window was wider than the dataset |
| **Memory recency, A3 (S10.3)** | **"confirmed fault in the last 7 days"** | **Fired on 86.7% of incidents.** Not a condition -- a CONSTANT. Ablation A3 would have compared "memory says yes" against "memory says yes" for six incidents in seven, and produced a confident null result that meant nothing. **This is the most consequential instance**, because A3 is the ablation that defends the memory agent's existence |
| False-alarm count (S10.3) | ">= 3 false alarms in **7** days" (a mis-tuning during testing) | Fired on **0.0%**. Only 11 false alarms occur across 3 machines in 150 incidents -- about one per machine per 18 days -- so >=3 within any 7-day window is **arithmetically impossible**, not merely unlikely. Corrected back to the PRD's original 30 days |

### The lesson, stated generally

> A threshold expressed in units that nothing has yet measured cannot be wrong, and
> therefore cannot be right either. Tests confirm that such a branch is reachable
> in principle; only arithmetic against measured data shows whether it is reachable
> in practice.

**The two directions of the same failure.** A threshold can be inert because
nothing ever crosses it, or degenerate because everything always does. Both look
identical in code and both pass every test:

| Direction | Example | Symptom |
|---|---|---|
| **Inert** | Budget tiers; ">=3 false alarms in 7 days" | Rate ~0%. Mechanism never fires; branch is dead code |
| **Degenerate** | "confirmed fault in 7 days" at 86.7% | Rate ~100%. Condition is a constant; the ablation measures nothing |

**A corollary worth stating separately: a threshold on a COUNT must be checked
against the base rate of the thing being counted, not only against the window
width.** ">=3 false alarms in 7 days" is not a strict condition -- it is an
impossible one, given that the data contains roughly one false alarm per machine
per 18 days. Checking the window alone would never have revealed that; only
counting the events did.

In all three cases the tests passed. What caught the failure was arithmetic against
a real number -- PaDiM's 161 ms, the dataset's actual time span, the observed
false-alarm density. **No test we would plausibly have written would have caught
any of them**, because each branch was individually correct and the defect was in
the relationship between a constant and a distribution.

### What we changed as a result

1. Every threshold is measured against the data distribution it discriminates over
   **before** the code that depends on it is written.
2. Firing rates for every gate are asserted in tests with target bands, so a later
   change that quietly drives a rate to zero fails loudly (`no_oracle_rate`,
   `test_no_severity_tier_permits_the_exhaustive_sweep`, the Tier 3 demo assertion).
3. Parameters that only make sense relative to data carry a version string that
   travels with results (`budget-v1`, `logodds-v1`, `memrules-v1`, `HARNESS_VERSION`).
4. Where two rules could overlap, the overlap is measured before either is built.
   The three memory rules are mutually disjoint on the test split (39 + 3 + 3 = 45,
   exactly their union), so A3 ablates three separable mechanisms -- but that is a
   property of the chosen window widths, not a guarantee. At a 3-day window instead
   of 2, the Tier 3 incidents become a strict subset of `lower_threshold` and A3
   loses the ability to attribute effects separately.

This is a genuine methodological contribution of the project, and it is worth more
marks stated plainly than a claim that everything worked first time.

## 21. Resource Index

### ADK
- ADK 2.0 landing: https://google.github.io/adk-docs/2.0/
- Dynamic workflows: https://google.github.io/adk-docs/workflows/dynamic/
- Parallel workflow (1.x reference): https://google.github.io/adk-docs/agents/workflow-agents/parallel-agents/
- Custom agents: https://google.github.io/adk-docs/agents/custom-agents/
- Ollama models: https://google.github.io/adk-docs/agents/models/ollama
- LiteLLM connector: https://google.github.io/adk-docs/agents/models/litellm
- MCP tools: https://github.com/google/adk-docs/blob/main/docs/tools-custom/mcp-tools.md
- A2A overview: https://google.github.io/adk-docs/a2a/
- A2A exposing: https://google.github.io/adk-docs/a2a/quickstart-exposing/
- Evaluation: https://adk.dev/evaluate/
- Eval criteria: https://google.github.io/adk-docs/evaluate/criteria/
- Phoenix integration: https://google.github.io/adk-docs/integrations/phoenix
- Repo: https://github.com/google/adk-python
- Multi-agent codelab: https://codelabs.developers.google.com/codelabs/production-ready-ai-with-gc/3-developing-agents/build-a-multi-agent-system-with-adk

### Detectors
- Anomalib PyPI: https://pypi.org/project/anomalib/
- Anomalib repo: https://github.com/open-edge-platform/anomalib
- PatchCore docs: https://anomalib.readthedocs.io/en/latest/markdown/guides/reference/models/image/patchcore.html
- PaDiM vs PatchCore vs EfficientAd benchmark: https://datature.io/blog/visual-anomaly-detection-with-anomalib-a-hands-on-guide-2026
- Anomalib for industrial inspection tutorial: https://swedenaifactory.se/short-tutorials/2026/06/anomalib-for-industrial-quality-inspection/

### Data
- MIMII: https://zenodo.org/records/3384388
- MIMII baseline code: https://github.com/MIMII-hitachi/mimii_baseline
- MIMII paper: https://arxiv.org/pdf/1909.09347
- MVTec AD: https://www.mvtec.com/company/research/datasets/mvtec-ad
- MVTec AD mirror: https://huggingface.co/datasets/Voxel51/mvtec-ad
- AI4I 2020: https://archive.ics.uci.edu/dataset/601
- Audio-as-image transfer learning reference: https://arxiv.org/pdf/2006.03429

### Protocols and observability
- A2A protocol: https://a2a-protocol.org/latest/
- Phoenix: https://github.com/Arize-ai/phoenix

### Citations for the report

```
Purohit, H., Tanabe, R., Ichige, K., Endo, T., Nikaido, Y., Suefusa, K., Kawaguchi, Y. (2019).
MIMII Dataset: Sound Dataset for Malfunctioning Industrial Machine Investigation and Inspection.
Proc. 4th DCASE Workshop. arXiv:1909.09347.

Bergmann, P., Batzner, K., Fauser, M., Sattlegger, D., Steger, C. (2021).
The MVTec Anomaly Detection Dataset: A Comprehensive Real-World Dataset for
Unsupervised Anomaly Detection. IJCV 129, 1038-1059.

Matzka, S. (2020). AI4I 2020 Predictive Maintenance Dataset.
UCI Machine Learning Repository. DOI: 10.24432/C5HS5C.
```

---

## 22. Open Questions to Resolve This Week

1. Which of `metal_nut` / `screw` maps to which MIMII fan model ID? Decide and justify in the harness spec (v1.1 cut the scope to one machine type and two categories, so this is now a three-way mapping, not a grid).
2. Which team machine hosts Ollama, and is 16 GB available?
3. Gemma 3 4B or Qwen3 4B for the analyst agents? Test tool-call reliability on both and pick.
4. Does the faculty prefer CrewAI or ADK? The syllabus weights ADK far more heavily (20 sessions vs 8), so ADK is the default, but confirm.
5. Confirm whether the provided report template is mandatory and obtain it.
6. Confirm the current Gemini free-tier RPM/RPD; S7.8's whole arithmetic depends on figures we have not re-checked since drafting.
7. Confirm `McpToolset` behaviour for concurrent calls over stdio (R20), since it decides whether the parallel path is real.

---

## 23. Final Assessment

**Technical feasibility:** High. Every component is verified, free, and documented. The hardest technical item is the ADK 2.0 learning curve, which has a clean 1.x fallback.

**Cost feasibility:** Confirmed zero. The binding constraint is LLM request quota, and the mitigations in Section 7.8 resolve it.

**Data feasibility:** Confirmed. All three datasets are accessible under academic-compatible licences. The MVTec registration step is the only gate and it is low risk.

**Schedule feasibility:** The tightest dimension. The harness is the hidden cost. The 5 October gate is the control.

**Confidence:** ~85% of delivering Tier 0 or Tier 1 scope. ~98% of delivering at least Tier 7, which is still a complete, passing agentic project.

The project is worth doing and the plan is executable. Protect the static pipeline, build the harness early, and cache every LLM call.