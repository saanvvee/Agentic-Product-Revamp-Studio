"""Browser evidence: axe-core accessibility scans, scripted journeys, rendered page text.

The browser itself is driven by a small Node worker (browser_worker/worker.mjs) using
Playwright for Node and axe-core from npm. Python's playwright package is a wrapper
around that same Node driver, and it cannot be installed on the campus network
(PyPI is TLS-intercepted) while npm works. So we call the driver directly: one JSON
job on stdin, one JSON result on stdout.

Journeys produce two kinds of output: Findings for measurable breakage (HTTP errors,
console errors, failed requests, slow loads) and screenshots, which the Journey
Auditor agent looks at with a vision model. The screenshot is the second modality.
"""

from __future__ import annotations

import asyncio
import json
import shutil

from revamp.contracts import Evidence, Finding
from revamp.settings import settings
from revamp.tools.common import artifacts_dir, evidence_timer, join, safe_name, save_json

AXE_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]
IMPACT = {"minor": "low", "moderate": "medium", "serious": "high", "critical": "critical"}
WORKER = settings.root / "browser_worker" / "worker.mjs"


class BrowserUnavailable(RuntimeError):
    pass


async def run_worker(job: dict, timeout: float = 600) -> object:
    node = shutil.which("node")
    if node is None:
        raise BrowserUnavailable("node not found: install Node 22")
    if not (WORKER.parent / "node_modules" / "playwright").is_dir():
        raise BrowserUnavailable("run `npm install` and `npx playwright install chromium` "
                                 "in browser_worker/ (scripts/fetch_binaries.ps1 does both)")
    proc = await asyncio.create_subprocess_exec(
        node, str(WORKER), stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE, cwd=str(WORKER.parent))
    out, err = await asyncio.wait_for(proc.communicate(json.dumps(job).encode()), timeout)
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        raise BrowserUnavailable(f"worker failed: {err.decode(errors='replace')[-400:]}")
    if isinstance(data, dict) and "error" in data:
        raise BrowserUnavailable(data["error"])
    return data


def parse_axe(result: dict, *, product: str, url: str, target: str,
              artifact: str | None) -> list[Finding]:
    version = (result.get("testEngine") or {}).get("version", "")
    out = []
    for v in result.get("violations", []):
        nodes = v.get("nodes", [])
        example = (nodes[0].get("target") if nodes else None) or []
        wcag = tuple(t for t in v.get("tags", []) if t.startswith("wcag"))
        out.append(Finding.make(
            product=product, category="accessibility",
            severity=IMPACT.get(v.get("impact") or "", "medium"),
            title=f"{v.get('help', v.get('id'))} ({url})",
            detail=f"{v.get('description', '')} e.g. {example}. {v.get('helpUrl', '')}"[:600],
            metric=v.get("id"), value=len(nodes), unit="elements",
            evidence=Evidence(tool="axe-core", tool_version=version, target=target,
                              locator=url, artifact_path=artifact),
            tags=wcag))
    return out


async def axe_audit(product: str, base_url: str, pages: list[str],
                    target: str = "live") -> list[Finding]:
    urls = [join(base_url, p) for p in pages]
    with evidence_timer():
        results = await run_worker({"op": "axe", "urls": urls, "tags": AXE_TAGS})
    out: list[Finding] = []
    for r in results:
        art = save_json(artifacts_dir(product, "axe") / f"{safe_name(r['url'])}.json",
                        r["result"])
        out += parse_axe(r["result"], product=product, url=r["url"], target=target,
                         artifact=art)
    return out


def journey_findings(product: str, flow_name: str, steps: list[dict],
                     target: str) -> list[Finding]:
    findings: list[Finding] = []
    for i, s in enumerate(steps, 1):
        url = s["url"]
        ev = Evidence(tool="playwright_journey", target=target, locator=url,
                      artifact_path=s.get("screenshot"))
        step = f"step {i} of flow '{flow_name}'"
        status = s.get("status", 0)
        if status >= 400 or status == 0:
            findings.append(Finding.make(
                product=product, category="journey", severity="high", evidence=ev,
                title=f"HTTP {status} at {step} ({url})", metric="http_status", value=status,
                detail=s.get("error") or ""))
        if s.get("consoleErrors"):
            findings.append(Finding.make(
                product=product, category="journey", severity="medium", evidence=ev,
                title=f"{len(s['consoleErrors'])} console errors at {step} ({url})",
                detail=" | ".join(s["consoleErrors"][:5])[:600],
                metric="console_errors", value=len(s["consoleErrors"])))
        if s.get("failedRequests"):
            findings.append(Finding.make(
                product=product, category="journey", severity="low", evidence=ev,
                title=f"{len(s['failedRequests'])} failed requests at {step} ({url})",
                detail=" | ".join(s["failedRequests"][:5])[:600], metric="failed_requests",
                value=len(s["failedRequests"])))
        load_ms = s.get("loadMs", 0)
        findings.append(Finding.make(
            product=product, category="journey", evidence=ev,
            severity="medium" if load_ms > 5000 else "info",
            title=f"Load {load_ms} ms at {step} ({url})",
            metric="load_event_ms", value=load_ms, unit="ms",
            detail="Wall-clock to the load event from this machine; noisy, lab only.",
            tags=("screenshot",)))
    return findings


async def run_journey(product: str, base_url: str, flow_name: str, steps: list[str],
                      target: str = "live") -> tuple[list[Finding], list[str]]:
    """Returns (findings, screenshot paths). Screenshots go to the Journey Auditor."""
    shot_dir = artifacts_dir(product, f"journey/{flow_name}")
    with evidence_timer():
        results = await run_worker({"op": "journey", "shotDir": str(shot_dir),
                                    "urls": [join(base_url, p) for p in steps]})
    return (journey_findings(product, flow_name, results, target),
            [r["screenshot"] for r in results])


async def rendered_text(url: str) -> str | None:
    """Page text after JavaScript runs; None if the browser worker is unavailable."""
    try:
        return (await run_worker({"op": "text", "url": url}, timeout=120))["text"]
    except BrowserUnavailable:
        return None
