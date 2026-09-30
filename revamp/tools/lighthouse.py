"""Lighthouse: parse a Lighthouse result (LHR) into Findings; run PSI or local CLI.

Two sources, one parser:
  * PageSpeed Insights API: Lighthouse on Google's servers. Primary for live sites
    (PLAN D3) because it puts no load on the target from our side and it also
    returns CrUX field data (real Chrome users) when the origin has enough traffic.
  * Local Lighthouse CLI (npx lighthouse@13.5.0): for local Docker instances, where
    PSI cannot reach. Lighthouse varies run to run, so we take the median of N runs.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import statistics
from typing import Any

from revamp.contracts import Evidence, Finding
from revamp.settings import settings
from revamp.tools.common import Polite, artifacts_dir, evidence_timer, safe_name, save_json

LIGHTHOUSE_VERSION = "13.5.0"
PSI_ENDPOINT = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"

# (audit id, label, unit, good_max, poor_min). Thresholds: web.dev Core Web Vitals
# and Lighthouse's own metric scoring bands.
METRICS = [
    ("largest-contentful-paint", "LCP", "ms", 2500, 4000),
    ("cumulative-layout-shift", "CLS", "", 0.1, 0.25),
    ("total-blocking-time", "TBT", "ms", 200, 600),
    ("first-contentful-paint", "FCP", "ms", 1800, 3000),
    ("speed-index", "SI", "ms", 3400, 5800),
]
CATEGORY_MAP = {
    "performance": "performance",
    "accessibility": "accessibility",
    "seo": "seo",
    "best-practices": "code_health",
}


def _band(value: float, good: float, poor: float) -> str:
    if value <= good:
        return "info"
    return "high" if value > poor else "medium"


def parse_lhr(lhr: dict[str, Any], *, product: str, tool: str, target: str,
              url: str, artifact: str | None = None) -> list[Finding]:
    audits = lhr.get("audits", {})
    ev = Evidence(tool=tool, tool_version=lhr.get("lighthouseVersion", ""),
                  target=target, locator=url, artifact_path=artifact)
    out: list[Finding] = []

    for aid, label, unit, good, poor in METRICS:
        a = audits.get(aid)
        if not a or a.get("numericValue") is None:
            continue
        v = float(a["numericValue"])
        out.append(Finding.make(
            product=product, category="performance", evidence=ev,
            title=f"{label} {a.get('displayValue', round(v, 2))} on {url}",
            severity=_band(v, good, poor), metric=label, value=round(v, 3), unit=unit,
            detail=f"Lab value, Lighthouse {label}. Good <= {good}{unit}, poor > {poor}{unit}.",
            tags=("lab",)))

    metric_ids = {m[0] for m in METRICS}
    for cat_id, cat in lhr.get("categories", {}).items():
        category = CATEGORY_MAP.get(cat_id)
        if category is None:
            continue
        score = cat.get("score")
        if score is not None:
            out.append(Finding.make(
                product=product, category=category, evidence=ev,
                title=f"Lighthouse {cat.get('title', cat_id)} score {round(score * 100)} on {url}",
                severity="info" if score >= 0.9 else "medium" if score >= 0.5 else "high",
                metric=f"lh_{cat_id}_score", value=round(score * 100), unit="/100"))
        for ref in cat.get("auditRefs", []):
            aid, weight = ref.get("id"), ref.get("weight", 0)
            a = audits.get(aid, {})
            s = a.get("score")
            if aid in metric_ids or s is None or s >= 0.9 or \
                    a.get("scoreDisplayMode") in {"manual", "notApplicable", "informative"}:
                continue
            n_items = len((a.get("details") or {}).get("items", []) or [])
            sev = "high" if s < 0.5 and weight >= 3 else "medium" if s < 0.5 else "low"
            out.append(Finding.make(
                product=product, category=category, evidence=ev,
                title=f"{a.get('title', aid)} ({url})",
                severity=sev, metric=aid, value=n_items or None, unit="items" if n_items else None,
                detail=(a.get("displayValue", "") + " " + (a.get("description") or ""))[:600].strip(),
                tags=("lab", cat_id)))
    return out


def parse_crux(field: dict[str, Any], *, product: str, url: str, scope: str) -> list[Finding]:
    """PSI's loadingExperience / originLoadingExperience block (CrUX, 28-day p75)."""
    out = []
    ev = Evidence(tool="crux", target="live", locator=url)
    for key, m in (field.get("metrics") or {}).items():
        cat = m.get("category")  # FAST | AVERAGE | SLOW
        sev = {"FAST": "info", "AVERAGE": "medium", "SLOW": "high"}.get(cat, "info")
        out.append(Finding.make(
            product=product, category="performance", evidence=ev,
            title=f"Real-user {key} p75={m.get('percentile')} ({cat}, {scope})",
            severity=sev, metric=key, value=m.get("percentile"),
            detail="Chrome UX Report field data, 28-day rolling p75.", tags=("field", scope)))
    return out


async def psi_audit(product: str, url: str, strategy: str = "mobile",
                    http: Polite | None = None) -> list[Finding]:
    params = [("url", url), ("strategy", strategy)] + [
        ("category", c) for c in ("PERFORMANCE", "ACCESSIBILITY", "SEO", "BEST_PRACTICES")]
    if settings.psi_api_key:
        params.append(("key", settings.psi_api_key))
    own = http is None
    http = http or Polite(interval=1.0, timeout=120)
    try:
        with evidence_timer():
            # PSI is Google's API, not the target site: robots.txt of the target
            # does not apply to it, and Google fetches the page itself.
            r = await http.get(PSI_ENDPOINT, params=params, check_robots=False)
        r.raise_for_status()
        data = r.json()
    finally:
        if own:
            await http.client.aclose()
    art = save_json(artifacts_dir(product, "psi") / f"{safe_name(url)}.{strategy}.json", data)
    out = parse_lhr(data.get("lighthouseResult", {}), product=product, tool="psi",
                    target="live", url=url, artifact=art)
    if data.get("loadingExperience", {}).get("metrics"):
        out += parse_crux(data["loadingExperience"], product=product, url=url, scope="url")
    elif data.get("originLoadingExperience", {}).get("metrics"):
        out += parse_crux(data["originLoadingExperience"], product=product, url=url,
                          scope="origin")
    return out


def _chrome_env() -> dict[str, str]:
    """chrome-launcher finds Chrome through PROGRAMFILES/LOCALAPPDATA, which an MCP
    stdio child does not get by default. Point it at a browser explicitly."""
    import os
    from pathlib import Path
    env = dict(os.environ)
    if "CHROME_PATH" not in env:
        for cand in (r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                     r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                     r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                     "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                     "/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser"):
            if Path(cand).is_file():
                env["CHROME_PATH"] = cand
                break
    return env


async def _run_cli_once(url: str) -> dict[str, Any]:
    npx = shutil.which("npx")  # npx.cmd on Windows
    if npx is None:
        raise RuntimeError("npx not found: install Node 22")
    proc = await asyncio.create_subprocess_exec(
        npx, "--yes", f"lighthouse@{LIGHTHOUSE_VERSION}", url,
        "--output=json", "--output-path=stdout", "--quiet",
        "--only-categories=performance,accessibility,seo,best-practices",
        "--chrome-flags=--headless=new",
        # DEVNULL: inside the MCP server, stdin is the JSON-RPC pipe; a child must not inherit it.
        stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE, env=_chrome_env())
    out, err = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"lighthouse failed ({proc.returncode}): {err.decode(errors='replace')[:500]}")
    return json.loads(out)


async def local_lighthouse(product: str, url: str, target: str, runs: int = 5) -> list[Finding]:
    """Median-of-N by performance score (Lighthouse docs: 5 runs roughly halves
    variance). Runs are sequential: parallel runs on one CPU distort each other."""
    lhrs = []
    with evidence_timer():
        for _ in range(runs):
            lhrs.append(await _run_cli_once(url))
    perf = [(l.get("categories", {}).get("performance", {}).get("score") or 0) for l in lhrs]
    median_score = statistics.median_low(perf)
    lhr = lhrs[perf.index(median_score)]
    art = save_json(artifacts_dir(product, "lighthouse") / f"{safe_name(url)}.json", lhr)
    found = parse_lhr(lhr, product=product, tool="lighthouse", target=target, url=url,
                      artifact=art)
    spread = (max(perf) - min(perf)) * 100
    found.append(Finding.make(
        product=product, category="performance",
        evidence=Evidence(tool="lighthouse", tool_version=LIGHTHOUSE_VERSION, target=target,
                          locator=url, artifact_path=art),
        title=f"Lighthouse run-to-run spread {spread:.0f} points over {runs} runs ({url})",
        severity="info", metric="lh_perf_spread", value=round(spread, 1), unit="points",
        detail="Measurement noise. Differences smaller than this are not evidence."))
    return found


async def performance_audit(product: str, base_url: str, pages: list[str],
                            target: str) -> list[Finding]:
    """Live pages: PSI if a key is set (Google runs Lighthouse, returns CrUX field
    data too). Without a key, or for a local instance: the Lighthouse CLI on this
    machine, median of 3 runs on the first 2 pages (about 100 s per run on this CPU)."""
    out: list[Finding] = []
    if target == "live" and settings.psi_api_key:
        for path in pages[:3]:
            out += await psi_audit(product, base_url.rstrip("/") + path)
        return out
    for path in pages[:2]:
        out += await local_lighthouse(product, base_url.rstrip("/") + path, target, runs=3)
    return out
