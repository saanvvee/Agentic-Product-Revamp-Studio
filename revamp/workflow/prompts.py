"""Build each agent's prompt from the KB and the run state.

Everything an agent sees is assembled here, in one place, so "what did the model know
when it decided?" has a readable answer. Note what is NOT here: the client's private
constraints appear only in `team_prompt` for arm A6, which exists to measure exactly
what that visibility is worth.
"""

from __future__ import annotations

from revamp import evidence
from revamp.contracts import ClientConstraint, Finding, Plan, Proposal
from revamp.products import Product


def _header(product: Product, budget: float | None = None) -> str:
    h = f"Product: {product.name} (github.com/{product.repo}, audited release {product.ref})."
    if budget is not None:
        h += f"\nEngineering budget for the revamp: {budget:g} engineer-days."
    return h


def brief_prompt(product: Product, findings: list[Finding], budget: float) -> str:
    cov = evidence.coverage(findings)
    return (f"{_header(product, budget)}\n\nEvidence coverage (category: severity counts):\n"
            + "\n".join(f"- {c}: {s}" for c, s in cov.items())
            + "\n\nMost severe findings:\n" + evidence.render(findings, per_category=5))


def voice_prompt(product: Product, findings: list[Finding]) -> str:
    voice = [f for f in findings if f.category == "user_voice"]
    lines = [f"{f.id} | engagement {f.value or 0:g} | {f.title} :: {f.detail[:200]}" for f in
             sorted(voice, key=lambda f: -(f.value or 0))[:40]]
    return f"{_header(product)}\n\nUser posts:\n" + ("\n".join(lines) or "(none)")


def journey_prompt(product: Product, steps: list[Finding], facts: list[Finding]) -> str:
    out = [_header(product), "", "Journey steps, in the order of the screenshots:"]
    for i, s in enumerate(steps, 1):
        out.append(f"Screenshot {i}: {s.id} | {s.evidence.locator} | {s.title}")
    if facts:
        out += ["", "Measured problems on these steps:"] + [evidence.line(f) for f in facts]
    return "\n".join(out)


def team_prompt(product: Product, team: str, budget: float, focus: list[str],
                findings: list[Finding], voice_themes: list[dict], journey: list[Finding],
                feedback: str = "", constraints: list[ClientConstraint] = ()) -> str:
    parts = [_header(product, budget),
             "Engagement focus: " + (", ".join(focus) or "not set"),
             "", "Measured evidence (id | category/severity | finding):",
             evidence.render(findings, per_category=8)]
    signal = [t for t in voice_themes if t.get("is_signal")]
    if signal:
        parts += ["", "User-complaint themes judged as signal:"]
        parts += [f"- {t['theme']} (cite: {', '.join(t['finding_ids'][:4])})" for t in signal]
    if journey:
        parts += ["", "Journey problems seen in screenshots:"] + [evidence.line(f) for f in journey]
    if constraints:  # arm A6 only
        parts += ["", "Client constraints (confidential, provided for this engagement):"]
        parts += [f"- {c.description}" for c in constraints]
    if feedback:
        parts += ["", "FEEDBACK ON YOUR PREVIOUS PROPOSALS (address it):", feedback]
    return "\n".join(parts)


def proposals_block(props: list[Proposal]) -> str:
    return "\n".join(
        f"{p.id} [{p.team}] {p.title} | {p.cost_days:g}d | value {p.value} | areas "
        f"{','.join(p.areas)} | risk {p.risk} | deps {','.join(p.depends_on) or '-'}\n"
        f"    change: {p.change[:220]}" for p in props)


def handoff_prompt(product: Product, props: list[Proposal]) -> str:
    return f"{_header(product)}\n\nProposals to review:\n{proposals_block(props)}"


def conflict_prompt(product: Product, props: list[Proposal]) -> str:
    return f"{_header(product)}\n\nAll proposals:\n{proposals_block(props)}"


def red_team_prompt(product: Product, plan: Plan, props: dict[str, Proposal],
                    chains: dict[str, list[Finding]]) -> str:
    out = [_header(product, plan.budget_days), "", "Draft plan items and their evidence:"]
    for item in plan.items:
        p = props[item.proposal_id]
        out.append(f"\n{p.id} [{p.team}] {p.title} ({p.cost_days:g}d, value {p.value})")
        out.append(f"  change: {p.change[:200]}")
        out.append(f"  rationale: {p.rationale[:200]}")
        for f in chains.get(p.id, []):
            out.append("  evidence: " + evidence.line(f))
    return "\n".join(out)


def adapt_prompt(product: Product, plan: Plan, props: dict[str, Proposal],
                 history: list[dict]) -> str:
    out = [_header(product, plan.budget_days), "", "Current plan:"]
    out.append(proposals_block([props[i.proposal_id] for i in plan.items]))
    out += ["", "Client responses so far (oldest first):"]
    for h in history:
        out.append(f"- round {h['round']}: {h['decision']} | reasons {h['reason_codes']} | "
                   f"vetoed {h['vetoed']} | \"{h['message']}\"")
    return "\n".join(out)


def single_llm_prompt(product: Product, findings: list[Finding], budget: float) -> str:
    return (f"{_header(product, budget)}\n\nMeasured evidence (id | category/severity | "
            f"finding):\n{evidence.render(findings, per_category=8)}")
