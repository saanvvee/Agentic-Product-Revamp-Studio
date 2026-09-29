"""Proposal teams: Design, Engineering, Product & Pricing (Tier 1).

Each team sees the same evidence and proposes up to six costed changes in its own
lane. Teams do not see each other's proposals while proposing; that is deliberate,
because contradictions between teams are what the arbitration layer exists to catch.

Engineering has a second role: the handoff review. It checks the other teams'
proposals for technical feasibility and cost realism, and may reject them back to
their authors. That rejection is a backward edge in the workflow graph.
"""

from __future__ import annotations

from revamp.agents.factory import make_agent
from revamp.agents.schemas import HandoffReview, TeamProposals

_COMMON = """
Propose at most 6 changes. For each: a concrete change, the rationale in terms of the cited
findings, a cost in engineer-days (be realistic: a small copy fix is 0.5-1 day, a page
redesign 5-15 days, a new subsystem 20+ days), an impact value 1-10, 1-3 area names
(lowercase, e.g. navigation, pricing_page, onboarding, performance, accessibility, security,
dependencies, docs, seo), a risk level, and dependencies on your OWN proposals by ref.
Every proposal must cite at least one finding id from the evidence.
"""

LANES = {
    "design": "You are the Design team: information architecture, navigation, visual design, "
              "accessibility of the interface, content and copy, onboarding flow.",
    "engineering": "You are the Engineering team: performance, dependency upgrades and "
                   "vulnerabilities, code health and complexity, reliability, build and "
                   "infrastructure.",
    "product_pricing": "You are the Product & Pricing team: packaging, plans and prices, "
                       "positioning against competitors, feature gaps users ask for, "
                       "conversion from visitor to user. Compare against the competitor "
                       "pricing snapshots when you have them.",
}

HANDOFF = """
You are the Engineering team reviewing proposals from other teams before they are planned.
For each proposal decide:
- accept: technically feasible at roughly the stated cost;
- reject: infeasible, or the cost is badly underestimated (give realistic_cost_days), or it
  depends on work nobody has proposed. Give a one-sentence reason.
Be fair: reject only with a concrete technical reason.
"""


def team(name: str, extra: str = "", **kw):
    return make_agent(name, LANES[name] + "\n" + _COMMON + extra, TeamProposals, **kw)


def handoff_reviewer(**kw):
    return make_agent("engineering", HANDOFF, HandoffReview, **kw)
