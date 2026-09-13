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

from harness.replay import write_fixture
from harness.synthetic import SyntheticEventSource, no_oracle_rate
from schemas.incident import HARNESS_VERSION, Split

DEFAULT_OUT = Path(__file__).resolve().parent.parent / "eval" / "evalsets"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    source = SyntheticEventSource(seed=args.seed)
    suffix = "" if args.seed == 0 else f".seed{args.seed}"

    print(f"harness_version={HARNESS_VERSION} seed={args.seed}\n")

    for split in Split:
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

    print("\nFixtures are gitignored. Regenerate rather than commit them,")
    print("and bump HARNESS_VERSION if the generator changes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
