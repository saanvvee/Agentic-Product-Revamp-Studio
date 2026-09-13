"""The evidence report contract (PRD S5.4). FROZEN.

Every evidence source returns exactly this structure. Changing it breaks three
workstreams at once, so a change here is a schema amendment, not a refactor:
bump SCHEMA_VERSION, record it in the PRD amendment log, and tell the team.

Why this is frozen first: it decouples the workstreams. Once this exists,
detector work, orchestration work, and evaluation work proceed in parallel
against a contract rather than against each other.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

SCHEMA_VERSION = "1.0"


class Source(str, Enum):
    """Where a piece of evidence came from.

    These are the queryable sources in PRD S5.6's sequential cap of 4. Adding a
    member changes the oracle's subset enumeration (2^n), so it is a schema
    amendment, not a convenience.
    """

    AUDIO = "audio"
    VISION = "vision"
    TELEMETRY = "telemetry"
    MEMORY = "memory"
    MANUAL = "manual"


class Verdict(str, Enum):
    """A source's own reading of the evidence it gathered.

    INCONCLUSIVE is a first-class answer, not a failure. A source that says "I
    cannot tell" is giving the orchestrator real information, and escalation
    precision (PRD S12.1) depends on that distinction being recorded honestly.
    """

    NORMAL = "normal"
    ANOMALOUS = "anomalous"
    INCONCLUSIVE = "inconclusive"


class EvidenceReport(BaseModel):
    """One source's answer about one machine at one moment.

    The orchestrator never sees raw sensor data (PRD S4.2) -- it sees these.
    That is what keeps orchestration logic modality-agnostic and testable.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    source: Source
    machine_id: str = Field(min_length=1)
    verdict: Verdict

    confidence: float = Field(ge=0.0, le=1.0)
    """Calibrated to [0, 1] (PRD S8.4). NOT a raw detector score.

    The orchestrator's guard bands are defined on this value, so an uncalibrated
    number here silently invalidates every routing decision downstream.
    """

    score_raw: float
    """The detector's native output before calibration. Unbounded by design.

    Kept so calibration can be re-fitted or audited without re-running
    detectors, and so the report can show the raw-to-calibrated mapping.
    """

    evidence_summary: str = Field(min_length=1, max_length=500)
    """One sentence of natural language, for the incident log and the critic."""

    supporting_detail: dict[str, Any] = Field(default_factory=dict)
    """Source-specific extras (bounding boxes, band energies, feature names).

    Deliberately untyped: it must never carry anything the orchestrator routes
    on, or the modality-agnostic property in PRD S4.2 is lost.
    """

    cost_ms: int = Field(ge=0)
    """MEASURED domain cost, not wall-clock of the whole call (PRD S5.5b).

    Detector inference plus modelled sensor acquisition. LLM latency is system
    overhead and is never recorded here.
    """

    cost_tokens: int = Field(ge=0)
    """Tokens actually spent acquiring this evidence. Zero for pure detectors."""

    timestamp: datetime
    schema_version: str = SCHEMA_VERSION

    @field_validator("timestamp")
    @classmethod
    def _require_timezone(cls, v: datetime) -> datetime:
        """Reject naive datetimes.

        Incidents are ordered across a simulated facility and compared against
        persistent history; a naive timestamp silently means "some timezone" and
        corrupts that ordering in a way that is very hard to see later.
        """
        if v.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware (use UTC)")
        return v.astimezone(timezone.utc)

    @property
    def is_decisive(self) -> bool:
        """True when this report alone could justify acting.

        Deliberately NOT the guard-band check: this asks whether the source
        committed to an answer, while the guard bands (config, PRD S5.5) decide
        whether the orchestrator trusts it. Keeping them separate is what lets
        the bands be tuned without touching the contract.
        """
        return self.verdict is not Verdict.INCONCLUSIVE
