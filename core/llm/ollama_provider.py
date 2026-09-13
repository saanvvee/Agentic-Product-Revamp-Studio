"""Local LLM provider via Ollama's HTTP API.

This is the privacy-preserving path that CO2 asks for: no prompt leaves the
machine. It is also slow on CPU -- 82.5 s measured for one tool-calling round
trip on the dev laptop (PRD R22) -- which is why eval runs move inference to a
free Colab GPU and why every call goes through the cache.

Talks to Ollama's REST API directly rather than through litellm or ADK. Three
reasons: the seam is ours and should not inherit a third library's shape; the
dependency chain stays short; and provider-specific behaviour (the /no_think
directive, token accounting) stays visible here instead of buried in a wrapper.

Verified 13 September 2026 with qwen3:4b. Note that Gemma 3 cannot be used at
all -- Ollama rejects tool calls for it outright:
    {"error":"registry.ollama.ai/library/gemma3:4b does not support tools"}
"""

from __future__ import annotations

import json
import time
from typing import Any

import httpx

from core.llm.base import (
    LLMResponse,
    ProviderUnavailableError,
    ToolCall,
    ToolSpec,
)


class OllamaProvider:
    """LLMProvider backed by a local Ollama server."""

    def __init__(
        self,
        model: str = "qwen3:4b",
        *,
        host: str = "http://localhost:11434",
        no_think: bool = True,
        timeout_s: float = 300.0,
    ) -> None:
        if model.endswith(":latest"):
            raise ValueError(
                "Refusing a ':latest' tag. Pin an exact model tag so results "
                "stay attributable to a known model (PRD R23)."
            )
        self._model = model
        self._host = host.rstrip("/")
        self._no_think = no_think
        # Generous default: a 4B model on CPU genuinely takes over a minute per
        # call, and a short timeout would look like a provider bug.
        self._client = httpx.AsyncClient(timeout=timeout_s)

    @property
    def model_id(self) -> str:
        return f"ollama/{self._model}"

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
        messages: list[dict[str, Any]] = []
        if system:
            messages.append({"role": "system", "content": system})

        content = prompt
        if self._no_think:
            # Qwen3 is a reasoning model and emits visible thinking tokens on
            # every call. Those are pure cost here: our agents produce short
            # structured output, and the thinking is neither parsed nor logged.
            # Suppressing it is the cheapest available mitigation for R22.
            content = f"{prompt}\n/no_think"
        messages.append({"role": "user", "content": content})

        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature, "seed": seed},
        }
        if max_tokens is not None:
            payload["options"]["num_predict"] = max_tokens
        if tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters,
                    },
                }
                for t in tools
            ]

        started = time.perf_counter()
        try:
            resp = await self._client.post(f"{self._host}/api/chat", json=payload)
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(
                f"Ollama unreachable at {self._host}. Is `ollama serve` running? ({exc})"
            ) from exc
        latency_ms = int((time.perf_counter() - started) * 1000)

        if resp.status_code >= 400:
            # Surfaced verbatim: this is exactly how we learned Gemma 3 cannot
            # tool-call, and a swallowed body would have hidden it.
            raise ProviderUnavailableError(
                f"Ollama returned HTTP {resp.status_code}: {resp.text[:400]}"
            )

        data = resp.json()
        message = data.get("message", {}) or {}

        calls = tuple(
            ToolCall(
                name=c["function"]["name"],
                arguments=(
                    c["function"]["arguments"]
                    if isinstance(c["function"].get("arguments"), dict)
                    else json.loads(c["function"].get("arguments") or "{}")
                ),
            )
            for c in (message.get("tool_calls") or [])
        )

        return LLMResponse(
            text=(message.get("content") or "").strip(),
            tool_calls=calls,
            prompt_tokens=data.get("prompt_eval_count", 0),
            completion_tokens=data.get("eval_count", 0),
            latency_ms=latency_ms,
            model=self.model_id,
            cached=False,
            raw=data,
        )

    async def aclose(self) -> None:
        await self._client.aclose()
