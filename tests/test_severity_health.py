"""Tests for severity-distribution degeneracy detection (PRD S12.1).

Triage became load-bearing on the headline result once the budget tiers were
calibrated to bind (PRD v1.5). A degenerate distribution makes the tier system
decorative in a way every mechanism test would still pass, so it is checked
explicitly rather than assumed.
"""

from __future__ import annotations

from core.config import Severity
from eval.severity_health import assess_severity_distribution

LOW, STD, CRIT = Severity.LOW, Severity.STANDARD, Severity.CRITICAL


def test_balanced_distribution_is_healthy():
    health = assess_severity_distribution([LOW] * 30 + [STD] * 60 + [CRIT] * 30)
    assert not health.degenerate
    assert health.total == 120
    assert health.shares[STD] == 0.5


def test_one_tier_dominating_is_flagged():
    """THE failure this module exists for: a triage agent labelling almost
    everything `standard` would leave every budget mechanism working and never
    exercised -- decorative in a subtler way than the inert table was."""
    health = assess_severity_distribution([STD] * 95 + [LOW] * 3 + [CRIT] * 2)
    assert health.degenerate
    assert any("decorative" in f for f in health.findings)


def test_a_missing_tier_is_flagged():
    """A tier with no incidents has an untested budget, so any tier-specific rate
    derived from it is noise."""
    health = assess_severity_distribution([STD] * 50 + [CRIT] * 50)
    assert health.degenerate
    assert any("low" in f and "untested" in f for f in health.findings)


def test_an_underrepresented_tier_is_flagged():
    health = assess_severity_distribution([STD] * 60 + [CRIT] * 35 + [LOW] * 5)
    assert health.degenerate
    assert any("low is 5.0%" in f for f in health.findings)


def test_empty_run_is_degenerate():
    health = assess_severity_distribution([])
    assert health.degenerate
    assert health.total == 0


def test_log_fields_carry_the_distribution():
    """A results table without its severity distribution cannot be interpreted:
    the same orchestrator yields very different aggregate costs depending on how
    triage classified the set (PRD R23 discipline)."""
    health = assess_severity_distribution([LOW] * 30 + [STD] * 60 + [CRIT] * 30)
    fields = health.as_log_fields()
    assert fields["severity_counts"] == {"low": 30, "standard": 60, "critical": 30}
    assert fields["severity_degenerate"] is False


def test_report_is_human_readable():
    health = assess_severity_distribution([STD] * 100)
    text = health.report()
    assert "DEGENERATE" in text
    assert "standard" in text
