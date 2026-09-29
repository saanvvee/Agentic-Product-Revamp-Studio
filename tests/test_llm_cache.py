import asyncio

import pytest
from google.adk.models.llm_request import LlmRequest
from google.genai import types

from revamp.contracts import CostLedger
from revamp.llm.cache import CachedLlm, CacheMiss, current_ledger
from revamp.llm.stub import ScriptedLlm, last_user_text


def _req(text="hello", temperature=0.0):
    return LlmRequest(contents=[types.Content(role="user", parts=[types.Part(text=text)])],
                      config=types.GenerateContentConfig(temperature=temperature))


async def _call(llm, req):
    return [r async for r in llm.generate_content_async(req)]


def _stub():
    return ScriptedLlm(responder=lambda r: "echo:" + last_user_text(r))


async def test_second_call_is_a_hit(tmp_path):
    inner = _stub()
    llm = CachedLlm(inner=inner, cache_dir=tmp_path)
    a = await _call(llm, _req())
    b = await _call(llm, _req())
    assert a[0].content.parts[0].text == b[0].content.parts[0].text == "echo:hello"
    assert inner.calls == 1 and llm.stats == {"hits": 1, "misses": 1}


async def test_seed_is_part_of_the_key(tmp_path):
    inner = _stub()
    await _call(CachedLlm(inner=inner, cache_dir=tmp_path, seed=0), _req())
    await _call(CachedLlm(inner=inner, cache_dir=tmp_path, seed=1), _req())
    assert inner.calls == 2


async def test_temperature_and_prompt_are_in_the_key(tmp_path):
    inner = _stub()
    llm = CachedLlm(inner=inner, cache_dir=tmp_path)
    await _call(llm, _req("a"))
    await _call(llm, _req("b"))
    await _call(llm, _req("a", temperature=0.7))
    assert inner.calls == 3


async def test_read_only_miss_raises(tmp_path):
    llm = CachedLlm(inner=_stub(), cache_dir=tmp_path, read_only=True)
    with pytest.raises(CacheMiss):
        await _call(llm, _req())


async def test_ledger_counts_hits_and_tokens(tmp_path):
    llm = CachedLlm(inner=_stub(), cache_dir=tmp_path)
    ledger = CostLedger()
    token = current_ledger.set(ledger)
    try:
        await _call(llm, _req())
        await _call(llm, _req())
    finally:
        current_ledger.reset(token)
    assert ledger.llm_calls == 2 and ledger.llm_cache_hits == 1
    assert ledger.prompt_tokens == 10  # the hit adds no tokens


async def test_concurrency_never_exceeds_limit(tmp_path):
    in_flight = peak = 0

    class Slow(ScriptedLlm):
        async def generate_content_async(self, req, stream=False):
            nonlocal in_flight, peak
            in_flight += 1
            peak = max(peak, in_flight)
            await asyncio.sleep(0.02)
            in_flight -= 1
            async for r in super().generate_content_async(req, stream):
                yield r

    llm = CachedLlm(inner=Slow(responder=lambda r: "x"), cache_dir=tmp_path, concurrency=3)
    await asyncio.gather(*[_call(llm, _req(str(i))) for i in range(10)])
    assert peak == 3
