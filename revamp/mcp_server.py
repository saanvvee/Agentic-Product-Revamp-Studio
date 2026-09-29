"""MCP tool server: the audit tools and read-only evidence access (PLAN M3).

Started as a child process by the Chief Diagnostician's McpToolset:

    python -m revamp.mcp_server --product umami --role team

It is locked to ONE product and ONE knowledge-base role for its whole life. The role
is fixed at launch by the orchestrator, not chosen by the model, so a team agent
cannot ask this server for the client's private namespace: the KB handle it holds
raises AccessDenied for that namespace, and no tool exposes it anyway.

Audit tools write Findings to the KB and return a short text summary, not raw
output: a 4B model reasons better over ten lines than over a Lighthouse JSON.
"""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

from mcp.server.mcpserver import MCPServer

from revamp import evidence
from revamp.contracts import Finding
from revamp.kb import KnowledgeBase
from revamp.products import Product, load_product
from revamp.settings import settings
from revamp.tools import browser, code, lighthouse, pricing, seo, voice


def build_server(product: Product, kb: KnowledgeBase) -> MCPServer:
    server = MCPServer(
        name="revamp-audit",
        instructions=f"Audit tools for the product '{product.name}'. Every audit stores "
                     "its findings; use list_findings to read them back.")

    def base(target: str) -> str:
        if target == "local":
            if not product.local_base_url:
                raise ValueError("this product has no local instance configured")
            return product.local_base_url
        return product.live.base_url

    def summarise(label: str, found: list[Finding]) -> str:
        new = kb.add_findings(found)
        sev = Counter(f.severity for f in found)
        top = evidence.select(found, per_category=4)
        lines = [f"{label}: {len(found)} findings ({new} new). By severity: {dict(sev)}"]
        lines += [evidence.line(f) for f in top[:10]]
        return "\n".join(lines)

    @server.tool()
    async def coverage() -> str:
        """How much evidence exists per category and severity. Call this first."""
        cov = evidence.coverage(kb.findings(product.name))
        if not cov:
            return "No findings yet."
        return "\n".join(f"{c}: {s}" for c, s in cov.items())

    @server.tool()
    async def list_findings(category: str = "", min_severity: str = "low",
                            limit: int = 30) -> str:
        """List stored findings, most severe first. category: performance, accessibility,
        seo, security, code_health, user_voice, journey, pricing (empty = all)."""
        fs = kb.findings(product.name, category or None, min_severity or None)
        return evidence.render(fs, per_category=limit, skip_info=False)

    @server.tool()
    async def get_finding(finding_id: str) -> str:
        """Full detail and provenance of one finding."""
        for f in kb.findings(product.name):
            if f.id == finding_id:
                return f.model_dump_json(indent=1)
        return f"No finding {finding_id}"

    @server.tool()
    async def audit_seo(target: str = "live") -> str:
        """Cheap. Raw-HTML SEO checks on the configured pages, robots.txt, sitemap."""
        return summarise("seo", await seo.seo_audit(product.name, base(target),
                                                    product.live.pages, target))

    @server.tool()
    async def audit_pricing() -> str:
        """Cheap. Snapshot the product's pricing page and competitors' pricing pages."""
        return summarise("pricing", await pricing.pricing_snapshots(
            product.name, product.live.pricing_url, product.live.competitor_pricing))

    @server.tool()
    async def audit_user_voice() -> str:
        """Cheap. Top GitHub issues and forum topics created before the product cutoff."""
        found = await voice.github_issues(product.name, product.repo, product.cutoff)
        if product.forum:
            found += await voice.discourse_topics(product.name, product.forum.base_url,
                                                  product.cutoff)
        return summarise("user_voice", found)

    @server.tool()
    async def audit_code() -> str:
        """Expensive (minutes). Clone the audited release; size, complexity, dependency CVEs."""
        found: list[Finding] = []
        for repo in [product.repo] + product.extra_repos:
            ref = product.ref if repo == product.repo else "HEAD"
            if ref == "HEAD":
                continue  # extra repos have no pinned ref yet; skip rather than drift
            found += await code.code_audit(product.name, repo, ref, cutoff=product.cutoff)
        return summarise("code", found)

    @server.tool()
    async def audit_performance(target: str = "live") -> str:
        """Expensive. Lighthouse via PageSpeed Insights for live pages (median of 5 local
        runs when target='local')."""
        found: list[Finding] = []
        for path in product.live.pages[:3]:
            url = base(target).rstrip("/") + path
            if target == "local":
                found += await lighthouse.local_lighthouse(product.name, url,
                                                           f"local:{product.ref}")
            else:
                found += await lighthouse.psi_audit(product.name, url)
        return summarise("performance", found)

    @server.tool()
    async def audit_accessibility(target: str = "live") -> str:
        """Expensive. axe-core WCAG 2.2 AA scan of the configured pages in a real browser."""
        tgt = "live" if target == "live" else f"local:{product.ref}"
        return summarise("accessibility", await browser.axe_audit(
            product.name, base(target), product.live.pages, tgt))

    @server.tool()
    async def audit_journeys(target: str = "live") -> str:
        """Expensive. Walk each scripted user journey, screenshot every step."""
        tgt = "live" if target == "live" else f"local:{product.ref}"
        found: list[Finding] = []
        for flow in product.flows:
            f, _ = await browser.run_journey(product.name, base(target), flow.name,
                                             flow.steps, tgt)
            found += f
        return summarise("journeys", found)

    return server


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--product", required=True)
    ap.add_argument("--role", default="team", choices=["team", "evaluator"])
    ap.add_argument("--kb", default=str(settings.kb_path))
    a = ap.parse_args()
    import logging
    logging.getLogger("httpx").setLevel(logging.WARNING)
    server = build_server(load_product(a.product), KnowledgeBase(Path(a.kb), a.role))
    server.run("stdio")


if __name__ == "__main__":
    main()
