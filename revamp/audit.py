"""Evidence gathering, run once per product and shared by every arm.

Two ways to fill the KB:
  * `deterministic_audit`: every tool, in a fixed order, no LLM. The G1 gate
    ("audit a product with no LLM involved") and the reproducible default for
    evaluation, because every arm must see IDENTICAL evidence.
  * `agentic_audit`: the Chief Diagnostician chooses which audits to run over MCP.
    This is the agentic version, used for demos and for measuring how much evidence
    the agent buys versus the deterministic sweep.

An audit is a run like any other one: it gets a run id, a `RunRecord` in the KB, an
event stream under `runs/events/`, one OpenTelemetry trace, and an HTML report from
`revamp.report`. That is what makes an audit verifiable after the fact instead of
just a wall of terminal output.

Each step is emitted as `node_started` / `node_finished`, so the dashboard draws a
deterministic audit as the chain it is (START -> seo -> pricing -> ...) and the
inspector can open a step. The `audit-` arm prefix is how `report.render` tells an
audit from an engagement, and `evaluation.run_metrics` ignores any record without a
plan, so the audit arms stay out of the experiment.
"""

from __future__ import annotations

import logging
import time

from revamp import observe, tracing
from revamp.contracts import CostLedger, Finding, RunRecord, utcnow
from revamp.kb import KnowledgeBase
from revamp.llm.cache import current_ledger
from revamp.products import Product
from revamp.settings import settings
from revamp.tools import browser, code, lighthouse, pricing, seo, voice

log = logging.getLogger(__name__)
STEPS = ("seo", "pricing", "voice", "code", "performance", "accessibility", "journeys")

# What the Chief Diagnostician's MCP toolset offers. Declared here so the dashboard
# never hardcodes the tool list in JavaScript and cannot drift from the server.
MCP_TOOLS = ("coverage", "list_findings", "get_finding") + tuple(f"audit_{s}" for s in STEPS)

ARM_DET, ARM_AGENTIC, HUB = "audit-det", "audit-agentic", "chief_diagnostician"


def is_audit(arm: str) -> bool:
    return arm in (ARM_DET, ARM_AGENTIC)


async def _step(name: str, p: Product, target: str) -> list[Finding]:
    base = p.live.base_url if target == "live" else p.local_base_url
    tgt = "live" if target == "live" else f"local:{p.ref}"
    if base is None:
        raise ValueError(f"no base URL for target {target}")
    if name == "seo":
        return await seo.seo_audit(p.name, base, p.live.pages, tgt)
    if name == "pricing":
        return await pricing.pricing_snapshots(p.name, p.live.pricing_url,
                                               p.live.competitor_pricing)
    if name == "voice":
        out = await voice.github_issues(p.name, p.repo, p.cutoff)
        if p.forum:
            out += await voice.discourse_topics(p.name, p.forum.base_url, p.cutoff)
        return out
    if name == "code":
        return await code.code_audit(p.name, p.repo, p.ref, cutoff=p.cutoff)
    if name == "performance":
        return await lighthouse.performance_audit(p.name, base, p.live.pages, tgt)
    if name == "accessibility":
        return await browser.axe_audit(p.name, base, p.live.pages, tgt)
    if name == "journeys":
        out = []
        for flow in p.flows:
            f, _ = await browser.run_journey(p.name, base, flow.name, flow.steps, tgt)
            out += f
        return out
    raise KeyError(name)


def step_input(p: Product, name: str, target: str) -> dict:
    """What a step was asked to measure. Recorded on the tool call so the report and
    the dashboard show the input of a step, not only its output."""
    if name in ("seo", "performance", "accessibility"):
        return {"target": target, "pages": list(p.live.pages)}
    if name == "pricing":
        return {"pricing_url": p.live.pricing_url,
                "competitors": sorted(p.live.competitor_pricing)}
    if name == "voice":
        return {"repo": p.repo, "cutoff": p.cutoff.isoformat(),
                "forum": p.forum.base_url if p.forum else None}
    if name == "code":
        return {"repo": p.repo, "ref": p.ref, "cutoff": p.cutoff.isoformat()}
    if name == "journeys":
        return {"flows": [f.name for f in p.flows]}
    raise KeyError(name)


def audit_run_id(product: str) -> str:
    return f"audit-{product}-{time.strftime('%Y%m%d-%H%M%S')}"


def _record(run_id: str, p: Product, arm: str, ledger: CostLedger, seed: int = 0) -> RunRecord:
    return RunRecord(run_id=run_id, product=p.name, arm=arm, seed=seed, cost=ledger)


def _close(record: RunRecord, kb: KnowledgeBase, ledger: CostLedger, span,
           **fields) -> dict:
    """Save the run record, close the trace and announce the end of the audit.

    Everything an audit needs to be reported on later is already in the two files
    this writes: the record in the KB and the events in `runs/events/`.
    """
    record.finished_at = utcnow()
    record.cost = ledger
    kb.save_run(record)
    observe.set_output(span, {"status": record.status, "run_id": record.run_id})
    observe.emit("audit_finished", status=record.status, error=record.error or None,
                 cost=ledger.model_dump(), **fields)
    tracing.flush()
    return {"run_id": record.run_id, "product": record.product, "arm": record.arm,
            "status": record.status, "cost": ledger.model_dump()}


async def deterministic_audit(p: Product, kb: KnowledgeBase, target: str = "live",
                              steps: tuple[str, ...] = STEPS,
                              run_id: str | None = None) -> dict:
    """Every step in order, no model involved. Returns the per-step report plus the
    totals the CLI and the HTML report need."""
    run_id = run_id or audit_run_id(p.name)
    ledger = CostLedger()
    token = current_ledger.set(ledger)
    run_token = observe.current_run.set(run_id)
    record = _record(run_id, p, ARM_DET, ledger)
    report: dict[str, str] = {}
    detail: list[dict] = []
    total = added = 0
    with observe.span("audit", "AGENT", input={"product": p.name, "target": target,
                                               "steps": list(steps), "mode": "deterministic"},
                      **{"langfuse.trace.name": f"revamp audit {p.name}",
                         "revamp.run_id": run_id}) as root:
        tid = observe.trace_id_hex()
        try:
            observe.emit("audit_started", product=p.name, target=target,
                         mode="deterministic", steps=list(steps), agentic=False,
                         tools=list(MCP_TOOLS), trace_id=tid,
                         trace_url=tracing.trace_url(tid))
            for name in steps:
                t0 = time.perf_counter()
                args = step_input(p, name, target)
                observe.emit("node_started", node=name)
                observe.emit("tool_started", tool=name, agent="deterministic", node=name,
                             args=args)
                with observe.span(f"tool.{name}", "TOOL", input=args) as s:
                    count, new, ids, err = 0, 0, [], ""
                    try:
                        found = await _step(name, p, target)
                        new = kb.add_findings(found)
                        count, ids = len(found), [f.id for f in found]
                        line = (f"{count} findings ({new} new) in "
                                f"{time.perf_counter() - t0:.0f}s")
                    except Exception as e:  # one failing tool must not sink the audit
                        line = f"SKIPPED: {type(e).__name__}: {str(e)[:160]}"
                        err = f"{type(e).__name__}: {e}"[:300]
                        log.warning("audit step %s failed: %s", name, e)
                    report[name] = line
                    total, added = total + count, added + new
                    observe.set_output(s, line)
                ms = round((time.perf_counter() - t0) * 1000)
                detail.append({"step": name, "count": count, "new": new, "ms": ms,
                               "error": err or None, "finding_ids": ids})
                observe.emit("tool_finished", tool=name, agent="deterministic", node=name,
                             result=line, count=count, new=new, finding_ids=ids,
                             error=err or None, ms=ms)
                observe.emit("node_finished", node=name, route=None, output=line, ms=ms)
            record.status = "done"
        except BaseException as e:
            record.status, record.error = "failed", f"{type(e).__name__}: {e}"[:1000]
            observe.emit("audit_error", error=record.error)
            raise
        finally:
            out = _close(record, kb, ledger, root, report=report, steps=list(steps),
                         findings=total, new=added, agentic=False)
            current_ledger.reset(token)
            observe.current_run.reset(run_token)
    out.update({"mode": "deterministic", "report": report, "results": detail,
                "findings": total, "new": added,
                "evidence_seconds": round(ledger.evidence_seconds)})
    return out


async def agentic_audit(p: Product, max_tool_calls: int = 8, seed: int = 0,
                        mode: str | None = None, run_id: str | None = None,
                        kb: KnowledgeBase | None = None) -> dict:
    """The Chief Diagnostician runs audits through the MCP server (child process).

    The tools execute in the child, so the parent's `evidence_timer` never sees their
    wall time; the tool callbacks in `agents/diagnostics.py` book it here instead.
    """
    from revamp.agents.diagnostics import chief_diagnostician
    from revamp.agents.runtime import ask
    from revamp.agents.schemas import DiagnosisReport

    kb = kb or KnowledgeBase(settings.kb_path, "team")
    run_id = run_id or audit_run_id(p.name)
    ledger = CostLedger()
    token = current_ledger.set(ledger)
    run_token = observe.current_run.set(run_id)
    record = _record(run_id, p, ARM_AGENTIC, ledger, seed)
    before = len(kb.finding_ids(p.name))
    agent = None
    diagnosis = None
    with observe.span("audit", "AGENT", input={"product": p.name, "target": "live",
                                               "mode": "agentic",
                                               "max_tool_calls": max_tool_calls},
                      **{"langfuse.trace.name": f"revamp audit {p.name} (agentic)",
                         "revamp.run_id": run_id}) as root:
        tid = observe.trace_id_hex()
        try:
            observe.emit("audit_started", product=p.name, target="live", agentic=True,
                         mode="agentic", steps=[], tools=list(MCP_TOOLS),
                         max_tool_calls=max_tool_calls, seed=seed,
                         trace_id=tid, trace_url=tracing.trace_url(tid))
            agent = chief_diagnostician(p.name, max_tool_calls=max_tool_calls, seed=seed,
                                        mode=mode)
            t0 = time.perf_counter()
            observe.emit("node_started", node=HUB)
            diagnosis = await ask(agent, f"Audit the product {p.name} ({p.live.base_url}, "
                                         f"github.com/{p.repo} at {p.ref}).", DiagnosisReport)
            ms = round((time.perf_counter() - t0) * 1000)
            observe.emit("node_finished", node=HUB, route=None,
                         output=diagnosis.model_dump(mode="json"), ms=ms)
            record.status = "done"
        except BaseException as e:
            record.status, record.error = "failed", f"{type(e).__name__}: {e}"[:1000]
            observe.emit("node_error", node=HUB, error=record.error)
            observe.emit("audit_error", error=record.error)
            raise
        finally:
            after = len(kb.finding_ids(p.name))
            out = _close(record, kb, ledger, root, steps=[], agentic=True,
                         tool_calls=agent.before_tool_callback.calls["n"] if agent else 0,
                         new_findings=after - before, kb_findings=after,
                         diagnosis=diagnosis.model_dump(mode="json") if diagnosis else None)
            current_ledger.reset(token)
            observe.current_run.reset(run_token)
    out["mode"] = "agentic"
    out["report"] = diagnosis.model_dump(mode="json") if diagnosis else None
    return out