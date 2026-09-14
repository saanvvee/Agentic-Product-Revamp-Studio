"""Where `as_of` comes from -- the one place a memory leak could still enter.

The stores bound every query strictly below `as_of`, and that is tested. But the
guard is only as good as its INPUT: if anything anywhere passes wall-clock time
instead of the incident's own timestamp, the bound is satisfied and useless, and
every memory effect silently inflates because every past incident falls inside
every window.

That failure would not raise, would not fail a test, and would produce better
numbers. It is the same shape as the five discriminate-ability failures in PRD
S20.1 -- a mechanism that works perfectly and measures nothing.

So `as_of` is not a bare datetime that callers construct. It is derived from an
IncidentRecord, by one function, and asserted in the eval loop.
"""

from __future__ import annotations

from datetime import datetime

from schemas.incident import IncidentRecord


class ClockLeakError(RuntimeError):
    """Raised when `as_of` does not match the incident being processed."""


def as_of_for(incident: IncidentRecord) -> datetime:
    """THE only sanctioned way to obtain `as_of` during a run.

    Deliberately trivial. Its value is not the computation but the fact that it
    is a named, greppable chokepoint: `grep -rn "as_of=" ` should show this
    function and nothing else in the production path.
    """
    return incident.timestamp


def assert_no_clock_leak(incident: IncidentRecord, as_of: datetime) -> None:
    """Assert `as_of` is the incident's own timestamp, not wall-clock.

    Called in the eval loop for every incident. Cheap, and it converts a silent
    inflation of every memory effect into a loud failure on the first incident.

    Wall-clock would be roughly a year past our simulated facility's timeline, so
    the failure mode is not subtle once checked -- only once UNchecked.
    """
    if as_of != incident.timestamp:
        raise ClockLeakError(
            f"as_of ({as_of.isoformat()}) is not incident "
            f"{incident.incident_id}'s timestamp ({incident.timestamp.isoformat()}).\n"
            "  Memory queries are bounded by as_of, so a wall-clock value would\n"
            "  place every past incident inside every window and silently inflate\n"
            "  every memory effect. Use memory.clock.as_of_for(incident)."
        )
