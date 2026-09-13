# PRD: Adaptive Multi-Modal Industrial Incident-Response Agent

**Course:** CSE3101 Agentic AI (BML Munjal University, 2026-27, 7th Semester)
**Faculty:** Dr. Soharab Hossain Shaikh, Mr. Pranshu Tiwari
**Document version:** 1.0
**Date:** 13 September 2026
**Semester window:** 27 July 2026 to 20 November 2026
**Status:** Ready for Phase-1 submission

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
| G1 | Build a working multi-agent system with at least 8 distinct agent roles, of which at least 5 make genuine autonomous decisions |
| G2 | Demonstrate three structurally different workflow paths chosen at runtime by evidence, not by configuration |
| G3 | Implement transient vs persistent memory with measurable effect on decisions |
| G4 | Implement reflection: the system can decide its own evidence is insufficient and gather more |
| G5 | Enforce guardrails via callbacks, including human-in-the-loop for high-impact actions |
| G6 | Expose detectors over MCP and the dispatch service over A2A |
| G7 | Produce an evaluation with ablations comparing adaptive vs static orchestration |
| G8 | Run analyst agents on a local LLM for privacy-preserving operation |
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
A fan produces a borderline acoustic reading. The orchestrator concludes it cannot decide, fires audio, vision, and telemetry analysts concurrently, and joins the results.

**Scenario C: Weak signals across all modalities (escalation loop)**
Nothing is decisive. The orchestrator gathers one evidence source at a time, checking after each whether it has crossed the confidence threshold, until it either resolves or exhausts its budget and escalates to a human.

**Scenario D: High-impact recommended action (guardrail)**
The system concludes the correct action is to halt a production line. The guardrail agent blocks the tool call and requires human confirmation before dispatch.

**Scenario E: Repeat offender (memory)**
A zone that produced four false alarms last month generates another borderline reading. The memory agent surfaces that history and the orchestrator lowers its escalation priority.

Scenarios A, B, C, and E are your demo script. Scenario D is your safety story. Rehearse all five.

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

| # | Agent | LLM? | Decides what | Holds state |
|---|---|---|---|---|
| 1 | Triage agent | Local | Investigate, drop, or escalate immediately | No |
| 2 | Orchestrator / planner | Gemini Flash | Which path, which evidence, in what order, what budget | Yes (plan) |
| 3 | Audio analyst | Local | Which window to score, how to phrase confidence | No |
| 4 | Vision analyst | Local | Which frame or region, whether to request recapture | No |
| 5 | Telemetry analyst | Local | Which window, which features matter | No |
| 6 | Memory agent | Local | Which history is relevant to this machine and symptom | Yes (persistent) |
| 7 | Diagnostic RAG agent | Gemini Flash | Which manual sections to retrieve, what root cause fits | No |
| 8 | Critic / reflection agent | Gemini Flash | Is the evidence sufficient, or gather more | Yes (iteration count) |
| 9 | Safety guardrail | Rules + callback | Block, allow, or require human approval | No |
| 10 | Dispatch agent (remote, A2A) | Local | Which work-order template, what priority | Yes (ticket log) |
| 11 | Post-incident reviewer | Gemini Flash | What to write back to persistent memory | Yes (writes) |

Nine of these are agents by our own definition. The guardrail is implemented as a callback plus a small rule engine and should be described as such in the report, not padded into an "agent" count.

### 5.2 LLM assignment strategy

This is driven entirely by free-tier quota (see Section 7.4).

- **Local via Ollama:** triage, audio analyst, vision analyst, telemetry analyst, memory agent, dispatch agent. High call volume, low reasoning complexity, mostly structured output.
- **Gemini Flash:** orchestrator, critic, diagnostic RAG, post-incident reviewer. Low call volume, high reasoning complexity.

Per incident that means roughly 3 to 5 Gemini calls and 3 to 8 local calls.

### 5.3 Architecture layers

```
Layer 0  Scenario harness        Emits synchronised multi-modal events
Layer 1  Ingestion               Triage agent
Layer 2  Orchestration           Planner, critic, budget accounting
Layer 3  Evidence                5 analyst agents behind one MCP server
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

### 5.6 Three paths, specified

**Fast path**
One evidence source already scored. Skip corroboration. Straight to critic, then guardrail, then dispatch. Target latency under 2 seconds. Target 1 Gemini call.

**Parallel fan-out**
Three analysts run concurrently. Results joined. Highest latency reduction, highest token cost. Target latency under 5 seconds.

**Sequential escalation loop**
Query one source, evaluate, decide whether to continue. Max 4 iterations or budget exhaustion. Lowest token cost, highest latency. Ends in resolution or human escalation.

The comparison between parallel and sequential is a genuine cost/latency tradeoff the planner makes. Measuring that tradeoff is a headline result.

---

## 6. Workflow Implementation

### 6.1 Framework decision: ADK Python 2.0

**Use ADK Python 2.0, not 1.x.** ADK Python 2.0 reached general availability on 19 May 2026. It introduces a Workflow Runtime, a graph-based execution engine supporting routing, fan-out/fan-in, loops, retry, state management, dynamic nodes, human-in-the-loop, and nested workflows, plus a Task API for structured agent-to-agent delegation.

Your syllabus lists "Graph workflows, dynamic workflows, collaborative workflows" as explicit topics. Those are the 2.0 feature names. The course was written against 2.0.

**Critical warnings:**
- 2.0 has breaking changes to the agent API, event model, and session schema versus 1.x.
- Most blog tutorials you will find online are 1.x. Use only the official docs at `google.github.io/adk-docs/2.0/`.
- Pin the exact version in `requirements.txt` on day one and never float it.

### 6.2 Which workflow construct for which path

| Path | Construct |
|---|---|
| Overall incident flow | Dynamic workflow (Python control flow, `async`/`await`) |
| Parallel fan-out | Fan-out with join node |
| Sequential escalation | `while` loop inside the dynamic workflow with budget check |
| Human approval | Built-in HITL pause/resume |
| Dispatch | Remote A2A agent as a workflow node |

Dynamic workflows in ADK 2.0 track each node execution and automatically skip successful sub-nodes when resuming, which makes complex logic durable and resumable by default. That is free crash resilience for your demo.

### 6.3 Fallback if ADK 2.0 fights you

If after 3 days you cannot get a hello-world graph workflow running, fall back to ADK 1.x with `SequentialAgent`, `ParallelAgent`, `LoopAgent`, and a `CustomAgent` implementing `_run_async_impl` for the branching logic. This is fully supported, well documented, and costs you maybe half a grade band. Do not burn a week fighting the framework.

---

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

| Dataset | What to take | Approx size |
|---|---|---|
| MIMII | **One SNR level (+6 dB), two machine types (fan, pump), all four model IDs** | ~5 GB |
| MVTec AD | **Four categories only** (e.g. bottle, metal_nut, screw, transistor) | ~2 GB |
| AI4I 2020 | Everything | 500 KB |

Taking all of MIMII across all three SNR levels would be tens of GB and gains you nothing.

### 7.4 Licence compliance and repo hygiene

The handout mandates a public GitHub repository. MVTec AD is NonCommercial-ShareAlike. Handle this correctly:

- Add `data/` to `.gitignore` on the very first commit, before any data exists
- Commit `scripts/download_data.sh` instead of data
- Create `DATA.md` listing every dataset, its licence, its URL, and its full citation
- Never commit `.wav`, `.png` from MVTec, or derived spectrograms
- Add a licence note in the README stating the datasets are used for non-commercial academic research

### 7.5 The scenario harness: the hidden critical path

**This is the single most underestimated work item in the project. Budget one full week.**

MIMII, MVTec AD, and AI4I have no shared machine identity. There is no real facility where the same pump has audio, images, and telemetry. Without a synthesis layer, "at least two distinct workflow paths taken depending on evidence confidence" is unmeasurable, because you have no ground truth for what the correct path was.

**What the harness does:**

1. Defines a simulated facility with N machines (e.g. 6 machines across 3 zones)
2. Maps each machine to one MIMII machine ID, one MVTec category, and one AI4I product type
3. Emits synchronised events: `(audio_clip_path, image_path, telemetry_row, timestamp, machine_id)`
4. Attaches ground truth: `is_anomalous` plus an **ambiguity level** in {clear, borderline, deceptive}
5. Attaches an expected-path label so trajectory correctness is measurable

**Ambiguity is manufactured deliberately:**

| Level | Construction | Expected path |
|---|---|---|
| Clear | Anomalous audio + anomalous image + anomalous telemetry | Fast |
| Clear-normal | All three normal | Fast |
| Borderline | Anomalous in exactly one modality, normal in others | Parallel |
| Deceptive | Weakly anomalous in two, the pairing conflicts | Sequential, or escalate |

**Declare the simulation honestly in the report.** Write: "Because no public dataset provides time-aligned multi-modal recordings of the same industrial asset, we construct a synthetic facility that composes three real public datasets into synchronised incident events. Detector inputs are real; the cross-modal alignment is synthetic. This is a limitation we state explicitly."

An examiner who spots a hidden simulation will punish you. An examiner who reads that you declared it will credit you for rigour.

### 7.6 Maintenance manual corpus for the RAG agent

There is no public corpus of industrial maintenance manuals matching these machines. Options in order of preference:

1. Write 15 to 20 short synthetic fault-cause documents yourself, one per failure mode (TWF, HDF, PWF, OSF, and MIMII anomaly types such as contamination, leakage, rotating unbalance, rail damage). About 200 words each. Two hours of work, fully controllable.
2. Use public equipment maintenance guides from manufacturer websites where licensing permits.

Option 1 is correct for a course project. Say so.

### 7.7 Eval set sizing

| Split | Incidents | Purpose |
|---|---|---|
| Dev | 50 | Prompt iteration, fast loop |
| Test | 150 | Reported results, frozen |
| Demo | 8 | Hand-picked, one per scenario in Section 3 |

150 is deliberate. It is enough for a credible table and small enough to survive Section 7.8.

### 7.8 The real constraint: LLM quota, not compute

Compute is a non-issue. Quota is the binding constraint.

As of 2026, Gemini Flash sits at roughly 15 requests per minute and about 1,500 requests per day on the free tier. Pro models were removed from the free tier in April 2026. Parallel requests and token-heavy prompts are the two patterns that hit these limits fastest, usually before developers expect them to.

**Arithmetic:** 4 Gemini-backed agents x 150 incidents = 600 calls for one eval run. Five ablation configurations = 3,000 calls. That exceeds two full days of quota, and your parallel fan-out will trip 429s on the RPM limit immediately.

**Mandatory mitigations:**

| Mitigation | Effect |
|---|---|
| Local Ollama for the 6 high-volume agents | Removes ~60% of calls |
| Response cache keyed on prompt hash, on disk, committed as a fixture | Re-running an ablation costs near zero |
| Exponential backoff with jitter on 429 | Survives RPM limits |
| Semaphore capping concurrency at 3 | Prevents fan-out from tripping RPM |
| Eval set at 150, not 500 | Keeps a full run inside one day |
| Run ablations overnight, one per night | Spreads across the RPD ceiling |

The cache is not optional. Without it you cannot iterate.

**This constraint is also a deliverable.** CO2 requires privacy-preserving local LLMs. Write in the report that quota economics drove a hybrid local/hosted architecture, and measure the quality delta between all-Gemini and hybrid. That is a legitimate experiment.

---

## 8. Detector Specification

### 8.1 The simplification that saves a week

**Do not build a separate audio model.** Convert MIMII clips to mel-spectrogram images and run the same Anomalib model used for vision. Anomaly patterns are frequently visible in mel-spectrograms, making image-based models a reasonable choice for acoustic anomaly detection. This collapses two detector codebases into one.

### 8.2 Model choice

| Detector | Model | Rationale |
|---|---|---|
| Vision | Anomalib PaDiM | PaDiM trains in about 9.2 seconds versus PatchCore's 282.8 seconds, with a pixel AUROC drop of only 0.003 |
| Audio | Anomalib PaDiM on mel-spectrograms | Same pipeline, same code |
| Telemetry | scikit-learn IsolationForest | Trivial on 10k rows |

If PaDiM underperforms, switch to PatchCore. PatchCore requires no backpropagation, using a pretrained backbone plus nearest-neighbour search over a memory bank.

### 8.3 Spectrogram parameters

Use published settings as your starting point: 64 mel bands, frame size 1024, hop 512, then upscale patches to 224x224 and standardise with ImageNet statistics to match the pretrained backbone's domain.

### 8.4 Confidence calibration

Raw anomaly scores from PaDiM are unbounded distances, not probabilities. **The orchestrator's entire decision policy depends on calibrated confidence.** Fit a simple calibration (min-max over the validation set, or Platt scaling) so that confidence is in [0, 1] and roughly means what it says. Document the calibration method. An uncalibrated confidence makes your guard bands meaningless and an examiner will ask.

---

## 9. Tool Layer: MCP

### 9.1 Design

One MCP server, `behooked_detectors` (rename appropriately), exposing:

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

### 9.3 Why this is worth doing

It is a named syllabus topic, it forces a clean contract between the ML work and the agent work so two team members can work in parallel, and it makes the detectors swappable for ablations.

---

## 10. Memory Design

The syllabus distinguishes transient versus persistent state. Implement both visibly.

### 10.1 Transient (session state)

Lives for one incident. Held in ADK session state.

Contents: current evidence reports, budget remaining, reflection iteration count, orchestrator plan, path taken.

### 10.2 Persistent (across incidents)

SQLite for structured history, ChromaDB for semantic retrieval of past incident narratives.

| Table / collection | Contents |
|---|---|
| `machines` | machine_id, zone, type, install_date |
| `incidents` | incident_id, machine_id, timestamp, verdict, action, was_false_alarm |
| `incident_narratives` (Chroma) | Embedded free-text summaries for similarity search |

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

### 11.2 Implementation

Use `before_tool_callback` to intercept tool calls. If the requested action is Tier 3, block execution and trigger the HITL pause. ADK 2.0's workflow runtime has built-in human-in-the-loop pause and resume, so the workflow suspends cleanly and resumes on approval.

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
- **Path selection accuracy:** did the orchestrator pick the expected path for this ambiguity level?
- **Trajectory correctness:** were the right agents consulted, in a sensible order?
- **Evidence efficiency:** average number of sources queried per correct decision
- **Escalation precision and recall:** when the system said "I cannot decide," was it right to say so? This is your most novel metric.
- **Overconfidence rate:** fraction of wrong decisions made at confidence > 0.85

**Cost**
- Wall-clock latency per incident, per path
- Tokens per incident, split local vs hosted
- Latency and tokens per *correct* decision (the efficiency frontier)

**Safety**
- Tier-3 block rate (should be 100%)
- False block rate on Tier 0 to 2 actions

### 12.2 Ablation matrix

| # | Configuration | Question answered |
|---|---|---|
| A0 | Single modality (audio only), fixed threshold | Naive baseline |
| A1 | Static pipeline: always query all three, fixed order | Does adaptivity beat brute force? |
| A2 | Full adaptive system | The proposal |
| A3 | Adaptive, memory agent disabled | Does memory earn its place? |
| A4 | Adaptive, critic/reflection disabled | Does reflection earn its place? |
| A5 | Adaptive, all-Gemini (no local models) | Cost of the privacy-preserving choice |

Six runs. With caching, reruns are nearly free. Without caching, this is three days of quota.

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

LLM outputs are stochastic. Run the test set 3 times per configuration with different seeds and report mean plus standard deviation. A single-run table with three decimal places is not credible and an examiner may say so.

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
| Agent framework | `google-adk` 2.x | **Pin exact patch version** |
| Local LLM host | Ollama | Gemma 3 4B or Qwen3 4B |
| Hosted LLM | Gemini Flash (AI Studio free tier) | |
| Model connector | `litellm` via ADK's `LiteLlm` | |
| Detectors | `anomalib` 2.x | Pin |
| Telemetry | `scikit-learn` | |
| MCP server | `mcp` Python package | |
| Memory | `sqlite3` + `chromadb` | |
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

### 14.3 Hardware

| Task | Requirement |
|---|---|
| Detector training | Colab free tier or any laptop |
| Ollama with a 4B model | 8 GB RAM minimum, 16 GB comfortable |
| Everything else | Any laptop |

If no team member has 16 GB RAM, use Gemma 3 1B, or run Ollama on Colab and expose it, or fall back to Gemini Flash for everything and accept the quota squeeze. Check this on day one.

### 14.4 Repository structure

```
incident-response-agent/
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
│   ├── analysts.py
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
│   └── store.py
├── eval/
│   ├── evalsets/*.test.json
│   ├── custom_trajectory.py
│   └── run_ablations.py
├── cache/                      gitignored, but keep a committed fixture subset
└── demo/
    └── dashboard.py
```

---

## 15. Pre-Flight Checklist

**Complete every item before writing a single line of agent code.** Each takes minutes. Skipping them costs days.

- [ ] Confirm at least one team machine has 16 GB RAM for Ollama
- [ ] `pip install google-adk` and run a hello-world agent
- [ ] Build a hello-world **graph workflow** in ADK 2.0 with two nodes and a conditional route
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
- [ ] Expose a trivial agent over A2A with `to_a2a()` and call it from another agent
- [ ] `phoenix serve` and confirm one ADK trace appears
- [ ] Create the GitHub repo, public, with `.gitignore` containing `data/` in the first commit
- [ ] Agree and freeze the evidence report JSON schema (Section 5.4)

If any item fails, you have found a risk before it becomes a crisis. That is the point.

---

## 16. Timeline and Milestones

Today is 13 September 2026. Semester ends 20 November 2026. That is roughly 10 weeks.

| Window | Milestone | Exit criterion |
|---|---|---|
| **13 to 20 Sep** | **M0: Phase-1 submission** | Charter, timeline, responsibility matrix submitted. Pre-flight checklist 100% green. Repo created. Schema frozen. |
| 21 Sep to 28 Sep | M1: Detectors + harness | All three detectors scoring, calibrated. Harness emits 200 labelled synchronised events. |
| 29 Sep to **5 Oct** | **M2: Static pipeline (CRITICAL GATE)** | `static_baseline.py` runs end-to-end on 50 incidents and produces a results table. **If this slips, descope immediately.** |
| 6 Oct to 13 Oct | M3: MCP + adaptive skeleton | Detectors behind MCP. Orchestrator picks between fast and parallel paths. |
| 14 Oct to 20 Oct | M4: Memory + critic + guardrails | Three paths live. Reflection loop bounded. Tier-3 blocking works. |
| **21 to 26 Oct** | **M5: Phase-2 demo** | Working prototype, progress report, revised timeline, three-path trace screenshots. |
| 27 Oct to 3 Nov | M6: A2A + RAG + HITL | Dispatch service running as separate A2A process. Diagnostic RAG agent live. Human approval flow demoed. |
| 4 Nov to 11 Nov | M7: Evaluation | All six ablations run 3x. Custom trajectory metric implemented. Results table final. |
| 12 Nov to 17 Nov | M8: Report + deck | Report written, deck built, EVAL.md complete. |
| 18 to 20 Nov | **M9: Phase-3** | Final demo, viva, submission. |

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
| R1 | ADK 2.0 breaking changes, sparse examples | Medium | High | Hello-world graph workflow in pre-flight; pin version; use official docs only | Drop to ADK 1.x `SequentialAgent`/`ParallelAgent`/`LoopAgent` + `CustomAgent`. Costs ~half a grade band. |
| R2 | Gemini free-tier 429s block eval | **High** | High | Local models for 6 agents; disk cache; concurrency semaphore at 3; backoff with jitter | Reduce test set to 80; run ablations across 4 nights; if desperate, use a second team member's API key |
| R3 | Harness takes longer than planned | **High** | High | Allocate a full week; spec it in Phase-1 charter | Cut to 3 machines and 2 ambiguity levels; 100 incidents |
| R4 | MVTec registration not approved in time | Low | Medium | Submit today | Use the Voxel51 Hugging Face mirror |
| R5 | Official MVTec download URL broken | Medium | Low | Anomalib's data module auto-downloads | Manual download from the MVTec page, or the HF/Kaggle mirror |
| R6 | Ollama tool calling unreliable with small models | Medium | High | Use `ollama_chat` prefix; test tool calling in pre-flight; prefer Gemma 3 4B over 1B | Move analyst agents to Gemini Flash and cut test set to 80 to stay in quota |
| R7 | Confidence scores uncalibrated, guard bands meaningless | Medium | **High** | Explicit calibration step in M1 with a validation split | Use percentile-rank confidence instead of calibrated probability; document it |
| R8 | Adaptive system does not beat static baseline on accuracy | **High** | Low | Expect it. Frame the contribution as efficiency, not accuracy | Report the efficiency win honestly; a negative accuracy result with a positive cost result is a good result |
| R9 | Reflection loop runs away, burns quota | Medium | Medium | Hard cap of 2 iterations enforced in code | Cap at 1 |
| R10 | Parallel fan-out trips RPM before finishing | **High** | Medium | Semaphore at 3 concurrent; local models for the three analysts | Make "parallel" logical-only (sequential execution, joined results), and disclose it |
| R11 | No team machine can run Ollama | Low | High | Verify in pre-flight today | Gemma 3 1B, or Colab-hosted Ollama, or all-Gemini with reduced eval |
| R12 | Detector accuracy too low for meaningful orchestration | Low | Medium | PaDiM on MVTec is a strong published baseline | Switch to PatchCore; or restrict to easier MVTec categories |
| R13 | A2A service adds integration pain late in the project | Medium | Low | Build it in M6 as an isolated optional layer | Drop it. It is the cheapest thing to cut. |

### 18.2 Project-management risks

| # | Risk | Mitigation |
|---|---|---|
| R14 | Team builds the exciting part first and has no fallback demo | The 5 October gate. Non-negotiable. |
| R15 | Uneven contribution; one member cannot answer viva questions | Rotation matrix + internal cross-examination at M5 and M8 |
| R16 | AI-generated code flagged under UFM | Write your own code. Keep `notes/` design journals showing your reasoning. Commit incrementally, not in giant drops. Be able to modify any file live. |
| R17 | Datasets accidentally committed to the public repo | `.gitignore` in the first commit, before data exists |
| R18 | Scope creep during M3 to M4 | This PRD is the scope. Changes require a written amendment. |

### 18.3 Descope ladder

If you fall behind, cut **in this exact order**. Each tier still passes.

| Tier | Cut | Still delivers |
|---|---|---|
| 0 | Nothing | Full PRD scope, A+ candidate |
| 1 | Post-incident reviewer agent | 9 agents, all else intact |
| 2 | A2A dispatch service (make dispatch a local agent) | Loses one syllabus topic, keeps everything else |
| 3 | Diagnostic RAG agent | Loses Agentic RAG topic |
| 4 | Sequential escalation path (keep fast + parallel) | Still satisfies "at least two distinct workflow paths" from the original brief |
| 5 | Ablations A3, A4, A5 (keep A0, A1, A2) | Still proves adaptive vs static |
| 6 | Telemetry modality (back to audio + vision) | Original two-modality scope |
| 7 | Memory agent | Minimal viable: triage, planner, 2 analysts, critic, guardrail, dispatch, 2 paths |

**Tier 7 is still a complete, demonstrable, passing agentic project.** That is your floor, and the floor is high. This is why the feasibility verdict is confident.

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
13. Limitations and threats to validity
14. Future work
15. Individual contributions

---

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

1. Which MVTec categories map most plausibly to which MIMII machine types? Decide and justify in the harness spec.
2. Which team machine hosts Ollama, and is 16 GB available?
3. Gemma 3 4B or Qwen3 4B for the analyst agents? Test tool-call reliability on both and pick.
4. Does the faculty prefer CrewAI or ADK? The syllabus weights ADK far more heavily (20 sessions vs 8), so ADK is the default, but confirm.
5. Confirm whether the provided report template is mandatory and obtain it.

---

## 23. Final Assessment

**Technical feasibility:** High. Every component is verified, free, and documented. The hardest technical item is the ADK 2.0 learning curve, which has a clean 1.x fallback.

**Cost feasibility:** Confirmed zero. The binding constraint is LLM request quota, and the mitigations in Section 7.8 resolve it.

**Data feasibility:** Confirmed. All three datasets are accessible under academic-compatible licences. The MVTec registration step is the only gate and it is low risk.

**Schedule feasibility:** The tightest dimension. The harness is the hidden cost. The 5 October gate is the control.

**Confidence:** ~85% of delivering Tier 0 or Tier 1 scope. ~98% of delivering at least Tier 7, which is still a complete, passing agentic project.

The project is worth doing and the plan is executable. Protect the static pipeline, build the harness early, and cache every LLM call.