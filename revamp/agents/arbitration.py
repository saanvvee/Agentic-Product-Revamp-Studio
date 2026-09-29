"""Arbitration layer, LLM part: Conflict Detector and Red Team.

The rest of arbitration is deterministic (revamp/arbitration): the Budget Allocator
solves an ILP, the Dependency Sequencer does a topological sort. The LLM agents here
supply the judgments a solver cannot make: which proposals contradict each other, and
which plan items the evidence does not really support.
"""

from __future__ import annotations

from revamp.agents.factory import make_agent
from revamp.agents.schemas import ConflictReport, RedTeamReport

CONFLICTS = """
You are the Conflict Detector. You see every team's proposals. Find pairs that should not
both ship as written:
- contradiction: they pull in opposite directions (e.g. one adds a step to signup, another
  removes steps; one raises the free tier limit, another restricts it; one rewrites a page,
  another polishes the page being replaced).
- same_area_overlap: they change the same thing twice, so one is wasted work.
Set exclusive=true when only one of the pair can reasonably ship. Report only real
conflicts; an empty list is a valid answer. Use the proposal ids exactly.
"""

RED_TEAM = """
You are the Red Team. You see a draft plan and, for each item, the findings it cites.
Challenge each item: does the cited evidence actually support this change? Is the claimed
impact plausible? Is it solving a problem the evidence shows, or a different one?
- block: the cited evidence does not support the item at all (wrong finding, trivial finding,
  or no causal link).
- flag: supported but weak, or the cost or impact looks off.
Do not object for style. An empty list is a valid answer.
"""


def conflict_detector(**kw):
    return make_agent("conflict_detector", CONFLICTS, ConflictReport, **kw)


def red_team(**kw):
    return make_agent("red_team", RED_TEAM, RedTeamReport, **kw)
