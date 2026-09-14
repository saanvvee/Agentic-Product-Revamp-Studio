"""The test that proves the MemoryStore seam is real, plus the A3 properties.

Contract tests run against BOTH implementations. The rules themselves live on
MachineHistory, so these tests check that two different storage backends answer
identically -- which is the thing that makes the seam meaningful rather than a
check that two databases can both hold rows.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from memory.base import (
    MEMORY_RULES_VERSION,
    IncidentOutcome,
    MemoryStore,
)
from memory.in_memory import DisabledStore, InMemoryStore
from memory.sqlite_store import SqliteStore

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
MACHINE = "zone_a_fan_00"


@pytest.fixture(params=["in_memory", "sqlite"])
def store(request, tmp_path):
    if request.param == "in_memory":
        built = InMemoryStore()
    else:
        built = SqliteStore(tmp_path / "incidents.db")
    yield built
    built.close()


def outcome(
    *,
    incident_id: str,
    days_ago: float,
    verdict: bool,
    truth: bool,
    fused: float = 9.0,
    tags: tuple[str, ...] = (),
    machine: str = MACHINE,
) -> IncidentOutcome:
    return IncidentOutcome(
        incident_id=incident_id,
        machine_id=machine,
        timestamp=NOW - timedelta(days=days_ago),
        verdict_anomalous=verdict,
        ground_truth_anomalous=truth,
        fused_log_odds=fused,
        action="WO-TECH-ROUTINE",
        symptom_tags=tags,
    )


# --------------------------------------------------------------------------
# Contract: both implementations must satisfy these
# --------------------------------------------------------------------------


def test_satisfies_the_protocol(store):
    assert isinstance(store, MemoryStore)


def test_empty_history_triggers_no_rule(store):
    history = store.history_for(MACHINE, as_of=NOW)
    assert history.false_alarms_in_window == 0
    assert not history.downgrade_priority
    assert not history.lower_confidence_threshold


def test_false_alarm_rule_needs_three(store):
    """PRD S10.3: >=3 false alarms in 30 days. Measured at 26.0% of incidents."""
    for i in range(2):
        store.record(outcome(incident_id=f"fa{i}", days_ago=i + 1, verdict=True, truth=False))
    assert not store.history_for(MACHINE, as_of=NOW).downgrade_priority

    store.record(outcome(incident_id="fa2", days_ago=3, verdict=True, truth=False))
    history = store.history_for(MACHINE, as_of=NOW)
    assert history.false_alarms_in_window == 3
    assert history.downgrade_priority


def test_false_alarms_outside_thirty_days_do_not_count(store):
    for i in range(3):
        store.record(
            outcome(incident_id=f"old{i}", days_ago=31 + i, verdict=True, truth=False)
        )
    assert not store.history_for(MACHINE, as_of=NOW).downgrade_priority


def test_a_correct_anomalous_verdict_is_not_a_false_alarm(store):
    """The distinction the whole store turns on."""
    for i in range(3):
        store.record(outcome(incident_id=f"ok{i}", days_ago=i + 1, verdict=True, truth=True))
    assert store.history_for(MACHINE, as_of=NOW).false_alarms_in_window == 0


def test_confirmed_fault_requires_decisive_confidence(store):
    """A barely-anomalous verdict that happened to be right is not a confirmed
    fault. Halting a line on two lucky guesses would be exactly wrong."""
    for i in range(2):
        store.record(
            outcome(incident_id=f"weak{i}", days_ago=0.5, verdict=True, truth=True, fused=1.0)
        )
    assert store.history_for(MACHINE, as_of=NOW).confirmed_faults_in_window == 0

    for i in range(2):
        store.record(
            outcome(
                incident_id=f"strong{i}",
                days_ago=0.5 + i * 0.1,
                verdict=True,
                truth=True,
                fused=9.0,
            )
        )
    assert store.history_for(MACHINE, as_of=NOW).lower_confidence_threshold


def test_history_is_per_machine(store):
    """A fault on one machine must not downgrade another, or the memory effect is
    a facility-wide constant rather than a per-asset judgement."""
    for i in range(3):
        store.record(
            outcome(
                incident_id=f"other{i}",
                days_ago=i + 1,
                verdict=True,
                truth=False,
                machine="zone_b_fan_04",
            )
        )
    assert not store.history_for(MACHINE, as_of=NOW).downgrade_priority
    assert store.history_for("zone_b_fan_04", as_of=NOW).downgrade_priority


def test_as_of_excludes_the_future(store):
    """THE leakage guard. Evaluation replays incidents in order; a store that
    answered with everything it holds would let an incident see its own future and
    inflate every memory effect."""
    for i in range(3):
        store.record(
            outcome(incident_id=f"later{i}", days_ago=-(i + 1), verdict=True, truth=False)
        )
    assert not store.history_for(MACHINE, as_of=NOW).downgrade_priority


def test_an_incident_cannot_count_itself(store):
    """Strictly-before, not <=."""
    store.record(outcome(incident_id="self", days_ago=0, verdict=True, truth=False))
    assert store.history_for(MACHINE, as_of=NOW).false_alarms_in_window == 0


def test_naive_timestamps_are_rejected(store):
    with pytest.raises(ValueError, match="timezone-aware"):
        store.history_for(MACHINE, as_of=datetime(2026, 10, 1, 12, 0))


def test_similar_incidents_by_symptom_tag(store):
    store.record(
        outcome(
            incident_id="tagged",
            days_ago=2,
            verdict=True,
            truth=True,
            tags=("bearing_wear", "rotating_unbalance"),
        )
    )
    store.record(outcome(incident_id="untagged", days_ago=1, verdict=True, truth=True))

    history = store.history_for(MACHINE, as_of=NOW, symptom_tags=("bearing_wear",))
    assert [o.incident_id for o in history.similar_incidents] == ["tagged"]


def test_recording_is_idempotent(store):
    """Re-running an eval over the same fixture must be safe, or the
    reruns-are-free property does not hold for memory (PRD S7.8)."""
    for _ in range(3):
        store.record(outcome(incident_id="same", days_ago=1, verdict=True, truth=False))
    assert store.history_for(MACHINE, as_of=NOW).false_alarms_in_window == 1


def test_rules_version_travels_with_the_history(store):
    assert store.history_for(MACHINE, as_of=NOW).rules_version == MEMORY_RULES_VERSION


# --------------------------------------------------------------------------
# The two implementations must AGREE, not merely both work
# --------------------------------------------------------------------------


def test_both_implementations_answer_identically(tmp_path):
    """What makes this a seam. If they diverged, A3 would measure the storage
    backend rather than the memory agent."""
    memory = InMemoryStore()
    sqlite = SqliteStore(tmp_path / "agree.db")

    events = [
        outcome(incident_id="a", days_ago=25, verdict=True, truth=False),
        outcome(incident_id="b", days_ago=10, verdict=True, truth=False),
        outcome(incident_id="c", days_ago=1.5, verdict=True, truth=False),
        outcome(incident_id="d", days_ago=1.0, verdict=True, truth=True, fused=9.0),
        outcome(incident_id="e", days_ago=0.5, verdict=True, truth=True, fused=8.0),
        outcome(incident_id="f", days_ago=40, verdict=True, truth=False),
    ]
    for event in events:
        memory.record(event)
        sqlite.record(event)

    left = memory.history_for(MACHINE, as_of=NOW)
    right = sqlite.history_for(MACHINE, as_of=NOW)

    assert left.false_alarms_in_window == right.false_alarms_in_window == 3
    assert left.confirmed_faults_in_window == right.confirmed_faults_in_window == 2
    assert left.downgrade_priority == right.downgrade_priority is True
    assert left.lower_confidence_threshold == right.lower_confidence_threshold is True

    sqlite.close()
    memory.close()


def test_sqlite_persists_across_connections(tmp_path):
    """The property in_memory cannot provide, and the reason SQLite ships."""
    path = tmp_path / "persist.db"
    first = SqliteStore(path)
    for i in range(3):
        first.record(outcome(incident_id=f"p{i}", days_ago=i + 1, verdict=True, truth=False))
    first.close()

    second = SqliteStore(path)
    assert second.history_for(MACHINE, as_of=NOW).downgrade_priority
    second.close()


# --------------------------------------------------------------------------
# Ablation A3
# --------------------------------------------------------------------------


def test_disabled_store_reports_nothing_but_accepts_writes():
    """A3 is a CONFIGURATION, not a code path: the workflow must run identical
    code in A2 and A3, so any difference is attributable to memory alone."""
    disabled = DisabledStore()
    for i in range(5):
        disabled.record(outcome(incident_id=f"x{i}", days_ago=i, verdict=True, truth=False))

    history = disabled.history_for(MACHINE, as_of=NOW)
    assert not history.downgrade_priority
    assert not history.lower_confidence_threshold
    assert history.similar_incidents == ()
    assert disabled.discarded_writes == 5, (
        "discarded writes are counted so a run can prove memory was disabled, "
        "rather than silently absent because nothing tried to write"
    )


def test_disabled_store_satisfies_the_protocol():
    assert isinstance(DisabledStore(), MemoryStore)


def test_tier3_gate_needs_memory():
    """PRD S11.1a: memory is a NECESSARY condition for Tier 3, never sufficient.
    Confidence alone would fire on 20.0% of incidents; gated it is 2.0%."""
    disabled = DisabledStore()
    history = disabled.history_for(MACHINE, as_of=NOW)
    assert not history.permits_tier3(fused_log_odds=9.9, anomalous=True)

    memory = InMemoryStore()
    for i in range(2):
        memory.record(
            outcome(
                incident_id=f"cf{i}", days_ago=1 + i * 0.5, verdict=True, truth=True, fused=9.0
            )
        )
    enabled = memory.history_for(MACHINE, as_of=NOW)
    assert enabled.permits_tier3(fused_log_odds=9.9, anomalous=True)
    assert not enabled.permits_tier3(fused_log_odds=2.0, anomalous=True)
    assert not enabled.permits_tier3(fused_log_odds=9.9, anomalous=False)


# --------------------------------------------------------------------------
# Factory: A3 is a config flag, not a code path
# --------------------------------------------------------------------------


def test_factory_builds_sqlite_by_default(monkeypatch, tmp_path):
    from core.config import Settings
    from memory.factory import build_memory_store
    from memory.sqlite_store import SqliteStore

    monkeypatch.setenv("IRA_MEMORY__DB_PATH", str(tmp_path / "f.db"))
    built = build_memory_store(Settings())
    assert isinstance(built, SqliteStore)
    built.close()


def test_factory_builds_disabled_store_for_ablation_a3(monkeypatch):
    """One config flag turns A2 into A3."""
    from core.config import Settings
    from memory.factory import build_memory_store

    monkeypatch.setenv("IRA_MEMORY__ENABLED", "false")
    built = build_memory_store(Settings())
    assert isinstance(built, DisabledStore)


def test_disabled_wins_over_impl(monkeypatch):
    """enabled=false must disable memory regardless of which impl is named,
    otherwise A3 could silently run with a working store."""
    from core.config import Settings
    from memory.factory import build_memory_store

    monkeypatch.setenv("IRA_MEMORY__ENABLED", "false")
    monkeypatch.setenv("IRA_MEMORY__IMPL", "in_memory")
    assert isinstance(build_memory_store(Settings()), DisabledStore)


# --------------------------------------------------------------------------
# Where as_of comes from: the remaining leak surface
# --------------------------------------------------------------------------


def test_as_of_is_sourced_from_the_incident_not_the_clock():
    """The guard is only as good as its input.

    Bounding queries below as_of is tested above. This tests the other half: that
    as_of is the incident's OWN timestamp. Wall-clock would satisfy the bound and
    be useless, placing every past incident inside every window -- a silent
    inflation of every memory effect that would not raise and would not fail a
    test.
    """
    from datetime import datetime, timezone

    from harness.synthetic import SyntheticEventSource
    from memory.clock import ClockLeakError, as_of_for, assert_no_clock_leak
    from schemas.incident import Split

    incident = next(iter(SyntheticEventSource(seed=0).events(Split.DEV)))

    assert as_of_for(incident) == incident.timestamp
    assert_no_clock_leak(incident, as_of_for(incident))  # must not raise

    wall_clock = datetime.now(timezone.utc)
    with pytest.raises(ClockLeakError, match="wall-clock"):
        assert_no_clock_leak(incident, wall_clock)


def test_wall_clock_would_inflate_every_memory_effect():
    """Demonstrates WHY the assertion exists, rather than asserting it abstractly.

    Same store, same three false alarms, two values of as_of. Judged at the
    incident's own timestamp the history is empty and the rule does not fire;
    judged at a later wall-clock time all three fall inside the 30-day window and
    it does. Nothing raises in either case -- which is exactly the problem.
    """
    store = InMemoryStore()
    for i in range(3):
        # Recorded 5, 6 and 7 days before NOW.
        store.record(
            outcome(incident_id=f"past{i}", days_ago=5 + i, verdict=True, truth=False)
        )

    # An incident that occurred BEFORE those records: nothing to remember yet.
    incident_time = NOW - timedelta(days=10)
    assert not store.history_for(MACHINE, as_of=incident_time).downgrade_priority

    # The same query at wall-clock time sweeps all three in.
    assert store.history_for(MACHINE, as_of=NOW).downgrade_priority

    store.close()
