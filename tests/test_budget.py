"""Tests for domain-cost budget accounting (PRD S5.5a, S5.5b).

One test per decision the PRD left unspecified, plus the property that made
recalibrating the budget table necessary: a budget that never binds makes
"budget-aware orchestration" untestable.
"""

from __future__ import annotations

import pytest

from core.budget import (
    AdmissionOutcome,
    BudgetLedger,
    TerminalReason,
    assess_paths,
)
from core.config import Settings, Severity
from harness.reference_rule import DECLARED_COST_MS
from schemas.evidence import Source

A, V, T, M, ME = (
    Source.AUDIO,
    Source.VISION,
    Source.TELEMETRY,
    Source.MANUAL,
    Source.MEMORY,
)
TRIO = (A, V, T)
ALL = (A, V, T, M, ME)


def ledger(budget_ms: int, *, steps: int = 4) -> BudgetLedger:
    return BudgetLedger(
        budget_ms=budget_ms,
        budget_tokens=10_000,
        max_evidence_steps=steps,
        declared_costs=DECLARED_COST_MS,
    )


# --------------------------------------------------------------------------
# Composition: two ledgers that compose differently (PRD S5.5a)
# --------------------------------------------------------------------------


def test_parallel_latency_is_max_sequential_is_sum():
    """Wall-clock is what the supervisor waits for, so a parallel group costs its
    slowest member; tokens would sum, but tokens are never budgeted."""
    book = ledger(2_000)
    assert book.declared_cost(TRIO, parallel=True) == 350  # max(350, 200, 50)
    assert book.declared_cost(TRIO, parallel=False) == 600  # 350 + 200 + 50


def test_fast_path_uses_the_same_accounting():
    """DECISION 4: no exception for the fast path. Its cheapness is emergent
    from querying one source, not a privilege in the ledger, so a fast-path cost
    is directly comparable to a parallel one."""
    book = ledger(1_200)
    assert book.declared_cost((T,), parallel=False) == 50
    assert book.declared_cost((T,), parallel=True) == 50  # shape is irrelevant at n=1

    decision = book.request((T,))
    assert decision.admitted
    book.record((T,), measured_cost_ms=48)
    assert book.spent_ms == 48
    assert book.steps_used == 1, "the fast path consumes a step like anything else"


def test_measured_cost_is_debited_not_declared():
    """The orchestrator plans against declared cost; the ledger debits what
    happened. Their drift is a published result, not an error term."""
    book = ledger(1_200)
    book.request((V,))
    debit = book.record((V,), measured_cost_ms=161)  # real PaDiM measurement
    assert debit.declared_cost_ms == 200
    assert debit.measured_cost_ms == 161
    assert debit.drift_ms == -39
    assert book.spent_ms == 161


# --------------------------------------------------------------------------
# Decision 1: rejection with budget remaining is NOT exhaustion
# --------------------------------------------------------------------------


def test_no_affordable_source_is_distinct_from_exhaustion():
    """DECISION 1. Budget remains but nothing fits.

    250 ms budget, telemetry (50) gathered, 200 ms left. Audio costs 350 and
    manual 400, so neither is affordable -- but vision at 200 exactly fits, so we
    take it too, leaving 0... instead use a budget that strands the caller.
    """
    book = ledger(300)
    book.request((T,))
    book.record((T,), measured_cost_ms=50)  # 250 remains

    # Audio (350) and manual (400) are both unaffordable; vision (200) is not.
    assert book.affordable_sources((A, M)) == ()
    assert book.remaining_ms == 250, "budget REMAINS -- this is not exhaustion"

    reason = book.terminal_reason((A, M), resolved=False)
    assert reason is TerminalReason.NO_AFFORDABLE_SOURCE
    assert reason is not TerminalReason.BUDGET_EXHAUSTED


def test_exhaustion_is_reported_when_nothing_remains():
    book = ledger(400)
    book.request((A,))
    book.record((A,), measured_cost_ms=400)
    assert book.remaining_ms == 0
    assert book.terminal_reason(ALL, resolved=False) is TerminalReason.BUDGET_EXHAUSTED


def test_resolved_beats_every_exhaustion_reason():
    """Reaching an answer on the last affordable source is a success, not an
    exhaustion, and the log must not call it one."""
    book = ledger(50)
    book.request((T,))
    book.record((T,), measured_cost_ms=50)
    assert book.terminal_reason(ALL, resolved=True) is TerminalReason.RESOLVED


# --------------------------------------------------------------------------
# Decision 2: a rejected admission consumes an evidence step
# --------------------------------------------------------------------------


def test_rejection_consumes_a_step():
    """DECISION 2. Planning is not free, and this makes termination fall out of
    the existing bound instead of needing a second counter."""
    book = ledger(100, steps=4)
    before = book.steps_used

    decision = book.request((M,))  # 400 ms against 100
    assert decision.outcome is AdmissionOutcome.REJECTED_COST
    assert book.steps_used == before + 1


def test_repeated_unaffordable_requests_terminate_on_steps():
    """The guarantee decision 2 buys: a system that keeps proposing groups it
    cannot afford stops, rather than spinning forever."""
    book = ledger(10, steps=3)
    for _ in range(3):
        assert book.request((M,)).outcome is AdmissionOutcome.REJECTED_COST

    assert book.steps_remaining == 0
    assert book.request((M,)).outcome is AdmissionOutcome.REJECTED_STEPS
    assert book.terminal_reason(ALL, resolved=False) is TerminalReason.STEPS_EXHAUSTED


def test_re_requesting_a_gathered_source_does_not_consume_a_step():
    """PRD S11.3 forbids it, and it is a critic logic error rather than a budget
    event -- charging a step would hide the bug behind a plausible-looking
    termination."""
    book = ledger(1_200)
    book.request((T,))
    book.record((T,), measured_cost_ms=50)
    steps_after_real_work = book.steps_used

    decision = book.request((T,))
    assert decision.outcome is AdmissionOutcome.REJECTED_ALREADY_GATHERED
    assert book.steps_used == steps_after_real_work


# --------------------------------------------------------------------------
# Decision 3: all-or-nothing parallel admission, availability logged apart
# --------------------------------------------------------------------------


def test_parallel_group_is_all_or_nothing():
    """DECISION 3. A group that does not fit is rejected whole; the caller may
    re-plan something smaller, at the cost of another step."""
    book = ledger(250)
    decision = book.request(TRIO, parallel=True)  # max cost 350 > 250
    assert decision.outcome is AdmissionOutcome.REJECTED_COST
    assert "all-or-nothing" in decision.reason

    # A smaller group does fit, which is what re-planning looks like.
    assert book.request((V, T), parallel=True).admitted


def test_availability_is_separable_from_choice():
    """THE instrumentation that keeps the headline result interpretable.

    Without this, "the orchestrator prefers sequential under budget pressure" is
    unfalsifiable -- it could be policy, or parallel could never have been on the
    menu. With it, orchestrator BEHAVIOUR and admission MECHANISM are two
    different reported rates.
    """
    generous = assess_paths(ledger(1_200), TRIO)
    assert generous.parallel_available
    assert generous.parallel_declared_ms == 350

    tight = assess_paths(ledger(250), TRIO)
    assert not tight.parallel_available, "mechanism, not preference"
    assert tight.fast_available, "telemetry at 50 ms is still affordable"

    fields = tight.as_log_fields()
    assert fields["parallel_available"] is False
    assert fields["remaining_ms_at_decision"] == 250


def test_assessing_paths_does_not_consume_a_step():
    """Availability is a pure query. Charging for it would make logging the
    mechanism cost the thing being measured."""
    book = ledger(1_200)
    assess_paths(book, TRIO)
    assess_paths(book, TRIO)
    assert book.steps_used == 0


def test_snapshot_preserves_rejection_counts():
    """Analysis must distinguish 'chose not to' from 'could not' without
    re-running anything."""
    book = ledger(250)
    book.request(TRIO, parallel=True)  # rejected
    book.request((T,))
    book.record((T,), measured_cost_ms=50)

    snap = book.snapshot()
    assert snap["n_rejected_cost"] == 1
    assert snap["gathered"] == ["telemetry"]
    assert snap["spent_ms"] == 50


# --------------------------------------------------------------------------
# The reason the budget table was recalibrated (PRD v1.5)
# --------------------------------------------------------------------------


def test_overspend_is_bounded_by_one_groups_drift():
    """Admission control, not interruption: an in-flight call is never killed, so
    spend can exceed the budget by at most one group's declared-to-measured
    drift. The report states that bound, so it is asserted here."""
    book = ledger(400)
    assert book.request((M,)).admitted  # declares exactly 400
    book.record((M,), measured_cost_ms=520)  # ran over

    assert book.spent_ms == 520
    assert book.remaining_ms == 0, "remaining never goes negative"
    assert book.debits[0].drift_ms == 120


@pytest.mark.parametrize("severity", list(Severity))
def test_no_severity_tier_permits_the_exhaustive_sweep(severity):
    """THE regression test for an inert budget.

    The v1.1 placeholder table (8000/4000/1500 ms) made the budget unable to bind
    at all: querying EVERY source costs 1,050 ms, so even the tightest tier had
    1.4x headroom over the absolute worst case. Admission control could never
    reject, budget_exhausted could never fire, and the project's central claim
    was untestable -- an examiner asking to see an incident where the budget
    changed the decision would have had nothing to show.
    """
    budget_ms = Settings().budget.table[severity].budget_ms
    everything = sum(DECLARED_COST_MS[s] for s in ALL)
    assert budget_ms < everything, (
        f"{severity.value} budget {budget_ms} ms admits all five sources "
        f"({everything} ms): the budget cannot bind and admission control is "
        "dead code"
    )


def test_each_tier_binds_differently():
    """A tier structure that forbids nothing distinct would make severity
    classification decorative."""
    table = Settings().budget.table
    parallel_trio = 350
    sequential_trio = 600

    low = table[Severity.LOW].budget_ms
    standard = table[Severity.STANDARD].budget_ms
    critical = table[Severity.CRITICAL].budget_ms

    # low: the tier where admission control forces sequential investigation.
    assert low < parallel_trio, "low must make the parallel path unavailable"
    assert low >= DECLARED_COST_MS[T], "low must still afford the cheapest source"

    # standard: binds exactly at the sequential trio, so a fourth source cannot
    # be added and budget exhaustion is reachable.
    assert standard >= sequential_trio
    assert standard < sequential_trio + DECLARED_COST_MS[M]

    # critical: generous, but still refuses everything.
    assert critical > standard


# --------------------------------------------------------------------------
# The low tier's policy meaning, and observability of free rejections
# --------------------------------------------------------------------------


def test_low_tier_is_cheap_investigation_not_no_investigation():
    """A deliberate policy decision, asserted because the two are very different
    results tables and the tier's NAME implies the first.

    At 250 ms, low affords telemetry (50), vision (200), and the pair at exactly
    250, rejecting only audio (350) and manual (400). A low-severity incident
    gathers two of three sensors and reaches a real verdict -- it does not
    terminate with zero evidence.
    """
    low_ms = Settings().budget.table[Severity.LOW].budget_ms
    book = ledger(low_ms)

    assert book.affordable_sources(TRIO), "low must afford at least one sensor"
    assert set(book.affordable_sources(TRIO)) == {T, V}
    assert book.can_afford((T, V), parallel=False), "the cheap pair must fit"
    assert not book.can_afford((A,), parallel=False), "audio must be out of reach"


def test_low_tier_gathers_then_strands_on_the_expensive_source():
    """The intended trajectory: investigate cheaply, then stop."""
    book = ledger(Settings().budget.table[Severity.LOW].budget_ms)
    for source in (T, V):
        assert book.request((source,)).admitted
        book.record((source,), measured_cost_ms=DECLARED_COST_MS[source])

    assert set(book.gathered) == {T, V}
    assert book.request((A,)).outcome is AdmissionOutcome.REJECTED_COST
    assert book.remaining_ms == 0


def test_duplicate_requests_are_counted_even_though_they_are_free():
    """A silent no-op is how we would fail to notice the critic re-requesting
    sources constantly. Non-zero here is a CRITIC BUG, not a budget event."""
    book = ledger(900)
    book.request((T,))
    book.record((T,), measured_cost_ms=50)

    for _ in range(3):
        book.request((T,))

    assert book.duplicate_requests == 3
    assert book.steps_used == 1, "duplicates still cost no step"
    assert book.snapshot()["n_rejected_duplicate"] == 3


def test_budget_table_version_is_frozen_and_exported():
    """Frozen before any eval run. A later change must bump this string, so a
    results table can never silently refer to a different cost policy."""
    from core.config import BUDGET_TABLE_VERSION

    assert BUDGET_TABLE_VERSION == "budget-v1"
