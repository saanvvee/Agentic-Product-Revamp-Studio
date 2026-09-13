"""M1 GATE: compare real detector scores against the synthetic score bands.

Why this script is mandatory rather than optional.

`harness/synthetic.py` samples confidences from FIXED parameter bands, chosen
before any real detector existed. That was a deliberate decision (it kept the
generator unblocked while datasets downloaded, and keeps it reproducible), but it
has an honest cost: **the mock and real detectors will differ in distribution**,
so swapping `IRA_DETECTOR__IMPL=mock` for `padim` is one line of config but is
NOT distribution-preserving.

An unexamined gap there would quietly invalidate every result built on mock data,
because the orchestrator's guard bands, the ambiguity construction, and the
oracle all live in confidence space. If real PaDiM confidences cluster at 0.99
and 0.01, our carefully constructed "weak anomalous at 0.55-0.75" band describes
nothing that ever happens, and the deceptive level stops being deceptive.

So: run this at M1, once calibrated detectors exist. Report the divergence in
EVAL.md whether it is large or small. If it is large, refit the bands in
`harness/synthetic.py`, bump HARNESS_VERSION, and regenerate every fixture.

Usage:
    python scripts/compare_score_distributions.py --calibrated-scores path.json

The input is whatever `detectors/calibration.py` emits: a JSON mapping of
source -> list of calibrated confidences over the held-out `calib` split.
"""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

from harness.synthetic import (
    STRONG_ANOMALOUS,
    STRONG_NORMAL,
    UNINFORMATIVE,
    WEAK_ANOMALOUS,
    WEAK_NORMAL,
    ScoreBand,
)

BANDS: dict[str, ScoreBand] = {
    "strong_anomalous": STRONG_ANOMALOUS,
    "weak_anomalous": WEAK_ANOMALOUS,
    "uninformative": UNINFORMATIVE,
    "weak_normal": WEAK_NORMAL,
    "strong_normal": STRONG_NORMAL,
}


def occupancy(confidences: list[float]) -> dict[str, float]:
    """What fraction of real scores falls in each synthetic band.

    The headline number. If `weak_anomalous` occupancy is near zero, our
    deceptive incidents are constructed in a region the real detector never
    visits, and the whole ambiguity design needs refitting.
    """
    if not confidences:
        return {name: 0.0 for name in BANDS}
    total = len(confidences)
    return {
        name: sum(1 for c in confidences if band.low <= c <= band.high) / total
        for name, band in BANDS.items()
    }


def describe(confidences: list[float]) -> dict[str, float]:
    ordered = sorted(confidences)
    n = len(ordered)
    return {
        "n": n,
        "mean": statistics.fmean(ordered),
        "stdev": statistics.stdev(ordered) if n > 1 else 0.0,
        "p05": ordered[int(0.05 * n)],
        "p50": ordered[n // 2],
        "p95": ordered[min(n - 1, int(0.95 * n))],
        "at_or_below_0.01": sum(1 for c in ordered if c <= 0.01) / n,
        "at_or_above_0.99": sum(1 for c in ordered if c >= 0.99) / n,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--calibrated-scores",
        type=Path,
        required=True,
        help="JSON: {source: [calibrated confidence, ...]} over the calib split",
    )
    parser.add_argument(
        "--min-band-occupancy",
        type=float,
        default=0.05,
        help="Fail if any band holds less than this share of real scores",
    )
    args = parser.parse_args()

    data = json.loads(args.calibrated_scores.read_text(encoding="utf-8"))

    print("Real calibrated confidence vs synthetic score bands\n")
    failures: list[str] = []

    for source, confidences in sorted(data.items()):
        stats = describe(confidences)
        print(f"--- {source}  (n={stats['n']})")
        print(
            f"    mean={stats['mean']:.3f}  sd={stats['stdev']:.3f}  "
            f"p05={stats['p05']:.3f}  p50={stats['p50']:.3f}  p95={stats['p95']:.3f}"
        )

        # Saturation is the specific failure that breaks the reference rule: a
        # detector pinned at 0 or 1 has its log-odds clamped, so every subset it
        # appears in is decided by the clamp rather than by the evidence.
        sat = stats["at_or_below_0.01"] + stats["at_or_above_0.99"]
        print(f"    saturated (<=0.01 or >=0.99): {sat:.1%}")
        if sat > 0.25:
            failures.append(
                f"{source}: {sat:.1%} of scores are saturated; calibration is "
                "not producing usable probabilities (PRD R7)"
            )

        print("    band occupancy:")
        for name, share in occupancy(confidences).items():
            flag = "  <-- LOW" if share < args.min_band_occupancy else ""
            print(f"      {name:18} {share:6.1%}{flag}")
            if share < args.min_band_occupancy:
                failures.append(
                    f"{source}: band '{name}' holds only {share:.1%} of real "
                    "scores; incidents constructed there do not resemble reality"
                )
        print()

    if failures:
        print("DIVERGENCE FOUND -- refit the bands in harness/synthetic.py,")
        print("bump HARNESS_VERSION, and regenerate every fixture:\n")
        for failure in failures:
            print(f"  * {failure}")
        return 1

    print("Synthetic bands are consistent with real detector output.")
    print("Record this result in EVAL.md either way -- a passed check is evidence.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
