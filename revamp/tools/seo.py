"""SEO checks on raw HTML, plus robots.txt and sitemap presence.

Deliberately simple and explainable: each check is one line of logic against a
published guideline. It reads server HTML only (no JavaScript), so on a client-
rendered page it can under-report; every finding says it is a raw-HTML check.
"""

from __future__ import annotations

import httpx

from revamp.contracts import Evidence, Finding
from revamp.tools.common import Polite, artifacts_dir, evidence_timer, join, parse_html, safe_name


def check_page(product: str, url: str, html: str, target: str,
               artifact: str | None = None) -> list[Finding]:
    f = parse_html(html)
    ev = Evidence(tool="seo_html", target=target, locator=url, artifact_path=artifact)
    out: list[Finding] = []

    def add(title, severity, detail, metric=None, value=None):
        out.append(Finding.make(product=product, category="seo", evidence=ev,
                                title=f"{title} ({url})", severity=severity, detail=detail,
                                metric=metric, value=value, tags=("raw_html",)))

    if not f.title:
        add("Missing <title>", "high", "No title element in server HTML.", "title_length", 0)
    elif not 15 <= len(f.title) <= 65:
        add("Title length outside 15-65 chars", "low", f"Title: {f.title!r}",
            "title_length", len(f.title))
    desc = f.meta.get("description", "")
    if not desc:
        add("Missing meta description", "medium", "No <meta name=description>.",
            "meta_description_length", 0)
    elif not 50 <= len(desc) <= 170:
        add("Meta description length outside 50-170 chars", "low", desc[:200],
            "meta_description_length", len(desc))
    if len(f.h1) != 1:
        add(f"{len(f.h1)} <h1> elements (expected 1)", "low", "; ".join(f.h1)[:300],
            "h1_count", len(f.h1))
    if not f.lang:
        add("Missing <html lang>", "medium", "Screen readers and search engines use it.")
    if not f.canonical:
        add("Missing canonical link", "low", "No <link rel=canonical>.")
    if "noindex" in f.meta.get("robots", "").lower():
        add("Page is noindex", "high", f"meta robots: {f.meta['robots']}")
    if "viewport" not in f.meta:
        add("Missing viewport meta", "medium", "Page will not scale on mobile.")
    if not f.meta.get("og:title"):
        add("Missing Open Graph title", "low", "Link previews on social sites degrade.")
    if f.img_no_alt:
        add(f"{f.img_no_alt}/{f.img_total} images without alt", "medium",
            "Images without an alt attribute.", "img_missing_alt", f.img_no_alt)
    words = len(f.text.split())
    if words < 150:
        add(f"Thin server-rendered content ({words} words)", "low",
            "Little text in raw HTML; content may be client-rendered.", "word_count", words)
    return out


async def seo_audit(product: str, base_url: str, pages: list[str], target: str = "live",
                    http: Polite | None = None) -> list[Finding]:
    own = http is None
    http = http or Polite()
    out: list[Finding] = []
    try:
        with evidence_timer():
            for path in pages:
                url = join(base_url, path)
                try:
                    r = await http.get(url)
                except PermissionError as e:
                    out.append(Finding.make(
                        product=product, category="seo", title=f"Skipped: {e}",
                        severity="info", evidence=Evidence(tool="seo_html", target=target,
                                                           locator=url)))
                    continue
                except httpx.HTTPError as e:
                    out.append(Finding.make(
                        product=product, category="seo", title=f"Fetch failed: {type(e).__name__}",
                        severity="medium", evidence=Evidence(tool="seo_html", target=target,
                                                             locator=url)))
                    continue
                if r.status_code >= 400:
                    out.append(Finding.make(
                        product=product, category="seo", title=f"HTTP {r.status_code} on {url}",
                        severity="high", evidence=Evidence(tool="seo_html", target=target,
                                                           locator=url)))
                    continue
                art = artifacts_dir(product, "html") / f"{safe_name(url)}.html"
                art.write_text(r.text, encoding="utf-8")
                out += check_page(product, str(r.url), r.text, target, str(art))

            for name, path in (("robots.txt", "/robots.txt"), ("sitemap.xml", "/sitemap.xml")):
                url = join(base_url, path)
                try:
                    r = await http.get(url, check_robots=False)
                    ok = r.status_code == 200 and len(r.text) > 0
                except httpx.HTTPError:
                    ok = False
                if not ok:
                    out.append(Finding.make(
                        product=product, category="seo", title=f"No {name} at {url}",
                        severity="low" if name == "robots.txt" else "medium",
                        evidence=Evidence(tool="seo_html", target=target, locator=url)))
    finally:
        if own:
            await http.client.aclose()
    return out
