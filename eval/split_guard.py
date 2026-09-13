"""Refuse to compute reported results over a non-representative split.

The constructed demo split (harness/demo_builder.py) is hand-built for scenario
COVERAGE, not representativeness: it deliberately over-represents Tier 3 blocks
and repeat-offender chains so the demo can show every path. Aggregating over it
would produce numbers that look like results and describe nothing.

So every results-producing code path calls `assert_reportable()` first. Same class
of protection as the token-ledger regression test: a guard that makes a known
footgun impossible rather than merely documented.
"""

from __future__ import annotations

from schemas.incident import IncidentRecord, Split

CONSTRUCTED_ID_PREFIX = "demo_"
"""Constructed incidents are labelled by scenario (demo_d_tier3_block), never by
index, so they are identifiable even if the split field were wrong."""


class NonReportableSplitError(RuntimeError):
    """Raised when a results computation is handed the demo split."""


def is_constructed(record: IncidentRecord) -> bool:
    return record.split is Split.DEMO or record.incident_id.startswith(
        CONSTRUCTED_ID_PREFIX
    )


def assert_reportable(records: list[IncidentRecord], *, context: str) -> None:
    """Fail loudly if any record may not appear in a reported table.

    Call this at the TOP of anything that aggregates -- before the expensive work,
    so the failure is cheap and unambiguous.
    """
    offenders = [r.incident_id for r in records if is_constructed(r)]
    if offenders:
        raise NonReportableSplitError(
            f"{context}: refusing to aggregate over the constructed demo split.\n"
            f"  offending incidents: {offenders[:5]}"
            f"{' ...' if len(offenders) > 5 else ''}\n"
            "  The demo split is hand-built for scenario coverage and deliberately\n"
            "  over-represents rare paths (Tier 3 blocks, repeat-offender chains).\n"
            "  Aggregates over it would look like results and mean nothing.\n"
            "  Use the test split for reported numbers, dev for iteration."
        )
