"""CachedLlm: wraps ANY ADK model so every call goes through the disk cache.

Invariant 1. It sits at the lowest level ADK offers, BaseLlm.generate_content_async,
so no agent can bypass it: agents are handed a CachedLlm and never see the inner
model. The same wrapper enforces invariant 5 (at most 3 calls in flight) and
records every call's tokens and latency in the orchestration-cost ledger.

The key covers everything that can change the answer:
    model id + full request contents + config (system prompt, tools, output schema,
    temperature) + seed + a format version.
The seed matters: without it, three "seeded" runs would be cache hits returning
run 1's bytes and every standard deviation would be exactly zero. (Lesson carried
over from the archived project.)

One JSON file per call, sharded by the first two hex chars of the key. Files, not
SQLite, so a suspicious result can be opened and read by hand.
"""

from __future__ import annotations

import asyncio
import contextvars
import hashlib
import json
import time
from pathlib import Path
from typing import AsyncGenerator

from google.adk.models.base_llm import BaseLlm
from opentelemetry import trace
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from pydantic import ConfigDict, PrivateAttr

from revamp import observe
from revamp.contracts import CostLedger

CACHE_FORMAT_VERSION = "1"


class CacheMiss(RuntimeError):
    """Read-only mode and the answer is not cached. Raised instead of silently
    spending quota, e.g. when replaying an evaluation from committed fixtures."""


# The ledger for the current run. A ContextVar so concurrent runs (e.g. two arms in
# one process) keep separate books; each asyncio task inherits its creator's value.
current_ledger: contextvars.ContextVar[CostLedger | None] = contextvars.ContextVar(
    "current_ledger", default=None)

# One semaphore for the whole process: the limit is about the provider's rate limit,
# which is shared by every agent. Created lazily inside the running event loop.
_semaphores: dict[int, asyncio.Semaphore] = {}


def _semaphore(limit: int) -> asyncio.Semaphore:
    loop_id = id(asyncio.get_running_loop())
    if loop_id not in _semaphores:
        _semaphores[loop_id] = asyncio.Semaphore(limit)
    return _semaphores[loop_id]


def _schema_repr(schema) -> object:
    if schema is None:
        return None
    if hasattr(schema, "model_json_schema"):
        return schema.model_json_schema()
    if hasattr(schema, "model_dump"):
        return schema.model_dump(mode="json", exclude_none=True)
    return repr(schema)


def request_key(model: str, req: LlmRequest, seed: int) -> str:
    cfg = req.config.model_dump(mode="json", exclude_none=True,
                                exclude={"response_schema", "http_options"})
    material = {
        "v": CACHE_FORMAT_VERSION,
        "model": model,
        "seed": seed,
        "contents": [c.model_dump(mode="json", exclude_none=True) for c in req.contents],
        "config": cfg,
        "response_schema": _schema_repr(req.config.response_schema),
    }
    blob = json.dumps(material, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()


class CachedLlm(BaseLlm):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    inner: BaseLlm
    cache_dir: Path
    seed: int = 0
    read_only: bool = False
    concurrency: int = 3

    _hits: int = PrivateAttr(default=0)
    _misses: int = PrivateAttr(default=0)

    def __init__(self, **data):
        data.setdefault("model", data["inner"].model)
        super().__init__(**data)

    @property
    def capabilities(self):
        return self.inner.capabilities

    def _path(self, key: str) -> Path:
        return Path(self.cache_dir) / key[:2] / f"{key}.json"

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        # The seed is part of the request itself, so providers that honour it
        # (Gemini, Ollama) produce the same answer the key promises.
        if llm_request.config.seed is None:
            llm_request.config.seed = self.seed
        key = request_key(self.model, llm_request, self.seed)
        path = self._path(key)
        ledger = current_ledger.get()

        cached = self._load(path)
        span = trace.get_current_span()  # ADK's model-call span, when tracing is on
        span.set_attribute("revamp.cache_hit", cached is not None)
        if cached is not None:
            observe.emit("llm_call", model=self.model, cached=True, seconds=0)
            self._hits += 1
            if ledger:
                ledger.llm_calls += 1
                ledger.llm_cache_hits += 1
            for r in cached:
                yield r
            return

        if self.read_only:
            raise CacheMiss(f"{self.model}: no cached answer for key {key[:12]}")

        self._misses += 1
        started = time.perf_counter()
        async with _semaphore(self.concurrency):
            # Always non-streaming: one complete turn is what we cache and replay.
            responses = [r async for r in self.inner.generate_content_async(
                llm_request, stream=False) if not r.partial]
        elapsed = time.perf_counter() - started

        if ledger:
            ledger.llm_calls += 1
            ledger.llm_seconds += elapsed
            for r in responses:
                u = r.usage_metadata
                if u:
                    ledger.prompt_tokens += u.prompt_token_count or 0
                    ledger.completion_tokens += u.candidates_token_count or 0

        usage = [r.usage_metadata for r in responses if r.usage_metadata]
        observe.emit("llm_call", model=self.model, cached=False, seconds=round(elapsed, 1),
                     prompt_tokens=sum(u.prompt_token_count or 0 for u in usage),
                     completion_tokens=sum(u.candidates_token_count or 0 for u in usage))
        if not any(r.error_code for r in responses):  # never cache a failure
            self._store(path, responses)
        for r in responses:
            yield r

    @staticmethod
    def _load(path: Path) -> list[LlmResponse] | None:
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return [LlmResponse.model_validate(d) for d in data["responses"]]
        except (json.JSONDecodeError, KeyError, ValueError):
            return None  # corrupt entry (interrupted write): treat as a miss

    def _store(self, path: Path, responses: list[LlmResponse]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"model": self.model, "seed": self.seed,
                   "responses": [r.model_dump(mode="json", exclude_none=True)
                                 for r in responses]}
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=1), encoding="utf-8")
        tmp.replace(path)  # atomic: a Ctrl-C never leaves half a file

    @property
    def stats(self) -> dict[str, int]:
        return {"hits": self._hits, "misses": self._misses}
