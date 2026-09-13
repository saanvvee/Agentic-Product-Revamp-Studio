"""The test that proves the LLM seam is real.

The contract tests below run against EVERY implementation via parametrisation.
A seam with only one implementation is not a seam -- it is an abstraction nobody
has checked, and it fails at the worst moment. These tests are what stop that.

Live providers (Ollama, Gemini) are covered by the same contract but skipped
unless the backing service is actually available, so the suite stays fast and
runnable on a machine with no model server and no API key.
"""

from __future__ import annotations

import functools
import json
import os

import httpx
import pytest

from core.config import Settings
from core.llm.base import LLMProvider, LLMResponse, ToolCall, ToolSpec
from core.llm.cached_provider import CachedProvider
from core.llm.factory import build_llm_provider
from core.llm.stub_provider import StubProvider, StubResponseMissing, json_stub

PROMPT = "Classify the severity of this incident."


@functools.lru_cache(maxsize=1)
def _ollama_up() -> bool:
    """Probe once per session, not once per parametrised test.

    Without the cache this HTTP probe runs in every test's setup and adds ~2.6 s
    each, which quietly turns a fast suite into a slow one.
    """
    try:
        return httpx.get("http://localhost:11434/api/version", timeout=2.0).status_code == 200
    except Exception:
        return False


# --------------------------------------------------------------------------
# Contract: every implementation must satisfy these.
# --------------------------------------------------------------------------


def _implementations(tmp_path):
    """Build one instance of each available implementation.

    Returns (id, provider) pairs. Live services are included only when present,
    which keeps the default suite hermetic without letting the real providers
    escape the contract when they ARE available.
    """
    impls = [
        ("stub", StubProvider(default="ok")),
        ("cached_over_stub", CachedProvider(StubProvider(default="ok"), tmp_path / "c")),
    ]

    if _ollama_up():
        from core.llm.ollama_provider import OllamaProvider

        impls.append(("ollama", OllamaProvider(model="qwen3:4b")))

    key = os.environ.get("IRA_GOOGLE_API_KEY")
    if key:
        from core.llm.gemini_provider import GeminiProvider

        impls.append(("gemini", GeminiProvider(api_key=key)))

    return impls


@pytest.fixture(
    params=[
        "stub",
        "cached_over_stub",
        pytest.param("ollama", marks=pytest.mark.live),
        pytest.param("gemini", marks=pytest.mark.live),
    ]
)
def provider(request, tmp_path):
    """Every implementation, one at a time, through the same contract.

    Live providers carry the `live` marker and are deselected by default: one
    real qwen3:4b round trip takes ~82 s on CPU (PRD R22), and a suite nobody
    runs is a suite that protects nothing. Run them explicitly with:

        pytest -m live

    They are NOT optional -- CI and any pre-merge check must run them, because a
    contract verified only against stubs is not verified.
    """
    available = dict(_implementations(tmp_path))
    if request.param not in available:
        pytest.skip(f"{request.param} not available in this environment")
    return available[request.param]


async def test_satisfies_the_protocol(provider):
    """Structural check: every implementation IS an LLMProvider."""
    assert isinstance(provider, LLMProvider)


async def test_returns_a_well_formed_response(provider):
    response = await provider.complete(PROMPT, seed=0)
    assert isinstance(response, LLMResponse)
    assert isinstance(response.text, str)
    assert response.prompt_tokens >= 0
    assert response.completion_tokens >= 0
    assert response.total_tokens == response.prompt_tokens + response.completion_tokens


async def test_model_id_is_pinned_not_floating(provider):
    """A ':latest' tag makes results unattributable to a known model (R23)."""
    assert provider.model_id
    assert not provider.model_id.endswith(":latest")


async def test_aclose_is_idempotent(provider):
    """Called from a finally block that may run twice on a nested failure."""
    await provider.aclose()
    await provider.aclose()


# --------------------------------------------------------------------------
# Cache behaviour: the correctness that PRD S7.8 and B11 depend on.
# --------------------------------------------------------------------------


async def test_cache_serves_second_identical_call(tmp_path):
    inner = StubProvider(default="first")
    cached = CachedProvider(inner, tmp_path / "cache")

    first = await cached.complete(PROMPT, seed=0)
    second = await cached.complete(PROMPT, seed=0)

    assert first.text == second.text
    assert not first.cached and second.cached
    assert (cached.hits, cached.misses) == (1, 1)
    assert len(inner.calls) == 1, "second call must not reach the inner provider"


async def test_different_seeds_are_different_cache_entries(tmp_path):
    """THE regression test for B11.

    With a prompt-only cache key, seeded runs 2 and 3 return run 1's bytes and
    the standard deviation reported for A2 is exactly zero -- an artefact that
    looks like a result. The seed must be part of the key.
    """
    inner = StubProvider(handler=lambda p: "response")
    cached = CachedProvider(inner, tmp_path / "cache")

    await cached.complete(PROMPT, seed=0)
    await cached.complete(PROMPT, seed=1)
    await cached.complete(PROMPT, seed=2)

    assert cached.misses == 3, "each seed must be a distinct cache entry"
    assert cached.hits == 0
    assert len(inner.calls) == 3


async def test_tools_are_part_of_the_cache_key(tmp_path):
    """The same prompt with different tools available is a different question."""
    inner = StubProvider(default="x")
    cached = CachedProvider(inner, tmp_path / "cache")
    spec = ToolSpec(name="score_audio", description="Score audio", parameters={})

    await cached.complete(PROMPT, seed=0)
    await cached.complete(PROMPT, seed=0, tools=(spec,))

    assert cached.misses == 2


async def test_temperature_is_part_of_the_cache_key(tmp_path):
    inner = StubProvider(default="x")
    cached = CachedProvider(inner, tmp_path / "cache")

    await cached.complete(PROMPT, seed=0, temperature=0.0)
    await cached.complete(PROMPT, seed=0, temperature=0.7)

    assert cached.misses == 2


async def test_cache_survives_a_new_process(tmp_path):
    """Re-running an ablation on a fresh process must be nearly free, which is
    the entire reason the cache is on disk rather than in memory."""
    cache_dir = tmp_path / "cache"
    first = CachedProvider(StubProvider(default="persisted"), cache_dir)
    await first.complete(PROMPT, seed=0)

    second = CachedProvider(StubProvider(default="DIFFERENT"), cache_dir)
    response = await second.complete(PROMPT, seed=0)

    assert response.text == "persisted"
    assert response.cached
    assert second.hits == 1


async def test_corrupt_cache_entry_is_treated_as_a_miss(tmp_path):
    """An interrupted write must not poison a run."""
    cache_dir = tmp_path / "cache"
    cached = CachedProvider(StubProvider(default="good"), cache_dir)
    await cached.complete(PROMPT, seed=0)

    for path in cache_dir.rglob("*.json"):
        path.write_text("{ not json", encoding="utf-8")

    response = await cached.complete(PROMPT, seed=0)
    assert response.text == "good"


async def test_tool_calls_round_trip_through_the_cache(tmp_path):
    """Tool calls are how agents act; losing them in the cache would break the
    trajectory metric while still looking like a working system."""
    call = ToolCall(name="score_audio", arguments={"machine_id": "zone_a_fan_02"})
    inner = StubProvider(tool_responses={"Classify": (call,)})
    cached = CachedProvider(inner, tmp_path / "cache")

    await cached.complete(PROMPT, seed=0)
    restored = await cached.complete(PROMPT, seed=0)

    assert restored.cached
    assert restored.tool_calls == (call,)


# --------------------------------------------------------------------------
# Stub honesty: it must refuse to guess.
# --------------------------------------------------------------------------


async def test_unscripted_prompt_raises_rather_than_inventing():
    """A stub that quietly makes something up lets a broken agent pass."""
    provider = StubProvider(responses={"severity": "critical"})
    with pytest.raises(StubResponseMissing):
        await provider.complete("a completely unrelated question")


async def test_stub_records_calls_for_assertion():
    """Lets a test check what an agent ASKED, not only what it returned."""
    provider = json_stub({"severity": "standard", "reason": "single weak source"})
    await provider.complete(PROMPT, system="You are triage.", seed=7)

    assert len(provider.calls) == 1
    assert provider.calls[0]["seed"] == 7
    assert provider.calls[0]["system"] == "You are triage."
    assert json.loads((await provider.complete(PROMPT)).text)["severity"] == "standard"


# --------------------------------------------------------------------------
# The one-line switch, as an assertion rather than a claim.
# --------------------------------------------------------------------------


def test_factory_builds_stub_from_config(monkeypatch):
    monkeypatch.setenv("IRA_LLM__PROVIDER", "stub")
    monkeypatch.setenv("IRA_LLM__CACHED", "false")
    provider = build_llm_provider(Settings())
    assert isinstance(provider, StubProvider)


def test_factory_wraps_in_cache_by_default(monkeypatch, tmp_path):
    """PRD invariant 3: every LLM call goes through the disk cache."""
    monkeypatch.setenv("IRA_LLM__PROVIDER", "stub")
    monkeypatch.setenv("IRA_CACHE_DIR", str(tmp_path))
    provider = build_llm_provider(Settings())
    assert isinstance(provider, CachedProvider)


def test_factory_builds_ollama_from_config(monkeypatch):
    """The local-to-API switch, one env var, no code change."""
    monkeypatch.setenv("IRA_LLM__PROVIDER", "ollama")
    monkeypatch.setenv("IRA_LLM__CACHED", "false")
    from core.llm.ollama_provider import OllamaProvider

    provider = build_llm_provider(Settings())
    assert isinstance(provider, OllamaProvider)
    assert provider.model_id == "ollama/qwen3:4b"


def test_factory_refuses_gemini_without_a_key(monkeypatch):
    """Fail at construction, not deep inside a workflow."""
    monkeypatch.setenv("IRA_LLM__PROVIDER", "gemini")
    monkeypatch.delenv("IRA_GOOGLE_API_KEY", raising=False)
    with pytest.raises(ValueError, match="no API key"):
        build_llm_provider(Settings(google_api_key=None))


def test_ollama_provider_refuses_floating_tag():
    from core.llm.ollama_provider import OllamaProvider

    with pytest.raises(ValueError, match="latest"):
        OllamaProvider(model="qwen3:latest")
