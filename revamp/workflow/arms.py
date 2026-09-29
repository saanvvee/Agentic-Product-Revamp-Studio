"""Evaluation arms (PLAN Section 6). Each ablation switches off exactly one mechanism.

The graph has the same shape in every arm except A0; the switches are read inside
the nodes. So a difference between A2 and A3 is caused by the Conflict Detector and
nothing else.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

# Loop caps (invariant 4). ADK does not bound graph cycles; these counters do.
HANDOFF_CAP = 2  # rounds of teams revising after an Engineering handoff rejection
RED_TEAM_CAP = 2  # rounds of re-planning after Red Team blocks
CLIENT_CAP = 3  # rounds of negotiation after a Client rejection


@dataclass(frozen=True)
class Arm:
    name: str
    description: str
    single_llm: bool = False
    arbitration: bool = True  # budget solver + sequencer; False = keep everything
    conflict_detection: bool = True
    budget_limited: bool = True
    handoff_rejection: bool = True
    red_team: bool = True
    client_loop: bool = True
    client_visible: bool = False  # True = teams see the private constraints (A6)


_FULL = Arm("A2", "Full system")

ARMS: dict[str, Arm] = {
    "A0": Arm("A0", "Single LLM, same evidence, asked for a plan", single_llm=True,
              arbitration=False, conflict_detection=False, handoff_rejection=False,
              red_team=False, client_loop=False),
    "A1": Arm("A1", "Teams in parallel, no arbitration", arbitration=False,
              conflict_detection=False, handoff_rejection=False, red_team=False,
              client_loop=False),
    "A2": _FULL,
    "A3": replace(_FULL, name="A3", description="Full minus Conflict Detector",
                  conflict_detection=False),
    "A4": replace(_FULL, name="A4", description="Full with unlimited budget",
                  budget_limited=False),
    "A5": replace(_FULL, name="A5", description="Full minus handoff rejection",
                  handoff_rejection=False),
    "A6": replace(_FULL, name="A6", description="Full with client constraints visible",
                  client_visible=True),
}
