"""Command line:  python -m revamp <command> ...

  products                         list configured products
  audit <product> [--agentic]      gather evidence into the KB (no LLM unless --agentic)
  constraints <product>            load the product's private client constraints
  findings <product>               evidence coverage table
  run <product> [--arm A2] [--seed 0] [--hitl]
                                   one engagement; writes an HTML report
  eval <product...> [--arms A0,A1,A2] [--seeds 0,1,2]
                                   run arms x seeds, write results tables
  report <run_id>                  (re)build a run's HTML report
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys

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


def cmd_audit(a) -> None:
    from revamp.audit import STEPS, agentic_audit, deterministic_audit
    p = load_product(a.product)
    if a.agentic:
        out = asyncio.run(agentic_audit(p, max_tool_calls=a.max_tools, mode=a.mode))
    else:
        steps = tuple(s for s in STEPS if s not in set(a.skip.split(",")))
        out = asyncio.run(deterministic_audit(p, _kb("team"), a.target, steps))
    print(json.dumps(out, indent=1))


def cmd_constraints(a) -> None:
    cs = load_constraints(a.product)
    _kb("client").set_constraints(a.product, cs)
    print(f"{len(cs)} private constraints loaded for {a.product} (client namespace)")


def cmd_findings(a) -> None:
    fs = _kb("team").findings(a.product)
    for c, s in evidence.coverage(fs).items():
        print(f"{c:14} {s}")
    print(f"total {len(fs)}")


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
    print(report.write(a.run_id))


def main(argv=None) -> None:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(prog="revamp", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mode", choices=["hybrid", "local", "gemini"], default=None,
                    help="route all agents to one model family")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("products").set_defaults(fn=lambda a: print("\n".join(list_products())))
    s = sub.add_parser("audit")
    s.add_argument("product")
    s.add_argument("--agentic", action="store_true")
    s.add_argument("--max-tools", type=int, default=8)
    s.add_argument("--target", choices=["live", "local"], default="live")
    s.add_argument("--skip", default="", help="comma list: seo,pricing,voice,code,"
                                              "performance,accessibility,journeys")
    s.set_defaults(fn=cmd_audit)
    s = sub.add_parser("constraints")
    s.add_argument("product")
    s.set_defaults(fn=cmd_constraints)
    s = sub.add_parser("findings")
    s.add_argument("product")
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
    s.set_defaults(fn=cmd_report)
    a = ap.parse_args(argv)
    tracing.setup()
    a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
