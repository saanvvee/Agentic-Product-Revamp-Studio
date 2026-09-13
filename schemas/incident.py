"""Harness output contract (PRD S7.5c). FROZEN alongside schemas.evidence.

One record per incident: the synchronised multi-modal event, its ground truth,
and the cost-optimal oracle plan that orchestration quality is measured against.

Freezing this early is R3's real mitigation. With this fixed, detector work and
orchestration work proceed against synthetic harness output while the real
harness is still being built.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from schemas.evidence import Source

SCHEMA_VERSION = "1.0"
HARNESS_VERSION = "1.0"


class AmbiguityLevel(str, Enum):
    """How hard this incident is meant to be (PRD S7.5a).

    Constructed deliberately in calibrated detector-score space, not in physics:
    our machines are synthetic composites, so no cross-modal physical law exists
    to violate. Declared as a limitation in the report.
    """

    CLEAR_ANOMALOUS = "clear_anomalous"
    CLEAR_NORMAL = "clear_normal"
    BORDERLINE = "borderline"
    DECEPTIVE = "deceptive"


class Path(str, Enum):
    """The three structurally different execution paths (PRD S5.6)."""

    FAST = "fast"
    PARALLEL = "parallel"
    SEQUENTIAL = "sequential"


class Split(str, Enum):
    DEV = "dev"
    TEST = "test"
    DEMO = "demo"


class CachedScore(BaseModel):
    """A detector's pre-computed answer for one source on one incident.

    Computed once by the harness so the oracle can be brute-forced offline
    without re-running detectors 16 times per incident, and so eval runs are
    reproducible. This is the SAME calibrated score the live system will see.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    score_raw: float
    confidence: float = Field(ge=0.0, le=1.0)


class IncidentRecord(BaseModel):
    """One synchronised multi-modal incident with ground truth and oracle plan."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    incident_id: str = Field(min_length=1)
    machine_id: str = Field(min_length=1)
    timestamp: datetime

    # --- payload paths: real dataset files, synthetically aligned (PRD S7.5) ---
    audio_clip_path: str
    image_path: str
    telemetry_row: dict[str, float]

    # --- ground truth ---
    is_anomalous: bool
    """Facility-level truth for this incident. The thing a decision is scored against."""

    ambiguity_level: AmbiguityLevel

    expected_path: Path
    """DESCRIPTIVE ONLY -- never a scored target (PRD S7.5b).

    v1.0 scored "path selection accuracy" against this and that was circular:
    the label was assigned by us from the ambiguity level, so a three-line
    if/else over the same rule scores 100%. Kept solely to stratify results by
    intended difficulty. Orchestration quality is measured as regret against the
    oracle below.
    """

    cached_scores: dict[Source, CachedScore]

    # --- cost-optimal oracle (PRD S7.5b) ---
    oracle_exists: bool
    """False when NO subset of sources yields the correct verdict.

    A legitimate and informative case, not an error: these incidents SHOULD
    escalate, and they are the ground truth for escalation precision (S12.1).
    """

    oracle_sources: list[Source] = Field(default_factory=list)
    """Minimum-cost sufficient subset. Empty iff oracle_exists is False."""

    oracle_cost_ms: int = Field(ge=0)
    oracle_cost_tokens: int = Field(ge=0)

    split: Split
    seed: int
    harness_version: str = HARNESS_VERSION
    schema_version: str = SCHEMA_VERSION

    @field_validator("timestamp")
    @classmethod
    def _require_timezone(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware (use UTC)")
        return v.astimezone(timezone.utc)

    @model_validator(mode="after")
    def _oracle_consistency(self) -> "IncidentRecord":
        """The oracle's two halves must agree.

        Asserted rather than commented because an inconsistent oracle produces
        regret numbers that look plausible and are wrong -- the worst kind of bug
        for a results table nobody re-derives by hand.
        """
        if self.oracle_exists and not self.oracle_sources:
            raise ValueError("oracle_exists is True but oracle_sources is empty")
        if not self.oracle_exists:
            if self.oracle_sources:
                raise ValueError("oracle_exists is False but oracle_sources is non-empty")
            if self.oracle_cost_ms or self.oracle_cost_tokens:
                raise ValueError("oracle_exists is False but an oracle cost was recorded")
        if len(set(self.oracle_sources)) != len(self.oracle_sources):
            raise ValueError("oracle_sources contains duplicates")
        return self
