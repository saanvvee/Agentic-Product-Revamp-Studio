"""Evaluation: metrics per run, aggregated per arm (PLAN Section 6).

Every metric here is computed in code from what the run stored in the KB. None asks
a model for its opinion, so none can be talked up by one. The one LLM-free proxy we
use for "unresolved contradictions" (same-area overlap between teams) is crude, and
the report says so.
"""

from __future__ import annotations

import csv
import json
import statistics
from dataclasses import asdict, dataclass
from pathlib import Path

from revamp.arbitration.constraints import check
from revamp.contracts import Plan, Proposal
from revamp.kb import KnowledgeBase
from revamp.products import Product


@dataclass
class RunMetrics:
    run_id: str
    product: str
    arm: str
    seed: int
    status: str
    items: int
    total_cost: float
    budget_days: float  # the product's original budget, the same for every arm
    over_budget_days: float
    total_value: int
    dependency_violations: int
    cross_team_overlaps: int
    hidden_violations: int
    client_accepted: bool
    client_rounds: int
    handoff_rejections: int
    red_team_rounds: int
    citations_total: int
    citation_invalid_rate: float
    unsupported_dropped: int
    answer_key_recall: float | None
    evidence_seconds: float  # invariant 9: kept apart from ...
    llm_calls: int  # ... orchestration cost
    llm_cache_hits: int
    prompt_tokens: int
    completion_tokens: int
    llm_seconds: float


def dependency_violations(plan: Plan, props: dict[str, Proposal]) -> int:
    """A planned item whose dependency is missing from the plan, or not scheduled
    in an earlier wave."""
    wave = {i.proposal_id: i.order for i in plan.items}
    bad = 0
    for i in plan.items:
        for dep in props[i.proposal_id].depends_on:
            if dep not in wave or wave[dep] >= i.order:
                bad += 1
    return bad


def cross_team_overlaps(plan: Plan, props: dict[str, Proposal]) -> int:
    """Pairs of planned items from DIFFERENT teams touching the same area. A proxy for
    uncoordinated work: two teams changing one thing without having agreed how."""
    items = [props[i.proposal_id] for i in plan.items]
    n = 0
    for a_i, a in enumerate(items):
        for b in items[a_i + 1:]:
            if a.team != b.team and set(a.areas) & set(b.areas):
                n += 1
    return n


def parse_theme(theme: str) -> tuple[str, list[str]]:
    """Answer-key theme format: "Redesigned navigation :: navigation, sidebar, menu"."""
    text, _, kws = theme.partition("::")
    words = [k.strip().lower() for k in kws.split(",") if k.strip()]
    return text.strip(), words or [text.strip().lower()]


def answer_key_recall(plan: Plan, props: dict[str, Proposal], themes: list[str]) -> float | None:
    """Fraction of the redesign themes the product really shipped that at least one plan
    item touches (keyword match on title, change and areas). Descriptive only
    (invariant 8): what shipped is not proof of what was optimal."""
    if not themes:
        return None
    blobs = [" ".join([p.title, p.change, " ".join(p.areas)]).lower()
             for p in (props[i.proposal_id] for i in plan.items)]
    hit = sum(1 for t in themes if any(k in b for k in parse_theme(t)[1] for b in blobs))
    return hit / len(themes)


def run_metrics(run_id: str, kb: KnowledgeBase, product: Product,
                stats: dict | None = None) -> RunMetrics:
    if kb.role != "evaluator":
        raise PermissionError("metrics need the evaluator role (they read hidden constraints)")
    rec = kb.run(run_id)
    if rec is None or rec.plan_id is None:
        raise ValueError(f"run {run_id} has no final plan")
    plan = next(p for p in kb.plans(run_id) if p.id == rec.plan_id)
    props = {p.id: p for p in kb.proposals(run_id)}
    verdicts = kb.verdicts(run_id)
    stats = stats or {}
    total = int(stats.get("citations_total", 0))
    themes = product.answer_key.themes if product.answer_key else []
    c = rec.cost
    return RunMetrics(
        run_id=run_id, product=rec.product, arm=rec.arm, seed=rec.seed, status=rec.status,
        items=len(plan.items), total_cost=plan.total_cost, budget_days=product.budget_days,
        over_budget_days=max(0.0, plan.total_cost - product.budget_days),
        total_value=plan.total_value,
        dependency_violations=dependency_violations(plan, props),
        cross_team_overlaps=cross_team_overlaps(plan, props),
        hidden_violations=len(check(plan, props, kb.constraints(rec.product))),
        client_accepted=bool(verdicts) and verdicts[-1].decision == "accept",
        client_rounds=rec.client_rounds, handoff_rejections=rec.handoff_rejections,
        red_team_rounds=rec.red_team_rounds, citations_total=total,
        citation_invalid_rate=(stats.get("citations_invalid", 0) / total) if total else 0.0,
        unsupported_dropped=int(stats.get("unsupported_dropped", 0)),
        answer_key_recall=answer_key_recall(plan, props, themes),
        evidence_seconds=round(c.evidence_seconds, 1), llm_calls=c.llm_calls,
        llm_cache_hits=c.llm_cache_hits, prompt_tokens=c.prompt_tokens,
        completion_tokens=c.completion_tokens, llm_seconds=round(c.llm_seconds, 1))


# ------------------------------------------------------------------ aggregation

KEY_METRICS = ("items", "total_cost", "over_budget_days", "total_value", "hidden_violations",
               "dependency_violations", "cross_team_overlaps", "client_rounds",
               "citation_invalid_rate", "answer_key_recall", "llm_calls", "llm_seconds",
               "evidence_seconds")


def _fmt(values: list[float]) -> str:
    vals = [v for v in values if v is not None]
    if not vals:
        return "-"
    m = statistics.mean(vals)
    if len(vals) == 1:
        return f"{m:.2f}".rstrip("0").rstrip(".")
    return f"{m:.2f} ± {statistics.stdev(vals):.2f}"


def summarise(rows: list[RunMetrics]) -> str:
    """Markdown table: one row per (product, arm), mean ± std over seeds."""
    groups: dict[tuple[str, str], list[RunMetrics]] = {}
    for r in rows:
        groups.setdefault((r.product, r.arm), []).append(r)
    head = ["product", "arm", "n", "accepted"] + list(KEY_METRICS)
    out = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for (prod, arm), rs in sorted(groups.items()):
        cells = [prod, arm, str(len(rs)), f"{sum(r.client_accepted for r in rs)}/{len(rs)}"]
        cells += [_fmt([getattr(r, m) for r in rs]) for m in KEY_METRICS]
        out.append("| " + " | ".join(cells) + " |")
    return "\n".join(out)


def write_results(rows: list[RunMetrics], out_dir: Path, name: str) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path, md_path = out_dir / f"{name}.csv", out_dir / f"{name}.md"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(asdict(rows[0]).keys()))
        w.writeheader()
        for r in rows:
            w.writerow(asdict(r))
    md_path.write_text(summarise(rows) + "\n", encoding="utf-8")
    (out_dir / f"{name}.json").write_text(json.dumps([asdict(r) for r in rows], indent=1),
                                          encoding="utf-8")
    return csv_path, md_path
