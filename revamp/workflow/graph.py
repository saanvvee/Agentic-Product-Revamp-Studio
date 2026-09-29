"""The ADK 2.9 graph. Two shapes: the full engagement, and A0's single call.

Full engagement:

  START -> init -> brief -> perspectives -> propose -> handoff
  handoff      --revise--> propose            (Engineering rejects; <= HANDOFF_CAP)
               --ok------> conflicts -> allocate -> red_team
  red_team     --replan--> allocate           (Red Team blocks;    <= RED_TEAM_CAP)
               --ok------> client
  client       --accept--> approve            (human approval of high-impact items)
               --reject--> adapt              (Client rejects;     <= CLIENT_CAP)
               --stop----> finalize
  approve      --ok------> finalize
               --replan--> allocate           (human rejected items; asked once)
  adapt        --replan--> allocate
               --propose-> propose

Every cycle passes through a routed edge, which ADK requires; the counters that
bound each cycle live in the nodes.
"""

from __future__ import annotations

from google.adk.workflow import DEFAULT_ROUTE, START, FunctionNode, Workflow

from revamp.workflow import nodes as n
from revamp.workflow.arms import Arm


def _node(fn) -> FunctionNode:
    return FunctionNode(func=fn, name=fn.__name__)


def build(arm: Arm) -> Workflow:
    N = {name: _node(getattr(n, name)) for name in (
        "init", "brief", "perspectives", "propose", "handoff", "conflicts", "allocate",
        "red_team", "client", "adapt", "single_llm", "finalize")}
    # rerun_on_resume: after the human answers, the node runs again and reads the
    # answer from ctx.resume_inputs instead of treating it as its output.
    N["approve"] = FunctionNode(func=n.approve, name="approve", rerun_on_resume=True)

    if arm.single_llm:
        # A0 has no negotiation: the client only scores the plan.
        edges = [(START, N["init"], N["single_llm"], N["client"],
                  {DEFAULT_ROUTE: N["finalize"]})]
    else:
        edges = [
            (START, N["init"], N["brief"], N["perspectives"], N["propose"], N["handoff"],
             {"revise": N["propose"], "ok": N["conflicts"]}),
            (N["conflicts"], N["allocate"], N["red_team"],
             {"replan": N["allocate"], "ok": N["client"]}),
            (N["client"], {"accept": N["approve"], "reject": N["adapt"],
                           "stop": N["finalize"]}),
            (N["approve"], {"ok": N["finalize"], "replan": N["allocate"]}),
            (N["adapt"], {"replan": N["allocate"], "propose": N["propose"]}),
        ]
    return Workflow(name=f"revamp_{arm.name}", edges=edges)
