"""Static HTML report for one run (PLAN B12): the plan, the budget ledger, the conflict
register, rejections, the client negotiation, the evidence chains and the cost split.

An audit is a run too, so `render` serves it as well: `runs/reports/<audit id>.html`
holds the per-step table, the findings each step measured with their provenance, the
coverage they built up and the cost split (PLAN B14).

Both reports are built from files only, never from a model: the KB for the artifacts,
`runs/events/<run id>.jsonl` for what happened. So any past run's report can be rebuilt
with `python -m revamp report <run id>`, and a report cannot claim something the event
stream does not show.

Plain HTML with inline CSS, no JavaScript and no dependencies: it opens from disk and
prints cleanly, which is what a demo fallback needs.
"""

from __future__ import annotations

import html
import json
from pathlib import Path

from revamp import observe
from revamp.contracts import SEVERITY_RANK, Finding
from revamp.kb import KnowledgeBase
from revamp.settings import settings

CSS = """
:root{--bg:#fff;--fg:#1d2433;--mute:#5b6475;--line:#e3e6ec;--card:#f6f7f9;--acc:#2957c7;
--ok:#1e7a46;--bad:#b3261e;--warn:#9a6700}
@media (prefers-color-scheme:dark){:root{--bg:#12151b;--fg:#e6e9ef;--mute:#9aa3b2;
--line:#2a2f3a;--card:#1a1e26;--acc:#7aa2ff;--ok:#5cc28a;--bad:#ff7b72;--warn:#e3b341}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);
font:15px/1.5 system-ui,-apple-system,Segoe UI,sans-serif}
main{max-width:1100px;margin:0 auto;padding:24px 16px}h1{font-size:24px;margin:0 0 4px}
h2{font-size:18px;margin:32px 0 8px;border-bottom:1px solid var(--line);padding-bottom:4px}
.mute{color:var(--mute)}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px}
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:12px}
.card b{display:block;font-size:22px}table{width:100%;border-collapse:collapse;font-size:14px}
th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--mute);font-weight:600}.wrap{overflow-x:auto}
.bar{height:14px;background:var(--line);border-radius:7px;overflow:hidden}
.bar span{display:block;height:100%;background:var(--acc)}
.tag{display:inline-block;padding:0 6px;border-radius:4px;background:var(--line);font-size:12px;margin:1px}
.ok{color:var(--ok)}.bad{color:var(--bad)}.warn{color:var(--warn)}
details{margin:4px 0}code{font-size:12px}ol.log li{margin:2px 0}
.mono{font-family:ui-monospace,Consolas,monospace;font-size:12px;color:var(--mute)}
.sev-critical,.sev-high{color:var(--bad);font-weight:600}.sev-medium{color:var(--warn)}
.sev-low,.sev-info{color:var(--mute)}
pre{background:var(--card);border:1px solid var(--line);border-radius:6px;padding:8px;
font-size:12px;white-space:pre-wrap;word-break:break-word;margin:6px 0 8px}
a{color:var(--acc)}
"""


def _e(x) -> str:
    return html.escape(str(x))


def _audit_record_from_events(run_id: str):
    """Rebuild a RunRecord for an audit that never wrote one.

    Audits only started writing a record to the knowledge base in B14. The older ones still
    have their events on disk, and the docstring promise is that any past run's report can be
    rebuilt, so read the record back out of the events instead of refusing. Audits only: an
    engagement has always written a record, and its report needs plan data this cannot invent.
    """
    from revamp.audit import ARM_AGENTIC, ARM_DET
    from revamp.contracts import CostLedger, RunRecord

    events = observe.load_events(run_id)
    started = next((e for e in events if e["type"] == "audit_started"), None)
    if started is None or not started.get("product"):
        return None
    finished = next((e for e in reversed(events) if e["type"] == "audit_finished"), {})
    # `agentic` is absent on a deterministic audit; there is no LLM cost to put in the ledger.
    return RunRecord(
        run_id=run_id,
        product=started["product"],
        arm=ARM_AGENTIC if started.get("agentic") else ARM_DET,
        seed=0,
        status="done" if finished else "running",
        cost=CostLedger(evidence_seconds=float(finished.get("evidence_seconds") or 0.0)),
    )


def render(run_id: str, kb_path: Path | None = None) -> str:
    """One entry point for both kinds of run: an engagement, or an audit."""
    from revamp.audit import is_audit  # local: audit.py imports the whole tool stack
    kb = KnowledgeBase(kb_path or settings.kb_path, "team")  # team-visible data only
    rec = kb.run(run_id) or _audit_record_from_events(run_id)
    if rec is None:
        raise ValueError(f"no run {run_id}")
    if is_audit(rec.arm):
        return render_audit(run_id, rec, kb)
    return render_engagement(run_id, rec, kb)


def render_engagement(run_id: str, rec, kb: KnowledgeBase) -> str:
    plan = next((p for p in kb.plans(run_id) if p.id == rec.plan_id), None)
    props = {p.id: p for p in kb.proposals(run_id)}
    verdicts = kb.verdicts(run_id)
    log_path = settings.runs_dir / "logs" / f"{run_id}.json"
    log = json.loads(log_path.read_text(encoding="utf-8")) if log_path.is_file() else {}

    h = [f"<!doctype html><html lang=en><head><meta charset=utf-8>"
         f"<meta name=viewport content='width=device-width,initial-scale=1'>"
         f"<title>Revamp plan {_e(rec.product)}</title><style>{CSS}</style></head><body><main>",
         f"<h1>Revamp plan: {_e(rec.product)}</h1>",
         f"<p class=mute>Run {_e(run_id)} · arm {_e(rec.arm)} · seed {rec.seed} · "
         f"status {_e(rec.status)}</p>"]
    if plan is None:
        h.append(f"<p class=bad>No plan. {_e(rec.error)}</p></main></body></html>")
        return "".join(h)

    last = verdicts[-1] if verdicts else None
    c = rec.cost
    h.append("<div class=grid>")
    for label, val in (("Plan items", len(plan.items)),
                       ("Cost / budget", f"{plan.total_cost:g} / {plan.budget_days:g} d"),
                       ("Total value", plan.total_value),
                       ("Client", (last.decision if last else "-")),
                       ("Client rounds", rec.client_rounds),
                       ("Evidence time", f"{c.evidence_seconds:.0f} s"),
                       ("LLM calls (cached)", f"{c.llm_calls} ({c.llm_cache_hits})"),
                       ("LLM time", f"{c.llm_seconds:.0f} s")):
        h.append(f"<div class=card><span class=mute>{label}</span><b>{_e(val)}</b></div>")
    h.append("</div>")

    share = min(1.0, plan.total_cost / plan.budget_days) if plan.budget_days else 0
    h.append(f"<h2>Budget ledger</h2><div class=bar><span style='width:{share * 100:.0f}%'>"
             f"</span></div><p class=mute>{plan.total_cost:g} of {plan.budget_days:g} "
             f"engineer-days allocated.</p>")

    h.append("<h2>Sequenced plan</h2><div class=wrap><table><tr><th>Wave</th><th>Item</th>"
             "<th>Team</th><th>Days</th><th>Value</th><th>Areas</th><th>Evidence</th></tr>")
    for i in plan.items:
        p = props[i.proposal_id]
        chain = kb.evidence_chain(run_id, p.id)
        ev = "".join(f"<details><summary>{_e(f.id)} · {_e(f.category)}/{_e(f.severity)}"
                     f"</summary>{_e(f.title)}<br><code>{_e(f.evidence.tool)} · "
                     f"{_e(f.evidence.locator)}</code></details>" for f in chain)
        after = f"<br><span class=mute>after {_e(', '.join(i.after))}</span>" if i.after else ""
        h.append(f"<tr><td>{i.order}</td><td><b>{_e(p.title)}</b><br>{_e(p.change)}{after}</td>"
                 f"<td>{_e(p.team)}</td><td>{p.cost_days:g}</td><td>{p.value}</td><td>"
                 + "".join(f"<span class=tag>{_e(a)}</span>" for a in p.areas)
                 + f"</td><td>{ev}</td></tr>")
    h.append("</table></div>")

    h.append("<h2>Conflict register</h2>")
    if plan.conflicts:
        h.append("<div class=wrap><table><tr><th>Pair</th><th>Kind</th><th>Exclusive</th>"
                 "<th>Why</th></tr>")
        for cf in plan.conflicts:
            h.append(f"<tr><td>{_e(cf.a)} × {_e(cf.b)}</td><td>{_e(cf.kind)}</td>"
                     f"<td>{'yes' if cf.exclusive else 'no'}</td><td>{_e(cf.explanation)}</td></tr>")
        h.append("</table></div>")
    else:
        h.append("<p class=mute>No conflicts detected (or detection off in this arm).</p>")

    h.append("<h2>Not in the plan</h2>")
    if plan.rejected:
        h.append("<div class=wrap><table><tr><th>Proposal</th><th>Reason</th><th>Detail</th></tr>")
        for r in plan.rejected:
            title = props[r.proposal_id].title if r.proposal_id in props else r.proposal_id
            h.append(f"<tr><td>{_e(r.proposal_id)}: {_e(title)}</td><td class=warn>"
                     f"{_e(r.reason)}</td><td>{_e(r.detail)}</td></tr>")
        h.append("</table></div>")
    else:
        h.append("<p class=mute>Nothing rejected.</p>")

    h.append("<h2>Client negotiation</h2><ol>")
    for v in verdicts:
        cls = "ok" if v.decision == "accept" else "bad"
        h.append(f"<li><span class={cls}>{_e(v.decision)}</span> "
                 f"{_e(', '.join(v.reason_codes))} {_e(v.message)}"
                 + (f" <span class=mute>vetoed {_e(', '.join(v.vetoed_proposal_ids))}</span>"
                    if v.vetoed_proposal_ids else "") + "</li>")
    h.append("</ol>")

    if log.get("log"):
        h.append("<h2>Agent trace</h2><ol class=log>")
        h += [f"<li>{_e(line)}</li>" for line in log["log"]]
        h.append("</ol>")
        if settings.phoenix_endpoint:
            h.append(f"<p class=mute>Full spans in Phoenix: {_e(settings.phoenix_endpoint)}</p>")
    h.append("</main></body></html>")
    return "".join(h)


# ----------------------------------------------------------------------------- audit

def _steps(events: list[dict]) -> list[dict]:
    """Rebuild the audit's step table from the event stream.

    One row per tool run. A deterministic audit emits a node and a tool call for each
    step, so the tool's numbers are merged into the node's row; the agentic audit may
    call the same tool more than once, so those rows are keyed by the call number the
    Chief Diagnostician's cap counts.
    """
    order: list[tuple] = []
    rows: dict[tuple, dict] = {}

    def row_for(key: tuple, step: str, **kw) -> dict:
        row = rows.get(key)
        if row is None:
            order.append(key)
            row = rows[key] = {"step": step, "args": {}, "count": None, "new": None,
                               "ids": [], "ms": None, "error": "", "result": "",
                               "call": None, "cap": None}
        row.update({k: v for k, v in kw.items() if v is not None})
        return row

    for ev in events:
        t = ev["type"]
        if t == "node_started":
            row_for((ev["node"], None), ev["node"])
        elif t == "tool_started":
            row = row_for((ev["tool"], ev.get("call")), ev["tool"],
                          args=ev.get("args") or None, call=ev.get("call"), cap=ev.get("cap"))
            row["args"] = row["args"] or {}
        elif t in ("tool_finished", "tool_refused"):
            key = (ev["tool"], ev.get("call"))
            row = rows.get(key) or rows.get((ev["tool"], None))
            if row is None:
                row = row_for(key, ev["tool"], call=ev.get("call"), cap=ev.get("cap"))
            row["result"] = ev.get("result") or row["result"]
            row["ms"] = ev.get("ms") if ev.get("ms") is not None else row["ms"]
            if t == "tool_refused":
                row["error"] = "refused: the tool call budget was exhausted"
            else:
                row["count"] = ev.get("count")
                row["new"] = ev.get("new")
                row["ids"] = list(dict.fromkeys(ev.get("finding_ids") or []))
                if ev.get("error"):
                    row["error"] = ev["error"]
        elif t == "node_finished":
            # A step whose tool never finished still gets its time from the node event.
            for (name, _), row in rows.items():
                if name == ev["node"] and row["ms"] is None:
                    row["ms"] = ev.get("ms")
                    break
    return [rows[k] for k in order]


def _artifact_href(path: str) -> str | None:
    """`runs/artifacts/x.png` -> `../artifacts/x.png`, a link that works from the
    report's own folder in `runs/reports/`."""
    try:
        return "../" + Path(path).relative_to("runs").as_posix()
    except ValueError:
        return None


def _finding_rows(findings: list[Finding]) -> str:
    h = ["<table><tr><th>Id</th><th>Category</th><th>Severity</th><th>Finding</th>"
         "<th>Metric</th><th>Evidence</th></tr>"]
    for f in sorted(findings, key=lambda f: (-SEVERITY_RANK[f.severity], f.id)):
        val = (f"{_e(f.metric)} = {f.value:g}{(' ' + _e(f.unit)) if f.unit else ''}"
               if f.value is not None else (_e(f.metric) if f.metric else ""))
        art = _artifact_href(f.evidence.artifact_path) if f.evidence.artifact_path else None
        h.append(f"<tr><td><span class=tag>{_e(f.id)}</span></td>"
                 f"<td>{_e(f.category.replace('_', ' '))}</td>"
                 f"<td class=sev-{_e(f.severity)}>{_e(f.severity)}</td>"
                 f"<td>{_e(f.title)}"
                 + (f"<div class=mute>{_e(f.detail)}</div>" if f.detail else "")
                 + f"</td><td>{val}</td><td class=mono>{_e(f.evidence.tool)}<br>"
                 f"{_e(f.evidence.locator)}"
                 + (f"<br><a href='{_e(art)}'>artifact</a>" if art else "")
                 + (f"<br>{_e(f.evidence.target)}" if f.evidence.target != "live" else "")
                 + "</td></tr>")
    h.append("</table>")
    return "".join(h)


def render_audit(run_id: str, rec, kb: KnowledgeBase) -> str:
    """The audit's own report: what each step measured, what it found, and what it cost.

    Read from the KB plus `runs/events/<run id>.jsonl`, so it rebuilds for any past
    audit without re-running a single tool.
    """
    events = observe.load_events(run_id)
    started = next((e for e in events if e["type"] == "audit_started"), {})
    finished = next((e for e in reversed(events) if e["type"] == "audit_finished"), {})
    agentic = bool(started.get("agentic"))
    steps = _steps(events)
    c = rec.cost
    by_id = {f.id: f for f in kb.findings(rec.product)}
    measured = sum(s["count"] or 0 for s in steps)
    new = sum(s["new"] or 0 for s in steps)
    failed = [s for s in steps if s["error"]]
    mode = ("Chief Diagnostician over MCP" if agentic
            else "deterministic sweep: every tool, fixed order, no model")

    h = [f"<!doctype html><html lang=en><head><meta charset=utf-8>"
         f"<meta name=viewport content='width=device-width,initial-scale=1'>"
         f"<title>Audit {_e(rec.product)} {_e(run_id)}</title><style>{CSS}</style></head>"
         f"<body><main>",
         f"<h1>Audit: {_e(rec.product)}</h1>",
         f"<p class=mute>Run {_e(run_id)} · {_e(mode)} · target {_e(started.get('target', 'live'))}"
         f" · status {_e(rec.status)}"
         + (f" · <span class=bad>{_e(rec.error)}</span>" if rec.error else "")
         + "</p>"]

    cards = [("Steps", f"{len(steps) - len(failed)}/{len(steps)}",
              "one failing tool never sinks the audit" if not failed
              else f"{len(failed)} failed or refused"),
             ("Findings measured", measured, f"{new} new to the knowledge base"),
             ("Evidence in the KB", len(by_id), f"every audit of {_e(rec.product)} so far"),
             ("Evidence time", f"{c.evidence_seconds:.0f} s", "wall time in the tools")]
    if agentic:
        cards += [("Tool calls", finished.get("tool_calls", 0),
                   f"cap {started.get('max_tool_calls', '?')}, enforced in code"),
                  ("LLM calls", f"{c.llm_calls} ({c.llm_cache_hits} cached)",
                   f"{c.llm_seconds:.0f} s of model time"),
                  ("Tokens", f"{c.prompt_tokens + c.completion_tokens}",
                   f"{c.prompt_tokens} in, {c.completion_tokens} out")]
    else:
        cards.append(("LLM calls", "0", "by design: this audit has no model in it"))
    h.append("<div class=grid>")
    for label, val, sub in cards:
        h.append(f"<div class=card><span class=mute>{_e(label)}</span><b>{_e(val)}</b>"
                 f"<div class=mute>{_e(sub)}</div></div>")
    h.append("</div>")

    h.append("<h2>Steps</h2><div class=wrap><table><tr><th>Step</th><th>Input</th>"
             "<th>Findings</th><th>New</th><th>Time</th><th>Status</th></tr>")
    for s in steps:
        label = _e(s["step"]) + (f" <span class=mute>call {s['call']}/{s['cap']}</span>"
                                 if s["call"] else "")
        secs = f"{s['ms'] / 1000:.0f} s" if s["ms"] is not None else "—"
        if s["error"]:
            status = f"<span class=bad>{_e(s['error'])}</span>"
        elif s["count"] is None:
            status = "<span class=mute>summary only</span>"  # agentic: no per-call ids
        else:
            status = f"<span class=ok>{s['count']} findings</span>"
        h.append(f"<tr><td>{label}</td><td class=mono>{_e(json.dumps(s['args'])[:300])}</td>"
                 f"<td>{s['count'] if s['count'] is not None else '—'}</td>"
                 f"<td>{s['new'] if s['new'] is not None else '—'}</td>"
                 f"<td>{secs}</td><td>{status}</td></tr>")
    h.append("</table></div>")

    h.append("<h2>Findings by step</h2>")
    listed = False
    for s in steps:
        found = [by_id[i] for i in s["ids"] if i in by_id]
        if not found:
            continue
        listed = True
        h.append(f"<details><summary>{_e(s['step'])} · {len(found)} findings · "
                 f"{s['new']} new</summary>")
        h.append(_finding_rows(found))
        h.append("</details>")
    if not listed:
        h.append("<p class=mute>This audit recorded no finding ids per step (an agentic "
                 "audit learns them from the tool summaries instead). Every finding the "
                 "tools stored is listed under Coverage below.</p>")

    h.append("<h2>Coverage</h2><p class=mute>Findings per category and severity, "
             "cumulative over every audit of this product.</p><div class=grid>")
    cov: dict[str, dict[str, int]] = {}
    for f in by_id.values():
        cov.setdefault(f.category, {}).setdefault(f.severity, 0)
        cov[f.category][f.severity] += 1
    for cat in sorted(cov):
        sevs = " · ".join(f"{n} {s}" for s, n in sorted(cov[cat].items(),
                                                        key=lambda kv: -SEVERITY_RANK[kv[0]]))
        h.append(f"<div class=card><span class=mute>{_e(cat.replace('_', ' '))}</span>"
                 f"<b>{sum(cov[cat].values())}</b><div class=mute>{_e(sevs)}</div></div>")
    h.append("</div>")

    # Invariant 9: what measuring cost, and what reasoning cost, are separate numbers.
    top = max(1.0, c.evidence_seconds, c.llm_seconds)
    h.append("<h2>Cost split</h2>")
    for label, val, colour in (("Evidence (audit tools)", c.evidence_seconds, "var(--acc)"),
                               ("Orchestration (LLM)", c.llm_seconds, "var(--acc)")):
        h.append(f"<p>{_e(label)}: <b>{val:.0f} s</b></p>"
                 f"<div class=bar><span style='width:{val / top * 100:.0f}%;"
                 f"background:{colour}'></span></div>")

    diag = finished.get("diagnosis")
    if diag:
        h.append("<h2>Chief Diagnostician's report</h2>")
        h.append(f"<p>{_e(diag.get('summary', ''))}</p>")
        if diag.get("key_finding_ids"):
            h.append("<p>Key findings: " + "".join(
                f"<span class=tag>{_e(i)}</span>" for i in diag["key_finding_ids"]) + "</p>")
        if diag.get("gaps"):
            h.append("<p class=mute>Remaining gaps: " +
                     _e(", ".join(diag["gaps"])) + "</p>")

    reads = [s for s in steps if not s["ids"] and s["result"] and not s["count"]]
    if reads:
        h.append("<h2>Tool results</h2>")
        for s in reads:
            label = _e(s["step"]) + (f" <span class=mute>call {s['call']}/{s['cap']}</span>"
                                     if s["call"] else "")
            h.append(f"<details><summary>{label}</summary><pre>{_e(s['result'])}</pre></details>")

    url = started.get("trace_url")
    if url:
        h.append(f"<p class=mute>Spans for this audit: <a href='{_e(url)}'>{_e(url)}</a></p>")
    h.append("<p class=mute>Rebuilt from runs/events/" + _e(run_id) + ".jsonl and the "
             "knowledge base. No model was asked anything to produce this page.</p>")
    h.append("</main></body></html>")
    return "".join(h)


def write(run_id: str, kb_path: Path | None = None) -> Path:
    out = settings.runs_dir / "reports" / f"{run_id}.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(run_id, kb_path), encoding="utf-8")
    return out
