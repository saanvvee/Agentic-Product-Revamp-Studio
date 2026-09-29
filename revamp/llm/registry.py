"""Which model each agent uses. The only place that names a model class.

Hybrid routing (default): Gemini for agents that plan, arbitrate, negotiate or need
vision; local qwen3:4b for high-volume, narrower agents. Mode "local" or "gemini"
routes everything to one family, which is itself an experiment (quality vs quota).

Every model handed out is wrapped in CachedLlm. There is no code path that returns
an uncached model (invariant 1).
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from google.adk.models.base_llm import BaseLlm

from revamp.llm.cache import CachedLlm
from revamp.settings import settings

GEMINI_AGENTS = {
    "engagement_lead",
    "client",
    "journey_auditor",  # needs vision
    "product_pricing",
    "conflict_detector",
    "red_team",
    "single_llm_baseline",  # A0 gets the strongest model, to be a fair baseline
}
LOCAL_AGENTS = {
    "chief_diagnostician",
    "voice_of_customer",
    "design",
    "engineering",
}


def family_for(agent: str, mode: str | None = None) -> str:
    mode = mode or settings.model_mode
    if mode in {"local", "gemini"}:
        return mode
    if agent in GEMINI_AGENTS:
        return "gemini"
    if agent in LOCAL_AGENTS:
        return "local"
    raise KeyError(f"no model route for agent {agent!r}")


def _inner(family: str) -> BaseLlm:
    if family == "gemini":
        from google.adk.models.google_llm import Gemini
        return Gemini(model=settings.gemini_model)
    from google.adk.models.lite_llm import LiteLlm
    # The ollama_chat/ prefix is mandatory: plain ollama/ silently drops tool calls.
    # num_ctx: Ollama's default context is small; evidence lists need ~8-12k tokens.
    return LiteLlm(model=settings.local_model, num_ctx=16384)


_SCRATCH: Path | None = None


def _scratch_cache() -> Path:
    global _SCRATCH
    if _SCRATCH is None:
        _SCRATCH = Path(tempfile.mkdtemp(prefix="revamp_scripted_"))
    return _SCRATCH


def model_for(agent: str, *, seed: int = 0, mode: str | None = None,
              override: BaseLlm | None = None) -> CachedLlm:
    """`override` swaps the inner model (tests pass a ScriptedLlm); it is still cached."""
    inner = override if override is not None else _inner(family_for(agent, mode))
    # Scripted (fake) models get a throwaway cache: tests change their responders
    # freely, and a persistent cache would replay stale fake answers.
    cache_dir = settings.cache_dir if override is None else _scratch_cache()
    return CachedLlm(inner=inner, cache_dir=cache_dir, seed=seed,
                     read_only=settings.cache_read_only,
                     concurrency=settings.llm_concurrency)
