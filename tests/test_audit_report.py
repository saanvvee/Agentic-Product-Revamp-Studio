"""The audit is a run too: run record, events, HTML report, cost split (PLAN B14).

No network and no models. The audit steps are replaced by scripted functions, so what
is under test is the reporting and the evidence chain, not the tools themselves.
"""

import asyncio

import pytest

from revamp import audit, observe, report
from revamp.contracts import CostLedger, Evidence, Finding
from revamp.kb import KnowledgeBase
from revamp.products import load_product
from tests.test_workflow_e2e import PRODUCT, kb_path  # noqa: F401  (fixture)

CATEGORY = {"seo": "seo", "pricing": "pricing", "voice": "user_voice",
            "code": "code_health", "performance": "performance",
            "accessibility": "accessibility", "journeys": "ux"}


def scripted_step(step: str, n: int = 2) -> list[Finding]:
    return [Finding.make(product=PRODUCT, category=CATEGORY[step], severity="high",
                         title=f"{step} problem {i + 1}", detail="measured, not guessed",
                         metric=f"{step}_score", value=40 + i, unit="pts",
                         evidence=Evidence(tool=f"test_{step}", target="live",
                                           locator=f"https://example.test/{step}/{i}"))
            for i in range(n)]


@pytest.fixture
def scripted_audit(monkeypatch, kb_path):  # noqa: F811
    """A deterministic audit whose tools are scripted: one step fails, on purpose."""
    from revamp.settings import settings

    async def fake_step(name, p, target):
        if name == "pricing":
            raise TimeoutError("psi did not answer")
        return scripted_step(name)
    monkeypatch.setattr(audit, "_step", fake_step)
    # `report.write` and the dashboard read settings.kb_path, so point it at the test KB.
    original = settings.kb_path
    object.__setattr__(settings, "kb_path", kb_path)
    yield kb_path
    object.__setattr__(settings, "kb_path", original)


def run_det(kb_path, steps=("seo", "pricing", "voice")):
    kb = KnowledgeBase(kb_path, "team")
    p = load_product(PRODUCT)
    return asyncio.run(audit.deterministic_audit(p, kb, "live", steps))


def test_audit_writes_a_run_record_and_says_it_finished(scripted_audit):
    path = scripted_audit
    out = run_det(path)
    rec = KnowledgeBase(path, "team").run(out["run_id"])
    assert rec.arm == "audit-det" and rec.status == "done"  # one failing tool did not sink it
    assert out["findings"] == 4 and out["new"] == 4  # pricing raised, so nothing from it
    evs = observe.load_events(out["run_id"])
    assert [e["type"] for e in evs][0] == "audit_started"
    assert [e["type"] for e in evs][-1] == "audit_finished"  # the dashboard can stop waiting
    # Every step is a node with a tool under it, so the dashboard graph has something to draw.
    assert [e.get("node") for e in evs if e["type"] == "node_started"] == ["seo", "pricing", "voice"]
    finished = evs[-1]
    assert finished["status"] == "done" and finished["findings"] == 4
    assert finished["cost"]["evidence_seconds"] >= 0


def test_step_events_carry_the_evidence_not_just_the_answer(scripted_audit):
    out = run_det(scripted_audit)
    evs = observe.load_events(out["run_id"])
    seo = next(e for e in evs if e["type"] == "tool_started" and e["tool"] == "seo")
    assert seo["args"]["pages"] and seo["args"]["target"] == "live"  # the step's input
    done = next(e for e in evs if e["type"] == "tool_finished" and e["tool"] == "seo")
    assert done["count"] == 2 and len(done["finding_ids"]) == 2 and done["ms"] >= 0
    bad = next(e for e in evs if e["type"] == "tool_finished" and e["tool"] == "pricing")
    assert "TimeoutError" in bad["error"] and bad["count"] == 0
    assert "SKIPPED" in bad["result"]  # the dashboard feed shows the reason


def test_report_rebuilds_from_the_events_without_running_a_tool(scripted_audit):
    out = run_det(scripted_audit)
    ids = next(e for e in observe.load_events(out["run_id"])
               if e["type"] == "tool_finished" and e["tool"] == "seo")["finding_ids"]
    html = report.render(out["run_id"], scripted_audit)
    assert "Audit: umami" in html and "Sequenced plan" not in html  # the audit's own report
    for step in ("seo", "pricing", "voice"):
        assert step in html
    assert all(i in html for i in ids)  # every finding id the step measured is on the page
    assert "test_seo" in html and "TimeoutError" in html  # provenance and the failure, too
    assert "Cost split" in html and "no model in it" in html  # invariant 9, stated
    assert report.render(out["run_id"], scripted_audit) == html  # deterministic output


def test_report_file_lands_where_the_cli_prints(scripted_audit):
    out = run_det(scripted_audit)
    path = report.write(out["run_id"], scripted_audit)
    assert path.is_file() and path.suffix == ".html"
    assert path.name == f"{out['run_id']}.html"
    assert path.read_text(encoding="utf-8").count("<html") == 1


def test_dashboard_launches_an_audit_and_serves_its_report(scripted_audit):
    """The demo path: Mission Control starts the audit and links its report when it ends."""
    import time

    from starlette.testclient import TestClient

    from revamp.dashboard.server import app

    with TestClient(app) as client:
        started = client.post("/api/audit", json={"product": PRODUCT, "steps": ["seo", "voice"]})
        assert started.status_code == 200
        run_id = started.json()["run_id"]  # minted up front, so the UI can link it
        deadline = time.time() + 30
        while time.time() < deadline:
            evs = client.get(f"/api/runs/{run_id}/events").json()
            if evs and evs[-1]["type"] == "audit_finished":
                break
            time.sleep(0.05)
        assert [e["type"] for e in evs][-1] == "audit_finished", "the run never announced its end"
        page = client.get(f"/api/runs/{run_id}/report")
        assert page.status_code == 200 and "Audit: umami" in page.text
        assert {r["run_id"] for r in client.get("/api/runs").json()} >= {run_id}


def test_dashboard_started_audit_leaves_a_report_file_on_disk(scripted_audit):
    """Regression: the CLI wrote runs/reports/<id>.html itself, but an audit started from
    Mission Control only served one on demand, so the demo had no file to open."""
    import time

    from starlette.testclient import TestClient

    from revamp.dashboard.server import app
    from revamp.settings import settings

    with TestClient(app) as client:
        started = client.post("/api/audit", json={"product": PRODUCT, "steps": ["seo"]})
        run_id = started.json()["run_id"]
        path = settings.runs_dir / "reports" / f"{run_id}.html"
        deadline = time.time() + 30
        while time.time() < deadline and not path.is_file():
            time.sleep(0.05)
        assert path.is_file(), f"no report file for {run_id}"
        assert "Audit: umami" in path.read_text(encoding="utf-8")


def test_findings_full_lists_the_evidence_not_only_the_counts(scripted_audit):
    """`findings` printed severity counts, which is not something you can read a report from."""
    from revamp.cli import findings_lines

    run_det(scripted_audit, steps=("seo",))
    fs = KnowledgeBase(scripted_audit, "team").findings(PRODUCT)
    text = "\n".join(findings_lines(fs, full=True))
    assert text.count("total") == 1
    for f in fs:
        assert f"{f.id}  {f.severity:8} {f.category:14} {f.title}" in text
    assert "total" in findings_lines(fs, full=False)[-1]  # counts stay the default


def test_a_pre_b14_audit_rebuilds_from_its_events(scripted_audit, monkeypatch):
    """Audits only started writing a RunRecord to the KB in B14. The older ones still have
    their events, and 'any past run's report can be rebuilt' is a promise we should keep."""
    from revamp.kb import KnowledgeBase

    run_id = run_det(scripted_audit, steps=("seo",))["run_id"]
    assert KnowledgeBase(scripted_audit, "team").run(run_id) is not None

    # pretend the KB has no record for it, as if the audit had run before B14 wrote one
    keep = KnowledgeBase.run

    def only_this_run(self, rid):
        return None if rid == run_id else keep(self, rid)

    monkeypatch.setattr(KnowledgeBase, "run", only_this_run)
    page = report.write(run_id, scripted_audit).read_text(encoding="utf-8")
    assert "Audit: umami" in page  # rebuilt from the events, not refused


def test_rail_states_the_order_and_gates_on_evidence(scripted_audit):
    """An engagement cannot run without findings, so the rail says so instead of letting
    someone discover it as a failed run."""
    from starlette.testclient import TestClient

    from revamp.dashboard.server import app

    with TestClient(app) as client:
        page = client.get("/").text
        for i in ("stepAudit", "auditGate", "runGate", "auditMode", "go", "audit"):
            assert f'id="{i}"' in page
        assert page.index("Run the audit") < page.index("Run engagement")  # audit is step 1
        assert client.get("/api/findings/umami").json()["findings"]      # audited: step 2 open
        assert client.get("/api/findings/plane").json()["findings"] == []  # never audited: blocked


def test_agentic_tool_time_is_booked_to_the_evidence_ledger():
    """The MCP tools run in a child process, so the parent's ledger needs the time from
    the tool callbacks, or an agentic audit would report zero evidence cost."""
    import time

    from revamp.agents import diagnostics
    from revamp.llm.cache import current_ledger

    class _Tool:
        name = "audit_seo"

    ledger = CostLedger()
    token = current_ledger.set(ledger)
    run_token = observe.current_run.set("audit-test-0001")
    q = observe.bus.subscribe()
    try:
        cap = diagnostics.tool_call_cap(1)
        assert cap(_Tool(), {}, None) is None  # first call: allowed
        time.sleep(0.02)
        diagnostics.report_tool_result(_Tool(), {}, None, "3 findings")
        assert cap(_Tool(), {}, None) == {"error": "tool budget exhausted (1 calls). "
                                                   "Write your report now."}
        live = []
        while not q.empty():
            live.append(q.get_nowait())
    finally:
        current_ledger.reset(token)
        observe.current_run.reset(run_token)
        observe.bus.unsubscribe(q)
        diagnostics._STARTED.clear()
    assert ledger.evidence_seconds >= 0.02  # the child's wall time reached the parent's ledger
    assert cap.calls["n"] == 2
    assert [e["type"] for e in live] == ["tool_started", "tool_finished", "tool_refused"]
    assert observe.load_events("audit-test-0001")[0]["tool"] == "audit_seo"
