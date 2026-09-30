# Walkthrough 05: observability and Mission Control (everyone)

Files: `revamp/observe.py`, `revamp/tracing.py`, `revamp/dashboard/`, `deploy/langfuse/`.

## Two audiences, two mechanisms

| | Events (`observe.emit`) | Traces (OpenTelemetry spans) |
|---|---|---|
| For | Watching a run live; the viva demo | Debugging; latency and token analysis |
| Where | Mission Control (`python -m revamp.dashboard`) and `runs/events/<run>.jsonl` | Langfuse and/or Arize Phoenix |
| Content | Orchestration facts: node started/finished with its route, agent prompt and answer, proposals, plan, conflicts, verdicts, approvals, tool calls | Span tree: engagement → node.* → ADK invocation → agent → model call (tokens, cache hit) |
| Needs | Nothing (always on) | `LANGFUSE_*` or `PHOENIX_COLLECTOR_ENDPOINT` in `.env` |

Both are fed from the same places:
- the node wrapper `observe.traced_node`, applied to every workflow node in `workflow/graph.py`;
- `agents/runtime.ask`, which every agent call goes through;
- `llm/cache.CachedLlm`, which every model call goes through.

So nothing can run without being observed.

## Tracing without a vendor SDK

`tracing.py` builds an OpenTelemetry `TracerProvider` with one OTLP/HTTP exporter per backend.

- **Langfuse:** `POST <host>/api/public/otel/v1/traces` with
  `Authorization: Basic base64(public:secret)` and `x-langfuse-ingestion-version: 4`. This is
  what the langfuse SDK does internally. We do it directly because PyPI is unreachable on campus.
- **Phoenix:** `POST <endpoint>/v1/traces`.
- **ADK's own spans** come from the OpenInference `GoogleADKInstrumentor`.
- **One run = one trace:** the root span `engagement` (runner.py) wraps the whole run. OTel
  context travels with asyncio contextvars, so node, agent and model spans (including parallel
  ones from `asyncio.gather`) nest under it.
- **Sessions:** `using_session(...)` puts `session.id` on every span, which groups runs into
  Langfuse sessions.
- **Agent graph:** every span carries `openinference.span.kind` and `langfuse.observation.type`
  (chain / agent / tool). Langfuse builds its agent graph from those types plus nesting.
- **Not traced:** the MCP server and the A2A client service are separate processes, so their
  internal spans are not linked. The calls to them are traced on our side as tool and agent
  spans.

Choosing a backend on this laptop:
- **Langfuse self-hosted** (`deploy/langfuse`) needs about 4–6 GB for ClickHouse, Postgres,
  Redis and MinIO. On 30 Sep it exhausted RAM next to Ollama and the Docker pull failed. Use it
  on a bigger machine.
- **Langfuse Cloud Hobby** is free with no card. Set `LANGFUSE_BASE_URL=https://cloud.langfuse.com`
  and the keys from its project settings.
- **Phoenix** (`python -m phoenix.server.main serve`, UI at http://localhost:6006) is light and
  works now. Verified on 30 Sep: OTLP POST returned 200.

## Mission Control

`python -m revamp.dashboard`, then open http://localhost:8700.

- **Graph:** the workflow is drawn from `workflow/graph.py::describe`, the same edge list that
  builds the ADK Workflow, so the picture cannot drift from the code.
  - Each node shows the agents or deterministic components working inside it.
  - The active node and the working agents light up.
  - Revisits show as `propose ×2`.
  - Back-edges (revise / replan / reject / propose) turn red when taken, with a count.
- **Tabs:**
  - Timeline
  - Agents (each call's full prompt and structured answer)
  - Tools (the audit tools and the Chief Diagnostician's MCP calls)
  - Proposals (with plan status)
  - Plan & budget: ledger bar, execution waves, rejections with reasons, conflict register,
    handoff and red-team actions
  - Client: rounds, reason codes, vetoes, messages, and the Engagement Lead's adaptations
  - Evidence: KB coverage and findings
  - Cost: orchestration time and tokens vs evidence time, reported separately
- **Controls:**
  - Launch an engagement (product, arm, seed, model routing, human approval) or an audit.
  - Human approval opens a dialog in the browser; the answer resumes the paused ADK workflow.
  - **Replay** animates any past run from its JSONL, without a model. This is the fallback for a
    live demo on a slow CPU.
- **Transport:** SSE (`/api/stream`), one-way and auto-reconnecting. Actions are plain POSTs.
- **Libraries:** Cytoscape.js and dagre are vendored in `static/vendor/`, so the demo works
  offline.

Why a custom dashboard as well as Langfuse: trace UIs show spans, and they do not know what a
budget ledger, a veto or a handoff rejection is. Our events speak the orchestration's own
vocabulary. This follows the AG-UI idea: typed run, step and tool events plus state snapshots.

## Viva questions

1. Why does one engagement appear as ONE trace even though agents run in parallel?
2. What would you have to add so the MCP server's internal spans join the same trace?
3. Why can the dashboard graph never disagree with the real workflow?
4. The dashboard shows `handoff → propose (revise ×2)`. What happened, and what stops a third
   time?
5. Why are events written to JSONL as well as streamed?
