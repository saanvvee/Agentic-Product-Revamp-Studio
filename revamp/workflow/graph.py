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

The edge list below is the single source of truth: `build` turns it into an ADK
Workflow, `describe` turns it into the picture the live dashboard draws.
"""

from __future__ import annotations

from google.adk.workflow import DEFAULT_ROUTE, START, FunctionNode, Workflow

from revamp import observe
from revamp.workflow import nodes as n
from revamp.workflow.arms import Arm

# (from, to, route label or None). "default" = ADK's DEFAULT_ROUTE.
FULL_EDGES = [
    ("START", "init", None), ("init", "brief", None), ("brief", "perspectives", None),
    ("perspectives", "propose", None), ("propose", "handoff", None),
    ("handoff", "propose", "revise"), ("handoff", "conflicts", "ok"),
    ("conflicts", "allocate", None), ("allocate", "red_team", None),
    ("red_team", "allocate", "replan"), ("red_team", "client", "ok"),
    ("client", "approve", "accept"), ("client", "adapt", "reject"),
    ("client", "finalize", "stop"),
    ("approve", "finalize", "ok"), ("approve", "allocate", "replan"),
    ("adapt", "allocate", "replan"), ("adapt", "propose", "propose"),
]
SINGLE_EDGES = [
    ("START", "init", None), ("init", "single_llm", None), ("single_llm", "client", None),
    ("client", "finalize", "default"),
]

# Which agents (or deterministic components) work inside each node. Dashboard only.
NODE_WORKERS = {
    "brief": ["engagement_lead"],
    "perspectives": ["voice_of_customer", "journey_auditor"],
    "propose": ["design", "engineering", "product_pricing"],
    "handoff": ["handoff_reviewer"],
    "conflicts": ["conflict_detector"],
    "allocate": ["budget_solver", "sequencer"],
    "red_team": ["red_team"],
    "client": ["client"],
    "approve": ["human"],
    "adapt": ["engagement_adapter"],
    "single_llm": ["single_llm"],
}
DETERMINISTIC = {"budget_solver", "sequencer", "human"}


def _edges(arm: Arm):
    return SINGLE_EDGES if arm.single_llm else FULL_EDGES


def build(arm: Arm) -> Workflow:
    nodes: dict[str, object] = {"START": START}

    def node(name: str):
        if name not in nodes:
            fn = observe.traced_node(getattr(n, name))
            # rerun_on_resume: after the human answers, `approve` runs again and reads
            # the answer from ctx.resume_inputs instead of treating it as its output.
            nodes[name] = FunctionNode(func=fn, name=name,
                                       rerun_on_resume=(name == "approve"))
        return nodes[name]

    # Group edges by source: unrouted edges chain, routed edges become one dict.
    by_src: dict[str, list[tuple[str, str | None]]] = {}
    for src, dst, route in _edges(arm):
        by_src.setdefault(src, []).append((dst, route))
    edges = []
    for src, outs in by_src.items():
        routed = {(DEFAULT_ROUTE if r == "default" else r): node(d) for d, r in outs if r}
        for d, r in outs:
            if r is None:
                edges.append((node(src), node(d)))
        if routed:
            edges.append((node(src), routed))
    return Workflow(name=f"revamp_{arm.name}", edges=edges)


def describe(arm: Arm) -> dict:
    """Nodes, edges and the agents inside each node, for the dashboard."""
    names = []
    for src, dst, _ in _edges(arm):
        for x in (src, dst):
            if x not in names:
                names.append(x)
    return {
        "nodes": [{"id": x, "workers": NODE_WORKERS.get(x, [])} for x in names],
        "edges": [{"source": s, "target": d, "route": r} for s, d, r in _edges(arm)],
        "deterministic": sorted(DETERMINISTIC),
    }
