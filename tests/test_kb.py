import pytest

from revamp.contracts import ClientConstraint, ClientVerdict, Evidence, Finding, Proposal
from revamp.kb import AccessDenied, KnowledgeBase, ProvenanceError


@pytest.fixture
def kbs(tmp_path):
    path = tmp_path / "kb.sqlite3"
    return {r: KnowledgeBase(path, r) for r in ("team", "client", "evaluator")}


def _finding(title="Slow LCP"):
    return Finding.make(product="umami", category="performance", title=title,
                        severity="high", evidence=Evidence(tool="psi", target="live",
                                                           locator="https://umami.is/"))


def _proposal(fids, pid="P-1"):
    return Proposal(id=pid, team="engineering", title="t", change="c", rationale="r",
                    finding_ids=tuple(fids), cost_days=2, value=4, areas=("perf",))


def _constraint():
    return ClientConstraint(id="K-1", product="umami", kind="forbid_area", param="pricing_page",
                            reason_code="brand", description="Board froze pricing until Q3")


def test_findings_upsert_counts_new_only(kbs):
    f = _finding()
    assert kbs["team"].add_findings([f]) == 1
    assert kbs["team"].add_findings([f, _finding("Big JS")]) == 1
    assert len(kbs["team"].findings("umami")) == 2


def test_team_cannot_read_client_private(kbs):
    """Invariant 3. The whole information-asymmetry design rests on this."""
    kbs["client"].set_constraints("umami", [_constraint()])
    with pytest.raises(AccessDenied):
        kbs["team"].constraints("umami")
    with pytest.raises(AccessDenied):
        kbs["team"].private_log("run-1")
    assert kbs["client"].constraints("umami")[0].param == "pricing_page"
    assert kbs["evaluator"].constraints("umami")  # evaluation needs ground truth


def test_team_cannot_write_client_private_or_verdicts(kbs):
    with pytest.raises(AccessDenied):
        kbs["team"].set_constraints("umami", [])
    with pytest.raises(AccessDenied):
        kbs["team"].add_verdict("run-1", ClientVerdict(plan_id="PL-1", decision="accept"))


def test_team_can_read_public_verdicts(kbs):
    kbs["client"].add_verdict("run-1", ClientVerdict(plan_id="PL-1", decision="reject",
                                                    reason_codes=("brand",)))
    assert kbs["team"].verdicts("run-1")[0].reason_codes == ("brand",)


def test_proposal_citing_unknown_finding_is_rejected(kbs):
    """Invariant 2: provenance is enforced in code."""
    with pytest.raises(ProvenanceError):
        kbs["team"].add_proposal("run-1", "umami", _proposal(["F-doesnotexist"]))


def test_evidence_chain_and_latest_revision(kbs):
    f = _finding()
    kbs["team"].add_findings([f])
    kbs["team"].add_proposal("run-1", "umami", _proposal([f.id]))
    kbs["team"].add_proposal("run-1", "umami",
                             _proposal([f.id]).model_copy(update={"revision": 1, "value": 9}))
    latest = kbs["team"].proposals("run-1")
    assert len(latest) == 1 and latest[0].value == 9
    assert [x.id for x in kbs["team"].evidence_chain("run-1", "P-1")] == [f.id]


def test_priors_are_read_only_for_team(kbs):
    kbs["evaluator"].set_prior("cost_bias.design", 1.3)
    assert kbs["team"].prior("cost_bias.design") == 1.3
    with pytest.raises(AccessDenied):
        kbs["team"].set_prior("cost_bias.design", 1.0)
