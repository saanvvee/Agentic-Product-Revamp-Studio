"""The Client as a separate A2A service (PLAN M10).

Run it in its own terminal:

    python -m revamp.client_service --port 8765

and point the orchestrator at it with REVAMP_CLIENT_URL=http://localhost:8765 .
Then the Client's private constraints exist only in THIS process: the orchestrator
never opens the client namespace at all (except in arm A6, by design). Information
asymmetry is enforced by a process boundary, on top of the KB's role check.

Without REVAMP_CLIENT_URL the same `evaluate()` runs in-process (descope fallback,
PLAN Section 7 step 3); behaviour is identical, only the isolation is weaker.

Note: use `localhost`, not 127.0.0.1. The A2A agent card advertises an origin and
the client enforces it; the two are different origins.
"""

from __future__ import annotations

import argparse
import json
import uuid

from google.adk.agents import LlmAgent
from google.adk.runners import InMemoryRunner
from google.genai import types

from revamp.agents.client import client_agent
from revamp.agents.runtime import ask
from revamp.agents.schemas import ClientReply
from revamp.arbitration.constraints import check
from revamp.contracts import ClientVerdict, Plan, Proposal
from revamp.kb import KnowledgeBase

GENERIC_CONCERN = {
    "budget": "The total cost is more than we can fund.",
    "timeline": "This will take longer than we can wait.",
    "brand": "Parts of this plan do not fit how we want the brand to be seen.",
    "compliance": "Parts of this plan raise compliance concerns for us.",
    "scope": "The plan misses something we consider essential.",
    "risk": "Some items are riskier than we are willing to take on right now.",
    "other": "Some items do not work for us.",
}


def client_prompt(decision: str, concerns: list[str]) -> str:
    if decision == "accept":
        return "You are ACCEPTING the plan."
    return "You are REJECTING the plan. Your concerns:\n" + "\n".join(f"- {c}" for c in concerns)


async def evaluate(plan: Plan, proposals: dict[str, Proposal], run_id: str, round_no: int,
                   kb: KnowledgeBase, agent: LlmAgent) -> ClientVerdict:
    """Decide in code against the private constraints; the LLM only words the reply."""
    if kb.role != "client":
        raise PermissionError("the client evaluation needs the client KB role")
    constraints = kb.constraints(plan.product)
    violations = check(plan, proposals, constraints)
    decision = "reject" if violations else "accept"
    by_id = {c.id: c for c in constraints}
    concerns = [by_id[v.constraint_id].public_hint or GENERIC_CONCERN[v.reason_code]
                for v in violations]
    reply = await ask(agent, client_prompt(decision, concerns), ClientReply)
    verdict = ClientVerdict(
        plan_id=plan.id, decision=decision,
        reason_codes=tuple(sorted({v.reason_code for v in violations})),
        vetoed_proposal_ids=tuple(sorted({pid for v in violations for pid in v.proposal_ids})),
        message=reply.message)
    kb.add_verdict(run_id, verdict)
    kb.log_private(run_id, plan.id, {"round": round_no,
                                     "violations": [v.__dict__ for v in violations]})
    return verdict


# ------------------------------------------------------------------ wire format

def encode_request(plan: Plan, proposals: dict[str, Proposal], run_id: str,
                   round_no: int, seed: int) -> str:
    used = {i.proposal_id for i in plan.items}
    return json.dumps({
        "run_id": run_id, "round": round_no, "seed": seed,
        "plan": json.loads(plan.model_dump_json()),
        # Only what the client needs to judge the plan items it was sent.
        "proposals": [json.loads(p.model_dump_json()) for p in proposals.values()
                      if p.id in used]})


# ------------------------------------------------------------------ remote call

async def remote_evaluate(url: str, plan: Plan, proposals: dict[str, Proposal],
                          run_id: str, round_no: int, seed: int) -> ClientVerdict:
    from google.adk.agents.remote_a2a_agent import RemoteA2aAgent

    remote = RemoteA2aAgent(name="client_remote",
                            agent_card=f"{url.rstrip('/')}/.well-known/agent-card.json",
                            timeout=600.0)
    runner = InMemoryRunner(agent=remote, app_name="client_call")
    s = await runner.session_service.create_session(app_name="client_call", user_id="team",
                                                    session_id=uuid.uuid4().hex)
    text = []
    msg = types.Content(role="user", parts=[types.Part(
        text=encode_request(plan, proposals, run_id, round_no, seed))])
    async for ev in runner.run_async(user_id="team", session_id=s.id, new_message=msg):
        if ev.content and ev.content.parts:
            text += [p.text for p in ev.content.parts if p.text]
    # A2A may deliver the answer in several events; the verdict is the last JSON object.
    for chunk in reversed(text):
        try:
            return ClientVerdict.model_validate_json(chunk)
        except ValueError:
            continue
    raise RuntimeError(f"client service returned no verdict: {''.join(text)[:300]}")


# ------------------------------------------------------------------ server

def build_app(kb_path: str, host: str, port: int, mode: str | None = None,
              override=None):
    """`override`: a fake model for tests (still cached, like every model)."""
    from google.adk.a2a.utils.agent_to_a2a import to_a2a
    from google.adk.workflow import START, FunctionNode, Workflow

    kb = KnowledgeBase(kb_path, "client")
    agents: dict[int, LlmAgent] = {}

    async def respond(node_input: str):
        req = json.loads(node_input)
        seed = int(req.get("seed", 0))
        agents.setdefault(seed, client_agent(seed=seed, mode=mode, override=override))
        plan = Plan.model_validate(req["plan"])
        props = {p["id"]: Proposal.model_validate(p) for p in req["proposals"]}
        verdict = await evaluate(plan, props, req["run_id"], int(req.get("round", 0)),
                                 kb, agents[seed])
        return types.Content(role="model", parts=[types.Part(text=verdict.model_dump_json())])

    wf = Workflow(name="client", description="The client who commissioned the revamp. "
                  "Send a plan; receive an accept/reject verdict.",
                  edges=[(START, FunctionNode(func=respond, name="respond"))])
    return to_a2a(wf, host=host, port=port)


def main() -> None:
    import uvicorn

    from revamp.settings import settings
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="localhost")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--kb", default=str(settings.kb_path))
    a = ap.parse_args()
    uvicorn.run(build_app(a.kb, a.host, a.port), host=a.host, port=a.port)


if __name__ == "__main__":
    main()
