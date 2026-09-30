"""Run one engagement: one product, one arm, one seed."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
import inspect
from typing import Awaitable, Callable

from google.adk.models.base_llm import BaseLlm
from openinference.instrumentation import using_session
from google.adk.runners import InMemoryRunner
from google.genai import types

from revamp import observe, tracing
from revamp.contracts import Plan, RunRecord, stable_id, utcnow
from revamp.kb import KnowledgeBase
from revamp.llm.cache import current_ledger
from revamp.llm.registry import LOCAL_TIER, describe_route
from revamp.products import load_product
from revamp.settings import settings
from revamp.workflow import run_context as runs
from revamp.workflow.arms import ARMS
from revamp.workflow.graph import build, describe
from revamp.workflow.nodes import APPROVAL_ID


@dataclass
class RunResult:
    record: RunRecord
    plan: Plan | None
    log: list[str]
    stats: dict


def new_run_id(product: str, arm: str, seed: int) -> str:
    return stable_id("R", product, arm, str(seed), utcnow().isoformat())


async def run_engagement(product: str, arm: str = "A2", seed: int = 0, *,
                         kb_path: Path | None = None, mode: str | None = None,
                         overrides: dict[str, BaseLlm] | None = None,
                         approver: Callable[[dict], dict | Awaitable[dict]] | None = None,
                         run_id: str | None = None, session: str | None = None) -> RunResult:
    """`approver`: if given, human-in-the-loop is on. When the workflow pauses for
    approval of high-impact items, it is called (sync or async) with the pending
    items and must return {"rejected": [proposal ids]}. The CLI passes a terminal
    prompt; the dashboard passes a coroutine that waits for the browser's answer.

    `session` groups runs in Langfuse (default: one session per product and arm)."""
    kb_path = kb_path or settings.kb_path
    prod = load_product(product)
    run_id = run_id or new_run_id(product, arm, seed)
    record = RunRecord(run_id=run_id, product=product, arm=arm, seed=seed)
    rc = runs.RunContext(
        run_id=run_id, product=prod, arm=ARMS[arm], seed=seed,
        team_kb=KnowledgeBase(kb_path, "team"),
        # With a remote Client, this process holds no client-role handle at all,
        # except in A6, whose whole point is to show the constraints to the teams.
        client_kb=(KnowledgeBase(kb_path, "client")
                   if not settings.client_url or ARMS[arm].client_visible else None),
        crew=runs.Crew(seed=seed, mode=mode, overrides=overrides or {}), record=record,
        hitl=approver is not None)
    runs.register(rc)
    token = current_ledger.set(record.cost)  # every LLM call and tool run books here
    run_token = observe.current_run.set(run_id)  # every event is tagged with this run
    try:
        with using_session(session or f"{product}-{arm}"), observe.span(
                "engagement", "AGENT", input={"product": product, "arm": arm, "seed": seed},
                **{"langfuse.trace.name": f"revamp {product} {arm}",
                   "revamp.run_id": run_id}) as root:
            tid = observe.trace_id_hex()
            observe.emit("run_started", product=product, arm=arm, seed=seed,
                         arm_description=rc.arm.description, budget_days=prod.budget_days,
                         mode=mode or settings.model_mode, graph=describe(rc.arm),
                         models={r: describe_route(r, mode) for r in LOCAL_TIER},
                         trace_id=tid, trace_url=tracing.trace_url(tid))
            await _drive(rc, product, approver)
            observe.set_output(root, {"plan_id": record.plan_id, "status": record.status})
    except Exception as e:
        record.status, record.error = "failed", f"{type(e).__name__}: {e}"[:1000]
        rc.team_kb.save_run(record)
        observe.emit("run_error", error=record.error)
        raise
    finally:
        observe.emit("run_finished", status=record.status, plan_id=record.plan_id,
                     cost=record.cost.model_dump(), stats=rc.stats,
                     client_rounds=record.client_rounds)
        current_ledger.reset(token)
        observe.current_run.reset(run_token)
        _write_log(rc)
        runs.release(run_id)
        tracing.flush()
    return RunResult(record=record, plan=rc.current_plan, log=rc.log, stats=rc.stats)


async def _drive(rc: runs.RunContext, product: str, approver) -> None:
    workflow = build(rc.arm)
    runner = InMemoryRunner(agent=workflow, app_name="revamp")
    session = await runner.session_service.create_session(
        app_name="revamp", user_id="consultancy", state={"run_id": rc.run_id})
    msg = types.Content(role="user", parts=[types.Part(text=f"Revamp {product}")])
    while True:
        async for _ in runner.run_async(user_id="consultancy", session_id=session.id,
                                        new_message=msg):
            pass
        if rc.pending_approval is None:
            break
        # Paused at the approval node: ask the human, resume the same session.
        observe.emit("approval_requested", **rc.pending_approval)
        answer = approver(rc.pending_approval)
        if inspect.isawaitable(answer):
            answer = await answer
        rejected = list(answer.get("rejected", []))
        observe.emit("approval_resolved", rejected=rejected)
        msg = types.Content(role="user", parts=[types.Part(
            function_response=types.FunctionResponse(
                id=APPROVAL_ID, name="adk_request_input", response={"rejected": rejected}))])
        rc.pending_approval = None


def _write_log(rc: runs.RunContext) -> None:
    out = settings.runs_dir / "logs"
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{rc.run_id}.json").write_text(json.dumps({
        "record": json.loads(rc.record.model_dump_json()),
        # Which model served each agent: needed to compare runs fairly.
        "models": {r: describe_route(r, rc.crew.mode) for r in LOCAL_TIER},
        "log": rc.log, "stats": rc.stats,
        "plan": json.loads(rc.current_plan.model_dump_json()) if rc.current_plan else None,
    }, indent=1), encoding="utf-8")
