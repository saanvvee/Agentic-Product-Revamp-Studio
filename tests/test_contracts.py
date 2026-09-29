import pytest
from pydantic import ValidationError

from revamp.contracts import Conflict, Evidence, Finding, Proposal


def _ev(locator="https://example.com/"):
    return Evidence(tool="axe", target="live", locator=locator)


def test_finding_id_is_deterministic():
    a = Finding.make(product="umami", category="accessibility", title="Low contrast",
                     severity="medium", evidence=_ev())
    b = Finding.make(product="umami", category="accessibility", title="Low contrast",
                     severity="medium", evidence=_ev())
    c = Finding.make(product="umami", category="accessibility", title="Low contrast",
                     severity="medium", evidence=_ev("https://example.com/login"))
    assert a.id == b.id != c.id
    assert a.id.startswith("F-")


def _proposal(**kw):
    base = dict(id="P-1", team="design", title="t", change="c", rationale="r",
                finding_ids=("F-1",), cost_days=3, value=5, areas=("Navigation",))
    base.update(kw)
    return Proposal(**base)


def test_proposal_requires_a_finding():
    with pytest.raises(ValidationError):
        _proposal(finding_ids=())


def test_proposal_areas_are_normalised():
    assert _proposal(areas=("Sign Up", "navigation", "Navigation")).areas == (
        "navigation", "sign_up")


def test_proposal_cannot_depend_on_itself():
    with pytest.raises(ValidationError):
        _proposal(depends_on=("P-1",))


def test_conflict_needs_two_proposals():
    with pytest.raises(ValidationError):
        Conflict(id="C-1", a="P-1", b="P-1", kind="contradiction", explanation="x")


def test_contracts_are_frozen():
    p = _proposal()
    with pytest.raises(ValidationError):
        p.cost_days = 1
