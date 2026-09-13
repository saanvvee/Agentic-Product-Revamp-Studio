"""Validation tests for the two frozen contracts (PRD S5.4, S7.5c).

These tests exist to make the contracts enforceable rather than aspirational.
Each one corresponds to a way the schema could silently rot and take a results
table with it.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from schemas.evidence import SCHEMA_VERSION, EvidenceReport, Source, Verdict
from schemas.incident import (
    AmbiguityLevel,
    CachedScore,
    IncidentRecord,
    Path,
    Split,
)

NOW = datetime.now(timezone.utc)


def _report(**overrides) -> EvidenceReport:
    base = dict(
        source=Source.AUDIO,
        machine_id="zone_a_fan_02",
        verdict=Verdict.ANOMALOUS,
        confidence=0.91,
        score_raw=14.2,
        evidence_summary="Broadband energy rise at 3-5 kHz.",
        cost_ms=140,
        cost_tokens=0,
        timestamp=NOW,
    )
    base.update(overrides)
    return EvidenceReport(**base)


def _incident(**overrides) -> IncidentRecord:
    base = dict(
        incident_id="inc_0042",
        machine_id="zone_a_fan_02",
        timestamp=NOW,
        audio_clip_path="data/mimii/fan/id_02/abnormal/00000012.wav",
        image_path="data/mvtec/metal_nut/test/bent/003.png",
        telemetry_row={"torque_nm": 40.1, "tool_wear_min": 108.0},
        is_anomalous=True,
        ambiguity_level=AmbiguityLevel.BORDERLINE,
        expected_path=Path.PARALLEL,
        cached_scores={
            Source.AUDIO: CachedScore(score_raw=14.2, confidence=0.72),
            Source.VISION: CachedScore(score_raw=2.1, confidence=0.31),
        },
        oracle_exists=True,
        oracle_sources=[Source.AUDIO, Source.TELEMETRY],
        oracle_cost_ms=1_400,
        oracle_cost_tokens=900,
        split=Split.TEST,
        seed=0,
    )
    base.update(overrides)
    return IncidentRecord(**base)


# --------------------------------------------------------------------------
# EvidenceReport
# --------------------------------------------------------------------------


def test_valid_report_round_trips_through_json():
    """Serialisation must be lossless: these cross a process boundary via MCP."""
    original = _report()
    restored = EvidenceReport.model_validate_json(original.model_dump_json())
    assert restored == original


def test_confidence_must_be_calibrated_to_unit_interval():
    """The guard bands are defined on confidence, so an out-of-range value would
    silently break every routing decision (PRD S8.4)."""
    for bad in (-0.01, 1.01):
        with pytest.raises(ValidationError):
            _report(confidence=bad)


def test_score_raw_is_unbounded():
    """PaDiM returns unbounded distances. Constraining this would force callers
    to pre-normalise and lose the audit trail from raw to calibrated."""
    assert _report(score_raw=1e6).score_raw == 1e6
    assert _report(score_raw=-5.0).score_raw == -5.0


def test_naive_timestamps_are_rejected():
    """A naive datetime silently means 'some timezone' and corrupts incident
    ordering against persistent history."""
    with pytest.raises(ValidationError, match="timezone-aware"):
        _report(timestamp=datetime(2026, 9, 13, 12, 0, 0))


def test_timestamps_are_normalised_to_utc():
    ist = timezone(timedelta(hours=5, minutes=30))
    report = _report(timestamp=datetime(2026, 9, 13, 17, 30, tzinfo=ist))
    assert report.timestamp.utcoffset() == timedelta(0)
    assert report.timestamp.hour == 12


def test_unknown_fields_are_rejected():
    """extra='forbid' is what makes this contract frozen in practice: a typo'd
    or invented field fails loudly instead of being silently dropped."""
    with pytest.raises(ValidationError):
        _report(confidenc=0.9)  # typo


def test_report_is_immutable():
    """Evidence is a record of what a source said. Mutating it after the fact
    would make the decision log unfaithful."""
    with pytest.raises(ValidationError):
        _report().confidence = 0.1


def test_inconclusive_is_not_decisive():
    assert _report(verdict=Verdict.ANOMALOUS).is_decisive
    assert _report(verdict=Verdict.NORMAL).is_decisive
    assert not _report(verdict=Verdict.INCONCLUSIVE).is_decisive


def test_costs_cannot_be_negative():
    with pytest.raises(ValidationError):
        _report(cost_ms=-1)
    with pytest.raises(ValidationError):
        _report(cost_tokens=-1)


def test_schema_version_is_stamped():
    """Every report carries its version so a mixed-version results set is
    detectable rather than quietly incoherent."""
    assert _report().schema_version == SCHEMA_VERSION


# --------------------------------------------------------------------------
# IncidentRecord and the oracle invariants
# --------------------------------------------------------------------------


def test_valid_incident_round_trips_through_json():
    original = _incident()
    restored = IncidentRecord.model_validate_json(original.model_dump_json())
    assert restored == original


def test_oracle_exists_requires_sources():
    """An inconsistent oracle produces regret numbers that look plausible and
    are wrong -- the worst kind of bug for a table nobody re-derives by hand."""
    with pytest.raises(ValidationError, match="oracle_sources is empty"):
        _incident(oracle_exists=True, oracle_sources=[])


def test_absent_oracle_must_have_no_sources_and_no_cost():
    with pytest.raises(ValidationError, match="non-empty"):
        _incident(oracle_exists=False, oracle_sources=[Source.AUDIO])

    with pytest.raises(ValidationError, match="oracle cost"):
        _incident(
            oracle_exists=False,
            oracle_sources=[],
            oracle_cost_ms=100,
            oracle_cost_tokens=0,
        )


def test_absent_oracle_is_a_legitimate_record():
    """oracle_exists=False means no subset of sources yields the right answer.
    These incidents SHOULD escalate and are the ground truth for escalation
    precision (PRD S12.1), so the schema must represent them cleanly."""
    record = _incident(
        oracle_exists=False,
        oracle_sources=[],
        oracle_cost_ms=0,
        oracle_cost_tokens=0,
    )
    assert not record.oracle_exists


def test_oracle_sources_must_not_repeat():
    """A duplicated source would double-count its cost and understate regret."""
    with pytest.raises(ValidationError, match="duplicates"):
        _incident(oracle_sources=[Source.AUDIO, Source.AUDIO])


def test_expected_path_is_descriptive_only():
    """Guard against regression to the v1.0 circular metric: expected_path is
    kept for stratification, and nothing may score against it (PRD S7.5b)."""
    record = _incident(expected_path=Path.FAST, ambiguity_level=AmbiguityLevel.DECEPTIVE)
    assert record.expected_path is Path.FAST  # deliberately inconsistent, still valid


def test_incident_is_immutable():
    with pytest.raises(ValidationError):
        _incident().is_anomalous = False


def test_harness_version_is_stamped():
    """Regenerating the harness after results exist, without a version bump, is
    how a results table silently stops matching its data (PRD S7.5c)."""
    assert _incident().harness_version
