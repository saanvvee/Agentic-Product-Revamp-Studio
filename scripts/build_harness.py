"""Generate the incident fixtures that eval runs replay.

Generation is where randomness lives; replay has none. Every reported result
therefore refers to one specific frozen file whose harness_version and
reference_rule_version are recorded in every row (PRD S7.5b, R23).

Usage:
    python scripts/build_harness.py                 # all splits, seed 0
    python scripts/build_harness.py --seed 1        # a variance run
"""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

from harness.demo_builder import DEMO_FIXTURE_NAME, build_demo_incidents
from harness.replay import write_fixture
from harness.synthetic import (
    INCIDENT_SPACING_HOURS,
    SyntheticEventSource,
    no_oracle_rate,
)
from schemas.incident import HARNESS_VERSION, Split

DEFAULT_OUT = Path(__file__).resolve().parent.parent / "eval" / "evalsets"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    source = SyntheticEventSource(seed=args.seed)
    suffix = "" if args.seed == 0 else f".seed{args.seed}"

    print(
        f"harness_version={HARNESS_VERSION} seed={args.seed} "
        f"spacing={INCIDENT_SPACING_HOURS}h\n"
    )

    for split in Split:
        if split is Split.DEMO:
            # The SAMPLED demo split cannot reach Scenario D (PRD S7.7): 8
            # incidents across 3 machines can never accumulate the two prior
            # confirmed faults the Tier 3 gate needs. The constructed split is
            # written separately below.
            continue

        path = args.out_dir / f"incidents.{split.value}{suffix}.jsonl"
        written = write_fixture(source.events(split), path)

        records = list(source.events(split))
        levels = Counter(r.ambiguity_level.value for r in records)
        rate = no_oracle_rate(source, split)

        print(f"{split.value:5} n={written:3} -> {path.name}")
        print(f"      levels: {dict(levels)}")
        print(f"      anomalous: {sum(r.is_anomalous for r in records) / written:.1%}")
        # Printed every run, not buried in a test: if this drifts out of the
        # 5-10% band, escalation precision loses its hardest cases (PRD S12.1).
        #
        # The band is only meaningful once n is large enough for one incident to
        # be worth less than the band's width. At n=8 a single unresolvable
        # incident is 12.5%, so reporting "out of band" there would be noise
        # dressed as a warning -- the demo split is hand-sized for the five
        # scenarios in S3.2 and is never used for reported rates.
        if written < 30:
            flag = f"n too small to assess ({written} incidents)"
        elif 0.05 <= rate <= 0.10:
            flag = "OK"
        else:
            flag = "OUT OF TARGET BAND"
        print(f"      no-oracle rate: {rate:.1%}  [{flag}]")

    demo_path = args.out_dir / DEMO_FIXTURE_NAME
    written = write_fixture(build_demo_incidents(seed=args.seed), demo_path)
    print(f"demo  n={written:3} -> {demo_path.name}  [CONSTRUCTED]")
    print("      hand-built for scenario coverage, never used for reported")
    print("      results; eval/split_guard.py refuses to aggregate over it.")

    print("\nFixtures ARE committed, deliberately: PRD S7.5b requires every")
    print("reported result to replay one specific frozen file, and they hold no")
    print("dataset bytes -- only paths, labels, scores, and the oracle.")
    print("Bump HARNESS_VERSION when the generator changes, and commit the")
    print("regenerated fixtures in the same commit as the generator change.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
