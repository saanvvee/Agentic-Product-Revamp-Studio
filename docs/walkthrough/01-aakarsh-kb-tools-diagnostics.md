# Walkthrough 01: knowledge base, tool layer, diagnostics (owner: Aakarsh)

Files: `revamp/contracts.py`, `revamp/kb.py`, `revamp/tools/*`, `revamp/mcp_server.py`,
`revamp/agents/diagnostics.py`, `revamp/audit.py`, `revamp/evidence.py`.

## Contracts (`contracts.py`)

Frozen pydantic models shared by everything: `Finding`, `Proposal`, `Conflict`, `Plan`,
`ClientVerdict`, `ClientConstraint`, `RunRecord`.

- **`Finding.make` derives the id from content**, via `stable_id` (a sha256 of product, category,
  tool, locator and title). Re-running a tool on the same page gives the same id, so the KB
  deduplicates instead of piling up copies.
- **`Proposal` requires at least one `finding_id`** and at least one area. Areas are normalised
  (lowercase, underscores) because the conflict proxy and the client constraints match on them.
- **Amendments are logged** in PLAN.md Section 2a. The only one so far adds
  `Team = "single_llm"` for arm A0.

## Knowledge base (`kb.py`)

One SQLite file, three namespaces, and a role fixed when the handle is opened:

| Namespace | Read | Write |
|---|---|---|
| shared | team, client, evaluator | team, evaluator |
| client_private | client, evaluator | client, evaluator |
| priors | team, evaluator | evaluator |

Every method calls `_check(namespace, op)` first.

**Why in code, not a prompt:** ADK session state is one dict with no access control (checked in
the ADK 2.9 source). A prompt saying "do not look" is not access control.

`add_proposal` rejects any proposal citing a finding the KB does not hold (`ProvenanceError`).
This is the second provenance gate; the first is in `workflow/nodes.py::drafts_to_proposals`.

## Tools (`tools/`)

Every runner is a plain async function returning `Finding`s. None calls an LLM.

| File | Measures | Notes |
|---|---|---|
| `lighthouse.py` | PSI API (live) and the local Lighthouse CLI | One parser (`parse_lhr`). Core Web Vitals thresholds from web.dev. Local runs take the median of 5 (Lighthouse variance) |
| `browser.py` | axe-core WCAG 2.2 AA; Playwright journeys with screenshots | axe is injected from `tools/bin/axe.min.js`, so no wrapper dependency |
| `seo.py` | Raw-HTML checks, robots.txt, sitemap | Client-rendered sites look thin; that is itself a finding |
| `pricing.py` | Pricing page text, own and competitors' | Falls back to a real browser if the raw text is under 300 characters |
| `voice.py` | GitHub issues, Discourse topics | **Only items created before `cutoff`**, filtered twice |
| `code.py` | scc size, lizard complexity, osv-scanner CVEs | Nothing from the audited repo is installed or executed |

Two findings from building this that are worth mentioning in the viva:

1. **osv-scanner 2.6's `--recursive` flag walks the drive root on Windows.** We pass each
   lockfile explicitly with `-L`.
2. **Advisories published after the cutoff must be excluded.** For umami v2.19.0, the count
   drops from 152 advisories to 3. Counting the other 149 would give the system hindsight.

Politeness (`common.py::Polite`): at most one request per second per host, robots.txt honoured,
an identifying User-Agent. The Discourse `/search` endpoint is disallowed by robots.txt, so we
use `/top.json`.

## MCP server (`mcp_server.py`)

`python -m revamp.mcp_server --product umami --role team`. It is locked to one product and one
KB role for its whole life. Audit tools store findings and return a short text summary rather
than raw JSON, because a 4B model reasons better over ten lines.

## Chief Diagnostician (`agents/diagnostics.py`)

An `LlmAgent` whose tools come from an `McpToolset` that launches the server above as a child
process over stdio. The model decides which audits to run and when to stop. The cap is code: a
`before_tool_callback` that returns a refusal dict after N calls. In ADK 2.9, returning a dict
from that callback skips the real tool.

One consequence worth knowing: **the tools do not run in this process.** The MCP server is a child,
so the audit's wall time is spent over there. The `after_tool_callback` therefore books the tool's
elapsed time onto the parent run's `CostLedger.evidence_seconds` (`_STARTED` holds the start time
between the two callbacks). Without it, an agentic audit would report zero evidence cost and the
evidence/orchestration split of invariant 9 would be a lie.

## An audit is a run (`audit.py`)

`deterministic_audit` runs the seven steps in order with no model; `agentic_audit` hands the choice
to the Chief Diagnostician. Both behave the same way afterwards, because "a thing that produced
evidence, findings, a cost and a verdict deserves a record":

| What | Where |
|---|---|
| Run record, arm `audit-det` or `audit-agentic` | `kb.save_run`, so `revamp runs` and the dashboard list it like an engagement |
| Per-step events: input, finding ids, wall time, error | `runs/events/<run id>.jsonl` |
| HTML report | `runs/reports/<run id>.html`, built by `report.render_audit` from the events + the KB |
| Trace | one root `audit` span with a `tool.<step>` span per step |

Two rules make it safe to report on:

- **One failing tool must not sink the audit.** The step is caught, recorded as `SKIPPED: <error>`
  and the sweep continues; the report shows it in red.
- **The report never asks a model.** It is rebuilt from the event file and the KB, so
  `python -m revamp report <id>` reproduces any past audit without touching the live site.

## Viva questions

1. Why is the Finding id a hash of content rather than a random UUID? What breaks if two tools
   report the same page?
2. A team agent is given the KB file path. Can it read client constraints? Walk through exactly
   what stops it.
3. Why exclude CVE advisories published after the cutoff? What would the security numbers look
   like otherwise, and why would that be unfair?
4. Why does `lizard_metrics` check that the module exists before running, instead of trusting
   the exit code?
5. The Chief Diagnostician "decides when evidence is sufficient". What in code guarantees it
   stops?
6. The audit tools run in a separate process. How does the parent process still know how long the
   evidence took, and what would the report look like without that?
7. If the PSI tool times out halfway through a sweep, what does the audit record, and what does the
   final report say about the product's coverage?
