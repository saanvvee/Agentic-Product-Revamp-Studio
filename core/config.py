"""Single source of truth for which implementation sits behind every seam.

The rule this file exists to enforce: NO module anywhere else in the tree
imports a concrete provider, detector, store, sink, or tracer. They take one by
injection, and this file decides which one. Switching the whole system from
local to API is one line here or one env var.

Why that matters beyond tidiness: PRD S12.2's ablations ARE configurations. A5
(all-Gemini) and A3 (memory disabled) must be expressible without touching code,
or every ablation risks being a slightly different program.

Env vars override the file, prefixed IRA_ and nested with __:
    IRA_LLM__PROVIDER=gemini
    IRA_DETECTOR__IMPL=mock
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parent.parent


class Severity(str, Enum):
    """Triage's output class. The LLM picks one of these; it never picks a budget."""

    CRITICAL = "critical"
    STANDARD = "standard"
    LOW = "low"


class BudgetAllocation(BaseModel):
    """Domain-cost budget for one severity class (PRD S5.5a, S5.5b).

    These are DOMAIN costs: modelled sensor acquisition plus detector inference.
    LLM wall-clock is system overhead and is never budgeted against these.
    """

    model_config = {"extra": "forbid", "frozen": True}

    budget_ms: int = Field(gt=0)
    budget_tokens: int = Field(gt=0)


class BudgetSettings(BaseModel):
    """The severity-to-budget table. Deterministic, auditable, diffable.

    Lives in config and never in a prompt: a prompt-supplied budget drifts per
    call, cannot be asserted in a test, and would silently differ across
    ablation runs, making A1-vs-A2 cost comparisons meaningless.
    """

    model_config = {"extra": "forbid"}

    table: dict[Severity, BudgetAllocation] = Field(
        default_factory=lambda: {
            Severity.CRITICAL: BudgetAllocation(budget_ms=8_000, budget_tokens=6_000),
            Severity.STANDARD: BudgetAllocation(budget_ms=4_000, budget_tokens=3_000),
            Severity.LOW: BudgetAllocation(budget_ms=1_500, budget_tokens=1_000),
        }
    )

    @model_validator(mode="after")
    def _all_severities_present(self) -> "BudgetSettings":
        missing = set(Severity) - set(self.table)
        if missing:
            raise ValueError(
                f"budget table missing severities: {sorted(s.value for s in missing)}"
            )
        return self


class GuardBands(BaseModel):
    """Confidence thresholds for path selection (PRD S5.5).

    Tunable and declared in the report. They live here, not in a prompt, so the
    orchestrator's policy is auditable and identical across ablation runs.
    """

    model_config = {"extra": "forbid", "frozen": True}

    decisive_high: float = Field(default=0.85, ge=0.0, le=1.0)
    """>= this is confidently anomalous -> fast path."""

    decisive_low: float = Field(default=0.15, ge=0.0, le=1.0)
    """<= this is confidently normal -> fast path."""

    @model_validator(mode="after")
    def _ordered(self) -> "GuardBands":
        if self.decisive_low >= self.decisive_high:
            raise ValueError("decisive_low must be < decisive_high")
        return self


class LLMSettings(BaseModel):
    model_config = {"extra": "forbid"}

    provider: Literal["ollama", "gemini", "stub"] = "ollama"
    """Which LLMProvider implementation to build. THE local-to-API switch."""

    cached: bool = True
    """Wrap the provider in the disk cache. PRD invariant 3: never make an
    uncached call. Disable only in a test that is explicitly testing the cache."""

    ollama_model: str = "qwen3:4b"
    """Exact tag, never ':latest' (R23). Gemma 3 cannot tool-call in Ollama."""

    ollama_host: str = "http://localhost:11434"

    ollama_no_think: bool = True
    """Suppress Qwen3 reasoning tokens. Mitigates R22 eval wall-clock."""

    gemini_model: str = "gemini-2.5-flash"
    """Pinned exactly (R23). The free-tier Flash lineup spans many versions."""

    temperature: float = Field(default=0.0, ge=0.0, le=2.0)

    seed: int = 0
    """Part of the cache key (PRD S7.8 / B11). Varying it is what makes the
    3-seed variance run on A2 real instead of returning run 1's bytes."""

    max_concurrency: int = Field(default=3, ge=1)
    """PRD invariant 4. Also passed to Workflow(max_concurrency=...)."""


class DetectorSettings(BaseModel):
    model_config = {"extra": "forbid"}

    impl: Literal["padim", "mock"] = "mock"
    """'mock' until trained weights exist; padim.py raises NotImplementedError
    rather than returning plausible garbage."""

    weights_dir: Path = REPO_ROOT / "artifacts" / "detectors"
    calibration_path: Path = REPO_ROOT / "artifacts" / "calibration.json"


class HarnessSettings(BaseModel):
    model_config = {"extra": "forbid"}

    impl: Literal["synthetic", "replay"] = "synthetic"
    fixture_path: Path = REPO_ROOT / "eval" / "evalsets" / "incidents.jsonl"

    n_machines: int = Field(default=3, ge=1)
    """PRD S7.5 v1.1: 3 machines across 2 zones."""

    seed: int = 0


class MemorySettings(BaseModel):
    model_config = {"extra": "forbid"}

    impl: Literal["sqlite", "in_memory"] = "sqlite"
    db_path: Path = REPO_ROOT / "artifacts" / "incidents.db"

    enabled: bool = True
    """False is ablation A3 (memory disabled). A config flag, not a code branch."""


class DispatchSettings(BaseModel):
    model_config = {"extra": "forbid"}

    impl: Literal["a2a", "local_stub"] = "local_stub"

    a2a_url: str = "http://localhost:8001"
    """One hostname spelling project-wide: the agent card's origin is enforced,
    so 'localhost' and '127.0.0.1' are NOT interchangeable."""


class TracingSettings(BaseModel):
    model_config = {"extra": "forbid"}

    impl: Literal["phoenix", "noop"] = "noop"
    endpoint: str = "http://localhost:6006/v1/traces"
    project_name: str = "incident-response"


class ReflectionSettings(BaseModel):
    model_config = {"extra": "forbid", "frozen": True}

    max_reflection_loops: int = Field(default=2, ge=0, le=2)
    """PRD invariant 5. Capped at 2 IN THE TYPE, so a config typo cannot raise
    it -- the cap is enforced in code, never in a prompt."""

    max_evidence_steps: int = Field(default=4, ge=1, le=4)
    """Distinct from the above: evidence sources queried in one sequential path."""


class Settings(BaseSettings):
    """Root config. One object, injected from the composition root."""

    model_config = SettingsConfigDict(
        env_prefix="IRA_",
        env_nested_delimiter="__",
        env_file=".env",
        extra="forbid",
    )

    llm: LLMSettings = Field(default_factory=LLMSettings)
    detector: DetectorSettings = Field(default_factory=DetectorSettings)
    harness: HarnessSettings = Field(default_factory=HarnessSettings)
    memory: MemorySettings = Field(default_factory=MemorySettings)
    dispatch: DispatchSettings = Field(default_factory=DispatchSettings)
    tracing: TracingSettings = Field(default_factory=TracingSettings)
    budget: BudgetSettings = Field(default_factory=BudgetSettings)
    guard_bands: GuardBands = Field(default_factory=GuardBands)
    reflection: ReflectionSettings = Field(default_factory=ReflectionSettings)

    cache_dir: Path = REPO_ROOT / "cache"

    google_api_key: str | None = None
    """From .env, never committed. None is a legitimate state: the Ollama path
    does not need it, and a missing key must fail loudly at Gemini construction
    rather than silently here."""

    run_environment: str = "local-cpu"
    """Stamped into results tables and decisions.jsonl (R23). Dev runs on local
    CPU, eval runs on Colab GPU; different quantisations give different outputs,
    and "the numbers changed and we do not know why" is a bad week in November.
    """
