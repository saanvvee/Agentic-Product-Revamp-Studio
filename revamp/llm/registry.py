"""Which model each agent uses. The only place that names a model class.

Three routing modes (REVAMP_MODEL_MODE):

  local (default)  every agent on Ollama, split into three tiers by the kind of work:
                     instruct  fast, no reasoning pass: extraction, classification,
                               writing proposals, tool loops, wording replies
                     thinking  reasons before answering: the arbitration judgments
                               (conflicts, red team, feasibility) and inferring the
                               client's hidden constraints
                     vision    reads screenshots (Journey Auditor)
  hybrid           Gemini for planning/arbitration/vision, Ollama instruct for the rest
  gemini           every agent on Gemini

Agents are routed by a ROUTE KEY, not their ADK name, because two roles share a name:
the Engagement Lead's adapt step and the Engineering handoff review.

Every model handed out is wrapped in CachedLlm. There is no code path that returns
an uncached model (invariant 1).
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from google.adk.models.base_llm import BaseLlm

from revamp.llm.cache import CachedLlm
from revamp.settings import settings

# Local tiers (PLAN, layer assignment of 30 Sep). Override per agent with
# REVAMP_LOCAL_TIERS="red_team=instruct,...".
LOCAL_TIER = {
    "engagement_lead": "instruct",      # pick focus areas from a short list
    "engagement_adapter": "thinking",   # infer hidden constraints from rejections
    "client": "instruct",               # decision is code; the model only words it
    "chief_diagnostician": "instruct",  # multi-turn tool loop: keep each turn fast
    "voice_of_customer": "instruct",    # classify complaints
    "journey_auditor": "vision",        # screenshots
    "design": "instruct",
    "engineering": "instruct",
    "product_pricing": "instruct",
    "handoff_reviewer": "thinking",     # technical feasibility and cost realism
    "conflict_detector": "thinking",    # pairwise contradictions across ~20 proposals
    "red_team": "thinking",             # does the evidence support each item?
    "single_llm_baseline": "thinking",  # A0 gets the strongest setting: fair baseline
}
TIERS = ("instruct", "thinking", "vision")

GEMINI_AGENTS = {  # hybrid mode
    "engagement_lead", "engagement_adapter", "client", "journey_auditor",
    "product_pricing", "conflict_detector", "red_team", "handoff_reviewer",
    "single_llm_baseline",
}


def family_for(route: str, mode: str | None = None) -> str:
    """"gemini" or "local"."""
    mode = mode or settings.model_mode
    if mode == "gemini":
        return "gemini"
    if mode == "hybrid":
        return "gemini" if route in GEMINI_AGENTS else "local"
    if mode == "local":
        return "local"
    raise ValueError(f"unknown REVAMP_MODEL_MODE {mode!r}")


def tier_for(route: str) -> str:
    tier = settings.local_tier_overrides.get(route) or LOCAL_TIER.get(route)
    if tier is None:
        raise KeyError(f"no local tier for agent route {route!r}")
    if tier not in TIERS:
        raise ValueError(f"REVAMP_LOCAL_TIERS: {route}={tier} is not one of {TIERS}")
    return tier


def sees_images(route: str, mode: str | None = None) -> bool:
    """Whether this agent's model can be sent screenshots."""
    return family_for(route, mode) == "gemini" or tier_for(route) == "vision"


def ollama_llm(tier: str) -> BaseLlm:
    from google.adk.models.lite_llm import LiteLlm
    return LiteLlm(
        # The ollama_chat/ prefix is mandatory: plain ollama/ silently drops tool calls.
        model=f"ollama_chat/{settings.ollama_models[tier]}",
        api_base=settings.ollama_api_base,
        num_ctx=settings.ollama_num_ctx[tier],
        # num_gpu = layers offloaded to the GPU. 999 = all of them, i.e. force GPU;
        # -1 leaves the choice to Ollama. Sent in Ollama's per-request "options".
        **({"num_gpu": settings.ollama_num_gpu} if settings.ollama_num_gpu >= 0 else {}),
        keep_alive=settings.ollama_keep_alive,
        # LiteLLM maps reasoning_effort to Ollama's `think`: "none" -> false, else true.
        # Instruct and vision tags do not reason anyway; this makes it explicit.
        reasoning_effort="medium" if tier == "thinking" else "none",
        timeout=settings.llm_timeout,
    )


def _inner(route: str, mode: str | None) -> BaseLlm:
    if family_for(route, mode) == "gemini":
        from google.adk.models.google_llm import Gemini
        return Gemini(model=settings.gemini_model)
    # hybrid sends its non-Gemini agents to the instruct tier
    tier = tier_for(route) if (mode or settings.model_mode) == "local" else "instruct"
    return ollama_llm(tier)


def describe_route(route: str, mode: str | None = None) -> str:
    """Human-readable model for a route, for run records and the dashboard."""
    if family_for(route, mode) == "gemini":
        return settings.gemini_model
    tier = tier_for(route) if (mode or settings.model_mode) == "local" else "instruct"
    return f"{settings.ollama_models[tier]} ({tier})"


_SCRATCH: Path | None = None


def _scratch_cache() -> Path:
    global _SCRATCH
    if _SCRATCH is None:
        _SCRATCH = Path(tempfile.mkdtemp(prefix="revamp_scripted_"))
    return _SCRATCH


def model_for(route: str, *, seed: int = 0, mode: str | None = None,
              override: BaseLlm | None = None) -> CachedLlm:
    """`override` swaps the inner model (tests pass a ScriptedLlm); it is still cached."""
    inner = override if override is not None else _inner(route, mode)
    # Scripted (fake) models get a throwaway cache: tests change their responders
    # freely, and a persistent cache would replay stale fake answers.
    cache_dir = settings.cache_dir if override is None else _scratch_cache()
    return CachedLlm(inner=inner, cache_dir=cache_dir, seed=seed,
                     read_only=settings.cache_read_only,
                     concurrency=settings.llm_concurrency)
