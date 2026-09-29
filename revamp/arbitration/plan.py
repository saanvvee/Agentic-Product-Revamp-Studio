"""Assemble a Plan: allocate under budget, then sequence what survived."""

from __future__ import annotations

from revamp.arbitration.budget import allocate
from revamp.arbitration.sequencer import sequence
from revamp.contracts import Conflict, Plan, Proposal, stable_id


def build_plan(*, product: str, arm: str, round: int, budget_days: float,
               proposals: list[Proposal], conflicts: list[Conflict] = (),
               blocked: dict[str, tuple[str, str]] | None = None,
               notes: str = "") -> Plan:
    alloc = allocate(proposals, budget_days, list(conflicts), blocked)
    by_id = {p.id: p for p in proposals}
    items = sequence([by_id[i] for i in alloc.selected])
    return Plan(
        id=stable_id("PL", product, arm, str(round), *alloc.selected),
        product=product, arm=arm, round=round, budget_days=budget_days,
        items=tuple(items), rejected=alloc.rejected, conflicts=tuple(conflicts),
        total_cost=alloc.total_cost, total_value=alloc.total_value, notes=notes,
    )


def plan_without_arbitration(*, product: str, arm: str, budget_days: float,
                             proposals: list[Proposal], notes: str = "") -> Plan:
    """Baseline A1: every proposal is kept, in team order, no budget, no conflicts.
    The plan is honest about its cost; the metrics then show the overrun."""
    from revamp.contracts import PlanItem
    items = tuple(PlanItem(proposal_id=p.id, order=1, after=p.depends_on,
                           cost_days=p.cost_days, value=p.value)
                  for p in sorted(proposals, key=lambda p: (p.team, p.id)))
    return Plan(
        id=stable_id("PL", product, arm, "0", *(p.id for p in proposals)),
        product=product, arm=arm, round=0, budget_days=budget_days, items=items,
        total_cost=float(sum(p.cost_days for p in proposals)),
        total_value=int(sum(p.value for p in proposals)), notes=notes,
    )
