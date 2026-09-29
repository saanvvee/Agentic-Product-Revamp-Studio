"""Evidence gathering, run once per product and shared by every arm.

Two ways to fill the KB:
  * `deterministic_audit`: every tool, in a fixed order, no LLM. The G1 gate
    ("audit a product with no LLM involved") and the reproducible default for
    evaluation, because every arm must see IDENTICAL evidence.
  * `agentic_audit`: the Chief Diagnostician chooses which audits to run over MCP.
    This is the agentic version, used for demos and for measuring how much evidence
    the agent buys versus the deterministic sweep.
"""

from __future__ import annotations

import logging
import time

from revamp.contracts import CostLedger, Finding
from revamp.kb import KnowledgeBase
from revamp.llm.cache import current_ledger
from revamp.products import Product
from revamp.settings import settings
from revamp.tools import browser, code, lighthouse, pricing, seo, voice

log = logging.getLogger(__name__)
STEPS = ("seo", "pricing", "voice", "code", "performance", "accessibility", "journeys")


async def _step(name: str, p: Product, target: str) -> list[Finding]:
    base = p.live.base_url if target == "live" else p.local_base_url
    tgt = "live" if target == "live" else f"local:{p.ref}"
    if base is None:
        raise ValueError(f"no base URL for target {target}")
    if name == "seo":
        return await seo.seo_audit(p.name, base, p.live.pages, tgt)
    if name == "pricing":
        return await pricing.pricing_snapshots(p.name, p.live.pricing_url,
                                               p.live.competitor_pricing)
    if name == "voice":
        out = await voice.github_issues(p.name, p.repo, p.cutoff)
        if p.forum:
            out += await voice.discourse_topics(p.name, p.forum.base_url, p.cutoff)
        return out
    if name == "code":
        return await code.code_audit(p.name, p.repo, p.ref, cutoff=p.cutoff)
    if name == "performance":
        out = []
        for path in p.live.pages[:3]:
            url = base.rstrip("/") + path
            if target == "live":
                if not settings.psi_api_key:
                    raise RuntimeError("PSI_API_KEY not set (keyless PSI returns 429)")
                out += await lighthouse.psi_audit(p.name, url)
            else:
                out += await lighthouse.local_lighthouse(p.name, url, tgt)
        return out
    if name == "accessibility":
        return await browser.axe_audit(p.name, base, p.live.pages, tgt)
    if name == "journeys":
        out = []
        for flow in p.flows:
            f, _ = await browser.run_journey(p.name, base, flow.name, flow.steps, tgt)
            out += f
        return out
    raise KeyError(name)


async def deterministic_audit(p: Product, kb: KnowledgeBase, target: str = "live",
                              steps: tuple[str, ...] = STEPS) -> dict:
    ledger = CostLedger()
    token = current_ledger.set(ledger)
    report: dict[str, str] = {}
    try:
        for name in steps:
            t0 = time.perf_counter()
            try:
                found = await _step(name, p, target)
                new = kb.add_findings(found)
                report[name] = f"{len(found)} findings ({new} new) in {time.perf_counter() - t0:.0f}s"
            except Exception as e:  # one failing tool must not sink the audit
                report[name] = f"SKIPPED: {type(e).__name__}: {str(e)[:160]}"
                log.warning("audit step %s failed: %s", name, e)
    finally:
        current_ledger.reset(token)
    report["evidence_seconds"] = f"{ledger.evidence_seconds:.0f}"
    return report


async def agentic_audit(p: Product, max_tool_calls: int = 8, seed: int = 0,
                        mode: str | None = None) -> dict:
    """The Chief Diagnostician runs audits through the MCP server (child process)."""
    from revamp.agents.diagnostics import chief_diagnostician
    from revamp.agents.runtime import ask
    from revamp.agents.schemas import DiagnosisReport

    ledger = CostLedger()
    token = current_ledger.set(ledger)
    try:
        agent = chief_diagnostician(p.name, max_tool_calls=max_tool_calls, seed=seed, mode=mode)
        out = await ask(agent, f"Audit the product {p.name} ({p.live.base_url}, "
                               f"github.com/{p.repo} at {p.ref}).", DiagnosisReport)
    finally:
        current_ledger.reset(token)
    return {"report": out.model_dump(), "tool_calls": agent.before_tool_callback.calls["n"],
            "llm_calls": ledger.llm_calls, "llm_seconds": round(ledger.llm_seconds)}
