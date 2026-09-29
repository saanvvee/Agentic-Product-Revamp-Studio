"""Budget Allocator: choose the subset of proposals that fits the engineering budget.

This is a 0/1 knapsack with two extra kinds of constraint, solved exactly as an
integer linear program with scipy.optimize.milp (PLAN D5):

    maximise    sum(value_i * x_i)
    subject to  sum(cost_i * x_i) <= budget          capacity
                x_i <= x_j   for each i depends_on j  precedence
                x_a + x_b <= 1  for each exclusive conflict
                x_i = 0      for vetoed / blocked proposals
                x_i in {0, 1}

Why an exact solver and not "sort by value/cost and take greedily": greedy fails
exactly the case the synopsis cares about, where one individually worthwhile
proposal loses to two cheaper ones that together are worth more. Precedence makes
greedy worse still: a cheap proposal can be worthless on its own but unlock a
valuable one.

Ties are broken towards the cheaper plan by subtracting a tiny cost term, so two
runs with equal value always pick the same subset.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp

from revamp.contracts import Conflict, Proposal, Rejected

_TIE_BREAK = 1e-4


@dataclass(frozen=True)
class Allocation:
    selected: tuple[str, ...]
    rejected: tuple[Rejected, ...]
    total_cost: float
    total_value: int


def allocate(
    proposals: list[Proposal],
    budget_days: float,
    conflicts: list[Conflict] = (),
    blocked: dict[str, tuple[str, str]] | None = None,
) -> Allocation:
    """`blocked` maps proposal id -> (reason, detail) for proposals forced out
    before solving, e.g. a Client veto or a Red Team rejection."""
    blocked = dict(blocked or {})
    by_id = {p.id: p for p in proposals}
    ids = sorted(by_id)
    n = len(ids)
    if n == 0:
        return Allocation((), (), 0.0, 0)
    col = {pid: k for k, pid in enumerate(ids)}

    # A dependency on a proposal we do not have makes the dependent unshippable.
    # Propagate transitively: A needs B, B needs a missing C -> A is blocked too.
    changed = True
    while changed:
        changed = False
        for pid in ids:
            if pid in blocked:
                continue
            for dep in by_id[pid].depends_on:
                if dep not in by_id or dep in blocked:
                    blocked[pid] = ("dependency", f"needs {dep}, which is unavailable")
                    changed = True
                    break

    cost = np.array([by_id[i].cost_days for i in ids], dtype=float)
    value = np.array([by_id[i].value for i in ids], dtype=float)
    # milp minimises, so negate value; subtract cost slightly to prefer cheaper ties.
    c = -(value - _TIE_BREAK * cost)

    rows, lo, hi = [cost], [-np.inf], [budget_days]
    for pid in ids:
        for dep in by_id[pid].depends_on:
            if dep in col:
                r = np.zeros(n)
                r[col[pid]], r[col[dep]] = 1, -1  # x_i - x_j <= 0
                rows.append(r); lo.append(-np.inf); hi.append(0)
    exclusive = [cf for cf in conflicts if cf.exclusive and cf.a in col and cf.b in col]
    for cf in exclusive:
        r = np.zeros(n)
        r[col[cf.a]] = r[col[cf.b]] = 1
        rows.append(r); lo.append(-np.inf); hi.append(1)

    upper = np.array([0.0 if pid in blocked else 1.0 for pid in ids])
    res = milp(c=c, constraints=LinearConstraint(np.vstack(rows), lo, hi),
               integrality=np.ones(n), bounds=Bounds(np.zeros(n), upper))
    if not res.success:  # only possible if the model is malformed; all-zero is feasible
        raise RuntimeError(f"budget solver failed: {res.message}")

    chosen = {ids[k] for k in range(n) if res.x[k] > 0.5}
    rejected = []
    for pid in ids:
        if pid in chosen:
            continue
        winner = next((other for cf in exclusive if pid in (cf.a, cf.b)
                       for other in (cf.a, cf.b) if other != pid and other in chosen), None)
        if pid in blocked:
            reason, detail = blocked[pid]
        elif winner:
            reason, detail = "conflict", f"lost to {winner}"
        else:
            reason, detail = "over_budget", f"{by_id[pid].cost_days}d did not fit"
        rejected.append(Rejected(proposal_id=pid, reason=reason, detail=detail))

    sel = tuple(sorted(chosen))
    return Allocation(
        selected=sel,
        rejected=tuple(rejected),
        total_cost=float(sum(by_id[i].cost_days for i in sel)),
        total_value=int(sum(by_id[i].value for i in sel)),
    )
