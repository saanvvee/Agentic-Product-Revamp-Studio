"""Model routing: which agent gets which Ollama tier, and what reaches Ollama."""

import dataclasses
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from google.adk.models.llm_request import LlmRequest
from google.genai import types

from revamp.agents import engagement, teams
from revamp.llm import registry
from revamp.settings import settings


@pytest.fixture
def local_mode(monkeypatch):
    monkeypatch.setattr(registry, "settings", dataclasses.replace(settings, model_mode="local",
                                                                  local_tier_overrides={}))


def test_every_agent_route_has_a_tier(local_mode):
    for route in registry.LOCAL_TIER:
        assert registry.tier_for(route) in registry.TIERS


def test_judgment_agents_think_and_volume_agents_do_not(local_mode):
    for route in ("conflict_detector", "red_team", "handoff_reviewer", "engagement_adapter"):
        assert registry.tier_for(route) == "thinking"
    for route in ("design", "engineering", "product_pricing", "voice_of_customer", "client",
                  "chief_diagnostician", "engagement_lead"):
        assert registry.tier_for(route) == "instruct"
    assert registry.tier_for("journey_auditor") == "vision"
    assert registry.sees_images("journey_auditor") and not registry.sees_images("design")


def test_shared_agent_names_route_separately(local_mode):
    """The adapter and the handoff reviewer reuse an ADK name but not a model."""
    tag = lambda a: a.model.inner.model  # noqa: E731  CachedLlm -> LiteLlm model string
    lead, adapter = engagement.engagement_lead(), engagement.engagement_lead_adapter()
    eng, reviewer = teams.team("engineering"), teams.handoff_reviewer()
    assert lead.name == adapter.name and tag(lead) != tag(adapter)
    assert eng.name == reviewer.name and tag(eng) != tag(reviewer)
    assert "thinking" in tag(adapter) and "instruct" in tag(lead)


def test_tier_overrides(monkeypatch):
    monkeypatch.setattr(registry, "settings", dataclasses.replace(
        settings, model_mode="local", local_tier_overrides={"red_team": "instruct"}))
    assert registry.tier_for("red_team") == "instruct"
    monkeypatch.setattr(registry, "settings", dataclasses.replace(
        settings, model_mode="local", local_tier_overrides={"red_team": "fast"}))
    with pytest.raises(ValueError):
        registry.tier_for("red_team")


@pytest.fixture
def fake_ollama(monkeypatch):
    """A stand-in Ollama that records every request body."""
    seen = []

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            seen.append((self.path, body))
            out = json.dumps({"model": "x", "created_at": "2026-09-30T00:00:00Z", "done": True,
                              "message": {"role": "assistant", "content": "{}"},
                              "prompt_eval_count": 1, "eval_count": 1}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(out)))
            self.end_headers()
            self.wfile.write(out)

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setattr(registry, "settings", dataclasses.replace(
        settings, ollama_api_base=f"http://127.0.0.1:{srv.server_port}", ollama_num_gpu=999))
    yield seen
    srv.shutdown()


@pytest.mark.parametrize("tier,think", [("instruct", False), ("thinking", True),
                                        ("vision", False)])
async def test_request_forces_gpu_and_sets_think(fake_ollama, tier, think):
    llm = registry.ollama_llm(tier)
    req = LlmRequest(contents=[types.Content(role="user", parts=[types.Part(text="hi")])])
    async for _ in llm.generate_content_async(req):
        pass
    chat = [b for path, b in fake_ollama if path == "/api/chat"][-1]
    assert chat["model"] == registry.settings.ollama_models[tier]
    assert chat["options"]["num_gpu"] == 999  # every layer on the GPU
    assert chat["options"]["num_ctx"] == registry.settings.ollama_num_ctx[tier]
    assert chat["think"] is think
    assert chat["keep_alive"] == registry.settings.ollama_keep_alive
