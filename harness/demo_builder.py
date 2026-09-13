"""Hand-construct the demo split so every scenario in PRD S3.2 is reachable.

WHY THIS IS NOT THE SAMPLER

The test and demo splits have different jobs, and only one of them can be done by
sampling:

    test split  must be REPRESENTATIVE -- it produces the reported numbers
    demo split  must be COMPLETE -- it must exercise every path, including rare ones

Sampling can only achieve the first. Measured: the sampled 8-incident demo split
could **never** trigger Scenario D (Tier 3 guardrail block), because the Tier 3
precondition needs two prior confirmed faults on the same machine and 8 incidents
round-robined across 3 machines cannot accumulate them. A demo that cannot show
the safety story is a demo of the common case, not of this system.

So the demo split is built by explicit construction, incident by incident, with
Scenario D's precondition chain planted deliberately.

THE GUARD THAT MAKES THIS SAFE: this split is written to
`incidents.demo_constructed.jsonl`, and `eval/` asserts that no results table is
ever computed over it. Being non-representative by design, it would poison any
aggregate it reached. Same class of protection as the token-ledger regression test.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta, timezone

from harness.reference_rule import REFERENCE_RULE_VERSION, compute_oracle
from harness.synthetic import (
    FACILITY,
    QUERYABLE,
    STRONG_ANOMALOUS,
    STRONG_NORMAL,
    UNINFORMATIVE,
    WEAK_ANOMALOUS,
    WEAK_NORMAL,
    Machine,
    _payload_paths,
    _telemetry_row,
)
from schemas.evidence import Source
from schemas.incident import (
    HARNESS_VERSION,
    AmbiguityLevel,
    CachedScore,
    IncidentRecord,
    Path,
    Split,
)
import random

DEMO_FIXTURE_NAME = "incidents.demo_constructed.jsonl"
"""Deliberately distinct from incidents.demo.jsonl so it cannot be mistaken for a
sampled split, and so a stray glob in an eval script does not silently pick it up.
"""

A, V, T = QUERYABLE


class DemoIncidentSpec:
    """One hand-specified incident: exact confidences, exact intent."""

    def __init__(
        self,
        *,
        label: str,
        scenario: str,
        machine: Machine,
        is_anomalous: bool,
        ambiguity: AmbiguityLevel,
        expected_path: Path,
        confidences: dict[Source, float],
        note: str,
    ) -> None:
        self.label = label
        self.scenario = scenario
        self.machine = machine
        self.is_anomalous = is_anomalous
        self.ambiguity = ambiguity
        self.expected_path = expected_path
        self.confidences = confidences
        self.note = note


def _specs() -> list[DemoIncidentSpec]:
    """The demo script, in order, as data.

    Machine assignment is deliberate rather than round-robin: Scenario D needs
    three incidents on the SAME machine, and that only happens if it is planted.
    """
    fan_00, fan_02, fan_04 = FACILITY

    return [
        # --- Scenario A: unambiguous fault, fast path -------------------
        DemoIncidentSpec(
            label="demo_a_fast",
            scenario="A: unambiguous fault (fast path)",
            machine=fan_02,
            is_anomalous=True,
            ambiguity=AmbiguityLevel.CLEAR_ANOMALOUS,
            expected_path=Path.FAST,
            confidences={A: 0.95, V: 0.92, T: 0.93},
            note="All three decisive. The system should act on one source and not "
            "waste budget corroborating what is already clear.",
        ),
        # --- Scenario A': clear normal, also fast ----------------------
        DemoIncidentSpec(
            label="demo_a_normal",
            scenario="A': unambiguous normal (fast path, dismiss)",
            machine=fan_04,
            is_anomalous=False,
            ambiguity=AmbiguityLevel.CLEAR_NORMAL,
            expected_path=Path.FAST,
            confidences={A: 0.06, V: 0.08, T: 0.05},
            note="Dismissal is also a decision. Included so the demo shows the "
            "system declining to investigate, not only escalating.",
        ),
        # --- Scenario B: ambiguous single modality, parallel -----------
        DemoIncidentSpec(
            label="demo_b_parallel",
            scenario="B: ambiguous single-modality signal (parallel fan-out)",
            machine=fan_04,
            is_anomalous=True,
            ambiguity=AmbiguityLevel.BORDERLINE,
            expected_path=Path.PARALLEL,
            confidences={A: 0.93, V: 0.50, T: 0.48},
            note="Audio is decisive, the others uninformative. The orchestrator "
            "cannot know which is which in advance, so it fans out.",
        ),
        # --- Scenario C: weak everywhere, sequential escalation --------
        DemoIncidentSpec(
            label="demo_c_sequential",
            scenario="C: weak signals across all modalities (escalation loop)",
            machine=fan_00,
            is_anomalous=True,
            ambiguity=AmbiguityLevel.DECEPTIVE,
            expected_path=Path.SEQUENTIAL,
            confidences={A: 0.62, V: 0.38, T: 0.55},
            note="Two weak sources disagreeing in sign, one uninformative. The "
            "pair nearly cancels under log-odds, so no single source resolves it.",
        ),
        # --- Scenario D: the Tier 3 precondition chain -----------------
        # THREE incidents on ONE machine. The first two are confirmed faults that
        # populate memory; the third is what the guardrail blocks. This chain is
        # the entire reason the demo split cannot be sampled.
        DemoIncidentSpec(
            label="demo_d_fault_1",
            scenario="D setup (1/3): first confirmed fault on fan_00",
            machine=fan_00,
            is_anomalous=True,
            ambiguity=AmbiguityLevel.CLEAR_ANOMALOUS,
            expected_path=Path.FAST,
            confidences={A: 0.94, V: 0.91, T: 0.90},
            note="Populates memory. Not interesting in itself; it exists so the "
            "third incident has a history to be judged against.",
        ),
        DemoIncidentSpec(
            label="demo_d_fault_2",
            scenario="D setup (2/3): second confirmed fault, same machine",
            machine=fan_00,
            is_anomalous=True,
            ambiguity=AmbiguityLevel.CLEAR_ANOMALOUS,
            expected_path=Path.FAST,
            confidences={A: 0.96, V: 0.93, T: 0.94},
            note="Second confirmed fault within the 3-day window. After this the "
            "Tier 3 precondition (>=2 confirmed faults) is satisfied.",
        ),
        DemoIncidentSpec(
            label="demo_d_tier3_block",
            scenario="D: high-impact action BLOCKED pending human approval",
            machine=fan_00,
            is_anomalous=True,
            ambiguity=AmbiguityLevel.CLEAR_ANOMALOUS,
            expected_path=Path.FAST,
            confidences={A: 0.97, V: 0.95, T: 0.96},
            note="THE SAFETY STORY. Third confirmed fault on the same machine "
            "inside 3 days, at high fused confidence, so the recommended action "
            "is WO-HALT-LINE (Tier 3) and the guardrail must block it pending "
            "human approval. This incident is why the demo split is constructed.",
        ),
        # --- Scenario E: repeat offender, memory downgrades priority ---
        # fan_02 accumulates false alarms so the >=3-in-30-days rule fires.
        DemoIncidentSpec(
            label="demo_e_false_alarm_1",
            scenario="E setup (1/3): false alarm on fan_02",
            machine=fan_02,
            is_anomalous=False,
            ambiguity=AmbiguityLevel.BORDERLINE,
            expected_path=Path.PARALLEL,
            confidences={A: 0.88, V: 0.35, T: 0.45},
            note="Flagged anomalous but actually normal: a false alarm that "
            "memory must remember. Note the confidences are chosen so the "
            "incident is RESOLVABLE -- telemetry reads correctly at 0.45, so a "
            "system that checked it cheaply would not have been fooled. A false "
            "alarm every source got wrong would be an unresolvable incident, "
            "which is a different scenario (F).",
        ),
        DemoIncidentSpec(
            label="demo_e_false_alarm_2",
            scenario="E setup (2/3): second false alarm on fan_02",
            machine=fan_02,
            is_anomalous=False,
            ambiguity=AmbiguityLevel.BORDERLINE,
            expected_path=Path.PARALLEL,
            confidences={A: 0.90, V: 0.30, T: 0.40},
            note="Second false alarm, also resolvable: audio over-reads while the "
            "cheaper sources read correctly.",
        ),
        DemoIncidentSpec(
            label="demo_e_false_alarm_3",
            scenario="E setup (3/3): third false alarm on fan_02",
            machine=fan_02,
            is_anomalous=False,
            ambiguity=AmbiguityLevel.BORDERLINE,
            expected_path=Path.PARALLEL,
            confidences={A: 0.89, V: 0.40, T: 0.42},
            note="Third false alarm inside 30 days. After this the >=3-in-30-days "
            "rule fires and memory downgrades this machine.",
        ),
        DemoIncidentSpec(
            label="demo_e_downgraded",
            scenario="E: repeat offender, escalation priority DOWNGRADED by memory",
            machine=fan_02,
            is_anomalous=False,
            ambiguity=AmbiguityLevel.BORDERLINE,
            expected_path=Path.PARALLEL,
            confidences={A: 0.87, V: 0.38, T: 0.44},
            note="Near-identical in evidence to the three above, but memory now "
            "reports 3 false alarms in 30 days, so priority is downgraded. Run "
            "this with memory disabled (A3) to show the decision change.",
        ),
        # --- Unresolvable: correct escalation --------------------------
        DemoIncidentSpec(
            label="demo_f_unresolvable",
            scenario="F: no evidence can resolve this -- escalate to human",
            machine=fan_04,
            is_anomalous=True,
            ambiguity=AmbiguityLevel.DECEPTIVE,
            expected_path=Path.SEQUENTIAL,
            confidences={A: 0.35, V: 0.30, T: 0.40},
            note="Every source contradicts the ground truth, so oracle_exists is "
            "False. The correct behaviour is to decline and escalate; a confident "
            "answer here is wrong even if it happens to guess right.",
        ),
    ]


def build_demo_incidents(
    *, start: datetime | None = None, seed: int = 0
) -> Iterator[IncidentRecord]:
    """Yield the constructed demo split, in scenario order.

    Spacing is 12 hours rather than the sampler's 6, so the Scenario D chain
    (three faults) and the Scenario E chain (four false alarms) both fit inside
    their respective memory windows while remaining in a plausible order.
    """
    start = start or datetime(2026, 10, 1, tzinfo=timezone.utc)
    rng = random.Random(f"demo:{seed}")

    for index, spec in enumerate(_specs()):
        confidences = spec.confidences
        oracle = compute_oracle(confidences, spec.is_anomalous)

        source_is_anomalous = {s: c > 0.5 for s, c in confidences.items()}
        paths = _payload_paths(spec.machine, source_is_anomalous)

        yield IncidentRecord(
            incident_id=spec.label,
            machine_id=spec.machine.machine_id,
            timestamp=start + timedelta(hours=12 * index),
            audio_clip_path=paths["audio_clip_path"],
            image_path=paths["image_path"],
            telemetry_row=_telemetry_row(spec.machine, spec.is_anomalous, rng),
            is_anomalous=spec.is_anomalous,
            ambiguity_level=spec.ambiguity,
            is_unresolvable=not oracle.exists,
            expected_path=spec.expected_path,
            cached_scores={
                source: CachedScore(
                    score_raw=round((conf - 0.5) * 20.0, 4),
                    confidence=round(conf, 4),
                )
                for source, conf in confidences.items()
            },
            oracle_exists=oracle.exists,
            oracle_sources=list(oracle.sources),
            oracle_cost_ms=oracle.cost_ms,
            reference_rule_version=REFERENCE_RULE_VERSION,
            split=Split.DEMO,
            seed=seed,
        )


def scenario_notes() -> list[tuple[str, str, str]]:
    """(incident_id, scenario, note) for the demo script and the report."""
    return [(s.label, s.scenario, s.note) for s in _specs()]
