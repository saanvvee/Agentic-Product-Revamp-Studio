"""Workflow nodes. One function per step of the engagement.

Conventions (ADK 2.9 FunctionNode):
  * each node takes `ctx`; routing is `ctx.route = "<edge label>"`;
  * session state holds only plain values (ids, counters, budget); per-run objects
    (KB handles, agents, proposals) come from run_context.get(run_id);
  * every loop counter is checked here, in code (invariant 4).
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from google.adk.events.request_input import RequestInput

from revamp.agents.runtime import ask
from revamp.agents.schemas import (
    ClientAdaptation,
    ConflictReport,
    EngagementBrief,
    HandoffReview,
    JourneyReport,
    RedTeamReport,
    SingleLlmPlan,
    TeamProposals,
    VoiceReport,
)
from revamp import client_service, observe
from revamp.arbitration.plan import build_plan, plan_without_arbitration
from revamp.arbitration.sequencer import find_cycle
from revamp.contracts import (
    Conflict,
    Evidence,
    Finding,
    Plan,
    PlanItem,
    Proposal,
    stable_id,
    utcnow,
)
from revamp.llm.registry import family_for
from revamp.settings import settings
from revamp.workflow import prompts
from revamp.workflow import run_context as runs
from revamp.workflow.arms import CLIENT_CAP, HANDOFF_CAP, RED_TEAM_CAP

TEAMS = ("design", "engineering", "product_pricing")
ABBR = {"design": "DE", "engineering": "EN", "product_pricing": "PP", "single_llm": "SL"}


def _rc(ctx) -> runs.RunContext:
    return runs.get(ctx.state["run_id"])


def _findings(rc: runs.RunContext) -> list[Finding]:
    return rc.team_kb.findings(rc.product.name)


# ------------------------------------------------------------------ conversion

def drafts_to_proposals(team: str, drafts: TeamProposals | SingleLlmPlan, known: set[str],
                        tag: str, stats: dict) -> list[Proposal]:
    """LLM drafts -> frozen Proposals. Provenance is enforced HERE (invariant 2):
    unknown finding ids are removed, and a draft left with none is discarded."""
    items = drafts.proposals if isinstance(drafts, TeamProposals) else drafts.items
    ref_to_id: dict[str, str] = {}
    staged = []
    for k, d in enumerate(items, 1):
        pid = f"{ABBR[team]}{tag}-{k}"
        ref_to_id[getattr(d, "ref", str(k))] = pid
        staged.append((pid, d))
    out = []
    for pid, d in staged:
        cited = [f for f in d.finding_ids if f in known]
        stats["citations_total"] = stats.get("citations_total", 0) + len(d.finding_ids)
        stats["citations_invalid"] = stats.get("citations_invalid", 0) + \
            len(d.finding_ids) - len(cited)
        if not cited:
            stats["unsupported_dropped"] = stats.get("unsupported_dropped", 0) + 1
            continue
        deps = [ref_to_id[r] for r in getattr(d, "depends_on", []) if r in ref_to_id]
        out.append(Proposal(
            id=pid, team=team, title=d.title, change=d.change,
            rationale=getattr(d, "rationale", ""), finding_ids=tuple(dict.fromkeys(cited)),
            cost_days=d.cost_days, value=d.value,
            depends_on=tuple(x for x in deps if x != pid),
            areas=tuple(d.areas), risk=getattr(d, "risk", "low")))
    return out


# ------------------------------------------------------------------ nodes

async def init(ctx):
    rc = _rc(ctx)
    ctx.state["budget_days"] = rc.product.budget_days
    for key, default in (("blocked", {}), ("feedback", {}), ("teams_to_run", list(TEAMS)),
                         ("focus", []), ("voice_themes", []), ("journey_ids", []),
                         ("conflicts", []), ("client_history", []), ("reviewed", []),
                         ("red_reviewed", []), ("conflict_sig", ""), ("handoff_rounds", 0),
                         ("red_team_rounds", 0), ("client_rounds", 0), ("propose_rounds", {})):
        ctx.state[key] = default
    n = len(_findings(rc))
    if n == 0:
        raise RuntimeError(f"no findings for {rc.product.name}; run `revamp audit` first")
    rc.note(f"run {rc.run_id}: {rc.product.name}, arm {rc.arm.name}, seed {rc.seed}, "
            f"{n} findings in KB")
    return {"findings": n}


async def brief(ctx):
    rc = _rc(ctx)
    out = await ask(rc.crew.get("engagement_lead"),
                    prompts.brief_prompt(rc.product, _findings(rc), ctx.state["budget_days"]),
                    EngagementBrief)
    ctx.state["focus"] = out.focus[:4]
    rc.note(f"brief: focus {out.focus[:4]}")
    return out.model_dump()


async def _voice(rc) -> list[dict]:
    fs = _findings(rc)
    if not any(f.category == "user_voice" for f in fs):
        return []
    out = await ask(rc.crew.get("voice_of_customer"), prompts.voice_prompt(rc.product, fs),
                    VoiceReport)
    known = {f.id for f in fs}
    themes = []
    for t in out.themes:
        ids = [i for i in t.finding_ids if i in known]
        if ids:  # a theme with no real post behind it is dropped (provenance)
            themes.append({**t.model_dump(), "finding_ids": ids})
    return themes


async def _journey(rc) -> list[str]:
    fs = _findings(rc)
    steps = [f for f in fs if f.category == "journey" and "screenshot" in f.tags
             and f.evidence.artifact_path and Path(f.evidence.artifact_path).is_file()][:6]
    if not steps:
        return []
    locators = {s.evidence.locator for s in steps}
    facts = [f for f in fs if f.category == "journey" and f.severity != "info"
             and f.evidence.locator in locators and "llm_observation" not in f.tags]
    images = []
    vision = "journey_auditor" in rc.crew.overrides or \
        family_for("journey_auditor", rc.crew.mode) == "gemini"
    if vision:  # the local 4B model has no vision; it then reasons from step facts only
        for s in steps:
            data = Path(s.evidence.artifact_path).read_bytes()
            if len(data) < 4_000_000:
                images.append((data, "image/png"))
    out = await ask(rc.crew.get("journey_auditor"), prompts.journey_prompt(rc.product, steps, facts),
                    JourneyReport, images=images)
    by_id = {s.id: s for s in steps}
    new = []
    for issue in out.issues:
        step = by_id.get(issue.screenshot_finding_id)
        if step is None:
            continue  # must point at a real screenshot
        new.append(Finding.make(
            product=rc.product.name, category="journey", title=issue.issue[:200],
            severity=issue.severity,
            evidence=Evidence(tool="journey_auditor_vision", target=step.evidence.target,
                              locator=step.evidence.locator,
                              artifact_path=step.evidence.artifact_path),
            tags=("llm_observation", issue.area)))
    rc.team_kb.add_findings(new)
    return [f.id for f in new]


async def perspectives(ctx):
    """Voice of Customer and Journey Auditor run concurrently: independent inputs."""
    rc = _rc(ctx)
    themes, journey_ids = await asyncio.gather(_voice(rc), _journey(rc))
    ctx.state["voice_themes"] = themes
    ctx.state["journey_ids"] = journey_ids
    observe.emit("perspectives", themes=themes, journey_issues=[
        {"id": f.id, "title": f.title, "severity": f.severity}
        for f in _findings(rc) if f.id in set(journey_ids)])
    rc.note(f"perspectives: {sum(t['is_signal'] for t in themes)} signal themes, "
            f"{len(journey_ids)} journey issues")
    return {"themes": len(themes), "journey_issues": len(journey_ids)}


async def _propose_one(rc, ctx_state: dict, team: str, round_no: int) -> list[Proposal]:
    fs = _findings(rc)
    journey = [f for f in fs if f.id in set(ctx_state["journey_ids"])]
    constraints = rc.client_kb.constraints(rc.product.name) if rc.arm.client_visible else ()
    prompt = prompts.team_prompt(rc.product, team, ctx_state["budget_days"], ctx_state["focus"],
                                 [f for f in fs if "llm_observation" not in f.tags],
                                 ctx_state["voice_themes"], journey,
                                 ctx_state["feedback"].get(team, ""), constraints)
    drafts = await ask(rc.crew.get(team), prompt, TeamProposals)
    return drafts_to_proposals(team, drafts, {f.id for f in fs}, str(round_no), rc.stats)


async def propose(ctx):
    rc = _rc(ctx)
    teams = list(ctx.state["teams_to_run"])
    rounds = dict(ctx.state["propose_rounds"])
    for t in teams:
        rounds[t] = rounds.get(t, 0) + 1
    snapshot = ctx.state.to_dict()
    results = await asyncio.gather(*[_propose_one(rc, snapshot, t, rounds[t]) for t in teams])
    for team, props in zip(teams, results):
        # A team's new set replaces its old one; other teams' proposals are kept.
        rc.proposals = {k: v for k, v in rc.proposals.items() if v.team != team}
        for p in props:
            rc.team_kb.add_proposal(rc.run_id, rc.product.name, p)
            rc.proposals[p.id] = p
    feedback = {k: v for k, v in ctx.state["feedback"].items() if k not in teams}
    ctx.state["feedback"] = feedback
    ctx.state["teams_to_run"] = list(TEAMS)
    ctx.state["propose_rounds"] = rounds
    observe.emit("proposals", teams=teams, proposals=[
        p.model_dump(mode="json") for p in rc.proposals.values()])
    rc.note(f"propose: {', '.join(f'{t}={len(r)}' for t, r in zip(teams, results))}")
    return {"proposals": len(rc.proposals)}


async def handoff(ctx):
    rc = _rc(ctx)
    ctx.route = "ok"
    if not rc.arm.handoff_rejection:
        return {"skipped": True}
    reviewed = set(ctx.state["reviewed"])
    todo = [p for p in rc.proposals.values() if p.team != "engineering" and p.id not in reviewed]
    if not todo:
        return {"reviewed": 0}
    out = await ask(rc.crew.get("handoff_reviewer"), prompts.handoff_prompt(rc.product, todo),
                    HandoffReview)
    ctx.state["reviewed"] = sorted(reviewed | {p.id for p in todo})
    rejects = [d for d in out.decisions
               if d.decision == "reject" and d.proposal_id in {p.id for p in todo}]
    rc.record.handoff_rejections += len(rejects)
    observe.emit("handoff_review", reviewed=[p.id for p in todo], rejected=[
        {"id": d.proposal_id, "reason": d.reason, "realistic_cost_days": d.realistic_cost_days}
        for d in rejects], round=ctx.state["handoff_rounds"])
    if not rejects:
        return {"rejected": 0}

    if ctx.state["handoff_rounds"] < HANDOFF_CAP:
        feedback = dict(ctx.state["feedback"])
        for d in rejects:
            team = rc.proposals[d.proposal_id].team
            cost = f" Engineering estimates {d.realistic_cost_days:g} days." \
                if d.realistic_cost_days else ""
            feedback[team] = feedback.get(team, "") + \
                f"- {d.proposal_id} rejected by Engineering: {d.reason}.{cost}\n"
        ctx.state["feedback"] = feedback
        ctx.state["teams_to_run"] = sorted({rc.proposals[d.proposal_id].team for d in rejects})
        ctx.state["handoff_rounds"] += 1
        ctx.route = "revise"
        rc.note(f"handoff: {len(rejects)} rejected, sent back to {ctx.state['teams_to_run']}")
        return {"rejected": len(rejects), "route": "revise"}

    # Cap reached: Engineering's cost estimate stands in for the proposer's.
    for d in rejects:
        p = rc.proposals[d.proposal_id]
        if d.realistic_cost_days and d.realistic_cost_days > p.cost_days:
            p2 = p.model_copy(update={"cost_days": min(d.realistic_cost_days, 200.0),
                                      "revision": p.revision + 1})
            rc.proposals[p.id] = p2
            rc.team_kb.add_proposal(rc.run_id, rc.product.name, p2)
    rc.note(f"handoff: cap reached, {len(rejects)} costs re-estimated by Engineering")
    return {"rejected": len(rejects), "route": "ok"}


async def conflicts(ctx):
    rc = _rc(ctx)
    if not rc.arm.conflict_detection or len(rc.proposals) < 2:
        return {"skipped": True}
    sig = stable_id("S", *sorted(f"{p.id}r{p.revision}" for p in rc.proposals.values()))
    if sig == ctx.state["conflict_sig"]:
        return {"unchanged": True}
    out = await ask(rc.crew.get("conflict_detector"),
                    prompts.conflict_prompt(rc.product, list(rc.proposals.values())),
                    ConflictReport)
    found = []
    for c in out.conflicts:
        if c.a in rc.proposals and c.b in rc.proposals and c.a != c.b:
            found.append(Conflict(id=stable_id("C", *sorted([c.a, c.b])), a=c.a, b=c.b,
                                  kind=c.kind, explanation=c.explanation,
                                  exclusive=c.exclusive).model_dump())
    ctx.state["conflicts"] = found
    ctx.state["conflict_sig"] = sig
    observe.emit("conflicts", conflicts=found)
    rc.note(f"conflicts: {len(found)} ({sum(c['exclusive'] for c in found)} exclusive)")
    return {"conflicts": len(found)}


def _break_cycles(props: list[Proposal], blocked: dict) -> dict:
    live = [p for p in props if p.id not in blocked]
    while (cycle := find_cycle(live)):
        victim = cycle[0]
        blocked[victim] = ["dependency", f"dependency cycle {' -> '.join(cycle)}"]
        live = [p for p in live if p.id != victim]
    return blocked


async def allocate(ctx):
    rc = _rc(ctx)
    props = list(rc.proposals.values())
    if not rc.arm.arbitration:
        plan = plan_without_arbitration(product=rc.product.name, arm=rc.arm.name,
                                        budget_days=ctx.state["budget_days"], proposals=props)
    else:
        blocked = _break_cycles(props, dict(ctx.state["blocked"]))
        ctx.state["blocked"] = blocked
        budget = ctx.state["budget_days"] if rc.arm.budget_limited else \
            sum(p.cost_days for p in props)
        plan = build_plan(product=rc.product.name, arm=rc.arm.name,
                          round=ctx.state["client_rounds"], budget_days=budget, proposals=props,
                          conflicts=[Conflict(**c) for c in ctx.state["conflicts"]],
                          blocked={k: tuple(v) for k, v in blocked.items()})
    rc.team_kb.add_plan(rc.run_id, plan)
    rc.current_plan = plan
    ctx.state["plan_id"] = plan.id
    observe.emit("plan", plan=plan.model_dump(mode="json"), arbitrated=rc.arm.arbitration,
                 titles={p.id: p.title for p in props}, teams={p.id: p.team for p in props})
    rc.note(f"allocate: {len(plan.items)} items, {plan.total_cost:g}/{plan.budget_days:g}d, "
            f"value {plan.total_value}, {len(plan.rejected)} rejected")
    return {"items": len(plan.items), "cost": plan.total_cost}


async def red_team(ctx):
    rc = _rc(ctx)
    ctx.route = "ok"
    plan: Plan = rc.current_plan
    reviewed = set(ctx.state["red_reviewed"])
    todo = [i for i in plan.items if i.proposal_id not in reviewed]
    if not rc.arm.red_team or not todo:
        return {"skipped": True}
    chains = {i.proposal_id: rc.team_kb.evidence_chain(rc.run_id, i.proposal_id) for i in todo}
    sub = plan.model_copy(update={"items": tuple(todo)})
    out = await ask(rc.crew.get("red_team"),
                    prompts.red_team_prompt(rc.product, sub, rc.proposals, chains), RedTeamReport)
    ctx.state["red_reviewed"] = sorted(reviewed | {i.proposal_id for i in todo})
    blocks = [o for o in out.objections if o.action == "block" and o.proposal_id in chains]
    flags = [o for o in out.objections if o.action == "flag" and o.proposal_id in chains]
    rc.stats["red_team_flags"] = rc.stats.get("red_team_flags", 0) + len(flags)
    observe.emit("red_team_review", reviewed=list(chains), round=ctx.state["red_team_rounds"],
                 blocks=[o.model_dump() for o in blocks], flags=[o.model_dump() for o in flags])
    if not blocks:
        return {"blocks": 0, "flags": len(flags)}
    if ctx.state["red_team_rounds"] >= RED_TEAM_CAP:
        rc.note(f"red team: cap reached, {len(blocks)} blocks not applied")
        return {"blocks": len(blocks), "applied": False}
    blocked = dict(ctx.state["blocked"])
    for o in blocks:
        blocked[o.proposal_id] = ["red_team", o.issue[:200]]
    ctx.state["blocked"] = blocked
    ctx.state["red_team_rounds"] += 1
    rc.record.red_team_rounds = ctx.state["red_team_rounds"]
    ctx.route = "replan"
    rc.note(f"red team: blocked {[o.proposal_id for o in blocks]}")
    return {"blocks": len(blocks), "route": "replan"}


async def client(ctx):
    """The Client decides in code against its private constraints; the LLM only
    words the reply (revamp/client_service.py). With REVAMP_CLIENT_URL set, the
    Client is a separate A2A process and this process never touches its data."""
    rc = _rc(ctx)
    plan: Plan = rc.current_plan
    round_no = ctx.state["client_rounds"]
    if settings.client_url:
        verdict = await client_service.remote_evaluate(
            settings.client_url, plan, rc.proposals, rc.run_id, round_no, rc.seed)
    else:
        verdict = await client_service.evaluate(plan, rc.proposals, rc.run_id, round_no,
                                                rc.client_kb, rc.crew.get("client"))
    decision = verdict.decision
    vetoed = list(verdict.vetoed_proposal_ids)
    ctx.state["client_rounds"] += 1
    rc.record.client_rounds = ctx.state["client_rounds"]
    ctx.state["client_history"] = ctx.state["client_history"] + [{
        "round": ctx.state["client_rounds"], "decision": decision,
        "reason_codes": list(verdict.reason_codes), "vetoed": vetoed,
        "message": verdict.message}]
    observe.emit("client_verdict", round=ctx.state["client_rounds"],
                 remote=bool(settings.client_url), **verdict.model_dump(mode="json"))
    rc.note(f"client round {ctx.state['client_rounds']}: {decision} {list(verdict.reason_codes)}")
    if decision == "accept":
        ctx.route = "accept"
    elif rc.arm.client_loop and ctx.state["client_rounds"] < CLIENT_CAP:
        ctx.route = "reject"
    else:
        ctx.route = "stop"
    return verdict.model_dump()


APPROVAL_ID = "approve-plan"
HIGH_IMPACT_SHARE = 0.25  # an item costing a quarter of the budget needs a human


def high_impact(plan: Plan, props: dict[str, Proposal]) -> list[str]:
    return [i.proposal_id for i in plan.items
            if props[i.proposal_id].risk == "high"
            or i.cost_days >= HIGH_IMPACT_SHARE * plan.budget_days]


async def approve(ctx):
    """Guardrail: high-impact items need a human's approval before the plan is final.

    This is a node, not an agent: it decides nothing itself. It pauses the workflow
    with RequestInput; the runner collects the human's answer and resumes. Items the
    human rejects are blocked and the plan is re-solved. Asked at most once per run.
    """
    rc = _rc(ctx)
    # Do NOT set ctx.route before pausing: ADK records a route set before an
    # interrupt and, on resume, fast-forwards past this node using it (ADK 2.9
    # _replay_interceptor "Case 4"). Route only once the decision is made.
    plan: Plan = rc.current_plan
    pending = high_impact(plan, rc.proposals)
    if not rc.hitl or not pending or ctx.state.get("approval_done"):
        ctx.route = "ok"
        yield {"approval": "not required" if not pending else "auto"}
        return
    answer = ctx.resume_inputs.get(APPROVAL_ID)
    if answer is None:
        rc.pending_approval = {"plan_id": plan.id, "items": [
            {"id": pid, "title": rc.proposals[pid].title,
             "cost_days": rc.proposals[pid].cost_days, "risk": rc.proposals[pid].risk}
            for pid in pending]}
        yield RequestInput(interrupt_id=APPROVAL_ID, payload=rc.pending_approval,
                           message=f"Approve {len(pending)} high-impact plan items?")
        return
    rc.pending_approval = None
    ctx.state["approval_done"] = True
    rejected = [pid for pid in (answer.get("rejected") or []) if pid in pending]
    rc.note(f"approval: human rejected {rejected or 'nothing'}")
    if rejected:
        blocked = dict(ctx.state["blocked"])
        for pid in rejected:
            blocked[pid] = ["client_veto", "rejected by human approver"]
        ctx.state["blocked"] = blocked
    ctx.route = "replan" if rejected else "ok"
    yield {"approval": "done", "rejected": rejected}


async def adapt(ctx):
    rc = _rc(ctx)
    plan: Plan = rc.current_plan
    out = await ask(rc.crew.get("engagement_adapter"),
                    prompts.adapt_prompt(rc.product, plan, rc.proposals,
                                         ctx.state["client_history"]), ClientAdaptation)
    blocked = dict(ctx.state["blocked"])
    for pid in ctx.state["client_history"][-1]["vetoed"]:
        blocked[pid] = ["client_veto", "vetoed by client"]
    for pid in out.drop:
        if pid in rc.proposals and pid not in blocked:
            blocked[pid] = ["client_veto", "dropped to address client feedback"]
    ctx.state["blocked"] = blocked
    if out.budget_days and 0 < out.budget_days < ctx.state["budget_days"]:
        ctx.state["budget_days"] = out.budget_days
    observe.emit("adaptation", effective_budget_days=ctx.state["budget_days"], blocked=blocked,
                 **out.model_dump(mode="json"))
    rc.note(f"adapt: drop {out.drop}, budget {ctx.state['budget_days']:g}, "
            f"request '{out.request}' -> {out.team or '-'}; {out.reasoning[:160]}")
    if out.request and out.team in TEAMS:
        ctx.state["feedback"] = {**ctx.state["feedback"], out.team:
                                 f"The client appears to need this covered: {out.request}. "
                                 "Include a proposal for it."}
        ctx.state["teams_to_run"] = [out.team]
        ctx.route = "propose"
    else:
        ctx.route = "replan"
    return out.model_dump()


async def single_llm(ctx):
    """Arm A0: one call, one plan. Its items go through the same provenance filter."""
    rc = _rc(ctx)
    fs = _findings(rc)
    out = await ask(rc.crew.get("single_llm"),
                    prompts.single_llm_prompt(rc.product, fs, ctx.state["budget_days"]),
                    SingleLlmPlan)
    props = drafts_to_proposals("single_llm", out, {f.id for f in fs}, "0", rc.stats)
    order = {f"SL0-{k}": d.order for k, d in enumerate(out.items, 1)}
    for p in props:
        rc.team_kb.add_proposal(rc.run_id, rc.product.name, p)
        rc.proposals[p.id] = p
    base = plan_without_arbitration(product=rc.product.name, arm=rc.arm.name,
                                    budget_days=ctx.state["budget_days"], proposals=props)
    items = tuple(PlanItem(proposal_id=i.proposal_id, order=order[i.proposal_id], after=(),
                           cost_days=i.cost_days, value=i.value)
                  for i in sorted(base.items, key=lambda i: (order[i.proposal_id],
                                                             i.proposal_id)))
    plan = base.model_copy(update={"items": items, "notes": out.summary[:500]})
    rc.team_kb.add_plan(rc.run_id, plan)
    rc.current_plan = plan
    ctx.state["plan_id"] = plan.id
    observe.emit("plan", plan=plan.model_dump(mode="json"), arbitrated=False,
                 titles={p.id: p.title for p in props}, teams={p.id: p.team for p in props})
    rc.note(f"single LLM: {len(items)} items, {plan.total_cost:g}d")
    return {"items": len(items)}


async def finalize(ctx):
    rc = _rc(ctx)
    rc.record.status = "done"
    rc.record.finished_at = utcnow()
    rc.record.plan_id = ctx.state.get("plan_id")
    rc.team_kb.save_run(rc.record)
    last = ctx.state["client_history"][-1]["decision"] if ctx.state["client_history"] else None
    rc.note(f"finalize: plan {rc.record.plan_id}, client {last}")
    return {"plan_id": rc.record.plan_id, "client": last}
