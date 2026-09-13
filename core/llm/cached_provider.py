"""Disk cache decorator. Wraps ANY LLMProvider (PRD invariant 3).

Without this, iterating is impossible: PRD S7.8's arithmetic is 4 Gemini-backed
agents x 150 incidents x several ablations, which exceeds the free-tier daily
quota well before the results table exists. With it, re-running an unchanged
configuration costs nothing.

THE CACHE KEY INCLUDES THE SEED. This is not a detail. v1.0 specified a
prompt-hash key while also requiring three seeded runs for error bars; with a
prompt-only key, runs 2 and 3 are cache hits returning run 1's bytes and the
reported standard deviation is exactly zero -- a number that looks like a result
and is an artefact of the cache. See PRD S7.8 and the B11 amendment.

It is a decorator rather than a base class so that caching composes with any
provider and can be switched off in one config flag without changing which
provider is built.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from core.llm.base import LLMProvider, LLMResponse, ToolCall, ToolSpec

CACHE_FORMAT_VERSION = "1"
"""Bump to invalidate every entry at once, e.g. if LLMResponse gains a field
that changes meaning. Cheaper and safer than hand-deleting a cache directory.
"""


class CachedProvider:
    """Reads through to an inner provider, writing every response to disk.

    One JSON file per entry, named by key. Files rather than SQLite because they
    diff, they can be inspected by hand when a result looks wrong, and a fixture
    subset can be committed to make an eval reproducible on a fresh checkout.
    """

    def __init__(
        self,
        inner: LLMProvider,
        cache_dir: Path,
        *,
        read_only: bool = False,
    ) -> None:
        self._inner = inner
        self._cache_dir = Path(cache_dir)
        self._read_only = read_only
        self._cache_dir.mkdir(parents=True, exist_ok=True)

        self.hits = 0
        self.misses = 0
        """Counted so an eval run can report its cache hit rate. A run that was
        supposed to be free and was not is worth noticing before the quota is
        gone, not after."""

    @property
    def model_id(self) -> str:
        return self._inner.model_id

    def _key(
        self,
        *,
        prompt: str,
        system: str | None,
        tools: tuple[ToolSpec, ...],
        temperature: float,
        seed: int,
        max_tokens: int | None,
    ) -> str:
        """Every input that can change the response is in the key.

        Including tools: the same prompt with different tools available is a
        different question, and colliding those would silently serve an answer
        that could not have used the tool the caller offered.
        """
        material = json.dumps(
            {
                "v": CACHE_FORMAT_VERSION,
                "model": self._inner.model_id,
                "prompt": prompt,
                "system": system,
                "tools": sorted(
                    (t.name, json.dumps(t.parameters, sort_keys=True)) for t in tools
                ),
                "temperature": temperature,
                "seed": seed,
                "max_tokens": max_tokens,
            },
            sort_keys=True,
        )
        return hashlib.sha256(material.encode()).hexdigest()

    def _path(self, key: str) -> Path:
        """Shard by first two hex chars: a flat directory with tens of thousands
        of files is slow to list on Windows."""
        return self._cache_dir / key[:2] / f"{key}.json"

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
        key = self._key(
            prompt=prompt,
            system=system,
            tools=tools,
            temperature=temperature,
            seed=seed,
            max_tokens=max_tokens,
        )
        path = self._path(key)

        if path.is_file():
            try:
                cached = self._load(path)
            except (json.JSONDecodeError, KeyError, TypeError):
                # A corrupt entry (interrupted write, edited by hand) must not
                # poison a run. Treat it as a miss and overwrite it.
                cached = None
            if cached is not None:
                self.hits += 1
                return cached

        self.misses += 1
        response = await self._inner.complete(
            prompt,
            system=system,
            tools=tools,
            temperature=temperature,
            seed=seed,
            max_tokens=max_tokens,
        )

        if not self._read_only:
            self._store(path, response)

        return response

    @staticmethod
    def _load(path: Path) -> LLMResponse:
        data = json.loads(path.read_text(encoding="utf-8"))
        return LLMResponse(
            text=data["text"],
            tool_calls=tuple(
                ToolCall(name=c["name"], arguments=c["arguments"])
                for c in data.get("tool_calls", [])
            ),
            prompt_tokens=data.get("prompt_tokens", 0),
            completion_tokens=data.get("completion_tokens", 0),
            latency_ms=data.get("latency_ms", 0),
            model=data.get("model", ""),
            cached=True,
            raw=data.get("raw", {}),
        )

    @staticmethod
    def _store(path: Path, response: LLMResponse) -> None:
        """Write atomically.

        An interrupted eval run (Ctrl-C, laptop sleep) must not leave a
        half-written JSON file that fails to parse on the next run.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "text": response.text,
            "tool_calls": [
                {"name": c.name, "arguments": c.arguments} for c in response.tool_calls
            ],
            "prompt_tokens": response.prompt_tokens,
            "completion_tokens": response.completion_tokens,
            "latency_ms": response.latency_ms,
            "model": response.model,
            "raw": response.raw,
        }
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(path)

    async def aclose(self) -> None:
        await self._inner.aclose()
