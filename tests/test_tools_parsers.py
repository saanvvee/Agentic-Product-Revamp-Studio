"""Parser tests on small synthetic tool outputs. No network, no binaries."""

from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from revamp.contracts import Evidence, Finding
from revamp.tools.browser import parse_axe
from revamp.tools.code import parse_lizard_csv, parse_osv, parse_scc
from revamp.tools.lighthouse import parse_crux, parse_lhr
from revamp.tools.seo import check_page
from revamp.tools.voice import LeakageError, _assert_no_leak

LHR = {
    "lighthouseVersion": "13.5.0",
    "audits": {
        "largest-contentful-paint": {"numericValue": 5200, "displayValue": "5.2 s"},
        "cumulative-layout-shift": {"numericValue": 0.02},
        "color-contrast": {"score": 0, "title": "Low contrast", "scoreDisplayMode": "binary",
                           "details": {"items": [1, 2, 3]}},
        "document-title": {"score": 1, "title": "Has title", "scoreDisplayMode": "binary"},
    },
    "categories": {
        "performance": {"score": 0.42, "title": "Performance",
                        "auditRefs": [{"id": "largest-contentful-paint", "weight": 25}]},
        "accessibility": {"score": 0.8, "title": "Accessibility",
                          "auditRefs": [{"id": "color-contrast", "weight": 7},
                                        {"id": "document-title", "weight": 3}]},
    },
}


def test_parse_lhr():
    fs = parse_lhr(LHR, product="p", tool="psi", target="live", url="https://x/")
    by_metric = {f.metric: f for f in fs}
    assert by_metric["LCP"].severity == "high" and by_metric["LCP"].value == 5200
    assert by_metric["CLS"].severity == "info"
    assert by_metric["lh_performance_score"].severity == "high"
    assert by_metric["color-contrast"].severity == "high" and by_metric["color-contrast"].value == 3
    assert "document-title" not in by_metric  # passing audits are not findings


def test_parse_crux():
    fs = parse_crux({"metrics": {"LARGEST_CONTENTFUL_PAINT_MS": {"percentile": 3100,
                                                                  "category": "AVERAGE"}}},
                    product="p", url="https://x/", scope="origin")
    assert fs[0].severity == "medium" and fs[0].evidence.tool == "crux"


def test_parse_axe():
    res = {"testEngine": {"version": "4.13.0"}, "violations": [
        {"id": "image-alt", "impact": "critical", "help": "Images need alt",
         "tags": ["wcag2a", "cat.text"], "nodes": [{"target": ["img"]}, {"target": ["img.b"]}]}]}
    f = parse_axe(res, product="p", url="https://x/", target="live", artifact=None)[0]
    assert f.severity == "critical" and f.value == 2 and f.tags == ("wcag2a",)
    assert f.evidence.tool_version == "4.13.0"


def test_seo_checks():
    html = "<html><head><title>x</title></head><body><h1>A</h1><h1>B</h1><img src=a></body></html>"
    titles = {f.metric: f for f in check_page("p", "https://x/", html, "live")}
    assert titles["title_length"].value == 1
    assert titles["meta_description_length"].severity == "medium"
    assert titles["h1_count"].value == 2
    assert titles["img_missing_alt"].value == 1


def test_parse_scc():
    rows = [{"Name": "TypeScript", "Code": 900, "Complexity": 200, "Count": 10},
            {"Name": "CSS", "Code": 100, "Complexity": 0, "Count": 2}]
    fs = parse_scc(rows, product="p", locator="L", artifact=None)
    assert fs[0].value == 1000 and fs[1].value == 200.0 and fs[1].severity == "medium"


def test_parse_lizard(tmp_path):
    root = tmp_path
    f = root / "src" / "a.ts"
    csv_text = ("NLOC,CCN,token,PARAM,length,location,file,function,long_name,start,end\n"
                f'80,45,500,2,90,"big@1-90@{f}",{f},big,big(a,b),1,90\n'
                f'5,2,20,0,5,"small@1-5@{f}",{f},small,small(),100,105\n')
    fs = parse_lizard_csv(csv_text, product="p", root=root, locator="L", artifact=None)
    assert fs[0].value == 1  # one of two functions over 15
    assert fs[1].value == 45 and fs[1].severity == "high" and "src/a.ts" in fs[1].title


OSV = {"results": [{"source": {"path": "/r/pnpm-lock.yaml"}, "packages": [{
    "package": {"name": "next", "version": "15.3.3", "ecosystem": "npm"},
    "vulnerabilities": [
        {"id": "GHSA-old", "summary": "old bug", "published": "2025-01-10T00:00:00Z"},
        {"id": "GHSA-new", "summary": "new bug", "published": "2026-02-01T00:00:00Z"}],
    "groups": [{"ids": ["GHSA-old"], "max_severity": "9.1"},
               {"ids": ["GHSA-new"], "max_severity": "7.5"}]}]}]}


def test_parse_osv_severity_and_cutoff():
    all_ = parse_osv(OSV, product="p", locator="L", artifact=None)
    assert all_[0].value == 2 and {f.severity for f in all_[1:]} == {"critical", "high"}
    past = parse_osv(OSV, product="p", locator="L", artifact=None, cutoff=date(2025, 7, 1))
    assert past[0].value == 1 and past[1].metric == "GHSA-old"
    assert "1 advisories published after" in past[0].detail


def test_voice_leak_guard():
    ev = Evidence(tool="github_issues", target="live", locator="https://gh/1",
                  observed_at=datetime(2025, 8, 1, tzinfo=timezone.utc))
    f = Finding.make(product="p", category="user_voice", title="t", severity="low", evidence=ev)
    with pytest.raises(LeakageError):
        _assert_no_leak([f], date(2025, 7, 28))
    assert _assert_no_leak([f], date(2025, 8, 2)) == [f]
