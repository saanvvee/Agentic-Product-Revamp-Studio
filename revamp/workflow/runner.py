"""Run one engagement: one product, one arm, one seed."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from google.adk.models.base_llm import BaseLlm
from google.adk.runners import InMemoryRunner
from google.genai import types

from revamp.contracts import Plan, RunRecord, stable_id, utcnow
from revamp.kb import KnowledgeBase
from revamp.llm.cache import current_ledger
from revamp.products import load_product
from revamp.settings import settings
from revamp.workflow import run_context as runs
from revamp.workflow.arms import ARMS
from revamp.workflow.graph import build
from revamp.workflow.nodes import APPROVAL_ID


@dataclass
class RunResult:
    record: RunRecord
    plan: Plan | None
    log: list[str]
    stats: dict


async def run_engagement(product: str, arm: str = "A2", seed: int = 0, *,
                         kb_path: Path | None = None, mode: str | None = None,
                         overrides: dict[str, BaseLlm] | None = None,
                         approver: Callable[[dict], dict] | None = None) -> RunResult:
    """`approver`: if given, human-in-the-loop is on. When the workflow pauses for
    approval of high-impact items, it is called with the pending items and must
    return {"rejected": [proposal ids]}. The CLI passes a terminal prompt."""
    kb_path = kb_path or settings.kb_path
    prod = load_product(product)
    run_id = stable_id("R", product, arm, str(seed), utcnow().isoformat())
    record = RunRecord(run_id=run_id, product=product, arm=arm, seed=seed)
    rc = runs.RunContext(
        run_id=run_id, product=prod, arm=ARMS[arm], seed=seed,
        team_kb=KnowledgeBase(kb_path, "team"), client_kb=KnowledgeBase(kb_path, "client"),
        crew=runs.Crew(seed=seed, mode=mode, overrides=overrides or {}), record=record,
        hitl=approver is not None)
    runs.register(rc)
    token = current_ledger.set(record.cost)  # every LLM call and tool run books here
    try:
        workflow = build(rc.arm)
        runner = InMemoryRunner(agent=workflow, app_name="revamp")
        session = await runner.session_service.create_session(
            app_name="revamp", user_id="consultancy", state={"run_id": run_id})
        msg = types.Content(role="user", parts=[types.Part(text=f"Revamp {product}")])
        while True:
            async for _ in runner.run_async(user_id="consultancy", session_id=session.id,
                                            new_message=msg):
                pass
            if rc.pending_approval is None:
                break
            # Paused at the approval node: ask the human, resume the same session.
            answer = approver(rc.pending_approval)
            msg = types.Content(role="user", parts=[types.Part(
                function_response=types.FunctionResponse(
                    id=APPROVAL_ID, name="adk_request_input",
                    response={"rejected": list(answer.get("rejected", []))}))])
            rc.pending_approval = None
    except Exception as e:
        record.status, record.error = "failed", f"{type(e).__name__}: {e}"[:1000]
        rc.team_kb.save_run(record)
        raise
    finally:
        current_ledger.reset(token)
        _write_log(rc)
        runs.release(run_id)
    return RunResult(record=record, plan=rc.current_plan, log=rc.log, stats=rc.stats)


def _write_log(rc: runs.RunContext) -> None:
    out = settings.runs_dir / "logs"
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{rc.run_id}.json").write_text(json.dumps({
        "record": json.loads(rc.record.model_dump_json()),
        "log": rc.log, "stats": rc.stats,
        "plan": json.loads(rc.current_plan.model_dump_json()) if rc.current_plan else None,
    }, indent=1), encoding="utf-8")
