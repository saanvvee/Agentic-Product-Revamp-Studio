"""The LLM provider seam.

Every agent takes an LLMProvider by constructor injection. No agent imports
Ollama, Gemini, or litellm directly -- ever. That rule is what makes the
local-to-API switch one line of config instead of a refactor, and what makes
ablation A5 (all-Gemini) a configuration rather than a second program.

Three implementations plus a decorator:
    ollama_provider.OllamaProvider    local qwen3:4b, privacy-preserving
    gemini_provider.GeminiProvider    hosted Flash, quota-constrained
    stub_provider.StubProvider        deterministic, no network, for tests
    cached_provider.CachedProvider    wraps ANY of the above (PRD invariant 3)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


class LLMError(RuntimeError):
    """Base for provider failures that callers may reasonably handle."""


class QuotaExceededError(LLMError):
    """Rate limit or daily quota hit (HTTP 429).

    Distinct from a generic failure because the response is different: back off
    and retry, rather than fail the incident. PRD R2 and R21.
    """


class ProviderUnavailableError(LLMError):
    """The provider could not be reached at all (server down, bad host)."""


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """A tool offered to the model, in provider-neutral form.

    Deliberately not any vendor's schema type: keeping this ours is what stops
    a vendor's shape leaking into agent code through the seam.
    """

    name: str
    description: str
    parameters: dict[str, Any]
    """JSON Schema for the arguments object."""


@dataclass(frozen=True, slots=True)
class ToolCall:
    """A model's request to invoke a tool."""

    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True, slots=True)
class LLMResponse:
    """One completion, with the cost accounting the budget ledger needs.

    `latency_ms` is SYSTEM OVERHEAD, never domain cost (PRD S5.5b). It is
    measured and reported, but it is never debited from an incident's budget:
    the budget models plant evidence acquisition, and the LLM is the reasoning
    substrate deciding about that, not part of the modelled process.
    """

    text: str
    tool_calls: tuple[ToolCall, ...] = ()
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: int = 0
    model: str = ""
    cached: bool = False
    """True when served from the disk cache. Cached calls cost no quota, which
    is what makes re-running an ablation nearly free (PRD S7.8)."""

    raw: dict[str, Any] = field(default_factory=dict, repr=False)
    """Provider-native payload, kept for debugging. Never routed on."""

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@runtime_checkable
class LLMProvider(Protocol):
    """What every agent depends on, and the only LLM surface they may touch.

    Kept deliberately small. A wide protocol is hard to implement twice, and a
    seam with only one real implementation is not a seam.
    """

    @property
    def model_id(self) -> str:
        """Exact pinned model identifier, never a floating tag like ':latest'.

        Stamped into results and into the cache key, so a model swap can never
        be mistaken for a change in system behaviour (PRD R23).
        """
        ...

    async def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        tools: tuple[ToolSpec, ...] = (),
        temperature: float = 0.0,
        seed: int = 0,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """Run one completion.

        `seed` is part of the cache key, not decoration: without it, the three
        seeded runs required for A2's error bars would be cache hits returning
        identical bytes, and the reported standard deviation would be exactly
        zero (PRD S7.8, S12.4).
        """
        ...

    async def aclose(self) -> None:
        """Release resources. Safe to call more than once."""
        ...
