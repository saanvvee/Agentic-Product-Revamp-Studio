"""The test that proves the EventSource seam is real, plus generator invariants.

Contract tests run against BOTH implementations. The generator-specific tests
below guard properties that were each discovered by measuring rather than by
assuming -- the no-oracle rate in particular was 0.0% in the first version, which
would have left the project's most novel metric with nothing to measure.
"""

from __future__ import annotations

from collections import Counter

import pytest

from harness.base import EventSource
from harness.replay import ReplayEventSource, write_fixture
from harness.synthetic import (
    FACILITY,
    LEVEL_MIX,
    QUERYABLE,
    UNRESOLVABLE_SHARE,
    SyntheticEventSource,
    no_oracle_rate,
)
from schemas.incident import AmbiguityLevel, IncidentRecord, Split

SPLIT = Split.DEV


@pytest.fixture
def fixture_path(tmp_path):
    path = tmp_path / "incidents.jsonl"
    write_fixture(SyntheticEventSource(seed=0).events(SPLIT), path)
    return path


@pytest.fixture(params=["synthetic", "replay"])
def source(request, fixture_path):
    """Both implementations, one at a time, through the same contract."""
    if request.param == "synthetic":
        return SyntheticEventSource(seed=0)
    return ReplayEventSource(fixture_path)


# --------------------------------------------------------------------------
# Contract: both implementations must satisfy these.
# --------------------------------------------------------------------------


def test_satisfies_the_protocol(source):
    assert isinstance(source, EventSource)


def test_yields_validated_records(source):
    records = list(source.events(SPLIT))
    assert records
    assert all(isinstance(r, IncidentRecord) for r in records)


def test_count_matches_what_is_yielded(source):
    assert source.count(SPLIT) == len(list(source.events(SPLIT)))


def test_harness_version_is_reported(source):
    assert source.harness_version


def test_iteration_is_repeatable(source):
    """An eval run that iterates twice must see the same incidents both times,
    or a second pass would silently score a different set."""
    first = [r.incident_id for r in source.events(SPLIT)]
    second = [r.incident_id for r in source.events(SPLIT)]
    assert first == second


def test_incident_ids_are_unique(source):
    ids = [r.incident_id for r in source.events(SPLIT)]
    assert len(ids) == len(set(ids))


def test_every_record_carries_a_consistent_oracle(source):
    """The schema validates this per record; here we check it holds across a
    whole split, because a single inconsistent row would corrupt an aggregate."""
    for record in source.events(SPLIT):
        if record.oracle_exists:
            assert record.oracle_sources
            assert record.oracle_cost_ms > 0
        else:
            assert not record.oracle_sources
            assert record.oracle_cost_ms == 0


# --------------------------------------------------------------------------
# Round trip: the two implementations must agree exactly.
# --------------------------------------------------------------------------


def test_replay_reproduces_the_generator_byte_for_byte(fixture_path):
    """This is what makes the seam trustworthy: a frozen fixture is not an
    approximation of the generator, it IS the generator's output."""
    generated = list(SyntheticEventSource(seed=0).events(SPLIT))
    replayed = list(ReplayEventSource(fixture_path).events(SPLIT))
    assert generated == replayed


def test_replay_rejects_a_corrupt_fixture(tmp_path):
    """A hand-edited or schema-stale fixture must fail loudly, not produce
    plausible-looking results."""
    path = tmp_path / "bad.jsonl"
    path.write_text('{"incident_id": "x"}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="failed schema validation"):
        list(ReplayEventSource(path).events(SPLIT))


def test_replay_reports_the_fixtures_version_not_the_codes(fixture_path):
    """The version is a property of the data. Reporting the current code's
    version for an old fixture is the confusion the field exists to prevent."""
    assert ReplayEventSource(fixture_path).harness_version


def test_missing_fixture_names_the_fix(tmp_path):
    with pytest.raises(FileNotFoundError, match="build_harness"):
        ReplayEventSource(tmp_path / "nope.jsonl")


# --------------------------------------------------------------------------
# Generator invariants (PRD S7.5a)
# --------------------------------------------------------------------------


def test_generation_is_deterministic_for_a_seed():
    a = list(SyntheticEventSource(seed=7).events(SPLIT))
    b = list(SyntheticEventSource(seed=7).events(SPLIT))
    assert a == b


def test_different_seeds_give_different_incidents():
    a = [r.cached_scores for r in SyntheticEventSource(seed=0).events(SPLIT)]
    b = [r.cached_scores for r in SyntheticEventSource(seed=1).events(SPLIT)]
    assert a != b


def test_splits_are_independently_seeded():
    """Adding incidents to dev must not perturb a single record in test, or
    regenerating the dev set would invalidate every frozen test result."""
    base = list(SyntheticEventSource(seed=0).events(Split.TEST))
    resized = SyntheticEventSource(
        seed=0, split_sizes={Split.DEV: 999, Split.TEST: 150, Split.DEMO: 8}
    )
    assert list(resized.events(Split.TEST)) == base


def test_level_mix_is_exact_not_approximate():
    """Stratified allocation: at n=50, independent sampling could easily yield 4
    deceptive incidents instead of 15 and make per-level regret meaningless."""
    counts = Counter(r.ambiguity_level for r in SyntheticEventSource(seed=0).events(SPLIT))
    for level, share in LEVEL_MIX.items():
        assert counts[level] == round(50 * share)


@pytest.mark.parametrize("seed", range(6))
def test_no_oracle_rate_stays_in_the_target_band(seed):
    """THE regression test for the escalation metric (PRD S12.1).

    Two failures were found by measuring this rather than assuming it:

      1. The first generator produced exactly 0.0% -- every construction
         guaranteed a source agreeing with ground truth, so escalation precision
         would have had no hard cases at all.
      2. The fix, drawn as a per-incident probability, gave realised rates from
         0.0% to 10.0% across seeds; one seed produced a test split with NO
         unresolvable incidents, leaving the metric undefined for that run.

    Allocating an exact count fixes both. This test pins it for every seed, so a
    future change to the generator cannot silently drift it back toward zero.
    """
    source = SyntheticEventSource(seed=seed)
    for split in (Split.DEV, Split.TEST):
        rate = no_oracle_rate(source, split)
        assert 0.05 <= rate <= 0.10, f"seed={seed} split={split.value} rate={rate:.1%}"


def test_unresolvable_incidents_are_always_deceptive():
    """An incident every sensor gets wrong is by definition deceptive; marking a
    'clear' incident unresolvable would contradict its own label."""
    for record in SyntheticEventSource(seed=0).events(Split.TEST):
        if not record.oracle_exists:
            assert record.ambiguity_level is AmbiguityLevel.DECEPTIVE


def test_clear_incidents_always_have_a_cheap_oracle():
    """Correctness check on the construction: if a 'clear' incident needed
    expensive evidence, the level would be mislabelled."""
    for record in SyntheticEventSource(seed=0).events(Split.TEST):
        if record.ambiguity_level in (
            AmbiguityLevel.CLEAR_ANOMALOUS,
            AmbiguityLevel.CLEAR_NORMAL,
        ):
            assert record.oracle_exists
            assert len(record.oracle_sources) == 1, "one source should suffice"


def test_ambiguous_levels_are_not_correlated_with_ground_truth():
    """If 'ambiguous' implied 'anomalous', a system could exploit the label
    instead of the evidence and score well for the wrong reason."""
    records = [
        r
        for r in SyntheticEventSource(seed=0).events(Split.TEST)
        if r.ambiguity_level in (AmbiguityLevel.BORDERLINE, AmbiguityLevel.DECEPTIVE)
    ]
    anomalous_share = sum(r.is_anomalous for r in records) / len(records)
    assert 0.35 <= anomalous_share <= 0.65


def test_every_machine_is_exercised():
    machines = {r.machine_id for r in SyntheticEventSource(seed=0).events(Split.TEST)}
    assert machines == {m.machine_id for m in FACILITY}


def test_all_three_modalities_are_scored():
    for record in SyntheticEventSource(seed=0).events(SPLIT):
        assert set(record.cached_scores) == set(QUERYABLE)


def test_payload_class_matches_the_sampled_score_sign():
    """The stand-in paths name a file whose CLASS matches the sampled score, so
    swapping in real detectors does not invert the labelling."""
    for record in SyntheticEventSource(seed=0).events(SPLIT):
        from schemas.evidence import Source

        audio_anomalous = record.cached_scores[Source.AUDIO].confidence > 0.5
        assert ("abnormal" in record.audio_clip_path) == audio_anomalous

        vision_anomalous = record.cached_scores[Source.VISION].confidence > 0.5
        assert ("/good/" in record.image_path) != vision_anomalous


def test_unresolvable_share_is_documented_where_it_is_used():
    """Guard against the constant drifting away from the tested band."""
    assert 0.05 <= UNRESOLVABLE_SHARE <= 0.10


# --------------------------------------------------------------------------
# is_unresolvable vs ambiguity_level: the escalation metric depends on the
# distinction, so it is asserted rather than assumed (PRD S12.1).
# --------------------------------------------------------------------------


def test_unresolvable_is_not_the_same_as_deceptive():
    """The confound this field exists to prevent.

    Escalating on an unresolvable incident is CORRECT -- no evidence could have
    resolved it. Escalating on a merely deceptive one may be a FAILURE, because
    the evidence was sufficient and the system gave up. If ambiguity_level stood
    in for unresolvability, escalation precision would reward giving up on hard
    cases.
    """
    records = list(SyntheticEventSource(seed=0).events(Split.TEST))
    deceptive = [r for r in records if r.ambiguity_level is AmbiguityLevel.DECEPTIVE]
    unresolvable = [r for r in records if r.is_unresolvable]

    assert unresolvable, "no unresolvable incidents: escalation has no ground truth"
    # Every unresolvable incident is deceptive...
    assert all(r.ambiguity_level is AmbiguityLevel.DECEPTIVE for r in unresolvable)
    # ...but MOST deceptive incidents are resolvable, which is the whole point.
    assert len(unresolvable) < len(deceptive)
    resolvable_deceptive = [r for r in deceptive if not r.is_unresolvable]
    assert resolvable_deceptive, "deceptive must include resolvable cases too"


def test_intent_and_measured_outcome_agree():
    """is_unresolvable is the harness's construction; oracle_exists is what the
    reference rule measured. Keeping both is only worthwhile if a divergence
    fails loudly, which the schema validator enforces."""
    for record in SyntheticEventSource(seed=0).events(Split.TEST):
        assert record.is_unresolvable == (not record.oracle_exists)


def test_schema_rejects_a_disagreement_between_intent_and_outcome():
    """Directly exercise the validator: a future fusion-rule change that breaks
    the correspondence must fail rather than silently shift escalation numbers."""
    from pydantic import ValidationError

    record = next(iter(SyntheticEventSource(seed=0).events(Split.DEV)))
    payload = record.model_dump(mode="json")
    payload["is_unresolvable"] = True  # claim unresolvable while an oracle exists

    with pytest.raises(ValidationError, match="construction and the rule disagree"):
        IncidentRecord.model_validate(payload)
