"""Composition root for the LLM seam.

This is the ONLY module in the tree that is allowed to import concrete
providers. Everything else -- every agent, every workflow node -- receives an
LLMProvider through its constructor.

That rule is what makes `IRA_LLM__PROVIDER=gemini` switch the entire system, and
what makes ablation A5 (all-Gemini) a configuration rather than a fork of the
code. If you find yourself importing OllamaProvider anywhere else, the seam has
been breached and the ablation is no longer trustworthy.
"""

from __future__ import annotations

from core.config import Settings
from core.llm.base import LLMProvider
from core.llm.cached_provider import CachedProvider


def build_llm_provider(settings: Settings) -> LLMProvider:
    """Construct the configured provider, wrapped in the cache unless disabled.

    Caching is applied last so it wraps whatever is underneath: the cache is a
    property of how we call a model, not of which model we called.
    """
    provider = _build_inner(settings)

    if settings.llm.cached:
        return CachedProvider(provider, cache_dir=settings.cache_dir)

    # Uncached is legitimate only in a test that is testing the cache itself, or
    # in a deliberate one-off. PRD invariant 3 otherwise forbids it: uncached
    # calls burn quota that cannot be replaced.
    return provider


def _build_inner(settings: Settings) -> LLMProvider:
    match settings.llm.provider:
        case "ollama":
            from core.llm.ollama_provider import OllamaProvider

            return OllamaProvider(
                model=settings.llm.ollama_model,
                host=settings.llm.ollama_host,
                no_think=settings.llm.ollama_no_think,
            )

        case "gemini":
            from core.llm.gemini_provider import GeminiProvider

            if not settings.google_api_key:
                raise ValueError(
                    "llm.provider is 'gemini' but no API key is configured. "
                    "Set IRA_GOOGLE_API_KEY in .env."
                )
            return GeminiProvider(
                api_key=settings.google_api_key,
                model=settings.llm.gemini_model,
                max_concurrency=settings.llm.max_concurrency,
            )

        case "stub":
            from core.llm.stub_provider import StubProvider

            # No default response: an unscripted prompt must raise rather than
            # invent an answer. A stub that guesses would let a broken agent
            # pass its tests, which is worse than no test at all.
            return StubProvider()

        case unknown:  # pragma: no cover - Literal type makes this unreachable
            raise ValueError(f"unknown llm provider: {unknown!r}")
