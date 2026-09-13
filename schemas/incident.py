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

SCHEMA_VERSION = "1.2"
"""1.1 removed oracle_cost_tokens and added reference_rule_version (PRD v1.3).
1.2 added is_unresolvable, distinct from ambiguity_level, so that escalation
precision can separate 'correctly declined an impossible incident' from 'gave up
on a merely hard one' (PRD v1.4)."""

HARNESS_VERSION = "1.0"

REFERENCE_RULE_VERSION = "logodds-v1"
"""The fusion rule used to decide oracle sufficiency (PRD S7.5b).

'logodds-v1' is sum of log-odds over clamped confidences, anomalous if > 0.
If the M1 calibration check fails (R7), the documented fallback is
'maxconf-v1', and that string must be recorded here for affected fixtures.
"""


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

    is_unresolvable: bool = False
    """True when the harness CONSTRUCTED this incident so every source
    contradicts ground truth (PRD S7.5a).

    Deliberately distinct from `ambiguity_level` and from `not oracle_exists`,
    because collapsing them confounds two different behaviours in the escalation
    metric (PRD S12.1):

        escalated on an unresolvable incident  -> CORRECT. No evidence could have
                                                  resolved it; declining to answer
                                                  is the right action.
        escalated on a merely deceptive one    -> possibly a FAILURE. The evidence
                                                  was sufficient and the system
                                                  gave up anyway.

    Every unresolvable incident is deceptive, but most deceptive incidents are
    resolvable, so `ambiguity_level` cannot stand in for this. Without the
    separate field, escalation precision would silently reward giving up on hard
    cases.

    Note this is the harness's INTENT, whereas `oracle_exists` is the measured
    consequence under the reference rule. They agree in practice and a validator
    below asserts it; keeping both means a future rule change that breaks the
    correspondence fails loudly instead of quietly shifting the metric.
    """

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
    """Domain cost of the oracle set, in milliseconds. ONE ledger only.

    There is deliberately no oracle_cost_tokens: per PRD S5.5b tokens are
    measured but never budgeted, so the oracle optimises a single quantity and
    the two-ledger ordering ambiguity never arises. An earlier draft of this
    schema carried a token field that S5.5b had already eliminated.
    """

    reference_rule_version: str = REFERENCE_RULE_VERSION
    """Which fusion rule decided sufficiency (PRD S7.5b).

    Travels WITH the data because the oracle is frozen at generation time and
    never recomputed. Without this, changing the fusion rule would silently
    rewrite every historical results table -- the same class of failure as R23,
    with the same fix: a version string beside the numbers it explains.
    """

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
            if self.oracle_cost_ms:
                raise ValueError("oracle_exists is False but an oracle cost was recorded")
        if len(set(self.oracle_sources)) != len(self.oracle_sources):
            raise ValueError("oracle_sources contains duplicates")

        # The harness's intent and the reference rule's measured outcome must
        # agree. They are separate fields on purpose (see is_unresolvable), and
        # this assertion is what makes keeping both worthwhile: if a future rule
        # change breaks the correspondence, it fails here rather than quietly
        # shifting every escalation number.
        if self.is_unresolvable and self.oracle_exists:
            raise ValueError(
                "is_unresolvable is True but the reference rule found a "
                "sufficient subset -- the construction and the rule disagree"
            )
        if not self.oracle_exists and not self.is_unresolvable:
            raise ValueError(
                "no sufficient subset exists but is_unresolvable is False -- an "
                "incident became unresolvable by accident, which means the "
                "ambiguity construction is not doing what it claims"
            )
        return self
