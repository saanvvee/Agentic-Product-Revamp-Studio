"""In-memory MemoryStore. For tests, and for ablation A3's disabled variant.

Not a mock: it implements the contract completely and correctly. The difference
from the SQLite store is durability, not behaviour, and the dual-implementation
test asserts they agree on every query.
"""

from __future__ import annotations

from datetime import datetime

from memory.base import (
    CONFIRMED_FAULT_WINDOW,
    FALSE_ALARM_WINDOW,
    TIER3_WINDOW,
    IncidentOutcome,
    MachineHistory,
)


class InMemoryStore:
    """Incident history held in a dict keyed by incident_id. No schema, no disk."""

    def __init__(self, *, similar_limit: int = 5) -> None:
        # Keyed by incident_id, not a list. The dual-implementation test caught
        # this: SqliteStore uses INSERT OR REPLACE and is idempotent, while an
        # append-only list counted a re-recorded incident three times. Re-running
        # an eval over the same fixture must be safe (PRD S7.8), and the two
        # stores must agree or A3 would measure the storage backend.
        self._outcomes: dict[str, IncidentOutcome] = {}
        self._similar_limit = similar_limit
        self._closed = False

    def record(self, outcome: IncidentOutcome) -> None:
        if self._closed:
            raise RuntimeError("store used after close()")
        self._outcomes[outcome.incident_id] = outcome

    def history_for(
        self,
        machine_id: str,
        *,
        as_of: datetime,
        symptom_tags: tuple[str, ...] = (),
    ) -> MachineHistory:
        if as_of.tzinfo is None:
            raise ValueError("as_of must be timezone-aware")

        # STRICTLY BEFORE as_of: an incident cannot inform the decision that
        # produced it, and `<=` would let the current incident count itself.
        past = [
            o
            for o in self._outcomes.values()
            if o.machine_id == machine_id and o.timestamp < as_of
        ]

        false_alarms = sum(
            1 for o in past if o.was_false_alarm and as_of - o.timestamp <= FALSE_ALARM_WINDOW
        )
        confirmed = sum(
            1
            for o in past
            if o.was_confirmed_fault and as_of - o.timestamp <= CONFIRMED_FAULT_WINDOW
        )
        confirmed_tier3 = sum(
            1
            for o in past
            if o.was_confirmed_fault and as_of - o.timestamp <= TIER3_WINDOW
        )

        similar: tuple[IncidentOutcome, ...] = ()
        if symptom_tags:
            wanted = set(symptom_tags)
            matches = [o for o in past if wanted & set(o.symptom_tags)]
            matches.sort(key=lambda o: o.timestamp, reverse=True)
            similar = tuple(matches[: self._similar_limit])

        return MachineHistory(
            machine_id=machine_id,
            false_alarms_in_window=false_alarms,
            confirmed_faults_in_window=confirmed,
            confirmed_faults_tier3_window=confirmed_tier3,
            similar_incidents=similar,
        )

    def close(self) -> None:
        self._closed = True


class DisabledStore:
    """Ablation A3: memory disabled, expressed as a store rather than a branch.

    A3 is a CONFIGURATION, not a code path (PRD S12.2). Implementing it as a store
    that always reports an empty history means the orchestrator, critic, and
    guardrail run byte-identical code in A2 and A3, so any difference in results is
    attributable to memory and to nothing else.

    Writes are accepted and discarded rather than raising: the workflow must not
    need to know memory is off, or A3 would be testing a different program.
    """

    def __init__(self) -> None:
        self.discarded_writes = 0
        """Counted so a run can prove memory really was disabled, rather than
        silently absent because nothing ever tried to write."""

    def record(self, outcome: IncidentOutcome) -> None:
        self.discarded_writes += 1

    def history_for(
        self,
        machine_id: str,
        *,
        as_of: datetime,
        symptom_tags: tuple[str, ...] = (),
    ) -> MachineHistory:
        return MachineHistory(
            machine_id=machine_id,
            false_alarms_in_window=0,
            confirmed_faults_in_window=0,
            confirmed_faults_tier3_window=0,
            similar_incidents=(),
        )

    def close(self) -> None:
        return None
