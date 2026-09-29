"""Dependency Sequencer: order the selected proposals into execution waves.

Kahn's topological sort, layered: wave 1 is everything with no unmet dependency,
wave 2 is everything whose dependencies are all in wave 1, and so on. Items in one
wave can run in parallel. A cycle is an error, not something to resolve silently:
it means two teams each claimed to need the other first.
"""

from __future__ import annotations

from revamp.contracts import PlanItem, Proposal


class DependencyCycle(ValueError):
    pass


def sequence(selected: list[Proposal]) -> list[PlanItem]:
    by_id = {p.id: p for p in selected}
    # Only dependencies inside the selected set matter; the allocator already
    # guaranteed every dependency of a selected item is itself selected.
    deps = {p.id: {d for d in p.depends_on if d in by_id} for p in selected}
    placed: dict[str, int] = {}
    wave = 0
    remaining = set(by_id)
    while remaining:
        wave += 1
        ready = sorted(pid for pid in remaining if deps[pid] <= placed.keys())
        if not ready:
            raise DependencyCycle(f"cycle among {sorted(remaining)}")
        for pid in ready:
            placed[pid] = wave
        remaining -= set(ready)

    return [
        PlanItem(proposal_id=pid, order=placed[pid], after=tuple(sorted(deps[pid])),
                 cost_days=by_id[pid].cost_days, value=by_id[pid].value)
        for pid in sorted(placed, key=lambda x: (placed[x], x))
    ]


def find_cycle(proposals: list[Proposal]) -> list[str] | None:
    """Return one dependency cycle among proposals, or None. Used to reject a
    proposal set before solving, with a message the teams can act on."""
    graph = {p.id: [d for d in p.depends_on] for p in proposals}
    state: dict[str, int] = {}  # 1 = on stack, 2 = done
    stack: list[str] = []

    def visit(u: str) -> list[str] | None:
        state[u] = 1
        stack.append(u)
        for v in graph.get(u, []):
            if v not in graph:
                continue
            if state.get(v) == 1:
                return stack[stack.index(v):] + [v]
            if v not in state:
                found = visit(v)
                if found:
                    return found
        stack.pop()
        state[u] = 2
        return None

    for node in sorted(graph):
        if node not in state:
            found = visit(node)
            if found:
                return found
    return None
