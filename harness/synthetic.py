"""Synthetic facility generator: real labelling, real oracle, stand-in payloads.

This is the module that closes B8. The original critique said the "deceptive"
ambiguity level was **unbuildable**, because our machines are synthetic
composites of three unrelated datasets and there is no physical law linking a
fan's audio to a metal nut's image, so no rule could say when two modalities
"conflict".

Constructing directly in **calibrated score space** dissolves that problem. We do
not search real clips for a cross-modal conflict that does not exist; we sample
confidences with a specified statistical relationship and then attach real files
whose class (normal or anomalous) matches the sampled sign. The conflict is
defined where it is actually measurable -- in the detector's own output -- and the
report declares that openly.

DESIGN DECISION, taken deliberately (PRD S7.5a): the per-level score
distributions are FIXED PARAMETERS, not fitted to real detector output. Fitting
would block the generator on datasets that are still downloading, and fixed
parameters keep the generator reproducible and hand-checkable. The honest cost is
that the mock and real detectors will differ in distribution, so the mock-to-real
swap is one line of config but NOT distribution-preserving. M1 therefore carries a
mandated check: compare real PaDiM score distributions against these, report the
divergence, and refit if it is large. See `scripts/compare_score_distributions.py`.
"""

from __future__ import annotations

import random
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass

from harness.reference_rule import (
    DECLARED_COST_MS,
    REFERENCE_RULE_VERSION,
    compute_oracle,
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

# --------------------------------------------------------------------------
# The simulated facility (PRD S7.5, scope cut to 3 machines in v1.1)
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Machine:
    """One simulated asset, composed from three unrelated real datasets.

    `mimii_id` is what makes machine identity real rather than invented: the four
    MIMII fan model IDs (00, 02, 04, 06) are genuinely different physical units,
    so per-machine history in the memory store refers to something.
    """

    machine_id: str
    zone: str
    mimii_id: str
    mvtec_category: str
    ai4i_product_type: str


FACILITY: tuple[Machine, ...] = (
    Machine("zone_a_fan_00", "zone_a", "id_00", "metal_nut", "L"),
    Machine("zone_a_fan_02", "zone_a", "id_02", "screw", "M"),
    Machine("zone_b_fan_04", "zone_b", "id_04", "metal_nut", "H"),
)
"""Three machines across two zones. Two zones rather than three so that
zone-level history has at least two machines to aggregate over, which is what
the memory agent's false-alarm rule needs to be non-trivial."""


# --------------------------------------------------------------------------
# Score-space construction (PRD S7.5a)
# --------------------------------------------------------------------------

QUERYABLE: tuple[Source, ...] = (Source.AUDIO, Source.VISION, Source.TELEMETRY)
"""The three sensing modalities the harness emits.

MEMORY and MANUAL are real sources the orchestrator may query, but they are
derived from history and documents rather than from this incident's sensors, so
the harness does not generate scores for them. The oracle therefore enumerates
over 2^3 = 8 subsets, not 16.
"""


@dataclass(frozen=True, slots=True)
class ScoreBand:
    """A uniform confidence band, closed on the low end.

    Uniform rather than Gaussian on purpose: the band edges are the thing that
    matters for constructing ambiguity relative to the guard bands, and a
    truncated Gaussian would put most mass in the middle of each band where it
    tells us least.
    """

    low: float
    high: float

    def sample(self, rng: random.Random) -> float:
        return rng.uniform(self.low, self.high)


STRONG_ANOMALOUS = ScoreBand(0.88, 0.98)
"""Above the 0.85 guard band: decisive on its own."""

STRONG_NORMAL = ScoreBand(0.02, 0.12)
"""Below the 0.15 guard band: decisive on its own."""

WEAK_ANOMALOUS = ScoreBand(0.55, 0.75)
"""Inside the guard band, leaning anomalous. PRD S7.5a's 55th-75th percentile
band, expressed directly in calibrated confidence."""

WEAK_NORMAL = ScoreBand(0.25, 0.45)
"""Inside the guard band, leaning normal."""

UNINFORMATIVE = ScoreBand(0.40, 0.60)
"""Straddles 0.5: contributes almost nothing to the fused log-odds, which is
exactly what 'uninformative' should mean under the reference rule."""


LEVEL_MIX: dict[AmbiguityLevel, float] = {
    AmbiguityLevel.CLEAR_ANOMALOUS: 0.20,
    AmbiguityLevel.CLEAR_NORMAL: 0.20,
    AmbiguityLevel.BORDERLINE: 0.30,
    AmbiguityLevel.DECEPTIVE: 0.30,
}
"""Share of the incident set at each level (PRD S7.5a)."""

UNRESOLVABLE_SHARE = 0.07
"""Fraction of ALL incidents where EVERY source contradicts ground truth, so no
subset of evidence can reach the right answer.

**Allocated as a count, never sampled as a probability.** An earlier version
drew this per-incident with `rng.random() < share`, and the realised rate then
swung between 0.0% and 10.0% depending on the seed -- one seed produced a test
split with NO unresolvable incidents at all, which would have silently left
escalation precision undefined for that run. Stratified allocation makes the
count exact for every seed.

This is a deliberate construction and a tuning target, not an accident. The
first version of this generator produced a no-oracle rate of exactly **0.0%**,
because every ambiguity construction guaranteed at least one source agreeing
with the truth -- which would have left escalation precision and recall, the
project's most novel metric (PRD S12.1), with nothing at all to measure.

Set so the overall no-oracle rate lands in the 5-10% band: 8% of the 30%
deceptive slice is ~2.4%, plus the deceptive cases that fail on cancellation
alone. Asserted in tests so a future generator change cannot silently drift it
back toward zero.

These incidents are physically meaningful, not contrived: a genuine early-stage
fault that no installed sensor can yet detect is exactly the case where an
honest system must say "I cannot determine this" rather than guess.
"""

EXPECTED_PATH: dict[AmbiguityLevel, Path] = {
    AmbiguityLevel.CLEAR_ANOMALOUS: Path.FAST,
    AmbiguityLevel.CLEAR_NORMAL: Path.FAST,
    AmbiguityLevel.BORDERLINE: Path.PARALLEL,
    AmbiguityLevel.DECEPTIVE: Path.SEQUENTIAL,
}
"""DESCRIPTIVE ONLY. Never scored against (PRD S7.5b) -- it is the circular
metric that v1.0 used. Kept so results can be stratified by intended difficulty.
"""


def _sample_scores(
    level: AmbiguityLevel,
    is_anomalous: bool,
    rng: random.Random,
    *,
    unresolvable: bool = False,
) -> dict[Source, float]:
    """Sample one confidence per modality according to the ambiguity level.

    Each branch is a construction, not a filter: we decide what pattern of
    evidence this incident should present, then sample it.
    """
    audio, vision, telemetry = QUERYABLE

    if level is AmbiguityLevel.CLEAR_ANOMALOUS:
        # All three agree and all three are decisive.
        return {s: STRONG_ANOMALOUS.sample(rng) for s in QUERYABLE}

    if level is AmbiguityLevel.CLEAR_NORMAL:
        return {s: STRONG_NORMAL.sample(rng) for s in QUERYABLE}

    if level is AmbiguityLevel.BORDERLINE:
        # Anomalous in exactly one modality, normal in the others. Which
        # modality carries the signal is randomised so the orchestrator cannot
        # learn "always check audio first" and score well by accident.
        informative = rng.choice(QUERYABLE)
        scores: dict[Source, float] = {}
        for source in QUERYABLE:
            if source == informative:
                band = STRONG_ANOMALOUS if is_anomalous else STRONG_NORMAL
            else:
                band = UNINFORMATIVE
            scores[source] = band.sample(rng)
        return scores

    # DECEPTIVE (PRD S7.5a). Two sub-cases.
    #
    # THIS is the construction that closes B8: the conflict is defined in score
    # space, where it is measurable, not in physics, where it does not exist.

    if unresolvable:
        # UNRESOLVABLE: every source contradicts the ground truth, so no subset
        # can reach the right answer and oracle_exists is False. The correct
        # behaviour is to escalate, and these rows are the ground truth for
        # escalation precision (PRD S12.1). Allocated by count upstream, never
        # rolled here.
        wrong_band = WEAK_NORMAL if is_anomalous else WEAK_ANOMALOUS
        return {s: wrong_band.sample(rng) for s in QUERYABLE}

    # Ordinary deceptive: exactly two sources weakly anomalous and disagreeing
    # in sign with each other, third uninformative. One is a "hit" (agrees with
    # ground truth) and one a "miss" (contradicts it), so no SINGLE source
    # reliably resolves the incident and the pair nearly cancels under log-odds.
    conflicting = rng.sample(QUERYABLE, 2)
    third = next(s for s in QUERYABLE if s not in conflicting)

    hit_band = WEAK_ANOMALOUS if is_anomalous else WEAK_NORMAL
    miss_band = WEAK_NORMAL if is_anomalous else WEAK_ANOMALOUS

    return {
        conflicting[0]: hit_band.sample(rng),
        conflicting[1]: miss_band.sample(rng),
        third: UNINFORMATIVE.sample(rng),
    }


# --------------------------------------------------------------------------
# Payload paths
# --------------------------------------------------------------------------


def _payload_paths(machine: Machine, source_is_anomalous: dict[Source, bool]) -> dict[str, str]:
    """Build dataset-relative paths whose CLASS matches the sampled score sign.

    The files do not exist yet -- the datasets are still downloading -- and these
    are honest placeholders in the sense that they name the file that WILL be
    loaded, in the real dataset's real layout. They are not fabricated data: no
    detector reads them while `detector.impl == "mock"`, and the real detector
    will fail loudly on a missing path rather than inventing a score.
    """
    audio_cls = "abnormal" if source_is_anomalous[Source.AUDIO] else "normal"
    if source_is_anomalous[Source.VISION]:
        image = f"datasets/MVTecAD/{machine.mvtec_category}/test/bent/000.png"
    else:
        image = f"datasets/MVTecAD/{machine.mvtec_category}/test/good/000.png"
    return {
        "audio_clip_path": f"data/mimii/fan/{machine.mimii_id}/{audio_cls}/00000000.wav",
        "image_path": image,
    }


def _telemetry_row(machine: Machine, is_anomalous: bool, rng: random.Random) -> dict[str, float]:
    """AI4I-shaped feature row. Real column names, plausible ranges.

    Anomalous rows shift torque and tool wear upward, which is the direction the
    AI4I failure modes actually take (tool wear failure, overstrain). Replaced by
    real sampled rows once the dataset is in place.
    """
    base_torque = 40.0
    base_wear = 100.0
    shift = rng.uniform(8.0, 20.0) if is_anomalous else rng.uniform(-4.0, 4.0)
    return {
        "air_temperature_k": round(rng.uniform(295.0, 305.0), 2),
        "process_temperature_k": round(rng.uniform(305.0, 314.0), 2),
        "rotational_speed_rpm": round(rng.uniform(1200.0, 2800.0), 1),
        "torque_nm": round(base_torque + shift, 2),
        "tool_wear_min": round(base_wear + max(0.0, shift * 4.0), 1),
        "product_type_encoded": float("LMH".index(machine.ai4i_product_type)),
    }


# --------------------------------------------------------------------------
# The generator
# --------------------------------------------------------------------------

INCIDENT_SPACING_HOURS = 6
"""Hours between consecutive incidents. A LOAD-BEARING parameter, not cosmetic.

Measured consequence of getting it wrong (PRD v1.6). At the original 1 hour, 150
incidents spanned 6 days across 3 machines, so every machine always had a recent
prior fault and every memory rule keyed on recency became a CONSTANT rather than a
condition:

    rule "confirmed fault in last 7 days"   fired on 86.7% of incidents
    rule ">=3 false alarms in 30 days"      fired on 28.7%
    Tier 3 gate "prior fault within 7 days" filtered 20.0% -> 18.7%, i.e. barely

The 7-day window was wider than the entire dataset's 6-day span. A3 (memory
disabled) would therefore have measured almost nothing, and A3 is the ablation
that defends the memory agent's existence.

At 6 hours the same 150 incidents span 37 days -- plausible for a small facility --
and the rules discriminate: 26.0% and 2.0% respectively. Changing this value
changes every memory-dependent result, so it travels with HARNESS_VERSION.

This is the THIRD occurrence of one pattern: a threshold that could not
discriminate because the data had no range to discriminate over. The others were
the inert budget table and the unfalsifiable placeholder latencies. Recorded in
the PRD as a recurring methodological lesson rather than three anecdotes.
"""

SPLIT_SIZES: dict[Split, int] = {Split.DEV: 50, Split.TEST: 150, Split.DEMO: 8}
"""PRD S7.7. Dev for prompt iteration, test frozen for reported results, demo
hand-sized for the five scenarios in S3.2."""


class SyntheticEventSource:
    """Generates labelled, oracle-annotated incidents for the simulated facility.

    Deterministic given a seed: the same seed and split always yield byte-identical
    records, which is what lets a fixture be regenerated and diffed rather than
    trusted.
    """

    def __init__(
        self,
        *,
        seed: int = 0,
        machines: tuple[Machine, ...] = FACILITY,
        split_sizes: dict[Split, int] | None = None,
        start_time: datetime | None = None,
    ) -> None:
        self._seed = seed
        self._machines = machines
        self._split_sizes = split_sizes or SPLIT_SIZES
        self._start = start_time or datetime(2026, 9, 1, tzinfo=timezone.utc)

    @property
    def harness_version(self) -> str:
        return HARNESS_VERSION

    def count(self, split: Split) -> int:
        return self._split_sizes[split]

    def events(self, split: Split) -> Iterator[IncidentRecord]:
        """Yield one split's incidents.

        The RNG is seeded per split so that adding incidents to `dev` cannot
        change a single record in `test`. Without that, regenerating the dev set
        would silently invalidate every frozen test result.
        """
        rng = random.Random(f"{self._seed}:{split.value}")
        n = self._split_sizes[split]
        schedule = self._level_schedule(n, rng)

        for index, (level, unresolvable) in enumerate(schedule):
            yield self._build_one(
                index=index,
                level=level,
                unresolvable=unresolvable,
                split=split,
                rng=rng,
            )

    def _level_schedule(
        self, n: int, rng: random.Random
    ) -> list[tuple[AmbiguityLevel, bool]]:
        """Deterministic stratified allocation of levels AND unresolvability.

        Stratified rather than independently sampled so that a 50-incident dev
        split contains exactly the intended proportion of each level. Independent
        sampling at n=50 can easily yield 4 deceptive incidents instead of 15,
        which would make per-level regret numbers meaningless.

        The same argument applies with more force to the unresolvable count: a
        probability draw gave realised rates from 0.0% to 10.0% across seeds, and
        a split with zero unresolvable incidents leaves escalation precision
        undefined. Allocating an exact count removes that failure entirely.
        """
        levels: list[AmbiguityLevel] = []
        for level, share in LEVEL_MIX.items():
            levels.extend([level] * round(n * share))

        # Rounding can leave the list a little short or long.
        while len(levels) < n:
            levels.append(AmbiguityLevel.BORDERLINE)
        del levels[n:]

        # Unresolvable incidents are drawn only from the deceptive slice: an
        # incident every sensor gets wrong is by definition deceptive, and
        # marking a "clear" incident unresolvable would contradict its own label.
        n_unresolvable = round(n * UNRESOLVABLE_SHARE)
        deceptive_positions = [
            i for i, lv in enumerate(levels) if lv is AmbiguityLevel.DECEPTIVE
        ]
        if n_unresolvable > len(deceptive_positions):
            raise ValueError(
                f"UNRESOLVABLE_SHARE={UNRESOLVABLE_SHARE} needs {n_unresolvable} "
                f"incidents but only {len(deceptive_positions)} are deceptive. "
                "Raise the deceptive share in LEVEL_MIX or lower the target."
            )
        chosen = set(rng.sample(deceptive_positions, n_unresolvable))

        schedule = [(lv, i in chosen) for i, lv in enumerate(levels)]
        rng.shuffle(schedule)
        return schedule

    def _build_one(
        self,
        *,
        index: int,
        level: AmbiguityLevel,
        unresolvable: bool,
        split: Split,
        rng: random.Random,
    ) -> IncidentRecord:
        machine = self._machines[index % len(self._machines)]

        # Ground truth is implied by the level for the two clear cases, and drawn
        # for the ambiguous ones so that a borderline incident is as likely to be
        # a real fault as a false alarm. Otherwise "ambiguous" would correlate
        # with "anomalous" and the system could exploit that.
        if level is AmbiguityLevel.CLEAR_ANOMALOUS:
            is_anomalous = True
        elif level is AmbiguityLevel.CLEAR_NORMAL:
            is_anomalous = False
        else:
            is_anomalous = rng.random() < 0.5

        confidences = _sample_scores(
            level, is_anomalous, rng, unresolvable=unresolvable
        )

        oracle = compute_oracle(confidences, is_anomalous)

        source_is_anomalous = {s: c > 0.5 for s, c in confidences.items()}
        paths = _payload_paths(machine, source_is_anomalous)

        return IncidentRecord(
            incident_id=f"{split.value}_{index:04d}",
            machine_id=machine.machine_id,
            timestamp=self._start + timedelta(hours=INCIDENT_SPACING_HOURS * index),
            audio_clip_path=paths["audio_clip_path"],
            image_path=paths["image_path"],
            telemetry_row=_telemetry_row(machine, is_anomalous, rng),
            is_anomalous=is_anomalous,
            ambiguity_level=level,
            is_unresolvable=unresolvable,
            expected_path=EXPECTED_PATH[level],
            cached_scores={
                source: CachedScore(
                    # score_raw is a stand-in until real detectors exist: an
                    # unbounded value that maps monotonically to confidence, so
                    # anything that sorts by raw score behaves correctly.
                    score_raw=round((conf - 0.5) * 20.0, 4),
                    confidence=round(conf, 4),
                )
                for source, conf in confidences.items()
            },
            oracle_exists=oracle.exists,
            oracle_sources=list(oracle.sources),
            oracle_cost_ms=oracle.cost_ms,
            reference_rule_version=REFERENCE_RULE_VERSION,
            split=split,
            seed=self._seed,
        )


def no_oracle_rate(source: SyntheticEventSource, split: Split) -> float:
    """Fraction of incidents where NO subset of sources yields the right answer.

    This is a TUNING TARGET, not an observation to discover after the fact
    (PRD S7.5b). Those incidents are where escalation precision and recall get
    their teeth: the correct behaviour is "I cannot determine this, escalate",
    and a system that answers confidently is wrong even when it guesses right.

    Target 5-10%. Too near zero and our most novel metric has nothing to
    measure; too large and the ambiguity construction or the calibration is
    wrong. Asserted in the tests so a generator change cannot silently drift it.
    """
    records = list(source.events(split))
    if not records:
        return 0.0
    return sum(1 for r in records if not r.oracle_exists) / len(records)
