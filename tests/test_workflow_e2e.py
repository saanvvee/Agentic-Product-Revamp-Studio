"""End-to-end workflow runs with scripted models: no network, no Ollama, no Gemini.

These test the ORCHESTRATION (routing, loop caps, provenance, veto, arms), not model
quality. Each scripted responder answers like a plausible agent would.
"""

import json

import pytest

from revamp.contracts import ClientConstraint, Evidence, Finding
from revamp.kb import KnowledgeBase
from revamp.llm.stub import ScriptedLlm, last_user_text
from revamp.workflow.runner import run_engagement

PRODUCT = "umami"


def _finding(title, cat, sev):
    return Finding.make(product=PRODUCT, category=cat, title=title, severity=sev,
                        evidence=Evidence(tool="test", target="live", locator=f"https://x/{title}"))


F_PERF = _finding("LCP 5.2 s", "performance", "high")
F_A11Y = _finding("Low contrast", "accessibility", "high")
F_VOICE = _finding("Please add OIDC login", "user_voice", "high")
F_PRICE = _finding("Pricing snapshot: self", "pricing", "info")


@pytest.fixture
def kb_path(tmp_path):
    path = tmp_path / "kb.sqlite3"
    KnowledgeBase(path, "team").add_findings([F_PERF, F_A11Y, F_VOICE, F_PRICE])
    KnowledgeBase(path, "client").set_constraints(PRODUCT, [ClientConstraint(
        id="K1", product=PRODUCT, kind="forbid_area", param="pricing_page",
        reason_code="brand", description="Board has frozen pricing until next year",
        public_hint="We are not touching pricing this year.")])
    return path


def J(obj):
    return json.dumps(obj)


def scripted(counter=None):
    counter = counter if counter is not None else {}

    def bump(k):
        counter[k] = counter.get(k, 0) + 1
        return counter[k]

    def design(req):
        n = bump("design")
        cost = 3 if n == 1 else 6  # second round: re-estimated after handoff rejection
        return J({"proposals": [
            {"ref": "D1", "title": "Fix contrast", "change": "raise contrast", "rationale": "a11y",
             "finding_ids": [F_A11Y.id], "cost_days": cost, "value": 7, "areas": ["accessibility"]},
            {"ref": "D2", "title": "Invented", "change": "x", "rationale": "x",
             "finding_ids": ["F-madeup0000"], "cost_days": 1, "value": 9, "areas": ["navigation"]},
        ]})

    responders = {
        "engagement_lead": lambda r: J({"focus": ["performance", "accessibility"],
                                        "rationale": "worst evidence"}),
        "voice_of_customer": lambda r: J({"themes": [
            {"theme": "SSO", "is_signal": True, "finding_ids": [F_VOICE.id], "why": "many"}]}),
        "journey_auditor": lambda r: J({"issues": []}),
        "design": design,
        "engineering": lambda r: J({"proposals": [
            {"ref": "E1", "title": "Code-split bundle", "change": "split", "rationale": "LCP",
             "finding_ids": [F_PERF.id], "cost_days": 8, "value": 8, "areas": ["performance"]},
            {"ref": "E2", "title": "Add OIDC", "change": "oidc", "rationale": "users ask",
             "finding_ids": [F_VOICE.id], "cost_days": 15, "value": 6, "areas": ["auth"],
             "depends_on": ["E1"]}]}),
        "product_pricing": lambda r: J({"proposals": [
            {"ref": "PP1", "title": "New pricing tiers", "change": "tiers", "rationale": "comp",
             "finding_ids": [F_PRICE.id], "cost_days": 4, "value": 5,
             "areas": ["pricing_page"]}]}),
        # Rejects the design proposal the first time it sees it, accepts the rest.
        "handoff_reviewer": lambda r: J({"decisions": [
            {"proposal_id": "DE1-1", "decision": "reject", "reason": "underestimated",
             "realistic_cost_days": 6}] if "DE1-1" in last_user_text(r) else []}),
        "conflict_detector": lambda r: J({"conflicts": []}),
        "red_team": lambda r: J({"objections": [
            {"proposal_id": "EN1-2", "issue": "OIDC is not a revamp priority", "action": "block"}]
            if "EN1-2" in last_user_text(r) else []}),
        "client": lambda r: J({"message": "noted"}),
        "engagement_adapter": lambda r: J({"drop": [], "reasoning": "pricing is off-limits"}),
        "single_llm": lambda r: J({"summary": "plan", "items": [
            {"title": "Fix perf", "change": "c", "finding_ids": [F_PERF.id], "cost_days": 10,
             "value": 8, "areas": ["performance"], "order": 1},
            {"title": "Reprice", "change": "c", "finding_ids": [F_PRICE.id], "cost_days": 4,
             "value": 5, "areas": ["pricing_page"], "order": 2}]}),
    }
    return {k: ScriptedLlm(responder=v) for k, v in responders.items()}, counter


async def test_full_arm_runs_every_mechanism(kb_path):
    overrides, counter = scripted()
    res = await run_engagement(PRODUCT, "A2", kb_path=kb_path, overrides=overrides)
    log = "\n".join(res.log)

    assert res.record.status == "done"
    # Handoff rejection sent Design back once; it re-proposed.
    assert counter["design"] == 2 and res.record.handoff_rejections == 1
    # Provenance: the invented citation was dropped, not planned.
    assert res.stats["unsupported_dropped"] >= 1
    assert all(i.proposal_id != "DE1-2" for i in res.plan.items)
    # Red Team blocked OIDC once.
    assert res.record.red_team_rounds == 1
    assert "EN1-2" not in {i.proposal_id for i in res.plan.items}
    # Client vetoed pricing, then accepted the adapted plan.
    assert res.record.client_rounds == 2
    assert "PP1-1" not in {i.proposal_id for i in res.plan.items}
    assert "client round 2: accept" in log
    # Budget respected and every item cites a real finding.
    assert res.plan.total_cost <= res.plan.budget_days


async def test_team_never_sees_private_constraint_in_normal_arms(kb_path):
    seen = []
    overrides, _ = scripted()
    orig = overrides["design"].responder
    overrides["design"].responder = lambda r: (seen.append(last_user_text(r)), orig(r))[1]
    await run_engagement(PRODUCT, "A2", kb_path=kb_path, overrides=overrides)
    assert seen and not any("frozen pricing" in s for s in seen)


async def test_a6_shows_constraint_to_teams(kb_path):
    seen = []
    overrides, _ = scripted()
    orig = overrides["design"].responder
    overrides["design"].responder = lambda r: (seen.append(last_user_text(r)), orig(r))[1]
    await run_engagement(PRODUCT, "A6", kb_path=kb_path, overrides=overrides)
    assert any("frozen pricing" in s for s in seen)


async def test_a1_keeps_everything_and_does_not_loop(kb_path):
    overrides, counter = scripted()
    res = await run_engagement(PRODUCT, "A1", kb_path=kb_path, overrides=overrides)
    assert counter["design"] == 1 and res.record.client_rounds == 1
    assert "PP1-1" in {i.proposal_id for i in res.plan.items}  # no arbitration, no veto loop


async def test_a0_single_llm(kb_path):
    overrides, _ = scripted()
    res = await run_engagement(PRODUCT, "A0", kb_path=kb_path, overrides=overrides)
    assert [i.proposal_id for i in res.plan.items] == ["SL0-1", "SL0-2"]
    assert res.record.client_rounds == 1


async def test_client_loop_is_capped(kb_path):
    """The client keeps rejecting (adapter never drops the offending item and the
    veto is re-proposed each round); the loop must still stop at CLIENT_CAP."""
    overrides, _ = scripted()
    # Make every team propose a pricing change so a veto always remains.
    overrides["engagement_adapter"].responder = lambda r: J({
        "drop": [], "request": "pricing", "team": "product_pricing", "reasoning": "x"})
    res = await run_engagement(PRODUCT, "A2", kb_path=kb_path, overrides=overrides)
    from revamp.workflow.arms import CLIENT_CAP
    assert res.record.client_rounds <= CLIENT_CAP


async def test_human_approval_pauses_and_blocks_rejected_items(kb_path):
    """HITL: E1 costs 8d of a 60d budget (not high impact); make it high risk so the
    approval node must pause. The human rejects it; it must leave the plan."""
    overrides, _ = scripted()
    orig = overrides["engineering"].responder

    def risky(req):
        data = json.loads(orig(req))
        data["proposals"][0]["risk"] = "high"
        return json.dumps(data)

    overrides["engineering"].responder = risky
    asked = []

    def approver(pending):
        asked.append(pending)
        return {"rejected": ["EN1-1"]}

    res = await run_engagement(PRODUCT, "A2", kb_path=kb_path, overrides=overrides,
                               approver=approver)
    assert len(asked) == 1 and asked[0]["items"][0]["id"] == "EN1-1"
    assert "EN1-1" not in {i.proposal_id for i in res.plan.items}
    assert res.record.status == "done"
