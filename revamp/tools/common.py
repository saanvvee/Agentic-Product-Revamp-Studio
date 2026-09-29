"""Shared plumbing for tool runners: evidence-cost timing, polite HTTP, HTML parsing."""

from __future__ import annotations

import asyncio
import contextlib
import json
import re
import time
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx

from revamp.llm.cache import current_ledger
from revamp.settings import settings

USER_AGENT = ("RevampStudio/0.1 (university course project; "
              "+https://github.com/goyalaakarsh/ai-prj)")


@contextlib.contextmanager
def evidence_timer():
    """Invariant 9: wall time spent measuring is booked to the evidence ledger,
    separately from LLM (orchestration) time."""
    started = time.perf_counter()
    try:
        yield
    finally:
        ledger = current_ledger.get()
        if ledger is not None:
            ledger.evidence_seconds += time.perf_counter() - started


def artifacts_dir(product: str, kind: str) -> Path:
    d = settings.runs_dir / "artifacts" / product / kind
    d.mkdir(parents=True, exist_ok=True)
    return d


def safe_name(url_or_path: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", url_or_path).strip("_")[:120] or "root"


def save_json(path: Path, data) -> str:
    path.write_text(json.dumps(data, indent=1), encoding="utf-8")
    return str(path.relative_to(settings.root)) if path.is_relative_to(settings.root) else str(path)


# ------------------------------------------------------------------ polite HTTP

class Polite:
    """One HTTP client that waits at least `interval` seconds between requests to
    the same host and honours robots.txt (invariant 10).

    TLS: httpx verifies certificates. On a network that intercepts TLS, point
    SSL_CERT_FILE at that network's CA bundle; never disable verification.
    """

    def __init__(self, interval: float = 1.0, timeout: float = 30.0):
        self.interval = interval
        self._last: dict[str, float] = {}
        self._robots: dict[str, RobotFileParser | None] = {}
        self._lock = asyncio.Lock()
        self.client = httpx.AsyncClient(headers={"User-Agent": USER_AGENT},
                                        timeout=timeout, follow_redirects=True)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        await self.client.aclose()

    async def _wait_turn(self, host: str) -> None:
        async with self._lock:
            gap = time.monotonic() - self._last.get(host, 0.0)
            if gap < self.interval:
                await asyncio.sleep(self.interval - gap)
            self._last[host] = time.monotonic()

    async def allowed(self, url: str) -> bool:
        parts = urlparse(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in self._robots:
            rp = RobotFileParser()
            try:
                await self._wait_turn(parts.netloc)
                r = await self.client.get(origin + "/robots.txt")
                rp.parse(r.text.splitlines() if r.status_code == 200 else [])
            except httpx.HTTPError:
                rp.parse([])
            self._robots[origin] = rp
        return self._robots[origin].can_fetch(USER_AGENT, url)

    async def get(self, url: str, *, check_robots: bool = True, **kw) -> httpx.Response:
        if check_robots and not await self.allowed(url):
            raise PermissionError(f"robots.txt disallows {url}")
        await self._wait_turn(urlparse(url).netloc)
        return await self.client.get(url, **kw)


def join(base: str, path: str) -> str:
    return urljoin(base.rstrip("/") + "/", path.lstrip("/"))


# ------------------------------------------------------------------ HTML parsing

class PageFacts(HTMLParser):
    """Just enough HTML parsing for SEO checks and text extraction, stdlib only."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.lang = ""
        self.meta: dict[str, str] = {}
        self.canonical = ""
        self.h1: list[str] = []
        self.img_total = 0
        self.img_no_alt = 0
        self.links: list[str] = []
        self._text: list[str] = []
        self._stack: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        if tag == "html":
            self.lang = a.get("lang", "")
        elif tag == "meta":
            key = (a.get("name") or a.get("property") or "").lower()
            if key:
                self.meta[key] = a.get("content", "")
        elif tag == "link" and "canonical" in a.get("rel", "").lower():
            self.canonical = a.get("href", "")
        elif tag == "img":
            self.img_total += 1
            if "alt" not in a:
                self.img_no_alt += 1
        elif tag == "a" and a.get("href"):
            self.links.append(a["href"])
        if tag in {"script", "style", "noscript", "svg"}:
            self._skip += 1
        self._stack.append(tag)

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript", "svg"} and self._skip:
            self._skip -= 1
        if self._stack and self._stack[-1] == tag:
            self._stack.pop()

    def handle_data(self, data):
        if self._skip:
            return
        cur = self._stack[-1] if self._stack else ""
        if cur == "title":
            self.title += data
        elif cur == "h1":
            self.h1.append(data.strip())
        if data.strip():
            self._text.append(data.strip())

    @property
    def text(self) -> str:
        return re.sub(r"\s+", " ", " ".join(self._text)).strip()


def parse_html(html: str) -> PageFacts:
    p = PageFacts()
    p.feed(html)
    p.h1 = [h for h in p.h1 if h]
    p.title = p.title.strip()
    return p
