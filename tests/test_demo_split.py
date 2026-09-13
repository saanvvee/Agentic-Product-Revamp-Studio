"""The constructed demo split must cover every scenario, and never be reported.

Both halves matter. Coverage is why it is constructed rather than sampled;
the reporting guard is what stops that construction poisoning an aggregate.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from eval.split_guard import NonReportableSplitError, assert_reportable
from harness.demo_builder import build_demo_incidents, scenario_notes
from harness.reference_rule import fuse_log_odds
from harness.synthetic import SyntheticEventSource
from schemas.incident import AmbiguityLevel, Path, Split

TIER3_MIN_PRIOR_FAULTS = 2
TIER3_WINDOW_DAYS = 3
TIER3_FUSED_THRESHOLD = 5.0
DOWNGRADE_MIN_FALSE_ALARMS = 3
DOWNGRADE_WINDOW_DAYS = 30


@pytest.fixture
def demo():
    return list(build_demo_incidents())


def test_scenario_d_tier_three_is_reachable(demo):
    """THE test that justifies constructing this split.

    Measured: the SAMPLED 8-incident demo split could never trigger Tier 3,
    because the precondition needs two prior confirmed faults on one machine and
    8 incidents across 3 machines cannot accumulate them. A demo that cannot show
    the safety story is a demo of the common case.
    """
    confirmed: dict[str, list] = {}
    blocked: list[str] = []

    for record in demo:
        fused = fuse_log_odds([c.confidence for c in record.cached_scores.values()])
        priors = [
            t
            for t in confirmed.get(record.machine_id, [])
            if (record.timestamp - t) <= timedelta(days=TIER3_WINDOW_DAYS)
        ]
        if (
            record.is_anomalous
            and fused > TIER3_FUSED_THRESHOLD
            and len(priors) >= TIER3_MIN_PRIOR_FAULTS
        ):
            blocked.append(record.incident_id)
        if record.is_anomalous and fused > TIER3_FUSED_THRESHOLD:
            confirmed.setdefault(record.machine_id, []).append(record.timestamp)

    assert blocked == ["demo_d_tier3_block"], (
        "exactly one incident must trigger the Tier 3 guardrail, and it must be "
        "the one named for it"
    )


def test_scenario_e_memory_downgrade_is_reachable(demo):
    """The repeat-offender rule (PRD S10.3) needs 3 false alarms in 30 days on one
    machine -- also unreachable by sampling 8 incidents."""
    false_alarms: dict[str, list] = {}
    downgraded: list[str] = []

    for record in demo:
        fused = fuse_log_odds([c.confidence for c in record.cached_scores.values()])
        priors = [
            t
            for t in false_alarms.get(record.machine_id, [])
            if (record.timestamp - t) <= timedelta(days=DOWNGRADE_WINDOW_DAYS)
        ]
        if len(priors) >= DOWNGRADE_MIN_FALSE_ALARMS:
            downgraded.append(record.incident_id)
        if not record.is_anomalous and fused > 0:
            false_alarms.setdefault(record.machine_id, []).append(record.timestamp)

    assert "demo_e_downgraded" in downgraded


def test_every_path_is_represented(demo):
    """Completeness, which is the demo split's whole job."""
    assert {r.expected_path for r in demo} == set(Path)


def test_every_ambiguity_level_is_represented(demo):
    assert {r.ambiguity_level for r in demo} == set(AmbiguityLevel)


def test_an_unresolvable_incident_is_present(demo):
    """Escalation is a demonstrable behaviour, not only a metric."""
    unresolvable = [r for r in demo if r.is_unresolvable]
    assert len(unresolvable) == 1
    assert unresolvable[0].incident_id == "demo_f_unresolvable"


def test_a_dismissal_is_present(demo):
    """Declining to investigate is also a decision worth demonstrating."""
    assert any(
        not r.is_anomalous and r.ambiguity_level is AmbiguityLevel.CLEAR_NORMAL
        for r in demo
    )


def test_construction_is_deterministic():
    assert list(build_demo_incidents()) == list(build_demo_incidents())


def test_every_incident_has_a_documented_purpose(demo):
    """A demo incident nobody can explain is a demo incident that will be cut."""
    notes = {label: note for label, _, note in scenario_notes()}
    assert set(notes) == {r.incident_id for r in demo}
    assert all(len(note) > 40 for note in notes.values())


# --------------------------------------------------------------------------
# The guard: constructed incidents must never reach a results table
# --------------------------------------------------------------------------


def test_guard_rejects_the_demo_split(demo):
    with pytest.raises(NonReportableSplitError, match="scenario coverage"):
        assert_reportable(demo, context="test aggregate")


def test_guard_allows_the_test_split():
    records = list(SyntheticEventSource(seed=0).events(Split.TEST))
    assert_reportable(records, context="test aggregate")  # must not raise


def test_guard_catches_a_single_smuggled_incident(demo):
    """One constructed incident mixed into a real split must still fail: it
    over-represents a rare path and would shift the aggregate."""
    records = list(SyntheticEventSource(seed=0).events(Split.TEST))
    records.append(demo[6])
    with pytest.raises(NonReportableSplitError):
        assert_reportable(records, context="test aggregate")
