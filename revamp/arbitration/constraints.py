"""Check a plan against the Client's private constraints.

Used twice, which is the point of having it in code:
  1. by the Client agent, to decide accept / reject;
  2. by the evaluation, to count hidden-constraint violations per arm.
Both see identical logic, so the metric and the behaviour cannot drift apart.
"""

from __future__ import annotations

from dataclasses import dataclass

from revamp.contracts import ClientConstraint, Plan, Proposal

_RISK = {"low": 0, "medium": 1, "high": 2}


@dataclass(frozen=True)
class Violation:
    constraint_id: str
    reason_code: str
    proposal_ids: tuple[str, ...]  # offending items; empty for plan-level rules
    detail: str


def check(plan: Plan, proposals: dict[str, Proposal],
          constraints: list[ClientConstraint]) -> list[Violation]:
    items = [proposals[i.proposal_id] for i in plan.items if i.proposal_id in proposals]
    out: list[Violation] = []
    for c in constraints:
        if c.kind == "forbid_area":
            bad = tuple(p.id for p in items if c.param in p.areas)
            if bad:
                out.append(Violation(c.id, c.reason_code, bad, f"touches {c.param}"))
        elif c.kind == "require_area":
            if not any(c.param in p.areas for p in items):
                out.append(Violation(c.id, c.reason_code, (), f"nothing addresses {c.param}"))
        elif c.kind == "max_total_days":
            if plan.total_cost > float(c.param):
                out.append(Violation(c.id, c.reason_code, (),
                                     f"{plan.total_cost}d exceeds {c.param}d"))
        elif c.kind == "max_risk":
            bad = tuple(p.id for p in items if _RISK[p.risk] > _RISK[c.param])
            if bad:
                out.append(Violation(c.id, c.reason_code, bad, f"risk above {c.param}"))
        elif c.kind == "forbid_team":
            bad = tuple(p.id for p in items if p.team == c.param)
            if bad:
                out.append(Violation(c.id, c.reason_code, bad, f"work from {c.param}"))
    return out
