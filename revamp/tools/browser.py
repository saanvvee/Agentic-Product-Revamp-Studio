"""Browser evidence with Playwright: axe-core accessibility scans and scripted journeys.

axe-core is injected from tools/bin/axe.min.js (scripts/fetch_binaries.ps1) rather
than through a Python wrapper: one fewer dependency, and the exact axe version is
visible in every Finding.

Journeys produce two kinds of output: Findings for measurable breakage (HTTP errors,
console errors, failed requests, slow loads) and screenshots, which the Journey
Auditor agent looks at with a vision model. The screenshot is the second modality.
"""

from __future__ import annotations

import time

from revamp.contracts import Evidence, Finding
from revamp.settings import settings
from revamp.tools.common import artifacts_dir, evidence_timer, join, safe_name, save_json

AXE_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]
IMPACT = {"minor": "low", "moderate": "medium", "serious": "high", "critical": "critical"}
VIEWPORT = {"width": 1280, "height": 800}


def _axe_js() -> str:
    path = settings.tools_bin / "axe.min.js"
    if not path.is_file():
        raise FileNotFoundError("tools/bin/axe.min.js missing; run scripts/fetch_binaries.ps1")
    return path.read_text(encoding="utf-8")


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


async def _browser():
    from playwright.async_api import async_playwright  # imported lazily: optional dep
    pw = await async_playwright().start()
    browser = await pw.chromium.launch(headless=True)
    return pw, browser


async def axe_audit(product: str, base_url: str, pages: list[str],
                    target: str = "live") -> list[Finding]:
    js = _axe_js()
    out: list[Finding] = []
    with evidence_timer():
        pw, browser = await _browser()
        try:
            ctx = await browser.new_context(viewport=VIEWPORT)
            page = await ctx.new_page()
            for path in pages:
                url = join(base_url, path)
                await page.goto(url, wait_until="load", timeout=60_000)
                await page.add_script_tag(content=js)
                result = await page.evaluate(
                    "tags => axe.run(document, {runOnly: {type: 'tag', values: tags}})",
                    AXE_TAGS)
                art = save_json(artifacts_dir(product, "axe") / f"{safe_name(url)}.json", result)
                out += parse_axe(result, product=product, url=url, target=target, artifact=art)
        finally:
            await browser.close()
            await pw.stop()
    return out


async def run_journey(product: str, base_url: str, flow_name: str, steps: list[str],
                      target: str = "live") -> tuple[list[Finding], list[str]]:
    """Returns (findings, screenshot paths). Screenshots go to the Journey Auditor."""
    findings: list[Finding] = []
    shots: list[str] = []
    shot_dir = artifacts_dir(product, f"journey/{flow_name}")
    with evidence_timer():
        pw, browser = await _browser()
        try:
            ctx = await browser.new_context(viewport=VIEWPORT)
            page = await ctx.new_page()
            console_errors: list[str] = []
            failed: list[str] = []
            page.on("console", lambda m: console_errors.append(m.text)
                    if m.type == "error" else None)
            page.on("requestfailed", lambda r: failed.append(r.url))
            for i, path in enumerate(steps, 1):
                url = join(base_url, path)
                console_errors.clear()
                failed.clear()
                t0 = time.perf_counter()
                resp = await page.goto(url, wait_until="load", timeout=60_000)
                load_ms = (time.perf_counter() - t0) * 1000
                shot = shot_dir / f"{i:02d}_{safe_name(path)}.png"
                await page.screenshot(path=str(shot), full_page=True)
                shots.append(str(shot))
                ev = Evidence(tool="playwright_journey", target=target, locator=url,
                              artifact_path=str(shot))
                step = f"step {i} of flow '{flow_name}'"
                status = resp.status if resp else 0
                if status >= 400 or status == 0:
                    findings.append(Finding.make(
                        product=product, category="journey", severity="high", evidence=ev,
                        title=f"HTTP {status} at {step} ({url})", metric="http_status",
                        value=status))
                if console_errors:
                    findings.append(Finding.make(
                        product=product, category="journey", severity="medium", evidence=ev,
                        title=f"{len(console_errors)} console errors at {step} ({url})",
                        detail=" | ".join(console_errors[:5])[:600],
                        metric="console_errors", value=len(console_errors)))
                if failed:
                    findings.append(Finding.make(
                        product=product, category="journey", severity="low", evidence=ev,
                        title=f"{len(failed)} failed requests at {step} ({url})",
                        detail=" | ".join(failed[:5])[:600], metric="failed_requests",
                        value=len(failed)))
                findings.append(Finding.make(
                    product=product, category="journey", evidence=ev,
                    severity="medium" if load_ms > 5000 else "info",
                    title=f"Load {load_ms:.0f} ms at {step} ({url})",
                    metric="load_event_ms", value=round(load_ms), unit="ms",
                    detail="Wall-clock to the load event from this machine; noisy, lab only.",
                    tags=("screenshot",)))
        finally:
            await browser.close()
            await pw.stop()
    return findings, shots
