"""Config is the mechanism that makes every seam swappable, so it gets tested.

PRD S12.2's ablations ARE configurations (A3 = memory disabled, A5 = all
Gemini). If config silently accepts a bad value, an ablation silently becomes a
different experiment than the one reported.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from core.config import GuardBands, ReflectionSettings, Settings, Severity


def test_defaults_load():
    s = Settings()
    assert s.llm.provider == "ollama"
    assert s.llm.ollama_model == "qwen3:4b"
    assert s.llm.cached is True


def test_every_severity_has_a_budget():
    """A missing severity would make triage's output unmappable at runtime,
    deep inside a workflow, rather than at startup."""
    table = Settings().budget.table
    assert set(table) == set(Severity)
    assert table[Severity.CRITICAL].budget_ms > table[Severity.LOW].budget_ms


def test_reflection_cap_cannot_exceed_two():
    """PRD invariant 5 enforced in the TYPE, so a config typo cannot raise it.
    This is the difference between a cap in code and a cap in a prompt."""
    with pytest.raises(ValidationError):
        ReflectionSettings(max_reflection_loops=5)


def test_evidence_step_cap_cannot_exceed_four():
    """Only four queryable sources exist and S11.3 forbids re-querying one."""
    with pytest.raises(ValidationError):
        ReflectionSettings(max_evidence_steps=9)


def test_guard_bands_must_be_ordered():
    """Inverted bands would make every incident take the fast path while looking
    like a working policy."""
    with pytest.raises(ValidationError, match="decisive_low must be"):
        GuardBands(decisive_low=0.9, decisive_high=0.2)


def test_unknown_config_keys_are_rejected():
    """A typo'd key that is silently ignored means the ablation you ran is not
    the ablation you documented."""
    with pytest.raises(ValidationError):
        GuardBands(decisive_hi=0.85)


def test_env_vars_override_defaults(monkeypatch):
    """The one-line local-to-API switch, as an assertion rather than a claim."""
    monkeypatch.setenv("IRA_LLM__PROVIDER", "gemini")
    monkeypatch.setenv("IRA_MEMORY__ENABLED", "false")
    s = Settings()
    assert s.llm.provider == "gemini"
    assert s.memory.enabled is False


def test_invalid_provider_is_rejected():
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setenv("IRA_LLM__PROVIDER", "openai")
    with pytest.raises(ValidationError):
        Settings()
    monkeypatch.undo()
