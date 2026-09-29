"""Codebase evidence: shallow clone at a pinned ref, then size (scc), complexity
(lizard) and known-vulnerable dependencies (osv-scanner).

All three read the source tree only. Nothing is installed or executed from the
audited repo, so auditing a hostile or broken repo cannot run its code.
"""

from __future__ import annotations

import asyncio
import csv
import io
import json
import shutil
import sys
from datetime import date
from pathlib import Path

from revamp.contracts import Evidence, Finding
from revamp.settings import settings
from revamp.tools.common import artifacts_dir, evidence_timer, save_json

EXCLUDE_DIRS = ("node_modules", "vendor", "dist", "build", ".next", "public", "fixtures",
                "__tests__", "tests", "test", "e2e", "migrations", "locales", "lang")
LIZARD_LANGS = ("javascript", "typescript", "php", "ruby", "python", "go")


async def _run(*cmd: str, cwd: Path | None = None, ok_codes=(0,)) -> str:
    proc = await asyncio.create_subprocess_exec(
        *cmd, cwd=cwd, stdin=asyncio.subprocess.DEVNULL,  # never inherit the MCP stdio pipe
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    out, err = await proc.communicate()
    if proc.returncode not in ok_codes:
        raise RuntimeError(f"{Path(cmd[0]).name} exited {proc.returncode}: "
                           f"{err.decode(errors='replace')[-500:]}")
    return out.decode(errors="replace")


def _binary(name: str) -> str:
    for cand in (settings.tools_bin / f"{name}.exe", settings.tools_bin / name):
        if cand.is_file():
            return str(cand)
    found = shutil.which(name)
    if not found:
        raise FileNotFoundError(f"{name} not found; run scripts/fetch_binaries.ps1")
    return found


async def clone(repo: str, ref: str) -> Path:
    dest = settings.workspace_dir / f"{repo.replace('/', '__')}@{ref}"
    if (dest / ".git").is_dir():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    with evidence_timer():
        await _run("git", "clone", "--quiet", "--depth", "1", "--branch", ref,
                   f"https://github.com/{repo}.git", str(dest))
    return dest


def _ev(tool: str, locator: str, artifact: str | None = None, version: str = "") -> Evidence:
    return Evidence(tool=tool, tool_version=version, target="source", locator=locator,
                    artifact_path=artifact)


# ------------------------------------------------------------------ scc

def parse_scc(rows: list[dict], *, product: str, locator: str, artifact: str | None) -> list[Finding]:
    rows = sorted(rows, key=lambda r: -r.get("Code", 0))
    total_code = sum(r.get("Code", 0) for r in rows) or 1
    total_cx = sum(r.get("Complexity", 0) for r in rows)
    out = [Finding.make(
        product=product, category="code_health", severity="info", evidence=_ev("scc", locator, artifact),
        title=f"Codebase size: {total_code} lines of code in {sum(r.get('Count', 0) for r in rows)} files",
        metric="loc", value=total_code, unit="lines",
        detail="; ".join(f"{r['Name']}: {r.get('Code', 0)}" for r in rows[:8]))]
    density = total_cx / total_code * 1000
    out.append(Finding.make(
        product=product, category="code_health", evidence=_ev("scc", locator, artifact),
        title=f"Complexity density {density:.0f} branches per 1k lines",
        severity="medium" if density > 150 else "info",
        metric="complexity_per_kloc", value=round(density, 1),
        detail="scc counts branch and loop keywords; a coarse maintainability signal."))
    return out


async def scc_metrics(product: str, root: Path, locator: str) -> list[Finding]:
    args = [_binary("scc"), "--format", "json", "--no-cocomo"]
    for d in EXCLUDE_DIRS:
        args += ["--exclude-dir", d]
    with evidence_timer():
        rows = json.loads(await _run(*args, str(root)))
    art = save_json(artifacts_dir(product, "code") / "scc.json", rows)
    return parse_scc(rows, product=product, locator=locator, artifact=art)


# ------------------------------------------------------------------ lizard

def parse_lizard_csv(text: str, *, product: str, root: Path, locator: str,
                     artifact: str | None, top: int = 15) -> list[Finding]:
    funcs = []
    for row in csv.reader(io.StringIO(text)):
        if len(row) < 11 or not row[1].strip().isdigit():
            continue  # header line or noise
        nloc, ccn, _tok, params, _len, _loc, file, name = row[:8]
        start = row[9]
        try:
            rel = str(Path(file).resolve().relative_to(root.resolve())).replace("\\", "/")
        except ValueError:
            rel = file
        funcs.append((int(ccn), int(nloc), name, rel, start))
    if not funcs:
        return []
    funcs.sort(reverse=True)
    over15 = sum(1 for f in funcs if f[0] > 15)
    out = [Finding.make(
        product=product, category="code_health", evidence=_ev("lizard", locator, artifact),
        title=f"{over15} of {len(funcs)} functions exceed cyclomatic complexity 15",
        severity="medium" if over15 / len(funcs) > 0.03 else "low",
        metric="functions_ccn_over_15", value=over15, unit="functions")]
    for ccn, nloc, name, rel, start in funcs[:top]:
        if ccn < 20:
            break
        out.append(Finding.make(
            product=product, category="code_health",
            evidence=_ev("lizard", f"{locator}/{rel}#L{start}", artifact),
            title=f"Complex function {name} (CCN {ccn}, {nloc} lines) in {rel}",
            severity="high" if ccn >= 40 else "medium", metric="ccn", value=ccn))
    return out


async def lizard_metrics(product: str, root: Path, locator: str) -> list[Finding]:
    import importlib.util
    if importlib.util.find_spec("lizard") is None:
        # Checked up front: lizard exits 1 on warnings, so a missing module would
        # otherwise look like "no complex functions", which is a false negative.
        raise FileNotFoundError("lizard not installed (pip install -r requirements.txt)")
    args = [sys.executable, "-m", "lizard", "--csv"]
    for lang in LIZARD_LANGS:
        args += ["-l", lang]
    for d in EXCLUDE_DIRS:
        args += ["-x", f"*/{d}/*"]
    with evidence_timer():
        text = await _run(*args, str(root), ok_codes=(0, 1))
    path = artifacts_dir(product, "code") / "lizard.csv"
    path.write_text(text, encoding="utf-8")
    return parse_lizard_csv(text, product=product, root=root, locator=locator, artifact=str(path))


# ------------------------------------------------------------------ osv-scanner

def _cvss_severity(max_sev: str | None) -> str:
    try:
        s = float(max_sev)
    except (TypeError, ValueError):
        return "medium"  # unscored advisories are still advisories
    return "critical" if s >= 9 else "high" if s >= 7 else "medium" if s >= 4 else "low"


def parse_osv(report: dict, *, product: str, locator: str, artifact: str | None,
              root: Path | None = None, cutoff: date | None = None,
              top: int = 25) -> list[Finding]:
    """`cutoff`: drop advisories published on or after it. Auditing an old release
    as of its release date, an advisory disclosed later was not knowable then;
    counting it would hand the system hindsight (same reasoning as invariant 7)."""
    rows = []
    hidden = 0
    for res in report.get("results", []):
        lockfile = (res.get("source") or {}).get("path", "")
        if root is not None:
            try:
                lockfile = str(Path(lockfile).resolve().relative_to(root.resolve()))
            except ValueError:
                pass
        lockfile = lockfile.replace("\\", "/")
        for pkg in res.get("packages", []):
            p = pkg.get("package", {})
            vulns = pkg.get("vulnerabilities", [])
            summaries = {v.get("id"): v.get("summary", "") for v in vulns}
            published = {v.get("id"): v.get("published", "") for v in vulns}
            for g in pkg.get("groups", []):
                ids = g.get("ids", [])
                if cutoff is not None:
                    dates = [published.get(i, "")[:10] for i in ids if published.get(i)]
                    if dates and min(dates) >= cutoff.isoformat():
                        hidden += 1
                        continue
                sev = _cvss_severity(g.get("max_severity"))
                rows.append((sev, g.get("max_severity") or "", p, ids, summaries, lockfile))
    rank = {"critical": 4, "high": 3, "medium": 2, "low": 1}
    rows.sort(key=lambda r: (-rank[r[0]], r[2].get("name", "")))
    out = [Finding.make(
        product=product, category="security", evidence=_ev("osv-scanner", locator, artifact),
        title=f"{len(rows)} known-vulnerable dependency advisories in lockfiles",
        severity="high" if any(r[0] in {"critical", "high"} for r in rows) else
        "medium" if rows else "info",
        metric="vuln_advisories", value=len(rows),
        detail="; ".join(f"{s}: {sum(1 for r in rows if r[0] == s)}" for s in rank)
        + (f". {hidden} advisories published after {cutoff} excluded." if hidden else ""))]
    for sev, score, p, ids, summaries, lockfile in rows[:top]:
        primary = next((i for i in ids if i.startswith("CVE-")), ids[0] if ids else "?")
        out.append(Finding.make(
            product=product, category="security", severity=sev,
            evidence=_ev("osv-scanner", f"{locator}/{lockfile}#{p.get('name')}@{p.get('version')}",
                         artifact),
            title=f"{p.get('name')}@{p.get('version')} ({p.get('ecosystem')}): {primary}",
            detail=next((summaries[i] for i in ids if summaries.get(i)), "")[:400],
            metric=primary, value=float(score) if score.replace(".", "", 1).isdigit() else None,
            unit="cvss", tags=tuple(ids)))
    return out


LOCKFILES = ("package-lock.json", "pnpm-lock.yaml", "yarn.lock", "bun.lock", "composer.lock",
             "Gemfile.lock", "poetry.lock", "uv.lock", "Pipfile.lock", "go.mod", "mix.lock",
             "Cargo.lock")


def find_lockfiles(root: Path) -> list[Path]:
    """We list lockfiles ourselves: osv-scanner 2.6's --recursive walk starts at the
    drive root on Windows and finds nothing (seen 29 Sep 2026); -L per file works."""
    found = []
    for name in LOCKFILES:
        for p in root.rglob(name):
            if not any(part in EXCLUDE_DIRS for part in p.relative_to(root).parts[:-1]):
                found.append(p)
    return sorted(found)


async def osv_scan(product: str, root: Path, locator: str,
                   cutoff: date | None = None) -> list[Finding]:
    lockfiles = find_lockfiles(root)
    if not lockfiles:
        return [Finding.make(product=product, category="security", severity="info",
                             evidence=_ev("osv-scanner", locator),
                             title="No lockfiles found; dependency CVEs not assessed")]
    args = [_binary("osv-scanner"), "scan", "source", "--format", "json"]
    for lf in lockfiles:
        args += ["-L", str(lf.relative_to(root))]
    with evidence_timer():
        # Exit code 1 means "vulnerabilities found", which is a result, not an error.
        text = await _run(*args, cwd=root, ok_codes=(0, 1))
    report = json.loads(text) if text.strip() else {}
    art = save_json(artifacts_dir(product, "code") / "osv.json", report)
    return parse_osv(report, product=product, locator=locator, artifact=art, root=root,
                     cutoff=cutoff)


async def code_audit(product: str, repo: str, ref: str,
                     cutoff: date | None = None) -> list[Finding]:
    root = await clone(repo, ref)
    locator = f"https://github.com/{repo}/tree/{ref}"
    out: list[Finding] = []
    for fn in (scc_metrics, lizard_metrics, osv_scan):
        try:
            if fn is osv_scan:
                out += await fn(product, root, locator, cutoff)
            else:
                out += await fn(product, root, locator)
        except (FileNotFoundError, RuntimeError) as e:
            out.append(Finding.make(
                product=product, category="code_health", severity="info",
                evidence=_ev(fn.__name__, locator),
                title=f"{fn.__name__} unavailable: {str(e)[:120]}"))
    return out
