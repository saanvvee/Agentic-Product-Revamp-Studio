"""The event source seam.

Two implementations, both real:

    synthetic.py  generates incidents, with REAL labelling and REAL oracle
                  computation. Only the bytes behind the payload paths are
                  stand-ins until the datasets land.
    replay.py     reads a frozen JSONL fixture, so an eval run is reproducible
                  and the oracle is never recomputed (PRD S7.5b).

The split matters for reproducibility: generation is where randomness lives, and
replay has none. Eval runs use replay so that a results table always refers to a
specific frozen file with a `harness_version` and a `reference_rule_version`.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Protocol, runtime_checkable

from schemas.incident import IncidentRecord, Split


@runtime_checkable
class EventSource(Protocol):
    """Yields incidents for the system to process.

    Deliberately an iterator rather than a list: the replay source streams from
    disk, and an eval run over 150 incidents should not require holding every
    cached score in memory at once.
    """

    @property
    def harness_version(self) -> str:
        """Stamped into every record. Regenerating the harness after results
        exist, without a version bump, is how a results table silently stops
        matching its data (PRD S7.5c)."""
        ...

    def events(self, split: Split) -> Iterator[IncidentRecord]:
        """Yield every incident in one split, in a deterministic order."""
        ...

    def count(self, split: Split) -> int:
        """How many incidents that split holds. Used for progress and for
        asserting an eval run saw everything it should have."""
        ...
