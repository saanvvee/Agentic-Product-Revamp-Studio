"""Pricing snapshots: fetch the product's and competitors' pricing pages as text.

The tool does not interpret prices (that is the Product & Pricing team's job). It
records what the page said, when, and where the text is stored, so every pricing
proposal can cite a real snapshot rather than the model's memory of a price list.
"""

from __future__ import annotations

import httpx

from revamp.contracts import Evidence, Finding
from revamp.tools.browser import rendered_text
from revamp.tools.common import Polite, artifacts_dir, evidence_timer, parse_html, safe_name

MAX_CHARS = 12_000
MIN_USEFUL_CHARS = 300  # below this the page is client-rendered; try a real browser


async def pricing_snapshots(product: str, own_url: str | None,
                            competitors: dict[str, str],
                            http: Polite | None = None) -> list[Finding]:
    own = http is None
    http = http or Polite()
    targets = ([("self", own_url)] if own_url else []) + sorted(competitors.items())
    out: list[Finding] = []
    try:
        with evidence_timer():
            for name, url in targets:
                ev_base = dict(tool="pricing_snapshot", target="live", locator=url)
                try:
                    r = await http.get(url)
                    r.raise_for_status()
                except (httpx.HTTPError, PermissionError) as e:
                    out.append(Finding.make(
                        product=product, category="pricing", severity="info",
                        title=f"Pricing page unavailable: {name} ({type(e).__name__})",
                        evidence=Evidence(**ev_base)))
                    continue
                text = parse_html(r.text).text
                how = "raw_html"
                if len(text) < MIN_USEFUL_CHARS:
                    rendered = await rendered_text(url)
                    if rendered:
                        text, how = rendered, "rendered"
                text = " ".join(text.split())[:MAX_CHARS]
                path = artifacts_dir(product, "pricing") / f"{safe_name(name)}.txt"
                path.write_text(f"SOURCE: {url}\n\n{text}", encoding="utf-8")
                who = "own" if name == "self" else "competitor"
                out.append(Finding.make(
                    product=product, category="pricing", severity="info",
                    title=f"Pricing snapshot: {name} ({who})",
                    detail=text[:500], metric="pricing_text_chars", value=len(text),
                    evidence=Evidence(**ev_base, artifact_path=str(path)),
                    tags=(who, name, how)))
    finally:
        if own:
            await http.client.aclose()
    return out
