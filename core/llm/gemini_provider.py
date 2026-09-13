"""Hosted LLM provider: Gemini Flash on the AI Studio free tier.

Used for the reasoning-heavy, low-volume agents (orchestrator, critic,
diagnostic RAG). Quota, not compute, is the binding constraint on this project
(PRD S7.8), so this class is built around surviving 429s rather than around
throughput.

Two mechanisms, both required:

  * A concurrency semaphore (PRD invariant 4, default 3). Parallel work is what
    trips a per-minute limit first, and the limit is per-key, so it must be
    enforced in one place that every caller shares.
  * Exponential backoff with jitter on 429. Jitter matters: without it, several
    coroutines that hit the limit together retry together and trip it again.

Note the free-tier RPM/RPD figures are no longer published on a public page;
they are per-account and must be read from the AI Studio dashboard. Do not
hardcode an assumed limit here -- let the API tell us, and back off when it does.
"""

from __future__ import annotations

import asyncio
import random
import time
from typing import Any

from core.llm.base import (
    LLMError,
    LLMResponse,
    ProviderUnavailableError,
    QuotaExceededError,
    ToolCall,
    ToolSpec,
)


class GeminiProvider:
    """LLMProvider backed by Google AI Studio's Gemini API."""

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-2.5-flash",
        *,
        max_concurrency: int = 3,
        max_retries: int = 5,
        base_delay_s: float = 2.0,
        max_delay_s: float = 60.0,
    ) -> None:
        if not api_key:
            # Fail here, loudly, at construction. A provider built without a key
            # would fail later inside a workflow, where the real cause is much
            # harder to see.
            raise ValueError(
                "GeminiProvider requires an API key. Set IRA_GOOGLE_API_KEY in "
                ".env (get one at https://aistudio.google.com/apikey)."
            )

        from google import genai  # imported lazily: the Ollama path needs no SDK

        self._client = genai.Client(api_key=api_key)
        self._model = model
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._max_retries = max_retries
        self._base_delay_s = base_delay_s
        self._max_delay_s = max_delay_s

        self.quota_events = 0
        """Count of 429s survived. Reported with eval results: 'we hit the limit
        N times and backoff absorbed it' is a real finding about free-tier
        operation, and it is evidence the mitigation works."""

    @property
    def model_id(self) -> str:
        return f"gemini/{self._model}"

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
        from google.genai import types

        config: dict[str, Any] = {"temperature": temperature, "seed": seed}
        if system:
            config["system_instruction"] = system
        if max_tokens is not None:
            config["max_output_tokens"] = max_tokens
        if tools:
            config["tools"] = [
                types.Tool(
                    function_declarations=[
                        types.FunctionDeclaration(
                            name=t.name,
                            description=t.description,
                            parameters=t.parameters,
                        )
                        for t in tools
                    ]
                )
            ]

        async with self._semaphore:
            return await self._complete_with_backoff(
                prompt=prompt, config=types.GenerateContentConfig(**config)
            )

    async def _complete_with_backoff(self, *, prompt: str, config: Any) -> LLMResponse:
        last_error: Exception | None = None

        for attempt in range(self._max_retries):
            started = time.perf_counter()
            try:
                response = await self._client.aio.models.generate_content(
                    model=self._model, contents=prompt, config=config
                )
            except Exception as exc:  # SDK raises a wide range of error types
                if not self._is_quota_error(exc):
                    raise ProviderUnavailableError(f"Gemini call failed: {exc}") from exc

                self.quota_events += 1
                last_error = exc

                if attempt == self._max_retries - 1:
                    break

                # Full jitter: sleep uniformly in [0, capped_backoff]. Retrying
                # at a fixed backoff would re-synchronise coroutines that were
                # throttled together and trip the limit again immediately.
                ceiling = min(self._base_delay_s * (2**attempt), self._max_delay_s)
                await asyncio.sleep(random.uniform(0.0, ceiling))
                continue

            latency_ms = int((time.perf_counter() - started) * 1000)
            return self._to_response(response, latency_ms)

        raise QuotaExceededError(
            f"Gemini quota exhausted after {self._max_retries} attempts. "
            f"Free-tier limits are per-account; check the AI Studio dashboard. "
            f"Last error: {last_error}"
        )

    @staticmethod
    def _is_quota_error(exc: Exception) -> bool:
        """Identify a 429 without depending on one SDK exception class.

        The SDK's exception hierarchy has moved between versions; matching on
        the status code and the standard status string is more durable than
        catching a type that may be renamed.
        """
        text = str(exc).lower()
        return (
            "429" in text
            or "resource_exhausted" in text
            or "rate limit" in text
            or "quota" in text
        )

    def _to_response(self, response: Any, latency_ms: int) -> LLMResponse:
        calls: list[ToolCall] = []
        text_parts: list[str] = []

        for candidate in getattr(response, "candidates", None) or []:
            content = getattr(candidate, "content", None)
            for part in getattr(content, "parts", None) or []:
                if getattr(part, "text", None):
                    text_parts.append(part.text)
                fn = getattr(part, "function_call", None)
                if fn is not None:
                    calls.append(
                        ToolCall(name=fn.name, arguments=dict(fn.args or {}))
                    )

        usage = getattr(response, "usage_metadata", None)
        return LLMResponse(
            text="".join(text_parts).strip(),
            tool_calls=tuple(calls),
            prompt_tokens=getattr(usage, "prompt_token_count", 0) or 0,
            completion_tokens=getattr(usage, "candidates_token_count", 0) or 0,
            latency_ms=latency_ms,
            model=self.model_id,
            cached=False,
            raw={},
        )

    async def aclose(self) -> None:
        """No persistent connection to release; defined to satisfy the protocol."""
        return None


__all__ = ["GeminiProvider", "LLMError", "QuotaExceededError"]
