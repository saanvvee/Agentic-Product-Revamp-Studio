"""SQLite MemoryStore. This is the one we ship (PRD S10.2).

No ChromaDB: dropped in PRD v1.1 because all three measurable memory effects are
structured queries, and similarity retrieval by symptom tag is not meaningfully
worse than embedding search over 3 machines and 150 incidents -- while being fully
explainable in a viva.

Timestamps are stored as ISO-8601 UTC strings rather than as Unix floats. Slightly
slower, and worth it: the table is readable with any SQLite browser when a result
looks wrong, which is a debugging property that matters more than microseconds at
this scale.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from memory.base import (
    CONFIRMED_FAULT_WINDOW,
    FALSE_ALARM_WINDOW,
    TIER3_FUSED_THRESHOLD,
    TIER3_WINDOW,
    IncidentOutcome,
    MachineHistory,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS machines (
    machine_id   TEXT PRIMARY KEY,
    zone         TEXT,
    machine_type TEXT,
    install_date TEXT
);

CREATE TABLE IF NOT EXISTS incidents (
    incident_id            TEXT PRIMARY KEY,
    machine_id             TEXT NOT NULL,
    timestamp              TEXT NOT NULL,
    verdict_anomalous      INTEGER NOT NULL,
    ground_truth_anomalous INTEGER NOT NULL,
    fused_log_odds         REAL NOT NULL,
    action                 TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS incident_tags (
    incident_id TEXT NOT NULL,
    symptom_tag TEXT NOT NULL,
    PRIMARY KEY (incident_id, symptom_tag)
);

-- Every query filters by machine and orders by time, so this is the only index
-- that matters. Adding more would be speculation at 150 rows.
CREATE INDEX IF NOT EXISTS idx_incidents_machine_time
    ON incidents (machine_id, timestamp);
"""


def _iso(moment: datetime) -> str:
    if moment.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    return moment.astimezone(timezone.utc).isoformat()


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value)


class SqliteStore:
    """Persistent incident history backed by SQLite."""

    def __init__(self, db_path: Path | str, *, similar_limit: int = 5) -> None:
        self._path = Path(db_path)
        if str(db_path) != ":memory:":
            self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._conn.commit()
        self._similar_limit = similar_limit

    def record(self, outcome: IncidentOutcome) -> None:
        """Persist one incident. Idempotent by incident_id.

        REPLACE rather than INSERT so that re-running an eval over the same
        fixture does not fail on the second pass -- a re-run must be safe, or the
        cache-makes-reruns-free property (PRD S7.8) would not hold for memory.
        """
        with self._conn:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO incidents
                    (incident_id, machine_id, timestamp, verdict_anomalous,
                     ground_truth_anomalous, fused_log_odds, action)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    outcome.incident_id,
                    outcome.machine_id,
                    _iso(outcome.timestamp),
                    int(outcome.verdict_anomalous),
                    int(outcome.ground_truth_anomalous),
                    outcome.fused_log_odds,
                    outcome.action,
                ),
            )
            self._conn.execute(
                "DELETE FROM incident_tags WHERE incident_id = ?",
                (outcome.incident_id,),
            )
            self._conn.executemany(
                "INSERT INTO incident_tags (incident_id, symptom_tag) VALUES (?, ?)",
                [(outcome.incident_id, tag) for tag in outcome.symptom_tags],
            )

    def history_for(
        self,
        machine_id: str,
        *,
        as_of: datetime,
        symptom_tags: tuple[str, ...] = (),
    ) -> MachineHistory:
        """Snapshot as of a point in time.

        Every query below bounds timestamp STRICTLY BELOW `as_of`. Without that,
        replaying an eval set would let an incident see its own future and inflate
        every memory effect -- the kind of leak that produces better numbers and
        means nothing.
        """
        if as_of.tzinfo is None:
            raise ValueError("as_of must be timezone-aware")
        cutoff = _iso(as_of)

        false_alarms = self._conn.execute(
            """
            SELECT COUNT(*) FROM incidents
            WHERE machine_id = ?
              AND timestamp < ?
              AND timestamp >= ?
              AND verdict_anomalous = 1
              AND ground_truth_anomalous = 0
            """,
            (machine_id, cutoff, _iso(as_of - FALSE_ALARM_WINDOW)),
        ).fetchone()[0]

        def confirmed_within(window) -> int:
            return self._conn.execute(
                """
                SELECT COUNT(*) FROM incidents
                WHERE machine_id = ?
                  AND timestamp < ?
                  AND timestamp >= ?
                  AND verdict_anomalous = 1
                  AND ground_truth_anomalous = 1
                  AND fused_log_odds > ?
                """,
                (
                    machine_id,
                    cutoff,
                    _iso(as_of - window),
                    TIER3_FUSED_THRESHOLD,
                ),
            ).fetchone()[0]

        similar: tuple[IncidentOutcome, ...] = ()
        if symptom_tags:
            placeholders = ",".join("?" * len(symptom_tags))
            rows = self._conn.execute(
                f"""
                SELECT DISTINCT i.* FROM incidents i
                JOIN incident_tags t ON t.incident_id = i.incident_id
                WHERE i.machine_id = ?
                  AND i.timestamp < ?
                  AND t.symptom_tag IN ({placeholders})
                ORDER BY i.timestamp DESC
                LIMIT ?
                """,
                (machine_id, cutoff, *symptom_tags, self._similar_limit),
            ).fetchall()
            similar = tuple(self._row_to_outcome(row) for row in rows)

        return MachineHistory(
            machine_id=machine_id,
            false_alarms_in_window=false_alarms,
            confirmed_faults_in_window=confirmed_within(CONFIRMED_FAULT_WINDOW),
            confirmed_faults_tier3_window=confirmed_within(TIER3_WINDOW),
            similar_incidents=similar,
        )

    def _row_to_outcome(self, row: sqlite3.Row) -> IncidentOutcome:
        tags = self._conn.execute(
            "SELECT symptom_tag FROM incident_tags WHERE incident_id = ?",
            (row["incident_id"],),
        ).fetchall()
        return IncidentOutcome(
            incident_id=row["incident_id"],
            machine_id=row["machine_id"],
            timestamp=_parse(row["timestamp"]),
            verdict_anomalous=bool(row["verdict_anomalous"]),
            ground_truth_anomalous=bool(row["ground_truth_anomalous"]),
            fused_log_odds=row["fused_log_odds"],
            action=row["action"],
            symptom_tags=tuple(t["symptom_tag"] for t in tags),
        )

    def close(self) -> None:
        self._conn.close()
