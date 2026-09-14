"""The memory store seam, and the four decision rules it exists to serve.

Memory must CHANGE DECISIONS, not add colour (PRD S10.3). Ablation A3 disables it
and must show a measurable difference; if it does not, the memory agent is
decoration and the report should say so rather than pretend otherwise.

MEASURED FIRING RATES (test split, n=150, harness 1.1). Every one of these was
checked against the data before this module was written, because three previous
thresholds in this project were inert or degenerate and none of their tests
caught it:

    downgrade_priority     >=3 false alarms in 30 days      39 incidents (26.0%)
    lower_threshold        >=2 confirmed faults in 2 days     3 incidents ( 2.0%)
    tier3_gate             >=2 confirmed faults in 3 days     3 incidents ( 2.0%)
    similar_incidents      tag match, always available          n/a

The three gating rules are mutually DISJOINT on the test split (union exactly
39+3+3 = 45, 30.0%), so A3 ablates three separable mechanisms rather than one
tangled effect, and each rule's contribution is individually attributable.

That disjointness is a PROPERTY OF THE WINDOW WIDTHS, not a structural guarantee,
and it was nearly lost. `lower_threshold` uses a 2-day window while `tier3_gate`
uses 3 days. Measured sensitivity:

    lower_threshold window   fires   overlap with tier3_gate
        1 day                    0       0
        2 days                   3       0     <- chosen
        3 days                  22       3     <- tier3 becomes a strict SUBSET
        7 days                  80       3

At 3 days the Tier 3 incidents are entirely contained in `lower_threshold`, so A3
could not separate their effects. The 2-day window is therefore a deliberate
choice made to keep the ablation interpretable, and it is recorded here rather
than left to look arbitrary.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol, runtime_checkable

# --- Rule parameters. Frozen with MEMORY_RULES_VERSION below. --------------

FALSE_ALARM_WINDOW = timedelta(days=30)
FALSE_ALARM_MIN_COUNT = 3
"""PRD S10.3 as written. Kept at 30 days deliberately.

Narrowing it to 7 days during tuning produced a firing rate of exactly 0.0%,
because only 11 false alarms occur across 3 machines in 150 incidents -- roughly
one per machine per 18 days, so >=3 within any 7-day window is ARITHMETICALLY
IMPOSSIBLE, not merely unlikely.

The general lesson, recorded in PRD S20.1: a threshold on a COUNT must be checked
against the base rate of the thing counted, not only against the window width.
"""

CONFIRMED_FAULT_WINDOW = timedelta(days=2)
CONFIRMED_FAULT_MIN_COUNT = 2
"""2 days, and the reason is experimental design rather than domain intuition.

**The window was selected so that the three memory rules remain mutually
disjoint, which is what enables per-mechanism attribution in ablation A3.** At a
3-day window the Tier 3 incident set becomes a strict SUBSET of this rule's set,
and A3 can no longer say which mechanism produced which part of the effect --
it measures their union and nothing finer.

Measured, with `TIER3_WINDOW` fixed at 3 days (test split, n=150):

    window   this rule fires   overlap with Tier 3
      1 day         0                  0            rule is inert
      2 days        3                  0            <- chosen: disjoint
      3 days       22                  3            Tier 3 fully contained
      7 days       80                  3            Tier 3 fully contained

State it plainly if asked why 2 and not 3: the rules must be separable for the
ablation to attribute effects to individual mechanisms, and 3 days destroys that
separability. This is a design choice about what the experiment can measure, not
a claim that industrial faults recur on a 2-day rather than 3-day rhythm.
"""

TIER3_WINDOW = timedelta(days=3)
TIER3_MIN_FAULTS = 2
TIER3_FUSED_THRESHOLD = 5.0
"""PRD S11.1a. Confidence alone put Tier 3 at 20.0% of incidents -- one in five
halting a production line is not a safety control. Memory-gated it is 2.0%."""

MEMORY_RULES_VERSION = "memrules-v1"
"""Frozen 14 September 2026, before any evaluation run.

Stamped into results beside `budget-v1` and `logodds-v1`. These windows were
chosen by measuring firing rates against the data; changing them after results
exist would be indistinguishable from tuning until the numbers look good.
"""


@dataclass(frozen=True, slots=True)
class IncidentOutcome:
    """One past incident, as memory records it.

    `was_false_alarm` is the distinction the whole store turns on: an incident
    flagged anomalous that turned out normal. It is knowable only after the fact,
    which is why it lives in persistent memory rather than being derivable from
    the current evidence.
    """

    incident_id: str
    machine_id: str
    timestamp: datetime
    verdict_anomalous: bool
    """What the system decided."""

    ground_truth_anomalous: bool
    """What was actually true. Available in evaluation; in a real deployment this
    would arrive later from a technician's report."""

    fused_log_odds: float
    action: str
    symptom_tags: tuple[str, ...] = ()

    @property
    def was_false_alarm(self) -> bool:
        return self.verdict_anomalous and not self.ground_truth_anomalous

    @property
    def was_confirmed_fault(self) -> bool:
        """Flagged anomalous, confirmed anomalous, AND decisively so.

        The confidence requirement matters: a barely-anomalous verdict that
        happened to be right is not a 'confirmed fault' for the purpose of
        escalating a later incident to Tier 3. Halting a line on the strength of
        two lucky guesses would be exactly wrong.
        """
        return (
            self.verdict_anomalous
            and self.ground_truth_anomalous
            and self.fused_log_odds > TIER3_FUSED_THRESHOLD
        )


@dataclass(frozen=True, slots=True)
class MachineHistory:
    """What memory reports about one machine at one moment.

    Returned as a whole rather than as four separate queries so that every rule
    is evaluated against ONE consistent snapshot. Querying per-rule would risk
    two rules seeing different histories if a write landed between them.
    """

    machine_id: str
    false_alarms_in_window: int
    confirmed_faults_in_window: int
    confirmed_faults_tier3_window: int
    similar_incidents: tuple[IncidentOutcome, ...]
    rules_version: str = MEMORY_RULES_VERSION

    # --- the four decision effects (PRD S10.3, S11.1a) --------------------

    @property
    def downgrade_priority(self) -> bool:
        """Repeat offender: >=3 false alarms in 30 days. ~26% of incidents."""
        return self.false_alarms_in_window >= FALSE_ALARM_MIN_COUNT

    @property
    def lower_confidence_threshold(self) -> bool:
        """Recently faulty: >=2 confirmed faults in 2 days. ~2% of incidents."""
        return self.confirmed_faults_in_window >= CONFIRMED_FAULT_MIN_COUNT

    def permits_tier3(self, *, fused_log_odds: float, anomalous: bool) -> bool:
        """The Tier 3 precondition (PRD S11.1a).

        Memory is a NECESSARY condition, never a sufficient one: high confidence
        alone cannot halt a line. That is what keeps the rate at 2.0% rather than
        20.0%.
        """
        return (
            anomalous
            and fused_log_odds > TIER3_FUSED_THRESHOLD
            and self.confirmed_faults_tier3_window >= TIER3_MIN_FAULTS
        )

    def as_log_fields(self) -> dict[str, object]:
        """For decisions.jsonl. A memory effect that fired without being recorded
        is indistinguishable from one that did not fire."""
        return {
            "memory_false_alarms": self.false_alarms_in_window,
            "memory_confirmed_faults": self.confirmed_faults_in_window,
            "memory_downgrade_priority": self.downgrade_priority,
            "memory_lower_threshold": self.lower_confidence_threshold,
            "memory_similar_count": len(self.similar_incidents),
            "memory_rules_version": self.rules_version,
        }


@runtime_checkable
class MemoryStore(Protocol):
    """Persistent incident history. Two implementations: SQLite and in-memory.

    Deliberately narrow. The store answers questions and records outcomes; it does
    not decide anything. The RULES live on MachineHistory above, so they are
    identical no matter which implementation answered -- which is what makes the
    dual-implementation test meaningful rather than a check that two databases
    both store rows.
    """

    def record(self, outcome: IncidentOutcome) -> None:
        """Persist one completed incident."""
        ...

    def history_for(
        self, machine_id: str, *, as_of: datetime, symptom_tags: tuple[str, ...] = ()
    ) -> MachineHistory:
        """Snapshot of what is known about a machine at a point in time.

        `as_of` is mandatory and not defaulted to 'now'. Evaluation replays
        incidents in order, and a store that answered with everything it holds --
        including incidents from after `as_of` -- would leak the future into a
        decision and silently inflate every memory effect.
        """
        ...

    def close(self) -> None:
        ...
