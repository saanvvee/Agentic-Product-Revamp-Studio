import pytest

from revamp.arbitration.budget import allocate
from revamp.arbitration.constraints import check
from revamp.arbitration.plan import build_plan
from revamp.arbitration.sequencer import DependencyCycle, find_cycle, sequence
from revamp.contracts import ClientConstraint, Conflict, Proposal


def P(pid, cost, value, deps=(), areas=("x",), team="design", risk="low"):
    return Proposal(id=pid, team=team, title=pid, change="c", rationale="r",
                    finding_ids=("F-1",), cost_days=cost, value=value,
                    depends_on=tuple(deps), areas=areas, risk=risk)


def test_two_cheap_beat_one_expensive():
    """The synopsis's claim: an individually worthwhile item loses to two cheaper
    ones. Greedy by value would take A (value 9) and nothing else fits."""
    props = [P("A", 10, 9), P("B", 5, 6), P("C", 5, 6)]
    a = allocate(props, budget_days=10)
    assert a.selected == ("B", "C") and a.total_value == 12
    assert {r.proposal_id: r.reason for r in a.rejected} == {"A": "over_budget"}


def test_precedence_cheap_enabler_unlocks_value():
    """B is worth little alone but unlocks C; the solver must take both."""
    props = [P("A", 6, 6), P("B", 3, 1), P("C", 3, 8, deps=["B"])]
    a = allocate(props, budget_days=6)
    assert a.selected == ("B", "C")


def test_dependent_never_selected_without_its_dependency():
    props = [P("B", 8, 1), P("C", 3, 8, deps=["B"])]
    a = allocate(props, budget_days=5)
    assert a.selected == ()


def test_missing_dependency_blocks_transitively():
    props = [P("A", 1, 5, deps=["B"]), P("B", 1, 5, deps=["GONE"])]
    a = allocate(props, budget_days=10)
    assert a.selected == ()
    assert {r.reason for r in a.rejected} == {"dependency"}


def test_exclusive_conflict_keeps_one():
    props = [P("A", 2, 5), P("B", 2, 7)]
    cf = Conflict(id="C1", a="A", b="B", kind="contradiction", explanation="x")
    a = allocate(props, 10, [cf])
    assert a.selected == ("B",)
    assert a.rejected[0].reason == "conflict" and "B" in a.rejected[0].detail


def test_blocked_is_excluded_with_its_reason():
    a = allocate([P("A", 1, 5)], 10, blocked={"A": ("client_veto", "brand")})
    assert a.selected == () and a.rejected[0].reason == "client_veto"


def test_tie_prefers_cheaper():
    a = allocate([P("A", 4, 5), P("B", 2, 5)], budget_days=4)
    assert a.selected == ("B",)


def test_sequence_waves():
    items = sequence([P("A", 1, 1), P("B", 1, 1, deps=["A"]), P("C", 1, 1, deps=["A"]),
                      P("D", 1, 1, deps=["B", "C"])])
    assert [(i.proposal_id, i.order) for i in items] == [
        ("A", 1), ("B", 2), ("C", 2), ("D", 3)]


def test_cycle_detected():
    props = [P("A", 1, 1, deps=["B"]), P("B", 1, 1, deps=["A"])]
    with pytest.raises(DependencyCycle):
        sequence(props)
    assert set(find_cycle(props)) == {"A", "B"}


def test_constraint_check_and_plan():
    props = [P("A", 2, 5, areas=("pricing_page",)), P("B", 2, 4, risk="high")]
    plan = build_plan(product="umami", arm="A2", round=0, budget_days=10, proposals=props)
    ks = [ClientConstraint(id="K1", product="umami", kind="forbid_area", param="pricing_page",
                           reason_code="brand", description="d"),
          ClientConstraint(id="K2", product="umami", kind="max_risk", param="medium",
                           reason_code="risk", description="d"),
          ClientConstraint(id="K3", product="umami", kind="require_area", param="onboarding",
                           reason_code="scope", description="d")]
    v = check(plan, {p.id: p for p in props}, ks)
    assert {(x.constraint_id, x.proposal_ids) for x in v} == {
        ("K1", ("A",)), ("K2", ("B",)), ("K3", ())}
