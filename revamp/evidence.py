"""Turn KB findings into compact prompt text.

A 4B model has a small context and reads long lists badly, so agents see one line
per finding, highest severity first, capped per category. The id is always first
on the line so the model can cite it exactly.
"""

from __future__ import annotations

from collections import defaultdict

from revamp.contracts import SEVERITY_RANK, Finding


def line(f: Finding) -> str:
    val = ""
    if f.value is not None:
        val = f" [{f.metric}={f.value:g}{(' ' + f.unit) if f.unit else ''}]"
    return f"{f.id} | {f.category}/{f.severity} | {f.title}{val}"


def select(findings: list[Finding], per_category: int = 10,
           categories: set[str] | None = None, skip_info: bool = True) -> list[Finding]:
    groups: dict[str, list[Finding]] = defaultdict(list)
    for f in findings:
        if categories and f.category not in categories:
            continue
        if skip_info and f.severity == "info" and f.category not in {"pricing"}:
            continue
        groups[f.category].append(f)
    out = []
    for cat in sorted(groups):
        ranked = sorted(groups[cat], key=lambda f: (-SEVERITY_RANK[f.severity],
                                                    -(f.value or 0), f.id))
        out += ranked[:per_category]
    return out


def render(findings: list[Finding], **kw) -> str:
    chosen = select(findings, **kw)
    if not chosen:
        return "(no findings)"
    return "\n".join(line(f) for f in chosen)


def coverage(findings: list[Finding]) -> dict[str, dict[str, int]]:
    """Counts per category and severity; the Chief Diagnostician's view of gaps."""
    out: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for f in findings:
        out[f.category][f.severity] += 1
    return {c: dict(s) for c, s in sorted(out.items())}
