"""Replay event source: reads a frozen JSONL fixture.

This is the implementation eval runs use. Generation is where randomness lives;
replay has none, so a results table always refers to one specific file whose
`harness_version` and `reference_rule_version` are recorded in every row.

It is also what enforces "never recompute the oracle at eval time" (PRD S7.5b).
The oracle fields are read from the file exactly as generated. Changing the
fusion rule later cannot silently rewrite historical results, because replaying
an old fixture replays the old rule and says so.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path as FsPath

from schemas.incident import IncidentRecord, Split


class ReplayEventSource:
    """Streams incidents from a JSONL fixture, one record per line."""

    def __init__(self, fixture_path: FsPath | str) -> None:
        self._path = FsPath(fixture_path)
        if not self._path.is_file():
            raise FileNotFoundError(
                f"No incident fixture at {self._path}. Generate one with:\n"
                f"    python scripts/build_harness.py"
            )
        self._version: str | None = None

    @property
    def harness_version(self) -> str:
        """Read from the file's first record rather than from the current code.

        Deliberate: the fixture's version is a property of the DATA, and
        reporting the code's version for old data is exactly the confusion this
        field exists to prevent.
        """
        if self._version is None:
            for record in self._iter_all():
                self._version = record.harness_version
                break
            else:
                raise ValueError(f"fixture {self._path} is empty")
        return self._version

    def _iter_all(self) -> Iterator[IncidentRecord]:
        """Stream and validate every record.

        Validated on read, not trusted: a hand-edited fixture, or one written by
        an older schema version, must fail loudly here rather than produce
        plausible-looking results downstream.
        """
        with self._path.open(encoding="utf-8") as handle:
            for line_no, line in enumerate(handle, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    yield IncidentRecord.model_validate_json(line)
                except Exception as exc:
                    raise ValueError(
                        f"{self._path}:{line_no} failed schema validation. "
                        f"The fixture may predate a schema change -- check "
                        f"schema_version before regenerating.\n  {exc}"
                    ) from exc

    def events(self, split: Split) -> Iterator[IncidentRecord]:
        for record in self._iter_all():
            if record.split is split:
                yield record

    def count(self, split: Split) -> int:
        return sum(1 for _ in self.events(split))


def write_fixture(records: Iterator[IncidentRecord], path: FsPath | str) -> int:
    """Write incidents to JSONL, atomically. Returns the count written.

    Atomic because a half-written fixture that still parses is worse than one
    that fails: it would quietly shorten an eval run and change every aggregate.
    """
    path = FsPath(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")

    written = 0
    with tmp.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(record.model_dump_json() + "\n")
            written += 1

    tmp.replace(path)
    return written
