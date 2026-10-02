"""Command line:  python -m revamp <command> ...

  doctor [--gpu]                   check this machine is ready (--gpu: load each model and
                                   confirm it sits in VRAM)
  products                         list configured products
  audit <product> [--agentic]      gather evidence into the KB (no LLM unless --agentic)
  constraints <product>            load the product's private client constraints
  findings <product> [--full]       evidence coverage table (--full: every finding)
  run <product> [--arm A2] [--seed 0] [--hitl]
                                   one engagement; writes an HTML report
  eval <product...> [--arms A0,A1,A2] [--seeds 0,1,2]
                                   run arms x seeds, write results tables
  report <run_id> [--open]         (re)build a run's HTML report (--open: in a browser)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import webbrowser

from revamp import evidence, report, tracing
from revamp.kb import KnowledgeBase
from revamp.products import list_products, load_constraints, load_product
from revamp.settings import settings


def _kb(role: str) -> KnowledgeBase:
    return KnowledgeBase(settings.kb_path, role)


def terminal_approver(pending: dict) -> dict:
    print("\nHUMAN APPROVAL NEEDED: high-impact plan items")
    for it in pending["items"]:
        print(f"  {it['id']}: {it['title']} ({it['cost_days']:g}d, risk {it['risk']})")
    raw = input("Ids to REJECT (comma separated, empty = approve all): ").strip()
    return {"rejected": [x.strip() for x in raw.split(",") if x.strip()]}


def cmd_doctor(a) -> None:
    from revamp.doctor import run
    sys.exit(run(load_models=a.gpu))


def _print_audit(out: dict) -> None:
    """The audit's result on the terminal: one row per step, then the totals. The HTML
    report has the full detail."""
    cost = out["cost"]
    print(f"run {out['run_id']}  status {out['status']}")
    if out["mode"] == "agentic":
        print(f"tool calls {out.get('tool_calls', 0)}, LLM calls {cost['llm_calls']} "
              f"({cost['llm_cache_hits']} cached), evidence {cost['evidence_seconds']:.0f} s "
              f"+ model {cost['llm_seconds']:.0f} s")
        rep = out.get("report") or {}
        if rep:
            print(f"\n{rep.get('summary', '')}")
            if rep.get("key_finding_ids"):
                print("key findings: " + ", ".join(rep["key_finding_ids"]))
            if rep.get("gaps"):
                print("gaps: " + ", ".join(rep["gaps"]))
        print(f"\n{out.get('new_findings', 0)} new findings, "
              f"{out.get('kb_findings', 0)} in the knowledge base")
        return
    rows = out["results"]
    width = max((len(r["step"]) for r in rows), default=6)
    print(f"\n{'step'.ljust(width)}  findings   new     time")
    for r in rows:
        if r["error"]:
            print(f"{r['step'].ljust(width)}  SKIPPED: {r['error'][:120]}")
        else:
            print(f"{r['step'].ljust(width)}  {r['count']:>8}  {r['new']:>3}  "
                  f"{r['ms'] / 1000:>5.0f} s")
    print(f"\n{out['findings']} findings, {out['new']} new; evidence "
          f"{cost['evidence_seconds']:.0f} s, no model involved (by design)")


def cmd_audit(a) -> None:
    from revamp.audit import STEPS, agentic_audit, deterministic_audit
    p = load_product(a.product)
    if a.agentic:
        out = asyncio.run(agentic_audit(p, max_tool_calls=a.max_tools, mode=a.mode,
                                        kb=_kb("team")))
    else:
        steps = tuple(s for s in STEPS if s not in set(a.skip.split(",")))
        out = asyncio.run(deterministic_audit(p, _kb("team"), a.target, steps))
    if a.json:
        print(json.dumps(out, indent=1))
    else:
        _print_audit(out)
        print(f"\nreport: {report.write(out['run_id'])}")


def cmd_constraints(a) -> None:
    cs = load_constraints(a.product)
    _kb("client").set_constraints(a.product, cs)
    print(f"{len(cs)} private constraints loaded for {a.product} (client namespace)")


SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


def findings_lines(fs, full: bool) -> list[str]:
    """Coverage counts, plus every finding when asked. The audit's HTML report is the
    readable artifact; this is the same evidence on the terminal, for grepping."""
    lines = [f"{c:14} {s}" for c, s in evidence.coverage(fs).items()]
    lines.append(f"total {len(fs)}")
    if not full:
        return lines
    lines.append("")
    for f in sorted(fs, key=lambda f: (SEVERITY_RANK.get(f.severity, 9), f.category, f.id)):
        lines.append(f"{f.id}  {f.severity:8} {f.category:14} {f.title}")
        if f.metric:
            lines.append(f"{'':11}{f.evidence.tool:16} {f.metric}={f.value}"
                         + (f" {f.unit}" if f.unit else ""))
        if f.evidence.locator:
            lines.append(f"{'':11}{f.evidence.locator}")
    return lines


def cmd_findings(a) -> None:
    print("\n".join(findings_lines(_kb("team").findings(a.product), a.full)))


def _run(product: str, arm: str, seed: int, mode, approver):
    from revamp.workflow.runner import run_engagement
    return asyncio.run(run_engagement(product, arm, seed, mode=mode, approver=approver))


def cmd_run(a) -> None:
    res = _run(a.product, a.arm, a.seed, a.mode, terminal_approver if a.hitl else None)
    print("\n".join(res.log))
    path = report.write(res.record.run_id)
    print(f"\nreport: {path}")


def cmd_eval(a) -> None:
    from revamp.evaluation import run_metrics, write_results
    arms = a.arms.split(",")
    seeds = [int(s) for s in a.seeds.split(",")]
    rows = []
    ev = _kb("evaluator")
    for product in a.products:
        prod = load_product(product)
        for arm in arms:
            for seed in seeds:
                print(f"== {product} {arm} seed {seed}", flush=True)
                try:
                    res = _run(product, arm, seed, a.mode, None)
                except Exception as e:  # keep going; the failure is in the run record
                    print(f"   FAILED: {type(e).__name__}: {e}")
                    continue
                m = run_metrics(res.record.run_id, ev, prod, res.stats)
                rows.append(m)
                report.write(res.record.run_id)
                print(f"   items {m.items} cost {m.total_cost:g} hidden_viol "
                      f"{m.hidden_violations} accepted {m.client_accepted}")
    if rows:
        csv_path, md_path = write_results(rows, settings.runs_dir / "results", a.name)
        print(md_path.read_text(encoding="utf-8"))
        print(f"results: {csv_path}")


def cmd_report(a) -> None:
    path = report.write(a.run_id)
    print(path)
    if a.open:
        webbrowser.open(path.resolve().as_uri())


def main(argv=None) -> None:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(prog="revamp", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mode", choices=["hybrid", "local", "gemini"], default=None,
                    help="route all agents to one model family")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("doctor")
    s.add_argument("--gpu", action="store_true", help="load each model, confirm it is in VRAM")
    s.set_defaults(fn=cmd_doctor)
    sub.add_parser("products").set_defaults(fn=lambda a: print("\n".join(list_products())))
    s = sub.add_parser("audit")
    s.add_argument("product")
    s.add_argument("--agentic", action="store_true")
    s.add_argument("--max-tools", type=int, default=8)
    s.add_argument("--target", choices=["live", "local"], default="live")
    s.add_argument("--skip", default="", help="comma list: seo,pricing,voice,code,"
                                              "performance,accessibility,journeys")
    s.add_argument("--mode", choices=["local", "gemini"], default="local")
    s.add_argument("--json", action="store_true", help="print the raw result, not the summary")
    s.set_defaults(fn=cmd_audit)
    s = sub.add_parser("constraints")
    s.add_argument("product")
    s.set_defaults(fn=cmd_constraints)
    s = sub.add_parser("findings")
    s.add_argument("product")
    s.add_argument("--full", action="store_true",
                   help="list every finding, not just the coverage counts")
    s.set_defaults(fn=cmd_findings)
    s = sub.add_parser("run")
    s.add_argument("product")
    s.add_argument("--arm", default="A2")
    s.add_argument("--seed", type=int, default=0)
    s.add_argument("--hitl", action="store_true")
    s.set_defaults(fn=cmd_run)
    s = sub.add_parser("eval")
    s.add_argument("products", nargs="+")
    s.add_argument("--arms", default="A0,A1,A2,A3,A4,A5,A6")
    s.add_argument("--seeds", default="0")
    s.add_argument("--name", default="results")
    s.set_defaults(fn=cmd_eval)
    s = sub.add_parser("report")
    s.add_argument("run_id")
    s.add_argument("--open", action="store_true", help="open the report in the default browser")
    s.set_defaults(fn=cmd_report)
    a = ap.parse_args(argv)
    tracing.setup()
    a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
