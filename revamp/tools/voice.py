"""User complaints: GitHub issues and Discourse topics, strictly before the cutoff.

Invariant 7: only items created BEFORE the product's cutoff are returned. The cutoff
is the old release's date. Without this filter, complaints written after the
redesign (or about it) would leak the answer key into the input. The filter is
applied twice: in the query, and again on each item's own timestamp, because a
search index is not a guarantee.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import httpx

from revamp.contracts import Evidence, Finding
from revamp.settings import settings
from revamp.tools.common import Polite, evidence_timer, join


class LeakageError(AssertionError):
    pass


def _parse_ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _before(ts: datetime, cutoff: date) -> bool:
    return ts < datetime(cutoff.year, cutoff.month, cutoff.day, tzinfo=timezone.utc)


def _engagement_severity(score: int) -> str:
    return "high" if score >= 50 else "medium" if score >= 15 else "low"


def _assert_no_leak(findings: list[Finding], cutoff: date) -> list[Finding]:
    for f in findings:
        if not _before(f.evidence.observed_at, cutoff):
            raise LeakageError(f"{f.evidence.locator} created after cutoff {cutoff}")
    return findings


async def github_issues(product: str, repo: str, cutoff: date, limit: int = 40,
                        http: Polite | None = None) -> list[Finding]:
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if settings.github_token:
        headers["Authorization"] = f"Bearer {settings.github_token}"
    own = http is None
    # Search API: 30 requests/min authenticated, so 2 s between calls is safe.
    http = http or Polite(interval=2.0)
    seen: dict[str, dict] = {}
    try:
        with evidence_timer():
            for sort in ("reactions", "comments"):
                q = f"repo:{repo} is:issue created:<{cutoff.isoformat()}"
                r = await http.get("https://api.github.com/search/issues", check_robots=False,
                                   params={"q": q, "sort": sort, "order": "desc",
                                           "per_page": min(limit, 100)}, headers=headers)
                r.raise_for_status()
                for it in r.json().get("items", []):
                    seen.setdefault(it["html_url"], it)
    finally:
        if own:
            await http.client.aclose()

    out = []
    for url, it in seen.items():
        created = _parse_ts(it["created_at"])
        if not _before(created, cutoff):
            continue
        reactions = (it.get("reactions") or {}).get("total_count", 0)
        score = reactions + it.get("comments", 0)
        labels = tuple(sorted(l["name"] for l in it.get("labels", []) if l.get("name")))
        out.append(Finding.make(
            product=product, category="user_voice", title=it["title"][:200],
            detail=(it.get("body") or "")[:800], severity=_engagement_severity(score),
            metric="engagement", value=score, unit="reactions+comments",
            evidence=Evidence(tool="github_issues", target="live", locator=url,
                              observed_at=created),
            tags=("github", it.get("state", "")) + labels))
    out.sort(key=lambda f: -(f.value or 0))
    return _assert_no_leak(out[:limit], cutoff)


async def discourse_topics(product: str, base_url: str, cutoff: date, limit: int = 40,
                           pages: int = 5, http: Polite | None = None) -> list[Finding]:
    """All-time top topics, filtered to those created before the cutoff.

    Discourse's /search supports before: filters, but forums' robots.txt disallows
    /search (checked on forum.mautic.org, 29 Sep 2026), so we page through the
    allowed /top.json listing instead and filter on each topic's created_at.
    """
    own = http is None
    http = http or Polite(interval=1.0)
    topics: dict[int, dict] = {}
    blurbs: dict[int, str] = {}  # /top.json has excerpts only for some topics
    try:
        with evidence_timer():
            for page in range(pages):
                try:
                    r = await http.get(join(base_url, "/top.json"),
                                       params={"period": "all", "page": page})
                    r.raise_for_status()
                except (httpx.HTTPError, PermissionError):
                    break
                batch = (r.json().get("topic_list") or {}).get("topics", [])
                if not batch:
                    break
                for t in batch:
                    topics.setdefault(t["id"], t)
                    if t.get("excerpt"):
                        blurbs[t["id"]] = t["excerpt"]
    finally:
        if own:
            await http.client.aclose()

    out = []
    for tid, t in topics.items():
        created = _parse_ts(t["created_at"])
        if not _before(created, cutoff):
            continue
        score = int(t.get("like_count", 0)) + int(t.get("reply_count", t.get("posts_count", 1) - 1))
        url = join(base_url, f"/t/{t.get('slug', 'topic')}/{tid}")
        out.append(Finding.make(
            product=product, category="user_voice", title=t["title"][:200],
            detail=blurbs.get(tid, "")[:800], severity=_engagement_severity(score),
            metric="engagement", value=score, unit="likes+replies",
            evidence=Evidence(tool="discourse", target="live", locator=url, observed_at=created),
            tags=("discourse", f"views:{t.get('views', 0)}")))
    out.sort(key=lambda f: -(f.value or 0))
    return _assert_no_leak(out[:limit], cutoff)
