"""Deterministic in-process LLMProvider. No network, no model, no quota.

This is not a toy. It is what makes the whole system testable and what lets the
workflow, budget, and guardrail logic be developed and run end-to-end while the
real providers are slow (PRD R22: ~82.5 s per local call on the dev CPU).

It is a stub, never a fake that returns plausible garbage: responses are either
explicitly scripted by the test, or a flat refusal to guess. An unscripted
prompt raises rather than inventing an answer, because a stub that quietly makes
something up would let a broken agent pass its tests.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable

from core.llm.base import LLMResponse, ToolCall, ToolSpec


class StubResponseMissing(RuntimeError):
    """No scripted response matched this prompt.

    Raised rather than guessing. If a test hits this, the test is incomplete --
    that is information, not an obstacle.
    """


class StubProvider:
    """An LLMProvider whose answers are decided by the test, not by a model.

    Three ways to script it, most specific first:

    1. `responses`: exact substring of the prompt -> response text
    2. `tool_responses`: substring -> tool calls to emit
    3. `default`: used when nothing matches; if None, raises

    Example::

        provider = StubProvider(responses={"severity": '{"severity": "critical"}'})
    """

    def __init__(
        self,
        responses: dict[str, str] | None = None,
        *,
        tool_responses: dict[str, tuple[ToolCall, ...]] | None = None,
        default: str | None = None,
        latency_ms: int = 0,
        handler: Callable[[str], str] | None = None,
        model_id: str = "stub/deterministic-v1",
    ) -> None:
        self._responses = responses or {}
        self._tool_responses = tool_responses or {}
        self._default = default
        self._latency_ms = latency_ms
        self._handler = handler
        self._model_id = model_id

        self.calls: list[dict[str, object]] = []
        """Every call made, in order. Lets a test assert on what an agent asked,
        not merely on what it returned -- which is how we check that an agent
        actually consulted memory rather than inventing a history."""

        self._closed = False

    @property
    def model_id(self) -> str:
        return self._model_id

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
        if self._closed:
            raise RuntimeError("StubProvider used after aclose()")

        self.calls.append(
            {
                "prompt": prompt,
                "system": system,
                "tools": tuple(t.name for t in tools),
                "temperature": temperature,
                "seed": seed,
                "max_tokens": max_tokens,
            }
        )

        for needle, calls in self._tool_responses.items():
            if needle in prompt:
                return self._build(text="", tool_calls=calls, prompt=prompt, seed=seed)

        for needle, text in self._responses.items():
            if needle in prompt:
                return self._build(text=text, tool_calls=(), prompt=prompt, seed=seed)

        if self._handler is not None:
            return self._build(
                text=self._handler(prompt), tool_calls=(), prompt=prompt, seed=seed
            )

        if self._default is not None:
            return self._build(
                text=self._default, tool_calls=(), prompt=prompt, seed=seed
            )

        raise StubResponseMissing(
            "StubProvider has no scripted response for this prompt and no "
            "default was set. Script it explicitly rather than letting a stub "
            f"invent an answer.\nPrompt starts: {prompt[:200]!r}"
        )

    def _build(
        self,
        *,
        text: str,
        tool_calls: tuple[ToolCall, ...],
        prompt: str,
        seed: int,
    ) -> LLMResponse:
        """Token counts are a deterministic function of the text.

        Not real tokenisation -- a stub must not pretend to be a tokeniser. But
        they are stable across runs and vary with content, which is what budget
        accounting tests need.
        """
        digest = hashlib.sha256(f"{prompt}|{seed}".encode()).hexdigest()
        return LLMResponse(
            text=text,
            tool_calls=tool_calls,
            prompt_tokens=max(1, len(prompt) // 4),
            completion_tokens=max(1, len(text) // 4),
            latency_ms=self._latency_ms,
            model=self._model_id,
            cached=False,
            raw={"stub": True, "digest": digest[:16]},
        )

    async def aclose(self) -> None:
        self._closed = True


def json_stub(payload: dict[str, object], **kwargs) -> StubProvider:
    """Convenience: a provider that always returns one JSON object.

    Common in tests for agents whose contract is structured output, e.g. triage
    emitting {"severity": ..., "reason": ...}.
    """
    return StubProvider(default=json.dumps(payload), **kwargs)
