"""Is the severity distribution degenerate? Checked, not assumed.

WHY THIS EXISTS

Once the budget tiers were recalibrated to actually bind (PRD v1.5), triage's
classifier stopped being a routing convenience and became a **load-bearing input
to the headline result**:

    low (250 ms)      parallel structurally unavailable; only cheap sensors
    standard (600 ms) binds exactly at the sequential trio
    critical (900 ms) generous, but refuses the exhaustive sweep

So the severity distribution largely determines how often admission control fires
at all. A triage agent that labels 95% of incidents `standard` would make the
tier system decorative again -- in a subtler way than the inert table did, because
every mechanism would still work and simply never be exercised.

That failure is invisible in a results table unless it is looked for, so it is
measured here and reported alongside every run (PRD S12.1).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from core.config import Severity

MIN_TIER_SHARE = 0.10
"""No severity class may fall below this share, or its budget tier is untested.

At 10% of a 150-incident test set that is 15 incidents -- few, but enough for a
per-tier rate to mean something. Below that, any tier-specific finding is noise.
"""

MAX_TIER_SHARE = 0.75
"""No single class may dominate beyond this, or the tier system is decorative."""


@dataclass(frozen=True, slots=True)
class SeverityHealth:
    """Whether a run's severity distribution can support tier-level conclusions."""

    counts: dict[Severity, int]
    total: int
    degenerate: bool
    findings: tuple[str, ...]

    @property
    def shares(self) -> dict[Severity, float]:
        if not self.total:
            return {s: 0.0 for s in Severity}
        return {s: self.counts.get(s, 0) / self.total for s in Severity}

    def as_log_fields(self) -> dict[str, object]:
        """Stamped beside every results table, per PRD R23 discipline.

        A results table without its severity distribution cannot be interpreted:
        the same orchestrator produces very different aggregate costs depending on
        how triage classified the set.
        """
        return {
            "severity_counts": {s.value: self.counts.get(s, 0) for s in Severity},
            "severity_shares": {s.value: round(v, 4) for s, v in self.shares.items()},
            "severity_degenerate": self.degenerate,
            "severity_findings": list(self.findings),
        }

    def report(self) -> str:
        lines = [f"Severity distribution over {self.total} incidents:"]
        for severity in Severity:
            count = self.counts.get(severity, 0)
            share = self.shares[severity]
            lines.append(f"  {severity.value:9} {count:4}  {share:6.1%}")
        if self.findings:
            lines.append("")
            lines.append("DEGENERATE -- tier-level conclusions are not supported:")
            lines.extend(f"  * {f}" for f in self.findings)
        else:
            lines.append("")
            lines.append("Distribution supports tier-level conclusions.")
        return "\n".join(lines)


def assess_severity_distribution(severities: list[Severity]) -> SeverityHealth:
    """Check a run's classifications for degeneracy.

    Deliberately NOT a pass/fail gate on the run itself: a skewed distribution
    might be the correct response to the incident set, and forcing a target would
    mean tuning triage to produce a convenient spread, which is exactly the
    circularity we avoided when freezing the budget tiers. This reports, so the
    results can be read honestly.
    """
    counts = Counter(severities)
    total = len(severities)
    findings: list[str] = []

    if total == 0:
        return SeverityHealth({}, 0, True, ("no incidents classified",))

    for severity in Severity:
        share = counts.get(severity, 0) / total
        if share < MIN_TIER_SHARE:
            findings.append(
                f"{severity.value} is {share:.1%} of the set (<{MIN_TIER_SHARE:.0%}): "
                f"its budget tier of "
                f"{'250' if severity is Severity.LOW else '600' if severity is Severity.STANDARD else '900'} ms "
                "is effectively untested, so any tier-specific rate is noise"
            )
        if share > MAX_TIER_SHARE:
            findings.append(
                f"{severity.value} is {share:.1%} of the set (>{MAX_TIER_SHARE:.0%}): "
                "one tier dominates, so the tier system is decorative and "
                "admission control is rarely exercised"
            )

    return SeverityHealth(
        counts=dict(counts),
        total=total,
        degenerate=bool(findings),
        findings=tuple(findings),
    )
