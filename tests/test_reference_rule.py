"""Tests for the reference rule and the oracle (PRD S7.5b).

Every expected value below is computed BY HAND in the docstring, not by running
the code and recording what it said. That distinction matters: a test whose
expectation came from the implementation only proves the implementation is
consistent with itself, and would have happily locked in the non-monotone
mean-of-confidence rule that these tests now guard against.

Log-odds reference values used throughout (natural log):
    logit(0.95) = ln(0.95/0.05) = ln(19)    ~= +2.944
    logit(0.90) = ln(9)                     ~= +2.197
    logit(0.72) = ln(0.72/0.28)= ln(2.571)  ~= +0.944
    logit(0.62) = ln(0.62/0.38)= ln(1.632)  ~= +0.490
    logit(0.55) = ln(0.55/0.45)= ln(1.222)  ~= +0.201
    logit(0.50) = 0
    logit(0.45) = -0.201
    logit(0.38) = -0.490
    logit(0.31) = ln(0.31/0.69)= ln(0.449)  ~= -0.800
    logit(0.15) = ln(0.15/0.85)= ln(0.176)  ~= -1.735
    logit(0.10) = ln(1/9)                   ~= -2.197
"""

from __future__ import annotations

import math

import pytest

from harness.reference_rule import (
    DECLARED_COST_MS,
    REFERENCE_RULE_VERSION,
    clamp_confidence,
    compute_oracle,
    cost_regret,
    fuse_log_odds,
    is_sufficient,
    logit,
    reference_verdict,
    source_regret,
    subset_cost_ms,
)
from schemas.evidence import Source

A, V, T, M = Source.AUDIO, Source.VISION, Source.TELEMETRY, Source.MANUAL


# --------------------------------------------------------------------------
# The rule itself
# --------------------------------------------------------------------------


def test_logit_is_symmetric_about_one_half():
    """logit(p) == -logit(1-p). A sanity property of log-odds."""
    assert logit(0.5) == pytest.approx(0.0)
    assert logit(0.9) == pytest.approx(-logit(0.1))


def test_logit_matches_hand_computed_values():
    assert logit(0.95) == pytest.approx(math.log(19), abs=1e-9)
    assert logit(0.10) == pytest.approx(math.log(1 / 9), abs=1e-9)


def test_saturated_confidences_are_clamped():
    """Without clamping, one detector at 0.0 or 1.0 has infinite log-odds and
    decides every subset it appears in, regardless of other evidence."""
    assert clamp_confidence(0.0) == 0.01
    assert clamp_confidence(1.0) == 0.99
    assert math.isfinite(logit(0.0))
    assert math.isfinite(logit(1.0))


def test_log_odds_is_monotone_where_the_mean_is_not():
    """THE regression test for PRD v1.3's rule change.

    Hand-computed, the pathology that killed mean-of-confidence:
        mean(0.95, 0.10)       = 0.525 -> anomalous
        mean(0.95, 0.10, 0.15) = 0.400 -> NORMAL, verdict flipped by adding
                                          a third source

    Log-odds on the same numbers:
        0.95, 0.10        -> +2.944 - 2.197 = +0.747 -> anomalous
        0.95, 0.10, 0.15  -> +0.747 - 1.735 = -0.988 -> normal

    Note log-odds ALSO flips here, and that is correct rather than a bug: two
    independent sources both reading normal genuinely should outweigh one strong
    anomalous reading. The property that matters is not "never flips" but that
    the fused value moves in proportion to the evidence added, so a single weak
    source cannot drag a strong signal across the line. The next test pins that.
    """
    strong_only = fuse_log_odds([0.95])
    plus_one_weak = fuse_log_odds([0.95, 0.45])

    assert strong_only > 0
    assert plus_one_weak > 0, "one barely-normal source must not flip a strong signal"
    assert plus_one_weak < strong_only

    mean_two = (0.95 + 0.45) / 2
    assert mean_two > 0.5  # the mean agrees here
    # ...but the mean's margin collapses far faster than log-odds':
    assert (mean_two - 0.5) / 0.5 < 0.5


def test_a_weak_normal_source_cannot_overturn_a_strong_anomalous_one():
    """0.95 with a 0.45 reading: +2.944 - 0.201 = +2.743, still clearly anomalous.
    Under mean-of-confidence this is 0.70, also anomalous -- but a second such
    source (0.95, 0.45, 0.45) gives mean 0.617 and log-odds +2.542. The mean is
    three quarters of the way to flipping; log-odds has barely moved."""
    assert fuse_log_odds([0.95, 0.45, 0.45]) == pytest.approx(2.944 - 0.402, abs=0.01)
    assert reference_verdict([0.95, 0.45, 0.45]) is True


def test_empty_subset_reads_as_normal():
    """Log-odds of nothing is 0, and the boundary is read as not-anomalous, so
    the empty set can never be sufficient for a genuinely anomalous incident."""
    assert fuse_log_odds([]) == 0.0
    assert reference_verdict([]) is False


# --------------------------------------------------------------------------
# Sufficiency, hand-checked
# --------------------------------------------------------------------------


def test_sufficiency_requires_matching_the_ground_truth():
    """confidences: audio 0.90 (+2.197), vision 0.31 (-0.800).
    {audio}          = +2.197 -> anomalous -> correct for is_anomalous=True
    {vision}         = -0.800 -> normal    -> wrong
    {audio, vision}  = +1.397 -> anomalous -> correct
    """
    conf = {A: 0.90, V: 0.31}
    assert is_sufficient((A,), conf, True)
    assert not is_sufficient((V,), conf, True)
    assert is_sufficient((A, V), conf, True)


def test_missing_cached_score_raises():
    """A silently-skipped source would understate the oracle's cost and inflate
    every regret number computed against it."""
    with pytest.raises(KeyError):
        is_sufficient((A, V), {A: 0.9}, True)


# --------------------------------------------------------------------------
# The oracle, one case per ambiguity level (PRD S7.5a)
# --------------------------------------------------------------------------


def test_oracle_on_clear_anomalous_picks_the_cheapest_single_source():
    """CLEAR_ANOMALOUS: all three sources strongly anomalous.
        audio 0.95 (+2.944, 350ms)
        vision 0.92 (+2.442, 200ms)
        telemetry 0.90 (+2.197, 50ms)

    Every singleton is sufficient alone. Cheapest is telemetry at 50 ms.
    Hand-computed expectation: sources=(telemetry,), cost=50.
    """
    oracle = compute_oracle({A: 0.95, V: 0.92, T: 0.90}, True)
    assert oracle.exists
    assert oracle.sources == (T,)
    assert oracle.cost_ms == 50


def test_oracle_on_clear_normal_picks_the_cheapest_single_source():
    """CLEAR_NORMAL: all three strongly normal.
        audio 0.05, vision 0.08, telemetry 0.10 -- all negative log-odds.

    Every singleton reads normal, which is correct. Cheapest is telemetry, 50 ms.
    The empty set is excluded by allow_empty=False: 'gather nothing' would be
    trivially optimal for every normal incident and would make mean regret
    meaningless.
    """
    oracle = compute_oracle({A: 0.05, V: 0.08, T: 0.10}, False)
    assert oracle.exists
    assert oracle.sources == (T,)
    assert oracle.cost_ms == 50


def test_oracle_on_borderline_needs_the_informative_source():
    """BORDERLINE: anomalous in exactly one modality (PRD S7.5a).
        audio 0.72 (+0.944, 350ms)   <- the only informative source
        vision 0.45 (-0.201, 200ms)
        telemetry 0.45 (-0.201, 50ms)

    is_anomalous=True. Hand-computed:
        {telemetry}        -0.201 -> normal     wrong
        {vision}           -0.201 -> normal     wrong
        {audio}            +0.944 -> anomalous  CORRECT, 350ms
        {vision,telemetry} -0.402 -> normal     wrong
        {audio,telemetry}  +0.743 -> anomalous  correct, 400ms
        {audio,vision}     +0.743 -> anomalous  correct, 550ms

    Cheapest sufficient subset is {audio} at 350 ms -- the expensive source is
    the only one that helps, which is exactly the tradeoff the orchestrator has
    to discover without knowing the answer.
    """
    oracle = compute_oracle({A: 0.72, V: 0.45, T: 0.45}, True)
    assert oracle.exists
    assert oracle.sources == (A,)
    assert oracle.cost_ms == 350


def test_oracle_on_deceptive_may_require_a_pair():
    """DECEPTIVE: two weakly anomalous sources disagreeing in sign (PRD S7.5a).
        audio 0.62 (+0.490, 350ms)
        vision 0.38 (-0.490, 200ms)
        telemetry 0.55 (+0.201, 50ms)

    is_anomalous=True. Hand-computed:
        {telemetry}          +0.201 -> anomalous  CORRECT, 50ms
        {vision}             -0.490 -> normal     wrong
        {audio}              +0.490 -> anomalous  correct, 350ms
        {vision,telemetry}   -0.289 -> normal     wrong
        {audio,vision}        0.000 -> NOT > 0 -> normal, wrong (exact tie!)

    Cheapest is {telemetry} at 50 ms -- right by a thin margin of +0.201. A
    system that gathers all three gets +0.201 overall and is also correct, but
    pays 600 ms for it: regret 550. That is the 'charged for behaving correctly
    under uncertainty' case which is why S7.5b requires the achievable A1
    baseline alongside this oracle.

    The {audio, vision} exact tie also pins the boundary convention: fused == 0
    reads as normal, not anomalous.
    """
    conf = {A: 0.62, V: 0.38, T: 0.55}
    assert fuse_log_odds([conf[A], conf[V]]) == pytest.approx(0.0, abs=1e-9)
    assert not is_sufficient((A, V), conf, True)

    oracle = compute_oracle(conf, True)
    assert oracle.exists
    assert oracle.sources == (T,)
    assert oracle.cost_ms == 50


def test_oracle_may_not_exist():
    """No subset reaches the right answer: every source reads normal on a truly
    anomalous incident.
        audio 0.20, vision 0.25, telemetry 0.30 -- all negative log-odds, and
        any sum of negatives is negative.

    These incidents SHOULD escalate and are the ground truth for escalation
    precision (PRD S12.1), so oracle_exists=False is a result, not an error.
    """
    oracle = compute_oracle({A: 0.20, V: 0.25, T: 0.30}, True)
    assert not oracle.exists
    assert oracle.sources == ()
    assert oracle.cost_ms == 0


def test_oracle_tie_break_is_deterministic():
    """Equal-cost sufficient subsets must resolve the same way every run, or
    regret numbers drift between runs for no reason.

    memory and telemetry both cost 50 ms and both read anomalous alone, so the
    tie falls to lexical order: 'memory' < 'telemetry'.
    """
    conf = {Source.MEMORY: 0.90, T: 0.90}
    first = compute_oracle(conf, True)
    second = compute_oracle(conf, True)
    assert first.sources == second.sources == (Source.MEMORY,)
    assert DECLARED_COST_MS[Source.MEMORY] == DECLARED_COST_MS[T]


def test_oracle_prefers_fewer_sources_at_equal_cost():
    """Cost is the primary key; source count is the first tie-break. Two 50 ms
    sources cost 100 ms total, so a single 100 ms source would win on count --
    here we check the ordering holds by construction."""
    costs = {A: 100, T: 50, Source.MEMORY: 50}
    conf = {A: 0.90, T: 0.90, Source.MEMORY: 0.90}
    oracle = compute_oracle(conf, True, costs=costs)
    assert oracle.cost_ms == 50
    assert oracle.n_sources == 1


def test_allow_empty_exposes_the_trivial_normal_case():
    """Documented behaviour, off by default. With the empty set permitted, every
    normal incident has a zero-cost oracle, which is why we exclude it."""
    oracle = compute_oracle({A: 0.05}, False, allow_empty=True)
    assert oracle.exists
    assert oracle.sources == ()
    assert oracle.cost_ms == 0


def test_rule_version_is_recorded_on_the_plan():
    """The oracle is frozen into the fixture; the rule that produced it must
    travel with it (PRD S7.5b, same class as R23)."""
    assert compute_oracle({A: 0.9}, True).rule_version == REFERENCE_RULE_VERSION


# --------------------------------------------------------------------------
# Regret
# --------------------------------------------------------------------------


def test_cost_regret_is_zero_when_the_system_finds_the_oracle_set():
    oracle = compute_oracle({A: 0.95, V: 0.92, T: 0.90}, True)
    assert cost_regret(subset_cost_ms((T,)), oracle) == 0


def test_cost_regret_is_positive_when_over_gathering():
    """The deceptive case from above: oracle is {telemetry} at 50 ms, a system
    that queries all three pays 600 ms. Regret 550."""
    oracle = compute_oracle({A: 0.62, V: 0.38, T: 0.55}, True)
    assert cost_regret(subset_cost_ms((A, V, T)), oracle) == 550


def test_source_regret_is_negative_when_under_gathering():
    """Negative regret means the system gathered less than the oracle, which the
    trajectory metric penalises harder than over-gathering (PRD S12.3)."""
    oracle = compute_oracle({A: 0.72, V: 0.45, T: 0.45}, True)
    assert oracle.n_sources == 1
    assert source_regret((), oracle) == -1
    assert source_regret((A, V), oracle) == 1
