"""Observability: one event stream for the live dashboard, one trace for Langfuse.

Two audiences, two mechanisms, one call site:

  * Events (`emit`): small JSON records of what the orchestration is doing: node
    started or finished, an agent's prompt and answer, a plan, a verdict. They go to
    in-process subscribers (the dashboard's SSE stream) and to
    runs/events/<run_id>.jsonl, so any past run can be replayed without an LLM.
  * Spans (`span`, `traced_node`): OpenTelemetry spans exported over OTLP to
    Langfuse and/or Phoenix (revamp/tracing.py). ADK's own agent and model spans
    (OpenInference instrumentor) nest under ours, so a run is ONE trace whose tree
    mirrors the workflow graph.

Neither changes behaviour: with no subscribers and no tracer configured, both
are no-ops apart from the JSONL file.
"""

from __future__ import annotations

import asyncio
import contextlib
import contextvars
import functools
import inspect
import json
import time
from typing import Any

from opentelemetry import trace

from revamp.settings import settings

current_run: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "current_run", default=None)
tracer = trace.get_tracer("revamp")

_KIND_TO_LANGFUSE = {"CHAIN": "chain", "AGENT": "agent", "TOOL": "tool",
                     "GUARDRAIL": "guardrail", "EVALUATOR": "evaluator"}


def _jsonable(x: Any) -> Any:
    try:
        json.dumps(x)
        return x
    except TypeError:
        if hasattr(x, "model_dump"):
            return x.model_dump(mode="json")
        return str(x)


# ------------------------------------------------------------------ events

class EventBus:
    def __init__(self) -> None:
        self._subs: set[asyncio.Queue] = set()
        self._seq = 0

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=5000)
        self._subs.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subs.discard(q)

    def emit(self, type_: str, run_id: str | None = None, **fields: Any) -> dict | None:
        run_id = run_id or current_run.get()
        if run_id is None:
            return None
        self._seq += 1
        ev = {"v": 1, "seq": self._seq, "ts": time.time(), "run_id": run_id, "type": type_,
              **{k: _jsonable(v) for k, v in fields.items()}}
        path = settings.runs_dir / "events" / f"{run_id}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(ev, default=str) + "\n")
        for q in list(self._subs):
            try:
                q.put_nowait(ev)
            except asyncio.QueueFull:
                pass  # a stalled browser tab must never block the engagement
        return ev


bus = EventBus()
emit = bus.emit


def load_events(run_id: str) -> list[dict]:
    path = settings.runs_dir / "events" / f"{run_id}.jsonl"
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


# ------------------------------------------------------------------ spans

@contextlib.contextmanager
def span(name: str, kind: str = "CHAIN", input: Any = None, **attrs: Any):
    """An OpenTelemetry span typed for both OpenInference (Phoenix) and Langfuse, so
    Langfuse draws it in the agent graph as a chain, agent, tool or guardrail."""
    with tracer.start_as_current_span(name) as s:
        s.set_attribute("openinference.span.kind", kind)
        s.set_attribute("langfuse.observation.type", _KIND_TO_LANGFUSE.get(kind, "span"))
        if input is not None:
            s.set_attribute("input.value", json.dumps(_jsonable(input), default=str)[:20000])
        for k, v in attrs.items():
            if v is not None:
                s.set_attribute(k, v if isinstance(v, (str, int, float, bool)) else str(v))
        yield s


def set_output(s, output: Any) -> None:
    s.set_attribute("output.value", json.dumps(_jsonable(output), default=str)[:20000])


def trace_id_hex() -> str | None:
    ctx = trace.get_current_span().get_span_context()
    return format(ctx.trace_id, "032x") if ctx.is_valid else None


def traced_node(fn):
    """Wrap a workflow node: a CHAIN span plus node_started / node_finished events.

    The wrapper keeps the function's signature (ADK binds node parameters by name)
    and its kind: an async generator node stays an async generator."""
    name = fn.__name__

    def _finish(s, ctx, out, t0):
        route = getattr(ctx, "route", None)
        set_output(s, out)
        emit("node_finished", node=name, route=route, output=out,
             ms=round((time.perf_counter() - t0) * 1000))

    if inspect.isasyncgenfunction(fn):
        @functools.wraps(fn)
        async def gen_wrapper(ctx, *a, **kw):
            t0 = time.perf_counter()
            emit("node_started", node=name)
            with span(f"node.{name}", "CHAIN") as s:
                last = None
                async for item in fn(ctx, *a, **kw):
                    last = item
                    yield item
                _finish(s, ctx, last if isinstance(last, dict) else {"paused": True}, t0)
        return gen_wrapper

    @functools.wraps(fn)
    async def wrapper(ctx, *a, **kw):
        t0 = time.perf_counter()
        emit("node_started", node=name)
        with span(f"node.{name}", "CHAIN") as s:
            try:
                out = await fn(ctx, *a, **kw)
            except Exception as e:
                emit("node_error", node=name, error=f"{type(e).__name__}: {e}"[:500])
                raise
            _finish(s, ctx, out, t0)
            return out
    return wrapper
