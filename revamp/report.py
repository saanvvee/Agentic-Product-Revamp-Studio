"""Static HTML report for one run (PLAN B12): the plan, the budget ledger, the conflict
register, rejections, the client negotiation, the evidence chains and the cost split.

Plain HTML with inline CSS, no JavaScript and no dependencies: it opens from disk and
prints cleanly, which is what a demo fallback needs.
"""

from __future__ import annotations

import html
import json
from pathlib import Path

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
"""


def _e(x) -> str:
    return html.escape(str(x))


def render(run_id: str, kb_path: Path | None = None) -> str:
    kb = KnowledgeBase(kb_path or settings.kb_path, "team")  # the report shows team-visible data
    rec = kb.run(run_id)
    if rec is None:
        raise ValueError(f"no run {run_id}")
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


def write(run_id: str, kb_path: Path | None = None) -> Path:
    out = settings.runs_dir / "reports" / f"{run_id}.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(run_id, kb_path), encoding="utf-8")
    return out
