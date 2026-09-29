"""Events, spans and the dashboard API, on a scripted run (no network, no models)."""

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from starlette.testclient import TestClient

from revamp import observe
from revamp.workflow.runner import run_engagement
from tests.test_workflow_e2e import PRODUCT, kb_path, scripted  # noqa: F401  (fixture)

_EXPORTER = InMemorySpanExporter()


@pytest.fixture(scope="module", autouse=True)
def tracer_provider():
    """The global provider can be set once per process; tests share this one."""
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(_EXPORTER))
    trace.set_tracer_provider(provider)
    yield


async def test_events_cover_the_run_and_are_replayable(kb_path):  # noqa: F811
    q = observe.bus.subscribe()
    try:
        res = await run_engagement(PRODUCT, "A2", kb_path=kb_path, overrides=scripted()[0])
    finally:
        observe.bus.unsubscribe(q)
    live = []
    while not q.empty():
        live.append(q.get_nowait())
    stored = observe.load_events(res.record.run_id)
    assert [e["seq"] for e in stored] == [e["seq"] for e in live]  # file == stream
    types = {e["type"] for e in stored}
    assert {"run_started", "node_started", "node_finished", "agent_started", "agent_finished",
            "llm_call", "proposals", "plan", "client_verdict", "run_finished"} <= types
    started = next(e for e in stored if e["type"] == "run_started")
    assert {n["id"] for n in started["graph"]["nodes"]} >= {"propose", "client", "allocate"}
    # The back-edge the scripted run takes is visible as a routed node_finished.
    assert any(e["type"] == "node_finished" and e["node"] == "handoff" and e["route"] == "revise"
               for e in stored)
    assert "frozen pricing" not in str(stored)  # private constraint text never streamed


async def test_one_trace_per_run_with_nested_node_spans(kb_path):  # noqa: F811
    _EXPORTER.clear()
    await run_engagement(PRODUCT, "A1", kb_path=kb_path, overrides=scripted()[0])
    spans = _EXPORTER.get_finished_spans()
    root = [s for s in spans if s.name == "engagement"]
    assert len(root) == 1
    nodes = [s for s in spans if s.name.startswith("node.")]
    assert {s.name for s in nodes} >= {"node.init", "node.propose", "node.allocate",
                                      "node.client", "node.finalize"}
    assert {s.context.trace_id for s in nodes} == {root[0].context.trace_id}
    assert root[0].attributes["langfuse.trace.name"] == f"revamp {PRODUCT} A1"
    assert nodes[0].attributes["langfuse.observation.type"] == "chain"


async def test_dashboard_api_lists_and_replays_runs(kb_path):  # noqa: F811
    from revamp.dashboard.server import app
    res = await run_engagement(PRODUCT, "A1", kb_path=kb_path, overrides=scripted()[0])
    with TestClient(app) as client:
        meta = client.get("/api/meta").json()
        assert "umami" in meta["products"] and any(a["name"] == "A2" for a in meta["arms"])
        runs = client.get("/api/runs").json()
        assert res.record.run_id in {r["run_id"] for r in runs}
        evs = client.get(f"/api/runs/{res.record.run_id}/events").json()
        assert evs[0]["type"] == "run_started" and evs[-1]["type"] == "run_finished"
        assert client.get("/").status_code == 200
        assert client.get("/static/vendor/cytoscape.min.js").status_code == 200
        assert client.post(f"/api/runs/{res.record.run_id}/approval",
                           json={"rejected": []}).status_code == 404  # not paused
