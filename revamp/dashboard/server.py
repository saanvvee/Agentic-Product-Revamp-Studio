"""Mission Control: watch every agent, tool and orchestration step of a run, live.

    python -m revamp.dashboard            ->  http://localhost:8700

What it shows is the event stream from revamp/observe.py, pushed to the browser over
Server-Sent Events. The page draws the workflow graph (Cytoscape), lights up the
active node and the agents working inside it, and fills panels for agent prompts
and answers, tool calls, proposals, the budget ledger and plan, the conflict
register, the client negotiation, and the cost split.

It can also launch runs and audits, answer the human-approval pause from the
browser, and replay any past run from runs/events/*.jsonl without calling a model.

Langfuse (or Phoenix) holds the full span tree; each run links to its trace.
One run at a time: on a CPU-only laptop, two concurrent runs just halve each other.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from sse_starlette.sse import EventSourceResponse
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, HTMLResponse, JSONResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from revamp import evidence, observe, report, tracing
from revamp.kb import KnowledgeBase
from revamp.products import list_products, load_product
from revamp.settings import settings
from revamp.workflow.arms import ARMS

STATIC = Path(__file__).parent / "static"
log = logging.getLogger(__name__)


class State:
    task: asyncio.Task | None = None
    task_run_id: str | None = None
    approvals: dict[str, asyncio.Future] = {}


def _busy() -> bool:
    return State.task is not None and not State.task.done()


async def index(_: Request):
    return FileResponse(STATIC / "index.html")


async def meta(_: Request):
    conf = tracing.backends()
    return JSONResponse({
        "products": list_products(),
        "arms": [{"name": a.name, "description": a.description} for a in ARMS.values()],
        "modes": ["hybrid", "local", "gemini"], "default_mode": settings.model_mode,
        "tracing": {k: v["ui"] for k, v in conf.items()},
        "client_remote": bool(settings.client_url),
        "busy": _busy(), "active_run": State.task_run_id if _busy() else None,
    })


def _summary(path: Path) -> dict | None:
    first = last = None
    with path.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            ev = json.loads(line)
            first = first or ev
            last = ev
    if first is None:
        return None
    kind = "audit" if first["type"] == "audit_started" else "engagement"
    status = "running"
    if last["type"] in {"run_finished", "audit_finished"}:
        status = last.get("status", "done")
    return {"run_id": first["run_id"], "kind": kind, "product": first.get("product"),
            "arm": first.get("arm"), "seed": first.get("seed"), "started": first["ts"],
            "status": status}


async def runs(_: Request):
    d = settings.runs_dir / "events"
    files = sorted(d.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True) \
        if d.is_dir() else []
    out = [s for s in (_summary(p) for p in files[:60]) if s]
    return JSONResponse(out)


async def run_events(request: Request):
    return JSONResponse(observe.load_events(request.path_params["run_id"]))


async def stream(request: Request):
    """Live events. The browser replays history itself via /api/runs/{id}/events."""
    q = observe.bus.subscribe()

    async def gen():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=15)
                    yield {"event": "message", "data": json.dumps(ev, default=str)}
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": "{}"}
        finally:
            observe.bus.unsubscribe(q)
    return EventSourceResponse(gen())


def _launch(coro, run_id: str) -> None:
    async def wrapped():
        try:
            await coro
        except Exception:  # the run's own events already carry the error
            log.exception("run %s failed", run_id)
    State.task = asyncio.create_task(wrapped())
    State.task_run_id = run_id


async def start_run(request: Request):
    from revamp.workflow.runner import new_run_id, run_engagement
    if _busy():
        return JSONResponse({"error": f"run {State.task_run_id} is still going"}, 409)
    body = await request.json()
    product, arm = body.get("product", "umami"), body.get("arm", "A2")
    seed, mode = int(body.get("seed", 0)), body.get("mode") or None
    if product not in list_products() or arm not in ARMS:
        return JSONResponse({"error": "unknown product or arm"}, 400)
    run_id = new_run_id(product, arm, seed)
    approver = None
    if body.get("hitl"):
        async def approver(pending: dict) -> dict:
            fut = asyncio.get_running_loop().create_future()
            State.approvals[run_id] = fut
            try:
                return await fut
            finally:
                State.approvals.pop(run_id, None)
    _launch(run_engagement(product, arm, seed, mode=mode, approver=approver,
                           run_id=run_id, session=body.get("session")), run_id)
    return JSONResponse({"run_id": run_id})


async def approve(request: Request):
    fut = State.approvals.get(request.path_params["run_id"])
    if fut is None or fut.done():
        return JSONResponse({"error": "this run is not waiting for approval"}, 404)
    body = await request.json()
    fut.set_result({"rejected": list(body.get("rejected", []))})
    return JSONResponse({"ok": True})


async def start_audit(request: Request):
    from revamp.audit import STEPS, agentic_audit, audit_run_id, deterministic_audit
    if _busy():
        return JSONResponse({"error": f"run {State.task_run_id} is still going"}, 409)
    body = await request.json()
    product = body.get("product", "umami")
    if product not in list_products():
        return JSONResponse({"error": "unknown product"}, 400)
    p = load_product(product)
    if body.get("agentic"):
        # Mint the run id here too, so the client can link the report before the first
        # event lands instead of waiting for the audit to announce itself.
        run_id = audit_run_id(product)
        _launch(agentic_audit(p, max_tool_calls=int(body.get("max_tool_calls") or 8),
                              mode=body.get("mode") or None, run_id=run_id,
                              kb=KnowledgeBase(settings.kb_path, "team")), run_id)
        return JSONResponse({"run_id": run_id, "note": "agentic audit started"})
    run_id = audit_run_id(product)
    steps = tuple(s for s in body.get("steps", STEPS) if s in STEPS)
    _launch(deterministic_audit(p, KnowledgeBase(settings.kb_path, "team"),
                                body.get("target", "live"), steps, run_id=run_id), run_id)
    return JSONResponse({"run_id": run_id})


async def findings(request: Request):
    product = request.path_params["product"]
    fs = KnowledgeBase(settings.kb_path, "team").findings(product)
    return JSONResponse({"coverage": evidence.coverage(fs), "findings": [
        {"id": f.id, "category": f.category, "severity": f.severity, "title": f.title,
         "metric": f.metric, "value": f.value, "unit": f.unit, "tool": f.evidence.tool,
         "locator": f.evidence.locator} for f in fs]})


async def run_report(request: Request):
    try:
        return HTMLResponse(report.render(request.path_params["run_id"]))
    except (ValueError, StopIteration) as e:
        return HTMLResponse(f"<p>No report: {e}</p>", 404)


app = Starlette(routes=[
    Route("/", index),
    Route("/api/meta", meta),
    Route("/api/runs", runs),
    Route("/api/runs", start_run, methods=["POST"]),
    Route("/api/runs/{run_id}/events", run_events),
    Route("/api/runs/{run_id}/approval", approve, methods=["POST"]),
    Route("/api/runs/{run_id}/report", run_report),
    Route("/api/audit", start_audit, methods=["POST"]),
    Route("/api/findings/{product}", findings),
    Route("/api/stream", stream),
    Mount("/static", StaticFiles(directory=STATIC), name="static"),
])


def main() -> None:
    import argparse

    import uvicorn
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8700)
    a = ap.parse_args()
    logging.basicConfig(level=logging.WARNING)
    enabled = tracing.setup()
    print(f"Mission Control on http://localhost:{a.port}  (tracing: {enabled or 'off'})")
    uvicorn.run(app, host="localhost", port=a.port, log_level="warning")
