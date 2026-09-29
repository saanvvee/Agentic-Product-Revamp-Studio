"""The Client over a real A2A HTTP boundary (localhost), with a scripted model."""

import asyncio
import json
import socket

import pytest
import uvicorn

from revamp.arbitration.plan import build_plan
from revamp.client_service import build_app, remote_evaluate
from revamp.contracts import ClientConstraint, Proposal
from revamp.kb import KnowledgeBase
from revamp.llm.stub import ScriptedLlm


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("localhost", 0))
        return s.getsockname()[1]


@pytest.fixture
async def service(tmp_path):
    kb = tmp_path / "kb.sqlite3"
    KnowledgeBase(kb, "client").set_constraints("umami", [ClientConstraint(
        id="K1", product="umami", kind="forbid_area", param="pricing_page",
        reason_code="brand", description="secret board decision",
        public_hint="Pricing is off the table this year.")])
    port = _free_port()
    app = build_app(str(kb), "localhost", port,
                    override=ScriptedLlm(responder=lambda r: json.dumps({"message": "No."})))
    server = uvicorn.Server(uvicorn.Config(app, host="localhost", port=port, log_level="error"))
    task = asyncio.create_task(server.serve())
    while not server.started:
        await asyncio.sleep(0.05)
    yield f"http://localhost:{port}", kb
    server.should_exit = True
    await task


async def test_remote_client_vetoes_without_leaking(service):
    url, kb = service
    props = [Proposal(id="PP1-1", team="product_pricing", title="t", change="c", rationale="r",
                      finding_ids=("F-1",), cost_days=2, value=5, areas=("pricing_page",))]
    plan = build_plan(product="umami", arm="A2", round=0, budget_days=10, proposals=props)
    v = await remote_evaluate(url, plan, {p.id: p for p in props}, "run-x", 0, 0)
    assert v.decision == "reject" and v.vetoed_proposal_ids == ("PP1-1",)
    assert v.reason_codes == ("brand",)
    assert "secret board decision" not in v.model_dump_json()
    # The verdict was recorded by the service process, readable by the team role.
    assert KnowledgeBase(kb, "team").verdicts("run-x")[0].decision == "reject"
